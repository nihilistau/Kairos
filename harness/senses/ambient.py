"""ambient.py — the room, on a timer.

Every `SP_AMBIENT_S` seconds (default 3600) take one webcam frame, look at it with
the served model's own vision tower, and write one line to a rolling log. Nothing
is spoken, nothing interrupts, and no image file is retained unless the operator
asks for it — what persists is a dated sentence about the room.

ON BY DEFAULT, at the operator's explicit instruction ("yes but it is my room and
i want it on"). I argued the other way first and I was overruled, which is the
correct outcome: it is his room, his camera, his machine. The argument is recorded
here rather than in the default, because a default is not the place to keep
relitigating a decision someone already made.

WHAT MAKES THIS TOLERABLE, and all of it is load-bearing:
  - THE LIGHT IS THE TRUTH. Capture goes through the same harness.senses.capture
    path as every other look, so the camera's own indicator LED is the honest
    signal. Nothing here can look without the light.
  - IT IS VISIBLE. Every capture appends to var/senses/ambient.jsonl with a
    timestamp, and GET /v1/senses reports the last one and the next one. There is
    no state in which it is running and he cannot tell.
  - IT STOPS INSTANTLY. `enabled` is re-read EVERY tick, not captured at start.
    Turning it off in the profile or through the knob takes effect on the next
    beat rather than at the next restart — an off switch you have to reboot to use
    is not an off switch.
  - IT NEVER SPEAKS. This writes a log. It does not start a conversation, does not
    push a notification, and is not wired into the reply path. If she mentions the
    room it is because he asked and she read the log, never because a camera fired.
  - IT FAILS QUIET AND VISIBLE. A camera that is unplugged, in use, or refused
    logs the reason and keeps its schedule. It never retries in a tight loop and
    never takes the stack down.

Cost per tick, measured: ~2 s to capture, ~5 s to encode, one daemon turn.
"""
from __future__ import annotations

import json
import os
import threading
import logging
import time
from typing import Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG = os.environ.get("SP_AMBIENT_LOG",
                     os.path.join(_ROOT, "var", "senses", "ambient.jsonl"))
# TWO DEFAULTS, ON PURPOSE — not drift. serve.py's door default is PERSONAL (it
# names Sam, his room, her voice — 2026-08-21, his ask for "a shared, more
# personalized experience"), because the door builds HIS stack. This fallback is
# the env-less one (gates, bare imports) and assumes nothing about an operator.
PROMPT = os.environ.get(
    "SP_AMBIENT_PROMPT",
    "Describe this room in one short sentence — who or what is present, and what "
    "is happening. If nobody is there, say so plainly.")

_THREAD: Optional[threading.Thread] = None
_LAST: dict = {}


def enabled() -> bool:
    """RE-READ EVERY TICK. Never cached — see the module docstring.

    TWO SWITCHES, AND OFF WINS (2026-08-03). `SP_AMBIENT` is an env var, which means the
    only way to stop the timer was a restart — and the thing you most want to stop without
    a restart is a camera. So the operator also has `senses.ambient` in the tuning registry,
    and it is a VETO: the env may arm the eye, the knob may always shut it.

    Fail-safe direction is deliberate and is the opposite of the roleplay switch's. There,
    an unreadable registry means the stage is shut. Here, an unreadable registry must not be
    able to TURN A CAMERA ON, but it also must not silently disable a sense she relies on —
    so a missing or unreadable knob simply does not veto, and the env stays the arming
    authority. The knob can only ever subtract.

    HER OWN EYES ARE NOT AFFECTED. This gates the hourly TIMER only. `take_photo`,
    `look_at` and `room_history` are tools she calls, and they keep working with this off —
    which is the point: if the room stays healthy with the timer off but faults when she
    chooses to look, that narrows it to the vision forward rather than to the schedule."""
    if os.environ.get("SP_AMBIENT", "0") != "1":
        return False
    try:
        from harness.tuning import registry as tune
        v = tune.get("senses.ambient")
        if v is not None and not bool(v):
            return False
    except Exception:
        pass                       # a knob that cannot be read never arms anything
    return True


def interval_s() -> float:
    try:
        v = float(os.environ.get("SP_AMBIENT_S", "3600"))
    except ValueError:
        v = 3600.0
    return max(60.0, min(86400.0, v))       # a minute to a day


