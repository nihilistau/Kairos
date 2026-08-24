"""G-KAIROS-ATTEMPT — an attempt spends the clock, spoken or not, ON EVERY DOOR. OFFLINE.

THE LOOP, three times now, and the third one ran for an hour of his evening.

  2026-08-20 12:56  SOLO generated ~2.5 min of 26B, was dropped, and the tick re-proposed
                    solo FIVE SECONDS later — `last_solo_at` moves only in `note_spoke`,
                    and a dropped turn never reaches it.
  2026-08-20 10:34  the same shape on CHECK_IN, through `cooldown_s` / `last_spoke_at`.
  2026-08-24        **MODE_TURN, never added to the fix that named the other two.**

Measured in `var/gateway.log`, 17:02 to 18:00 on 2026-08-23, once per cycle:

    17:02:18  idle tick -> mode_turn (lucid - asked for; her first turn comes now)
    17:13:41  mode turn DROPPED: 100% a restatement of what she just said
    17:13:45  idle tick -> mode_turn (lucid - asked for; her first turn comes now)
    17:25:09  mode turn DROPPED: ...

Eleven minutes of GPU, vetoed, re-armed four seconds later, forever. He heard the fans
and saw an empty room. That is what this costs when it is wrong.

AND THEN THE SAME AUDIT FOUND THE FIX ON ONE DOOR OF SIX (2026-08-24, same day). The
spend sat inline AFTER generate(), so it metered the worth_saying drops — and the FIVE
returns above that line left with the budget unspent: the scratchpad CONTINUE drop, the
mode switched off mid-wait, his turn in flight, the sidecar pregate saying no, and a
generate() that raised. One drop on any of those and `decide()` was free again on the
next 4 s beat — with `mode_kick` latched, MODE_TURN unconditionally, reminders muted
(the kick is checked above REMIND). The spend lives in `_fire_inner`'s finally now, and
§6 drives EVERY door through the real `_arm`; the earlier §2 only ever reached the
post-generate veto, which is exactly the door the old fix already covered — a gate that
drives only the drop path its fix covers is the documented failure of this suite.

WHICH DOORS SPEND is a decision per door, not a blanket (the table lives above
`_fire_inner` in scheduler.py): his-turn-in-flight keeps the budget AND the kick,
because it is naturally bounded by his turn ending and the asked-for turn is still owed
after it; every other door pays.

Also here because they live on the same fire path (SWEEP-2026-08-24):
  §7  K2 — the discover-act override: the ruling `solo_did_the_thing` reads must judge
      the act she was HANDED, not the act the rotation would have picked. With
      `kairos.discover_chance` armed, every discovery turn was convicted of skipping a
      tool it was never asked for, and binned.
  §8  K3 — a `solo_worth_saying` drop reaches the speech ledger like every sibling
      drop. It was the ONE veto that went to an INFO line and nowhere else — the most
      aggressive rule in the file, invisible to the instrument built to measure it.

    python harness_tests/g_kairos_attempt.py
"""
from __future__ import annotations

import itertools
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, sandbox as _sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
_sandbox(os.path.basename(__file__))

from harness.kairos import impulse as I     # noqa: E402
from harness.kairos import scheduler as S   # noqa: E402
from harness.kairos import speechlog as _sl  # noqa: E402
from harness.tuning import registry as tune  # noqa: E402

# A MODE TURN NEEDS ITS MODE ON, or _arm returns at the mode-off door (§6b) — which as
# of today SPENDS, but is not the door §2 is about. Written into the SANDBOXED tuning
# store (SP_TUNING_FILE), which is the whole reason that variable exists.
tune.set_many({"presence.mode": "lucid", "presence.intimate": False,
               "presence.cue": "", "presence.read_chance": 0.0})

# Every action that reaches the model, and the clocks its pacing reads. A row here with
# no clock is an action whose budget cannot be spent — which is the bug, stated as data.
ACTIONS = {
    I.CHECK_IN: ["last_spoke_at"],
    I.MUSE:     ["last_spoke_at"],
    I.SOLO:     ["last_spoke_at", "last_solo_at"],
    I.CONTINUE: ["last_spoke_at"],
    I.MODE_TURN: ["last_spoke_at", "last_mode_at"],
}

