"""rank — the spine-aware rerank over deep-recall candidates (2026-08-22, D §3).

Cosine finds the SIMILAR moment; the spine's own signals find HER moment: the words of the
question, how recent the day is, and whether the moment backs a fact she actually holds. Pure,
deterministic, fixture-tested (G-AUX-LIBRARIAN §4). Off = raw cosine order (aux.spine_rerank).
"""
from __future__ import annotations

import calendar
import re
import time
from typing import Iterable, List, Optional

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

_W = re.compile(r"[a-z0-9']{3,}")
HALF_LIFE_DAYS = 90.0
W_OVERLAP, W_RECENCY, W_BOND = 0.25, 0.10, 0.15


def _toks(s: str) -> set:
    return set(_W.findall((s or "").lower()))


def _recency(day: str, now: Optional[float] = None) -> float:
    # calendar.timegm, NOT time.mktime (2026-08-22, G-CLOCK had been red on this line).
    # The day comes off a transcript filename and is UTC; mktime is the inverse of
    # LOCALTIME, so on this box (UTC+10) every archive chunk was aged ten hours wrong and
    # the recency term of spine_rerank — which is armed by default — leaned that far in
    # the wrong direction on every deep-recall candidate. Same bug G-CLOCK was written for
    # after it cost the registry ten hours; the gate caught the second instance and the
    # gate was red for long enough that nobody read it.
    try:
        t = calendar.timegm(time.strptime((day or "")[:10], "%Y-%m-%d"))
    except Exception as _swx:
        _swallowed(_swlog, "_recency", _swx, lane="sidecar")
        return 0.0
    age = max(0.0, ((now or time.time()) - t) / 86400.0)
    return 0.5 ** (age / HALF_LIFE_DAYS)


def testimony_bond(text: str, live_texts: Iterable[str]) -> float:
    """1.0 when the chunk carries a live fact (>= 0.5 of the fact's tokens), else 0."""
    ct = _toks(text)
    if not ct:
        return 0.0
    for f in live_texts:
        ft = _toks(f)
        if len(ft) >= 3 and len(ft & ct) / len(ft) >= 0.5:
            return 1.0
    return 0.0


def spine_rerank(query: str, hits: List[dict], k: int, live_texts: Optional[Iterable[str]] = None,
                 now: Optional[float] = None) -> List[dict]:
    """hits: [{day, source, text, score(cos)}] -> top-k by the hybrid score; each hit gains
    `rank` {cos, overlap, recency, bond, score}."""
    qt = _toks(query)
    lt = list(live_texts or [])
    out = []
    for h in hits:
        ct = _toks(h.get("text", ""))
        overlap = (len(qt & ct) / len(qt)) if qt else 0.0
        rec = _recency(h.get("day", ""), now)
        bond = testimony_bond(h.get("text", ""), lt)
        cos = float(h.get("score", 0.0))
        score = cos + W_OVERLAP * overlap + W_RECENCY * rec + W_BOND * bond
        h2 = dict(h)
        h2["rank"] = {"cos": round(cos, 4), "overlap": round(overlap, 3),
                      "recency": round(rec, 3), "bond": bond, "score": round(score, 4)}
        out.append(h2)
    out.sort(key=lambda h: -h["rank"]["score"])
    return out[:max(1, k)]
