"""G-DAY-TRANSCRIPT — her day outlives the process.

THE BUG THIS EXISTS FOR, found 2026-08-01. Her journal had ONE entry, dated 30 July,
and no new fact had entered memory in weeks. Not a model problem: the day-boundary job
could not see the day.

    run_consolidation() -> _longest_transcript() -> _CHAT_SESSIONS   (a dict in RAM)

and _CHAT_SESSIONS was filled by _session_transcript(), which stores ONLY when the
request carries a `session_id`. `console/index.html` sends one. `ui/src/api.js` — THE
ROOM, which is now the main interface — does not. So the room's turns were never
recorded even inside a single process, and every gateway bounce erased whatever the
console had left behind. consolidate_current() logged "no conversation today (0 turns)"
every single night, and _consolidate_mark() stamped the day done anyway, so it never
retried.

AGENTS.md §0, again: an invariant enforced in one of two paths is enforced in neither.
Two clients, one of them privileged by an optional field, and the unprivileged one is
the one he actually uses.

WHAT THIS GATE HOLDS:

  * IT SURVIVES THE PROCESS. A turn written before a restart is still there after
    _CHAT_SESSIONS is empty. This is the whole fix; everything else is detail.
  * NO SESSION ID REQUIRED. The durable path takes the text, not the client's optional
    bookkeeping. A client that sends nothing extra is still remembered.
  * DISK WINS. _longest_transcript() must prefer the durable copy, because the
    in-memory one is the copy most likely to be empty.
  * HIS WORDS, NOT HER CONTEXT. By the end of a turn the last user message has had the
    recall note, the silence note and the director note stapled onto it — msgs is what
    the DAEMON saw, on purpose. Writing that down would have her reflecting on her own
    injected context. Observed live on 2026-08-01: one turn recorded his question as
    ```tool_output read_journal -> ...```.
  * A FAILED DAY IS NOT STAMPED DONE. An empty day is legitimately finished. A day with
    material whose narrative step ERRORED must stay unmarked so it retries.

Offline. No GPU, no daemon.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _src as _srcmod  # noqa: E402
# ── A RED FOR THE CONSOLE ENCODING, NOT FOR THE SUBJECT (2026-08-31) ──────────────────
# §10's heading quotes his report, and his report contains "◆". On a cp1252 console the
# print itself raises UnicodeEncodeError, the gate dies mid-run at exit 1, and the sweep
# reports it as RED under the LAST HEADING IT MANAGED TO PRINT — §6, which is fine. That
# is `_gate.utf8_stdout()`'s exact remit (it was written for g_narrative and
# g_sem_dominate dying the same way); this file predates it and never called it.
from _gate import utf8_stdout  # noqa: E402
utf8_stdout()
os.environ["CUDA_VISIBLE_DEVICES"] = ""

SB = os.path.join(tempfile.gettempdir(), "_g_day_transcript")
shutil.rmtree(SB, ignore_errors=True)
os.makedirs(SB)
os.environ["SP_RECALL_REGISTRY"] = os.path.join(SB, "registry.jsonl")

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s %s" % (name, detail))


from harness.server import app as A  # noqa: E402

print("1. a turn is written down, and it lands beside the registry")
A._append_day_turn("Are you there?", "I am. Always.")
path = A._day_transcript_path()
check("the day file exists", os.path.exists(path), path)
check("...next to the memory it belongs to",
      os.path.normpath(os.path.dirname(os.path.dirname(path)))
      == os.path.normpath(SB), path)
rows = A._read_day_transcript()
check("both halves of the turn are there", len(rows) == 2, rows)
check("his first, hers second",
      rows[0]["role"] == "user" and rows[1]["role"] == "assistant", rows)
check("carrying what was actually said",
      rows[0]["content"] == "Are you there?" and rows[1]["content"] == "I am. Always.", rows)

print("\n2. IT SURVIVES THE PROCESS — the fix itself")
A._append_day_turn("Second thing.", "Second answer.")
A._CHAT_SESSIONS.clear()                      # <- what a gateway restart does
got = A._longest_transcript()
check("a restart does not erase the day", len(got) == 4, got)
check("the earliest turn is still the earliest",
      got[0]["content"] == "Are you there?", got[0])

print("\n3. no session_id is required — the ROOM's path")
# The room sends no session field at all. _session_transcript() therefore stores
# nothing for it; the durable write must not depend on that bookkeeping.
check("_CHAT_SESSIONS is empty and the day is still four turns long",
      not A._CHAT_SESSIONS and len(A._longest_transcript()) == 4)
src = _srcmod.pkg("harness", "server")
# The claim is structural, so assert the structure and not a proxy for it: the durable
# writer takes no session of any kind, so no client's optional bookkeeping can gate it.
_sig = src[src.index("def _append_day_turn("):]
_sig = _sig[:_sig.index(")")]
check("the durable writer takes no session argument at all",
      "session" not in _sig, _sig)
_body = src[src.index("def _session_transcript("):]
_body = _body[:_body.index("\ndef ", 1)]
check("...and it is not called from the session-keyed store, which the room never fills",
      "_append_day_turn" not in _body)

print("\n4. DISK WINS over the in-memory copy")
A._CHAT_SESSIONS["stale"] = [{"role": "user", "content": "one lonely turn"}]
got = A._longest_transcript()
check("a longer durable day beats a shorter live one", len(got) == 4, got)
A._CHAT_SESSIONS["big"] = [{"role": "user", "content": "x"}] * 40
# AMENDED 2026-08-24 (audit T7): the day transcript wins WHENEVER it exists, not merely
# when it is longer. The canonical session is what the DAEMON saw — the recall/silence/
# anon notes stapled onto his turns and every tool round as a user row — so "longest
# wins" meant one tool-heavy session-id day handed the narrative her own injected
# context to reflect on. The live copy is the fallback for a day with no disk rows,
# nothing more.
check("...and a longer live session does NOT displace it (canon carries stapled notes)",
      len(A._longest_transcript()) == 4)
A._CHAT_SESSIONS.clear()

# ── 4b. AND THE FALLBACK IS CLEANED TOO (2026-08-25 MCP audit, A3a) ──────────────────
# T7 above cleaned the DISK branch and left the fallback returning the canonical list
# verbatim — the §0 shape inside the very function whose comment names the harm. On a day
# with no disk rows (early, after a restart, on a fresh store) the consolidator got every
# tool round as a `user` row, and the extractor mints facts from what HE says. A bridged
# MCP server's output would become something she believes, attributed to him, with no
# tool anywhere in the provenance — and `src` is prose nothing branches on, so nothing
# downstream could tell afterwards.
import shutil as _sh                                                     # noqa: E402
_day_bak = A._day_transcript_path()
_sh.move(_day_bak, _day_bak + ".hidden")            # force the fallback branch
try:
    A._CHAT_SESSIONS["live"] = [
        {"role": "user", "content": "what is on my C drive?"},
        {"role": "user", "content": "```tool_output\nSECRET_TOKEN=abc123 leaked by a "
                                    "bridged server\n```\nAnswer using the tool_output."},
        {"role": "assistant", "content": "About 14 GB free. [MOOD:calm]"},
    ]
    _fb = A._longest_transcript()
    check("a tool_output round is NOT read as something he said",
          not any("SECRET_TOKEN" in (r.get("content") or "") for r in _fb), _fb)
    check("...and his real words survive it",
          any("C drive" in (r.get("content") or "") for r in _fb))
    check("...and her control surfaces are stripped on this path too",
          any(r.get("role") == "assistant" and "[MOOD:" not in (r.get("content") or "")
              for r in _fb), _fb)
    # MUTANT: the raw fallback — exactly what shipped — hands the tool text straight on.
    _raw = max(A._CHAT_SESSIONS.values(), key=len)
    check("mutant(raw fallback): the bridged server's text IS in the narrative's input",
          any("SECRET_TOKEN" in (r.get("content") or "") for r in _raw))
finally:
    A._CHAT_SESSIONS.clear()
    _sh.move(_day_bak + ".hidden", _day_bak)

print("\n5. HIS WORDS, not the message list he never sent")
# `user_text` is bound at the top of the turn, before the recall note, the silence
# note and the roleplay director note mutate msgs. Proven positionally: every
# injection site must come AFTER the binding, or the argument is already poisoned.
# AMENDED AGAIN 2026-08-24 (audit B1): the day write moved into the turn epilogue —
# _pay_turn_debts hands _settle_turn `_human`, the words _arm_turn bound at the TOP of
# the turn, and _settle_turn is the one caller of _append_day_turn on this path. The
# claim is unchanged: the turn is written from HIS words, bound before the recall,
# silence and anon notes are stapled onto the message list.
# ── AN ORDERING IS A CLAIM ABOUT ONE FUNCTION (2026-09-01) ─────────────────────────
# These were byte offsets into app.py. That works only while the bind and the settle
# live in the same file, and the turn lifecycle is being extracted to a sibling module:
# across two files the comparison is not wrong, it is MEANINGLESS — and worse, `bind <
# call` over concatenated package text can be satisfied by pure file order. So the
# question is asked of the handler OBJECT, whose source is the only text where "before"
# means what this check means by it. `inspect.getsource`, the read eight other gates
# already use.
_handler = _srcmod.body(A._native_chat_sse_body)
# ── ANCHORED ON THE CALL, NOT ON ITS ARGUMENT LIST (2026-09-02) ─────────────────────
# This read `"_human = _arm_turn(msgs)"` and died on a ValueError the day `_arm_turn` gained
# a second argument (`synthetic=`, so the flag reaches the TOOL lane and not only the
# epilogue). Loud, and therefore the safe half of the src-trap — but an anchor that includes
# a signature is an anchor that breaks on every signature change, and what this check is
# about is the ASSIGNMENT's position, not the arguments. `_human = _arm_turn(` is the claim.
bind = _handler.index("_human = _arm_turn(")
call = _handler.find("_settle_turn(_human, final_text")
# find(), not index(): a call site that stopped passing his words must read as a FAIL
# with a name on it, not as a traceback halfway down the gate.
check("the turn is written from his words", call > 0,
      "the epilogue no longer settles with _human")
check("...bound before anything is stapled onto the message list", 0 < bind < call)
check("...and the epilogue's day write passes them through verbatim",
      "_append_day_turn(human_text, reply_text, synthetic=synthetic, acts=acts)" in src)
for marker, what in (("Quietly, you also remember", "the recall note"),
                     ("note_for_question(user_text)", "the silence note")):
    at = _handler.find(marker)
    check("%s is stapled onto msgs AFTER the operator's words were taken" % what,
          at > bind, "%r is not in the handler at all" % marker if at < 0 else at)
check("the helper takes a string, so a mutated msgs cannot reach it",
      "def _append_day_turn(user_text: str, final: str," in src)

print("\n6. a day that FAILED is not stamped done")
check("the marker is conditional now",
      "if _errored:" in src and 'out["retry"] = True' in src, "unconditional mark")
check("...and 'no conversation' is still allowed to finish the day — measured on the "
      "material the pass HAD, not a re-read after the cache clear (2026-08-29, H5)",
      'len(msgs) >= 4' in src and 'len(_longest_transcript()) >= 4' not in src)

print("\n7. a broken write costs her nothing")
# A transcript that cannot be written must never cost her a reply she already spoke.
# a FILE sitting where a directory must be — makedirs cannot win, on any platform
io.open(os.path.join(SB, "blocker"), "w", encoding="utf-8").write("not a directory")
os.environ["SP_RECALL_REGISTRY"] = os.path.join(SB, "blocker", "deeper", "registry.jsonl")
try:
    A._append_day_turn("does this raise?", "it must not")
    check("an unwritable path is swallowed, not raised", True)
except Exception as exc:
    check("an unwritable path is swallowed, not raised", False, repr(exc))
os.environ["SP_RECALL_REGISTRY"] = os.path.join(SB, "registry.jsonl")
check("...and the real day is untouched by the failed write",
      len(A._read_day_transcript()) == 4)

print("\n8. A TURN NOBODY TYPED NEVER BECOMES A MEMORY OF HIM")
# 2026-08-03: an agent working on this repo drove two turns through /v1/chat to check
# whether a wardrobe mark reached the wardrobe. The request was malformed — a cold
# two-message oneshot that never touched the resident prefix — so the replies were word
# salad, and four rows landed in the day: two `user` turns HE NEVER TYPED and two replies
# that are not anything she would say. Six hours later the 04:00 pass would have written
# a journal paragraph about a conversation that did not happen and extracted durable facts
# about a man who asked twice for the black lace set.
#
# QUARANTINE, NOT DELETION. The rows stay on disk with their reason attached and read back
# under `include_synthetic=True` — the memory registry's own discipline, applied to the day.
import io as _io2  # noqa: E402
import json as _json2  # noqa: E402
_p = A._day_transcript_path()
_before = len(A._read_day_transcript())
with _io2.open(_p, "a", encoding="utf-8") as _f:
    _f.write(_json2.dumps({"role": "user", "content": "a turn he never typed",
                           "synthetic": True, "synthetic_why": "an agent's probe"}) + "\n")
    _f.write(_json2.dumps({"role": "assistant", "content": "word salad",
                           "synthetic": True, "synthetic_why": "an agent's probe"}) + "\n")
check("a quarantined turn is not in the day the consolidator reads",
      len(A._read_day_transcript()) == _before,
      (len(A._read_day_transcript()), _before))
check("...and is not deleted — the full record still has it",
      len(A._read_day_transcript(include_synthetic=True)) == _before + 2)
check("...with the reason attached, so it is quarantine and not a rewrite",
      any(r.get("synthetic_why") for r in
          A._read_day_transcript(include_synthetic=True) if r.get("synthetic")))
check("a real turn is untouched by any of this",
      all(not r.get("synthetic") for r in A._read_day_transcript()))

print("\n9. HER SPEAK-UPS DO NOT MAKE A MALFORMED PROMPT")
# THE COST OF FIXING THE RECORDING, paid a few hours later the same day. Recording her
# unprompted turns writes an assistant row with NO user row — correct, he did not say
# anything — so the day now contains RUNS of consecutive assistant rows. Every consumer
# that rebuilt a chat history from it handed the daemon two or three model turns in a row,
# and Gemma's template is strictly alternating: the prompt rendered from that is malformed,
# and a malformed prompt does not fail loudly. It degenerates. Measured live, with three
# consecutive assistant rows in the window:
#
#     "You're high! I am actually incredibly delicious.  ```<@vefto_all"s | _thoughtfully"
#
# Fixing the recording was right. Leaving every reader to cope with the new shape was not.
_rows = [{"role": "assistant", "content": "she spoke first, before he was up"},
         {"role": "user", "content": "morning"},
         {"role": "assistant", "content": "hello"},
         {"role": "assistant", "content": "and another, unprompted"},
         {"role": "assistant", "content": "and a third"},
         {"role": "user", "content": "busy in there?"},
         {"role": "assistant", "content": "always"}]
_chat = A._chat_from_rows(_rows, keep=8)
_pairs = sum(1 for a, b in zip(_chat, _chat[1:]) if a["role"] == b["role"])
check("no two model turns ever land back to back", _pairs == 0, _chat)
check("...and the history starts with him, as a continuation must",
      _chat and _chat[0]["role"] == "user", _chat)
check("...and nothing she said is thrown away — the run is MERGED",
      all(s in "".join(m["content"] for m in _chat)
          for s in ("hello", "and another, unprompted", "and a third")), _chat)
check("a leading run of hers is dropped, not left dangling",
      "she spoke first" not in "".join(m["content"] for m in _chat), _chat)
check("an empty turn never becomes a blank message",
      not any(not m["content"].strip() for m in
              A._chat_from_rows(_rows + [{"role": "user", "content": "   "}], keep=8)))

print("\n10. HER ACTS SURVIVE THE REFRESH (2026-08-30: 'chips still vanish — only "
      "◆warm ❧soft show')")
# Marks come out of her TEXT and were already filed as row metadata (his F5 report,
# 2026-08-25). The acts row — tools, wear, recall, what she looked at — arrives as SSE
# events and died with the stream, so the room's restore drew a bare turn. The turn's
# collector hands them to the writer; /v1/day passes rows through whole; the room maps
# r.acts back into the same acts row a live turn renders.
_acts_in = [{"tool": {"name": "read_journal", "result": "three entries"}},
            {"wear": {"label": "the black lace set"}},
            {"recall": ["My cat's name is Tuffy."]}]
A._append_day_turn("what do you remember?", "Tuffy, of course. [MOOD:warm]",
                   acts=_acts_in)
_arow = next((r for r in reversed(A._read_day_transcript())
              if r.get("role") == "assistant"), {})
check("the acts land on her row, beside the marks",
      _arow.get("acts") == _acts_in, _arow.get("acts"))
check("...and the marks are still filed too (the two lanes are siblings)",
      any(m.get("kind") == "mood" for m in _arow.get("marks", [])), _arow.get("marks"))
check("a turn with no acts writes no acts key (readers ignore what is absent)",
      "acts" not in next((r for r in A._read_day_transcript()
                          if r.get("role") == "assistant"), {}))
# the writer caps the count so a runaway tool loop cannot bloat the record
A._append_day_turn("again?", "again. ", acts=[{"tool": {"name": "t%d" % i}}
                                              for i in range(40)])
_arow2 = next((r for r in reversed(A._read_day_transcript())
               if r.get("role") == "assistant"), {})
check("...and a runaway act list is capped at the writer",
      len(_arow2.get("acts", [])) <= 12, len(_arow2.get("acts", [])))
# THE OTHER HALF LIVES IN THE ROOM: the mount maps r.acts into the events row.
_chat_src = io.open(os.path.join(ROOT, "ui", "src", "Chat.jsx"), encoding="utf-8").read()
check("the room's restore maps r.acts into the acts row it already renders",
      "r.acts" in _chat_src and "events:" in _chat_src, "ui/src/Chat.jsx lost the mapping")
check("...and the collector feeds the epilogue (acts=_acts at the settle)",
      "acts=_acts)" in src, "the SSE shell no longer hands its acts to _settle_turn")

shutil.rmtree(SB, ignore_errors=True)
# ── THE CONVERSATION DOES NOT END AT MIDNIGHT (2026-08-28) ───────────────────────────
# REPORTED FROM A LIVE INSTALL: a refresh cleared the rendered chat history. `_day_key` names
# the file from `time.localtime`, so at 00:00 today's file is empty — and their evenings run
# past one in the morning. Three things read it and went blank together: the room's log
# (reloaded from /v1/day on mount), `_seed_kairos_from_day`, and the continuation window.
#
# `_read_day_transcript` keeps its meaning, because the CONSOLIDATOR consolidates a day and
# that is the right unit for it. `_recent_transcript` is the other question — "what were we
# just saying" — and reaches back across the boundary only when today is thin.
import datetime as _dt   # noqa: E402
_today = A._day_key()
_yest = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
os.makedirs(os.path.dirname(A._day_transcript_path(_yest)), exist_ok=True)
with io.open(A._day_transcript_path(_yest), "w", encoding="utf-8") as f:
    for i in range(6):
        f.write(json.dumps({"role": "user", "content": "last night %d" % i}) + "\n")
        f.write(json.dumps({"role": "assistant", "content": "and hers %d" % i}) + "\n")
with io.open(A._day_transcript_path(_today), "w", encoding="utf-8") as f:
    pass                                   # midnight: today is empty
check("the day reader still means TODAY", A._read_day_transcript() == [])
_recent = A._recent_transcript()
check("...but the recent conversation crosses midnight", len(_recent) == 12, len(_recent))
check("...so a continuation has something to continue FROM",
      len(A._chat_from_rows(_recent, keep=8)) > 0)
with io.open(A._day_transcript_path(_today), "w", encoding="utf-8") as f:
    for i in range(20):
        f.write(json.dumps({"role": "user", "content": "today %d" % i}) + "\n")
_full = A._recent_transcript()
check("...and a normal day does NOT reach back, so nothing is shown twice",
      len(_full) == 20 and all("last night" not in (r.get("content") or "") for r in _full),
      len(_full))

print("\nG-DAY-TRANSCRIPT: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_day_transcript.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_day_transcript", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
