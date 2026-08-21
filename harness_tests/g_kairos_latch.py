"""G-KAIROS-LATCH — the four ways she was held silent, and the thought that was binned.

She had not spoken up in days. The machinery was alive the whole time — `var/gateway.log`
shows decide() running every 15 s — but four latches and one empty queue meant almost
nothing could reach him. None of them is a missing feature; all four are state that
outlives its purpose.

  1. SHE COULD NOT SPEAK FIRST AFTER A RESTART, EVER. `_LAST` is filled only by
     `on_reply`, and it holds a CLOSURE — the ability to run one more turn against a live
     history — which no process survives. So until HE spoke, `tick_once` iterated an empty
     dict. Every continuity phase spanning a restart was silent by construction, which is
     precisely the window (asleep, away) where initiative is the whole point. Fixed by
     rebuilding the closure from the day's transcript, which only became possible on
     2026-08-01 when the day started being written to disk for the consolidator: two
     fixes, filed against different bugs, turn out to be one fix.

  2. ONE QUESTION MUTED THE SESSION. `tick_once` re-passes her LAST reply on every beat,
     so a reply ending in "?" kept matching `_asked_a_question` forever. She asks ~6
     questions per 30 turns (CONTINUITY.md:127), so a large share of every idle window was
     permanently dead. The rule is about a silence she JUST created; once he has been
     quiet longer than the check-in threshold, the silence is simply him being away, and
     noticing that IS checking in.

  3. A THOUGHT THAT LOST THE TIMING RACE WAS DESTROYED. `reflect_tick()` latches its
     cooldown the moment it runs, so a conclusion arriving while decide() said SILENT was
     dropped and — for the next 1800 s — could not be recomputed. Measured: she spoke at
     20:41:52 and a 4.0-bit reflection landed at 20:42:04, twelve seconds too late.
     `_PENDING_INSIGHT` was declared for exactly this and referenced NOWHERE.

  4. `max_chain = 1` forbade the follow-on. One unprompted remark latched her silent until
     he spoke — including her reminders' poor cousin, the MUSE.

Offline. Pure policy: `decide()` takes `now`, `rng` and its inputs by injection, so every
case below is determinable without a daemon.
"""
from __future__ import annotations

import io
import json
import os
import random
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
        print("  FAIL %s %s" % (name, detail))


from harness.kairos import scheduler as S              # noqa: E402
from harness.kairos.impulse import (                   # noqa: E402
    CHECK_IN, MUSE, SILENT, KairosConfig, TurnState, decide, note_spoke, note_user,
)

CFG = KairosConfig(enabled=True, max_chain=2, cooldown_s=45.0, max_per_hour=6,
                   checkin_idle_s=240.0, checkin_chance=1.0)
ALWAYS = random.Random(0)


class Sure(random.Random):
    """checkin_chance is a coin flip; this gate is about the LATCHES, not the coin."""
    def random(self):  # noqa: D102
        return 0.0


def d(state, now, reply="ok.", insight=None, margin=None):
    return decide(cfg=CFG, state=state, now=now, reply_text=reply,
                  eot_margin=margin, insight=insight, rng=Sure())


print("1. SHE CAN SPEAK FIRST AFTER A RESTART")
S._LAST.clear()
S._STATE.clear()
check("a fresh process has nothing to speak into — this is the bug",
      not S._LAST)
# SEEDING IS OPT-IN SINCE 2026-08-20 (his order: "she shouldn't act first at bounce").
# This gate tests the SEAM, not his knob — arm it for the run and put his choice back.
from harness.tuning import registry as _tune_seed  # noqa: E402
import atexit as _atexit_seed  # noqa: E402
_seed_was = _tune_seed.chosen("kairos.seed_on_boot")
_tune_seed.set_many({"kairos.seed_on_boot": True})
_atexit_seed.register(lambda: (_tune_seed.reset("kairos.seed_on_boot") if _seed_was is None
                               else _tune_seed.set_many({"kairos.seed_on_boot": bool(_seed_was)})))
ok = S.seed("room", "I was just thinking about the room.", lambda nudge: "…")
check("seeding from the day's transcript gives her one", ok and "room" in S._LAST)
check("...and starts her idle clock, so CHECK_IN is reachable at all",
      S._STATE["room"].last_user_at > 0)
# CHECK_IN reads `state.last_user_at`; at the 0.0 default it is unreachable forever.
st = S._STATE["room"]
check("she does NOT blurt the moment the process comes up",
      d(st, st.last_user_at + 5.0).action == SILENT)