def quiet_s() -> float:
    """How long the room must have been quiet before the eye may open (2026-08-21,
    the re-arm's condition: "doesn't just fire blindly... waits until there is a
    5-10 minute window of no activity"). Override-only through the panel knob;
    the env carries the boot default."""
    try:
        from harness.tuning import registry as tune
        c = tune.chosen("senses.ambient_quiet_s")
        if c is not None:
            return max(60.0, min(1800.0, float(c)))
    except Exception:
        pass
    try:
        v = float(os.environ.get("SP_AMBIENT_QUIET_S", "300"))
    except ValueError:
        v = 300.0
    return max(60.0, min(1800.0, v))


_BOOT_AT = time.monotonic()     # when THIS process opened its eyes


def _on_boot_ok() -> bool:
    """May an overdue capture fire straight after a start/bounce? Default NO
    (2026-08-21, his call, same shape as the kairos act-first-at-bounce knobs):
    a bounce empties the kairos activity state, so the recency signal cannot
    testify and the guard would fail open — the one capture at 04:01 that
    prompted this. Off means the first capture waits a full quiet window from
    process start; on restores fire-when-due."""
    try:
        from harness.tuning import registry as tune
        c = tune.chosen("senses.ambient_on_boot")
        if c is not None:
            return bool(c)
    except Exception:
        pass
    return os.environ.get("SP_AMBIENT_ON_BOOT", "0") == "1"


def _activity() -> str:
    """WHY the room is not quiet right now, or "" if it is. One reader, so the
    guard and the status readout can never disagree about what is blocking.

    THE EYE JOINS THE QUEUE (2026-08-21). The re-armed schedule does not fire a
    vision forward blindly into whatever the GPU is doing — the 2026-08-03 disarm
    happened precisely because a capture landed at the tail of a lockup mid-
    conversation. It defers to the same precedence every other background actor
    respects: his turn in flight, ANY generation in flight, the daemon streaming
    (her kairos/solo work included), and a recency window over the last time
    either of them did anything. Every check fails OPEN individually (a broken
    signal must not blind the eye forever) but the capture itself still only
    happens when none of them reports activity."""
    if not _on_boot_ok() and (time.monotonic() - _BOOT_AT) < quiet_s():
        return "the stack just started"
    try:
        from harness.kairos import scheduler as _ks
        if _ks.user_turn_active():
            return "his turn is in flight"
        with _ks._LOCK:
            last = max((max(st.last_user_at, st.last_spoke_at, st.last_solo_at)
                        for st in _ks._STATE.values()), default=0.0)
        if last > 0.0:
            ago = time.monotonic() - last
            if ago < quiet_s():
                return "the conversation was active %.0fs ago" % ago
    except Exception:
        pass
    try:
        from harness.control import shutdown as _sd
        with _sd._LOCK:
            if _sd._IN_FLIGHT > 0:
                return "a generation is in flight"
    except Exception:
        pass
    try:
        from harness.inference.client import get_client
        if float(get_client().metrics().get("tokens_per_sec", 0.0)) > 1.0:
            return "the daemon is streaming"
    except Exception:
        pass
    return ""


_WAITING: dict = {}       # {"since": ts, "why": str} while due-but-deferred


def status() -> dict:
    # OFF DISK, LIKE THE SCHEDULE. `_LAST` is this process's memory of the last look,
    # so after every gateway bounce it was empty and the panel said the eye had never
    # opened — `last: null, next_in_s: null` — while the log on disk held an unbroken
    # hourly run. That is what "the webcam capture and description are not displayed
    # anymore" was: the observation was made, written down, and then not read back.
    #
    # The LOOP was already fixed to count from disk. Fixing only the loop and not the
    # readout is §0 in miniature — two paths to the same fact, one of them corrected.
    last = _LAST or _last_row()
    nxt = None
    if last.get("at") and enabled():
        nxt = round(last["at"] + interval_s() - time.time())
    return {
        "enabled": enabled(),
        "interval_s": interval_s(),
        "quiet_s": quiet_s(),
        "running": bool(_THREAD and _THREAD.is_alive()),
        "last": last or None,
        "next_in_s": nxt,
        # DUE BUT DEFERRED — the guard is holding the shutter for quiet. The chips
        # read this; a "waiting" the panel cannot see is a schedule that looks hung.
        "waiting": ({"for_s": round(time.time() - _WAITING["since"]),
                     "why": _WAITING.get("why", "")}
                    if _WAITING.get("since") else None),
        "log": LOG,
    }


