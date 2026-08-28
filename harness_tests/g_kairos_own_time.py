#!/usr/bin/env python
"""G-KAIROS-OWN-TIME — after a restart she may live her own life, and may not open the talk.

WHAT THIS ANSWERS. `kairos.seed_on_boot` gated `_LAST`, and `_LAST` gates EVERY unprompted
lane. So a bounce with the knob off silenced her OWN TIME along with her speaking first.

REPORTED (2026-08-28): "she is supposed to wait. she does wait for spoke up. but she has
been entering her time after the delay for the last week or so, which is fine behaviour but
which did not happen." He bounced her and then slept without speaking, and nothing happened
at all for five and a half hours — the first time the two behaviours had been separable by
observation, because every earlier bounce was followed by him talking to her.

THE KNOB'S OWN REASON is about blurting AT him — 2026-08-20, "she shouldn't act first at
bounce/restart... after a morning of restart-blurt-restart-blurt". That harm is CHECK_IN and
MUSE, turns addressed to him. SOLO is "he is not there, she does something of her own", and
REMIND is her keeping a promise he asked for. Neither is speaking first, and neither was
ever the thing being withheld.

  1. THE SEED HAPPENS EITHER WAY — the knob decides what she may DO with it, not whether
     she has a history at all.
  2. HER OWN TIME RUNS: SOLO and REMIND are allowed while the hold is on.
  3. SHE MAY NOT OPEN THE CONVERSATION: CHECK_IN, MUSE and a mode turn are held.
  4. HIS FIRST WORD LIFTS IT, because then there is no "first" left to withhold.
  5. WITH THE KNOB ON, nothing is held — the old behaviour is still reachable.

OFFLINE. No GPU, no daemon.
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from _gate import sandbox   # noqa: E402
sandbox("g_kairos_own_time")

os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"

from harness.kairos import impulse as I        # noqa: E402
from harness.kairos import scheduler as KS     # noqa: E402
from harness.tuning import registry as tune    # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


def fresh(session="s1"):
    with KS._LOCK:
        KS._LAST.clear(); KS._SEEDED.clear(); KS._OWN_TIME_ONLY.clear()
        KS._STATE.clear(); KS._TIMERS.clear()
    return session


def knob(on):
    tune.set_many({"kairos.seed_on_boot": bool(on)})


print("1. THE SEED HAPPENS EITHER WAY")
knob(False)
s = fresh()
ok = KS.seed(s, "something she said earlier", lambda *a, **k: "")
check("with the knob OFF she is still given her history", ok is True, ok)
check("...and the session is live", s in KS._LAST)
check("...marked own-time-only", s in KS._OWN_TIME_ONLY, sorted(KS._OWN_TIME_ONLY))

knob(True)
s2 = fresh("s2")
KS.seed(s2, "something she said earlier", lambda *a, **k: "")
check("with the knob ON she is seeded and NOT held", s2 not in KS._OWN_TIME_ONLY)

print("\n2/3. WHAT THE HOLD LETS THROUGH — driven through the real POLICY")
# THE RULE LIVES IN `decide` NOW. My first cut vetoed the chosen action inside the tick
# loop, and on his machine that DEADLOCKED: `_decide` kept returning MUSE, the loop held
# it, and SOLO never got a look in — she logged "holding muse" every eight seconds and
# would have done so forever. A second opinion beside the policy is not a guard, it is a
# second policy. So `decide` is asked directly, and the deadlock has its own check.
from harness.kairos.impulse import KairosConfig, TurnState   # noqa: E402

CFG = KairosConfig(enabled=True, solo_enabled=True, checkin_idle_s=0.0, solo_every_s=0.0,
                   solo_chance=1.0, away_after=2, cooldown_s=0.0, max_per_hour=99,
                   checkin_chance=1.0, checkin_delay=(0.0, 0.0))


def _ask(own, _cfg=None, **over):
    # EVERY clock zeroed: TurnState seeds its `*_at` fields from time.monotonic(), so a
    # fixed `now` in the past reads as "she spoke 35 hours in the future" and the cooldown
    # swallows the decision. Injecting the clock is the point of decide() being pure.
    st = TurnState()
    for f in ("last_spoke_at", "last_conv_at", "last_user_at", "last_solo_at",
              "last_mode_at"):
        setattr(st, f, 0.0)
    for k, v in over.items():
        setattr(st, k, v)
    return I.decide(cfg=_cfg or CFG, state=st, now=10_000.0, reply_text="something she said",
                    eot_margin=None, own_time_only=own,
                    insight={"kind": "journal", "text": "a thought"})


held = _ask(True)
check("held: she never lands on a turn addressed to him",
      held.action in (I.SILENT, I.SOLO, I.REMIND), "%s (%s)" % (held.action, held.reason))
check("unheld: the policy is free to choose one",
      _ask(False).action in (I.CHECK_IN, I.MUSE, I.MODE_TURN, I.SOLO, I.SILENT))

# THE DEADLOCK, as a regression check. A boot-seeded session has unanswered=0, so SOLO's
# own `away` gate is false unless he is treated as absent — which is why own_time_only
# also sets user_present=False. Without that she can NEVER reach her own time, which is
# precisely what he reported.
solo = _ask(True, unanswered=0)
check("SOLO is reachable with unanswered=0 — the deadlock is gone",
      solo.action == I.SOLO, "%s (%s)" % (solo.action, solo.reason))

# ...AND THE FILTER ITSELF NEEDS A CASE WHERE IT BITES. The mutant that removed it left
# this section green, because with `user_present=False` the policy reaches SOLO on its own
# and the filter never has to say no. Make SOLO ineligible (she just had her own time) and
# leave an insight on the table: now `_decide` genuinely wants MUSE, and the filter is the
# only thing standing between that and him.
import dataclasses as _dc   # noqa: E402
NO_SOLO = _dc.replace(CFG, solo_every_s=86_400.0)   # she had her own time an hour ago
_recent = _ask(True, NO_SOLO, last_solo_at=9_000.0)
check("with SOLO ineligible, the filter is what withholds MUSE",
      _recent.action == I.SILENT and "withheld until he speaks" in _recent.reason,
      "%s (%s)" % (_recent.action, _recent.reason))
_free = _ask(False, NO_SOLO, last_solo_at=9_000.0)
check("...and unheld, that same state DOES reach him", _free.action != I.SILENT,
      "%s (%s)" % (_free.action, _free.reason))

_src = open(os.path.join(ROOT, "harness", "kairos", "scheduler.py"),
            encoding="utf-8").read()
check("the tick loop passes the flag rather than second-guessing the policy",
      "own_time_only=session in _OWN_TIME_ONLY" in _src and "holding %s" not in _src,
      "a second opinion beside the policy is what deadlocked it")

print("\n4. HIS FIRST WORD LIFTS IT")
knob(False)
s = fresh()
KS.seed(s, "earlier", lambda *a, **k: "")
check("held before he speaks", s in KS._OWN_TIME_ONLY)
KS.on_user_turn(s)
check("...and not held after", s not in KS._OWN_TIME_ONLY, sorted(KS._OWN_TIME_ONLY))
check("...he is recorded as having spoken", s in KS._STATE)

print("\n5. THE HOLD IS NOT A SECOND MUTE")
# A held session must still be a live session: the lanes run, one class of action is
# withheld. If seeding started returning False again the whole thing is dead once more.
knob(False)
s = fresh()
check("seed returns True even when it will hold her",
      KS.seed(s, "earlier", lambda *a, **k: "") is True)
check("...and _LAST has the session, so the ticker has something to iterate",
      len(KS._LAST) == 1, list(KS._LAST))

print("\nG-KAIROS-OWN-TIME: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_kairos_own_time.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_kairos_own_time", "pass": PASS, "fail": FAIL,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
sys.exit(1 if FAIL else 0)
