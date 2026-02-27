"""
state.py  —  Typed state shared across all LangGraph nodes.
"""
from __future__ import annotations
from typing import Any, Optional
from typing_extensions import TypedDict


class RepoState(TypedDict, total=False):
    # ── Input ────────────────────────────────────────────────────────────────
    repo_url: str            # Original GitHub URL
    output_dir: str          # Where to write results

    # ── Internal config (injected by pipeline.py) ───────────────────────────
    _openai_model: str
    _endee_base_url: Optional[str]

    # ── Clone node ───────────────────────────────────────────────────────────
    local_path: str          # Absolute path to cloned repository
    repo_name: str           # "owner/repo"
    default_branch: str

    # ── Code analyzer node ───────────────────────────────────────────────────
    code_chunks: list[dict[str, Any]]   # [{file, chunk_id, text, embedding}, ...]
    code_index_name: str                # Endee index name for code embeddings
    code_summary: str                   # LLM-generated structural summary

    # ── Text analyzer node ───────────────────────────────────────────────────
    text_chunks: list[dict[str, Any]]   # [{file, chunk_id, text, embedding}, ...]
    text_index_name: str                # Endee index name for text embeddings
    readme_summary: str                 # LLM summary of README / docs

    # ── Dependency analyzer node ─────────────────────────────────────────────
    dependency_graph: dict[str, list[str]]   # {module: [imports]}
    entry_points: list[str]                  # Detected main entry-point files
    dependency_summary: str

    # ── Retriever node ───────────────────────────────────────────────────────
    retrieved_snippets: list[dict[str, Any]] # Top-k snippets from Endee queries

    # ── Synthesizer node ─────────────────────────────────────────────────────
    explanation: str         # Full markdown explanation

    # ── Flowchart node ───────────────────────────────────────────────────────
    mermaid_code: str        # Raw Mermaid diagram definition

    # ── Renderer node ────────────────────────────────────────────────────────
    explanation_path: str    # Path to saved explanation.md
    mermaid_path: str        # Path to saved flowchart.mmd
    flowchart_path: str      # Path to saved flowchart.html (rendered)