def recent(n: int = 10) -> list:
    """The last n observations — what she reads when he asks about the room."""
    try:
        with open(LOG, "r", encoding="utf-8") as f:
            rows = [json.loads(x) for x in f if x.strip()]
        return rows[-n:]
    except (OSError, ValueError):
        return []


def _append(row: dict) -> None:
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def observe_once() -> dict:
    """One capture -> one logged sentence. Safe to call by hand."""
    global _LAST
    # ANONYMOUS MODE (2026-08-23). Held before the SHUTTER, not before the append: the
    # objection to an hourly photograph of the room during a private evening is the
    # photograph, and describing it only to discard the sentence would be the camera
    # opening anyway. The eye simply does not look while the switch is on.
    from harness.control import anon as _anon
    if _anon.holds("senses.ambient"):
        return {"skipped": _anon.WHY}
    row = {"at": time.time(),
           "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())}
    try:
        from harness.senses import capture
        from harness.skills.sight import _describe
        row["seen"] = _describe(capture.photo(), PROMPT)
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"[:300]
    _LAST = row
    _append(row)
    return row


logger = logging.getLogger(__name__)


def _last_row() -> dict:
    """The last look the ROOM had, off disk — the only record that survives a bounce."""
    try:
        rows = recent(1)
        return rows[-1] if rows else {}
    except Exception:
        return {}


def _last_at() -> float:
    """When the room was actually last looked at. One reader, so the schedule and the
    readout can never disagree about when the eye last opened."""
    try:
        return float(_last_row().get("at") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _loop() -> None:
    # ── THE SCHEDULE IS THE ROOM'S, NOT THE PROCESS'S (2026-08-03) ──────────────
    # This waited one FULL interval from boot before the first capture — right in
    # spirit ("every restart photographs the room" is not what hourly means), and
    # wrong in effect: the countdown restarted from zero on every bounce, so a day
    # with several restarts never accumulated an hour of continuous uptime and the
    # room was never looked at at all. Measured 2026-08-03: clean hourly entries at
    # 16:34 and 17:35, then nothing for eight hours across a night of restarts,
    # which is why the webcam capture and its description stopped appearing.
    #
    # So the delay is what is LEFT of the interval since the last real capture. A
    # bounce costs the remainder, not the whole hour; a genuinely fresh install
    # still waits a full one. Same class as the kairos _LAST bug: per-process state
    # that should have been read off disk, and the timestamp was already there.
    last = _last_at()
    nxt = (last + interval_s()) if last else (time.time() + interval_s())
    if last:
        logger.info("[ambient] last look was %.0f min ago; next in %.0f min",
                    (time.time() - last) / 60.0, max(0.0, nxt - time.time()) / 60.0)
    while True:
        time.sleep(5.0)                    # short beat so an off switch is prompt
        nxt = _beat(nxt)


def _beat(nxt: float) -> float:
    """ONE beat of the schedule, factored out so G-SENSES drives the REAL code —
    a guard that only exists inside a `while True` thread is a guard no gate can
    reach. Returns the next due time."""
    if not enabled():
        _WAITING.clear()
        return max(nxt, time.time())           # stay quiet without losing the schedule
    if time.time() < nxt:
        return nxt
    # DUE — but the eye waits for the room to go quiet (2026-08-21, the re-arm's
    # condition). It holds at the first quiet beat, not on a fresh timer: being
    # deferred does not push the schedule, it just holds the shutter.
    why = _activity()
    if why:
        if not _WAITING.get("since"):
            _WAITING["since"] = time.time()
            logger.info("[ambient] due, deferring for quiet: %s", why)
        _WAITING["why"] = why
        return nxt
    _WAITING.clear()
    try:
        observe_once()
    except Exception:                   # a sense must never take the stack down
        pass
    return time.time() + interval_s()


def start() -> bool:
    """Start the watcher thread. Idempotent; returns whether it is running."""
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return True
    _THREAD = threading.Thread(target=_loop, name="ambient-eye", daemon=True)
    _THREAD.start()
    return True
