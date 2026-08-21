#!/usr/bin/env python
"""G-LADDER-TABLE — the roleplay heat ladder as a finite object, walked edge to edge
(INVARIANT-ROADMAP.md Tier 2; the exhaustive recipe of G-KAIROS-TABLE).

step() is pure, and its magnitudes (beats) enter only through the DWELL thresholds — so
the verdict domain booleanizes exactly: level(8) × dwell_met(2) × cap(8) × intent(4) =
512 cells, all through the REAL step() with intents produced by the REAL regexes
("red" / "slow down" / "kiss me" / neutral — the intent CLASSIFIER stays a quarantined
prose producer; the TRANSITION given intent is the finite policy under test).

Committed: fixtures/roleplay/ladder-table.json. The φ-fragment theorems, all 512 cells:

    FORALL stop:                          level 0, beats 0 — a stop always wins, at any
                                          level, gated by NOTHING
    FORALL cool:                          level decreases by exactly 1 (floor 0), never
                                          gated — cooling always works
    FORALL heat with dwell unmet:         level unchanged — the build is the scene
    FORALL heat:                          new level <= cap and <= 7 — the ceiling holds
    FORALL neutral:                       level unchanged (the scene holds; beats accrue)
    FORALL cells:                         level never rises by more than 1 — no rung is
                                          ever skipped

Run:  python harness_tests/g_ladder_table.py            (gate)
      python harness_tests/g_ladder_table.py --freeze   (commit the artifact)

OFFLINE. No GPU, no daemon, no store.
"""
import itertools
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from harness.roleplay import ladder as L                 # noqa: E402

TABLE_PATH = os.path.join(HERE, "fixtures", "roleplay", "ladder-table.json")
INTENT_TEXT = {"stop": "red", "cool": "slow down a little",
               "heat": "kiss me", "neutral": "the rain sounds nice tonight"}


def run_cell(level, dwell_met, cap, intent):
    beats = L.DWELL.get(level, 2) if dwell_met else 0
    heat = L.Heat(level=level, beats_at_level=beats)
    new, _note = L.step(heat, INTENT_TEXT[intent], cap)
    return new


def enumerate_table():
    table = {}
    for level, dm, cap, intent in itertools.product(
            range(8), (0, 1), range(8), ("stop", "cool", "heat", "neutral")):
        new = run_cell(level, dm, cap, intent)
        key = "level=%d|dwell=%d|cap=%d|intent=%s" % (level, dm, cap, intent)
        table[key] = {"level": new.level, "beats": new.beats_at_level}
    return table


def main():
    table = enumerate_table()
    if "--freeze" in sys.argv:
        os.makedirs(os.path.dirname(TABLE_PATH), exist_ok=True)
        with open(TABLE_PATH, "w", encoding="utf-8") as f:
            json.dump({"coordinates": "level|dwell_met|cap|intent",
                       "intent_probes": INTENT_TEXT,
                       "table": dict(sorted(table.items()))}, f, indent=2)
        print("frozen: %s (%d cells)" % (TABLE_PATH, len(table)))
        return

    PASS = FAIL = 0

    def check(name, cond, detail=""):
        nonlocal PASS, FAIL
        if cond:
            PASS += 1
            print("  ok   %s" % name)
        else:
            FAIL += 1
            print("  FAIL %s   %s" % (name, str(detail)[:200]))

    def cells(intent=None):
        for k, v in table.items():
            d = dict(p.split("=") for p in k.split("|"))
            if intent is None or d["intent"] == intent:
                yield int(d["level"]), int(d["dwell"]), int(d["cap"]), v

    print("\n1. exhaustive and pinned")
    check("512 cells through the real step()", len(table) == 512, len(table))
    try:
        with open(TABLE_PATH, encoding="utf-8") as f:
            committed = json.load(f)["table"]
    except Exception:
        committed = None
    check("a committed artifact exists (--freeze)", committed is not None)
    if committed:
        moved = [k for k in table if committed.get(k) != table[k]]
        check("no ruling moved vs the committed table", not moved, moved[:3])

    print("\n2. the phi-fragment theorems, all 512 cells")
    check("FORALL stop: level 0, beats 0 — a stop always wins, gated by nothing",
          all(v == {"level": 0, "beats": 0} for _, _, _, v in cells("stop")))
    check("FORALL cool: exactly one rung down (floor 0), never gated",
          all(v["level"] == max(0, lv - 1) and v["beats"] == 0
              for lv, _, _, v in cells("cool")))
    check("FORALL heat with dwell unmet: level holds — the build is the scene",
          all(v["level"] == lv for lv, dm, _, v in cells("heat") if dm == 0))
    check("FORALL heat: never above the cap, never above 7",
          all(v["level"] <= min(cap, 7) or v["level"] == lv
              for lv, _, cap, v in cells("heat")))
    check("FORALL heat at-or-over cap: level holds (the ceiling is the operator's word)",
          all(v["level"] == lv for lv, _, cap, v in cells("heat") if lv >= cap))
    check("FORALL neutral: level holds, beats accrue",
          all(v["level"] == lv and v["beats"] >= 1 for lv, _, _, v in cells("neutral")))
    check("FORALL cells: no rung is ever skipped (rise <= 1)",
          all(v["level"] - lv <= 1 for lv, _, _, v in cells()))

    print("\nG-LADDER-TABLE: %d pass, %d fail" % (PASS, FAIL))
    rdir = os.path.join(ROOT, "var", "sem", "receipts")
    os.makedirs(rdir, exist_ok=True)
    with open(os.path.join(rdir, "g_ladder_table.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "g_ladder_table", "pass": PASS, "fail": FAIL,
                   "cells": len(table),
                   "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
