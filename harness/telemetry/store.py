"""store — where samples live, and the only code that writes them.

ONE FILE PER DAY, append-only JSONL under var/telemetry/. Same shape as her speech ledger
and the day transcript, for the same reason: a day is the unit a reader actually wants, an
append is atomic enough on one line, and a corrupt tail costs one day rather than the lot.

A SAMPLE is five fields and nothing clever:

    at      ISO-8601 UTC, always stamped HERE so two sources cannot disagree about clocks
    source  who measured it: "watch" | "phone" | "pc"
    kind    what it is: heart_rate | steps | motion | battery | screen | ...
    value   a number, or a short string for state kinds ("asleep", "on")
    meta    optional dict — accuracy, sensor id, whatever the source wants to carry

RETENTION IS A DIFFERENT QUESTION FROM MEMORY'S. "Nothing is ever deleted" is a rule about
what she BELIEVES: a fact she was told, a conclusion she drew. This is instrument data at up
to 1 Hz, and pretending it obeys the same law would either fill his disk or quietly start
dropping rows behind a promise it could not keep. So retention is an explicit knob with an
explicit default (keep everything), and `prune()` is the only thing that removes a sample —
never a write path, never a read path, never automatic without the knob being set.
"""
from __future__ import annotations

import calendar
import io
import json
import os
import threading
import time
from typing import Any, Dict, Iterable, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LOCK = threading.Lock()

# The kinds this store understands. A kind not in here is still STORED — a source that
# learns a new trick must not lose the data because the table has not caught up — but it is
# reported by `unknown_kinds()` so the omission is visible rather than silent.
KINDS = {
    # ── body (the watch) ────────────────────────────────────────────────────────────
    "heart_rate":      ("bpm",     "number"),
    "hr_variability":  ("ms",      "number"),
    "spo2":            ("%",       "number"),
    "skin_temp":       ("C",       "number"),
    "on_body":         ("",        "state"),    # on | off
    "sleep_stage":     ("",        "state"),    # awake | light | deep | rem
    "stress":          ("",        "number"),
    # ── movement (either device) ────────────────────────────────────────────────────
    "steps":           ("count",   "number"),   # cumulative since boot; deltas on read
    "cadence":         ("spm",     "number"),
    "accel_rms":       ("m/s2",    "number"),   # one number per window, not raw XYZ
    # GYRO AS ONE NUMBER, for the same reason accel is (2026-08-26, his ask: "gyroscopes
    # activity so she can see you are moving around a lot"). Raw XYZ at 100 Hz is a
    # firehose she has no use for; the magnitude of rotation over a window is the thing a
    # person in the room would actually notice — pacing, fidgeting, turning over in bed.
    "gyro_rms":        ("rad/s",   "number"),
    "motion":          ("",        "state"),    # still | moving | vehicle
    "calories":        ("kcal",    "number"),
    "distance":        ("m",       "number"),
    # ── device state (adb / companion) ──────────────────────────────────────────────
    "battery":         ("%",       "number"),
    "battery_temp":    ("C",       "number"),
    "charging":        ("",        "state"),    # on | off
    "screen":          ("",        "state"),    # on | off
    "light":           ("lux",     "number"),
    "pressure":        ("hPa",     "number"),
}

STATE_KINDS = frozenset(k for k, (_u, t) in KINDS.items() if t == "state")


# ── ONE CLOCK SPELLING, AT MILLISECONDS (2026-08-26) ──────────────────────────────────
# It was seconds, and that was a bug with a straight face. At 1 Hz several samples share a
# second routinely, `latest()` compared `at` strings with `>`, and on a tie the FIRST row
# won — so the newest reading lost to the oldest one in the same second. Live, that reads
# as "he seems to be asleep" while his heart rate is 112 and he is walking.
#
# Milliseconds fix the ties; `latest()` preferring the later row on an exact tie fixes the
# rest. Both, because at 1 kHz accelerometer batching the ties come back. And it is spelled
# HERE so the store, the door and the reader cannot drift into three formats — a comparison
# between "...:33Z" and "...:33.123Z" is lexicographic and silently wrong ('.' < 'Z').
def now_iso(now: Optional[float] = None) -> str:
    t = time.time() if now is None else now
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + ".%03dZ" % int((t % 1) * 1000)


