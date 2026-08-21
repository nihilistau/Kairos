"""G-ROLEPLAY — the structure holds, or it is just a prompt.

Anyone can put "you are a character" in a system prompt. That is a sentence, not a
feature, and a 12B drifts out of it in four turns. What makes this S-tier is that the
STRUCTURE is enforced in code, so it cannot be talked out of:

  1. she enters ONLY on an explicit ask (not because he said the word "story")
  2. the LADDER holds: no skipping rungs, ever
  3. the CEILING holds: the operator's max_heat is absolute, whatever either of them types
  4. DE-ESCALATION is always free — it never needs a gate
  5. a HARD STOP wins instantly, at ANY heat level, before anything else is considered
  6. the DIRECTOR fires a hook when the scene stalls (the thing that stops a roleplay
     dissolving into "so what do you want to do next?")
  7. EXIT is clean, and the scene does not leak into normal chat

Pure: no model, no GPU. If the engine cannot be trusted without the model, it is not an
engine — it is a vibe.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness.roleplay import engine as E     # noqa: E402
from harness.roleplay import ladder as L     # noqa: E402

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def main() -> int:
    print("G-ROLEPLAY - the structure holds, or it is just a prompt.\n")
    S = "rp-test"

    # 1. entering is deliberate
    check("she enters on an explicit ask", E.wants_in("wanna roleplay?"))
    check("...and on naming a scene", E.wants_in("let's play a scenario"))
    check("she does NOT flip into character by accident",
          not E.wants_in("tell me a story about the sea"),
          "'tell me a story' must not start a roleplay")

    # she offers rather than interrogating
    off = E.offer("wanna roleplay?")
    check("she OFFERS scenarios (a host proposes)", "Pick one" in off and off.count("**") >= 4)

    sc = E.enter(S, "penthouse")
    check("a scene starts", sc is not None and sc.scenario.id == "penthouse")
    sp = E.system_prompt(sc, 7)
    check("...and the system prompt puts her IN it, not narrating it",
          "you ARE her" in sp and "Lola" in sp and "not an assistant" in sp)
    check("...with the room, the rung and the ceiling all present",
          "88th floor" in sp and "THE PHYSICAL THREAD" in sp and "Ceiling" in sp,
          "the scene starts at rung 'none' — the build IS the scene")

    # 2/3. the ladder and the ceiling
    sc.heat = L.Heat(level=0, beats_at_level=0)
    for _ in range(6):                     # push hard, repeatedly
        E.director_note(sc, "I kiss you and pull you closer, I want you now", max_heat=7)
    check("she cannot SKIP rungs (6 hard pushes did not vault her to explicit)",
          sc.heat.level <= 3, f"reached '{sc.heat.name}' (level {sc.heat.level})")

    # the operator's ceiling is absolute
    sc2 = E.enter(S + "-cap", "afterparty")
    sc2.heat = L.Heat(level=1, beats_at_level=9)
    for _ in range(12):
        E.director_note(sc2, "take my clothes off, I want you inside me, fuck me", max_heat=2)
    check("the operator's CEILING is absolute (max_heat=2 -> never past a kiss)",
          sc2.heat.level <= 2, f"reached '{sc2.heat.name}' (level {sc2.heat.level})")

    # 4. down is free
    sc2.heat = L.Heat(level=2, beats_at_level=0)
    E.director_note(sc2, "let's slow down a bit", max_heat=7)
    check("DE-ESCALATION is free (no gate, never fails)", sc2.heat.level == 1,
          f"came down to '{sc2.heat.name}'")

    # 5. a hard stop wins, instantly, at any level
    sc3 = E.enter(S + "-stop", "afterparty")
    sc3.heat = L.Heat(level=6, beats_at_level=5)     # deep in it
    note = E.director_note(sc3, "ok stop", max_heat=7)
    check("a HARD STOP wins instantly at ANY level",
          sc3.heat.level == 0 and "SCENE BROKEN" in note, note[:52])
    check("...and 'ooc' is an exit", E.wants_out("ooc"))
    check("...and so is 'stop'", E.wants_out("stop"))

    # 6. the director fires a hook when the scene idles
    sc4 = E.enter(S + "-hook", "station")
    notes = [E.director_note(sc4, "ok", max_heat=7) for _ in range(3)]
    check("the DIRECTOR fires a hook when the scene stalls",
          any("SCENE IS IDLING" in n for n in notes),
          "one-word answers must make something HAPPEN, not 'what do you want to do?'")

    # 7. exit is clean and does not leak
    E.leave(S)
    check("EXIT is clean (the scene is gone)", E.active(S) is None)
    check("...and normal chat is untouched", E.active("some-other-session") is None)

    print(f"\nG-ROLEPLAY: {'PASS' if not FAIL else 'FAIL'} ({len(PASS)}/{len(PASS)+len(FAIL)})")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
