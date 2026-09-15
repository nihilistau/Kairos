"""G-VERSION-STEP — behaviour that ships moves the number. OFFLINE.

WHY (2026-09-15). This has now gone wrong four times:

    0.1.0   held through two releases            (fixed 2026-08-25)
    0.8.4   held through 0.8.5                   (fixed 2026-08-29)
    0.8.37  written in a commit title, unbumped  (caught in review, 2026-09-12)
    0.8.38  held through FIVE behaviour changes  (caught by an outside audit, 2026-09-15)

After the second one, a comment was added to `pyproject.toml` asking the next person to keep
the number in step, and describing the first two occurrences so the reason would be obvious.
It then failed to prevent the third and the fourth. **A comment addressed to whoever reads it
next is not a mechanism** — the whole point of the failure is that nobody was reading that
line — and this repo already knows what a mechanism looks like, because it is full of them.
So: a gate.

WHAT THIS HOLDS:

  §1 THE TWO PLACES AGREE. `kairos-export/pyproject.toml` and the newest `## X.Y.Z` heading
     in `kairos-export/CHANGELOG.md` name the same version. This is the cheap half and it
     catches the ordinary slip — a changelog entry written with the bump forgotten, or the
     reverse.
  §2 AND THE NUMBER IS NOT BEHIND THE CODE. No file on the BEHAVIOUR surface has been
     committed since the commit that last moved the version line. This is the half that
     would have caught all four, because in every one of them the files moved and the
     number did not.

WHY §2 IS THE BEHAVIOUR SURFACE AND NOT EVERYTHING THAT SHIPS. Docs ship too, and a typo fix
in a doc is not a release. A gate that goes red for a typo gets ignored inside a fortnight,
and an ignored gate is the same failure as the comment it replaces — this one has to stay
worth reading. The surface is intersected with the export manifest's own `include` list, so
it cannot quietly come to guard something the export does not actually ship.

SKIPS (exit 2) without git or outside a work tree: §2 is a question about history, and
answering it from a tarball would mean inventing an answer.

MUTANTS, run in-gate: disagree the two files (§1 red), and ask §2 the same question against
the PREVIOUS version commit, which has real behaviour changes after it (§2 red).

    python harness_tests/g_version_step.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, sandbox, skip, utf8_stdout  # noqa: E402

utf8_stdout()
sandbox("g_version_step")

try:
    import tomllib
except ImportError:                                   # pragma: no cover
    import tomli as tomllib  # type: ignore

PYPROJECT = os.path.join(ROOT, "kairos-export", "pyproject.toml")
CHANGELOG = os.path.join(ROOT, "kairos-export", "CHANGELOG.md")
MANIFEST = os.path.join(ROOT, "kairos-export", "kairos-export.toml")

# The surface where a change is a RELEASE. Docs are deliberately absent — see the header.
BEHAVIOUR = ("harness/", "ui/src/", "console/room/", "serve.py")

_VER_RE = re.compile(r'^version\s*=\s*"([^"]+)"', re.M)
_HEAD_RE = re.compile(r'^##\s+(\d+\.\d+\.\d+)', re.M)


def _read(p: str) -> str:
    with open(p, encoding="utf-8") as f:
        return f.read()


def _git(*args):
    """git, or None if this is not a work tree / git is not installed."""
    try:
        out = subprocess.run(("git",) + args, cwd=ROOT, capture_output=True, text=True,
                             timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


# ── §1 the two places agree ──────────────────────────────────────────────────────────
m = _VER_RE.search(_read(PYPROJECT))
h = _HEAD_RE.search(_read(CHANGELOG))
pv = m.group(1) if m else None
cv = h.group(1) if h else None

check("§1 pyproject.toml states a version", bool(pv), "no `version = \"...\"` line found")
check("§1 the changelog's newest heading states one", bool(cv),
      "no `## X.Y.Z` heading found in kairos-export/CHANGELOG.md")
check("§1 and they are the SAME version", pv is not None and pv == cv,
      "pyproject=%r  changelog=%r — one of the two was updated without the other" % (pv, cv))


# ── the shipped surface, from the manifest itself ────────────────────────────────────
def _shipped_prefixes():
    """The manifest's include globs, reduced to the prefixes §2 cares about.

    Intersecting with BEHAVIOUR means this gate can never come to guard a path the export
    does not ship — if a glob is dropped from the manifest, it silently leaves here too,
    rather than this file asserting about a directory nobody publishes.
    """
    # [target].include, NOT a top-level `include`. Reading the wrong key returns [], which
    # empties PREFIXES, which makes §2 filter every path away and pass while computing
    # nothing. That is exactly how this gate first ran, and the §2 mutant is what said so —
    # hence the leg below asserting the surface is non-empty rather than trusting it.
    try:
        with open(MANIFEST, "rb") as f:
            inc = (tomllib.load(f).get("target") or {}).get("include") or []
    except Exception:
        inc = []
    flat = [g.split("**")[0] for g in inc]
    keep = []
    for b in BEHAVIOUR:
        if any(b.startswith(g) or g.startswith(b) for g in flat):
            keep.append(b)
    return keep, inc


PREFIXES, INCLUDE = _shipped_prefixes()
check("§2 the behaviour surface is one the manifest actually ships",
      bool(PREFIXES) and bool(INCLUDE),
      "BEHAVIOUR=%r vs manifest include=%r — if this is empty the gate is asserting "
      "about paths that never reach the public tree" % (BEHAVIOUR, INCLUDE[:4]))


def _changed_since(commit: str):
    """Behaviour-surface files committed after `commit`."""
    names = _git("diff", "--name-only", "%s..HEAD" % commit)
    if names is None:
        return None
    return sorted(n for n in names.splitlines()
                  if n and any(n.startswith(p) for p in PREFIXES))


# ── §2 the number is not behind the code ─────────────────────────────────────────────
if _git("rev-parse", "--is-inside-work-tree") != "true":
    skip("not a git work tree — §2 asks a question about history", "G-VERSION-STEP")

VER_COMMIT = _git("log", "-1", "--format=%H", "-G", r'^version = "', "--",
                  "kairos-export/pyproject.toml")
if not VER_COMMIT:
    skip("cannot find the commit that last moved the version line", "G-VERSION-STEP")

stale = _changed_since(VER_COMMIT)
check("§2 no behaviour has shipped since the version last moved",
      stale == [],
      "%d file(s) committed after %s, the last commit that moved the version line, with "
      "the number still untouched:\n    %s\n"
      "    -> bump kairos-export/pyproject.toml and add the CHANGELOG entry in the SAME "
      "commit as the behaviour. This is the fourth time; the comment in pyproject.toml is "
      "not enough. (Working tree currently says %s.)"
      % (len(stale or []), (VER_COMMIT or "")[:9], "\n    ".join((stale or [])[:12]), pv))


# ── MUTANTS ──────────────────────────────────────────────────────────────────────────
# §1: disagree the two files in memory and confirm the comparison notices.
_m1 = not (pv is not None and pv == (cv or "") + ".0")
check("MUTANT a disagreeing version pair is caught by §1", _m1,
      "§1 must compare the two values, not merely find them")

# §2: ask the SAME question against the previous version commit. There are real behaviour
# changes between two releases, so an honest §2 must go red there — if it does not, §2 is
# computing nothing and would have stayed green through all four occurrences.
_prev = _git("log", "-2", "--format=%H", "-G", r'^version = "', "--",
             "kairos-export/pyproject.toml")
_prev_c = (_prev or "").splitlines()
if len(_prev_c) >= 2:
    _older = _changed_since(_prev_c[1])
    check("MUTANT §2 goes red against the PREVIOUS version commit", bool(_older),
          "asked against %s, §2 found no shipped changes — it is not reading history"
          % _prev_c[1][:9])
else:
    check("MUTANT §2 goes red against the PREVIOUS version commit", True,
          "only one version commit in history; nothing to compare against yet (not a fault)")

finish("G-VERSION-STEP")
