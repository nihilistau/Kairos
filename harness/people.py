"""PEOPLE — who and what she knows: people, animals, places, things (2026-11-26, design §2, §7b).

One append-only log per companion home (`people` in harness/home.py): every change is a NEW
line, the current state of a person is the last line for their id, and nothing is ever
removed — retiring is a status, the same law as her memory.

    {"op": "put", "row": {"id": "p1", "names": ["Sam", "Ray"], "kind": "person",
                          "pronouns": "he/him/his", "relation": "the one she lives with",
                          "notes": "", "user": true, "handle": "user1", "status": "live",
                          "proposed_by": "", "at": "..."}}
    {"op": "active", "id": "p1", "at": "..."}

USERS are people with `user: true` and a handle (user1, user2…). The ACTIVE user is who she
is talking to; serve.py reads it at launch and hands the name and pronouns to harness/user.py
— so switching users is a gateway restart, which is also what her cached prefix (it names
him) requires anyway.

PROPOSED people come from her (`meet`): a row with status "proposed" that does not count as
anyone until he confirms it in the People window. Her guess about who someone is must not
become a person on her word alone.

Gate: G-PEOPLE (harness_tests/g_people.py).
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Dict, List, Optional, Tuple

from harness import home as H

KINDS = ("person", "pet", "place", "thing", "org")
STATUSES = ("live", "proposed", "retired")
FIELDS = ("names", "kind", "pronouns", "relation", "notes", "user", "handle", "status",
          "proposed_by", "private")


class PeopleError(ValueError):
    pass


def path() -> str:
    return H.path("people")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _append(ev: dict) -> None:
    p = path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({**ev, "at": _now()}, ensure_ascii=False) + "\n")


def load() -> Tuple[Dict[str, dict], str]:
    """(id -> current row, active user id). A malformed line is skipped, never fatal."""
    rows: Dict[str, dict] = {}
    active = ""
    try:
        with open(path(), encoding="utf-8") as f:
            for line in f:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("op") == "put" and isinstance(ev.get("row"), dict) and ev["row"].get("id"):
                    rows[ev["row"]["id"]] = ev["row"]
                elif ev.get("op") == "active":
                    active = str(ev.get("id") or "")
    except OSError:
        pass
    if active and not (rows.get(active, {}).get("user") and rows[active].get("status") == "live"):
        active = ""
    return rows, active


def everyone(*, include_retired: bool = False) -> List[dict]:
    rows, active = load()
    out = [dict(r, active=(r["id"] == active)) for r in rows.values()
           if include_retired or r.get("status") != "retired"]
    return sorted(out, key=lambda r: (not r.get("user"), r.get("status") == "proposed", r["names"][0].lower()))


def get(pid: str) -> Optional[dict]:
    return load()[0].get(pid)


def _next_id(rows: Dict[str, dict]) -> str:
    n = 1 + max([int(k[1:]) for k in rows if re.fullmatch(r"p\d+", k)] or [0])
    return "p%d" % n


def _clean_names(names) -> List[str]:
    if isinstance(names, str):
        names = [n for n in re.split(r"[,;]", names)]
    out = []
    for n in names or []:
        n = re.sub(r"\s+", " ", str(n)).strip()
        if n and n.lower() not in [x.lower() for x in out]:
            out.append(n[:60])
    return out


def add(name, *, kind: str = "person", relation: str = "", pronouns: str = "", notes: str = "",
        user: bool = False, status: str = "live", proposed_by: str = "", aliases=()) -> dict:
    names = _clean_names([name] + list(aliases or []))
    if not names:
        raise PeopleError("a name is needed")
    if kind not in KINDS:
        raise PeopleError(f"kind is one of {', '.join(KINDS)}")
    if status not in STATUSES:
        raise PeopleError(f"status is one of {', '.join(STATUSES)}")
    rows, _a = load()
    same = [r for r in rows.values() if r.get("status") != "retired"
            and names[0].lower() in [x.lower() for x in r["names"]] and r["kind"] == kind]
    if same and not user:
        raise PeopleError(f"{names[0]} is already here ({same[0]['id']})")
    row = {"id": _next_id(rows), "names": names, "kind": kind, "pronouns": pronouns.strip(),
           "relation": relation.strip()[:200], "notes": notes.strip()[:2000], "user": bool(user),
           "handle": "", "status": status, "proposed_by": proposed_by, "private": False,
           "created": _now()}
    if user:
        row["kind"] = "person"
        row["handle"] = "user%d" % (1 + sum(1 for r in rows.values() if r.get("user")))
    _append({"op": "put", "row": row})
    return row


def update(pid: str, **fields) -> dict:
    rows, _a = load()
    if pid not in rows:
        raise PeopleError(f"no one with id {pid}")
    row = dict(rows[pid])
    for k, v in fields.items():
        if k not in FIELDS or k in ("user", "handle"):
            raise PeopleError(f"{k} cannot be changed here")
        if k == "names":
            v = _clean_names(v)
            if not v:
                raise PeopleError("a name is needed")
        if k == "kind" and v not in KINDS:
            raise PeopleError(f"kind is one of {', '.join(KINDS)}")
        if k == "status" and v not in STATUSES:
            raise PeopleError(f"status is one of {', '.join(STATUSES)}")
        row[k] = v
    _append({"op": "put", "row": row})
    return row


def retire(pid: str, why: str = "") -> dict:
    """Never removed: the row stays, marked retired, with the reason."""
    row = get(pid)
    if not row:
        raise PeopleError(f"no one with id {pid}")
    _, active = load()
    if pid == active:
        raise PeopleError("that is the user she is talking to now — switch user first")
    return update(pid, status="retired", notes=(row.get("notes", "") + ("\n[retired] " + why if why else "")).strip())


def confirm(pid: str) -> dict:
    row = get(pid)
    if not row or row.get("status") != "proposed":
        raise PeopleError("only a proposed person can be confirmed")
    return update(pid, status="live")


# ── users ────────────────────────────────────────────────────────────────────────────────
def users() -> List[dict]:
    return [r for r in everyone() if r.get("user")]


def add_user(name: str, pronouns: str = "", **kw) -> dict:
    return add(name, kind="person", pronouns=pronouns, user=True, **kw)


def set_active(pid: str) -> dict:
    row = get(pid)
    if not row or not row.get("user") or row.get("status") != "live":
        raise PeopleError("only a live user can be the one she talks to")
    _append({"op": "active", "id": pid})
    return row


def active() -> Optional[dict]:
    rows, a = load()
    return rows.get(a) if a else None


def seed_from_profile(name: str, pronouns: str = "") -> Optional[dict]:
    """The first user, from the profile's [user], when the home has none yet — so an existing
    companion's person is user1 without anyone typing him in again."""
    if not (name or "").strip() or users():
        return None
    row = add_user(name.strip(), pronouns)
    set_active(row["id"])
    return row


def find(name: str) -> Optional[dict]:
    """By id, handle, name or alias (case-insensitive), live or proposed."""
    q = (name or "").strip().lower()
    for r in everyone():
        if q in (r["id"], r.get("handle", "").lower()) or q in [n.lower() for n in r["names"]]:
            return r
    return None


def mentioned(text: str, rows: Optional[List[dict]] = None) -> List[str]:
    """Ids of live people whose name or alias appears in `text` as a whole word."""
    t = text or ""
    out = []
    for r in rows if rows is not None else everyone():
        if r.get("status") != "live":
            continue
        for n in r["names"]:
            if len(n) >= 2 and re.search(r"(?<![\w])" + re.escape(n) + r"(?![\w])", t, re.I):
                out.append(r["id"])
                break
    return out
