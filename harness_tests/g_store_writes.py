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
_tail = _src.rsplit("for w in waits:", 1)[-1]
_tail_code = [l.split("#")[0].rstrip() for l in _tail.splitlines()]
_tail_code = [l for l in _tail_code if l.strip()]
check("the last attempt is unguarded, so a spent budget RAISES",
      "except PermissionError:" in _tail
      and _tail_code[-1].strip() == "os.replace(tmp, dst)",
      _tail_code[-1:])

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

finish("G-STORE-WRITES")
