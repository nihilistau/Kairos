"""G-ONE-TRANSCRIPT — every path that talks to the daemon reads the SAME history. OFFLINE.

THE BUG CLASS, third instance in one night (AGENTS.md §0): an invariant enforced in one of
two paths is enforced in neither, because the unguarded path is the one that runs.

THE RULE. `_session_transcript(body)` is the canonical conversation — the one the daemon
actually saw, carrying the per-turn recall note and every tool round. Its own comment says
of the alternative, `body["messages"]`, that the client "echoed its own history back, which
NEVER matches what the daemon actually saw — so the turn AFTER any recall/tool turn diverged
from the persist-KV committed cache and paid a full preamble re-prefill".

THE INSTANCE. `_continue()` — the kairos follow-on that fires when her reply was cut off —
read `body["messages"]`. It therefore sent the daemon a prompt diverging from the committed
KV in the MIDDLE, committed that shape, and left the next ordinary turn diverging from it.

    PREFIX-MATCH: lcp 6402 of 6994 committed (drop 592)      <- a continuation interleaved
    PREFIX-MATCH: lcp 7522 of 7717 committed (drop 195)      <- steady state, nothing between

drop 592 puts lcp back at the preamble: the whole conversation re-prefills. And it is not
gated by `kairos.checkin_chance` — setting that to 0 does NOT stop it, which is how it
survived the first round of looking.

WHY A GATE AND NOT JUST A FIX. Because this is the THIRD time. The recall note learned it
(app.py:2031), `_chat_from_rows` learned it (consecutive assistant rows), `_continue` had
the reasoning written in its own docstring — "the next prefill would diverge from the
persist cache" — while reading the wrong list two lines below the sentence. Getting the
comment right is not the same as getting the code right, and only a gate knows the
difference.

WHAT THIS ASSERTS is structural and cheap: no daemon-facing generation path may build its
history from `body["messages"]`. That is a grep, and a grep is exactly the right shape here
— the failure is always "someone reached for the obvious list", never a subtle logic error.

Offline. Reads the source, runs nothing.

Run: python harness_tests/g_one_transcript.py
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


APP = os.path.join(ROOT, "harness", "server", "app.py")
src = open(APP, encoding="utf-8", errors="replace").read()
lines = src.splitlines()

print("1. THE CONTINUATION READS CANON, NOT THE CLIENT'S ECHO")
# Locate _continue by its definition rather than a line number: line numbers in this file
# move every day and a gate that drifts off its subject passes for the wrong reason.
blks = []
for m in re.finditer(r"def _continue\(", src):
    # The CALL, not the import — both functions import `_arm_self_repeat_ban` on their
    # first line, so searching for the bare name cut the block to two lines and every
    # assertion below it read an empty string. A gate whose subject is empty reports
    # whatever the assertion's default is, which here was three false failures.
    end = src.find("_arm_self_repeat_ban(", m.start())
    blks.append(src[m.start():end if end > 0 else m.start() + 2000])
check("BOTH continuation paths exist and are both checked (console + OpenAI)",
      len(blks) == 2, "found %d _continue definitions, expected 2" % len(blks))
blk = "\n".join(blks)
# AMENDED 2026-08-24: the real call is `_session_transcript(body, append=False)`; the
# bare-`(body)` spelling this used to look for existed only in a COMMENT inside the old
# closure, so the check was matching the description, not the code — the exact failure
# the "COMMENTS ARE NOT CODE" note below already names, on the affirmative side.
check("_continue builds its history from _session_transcript",
      "_session_transcript(body, append=False)" in blk,
      "it must see the same conversation the turn it continues saw")
# COMMENTS ARE NOT CODE. The first cut flagged its own explanation of the bug. A gate that
# cannot tell a fix from a description of the bug gets silenced by whoever documents it.
code = "\n".join(l for l in blk.splitlines() if not l.lstrip().startswith("#"))
check("...and NOT from body['messages']",
      'body.get("messages"' not in code and "body['messages']" not in code,
      "the client echo never matches the committed cache")
check("...copied AND read-only, so the nudge does not persist into canon",
      "list(_session_transcript(body, append=False))" in blk,
      "aliasing canon would leave a system aside in the transcript forever; and the "
      "append=False matters too — calling the mutating accessor a second time mid-turn "
      "appended the SAME user row again (two user turns in a row, the malformed-"
      "template bug by another door)")
# THE DUPLICATE-ASSISTANT TRAP. agent_chat_stream ran with mutate_messages=True on the turn
# being continued, so canon ALREADY ends with her reply. Appending it again renders two
# model turns in a row, which Gemma's strictly-alternating template turns into a malformed
# prompt — the same defect _chat_from_rows exists to prevent, arriving by another door.
check("...and her reply is not appended twice",
      'hist[-1].get("role") != "assistant"' in blk,
      "canon already ends with the reply that triggered this continuation")

print("\n2. NO OTHER GENERATION PATH REBUILDS ITS OWN HISTORY")
# Every remaining use of body["messages"] must be a READ for routing/inspection, not the
# list handed to a generator. The two legitimate shapes are `_session_transcript` (which
# seeds from it, by design) and a non-generating read.
bad = []
for n, ln in enumerate(lines, 1):
    if ln.lstrip().startswith("#") or ln.lstrip().startswith("*"):
        continue                      # a comment naming the bug is not the bug
    if re.search(r"""body(\.get\(["']messages|\[["']messages)""", ln):
        ctx = "\n".join(lines[max(0, n - 12):n + 12])
        if "_session_transcript" in ctx and "def _session_transcript" in ctx:
            continue                      # the one place that is SUPPOSED to read it
        if "agent_chat_stream" in ctx or "chat_stream" in ctx:
            bad.append((n, ln.strip()[:72]))
check("no generation path sources its history from body['messages']",
      not bad, bad)

print("\n3. THE SPEAK-UP PREFERS THE LIVE CANON TOO")
# The last caller found sending its own shape. `_generate` rebuilt an EIGHT-ROW WINDOW
# from the day transcript on every impulse — not an extension of anything (it starts at
# row N-8) and missing the recall note and tool rounds besides. Caught by [DAEMON-CALL]
# attribution landing between two of his turns, while the rest of the turn was already
# fixed:
#     agent_chat_stream <- app.py:_generate <- scheduler.py:_fire | msgs=10
#     agent_chat_stream <- app.py:_run                            | msgs=7
# Two histories, one KV cache, his turn paying for hers.
#
# The disk path STAYS as the fallback and that is not a compromise: `_LAST` holds a
# closure, a closure does not survive a process, and the day transcript is the only thing
# that lets her speak first after a restart. Prefer canon; fall back exactly when there
# isn't one.
gi = src.index("def _generate(")
gblk = src[gi:src.index("_arm_self_repeat_ban(", gi)]
check("_generate prefers the live canonical session",
      "_longest_session()" in gblk,
      "a keep=8 window from disk is not an extension of the committed cache")
# AMENDED 2026-08-28: still the disk, but via `_recent_transcript`, which reaches back
# across local midnight when today is thin. The fallback was reading a file named from
# `time.localtime`, so at 00:00 it fell back to nothing at all — see G-DAY-TRANSCRIPT.
check("...and still falls back to disk when there is no live session",
      "_recent_transcript()" in gblk or "_read_day_transcript()" in gblk,
      "she must still be able to speak first after a restart")
check("_longest_session is NOT _longest_transcript",
      "def _longest_session(" in src and "def _longest_transcript(" in src,
      "one wants the fullest record of the day, the other the list the KV was built from")

print("\n4. AND THE CANONICAL LIST IS STILL THE ONE THE TURN USES")
# If this ever stops being true the rule above is vacuous — everything would be reading the
# client echo and agreeing with itself.
check("the chat path itself resolves through _session_transcript",
      "msgs = _session_transcript(body)" in src)
check("_session_transcript appends ONLY the new user turn",
      "canon.append(dict(new_user))" in src,
      "anything else stops the daemon seeing a strict extension")

print("\n5. WHAT THE ENGINE COMMITS BECOMES CANON — the unprompted turns too")
# 2026-08-20, measured on the operator's evening: the kairos closures sent canon+nudge,
# the engine committed canon+nudge+tool-rounds+reply, and the canon kept NONE of it —
# so every turn after every speak-up diverged mid-prompt, the rewind refused ("delta
# crosses a commit"), and the engine re-prefilled ~3,300-3,950 tokens from the boot
# snapshot at ~87 ms/tok: 5-6 MINUTES per turn, his and hers alike, eleven in a row in
# the daemon log. The closures now generate with mutate_messages=True and commit their
# whole delta back into the canonical list (_commit_unprompted; the seed closure holds
# its canon directly and does it inline). Three closures, one law — a committer on one
# of three paths is a committer on none of them.
check("the OpenAI continuation commits what it sent",
      src.count("_commit_unprompted(body, _base_len, hist") >= 1)
check("...and the console continuation does too",
      src.count("_commit_unprompted(body, _base_len, hist") >= 2)
check("...and the seed closure extends its own canon",
      "_canon.extend(h[_base_len:])" in src)
check("all three generate with mutate_messages=True (tool rounds are committed tokens)",
      src.count("mutate_messages=True,") >= 3)   # the three closures' call sites; the
                                                 # main SSE lane passes it via its kw dict
check("the race guard exists: his turn moving the canon wins",
      "len(canon) != base_len" in src and "len(_canon) == _base_len" in src)

print("\nG-ONE-TRANSCRIPT: %d pass, %d fail" % (PASS, FAIL))
import io  # noqa: E402
import json  # noqa: E402
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_one_transcript.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_one_transcript", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
