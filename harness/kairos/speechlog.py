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
