"""
agents/flowchart_agent.py
Node: flowchart_node
"""
from __future__ import annotations
import re

from state import RepoState
from utils.helpers import truncate


SYSTEM_PROMPT = """\
You are an expert software visualisation engineer producing a Mermaid flowchart.

STRICT MERMAID SYNTAX RULES — follow exactly or the diagram will not render:

1. EDGES — only these forms are valid:
     A --> B
     A -->|label| B
   NEVER:  A -->|label|> B
   NEVER:  A -- label --> B

2. NODE IDs must start with a LETTER and contain only letters, digits, underscores.

3. NODE LABELS go inside brackets:
     app_py[app.py]

4. SUBGRAPHS must ALWAYS have a matching `end`.

5. No duplicate node definitions. No self-loops (A --> A).

6. Output ONLY raw Mermaid starting with `flowchart TD`.
"""


def _sanitize_mermaid(code: str) -> str:
    """Fix common LLM Mermaid syntax mistakes and enforce structural safety."""

    # Remove markdown fences
    code = re.sub(r'^```(?:mermaid)?\s*', '', code, flags=re.MULTILINE)
    code = re.sub(r'```\s*$', '', code, flags=re.MULTILINE)
    code = code.strip()

    # Ensure diagram starts properly
    if not re.match(r'^flowchart\s', code):
        code = 'flowchart TD\n' + code

    lines = code.splitlines()

    sanitized = []
    seen_lines: set[str] = set()

    subgraph_depth = 0

    for line in lines:
        original_line = line
        line = line.rstrip()

        # ---------- SYNTAX FIXES ----------

        # Fix -->|label|> Target
        line = re.sub(r'(\|[^|]*)\|>\s*', r'\1| ', line)

        # Fix A -- label --> B
        line = re.sub(
            r'(\w+)\s+--\s+([^-]+?)\s+-->\s+(\w+)',
            lambda m: f'{m.group(1)} -->|{m.group(2).strip()}| {m.group(3)}',
            line,
        )

        # Fix A ==label==> B
        line = re.sub(
            r'(\w+)\s*==([^=]+)==>\s*(\w+)',
            lambda m: f'{m.group(1)} -->|{m.group(2).strip()}| {m.group(3)}',
            line,
        )

        # Fix numeric node IDs
        line = re.sub(
            r'(?<![\w"])(\d+\w*)\s*(-->|\[)',
            r'n_\1 \2',
            line,
        )

        stripped = line.strip()

        # ---------- SUBGRAPH STRUCTURE HANDLING ----------

        if re.match(r'^subgraph\b', stripped):

            # If a previous subgraph is open at same level,
            # auto-close it before opening new one
            if subgraph_depth > 0:
                sanitized.append("    end")
                subgraph_depth -= 1

            subgraph_depth += 1
            sanitized.append(line)
            continue

        elif stripped == "end":

            if subgraph_depth > 0:
                subgraph_depth -= 1
                sanitized.append("    end")
            # If no subgraph open, ignore stray end
            continue

        # ---------- DEDUPLICATION ----------
        # Do NOT deduplicate 'end'
        if stripped and stripped != "end":
            if stripped in seen_lines:
                continue
            seen_lines.add(stripped)

        sanitized.append(line)

    # ---------- FINAL STRUCTURE BALANCING ----------
    # Close any remaining unclosed subgraphs
    while subgraph_depth > 0:
        sanitized.append("end")
        subgraph_depth -= 1

    return "\n".join(sanitized)


def flowchart_node(state: RepoState) -> RepoState:
    repo_name:    str  = state["repo_name"]
    llm_model:    str  = state.get("_groq_model", "llama-3.3-70b-versatile")
    explanation:  str  = state.get("explanation", "")
    code_summary: str  = state.get("code_summary", "")
    dep_summary:  str  = state.get("dependency_summary", "")
    entry_points: list = state.get("entry_points", [])
    dep_graph:    dict = state.get("dependency_graph", {})

    print("  [flow] Generating Mermaid flowchart ...")

    internal_deps = {
        k: [v for v in vals if not v.startswith(
            ("http", "os", "sys", "re", "json", "math", "typing",
             "collections", "itertools", "functools", "pathlib")
        )]
        for k, vals in list(dep_graph.items())[:40]
    }

    dep_lines = "\n".join(
        f"{k} -> {', '.join(v)}"
        for k, v in internal_deps.items() if v
    )

    user_content = f"""\
Repository: {repo_name}

Entry Points: {", ".join(entry_points) if entry_points else "unknown"}

Code Summary:
{truncate(code_summary, 800)}

Dependency Summary:
{truncate(dep_summary, 600)}

Key Explanation Excerpt:
{truncate(explanation, 1200)}

Internal Dependency Edges (file -> imported modules):
{truncate(dep_lines, 1500) or "(none detected)"}

REMINDER: Every subgraph MUST have a closing `end`.
"""

    from utils.helpers import groq_chat

    raw = groq_chat(
        model=llm_model,
        temperature=0.1,
        max_tokens=1200,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
    )

    mermaid_code = _sanitize_mermaid(raw)

    print(f"  [flow] Mermaid diagram generated ({len(mermaid_code.splitlines())} lines)")

    return {"mermaid_code": mermaid_code}