"""task_bridge — the board is where things are WRITTEN; the queue is where they are DONE.

THE GAP THIS CLOSES
───────────────────
There are two task systems in this repo and they have never met.

    notes.jsonl          category="task" notes. BOTH authors write here, she has tools for it
                         (add_note / edit_note / find_notes), the console renders it, and
                         `done` is read by due(), watch() and the stats. What it cannot do is
                         DO anything: a task note is a sentence on a board.

    _task_state/         TaskState. Bounded, resumable, receipted, verify-before-accept, and
                         drained by the day boundary — genuinely able to work a goal. What it
                         cannot do is be CREATED: `post_task()` had no tool, no route, and no
                         caller anywhere in the tree, so the drain has spent its whole life
                         draining an empty queue.

One side can only write, the other can only execute. This module is the join, and it is
deliberately a JOIN rather than a third surface: adding `add_task`/`close_task`/`my_tasks` tools
would take the live core toolset from 13 to 16, and agent.py:220 already warns — measured, in
G-NOTES-TOOLS — that a small model picks reliably from about six. She does not need new verbs.
She needs the verbs she has to reach the machinery.

    add_note("fix the recall filter", category="task")   ->  promote()  ->  TaskState(pending)
                                                              drain     ->  runs, receipts
    note.done = True, body gains the result              <-  writeback()

OWNERSHIP CROSSES THE BRIDGE INTACT. A note carries `speaker` — who pinned it — and that becomes
the TaskState's `owner`, which is what `task_table.may_close` rules on. A task he wrote stays his
after promotion: she may work it and report on it, and she may not close it. Losing the author
here would have handed her closing rights over everything he ever asked for, silently, at the
moment the two systems were connected.

NOTHING IS DELETED ON EITHER SIDE. Promotion writes a link, it does not consume the note.
Writeback ticks `done` and appends the result; the note, its history and the task's whole step
record all survive. (`notes.update`'s whitelist had to learn `task_id`/`task_status` to allow
this — it silently drops unknown fields, which is exactly how the watch fields were lost once.)
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# The board's author vocabulary is not the table's actor vocabulary, and they must not be
# conflated: notes record a SPEAKER ("user"/"self"/a name), the table rules on an OWNER
# ("operator"/"self"). One map, here, so no caller invents its own.
_OWNER_OF_SPEAKER = {"self": "self", "kairos": "self", "assistant": "self"}


def enabled() -> bool:
    """SP_TASK_BRIDGE — mapped in serve.py, DEFAULT OFF.

    Off, `promote()` and `writeback()` are no-ops and the two systems stay exactly as separate
    as they are today. It is off by default because promotion makes the drain REACH THE
    OPERATOR'S MACHINE — the task tools are read_file/write_file/edit_file/run_tests/
    run_command — and a queue that fills itself from a board he writes on is a thing he should
    switch on deliberately, not discover.
    """
    return os.environ.get("SP_TASK_BRIDGE", "0") == "1"


def owner_of(note: dict) -> str:
    """Who owns the work a note describes. Unknown speaker -> "operator", the reading that
    gives her LESS authority (she cannot close it), never more."""
    return _OWNER_OF_SPEAKER.get(str(note.get("speaker", "")).strip().lower(), "operator")


def open_task_notes() -> List[dict]:
    """Live, undone, category="task" notes — her open commitments, in the order pinned.

    This is also what the standing world renders, so there is ONE definition of "what is
    outstanding" rather than a world-side copy that drifts from the board.
    """
    from harness.skills import notes as N
    try:
        rows = N.live()
    except Exception as exc:                      # a broken board must never break a turn
        logger.warning("[task_bridge] board unreadable: %s", exc)
        return []
    return [r for r in rows
            if r.get("category") == "task" and not r.get("done") and not r.get("lifecycle")]


def promote(limit: int = 5) -> List[Dict[str, str]]:
    """Post every open task note that has no task yet onto the executable queue.

    Returns one record per promotion. Bounded by `limit` so a board with fifty task notes
    cannot enqueue fifty runs in a single night.
    """
    if not enabled():
        return []
    from harness.control.task_loop import post_task
    from harness.skills import notes as N

    out: List[Dict[str, str]] = []
    for note in open_task_notes():
        if note.get("task_id"):
            continue                              # already has one; promotion is idempotent
        if len(out) >= max(0, int(limit)):
            break
        goal = note.get("title", "").strip()
        body = (note.get("body") or "").strip()
        if body:
            goal = "%s\n\n%s" % (goal, body)
        if not goal:
            continue
        owner = owner_of(note)
        try:
            tid = post_task(goal, owner=owner)
        except Exception as exc:
            logger.error("[task_bridge] post_task failed for note %s: %s", note.get("id"), exc)
            continue
        N.update(note["id"], task_id=tid, task_status="pending")
        out.append({"note_id": note["id"], "task_id": tid, "owner": owner,
                    "title": note.get("title", "")[:80]})
        logger.info("[task_bridge] promoted note %s -> task %s (owner=%s)",
                    note["id"], tid, owner)
    return out


def writeback() -> List[Dict[str, str]]:
    """Carry every finished task's verdict back to the note it came from.

    A task that reached a terminal state ticks its note `done` and appends the result to the
    body. A task still pending or running only updates `task_status`, so the board shows work
    in flight rather than pretending nothing is happening.

    THE ONE THING THIS MAY NOT DO is close a task. Ticking a NOTE is a board edit; closing a
    TASK is a ruling, and it belongs to `task_table.may_close`. Writeback reports what the
    loop already decided — it never decides.
    """
    if not enabled():
        return []
    from harness.control.task_loop import TaskState
    from harness.skills import notes as N

    TERMINAL = ("done", "failed", "exhausted", "closed")
    out: List[Dict[str, str]] = []
    try:
        rows = N.live()
    except Exception as exc:
        logger.warning("[task_bridge] board unreadable: %s", exc)
        return []
    for note in rows:
        tid = note.get("task_id")
        if not tid or note.get("done"):
            continue
        st = TaskState.load(tid)
        if st is None:
            continue
        if st.status == note.get("task_status"):
            continue                              # nothing moved
        fields: Dict[str, object] = {"task_status": st.status}
        if st.status in TERMINAL:
            fields["done"] = True
            result = (st.result or "").strip()[:400]
            stamp = "\n\n[task %s: %s]%s" % (tid, st.status, ("\n" + result) if result else "")
            fields["body"] = ((note.get("body") or "") + stamp).strip()
        N.update(note["id"], **fields)
        out.append({"note_id": note["id"], "task_id": tid, "status": st.status})
        logger.info("[task_bridge] note %s <- task %s is %s", note["id"], tid, st.status)
    return out


def summary() -> str:
    """One line per open commitment, for the standing world. '' when there are none.

    Kept SHORT on purpose: this competes for the standing world's 180-word budget against her
    memory of him, and a to-do list is not more important than that.
    """
    rows = open_task_notes()
    if not rows:
        return ""
    bits = []
    for r in rows[:4]:
        t = (r.get("title") or "").strip()
        if not t:
            continue
        st = r.get("task_status")
        bits.append("%s%s" % (t[:60], " (in progress)" if st == "running" else ""))
    return "; ".join(bits)


def run_bridge(limit: int = 5) -> Dict[str, object]:
    """Both halves, in the order that matters: report finished work FIRST, then enqueue new.

    Writeback before promote so a note whose task finished this cycle is marked done and is not
    immediately re-promoted by the same pass.
    """
    if not enabled():
        return {"enabled": False}
    wrote = writeback()
    posted = promote(limit=limit)
    return {"enabled": True, "written_back": wrote, "promoted": posted}
