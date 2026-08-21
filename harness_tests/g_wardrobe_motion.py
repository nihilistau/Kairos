"""G-WARDROBE-MOTION — a still that is owed a loop must actually get one. OFFLINE.

THE DEFECT, 2026-08-04, in his words: "stills are showing in her wardrobe". Three of her
six looks — w004, w005, w006, every one of them the silver nightie — had a picture and no
loop, and the panel had been labelling them "still, moves overnight" for two days.

THE SHAPE OF IT is the reason this gate exists rather than a one-line fix and a shrug.

`avatar_gen.run_wants()` does BOTH halves of the job: stills for anything still `asked`,
then motion for anything that has a still and no loop. It used to return early when the
stills queue was empty. That was found, and fixed, and the fix carries this comment:

    # NO EARLY RETURN ON AN EMPTY STILLS QUEUE. It used to bail here, which made the
    # motion half — the half the docstring says this exists for — reachable only on a
    # night she happened to ask for something new. [...]
    # §0 again: work guarded on one of two paths runs on neither.

The fix went inside `run_wants`. It did not go into the CALLER — and the caller is where
the early return actually happens, because `run_consolidation` only launches the
subprocess when `wants(state="asked")` is non-empty. So the motion half remained reachable
only on a night she asked for something new: precisely the condition the inner fix was
written to remove, in the caller of the code that documents it.

`pending_motion()` — "made stills that have no loop yet — the boundary's work list" — had
been returning those three rows the entire time. Nothing called it.

So the assertion here is not "the loop generator works". It is that BOTH work lists are
consulted before the boundary decides it has nothing to do. A gate on the generator would
have stayed green through all of this, because the generator was never the problem.

Offline. Runs no generation, needs no GPU: it reads the decision, not the work.

Run: python harness_tests/g_wardrobe_motion.py
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["CUDA_VISIBLE_DEVICES"] = ""

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


APP = open(os.path.join(ROOT, "harness", "server", "app.py"),
           encoding="utf-8", errors="replace").read()
GEN = open(os.path.join(ROOT, "tools", "avatar_gen.py"),
           encoding="utf-8", errors="replace").read()

print("1. THE BOUNDARY CONSULTS BOTH WORK LISTS BEFORE DECIDING IT IS IDLE")
i = APP.index('"wardrobe.nightly"')
# THE WHOLE STEP, INCLUDING THE `else`. The first cut ended the slice at the else-branch's
# first statement, so the leg asserting the skip MESSAGE was reading a string that had been
# cut off — and reported a failure about text that was present three characters later. A
# gate that trims its own subject is testing the trim.
blk = APP[i:APP.index("except Exception as exc:", i)]
check("the nightly step reads wants(state='asked')", 'wants(state="asked")' in blk)
check("...AND pending_motion()", "pending_motion()" in blk,
      "the second work list is what w004/w005/w006 were sitting on")
# THE GUARD ITSELF, not merely the presence of the call. Reading `pending_motion()` and
# then still gating on `if pend:` would satisfy a naive grep and change nothing.
check("...and the launch guard tests BOTH, not just the stills queue",
      re.search(r"if\s+pend\s+or\s+motion\s*:", blk) is not None,
      "a call whose result never reaches the condition is decoration")
check("...and the skip message says both are empty, not just one",
      "no motion owed" in blk,
      "'nothing asked for' was true and misleading for two days")

print("\n2. THE GENERATOR'S OWN SECOND HALF IS STILL THERE")
# If this ever regresses, fixing the caller achieves nothing — so the gate holds both
# ends of the same rule rather than assuming the far end stays put.
rw = GEN[GEN.index("def run_wants("):GEN.index("def main(")]
check("run_wants still drains pending_motion after the stills",
      "pending_motion()" in rw)
check("...and still does not early-return on an empty stills queue",
      "NO EARLY RETURN" in rw,
      "the inner fix and the outer fix are the same rule; keep both")

print("\n3. THE WORK LIST IS REAL, AND IT AGREES WITH THE DISK")
from harness.control import wardrobe as WD  # noqa: E402
owed = WD.pending_motion()
looks = {l["id"]: l for l in WD.looks()}
print("   pending_motion(): %d — %s" % (len(owed), ", ".join(w["id"] for w in owed) or "none"))
# EVERY row it returns must be a still with no loop, and every still with no loop must be
# in it. A work list that disagrees with the folder in either direction is how three looks
# waited two days without anything reporting a problem.
stale = [w["id"] for w in owed if looks.get(w["id"], {}).get("moves")]
check("nothing in the work list already moves", not stale, stale)
missed = [i for i, l in looks.items()
          if l.get("kind") != "clip" and not l.get("moves")
          and i not in {w["id"] for w in owed}]
check("no still-without-a-loop is missing from the work list", not missed, missed)

print("\nG-WARDROBE-MOTION: %d pass, %d fail" % (PASS, FAIL))
import io  # noqa: E402
import json  # noqa: E402
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_wardrobe_motion.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_wardrobe_motion", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