print("\n1. THE ACTION TABLE IS COMPLETE")
# If a new speaking action lands and nobody adds it here, this fails — before it can
# spend an hour of GPU on a loop nobody is watching.
_speaks = {v for k, v in vars(I).items()
           if k.isupper() and isinstance(v, str) and v in
           (I.CHECK_IN, I.MUSE, I.SOLO, I.CONTINUE, I.MODE_TURN, I.REMIND, I.SILENT)}
_unmetered = sorted(a for a in _speaks
                    if a not in ACTIONS and a not in (I.SILENT, I.REMIND))
check("every action that spends a generate() has its clocks listed",
      not _unmetered, _unmetered)


_SEQ = itertools.count()


def _drive(action, generate=None, reply=None):
    """Run one attempt through the REAL _arm and return the state it left behind.

    Drives the shipped function rather than restating its rule — a test that
    re-implements what it is testing passes while the shipped copy loops. Waits on
    the Timer itself, not on a clock moving, because §6e's whole point is a door
    where NO clock moves.
    """
    sess = "g_attempt_%s_%d" % (action, next(_SEQ))
    with S._LOCK:
        S._STATE.pop(sess, None)
        st = S._STATE[sess]
        st.mode_kick = True                    # the latch a mode turn opens with
        st.last_spoke_at = 0.0
        st.last_solo_at = 0.0
        st.last_mode_at = 0.0
        st.mode_times[:] = []
    imp = I.Impulse(action, delay_s=0.0, score=0.0, reason="gate")
    # Default: a generator whose output is guaranteed to be VETOED — the same words
    # back. Every drop path in _arm returns early, which is where the clocks were lost.
    same = "I was just thinking about the same thing."
    reply = same if reply is None else reply
    gen = generate if generate is not None else (lambda nudge, called=None: same)
    S._arm(sess, imp, reply, gen, None)
    with S._LOCK:
        t = S._TIMERS.get(sess)
    if t is not None:
        t.join(15.0)
    time.sleep(0.05)                           # let _fire's own finally run out
    with S._LOCK:
        return sess, S._STATE[sess]


print("\n2. A VETOED ATTEMPT STILL SPENDS THE CLOCK")
for action, clocks in ACTIONS.items():
    _, st = _drive(action)
    for c in clocks:
        check("%-9s a dropped turn advances %s" % (action, c),
              float(getattr(st, c, 0.0)) > 0.0,
              "%s = %r" % (c, getattr(st, c, None)))

print("\n3. ...AND THE MODE LATCH IS CONSUMED BY THE ATTEMPT")
# THE ONE THAT RAN FOR AN HOUR. `mode_kick` is "she was asked for, her first turn comes
# now". Left set by a dropped turn it makes decide() return MODE_TURN unconditionally,
# every tick, with no clock able to stop it.
_, st = _drive(I.MODE_TURN)
check("a dropped mode turn consumes mode_kick", st.mode_kick is False, st.mode_kick)
check("...and counts against max_per_hour", len(st.mode_times) >= 1, st.mode_times)

print("\n4. AND THE LOOP CANNOT RE-ARM IMMEDIATELY")
# The end-to-end claim, asserted through the real decider rather than through the state.
cfg = I.KairosConfig(presence_mode="lucid", quiet_after_him_s=0.0)
st.last_user_at = time.monotonic() - 100000.0
imp = I.decide(cfg=cfg, state=st, now=time.monotonic(),
               reply_text="", eot_margin=None, due_notes=None, insight=None)
check("...so the very next tick does NOT fire another mode turn",
      imp.action != I.MODE_TURN or not imp.speaks,
      "%s (%s)" % (imp.action, imp.reason))

