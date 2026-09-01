"""authorship.py — who is speaking this turn, and what they asked.

Two ContextVars and the five accessors that are their whole contract. This is the
load-bearing bit for identity: the SAME sentence ("I am male") is a fact about the USER
when the user says it and a fact about KAIROS when she says it, so the author is passed
IN, never inferred from the words at read time — inferring it is exactly how she started
speaking as the user.

── AND set_question COMES HOME (2026-09-01) ──────────────────────────────────────────
`_QUESTION` was declared beside `_AUTHOR`, `reset_question` twenty lines below it, and
`set_question` **780 lines away**, in the middle of the ranking code, under a comment
explaining that the second half of the pair used to be a process-wide `_QUESTION = ""`
right there. Half a contract, filed under where it happened to be needed. The pair is one
module now, which is the only reason this file is worth its own header: a set/reset pair
that a reader cannot see at once is a pair somebody will call half of.

G-AUTHOR-CTX is the gate, and it asks this package for EXACTLY ONE assignment of each
ContextVar — because a second one in a sibling would be two authors, silently.
"""
from __future__ import annotations

import contextvars


# WHO IS SPEAKING THIS TURN. The gateway sets this before dispatching tools. It is the
# load-bearing bit for identity: the SAME sentence ("I am male") is a fact about the
# USER when the user says it and a fact about KAIROS when she says it. Inferring the
# owner from the words at READ time is exactly how she started speaking as the user.
#
# PER-CONTEXT, NEVER PROCESS-WIDE (2026-08-19). These used to be module globals under
# a ThreadingHTTPServer. Concurrent turns (him typing + a kairos speak-up, or two
# tabs) crossed speaker attribution: turn A set _AUTHOR="self" for remember_about_self,
# turn B's remember() raced it, and B's fact was stamped with A's author. ContextVar
# is the seam — a thread/task cannot see another turn's author. Gate: G-AUTHOR-CTX.
_AUTHOR: contextvars.ContextVar[str] = contextvars.ContextVar("memory_author", default="user")
_QUESTION: contextvars.ContextVar[str] = contextvars.ContextVar("memory_question", default="")


def current_author() -> str:
    return _AUTHOR.get()


def current_question() -> str:
    return _QUESTION.get()


def set_author(who: str):
    """Stamp this context's author. Returns the ContextVar token so a caller can
    RESET the previous value instead of assuming it was 'user'."""
    return _AUTHOR.set("self" if who == "self" else "user")


def reset_author(token) -> None:
    """RESET to whatever the author was before set_author — the other half of the
    contract. Callers that did `finally: set_author("user")` were clobbering a
    surrounding self-turn (the exact class G-AUTHOR-CTX fixed in remember_about_self,
    left alive in ops.add/ops.insight until 2026-08-19)."""
    _AUTHOR.reset(token)


def reset_question(token) -> None:
    """The question's half of the same contract (2026-08-24 audit, A5): her unprompted
    turns now arm the lane with author=self and the impulse nudge, and must restore
    BOTH on the way out — resetting the author while leaving the previous turn's
    question standing is the lag _arm_turn's own receipt documents."""
    _QUESTION.reset(token)


# THE USER'S ACTUAL WORDS THIS TURN. The gateway sets this before the agent runs.
#
# WHY IT HAS TO BE HIS SENTENCE AND NOT HER QUERY (2026-07-12, from the trace). Asked
# "what is YOUR name?", she called recall(query="What is my name?") — she rewrites the
# question into her own first person, which is the natural thing to do. Asked "what is MY
# name?", she called recall(query="What is my name?") — the identical string. Two opposite
# questions, one query. So the pronoun in the string SHE passes carries no information
# about who is being asked after; it only tells you whose mouth the paraphrase is in.
#
# The pronoun is only reliable where it was UTTERED. In HIS sentence "my" means Sam and
# "your" means Kairos, always. So ownership is resolved from the human's words, and her
# query is used for what it is actually good for: matching the content.
#
# Same ContextVar seam as _AUTHOR (G-AUTHOR-CTX). The second assignment used to live
# here as `_QUESTION = ""` — a process-wide slot. It is defined with _AUTHOR above.


def set_question(text: str):
    return _QUESTION.set(text or "")
