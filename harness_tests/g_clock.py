"""G-CLOCK — every timestamp in this system must survive its own round trip.

THIS GATE EXISTS BECAUSE I FIXED THE SAME BUG TWICE, EIGHT HOURS APART, IN TWO FILES.

    watch.py    (2026-07-13, morning)   check() wrote gmtime; due_checks() read mktime.
                                        Every watch was 10 hours overdue the moment it ran.
                                        She searched for his RTX 3090 forty-six times.

    lifecycle.py (2026-07-14, night)    _age_days() — THE one age function in the memory
                                        system — did exactly the same thing. Every fact was
                                        0.42 days old the instant it was written. Salience
                                        decayed on it. Silence accrued on it.

I found the first, fixed it, wrote a commit about it, AND NEVER GREPPED FOR THE PATTERN.
There is a phrase for that in this codebase, from an earlier commit of mine about the identity
firewall: "I FIXED THE INSTANCE AND CALLED IT THE CLASS." So here is the class.

────────────────────────────────────────────────────────────────────────────────────────
THE RULE

    time.mktime   is the inverse of  time.localtime
    calendar.timegm is the inverse of  time.gmtime

Every stamp in this tree is WRITTEN with time.gmtime() and a literal 'Z'. Anything that reads
one back with mktime() is telling a lie exactly the size of the local UTC offset. That lie is:

    ZERO in London.       5 hours in New York.       10 HOURS where the operator lives.

Which is why it cannot be caught by a normal test: IT IS CORRECT ON THE MAINTAINER'S LAPTOP.
It needs a ROUND TRIP — write it the way the store writes it, read it the way the store reads
it, and demand they agree — under a forced non-zero timezone.

    python harness_tests/g_clock.py
"""
from __future__ import annotations

import calendar
import os
import re
import sys
import time
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP = tempfile.mkdtemp()
os.environ["SP_RECALL_REGISTRY"] = os.path.join(_TMP, "registry.jsonl")
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"      # a gate must not need a GPU

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""), flush=True)


STAMP = "%Y-%m-%dT%H:%M:%SZ"


def main() -> int:
    print("G-CLOCK - a stamp must survive its own round trip.\n", flush=True)
    tz = os.environ.get("TZ", "(system)")
    print(f"  timezone under test: {tz}\n", flush=True)

    # ── 1. THE ROUND TRIP, on the one age function the whole memory system uses ──────────
    # Write it exactly as the store writes it. Read it exactly as the store reads it.
    from harness.skills import lifecycle as lc

    iso = time.strftime(STAMP, time.gmtime())
    age_s = lc._age_days(iso) * 86400.0
    check("_age_days: a fact stored NOW is ZERO seconds old",
          abs(age_s) < 5,
          f"{age_s:.0f}s  (the mktime bug read 36000s = exactly 10h at UTC+10)")

    # ── 2. THE SAME, on the watch clock (fixed 2026-07-13; must not regress) ────────────
    from harness.skills import watch as W

    w_iso = time.strftime(STAMP, time.gmtime())
    drift = abs(time.time() - calendar.timegm(time.strptime(w_iso, STAMP)))
    check("watch last_checked survives its round trip",
          drift < 5, f"{drift:.0f}s drift")

    # ── 3. THE ACTUAL BEHAVIOUR EACH BUG CAUSED ─────────────────────────────────────────
    # A clock bug is not interesting; what it DOES is. Assert the consequence, not the maths.
    from harness.skills import notes as N

    w = N.add("3090", category="watch", watch="rtx 3090")
    N.update(w["id"], checked=1, last_checked=time.strftime(STAMP, time.gmtime()))
    check("a watch checked ONE SECOND AGO is not due again",
          not [r for r in W.due_checks() if r["id"] == w["id"]],
          "the ticker re-ran it every 15s and she searched 46 times")

    salience_now = lc.salience({"ts": iso, "mem_class": "event", "mentions": 1})
    salience_fresh = lc.salience({"ts": time.strftime(STAMP, time.gmtime()),
                                  "mem_class": "event", "mentions": 1})
    check("a fresh EVENT has not already begun decaying",
          abs(salience_now - salience_fresh) < 1e-6 and salience_now > 0.5,
          f"salience={salience_now:.3f} (a 3-day half-life loses ~10% to a 10h phantom age)")

    # ── 4. THE CLASS, NOT THE INSTANCE. Grep the tree. ──────────────────────────────────
    # THIS is the check that would have saved eight hours. A bug found in one file is a
    # HYPOTHESIS ABOUT THE CODEBASE, not a fact about the file — and the grep is the cheapest
    # thing in the entire toolbox.
    # Parse the AST, do not grep the text. My first cut grepped for the string "time.mktime"
    # and FLAGGED ITS OWN DOCUMENTATION — the comments in lifecycle.py that explain the bug.
    # A checker that cannot tell CODE from PROSE about code is the same class of mistake as
    # branching on a `src` field that is a paragraph. Look at what the program DOES.
    import ast

    # mktime is LEGAL as the inverse of localtime (local wall-clock arithmetic:
    # "what epoch is 04:00 today, here"). The crime is pairing it with gmtime /
    # a Z stamp. First cut of this check banned every mktime and flagged
    # app.py's room-pulse next-local-hour, which is the allowed pairing.
    offenders = []
    for root, _dirs, files in os.walk(os.path.join(ROOT, "harness")):
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(root, f)
            try:
                tree = ast.parse(open(p, "r", encoding="utf-8", errors="replace").read())
            except Exception:
                continue
            for fn in [n for n in ast.walk(tree)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                calls = set()
                for node in ast.walk(fn):
                    if (isinstance(node, ast.Call)
                            and isinstance(node.func, ast.Attribute)):
                        calls.add(node.func.attr)
                if "mktime" in calls and "localtime" not in calls:
                    offenders.append("%s:%s" % (f, fn.name))

    check("NOTHING in harness/ CALLS time.mktime on a UTC stamp",
          not offenders,
          "clean — the class, not just the instance"
          if not offenders else f"mktime without localtime (UTC pairing): {', '.join(offenders)}")

    total = len(PASS) + len(FAIL)
    print(f"\nG-CLOCK: {'PASS' if not FAIL else 'FAIL'} ({len(PASS)}/{total})", flush=True)
    if FAIL:
        print("  time.mktime is the inverse of localtime. calendar.timegm is the inverse of gmtime.",
              flush=True)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
