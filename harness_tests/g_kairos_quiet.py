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
check("the quiet gate exists in the scheduler", i_quiet > 0)
check("...ahead of the sidecar pre-judge (free before cheap before expensive)",
      0 < i_quiet < i_judge)
check("...and ahead of generate()", 0 < i_quiet < i_gen)
gate_block = sched_src[i_quiet - 800:i_quiet + 900]
check("it gates exactly the discretionary four",
      "CHECK_IN, CONTINUE, EXPAND, MUSE" in gate_block)
check("REMIND is not in the gated set", "REMIND" not in gate_block.split("(CHECK_IN")[1][:40]
      if "(CHECK_IN" in gate_block else False)
check("SOLO is not in the gated set", "SOLO" not in gate_block.split("(CHECK_IN")[1][:40]
      if "(CHECK_IN" in gate_block else False)
check("it measures HIM across ALL sessions (global max of last_user_at)",
      "max((st.last_user_at" in sched_src)

print("\n4. AN ATTEMPT CONSUMES THE CLOCK — dropped turns are not free retries")
# Live 2026-08-20 12:50-12:56: solo generated ~2.5 min of 26B, was dropped ("she
# did not feel like anything"), and the tick re-proposed solo FIVE SECONDS later —
# last_solo_at moved only in note_spoke, which a dropped turn never reaches. The
# pacing clocks must advance where the cost is paid: at generate().
i_stamp = sched_src.find("AN ATTEMPT CONSUMES THE CLOCK")
i_worth = sched_src.find("ok, why = worth_saying(text, reply_text)")
check("the attempt-stamp exists", i_stamp > 0)
check("...after generate() and before worth_saying can drop the turn",
      i_gen < i_stamp < i_worth, (i_gen, i_stamp, i_worth))
stamp_block = sched_src[i_stamp:i_stamp + 1200]
check("it advances last_spoke_at (the check-in/cooldown clock)",
      "last_spoke_at = time.monotonic()" in stamp_block)
check("...and last_solo_at for her own time", "last_solo_at" in stamp_block)
check("...and touches NO speech facts (chain/unanswered/spoken_times stay note_spoke's)",
      all(w not in stamp_block for w in (".chain =", "unanswered +=", "unanswered =",
                                         "spoken_times.append", "solo_n +=")))

print("\nG-KAIROS-QUIET  %d/%d" % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
