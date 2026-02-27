"""
chat.py  —  RAG chat engine for "chat with a GitHub repo".

Architecture:
  1. User sends a question + repo_name
  2. Embed the question with both ST models (text + code)
  3. Query both Endee indexes (text_<repo> and code_<repo>) in parallel
  4. De-duplicate, rank by similarity, keep top-K snippets
  5. Feed question + snippets as context to Groq LLM
  6. Stream the answer back token-by-token via SSE

The chat engine is stateless — conversation history is passed in by the
caller (the API keeps it in memory per session_id).
"""
from __future__ import annotations

import os
from typing import Generator

from utils.helpers import (
    get_endee_client,
    get_embeddings,
    get_code_embeddings,
    groq_chat,
    get_groq_client,
    truncate,
    slugify,
)

TOP_K_PER_INDEX = 5     # snippets retrieved from each index per question
EF              = 128   # Endee HNSW search quality
MAX_CONTEXT_CHARS = 6000  # total chars of retrieved snippets fed to LLM

SYSTEM_PROMPT = """\
You are an expert software engineer assistant. You have deep knowledge of the
GitHub repository the user is asking about, obtained by analysing its source
code and documentation.

When answering:
- Be precise and technical — the user is a developer.
- Always cite the specific file(s) your answer is drawn from.
- If the retrieved context does not contain enough information to answer
  confidently, say so rather than guessing.
- Use markdown formatting for code blocks and file paths.
- Keep answers focused and under 400 words unless the question demands more.
"""

# RAG RETRIEVAL USING ENDEE VECTOR DB:

def retrieve(
    question: str,
    repo_name: str,
    endee_url: str | None = None,
    top_k: int = TOP_K_PER_INDEX,
) -> list[dict]:
    """
    Retrieve the most relevant code and text snippets for a question.

    Returns a list of dicts: {source, file, text, similarity}
    sorted by descending similarity.
    """
    client     = get_endee_client(endee_url)
    slug       = slugify(repo_name)
    code_index = f"code_{slug}"
    text_index = f"text_{slug}"

    # Embed the question with both model flavours
    text_vec = get_embeddings([question])[0]
    code_vec = get_code_embeddings([question])[0]

    results: list[dict] = []

    for index_name, vec, source in [
        (code_index, code_vec, "code"),
        (text_index, text_vec, "text"),
    ]:
        try:
            index = client.get_index(name=index_name)
            hits  = index.query(vector=vec, top_k=top_k, ef=EF)
        except Exception as e:
            print(f"  [chat/retrieve] {index_name} query failed: {e}")
            continue

        for hit in hits:
            meta = hit.get("meta", {})
            results.append({
                "source":     source,
                "file":       meta.get("file", "unknown"),
                "text":       meta.get("text", ""),
                "similarity": round(hit.get("similarity", 0.0), 4),
            })

    # De-duplicate keeping highest similarity per (file, text_prefix)
    seen: dict[tuple, dict] = {}
    for item in results:
        key = (item["file"], item["text"][:120])
        if key not in seen or item["similarity"] > seen[key]["similarity"]:
            seen[key] = item

    ranked = sorted(seen.values(), key=lambda x: -x["similarity"])
    return ranked


def _build_context(snippets: list[dict]) -> str:
    """Format retrieved snippets into a compact context block for the LLM."""
    parts = []
    total = 0
    for s in snippets:
        chunk = f"[{s['source'].upper()} | {s['file']} | sim={s['similarity']}]\n{s['text']}"
        if total + len(chunk) > MAX_CONTEXT_CHARS:
            break
        parts.append(chunk)
        total += len(chunk)
    return "\n\n---\n\n".join(parts)



def answer(
    question: str,
    repo_name: str,
    history: list[dict] | None = None,
    endee_url: str | None = None,
    groq_model: str = "llama-3.3-70b-versatile",
) -> tuple[str, list[dict]]:
    """
    Answer a question about a repo using RAG.

    Args:
        question   : the user's question
        repo_name  : e.g. "tiangolo/fastapi"
        history    : list of {role, content} prior messages (for multi-turn)
        endee_url  : optional custom Endee base URL
        groq_model : Groq model to use

    Returns:
        (answer_text, snippets_used)
    """
    snippets = retrieve(question, repo_name, endee_url=endee_url)
    context  = _build_context(snippets)

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    if history:
        messages.extend(history[-12:])

    messages.append({
        "role": "user",
        "content": (
            f"Repository: {repo_name}\n\n"
            f"Retrieved context:\n{context}\n\n"
            f"Question: {question}"
        ),
    })

    response = groq_chat(
        messages=messages,
        model=groq_model,
        temperature=0.2,
        max_tokens=1024,
    )

    return response, snippets



def answer_stream(
    question: str,
    repo_name: str,
    history: list[dict] | None = None,
    endee_url: str | None = None,
    groq_model: str = "llama-3.3-70b-versatile",
) -> Generator[str, None, None]:
    """
    Stream the answer token-by-token as a generator of SSE-formatted strings.

    Yields strings in the format:
        "data: <token>\n\n"
    with a final:
        "data: [DONE]\n\n"
    """
    snippets = retrieve(question, repo_name, endee_url=endee_url)
    context  = _build_context(snippets)

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-12:])
    messages.append({
        "role": "user",
        "content": (
            f"Repository: {repo_name}\n\n"
            f"Retrieved context:\n{context}\n\n"
            f"Question: {question}"
        ),
    })

    client = get_groq_client()
    stream = client.chat.completions.create(
        model=groq_model,
        messages=messages,
        temperature=0.2,
        max_tokens=1024,
        stream=True,
    )

    citations = [{"file": s["file"], "source": s["source"], "similarity": s["similarity"]}
                 for s in snippets[:8]]
    import json
    yield f"event: citations\ndata: {json.dumps(citations)}\n\n"

    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield f"data: {delta.replace(chr(10), '<br>')}\n\n"

    yield "data: [DONE]\n\n"
