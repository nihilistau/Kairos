"""THE ATTENTION LEDGER — proof that she was looking.

    "Absence is only information if you can prove you were looking."

The neighbour tells you something by NOT being there only if you were at the window at 5am. If
you slept in, the empty driveway carries zero bits. The information is not in the absence — it
is in the CONJUNCTION of a live expectation and a proven observation that came back empty.

── THE BUG THIS EXISTS TO KILL ────────────────────────────────────────────────────────
PersonModel.silences() measured `quiet = days since he last MENTIONED a thing`. It never asked
whether he was THERE.

So: go away for three weeks — a holiday, a deadline, a hospital — and EVERY dimension with three
or more mentions goes silent SIMULTANEOUSLY, at high bits. She greets you with:

    "You've stopped talking about the marathon. And the GPU. And Tuffy. And your flight."

That is not noticing. THAT IS A BUG WEARING NOTICING'S CLOTHES, and it is worse than saying
nothing, because the one signal in this system that makes a person feel KNOWN would be firing on
the fact that they were busy.

── THE FIX: MEASURE TIME IN DAYS HE WAS ACTUALLY HERE ─────────────────────────────────
Calendar time is irrelevant to silence. ATTENTION TIME is the only clock that can make an
absence mean anything.

    quiet_days   = calendar days since he last mentioned it        <- WRONG
    attended_days = days he TALKED TO HER and STILL did not mention it   <- the real quantity

If he said nothing at all across the window, attended == 0, and NOTHING is surprising. Absence of
data is not data. That falls out of the arithmetic for free rather than needing a special case,
which is how you know it is the right quantity.

── WHY A DAILY BUCKET AND NOT AN EVENT LOG ────────────────────────────────────────────
Cadence in this system is measured in DAYS ("he brings it up every two days"). A per-turn log
would be a bigger, slower, more privacy-laden thing that answers a question nobody asked. One
integer per day answers the only question silence needs:

    "Was the channel open on this day, yes or no?"

The file is append-safe, human-readable, and small enough to never need pruning: one line per
day he spoke to her at all.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Dict, Optional

from harness.loud import swallowed as _swallowed
from harness.store_io import replace_atomic

logger = logging.getLogger(__name__)

_LEDGER_LOCK = threading.Lock()

_DAY = 86400.0


def _path() -> str:
    """Beside the memory registry — it is part of the same story about him."""
    reg = os.environ.get("SP_RECALL_REGISTRY", "")
    if reg:
        return os.path.join(os.path.dirname(reg), "presence.jsonl")
    return ""


def _day_key(ts: float) -> str:
    """UTC day. Written with gmtime, read with timegm — see G-CLOCK. This system has been
    bitten twice by pairing gmtime with mktime; the day bucket does not get to be the third."""
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def _load() -> Dict[str, int]:
    p = _path()
    if not p or not os.path.exists(p):
        return {}
    out: Dict[str, int] = {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    r = json.loads(ln)
                    out[r["day"]] = int(r.get("turns", 0))
                except Exception as _swx:
                    _swallowed(logger, "_load", _swx, lane="model")
                    continue
    except Exception as _swx:
        _swallowed(logger, "_load", _swx, lane="model")
        return {}
    return out


def _save(days: Dict[str, int]) -> None:
    p = _path()
    if not p:
        return
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for d in sorted(days):
                f.write(json.dumps({"day": d, "turns": days[d]}) + "\n")
        replace_atomic(tmp, p)      # atomic: a half-written ledger is worse than a stale one
    except Exception as exc:
        # The ledger this writes is what the room reads back as his days. Losing a write
        # silently means a day that happened is a day nothing remembers.
        logger.warning("[presence] the day ledger did not save (%s: %s) — %d day(s) of "
                       "turns are not on disk", type(exc).__name__, exc, len(days))
        _swallowed(logger, "presence ledger", exc, lane="presence")


def note_turn(ts: Optional[float] = None) -> None:
    """HE SPOKE TO HER. This is the observation receipt for the non-event.

    Called on every human turn. It records nothing about WHAT he said — only that the channel
    was open. That is deliberately all it needs to know, and it is the least invasive thing that
    can make silence mean anything: a count, not a transcript.
    """
    ts = ts if ts is not None else time.time()
    # Load-mutate-write under a lock: this runs on EVERY human turn under a
    # ThreadingHTTPServer, and two concurrent turns interleaving the unlocked
    # read-modify-write lose an increment — in the one counter silence.py's
    # MIN_LEDGER_DAYS gates on, i.e. the ledger that proves anyone was looking.
    with _LEDGER_LOCK:
        days = _load()
        k = _day_key(ts)
        days[k] = days.get(k, 0) + 1
        _save(days)


def attended_days(t0: float, t1: Optional[float] = None) -> float:
    """How many days between t0 and t1 did he ACTUALLY TALK TO HER?

    This is the denominator that makes silence honest. A gap he was not present for is not a
    silence — it is a gap in the RECORD, and a system that cannot tell those apart will
    confidently tell him he has gone quiet about something while he was in hospital.
    """
    t1 = t1 if t1 is not None else time.time()
    if t1 <= t0:
        return 0.0
    days = _load()
    if not days:
        # NO LEDGER AT ALL. Not "he was never here" — "I HAVE NO IDEA whether he was here."
        # Those are different, and conflating them is the entire bug. With no evidence of
        # attention, NOTHING can be surprising: return 0 and every silence scores zero bits.
        # A system with no memory of looking must not claim to have seen nothing.
        return 0.0
    n = 0
    t = t0
    while t <= t1 + 1.0:
        if days.get(_day_key(t), 0) > 0:
            n += 1
        t += _DAY
    return float(n)


def present_days_total() -> int:
    """How many distinct days he has ever spoken to her. The ledger's own receipt."""
    return sum(1 for v in _load().values() if v > 0)