check("...and after the quiet threshold she may check in",
      d(st, st.last_user_at + CFG.checkin_idle_s + 1).action == CHECK_IN)
before = S._LAST["room"]
check("a live conversation is never clobbered by a rebuilt one",
      S.seed("room", "different", lambda n: "x") is False and S._LAST["room"] is before)
check("an empty day seeds nothing rather than a hollow session",
      S.seed("other", "   ", lambda n: "x") is False)

print("\n2. ONE QUESTION NO LONGER MUTES THE SESSION")
st = TurnState()
note_user(st, 1000.0)
check("right after she asks, she waits — the rule keeps its force",
      d(st, 1005.0, reply="Did you sleep alright?").action == SILENT)
check("...still waiting well into the window",
      d(st, 1000.0 + CFG.checkin_idle_s - 1, reply="Did you sleep alright?").action == SILENT)
check("but once HE has been quiet longer than that, she may speak",
      d(st, 1000.0 + CFG.checkin_idle_s + 1, reply="Did you sleep alright?").action != SILENT)
check("a reply that is NOT a question was never muted",
      d(st, 1000.0 + CFG.checkin_idle_s + 1, reply="Sleep well.").action != SILENT)

print("\n3. A THOUGHT WAITS FOR ITS MOMENT INSTEAD OF DYING AT IT")
src = io.open(os.path.join(ROOT, "harness", "kairos", "scheduler.py"),
              encoding="utf-8").read()
check("_PENDING_INSIGHT is actually wired now, not just declared",
      src.count("_PENDING_INSIGHT") >= 4, "declared and unreferenced was the bug")
check("...it is cleared once she has SAID it",
      "_PENDING_INSIGHT.clear()       # spoken" in src)
check("...and it has a shelf life, so a cold thought is not delivered hours later",
      "reflect.cooldown_s" in src.split("a held thought went stale")[0][-900:])

# THE RETENTION ITSELF, EXECUTED — the source checks above would pass on a version that
# stashed the thought and never read it back, which is exactly the state this code was
# found in. Drive tick_once with a reflection that arrives once and see it survive.
_held = {"text": "Sam has been quieter this week.", "bits": 4.0}
_real_reflect, _real_cfg = S.reflect_tick, S.live_config
_calls = {"n": 0}


def _reflect_once(now=None):
    _calls["n"] += 1
    return dict(_held) if _calls["n"] == 1 else None


try:
    S.reflect_tick = _reflect_once
    S.live_config = lambda: KairosConfig(enabled=True, max_chain=0)   # decide() -> SILENT
    S._PENDING_INSIGHT.clear()
    S._LAST.clear()
    S._STATE.clear()
    S.tick_once(now=5000.0)
    check("a thought that arrives at a bad moment is HELD, not binned",
          S._PENDING_INSIGHT.get("text") == _held["text"], dict(S._PENDING_INSIGHT))
    S.tick_once(now=5015.0)          # reflect_tick now returns None, as the cooldown does
    check("...and is still there on the next beat, when it could not be recomputed",
          S._PENDING_INSIGHT.get("text") == _held["text"], dict(S._PENDING_INSIGHT))
    # AND IT IS ACTUALLY READ BACK. Stashing a thought and never offering it again is the
    # same silence with extra bookkeeping — an earlier version of this section passed with
    # the read-back deleted, so the moment that matters is now the one under test: a beat
    # where nothing blocks her must SPEAK the held thought (MUSE clears it on the way out).
    S.seed("room", "Earlier I was saying…", lambda nudge: "")
    S.live_config = lambda: KairosConfig(enabled=True, max_chain=2, cooldown_s=0.0,
                                         max_per_hour=6, checkin_idle_s=240.0)
    S.tick_once(now=5030.0)
    for _t in list(S._TIMERS.values()):
        _t.cancel()
    check("...and on a beat when nothing blocks her, the HELD thought is what she speaks",
          not S._PENDING_INSIGHT, dict(S._PENDING_INSIGHT))

    # the shelf life, on a fresh hold
    S._PENDING_INSIGHT.clear()
    S._LAST.clear()
    S._STATE.clear()
    _calls["n"] = 0
    S.live_config = lambda: KairosConfig(enabled=True, max_chain=0)
    S.tick_once(now=6000.0)
    S.tick_once(now=6000.0 + 1801.0)
    check("...and is dropped once it goes stale rather than delivered cold",
          not S._PENDING_INSIGHT, dict(S._PENDING_INSIGHT))
