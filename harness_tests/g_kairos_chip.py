"""G-KAIROS-CHIP — the presence chip and the policy read the SAME clock. OFFLINE.

THE DIVERGENCE (K4, SWEEP-2026-08-24). The room's presence chip answered "when is her
next mode turn?" with its own arithmetic in `scheduler._presence_state`:

    last = max(last_user_at, last_spoke_at, last_solo_at, last_mode_at)
    next_in_s = every - (now - last)

while the policy (`impulse.decide`) fires a MODE_TURN off a DIFFERENT computation:
`presence_idle` = max(last_user_at, last_conv_at, last_solo_at) — deliberately
EXCLUDING mode turns from the room's quiet — ANDed with the mode's own cadence
(now - last_mode_at), all of it downstream of a cooldown gate the chip never read at
all. Two spellings of one rule, §0's exact shape, in the one surface he looks at to
answer "why is she quiet": the chip could read "next ~0m" while decide() would not
fire for minutes — an instrument that promises what the policy will not deliver, which
reads as the machinery being broken (it has been reported as exactly that before,
G-KAIROS-LATCH's whole preamble).

THE FIX IS THE SEAM, NOT THE CALLER: the deterministic gates live in ONE function,
`impulse.mode_wait_s` — conversation quiet, mode cadence, cooldown, and the asked-for
kick's precedence — and BOTH the policy branch and the chip call it. 0.0 means the
clocks are open; the chance draw and the hourly caps still have their say (coins and
counts are not clocks, and a chip that pretended to predict a coin would be lying with
more precision).

The legs craft states on both sides of the line and assert the chip and the REAL
decide() agree — including the cooldown case the old chip was blind to, which is the
mutant: reintroduce the divergent max() and the cooldown leg goes red by name.

    python harness_tests/g_kairos_chip.py
"""
from __future__ import annotations

import os
import random
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

# presence_chance=1.0 and a pinned rng: the coin is removed from the experiment, so any
# chip/policy disagreement left is the CLOCKS — the thing this gate is about.
CFG = I.KairosConfig(enabled=True, presence_mode="lucid", presence_every_s=300.0,
                     cooldown_s=600.0, presence_chance=1.0, quiet_after_him_s=0.0)


def _state(ago: float, spoke_ago: float = None, mode_ago: float = None,
           kick: bool = False) -> I.TurnState:
    st = I.TurnState()
    now = time.monotonic()
    st.last_user_at = st.last_conv_at = st.last_solo_at = now - ago
    st.last_mode_at = now - (mode_ago if mode_ago is not None else ago)
    st.last_spoke_at = now - (spoke_ago if spoke_ago is not None else ago)
    st.mode_kick = kick
    return st


def _both(st):
    """The chip's number and the policy's ruling, same state, same instant — the REAL
    `_presence_state` and the REAL `decide`, never a re-implementation of either."""
    now = time.monotonic()
    chip = S._presence_state(CFG, st, now)["next_in_s"]
    imp = I.decide(cfg=CFG, state=st, now=now, reply_text="", eot_margin=None,
                   rng=random.Random(7), due_notes=None, insight=None)
    return chip, imp


print("\n1. THE COOLDOWN CASE — the one the old chip was blind to")
# Everything 400 s quiet (past the 300 s cadence) but she spoke 400 s ago and the
# cooldown is 600: the policy will NOT fire for another ~200 s. The old chip's max()
# never read the cooldown, said "next ~0m", and the operator watched a promise the
# policy had no intention of keeping. (Since the attempt-spend fix, EVERY vetoed
# attempt advances last_spoke_at — so this is no longer a corner; it is the state the
# room is in right after any dropped turn.)
st = _state(400.0)
chip, imp = _both(st)
check("the policy does not fire (cooldown holds)",
      imp.action == I.SILENT and "cooldown" in imp.reason, "%s (%s)" % (imp.action, imp.reason))
check("...and the chip says so too — next_in_s tracks the cooldown, not ~0",
      chip is not None and 150.0 <= chip <= 250.0, chip)

print("\n2. THE OPEN CASE — clocks clear on both readings")
st = _state(700.0)
chip, imp = _both(st)
check("the clocks are open and the chip reads 0", chip == 0.0, chip)
check("...and the policy fires the mode turn", imp.action == I.MODE_TURN,
      "%s (%s)" % (imp.action, imp.reason))

print("\n3. THE FRESH-MODE-TURN CASE — her own cadence, chip and policy together")
# The conversation has been quiet for 700 s but she took a mode turn 100 s ago: the
# cadence gate (and the cooldown) both hold for ~200 s more, and the chip must say so.
st = _state(700.0, spoke_ago=100.0, mode_ago=100.0)
chip, imp = _both(st)
check("the policy does not fire (her own cadence)", imp.action == I.SILENT,
      "%s (%s)" % (imp.action, imp.reason))
check("...and the chip agrees it is not ~0", chip is not None and chip > 0.0, chip)

print("\n4. THE ASKED-FOR CASE — a kick outranks every clock, on both readings")
# enter_mode arms the kick: decide() fires it ahead of cooldown and cadence (his ask is
# owed). The OLD chip could show minutes of wait while she was about to speak — the
# same divergence, other direction.
st = _state(10.0, kick=True)
chip, imp = _both(st)
check("the policy fires now (asked for)", imp.action == I.MODE_TURN,
      "%s (%s)" % (imp.action, imp.reason))
check("...and the chip reads 0, not the cadence", chip == 0.0, chip)

print("\n5. THE SEAM ITSELF — one arithmetic, agreed with everywhere it is read")
# The agreement above is the theorem; this is the ∀ over a sweep of states: wherever
# mode_wait_s says the clocks are open, decide() fires (coin pinned), and wherever it
# says wait, decide() is silent. If a caller grows its own arithmetic again, some cell
# here splits.
ok_all, bad = True, None
for ago in (0.0, 100.0, 250.0, 400.0, 650.0, 900.0):
    for spoke_ago in (5.0, 400.0, 900.0):
        for mode_ago in (5.0, 400.0, 900.0):
            st = _state(ago, spoke_ago=spoke_ago, mode_ago=mode_ago)
            now = time.monotonic()
            wait = I.mode_wait_s(CFG, st, now, 300.0)
            imp = I.decide(cfg=CFG, state=st, now=now, reply_text="",
                           eot_margin=None, rng=random.Random(7))
            fires = imp.action == I.MODE_TURN
            if fires != (wait <= 0.0):
                ok_all, bad = False, (ago, spoke_ago, mode_ago, wait, imp.action, imp.reason)
check("54 crafted states: (wait == 0) <=> the policy fires", ok_all, bad)
check("...and the wait is never negative",
      I.mode_wait_s(CFG, _state(99999.0), time.monotonic(), 300.0) == 0.0, None)

finish("G-KAIROS-CHIP")
