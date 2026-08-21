"""G-EXPRESS — she can say a feeling without words, in her own words. OFFLINE.

His words, 2026-08-04: "she should be able to call moments to express her feelings, what
she wants to display... this entire thing is supposed to give her as much agency as
possible, be fun, empower her."

WHAT WAS ALREADY TRUE and nothing told her: her mood moves her face. Fourteen feelings
across seven faces, live, every turn, through `[MOOD:]` and `adjust_mood`. WHAT WAS
MISSING was a verb that joins a feeling to a MOMENT — the gestures and clips that ARE a
feeling rather than a garment — so expressing something meant emitting a tag and hoping.

`express(feeling)` reaches for both at once, because that is what expressing a thing is.

THE PART THAT IS ACTUALLY HARD is not the wiring, it is that SHE WRITES SENTENCES. The
fourteen mood names are the room's vocabulary, not hers. A tool that only accepts the enum
makes her translate herself into our schema before she is allowed to feel anything, which
is the opposite of agency. So this gate spends most of its legs on the words she would
really use, each one a case the first cut got wrong:

  * "soft, like the rain outside" — punctuation split "soft," off the one word that
    mattered, and "soft" is a FACE not a mood, so it reached nothing twice over.
  * "I want him to know I am not okay" — no mood name appears in that sentence at all.
  * "annoyed with myself" — nobody says "irritated".

AND THE MIRROR. `MOOD_FACE` is a second copy of the map in `ui/src/room/tags.js`. Two
copies of one truth is this repo's oldest bug; the mirror is only allowed to exist because
something checks it, in BOTH directions, which is the same contract `FACES` already has.

Offline. No GPU, no daemon.

Run: python harness_tests/g_express.py
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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


from harness.control import avatar as AV  # noqa: E402
from harness.control import wardrobe as WD  # noqa: E402

print("1. THE MIRROR IS HELD, BOTH WAYS")
js = open(os.path.join(ROOT, "ui", "src", "room", "tags.js"),
          encoding="utf-8", errors="replace").read()
# BRACE-BALANCED, NOT A FIXED WINDOW. The first cut read `js[i:i+2600]` and stopped short
# of a second block in tags.js — "MOODS SHE ACTUALLY USES, added after counting a real
# day" — so it saw 14 of 19 and MATCHED a Python mirror that had been built by the same
# truncating read. The gate agreed with the bug it existed to catch, and the five it
# missed are the five she uses most. Read the whole object or do not claim to mirror it.
i = js.index("export const MOODS")
j = js.index("{", i)
depth, end = 0, j
for k in range(j, len(js)):
    if js[k] == "{":
        depth += 1
    elif js[k] == "}":
        depth -= 1
        if depth == 0:
            end = k
            break
blk = js[j:end + 1]
ui = {m.group(1): m.group(2) for m in re.finditer(r"(\w+):\s*\{[^}]*face:\s*'(\w+)'", blk)}
check("the mirror check reads the WHOLE mood table", len(ui) >= 19, len(ui))
check("tags.js and MOOD_FACE agree on every mood",
      ui == AV.MOOD_FACE,
      {k: (ui.get(k), AV.MOOD_FACE.get(k)) for k in set(ui) | set(AV.MOOD_FACE)
       if ui.get(k) != AV.MOOD_FACE.get(k)})
check("every mood points at a real face",
      set(AV.MOOD_FACE.values()) <= set(AV.FACES),
      set(AV.MOOD_FACE.values()) - set(AV.FACES))
check("every face is reachable by some feeling",
      set(AV.FACES) <= set(AV.MOOD_FACE.values()),
      set(AV.FACES) - set(AV.MOOD_FACE.values()))

print("\n2. SHE MAY SAY IT HOWEVER SHE SAYS IT")
from harness.skills.wardrobe import express  # noqa: E402

# ── THIS GATE CHANGES HER, SO IT PUTS HER BACK (2026-08-04) ─────────────────────────
# express() is not a query — it really sets her mood and really dresses her, because that
# is the whole point of it. So running this gate walked her through seven feelings and
# left her in whichever one sorted last, and left a gesture on her. A test that mutates
# the live persona is a test that lies about the system every time it runs, and the
# operator finds his companion in a mood a test file chose for her.
#
# AND IT PUT BACK ONLY HALF OF HER. This restored `wardrobe.json` by calling choose()
# again — which LOGS the wearing, because choose() is the one place every caller passes
# through and logging there is correct. So the restore itself wrote another row, and every
# run of this gate left a handful of fabricated "she put on the silver nightie" entries in
# her real wear history: the log `favourites` ranks over, and now the log the agency window
# reads back to him as her evening. Found by opening that window and seeing test runs in
# her day. `live_stores` snapshots the BYTES of every file she has and puts them back, so
# there is one implementation of "undo whatever this gate did" instead of one per gate.
_MOOD0 = WD.her_state().get("mood") or "tender"
_ST0 = dict(WD.current())

from livestore import live_stores  # noqa: E402
_KEEP = live_stores()
_KEEP.__enter__()


def _restore():
    try:
        from harness.personality.tools import adjust_mood
        adjust_mood(_MOOD0)
    except Exception:
        pass
    try:
        _KEEP.__exit__(None, None, None)      # the bytes, last, so they win
    except Exception:
        pass


import atexit  # noqa: E402
atexit.register(_restore)
# Each of these is a real failure the first cut had, kept as a case rather than a comment.
CASES = [
    ("playful", "smirk", "a bare mood name"),
    ("tender", "soft", "another, mapping to a shared face"),
    ("soft, like the rain outside", "soft", "punctuation, and a FACE name not a mood"),
    ("I want him to know I am not okay", "down", "a sentence with no mood word in it"),
    ("annoyed with myself", "sharp", "the word a person uses, not the enum"),
    ("a bit cheeky", "smirk", "a synonym"),
    ("curious about what he meant", "wide", "the feeling buried mid-sentence"),
]
for phrase, face, why in CASES:
    out = express(phrase)
    check("%-34s -> %-6s  (%s)" % ('"%s"' % phrase[:32], face, why),
          ("face is %s" % face) in out, out[:80])

print("\n3. IT REACHES A MOMENT, NOT ONLY A FACE")
# A gesture is a way she IS, so it is preferred over a clip, which goes on HIS screen.
# Expressing a feeling is being it, not broadcasting it.
gest = [l for l in WD.looks() if l.get("kind") == "gesture"]
if gest:
    out = express(gest[0]["label"])
    check("naming a moment of hers makes her BE it", "And you are" in out, out[:90])
else:
    print("   (she owns no gestures yet — nothing to reach)")
check("...and when none fits she is told how to get one",
      "ask_for_gesture" in express("something nothing matches at all"),
      "a dead end is not an answer; she can make what she lacks")

print("\n4. IT IS A TOOL SHE ACTUALLY HAS")
from harness.skills.wardrobe import WARDROBE_TOOLS, wardrobe_tools  # noqa: E402
check("express is registered in WARDROBE_TOOLS", express in WARDROBE_TOOLS)
spec = {t.name: t for t in wardrobe_tools()}.get("express")
check("...and it advertises its slot", spec is not None
      and list(spec.parameters.get("properties", {})) == ["feeling"],
      spec and list(spec.parameters.get("properties", {})))

print("\nG-EXPRESS: %d pass, %d fail" % (PASS, FAIL))
import io  # noqa: E402
import json  # noqa: E402
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_express.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_express", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