finally:
    S.reflect_tick, S.live_config = _real_reflect, _real_cfg
    S._PENDING_INSIGHT.clear()
# and the policy half: an insight offered while she is chained must not be spoken
st = TurnState()
note_user(st, 2000.0)
INSIGHT = {"text": "Sam has been quieter this week.", "bits": 4.0}
check("a surprising thought speaks when nothing blocks it",
      d(st, 2010.0, insight=INSIGHT).action == MUSE)
note_spoke(st, 2010.0)
note_spoke(st, 2100.0)                       # chain now at the limit
check("...and is correctly withheld once she is at the chain limit — the case that "
      "used to DESTROY it", d(st, 2200.0, insight=INSIGHT).action == SILENT)

print("\n4. THE FOLLOW-ON HE ASKED FOR IS PERMITTED, AND STILL BOUNDED")
st = TurnState()
note_user(st, 3000.0)
note_spoke(st, 3010.0)                       # she spoke once, unprompted
check("she may follow on from herself once",
      d(st, 3010.0 + CFG.cooldown_s + 1, insight=INSIGHT).action == MUSE)
note_spoke(st, 3060.0)
check("...but not a third time — she waits for him",
      d(st, 3200.0, insight=INSIGHT).action == SILENT)
note_user(st, 3300.0)
check("his turn buys her a fresh budget", st.chain == 0)
check("...and she may speak again", d(st, 3310.0, insight=INSIGHT).action == MUSE)
check("the cooldown still holds inside a chain",
      d(TurnState(chain=0, last_spoke_at=3300.0, last_user_at=3000.0), 3310.0,
        insight=INSIGHT).action == SILENT)

print("\n5. SHE KNOWS SHE ALREADY SAID IT")
# _LAST was written only on HIS turns, so an unprompted message never advanced the
# context she generates against — and she repeated herself: the same check-in spoken
# twice 3m44s apart, one line FOUR times in two hours (speech.jsonl, 2026-08-02).
# worth_saying compares against "the previous reply", and the previous reply it was
# shown never moved. Not the poller, not StrictMode: she did not know she had spoken.
# EXECUTED, not grepped — _arm is driven with a fake generate and _LAST is inspected.
S._LAST.clear()
S._STATE.clear()
S.seed("rp", "the reply before she spoke", lambda nudge: "something she says unprompted")
# THE QUIET-AFTER-HIM GUARD (2026-08-20, his order: five minutes of quiet after his last
# word) would hold this fake turn — the seed stamps last_user_at = now. This leg tests
# that an unprompted turn ADVANCES _LAST, not the guard; open the window for the run.
_qah_was = _tune_seed.chosen("kairos.quiet_after_him_s")
_tune_seed.set_many({"kairos.quiet_after_him_s": 0.0})
_atexit_seed.register(lambda: (_tune_seed.reset("kairos.quiet_after_him_s") if _qah_was is None
                               else _tune_seed.set_many({"kairos.quiet_after_him_s": float(_qah_was)})))
_real_cfg2 = S.live_config
try:
    S.live_config = lambda: KairosConfig(enabled=True, max_chain=3, cooldown_s=0.0,
                                         max_per_hour=6, checkin_idle_s=0.0,
                                         checkin_chance=1.0,
                                         checkin_delay=(0.0, 0.0))
    imp = S.decide(cfg=S.live_config(), state=S._STATE["rp"], now=time.monotonic(),
                   reply_text="the reply before she spoke", eot_margin=None) \
        if False else None
    S._arm("rp", __import__("harness.kairos.impulse", fromlist=["Impulse"]).Impulse(
        CHECK_IN, delay_s=0.0, reason="test"), "the reply before she spoke",
        S._LAST["rp"][1], None)
    import time as _t
    for _ in range(80):
        _t.sleep(0.05)
        if S._LAST["rp"][0] != "the reply before she spoke":
            break
    check("an unprompted turn advances the reply she is compared against",
          S._LAST["rp"][0] == "something she says unprompted", S._LAST["rp"][0])
    check("...and the closure survives to continue from",
          callable(S._LAST["rp"][1]))
finally:
    S.live_config = _real_cfg2

S._LAST.clear()
S._STATE.clear()
print("\nG-KAIROS-LATCH: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_kairos_latch.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_kairos_latch", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
