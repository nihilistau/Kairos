"""looking.py — she is looking something up, or she is not.

ONE SEAM for every outward look: web_search (seconds, shallow) and research
(minutes, Grok). The room reads this. A chip that says "researching" while
nothing is running is a lie; a look that finishes with no receipt is a look
that did not happen.

In-flight is process-local. The receipt file is the ledger: append-only,
never rewritten, never deleted. The window reads the ledger; she cannot
edit it through this module.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Optional

from harness.loud import swallowed as _swallowed

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
# ── SCOPED TO THE TURN'S THREAD, NOT THE PROCESS (2026-08-24 audit, B10) ────────────
# `_NOW` was THE in-flight look and `_LISTENERS` was every subscriber, process-wide,
# under a ThreadingHTTPServer — trap 3(b), state with no owner, in the chip lane. Two
# overlapping looks (a chat turn and a kairos speak-up) meant the second `end()` built
# its ledger row from `base = {}` — losing the query, the kind and the seconds — and a
# chip from one session's turn was emitted onto EVERY concurrent session's SSE stream.
# A look begins and ends on the thread that runs the tool, and each turn subscribes
# from the thread that drains it, so the thread id IS the turn scope: `_NOW` is a map
# keyed by it, and a listener registered from a thread hears that thread's looks only.
# `_LAST` stays global (a status readout of "her most recent look" is genuinely
# process-wide); his_search never touched any of this and still does not.
_NOW: dict = {}                    # thread id -> the in-flight look
_LAST: Optional[dict] = None
_LISTENERS: dict = {}              # thread id -> [listeners]


def _root() -> str:
    return os.environ.get("SP_RESEARCH_RECEIPTS") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "var", "research")


def _looks_path() -> str:
    return os.path.join(_root(), "looks.jsonl")


def subscribe(fn):
    """SSE registers here, FROM THE THREAD THAT RUNS THE TURN — the subscription is
    scoped to that thread's looks (see the note on _NOW/_LISTENERS above)."""
    tid = threading.get_ident()
    with _LOCK:
        _LISTENERS.setdefault(tid, []).append(fn)
    def unsub() -> None:
        with _LOCK:
            lst = _LISTENERS.get(tid, [])
            if fn in lst:
                lst.remove(fn)
            if not lst:
                _LISTENERS.pop(tid, None)
    return unsub


def _emit(ev: dict) -> None:
    with _LOCK:
        fns = list(_LISTENERS.get(threading.get_ident(), ()))
    for fn in fns:
        try:
            fn(dict(ev))
        except Exception as _swx:
            _swallowed(logger, "_emit", _swx, lane="skills")


def begin(kind: str, query: str, by: str = "her") -> dict:
    """A look has STARTED. Pulse and the taskbar read this.

    `by` is WHO is looking. Every tool call of hers defaults to "her"; the room's
    manual search/research boxes pass "him". The distinction is the operator's ask
    (2026-08-21): one shared ledger both can read, but hers stay hers — her
    thoughts, her activities — and a chip says whose each row is."""
    row = {
        "kind": (kind or "look").strip() or "look",
        "query": (query or "").strip()[:240],
        "by": (by or "her").strip() or "her",
        "started": time.time(),
        "phase": "start",
    }
    with _LOCK:
        _NOW[threading.get_ident()] = dict(row)
    _emit({"phase": "start", "kind": row["kind"], "q": row["query"],
           "tool": row["kind"]})
    return row


def end(ok: bool, summary: str = "", sources: Optional[list] = None,
        title: str = "") -> dict:
    """A look has FINISHED. Written to the ledger, then cleared from in-flight."""
    global _LAST
    with _LOCK:
        base = dict(_NOW.pop(threading.get_ident(), None) or {})
    row = {
        **base,
        "ok": bool(ok),
        "ended": time.time(),
        "seconds": round(time.time() - float(base.get("started") or time.time()), 1),
        "title": (title or (base.get("query") or "")[:80]).strip(),
        "summary": (summary or "")[:800],
        "sources": list(sources or [])[:8],
        "phase": "done",
    }
    if "kind" not in row:
        row["kind"] = "look"
    if "query" not in row:
        row["query"] = row["title"]
    _write(row)
    with _LOCK:
        _LAST = dict(row)
    _emit({"phase": "done", "kind": row.get("kind") or "look",
           "q": row.get("query") or row.get("title") or "",
           "tool": row.get("kind") or "look",
           "ok": row["ok"], "title": row.get("title") or ""})
    return row


