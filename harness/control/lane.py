"""lane.py — is this turn one of HER unprompted ones, or is he talking to her?

One ContextVar and three functions. The consult tool (Claude, asked by her) can be switched
off for her own time by the operator; to honour that it has to know, deep inside the agent
loop, which kind of turn it is running in. The kairos scheduler sets this around every
unprompted generation (own time, solo, check-in, muse, continue, presence modes).

PER-CONTEXT, NEVER PROCESS-WIDE (2026-10-21), the same seam and the same reason as
harness/skills/memory/authorship.py: her turn on the scheduler's thread and his turn on an
HTTP thread run at the same time, and a module-level flag would let one stand over the other.
A new thread starts with an EMPTY context (PEP 567), so a thread that was not handed the lane
reads False - his - which is the safe default: consult stays available unless a scheduler
turn positively marked itself unprompted.

Gate: G-CONSULT section 1.
"""
from __future__ import annotations

import contextvars

_UNPROMPTED: contextvars.ContextVar[bool] = contextvars.ContextVar("turn_unprompted", default=False)


def unprompted() -> bool:
    """True only inside a turn the scheduler started on its own."""
    return _UNPROMPTED.get()


def set_unprompted(flag: bool):
    """Mark this context. Returns the token so the caller RESETS rather than assuming False."""
    return _UNPROMPTED.set(bool(flag))


def reset(token) -> None:
    """The other half of the contract: restore what it was before set_unprompted."""
    _UNPROMPTED.reset(token)
