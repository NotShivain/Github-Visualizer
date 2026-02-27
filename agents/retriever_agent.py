"""
agents/retriever_agent.py
Node: retriever_node

Issues a set of targeted queries against both Endee indexes
(code + text) to retrieve the most relevant snippets for the final
synthesis step.

Queries are derived from the summaries produced by the upstream nodes
so that we focus on the aspects the LLM already highlighted as important.

Populates state:
  - retrieved_snippets : list of {source, file, text, similarity} dicts
"""
from __future__ import annotations

from state import RepoState
from utils.helpers import (
    get_endee_client, get_embeddings, get_code_embeddings,
)

TOP_K       = 5    # per query
EF          = 128  # Endee search quality
MAX_QUERIES = 6    # total queries (budget control)


def _build_queries(state: RepoState) -> list[tuple[str, str]]:
    """
    Build a list of (query_text, index_type) tuples.
    index_type ∈ {"code", "text"}
    """
    code_summary: str = state.get("code_summary", "")
    readme_summary: str = state.get("readme_summary", "")
    dep_summary: str = state.get("dependency_summary", "")
    entry_points: list[str] = state.get("entry_points", [])

    queries = []

    # Always include a broad "what does this repo do" query against text
    queries.append(("What is this project about and what are its main features?", "text"))

    # Entry-point code retrieval
    if entry_points:
        ep = entry_points[0]
        queries.append((f"main entry point startup initialisation {ep}", "code"))

    # Use sentences from the code summary as code-side queries
    if code_summary:
        # Take first two sentences
        sentences = [s.strip() for s in code_summary.split(".") if len(s.strip()) > 20][:2]
        for s in sentences:
            queries.append((s, "code"))

    # Documentation queries from README summary
    if readme_summary:
        sentences = [s.strip() for s in readme_summary.split(".") if len(s.strip()) > 20][:2]
        for s in sentences:
            queries.append((s, "text"))

    # Dependency-level query
    if dep_summary:
        queries.append((dep_summary[:200], "code"))

    return queries[:MAX_QUERIES]


def retriever_node(state: RepoState) -> RepoState:
    endee_url   = state.get("_endee_base_url")
    code_index  = state.get("code_index_name", "")
    text_index  = state.get("text_index_name", "")

    client = get_endee_client(endee_url)
    queries = _build_queries(state)

    print(f"  [retriever] Running {len(queries)} Endee queries …")

    retrieved: list[dict] = []

    for query_text, index_type in queries:
        index_name = code_index if index_type == "code" else text_index
        if not index_name:
            continue

        try:
            index = client.get_index(name=index_name)
        except Exception as e:
            print(f"  [retriever] Warning — could not open index {index_name}: {e}")
            continue

        # Embed the query
        if index_type == "code":
            q_vec = get_code_embeddings([query_text])[0]
        else:
            q_vec = get_embeddings([query_text])[0]

        try:
            results = index.query(vector=q_vec, top_k=TOP_K, ef=EF)
        except Exception as e:
            print(f"  [retriever] Query failed for '{query_text[:60]}': {e}")
            continue

        for item in results:
            meta = item.get("meta", {})
            retrieved.append({
                "source":     index_type,
                "file":       meta.get("file", "unknown"),
                "text":       meta.get("text", ""),
                "similarity": round(item.get("similarity", 0.0), 4),
                "query":      query_text[:80],
            })

    # De-duplicate by (file, text) keeping highest similarity
    seen: dict[tuple, dict] = {}
    for item in retrieved:
        key = (item["file"], item["text"][:100])
        if key not in seen or item["similarity"] > seen[key]["similarity"]:
            seen[key] = item

    unique = sorted(seen.values(), key=lambda x: -x["similarity"])
    print(f"  [retriever] Retrieved {len(unique)} unique snippets")

    return {"retrieved_snippets": unique}
