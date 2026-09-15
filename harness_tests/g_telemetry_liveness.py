"""G-TELEMETRY-LIVENESS — a feed that stopped gets SAID, to him, once. OFFLINE.

WHY (2026-09-15). `heart_rate` stopped on 2026-09-01 and the watch entirely on 2026-09-04.
It was noticed fourteen days later, by an audit, and nothing was broken:

    G-TELEMETRY §2 — SILENCE IS AN ANSWER. Stale data -> she is told NOTHING.

§2 is right and is untouched. But it was enforced for exactly one audience: she went quiet
about his body, correctly, and nobody was told why — so "the watch is dead" and "he is
having a quiet afternoon" produced the same observable, which is none. An invariant enforced
on one side of a seam and on no other side is AGENTS.md §0, and this gate holds the other
side.

WHAT THIS HOLDS, in the order it is needed:

  §1 A FEED THAT STOPPED IS NAMED, with when it stopped and how busy it was the day it did.
     "22,470 rows on 08-31, nothing since" is the sentence that separates a dead instrument
     from one this setup never had.
  §2 SILENCE WHEN ALL IS WELL. report() is EMPTY when the feeds are current. A report that
     prints on a healthy boot is one nobody reads by the third week, and then §1 is dead too.
  §3 THE WHOLE STORE GOING QUIET IS ITS OWN ALARM, AND IT IS MEASURED IN HOURS. Ingest
     arrives through her gateway, so the stack being down stops EVERY kind at once and no
     per-kind check can see it. Hours, not days: the real outage was 30 h across a midnight,
     which a day-granularity check reads as "1 day" and shrugs at.
  §4 THE DAY FILES ARE UTC. store.day_path() names them from gmtime(); reading them back
     with localtime is wrong by the local offset and, at +10, makes every morning before
     10:00 report the newest file as a day stale. G-CLOCK's bug, one module further on.
  §5 A SENSOR HE NEVER OWNED IS NOT A FAULT. Absent kinds stay absent from the report.
  §6 IT NEVER REACHES HER. This module reads timestamps and counts rows. The moment it
     reports a VALUE it has become the second reader G-TELEMETRY §5 forbids.

MUTANTS, run in-gate: blind the per-kind threshold (§1 red), blind the store threshold
(§3 red), and put the clock back on localtime (§4 red).

    python harness_tests/g_telemetry_liveness.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _gate  # noqa: E402
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_telemetry_liveness")     # FIRST — redirects SP_TELEMETRY_DIR off his real one

import calendar  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402

from harness.telemetry import liveness  # noqa: E402

# A FIXED instant, so this gate says the same thing at 3am as at noon. UTC 2026-09-15 06:00.
NOW = calendar.timegm(time.strptime("2026-09-15 06:00", "%Y-%m-%d %H:%M"))
DAY = 86400.0


def _store(sub: str) -> str:
    """A fresh telemetry dir per section, under the sandbox."""
    p = os.path.join(SB, "tele-" + sub)
    os.makedirs(p, exist_ok=True)
    os.environ["SP_TELEMETRY_DIR"] = p
    return p


def _rows(kind: str, end_ts: float, n: int = 5, step: float = 300.0) -> None:
    """`n` rows of one kind, the newest at `end_ts`, written where the store would put them
    (day file named by the UTC date of the stamp — same rule as store._append)."""
    for i in range(n):
        t = end_ts - i * step
        at = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + ".000Z"
        p = os.path.join(os.environ["SP_TELEMETRY_DIR"], at[:10] + ".jsonl")
        with io.open(p, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"at": at, "kind": kind, "source": "watch", "value": 60.0},
                               sort_keys=True) + "\n")


# ── §1 a feed that stopped is named ──────────────────────────────────────────────────
_store("dead")
_rows("heart_rate", NOW - 14 * DAY, n=40)        # busy, then gone
_rows("sleep_confidence", NOW - 600, n=6)        # still arriving

f = liveness.feeds(now=NOW)
by = {r["kind"]: r for r in f["kinds"]}
lines = "\n".join(liveness.report(now=NOW))

check("§1 the stopped feed is in the report by name", "heart_rate" in lines, lines[:200])
check("§1 it is marked dark", bool(by.get("heart_rate", {}).get("dark")),
      "heart_rate=%r" % (by.get("heart_rate"),))
check("§1 it says HOW LONG", by.get("heart_rate", {}).get("days_ago") == 14,
      "days_ago=%r (expected 14)" % (by.get("heart_rate", {}).get("days_ago"),))
check("§1 it says how busy the last day was", by.get("heart_rate", {}).get("rows") == 40,
      "rows=%r (expected 40)" % (by.get("heart_rate", {}).get("rows"),))
check("§1 the live feed is NOT called dark", not by.get("sleep_confidence", {}).get("dark"),
      "sleep_confidence=%r" % (by.get("sleep_confidence"),))

# ── §5 a sensor he never owned is not a fault ────────────────────────────────────────
check("§5 a kind that never existed is absent, not 'never'",
      "spo2" not in by and "spo2" not in lines, sorted(by))

# ── §6 it never reaches her ──────────────────────────────────────────────────────────
check("§6 no reading VALUE is carried out of this module",
      all("value" not in r for r in f["kinds"]) and "60.0" not in lines,
      "a value in the liveness report is the second reader G-TELEMETRY §5 forbids")

# ── §2 silence when all is well ──────────────────────────────────────────────────────
_store("well")
_rows("heart_rate", NOW - 600, n=6)
_rows("sleep_confidence", NOW - 300, n=6)
well = liveness.report(now=NOW)
check("§2 a healthy store reports NOTHING", well == [], "report()=%r" % (well,))

# ── §3 the whole store going quiet, in hours ─────────────────────────────────────────
# 30 hours, straddling a midnight — the outage that actually happened (2026-09-14).
_store("down")
_rows("heart_rate", NOW - 30 * 3600, n=6)
_rows("sleep_confidence", NOW - 30 * 3600, n=6)
down = liveness.feeds(now=NOW)
dl = "\n".join(liveness.report(now=NOW))
check("§3 a 30-hour outage is reported", "NOTHING has arrived" in dl, dl[:200])
check("§3 it is measured in hours, not days", 29.0 < (down["store_age_h"] or 0) < 31.0,
      "store_age_h=%r" % (down["store_age_h"],))
check("§3 and a day-granularity check would have MISSED it",
      down["store_days_ago"] <= 1,
      "store_days_ago=%r — the point of §3 is that this number shrugs at a real outage"
      % (down["store_days_ago"],))

# ── §4 the day files are UTC ─────────────────────────────────────────────────────────
# This leg needs an instant where the local date and the UTC date DISAGREE, or there is
# nothing for a clock bug to be wrong ABOUT. Found by looking rather than by arithmetic on
# time.timezone: altzone/daylight describe the box's CURRENT dst state, not the one in
# force on the modelled day, and getting that backwards is the same class of bug as the
# one being tested.
def _disagreeing_instant():
    base = calendar.timegm(time.strptime("2026-09-15 00:00", "%Y-%m-%d %H:%M"))
    for h in range(24):
        t = base + h * 3600.0
        if (time.strftime("%Y-%m-%d", time.gmtime(t))
                != time.strftime("%Y-%m-%d", time.localtime(t))):
            return t
    return None


NOW_TZ = _disagreeing_instant()
if NOW_TZ is None:
    _gate.omit("§4 the day files are UTC",
               "this box runs at UTC, where the local and UTC dates never disagree and a "
               "localtime/gmtime swap is unobservable. Run east or west of Greenwich.")
    _gate.omit("MUTANT putting the clock back on localtime makes §4 go red",
               "same reason: nothing for the clock to be wrong about at UTC")
else:
    _store("clock")
    _rows("sleep_confidence", NOW_TZ - 600, n=4)
    c = liveness.feeds(now=NOW_TZ)
    newest = [r for r in c["kinds"] if r["last_day"] == c["last_row_day"]]
    check("§4 the newest day file reads 0 days old",
          bool(newest) and newest[0]["days_ago"] == 0,
          "at %s UTC / %s local — newest=%r today=%r"
          % (time.strftime("%Y-%m-%d %H:%M", time.gmtime(NOW_TZ)),
             time.strftime("%Y-%m-%d %H:%M", time.localtime(NOW_TZ)), newest, c["today"]))
    check("§4 'today' is the UTC date, matching how store.day_path names files",
          c["today"] == time.strftime("%Y-%m-%d", time.gmtime(NOW_TZ)),
          "today=%r gm=%r" % (c["today"], time.strftime("%Y-%m-%d", time.gmtime(NOW_TZ))))


# ── MUTANTS ──────────────────────────────────────────────────────────────────────────
# Each patches liveness ITSELF, the module that owns the constant, so the patch reaches the
# code under test rather than a copy of the name (mutants must patch the owner).
def _red(label: str, fn) -> bool:
    """True when the mutated module STOPS reporting the thing this gate says it reports."""
    try:
        return fn()
    except Exception as exc:                       # a crash is not a red, it is a broken gate
        print("   mutant %s raised %s" % (label, exc))
        return False


_store("dead")

_keep_dd = liveness.DARK_DAYS
liveness.DARK_DAYS = 9999
m1 = _red("dark-days", lambda: "heart_rate" not in "\n".join(liveness.report(now=NOW)))
liveness.DARK_DAYS = _keep_dd
check("MUTANT blinding DARK_DAYS makes §1 go quiet", m1,
      "with DARK_DAYS=9999 the stopped feed must vanish from the report, proving §1 is "
      "actually computed from it and not hard-coded")

_store("down")
_keep_sh = liveness.STORE_DARK_HOURS
liveness.STORE_DARK_HOURS = 9999
m2 = _red("store-hours", lambda: "NOTHING has arrived" not in "\n".join(liveness.report(now=NOW)))
liveness.STORE_DARK_HOURS = _keep_sh
check("MUTANT blinding STORE_DARK_HOURS makes §3 go quiet", m2,
      "with the store threshold blinded the 30-hour outage must stop being reported")


class _LocalClock(object):
    """time, with gmtime replaced by localtime — half of the original clock bug."""
    def __getattr__(self, n):
        return getattr(time, n)
    gmtime = staticmethod(time.localtime)


class _LocalCal(object):
    """calendar, with timegm replaced by mktime — the other half."""
    timegm = staticmethod(time.mktime)


if NOW_TZ is not None:
    _store("clock")
    _keep_t, _keep_c = liveness.time, liveness.calendar
    liveness.time, liveness.calendar = _LocalClock(), _LocalCal()

    def _clock_mutant():
        cc = liveness.feeds(now=NOW_TZ)
        nn = [r for r in cc["kinds"] if r["last_day"] == cc["last_row_day"]]
        # Red means: with the clock back on localtime the answer stops being right.
        return (not nn) or nn[0]["days_ago"] != 0 or cc["today"] != time.strftime(
            "%Y-%m-%d", time.gmtime(NOW_TZ))

    m3 = _red("clock", _clock_mutant)
    liveness.time, liveness.calendar = _keep_t, _keep_c
    check("MUTANT putting the clock back on localtime makes §4 go red", m3,
          "localtime/mktime must change the answer, or §4 is not testing the clock at all")

finish("G-TELEMETRY-LIVENESS")
