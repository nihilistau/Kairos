"""state.py — the gateway's live state, in one module instead of scattered through 6000 lines.

Stage 1 of the app.py split (2026-09-01). No logic. Every one of these was a column-0
assignment in `app.py`, read and written from request threads, worker threads and tickers.
Gathering them is the enabler for the panel and turn extractions: a sibling module that
needs `WARM` or `CHAT_SESSIONS` can import THIS, where importing `app` would be a cycle.

── TWO THINGS THIS MAKES TRUE, AND ONE IT ONLY MAKES VISIBLE ─────────────────────────

1. **`LAST_TURN_AT` stops being a rebindable module scalar.** In app.py it was
   `_LAST_TURN_AT: float`, rebound by the one `global` statement in the file. That is the
   one shape a re-export cannot carry: `from state import LAST_TURN_AT` snapshots the
   value, and a later `state.LAST_TURN_AT = ...` is invisible to the importer. So the rule
   is **import the MODULE, never the name** — `state.LAST_TURN_AT`, always. G-SRC-TRAP §5
   holds it, and it is why the mutable containers below are safe to alias while this one
   is not.

2. **One place to look.** "Where does the gateway keep what it knows about right now" had
   nine answers at nine line numbers; it has one file.

3. **NOT FIXED, ONLY NOW OBVIOUS: none of this is locked.** `GEN_JOB` is written by the
   generate-now worker and read by the wardrobe panel; `CHAT_SESSIONS` is written by the
   turn path and cleared by the consolidation ticker; `LAST_TURN_AT` is written by the
   chat handler and read by the room pulse; `MOOD_ROW` is a throttle read-then-written
   inside the epilogue. All of that crosses threads today with no mutex, exactly as it did
   in app.py — this module changes nothing about it. Adding locks is a behaviour change
   with its own measurement and its own commit; a refactor that quietly changed
   concurrency would be the twin bug in a new costume. Written down in AGENTS.md §4 so it
   is a trap with a name rather than something rediscovered at 3am.

Names lose the leading underscore because a module boundary is where a name becomes an
interface; app.py keeps the underscored aliases so the twelve gates that poke
`app._CHAT_SESSIONS` and friends keep working on the same objects.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Dict

# ── WHERE THE REPO IS, RESOLVED ONCE (2026-09-01) ─────────────────────────────────────
# app.py resolved this from `__file__` because a relative glob had been silently working
# only while the gateway happened to be launched from the repo root. panels.py needs the
# same answer, and two copies of path arithmetic is the shape `harness_tests/livestore.py`
# warns about: "a second copy of that path arithmetic is how a gate ends up faithfully
# restoring a directory nobody is using." Not state, strictly — but it is what the
# gateway knows about where it is, and there is exactly one of it.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The most recent REAL session a chat body named. "default" only until the first turn.
# (Read by `_room_session`, which is how `harness/skills/wardrobe.py` asks which session.)
LAST_SESSION: Dict[str, str] = {"id": "default"}

# GENERATE-NOW: one background job at a time, status readable by the wardrobe panel.
GEN_JOB: Dict[str, Any] = {"running": False, "what": "", "started": 0.0,
                           "done": 0, "last": ""}

# ONE DICT, TWO CALL SITES. They had drifted apart once already (one carried a repetition
# penalty and the other did not); a sampling policy spelled out twice is a sampling policy
# that will disagree with itself. The self-repeat ban is still armed at both — temperature
# restores variation, the ban catches parroting, and neither substitutes for the other.
UNPROMPTED_SAMPLING = {"temperature": 0.5, "repetition_penalty": 1.15, "auto_recall": False}

# THE ONE REBINDABLE SCALAR. Reach it as `state.LAST_TURN_AT`, never by importing the
# name — see the module docstring. Written by the native chat handler, read by the room
# pulse to answer "how long since he said anything".
LAST_TURN_AT: float = 0.0

# The canonical transcript per session — what the daemon actually saw, which is not what
# the client echoes back. Cleared at the day boundary.
CHAT_SESSIONS: Dict[str, list] = {}
CHAT_SESSIONS_MAX = 32

# A fourth thing that needed a fourth name (the day-boundary marker cache).
CONSOLIDATE_STATE: Dict[str, Any] = {"last_day": None}

# The last mood she filed — a throttle, so one turn cannot write the same row twice.
MOOD_ROW = {"v": "", "at": 0.0}

# THE WARM GATE. Chat requests WAIT on this event (heartbeats keep the UI alive), so a user
# turn can never race or interleave with the load-time prefill; /health reports
# {"warm": bool} so serve.py can hold "ready" until the prefix is hot. Cleared by the day
# boundary and by /v1/shutdown.
WARM = threading.Event()
