"""THE TEARDOWN LADDER — the one ordered place where this stack stops.

WHY THIS EXISTS. `serve.py --stop` is three `taskkill /F` calls: no atexit, no SIGTERM
handler, no KeyboardInterrupt path anywhere, and no HTTP route that could stop anything.
The operator's words: "currently due to the restart system there is no way to shutdown".

WHAT A KILL ACTUALLY COSTS, measured rather than assumed. `scheduler.py` calls
`_ON_SPOKE(text)` — the day-transcript writer — BEFORE it appends to `_OUTBOX`, so her
words are on disk the moment she says them. A kill loses a generation in flight and her
per-session turn state. It no longer loses DELIVERY (2026-08-20): flush() preserves the
unshown messages and `scheduler.reload_undelivered()` hands them back at the next
re-entry — gateway boot or resume() — while they are still warm (UNDELIVERED_SHELF_S;
past that they stay in the file as record). Until then the flush was write-only — the
loss it scoped away had merely been made tidy.

WHY THE GATEWAY OWNS IT. Every one of those lives in gateway memory. The process holding
the state has to be the one that flushes it, so the flush and the stop belong in one
ordered place rather than split across two processes.

NO HTTP AND NO ARGPARSE HERE. This is orchestration; the route is a caller. That is what
makes every rung testable without a socket.
"""
from __future__ import annotations

import io
import json
import logging
import os
import threading
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LOCK = threading.RLock()
_SHUTTING_DOWN = False
_LADDER_RUNNING = False

# Every mode, and the rung it stops at. A finite committed table rather than a chain of
# ifs, so "what does `her` do" is answerable by reading rather than by tracing.
MODES = ("her", "all", "kill")


def undelivered_path() -> str:
    return os.path.join(_ROOT, "var", "room", "undelivered.jsonl")


def is_shutting_down() -> bool:
    with _LOCK:
        return _SHUTTING_DOWN


def ladder_running() -> bool:
    """True while `shutdown()` is between its first and last rung.

    DISTINCT FROM is_shutting_down. After `mode=her` the shutting-down flag STAYS set —
    she is off, and it is what keeps new turns from starting against a dead daemon. This
    one is only true while the teardown is actually in progress, and it is what `/v1/start`
    must refuse on.

    FOUND BY DRIVING IT, 2026-08-06. `her` with a goodnight held the ladder for ~100 s at
    the goodnight rung while the room, which paints the down state the moment the request
    is ACCEPTED, was already offering `start her`. Pressing it launched a daemon that the
    still-running ladder then killed on its way past `stop_daemon` — leaving no daemon and
    a room saying "starting her" forever. No gate could have caught this: every rung was
    correct, and the hole was between the reply and the last rung.
    """
    with _LOCK:
        return _LADDER_RUNNING


def resume() -> bool:
    """Clear the shutting-down flag AND restart what quiesce() stopped.
    `/v1/start` calls this; nothing else should.

    The flag had no clearer at all, so a `her` shutdown latched the gateway into refusing
    turns for the rest of its life — she would come back on the daemon and be mute in the
    room, which is a worse failure than not starting.

    THE TICKER COMES BACK HERE TOO (2026-08-19). quiesce() stops it, and start_ticker()'s
    only other caller is boot — so after any `her` shutdown followed by the start button,
    she answered when spoken to and could NEVER SPEAK FIRST AGAIN for the life of the
    gateway process. resume undoes what quiesce did, both halves; start_ticker is
    idempotent, so a resume that never followed a quiesce costs nothing.
    """
    global _SHUTTING_DOWN
    with _LOCK:
        was, _SHUTTING_DOWN = _SHUTTING_DOWN, False
    if was:
        logger.info("[shutdown] resumed — turns are accepted again")
    try:
        from harness.kairos import scheduler as ks
        ks.start_ticker()
        # ...and what the shutdown before this flushed comes back to the queue that is
        # read (warm rows only; see reload_undelivered). resume() undoes what the
        # ladder did, ALL halves — the flag, the ticker, and the delivery it cost.
        ks.reload_undelivered()
    except Exception as exc:
        logger.warning("[shutdown] could not restart the ticker: %s", exc)
    return was


def _reset_for_test() -> None:
    """Gates drive this module repeatedly in one process. Not used in production."""
    global _SHUTTING_DOWN, _IN_FLIGHT, _LADDER_RUNNING
    with _LOCK:
        _SHUTTING_DOWN = False
        _IN_FLIGHT = 0
        _LADDER_RUNNING = False


