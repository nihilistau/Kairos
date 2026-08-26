#!/usr/bin/env python
"""G-HODOR — a short reply may repeat once; it may not become her whole vocabulary
(the operator's live transcript, 2026-07-15: "I know." x6 over SSE).

The self-repeat ban's >=5-word floor exists to spare short idioms — and it made
short-reply loops STRUCTURALLY INVISIBLE: a 2-word reply has no 4-grams, so the
degeneration attractor lives entirely below the floor. The Hodor clause escalates
instead of lowering the floor: the moment the last two assistant replies are
BYTE-IDENTICAL, the exact short sequence is banned at the sampler for the next turn.

The arming policy is finite; this gate walks ALL of it through the REAL
_arm_self_repeat_ban (the one convergence point both entry paths call — its own
docstring records the four times a guard got wired into one path of two):

    FORALL long prev (>=5 words):                 ngram=4 seeded from prev (unchanged)
    FORALL short prev, NOT identical to prev2:    unarmed (a second "Yes." is honest)
    FORALL short prev == prev2 (the loop, proven): ngram=min(2,words) seeded from prev
    FORALL empty history:                          unarmed
    FORALL already-armed cfg:                      untouched (explicit config wins)

OFFLINE. No GPU, no daemon.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from harness.agent import _arm_self_repeat_ban            # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, str(detail)[:200]))


class Cfg:
    self_repeat_ngram = None
    self_repeat_text = None


def arm(*assistant_replies, user_between=True):
    msgs = []
    for a in assistant_replies:
        msgs.append({"role": "user", "content": "something he said"})
        msgs.append({"role": "assistant", "content": a})
    msgs.append({"role": "user", "content": "the next turn"})
    cfg = Cfg()
    _arm_self_repeat_ban(cfg, msgs)
    return cfg


print("\n1. the long-reply law is unchanged")
c = arm("I have been thinking about the tide charts all morning")
# ── THE ORDER IS 8, AND IT IS A MEASUREMENT (2026-08-27) ─────────────────────────────
# It was 4, and 4 collides with ordinary English. His report: `won'll` and `aren-re` in
# one reply. Her previous reply ended "...when you aren't drifting off" — and in the very
# next reply `didn't`, `shouldn't` and `I'll` were fine while `aren't` came out `aren-re`.
# The ban masks TOKEN n-grams; `aren't` is `aren` + `'t`, and a masked `'t` takes the
# next-best SUB-WORD token. Measured over 1,497 of her real consecutive reply pairs:
# n=4 collides on 6% of them (12% before marks were stripped from the ban text), n=8 on
# 1% — while still banning 10 of the 15 genuine parrot pairs, including the one
# byte-identical pair this guard exists for.
check("a long previous reply arms the ban", c.self_repeat_ngram == 8, c.self_repeat_ngram)
# NOT "== 8" ALONE. A constant restated in a gate only proves someone typed it twice.
# What must hold is the PROPERTY the number was chosen for: long enough that her ordinary
# prose does not trip it, short enough to still catch a reply repeated verbatim.
check("...long enough that her idiolect does not collide",
      c.self_repeat_ngram > len("i was just thinking".split()) + 1, c.self_repeat_ngram)
check("...and short enough that a verbatim repeat is still inside it",
      c.self_repeat_ngram <= len((c.self_repeat_text or "").split()),
      (c.self_repeat_ngram, len((c.self_repeat_text or "").split())))
c = arm("short one", "I have been thinking about the tide charts all morning")
check("...seeded from the LAST reply only", c.self_repeat_text.startswith("I have been"))

print("\n2. a short reply may repeat once")
c = arm("I know.")
check("one short reply: unarmed", c.self_repeat_ngram is None)
c = arm("Yes.", "I know.")
check("two DIFFERENT short replies: unarmed", c.self_repeat_ngram is None)

print("\n3. the Hodor clause: the proven loop is banned at the sampler")
c = arm("I know.", "I know.")
check("two identical short replies arm the exact-sequence ban",
      c.self_repeat_ngram == 2 and c.self_repeat_text == "I know.",
      (c.self_repeat_ngram, c.self_repeat_text))
c = arm("Yes.", "Yes.")
check("a one-word loop arms a 1-gram ban (one-turn cost, loop broken)",
      c.self_repeat_ngram == 1 and c.self_repeat_text == "Yes.")
c = arm("I know.", "Yes.", "I know.")
check("non-CONSECUTIVE repeats do not arm (she may return to a phrase)",
      c.self_repeat_ngram is None)

print("\n4. edges")
c = arm()
check("empty history: unarmed", c.self_repeat_ngram is None)
cfg = Cfg()
cfg.self_repeat_ngram = 7
_arm_self_repeat_ban(cfg, [{"role": "assistant", "content": "I know."},
                           {"role": "assistant", "content": "I know."}])
check("an explicitly-armed cfg is never overridden", cfg.self_repeat_ngram == 7)
c = arm("I know.  ", "I know.")
check("whitespace does not defeat identity", c.self_repeat_ngram == 2)


# ── 5. HER MARKS ARE NOT HERS TO PARROT — THE BAN MAY NOT EAT THE CONTROL SURFACE ────
# The ban's own docstring is a two-step narrowing: whole prompt -> her previous reply.
# It was still one step too wide. Her previous reply CONTAINS her marks, so the 4-grams
# spanning `[MOOD:tender] [VOICE:soft]` went into the ban set and the sampler could not
# spell them on the next turn.
#
# MEASURED over 17 days of her real transcripts (2026-08-27): 70 of 230 distinct mark
# shapes sit within two edits of one she uses constantly — VOICE <- VOIC, VO_ICE, VOIX,
# VOILCE; MOOD <- MOODLY, MOOR, MOOT, MOORD, MO_OD; TRAIT <- TRAIL, TAIL, TRA_IT — and
# three consecutive turns read `[MOOD::tender] [VO_ICE:soft]` where the PREVIOUS turn
# contained MOOD and VOICE. That was written down as "she invents new spellings faster
# than they can be enumerated": a bug of ours, recorded as a fact about her.
print("\n5. the ban is seeded from her WORDS, not her machinery")
_marked = ("[MOOD:tender] [VOICE:soft] I have been thinking about the shape of the week "
           "and how quiet it has been between us lately.")
c = arm(_marked)
check("a marked reply still arms the ban", c.self_repeat_ngram == 8,
      c.self_repeat_ngram)
check("...and NO mark reaches the ban text",
      not any(k in (c.self_repeat_text or "")
              for k in ("[MOOD", "[VOICE", "[TRAIT", "[WEAR", "[SHOW")),
      c.self_repeat_text)
check("...so she can spell [MOOD:] and [VOICE:] again next turn",
      "MOOD" not in (c.self_repeat_text or "") and "VOICE" not in (c.self_repeat_text or ""),
      c.self_repeat_text)
# SURVIVAL, not just removal: a ban that stripped everything would pass the checks above
# and stop guarding parroting at all.
check("...while HER WORDS are still in the ban text",
      "thinking about the shape" in (c.self_repeat_text or ""), c.self_repeat_text)
check("...including the tail", "between us lately" in (c.self_repeat_text or ""),
      c.self_repeat_text)

# Voice tags are the same class: a fixed vocabulary the TTS reads, not prose she invented.
_voiced = ("<whisper>I keep coming back to that evening by the window</whisper> [breath] "
           "and I do not know how to put it down.")
c = arm(_voiced)
check("voice tags do not reach the ban text either",
      not any(k in (c.self_repeat_text or "") for k in ("<whisper", "[breath", "</whisper")),
      c.self_repeat_text)
check("...and the words they wrapped survive",
      "evening by the window" in (c.self_repeat_text or ""), c.self_repeat_text)

# The Hodor clause compares two short replies for identity. Two "I know."s that differ
# only by a mood mark are the SAME reply and must still trip it.
c = arm("[MOOD:flat] I know.", "[MOOD:tired] I know.")
check("two short replies differing only by a mark are still identical to the clause",
      c.self_repeat_ngram == 2, c.self_repeat_ngram)

print("\nG-HODOR: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_hodor.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_hodor", "pass": PASS, "fail": FAIL,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
sys.exit(1 if FAIL else 0)
