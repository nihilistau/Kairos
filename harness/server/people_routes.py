"""people_routes — the People window (2026-11-26, design §2, §7b; harness/people.py).

    GET  /v1/people        everyone she knows (users first, proposals flagged), the active
                           user, the kinds
    POST /v1/people        {op: add|update|retire|confirm|reject|add_user|switch, ...}

`switch` makes another user the one she talks to. Her prefix names the user, so it takes
effect at a gateway restart; the route records the choice and says so, and the window offers
the restart (the same ~20 s bounce the Companion window uses).
"""
from __future__ import annotations

from harness import people as PP


def _err(code, msg):
    return code, {"ok": False, "error": msg}


def get_people():
    import os
    rows = PP.everyone()
    act = PP.active()
    running = os.environ.get("SP_USER_ID", "")
    return 200, {"ok": True, "people": rows, "kinds": list(PP.KINDS),
                 "active": act, "running_as": running,
                 "switch_pending": bool(act and running and act["id"] != running),
                 "proposed": [r for r in rows if r.get("status") == "proposed"]}


def post_people(body: dict):
    op = str(body.get("op") or "")
    try:
        if op == "add":
            r = PP.add(str(body.get("name") or ""), kind=str(body.get("kind") or "person"),
                       relation=str(body.get("relation") or ""), pronouns=str(body.get("pronouns") or ""),
                       notes=str(body.get("notes") or ""), aliases=body.get("aliases") or [])
        elif op == "add_user":
            r = PP.add_user(str(body.get("name") or ""), str(body.get("pronouns") or ""),
                            relation=str(body.get("relation") or ""), notes=str(body.get("notes") or ""))
        elif op == "update":
            fields = {k: body[k] for k in ("names", "kind", "pronouns", "relation", "notes") if k in body}
            r = PP.update(str(body.get("id") or ""), **fields)
        elif op == "retire":
            r = PP.retire(str(body.get("id") or ""), str(body.get("why") or ""))
        elif op == "confirm":
            r = PP.confirm(str(body.get("id") or ""))
        elif op == "reject":
            # a proposal he says no to is retired with the reason — kept, never deleted
            row = PP.get(str(body.get("id") or ""))
            if not row or row.get("status") != "proposed":
                return _err(400, "only a proposed person can be rejected")
            r = PP.update(row["id"], status="retired",
                          notes=(row.get("notes", "") + "\n[not confirmed] " + str(body.get("why") or "")).strip())
        elif op == "switch":
            r = PP.set_active(str(body.get("id") or ""))
            return 200, {"ok": True, "row": r, "restart": True,
                         "note": f"she will be talking to {r['names'][0]} after a restart (about 20 s) — "
                                 "her prefix names who she is talking to"}
        else:
            return _err(400, "op must be add, add_user, update, retire, confirm, reject or switch")
    except PP.PeopleError as e:
        return _err(400, str(e))
    return 200, {"ok": True, "row": r}
