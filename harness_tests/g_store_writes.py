"""G-STORE-WRITES — every store this repo writes survives a reader holding it open. OFFLINE.

THE MORNING THIS EXISTS FOR (2026-08-31). His report was small and the cause was not:
"editing and saving also doesn't seem to work, i just tried retiring two clothing and
neither has retired." Neither had. Nothing reached `catalog.json` at all.

    ok=7  bad=5   [WinError 5] Access is denied: catalog.json.tmp -> catalog.json

`tmp + os.replace` is atomic and is the pattern this repo uses everywhere — and on
WINDOWS the rename FAILS while any other handle has the destination open. Python's
`open()` shares read and write but not DELETE, and renaming over a file is a delete of
the target. The reader was the gateway itself. The wardrobe re-opened and re-parsed the
whole overlay once PER ROW: 419 opens of one 2 KB file to answer a single panel poll,
four seconds apart, from several threads. Probed every 20 ms for twelve seconds:

    catalog.json           ok=  1  denied=189      # 85% of the time un-replaceable
    _probe_untouched.json  ok=189  denied=  0      # same folder, nothing reads it

So not a race his click lost occasionally: a file that was almost never writable.

AND THE REPO ALREADY KNEW. `harness/tuning/registry.py` carries a note from 2026-08-24
about `g_presence_modes` dying with this exact WinError 5 against her running stack — and
the answer then was to sandbox the GATE. That fixed the test and left every LIVE writer
exposed, which is where it actually cost him something. AGENTS.md §0: an invariant
enforced on the gate and not on the code is enforced nowhere.

WHAT THIS HOLDS:
  1. The helper exists, retries with a real budget, and RAISES when the budget is spent.
     A write that quietly gives up is the bug, not the fix.
  2. THE CENSUS: no `os.replace` survives anywhere under `harness/` except inside the
     helper itself. This is the leg that catches the NEXT store writer on the day it is
     added, rather than the next time somebody's edit vanishes.
  3. It actually lands under a reader, driven with real threads — because a gate that
     mocks the collision grades the mock.

    python harness_tests/g_store_writes.py
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, sandbox as _sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
_SB = _sandbox(os.path.basename(__file__))

from harness.store_io import replace_atomic, _WAITS  # noqa: E402

print("1. THE HELPER IS A RETRY WITH A BUDGET, AND IT STILL RAISES")
_src = io.open(os.path.join(ROOT, "harness", "store_io.py"),
               encoding="utf-8", errors="replace").read()
check("it retries rather than failing on the first refusal", len(_WAITS) >= 5, len(_WAITS))
check("...with a budget measured in seconds, not milliseconds",
      sum(_WAITS) >= 1.0, "%.2fs" % sum(_WAITS))
# THE LAST ATTEMPT IS OUTSIDE THE LOOP ON PURPOSE: a helper that swallowed the final
# PermissionError would turn "your edit did not save" into "your edit saved", which is
# strictly worse than the bug it replaces.
def _tail_of(fn_name, end_marker, src=_src):
    """The body of one helper, comments stripped — SLICED BY NAME, because the file has
    two retry loops now and `rsplit("for w in waits:")` silently graded the other one."""
    blk = src[src.index("def %s(" % fn_name):]
    blk = blk[:blk.index(end_marker)] if end_marker in blk else blk
    lines = [l.split("#")[0].rstrip() for l in blk.rsplit("for w in waits:", 1)[-1].splitlines()]
    return blk, [l for l in lines if l.strip()]


_blk, _tail_code = _tail_of("replace_atomic", "def read_bytes_retry")
check("the last attempt is unguarded, so a spent budget RAISES",
      "except PermissionError:" in _blk
      and _tail_code[-1].strip() == "os.replace(tmp, dst)",
      _tail_code[-1:])
# THE READ HELPER, same rule and for a sharper reason: a read that gives up quietly
# answers "empty", and empty is what a read-modify-write writes back.
_rblk, _rtail = _tail_of("read_bytes_retry", "\n\ndef ")
check("the read helper raises too — an unreadable store is never answered as empty",
      "return None" in _rblk and _rtail[-1].strip() == "return f.read()", _rtail[-2:])

print("\n2. THE CENSUS — every store writer under harness/ goes through it")
# CODE ONLY. Half a dozen of these files have a COMMENT that names os.replace to explain
# the pattern (or, now, to explain why it is not called directly), and a gate that cannot
# tell a call from a sentence about a call goes red on its own documentation.
_offenders = []
for here, dirs, files in os.walk(os.path.join(ROOT, "harness")):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for fn in files:
        if not fn.endswith(".py") or fn == "store_io.py":
            continue
        p = os.path.join(here, fn)
        body = io.open(p, encoding="utf-8", errors="replace").read()
        code = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith("#"))
        if re.search(r"\bos\.replace\s*\(", code):
            _offenders.append(os.path.relpath(p, ROOT).replace("\\", "/"))
check("no store writer renames with a bare os.replace", not _offenders, _offenders)
# ...and the census is not vacuous: it has to be looking at the files that DO write.
_users = 0
for here, dirs, files in os.walk(os.path.join(ROOT, "harness")):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for fn in files:
        if fn.endswith(".py") and fn != "store_io.py":
            if "replace_atomic(" in io.open(os.path.join(here, fn), encoding="utf-8",
                                            errors="replace").read():
                _users += 1
check("...and the helper is actually the one being used (>= 10 files)",
      _users >= 10, "%d files call replace_atomic" % _users)

print("\n3. AND IT LANDS WHILE SOMETHING IS READING")
# Shaped like a poller: bursts of reads with the file CLOSED in between. A reader with no
# gap at all cannot be beaten by any retry — that reader is what a cached read removes
# (wardrobe.overlay), and it is the half that actually fixed his room. This leg is about
# the write.
_p = os.path.join(_SB, "store-probe.json")
io.open(_p, "w", encoding="utf-8").write('{"n": 0}')
_stop = threading.Event()


def _poller():
    while not _stop.is_set():
        for _ in range(5):
            try:
                with io.open(_p, encoding="utf-8") as f:
                    json.load(f)
            except Exception:
                pass
        time.sleep(0.002)


_threads = [threading.Thread(target=_poller, daemon=True) for _ in range(3)]
for _t in _threads:
    _t.start()
_landed = 0
for _i in range(10):
    _tmp = _p + ".tmp"
    with io.open(_tmp, "w", encoding="utf-8") as f:
        json.dump({"n": _i}, f)
    try:
        replace_atomic(_tmp, _p)
        _landed += 1
    except PermissionError:
        pass
_stop.set()
for _t in _threads:
    _t.join(timeout=5)
check("ten writes, ten landed, with three pollers reading throughout",
      _landed == 10, "%d of 10" % _landed)
check("...and the last one is what is on disk",
      json.load(io.open(_p, encoding="utf-8")).get("n") == 9,
      json.load(io.open(_p, encoding="utf-8")))

print("\n4. A REWRITE NEVER TRUNCATES THE LIVE FILE")
# THE OTHER HALF OF THE SAME LESSON (2026-08-31, his call: "do those two as well").
# `replace_atomic` protects a rename; it does nothing for a writer that opens the REAL
# path with "w". Two did. `wardrobe._write_wants` is the rewrite every want, fulfil,
# dismiss and hide passes through — the file sat at zero bytes for a moment on each one,
# and `wants()` swallows a bad read and answers `[]`, which is indistinguishable from a
# woman who owns nothing. `tuning.reset()` truncated her live knobs the same way while
# `set_many()` thirty lines above it had been atomic since it was written: one file, two
# writers, the invariant held on one of them (§0).
#
# Asserted the only way that means anything: read the file from other threads WHILE it is
# rewritten, and demand that no reader ever saw fewer rows than were put there.
from harness.control import wardrobe as WD  # noqa: E402

_rows = [{"id": "w%03d" % i, "want": "a probe garment %d" % i, "kind": "look"}
         for i in range(1, 41)]
WD._write_wants(_rows)
_seen_short, _reads = [], [0]
_stop2 = threading.Event()


def _reader():
    # A POLLER, like §3 and like the gateway: it opens, parses, CLOSES, and comes back.
    # A reader that never lets go is not a reader this repo has, and no rename can beat
    # one — the honest note about that lives in harness/store_io.py rather than in an
    # assertion nothing could ever pass.
    while not _stop2.is_set():
        n = len(WD._wants_raw())
        _reads[0] += 1
        if n != len(_rows):
            _seen_short.append(n)
        time.sleep(0.001)


_rt = [threading.Thread(target=_reader, daemon=True) for _ in range(3)]
for _t in _rt:
    _t.start()
for _ in range(40):
    WD._write_wants(_rows)
_stop2.set()
for _t in _rt:
    _t.join(timeout=5)
check("forty rewrites, and no reader ever saw a torn want list",
      not _seen_short, "short reads: %s of %d" % (sorted(set(_seen_short))[:6], _reads[0]))
check("...and the readers were actually looking (>= 100 reads)",
      _reads[0] >= 100, _reads[0])
# STRUCTURAL, for the pair by name — the behavioural leg above can only fail on a machine
# where the threads happen to interleave, and "no reader saw it torn" is also what a gate
# that never scheduled a reader would report.
for _rel, _fn, _end in (("harness/control/wardrobe.py", "def _write_wants(", "def character("),
                        ("harness/tuning/registry.py", "def reset(", "def schema(")):
    _b = io.open(os.path.join(ROOT, _rel), encoding="utf-8", errors="replace").read()
    _blk = _b[_b.index(_fn):_b.index(_end)]
    _blk_code = "\n".join(l for l in _blk.splitlines() if not l.lstrip().startswith("#"))
    check("%-34s writes a tmp and renames it" % _rel.split("/")[-1],
          "replace_atomic(" in _blk_code and '.tmp' in _blk_code,
          [l.strip() for l in _blk_code.splitlines() if "open(" in l])

print("\n5. NO WRITE FAILS IN SILENCE, ANYWHERE UNDER harness/")
# ── THE AUDIT THIS GENERALISES (2026-08-31, his call: "do the same audit on the rest of
# the harness"). The wardrobe's three worst bugs this week were all one shape: a write
# inside a broad handler that answered with a bare default, so a write that FAILED and a
# write that WORKED were the same event to everyone downstream. The tree-wide count was
# 192 such handlers over 67 files; classified by what the try-block actually does, nine
# of them wrote. Eight are fixed (each says what was lost); one is listed below with its
# reason.
#
# THIS LEG IS ABOUT WRITES ONLY, on purpose. Most of the other 183 are a read degrading
# to a default, which is often exactly right — and demanding a log line at all 183 would
# be 183 edits of noise, which is how a real signal gets ignored (the same argument
# G-GATE-SANDBOX makes for not demanding sandbox() from all 136 gates). A swallowed
# WRITE is different: nothing downstream can tell, and the thing that was lost is gone.
_ALLOWED_WRITE_SWALLOWS = {
    # path:line -> why it is allowed to be silent
    "harness/server/app.py": "the error goodbye written to an SSE socket whose client has "
                             "already gone; the finally-block settle matters more, and "
                             "there is no store and nothing lost",
}
_BARE = re.compile(r"^(pass|return (\{\}|\[\]|\"\"|''|None|0|False|True|-1))\b")
_BROAD = re.compile(r"^(\s*)except\s+(Exception|BaseException)?(\s+as\s+\w+)?\s*:\s*$")
_WRITES = re.compile(r"""(\bopen\([^)]*['\"][wa]b?['\"]|replace_atomic\(|os\.replace\(|
                          json\.dump\(|\.write\(|os\.remove\(|shutil\.(copy|move|rmtree)|
                          _write_|set_overlay\()""", re.X)

_offenders, _scanned = [], 0
for _here, _dirs, _files in os.walk(os.path.join(ROOT, "harness")):
    _dirs[:] = [d for d in _dirs if d != "__pycache__"]
    for _fn in sorted(_files):
        if not _fn.endswith(".py"):
            continue
        _scanned += 1
        _fp = os.path.join(_here, _fn)
        _rel = os.path.relpath(_fp, ROOT).replace("\\", "/")
        _body = io.open(_fp, encoding="utf-8", errors="replace").read().splitlines()
        for _i, _ln in enumerate(_body):
            _m = _BROAD.match(_ln)
            if not _m:
                continue
            _nxt = _body[_i + 1].strip() if _i + 1 < len(_body) else ""
            if not _BARE.match(_nxt):
                continue
            # the try: that owns this handler, at the same indent
            _ind, _j, _t = len(_m.group(1)), _i - 1, None
            while _j >= 0 and _j > _i - 60:
                if _body[_j].strip() == "try:" and len(_body[_j]) - len(_body[_j].lstrip()) == _ind:
                    _t = _j
                    break
                _j -= 1
            _blk = "\n".join(_body[(_t if _t is not None else _i - 6) + 1:_i])
            if _WRITES.search(_blk) and _rel not in _ALLOWED_WRITE_SWALLOWS:
                _offenders.append("%s:%d" % (_rel, _i + 1))

check("the scan actually walked the tree (>= 100 files)", _scanned >= 100, _scanned)
check("no swallowed handler hides a WRITE", not _offenders, _offenders)
# ...and the allow-list is not a place to park a real one: every entry must exist and
# must carry a reason, or it is an exemption nobody agreed to.
for _rel, _why in _ALLOWED_WRITE_SWALLOWS.items():
    check("%-28s is exempt WITH a written reason" % _rel.split("/")[-1],
          os.path.exists(os.path.join(ROOT, _rel)) and len(_why) > 40, _why[:40])

finish("G-STORE-WRITES")