def parse_iso(at: str) -> float:
    """ISO (UTC) -> epoch seconds. 0.0 on anything unparseable, so a torn row ages out
    rather than becoming a confident timestamp.

    `calendar.timegm`, NOT `time.mktime`. mktime is the inverse of LOCALTIME; pairing it
    with a Z stamp is a lie exactly the size of the local UTC offset, and `- time.timezone`
    does not save it because that constant ignores DST. G-CLOCK exists for precisely this
    and caught this function within the hour of it being written — the same bug it was
    written for in 2026-07-13, in new code, which is what a gate is for."""
    try:
        head = (at or "")[:19]
        base = float(calendar.timegm(time.strptime(head, "%Y-%m-%dT%H:%M:%S")))
        ms = 0.0
        if len(at) > 20 and at[19] == ".":
            ms = float(at[20:23]) / 1000.0
        return base + ms
    except Exception:
        return 0.0


def dir_path() -> str:
    return os.environ.get("SP_TELEMETRY_DIR") or os.path.join(_ROOT, "var", "telemetry")


def day_path(day: str = "") -> str:
    return os.path.join(dir_path(), "%s.jsonl" % (day or time.strftime("%Y-%m-%d", time.gmtime())))


def _append(rows: List[Dict[str, Any]]) -> int:
    """THE write. Private on purpose — `ingest.record` is the door, and it is the door
    because the anon gate and the validation live there. A caller reaching past it would be
    the second path that this repo's §0 exists to talk about."""
    if not rows:
        return 0
    by_day: Dict[str, list] = {}
    for r in rows:
        by_day.setdefault((r.get("at") or "")[:10], []).append(r)
    n = 0
    with _LOCK:
        os.makedirs(dir_path(), exist_ok=True)
        for day, group in by_day.items():
            with io.open(day_path(day), "a", encoding="utf-8", newline="\n") as f:
                for r in group:
                    f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
                    n += 1
    return n


def days() -> List[str]:
    """Every day that has samples, oldest first."""
    try:
        return sorted(f[:-6] for f in os.listdir(dir_path()) if f.endswith(".jsonl"))
    except OSError:
        return []


def read_day(day: str = "") -> List[Dict[str, Any]]:
    """One day's samples. A malformed line is SKIPPED and counted, never fatal: an
    instrument feed that stops answering because one row got torn mid-write is worse than
    an instrument feed with a hole in it. `verify()` is where the holes are reported."""
    p = day_path(day)
    out: List[Dict[str, Any]] = []
    try:
        with io.open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        out.append(row)
                except Exception:
                    continue
    except OSError:
        return []
    return out


def read_since(seconds: float, now: Optional[float] = None) -> List[Dict[str, Any]]:
    """Every sample in the last `seconds`, across day boundaries, oldest first."""
    now = time.time() if now is None else now
    cutoff = now_iso(now - max(0.0, seconds))     # same spelling both sides of the compare
    out: List[Dict[str, Any]] = []
    for day in days():
        # a whole day older than the cutoff cannot contain a sample newer than it
        if day < cutoff[:10]:
            continue
        out.extend(r for r in read_day(day) if (r.get("at") or "") >= cutoff)
    # STABLE, and that is load-bearing: on an exact millisecond tie the row appended later
    # stays later, which is what lets `latest()` break a tie toward the newer reading.
    out.sort(key=lambda r: r.get("at") or "")
    return out


def verify() -> Dict[str, Any]:
    """What the store looks like, including what is wrong with it. The panel's health row."""
    d, total, bad, kinds, sources = days(), 0, 0, {}, {}
    for day in d:
        try:
            with io.open(day_path(day), encoding="utf-8", errors="replace") as f:
                for line in f:
                    if not line.strip():
                        continue
                    total += 1
                    try:
                        row = json.loads(line)
                        kinds[row.get("kind", "?")] = kinds.get(row.get("kind", "?"), 0) + 1
                        sources[row.get("source", "?")] = sources.get(row.get("source", "?"), 0) + 1
                    except Exception:
                        bad += 1
        except OSError:
            continue
    return {"days": len(d), "first": d[0] if d else "", "last": d[-1] if d else "",
            "samples": total, "malformed": bad, "kinds": kinds, "sources": sources,
            "unknown_kinds": sorted(k for k in kinds if k not in KINDS and k != "?")}


def prune(keep_days: int) -> Dict[str, Any]:
    """Remove whole days older than `keep_days`. THE ONLY REMOVER, and it is never called
    from a write or a read — retention is an operator decision, taken once, in the open.
    `keep_days <= 0` means keep everything and is the default everywhere."""
    if keep_days <= 0:
        return {"removed": [], "why": "retention is off; everything is kept"}
    d = days()
    if len(d) <= keep_days:
        return {"removed": [], "why": "nothing is older than the window"}
    gone = []
    for day in d[:-keep_days]:
        try:
            os.remove(day_path(day))
            gone.append(day)
        except OSError:
            pass
    return {"removed": gone, "kept": d[-keep_days:]}
