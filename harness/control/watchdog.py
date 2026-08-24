"""THE DAEMON IS NOT SUPERVISED, AND ON 2026-08-03 THAT REACHED HIM.

He wrote to her first thing and got:

    [error: [WinError 10061] No connection could be made because the target machine
     actively refused it]

The daemon had died in the night. `serve.py` launches it with Popen and exits; nothing
watches it, so a crash means connection-refused until a human notices and restarts by
hand. That is a supervision gap, not a model problem, and it is the gap this closes.

TWO FAILURE MODES, ONE CAUSE, DIFFERENT SEVERITIES. Both trace to a CUDA fault the engine
detects at `g4_ck` sync points (`reset:entry`, `byteexact_set:entry`) — 48 of them in the
log since 2026-07-29:

  * DEAD — the process is gone. `/v1/metrics` refuses the connection. Obvious once you
    look, invisible until you do.
  * WEDGED — the process is alive and answers `/v1/metrics` perfectly, but the CUDA
    context is destroyed, so every generation returns EMPTY in ~0.1 s. From the room this
    is indistinguishable from her having nothing to say; the gateway even dresses it up
    as "she was still thinking when the ceiling stopped her". This one is worse precisely
    because it looks healthy.

So health is not "does it answer" — it is "does it answer AND does it still generate".
A liveness probe that only opens a socket would have reported the wedge as fine for
hours, which is what happened.

WHAT IT DOES NOT DO. It does not restart on one empty reply — she is allowed to say
nothing. It takes a run of empty generations that FOLLOWED REAL PROMPTS, because that
combination has no innocent reading. And it rate-limits itself hard: a watchdog that can
restart every minute turns one bad turn into a restart loop, which is worse than the fault
it is treating.

This is a MITIGATION, and the file says so out loud. The CUDA fault is the bug; being
unreachable for eight hours is the consequence, and the consequence is worth fixing on its
own timescale.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# The knobs are read EVERY BEAT, never cached — the same rule the ambient eye and the
# backup ticker follow, and for the same reason: an off switch you have to reboot to use
# is not an off switch.
_THREAD: Optional[threading.Thread] = None
_LOCK = threading.Lock()

# What counts as wedged: this many consecutive generations that came back empty despite a
# real prompt. Three, because two can happen honestly (a refusal, a stop-token race) and
# four means he has already been staring at silence for three turns.
EMPTY_STREAK = 3

_state = {
    "empty_streak": 0,
    "last_restart_at": 0.0,
    "restarts": 0,
    "last_reason": "",
    "down_since": 0.0,
}


# ── THE COOLDOWN SURVIVES THE RESTART IT CAUSES (2026-08-24 audit, B7) ──────────────
# `last_restart_at` lived in process memory, and the one restart this module performs
# STOPS THIS PROCESS: the new gateway booted with 0.0, so the floor documented above
# ("a watchdog with no cooldown is a restart loop with a justification") never applied
# across the restarts it actually causes — a guard whose failure mode is no guard.
# Persisted beside the registry (the path every gate sandbox already redirects), read
# once at first need, written on every restart.
def _persist_path() -> str:
    reg = os.environ.get("SP_RECALL_REGISTRY", "")
    base = (os.path.dirname(reg) if reg else
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), "var", "memory"))
    return os.path.join(base, "watchdog.json")


def _recall_persisted() -> None:
    """Fold the previous process's restart clock into this one. Best-effort; called
    under _LOCK by _restart before the floor is judged."""
    if _state["last_restart_at"]:
        return
    try:
        import json
        with open(_persist_path(), encoding="utf-8") as f:
            d = json.load(f)
        _state["last_restart_at"] = float(d.get("last_restart_at") or 0.0)
        _state["restarts"] = int(d.get("restarts") or 0)
        _state["last_reason"] = str(d.get("last_reason") or "")
    except Exception:
        pass


def _persist() -> None:
    try:
        import json
        p = _persist_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"last_restart_at": _state["last_restart_at"],
                       "restarts": _state["restarts"],
                       "last_reason": _state["last_reason"]}, f)
    except Exception as exc:
        logger.warning("[watchdog] could not persist the restart clock: %s", exc)


def enabled() -> bool:
    return os.environ.get("SP_WATCHDOG", "1") != "0"


def interval_s() -> float:
    try:
        v = float(os.environ.get("SP_WATCHDOG_S", "30"))
    except ValueError:
        v = 30.0
    return max(10.0, min(600.0, v))


def cooldown_s() -> float:
    """The floor between restarts. A watchdog with no cooldown is a restart loop with a
    justification: if the fault recurs immediately, restarting every 30 s makes the stack
    permanently unusable instead of intermittently so, and buries the evidence."""
    try:
        v = float(os.environ.get("SP_WATCHDOG_COOLDOWN_S", "600"))
    except ValueError:
        v = 600.0
    return max(60.0, v)


def note_generation(prompt_chars: int, out_chars: int) -> None:
    """Called once per generation by the agent loop. THE WEDGE DETECTOR.

    `prompt_chars` matters: an empty generation from an empty prompt is arithmetic, not a
    fault. Only a real prompt that produced nothing counts toward the streak."""
    if prompt_chars < 200:
        return
    with _LOCK:
        if out_chars > 0:
            _state["empty_streak"] = 0
        else:
            _state["empty_streak"] += 1


def status() -> dict:
    with _LOCK:
        return {"enabled": enabled(), "interval_s": interval_s(),
                "empty_streak": _state["empty_streak"],
                "restarts": _state["restarts"],
                "last_restart_at": _state["last_restart_at"],
                "last_reason": _state["last_reason"],
                "down_since": _state["down_since"],
                "running": bool(_THREAD and _THREAD.is_alive())}


def _daemon_alive() -> bool:
    """REFUSED IS DEAD; TIMED OUT IS BUSY. They are not the same and treating them as the
    same makes this watchdog worse than the fault it exists for.

    Measured within an hour of shipping it: a kairos check-in kicked off a ~1450-token
    per-token prefill, the daemon saturated, `/v1/metrics` timed out for 330 s, and this
    function — which asked `get_client().health()` and caught every exception as "dead" —
    restarted a perfectly healthy stack mid-generation and threw away her reply.

    A TCP connect is the honest liveness question. If the socket is accepted the process is
    there, whatever it is doing with the GPU; if it is refused, the process is gone. The
    WEDGE detector (empty generations from real prompts) is what catches "alive but not
    generating", and it is the only thing that should."""
    import socket
    from urllib.parse import urlparse
    try:
        from harness.inference.client import get_client
        base = getattr(get_client(), "base_url", "http://127.0.0.1:3000")
    except Exception:
        base = "http://127.0.0.1:3000"
    u = urlparse(base)
    host, port = (u.hostname or "127.0.0.1"), (u.port or 3000)
    try:
        with socket.create_connection((host, port), timeout=5.0):
            return True
    except OSError:
        return False


