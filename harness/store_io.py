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

import logging
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


# ── AND THE READ SIDE, WHICH IS THE HALF THAT CAN DESTROY SOMETHING (2026-08-31) ──────
# Making the writers atomic moved the failure rather than removing it. MEASURED: with
# `_write_wants` doing tmp+rename and three pollers reading, readers still saw an EMPTY
# want list — because `open()` on the destination can be refused for the instant the
# rename lands, and `_wants_raw` caught the exception and answered `[]`.
#
# An empty answer to "what does she own" is not a small error here. Every writer in
# wardrobe.py is read-modify-write over that same reader: a transient `[]` read followed
# by a write does not lose the moment, it TRUNCATES THE FILE. That is the shape that
# already killed ten of her rows once by a different route (wardrobe.py::_wants_raw).
#
# So a store read distinguishes the two things a bare `except` flattens:
#   absent  -> None, immediately. An empty store is a real state.
#   present but unreadable right now -> retried, then RAISED. Never silently empty.
def read_bytes_retry(path: str, waits=_WAITS):
    """The bytes of a store, or None if it genuinely is not there.

    Raises if the file exists and could not be read within the budget — because the
    caller writing back what it thinks it read is the failure this exists to prevent.
    """
    for w in waits:
        try:
            with open(path, "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None           # os.replace is atomic: the destination never blinks out
        except OSError:
            time.sleep(w)
    with open(path, "rb") as f:   # the last attempt raises for the caller to handle
        return f.read()


# ── A STRANDED .tmp IS EVIDENCE, NOT LITTER ───────────────────────────────────────────
# (2026-08-24 audit H4, rehomed here 2026-09-01.) `tmp + replace` means a crash between
# the write and the rename leaves `<store>.tmp` on disk — a COMPLETE candidate store that
# never became the store. The next writer opens that same path "w" and silently overwrites
# it: the only record of what the dying process was about to commit, gone, from stores
# whose doctrine is that nothing is destroyed.
#
# IT LIVES HERE NOW, and that is the whole point of moving it. It was in
# `harness/skills/memory.py`, and `harness/skills/notes.py::_write_all` imported it back
# out — its comment saying "ONE implementation, both tmp+replace writers, or the doctrine
# holds in one of two lanes and thus neither". Correct instinct, wrong address: this is not
# a memory concern, it is a **tmp+replace** concern, and `replace_atomic` is right here.
# Two writers reaching into a third module for a store-io primitive was the coupling; the
# module that owns the pattern owns the guard.
#
# Once per path per process (`_RESCUED`): a crash kills the process, so the next stranding
# can only be met by a fresh one. Never deleted, never auto-restored — restoring would
# resurrect a rewrite whose context is unknowable. The operator can diff it at leisure.
_RESCUED: set = set()


def rescue_stray_tmp(path: str) -> str:
    """Quarantine a stranded `path + '.tmp'` (crash leftover). Returns the quarantine
    filename, or '' when there was nothing to rescue. Logged, never silent."""
    if not path or path in _RESCUED:
        return ""
    _RESCUED.add(path)
    tmp = path + ".tmp"
    log = logging.getLogger(__name__)
    try:
        if not os.path.exists(tmp):
            return ""
        dest = "%s.stranded-%s" % (tmp, time.strftime("%Y%m%d-%H%M%S", time.gmtime()))
        replace_atomic(tmp, dest)
        log.warning("[store-io] stranded %s found beside its store (a crash between the "
                    "tmp write and the rename) — quarantined to %s. Nothing deleted, "
                    "nothing auto-restored; diff it against %s if you want to know what "
                    "was lost.", tmp, dest, path)
        return dest
    except Exception as exc:
        # "LOGGED, NEVER SILENT" IS THIS FUNCTION'S OWN DOCSTRING. A broken rescue must
        # never block a write — which is why `""` is still the answer — but what failed is
        # the quarantine of the one record of what a dying process was about to commit,
        # and the very next write opens that path "w".
        log.warning("[store-io] could NOT quarantine the stranded %s.tmp (%s: %s) — the "
                    "next write to this store will overwrite it", path,
                    type(exc).__name__, exc)
        try:
            from harness.loud import swallowed as _sw
            _sw(log, "rescue_stray_tmp", exc, lane="store-io")
        except Exception as _swx:
            log.debug("loud unavailable: %s", _swx)
        return ""
