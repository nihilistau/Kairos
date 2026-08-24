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
src = io.open(os.path.join(ROOT, "harness", "server", "app.py"), encoding="utf-8").read()
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

print("\n5. HIS WORDS, not the message list he never sent")
# `user_text` is bound at the top of the turn, before the recall note, the silence
# note and the roleplay director note mutate msgs. Proven positionally: every
# injection site must come AFTER the binding, or the argument is already poisoned.
# AMENDED AGAIN 2026-08-24 (audit B1): the day write moved into the turn epilogue —
# _pay_turn_debts hands _settle_turn `_human`, the words _arm_turn bound at the TOP of
# the turn, and _settle_turn is the one caller of _append_day_turn on this path. The
# claim is unchanged: the turn is written from HIS words, bound before the recall,
# silence and anon notes are stapled onto the message list.
bind = src.index("_human = _arm_turn(msgs)")
call = src.find("_settle_turn(_human, final_text")
# find(), not index(): a call site that stopped passing his words must read as a FAIL
# with a name on it, not as a traceback halfway down the gate.
check("the turn is written from his words", call > 0,
      "the epilogue no longer settles with _human")
check("...bound before anything is stapled onto the message list", 0 < bind < call)
check("...and the epilogue's day write passes them through verbatim",
      "_append_day_turn(human_text, reply_text, synthetic=synthetic)" in src)
for marker, what in (("Things you happen to know", "the recall note"),
                     ("note_for_question(user_text)", "the silence note")):
    at = src.index(marker)
    check("%s is stapled onto msgs AFTER his words were taken" % what, at > bind)
check("the helper takes a string, so a mutated msgs cannot reach it",
      "def _append_day_turn(user_text: str, final: str," in src)

print("\n6. a day that FAILED is not stamped done")
check("the marker is conditional now",
      "if _errored:" in src and 'out["retry"] = True' in src, "unconditional mark")
check("...and 'no conversation' is still allowed to finish the day",
      'len(_longest_transcript()) >= 4' in src)

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

shutil.rmtree(SB, ignore_errors=True)
print("\nG-DAY-TRANSCRIPT: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_day_transcript.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_day_transcript", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