def quiesce() -> bool:
    """Rung 1 — stop starting new work. Returns True only the first time.

    Idempotent because a shutdown can be requested twice (a double click, a retry) and the
    second must not undo or re-run the first.
    """
    global _SHUTTING_DOWN
    with _LOCK:
        if _SHUTTING_DOWN:
            return False
        _SHUTTING_DOWN = True
    try:
        from harness.kairos import scheduler as ks
        ks.stop_ticker()
        # The ticker is the BEAT; a Timer already armed is a generation already
        # scheduled. Both stop here, or "nothing new starts" holds for one of two
        # clocks. (_fire also re-checks the flag — belt for a timer armed mid-call.)
        ks.cancel_timers()
    except Exception as exc:
        logger.warning("[shutdown] could not stop the ticker: %s", exc)
    logger.info("[shutdown] quiesced — nothing new will start")
    return True


def flush() -> int:
    """Rung 4 — write what only exists in memory, and return how many rows.

    APPEND, NEVER TRUNCATE. Two shutdowns in one day must not erase the first one's
    record; the store's rule is that nothing is ever deleted.
    """
    rows = []
    try:
        from harness.kairos import scheduler as ks
        with ks._LOCK:
            for session, dq in list(ks._OUTBOX.items()):
                while dq:
                    rows.append({"session": session, "why": "undelivered", **dq.popleft()})
            insight = dict(ks._PENDING_INSIGHT or {})
            ks._PENDING_INSIGHT.clear()
        if insight:
            rows.append({"session": "", "why": "pending_insight", **insight})
    except Exception as exc:
        logger.warning("[shutdown] could not read the outbox: %s", exc)
    if not rows:
        return 0
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        p = undelivered_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with io.open(p, "a", encoding="utf-8", newline="") as f:
            for r in rows:
                r.setdefault("at", stamp)
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("[shutdown] could not write undelivered rows: %s", exc)
        return 0
    logger.info("[shutdown] flushed %d undelivered row(s)", len(rows))
    return len(rows)


_IN_FLIGHT = 0


def note_turn_start() -> None:
    """The gateway calls this as a generation begins. See finish_or_abandon."""
    global _IN_FLIGHT
    with _LOCK:
        _IN_FLIGHT += 1


def begin_turn() -> bool:
    """Refuse-or-count, atomically (2026-08-24 audit, B9). The caller used to do
    `if is_shutting_down(): refuse` then `note_turn_start()` — two lock acquisitions
    with a gap `quiesce()` can land in, so `finish_or_abandon` could sample
    _IN_FLIGHT == 0 before the increment and the ladder proceed to stop_daemon with a
    turn running. One lock, one answer: False = shutting down, refuse the turn;
    True = counted, the caller owes note_turn_end()."""
    global _IN_FLIGHT
    with _LOCK:
        if _SHUTTING_DOWN:
            return False
        _IN_FLIGHT += 1
        return True


def note_turn_end() -> None:
    global _IN_FLIGHT
    with _LOCK:
        _IN_FLIGHT = max(0, _IN_FLIGHT - 1)


def finish_or_abandon(timeout_s: float = 120.0) -> bool:
    """Rung 2 — let a generation already running finish. Bounded, always.

    A HUNG MODEL MUST NEVER BLOCK A SHUTDOWN. That is the whole reason for the cap: the
    daemon can wedge and still answer /v1/metrics, and a teardown that waits on it would
    be the one thing the operator cannot escape. On timeout the turn is abandoned, which
    costs a half-written reply — the same thing a kill costs, and only in the case where
    waiting has already failed.
    """
    deadline = time.time() + max(0.0, timeout_s)
    while time.time() < deadline:
        with _LOCK:
            if _IN_FLIGHT <= 0:
                return True
        time.sleep(0.1)
    with _LOCK:
        stuck = _IN_FLIGHT
    if stuck:
        logger.warning("[shutdown] abandoning %d turn(s) still in flight after %.0fs",
                       stuck, timeout_s)
    return stuck <= 0


def goodnight(say, timeout_s: float = 120.0) -> bool:
    """Rung 3 — one last word, if she has one. Optional and never fatal.

    Run on a daemon thread with a join deadline rather than inline, because `say` reaches
    the model and the model can hang. A thread we stop waiting on is the only way to
    bound something we cannot interrupt.

    Returns True ONLY if she actually said something. A failure, a timeout, or an empty
    reply all mean the shutdown proceeds without a goodbye — which is a smaller loss than
    a shutdown that will not complete.
    """
    out: Dict[str, Any] = {}

    def _run():
        try:
            out["text"] = (say() or "").strip()
        except Exception as exc:
            logger.warning("[shutdown] her last word failed: %s", exc)

    th = threading.Thread(target=_run, name="shutdown-goodnight", daemon=True)
    th.start()
    th.join(max(0.0, timeout_s))
    text = out.get("text") or ""
    if not text:
        logger.info("[shutdown] no last word — proceeding")
        return False
    logger.info("[shutdown] her last word: %r", text[:80])
    return True


def _taskkill(image: str) -> bool:
    import subprocess
    r = subprocess.run(["taskkill", "/F", "/IM", image], capture_output=True)
    return r.returncode == 0


