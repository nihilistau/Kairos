"""THE LEDGER — the standing list of what we are doing, what we parked, and what we noticed.

A working session produces three kinds of thing and this repo has only ever kept the first:
the work itself goes into commits, but **the plan** lives in a plan file that goes stale, and
**everything noticed in passing** lives in a paragraph at the end of a reply that scrolls away.
Tonight alone that channel carried: the shared browser (deferred on purpose), replacing the
avatar's vector art with a Grok-driven image set, `g_narrative` failing on a Windows console
encoding, and fourteen unindexed gates — every one of them real, none of them anywhere a
future session would look. `docs/OFF-BY-DEFAULT.md` fixed exactly this problem for knobs. This
fixes it for everything else.

WHO OWNS IT. Claude maintains it; the operator may add, edit, and remove rows through the room.
Both are recorded in `owner`, because "who raised this" is the first thing you want to know
about a row you are reading three weeks later.

NOTHING IS DELETED. `drop()` sets status `dropped` and keeps the row, for the same reason
`forget()` tombstones rather than unlinking: a dropped idea that keeps coming back is itself
information, and a ledger you can quietly rewrite is a ledger nobody can trust. The room hides
dropped rows by default — hidden is not gone.

KIND AND STATUS ARE COMMITTED FINITE TABLES, not free text. An unknown value is refused, not
coerced. Free-text status fields are how you end up with `done`, `Done`, `complete` and
`finished` all meaning the same thing and none of them countable.

Storage is `var/room/ledger.json`, written atomically. It sits in `var/` deliberately: this is
mutable operator state of the same class as `var/tuning.json` and the fact registry, not
documentation — so it is gitignored, and `harness/control/backup.py` carries it in the hourly
snapshot instead. The rows point AT documents in git; they are not one.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# What a row IS. Ordered — the room renders sections in this order.
KINDS = ("plan", "parked", "noticed", "idea", "risk")
KIND_BLURB = {
    "plan":    "committed work, in flight or next",
    "parked":  "agreed to do, deliberately not now",
    "noticed": "found in passing and NOT touched",
    "idea":    "worth considering, nobody has committed",
    "risk":    "known sharp edge — not a bug yet",
}

# Where a row IS. `dropped` is the terminal state that replaces deletion.
STATUSES = ("open", "doing", "done", "dropped")

OWNERS = ("claude", "sam")

_MAX_TITLE = 200
_MAX_BODY = 8000


def path() -> str:
    return os.environ.get("SP_LEDGER_FILE") or os.path.join(_ROOT, "var", "room", "ledger.json")


def _now() -> int:
    return int(time.time())


def _read() -> Dict[str, Any]:
    p = path()
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("entries"), list):
            return d
    except Exception:
        pass
    # A missing or unreadable ledger is an EMPTY ledger, never an exception: the room
    # must render on a fresh clone, and a panel that throws takes its neighbours with it.
    return {"version": 1, "entries": []}


def _write(d: Dict[str, Any]) -> None:
    p = path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)          # atomic: a torn ledger is worse than a stale one


def _clean(e: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce one row to the schema. Refuses on the finite fields, truncates on the free ones."""
    kind = str(e.get("kind") or "noticed").strip().lower()
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r} (want one of {', '.join(KINDS)})")
    status = str(e.get("status") or "open").strip().lower()
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r} (want one of {', '.join(STATUSES)})")
    owner = str(e.get("owner") or "claude").strip().lower()
    if owner not in OWNERS:
        raise ValueError(f"unknown owner {owner!r} (want one of {', '.join(OWNERS)})")
    title = str(e.get("title") or "").strip()[:_MAX_TITLE]
    if not title:
        raise ValueError("a row needs a title")
    refs = [str(r).strip()[:300] for r in (e.get("refs") or []) if str(r).strip()][:12]
    return {
        "id": str(e.get("id") or uuid.uuid4().hex[:12]),
        "kind": kind,
        "status": status,
        "owner": owner,
        "title": title,
        "body": str(e.get("body") or "").strip()[:_MAX_BODY],
        "refs": refs,
        "pinned": bool(e.get("pinned")),
        "created": int(e.get("created") or _now()),
        "updated": int(e.get("updated") or _now()),
    }


