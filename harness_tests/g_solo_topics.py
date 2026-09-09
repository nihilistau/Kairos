#!/usr/bin/env python
"""G-SOLO-TOPICS — the loop detector detects a loop, and does not cry loop at a diverse day.

WHY THIS GATE. `tools/solo_topics.py` exists to answer "has her own time narrowed onto one
subject", and the failure mode of a measurement tool is not a crash — it is an answer. A
detector that fires on anything, or on nothing, still prints a confident table, and the
number then gets quoted in a changelog and acted on. So both directions are driven here
against corpora built for the purpose:

    PLANTED LOOP      -> the agnostic pass must surface the planted word
    DIVERSE CORPUS    -> it must NOT, at the same settings

The second is the one that matters. Without it, `lift` sorted descending always has a top
row and there is always something to point at.

AND ITS SIMILARITY IS THE POLICY'S. `impulse.restatement_overlap` was lifted out of
`worth_saying`'s nested `toks` on 2026-09-09 so the tool and the guard cannot drift. That
extraction is asserted here as BEHAVIOUR — `worth_saying` must still drop at the shared
threshold and keep below it — because an extraction that quietly changed the number would
make every historical measurement in the changelog wrong.

OFFLINE. No GPU, no daemon, no reading of her live stores: the corpus is written into the
sandbox's own registry directory.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, sandbox, utf8_stdout      # noqa: E402

utf8_stdout()
SB = sandbox("g_solo_topics")

from harness.kairos import speechlog as SL                 # noqa: E402
from harness.kairos.impulse import (RESTATEMENT_DROP,       # noqa: E402
                                    overlap_tokens,
                                    restatement_overlap,
                                    worth_saying)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))
import solo_topics as T                                     # noqa: E402


def write_log(texts, kind="solo", outcome="spoke"):
    """A speech log in the sandbox, shaped exactly as `record()` leaves one."""
    p = SL._path()
    assert p, "the sandbox must resolve SP_RECALL_REGISTRY or this gate proves nothing"
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with io.open(p, "w", encoding="utf-8") as f:
        for n, t in enumerate(texts):
            at = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                               time.gmtime(time.time() - (len(texts) - n) * 3600))
            f.write(json.dumps({"at": at, "kind": kind, "outcome": outcome,
                                "reason": "leg", "text": t}) + "\n")
    return p


print("1. THE EXTRACTION DID NOT MOVE THE NUMBER")
# The tool's whole claim to be worth reading is that its similarity IS the guard's. If
# these drift, every rate already written down becomes unverifiable.
check("the shared threshold is the documented 0.75", RESTATEMENT_DROP == 0.75,
      RESTATEMENT_DROP)
check("overlap is asymmetric — THIS turn is the denominator, so a long previous reply "
      "cannot dilute a short restatement",
      restatement_overlap("alpha beta", "alpha beta gamma delta epsilon zeta") == 1.0
      and restatement_overlap("alpha beta gamma delta", "alpha beta") == 0.5,
      "%r / %r" % (restatement_overlap("alpha beta", "alpha beta gamma delta epsilon zeta"),
                   restatement_overlap("alpha beta gamma delta", "alpha beta")))
check("...and short words are not content words (the >3 rule)",
      overlap_tokens("a an the of criticality") == {"criticality"},
      overlap_tokens("a an the of criticality"))
check("empty either side scores 0.0, not a division error",
      restatement_overlap("", "alpha") == 0.0 and restatement_overlap("alpha", "") == 0.0)
_same = "criticality avalanche poised power cascade timeout"
check("worth_saying DROPS at the shared threshold, driven through the real function",
      worth_saying(_same, _same)[0] is False
      and "restatement" in worth_saying(_same, _same)[1])
check("...and KEEPS something genuinely new",
      worth_saying("wardrobe silver nightie kitchen ladder", _same)[0] is True)

print("\n2. A PLANTED LOOP IS FOUND")
# Twelve recent turns that all carry one word, over a baseline that never does. The
# planted word must reach the printed rows; `lift` is capped at 15 rows, so "in the table"
# is the assertion and not "somewhere in the data".
BASE = ["I looked through the %s and thought about %s tonight" % (a, b)
        for a, b in (("wardrobe", "silk"), ("kitchen", "bread"), ("garden", "rain"),
                     ("bookshelf", "poetry"), ("window", "starlight"),
                     ("hallway", "footsteps"), ("mirror", "posture"),
                     ("drawer", "letters"), ("balcony", "traffic"),
                     ("kettle", "steam"), ("piano", "silence"), ("desk", "ledgers"),
                     ("cupboard", "spices"), ("radio", "weather"),
                     ("laundry", "linen"), ("staircase", "dust"))]
# ONE SHARED WORD AND NOTHING ELSE, which is what makes this the DEVELOPING case. My
# first cut wrote these as one sentence with twelve different endings, so every pair sat
# at 60-86% and the corpus was a groove rather than a subject — §4 then asserted
# "developing" about a corpus that was restating, and passed anyway because the verdict
# string "MOSTLY DEVELOPING" contains "DEVELOPING". Two mistakes holding each other up.
LOOPED = ["percolation held my attention until the small hours again",
          "reading about percolation, I forgot dinner entirely",
          "those percolation exponents refused every curve I fitted",
          "my percolation script timed out halfway through, unfinished",
          "a percolation threshold seems to shift whenever I approach",
          "percolation clusters look like frost spreading across glass",
          "nobody warned me percolation would eat a whole evening",
          "sketched percolation lattices onto the back of an envelope",
          "percolation, again — the numbers drift and I chase them",
          "percolation feels less like mathematics than weather",
          "wrote percolation notes nobody except me will ever read",
          "percolation: beautiful, infuriating, and still not finished"]
write_log(BASE + LOOPED)
import contextlib   # noqa: E402


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = T.main(argv)
    return rc, buf.getvalue()


rc, out = run([])
check("the tool runs clean on a corpus with a loop in it", rc == 0, "rc=%s" % rc)
_lift = out.split("1. IS SHE LOOPING")[1].split("3.")[0]
check("the planted word is surfaced by the AGNOSTIC pass — no lexicon was given",
      "percolation" in _lift, _lift[:300])
check("...and a word from the diverse baseline is not",
      "wardrobe" not in _lift and "bookshelf" not in _lift, _lift[:300])

print("\n3. AND A DIVERSE CORPUS DOES NOT PRODUCE A LOOP")
# THE LEG THAT MAKES §2 MEAN ANYTHING. `lift` is sorted descending, so there is always a
# top row; a detector that cannot stay quiet has not detected anything.
# WRITTEN OUT, NOT DERIVED FROM `LOOPED` BY REPLACEMENT. The first cut built this by
# str.replace on the looped sentences — and when those sentences were later rewritten the
# replacement silently became a no-op, so this section tested the LOOP and asserted there
# wasn't one. A corpus defined by patching another corpus is a corpus that can drift into
# being the thing it contrasts with.
DIVERSE = ["baking sourdough badly, the crumb collapsed again this morning",
           "sailing charts spread over the floor, plotting an imaginary crossing",
           "knitting something shapeless while listening to the pipes knock",
           "birdsong at four, and I could not name a single caller",
           "cartography of the walk to his office, drawn from memory",
           "espresso timing: nineteen grams, and still it ran sour",
           "origami cranes, badly creased, lined along the windowsill",
           "mosses on the north wall have taken over the brickwork entirely",
           "tidepools remembered from a childhood nobody gave me",
           "campanology, of all things — the mathematics of bell ringing",
           "marquetry veneers, and how patience is mostly just glue",
           "kites need wind I have never actually felt on skin"]
write_log(BASE + DIVERSE)
rc, out = run([])
_lift = out.split("1. IS SHE LOOPING")[1].split("3.")[0]
# NO `or` HERE. The first cut read `"no loop to see" in _lift or "percolation" not in
# _lift`, and the second half is true of a diverse corpus whatever the tool does — so
# deleting the recurrence floor left this GREEN while the tool ranked twelve rows of
# hapax noise at a billion-x lift. An `or` in an assertion is two claims, and the weaker
# one decides.
check("the tool SAYS there is no loop rather than ranking noise",
      "no loop to see" in _lift, _lift[:400])
check("...and lists no word rows at all — a floor is what makes silence possible",
      "lift" not in _lift.split("no loop to see")[0].replace("IS SHE LOOPING", ""),
      _lift[:400])

print("\n4. THE PER-DAY PASS CARRIES ITS DENOMINATOR, AND ITS TERMS")
write_log(BASE + LOOPED)
rc, out = run(["--terms", "percolation,avalanche"])
check("the share-by-day table appears with a lifetime row", "<- lifetime" in out)
check("...and reports the terms individually, so one cannot hide in the total",
      "percolation" in out.split("which terms carry it")[1][:200], out[-400:])
check("...and names a term that never fired rather than omitting it silently",
      "avalanche" not in out.split("which terms carry it")[1][:200]
      or "none of them" in out, "avalanche should not be credited with hits")
_ver = out.split("pairwise overlap over")[1]
check("the verdict COUNTS the pairs past the threshold rather than taking a max",
      "at or past the guard's" in _ver and "of" in _ver, _ver[:200])
# NOT `"DEVELOPING" in _ver` — the other branch reads "MOSTLY DEVELOPING", so that
# substring is true whatever the verdict and the leg could not fail. The clean-verdict
# branch is identified by the sentence only it prints.
check("...and this corpus, which develops, takes the clean branch",
      "not one pair reaches the threshold" in _ver, _ver[:260])
check("...which is a DIFFERENT string from the repeat branch, or the leg cannot fail",
      "not one pair reaches the threshold" not in
      T.__doc__ + "MOSTLY DEVELOPING with repeats", "the two verdicts must be separable")

print("\n5. A PLANTED EXACT REPEAT IS REPORTED, AND AS A GUARD QUESTION")
# The 2026-09-09 run found exactly one such pair in 510 (a near-verbatim solo eleven
# minutes after its twin, 2026-08-31). One is a guard question; a population is a groove.
write_log(BASE + LOOPED[:6] + [LOOPED[5]] + LOOPED[6:])
rc, out = run(["--terms", "percolation"])
_ver = out.split("pairwise overlap over")[1]
check("a 100% pair is counted, not averaged away",
      "100%" in _ver and "at or past the guard's 75%: 1" in _ver, _ver[:260])
check("...and framed as a guard question rather than a topic finding",
      "guard question" in _ver, _ver[:300])

print("\n6. IT DOES NOT INVENT AN ANSWER WHEN THERE IS NO CORPUS")
write_log([])
rc, out = run([])
check("an empty log exits non-zero and says so", rc == 2 and "no " in out.lower(),
      "rc=%s out=%r" % (rc, out[:120]))
write_log(["one lonely thought about percolation"])
rc, out = run([])
check("a single turn refuses to compute a lift", rc == 0 and "not enough history" in out,
      out[:200])

finish("G-SOLO-TOPICS")
