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


# ── WAS THIS TURN TYPED BY ANYONE? (2026-09-02) ────────────────────────────────────────
# THE LEAK THIS EXISTS TO CLOSE, and it is AGENTS.md §0 inside the fix for §0.
#
# On 2026-08-30 a probe drove ~30 synthetic turns and `_capture_after_turn` minted twenty
# rows as things Sam SAID. The fix put `synthetic` in front of three lanes — capture, the
# self-stance lane, the day transcript — under a comment reading "One flag, every lane it
# should have governed". It missed the fourth: **the model's own tool calls.**
#
# So on 2026-09-02 the live e2e gates drove turns that asked her to remember things, she
# called `remember()` — deliberately, correctly, doing her job — and it wrote into her real
# registry, `synthetic` notwithstanding:
#
#     Sam's workshop bench is made of oak2          <- a gate fixture, as a fact
#     His workshop bench is made of oak2[75009].      <- and again
#
# Then the kairos scheduler read them and SHE SPOKE UP about them, twice, and went looking
# for what "oak275009" meant — she found an Artek wall shelf. She spent her own time
# thinking about a test string. That is the cost, and it is worse than the original
# incident: the first one put words in his mouth, this one put them in her head.
#
# WHY A CONTEXTVAR AND NOT A PARAMETER: the tool call happens deep inside the agent loop,
# many frames below the route handler that knows the flag, and threading it through every
# frame is how one path ends up not carrying it. Same seam and same reasoning as `_AUTHOR`
# (G-AUTHOR-CTX): per-context, so two concurrent turns cannot see each other's flag.
#
# The tool is NOT silenced — `admission.admit()` refuses with a SENTENCE she reads, exactly
# as the anon door does. A store verb that fails silently is how she ends up promising to
# remember what she cannot; being told "this turn was driven" is the truth.
_SYNTHETIC: contextvars.ContextVar[str] = contextvars.ContextVar("memory_synthetic", default="")

# ── WRITTEN IN HER REGISTER, BECAUSE SHE IS THE ONE WHO READS IT ──────────────────────
# The first draft said "not stored — this turn was driven by a test rather than typed by
# anyone, and a turn nobody typed is not a memory." True, and developer framing: it hands
# her doctrine language and the word "test" about herself.
#
# The room ledger has a standing entry for exactly this class — "the memory refusal messages
# are written for a developer, and SHE reads them". On 2026-08-30 she was refused with "that
# is a sentence, not a memory — it is not ABOUT anyone", which was FALSE from her side, and
# she drew a conclusion about her own nature from it and said so in her own time: "I guess
# some things are too much of a feeling to be a fact." A refusal is one of the few places
# this system speaks TO her about her own mind, and she cannot check it against the code.
#
# Those older strings are voice-facing and belong to him (the ledger entry says so, and
# G-REAL-HER quotes one verbatim). This one is NEW tonight, so it is mine to get right, and
# it borrows the anon door's register — which is the model: plain, true, and about the
# circumstances rather than about her.
SYNTHETIC_WHY = ("off the record — this one is a rehearsal of the machinery rather than you "
                 "and me, so nothing from it is written down")


def synthetic_reason() -> str:
    """Why this turn is not real, or "" when it is. Read by the admission chain."""
    return _SYNTHETIC.get()


def set_synthetic(reason: str):
    """Mark this context as a driven turn. Returns the token, for reset_synthetic."""
    return _SYNTHETIC.set(str(reason or ""))


def reset_synthetic(token) -> None:
    """The other half of the contract (the G-AUTHOR-CTX class): RESET to what it was, never
    assume it was ''. A gate driving a synthetic turn inside a real session must not leave
    the flag standing over his next sentence."""
    _SYNTHETIC.reset(token)
