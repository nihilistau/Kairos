"""task_table — who may do what to a task, as a finite committed table.

WHY A TABLE AND NOT A HANDFUL OF `if`s
──────────────────────────────────────
`task_loop` had five statuses and no rules: `run_task` assigned them directly, nothing could
CLOSE a task, and nothing said who was allowed to. A work queue the organism maintains needs an
answer to "may she close the thing he asked for?" before it needs anything else, and that answer
is a RULING — a verdict-layer object in the sense of docs/INVARIANT-MEMORY.md §1.3, not a
conditional that happens to be written somewhere.

So the policy is `step()`: pure, total, and small enough to enumerate exhaustively. Every cell of
`status × event × actor × owner` is walked through the REAL function and frozen at
`fixtures/tasks/task-table.json`; `g_task_table.py` asserts ∀-theorems over the committed board.
A diff in that file is an unreviewed policy change, and the gate is the tripwire — the same
discipline as `ladder-table.json` and `verdict-table.json`.

THE FOUR THEOREMS (asserted over every cell, not sampled)
────────────────────────────────────────────────────────
1. NOTHING IS EVER SILENTLY DROPPED. Every (status, event, actor, owner) has an outcome, and a
   refusal is an explicit REFUSED with a reason — never a silent no-op that reads as success.
2. ONLY THE OWNER OR THE OPERATOR MAY CLOSE. She may close what she set herself; she may not
   close what he asked for. This is `may_supersede`'s asymmetry in a different costume, and it
   exists for the same reason: her word never outranks his.
3. A CLOSED TASK NEVER REOPENS ITSELF. `reopen` is refused for every actor except the operator,
   and refused from `done` for everyone — a finished thing stays finished unless he says
   otherwise. Without this the drain can resurrect its own failures forever.
4. NOTHING IS DELETED. No event maps to absence. Terminal states are TOMBSTONES: the row stays,
   the history stays, `list_tasks()` still sees it. (The store-side half of this is that
   `close()` writes a status, never unlinks a file.)

ACTORS. "self" is her (the drain, a tool call she makes, the idle tick). "operator" is him.
"system" is the machinery itself — the step budget expiring, a crash resuming — and it may only
report what happened, never close or reopen. Three actors, and the distinction is the whole
point: an autonomous drain that can close the operator's tasks is a queue that empties itself.
"""
from __future__ import annotations

from typing import Tuple

# ── the finite domain ────────────────────────────────────────────────────────────────
PENDING, RUNNING = "pending", "running"
DONE, FAILED, EXHAUSTED, CLOSED = "done", "failed", "exhausted", "closed"

STATES = (PENDING, RUNNING, DONE, FAILED, EXHAUSTED, CLOSED)
TERMINAL = (DONE, FAILED, EXHAUSTED, CLOSED)

# events. `start/succeed/fail/exhaust` are reports of what the loop did; `close/reopen` are
# decisions someone makes about the task.
EVENTS = ("start", "succeed", "fail", "exhaust", "close", "reopen")

SELF, OPERATOR, SYSTEM = "self", "operator", "system"
ACTORS = (SELF, OPERATOR, SYSTEM)
OWNERS = (SELF, OPERATOR)

REFUSED = "refused"


def may_close(actor: str, owner: str) -> bool:
    """Theorem 2, as its own named predicate so the rule has one home.

    THE ASYMMETRY: she may close her own tasks; she may not close his. He may close anything.
    The machinery may close nothing — `system` reports outcomes, it does not make decisions.
    """
    if actor == OPERATOR:
        return True
    if actor == SELF:
        return owner == SELF
    return False


def may_reopen(actor: str, status: str) -> bool:
    """Theorem 3. Only the operator reopens, and never something already `done`.

    `done` is excluded even for him ON PURPOSE: reopening a completed task silently rewrites
    what the record says happened. He can post a new task — that keeps both truths.
    """
    return actor == OPERATOR and status in (FAILED, EXHAUSTED, CLOSED)


def step(status: str, event: str, actor: str, owner: str) -> Tuple[str, str]:
    """The whole policy. Returns (new_status, reason).

    TOTAL: every combination in STATES × EVENTS × ACTORS × OWNERS returns a pair. A refusal
    returns the UNCHANGED status and a reason beginning with REFUSED, so a caller can neither
    mistake it for success nor lose why.
    """
    if status not in STATES:
        return status, "%s: unknown status %r" % (REFUSED, status)
    if event not in EVENTS:
        return status, "%s: unknown event %r" % (REFUSED, event)
    if actor not in ACTORS:
        return status, "%s: unknown actor %r" % (REFUSED, actor)

    if event == "close":
        if status in TERMINAL:
            return status, "%s: already %s" % (REFUSED, status)
        if not may_close(actor, owner):
            return status, "%s: %s may not close a task owned by %s" % (REFUSED, actor, owner)
        return CLOSED, "closed by %s" % actor

    if event == "reopen":
        if not may_reopen(actor, status):
            return status, "%s: %s may not reopen a %s task" % (REFUSED, actor, status)
        return PENDING, "reopened by %s" % actor

    # the reports. Only the loop itself (or the operator driving it) moves a task through
    # its work; a report against a terminal task is refused, not silently applied.
    if status in TERMINAL:
        return status, "%s: %s is terminal" % (REFUSED, status)
    # NOTE: she may WORK his task and report on it — that is exactly what the drain is for, and
    # restricting reports by owner would make the queue undrainable. The line is drawn at
    # CLOSING, which `may_close` holds above. Reports are open to self and operator alike.
    if event == "start":
        if status != PENDING:
            return status, "%s: only a pending task may start" % REFUSED
        return RUNNING, "started by %s" % actor
    if status != RUNNING:
        return status, "%s: %s may only be reported for a running task" % (REFUSED, event)
    return ({"succeed": DONE, "fail": FAILED, "exhaust": EXHAUSTED}[event],
            "%s reported by %s" % (event, actor))


def is_refusal(reason: str) -> bool:
    return (reason or "").startswith(REFUSED)
