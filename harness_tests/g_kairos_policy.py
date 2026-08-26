"""G-KAIROS-POLICY — she must not talk forever, and she must not talk every turn.

The operator's requirement, verbatim: "it has to make sense tho, you cant just let it
talk forever. or talk everyturn etc."

So the policy is gated BEFORE it is ever wired to a GPU. Silence is the default; speech
is earned. These are the bounds, and they are asserted, not asserted-about:

  1. an ORDINARY finished turn -> SILENT          (calibrated: margin +2 >> -13.75)
  2. a turn cut off mid-thought -> CONTINUE       (margin -15 < -13.75)
  3. she asked HIM a question   -> SILENT         (she waits; she does not answer herself)
  4. she cannot chain           -> one unprompted turn, then she MUST wait for him
  5. cooldown holds
  6. hourly cap holds
  7. his turn RESETS her budget (that is what makes it a conversation)
  8. a continuation that says nothing new is DROPPED, not shown

Pure: no daemon, no model, no clock. Injected `now` and a seeded rng.
"""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness.kairos.impulse import (  # noqa: E402
    CHECK_IN, CONTINUE, SILENT, KairosConfig, TurnState,
    decide, note_spoke, note_user, worth_saying,
)

# SYNTHETIC CLOCKS (2026-08-23): a fresh TurnState's clocks default to impulse.BOOT_AT,
# the real monotonic boot time (a1ecf2a — "a zero clock fails OPEN"), which sits in the
# FUTURE of the small fixtures below (100.0, 5000.0 ...) and silenced every decision with
# a nonsense cooldown. Pin the boot to t=1.0 for this process: non-zero, so the
# no-zero-clock rule is still exercised, and before every `now` this gate uses. Same pin
# as g_kairos_latch / g_kairos_presence / g_kairos_reasons, which a1ecf2a updated; this
# gate was one of the five it missed.
import harness.kairos.impulse as _imp_pin  # noqa: E402
_imp_pin.BOOT_AT = 1.0

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def main() -> int:
    print("G-KAIROS-POLICY - silence is the default; speech is earned.\n")
    # THE MARGINS BELOW ARE THIS MODEL'S. They were the retired reference model's (+2.01 finished, -14.8
    # cut off) and this gate passed 12/12 with them — because KairosConfig's dataclass
    # default was ALSO still -11.75, so the fixtures and the code under test were stale
    # together and agreed. Correcting the default alone took it to 8/12. Two wrong things
    # confirming each other is the exact failure a gate exists to prevent, so the numbers
    # are named here rather than sprinkled as literals.
    FINISHED, CUT = 13.10, -28.43        # 26B medians; threshold -18.50
    cfg = KairosConfig(enabled=True)
    rng = random.Random(7)

    # 1. ordinary finished turn -> SILENT (the calibrated margin of a completed thought)
    st = TurnState(last_user_at=100.0)
    d = decide(cfg=cfg, state=st, now=101.0, reply_text="The sky is blue on a clear day.",
               eot_margin=FINISHED, rng=rng)
    check("an ORDINARY finished turn -> SILENT", d.action == SILENT, d.reason)

    # 2. guillotined mid-thought -> CONTINUE
    st = TurnState(last_user_at=100.0)
    d = decide(cfg=cfg, state=st, now=101.0,
               eot_margin=CUT, reply_text="The ocean is a vast expanse of water, and th", rng=rng)
    check("a turn CUT OFF mid-thought -> CONTINUE", d.action == CONTINUE, d.reason)
    check("...with a realistic delay (she thinks, she does not lag)",
          0.5 <= d.delay_s <= 8.0, f"{d.delay_s:.1f}s")

    # 3. she asked HIM a question -> she waits. non-negotiable.
    st = TurnState(last_user_at=100.0)
    d = decide(cfg=cfg, state=st, now=101.0, eot_margin=CUT,
               reply_text="That's wild — what did you do next?", rng=rng)
    check("she asked HIM a question -> SILENT (she does not answer herself)",
          d.action == SILENT, d.reason)

    # 4. no chaining: one unprompted turn, then she must wait for him
    st = TurnState(last_user_at=100.0)
    d1 = decide(cfg=cfg, state=st, now=101.0, eot_margin=CUT, reply_text="mid thought", rng=rng)
    note_spoke(st, 101.0)
    d2 = decide(cfg=cfg, state=st, now=102.0, eot_margin=CUT, reply_text="still going", rng=rng)
    check("she CANNOT chain (one unprompted turn, then she waits)",
          d1.action == CONTINUE and d2.action == SILENT, d2.reason)

    # 5. cooldown
    st = TurnState(last_user_at=100.0)
    note_spoke(st, 100.0)
    st.chain = 0                       # pretend the chain reset but the cooldown has not
    d = decide(cfg=cfg, state=st, now=110.0, eot_margin=CUT, reply_text="mid thought", rng=rng)
    check("COOLDOWN holds", d.action == SILENT, d.reason)

    # 6. hourly cap
    st = TurnState(last_user_at=0.0)
    for i in range(cfg.max_per_hour):
        st.spoken_times.append(1000.0 + i)
    st.chain = 0
    st.last_spoke_at = 0.0
    d = decide(cfg=cfg, state=st, now=2000.0, eot_margin=CUT, reply_text="mid thought", rng=rng)
    check("HOURLY CAP holds", d.action == SILENT, d.reason)

    # 7. his turn resets her budget — this is what makes it a conversation
    st = TurnState(last_user_at=100.0)
    note_spoke(st, 101.0)
    note_user(st, 200.0)               # HE speaks
    d = decide(cfg=cfg, state=st, now=201.0, eot_margin=CUT, reply_text="mid thought", rng=rng)
    check("HIS turn resets her budget (a conversation, not a monologue)",
          d.action == CONTINUE, d.reason)

    # 8. an unprompted message that adds nothing is DROPPED, never shown
    ok1, why1 = worth_saying("Hey! Just checking in.", "I was saying the ocean is vast.")
    ok2, why2 = worth_saying("The ocean is vast, and the water is deep.",
                             "The ocean is vast and the water is deep and wide.")
    ok3, _ = worth_saying("— and the smell of it stays in your clothes for days.",
                          "The ocean is a vast expanse of water, and th")
    check("a GREETING-style continuation is DROPPED", not ok1, why1)
    check("a RESTATEMENT is DROPPED", not ok2, why2)
    check("a genuine new thought is KEPT", ok3)

    # 9. the whole point: over a normal conversation she is silent almost always
    st = TurnState(last_user_at=0.0)
    # Ten ordinary FINISHED turns, on the model scale (median +13.10, min +8.96).
    ordinary = [13.1, 14.2, 11.0, 16.4, 12.7, 9.1, 10.8, 15.3, 9.6, 13.9]
    spoke = 0
    for i, m in enumerate(ordinary):
        note_user(st, i * 100.0)
        d = decide(cfg=cfg, state=st, now=i * 100.0 + 1, eot_margin=m,
                   reply_text="a complete thought.", rng=rng)
        if d.speaks:
            spoke += 1
            note_spoke(st, i * 100.0 + 1)
    check("over 10 ORDINARY turns she speaks unprompted 0 times",
          spoke == 0, f"{spoke}/10 — she does not talk every turn")

    print(f"\nG-KAIROS-POLICY: {'PASS' if not FAIL else 'FAIL'} ({len(PASS)}/{len(PASS)+len(FAIL)})")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
