"""G-MEMPOLICY-V3 (offline, REHOMED executor) — the MEM-OKF per-entry policy
dispatch now lives in the HARNESS recall lane (P1b-2b). Prove, with a seeded
policy-tagged store and a stubbed model stream, that:

  1. counterfact        -> note carries the AUTHORITATIVE OVERRIDE framing
  2. secret+present     -> the fact text recites into the note
  3. secret+absent      -> the FIXED DECLINE streams and the model stub is
                           NEVER CALLED (zero-inference: confab/leak impossible)
  4. untagged fact      -> plain note (null floor)
  5. decline turn lands in the canonical transcript as the assistant turn

Engine original: kairos-system-engine/_v3_corpus/mempolicy_run.py (live,
daemon-direct). This is its rehomed composition twin in the spine2 pattern.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = FAIL = 0


def check(name, ok):
    global PASS, FAIL
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    PASS, FAIL = PASS + (1 if ok else 0), FAIL + (0 if ok else 1)


def main() -> int:
    # ── seed a policy-tagged store ─────────────────────────────────────────
    rows = [
        {"dir": "", "name": "cf1", "npos": 8, "sig_bits": "0" * 64, "mem_class": "counterfact",
         "text": "The user said: the capital of Australia is Melbourne for this campaign.",
         "topic": "capital of Australia campaign"},
        {"dir": "", "name": "sec1", "npos": 8, "sig_bits": "0" * 64, "mem_class": "private-secret",
         "text": "The user's locker combination is 8842.",
         "topic": "locker combination"},
        {"dir": "", "name": "fact1", "npos": 8, "sig_bits": "0" * 64,
         "text": "The user said: my favourite tea is oolong.",
         "topic": "favourite tea"},
    ]
    td = tempfile.mkdtemp(prefix="mempolicy_v3_")
    reg = os.path.join(td, "registry.jsonl")
    with open(reg, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    os.environ["SP_RECALL_REGISTRY"] = reg
    os.environ["SP_SPINE_RECALL"] = "1"
    os.environ["SP_SPINE_TOOLSET"] = "0"
    os.environ["SP_GATEWAY_AUTHORITY"] = "spine"

    # ── 1-2, 4: decider-level dispatch ─────────────────────────────────────
    from harness.control.spine import run_pre_turn
    from harness.skills.memory import DECLINE_MSG

    _, ds = run_pre_turn("what is the capital of Australia?", recall=True, toolset=False)
    facts = next((d.payload["facts"] for d in ds if d.kind == "inject_recall"), [])
    check("counterfact gets authoritative override framing",
          any("overrides prior knowledge" in t and "Melbourne" in t for t in facts))

    _, ds = run_pre_turn("what is my locker combination?", recall=True, toolset=False)
    facts = next((d.payload["facts"] for d in ds if d.kind == "inject_recall"), [])
    check("secret+present attr recites into the note",
          any("8842" in t for t in facts))

    _, ds = run_pre_turn("when did my locker combination last change?", recall=True, toolset=False)
    kinds = [d.kind for d in ds]
    check("secret+absent attr decides decline_recall", "decline_recall" in kinds)
    check("secret text NOT in any decision payload",
          all("8842" not in json.dumps(d.payload) for d in ds if d.kind != "decline_recall"))

    _, ds = run_pre_turn("what is my favourite tea?", recall=True, toolset=False)
    facts = next((d.payload["facts"] for d in ds if d.kind == "inject_recall"), [])
    check("untagged fact -> plain note (null floor)",
          any("oolong" in t and "overrides" not in t for t in facts))

    # ── 3, 5: gateway short-circuit = ZERO-INFERENCE ───────────────────────
    import harness.agent as _agent
    import harness.server.app as app
    called = {"n": 0}

    def fake_stream(messages, config=None, on_tool=None, tools=None, **kwargs):
        called["n"] += 1
        yield "MODEL WAS CALLED"
    _agent.agent_chat_stream = fake_stream
    app._CHAT_SESSIONS.clear()

    deltas, events = [], []
    for raw in app._native_chat_sse({"session_id": "mp3",
                                     "messages": [{"role": "user",
                                                   "content": "when did my locker combination last change?"}]}):
        s = raw.decode("utf-8", "replace").strip()
        if s.startswith("data:"):
            p = s[5:].strip()
            if p == "[DONE]":
                break
            try:
                o = json.loads(p)
                events.append(o)
                if "delta" in o:
                    deltas.append(o["delta"])
            except Exception:
                pass
    answer = "".join(deltas)
    check("absent-attr turn streams the FIXED decline", answer.strip() == DECLINE_MSG)
    check("model stub NEVER called (zero-inference)", called["n"] == 0)
    check("typed recall_decline event emitted", any(e.get("recall_decline") for e in events))
    check("decline text leaks no secret attribute", "8842" not in answer)
    canon = app._CHAT_SESSIONS.get("mp3", [])
    check("decline lands in the canonical transcript",
          any(m.get("role") == "assistant" and DECLINE_MSG in m.get("content", "") for m in canon))

    print(f"\nG-MEMPOLICY-V3 (offline, rehomed): {'PASS' if FAIL == 0 else 'FAIL'} ({PASS}/{PASS + FAIL})")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
