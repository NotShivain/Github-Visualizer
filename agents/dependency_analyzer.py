"""
agents/dependency_analyzer.py
Node: dependency_analyzer_node

Builds a lightweight import / dependency graph from the repository source
code by static analysis (no execution). Supports Python, JavaScript /
TypeScript, and Go out of the box; falls back to regex heuristics for
other languages.

Identifies likely entry-point files and generates an LLM summary of the
dependency structure.

Populates state:
  - dependency_graph   : {module_file: [imported_module_files]}
  - entry_points       : list of likely main files
  - dependency_summary : LLM-generated dependency summary
"""
from __future__ import annotations
import ast
import json
import os
import re
from pathlib import Path

from state import RepoState
from utils.helpers import truncate

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
             "dist", "build", ".next"}

MAX_FILES = 200   # cap to keep analysis tractable



def _python_imports(source: str) -> list[str]:
    """Return a list of module names imported in a Python file."""
    imports: list[str] = []
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module.split(".")[0])
    except SyntaxError:
        pass
    return imports


def _js_imports(source: str) -> list[str]:
    """Return modules referenced in import/require statements (JS/TS)."""
    # ES6: import ... from '...'
    patterns = [
        r"""import\s+.*?from\s+['"](.+?)['"]""",
        r"""require\s*\(\s*['"](.+?)['"]\s*\)""",
    ]
    results: list[str] = []
    for pat in patterns:
        results.extend(re.findall(pat, source, re.MULTILINE))
    return results


def _go_imports(source: str) -> list[str]:
    """Return package paths from Go import blocks."""
    match = re.search(r'import\s*\((.*?)\)', source, re.DOTALL)
    if not match:
        return re.findall(r'import\s+"(.+?)"', source)
    block = match.group(1)
    return re.findall(r'"(.+?)"', block)


def _generic_imports(source: str) -> list[str]:
    """Best-effort import extraction for unsupported languages."""
    patterns = [
        r'#include\s+[<"](.+?)[">]',          # C / C++
        r'use\s+([\w:]+);',                    # Rust / Perl
        r'import\s+[\w.]+;',                   # Java
        r'using\s+([\w.]+);',                  # C#
        r'require\s+[\'"](.+?)[\'"]',           # Ruby
    ]
    results: list[str] = []
    for pat in patterns:
        results.extend(re.findall(pat, source))
    return results


EXT_PARSER = {
    ".py":  _python_imports,
    ".js":  _js_imports,
    ".jsx": _js_imports,
    ".ts":  _js_imports,
    ".tsx": _js_imports,
    ".go":  _go_imports,
}

ENTRY_PATTERNS = {
    "main.py", "app.py", "server.py", "run.py", "manage.py",
    "index.js", "index.ts", "server.js", "server.ts", "app.js", "app.ts",
    "main.go", "main.rs", "main.cpp", "main.c",
    "program.cs", "application.java",
}


def dependency_analyzer_node(state: RepoState) -> RepoState:
    local_path: str = state["local_path"]
    repo_name:  str = state["repo_name"]
    llm_model: str  = state.get("_groq_model", "llama-3.3-70b-versatile")

    print(f"  [deps] Building dependency graph …")

    dep_graph: dict[str, list[str]] = {}
    entry_points: list[str] = []
    file_count = 0

    for root, dirs, files in os.walk(local_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for fname in files:
            if file_count >= MAX_FILES:
                break
            ext = Path(fname).suffix.lower()
            if ext not in EXT_PARSER and ext not in {".c", ".cpp", ".h",
                                                      ".rs", ".rb", ".java",
                                                      ".cs"}:
                continue
            full_path = os.path.join(root, fname)
            rel_path  = os.path.relpath(full_path, local_path)
            try:
                source = Path(full_path).read_text(errors="replace")
            except OSError:
                continue

            parser = EXT_PARSER.get(ext, _generic_imports)
            imports = parser(source)
            if imports:
                dep_graph[rel_path] = imports

            if fname.lower() in ENTRY_PATTERNS:
                entry_points.append(rel_path)

            file_count += 1

    print(f"  [deps] Analysed {file_count} files, {len(dep_graph)} with imports")
    print(f"  [deps] Entry points: {entry_points or ['(none detected)']}")

    # Send a compact JSON representation (first 50 entries)
    trimmed = dict(list(dep_graph.items())[:50])
    dep_json = json.dumps(trimmed, indent=2)

    from utils.helpers import groq_chat
    dependency_summary = groq_chat(
        model=llm_model,
        temperature=0.2,
        max_tokens=500,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a software architect. "
                    "Given a dependency graph (file → list of imported modules), "
                    "identify the main entry points, core modules, layered structure "
                    "(e.g. presentation / business logic / data), "
                    "and any potential circular dependency issues. "
                    "Be precise and under 300 words."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Repository: {repo_name}\n"
                    f"Detected entry points: {entry_points}\n\n"
                    f"Dependency graph (sample):\n```json\n{truncate(dep_json, 3000)}\n```"
                ),
            },
        ],
    )
    print(f"  [deps] Generated dependency summary")

    return {
        "dependency_graph":   dep_graph,
        "entry_points":       entry_points,
        "dependency_summary": dependency_summary,
    }
