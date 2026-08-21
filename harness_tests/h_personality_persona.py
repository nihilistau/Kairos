"""G-PF-PERSONA (PF-B2) — structured, live-editable persona.md: load_agent_system splits the VOICE
prose from the machine-parseable ## Personality state block, injects the current state (voice/mood/
traits) + the PF-B1 self-model, edits reflect live, and a malformed block falls back gracefully.

AND WHICH PROSE WINS. Since 2026-07-30 there are TWO sources of persona prose — persona.md and
the persona/ fragment directory — and agent.py:167 gives the fragments precedence: they replace
the prose, and ONLY the prose, because write_state() still rewrites the `## Personality state`
block in persona.md. That precedence is the live path. It is proved here, executed, because a
rule about which of two paths runs is precisely the rule AGENTS.md §0 says gets enforced in
neither.

THE ISOLATION IS PART OF THE CLAIM. This gate used to set SP_PERSONA_FILE and stop, leaving
SP_PERSONA_DIR unset — so compose() read the operator's real, gitignored persona/ directory and
its fragments replaced the temp file's prose. The gate therefore FAILED on a machine with
fragments and PASSED on a fresh clone without them: a verdict that depended on untracked local
files, which is worse than either answer. Both env vars are pinned below."""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = ""
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness.personality import persona_file as PF
from harness.personality.self_model import SelfModelStore

GATE = Path(tempfile.gettempdir()) / "_pf_persona_gate"
PERSONA = GATE / "persona.md"
SELF = GATE / "self"
LAYERS = GATE / "persona"          # pinned so the live persona/ dir can never leak in

PROSE = ("# Kairos\n\nYou are Kairos, a particular someone made of math.\n\n"
         "## How you talk\nLike someone, not a manual.\n")
STATE_BLOCK = "## Personality state\nvoice: dry, warm\nmood: neutral\ntraits: curious, candid\n"

# Two fragments for the layered path. Deliberately share NO wording with PROSE, so
# "the fragments replaced the prose" and "the prose survived" are distinguishable
# rather than two readings of one substring.
FRAG_A = "# Kairos\n\nYou are Kairos, assembled here from separate pieces.\n"
FRAG_B = "## How you talk\nIn fragments that were composed, not in one block.\n"


def load():
    # import inside so env vars are picked up per call
    from harness.agent import load_agent_system
    return load_agent_system()


def main() -> int:
    if GATE.exists():
        shutil.rmtree(GATE)
    GATE.mkdir(parents=True)
    LAYERS.mkdir(parents=True)                 # empty: no fragments, so persona.md prose stands
    PERSONA.write_text(PROSE + "\n" + STATE_BLOCK, encoding="utf-8")
    os.environ["SP_PERSONA_FILE"] = str(PERSONA)
    os.environ["SP_PERSONA_DIR"] = str(LAYERS)  # the isolation this gate lacked
    os.environ["SP_SELF_MODEL_ROOT"] = str(SELF)
    # SEEDED INTO THE REGISTRY, because that is what render_self_model reads since
    # 2026-08-01. Writing to the OKF tier here would assert the composition of a block
    # that production never builds — the dead-path mistake this gate itself was fixed for.
    _reg = str(GATE / "registry.jsonl")
    os.environ["SP_RECALL_REGISTRY"] = _reg
    io.open(_reg, "w", encoding="utf-8").write(json.dumps(
        {"text": "I can read and write memories.", "speaker": "self",
         "lifecycle": 0, "ts": 1}) + "\n")

    s = load()
    prose_ok = "particular someone made of math" in s
    state_ok = ("Current personality state" in s and "voice: dry, warm" in s
                and "mood: neutral" in s and "traits: curious, candid" in s)
    header_stripped = "## Personality state" not in s   # the raw block header must not leak in
    selfmodel_ok = "About yourself (self-model)" in s and "read and write memories" in s
    print(f"prose_ok={prose_ok} state_ok={state_ok} header_stripped={header_stripped} self_model_ok={selfmodel_ok}")

    # live edit: the model/system changes mood via write_state -> next load reflects it
    PF.write_state(str(PERSONA), {"voice": "dry, warm", "mood": "playful", "traits": "curious, candid"})
    s2 = load()
    edit_ok = "mood: playful" in s2 and "particular someone made of math" in s2  # prose preserved
    print(f"live edit -> mood:playful reflected={('mood: playful' in s2)} prose preserved={('math' in s2)}")

    # malformed block -> graceful fallback (prose still loads, no crash)
    PERSONA.write_text(PROSE + "\n## Personality state\n@@@ not key value @@@\n", encoding="utf-8")
    s3 = load()
    graceful = "particular someone made of math" in s3
    print(f"malformed block -> graceful (prose loads)={graceful}")

    # ── PRECEDENCE: the path that actually runs ──────────────────────────────────
    # Drop fragments into the layer dir. agent.py:167 says composition REPLACES the
    # prose and ONLY the prose. Both halves are asserted: the composed text is in,
    # the monolithic prose is OUT, and the state block — which write_state() still
    # owns in persona.md — is untouched by the swap.
    PERSONA.write_text(PROSE + "\n" + STATE_BLOCK, encoding="utf-8")
    (LAYERS / "00-a.md").write_text(FRAG_A, encoding="utf-8")
    (LAYERS / "10-b.md").write_text(FRAG_B, encoding="utf-8")
    s4 = load()
    frag_in = "assembled here from separate pieces" in s4 and "composed, not in one block" in s4
    prose_replaced = "particular someone made of math" not in s4
    state_survives = "voice: dry, warm" in s4 and "traits: curious, candid" in s4
    header_still_stripped = "## Personality state" not in s4
    layers_ok = frag_in and prose_replaced and state_survives and header_still_stripped
    print(f"fragments present -> composed in={frag_in} monolithic prose replaced={prose_replaced} "
          f"state block survives={state_survives} header stripped={header_still_stripped}")

    # A fragment that raises must not take the persona lever down with it: the
    # try/except around compose() is load-bearing, so prove it rather than grep it.
    for f in LAYERS.glob("*.md"):
        f.unlink()
    (LAYERS / "00-broken.md").write_bytes(b"---\norder: 0\n---\n\xff\xfe not utf-8 \xff")
    s5 = load()
    survives_broken = "particular someone made of math" in s5 or "voice: dry, warm" in s5
    print(f"unreadable fragment -> persona lever survives={survives_broken}")

    ok = (prose_ok and state_ok and header_stripped and selfmodel_ok and edit_ok and graceful
          and layers_ok and survives_broken)
    print(f"RESULT pf-persona: {'PASS' if ok else 'FAIL'} "
          f"(state parsed+injected + self-model + live-edit + graceful fallback "
          f"+ fragments-replace-prose-only + broken fragment survivable)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
