"""store_io.py — the atomic write, once, for stores a LIVE READER is holding open.

WHY THIS FILE EXISTS (2026-08-31, his report: "editing and saving also doesn't seem to
work, i just tried retiring two clothing and neither has retired").

`tmp + os.replace` is the pattern this repo uses everywhere and it is the right one: a
reader never sees half a file. On WINDOWS it has a second property nobody wrote down —
**the rename fails if any other handle has the destination open**, with
`PermissionError: [WinError 5] Access is denied`. Python's `open()` shares read and write
but not DELETE, and a rename over a file counts as a delete of the target.

MEASURED against her running gateway, twelve identical `POST /v1/catalog {op: edit}`:

    ok=7  bad=5      # [WinError 5] ... catalog.json.tmp -> catalog.json

Two of five of his panel edits were being thrown away — silently, because the route
catches the exception, answers 409/400, and the room showed nothing. The reader on the
other side was the gateway itself: `wardrobe.wants()` calls `overlay_for()` per row, which
re-opened and re-parsed `catalog.json` *per row* — about a hundred opens for one panel
poll, every four seconds, from several threads. The window was not a race so much as a
near-certainty.

The repo already knew the failure and had only ever answered it for GATES:
`harness/tuning/registry.py` line ~36 records `g_presence_modes` dying with the same
WinError 5 against her running stack, and the fix was to sandbox the gate. That leaves
the LIVE writers exposed, which is where it actually hurt.

So: one helper, retried, used by the writers a live reader can collide with. It is not a
lock — a lock across a process boundary would have to be taken by every reader too, and a
reader that must take a lock to read is how a panel poll ends up blocking her. A short
retry answers the real shape of the collision, which is momentary: the reader opens the
file, parses 2 KB and closes it.

    from harness.store_io import replace_atomic
    replace_atomic(tmp, path)

If it still cannot land after the full budget it RAISES, exactly as `os.replace` would.
A write that quietly gives up is the bug this was written to end.
"""
from __future__ import annotations

import os
import time

# ~3s of trying, front-loaded. Most collisions are one parse long (under a millisecond)
# and clear on the first or second attempt — measured in a controlled race, four reader
# threads on the pre-cache read pattern: 5 of 20 writes refused bare, 0 of 20 retried.
# The long tail is for the live directory, where his gateway's threads and whatever else
# Windows has opinions about the folder can hold it far longer than one parse. A write he
# CLICKED can afford three seconds; being told it did not save cannot be undone.
_WAITS = (0.002, 0.005, 0.01, 0.02, 0.04, 0.08, 0.12, 0.16, 0.25, 0.3, 0.3, 0.4,
          0.4, 0.5, 0.5)


def replace_atomic(tmp: str, dst: str, waits=_WAITS) -> None:
    """`os.replace(tmp, dst)`, retried while a reader holds `dst` open (Windows).

    Raises the last PermissionError if the whole budget is spent — the caller's error
    path is still the truth about whether the write landed.
    """
    for w in waits:
        try:
            os.replace(tmp, dst)
            return
        except PermissionError:
            time.sleep(w)
    os.replace(tmp, dst)          # the last attempt raises for the caller to handle
