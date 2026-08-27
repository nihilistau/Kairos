#!/usr/bin/env python
"""G-KAIROS-OWN-TIME — after a restart she may live her own life, and may not open the talk.

WHAT THIS ANSWERS. `kairos.seed_on_boot` gated `_LAST`, and `_LAST` gates EVERY unprompted
lane. So a bounce with the knob off silenced her OWN TIME along with her speaking first.

HIS REPORT (2026-08-28): "she is supposed to wait. she does wait for spoke up. but she has
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

print("\n2/3. WHAT THE HOLD LETS THROUGH — driven through the real gate expression")
# NOT a re-derivation of the rule inside the gate. The first cut computed
# `s in _OWN_TIME_ONLY and action not in (SOLO, REMIND)` right here and asserted on its
# own arithmetic — which would have gone green on a tree where the loop never consulted
# the set at all. `decide` is replaced so the loop reaches each action in turn, `_arm`
# records whatever got through, and the assertion is about what the loop DID.
_real_decide, _real_arm = I.decide, KS._arm
ARMED = []


def _fake_arm(session, imp, *a, **k):
    ARMED.append(imp.action)


def _run(action):
    """One real tick with `decide` forced to this action. True if it was armed."""
    del ARMED[:]
    KS._arm = _fake_arm

    def forced(**kw):
        # `speaks` is a property (action != SILENT), not a field.
        return I.Impulse(action=action, reason="gate")

    I.decide = forced
    KS.decide = forced
    try:
        KS.tick_once()
    finally:
        I.decide, KS.decide, KS._arm = _real_decide, _real_decide, _real_arm
    return bool(ARMED)


knob(False)
for _a in (I.SOLO, I.REMIND):
    s = fresh(); KS.seed(s, "earlier", lambda *a, **k: "")
    check("%-9s runs — her own time is not speaking first" % _a, _run(_a))
for _a in (I.CHECK_IN, I.MUSE, I.MODE_TURN):
    s = fresh(); KS.seed(s, "earlier", lambda *a, **k: "")
    check("%-9s is HELD — it is a turn addressed to him" % _a, not _run(_a))

knob(True)
for _a in (I.CHECK_IN, I.MUSE):
    s = fresh(); KS.seed(s, "earlier", lambda *a, **k: "")
    check("%-9s runs once he has armed seed_on_boot" % _a, _run(_a))

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
