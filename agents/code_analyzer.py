"""
agents/code_analyzer.py
Node: code_analyzer_node

Walks the cloned repository, reads source-code files, splits them into
chunks, embeds each chunk with a code-optimised embedding model, and
upserts all vectors into a dedicated Endee index.

Also asks an LLM for a high-level structural summary of the codebase.

Populates state:
  - code_chunks      : list of chunk dicts (file, chunk_id, text, embedding)
  - code_index_name  : name of the Endee index
  - code_summary     : LLM-generated structural summary
"""
from __future__ import annotations
import os
from pathlib import Path

from state import RepoState
from utils.helpers import (
    get_endee_client, ensure_index,
    get_code_embeddings, chunk_code,
    stable_id, truncate, slugify,
)

# ── Config ────────────────────────────────────────────────────────────────────

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".kt", ".go", ".rs", ".cpp", ".c", ".h",
    ".cs", ".rb", ".php", ".swift", ".scala",
    ".sh", ".bash", ".yaml", ".yml", ".toml", ".json",".ipynb"
}

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "coverage",
    "migrations", "fixtures",
}

SKIP_FILES = {"package-lock.json", "yarn.lock", "poetry.lock", "Pipfile.lock"}

MAX_FILE_BYTES = 200_000   # skip very large generated files
EMBEDDING_DIM   = 768      # matches microsoft/codebert-base output
BATCH_SIZE      = 32       # chunks per encode() call


# ── Node ──────────────────────────────────────────────────────────────────────

def code_analyzer_node(state: RepoState) -> RepoState:
    local_path: str = state["local_path"]
    repo_name:  str = state["repo_name"]
    endee_url       = state.get("_endee_base_url")
    llm_model: str  = state.get("_groq_model", "llama-3.3-70b-versatile")

    index_name = f"code_{slugify(repo_name)}"
    print(f"  [code] Scanning source files …")

    # ── 1. Walk and collect source files ─────────────────────────────────────
    source_files: list[tuple[str, str]] = []   # (relative_path, content)
    for root, dirs, files in os.walk(local_path):
        # Prune unwanted dirs in-place
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for fname in files:
            if fname in SKIP_FILES:
                continue
            ext = Path(fname).suffix.lower()
            if ext not in CODE_EXTENSIONS:
                continue
            full_path = os.path.join(root, fname)
            if os.path.getsize(full_path) > MAX_FILE_BYTES:
                continue
            rel_path = os.path.relpath(full_path, local_path)
            try:
                content = Path(full_path).read_text(errors="replace")
            except OSError:
                continue
            source_files.append((rel_path, content))

    print(f"  [code] Found {len(source_files)} source files")

    # ── 2. Chunk all files ───────────────────────────────────────────────────
    raw_chunks: list[dict] = []
    for rel_path, content in source_files:
        for chunk_text in chunk_code(content):
            raw_chunks.append({
                "file": rel_path,
                "chunk_id": stable_id(rel_path.replace("/", "_"), chunk_text),
                "text": chunk_text,
            })

    print(f"  [code] Generated {len(raw_chunks)} chunks")

    # ── 3. Embed all chunks (SentenceTransformer batches internally) ─────────
    texts = [c["text"] for c in raw_chunks]
    all_embeddings = get_code_embeddings(texts)

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
            "filter": {"type": "code", "file": c["file"]},
        }
        for c in raw_chunks
    ]

    # Upsert in batches of 100
    for i in range(0, len(vectors), 100):
        index.upsert(vectors[i : i + 100])

    print(f"  [code] Upserted {len(vectors)} vectors into Endee index '{index_name}'")

    # ── 5. LLM structural summary ────────────────────────────────────────────
    # Feed a representative sample (first 20 files) to the LLM
    sample_content = "\n\n".join(
        f"### {fp}\n```\n{truncate(content, 800)}\n```"
        for fp, content in source_files[:20]
    )

    from utils.helpers import groq_chat
    code_summary = groq_chat(
        model=llm_model,
        temperature=0.2,
        max_tokens=600,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a senior software architect. "
                    "Analyse the provided source files and produce a concise structural summary. "
                    "Cover: language(s), primary frameworks, module layout, main abstractions, "
                    "and key design patterns. Be precise, technical, and under 400 words."
                ),
            },
            {
                "role": "user",
                "content": f"Repository: {repo_name}\n\n{sample_content}",
            },
        ],
    )
    print(f"  [code] Generated structural summary")

    return {
        "code_chunks": raw_chunks,
        "code_index_name": index_name,
        "code_summary": code_summary,
    }
