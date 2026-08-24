"""G-KAIROS-QUIET — his quiet is the clock, and speaking first is a choice. OFFLINE.

Two operator rules, 2026-08-20 ("perhaps the spoke up and continuation should be
set to 5 minutes after I last say anything and she shouldn't act first at
bounce/restart like before. make them knobs defaulted to off."):

  1. kairos.quiet_after_him_s — no discretionary speak-up (check_in / continue /
     expand / muse) until N seconds since HE last said anything, in any session.
     The existing checkin_idle_s measures the SESSION's quiet, which includes her
     own speech — measured 10:11:07 check_in then 10:11:55 muse with him silent
     throughout. Reminders and her own time are deliberately not gated.
  2. kairos.seed_on_boot — seed() is the mechanism that lets her open the
     conversation after a restart; the knob makes it opt-in.

Both DEFAULT OFF: shipping defaults are the polite direction, arming is his call
(the room's tuning panel, no restart needed — the scheduler reads tune per fire).

WHERE THE GATE LIVES, AND WHAT IT COVERS NOW (2026-08-23). a1ecf2a moved the decision
out of the scheduler and into impulse.decide(), and this gate's section 3 was reading
scheduler.py's SOURCE for the old literal — so it went red on a code move while the
behaviour was intact. Section 3 now drives the real decide(), armed and off, per action.

AND ONE THING GENUINELY CHANGED, NOT JUST MOVED: rule 1 above says "her own time" is
deliberately NOT gated, and the moved check sits in the SOLO branch too, so today it is.
The knob ships 0.0 (off), so nothing observable differs by default — but the code and
the operator rule above disagree, and the SOLO row in section 3 is where that is
asserted rather than assumed. If the 2026-08-20 rule stands, the fix is one line in
impulse.py (drop `if not quiet_ok` from the SOLO branch) and one row here.

    python harness_tests/g_kairos_quiet.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


print("1. THE KNOBS EXIST AND SHIP OFF")
from harness.tuning import registry as tune  # noqa: E402

knobs = {k.key: k for k in tune.KNOBS} if hasattr(tune, "KNOBS") else {}
if not knobs:
    # fall back to reading declared defaults through the public getter on a
    # scratch store (SP-side default when nothing has been set)
    pass
check("kairos.quiet_after_him_s is a declared knob",
      any(k == "kairos.quiet_after_him_s" for k in getattr(tune, "_DEFAULTS", {}))
      or "kairos.quiet_after_him_s" in {getattr(k, "key", "") for k in getattr(tune, "KNOBS", [])}
      or tune.get("kairos.quiet_after_him_s") is not None)
check("kairos.seed_on_boot is a declared knob",
      tune.get("kairos.seed_on_boot") is not None)
reg_src = open(os.path.join(ROOT, "harness", "tuning", "registry.py"),
               encoding="utf-8").read()
check("quiet_after_him_s ships 0.0 (off)",
      '"kairos.quiet_after_him_s"' in reg_src.replace("'", '"')
      and '0.0' in reg_src.split("quiet_after_him_s", 1)[1][:400])
check("seed_on_boot ships False (off)",
      "False" in reg_src.split("seed_on_boot", 1)[1][:400])

print("\n2. SEED IS A CHOICE — off means a fresh boot waits for him")
from harness.kairos import scheduler as S  # noqa: E402

_real_get = tune.get
tune.get = lambda k: (False if k == "kairos.seed_on_boot" else _real_get(k))
try:
    seeded = S.seed("g-quiet-test-session", "yesterday she said goodnight", lambda n: "")
    check("seed() refuses when the knob is off", seeded is False)
    check("...and leaves no session behind", "g-quiet-test-session" not in S._LAST)
    tune.get = lambda k: (True if k == "kairos.seed_on_boot" else _real_get(k))
    seeded2 = S.seed("g-quiet-test-session", "yesterday she said goodnight", lambda n: "")
    check("seed() seeds when armed", seeded2 is True and "g-quiet-test-session" in S._LAST)
finally:
    tune.get = _real_get
    S._LAST.pop("g-quiet-test-session", None)
    S._SEEDED.discard("g-quiet-test-session")
    S._STATE.pop("g-quiet-test-session", None)

print("\n3. THE GATE SITS IN THE FIRE PATH, BEFORE ANY MODEL — and never gates a promise")
sched_src = open(os.path.join(ROOT, "harness", "kairos", "scheduler.py"),
                 encoding="utf-8").read()
i_quiet = sched_src.find("quiet_after_him_s")
i_judge = sched_src.find("pregate")
i_gen = sched_src.find("text = (generate(nudge, called)")
# The knob still reaches the scheduler (live_config reads it per fire, no restart), and
# decide() — which now holds the gate — is still consulted before anything is paid for.
check("the knob reaches the scheduler", i_quiet > 0)
check("...ahead of the sidecar pre-judge (free before cheap before expensive)",
      0 < i_quiet < i_judge)
check("...and ahead of generate()", 0 < i_quiet < i_gen)
i_decide = sched_src.find("decide(")
check("the policy is consulted before any model call", 0 < i_decide < i_gen)
# ── WHAT IS GATED, ASKED OF THE POLICY RATHER THAN OF A FILE (2026-08-23) ───────────
# These three checks used to read scheduler.py's source and look for the literal
# "CHECK_IN, CONTINUE, EXPAND, MUSE" in an 1700-character window around the knob name.
# a1ecf2a moved the decision INTO impulse.decide() (the commit title says so: "quiet-
# after-him decided in the policy"), the literal went with it, and all three went red
# while the behaviour they describe was intact — a gate reporting the location of a
# thing rather than the truth of it. Same class as the source-window probe that made
# G-KAIROS-TABLE red for eighteen days.
#
# So: drive the real decide() into each branch and ask what it does. A code move cannot
# break this, and a POLICY change — the thing the gate is actually for — still does.
#
# THE PAIRED RUN IS THE POINT. Asserting silence proves nothing on its own: every one of
# these worlds could be silent for some unrelated bound. Each row is run TWICE, with the
# knob armed and with it off (0.0, the shipping default), and the assertion is that the
# knob is what changed the answer.
from harness.kairos.impulse import (  # noqa: E402
    CHECK_IN, CONTINUE, EXPAND, MUSE, REMIND, SILENT, SOLO,
    KairosConfig, TurnState, decide,
)


class _Roll:
    """The rolls are coins this gate is not about; make them all land yes."""
    def random(self):
        return 0.0

    def uniform(self, a, b):
        return a


NOW = 100_000.0


def _world(**kw):
    """He spoke 300 s ago: past the 240 s check-in bar, inside a 600 s quiet-after-him.
    Every clock the policy reads is set — a defaulted one is impulse.BOOT_AT, which is
    the trap the other four gates in this repair fell into."""
    st = TurnState(last_spoke_at=NOW - 10_000.0, last_user_at=NOW - 300.0,
                   last_conv_at=NOW - 300.0, last_solo_at=NOW - 10_000.0)
    for k, v in kw.items():
        setattr(st, k, v)
    return st


def _cfg(quiet_s):
    return KairosConfig(enabled=True, cooldown_s=45.0, checkin_idle_s=240.0,
                        checkin_chance=1.0, solo_every_s=900.0, solo_chance=1.0,
                        quiet_after_him_s=quiet_s)


# (name, the action it produces with the knob OFF, kwargs for decide/state)
ROWS = [
    ("a check-in", CHECK_IN, {}, {"eot_margin": None, "reply_text": "done."}),
    ("her continuation", CONTINUE, {}, {"eot_margin": -20.0, "reply_text": "and then"}),
    ("an expansion", EXPAND, {}, {"eot_margin": -13.0, "reply_text": "done."}),
    ("a musing", MUSE, {}, {"eot_margin": None, "reply_text": "done.",
                            "insight": {"bits": 9.0, "text": "a conclusion"}}),
    # HER OWN TIME. The 2026-08-20 rule in this gate's own docstring says solo is NOT
    # gated; a1ecf2a's move placed the check in this branch too. The knob ships 0.0, so
    # the divergence is inert by default — but it IS a divergence, and this row is where
    # it is visible rather than assumed. Flagged for the operator 2026-08-23.
    ("her own time", SOLO, {"unanswered": 2}, {"eot_margin": None, "reply_text": "done."}),
]

for label, free_action, st_kw, kw in ROWS:
    off = decide(cfg=_cfg(0.0), state=_world(**st_kw), now=NOW, rng=_Roll(), **kw)
    on = decide(cfg=_cfg(600.0), state=_world(**st_kw), now=NOW, rng=_Roll(), **kw)
    check("%s happens when quiet-after-him is OFF" % label,
          off.action == free_action, "got %s — %s" % (off.action, off.reason))
    check("...and the knob is what withholds it",
          on.action == SILENT and "withheld" in on.reason,
          "got %s — %s" % (on.action, on.reason))

# ── AND IT NEVER GATES A PROMISE ────────────────────────────────────────────────────
# The one rule with no exception: he asked to be reminded. A reminder withheld because
# he has been talking is a reminder that arrives after the appointment.
due = decide(cfg=_cfg(600.0), state=_world(), now=NOW, rng=_Roll(),
             eot_margin=None, reply_text="done.",
             due_notes=[{"title": "call the clinic"}])
check("REMIND is never gated — a promise outranks his quiet",
      due.action == REMIND, "got %s — %s" % (due.action, due.reason))
check("it measures HIM across ALL sessions (global max of last_user_at)",
      "max((st.last_user_at" in sched_src)

print("\n4. AN ATTEMPT CONSUMES THE CLOCK — dropped turns are not free retries")
# Live 2026-08-20 12:50-12:56: solo generated ~2.5 min of 26B, was dropped ("she
# did not feel like anything"), and the tick re-proposed solo FIVE SECONDS later —
# last_solo_at moved only in note_spoke, which a dropped turn never reaches. The
# pacing clocks must advance where the cost is paid: at generate().
# AMENDED 2026-08-24 (audit K1): the spend is _spend_attempt now, called from
# _fire_inner's finally so EVERY drop door pays — the inline stamp block this used
# to anchor on covered one exit of six. The claim is unchanged and is what is
# asserted: the arithmetic exists, in one function, and touches no speech fact.
# The behavioural proof (every door, real _arm, state read back) is G-KAIROS-ATTEMPT.
i_stamp = sched_src.find("def _spend_attempt(")
check("the attempt-spend exists, as ONE function", i_stamp > 0)
check("...and it is paid from _fire_inner's finally (every exit, not one)",
      "finally:" in sched_src[sched_src.find("def _fire_inner"):
                              sched_src.find("def _attempt")]
      and "_spend_attempt(_STATE[session]" in sched_src)
# 1200 was enough until the block grew a comment (2026-08-24, MODE_TURN joined the
# two actions this fix originally named) and the code slid out of the window — a
# grep over a fixed slice measures the PROSE as much as the code. Widened, and the
# behavioural proof now lives in G-KAIROS-ATTEMPT, which drives the real _arm and
# reads the state instead of reading the file.
stamp_block = sched_src[i_stamp:i_stamp + 2400]
check("it advances last_spoke_at (the check-in/cooldown clock)",
      "st.last_spoke_at = _now" in stamp_block)
check("...and last_solo_at for her own time", "last_solo_at" in stamp_block)
check("...and touches NO speech facts (chain/unanswered/spoken_times stay note_spoke's)",
      all(w not in stamp_block for w in (".chain =", "unanswered +=", "unanswered =",
                                         "spoken_times.append", "solo_n +=")))

print("\nG-KAIROS-QUIET  %d/%d" % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
