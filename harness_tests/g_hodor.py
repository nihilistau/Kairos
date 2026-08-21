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
check("long prev arms the classic 4-gram ban", c.self_repeat_ngram == 4)
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

print("\nG-HODOR: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_hodor.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_hodor", "pass": PASS, "fail": FAIL,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
sys.exit(1 if FAIL else 0)
