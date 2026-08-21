"""G-PK2-SPINE (offline) — ADR-007: the harness Spine fold (decide → execute → verify),
the stock deciders (persona/hygiene/recall), and the VERIFY_FAIL honesty path. No daemon.

    python tests/g_pk2_spine_offline.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REG = os.path.join(tempfile.gettempdir(), "sp_pk2_spine.jsonl")
PERSONA = os.path.join(tempfile.gettempdir(), "sp_pk2_spine_persona.md")
os.environ["SP_RECALL_REGISTRY"] = REG
os.environ["SP_PERSONA_FILE"] = PERSONA
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:59999"
open(REG, "w").close()
with open(PERSONA, "w", encoding="utf-8") as f:
    f.write("You are Kairos.\n\n## Personality state\nvoice: dry\nmood: neutral\ntraits: curious\n")

from harness.control.spine import (TurnView, Decision, FnDecider, run_spine,
                                   run_post_turn, run_tick, recall_decider,
                                   stock_executors, stock_verifiers)
from harness.skills.memory import remember, search_memories, memory_stats


def check(name, ok):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    return ok


def main() -> int:
    res = []

    # 1) persona shift: decide -> execute -> VERIFY (mood really landed in persona.md)
    receipts = run_post_turn("how are you", "Feeling sharp today. [MOOD:playful]")
    r = [x for x in receipts if x.kind == "persona_shift"]
    from harness.personality.persona_file import parse_persona
    _, state = parse_persona(open(PERSONA, encoding="utf-8").read())
    res.append(check("persona shift decided + executed + verified",
                     len(r) == 1 and r[0].ok and r[0].verified is True and state.get("mood") == "playful"))

    # 2) no tags -> no decision (the decider is quiet on a plain reply)
    receipts = run_post_turn("hi", "Just a normal answer.")
    res.append(check("no tags -> no persona decision", not any(x.kind == "persona_shift" for x in receipts)))

    # 3) tick hygiene: dirty registry -> compaction decided, executed, VERIFIED clean
    remember("The user's name is Sam.", source="operator")
    with open(REG, "a", encoding="utf-8") as f:
        f.write("{bad line\n")
        f.write(json.dumps({"text": "The user's name is Sam.", "dir": "", "npos": 0}) + "\n")
    receipts = run_tick()
    r = [x for x in receipts if x.kind == "compact_registry"]
    res.append(check("tick hygiene: compaction decided + verified clean",
                     len(r) == 1 and r[0].ok and r[0].verified is True))
    receipts2 = run_tick()
    res.append(check("clean registry -> no compaction decision",
                     not any(x.kind == "compact_registry" for x in receipts2)))

    # 4) recall decider: matching fact -> inject_recall with the fact in payload
    remember("The user's favorite color is teal.", source="user turn")
    dec = recall_decider().decide(TurnView(phase="pre", user_text="what is my favorite color?"))
    res.append(check("recall decider proposes matching facts",
                     len(dec) == 1 and any("teal" in f for f in dec[0].payload["facts"])))
    dec2 = recall_decider().decide(TurnView(phase="pre", user_text="quantum chromodynamics lattice"))
    res.append(check("recall decider abstains on foreign query", dec2 == []))

    # 5) VERIFY_FAIL honesty: an executor that CLAIMS success but does nothing must be flagged
    lying = {"persona_shift": lambda d: "totally did it"}
    view = TurnView(phase="post", reply="[MOOD:stoic]")
    # fresh persona file the "executor" never touches -> verifier must fail it
    with open(PERSONA, "w", encoding="utf-8") as f:
        f.write("x\n\n## Personality state\nmood: playful\n")
    receipts = run_spine(view, [FnDecider("p", lambda v: [Decision(kind="persona_shift",
                                                                   payload={"reply": v.reply})])],
                         lying, stock_verifiers())
    res.append(check("lying executor -> VERIFY_FAIL receipt (never silently trusted)",
                     len(receipts) == 1 and receipts[0].ok and receipts[0].verified is False))

    # 6) the new memory tools
    s = search_memories("favorite color")
    res.append(check("search_memories ranks the match", "teal" in s and "match" in s))
    st = memory_stats()
    res.append(check("memory_stats summarizes provenance mix", "operator" in st and "facts" in st))

    ok = all(res)
    print(f"\nG-PK2-SPINE (offline): {'PASS' if ok else 'FAIL'} ({sum(res)}/{len(res)})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
