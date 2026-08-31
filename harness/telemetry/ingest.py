"""ingest — THE door samples come in through. One writer, one place the rules live.

Everything that measures him arrives here: the watch agent, the phone companion, the adb
poller on his PC. They are three programs on three devices written at three different times,
which is exactly the shape that grows three different ideas of what a sample is — so none of
them writes to the store. They call `record()`.

WHAT THIS DOOR IS FOR, in order of how badly it is needed:

  1. ANON MODE. "Off the record" promises nothing is written down. A telemetry lane logging
     his heart rate straight through it would make that promise false — silently, on the one
     feature whose whole value is that it is not silent about what it keeps. The gate is
     here because here is the only way in.
  2. ONE CLOCK. Every sample is stamped from THIS machine. Three devices with three notions
     of "now" produce a history that cannot be plotted, and a watch that has been in a drawer
     for a week comes back with a clock that is confidently wrong. `at_hint` lets a source
     say when it thinks a sample was taken; it is kept in meta, never trusted as `at`.

     ONE EXCEPTION, added 2026-08-26 and bounded so it cannot become a hole: `measured_at`,
     for a caller that did not measure the value itself but READ IT FROM SOMEWHERE THAT DID.
     Home Assistant is the case — its sleep confidence refreshes every ten minutes, so
     stamping it on arrival dates a nine-minute-old reading to now and every freshness
     decision downstream is then made against the wrong number.

     It is not a device's clock and no device can reach it: nothing arriving over
     /v1/telemetry/ingest passes it, only in-process callers do. It is clamped to
     [now - MAX_BACKDATE_S, now + MAX_SKEW_S], so a foreign clock can neither reach back to
     rewrite history nor forward to look fresh, and a batch outside that window is stamped
     on arrival with `clock_ignored` returned to the caller.
  3. SHAPE. A number is a number, a state is one of its allowed words, unknown kinds are
     stored anyway and reported. A door that refuses data it does not recognise loses the
     data; a door that refuses to SAY it did not recognise it loses the bug.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from harness.telemetry import store

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

# The words a state kind may take. A state outside its vocabulary is a source bug, and it is
# refused rather than stored: "asleep" landing in `charging` would quietly poison every
# reading built on top of it, and unlike a bad number it would never look wrong.
STATES = {
    "on_body":     ("on", "off"),
    "charging":    ("on", "off"),
    "screen":      ("on", "off"),
    "motion":      ("still", "moving", "vehicle"),
    "sleep_stage": ("awake", "light", "deep", "rem"),
    "activity": ("still", "walking", "running", "cycling", "vehicle"),
}

SOURCES = ("watch", "phone", "pc")

# Sanity bounds. NOT medical judgement — a refusal to store obvious instrument noise, so a
# dropped-watch spike of 4000 bpm does not end up drawn on his chart as if it happened. A
# reading outside these is kept in `rejected` with its reason, because "the sensor produced
# nonsense at 3am" is itself a fact worth being able to see.
BOUNDS = {
    "heart_rate": (20.0, 250.0),
    "spo2": (50.0, 100.0),
    "skin_temp": (20.0, 45.0),
    "battery": (0.0, 100.0),
    "battery_temp": (-20.0, 80.0),
    "hr_variability": (0.0, 500.0),
    "sleep_confidence": (0.0, 100.0),
}


# ── HOW OLD A FOREIGN READING MAY BE AND STILL BE DATED HONESTLY (2026-08-26) ─────────
# See `measured_at` in record(). Two hours is generous for a signal that refreshes every
# ten minutes; the point of the bound is not precision, it is that a clock we do not own
# can never reach far enough back to rewrite history or far enough forward to look fresh.
MAX_BACKDATE_S = 2 * 3600
MAX_SKEW_S = 120


def record(samples: List[Dict[str, Any]], *, source: str = "",
           allow_anon: bool = False,
           measured_at: Optional[float] = None) -> Dict[str, Any]:
    """Store a batch. Returns {stored, rejected:[{sample, why}], held}.

    `measured_at` (epoch seconds) is for ONE kind of caller: a source that read the value
    from somewhere else and knows when that somewhere else measured it. Home Assistant is
    the case — its sleep confidence refreshes every ten minutes, so stamping it on arrival
    would date a nine-minute-old reading to now, and every freshness decision downstream
    would then be made against the wrong number. That is the same defect as `latest()`
    returning yesterday's heart rate, arriving by a different road.

    IT DOES NOT REOPEN THE ONE-CLOCK RULE. A device's own clock is still never trusted —
    the watch does not get to pass this, and nothing that posts to /v1/telemetry/ingest can
    reach it. It is bounded on both sides: not more than MAX_BACKDATE_S in the past, and
    not more than MAX_SKEW_S in the future. Outside that window the batch is stamped on
    arrival exactly as before, because a foreign clock that is wildly wrong is more likely
    to be wrong than to be interesting.

    NEVER RAISES. A source that crashes the gateway because it sent a malformed row is a
    source that takes the whole room down from a watch on a wrist, so every failure here is
    a counted rejection with a reason attached.

    `allow_anon` exists for exactly one caller — a gate proving the anon gate works — and is
    named so that a production caller passing it is visible in review."""
    out: Dict[str, Any] = {"stored": 0, "rejected": [], "held": 0}

    # ── THE ANON GATE, FIRST, BEFORE ANY SHAPING ────────────────────────────────────
    # Held, not queued. A queue would mean the evening reaches the disk the moment the
    # switch goes off, which is the same leak with a delay on it. What happened off the
    # record is not recorded, and the count is returned so the room can say so honestly.
    if not allow_anon:
        try:
            from harness.control import anon as _anon
            if _anon.holds("telemetry.sample", len(samples or ())):
                out["held"] = len(samples or ())
                out["why"] = _anon.WHY
                return out
        except Exception as _swx:
            _swallowed(_swlog, "record", _swx, lane="telemetry")
            pass                       # anon unavailable is not a licence to write

    at = store.now_iso()
    if measured_at is not None:
        now = time.time()
        if now - MAX_BACKDATE_S <= float(measured_at) <= now + MAX_SKEW_S:
            at = store.now_iso(float(measured_at))
        else:
            # Not an error and not silent: the row still lands, stamped on arrival, and
            # the caller is told its clock was not believed.
            out["clock_ignored"] = True
    ok: List[Dict[str, Any]] = []
    for s in (samples or []):
        try:
            row = _shape(s, source, at)
        except ValueError as exc:
            out["rejected"].append({"sample": _brief(s), "why": str(exc)})
            continue
        ok.append(row)
    try:
        out["stored"] = store._append(ok)
    except Exception as exc:
        out["rejected"].append({"sample": "batch", "why": "store failed: %s" % str(exc)[:120]})
    return out


def _brief(s: Any) -> str:
    try:
        return str({k: s.get(k) for k in ("source", "kind", "value")})[:120]
    except Exception as _swx:
        _swallowed(_swlog, "_brief", _swx, lane="telemetry")
        return str(s)[:120]


def _shape(s: Dict[str, Any], default_source: str, at: str) -> Dict[str, Any]:
    if not isinstance(s, dict):
        raise ValueError("a sample must be an object")
    kind = str(s.get("kind") or "").strip().lower()
    if not kind:
        raise ValueError("a sample must say what kind it is")
    src = str(s.get("source") or default_source or "").strip().lower()
    if src not in SOURCES:
        raise ValueError("unknown source %r (want one of %s)" % (src, ", ".join(SOURCES)))

    value: Any = s.get("value")
    if kind in STATES:
        v = str(value).strip().lower()
        if v not in STATES[kind]:
            raise ValueError("%s must be one of %s, got %r"
                             % (kind, "/".join(STATES[kind]), value))
        value = v
    else:
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValueError("%s wants a number, got %r" % (kind, value))
        lo, hi = BOUNDS.get(kind, (None, None))
        if lo is not None and not (lo <= value <= hi):
            raise ValueError("%s=%g is outside %g..%g — instrument noise, not a reading"
                             % (kind, value, lo, hi))

    meta = s.get("meta")
    meta = dict(meta) if isinstance(meta, dict) else {}
    # THE SOURCE'S OWN CLOCK IS KEPT AND NOT TRUSTED (see the module docstring). A watch
    # that has been off his wrist for a week comes back confidently wrong about `now`.
    if s.get("at_hint"):
        meta["at_hint"] = str(s["at_hint"])[:32]
    row = {"at": at, "source": src, "kind": kind, "value": value}
    if meta:
        row["meta"] = meta
    return row
