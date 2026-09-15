"""Is the feed still speaking? — the OPERATOR's question, never hers.

WHY THIS EXISTS (2026-09-15). `heart_rate` stopped on 2026-09-01 and the watch stopped
entirely on 2026-09-04. Nobody noticed for a fortnight, and the reason is that everything
worked exactly as designed:

    G-TELEMETRY section 2 — SILENCE IS AN ANSWER. Stale data, no watch, off the wrist ->
    she is told NOTHING.

That rule is right and is not being changed here. A companion who says "you seem calm" from
a reading taken last Tuesday is worse than one who says nothing. But it was enforced for
exactly one audience. She fell silent about his body, correctly, and *no one was told why* —
so a dead watch and a quiet afternoon produced the identical observable: nothing. The rule
was enforced on her side of the seam and on nobody's side of it (AGENTS.md section 0).

This is the other side. It answers a DIFFERENT question from body.read():

    body.read()  -> "what is his body doing"   (an inference about a person)
    feeds()      -> "is the instrument on"     (a fact about a file)

That distinction is why this is not the second reader G-TELEMETRY section 5 forbids. Section
5 says the room and her prefix must not describe two different BODIES, and both of those
still come from body.read() alone. Nothing here reads a value, forms a fact, or reaches her
prefix: it reads timestamps and counts rows. If you ever find yourself adding a `value` to
what this returns, you are writing the second reader and section 5 is talking to you.

CHEAP ON PURPOSE. The old day files run to 10 MB and this runs at boot, so kinds are found
by a regex over the raw text rather than by parsing every row into a dict. Day granularity
is all an operator needs: "heart_rate: 14 days ago" does not get more actionable at second
precision.
"""
from __future__ import annotations

import calendar
import io
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from harness.loud import swallowed as _swallowed

from . import store

_swlog = logging.getLogger(__name__)

# `"kind": "heart_rate"` with whatever spacing json.dumps happened to use.
_KIND_RE = re.compile(r'"kind"\s*:\s*"([A-Za-z0-9_.-]+)"')

# A FEED is dark after this long, which is a much coarser question than FRESH_S asks.
# FRESH_S is "may she quote this number" and is measured in minutes; a watch off the wrist
# over lunch trips every one of them and that is correct. This is "has the instrument
# stopped", and three days is chosen so that a weekend away does not read as a fault.
DARK_DAYS = 3

# THE WHOLE STORE going quiet is a different and much faster fault than one kind stopping,
# so it gets its own threshold — and this one is MEASURED rather than picked. Over the ten
# most recent day files (1,049 rows) the gap between consecutive rows of any kind runs
# p50 6.0 min, p90 11.5 min, p99 40.8 min, and the longest gaps are:
#
#     0.8  0.9  1.0  1.7  |  9.2  16.7  30.0  54.2   hours
#
# There is nothing between 1.7 and 9.2, and everything on the right of that gap is a known
# outage (30.0 h is her being down across three reboots on 2026-09-14; 54.2 h is the missing
# 2026-09-07). Six hours sits in the empty space: past every normal quiet stretch, short of
# every real one. Day granularity is NOT enough here — at "1 day" this misses a 30-hour
# outage that straddles a midnight, which is exactly the one that happened.
STORE_DARK_HOURS = 6

# How far back to look for a kind's last appearance. Past this a kind is reported as gone
# rather than aged: the exact number of weeks is not the actionable part.
LOOKBACK_DAYS = 21


def _kinds_in_day(day: str) -> Dict[str, int]:
    """Every kind present in one day file, and how many rows each had."""
    out: Dict[str, int] = {}
    try:
        with io.open(store.day_path(day), encoding="utf-8", errors="replace") as f:
            for line in f:
                m = _KIND_RE.search(line)
                if m:
                    out[m.group(1)] = out.get(m.group(1), 0) + 1
    except OSError:
        pass
    return out


def _last_row_ts(day: str) -> Optional[float]:
    """The newest timestamp in one day file, read from the TAIL.

    Reading the whole file would be correct and, on a healthy day with the watch back, would
    mean parsing 10 MB to learn one number. Rows are appended in time order, so the last
    64 KB holds it; the first byte is dropped because a mid-file seek lands inside a line.
    """
    p = store.day_path(day)
    try:
        sz = os.path.getsize(p)
        with io.open(p, "rb") as f:
            if sz > 65536:
                f.seek(sz - 65536)
                f.readline()                      # partial line, discard
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    best = None
    for line in tail.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            at = json.loads(line).get("at")
            t = store.parse_iso(at) if at else None
        except Exception as _swx:
            # A torn row ages out rather than becoming a confident timestamp — same rule as
            # store.read_day. Named, not anonymous: a JSON error here is the world, but a
            # TypeError is this module being wrong, and loud.swallowed sorts the two.
            _swallowed(_swlog, "liveness._last_row_ts", _swx, lane="telemetry")
            continue
        if t is not None and (best is None or t > best):
            best = t
    return best


