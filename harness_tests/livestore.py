"""Put back everything a gate touched. ONE implementation, because two would not agree.

NOT `_livestore.py`: .gitignore line 19 is `_*.py` (session scratch), so an
underscore-prefixed helper would never be committed and three gates would fail on a
fresh clone with an ImportError — a green suite here and a broken one for anybody else.

WHY THIS EXISTS, 2026-08-05. Several gates have to exercise the real wardrobe: the whole
value of G-WARDROBE-REACH is that it feeds her ACTUAL inventory its own labels back, and
G-EXPRESS calls `express()` for real because express is not a query — it genuinely sets
her mood and genuinely dresses her. Fixtures would grade a wardrobe nobody wears.

So they write to live stores, and each one grew its own save/restore covering whatever
its author happened to think of. G-EXPRESS restored `wardrobe.json`. It did NOT restore
`worn.jsonl` — because `choose()` logs the wearing, by design, at the one place every
caller passes through. Every run of the suite therefore wrote a handful of fabricated
"she put on the silver nightie" rows into her real history: the same log `favourites`
ranks over, and now the log the agency window reads back to him as her evening. Found by
opening that window and seeing my own test runs in her day.

AGENTS.md §0 in its purest form — an invariant enforced in one of two paths is enforced
in neither — so the answer is not to patch each gate but to have one thing that knows
what her stores are:

    with live_stores():
        ...anything at all...
    # every file above is byte-identical to how it was found

A file that did not exist before is REMOVED rather than left empty, because an empty
wants.jsonl and a missing one are different states and only one of them is what he had.
"""
from __future__ import annotations

import contextlib
import io
import os


def paths():
    """Every file a gate can plausibly dirty by touching her, resolved live.

    Resolved through the modules' own accessors rather than composed here — `root()` reads
    SP_AVATAR_DIR, and a second copy of that path arithmetic is how a gate ends up
    faithfully restoring a directory nobody is using."""
    out = []
    try:
        from harness.control import wardrobe as WD
        d = os.path.dirname(WD._state_path())
        out += [WD._state_path(), WD._wants_path(), os.path.join(d, "worn.jsonl")]
    except Exception:
        pass
    try:
        from harness.personality import interceptor as IC
        out.append(IC._persona_path())
    except Exception:
        pass
    return [p for p in out if p]


def _lock_path():
    """One lock beside her stores, so it moves with SP_AVATAR_DIR."""
    try:
        from harness.control import wardrobe as WD
        return os.path.join(os.path.dirname(WD._state_path()), ".gate-livestore.lock")
    except Exception:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".gate-livestore.lock")


@contextlib.contextmanager
def _exclusive(timeout=90.0):
    """ONE GATE AT A TIME INSIDE HER STORES (2026-08-25).

    Restoring byte-identically is only half of it, and the half that shows up alone. The
    other half showed up under tools/sweep.py, which runs gates in PARALLEL: while
    G-WARDROBE-QUEUE was inside the block with two fabricated wants written to the real
    wants.jsonl, G-WARDROBE-REACH read that same file and convicted them — 38 items, two
    unreachable, RED. Run on its own the same gate is green at 37. A gate that is red only
    when its neighbour is mid-write is worse than a gate that is always red: it teaches
    people that reds in the sweep are noise, which is how a real one gets ignored.

    A cross-process lock, because the sweep is processes and not threads. Held for the
    whole block, taken by readers too — a reader of a store somebody else is halfway
    through rewriting is exactly the failure. On timeout it PROCEEDS rather than raising:
    the worst case is the flake we already had, and a gate suite that deadlocks is a
    suite nobody runs."""
    import time
    p = _lock_path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
    except Exception:
        pass
    fd, deadline = None, time.time() + timeout
    while fd is None and time.time() < deadline:
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            # A crashed gate must not wedge the suite forever.
            try:
                if time.time() - os.path.getmtime(p) > timeout:
                    os.remove(p)
                    continue
            except OSError:
                pass
            time.sleep(0.05)
        except Exception:
            break
    try:
        yield
    finally:
        if fd is not None:
            try:
                os.close(fd)
                os.remove(p)
            except Exception:
                pass


@contextlib.contextmanager
def live_reader():
    """For a gate that only READS her live stores — G-WARDROBE-REACH's whole design.

    It takes the same lock and restores nothing, because it changes nothing. Without this
    the restore discipline protects the stores and leaves the READERS racing."""
    with _exclusive():
        yield


@contextlib.contextmanager
def live_stores(extra=()):
    """Snapshot her stores, run the block, put them back exactly — alone."""
    with _exclusive():
        yield from _live_stores_inner(extra)


def _live_stores_inner(extra=()):
    keep = {}
    for p in list(paths()) + list(extra):
        try:
            keep[p] = io.open(p, "rb").read() if os.path.exists(p) else None
        except Exception:
            keep[p] = None
    try:
        yield
    finally:
        for p, blob in keep.items():
            try:
                if blob is None:
                    # It did not exist. An empty file is a different state from an absent
                    # one, and only one of them is what he had.
                    if os.path.exists(p):
                        os.remove(p)
                else:
                    io.open(p, "wb").write(blob)
            except Exception:
                pass