def stop_voice() -> bool:
    """Rung 5a — TTS FIRST, which inverts serve.py's order deliberately.

    `stop()` kills the daemon first. Harmless for a force-kill; wrong for a graceful one.
    The voice holds ~1.8 GB and, mid-generation, the GPU at 100%, so releasing it before
    the daemon unloads avoids a window where the daemon is tearing down VRAM while the
    voice is still competing for it.

    The image name comes from the profile via serve.py (SP_TTS_SERVER_IMAGE) — both
    binaries are per-profile knobs, and a hardcoded name here made teardown a silent
    no-op the day a build was renamed.
    """
    return _taskkill(os.environ.get("SP_TTS_SERVER_IMAGE") or "tts-server.exe")


def stop_daemon() -> bool:
    return _taskkill(os.environ.get("SP_ENGINE_IMAGE") or "sp-daemon.exe")


def stop_gateway() -> None:
    """Rung 6 — `all` only, and always last.

    os._exit, not sys.exit: this runs on the HTTP handler's own thread and a normal exit
    would unwind through the server that is still trying to write the response. The route
    flushes the socket BEFORE calling this — see the note there.
    """
    logger.info("[shutdown] gateway stopping")
    os._exit(0)


# WHICH RUNGS EACH MODE RUNS. A committed table: "what does `kill` do" is readable rather
# than traceable. `kill` deliberately holds none of the graceful rungs.
_LADDER = {
    "her": ("quiesce", "finish_or_abandon", "goodnight", "flush", "stop_voice", "stop_daemon"),
    "all": ("quiesce", "finish_or_abandon", "goodnight", "flush", "stop_voice", "stop_daemon",
            "stop_gateway"),
    # `kill` holds none of the WAITING rungs — but quiesce is instant (a flag, a ticker
    # stop, timer cancels) and without it the gateway kept accepting turns and the kairos
    # ticker kept beating in the window between stop_daemon and stop_gateway, both
    # against a dead socket.
    "kill": ("quiesce", "stop_voice", "stop_daemon", "stop_gateway"),
}


def shutdown(mode: str, goodnight_fn=None, timeout_s: float = 120.0,
             _steps=None) -> Dict[str, Any]:
    """Run the ladder for `mode`. The one entry point.

    `_steps` overrides rungs by name and exists so a gate can assert ORDER without killing
    the machine it is running on. Production never passes it.
    """
    if mode not in _LADDER:
        return {"ok": False, "error": "unknown mode %r — want one of %s"
                                      % (mode, ", ".join(MODES))}
    steps = {"quiesce": quiesce, "finish_or_abandon": finish_or_abandon, "flush": flush,
             "stop_voice": stop_voice, "stop_daemon": stop_daemon,
             "stop_gateway": stop_gateway}
    steps.update(_steps or {})

    out: Dict[str, Any] = {"ok": True, "mode": mode, "stopped": [], "goodnight_said": False,
                           "flushed": 0, "finished_cleanly": True}
    global _LADDER_RUNNING
    with _LOCK:
        _LADDER_RUNNING = True
    try:
        return _run_ladder(mode, goodnight_fn, timeout_s, steps, out)
    finally:
        # IN A `finally`. If a rung raises, a latched flag would refuse `/v1/start` for
        # the rest of the gateway's life and the only way back would be a terminal —
        # which is the exact thing this whole feature exists to remove.
        with _LOCK:
            _LADDER_RUNNING = False


def _run_ladder(mode, goodnight_fn, timeout_s, steps, out) -> Dict[str, Any]:
    for rung in _LADDER[mode]:
        if rung == "goodnight":
            if goodnight_fn is not None:
                # steps.get, so a gate can SPY THE POSITION: _run_ladder used to call
                # the module-level goodnight() directly, ignoring _steps — so
                # G-SHUTDOWN's order assertion never saw this rung at all, and moving
                # goodnight after stop_daemon (asking her for a last word from a dead
                # daemon — the failure ladder_running() was invented for) would have
                # kept every check green.
                g = steps.get("goodnight", goodnight)
                out["goodnight_said"] = bool(g(goodnight_fn, timeout_s))
            continue
        if rung == "finish_or_abandon":
            out["finished_cleanly"] = bool(steps[rung](timeout_s))
            continue
        if rung == "flush":
            out["flushed"] = int(steps[rung]() or 0)
            continue
        if rung == "quiesce":
            steps[rung]()
            continue
        steps[rung]()
        # Derived from the rung's own name, not a second literal table: a name->label
        # dict here duplicated exactly what _LADDER already says, and two tables that
        # must stay in sync is the bug class this repo's CLAUDE.md calls out — an
        # invariant enforced in one of two paths ends up enforced in neither. A rung
        # added to _LADDER is now the only edit a future stop_* rung needs; anything
        # that reaches here without the stop_ prefix still fails loud, on purpose.
        if not rung.startswith("stop_"):
            raise KeyError(rung)
        out["stopped"].append(rung[len("stop_"):])
    return out
