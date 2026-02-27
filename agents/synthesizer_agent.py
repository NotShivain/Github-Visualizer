"""
agents/synthesizer_agent.py
Node: synthesizer_node

Combines all upstream summaries and retrieved snippets into a rich
Markdown explanation of the repository: purpose, architecture, code
structure, data-flow, and key implementation details.

Populates state:
  - explanation : full Markdown string
"""
from __future__ import annotations
import json

from state import RepoState
from utils.helpers import truncate


SYSTEM_PROMPT = """\
You are an expert software engineer and technical writer.
Your task is to produce a **comprehensive yet readable Markdown explanation**
of a GitHub repository based on structured analysis data provided to you.

The explanation must include:

1. **Project Overview** — what the project does, its purpose, and target users.
2. **Technology Stack** — languages, frameworks, major libraries.
3. **Architecture & Design Patterns** — high-level structure, layers, patterns used.
4. **Key Modules & Components** — what each major file / package does.
5. **Data Flow** — how data moves through the system end-to-end.
6. **Entry Points & Execution Flow** — where execution starts, what happens next.
7. **Notable Implementation Details** — clever algorithms, interesting choices.
8. **Setup & Usage** — how to install and run (if evident from docs).

Use clear headings, inline code formatting, and concise prose.
Do not pad with filler text. Aim for 600–900 words.
"""


def synthesizer_node(state: RepoState) -> RepoState:
    repo_name:          str  = state["repo_name"]
    llm_model:          str  = state.get("_groq_model", "llama-3.3-70b-versatile")
    code_summary:       str  = state.get("code_summary", "")
    readme_summary:     str  = state.get("readme_summary", "")
    dep_summary:        str  = state.get("dependency_summary", "")
    entry_points:       list = state.get("entry_points", [])
    retrieved:          list = state.get("retrieved_snippets", [])
    dep_graph:          dict = state.get("dependency_graph", {})

    print(f"  [synth] Synthesising explanation …")

    # ── Build context for LLM ─────────────────────────────────────────────────
    snippet_block = "\n\n".join(
        f"[{s['source'].upper()} | {s['file']} | sim={s['similarity']}]\n{s['text']}"
        for s in retrieved[:20]     # top 20 most relevant
    )

    dep_sample = json.dumps(dict(list(dep_graph.items())[:30]), indent=2)

    user_content = f"""\
## Repository: {repo_name}

### README / Documentation Summary
{readme_summary or "(no documentation found)"}

### Code Structural Summary
{code_summary or "(no code found)"}

### Dependency Summary
{dep_summary or "(unavailable)"}

### Detected Entry Points
{", ".join(entry_points) if entry_points else "(none detected)"}

### Dependency Graph Sample (first 30 files)
```json
{truncate(dep_sample, 3000)}
```

### Top Retrieved Code & Text Snippets
{truncate(snippet_block, 4000)}
"""

    from utils.helpers import groq_chat
    explanation = groq_chat(
        model=llm_model,
        temperature=0.3,
        max_tokens=1500,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
    )
    print(f"  [synth] Explanation generated ({len(explanation)} chars)")

    return {"explanation": explanation}
