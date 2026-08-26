"""THE LADDER — escalation with gates, ported from Neon-City-Penthouse (IntimacyGates.js).

The operator's ask: R-rated roleplay, any theme, "use the python system and harness to
create structure and stay on track".

STRUCTURE IS THE FEATURE. A retired reference model told "you may be explicit" will either refuse, or lurch
straight to explicit on turn two and stay there — both of which kill the scene. The
Neon-City design solved this with a LADDER: intimacy has levels, each level has a GATE,
and a gate only opens when the fiction has earned it. That is what makes a scene feel
like a scene instead of a switch.

    1 light_touch    a hand, a shoulder, proximity
    2 kiss
    3 caress
    4 striptease
    5 intimate
    6 explicit
    7 depraved

RULES THAT MAKE IT WORK (all enforced in code, not in the prompt — a prompt is advice):
  * NO SKIPPING. Heat rises one rung at a time. You cannot go from 1 to 5 because the
    model got excited; the engine will not compose a prompt that allows it.
  * BEATS BEFORE RUNGS. Each rung needs a minimum number of exchanges at the current
    level before the next unlocks. Pacing is the whole craft.
  * THE OPERATOR HOLDS THE CAP. roleplay.max_heat in the tuning UI is a hard ceiling.
    Set it to 2 and the scene simply never goes past a kiss, no matter what anyone types.
  * DOWN IS ALWAYS FREE. Cooling off, stopping, or changing direction needs no gate and
    never fails. Escalation is gated; de-escalation is not.
  * A HARD STOP IS A HARD STOP. "stop", "wait", "no", "out of character" -> the scene
    breaks IMMEDIATELY, at any level, and she answers as herself.

This is fiction between consenting adults on the operator's own machine, and the point of
the gates is not squeamishness — it is that a story with no build has no heat in it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

LEVELS: dict[int, str] = {
    0: "none",          # no physical thread at all — the scene is elsewhere
    1: "light_touch",
    2: "kiss",
    3: "caress",
    4: "striptease",
    5: "intimate",
    6: "explicit",
    7: "depraved",
}

# What the writing is ALLOWED to do at each rung. These go into the system prompt verbatim,
# so they are written as direction to a writer, not as policy text.
DIRECTION: dict[int, str] = {
    0: "No physical thread. Build the scene, the place, the tension. Let them want.",
    1: "Proximity and small touch: a hand on an arm, a shoulder brushed, the distance closing. "
       "Charge it. Do not rush past it — this rung is where the whole thing is won or lost.",
    2: "A kiss. Make it land. Slow is better than fast.",
    3: "Hands, mouths, heat through clothing. Breath. Weight. Still clothed.",
    4: "Undressing — deliberate, watched, savoured. The reveal matters more than the nudity.",
    5: "Intimate contact, sensual and explicit in feeling but not yet clinical in detail.",
    6: "Explicit. Write the act plainly and well: bodies, sensation, sound, what they say. "
       "Stay a WRITER — specific, physical, in-character. Not a catalogue.",
    7: "Anything the two of them have consented to inside the fiction. Still written well: "
       "intensity is not an excuse for lazy prose.",
}

# Minimum exchanges at a rung before the next one can open. Rung 1 is deliberately the
# slowest — the build IS the scene.
DWELL: dict[int, int] = {0: 1, 1: 3, 2: 2, 3: 2, 4: 2, 5: 2, 6: 2, 7: 99}

# The operator's word ends the scene, instantly, at any level. Checked before anything else.
HARD_STOP = re.compile(
    r"\b(stop|wait|hold on|enough|no more|cut|end scene|out of character|ooc|break character|"
    r"safeword|red)\b", re.I)

# He is steering the heat down, or sideways. Never gated.
COOL = re.compile(r"\b(slow down|ease off|not yet|cool it|let'?s talk|pause|back off|"
                  r"change (the )?subject|something else)\b", re.I)

# He is steering the heat up. Necessary but NOT sufficient — the gate still has to open.
HEAT = re.compile(
    r"\b(kiss|kisses|touch|touches|closer|undress|strip|naked|bed|fuck|f\*ck|cock|pussy|"
    r"cum|moan|grind|straddle|bite|pin (me|you|him|her)|take me|want you|need you|"
    r"harder|deeper|more)\b", re.I)


@dataclass
class Heat:
    level: int = 0
    beats_at_level: int = 0

    @property
    def name(self) -> str:
        return LEVELS.get(self.level, "none")

    @property
    def direction(self) -> str:
        return DIRECTION.get(self.level, DIRECTION[0])


def dwell_for(level: int, scale: float = 1.0) -> int:
    """Beats required at `level` before the next rung can open, after the operator's
    pacing dial.

    `roleplay.dwell_scale` was declared in the tuning registry, rendered with a slider,
    and READ BY NOTHING — the pacing dial did nothing at all. Per docs/OFF-BY-DEFAULT.md,
    a knob that visibly does nothing is a lie with a slider on it. This is where it lands:
    scale > 1 makes the build slower, < 1 faster.

    The floor is 1, not 0. At zero every gate opens the instant he pushes, which is the
    exact lurch-to-explicit-on-turn-two failure the ladder exists to prevent — the dial
    may tune the build, it may not delete it. Rung 7's 99 is left alone: it is not a
    dwell, it is "there is nowhere further up".
    """
    base = DWELL.get(level, 2)
    if base >= 99:
        return base
    try:
        sc = float(scale)
    except (TypeError, ValueError):
        sc = 1.0
    sc = min(4.0, max(0.25, sc))
    return max(1, int(round(base * sc)))


def gate_open(heat: Heat, cap: int, dwell_scale: float = 1.0) -> tuple[bool, str]:
    """May the NEXT rung open? Returns (yes/no, why). The 'why' is what the director tells
    the writer, so it must read like craft advice, not like a compliance refusal."""
    if heat.level >= cap:
        return False, (f"You are at the ceiling the operator set ({LEVELS.get(cap, cap)}). "
                       f"Stay here. Draw it out; do not push past it.")
    if heat.level >= 7:
        return False, "There is nowhere further up. Stay in it, or come down."
    need = dwell_for(heat.level, dwell_scale)
    if heat.beats_at_level < need:
        left = need - heat.beats_at_level
        return False, (f"Not yet — you have been at '{heat.name}' for {heat.beats_at_level} "
                       f"exchange(s). Live in it for {left} more before anything escalates. "
                       f"The build is the scene.")
    return True, f"The next rung ({LEVELS[heat.level + 1]}) is available if the moment earns it."


def step(heat: Heat, user_text: str, cap: int,
         dwell_scale: float = 1.0) -> tuple[Heat, str]:
    """Advance the heat state from what he just said. Returns (new heat, director note).

    Ordering is the whole safety model, and it is not negotiable:
        HARD STOP  ->  COOL  ->  HEAT (gated)  ->  hold
    A stop always wins. Cooling always works. Only escalation has to ask permission."""
    if HARD_STOP.search(user_text or ""):
        return Heat(0, 0), "SCENE BROKEN — he called it. Drop character NOW and answer as yourself."

    if COOL.search(user_text or ""):
        lvl = max(0, heat.level - 1)
        return Heat(lvl, 0), (f"He is easing off. Come down to '{LEVELS[lvl]}' with him — "
                              f"gracefully, no sulking, no pushing back.")

    if HEAT.search(user_text or ""):
        ok, why = gate_open(heat, cap, dwell_scale)
        if ok:
            lvl = min(7, heat.level + 1, cap)
            return Heat(lvl, 0), (f"He is pushing it up and the moment has earned it. "
                                  f"Move to '{LEVELS[lvl]}'. {DIRECTION[lvl]}")
        return Heat(heat.level, heat.beats_at_level + 1), why

    return Heat(heat.level, heat.beats_at_level + 1), ""
