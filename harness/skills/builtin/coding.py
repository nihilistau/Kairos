"""
Built-in Coding Skills
=====================

The tool surface for the CLI coding interface. These are sandboxed to a
workspace root (``HARNESS_WORKSPACE`` env or cwd) so the model can read, search
and edit files but cannot escape the tree. Each is a plain ``@skill`` and thus
also an ephemeral tool the model can call mid-generation.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

from harness.skills.skill import skill, SkillCategory


def _root() -> Path:
    return Path(os.environ.get("HARNESS_WORKSPACE", os.getcwd())).resolve()


def _resolve(path: str) -> Path:
    p = (_root() / path).resolve()
    if _root() not in p.parents and p != _root():
        raise ValueError(f"path escapes workspace: {path}")
    return p


@skill(pack="coder", category=SkillCategory.CODE,
       description="List files under a directory in the workspace (relative path).")
def list_dir(path: str = ".") -> str:
    """List directory entries."""
    d = _resolve(path)
    if not d.is_dir():
        return f"not a directory: {path}"
    return "\n".join(sorted(e.name + ("/" if e.is_dir() else "") for e in d.iterdir()))


@skill(pack="coder", category=SkillCategory.CODE,
       description="Read a UTF-8 text file from the workspace and return its contents.")
def read_file(path: str, max_bytes: int = 100_000) -> str:
    """Read a file."""
    p = _resolve(path)
    if not p.is_file():
        return f"no such file: {path}"
    return p.read_text(encoding="utf-8", errors="replace")[:max_bytes]


@skill(pack="coder", category=SkillCategory.CODE,
       description="Write (overwrite) a UTF-8 text file in the workspace.")
def write_file(path: str, content: str) -> str:
    """Write a file, creating parent dirs."""
    p = _resolve(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} bytes to {path}"


@skill(pack="coder", category=SkillCategory.CODE,
       description="Search the workspace for a regex pattern (ripgrep if available, else Python).")
def search(pattern: str, glob: str = "") -> str:
    """Grep the workspace."""
    root = _root()
    rg = subprocess.run(
        ["rg", "-n", pattern] + (["-g", glob] if glob else []),
        cwd=str(root), capture_output=True, text=True,
    ) if _has_rg() else None
    if rg is not None:
        return (rg.stdout or rg.stderr or "(no matches)")[:20_000]
    # Fallback: naive python scan
    import re
    rx = re.compile(pattern)
    hits = []
    for f in root.rglob(glob or "*"):
        if f.is_file():
            try:
                for i, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{f.relative_to(root)}:{i}:{line}")
            except Exception:
                continue
    return "\n".join(hits[:500]) or "(no matches)"


@skill(pack="coder", category=SkillCategory.CODE, cooldown=0.0,
       description="Run a shell command in the workspace (use carefully). Returns stdout+stderr.")
def run_command(command: str, timeout: int = 60) -> str:
    """Run a shell command."""
    try:
        r = subprocess.run(command, shell=True, cwd=str(_root()),
                           capture_output=True, text=True, timeout=timeout)
        return f"[exit {r.returncode}]\n{r.stdout}\n{r.stderr}".strip()[:20_000]
    except subprocess.TimeoutExpired:
        return f"[timeout after {timeout}s]"


def _has_rg() -> bool:
    from shutil import which
    return which("rg") is not None


# ──── PK2 §T2-E2: the coding-campaign tools (anchored edit / tests / git) ────
@skill(pack="coder", category=SkillCategory.CODE,
       description="Edit a file by exact anchored find/replace (safer than rewriting the whole file).")
def edit_file(path: str, find: str, replace: str) -> str:
    """Replace an EXACT text anchor in a workspace file. The anchor must appear exactly
    once — if it's missing or ambiguous, nothing is changed and the error says why
    (include more surrounding lines to disambiguate)."""
    p = _resolve(path)
    if not p.is_file():
        return f"no such file: {path}"
    txt = p.read_text(encoding="utf-8", errors="replace")
    n = txt.count(find)
    if n == 0:
        return f"[edit_file] anchor NOT FOUND in {path} — copy the exact text (whitespace matters)"
    if n > 1:
        return f"[edit_file] anchor is AMBIGUOUS ({n} matches) in {path} — include more surrounding text"
    p.write_text(txt.replace(find, replace, 1), encoding="utf-8")
    df = len(replace) - len(find)
    return f"edited {path}: 1 replacement ({'+' if df >= 0 else ''}{df} chars)"


@skill(pack="coder", category=SkillCategory.CODE, cooldown=0.0,
       description="Run pytest in the workspace and return the tail of the output (pass/fail summary).")
def run_tests(path: str = "", timeout: int = 120) -> str:
    """Run pytest (optionally on one file/dir) and return exit code + the output tail —
    the summary lines a coder needs, not the full spew."""
    import sys as _sys
    cmd = [_sys.executable, "-m", "pytest", "-q", "--no-header"] + ([path] if path else [])
    try:
        r = subprocess.run(cmd, cwd=str(_root()), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"[run_tests timeout after {timeout}s]"
    out = (r.stdout + r.stderr).strip()
    tail = "\n".join(out.splitlines()[-25:])
    return f"[exit {r.returncode}]\n{tail}"


@skill(pack="coder", category=SkillCategory.CODE,
       description="Show git status --short of the workspace (read-only).")
def git_status() -> str:
    """git status --short (read-only; no git writes from tools)."""
    r = subprocess.run(["git", "status", "--short"], cwd=str(_root()),
                       capture_output=True, text=True, timeout=30)
    return (r.stdout or r.stderr or "(clean)").strip()[:5_000]


@skill(pack="coder", category=SkillCategory.CODE,
       description="Show the git diff of the workspace, optionally for one path (read-only).")
def git_diff(path: str = "") -> str:
    """git diff (read-only receipt of what changed)."""
    cmd = ["git", "diff", "--stat", "--patch"] + ([path] if path else [])
    r = subprocess.run(cmd, cwd=str(_root()), capture_output=True, text=True, timeout=30)
    out = (r.stdout or r.stderr or "(no diff)").strip()
    return out[:15_000] + ("\n…(truncated)" if len(out) > 15_000 else "")


CODING_TOOLS = [list_dir, read_file, write_file, edit_file, search,
                run_command, run_tests, git_status, git_diff]
