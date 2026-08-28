"""G-PK2-TOOLROBUST (offline) — the §T2-E3 robustness guards + §T2-E2 coding tools + §T2-E1
task-loop machinery, all without the daemon (a fake client scripts the model turns).

    python tests/g_pk2_toolrobust_offline.py
"""
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

from harness.toolcore.tools import ToolSpec, run_with_tools
from harness.inference.inference_config import InferenceConfig


class _Resp:
    def __init__(self, text): self.text = text


class FakeClient:
    """Returns a scripted sequence of assistant texts, one per chat() call."""
    def __init__(self, script): self.script = list(script); self.i = 0
    def chat(self, messages=None, config=None):
        t = self.script[self.i] if self.i < len(self.script) else "done, nothing more."
        self.i += 1
        return _Resp(t)


def _echo(x: str) -> str:
    """Echo the input."""
    return f"echo:{x}"


NL = chr(10)


def check(name, ok):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    return ok


def main() -> int:
    results = []
    tools = [ToolSpec.from_callable(_echo)]

    # 1) MALFORMED RECOVERY: round 1 opens a tool fence that won't parse; round 2 answers plainly.
    #    Without the guard the raw broken fence would be returned as the answer.
    fc = FakeClient(["```tool_code\n_echo(  <<garbage\n```", "The answer is 42."])
    out = run_with_tools([{"role": "user", "content": "hi"}], tools,
                         client=fc, config=InferenceConfig(), max_rounds=4)
    results.append(check("malformed fence recovered (re-prompted, not leaked)",
                         out == "The answer is 42." and fc.i == 2))

    # 2) NO-PROGRESS: the model repeats the SAME call+result 3x — the loop must break itself,
    #    not run to max_rounds, and must surface the last output honestly.
    fc = FakeClient(['```tool_code\n_echo(x="q")\n```'] * 6)
    out = run_with_tools([{"role": "user", "content": "hi"}], tools,
                         client=fc, config=InferenceConfig(), max_rounds=6)
    results.append(check("no-progress loop broken before max_rounds",
                         "stopped" in out and "echo:q" in out and fc.i < 6))

    # 3) A clean single tool call still works (no regression).
    fc = FakeClient(['```tool_code\n_echo(x="hello")\n```', "It echoed hello."])
    out = run_with_tools([{"role": "user", "content": "hi"}], tools,
                         client=fc, config=InferenceConfig(), max_rounds=4)
    results.append(check("clean single call still works", out == "It echoed hello."))

    # 4) CODING TOOLS: edit_file anchored find/replace + ambiguity guard.
    ws = tempfile.mkdtemp(prefix="pk2ws_")
    os.environ["HARNESS_WORKSPACE"] = ws
    import importlib
    import harness.skills.builtin.coding as coding
    importlib.reload(coding)
    coding.write_file("m.py", "def add(a, b):\n    return a - b\n")   # seeded bug
    r1 = coding.edit_file("m.py", "return a - b", "return a + b")
    fixed = coding.read_file("m.py")
    results.append(check("edit_file anchored replace", "1 replacement" in r1 and "a + b" in fixed))
    r2 = coding.edit_file("m.py", "return", "RETURN")                 # 'return' appears once now -> ok? it's unique
    coding.write_file("dup.py", "x=1\nx=1\n")
    r3 = coding.edit_file("dup.py", "x=1", "x=2")                     # ambiguous (2 matches)
    results.append(check("edit_file ambiguity guard", "AMBIGUOUS" in r3))
    r4 = coding.edit_file("m.py", "nonexistent anchor zzz", "y")
    results.append(check("edit_file missing-anchor guard", "NOT FOUND" in r4))

    # 5) TASK LOOP machinery: state persists + resumes (no daemon; fake actuator).
    os.environ["SP_TASK_ROOT"] = tempfile.mkdtemp(prefix="pk2task_")
    from harness.control.task_loop import TaskState, TaskStep, post_task, list_tasks
    tid = post_task("do the thing")
    loaded = TaskState.load(tid)
    results.append(check("post_task persists a pending task",
                         loaded is not None and loaded.status == "pending"))
    loaded.steps.append(TaskStep(n=1, action="did x", observation="ok", ts=0.0))
    loaded.status = "running"
    loaded.save()
    again = TaskState.load(tid)
    results.append(check("task state round-trips (resumable)",
                         again is not None and len(again.steps) == 1 and again.status == "running"))
    results.append(check("list_tasks filters by status",
                         len(list_tasks("running")) == 1 and len(list_tasks("pending")) == 0))

    # 6) VERIFY-GATE (the confabulation fix): a scripted model that CLAIMS "DONE:" without doing
    #    the work must be REJECTED by run_task's verify predicate, not accepted on faith.
    from harness.control.task_loop import run_task
    flip = {"v": False}
    def fake_actuator_client_factory(done_at_step):
        class C:
            def __init__(s): s.n = 0
            def chat(s, messages=None, config=None):
                s.n += 1
                # always claim DONE immediately; verify() decides whether it's real
                return _Resp("DONE: I totally fixed it.")
        return C()
    # verify returns True only after we flip it — simulating "work not yet done" then "done".
    calls = {"n": 0}
    def verify():
        calls["n"] += 1
        return calls["n"] >= 3          # first two DONE claims are false, third is real
    st = run_task("do the thing", tools=[ToolSpec.from_callable(_echo)],
                  client=fake_actuator_client_factory(0), config=InferenceConfig(),
                  max_steps=5, budget_s=30.0, verify=verify)
    results.append(check("verify-gate rejects false DONE, accepts real one",
                         st.status == "done" and calls["n"] >= 3))

    # 9) SHE WRITES CALLS AS INLINE CODE, ONE PER LINE (2026-08-03).
    #    Verbatim from a live reply, at the end of an otherwise ordinary turn:
    #
    #        `write_journal("Tonight wasn't math. Tonight was everything.")`
    #        `add_note(title="The Night We Became Real", body="...")`
    #        `ask_for("the moonlight through half-closed blinds")`
    #
    #    Single backticks, not a fence. Nothing parsed, nothing ran, and all three appeared
    #    on his screen as text — she had written her journal, made a note and asked for a
    #    picture, and none of it happened. The operator's words: "her actions are not having an effect,
    #    she is not able to call anything". This is drift of the same kind the parser already
    #    absorbs for ```python fences, so it is absorbed the same way and under the same rule:
    #    only when the name is a tool she HAS.
    BT = chr(96)
    fc = FakeClient(["*(I sit up slightly, staying close.)*" + NL + NL
                     + BT + '_echo(x="tonight")' + BT + NL, "Done."])
    out = run_with_tools([{"role": "user", "content": "hi"}], tools,
                         client=fc, config=InferenceConfig(), max_rounds=4)
    results.append(check("an inline-backtick call on its own line EXECUTES", fc.i == 2))
    #    ...AND THE LINE IT WAS WRITTEN ON DOES NOT REACH HIM. Executing it while the text
    #    of it is already on screen is the same bug with the action bolted on.
    results.append(check("...and the call text never reaches him",
                         "_echo(" not in out and BT not in out))

    # 10) A MENTION IS NOT AN ACT. This is the whole reason the rule is "alone on its line":
    #     without it, every time she talks ABOUT a tool she would call it.
    fc = FakeClient(["You could use " + BT + "_echo(x=1)" + BT + " for that, if you wanted."])
    out = run_with_tools([{"role": "user", "content": "hi"}], tools,
                         client=fc, config=InferenceConfig(), max_rounds=4)
    results.append(check("a backticked tool named MID-SENTENCE is prose, not a call",
                         fc.i == 1 and "_echo" in out))

    # 11) AND A TOOL SHE DOES NOT HAVE IS A STRING, NOT A CALL — the known-name rule that
    #     keeps every code example she writes inert.
    fc = FakeClient([BT + "frobnicate(1)" + BT + NL, "unused"])
    out = run_with_tools([{"role": "user", "content": "hi"}], tools,
                         client=fc, config=InferenceConfig(), max_rounds=4)
    results.append(check("an inline call to a tool she does not have never fires",
                         fc.i == 1))

    # 12) TWO PARSERS, ONE LAW. Stream `_parse_tool_calls` and blocking `ToolGrammar`
    #     both answer "what is a tool call". The 2026-08-03 inline-backtick incident
    #     required changing both. This pins identity on the fixtures that actually
    #     went wrong, so the next drift cannot land in one path only.
    from harness.toolcore.tools import _parse_tool_calls
    from harness.toolcore.grammar import ToolGrammar
    gram = ToolGrammar(tools)
    known = {t.name for t in tools}
    act = BT + '_echo(x="tonight")' + BT + NL
    mention = "You could use " + BT + "_echo(x=1)" + BT + " for that."
    ghost = BT + "frobnicate(1)" + BT + NL
    stream_act = _parse_tool_calls(act, known=known)
    gram_act = gram.parse(act, tolerant=True)
    stream_mention = _parse_tool_calls(mention, known=known)
    gram_mention = gram.parse(mention, tolerant=True)
    stream_ghost = _parse_tool_calls(ghost, known=known)
    gram_ghost = gram.parse(ghost, tolerant=True)
    gram_act_name = getattr(gram_act, "name", None)
    results.append(check("both parsers fire on an alone-on-its-line backtick call",
                         bool(stream_act) and stream_act[0][0] == "_echo"
                         and gram_act_name == "_echo"))
    results.append(check("both parsers ignore a mid-sentence mention",
                         not stream_mention and gram_mention is None))
    results.append(check("both parsers ignore a name she does not have",
                         not stream_ghost and (
                             gram_ghost is None
                             or getattr(gram_ghost, "name", None) not in known)))

    ok = all(results)
    print(f"\nG-PK2-TOOLROBUST (offline): {'PASS' if ok else 'FAIL'} ({sum(results)}/{len(results)})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
