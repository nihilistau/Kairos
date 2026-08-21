"""G-PF-DECORATORS (PF-B4) — @personality tools the model can CALL to durably self-modify. They
register into SKILL_REGISTRY (pack 'personality') with OpenAI schemas (so run_with_tools advertises
them), and calling them updates the persona state + self-model durably."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GATE = Path(tempfile.gettempdir()) / "_pf_dec_gate"
PERSONA = GATE / "persona.md"
SELF = GATE / "self"
BASE = ("# Kairos\n\nYou are Kairos.\n\n"
        "## Personality state\nvoice: dry\nmood: neutral\ntraits: curious, formal\n")


def main() -> int:
    if GATE.exists():
        shutil.rmtree(GATE)
    GATE.mkdir(parents=True)
    PERSONA.write_text(BASE, encoding="utf-8")
    os.environ["SP_PERSONA_FILE"] = str(PERSONA)
    os.environ["SP_SELF_MODEL_ROOT"] = str(SELF)
    # ISOLATE THE REGISTRY TOO. remember_self now writes there, and with this unset the
    # write silently goes nowhere (_reg_path() returns "" and the store is a no-op) — so
    # the gate would fail for a reason that has nothing to do with the code under test.
    os.environ["SP_RECALL_REGISTRY"] = str(SELF.parent / "registry.jsonl")

    from harness.personality import tools as T
    from harness.personality.persona_file import parse_persona
    from harness.personality.self_model import SelfModelStore
    from harness.personality import self_model as SM_MOD
    from harness.skills.registry import SKILL_REGISTRY, _schema_for

    # 1) registered as a 'personality' pack with real schemas (run_with_tools would advertise them)
    metas = SKILL_REGISTRY.get_pack_metas("personality")
    names = sorted(m.name for m in metas)
    reg_ok = set(["adjust_mood", "set_voice", "set_trait", "remember_self"]).issubset(names)
    schemas_ok = all(_schema_for(m)["function"]["name"] == m.name for m in metas)
    # set_trait's schema must expose its params (trait, action)
    st_meta = SKILL_REGISTRY.get_skill("set_trait")
    st_params = set(_schema_for(st_meta)["function"]["parameters"]["properties"].keys())
    params_ok = {"trait", "action"}.issubset(st_params)
    print(f"registered personality tools: {names}")
    print(f"reg_ok={reg_ok} schemas_ok={schemas_ok} set_trait params={sorted(st_params)} params_ok={params_ok}")

    # 2) calling them durably self-modifies (as the model would via run_with_tools)
    print("call:", T.adjust_mood("focused"))
    print("call:", T.set_voice("terse"))
    print("call:", T.set_trait("bold", "add"))
    print("call:", T.set_trait("formal", "remove"))
    print("call:", T.remember_self("I can classify my own memories."))

    _, state = parse_persona(PERSONA.read_text(encoding="utf-8"))
    traits = [t.strip().lower() for t in state.get("traits", "").split(",")]
    mutate_ok = (state.get("mood") == "focused" and state.get("voice") == "terse"
                 and "bold" in traits and "formal" not in traits and "curious" in traits)
    # HER TOOL MUST LAND WHERE THE PREFIX READS. `remember_self` now delegates to the
    # registry writer, so this asserts the whole round trip rather than the OKF tier the
    # renderer stopped reading on 2026-08-01 — the tier is vestigial and testing it would
    # prove nothing about what she carries.
    self_ok = "classify my own memories" in SM_MOD.render_self_model()
    print(f"persona state now: {state}")
    print(f"mutate_ok={mutate_ok} self_model_ok={self_ok}")

    ok = reg_ok and schemas_ok and params_ok and mutate_ok and self_ok
    print(f"RESULT pf-decorators: {'PASS' if ok else 'FAIL'} "
          f"(personality pack registered w/ schemas + model-callable + durable self-modify + self-fact)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
