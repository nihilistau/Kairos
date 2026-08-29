"""G-PF-CURATE (PF-B5) — NIGHTSHIFT personality curation: extract the shifts the model expressed in
a transcript, prune duplicate/stale traits, and snapshot the personality into a content-addressed
memory-okf-personality tier. Personality becomes system-curatable + recoverable."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness.personality import curator as C
from harness.personality.persona_file import parse_persona

GATE = Path(tempfile.gettempdir()) / "_pf_curate_gate"
PERSONA = GATE / "persona.md"
TIER = GATE / "personality"
# note the DUPLICATE "curious" + a "terse" the model will drop mid-conversation
BASE = ("# Kairos\n\nYou are Kairos.\n\n"
        "## Personality state\nvoice: dry\nmood: neutral\ntraits: curious, formal, curious, terse\n")

# a transcript where the model expressed personality shifts in its turns
MESSAGES = [
    {"role": "user", "content": "That was heavy. Can we slow down?"},
    {"role": "assistant", "content": "Of course. [MOOD:reflective] [VOICE:gentle] "
                                     "[TRAIT:+patient] [TRAIT:-terse] Take your time."},
    {"role": "user", "content": "Thanks."},
    {"role": "assistant", "content": "I'm here."},
]


def main() -> int:
    if GATE.exists():
        shutil.rmtree(GATE)
    GATE.mkdir(parents=True)
    PERSONA.write_text(BASE, encoding="utf-8")

    r = C.consolidate_personality(MESSAGES, persona_path=str(PERSONA), tier_root=str(TIER))
    _, state = parse_persona(PERSONA.read_text(encoding="utf-8"))
    traits = [t.strip().lower() for t in state.get("traits", "").split(",") if t.strip()]

    # ── THE REPLAY IS RETIRED (2026-08-29 audit, M8) — this gate used to assert the
    # OPPOSITE: that the marks in MESSAGES landed here. Every mark is applied LIVE on
    # all three mouths and her unprompted turns now (_settle_turn → run_post_turn),
    # so the nightly replay could only OVERWRITE a later direct state change with the
    # recording's last mark — she called adjust_mood("quiet") at midnight and woke
    # flirty because the transcript said so at 21:00. The state below stands for a
    # midnight direct write: the curator must leave it exactly alone.
    mood_ok = state.get("mood") == "neutral"      # NOT the transcript's "reflective"
    voice_ok = state.get("voice") == "dry"        # NOT the transcript's "gentle"
    trait_add = "patient" not in traits           # no mark is applied from a recording
    trait_rm = "curious" in traits                # ...and nothing real is lost
    # THE DUPLICATE IS GONE — asserted on the OUTCOME, and separately on the pass that
    # does it. `r["pruned"]` used to be the whole test, and it went to 0 on 2026-08-03
    # when the WRITER started sanitising traits (a captured `+` and a markdown escape had
    # both become traits she read back as her character). Nothing broke: the cleaning
    # moved one step earlier and the curator now legitimately finds nothing left to clean.
    # A gate that asserts WHO did the work fails when the work moves to a better place.
    dedup_ok = traits.count("curious") == 1
    # ...and the curator's own pass still works, on the input only IT sees: a persona file
    # edited by hand, with no transcript to have been sanitised on the way in.
    HAND = GATE / "hand_edited.md"
    HAND.write_text(BASE, encoding="utf-8")
    r2 = C.consolidate_personality(None, persona_path=str(HAND), tier_root=str(TIER))
    _, s2 = parse_persona(HAND.read_text(encoding="utf-8"))
    t2 = [t.strip().lower() for t in s2.get("traits", "").split(",") if t.strip()]
    dedup_ok = dedup_ok and t2.count("curious") == 1 and r2["pruned"] >= 1
    # snapshot written as an OKF concept in the personality tier
    snap = TIER / "full" / f"{r['snapshot_addr']}.md"
    snap_ok = snap.exists() and "mem_class: persona" in snap.read_text(encoding="utf-8") \
        and "mem_owner: self" in snap.read_text(encoding="utf-8")

    print(f"result: {r}")
    print(f"state: {state}  traits={traits}")
    print(f"mood={mood_ok} voice={voice_ok} trait_add={trait_add} trait_rm={trait_rm} "
          f"dedup={dedup_ok} snapshot={snap_ok}")
    ok = mood_ok and voice_ok and trait_add and trait_rm and dedup_ok and snap_ok
    print(f"RESULT pf-curate: {'PASS' if ok else 'FAIL'} "
          f"(extract shifts from transcript + prune duplicate traits + OKF snapshot)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