def _should_restart() -> str:
    """Returns a REASON, or "" for nothing to do. A reason, not a boolean, so the log and
    the panel say WHY the stack was restarted — a restart with no stated cause is
    indistinguishable from a crash, and this exists to make crashes legible."""
    # AN EXTERNAL ENGINE IS NOT OURS TO RESTART (2026-08-21): under the openai backend the
    # watchdog may observe and say, never relaunch.
    try:
        from harness.inference.backends import supports as _sup
        if not _sup("restart"):
            return ""
    except Exception:
        pass
    if not _daemon_alive():
        with _LOCK:
            if not _state["down_since"]:
                _state["down_since"] = time.time()
            down = time.time() - _state["down_since"]
        # Two beats, so a restart that is already in flight is not restarted again.
        if down >= interval_s():
            return "the daemon has not answered for %.0fs — it is dead, not busy" % down
        return ""
    with _LOCK:
        _state["down_since"] = 0.0
        streak = _state["empty_streak"]
    if streak >= EMPTY_STREAK:
        return ("%d generations in a row came back empty from real prompts — the CUDA "
                "context is wedged (the process answers, the GPU does not)" % streak)
    return ""


def _restart(reason: str, restart_fn: Callable[[bool], None]) -> None:
    now = time.time()
    with _LOCK:
        _recall_persisted()       # the previous process's clock counts against the floor
        since = now - (_state["last_restart_at"] or 0.0)
        if _state["last_restart_at"] and since < cooldown_s():
            logger.warning("[watchdog] would restart (%s) but the last one was %.0fs ago "
                           "and the floor is %.0fs — leaving it alone and saying so",
                           reason, since, cooldown_s())
            return
        _state["last_restart_at"] = now
        _state["restarts"] += 1
        _state["last_reason"] = reason
        _state["empty_streak"] = 0
        _state["down_since"] = 0.0
        _persist()                # so the gateway this restart spawns still knows
    logger.error("[watchdog] RESTARTING THE STACK: %s", reason)
    # ── THROUGH THE LADDER'S FIRST RUNGS, NOT AROUND THEM (2026-08-24 audit, B8) ──
    # The operator's shutdown runs quiesce -> finish_or_abandon -> flush before
    # anything stops; this automatic path ran NONE of it — no refusal of new turns,
    # no wait for the one in flight, and the undelivered outbox died with the
    # process. The invariant was enforced on one of two teardown paths and the
    # unguarded one was the automatic one. Bounded (finish_or_abandon has its own
    # timeout; a wedged CUDA context abandons rather than hangs), and if the spawn
    # itself fails the quiesce is RESUMED — a watchdog that leaves the gateway
    # refusing every turn after a failed restart would be the worse fault.
    _spawned = False
    try:
        from harness.control import shutdown as _sd
        try:
            _sd.quiesce()
            _sd.finish_or_abandon(60.0)
            _sd.flush()
        except Exception as exc:
            logger.warning("[watchdog] pre-restart rungs incomplete (%s) — "
                           "restarting anyway; the daemon is the thing that is broken",
                           exc)
        restart_fn(True)          # full: the daemon is the thing that is broken
        _spawned = True
    except Exception as exc:
        logger.error("[watchdog] restart failed: %s", exc)
    finally:
        if not _spawned:
            try:
                from harness.control import shutdown as _sd2
                _sd2.resume()
            except Exception:
                pass