def all_entries(include_dropped: bool = True) -> List[Dict[str, Any]]:
    rows = []
    for e in _read()["entries"]:
        try:
            rows.append(_clean(e))
        except Exception:
            continue        # a malformed row is skipped, never fatal to the panel
    if not include_dropped:
        rows = [r for r in rows if r["status"] != "dropped"]
    # pinned first, then most-recently-touched. Stable enough that the panel does not
    # reshuffle under the cursor on every 30s poll.
    rows.sort(key=lambda r: (not r["pinned"], -r["updated"]))
    return rows


def add(**kw: Any) -> Dict[str, Any]:
    row = _clean(kw)
    d = _read()
    d["entries"].append(row)
    _write(d)
    return row


def edit(entry_id: str, **kw: Any) -> Optional[Dict[str, Any]]:
    d = _read()
    for i, e in enumerate(d["entries"]):
        if str(e.get("id")) != str(entry_id):
            continue
        merged = dict(e)
        for k, v in kw.items():
            if k in ("kind", "status", "owner", "title", "body", "refs", "pinned") and v is not None:
                merged[k] = v
        merged["updated"] = _now()
        row = _clean(merged)
        row["created"] = int(e.get("created") or row["created"])   # created never moves
        d["entries"][i] = row
        _write(d)
        return row
    return None


def drop(entry_id: str) -> Optional[Dict[str, Any]]:
    """The remove button. Status only — the row stays. See the module docstring."""
    return edit(entry_id, status="dropped")


def counts() -> Dict[str, int]:
    rows = all_entries()
    out = {"total": len(rows)}
    for s in STATUSES:
        out[s] = sum(1 for r in rows if r["status"] == s)
    for k in KINDS:
        out[k] = sum(1 for r in rows if r["kind"] == k and r["status"] != "dropped")
    return out


# ── HEALTH ───────────────────────────────────────────────────────────────────────
# What the gates last said, and HOW LONG AGO. Read from var/sem/receipts/*.json, which
# 38 gates already write; nothing is executed here. That is the honest thing a poll
# every 30 seconds can offer — running the suite on a page load would be a lie about
# cost, and a "green" with no timestamp is the same lie G-PF-PERSONA was telling.

def gate_health(stale_days: int = 7) -> Dict[str, Any]:
    d = os.path.join(_ROOT, "var", "sem", "receipts")
    rows: List[Dict[str, Any]] = []
    try:
        names = sorted(os.listdir(d))
    except Exception:
        names = []
    now = time.time()
    for n in names:
        if not n.endswith(".json"):
            continue
        fp = os.path.join(d, n)
        try:
            with open(fp, "r", encoding="utf-8") as f:
                r = json.load(f)
            age = now - os.path.getmtime(fp)
        except Exception:
            continue
        # NOT EVERY RECEIPT IS A VERDICT. var/sem/receipts/ also holds MEASUREMENTS —
        # voice_baseline and voice_26b record medians and knob settings and assert
        # nothing. Defaulting their missing pass/fail to zero counted them as green,
        # which inflates the tally with rows that never had an opinion. A thing that
        # did not claim to pass must not be counted as passing.
        verdict = ("pass" in r) or ("fail" in r)
        fail = int(r.get("fail") or 0)
        rows.append({
            "name": str(r.get("name") or n[:-5]),
            "kind": "gate" if verdict else "measurement",
            "pass": int(r.get("pass") or 0),
            "fail": fail,
            "age_h": round(age / 3600.0, 1),
            # A receipt is a RECORD OF A PAST RUN, not a current verdict. Old enough and
            # it says nothing about the tree as it stands, so say that rather than green.
            "stale": age > stale_days * 86400,
            "ok": verdict and fail == 0,
        })
    gates = [r for r in rows if r["kind"] == "gate"]
    red = [r for r in gates if not r["ok"]]
    stale = [r for r in gates if r["stale"]]
    return {
        "receipts": rows,
        "total": len(gates),
        "measurements": len(rows) - len(gates),
        "red": len(red),
        "red_names": [r["name"] for r in red],
        "stale": len(stale),
        "note": ("last recorded run per gate, not a live verdict — "
                 "a receipt older than %d days is marked stale; "
                 "measurement receipts assert nothing and are counted separately"
                 % stale_days),
    }
