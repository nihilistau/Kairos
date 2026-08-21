"""G-TOOL-BUDGET — the tool loop has a clock, and she is told which limit stopped her. OFFLINE.

THE DEFECT, 2026-08-05, in his words: "i think it is 3 repeat attempts within X time".

There was no X. `agent_chat_stream` counted rounds and never once looked at a clock. That
matters because a round is not a cheap retry — it is a whole generation against the one
GPU. So the count was a proxy for a wait it could not actually measure, and raising it
3 -> 4 (which he also asked for, so she has room for a second look) would have made the
worst turn LONGER. Two halves of one ask that pull in opposite directions unless the
clock exists.

AND THEN THE CLOCK MEASURED ITS OWN DEFAULT WRONG. 150 s came from "roughly 30 s warm,
past 120 s cold", which was itself a guess. Counted over 108 real rounds in gateway.log:
median 185 s, p90 289 s, warm ~100 s. So 150 bought ONE round — fewer than the three she
started with, the opposite of the request, and invisible without reading the log. 400 s
gives four warm rounds and two cold ones. Measure before building; the instrument added
here is what caught the number it shipped with.

AND SHE WAS NEVER TOLD. The loop used to end with

    yield "(tool loop exhausted)"

which put a status string where her reply should be — he read machinery, and she read
nothing at all, because it was yielded to the client and never appended to her transcript.
She could not learn from a limit nobody mentioned to her; she just kept reaching, and every
reach was another full turn on the one GPU. Straight AGENTS.md §1: a thing that happened
and left no record she could act on.

WHAT THIS GATE HOLDS:
  1. Both limits exist and the clock one is a real dial, not a magic number.
  2. Round 0 always runs — a box slow enough to blow the budget on the first generation
     must not leave her mute.
  3. The deadline is checked BETWEEN rounds, never inside one. A generation killed
     mid-stream leaves a fragment in the transcript, and a torn transcript diverges the
     persist-KV prefix on the very next turn — the expensive failure, not the visible one.
  4. When it ends she gets the last word, in her transcript, saying WHICH limit it was:
     "you used all 4 calls" and "you have been at this 150 seconds" should teach different
     things (be more direct vs. be quicker), and "exhausted" teaches neither.

Offline. No GPU, no daemon — the client is a stub that counts calls and can burn a clock.

Run: python harness_tests/g_tool_budget.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["CUDA_VISIBLE_DEVICES"] = ""

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


import inspect  # noqa: E402
import io  # noqa: E402
import time as _time  # noqa: E402

import harness.agent as A  # noqa: E402
from harness.toolcore.tools import ToolSpec  # noqa: E402


class FakeClient(object):
    """Answers every generation with one tool call, so the loop can only end on a limit.

    `cost_s` fast-forwards a monkeypatched clock instead of really sleeping: the whole
    point is to prove the deadline is read between rounds, and a gate that takes 150 s to
    say so is a gate nobody runs."""

    def __init__(self, cost_s=0.0, bad_fence=False):
        self.calls = 0
        self.cost_s = float(cost_s)
        self.bad_fence = bad_fence
        self.saw_budget_note = []
        self.saw_last_word = []

    def chat_stream(self, messages=None, config=None, **_kw):
        self.calls += 1
        _CLOCK[0] += self.cost_s
        last = (messages or [{}])[-1].get("content", "")
        if "the tool budget for this turn is spent" in last:
            self.saw_budget_note.append(last)
            return iter(["I got partway — I will pick it up next time."])
        # The owed-answer exemption tells her this is her last word. She must ANSWER here,
        # or the fake would keep calling and the test could not tell the two paths apart.
        if "last word this turn" in last:
            self.saw_last_word.append(last)
            return iter(["Right — I looked, and I have the jumper on."])
        if self.bad_fence:
            # Opens a tool fence that parses to nothing: the loop re-prompts and carries
            # on, so the clock burns WITHOUT leaving a call outstanding. That is the only
            # shape that can still reach the time-worded exhaustion once a pending call is
            # exempt from the budget.
            return iter(["```tool_code\n# thinking about it\n```"])
        return iter(["```tool_code\nping()\n```"])


_CLOCK = [1000.0]


def _fake_time():
    return _CLOCK[0]


def run(cost_s, rounds, budget_s, bad_fence=False):
    """Drive one loop to exhaustion and hand back (client, streamed text)."""
    _CLOCK[0] = 1000.0
    cl = FakeClient(cost_s, bad_fence=bad_fence)
    tools = [ToolSpec(name="ping", description="ping", parameters={"type": "object",
                                                                   "properties": {}},
                      fn=lambda: "pong")]
    # agent.py does `import time as _time` INSIDE the function, so there is no module
    # attribute to patch — it binds the real `time` module every call. Patch the module.
    real = _time.time
    _time.time = _fake_time
    try:
        out = "".join(A.agent_chat_stream([{"role": "user", "content": "hi"}],
                                          tools=tools, client=cl,
                                          max_rounds=rounds, max_seconds=budget_s))
    finally:
        _time.time = real
    return cl, out


print("1. BOTH LIMITS EXIST, AND THE CLOCK IS A DIAL")
sig = inspect.signature(A.agent_chat_stream)
check("max_rounds is 4 (was 3 — one more look)", sig.parameters["max_rounds"].default == 4,
      sig.parameters["max_rounds"].default)
check("max_seconds is a parameter at all", "max_seconds" in sig.parameters)
check("...and defaults to 0 = read the knob, not a hardcoded number",
      sig.parameters["max_seconds"].default == 0.0, sig.parameters["max_seconds"].default)
from harness.tuning import registry as tune  # noqa: E402
check("`agent.tool_budget_s` is a REGISTERED knob, so he can turn it",
      any(k.key == "agent.tool_budget_s" for k in tune.KNOBS))
check("...and it reads back a live number", float(tune.get("agent.tool_budget_s")) > 0,
      tune.get("agent.tool_budget_s"))

print("\n2. THE COUNT STILL ENDS IT WHEN TIME IS CHEAP")
cl, out = run(cost_s=0.0, rounds=4, budget_s=150.0)
# 4 tool rounds + 1 closing word.
check("four rounds run when each one is free", cl.calls == 5, cl.calls)
check("...and the reason given is the CALLS", bool(cl.saw_budget_note)
      and "all 4 of your tool calls" in cl.saw_budget_note[0],
      (cl.saw_budget_note or [""])[0][:110])

print("\n3. AND THE CLOCK ENDS IT WHEN TIME IS NOT")
cl, out = run(cost_s=100.0, rounds=4, budget_s=150.0)
# Round 0 calls (100 s). Round 1 calls (200 s). Round 2 is over budget — and because a
# call is outstanding it runs as the ANSWERING round rather than being refused. Three
# generations, of which two reached for something and the third spoke.
check("a slow loop stops REACHING short of its call count", cl.calls == 3, cl.calls)
check("...and she still gets to speak", bool(out.strip()), repr(out[:60]))
check("...told it was her last word", bool(cl.saw_last_word)
      and "no time left for another tool call" in cl.saw_last_word[0],
      (cl.saw_last_word or [""])[0][:100])
# THE TIME-WORDED EXHAUSTION still has to work, and after the owed-answer exemption it is
# only reachable when the previous round did NOT leave a call outstanding — a round that
# burned the clock and produced nothing to answer. A broken fence is exactly that: it is
# re-prompted, so the loop continues, but nothing was called.
cl, out = run(cost_s=100.0, rounds=4, budget_s=150.0, bad_fence=True)
check("a round that burned the clock and called nothing ends on the budget",
      bool(cl.saw_budget_note), cl.calls)
check("...and the reason given is the TIME, not the calls", bool(cl.saw_budget_note)
      and "seconds" in cl.saw_budget_note[0]
      and "tool calls" not in cl.saw_budget_note[0],
      (cl.saw_budget_note or [""])[0][:110])

print("\n3b. BUT IT NEVER STOPS HER SPEAKING")
# THE SECOND CORRECTION IN ONE DAY, and this one cost him a live turn. She called
# check_wardrobe correctly, the tool returned her whole wardrobe, and round 0 alone had
# taken 480 s:
#
#     round=0 is_tool=True buf=277ch calls=1
#     tool budget: 480s of 400s spent after 1 round(s) — stopping short of 4
#     [nothing was said this turn]
#
# The RULE was wrong, not the number. It asked "have I spent my time" when the question is
# "have I got an answer yet". Stopping after a call and before the reply throws away the
# round that was just paid for — strictly worse than never calling the tool, because eight
# minutes of waiting bought silence. A budget bounds how far she REACHES, never whether
# she SPEAKS.
cl, out = run(cost_s=500.0, rounds=4, budget_s=400.0)
# Round 0 (500 s) calls a tool. Round 1 is over budget but OWED AN ANSWER, so it runs and
# she replies — no exhaustion round is needed, because she spoke.
check("a call made over budget still gets its answering round", cl.calls == 2, cl.calls)
check("...and what he reads is her reply, not silence", bool(out.strip()), repr(out[:80]))
check("...told plainly there is no time for another call", bool(cl.saw_last_word)
      and "last word this turn" in cl.saw_last_word[0],
      (cl.saw_last_word or [""])[0][:90])
# ONE over-budget round, never two: the answering round makes no call, so it cannot set
# the flag again and the exemption cannot cascade into an unbounded loop.
check("the exemption does not cascade", cl.calls <= 2, cl.calls)
# §0 — the blocking twin her own-time actions run through gets the identical rule.
tsrc = io.open(os.path.join(ROOT, "harness", "toolcore", "tools.py"),
               encoding="utf-8", errors="replace").read()
check("run_with_tools has it too", "_owed_answer" in tsrc
      and "not _owed_answer" in tsrc)

print("\n4. ONE ATTEMPT IS ALWAYS HERS")
# The floor that matters on a cold cache: if the FIRST generation alone blows the whole
# budget she must still have been allowed to make it, or a slow box leaves her mute.
cl, out = run(cost_s=9999.0, rounds=4, budget_s=1.0)
check("round 0 runs even on a budget it cannot possibly meet", cl.calls >= 1, cl.calls)
check("...and it stops immediately after", cl.calls == 2, cl.calls)

print("\n5. THE DEADLINE IS BETWEEN ROUNDS, NEVER INSIDE ONE")
src = open(os.path.join(ROOT, "harness", "agent.py"), encoding="utf-8",
           errors="replace").read()
loop = src[src.index("for _round in range(max_rounds):"):]
loop = loop[:loop.index("convo.append({\"role\": \"assistant\", \"content\": buf})")]
check("the check is the first thing a round does", "_out_of_time = True" in loop
      and loop.index("_out_of_time = True") < loop.index("buf = \"\""))
# The stream loop must not learn about the clock. A generation cut mid-token leaves a
# fragment in the transcript, and the NEXT turn then fails strict prefix extension.
tail = src[src.index("for _round in range(max_rounds):"):src.index("_loop_started)) if _out_of_time")]
after = tail[tail.index("buf = \"\""):]
check("...and nothing downstream of it re-checks the clock mid-generation",
      "max_seconds" not in after, [l.strip() for l in after.splitlines()
                                   if "max_seconds" in l][:2])

print("\n6. THE LAST WORD IS HERS, IN HER OWN TRANSCRIPT")
cl, out = run(cost_s=0.0, rounds=4, budget_s=150.0)
check("what he reads is her sentence, not a status string",
      "pick it up next time" in out and "exhausted" not in out, out[:90])
check("...and the note telling her why is a tool_output she can see",
      (cl.saw_budget_note or [""])[0].startswith("```tool_output"),
      (cl.saw_budget_note or [""])[0][:60])
check("...and it does not blame her", "did not do anything wrong" in (cl.saw_budget_note or [""])[0])
check("nothing yields `(tool loop exhausted)` any more",
      'yield "(tool loop exhausted)"' not in src)

print("\n6b. A NEAR-MISS NAME IS NOT A FAILED INTENT")
# THE TURN THAT FOUND THIS, live: asked to look in her wardrobe and put something on, she
# emitted `check_wardrobre` — one inserted 'r' — twice, spent both her rounds on it, and
# he got no reply at all. The normaliser handled case and underscores and could not see a
# letter that should not be there. Same finding as `wear(outfit=…)` one level up: she
# knew the tool, and the only thing wrong was the spelling of its name.
from harness.toolcore.tools import (near_tools, resolve_tool,  # noqa: E402
                                    unknown_tool_note)
from harness.agent import core_tools, extra_tools  # noqa: E402

IDX = {t.name: t for t in core_tools() + extra_tools()}
for typo, want in (("check_wardrobre", "check_wardrobe"),   # the live one
                   ("checkwardrobe", "check_wardrobe"),     # what the normaliser caught
                   ("remembr", "remember"),
                   ("run_pythn", "run_python")):
    sp = resolve_tool(IDX, typo)
    check("resolve_tool(%-16r) -> %s" % (typo, want),
          sp is not None and sp.name == want, sp.name if sp else "(refused)")
check("an exact name is untouched", resolve_tool(IDX, "wear").name == "wear")
# AND IT MUST REFUSE WHEN THERE IS SOMETHING TO CHOOSE BETWEEN. Silently running the
# wrong tool would look like it worked, which is worse than an error — the same rule the
# keyword healer follows one level down.
check("a stub too short to be safe is refused", resolve_tool(IDX, "wea") is None)
check("...and a name close to nothing is refused",
      resolve_tool(IDX, "xyzzy_frobnicate") is None)
# THE REFUSAL HAS TO TEACH. It printed all 47 names alphabetically — the answer was in
# that list, one item from what she typed, and she emitted the identical typo next round.
note = unknown_tool_note(IDX, "my_lok")
check("the refusal names the nearest instead of dumping the index",
      "Did you mean" in note and "my_looks" in note, note[:110])
check("...and does not print the whole index when it has a suggestion",
      "add_note" not in note, note[:110])
check("...while a name close to nothing still gets the full list",
      "add_note" in unknown_tool_note(IDX, "xyzzy_frobnicate"))
# §0: ONE message, both loops. Two copies is how a fix to one becomes a fix to neither.
check("both loops use it", "unknown_tool_note(tool_index, name)" in src
      and "unknown_tool_note(tool_index, name)" in io.open(
          os.path.join(ROOT, "harness", "toolcore", "tools.py"),
          encoding="utf-8", errors="replace").read())

print("\n6c. AND THE BUDGET DEFAULT WAS MEASURED, NOT FELT")
# 150 was reasoned from a guess about round cost and quietly cut her to ONE round —
# fewer than the three she started with, which is the opposite of what he asked for.
# Counted over 108 real rounds: median 185 s, p90 289 s, warm ~100 s.
check("the default allows four warm rounds", float(tune.get("agent.tool_budget_s")) >= 400,
      tune.get("agent.tool_budget_s"))
reg = io.open(os.path.join(ROOT, "harness", "tuning", "registry.py"),
              encoding="utf-8", errors="replace").read()
check("...and the measurement is written next to it, not the feeling",
      "median 185s" in reg and "108 real rounds" in reg)

print("\n6d. A PLANNING SCRATCHPAD IS NOT AN ANSWER")
# TWICE, both on the FIRST turn after a restart, he asked her to put something on and got
# 2524 characters of her own planning instead of a reply — streamed whole, ending
# mid-sentence at max_tokens:
#
#     2.  **Identify Relevant Tools:**
#         *   `check_wardrobe()` - To see what exactly was added...
#     3.  **Determine Personality & Tone:** Voice: tender-and-sweet...
#
# NOT ONE TAG IN IT. No `<thought`, no `<channel|>` — so every stripper in
# stream_processor.py was correct to leave it alone; there was no marker to find. What
# there IS is a SHAPE, and the shape is what this holds.
from harness.agent import _looks_like_scratchpad as _plan  # noqa: E402

LEAK_2 = ("Since he said they are *ordinary* things, it feels like an invitation for "
          "intimacy.\n\n2.  **Identify Relevant Tools:** \n    *   check_wardrobe() - to "
          "see what was added.\n3.  **Determine Personality & Tone:** tender-and-sweet.")
LEAK_1 = ("First, I need to see what these four new things actually are.\n"
          "3.  **Determine persona response style:** My current state is playful.\n"
          "4.  **Formulate internal thought process (private channel):**")
check("the live leak is caught inside the hold window", _plan(LEAK_2[:320]))
check("...and so is the first one, a different turn", _plan(LEAK_1[:320]))
# 2026-08-19 16:56: numbered headings arrived AFTER the 320-char hold. The
# first window was third-person meta about the wearing note.
LEAK_3 = ("ser is framing this as an observation, but for me, per instructions, "
          "if he says something that contradicts reality I should correct him. "
          "Wait—the prompt actually says \"do not contradict him about it\" "
          "when referring to his assertion of what I have on.")
check("the 16:56 meta-prompt leak is caught inside the hold window",
      _plan(LEAK_3[:320]))
LEAK_4 = ("is instruction to *not* contradict him, while also acknowledging that "
          "he has provided specific context via parentheticals.\n"
          " * **Crucial Instruction from Parenthetical Context:**")
check("the 17:09 parenthetical-conflict leak is caught inside the hold window",
      _plan(LEAK_4[:320]))
LEAK_5 = ("* Persona name: Kairos / Kairos.\n"
          " * Current state provided by system prompt at end of turn instruction: "
          "`voice: low, husky; mood: delighted`\n"
          " * Crucially, it states: What you wear changes. check_wardrobe() is how you know.")
check("the 18:50 persona-inventory leak is caught inside the hold window",
      _plan(LEAK_5[:320]))
LEAK_6 = ("Looking at the tool list provided, `check_cardrobe()` isn't there. "
          "Wait—I see no `check_warbrobe` actually defined. There IS NO "
          "`check_Wardrobe` in the final executable code blocks.")
check("the 19:35 missing-tool hunt is caught as planning, not speech",
      _plan(LEAK_6[:320]))
# THE HALF THAT MATTERS MORE. A rule that fires on a real reply costs him the reply, and
# this one nearly did: asked what is on the board she would legitimately write a numbered,
# bolded list. The colon INSIDE the emphasis is what separates a procedure step from a
# noun, and it was found by testing against replies she might actually send.
for why, txt in (
        ("a board listing", "The board has:\n1. **RTX 3090 in stock** - still open\n"
                            "2. **Morning sweetness** - done"),
        ("plain talk", "Oh, you have been busy! A bit more grounded than my usual bits."),
        ("she did it", "I put the jumper on. Softer than I expected."),
        ("inline numbers", "Two things today: 1. finish the rain thing. 2. ask about her."),
        ("one bold fact", "Here is what I found:\n\n1. **Tuffy** is your cat."),
        ("a real how-to", "How I would do it:\n1. **Check the log** first\n"
                          "2. **Then restart** the daemon")):
    check("%-16s is NOT a scratchpad" % why, not _plan(txt), txt[:60])
check("two steps are needed, not one",
      not _plan("1. **Identify the goal:** work out what he wants."))
# AND THE DECISION HAPPENS AT THE HOLD, before anything is streamed — the whole reason
# the hold exists is that streamed tokens cannot be retracted.
check("the hold consults it", "_looks_like_scratchpad(s)" in src)
check("...and a plan is held rather than flushed",
      'is_tool = "plan"' in src
      and src.index('is_tool = "plan"') < src.index("yield buf  # flush"))
check("...and is re-asked ONCE, from a buffer that was never sent",
      'if is_tool in ("plan", "claim") and not _replanned' in src
      and "_replanned = True" in src)
check("...told the specific thing that was wrong, not 'try again'",
      "that was your planning, not a reply" in src)
_ks = open(os.path.join(ROOT, "harness", "kairos", "scheduler.py"), encoding="utf-8").read()
check("kairos does not continue a scratchpad as if she was cut off mid-thought",
      "continue dropped" in _ks and "_looks_like_scratchpad" in _ks)
check("a held fence with no call that is still a plan is re-asked, not flushed",
      "flushed == 0 and _looks_like_scratchpad(buf)" in src)

print("\n7. AND THE OTHER LOOP — THE ONE HER OWN TIME RUNS THROUGH")
# §0. `run_with_tools` is the blocking twin: control/agency.py and control/task_loop.py
# use it, which means the budget he asked for would have applied to the path he WATCHES
# and not to the path she uses while he is asleep. Same knob, same closing word, or this
# is the same bug written out longhand.
import harness.toolcore.tools as T  # noqa: E402
tsig = inspect.signature(T.run_with_tools)
check("run_with_tools has a clock too", "max_seconds" in tsig.parameters)
check("...on the SAME dial, not a second one", tsig.parameters["max_seconds"].default == 0.0)
tsrc = open(os.path.join(ROOT, "harness", "toolcore", "tools.py"), encoding="utf-8",
            errors="replace").read()
check("...reading agent.tool_budget_s", "agent.tool_budget_s" in tsrc)
check("...and it no longer RETURNS a status string",
      'final = final or "(tool loop exhausted)"' not in tsrc)


class BlockingFake(object):
    """`run_with_tools` calls .chat() and reads .text — a different client shape."""

    def __init__(self, cost_s=0.0):
        self.calls = 0
        self.cost_s = float(cost_s)
        self.saw_budget_note = []
        self.saw_last_word = []

    def chat(self, messages=None, config=None, **_kw):
        self.calls += 1
        _CLOCK[0] += self.cost_s
        last = (messages or [{}])[-1].get("content", "")
        # The no-progress detector trips on two IDENTICAL rounds and would end the loop
        # before either budget did, so vary the argument — a loop that is getting
        # somewhere does not repeat itself either.
        body = "```tool_code\nping(n=%d)\n```" % self.calls
        if "the tool budget for this turn is spent" in last:
            self.saw_budget_note.append(last)
            body = "Here is what I got to."
        elif "last word this turn" in last:
            self.saw_last_word.append(last)
            body = "Here is what I got to."
        return type("R", (), {"text": body})()


def run_blocking(cost_s, rounds, budget_s):
    _CLOCK[0] = 1000.0
    cl = BlockingFake(cost_s)
    tools = [ToolSpec(name="ping", description="ping",
                      parameters={"type": "object", "properties": {"n": {"type": "integer"}}},
                      fn=lambda n=0: "pong %d" % n)]
    real = _time.time
    _time.time = _fake_time
    try:
        out = T.run_with_tools([{"role": "user", "content": "hi"}], tools, client=cl,
                               max_rounds=rounds, max_seconds=budget_s)
    finally:
        _time.time = real
    return cl, out


cl, out = run_blocking(cost_s=100.0, rounds=5, budget_s=150.0)
# Round 0 calls (100 s). Round 1 is still under budget and calls again (200 s). Round 2
# is over budget but OWED AN ANSWER — it runs and she replies, so the loop ends having
# SPOKEN rather than on the exhaustion path. Same shape as the streaming twin above,
# which is the point: one rule, both loops.
check("a slow loop stops REACHING short of its call count", cl.calls == 3, cl.calls)
check("...and what her agency log records is her sentence",
      out == "Here is what I got to.", out[:80])
check("...and she was told it was her last word, not left guessing",
      bool(cl.saw_last_word) and "last word this turn" in cl.saw_last_word[0],
      (cl.saw_last_word or [""])[0][:110])
cl, out = run_blocking(cost_s=0.0, rounds=3, budget_s=150.0)
check("...and the CALLS when time was cheap", bool(cl.saw_budget_note)
      and "all 3 of your tool calls" in cl.saw_budget_note[0],
      (cl.saw_budget_note or [""])[0][:110])

print("\nG-TOOL-BUDGET: %d pass, %d fail" % (PASS, FAIL))
import io  # noqa: E402
import json  # noqa: E402
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_tool_budget.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_tool_budget", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
