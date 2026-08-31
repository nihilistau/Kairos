"""decisions — the operator's queue: things only HE can settle, with a button each.

WHY THIS EXISTS. A running companion accumulates questions that are not engineering and
not hers: should this knob be armed, is this row mislabelled, should she keep doing X.
Until now they lived in three bad places — a reply that scrolls away, a ledger row that
says "owed" forever, or my own head between sessions. None of those is a queue, and none
of them tells you what is waiting.

WHAT IT IS NOT. It is **not her memory**. Nothing here reaches her prefix, her recall, her
journal or her sense of herself; `remember()` never sees it. It is not the ledger either —
`docs/OFF-BY-DEFAULT.md` records what is off and WHY, permanently, for a reader; this
records what is UNDECIDED, transiently, for a decider. When a decision lands, the ledger is
usually where its consequence gets written down.

THE STORE, following the semindex discipline for the same reasons:
  - APPEND-ONLY. A decision is never edited or removed; deciding APPENDS a verdict row
    with the same id. `items()` folds them, last verdict wins. So "what did he choose and
    when, and did he change his mind" is answerable forever.
  - Its own file (`var/decisions.jsonl`), beside the registry, never inside it.
  - Never blocks and never raises out: a broken queue costs a panel, never a turn.

SHAPES. `kind` says what happens on submit and is the whole contract with the panel:
  "once"    a one-off. The answer is the deliverable; I read it and do the work.
  "route"   the answer is applied by code the moment it is chosen (a knob, a relabel).
  "note"    a judgement recorded for the record with nothing to execute.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid

from harness.loud import swallowed as _swallowed

_logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
KINDS = ("once", "route", "note")


def path() -> str:
    """Beside the registry, so a sandbox inherits it for free via SP_RECALL_REGISTRY —
    the same trick narrative.md uses, and the reason gates need no new env."""
    p = os.environ.get("SP_DECISIONS", "")
    if p:
        return p
    reg = os.environ.get("SP_RECALL_REGISTRY", "")
    d = os.path.dirname(reg) if reg else ""
    return os.path.join(d, "decisions.jsonl") if d else ""


def _append(row: dict) -> bool:
    p = path()
    if not p:
        return False
    try:
        with _LOCK:
            d = os.path.dirname(p)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except Exception as exc:
        # `False` is honest and better than `pass` — but it says THAT it failed and never
        # WHY, and a decision that was never recorded is one nobody can walk back to.
        _logger.warning("[decisions] a decision row was not recorded (%s: %s)",
                        type(exc).__name__, exc)
        _swallowed(_logger, "decisions append", exc, lane="decisions")
        return False


def _read() -> list:
    p = path()
    if not p or not os.path.exists(p):
        return []
    out = []
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception as _swx:
        _swallowed(_logger, "_read", _swx, lane="skills")
        return []
    return out


def items() -> list:
    """Every decision, folded: the ASK plus its latest verdict. Newest ask last."""
    asks, verdicts = {}, {}
    for r in _read():
        if r.get("op") == "decide":
            verdicts[r.get("id")] = r
        elif r.get("id"):
            asks[r["id"]] = r
    out = []
    for i, a in asks.items():
        v = verdicts.get(i)
        out.append({**a,
                    "status": "decided" if v else "open",
                    "choice": (v or {}).get("choice", ""),
                    "note": (v or {}).get("note", ""),
                    "decided_at": (v or {}).get("at", "")})
    out.sort(key=lambda r: r.get("at", ""))
    return out


def open_items() -> list:
    return [r for r in items() if r["status"] == "open"]


def ask(title: str, body: str = "", options=None, kind: str = "once",
        area: str = "", detail: str = "", id: str = "") -> dict:
    """Put a question in the queue. Idempotent on `id`: re-asking an existing question
    does not duplicate it, so a boot-time seeder can run every start."""
    title = (title or "").strip()
    if not title:
        return {"ok": False, "error": "a decision needs a title"}
    # ANONYMOUS MODE (2026-08-23). A card carries a title and a body describing what came
    # up, which is a summary of the conversation filed under a different name. Guarded on
    # ask() and NOT on _append: decide() appends too, and holding HIS answer would be the
    # mode reaching past the record and into the room. Same rule as the wardrobe want —
    # the door that CREATES is held, the door that answers is not.
    from harness.control import anon as _anon
    if _anon.holds("decisions.card"):
        return {"ok": False, "error": _anon.WHY}
    if kind not in KINDS:
        return {"ok": False, "error": "kind must be one of %s" % (KINDS,)}
    ident = (id or "").strip() or uuid.uuid4().hex[:12]
    if any(r.get("id") == ident for r in items()):
        return {"ok": True, "id": ident, "already": True}
    row = {"id": ident, "op": "ask", "title": title, "body": body, "area": area,
           "detail": detail, "kind": kind,
           "options": list(options or ["yes", "no"]),
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    return {"ok": _append(row), "id": ident}


def decide(id: str, choice: str, note: str = "") -> dict:
    """Record his answer. APPENDS — the question and every previous verdict stay on disk,
    so changing his mind is history rather than a rewrite."""
    ident = (id or "").strip()
    cur = {r["id"]: r for r in items()}
    if ident not in cur:
        return {"ok": False, "error": "no decision %r" % ident}
    if choice not in cur[ident].get("options", []):
        return {"ok": False, "error": "choice must be one of %s"
                                      % (cur[ident].get("options"),)}
    ok = _append({"id": ident, "op": "decide", "choice": choice, "note": note or "",
                  "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return {"ok": ok, "id": ident, "choice": choice, "kind": cur[ident].get("kind")}
