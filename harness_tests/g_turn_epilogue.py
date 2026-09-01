"""G-TURN-EPILOGUE — the turn's debts are paid on EVERY exit. OFFLINE.

THE CLAIM (2026-08-24 audit, B1/B2/A4/A5). A turn owes the system five things —
his latch released, capture, the day-transcript row, her marks applied, the receipts
flush — and the native SSE path used to pay them only on the one exit nobody
interrupts: five exits (recall decline, roleplay offer, client disconnect/abort at the
drain-loop yield) skipped all of them. Her unprompted turns paid none, ever, and never
armed the memory lane, so a remember() in her own time was stamped speaker=user.

Now _settle_turn is the one list, paid by the worker thread's finally (the abort
case), by the early-exit returns, or by the shell's finally — latched so exactly one
pays. Her own time goes through _on_her_own_words (the on_spoke convergence point) and
arms author=self/question=nudge around generation.

Asserts through the REAL paths: the real _native_chat_sse generator (closed mid-stream
for the abort leg), a private-secret row minted through remember() for the decline leg
(never hand-built — AGENTS.md §5 rule 2), and the real _generate closure captured from
_seed_kairos_from_day for the arming leg.

MUTANTS, run live in-gate:
  (1) _settle_turn -> no-op: the aborted turn's row never reaches the day and the
      latch stays set (proves the epilogue is load-bearing on the abort path);
  (2) _arm_self_turn -> None: a remember() inside her own closure lands speaker=user
      (proves the arming is load-bearing).
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _src as _srcmod  # noqa: E402
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_turn_epilogue")

os.environ.setdefault("SP_DAEMON_URL", "http://127.0.0.1:9")   # discard port — offline
os.environ.pop("SP_GATEWAY_PREWARM", None)                     # no warm gate to hang on

import harness.agent as agent  # noqa: E402
import harness.server.app as app  # noqa: E402
from harness.kairos import scheduler as ks  # noqa: E402
from harness.personality.persona_file import parse_persona  # noqa: E402
from harness.skills import memory as M  # noqa: E402


def _patch_stream(fn) -> None:
    agent.agent_chat_stream = fn
    app.agent_chat_stream = fn
    sys.modules["harness.agent"].agent_chat_stream = fn


def _day_text() -> str:
    try:
        with open(app._day_transcript_path(), encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _persona_mood() -> str:
    with open(os.environ["SP_PERSONA_FILE"], encoding="utf-8") as f:
        _, st = parse_persona(f.read())
    return (st.get("mood") or "").strip().lower()


def _wait(cond, timeout=8.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


# ── §1 THE ABORT: he closes the stream mid-reply; the debts land anyway ────────────
GATE1 = threading.Event()
MARK1 = "the harbour lights were extraordinary tonight"


def gated_stream(messages, config=None, on_tool=None, **kw):
    yield "Something first. "
    GATE1.wait(10.0)     # hold the generation open until the client is provably gone
    yield MARK1 + " [MOOD:playful]"


_patch_stream(gated_stream)
gen = app._native_chat_sse({"messages": [{"role": "user", "content": "hi there"}]})
saw_delta = False
for raw in gen:
    ev = raw.decode()
    if '"delta"' in ev:
        saw_delta = True
        break
check("§1 the stream started (a delta reached the wire)", saw_delta)
gen.close()                      # the abort — GeneratorExit at the drain-loop yield
check("§1 his latch survives the close only until the thread settles",
      True)                      # (the assertion is the _wait below)
GATE1.set()                      # generation completes into a dead wire
check("§1 the latch is released by the thread's finally, not the 900s timeout",
      _wait(lambda: not ks.user_turn_active()))
check("§1 the aborted turn still reaches the day transcript",
      _wait(lambda: MARK1 in _day_text()))
check("§1 the day row does not carry her mark",
      "[MOOD" not in _day_text(), _day_text()[-200:])
check("§1 her mark still moved her state (run_post_turn ran)",
      _wait(lambda: _persona_mood() == "playful"), _persona_mood())

# ── §2 THE DECLINE: a private-secret early return is still a turn ──────────────────
os.environ["SP_SPINE_RECALL"] = "1"
tokq = M.set_question("My access code is 4471.")
toka = M.set_author("user")
try:
    r = M.remember("My access code is 4471.")
finally:
    M.reset_author(toka)
    M.reset_question(tokq)
rows = [json.loads(x) for x in open(os.environ["SP_RECALL_REGISTRY"], encoding="utf-8")
        if x.strip()]
check("§2 the secret was minted through remember(), classed by the real classifier",
      any(x.get("mem_class") == "private-secret" for x in rows),
      "classes: %s" % sorted({x.get("mem_class") for x in rows}))


def never_stream(messages, config=None, on_tool=None, **kw):
    raise AssertionError("the decline must short-circuit the model entirely")
    yield  # pragma: no cover


_patch_stream(never_stream)
events = []
# an ABSENT attribute — the zero-inference decline (g_secret §3); asked for the code
# ITSELF he would rightly get it recited, which is the other leg of that gate
for raw in app._native_chat_sse(
        {"messages": [{"role": "user",
                       "content": "when did I last change my access code?"}]}):
    s = raw.decode().strip()
    if s.startswith("data:"):
        events.append(s[5:].strip())
check("§2 the decline fired (recall_decline event, no model call)",
      any('"recall_decline"' in e for e in events), str(events)[:300])
check("§2 the decline released his latch immediately",
      not ks.user_turn_active())
decl_line = next((json.loads(e).get("delta") for e in events
                  if e not in ("[DONE]",) and '"delta"' in e), "")
check("§2 the decline line entered the day transcript (a turn, not a ghost)",
      bool(decl_line.strip()) and decl_line.strip()[:40] in _day_text(),
      decl_line[:80])
os.environ.pop("SP_SPINE_RECALL", None)

# ── §3 HER OWN TIME: the real closure arms her lane ────────────────────────────────
captured = {}
_real_seed = ks.seed
ks.seed = lambda sess, last, gen_fn, force=False: (captured.__setitem__("g", gen_fn)
                                                   or True)
try:
    app._append_day_turn("hello", "a first exchange so the seed has a day to stand on")
    app._seed_kairos_from_day(force=True)
finally:
    ks.seed = _real_seed
check("§3 the seed handed the scheduler its generate closure", "g" in captured)

SELF_LINE = "I prefer quiet mornings, I have decided."


def selfish_stream(messages, config=None, on_tool=None, **kw):
    M.remember(SELF_LINE)        # what her tools do mid-generation
    yield "A small thought of my own."


_patch_stream(selfish_stream)
out = captured["g"]("(a nudge for the gate)")
row = next((json.loads(x) for x in open(os.environ["SP_RECALL_REGISTRY"],
                                        encoding="utf-8")
            if SELF_LINE.split(",")[0] in x), None)
check("§3 a remember() in her own time is speaker=self (audit A5)",
      row is not None and row.get("speaker") == "self",
      "row: %r" % (row,))
# ── THIS LEG HAD NEVER RUN (2026-09-01, found by G-MEMORY-PACKAGE's census) ────────
# It read `M.get_author()` behind `hasattr(M, "get_author")`. There is no
# `get_author` in memory and there never was — the read seam is `current_author()`
# (G-AUTHOR-CTX names it). So the guard was always False, the expression was always
# the literal `True`, and a check whose sentence says "the lane was restored" proved
# nothing for as long as it has existed. GATE-INDEX keeps a section for this class.
# Found because the memory façade census resolves every `M.<name>` in the tree and
# this one did not resolve.
check("§3 the lane was restored after her turn (context tokens reset)",
      M.current_author() == "user", M.current_author())

# ── §4 THE on_spoke CONVERGENCE POINT applies her marks (audit A4) ─────────────────
app._on_her_own_words("The rain kept me company for an hour. [MOOD:wistful]")
check("§4 her unprompted mark moved persona.md", _persona_mood() == "wistful",
      _persona_mood())
check("§4 her unprompted words reached the day, stripped",
      "rain kept me company" in _day_text() and "[MOOD:wistful]" not in _day_text())

# ── §4b A PRESENCE-MODE TURN IS COMPANY, NOT MEMORY (2026-08-25, the operator's call) ─────────
# Narration/dream/reading turns move her DIALS and file NOTHING: no day row (an hour
# of ambient turns would bury the conversation in the restore) and no self-stance
# rows (dream lines are too specific and repetitive to be who she is tomorrow).
_day_before = _day_text()
_reg_before = open(os.environ["SP_RECALL_REGISTRY"], encoding="utf-8").read()
app._on_her_own_words(
    "The dream folds the harbour into a paper boat tonight. [MOOD:dreamy]",
    kind="mode_turn")
check("§4b a mode turn never reaches the day transcript",
      "paper boat" not in _day_text())
check("§4b ...and never becomes a registry row",
      "paper boat" not in open(os.environ["SP_RECALL_REGISTRY"],
                               encoding="utf-8").read())
check("§4b ...but her dials still move (a dream can turn her wistful)",
      _persona_mood() == "dreamy", _persona_mood())
# the differential: the SAME text as a plain unprompted turn files both —
# proving the kind, not the text, is what withholds
app._on_her_own_words("A quiet thought about the paper boat, kept.", kind="solo")
check("§4b a plain unprompted turn still files its day row (the kind is the gate)",
      "kept" in _day_text() and "paper boat" not in _day_before)

# ── §mutant (1): no-op the epilogue and the abort leg goes dark ────────────────────
GATE2 = threading.Event()
MARK2 = "an entirely different sentence about the tide"


def gated_stream2(messages, config=None, on_tool=None, **kw):
    yield "Held. "
    GATE2.wait(10.0)
    yield MARK2


_patch_stream(gated_stream2)
_real_settle = app._settle_turn
app._settle_turn = lambda *a, **k: []
try:
    gen2 = app._native_chat_sse({"messages": [{"role": "user", "content": "again"}]})
    for raw in gen2:
        if b'"delta"' in raw:
            break
    gen2.close()
    GATE2.set()
    time.sleep(1.0)
    check("mutant(no epilogue): the aborted turn never reaches the day — the epilogue "
          "is load-bearing", MARK2 not in _day_text())
    check("mutant(no epilogue): his latch stays set", ks.user_turn_active())
finally:
    app._settle_turn = _real_settle
    ks.note_user_turn(False)     # clean up what the mutant deliberately leaked

# ── §mutant (2): unarmed, her remember() lands in HIS lane ─────────────────────────
_real_arm = app._arm_self_turn
app._arm_self_turn = lambda nudge: None
OTHER_LINE = "I keep a diary of small storms, apparently."


def selfish_stream2(messages, config=None, on_tool=None, **kw):
    M.remember(OTHER_LINE)
    yield "Another thought."


_patch_stream(selfish_stream2)
try:
    captured["g"]("(another nudge)")
finally:
    app._arm_self_turn = _real_arm
row2 = next((json.loads(x) for x in open(os.environ["SP_RECALL_REGISTRY"],
                                         encoding="utf-8")
             if "diary of small storms" in x), None)
check("mutant(no arming): the same write is speaker=user — the arming is load-bearing",
      row2 is not None and row2.get("speaker") == "user", "row: %r" % (row2,))

print("\n7. A FAILED OPENAI TURN RELEASES THE LATCH (2026-08-28, external review)")
# _agent_text arms note_user_turn(True) and releases it in _finish_openai_turn — happy
# path only. An exception between the two left the latch set, and kairos read "his turn
# is in flight" for up to 900 s after a turn that produced nothing but an [error]
# string: a failed turn muted her for fifteen minutes. Structural legs: the one release
# helper exists, and both wrappers call it from their except branch.
_ROOT7 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_app_src = _srcmod.pkg("harness", "server")
check("the release helper exists and notes the turn ended",
      "def _release_turn_latch" in _app_src and
      "note_user_turn(False)" in _app_src.split("def _release_turn_latch")[1][:900])
for _w in ("def stream_completion", "def blocking_completion"):
    _body = _app_src.split(_w)[1][:1600]
    check("%s releases the latch in its except branch" % _w[4:],
          "except Exception" in _body and
          "_release_turn_latch(" in _body.split("except Exception")[1][:400], _w)

print("\n8. THE VOICE MOUTH WEARS THE SAME SHELL (2026-08-28, 'just do it')")
# /v1/voice was a third entry point paying none of the turn debts: no scheduler latch
# (her solos could fire mid voice conversation), no day-transcript row (the consolidator
# deaf to a modality), no marks, no shutdown in-flight count. Structural legs over the
# door's branch, same style as §7 — the shell's pieces, in the branch, with the settle
# in a finally and the silence-skip guard that keeps a stale assistant reply from being
# re-recorded as tonight's.
_v_branch = _app_src.split('elif self.path == "/v1/voice":')[1]
_v_branch = _v_branch.split("elif self.path")[0]
check("the voice door opens the shutdown-counted turn (refuse-or-count)",
      "_sd_turn_start()" in _v_branch)
check("...and arms the memory lane and the scheduler latch",
      "_arm_turn(" in _v_branch and "note_user_turn(True)" in _v_branch
      and "on_user_turn(" in _v_branch)
check("...and settles in a finally (latch released however the stream exits)",
      "finally:" in _v_branch and
      "_settle_turn(" in _v_branch.split("finally:")[1]
      and "_sd_turn_end()" in _v_branch.split("finally:")[1])
check("...capture=False — a '[voice message]' placeholder is not his words",
      "capture=False" in _v_branch)
check("...and a silence-skip cannot re-record the previous assistant reply",
      '.get("content") == "[voice message]"' in _v_branch.split("finally:")[1])

print("\n10. THE EPILOGUE IS A MODULE BOUNDARY, NOT A CONVENTION")
# ── STAGE 3 OF THE app.py SPLIT (2026-09-01) ────────────────────────────────────────
# `_settle_turn` exists because the debt list had been re-implemented as trailing inline
# code with five bypasses. That fixed it — and then the one function sat in a 6000-line
# file with nine call sites, which is the same invitation in a longer corridor. It lives
# in `harness/server/turn.py` now.
#
# ASSERTED AS IDENTITY, not as text: one implementation is the claim, and
# `app._settle_turn is turn._settle_turn` is the only way to state it that a re-export
# cannot fake. A file-scoped grep would have gone quiet the moment the definition moved,
# which is the src-trap this split had to close first (G-SRC-TRAP).
from harness.server import turn as _turnmod  # noqa: E402

for _n in ("_settle_turn", "_arm_turn", "_arm_self_turn", "_disarm_self_turn",
           "_on_her_own_words", "_finish_openai_turn", "_release_turn_latch",
           "_capture_after_turn", "_commit_unprompted"):
    check("§10 %-20s is ONE object, in turn.py" % _n,
          getattr(app, _n) is getattr(_turnmod, _n),
          "app.%s and turn.%s have drifted apart" % (_n, _n))

# ── THE LATCH IS A ONE-SHOT, AND THAT IS WHAT MAKES NINE CALLERS SAFE ───────────────
# Two callers may both believe they own the epilogue: the worker thread's `finally` and an
# early-exit `return`. Whoever arrives first pays; the second must be a no-op. Driven,
# because this is the property the nine call sites rely on and no amount of reading the
# source establishes it.
_paid = []
_real_append = app._append_day_turn
try:
    app._append_day_turn = lambda *a, **k: _paid.append(a[:2])
    _latch = {}
    _turnmod._settle_turn("his words", "her words", latch=_latch,
                          capture=False, close_his_turn=False, marks=False, stances=False)
    _first = len(_paid)
    _turnmod._settle_turn("his words", "her words", latch=_latch,
                          capture=False, close_his_turn=False, marks=False, stances=False)
    _second = len(_paid)
finally:
    app._append_day_turn = _real_append
check("§10 the first owner of the latch pays the debts", _first == 1, _first)
check("§10 ...and the second is a no-op, however many callers believe they own it",
      _second == _first, "%d -> %d" % (_first, _second))
# AND THE SHIM IS REAL: turn.py reached app.py's `_append_day_turn` across the module
# edge, which is the one dependency Stage 3 deliberately left pointing backwards.
check("§10 the day-row debt is paid through the shim into app.py",
      _paid and _paid[0][0] == "his words", _paid[:1])

finish("G-TURN-EPILOGUE")