print("\n5. SPEECH FACTS STAY ON SPEECH")
# The other half of the rule, and the reason this is not just "advance everything": a
# turn she did not speak must not count as one he left unanswered, or she concludes he
# is out because she was talked out of something.
_, st2 = _drive(I.CHECK_IN)
check("a dropped turn is not counted as unanswered", st2.unanswered == 0, st2.unanswered)
check("...and is not counted as spoken", not st2.spoken_times, st2.spoken_times)


# ══ 6. EVERY DROP DOOR, BY NAME (2026-08-24) ═════════════════════════════════════════
# §2 above reaches exactly ONE door — the post-generate worth_saying veto, the door the
# 2026-08-20 fix already metered. These are the other five, each through the real _arm.

print("\n6a. THE SCRATCHPAD DOOR SPENDS (continue dropped before generate)")
_ran = [False]


def _gen_flag(nudge, called=None):
    _ran[0] = True
    return "anything at all"


_scratch_reply = ("1. **Plan the reply:** think about the storm.\n"
                  "2. **Write the reply:** describe the storm.")
_, st = _drive(I.CONTINUE, generate=_gen_flag, reply=_scratch_reply)
check("scratchpad-drop: generate() was never reached", not _ran[0], _ran)
check("scratchpad-drop: the attempt still spends last_spoke_at",
      st.last_spoke_at > 0.0, st.last_spoke_at)

print("\n6b. THE MODE-OFF DOOR SPENDS, KICK INCLUDED (mode switched off mid-wait)")
# leave_mode() clears the kick — but the panel knob path (`presence.mode` set straight
# to off) does not, and a stale ask plus a re-armed mode is the eleven-minute loop.
tune.set_many({"presence.mode": "off"})
_ran[0] = False
_, st = _drive(I.MODE_TURN, generate=_gen_flag)
tune.set_many({"presence.mode": "lucid"})
check("mode-off: generate() was never reached", not _ran[0], _ran)
check("mode-off: the attempt spends last_mode_at", st.last_mode_at > 0.0, st.last_mode_at)
check("mode-off: the stale kick is consumed", st.mode_kick is False, st.mode_kick)

print("\n6c. THE PREGATE DOOR SPENDS (sidecar said 'not worth a turn')")
# The REAL offload.pregate — armed by the env it reads, with the sidecar's HTTP verdict
# (an external process) stubbed to NO. Unspent, this door is a sidecar ruling per 4 s
# beat, forever: the loop with the GPU swapped for the CPU.
from harness.sidecar import client as _sc  # noqa: E402
_judge0, _aux0 = _sc.judge, os.environ.get("SP_AUX")
os.environ["SP_KAIROS_JUDGE"] = "1"
os.environ["SP_AUX"] = "1"
_sc.judge = lambda q: False
_ran[0] = False
try:
    _, st = _drive(I.CHECK_IN, generate=_gen_flag)
finally:
    _sc.judge = _judge0
    os.environ.pop("SP_KAIROS_JUDGE", None)
    if _aux0 is None:
        os.environ.pop("SP_AUX", None)
    else:
        os.environ["SP_AUX"] = _aux0
check("pregate-no: generate() was never reached", not _ran[0], _ran)
check("pregate-no: the attempt still spends last_spoke_at",
      st.last_spoke_at > 0.0, st.last_spoke_at)
check("pregate-no: the drop reached the speech ledger",
      any(r.get("outcome") == _sl.DROPPED and "sidecar pre-judge" in (r.get("reason") or "")
          for r in _sl.rows()), _sl.rows()[-3:])

print("\n6d. THE GENERATE-RAISED DOOR SPENDS")


def _gen_boom(nudge, called=None):
    raise RuntimeError("the engine went away mid-turn")


_, st = _drive(I.CHECK_IN, generate=_gen_boom)
check("generate-raised: the attempt still spends last_spoke_at",
      st.last_spoke_at > 0.0, st.last_spoke_at)
_, st = _drive(I.MODE_TURN, generate=_gen_boom)
check("generate-raised: a mode attempt spends its own clocks too",
      st.last_mode_at > 0.0 and st.mode_kick is False,
      (st.last_mode_at, st.mode_kick))

