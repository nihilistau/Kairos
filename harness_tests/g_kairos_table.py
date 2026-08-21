#!/usr/bin/env python
"""G-KAIROS-TABLE — the unprompted-speech gate as a finite object (INVARIANT-ROADMAP.md
Tier 1.1; the recipe of INVARIANT-MEMORY.md applied to kairos/impulse.decide()).

impulse.decide() is PURE with an injected clock and rng, and every magnitude it reads
(margins, idle, cooldown, cap) enters only through THRESHOLD comparisons — so its verdict
domain booleanizes EXACTLY into nine coordinates, and this gate enumerates the ENTIRE
domain: all 512 cells, through the REAL decide(), no sampling, no writer, no GPU.

    enabled | cooling | cap | due | chainmax | askedq | insight | contlow | checkin
        -> action in {silent, remind, muse, continue, check_in}

(delay, score, reason are the RANK/audit layer — magnitudes by design, not verdicts.)

Because the enumeration is EXHAUSTIVE, no runtime shadow is needed: the committed table
is complete coverage of the verdict function, and ANY behavioural change to the cascade
trips this gate as a cell diff. This is the strongest form the discipline takes — the
memory table needed a field shadow because the world could produce unseen shapes; here
the domain has edges we can walk.

THE ORDER IS THE POLICY, NOW AS DATA: impulse.py spends ~80 lines arguing why REMIND
sits above the chain/question rules and MUSE below them. That argument is now the
committed PRECEDENCE artifact, and section 2 PROVES the code implements it (first-match
semantics over every cell). The prose stays as the why; the artifact is the what.

And the phi-fragment theorems (INVARIANT-ROADMAP.md §1.6 — universal sentences over the
cells, bounded negation, no existential demands), quantified over all 512:

    FORALL cells: not enabled                        -> silent
    FORALL cells: cooling or cap                     -> silent   (spam bounds dominate
                                                      EVERYTHING — even promises)
    FORALL cells: enabled, not cooling/cap, due      -> remind   (a promise outranks
                                                      manners: chain, question, all of it)
    FORALL cells: askedq, not due, question LIVE     -> never muse/continue/check_in
                                                      (she does not fill a silence SHE made;
                                                      a STALE question — him quiet past the
                                                      check-in bar — releases the floor,
                                                      per the 2026-08-01 release, 77d5bcb)
    FORALL cells: speaks                             -> enabled and not cooling and not cap
                                                      (no path around the spam bounds)
    FORALL cells: chainmax and not due               -> silent   (his turn buys her budget)

Run:  python harness_tests/g_kairos_table.py            (gate)
      python harness_tests/g_kairos_table.py --freeze   (commit the artifact)

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

from harness.kairos import impulse as I                  # noqa: E402

TABLE_PATH = os.path.join(HERE, "fixtures", "kairos", "impulse-table.json")
COORDS = ("enabled", "cooling", "cap", "due", "chainmax", "askedq",
          "insight", "contlow", "checkin")

# THE ORDER IS THE POLICY. First matching row wins; guards are cell predicates.
PRECEDENCE = [
    {"when": {"enabled": 0}, "action": I.SILENT},
    {"when": {"cooling": 1}, "action": I.SILENT},
    {"when": {"cap": 1}, "action": I.SILENT},
    {"when": {"due": 1}, "action": I.REMIND},        # a promise outranks manners
    {"when": {"chainmax": 1}, "action": I.SILENT},
    # She waits for HIS answer — while the silence is still the one SHE made. checkin=1
    # means he has been quiet past checkin_idle_s, and decide()'s 2026-08-01 release
    # (commit 77d5bcb, its own incident receipt: one reply ending in "?" muted CHECK_IN
    # and CONTINUE indefinitely, "read exactly like the machinery being broken, which is
    # what he reported") says a stale question no longer holds the floor. That commit
    # changed decide() and left THIS row, the theorem below, and the frozen artifact all
    # saying the old rule — so this gate was red from 2026-08-01 to 2026-08-19 with
    # nobody watching. The policy was reviewed; the table now says what decide() says.
    {"when": {"askedq": 1, "checkin": 0}, "action": I.SILENT},
    {"when": {"insight": 1}, "action": I.MUSE},
    {"when": {"contlow": 1}, "action": I.CONTINUE},
    {"when": {"checkin": 1}, "action": I.CHECK_IN},
    {"when": {}, "action": I.SILENT},                # nothing to add
]


class _Rng:
    """Deterministic rng stub: the check-in ROLL is part of the checkin coordinate."""
    def __init__(self, r):
        self.r = r

    def random(self):
        return self.r

    def uniform(self, a, b):
        return a


def _cell_key(bits):
    return "|".join("%s=%d" % (c, b) for c, b in zip(COORDS, bits))


def run_cell(bits):
    """Build the EXACT world for one cell and ask the REAL decide()."""
    d = dict(zip(COORDS, bits))
    now = 100000.0
    cfg = I.KairosConfig(enabled=bool(d["enabled"]))
    state = I.TurnState(
        chain=cfg.max_chain if d["chainmax"] else 0,
        last_spoke_at=(now - 10.0) if d["cooling"] else 0.0,       # 10 < cooldown 45
        last_user_at=(now - 300.0) if d["checkin"] else (now - 10.0),  # 300 >= idle 240
        spoken_times=[now - 200.0 - i for i in range(cfg.max_per_hour)] if d["cap"] else [],
    )
    return I.decide(
        cfg=cfg, state=state, now=now,
        reply_text="shall we try it?" if d["askedq"] else "done.",
        eot_margin=-20.0 if d["contlow"] else 5.0,                  # -20 < -11.75
        user_present=True,
        rng=_Rng(0.0 if d["checkin"] else 0.99),                    # roll folded into coord
        due_notes=[{"title": "call the clinic"}] if d["due"] else None,
        insight={"bits": 3.2, "text": "a conclusion"} if d["insight"] else None,
    )


def precedence_action(bits):
    d = dict(zip(COORDS, bits))
    for row in PRECEDENCE:
        if all(d[c] == v for c, v in row["when"].items()):
            return row["action"]
    return I.SILENT


def enumerate_table():
    table = {}
    for bits in itertools.product((0, 1), repeat=len(COORDS)):
        imp = run_cell(bits)
        table[_cell_key(bits)] = imp.action
    return table


def main():
    table = enumerate_table()
    if "--freeze" in sys.argv:
        os.makedirs(os.path.dirname(TABLE_PATH), exist_ok=True)
        with open(TABLE_PATH, "w", encoding="utf-8") as f:
            json.dump({"coordinates": list(COORDS), "precedence": PRECEDENCE,
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

    def cells(**want):
        for k, a in table.items():
            d = dict(p.split("=") for p in k.split("|"))
            if all(int(d[c]) == v for c, v in want.items()):
                yield k, a

    print("\n1. the board is exhaustive and pinned")
    check("512 cells enumerated through the real decide()", len(table) == 512, len(table))
    try:
        with open(TABLE_PATH, encoding="utf-8") as f:
            committed = json.load(f)
    except Exception:
        committed = None
    check("a committed artifact exists (--freeze)", committed is not None)
    if committed:
        moved = [k for k in table if committed["table"].get(k) != table[k]]
        check("no ruling moved vs the committed table (a diff = an unreviewed "
              "policy change)", not moved,
              [(k, committed["table"].get(k), table[k]) for k in moved[:2]])
        check("the committed precedence artifact matches the in-gate one",
              committed.get("precedence") == PRECEDENCE)

    print("\n2. THE ORDER IS THE POLICY: decide() implements the precedence list")
    bad = [(_cell_key(b), run_cell(b).action, precedence_action(b))
           for b in itertools.product((0, 1), repeat=len(COORDS))
           if table[_cell_key(b)] != precedence_action(b)]
    check("first-match precedence semantics hold on all 512 cells", not bad, bad[:2])

    print("\n3. the phi-fragment theorems (universal, over every cell)")
    check("FORALL not enabled -> silent",
          all(a == I.SILENT for _, a in cells(enabled=0)))
    check("FORALL cooling -> silent (spam bounds dominate even promises)",
          all(a == I.SILENT for _, a in cells(enabled=1, cooling=1)))
    check("FORALL cap -> silent",
          all(a == I.SILENT for _, a in cells(enabled=1, cap=1)))
    check("FORALL clear bounds + due -> remind (a promise outranks manners)",
          all(a == I.REMIND for _, a in cells(enabled=1, cooling=0, cap=0, due=1)))
    check("FORALL askedq, not due, question still LIVE -> never muse/continue/check_in",
          all(a in (I.SILENT, I.REMIND)
              for _, a in cells(enabled=1, askedq=1, due=0, checkin=0)))
    check("...and a STALE question (idle past the check-in bar) releases the floor",
          any(a == I.CHECK_IN
              for _, a in cells(enabled=1, cooling=0, cap=0, chainmax=0,
                                askedq=1, due=0, checkin=1)))
    check("FORALL chainmax and not due -> silent (his turn buys her budget)",
          all(a == I.SILENT
              for _, a in cells(enabled=1, cooling=0, cap=0, chainmax=1, due=0)))
    check("FORALL speaks -> enabled and not cooling and not cap (no path around "
          "the spam bounds)",
          all(a == I.SILENT for k, a in table.items()
              if ("enabled=0" in k or "cooling=1" in k or "cap=1" in k)))

    print("\nG-KAIROS-TABLE: %d pass, %d fail" % (PASS, FAIL))
    rdir = os.path.join(ROOT, "var", "sem", "receipts")
    os.makedirs(rdir, exist_ok=True)
    with open(os.path.join(rdir, "g_kairos_table.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "g_kairos_table", "pass": PASS, "fail": FAIL,
                   "cells": len(table),
                   "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
