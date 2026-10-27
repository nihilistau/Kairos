"""room.py — which session is the room actually in? One neutral door for asking.

WHY (2026-10-21, the consult review). Tools that need "the live session" (the consult scene
door, the wardrobe's rung) used to import `harness.server.app` for `_room_session()`. The
gateway runs as `python -m harness.server.app`, so the serving module is `__main__` and that
import builds a SECOND copy of app.py inside her process. It answered correctly only because
both copies happened to point `_LAST_SESSION` at the one dict in harness/server/state.py — a
property nobody stated, which the next refactor of app.py could quietly drop.

So the dict lives HERE, in a module that imports nothing from the server, and
harness/server/state.py's LAST_SESSION is this same object (an alias, not a copy: two stores
of "which session" is the exact bug AGENTS.md §0 names). The chat handlers write through
set_session(); tools read session() without importing the gateway at all.

Gate: G-CONSULT section 10.
"""
from __future__ import annotations

from typing import Dict

# The most recent REAL session a chat body named. "default" until the first turn.
LAST: Dict[str, str] = {"id": "default"}


def set_session(sid: str) -> None:
    """The chat handlers call this when a body names its session. One str assignment —
    atomic under the GIL, so no lock."""
    if sid:
        LAST["id"] = str(sid)


def session() -> str:
    return str(LAST.get("id") or "default")