def _held_by_shutdown() -> bool:
    """A SHUTDOWN IS NOT A CRASH (2026-08-19). `mode=her` kills the daemon ON PURPOSE
    and leaves the gateway up with the flag latched — and this loop, which checked only
    "has the daemon answered", concluded "dead, not busy" ~30-60 s later and brought
    the whole stack back up: the operator shut her down and the watchdog un-shut her.
    The deliberate-stop flag outranks the liveness probe; ladder_running covers the
    in-progress window. down_since is cleared so a later REAL crash starts its own
    clock instead of inheriting the shutdown's."""
    from harness.control import shutdown as _sd
    if _sd.is_shutting_down() or _sd.ladder_running():
        with _LOCK:
            _state["down_since"] = 0.0
        return True
    return False


def _loop(restart_fn: Callable[[bool], None]) -> None:
    while True:
        try:
            time.sleep(interval_s())
            if not enabled():
                continue
            if _held_by_shutdown():
                continue
            reason = _should_restart()
            if reason:
                _restart(reason, restart_fn)
        except Exception as exc:                # never let the watchdog be the thing that dies
            logger.warning("[watchdog] beat failed: %s", exc)
            time.sleep(30.0)


def start(restart_fn: Callable[[bool], None]) -> None:
    """Start the watcher. `restart_fn` is injected rather than imported so this module
    knows nothing about the gateway — the gateway owns the one restart door (`_do_restart`,
    which goes through serve.py so the profile and env guards still run), and a second
    hand-rolled relaunch path in here is exactly the kind of duplicate that this codebase
    keeps paying for."""
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return
    _THREAD = threading.Thread(target=_loop, args=(restart_fn,), daemon=True,
                               name="watchdog")
    _THREAD.start()
