"""
agents/text_analyzer.py
Node: text_analyzer_node

Finds README files, Markdown documentation, and plain-text notes inside
the repository. Chunks, embeds, and upserts them into a dedicated Endee
text index. Also generates a concise README / docs summary via LLM.

Populates state:
  - text_chunks      : list of chunk dicts (file, chunk_id, text, embedding)
  - text_index_name  : name of the Endee index for text
  - readme_summary   : LLM-generated summary of README and docs
"""
from __future__ import annotations
import os
from pathlib import Path

from state import RepoState
from utils.helpers import (
    get_endee_client, ensure_index,
    get_embeddings, chunk_text,
    stable_id, truncate, slugify,
)

TEXT_EXTENSIONS = {".md", ".rst", ".txt", ".adoc", ".wiki"}
SKIP_DIRS       = {".git", "node_modules", "__pycache__", ".venv", "venv"}
MAX_FILE_BYTES  = 500_000
EMBEDDING_DIM   = 768      # matches all-mpnet-base-v2 output
BATCH_SIZE      = 32


def text_analyzer_node(state: RepoState) -> RepoState:
    local_path: str = state["local_path"]
    repo_name:  str = state["repo_name"]
    endee_url       = state.get("_endee_base_url")
    llm_model: str  = state.get("_groq_model", "llama-3.3-70b-versatile")

    index_name = f"text_{slugify(repo_name)}"
    print(f"  [text] Scanning documentation files …")

    # ── 1. Collect text files ─────────────────────────────────────────────────
    text_files: list[tuple[str, str]] = []
    for root, dirs, files in os.walk(local_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for fname in files:
            ext = Path(fname).suffix.lower()
            if ext not in TEXT_EXTENSIONS:
                continue
            full_path = os.path.join(root, fname)
            if os.path.getsize(full_path) > MAX_FILE_BYTES:
                continue
            rel_path = os.path.relpath(full_path, local_path)
            try:
                content = Path(full_path).read_text(errors="replace")
            except OSError:
                continue
            text_files.append((rel_path, content))

    # Ensure README is first for the LLM prompt
    text_files.sort(key=lambda x: (0 if "readme" in x[0].lower() else 1, x[0]))
    print(f"  [text] Found {len(text_files)} documentation files")

    # ── 2. Chunk ─────────────────────────────────────────────────────────────
    raw_chunks: list[dict] = []
    for rel_path, content in text_files:
        for ct in chunk_text(content, chunk_size=300, overlap=40):
            raw_chunks.append({
                "file":     rel_path,
                "chunk_id": stable_id(rel_path.replace("/", "_"), ct),
                "text":     ct,
            })

    print(f"  [text] Generated {len(raw_chunks)} text chunks")

    # ── 3. Embed all chunks (SentenceTransformer batches internally) ─────────
    texts        = [c["text"] for c in raw_chunks]
    all_embeddings = get_embeddings(texts)

    for chunk, emb in zip(raw_chunks, all_embeddings):
        chunk["embedding"] = emb

    # ── 4. Upsert to Endee ───────────────────────────────────────────────────
    client = get_endee_client(endee_url)
    index  = ensure_index(client, index_name, dimension=EMBEDDING_DIM)

    vectors = [
        {
            "id":     c["chunk_id"],
            "vector": c["embedding"],
            "meta":   {"file": c["file"], "text": c["text"][:500]},
            "filter": {"type": "text", "file": c["file"]},
        }
        for c in raw_chunks
    ]
    for i in range(0, len(vectors), 100):
        index.upsert(vectors[i : i + 100])

    print(f"  [text] Upserted {len(vectors)} vectors into Endee index '{index_name}'")

    # ── 5. LLM documentation summary ─────────────────────────────────────────
    combined_docs = "\n\n---\n\n".join(
        f"**{fp}**\n\n{truncate(content, 2000)}"
        for fp, content in text_files[:5]    # top 5 docs
    )

    from utils.helpers import groq_chat
    readme_summary = groq_chat(
        model=llm_model,
        temperature=0.2,
        max_tokens=600,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a technical writer. Summarise the provided README and "
                    "documentation for a software project. "
                    "Cover: purpose, key features, architecture overview, setup, and usage. "
                    "Be clear, accurate, and under 400 words."
                ),
            },
            {
                "role": "user",
                "content": f"Repository: {repo_name}\n\n{combined_docs or 'No documentation found.'}",
            },
        ],
    )
    print(f"  [text] Generated README / docs summary")

    return {
        "text_chunks":     raw_chunks,
        "text_index_name": index_name,
        "readme_summary":  readme_summary,
    }
