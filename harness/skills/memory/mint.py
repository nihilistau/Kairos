"""mint.py — the KV capture queue: she answers first, the cache catches up.

One worker, one queue, one daemon thread, deliberately: the engine is a single GPU and the
whole point is to stop contending with the turn she is trying to answer. Four parallel
captures would move the stall from the harness into the engine rather than removing it.

`_mint_now` asks the daemon to mint an episode KV for a fact that was just written;
`_mint_later` hands it to the worker instead when `SP_CAPTURE_ASYNC` is on; `_mint_drain`
writes the result back into the registry — which is why this module reaches the store, and
reaches it as a MODULE (`_store._load`, `_store._save_all`, `_store._REG_LOCK`): see
`store.py`'s header for the read-modify-write race a by-name binding would hide.

`_MINT_WORKER` keeps its `global` rebind. It is the one lazily-started singleton here and the
rebind is the start-once contract; moving it did not change that, and `_MINT_LOCK` is what
makes it a contract rather than a hope.

Extracted from `memory.py` on 2026-09-01, byte-identical.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import urllib.error
import urllib.request

from harness.loud import swallowed as _sw
from harness.skills.memory import store as _store

_log = logging.getLogger("harness.memory")     # the same object; see store.py's note


# ── THE MINT QUEUE: SHE ANSWERS FIRST, THE CACHE CATCHES UP ────────────────────────────
# One worker, one queue, daemon thread. Deliberately ONE: the daemon is a single GPU and the whole
# point is to stop contending with the turn she is trying to answer. Four parallel captures would
# just move the stall from the harness into the engine.
_MINT_Q: "queue.Queue" = queue.Queue()
_MINT_WORKER = None
_MINT_LOCK = threading.Lock()


def _mint_is_async() -> bool:
    """Async unless explicitly told otherwise. SP_CAPTURE_ASYNC is mapped in serve.py (it has to
    be: build_env now strips every unmapped SP_*, so an unmapped knob is an unreachable one —
    G-ONEDOOR made that structural, and it is what forced this to be a real profile knob rather
    than a getenv nobody could find)."""
    return os.environ.get("SP_CAPTURE_ASYNC", "1") == "1"


# ── THE ENGINE MAY REFUSE, AND IT DID, SILENTLY, FOR WEEKS (2026-08-23) ────────────────
# MEASURED on the live store: 253 of the 253 rows written since 2026-08-19 carry npos=0 and
# no minted_at — not one KV episode. 641 of the 747 directories under var/memory/eps/ are
# EMPTY. Zero ep.l5 sidecars in three weeks. The cause, straight from the route:
#
#   gemma4_decode_cuda: gemma4-MoE not supported on this path — its three internal FFN
#   copies are not on the g4_ffn_apply seam (ADR-013); use the served decode
#
# /v1/capture cannot run on the model MoE and has not since the model landed. Her MEMORY is
# unaffected — the registry is the recall authority and never touches the daemon — but the
# engine-side episode representation is empty for everything recent, and so is the L5 half
# of the semantic index. That second consequence is the load-bearing one: EVERY embedding
# contender this repo measured and rejected was measured against a 93%-hash document index.
#
# It failed silently because the whole call sat under a bare `except: return 0, False`,
# which cannot tell "the daemon is down" from "the engine says never". Those need different
# answers, and now they get them:
#   transport failure   -> quiet, retried on the next fact, exactly as before.
#   a REFUSAL with a body -> logged ONCE with the engine's own words, and not asked again
#                            this process. Retrying a structural no, per fact, forever, is
#                            how 641 empty directories happen.
_CAPTURE_REFUSED = {"why": "", "at": 0.0, "n": 0}


def capture_status() -> dict:
    """Why the KV mint is not running, if it is not. Read by _registry_health so the number
    reaches a surface instead of sitting in a stat nobody prints."""
    return dict(_CAPTURE_REFUSED)


def eps_root() -> str:
    """Where episodes live. Beside the registry unless told otherwise.

    AN EPISODE IS BIG AND COLD: ep.k + ep.v at full depth per position, mean 11.1 MB
    over her real ones, written once and read only on a deep recall. That is exactly
    the shape you want OFF the working drive, and this box has a 32 GB Optane sitting
    idle (F:). MEASURED at that shape (tools/disk_bench.py, unbuffered): F: writes at
    0.30 GB/s and random-reads 2.84 MB blocks at 1.36 GB/s -- slower than D:, and far
    too slow to stream EXPERTS from, which is why that idea was measured and dropped.
    For an 11 MB write-once blob it is ample: ~37 ms to mint, ~8 ms to read back.

    The row carries its own absolute `dir`, so moving the root does not orphan
    anything already written -- old episodes stay where they are and are still found.
    """
    d = (os.environ.get("SP_EPS_DIR") or "").strip()
    if d:
        return d.replace("\\", "/").rstrip("/")
    return os.path.join(os.path.dirname(_store._reg_path()), "eps").replace("\\", "/")


def _mint_now(daemon: str, fact: str, out_dir: str):
    """The blocking capture. Still used when async is off (gates that want determinism) and by the
    background worker, which is the only place it belongs.

    NO ENGINE, NO MINT (2026-08-21): under a foreign backend there is no /v1/capture; the
    row still lands with npos=0 — recall is text/sem, no episode. Said once, not retried
    into a timeout per fact."""
    try:
        from harness.inference.backends import supports as _sup
        if not _sup("capture"):
            return 0, False
    except Exception as _swx:
        _sw(_log, "_mint_now", _swx, lane="skills")
    if _CAPTURE_REFUSED["why"]:
        _CAPTURE_REFUSED["n"] += 1        # counted, not retried: the engine already said no
        return 0, False
    # ── THE DISK FLOOR (2026-08-23, the day the mint came back). ──────────────────
    # An episode is not small: MEASURED over her 51 real ones, mean 11.1 MB and max
    # 79.1 MB (ep.k + ep.v are the full-depth K/V rows for every position). While
    # /v1/capture was refusing on the MoE this cost nothing, and the drive filled up
    # for other reasons — 930 of 932 GB, 2.57 GB free, about 231 episodes of headroom.
    # Turning the mint back on without a floor would quietly spend that in a week.
    #
    # A FULL DISK IS NOT A MEMORY PROBLEM, it is an everything problem: the gateway
    # log, the KV snapshot capture and the registry write all fail on it, and the
    # registry write is the one that would actually lose something of hers. So the
    # mint yields first. The row still lands with npos=0 — recall is text + semantic,
    # no episode — which is exactly the documented degradation for "no engine, no
    # mint", reached by a different road.
    #
    # Said ONCE through the same breaker as a structural refusal, because "the disk is
    # full" is also a standing no rather than a transient one; it clears on restart,
    # by which time somebody has either freed space or not.
    #
    # THE PROBE IS INSIDE THE try; THE REFUSAL IS NOT. First draft put the whole thing
    # in one try/except and called a `logger` this module does not have — the NameError
    # was swallowed by the except, execution fell through, and the mint ran anyway. A
    # guard whose failure mode is "no guard" is worse than no guard, because it reads
    # like protection. So: measure defensively, decide in the open.
    # ...AND THE PROBE MUST ASK A DIRECTORY THAT EXISTS. `out_dir` is the episode dir
    # and it has NOT been created yet at this point, so disk_usage() on it (or on its
    # parent, the first time) raises and the guard silently skips — measured: the floor
    # set to an impossible 9000 GB and the mint ran anyway, npos=12. Walk up to the
    # nearest ancestor that exists; the free space of any of them is the same volume.
    _free_gb = None
    try:
        import shutil
        _p = os.path.abspath(out_dir)
        for _ in range(6):
            if os.path.isdir(_p):
                break
            _up = os.path.dirname(_p)
            if _up == _p:
                break
            _p = _up
        _free_gb = shutil.disk_usage(_p if os.path.isdir(_p) else ".").free / 1e9
    except Exception as _swx:
        _sw(_log, "_mint_now", _swx, lane="skills")
        _free_gb = None                   # a broken probe must never block a memory
    if _free_gb is not None:
        try:
            _floor = float(os.environ.get("SP_CAPTURE_MIN_FREE_GB", "2") or 2)
        except ValueError:
            _floor = 2.0
        if _free_gb < _floor:
            why = ("disk floor: %.2f GB free, below the %.2f GB floor — the mint yields "
                   "so the registry write does not fail. Rows land with npos=0; recall is "
                   "text + semantic until there is room." % (_free_gb, _floor))
            _CAPTURE_REFUSED.update(why=why, at=time.time(), n=1)
            return 0, False
    try:
        body = json.dumps({"text": fact, "out_dir": out_dir}).encode()
        req = urllib.request.Request(
            daemon + "/v1/capture", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            j = json.loads(r.read().decode())
        npos = int(j.get("npos", 0))
        return npos, (bool(j.get("ok", False)) or npos > 0)
    except urllib.error.HTTPError as exc:
        # THE ENGINE ANSWERED, AND THE ANSWER WAS NO. Its body says why; say it once.
        why = ""
        try:
            why = str((json.loads(exc.read().decode()) or {}).get("error", ""))[:400]
        except Exception as _swx:
            _sw(_log, "_mint_now", _swx, lane="skills")
            why = "HTTP %s" % getattr(exc, "code", "?")
        if why and not _CAPTURE_REFUSED["why"]:
            _CAPTURE_REFUSED.update(why=why, at=time.time(), n=1)
            try:
                import logging
                logging.getLogger("harness.memory").warning(
                    "[memory] /v1/capture REFUSED by the engine; rows will carry npos=0 and "
                    "no ep.l5 until this is fixed. Not asked again this process. Engine said: %s",
                    why)
            except Exception as _swx:
                _sw(_log, "_mint_now", _swx, lane="skills")
        return 0, False
    except Exception as _swx:
        _sw(_log, "_mint_now", _swx, lane="skills")
        return 0, False                   # transport: quiet, and tried again next time


def _mint_drain():
    while True:
        item = _MINT_Q.get()
        try:
            if item is None:
                return
            fact, out_dir = item
            daemon = os.environ.get("SP_DAEMON_URL", "http://127.0.0.1:3000")
            npos, minted = _mint_now(daemon, fact, out_dir)
            if not minted:
                continue
            # Update the row IN PLACE, found by its out_dir — NOT by its text.
            #
            # By the time this lands, the turn is long over and the store has moved on. If we
            # matched on text, a reinforcement or a supersede could have changed which row that
            # text belongs to, and we would stamp npos onto the wrong memory. `dir` is unique per
            # capture and was written at the same instant as the row. It is the only key that
            # still means what it meant when we queued it.
            with _store._REG_LOCK:
                rows = _store._load()
                hit = next((r for r in rows if r.get("dir") == out_dir), None)
                if hit is not None:
                    hit["npos"] = npos
                    hit["minted_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    _store._save_all(rows)
            # SEM S0: if the engine wrote an ep.l5 sidecar into this episode dir, append
            # the l5-space index row (an UPGRADE is an APPEND — nothing is edited).
            # /v1/capture mints ep.l5 when SP_CAPTURE_L5=1. upgrade() no-ops when the
            # sidecar is absent. Never raises.
            if hit is not None:
                from harness.skills import semindex as _sem
                _sem.upgrade(out_dir, fact, hit.get("ts", ""))
        except Exception as _swx:
            _sw(_log, "_mint_drain", _swx, lane="skills")
        finally:
            _MINT_Q.task_done()


def _mint_later(fact: str, out_dir: str) -> None:
    global _MINT_WORKER
    with _MINT_LOCK:
        if _MINT_WORKER is None or not _MINT_WORKER.is_alive():
            _MINT_WORKER = threading.Thread(target=_mint_drain, name="sp-mint",
                                            daemon=True)
            _MINT_WORKER.start()
    _MINT_Q.put((fact, out_dir))


def mint_backlog() -> int:
    """How many episodes are still waiting to be minted. For the gate and the ops panel."""
    return _MINT_Q.qsize()


def mint_drain_blocking(timeout: float = 30.0) -> bool:
    """Wait for the queue to empty. Gates and shutdown only — never a turn."""
    t0 = time.time()
    while _MINT_Q.qsize() and time.time() - t0 < timeout:
        time.sleep(0.05)
    return _MINT_Q.qsize() == 0
