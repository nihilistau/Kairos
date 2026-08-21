"""_gate.py — the shared verdict for gates written from 2026-08-21 on.

THE EXIT CONVENTION (gates/GATE-INDEX.md): the verdict must reach the exit code.
  exit 0  asserted and held — never reachable with zero assertions made
  exit 1  asserted and failed
  exit 2  SKIP — the subject is absent here (no npm, no persona/, no engine checkout);
          real where it exists, vacuous here, and the exit code says so

This file exists because the 2026-08-19 audit found ten gates that printed a verdict
and fell off the end of `__main__` (exit 0 on FAIL), and two more that exited 0 from
a usage line having tested nothing. Every gate re-implementing `check()` is one more
place that rule can be forgotten. Adopted by NEW gates and by gates touched from
here on — not a mass migration; the 185 existing `check()`s are not wrong, they are
just copies.

Usage:
    from _gate import check, finish, skip, utf8_stdout
    utf8_stdout()
    check("the thing holds", cond, detail)
    ...
    finish("G-NAME")            # prints the tally, exits 0/1 — or 2 if nothing was asserted
"""
from __future__ import annotations

import sys

PASS = 0
FAIL = 0
_FAILED: list = []


def utf8_stdout() -> None:
    """A cp1252 console crashed g_narrative and g_sem_dominate mid-"ok" line — which
    reads as RED for a reason unrelated to what the gate guards."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def check(name: str, cond, detail="") -> bool:
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        _FAILED.append(name)
        print("  FAIL %s   %s" % (name, detail))
    return bool(cond)


def skip(reason: str, gate: str = "") -> None:
    """The subject is absent here. Says so, exits 2 — never 0."""
    print("\n%sSKIP — %s" % ((gate + "  ") if gate else "", reason))
    sys.exit(2)


def finish(gate: str) -> None:
    """Print the tally and exit with the verdict. A gate that asserted NOTHING is a
    skip, not a pass — exit 2 — because a green with zero checks is the exact failure
    this convention exists to end."""
    total = PASS + FAIL
    print("\n%s  %d/%d" % (gate, PASS, total))
    if total == 0:
        print("  (no assertions were made — that is a skip, not a pass)")
        sys.exit(2)
    sys.exit(1 if FAIL else 0)