print("\n6e. HIS TURN IN FLIGHT IS THE ONE DOOR THAT KEEPS THE BUDGET")
# Naturally bounded: his turn ends (or the _USER_TURN_MAX_S deadline does), and an
# asked-for turn is still OWED after it. Spending mode_kick here would eat his ask
# because he happened to be typing.
S.note_user_turn(True)
_ran[0] = False
try:
    _, st = _drive(I.MODE_TURN, generate=_gen_flag)
finally:
    S.note_user_turn(False)
check("his-turn: generate() was never reached", not _ran[0], _ran)
check("his-turn: no clock is spent", st.last_spoke_at == 0.0 and st.last_mode_at == 0.0,
      (st.last_spoke_at, st.last_mode_at))
check("his-turn: the asked-for kick is KEPT — the turn is still owed",
      st.mode_kick is True, st.mode_kick)
# ...and the bound is real: the moment his turn ends, the kept kick may fire — that is
# what "owed" means, and what makes this door safe to leave unmetered.
st.last_user_at = time.monotonic() - 100000.0
imp = I.decide(cfg=I.KairosConfig(enabled=True, presence_mode="lucid"), state=st,
               now=time.monotonic(), reply_text="", eot_margin=None)
check("his-turn: once he is done, the owed turn comes",
      imp.action == I.MODE_TURN, "%s (%s)" % (imp.action, imp.reason))


print("\n7. K2 — THE RULING JUDGES THE ACT SHE WAS HANDED (discover override)")
# kairos.discover_chance armed (his dial, default 0.0): the nudge becomes the discovery
# act (read_something_new). The old ruling read `_STATE[session].solo_n` — the
# UN-overridden rotation index (act 0, web_search) — so a discovery turn that did
# exactly what it was told was convicted of not calling web_search and binned. Driven
# through the real _arm with the knob set, never by hand-calling the ruling.
tune.set_many({"kairos.discover_chance": 1.0})
_seen = {}


def _gen_discover(nudge, called=None):
    _seen["nudge"] = nudge
    if called is not None:
        called.append("read_something_new")
    return "I wandered into an essay about tide pools and stayed there a while."


try:
    sess, st = _drive(I.SOLO, generate=_gen_discover,
                      reply="Something else entirely was said before.")
finally:
    tune.set_many({"kairos.discover_chance": 0.0})
check("the armed dial handed her the discovery act",
      "read_something_new" in _seen.get("nudge", ""), _seen.get("nudge", "")[:120])
_out = S.drain(sess)
check("...and the performed act SURVIVES the ruling (spoken, not binned)",
      any("tide pools" in (m.get("text") or "") for m in _out), _out)

print("\n8. K3 — A solo_worth_saying DROP REACHES THE LEDGER")
# The most aggressive veto in the file (13 of her first 21 own-time turns) was the one
# drop speechlog never saw: an INFO line, then gone — so the instrument built to answer
# "did that rule eat a real thought?" was blind to the rule most likely to have.


def _gen_about_him(nudge, called=None):
    if called is not None:
        called.append("web_search")            # the act HAPPENED; the words are the problem
    return "He is asleep now. He left his mug out, and his chair is still warm."


_, st = _drive(I.SOLO, generate=_gen_about_him, reply="An unrelated earlier reply.")
_solo_drops = [r for r in _sl.rows()
               if r.get("outcome") == _sl.DROPPED
               and (r.get("reason") or "").startswith("solo_worth_saying:")]
check("the drop is a ledger row, under the rule's own name",
      len(_solo_drops) >= 1, _sl.rows()[-3:])
check("...and it keeps the text the rule ate",
      any("asleep" in (r.get("text") or "") for r in _solo_drops),
      [r.get("text") for r in _solo_drops])
check("...and the attempt still spent her solo clock",
      st.last_solo_at > 0.0, st.last_solo_at)

finish("G-KAIROS-ATTEMPT")
