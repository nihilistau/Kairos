"""G-PK2-UI-ENDPOINTS (offline) — the §U operator-panel gateway surfaces (memory/tasks/persona)
and the persona editor round-trip, called directly (no server, no daemon).

    python tests/g_pk2_ui_endpoints_offline.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REG = os.path.join(tempfile.gettempdir(), "sp_pk2_ui.jsonl")
os.environ["SP_RECALL_REGISTRY"] = REG
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:59999"
os.environ["SP_TASK_ROOT"] = tempfile.mkdtemp(prefix="pk2ui_tasks_")
PERSONA = os.path.join(tempfile.gettempdir(), "sp_pk2_persona.md")
os.environ["SP_PERSONA_FILE"] = PERSONA
open(REG, "w").close()

from harness.skills.memory import remember
from harness.control.task_loop import post_task
from harness.server.app import _memory_json, _tasks_json, _persona_get, _persona_set, _persona_state


def check(name, ok):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    return ok


def main() -> int:
    res = []

    remember("The user's name is Sam.", source="operator")
    remember("The user is building Kairos.", source="user turn")
    mj = _memory_json()
    res.append(check("/v1/memory returns facts + provenance",
                     mj["count"] == 2 and mj["facts"][0]["src"] == "operator" and "health" in mj))

    tid = post_task("make the tests pass")
    tj = _tasks_json()
    res.append(check("/v1/tasks returns the queued task",
                     tj["count"] == 1 and tj["tasks"][0]["status"] == "pending"
                     and tj["tasks"][0]["id"] == tid))

    # persona editor round-trip
    _persona_set("# Persona v2\n\nYou are Kairos.\n\n## Personality state\nvoice: dry, warm\nmood: focused\ntraits: curious, precise\n")
    pg = _persona_get()
    res.append(check("/v1/persona GET returns the written persona",
                     pg["ok"] and "Persona v2" in pg["persona"] and "mood: focused" in pg["persona"]))
    # the editor stamped an operator-provenance memory
    res.append(check("persona edit recorded as operator-provenance memory",
                     any(f["src"] == "operator" and "persona" in f["text"].lower()
                         for f in _memory_json()["facts"])))

    # the structured state block still parses (personality system intact)
    from harness.personality.persona_file import parse_persona, render_state
    prose, state = parse_persona(pg["persona"])
    rs = render_state(state)
    res.append(check("persona v2 state block parses",
                     state.get("mood") == "focused" and "voice: dry, warm" in rs and "Persona v2" in prose))

    # ADR-006 personality chip endpoint
    ps = _persona_state()
    res.append(check("/v1/persona/state returns parsed state",
                     ps["ok"] and ps["state"].get("mood") == "focused"))

    # ADR-006 §D4: agency-tick hygiene compacts a dirty registry deterministically (no model call)
    import json as _json
    reg = os.environ["SP_RECALL_REGISTRY"]
    with open(reg, "a", encoding="utf-8") as f:
        f.write("{bad json line\n")
    from harness.skills.memory import verify_registry, compact_registry
    dirty = "NEEDS COMPACTION" in verify_registry()
    compact_registry()
    clean = "OK" in verify_registry()
    res.append(check("agency hygiene: verify flags + compact cleans", dirty and clean))

    ok = all(res)
    print(f"\nG-PK2-UI-ENDPOINTS (offline): {'PASS' if ok else 'FAIL'} ({sum(res)}/{len(res)})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
