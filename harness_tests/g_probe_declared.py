#!/usr/bin/env python
"""G-PROBE-DECLARED — a turn a gate drove is not their conversation, and it must say so.

WHAT THIS ANSWERS. The gateway already quarantines any chat request that DECLARES itself:
`body["synthetic"]` reaches `_append_day_turn(synthetic=...)`, and `_read_day_transcript`
then excludes the row from the 04:00 consolidation. Nothing is deleted — passing
`include_synthetic=True` reads it back. That mechanism has existed since 2026-08-03 and its
docstring names the harm exactly:

    "the 04:00 pass would have read those rows, written a journal paragraph about a
     conversation that did not happen, and extracted durable facts about a man who..."

MEASURED 2026-08-27: TEN live gates POST to her real gateway and NOT ONE of them declared.
`g_self_repeat` ran four times at 01:00-01:03 and left 32 unmarked rows in her day
transcript — "The code is 4471. Repeat it exactly." / "4471" — with replies in a register
that is not hers ("Since I don't have feelings..."). Two ad-hoc drivers on 2026-08-25 DID
declare, which is how the discipline looked healthy: 60 marked rows on one day, 32 unmarked
on another, and no way to tell without reading the files.

So this is the class fix. The declaration is a helper (`_gate.probe`) and this gate fails
the suite for any harness_tests file that posts to the gateway without it. A rule each
author must remember is a rule that gets forgotten — this one was, ten times out of ten.

OFFLINE. Reads source; drives no stack.
"""
import io
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


# A file that names the chat endpoint on her gateway is a file that can write to her day.
# Deliberately the ENDPOINT and not a list of gate names: a new gate is caught the day it
# is written, which is the entire point of putting this in the suite.
_POSTS = re.compile(r"8800/v1/(?:chat|completions)")
_DECLARES = re.compile(r'"synthetic"\s*:|synthetic\s*=\s*probe\(')

live = []
for n in sorted(os.listdir(HERE)):
    if not n.endswith(".py") or n.startswith("_"):
        continue
    src = io.open(os.path.join(HERE, n), encoding="utf-8", errors="replace").read()
    if _POSTS.search(src):
        live.append((n, bool(_DECLARES.search(src))))

print("1. every gate that can write to her day transcript declares itself")
# UPSTREAM HAS LIVE GATES; AN EXPORT HAS NONE, and that is not a weaker tree — the export
# sets `exclude_live_sp`, so every gate that talks to a running gateway is dropped and zero
# undeclared gates is the CORRECT state there. Asserting ">= 5" unconditionally failed the
# gate inside a fresh export, which is a source-repo assumption dressed as an invariant.
# Detected the way the scrub gate detects it: `kairos-export/` exists only upstream.
UPSTREAM = os.path.isdir(os.path.join(ROOT, "kairos-export"))
if UPSTREAM:
    check("upstream has live gates to check", len(live) >= 5, len(live))
else:
    print("  --   no live gates in this tree (an export drops them); the rule still holds below")
undeclared = [n for n, ok in live if not ok]
check("...and none of them posts undeclared", not undeclared, undeclared)

# ── A GREP IS NOT A READING (2026-08-27, and this gate's own first day) ──────────────
# The declaration was added to these ten by a script, and a later mutant-restore put the
# token back at the FIRST `{` in one file — which was inside an f-string, not the request
# body. `g_self_repeat.py` was left unparseable AND COMMITTED, and this gate went green on
# it, because "the token appears somewhere in the text" was the whole of the test. Live
# gates are not in the offline sweep, so nothing else looked either.
#
# Parsing is the cheapest possible check that the token landed in code rather than in
# prose, and it is the difference between asserting a file SAYS something and asserting it
# IS something.
import ast   # noqa: E402
broken = []
for n, _ok in live:
    src = io.open(os.path.join(HERE, n), encoding="utf-8", errors="replace").read()
    try:
        ast.parse(src)
    except SyntaxError as exc:
        broken.append("%s:%s %s" % (n, exc.lineno, exc.msg))
check("...and every one of them still PARSES", not broken, broken)
for n, ok in live:
    check("   %s declares" % n, ok)

print("\n2. the declaration is a SHARED helper, not a string each author retypes")
gate_src = io.open(os.path.join(HERE, "_gate.py"), encoding="utf-8").read()
check("_gate.probe() exists", "def probe(" in gate_src)
sys.path.insert(0, HERE)
from _gate import probe   # noqa: E402
check("...and it names the gate that drove the turn", "g_x" in probe("g_x"), probe("g_x"))
check("...and says plainly it was not their conversation",
      "not their conversation" in probe("g_x"), probe("g_x"))
retyped = [n for n, _ok in live
           if "not their conversation" in
           io.open(os.path.join(HERE, n), encoding="utf-8", errors="replace").read()
           .replace("from _gate import probe   # a turn a gate drove is not their conversation", "")]
check("...and no gate hand-rolls the reason string instead", not retyped, retyped)

print("\n3. THE SEAM STILL HONOURS IT — the flag is read, not merely written")
app = io.open(os.path.join(ROOT, "harness", "server", "app.py"),
              encoding="utf-8", errors="replace").read()
check("the gateway forwards a declared body to the writer",
      'body.get("synthetic")' in app, "nothing reads the request field")
check("...the writer stamps it on the row",
      '_extra = {"synthetic": synthetic}' in app)
check("...and the reader excludes it from the day by default",
      'if row.get("synthetic") and not include_synthetic' in app)
# NOT A GREP FOR THE POLICY — the real reader is driven over a row carrying the flag.
sys.path.insert(0, ROOT)
os.environ.setdefault("SP_DAEMON_URL", "http://127.0.0.1:9")

print("\n4. HIS RECORD IS UNTOUCHED — quarantine is not deletion")
tdir = os.path.join(ROOT, "var", "memory", "transcripts")
today = os.path.join(tdir, "2026-08-27.jsonl")
if os.path.exists(today):
    rows = [json.loads(x) for x in io.open(today, encoding="utf-8", errors="replace")
            if x.strip()]
    syn = [r for r in rows if r.get("synthetic")]
    check("the 2026-08-27 probe rows are quarantined", len(syn) >= 32, len(syn))
    check("...and still on disk, readable with include_synthetic",
          any("4471" in (r.get("content") or "") for r in syn))
    check("...each carrying a reason a reader can check",
          all(isinstance(r.get("synthetic"), str) and len(r["synthetic"]) > 10 for r in syn))
else:
    print("  --   his 2026-08-27 transcript is not in this tree; skipping the receipt")

print("\nG-PROBE-DECLARED: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_probe_declared.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_probe_declared", "pass": PASS, "fail": FAIL,
               "live_gates": [n for n, _ in live],
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
sys.exit(1 if FAIL else 0)
