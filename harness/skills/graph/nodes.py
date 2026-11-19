"""Graph nodes: her registry facts and every transcript turn, each under a stable ID.

WHY THE IDS ARE WHAT THEY ARE. A turn's ID is its `oid` when it has one, else
`t:<YYYY-MM-DD>:<line index>`, where the index is the 0-based PHYSICAL line in the day file
(`transcript.all_rows` counts blank and malformed lines), so a bad line never renumbers the
turns after it and appending never renumbers the turns before. Facts keep their registry
`name`. The audit door `memory.all_rows` is used for facts on purpose: retired rows stay
nodes (marked `retired`), because "what did she believe, and what replaced it" is the point.
Nothing here filters for liveness or secrecy; that is the reader's job at the memory doors.

APP EVENTS (2026-11-08). What he did in another app (`harness/model/activity.py`) is an
`app_event` node, ID `a:<app>:<day>:<line index>` on the same physical-line rule, with `app`,
`event` and `ref` beside the usual fields and the title as its `text`. Private rows never reach
here: the activity reader drops them first.

A node is `{"id", "kind", "day", "at", "text"}` plus, where they apply, `speaker`, `role`,
`synthetic`, `retired`; fact nodes also carry `superseded_by` / `derived_from` so the explicit
rule can work from nodes alone. `at` is float epoch SECONDS or None (transcript `at` is
milliseconds and often absent; registry `first_seen` is ISO with a literal Z).
"""
from __future__ import annotations

import datetime as _dt
import os
from typing import Optional

import harness.skills.memory as M
from harness.model import activity, transcript
from harness.skills import lifecycle


def turn_id(row: dict, day: str, line: int) -> str:
    oid = row.get("oid")
    return str(oid) if oid else f"t:{day}:{line}"


def _iso_to_epoch(s) -> Optional[float]:
    if not isinstance(s, str) or not s:
        return None
    try:
        d = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d.timestamp()


def _utc_day(at: float) -> str:
    return _dt.datetime.fromtimestamp(at, _dt.timezone.utc).strftime("%Y-%m-%d")


def _text(v) -> str:
    return v if isinstance(v, str) else ("" if v is None else str(v))


def _fact_node(row: dict) -> Optional[dict]:
    name = row.get("name")
    if not name:
        return None
    at = _iso_to_epoch(row.get("first_seen"))
    n = {"id": str(name), "kind": "fact",
         "day": _utc_day(at) if at is not None else "",
         "at": at, "text": _text(row.get("text") or row.get("topic")),
         "speaker": row.get("speaker") or lifecycle.SPEAKER_USER,
         "superseded_by": row.get("superseded_by") or None,
         "derived_from": [str(x) for x in (row.get("derived_from") or [])]}
    if lifecycle.is_retired(row):
        n["retired"] = True
    return n


def _turn_node(row: dict, day: str, line: int) -> Optional[dict]:
    kind = {"user": "turn_user", "assistant": "turn_her"}.get(row.get("role"))
    if kind is None:
        return None
    ms = row.get("at")
    n = {"id": turn_id(row, day, line), "kind": kind, "day": day,
         "at": ms / 1000.0 if isinstance(ms, (int, float)) and not isinstance(ms, bool) else None,
         "text": _text(row.get("content")), "role": row["role"]}
    if row.get("synthetic"):
        n["synthetic"] = True
    return n


def event_id(app: str, day: str, line: int) -> str:
    return f"a:{app}:{day}:{line}"


def _event_node(app: str, day: str, line: int, row: dict) -> dict:
    ms = row.get("at")
    return {"id": event_id(app, day, line), "kind": "app_event", "day": day,
            "at": ms / 1000.0 if isinstance(ms, (int, float)) and not isinstance(ms, bool) else None,
            "text": row["title"], "app": app, "event": row["event"], "ref": row.get("ref") or None}


def transcripts_state(registry: str = "") -> str:
    """"absent" (no transcripts dir), "unreadable" (it exists and could not be read) or "ok".
    `collect` turns an unreadable directory into "no turns"; the build summary needs the
    difference, or a graph built with the disk unplugged looks like a graph of an empty week."""
    d = transcript._dir(registry)
    if not d or not os.path.isdir(d):
        return "absent"
    return "ok" if transcript.all_rows(registry) is not None else "unreadable"


def collect(registry: str = "") -> list:
    """Turns (oldest day first, file order), then facts (store order), then app events (app,
    day, file order). Duplicate IDs keep the first: a graph with two nodes under one ID would
    make every edge to it ambiguous."""
    out, seen = [], set()
    for day, line, row in transcript.all_rows(registry) or []:
        n = _turn_node(row, day, line)
        if n and n["id"] not in seen:
            seen.add(n["id"])
            out.append(n)
    for row in M.all_rows(registry):
        n = _fact_node(row)
        if n and n["id"] not in seen:
            seen.add(n["id"])
            out.append(n)
    for app, day, line, row in activity.all_rows(registry) or []:
        n = _event_node(app, day, line, row)
        if n["id"] not in seen:
            seen.add(n["id"])
            out.append(n)
    return out
