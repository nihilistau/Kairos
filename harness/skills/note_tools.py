"""THE NOTE TOOLS — the board, in her hands.

These are written to be CALLED BY A 12B, which means three constraints shaped them, and all
three were paid for elsewhere in this system:

  1. A TOOL WITH NO DOCSTRING IS A TOOL SHE GUESSES AT. The personality tools shipped with
     their help in the decorator while the schema was built from __doc__, so she saw empty
     descriptions, invented `adjust_mood(new="calm")`, and blew the tool loop on a
     TypeError. Every argument here is named, typed in prose, and shown in an example.

  2. A TOOL THAT IS NOT IN THE LIVE SET DOES NOT EXIST. recall() sat in MEMORY_TOOLS_EXTRA
     for weeks — correct, gated, wired into nothing — so she answered "what is my name?"
     from her persona instead of looking it up. These join default_tools().

  3. FEW TOOLS, OR SHE PICKS BADLY. agent.py's own comment: "a 12B picks reliably and fast
     from ~6 tools; 14 overwhelms it (it explores and stalls)". So this is FIVE verbs, not
     the eight the feature naturally wants. `add_note` absorbs "remind me" (a note with a
     due date IS a reminder); `find_notes` with no query absorbs "list them all".

AND `due` TAKES ENGLISH. Asking a 12B to emit "2026-07-17T09:00:00Z" is asking for a
malformed timestamp and a silent no-op reminder. It says "friday", "tomorrow 9am", "in 2
hours" — the words he used — and the PARSER does the arithmetic, where arithmetic belongs.
"""
from __future__ import annotations

from contextlib import contextmanager

from harness.skills import notes as N
from harness.skills.duetime import parse_due


@contextmanager
def _mine():
    """THESE TOOLS ARE ONLY EVER CALLED BY HER. The panel writes through /v1/notes/* and
    stamps `user`; the model writes through here and stamps `self`. Ownership is decided by
    WHICH DOOR THE WRITE CAME THROUGH, never inferred from the words — the fact store lost
    Sam's name and then his gender to exactly that mistake, twice in one day.

    A context manager, token-RESET on exit (2026-08-19): the old `N.set_author(SELF)`
    with no restore left the rest of the surrounding context stamped `self` — the
    clobber class G-AUTHOR-CTX closed in memory's twin."""
    tok = N.set_author(N.SPEAKER_SELF)
    try:
        yield
    finally:
        N._AUTHOR.reset(tok)


def _fmt(n: dict) -> str:
    bits = [f"[{n['id']}]", f"({n.get('category', 'note')})", n.get("title", "")]
    if n.get("due_at"):
        bits.append("— due " + n["due_at"][:16].replace("T", " ") + ("  ✓done" if n.get("done") else ""))
    bits.append("· by " + ("you" if n.get("speaker") == "self" else "Sam"))
    return " ".join(b for b in bits if b)


def add_note(title: str, body: str = "", category: str = "note", due: str = "") -> str:
    """Pin a note, idea, task or REMINDER to the shared board that Sam can see.

    title     one short line — what it is (required)
    body      the detail, if there is any (optional)
    category  one of: idea, reminder, task, important, note
    due       WHEN, in plain English, for a reminder: "friday", "tomorrow 9am",
              "in 2 hours", "2026-07-17". Leave empty for a plain note.

    A note with a `due` IS a reminder — you will bring it up yourself when it comes due.

    e.g. add_note("Buy a 3090 if stock returns", category="idea")
         add_note("Call the NUC supplier", due="friday 10am")   <- "remind me to..."
    """
    iso, human = parse_due(due)
    if due and not iso:
        return (f"(could not read '{due}' as a time — try 'friday', 'tomorrow 9am', "
                f"'in 2 hours', or a date like 2026-07-17)")
    with _mine():
        n = N.add(title=title, body=body, category=category, due_at=iso)
    return f"noted: {_fmt(n)}" + (f"  (I'll remind you {human})" if iso else "")


def watch_for(title: str, look_for: str) -> str:
    """KEEP AN EYE OUT for something in the world, and tell him when it happens.

    title      what he is waiting for, e.g. "RTX 3090 back in stock"
    look_for   what to SEARCH for, as a search query: "RTX 3090 in stock under $1500"

    e.g. watch_for("3090 available", look_for="RTX 3090 in stock buy")

    THIS IS THE ONLY WAY YOU CAN ACTUALLY WATCH FOR ANYTHING. If you tell him "I'll look out
    for X" without calling this, nothing will look, nothing will happen, and he will find out
    weeks later that you never meant it. You may say you will keep an eye out ONLY if you
    have called this — then it is true: the harness searches for you every few hours, and
    when it finds real evidence, you tell him and show him the link."""
    look_for = (look_for or title or "").strip()
    if not look_for:
        return "(a watch needs something to look for)"
    with _mine():
        n = N.add(title=title, category="watch", watch=look_for)
    return (f"watching: {_fmt(n)}  (searching for {look_for!r} every few hours — "
            f"I'll tell you when something real turns up)")


def find_notes(query: str = "") -> str:
    """Search the board — or show ALL of it when `query` is empty.

    Use this whenever he asks what is on the board, whether he wrote something down, or
    what his ideas/tasks were. e.g. find_notes("gpu"), find_notes()"""
    rows = N.search(query) if query else N.live()
    if not rows:
        return f"(nothing on the board about '{query}')" if query else "(the board is empty)"
    return "\n".join(_fmt(n) for n in rows)


def due_reminders() -> str:
    """What Sam should be reminded about RIGHT NOW. Use this when he asks "is there
    anything I need to be reminded about?" and answer from what it returns."""
    rows = N.due(include_raised=True)
    if not rows:
        return "(nothing is due)"
    return "\n".join(_fmt(n) for n in rows)


def edit_note(note_id: str, title: str = "", body: str = "",
              category: str = "", due: str = "", done: str = "") -> str:
    """Change a note already on the board. Pass its id — the [xxxx] shown in the listing —
    and ONLY the fields you are changing.

    e.g. edit_note("a1b2c3d4e5f6", done="yes")          — tick it off
         edit_note("a1b2c3d4e5f6", due="next monday")   — move it
    """
    fields: dict = {}
    if title:
        fields["title"] = title
    if body:
        fields["body"] = body
    if category:
        fields["category"] = category
    if due:
        iso, _ = parse_due(due)
        if not iso:
            return f"(could not read '{due}' as a time)"
        fields["due_at"] = iso
        fields["raised"] = False        # it moved, so it may be raised again
    if done:
        fields["done"] = str(done).strip().lower() in ("1", "true", "yes", "y", "done")
    if not fields:
        return "(nothing to change — pass a field)"
    with _mine():
        n = N.update(note_id, **fields)
    return f"updated: {_fmt(n)}" if n else f"(no note with id {note_id})"


def remove_note(note_id: str) -> str:
    """Take a note off the board. Tombstoned, not destroyed.

    e.g. remove_note("a1b2c3d4e5f6")"""
    with _mine():
        n = N.remove(note_id)
    return f"removed: {n.get('title')}" if n else f"(no note with id {note_id})"


NOTE_TOOLS = [add_note, watch_for, find_notes, due_reminders, edit_note, remove_note]