def his_search(query: str, n: int = 6) -> dict:
    """The room's manual search box (2026-08-21, the operator's ask). Runs the SAME engine her
    web_search uses — picker, live knob, Wikipedia blend, all of it — but it is HIS
    look: the row is written `by: him`, and _NOW/_LAST are never touched, because
    the taskbar's "she is looking up…" chip reports HER activity and must not wear
    his clicks. She can still read these rows (my_research marks them "(his)")."""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query"}
    from harness.skills import search as S
    t0 = time.time()
    try:
        hits = S.search_web(q, max(1, min(int(n or 6), 10)))
    except Exception as exc:
        hits = []
        err = str(exc)[:200]
    else:
        err = ""
    summary = "\n".join(
        "%s — %s" % (h.get("title") or "?", (h.get("snippet") or h.get("extract") or "")[:160])
        for h in hits[:6])
    row = {
        "kind": "web_search", "query": q[:240], "by": "him",
        "started": t0, "ended": time.time(),
        "seconds": round(time.time() - t0, 1),
        "ok": bool(hits), "title": q[:80],
        "summary": (summary or err or "(nothing came back)")[:800],
        "sources": [h.get("url") for h in hits[:8] if h.get("url")],
        "phase": "done",
    }
    _write(row)
    return {"ok": True, "hits": hits, "row": row}


