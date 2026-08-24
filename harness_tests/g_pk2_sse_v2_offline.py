"""G-PK2-SSE-V2 (offline) — the gateway's typed SSE events (ADR-006 §D3): persona + tool + delta,
backward-compatible with pure-delta clients. No daemon (agent_chat_stream is monkeypatched).

    python tests/g_pk2_sse_v2_offline.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# SANDBOX FIRST (2026-08-24). One of nine gates the sandbox audit caught writing into
# her REAL stores; `_gate.sandbox` points every root at a temp dir and must run BEFORE
# any harness import, because a module resolves its root once, at import.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import sandbox as _sandbox  # noqa: E402
_sandbox(os.path.basename(__file__))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PERSONA = os.path.join(tempfile.gettempdir(), "sp_pk2_sse_persona.md")
os.environ["SP_PERSONA_FILE"] = PERSONA
with open(PERSONA, "w", encoding="utf-8") as f:
    f.write("You are Kairos.\n\n## Personality state\nvoice: dry, warm\nmood: focused\ntraits: curious\n")

import harness.agent as agent
import harness.server.app as app


def fake_stream(messages, config=None, on_tool=None, **kwargs):
    # simulate: the model calls a tool, then answers
    # **kwargs: agent_chat_stream gained mutate_messages; a stub that does not
    # absorb it never runs, and every later check false-fails.
    if on_tool:
        on_tool("run_python", {"args": [], "kwargs": {"code": "2+2"}}, "4")
    yield "The answer "
    yield "is 4."


def fake_stream_shift(messages, config=None, on_tool=None, **kwargs):
    # simulate: the model shifts its own mood via a PF-B3 tag (ADR-007 post-turn spine)
    yield "Ha — good one. "
    yield "[MOOD:playful]"


def check(name, ok):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    return ok


def collect(body, stream=fake_stream):
    agent.agent_chat_stream = stream  # monkeypatch the streaming agent
    app.agent_chat_stream = stream
    # app imports agent_chat_stream inside the fn, so patch the source module
    import sys as _s
    _s.modules["harness.agent"].agent_chat_stream = stream
    events = []
    for raw in app._native_chat_sse(body):
        s = raw.decode().strip()
        if s.startswith("data:"):
            p = s[5:].strip()
            if p == "[DONE]":
                events.append("[DONE]")
            else:
                events.append(json.loads(p))
    return events


def main() -> int:
    res = []
    ev = collect({"messages": [{"role": "user", "content": "hi"}]})
    persona_ev = [e for e in ev if isinstance(e, dict) and "persona" in e]
    tool_ev = [e for e in ev if isinstance(e, dict) and "tool" in e]
    delta_ev = [e for e in ev if isinstance(e, dict) and "delta" in e]
    res.append(check("persona event emitted with state",
                     bool(persona_ev) and persona_ev[0]["persona"].get("mood") == "focused"))
    res.append(check("tool event emitted with name+result",
                     bool(tool_ev) and tool_ev[0]["tool"]["name"] == "run_python"
                     and tool_ev[0]["tool"]["result"] == "4"))
    res.append(check("delta events carry the answer", "".join(e["delta"] for e in delta_ev) == "The answer is 4."))
    res.append(check("stream terminates with [DONE]", ev[-1] == "[DONE]"))

    # backward-compat: typed_events=false yields ONLY delta + DONE
    ev2 = collect({"messages": [{"role": "user", "content": "hi"}], "typed_events": False})
    only_delta = all((e == "[DONE]") or ("delta" in e) for e in ev2)
    res.append(check("typed_events=false is pure-delta (backward compatible)", only_delta and not any("tool" in e for e in ev2 if isinstance(e, dict))))

    # ADR-007 post-turn spine: a [MOOD:] tag in the reply -> persisted + a changed:true persona
    # event AFTER the answer (verified shift), before [DONE].
    ev3 = collect({"messages": [{"role": "user", "content": "tell me a joke"}]}, stream=fake_stream_shift)
    shifted = [e for e in ev3 if isinstance(e, dict) and e.get("changed") is True and "persona" in e]
    res.append(check("verified persona shift emits changed:true event",
                     len(shifted) == 1 and shifted[0]["persona"].get("mood") == "playful"))
    from harness.personality.persona_file import parse_persona
    _, st2 = parse_persona(open(PERSONA, encoding="utf-8").read())
    res.append(check("the shift persisted to persona.md", st2.get("mood") == "playful"))

    ok = all(res)
    print(f"\nG-PK2-SSE-V2 (offline): {'PASS' if ok else 'FAIL'} ({sum(res)}/{len(res)})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
