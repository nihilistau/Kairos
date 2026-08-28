"""index_rows — read GATE-INDEX.md as rows, ONE parser, for everything that reads it.

WHY IT EXISTS (2026-08-28). `tools/sweep.py` picked a row's lane out of `line.split("|")[4]`.
That is correct only while no DESCRIPTION contains a pipe — and ten of them did, because a
description is prose and prose contains things like `<channel>thought|` and set notation.
Every one of those rows shifted its own cells along, the lane cell came out as a fragment of
the sentence before it, `"OFFLINE" not in cells[4]` was true, and the gate was skipped.

NINE OFFLINE GATES WERE NEVER RUN BY THE SWEEP: g_narrative, g_sight_backends,
g_control_surface, g_persona_layers, g_backend_seam, g_cfg_derive, g_reflection_loop,
g_wardrobe, g_marks_leak. CLAUDE.md calls that sweep "the whole offline suite in one
command" and "what proves it still works", and G-DOCS-TRUE checked that every gate HAS a
row — never that the row PARSES. A gate documented and silently unrun is worse than one
that was never written, because the index says it is covered.

It was found by writing an eleventh such row and noticing the sweep's total did not move.

So: unescaped pipes separate cells, `\\|` is a literal one, and both the sweep and the
gate that grades the index read rows through here rather than each writing the rule out.
"""

from __future__ import annotations

import io
import os
import re

_ESC = "\\|"                 # a pipe that belongs to the prose
_SENT = "\x00GATEPIPE\x00"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "gates", "GATE-INDEX.md")

# | NAME | `path` | description | LANE | `command` |  -> 7 cells with the empty ends
CELLS = 7
NAME, PATH, DESC, LANE, CMD = 1, 2, 3, 4, 5


def cells(line: str) -> list:
    """The cells of one table row, honouring backslash-escaped pipes inside prose."""
    return [c.replace(_SENT, _ESC).strip()
            for c in line.replace(_ESC, _SENT).split("|")]


def rows(path: str = ""):
    """Every gate row: (cells, source_line). Rows naming no gate file are skipped."""
    text = io.open(path or INDEX, encoding="utf-8").read()
    out = []
    for line in text.splitlines():
        if not line.startswith("|") or "harness_tests/" not in line:
            continue
        out.append((cells(line), line))
    return out


def gate_path(cs: list) -> str:
    """The gate file a row names, or "" — read from the PATH cell only, never the prose."""
    m = re.search(r"`(harness_tests/[a-z0-9_]+\.py)`", cs[PATH] if len(cs) > PATH else "")
    return m.group(1) if m else ""


def malformed(path: str = "") -> list:
    """Rows whose cell count is wrong — the shape that makes a lane unreadable."""
    return [(cs[NAME][:60] if len(cs) > NAME else line[:60], len(cs))
            for cs, line in rows(path) if len(cs) != CELLS]
