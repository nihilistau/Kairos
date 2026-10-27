"""G-LAUNCH-REPLY-STAMP — every reply of hers carries the setup and fingerprint. OFFLINE.

`_append_day_turn` (harness/server/day.py) is the single writer of the day transcript. Her
row gains `setup` (the launched setup's name) and `cfg` (8 hex), taken when the row is
written; his row does not. The room draws them as a small chip, so a reply says which
configuration produced it.

  (a) her row has the launched setup and an 8-hex cfg; his row has neither.
  (b) an unprompted (`own=`) row is stamped too.
  (c) `current_stamp` raising never loses the row: it is written, unstamped.
  (d) GET /v1/launch/status carries `setup` and `cfg` for the room's live messages.

    python harness_tests/g_launch_reply_stamp.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
sandbox("g_launch_reply_stamp")

VAR = tempfile.mkdtemp(prefix="g_launch_reply_stamp_var_")
os.environ["SP_LAUNCH_VAR"] = VAR

from harness.launch import stamp  # noqa: E402
from harness.server import day, launch_routes  # noqa: E402

SETUP = "old weights, kernels off"
stamp.write_launched({"_profile_name": "fx", "decode": {"attn_split": 0}},
                     {"SP_X": "1"}, SETUP)


def rows():
    with open(day._day_transcript_path(), encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def is_hex8(s):
    return isinstance(s, str) and len(s) == 8 and all(c in "0123456789abcdef" for c in s)


day._append_day_turn("hi", "hello")
r = rows()
check("(a) two rows written", len(r) == 2, r)
user, her = r[0], r[1]
check("(a) her row carries the launched setup", her.get("setup") == SETUP, her)
check("(a) her row carries an 8-hex cfg", is_hex8(her.get("cfg")), her)
check("(a) his row carries neither", "setup" not in user and "cfg" not in user, user)

day._append_day_turn("", "a thought of my own",
                     own={"oid": "o1", "kind": "muse", "why": "quiet"})
own = rows()[-1]
check("(b) an unprompted row is stamped", own.get("setup") == SETUP
      and is_hex8(own.get("cfg")) and own.get("unprompted") is True, own)

_real = stamp.current_stamp


def boom():
    raise RuntimeError("stamp store unreadable")


stamp.current_stamp = boom
try:
    day._append_day_turn("again", "still here")
finally:
    stamp.current_stamp = _real
tail = rows()[-2:]
check("(c) a failing stamp still writes both rows",
      [x["role"] for x in tail] == ["user", "assistant"]
      and tail[1]["content"] == "still here", tail)
check("(c) the row is written unstamped", "setup" not in tail[1] and "cfg" not in tail[1],
      tail[1])

code, res = launch_routes.get_status()
check("(d) /v1/launch/status carries setup", code == 200 and res.get("setup") == SETUP, res)
check("(d) /v1/launch/status carries cfg", is_hex8(res.get("cfg")), res)

finish("G-LAUNCH-REPLY-STAMP")