def his_research(query: str, depth: str = "normal") -> dict:
    """The room's manual research box. Same backend her research tool uses, but NOT
    gated on SP_RESEARCH — that knob governs whether SHE may reach for the paid
    tier unprompted; the operator clicking a button IS the authorization. Writes
    `by: him` onto the receipt so the shared window says whose it was, and leaves
    _NOW/_LAST alone for the same reason as his_search."""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty question"}
    from harness.skills import research as R
    b = R.backend()
    if not b.available():
        return {"ok": False, "error": "no %s backend available on this machine" % b.name}
    if depth not in R.DEPTHS:
        depth = "normal"
    try:
        ans = b.ask(q, depth)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}
    # the receipt already exists (b.ask writes it); stamp whose it was
    if ans.receipt and os.path.isfile(ans.receipt):
        try:
            with open(ans.receipt, encoding="utf-8") as f:
                rec = json.load(f)
            rec["by"] = "him"
            with open(ans.receipt, "w", encoding="utf-8") as f:
                json.dump(rec, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            # WHOSE LOOKUP IT WAS is the fact the his/hers chips render from. A receipt
            # that silently keeps the wrong `by` is a lookup of his filed as one of hers.
            logger.warning("[looking] could not stamp %r as his (%s: %s) — the ledger will "
                           "show it as hers", os.path.basename(ans.receipt),
                           type(exc).__name__, exc)
            _swallowed(logger, "looking receipt stamp", exc, lane="looking")
    return {"ok": ans.ok, "text": ans.text, "sources": ans.sources,
            "seconds": ans.seconds, "receipt": ans.receipt,
            "provenance": ans.provenance}


def status() -> dict:
    """What the pulse and the research window need. Never raises."""
    from harness.skills import research as R
    from harness.skills import search as S
    with _LOCK:
        # ANY thread's in-flight look: the taskbar asks "is she looking something up",
        # not "is this thread" — the map is per-turn, the readout is process-wide.
        inflight = next((dict(v) for v in _NOW.values()), None)
        last = dict(_LAST) if _LAST else None
    # Process-local last dies on bounce. The ledger does not. HERS ONLY here:
    # the taskbar chip this feeds says what SHE looked up, and his manual rows
    # (by=him, 2026-08-21) must not wear her face — his search showed up as
    # "looked up" on the taskbar within a minute of the run route landing.
    if last is None:
        looks = [r for r in list_looks(5) if r.get("by") != "him"]
        last = looks[0] if looks else None
    return {
        "inflight": inflight,
        "last": last,
        "armed": bool(R.ARMED),
        "backend": R.backend().name,
        "backend_available": R.backend().available(),
        "search_backend": S.backend().name,
        "search_engines": S.status()["engines"],
    }


def my_research(n: int = 12) -> str:
    """What you have actually looked up. The ledger, not your memory of looking.

    Titles and short summaries of web_search and research calls that returned.
    If this is empty, you have not looked anything up — say that, do not invent."""
    try:
        n = max(1, min(int(n or 12), 40))
    except (TypeError, ValueError):
        n = 12
    rows = list_looks(n)
    if not rows:
        return ("(you have not looked anything up yet — no web_search and no "
                "research call has returned. Say that plainly. Do not invent a finding.)")
    lines = []
    for r in rows:
        title = (r.get("title") or r.get("query") or "(untitled)").strip()
        kind = r.get("kind") or "look"
        ok = "ok" if r.get("ok") is not False else "failed"
        summ = (r.get("summary") or "").strip().replace("\n", " ")
        if len(summ) > 280:
            summ = summ[:277] + "..."
        # HIS lookups are in the shared ledger too (the room's manual boxes). She
        # may read and use them — but they are his searches, not her activity, and
        # the marker keeps her from narrating his clicks as things she did.
        his = " — his search, not yours" if (r.get("by") == "him") else ""
        lines.append("- [%s %s%s] %s\n  %s" % (kind, ok, his, title,
                                               summ or "(no text came back)"))
    return ("(these are your notes — things you actually looked up, not memories "
            "and not things he told you. Rows marked 'his search' are things HE "
            "looked up in the room; you may use them, but they are not your doing)"
            "\n\n" + "\n".join(lines))


def looking_tools():
    """Always offered. The ledger exists whether the Grok tier is armed or not."""
    try:
        from harness.toolcore.tools import ToolSpec
        return [ToolSpec.from_callable(my_research)]
    except Exception as _swx:
        _swallowed(logger, "looking_tools", _swx, lane="skills")
        return []


def list_looks(n: int = 40) -> list:
    """Newest first. Receipts (research) plus looks.jsonl (every outward look)."""
    rows: list[dict] = []
    root = _root()
    looks = _looks_path()
    if os.path.isfile(looks):
        try:
            with open(looks, encoding="utf-8", errors="replace") as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        rec = json.loads(ln)
                    except Exception as _swx:
                        _swallowed(logger, "list_looks", _swx, lane="skills")
                        continue
                    # research() also writes r_*.json, which is the fuller receipt.
                    # The jsonl copy is the audit that a look happened; the window
                    # prefers the receipt so the same look is not listed twice.
                    if rec.get("kind") == "research":
                        continue
                    rec.setdefault("by", "her")   # rows predating 2026-08-21 are all hers
                    rows.append(rec)
        except OSError:
            pass
    if os.path.isdir(root):
        for name in os.listdir(root):
            if not (name.startswith("r_") and name.endswith(".json")):
                continue
            p = os.path.join(root, name)
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    rec = json.load(f)
            except Exception as _swx:
                _swallowed(logger, "list_looks", _swx, lane="skills")
                continue
            rows.append({
                "kind": "research",
                "query": rec.get("question") or "",
                "title": (rec.get("question") or "")[:80],
                "summary": (rec.get("text") or "")[:800],
                "sources": rec.get("sources") or [],
                "ok": rec.get("ok", True),
                "seconds": rec.get("seconds") or 0,
                "ended": _mtime(p),
                "receipt": p,
                "phase": "done",
                "provenance": rec.get("provenance") or "",
                "by": rec.get("by") or "her",
            })
    rows.sort(key=lambda r: float(r.get("ended") or r.get("started") or 0), reverse=True)
    return rows[:n]


def _mtime(p: str) -> float:
    try:
        return os.path.getmtime(p)
    except OSError:
        return 0.0


def _write(row: dict) -> None:
    # ANONYMOUS MODE (2026-08-23). The receipt ledger carries the QUERY and 800 characters
    # of what came back, which over a private evening is the most legible record in the
    # system of what was being talked about. Held at the write and not at the two callers,
    # because both of them — her look and his — are recording. The chip still moves: the
    # in-flight state is process-local (`_NOW`/`_LAST`), so the room still shows her
    # looking something up; only the durable receipt is held.
    from harness.control import anon as _anon
    if _anon.holds("lookup.receipt"):
        return
    p = _looks_path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass
