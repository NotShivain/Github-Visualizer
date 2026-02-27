"""
agents/clone_agent.py
Node: clone_node

Clones the target GitHub repository to a temporary local directory.
Populates state with:
  - local_path   : absolute filesystem path of the clone
  - repo_name    : "owner/repo" string
  - default_branch
"""
from __future__ import annotations
import os
import re
import tempfile

from state import RepoState


# Files / dirs to skip when cloning (mirrors .gitignore conventions)
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "coverage",
}


def clone_node(state: RepoState) -> RepoState:
    """Clone the repository and return updated state."""
    repo_url: str = state["repo_url"]

    # Normalise URL — strip trailing .git
    repo_url = repo_url.rstrip("/")
    if not repo_url.endswith(".git"):
        git_url = repo_url + ".git"
    else:
        git_url = repo_url

    # Extract owner/repo
    match = re.search(r"github\.com[:/](.+?/[^/]+?)(?:\.git)?$", git_url)
    if not match:
        raise ValueError(f"Cannot parse GitHub URL: {repo_url}")
    repo_name = match.group(1)

    print(f"  [clone] Cloning {repo_name} …")

    import git  # GitPython
    tmp_dir = tempfile.mkdtemp(prefix="ghviz_")
    repo = git.Repo.clone_from(git_url, tmp_dir, depth=1)
    default_branch = repo.active_branch.name if not repo.head.is_detached else "main"

    print(f"  [clone] Cloned to {tmp_dir}  (branch: {default_branch})")

    return {
        "local_path": tmp_dir,
        "repo_name": repo_name,
        "default_branch": default_branch,
    }
