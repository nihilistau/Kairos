"""_src.py — how a gate reads source, so a refactor cannot make it go quiet.

── THE SRC-TRAP, AIMED AT A REFACTOR (2026-09-01) ────────────────────────────────────
This repo already has a name for asserting over source text instead of over behaviour:
the **src-trap** (`gates/GATE-INDEX.md`, `harness/control/spine.py`,
`harness_tests/g_lane_table.py` — *"branching on a paragraph, the src-trap in a lab
coat"*). Sometimes it is the only tool available: "every gateway path arms the memory lane
before it consults it" is a claim about the SHAPE of the code, and no amount of driving one
path proves it of the others.

The trap has a second edge, and splitting `harness/server/app.py` is what walks onto it.
Forty-two read sites across thirty-nine gates open that one file and assert on its text.
When a function moves to a sibling module:

  * `.index(marker)` raises ValueError and `.split(marker)[1]` raises IndexError — LOUD,
    and therefore safe. They announce themselves.
  * every `X not in src` goes GREEN, because X is genuinely not in that file any more.
    There are ~186 such assertions in those gates.
  * every `src.count(X) == N` floor collapses for the same reason.
  * and the worst shape: `g_asked` AST-walks the file for functions containing a marker
    and asserts something about each. Move them out and NO FUNCTION MATCHES, so the
    offender list is empty and the gate passes over nothing at all. That is the
    "GATES THAT ASSERTED THE PAST" class GATE-INDEX keeps a section for.

So the unit of a source assertion is not the FILE. It is either the PACKAGE (for "nowhere
in the gateway does X happen") or the OBJECT (for "inside this function, X comes before
Y"). Both are below. `text()` stays for the cases that genuinely mean one file — a
manifest, a config, a doc.

G-SRC-TRAP holds the migration: no gate may name `harness/server/app.py` or
`harness/skills/memory.py` as a path again, and every source path a gate reads must exist.
"""
from __future__ import annotations

import inspect
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def text(*parts: str) -> str:
    """One file, by path parts under the repo root. For things that ARE one file."""
    p = os.path.join(ROOT, *parts)
    if not os.path.exists(p):
        raise FileNotFoundError("no such source file: %s" % os.path.join(*parts))
    return io.open(p, encoding="utf-8", errors="replace").read()


def pkg(*parts: str) -> str:
    """Every `*.py` in one package, sorted, concatenated.

    THE UNIT FOR AN ABSENCE OR A COUNT. "The gateway never does X" is a claim about
    `harness/server/`, not about whichever file X used to live in — so a negative
    assertion over this text stays true when code moves between siblings, and a
    `count(...)` floor keeps counting the same call sites.

    Files are separated by a `# ==== file: NAME ====` line so a positive assertion can
    still slice, and so a failure detail says which file it was looking at. `__init__.py`
    is included: a re-export surface is part of what the package says.
    """
    d = os.path.join(ROOT, *parts)
    if not os.path.isdir(d):
        raise NotADirectoryError("no such package: %s" % os.path.join(*parts))
    names = sorted(f for f in os.listdir(d) if f.endswith(".py"))
    if not names:
        raise FileNotFoundError("package has no .py files: %s" % os.path.join(*parts))
    out = []
    for n in names:
        out.append("\n# ==== file: %s ====\n" % n)
        out.append(io.open(os.path.join(d, n), encoding="utf-8", errors="replace").read())
    return "".join(out)


def body(obj) -> str:
    """One function's or class's own source — `inspect.getsource`.

    THE UNIT FOR AN ORDERING. `g_day_transcript` compared BYTE OFFSETS in app.py to prove
    the memory lane is armed before it is consulted; across two files those offsets mean
    nothing, and within the wrong file they are silently satisfied. Asked of the object,
    the question survives any move — which is why eight gates already read this way
    (`g_delegate`, `g_research`, `g_sem_rank`, `g_byteexact`, `g_senses`, `g_discover`,
    `g_holdem`, `g_silence_answer`).

    Prefer this over `pkg()` whenever the claim is about ONE function. It is the only
    read that cannot be fooled by a sibling that happens to contain the same words.
    """
    return inspect.getsource(obj)


def files(*parts: str) -> list:
    """The package's member filenames, sorted — for a gate that wants to say WHICH."""
    d = os.path.join(ROOT, *parts)
    return sorted(f for f in os.listdir(d) if f.endswith(".py"))
