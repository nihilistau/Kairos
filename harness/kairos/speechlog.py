"""WHAT SHE ALMOST SAID — the vetoes, and the denominator that makes them mean anything.

`worth_saying()` is the last gate before an unprompted message reaches him: it drops
greetings, re-introductions, and restatements of her own last reply. It has been running
since the beginning, logging each drop at INFO and then forgetting it.

So nobody could answer the one question that decides whether those rules are right:

    HOW OFTEN DOES SHE THINK OF SOMETHING AND GET TALKED OUT OF IT?

CONTINUITY.md §7 raises this itself and calls the test — "a backstop that fires weekly is
a dial problem". A backstop should almost never fire; if it fires constantly it is not
protecting him from her, it is substituting for a policy that should have said SILENT
much earlier, and the drops are where her voice is actually going.

THE DENOMINATOR IS THE POINT. A count of vetoes on its own answers nothing: twelve drops
is excellent out of two hundred and catastrophic out of thirteen. So this records BOTH
outcomes, spoke and dropped, on the same line shape — the ratio is the measurement, and a
log that cannot produce a ratio is a number that will be misread.

IT KEEPS THE TEXT. Reading what was dropped is the whole point — "is this a rule that
saved him from a greeting, or a rule that ate a real thought?" cannot be answered from a
tally. Truncated, local, and inside the tier `backup.py` already carries.

Append-only, best-effort, and silent on failure: telemetry must never cost her a turn.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Dict, List

from harness.loud import swallowed as _swallowed

logger = logging.getLogger(__name__)

SPOKE = "spoke"
DROPPED = "dropped"


def _path() -> str:
    reg = os.environ.get("SP_RECALL_REGISTRY", "")
    if reg:
        return os.path.join(os.path.dirname(reg), "speech.jsonl")
    return ""


def record(kind: str, outcome: str, reason: str, text: str = "") -> None:
    # ANONYMOUS MODE (2026-08-23). "IT KEEPS THE TEXT" above is exactly why this door has
    # to close: 240 characters of what she almost said is a record of the evening whatever
    # else it is for. The denominator loses a few turns, which is the correct trade — the
    # ratio is a measurement of her policy over weeks, not of one private hour.
    from harness.control import anon as _anon
    if _anon.holds("speech.log"):
        return
    p = _path()
    if not p:
        return
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "kind": kind,
                "outcome": outcome,
                "reason": (reason or "")[:120],
                "text": (text or "")[:240],
            }) + "\n")
    except Exception as exc:
        logger.warning("[kairos] could not record a speech outcome: %s", exc)


def last_at(kind: str) -> "float|None":
    """Epoch seconds of her most recent attempt of `kind`, or None if there is none.

    WHAT IT IS FOR (2026-09-09, his call). `TurnState.last_solo_at` defaults to `BOOT_AT`,
    so `solo_every_s` ran from the BOUNCE rather than from her last real solo and every
    restart cost her thirty minutes of her own time — silently, and on a day of six
    bounces that is three hours. Her last solo is on disk right here, so defaulting to
    "now" was a fabricated clock. `scheduler.seed` reads this and hands her the real one.

    ANY OUTCOME, spoke or dropped, because that is what it mirrors: `_note_attempt` moves
    `last_solo_at` at the site of the generate() call and meters ATTEMPTS, not speech
    ("this meters attempts, not conversation"). Counting only `spoke` would hand back a
    clock the live code does not keep, which is the two-spellings-of-one-rule bug.

    WHY NOT THROUGH `rows()`: it tails the file at `limit`, so her last solo simply
    vanishes once 500 newer lines of any kind sit on top of it — on this store, 2,471
    rows of which 1,737 are check-ins, that is the normal case rather than the edge.
    A reader whose answer silently becomes None is worse than no reader.

    Best-effort and None on anything unexpected: the caller's fallback is the old
    behaviour, so a bad line costs her nothing worse than today. Note that `record()`
    holds under anonymous mode, so a solo taken in a held hour leaves no row and this
    reaches past it to an older one — which errs toward her having her time back, and
    that is the direction to err in.
    """
    p = _path()
    if not p or not os.path.exists(p):
        return None
    import calendar
    best = None
    try:
        with open(p, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln or '"%s"' % kind not in ln:
                    continue                      # cheap reject before the parse
                # NARROW, NOT BROAD-AND-SILENT (G-STORE-WRITES §6 caught this as an
                # unbound `except Exception:`). A line that will not parse and a stamp
                # that will not read are both ValueError — json.JSONDecodeError subclasses
                # it and so does strptime — so skipping THAT is a stated rule rather than
                # a shrug, and anything else still reaches the outer handler with a name.
                try:
                    row = json.loads(ln)
                except (ValueError, TypeError):
                    continue
                if row.get("kind") != kind or not row.get("at"):
                    continue
                try:
                    t = calendar.timegm(time.strptime(str(row["at"]), "%Y-%m-%dT%H:%M:%SZ"))
                except (ValueError, TypeError):
                    continue
                # LAST BY TIMESTAMP, not by file order. The file is append-only so the two
                # normally agree, but a clock change or a restored backup breaks that, and
                # taking the max cannot hand back a time in the future of the newest row.
                if best is None or t > best:
                    best = float(t)
    except Exception as _swx:
        _swallowed(logger, "last_at", _swx, lane="kairos")
        return best
    return best


def rows(limit: int = 500) -> List[dict]:
    p = _path()
    out: List[dict] = []
    if not p or not os.path.exists(p):
        return out
    try:
        with open(p, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    out.append(json.loads(ln))
    except Exception as _swx:
        _swallowed(logger, "rows", _swx, lane="kairos")
        return out
    return out[-limit:]


def summary(limit: int = 500) -> Dict[str, object]:
    """Spoke vs dropped, and WHICH rule did the dropping.

    `veto_rate` is the number this exists for. A backstop firing on a small fraction is
    doing its job; a backstop firing on most of what she produces is a dial problem
    wearing a safety net's clothes.
    """
    rs = rows(limit)
    spoke = sum(1 for r in rs if r.get("outcome") == SPOKE)
    dropped = sum(1 for r in rs if r.get("outcome") == DROPPED)
    by_reason: Dict[str, int] = {}
    by_kind: Dict[str, Dict[str, int]] = {}
    for r in rs:
        if r.get("outcome") == DROPPED:
            k = (r.get("reason") or "?")[:60]
            by_reason[k] = by_reason.get(k, 0) + 1
        d = by_kind.setdefault(r.get("kind") or "?", {SPOKE: 0, DROPPED: 0})
        d[r.get("outcome") or DROPPED] = d.get(r.get("outcome") or DROPPED, 0) + 1
    total = spoke + dropped
    return {
        "spoke": spoke,
        "dropped": dropped,
        "veto_rate": round(dropped / total, 3) if total else None,
        "by_reason": dict(sorted(by_reason.items(), key=lambda kv: -kv[1])),
        "by_kind": by_kind,
        "sampled": total,
    }