def feeds(now: Optional[float] = None,
          lookback_days: Optional[int] = None,
          dark_days: Optional[int] = None) -> Dict[str, Any]:
    """What each kind last did, newest-silence first.

    Returns `{"today", "last_row_day", "store_days_ago", "kinds": [...]}` where each kind is
    `{"kind", "last_day", "days_ago", "rows", "dark"}`. A kind that has not appeared inside
    the lookback window is absent from the list entirely — it is not a fault, it is a sensor
    this setup has never had, and listing `spo2: never` forever trains the reader to skim.
    """
    # Resolved HERE, not in the signature. `dark_days: int = DARK_DAYS` would bind the
    # module constant at def time, so editing DARK_DAYS afterwards — an operator tuning it,
    # or a gate mutating it to prove this check can go red — would change nothing at all.
    # That is the same shape as the defect this whole module exists to report.
    lookback_days = LOOKBACK_DAYS if lookback_days is None else lookback_days
    dark_days = DARK_DAYS if dark_days is None else dark_days
    now = time.time() if now is None else now
    # UTC, and it is not a detail. store.day_path() names day files from time.gmtime() and
    # _append buckets rows by the first 10 characters of a Z stamp, so the file names ARE
    # UTC dates. Reading them with localtime/mktime is wrong by exactly the local offset —
    # in +10 that makes every morning before 10:00 report the newest file as a day stale.
    # This is the bug store.parse_iso's docstring warns about and G-CLOCK was built for.
    today = time.strftime("%Y-%m-%d", time.gmtime(now))

    all_days = store.days()                       # oldest first
    window = all_days[-lookback_days:] if lookback_days > 0 else all_days

    def _days_ago(day: str) -> int:
        try:
            t = calendar.timegm(time.strptime(day, "%Y-%m-%d"))
            t0 = calendar.timegm(time.strptime(today, "%Y-%m-%d"))
        except ValueError:
            return 999
        return max(0, int((t0 - t) // 86400))

    # Backwards, so the FIRST time a kind turns up is its LAST appearance.
    seen: Dict[str, Dict[str, Any]] = {}
    for day in reversed(window):
        for kind, n in _kinds_in_day(day).items():
            if kind not in seen:
                seen[kind] = {"kind": kind, "last_day": day,
                              "days_ago": _days_ago(day), "rows": n}

    kinds = sorted(seen.values(), key=lambda r: (-r["days_ago"], r["kind"]))
    for r in kinds:
        r["dark"] = r["days_ago"] >= dark_days

    # THE WHOLE STORE, not just a kind. This is the one that catches the failure no
    # per-kind check can see: ingest itself stopped, because the stack it arrives through
    # was not running. She was down 30 hours across three reboots on 2026-09-14 and this
    # is what would have said so — in HOURS, because that outage straddled a midnight and
    # a day-granularity check reads it as "1 day" and shrugs.
    last_day = all_days[-1] if all_days else ""
    last_ts = _last_row_ts(last_day) if last_day else None
    return {"today": today,
            "last_row_day": last_day,
            "store_days_ago": _days_ago(last_day) if last_day else None,
            "store_last_ts": last_ts,
            "store_age_h": ((now - last_ts) / 3600.0) if last_ts else None,
            "kinds": kinds}


def report(now: Optional[float] = None, **kw) -> List[str]:
    """`feeds()` as lines for a human. EMPTY when everything is current — a report that
    prints when there is nothing wrong is a report nobody reads by the third week."""
    f = feeds(now=now, **kw)
    dark = [r for r in f["kinds"] if r["dark"]]
    age_h = f["store_age_h"]
    out: List[str] = []

    if age_h is not None and age_h >= STORE_DARK_HOURS:
        out.append("telemetry: NOTHING has arrived for %.1f hours (last row %s). Normal "
                   "quiet tops out near 1.7 h, so this is an outage, not an evening. The "
                   "feed reaches the store through her gateway — check the stack is up."
                   % (age_h, f["last_row_day"]))
    if dark:
        out.append("telemetry: %d feed(s) stopped and she has been silent about them since:"
                   % len(dark))
        for r in dark:
            out.append("  %-18s last %s  (%d days ago, %d rows that day)"
                       % (r["kind"], r["last_day"], r["days_ago"], r["rows"]))
        out.append("  She is CORRECT to say nothing — stale data never reaches her "
                   "(G-TELEMETRY section 2). This line is so that you know why she is quiet.")
    return out
