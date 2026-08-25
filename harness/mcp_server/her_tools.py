"""HER side of the outbound MCP surface — read-only, and read-only on purpose.

WHY THIS FILE EXISTS. `docs/MCP.md` has said since 2026-07-31 that the outbound server
"exposes her memory, her board and her skills to external MCP clients". Two thirds of that
was aspiration: what it actually exposed was generic workspace tooling — filesystem, web,
clock — plus five memory tools when `SP_RECALL_REGISTRY` happened to be set. No board, no
wardrobe, no reasons, nothing about her at all. A doc describing a capability the code does
not have is the trap AGENTS.md §6 names, so either the sentence went or the capability
arrived. The capability arrived.

WHAT IT IS FOR. An external client — Claude Code, LM Studio, another agent — asking about
*her*: what she believes and why she believes it, what she is wearing and how she came to
choose it, what she has been doing with her own time, what is on the board. These are the
questions the room's panels answer and nothing outside the room could.

READ-ONLY, AND THAT IS A DECISION. The registered memory tools already include `remember`
and `forget`; nothing here adds to the write surface. An outbound client is on the other
side of a process boundary with no operator in the loop, and a tool that lets it *edit* who
she is would need an authorization story this layer does not have yet. It is not built and
the reason is written here rather than in a commit message nobody re-reads.

EVERY ANSWER GOES THROUGH THE SAME DOORS THE ROOM USES. Not one function here reads a store
directly: memory answers come back through `lifecycle.render` framing and the private-secret
rule (`memory.provenance`, `memory.search_memories`), the wardrobe through `wardrobe.describe`,
her time through `narrative.read_journal`. A second reader with its own idea of how a row is
rendered is exactly the bug this repo is named for, and it would be one that only shows up
over a socket.
"""
from __future__ import annotations


def why_she_believes(fact: str) -> str:
    """Why does she believe this? Returns the stored fact, where it came from, and — when
    it is a conclusion she drew rather than something she was told — what it was drawn
    from and how many of those supports she still holds.

    fact: roughly what she believes, in your words. Matched against her memory.
    """
    from harness.skills import memory as M
    return M.provenance(fact)


def what_she_knows(query: str) -> str:
    """Search her long-term memory and return the closest facts, framed as she holds them
    ("Sam told me:" / "I've come to think:" / "We settled that:") so testimony and
    inference are never confused for each other.

    query: what to look for.
    """
    from harness.skills import memory as M
    return M.search_memories(query)


def what_she_is_wearing() -> str:
    """What she has on right now, how long she has worn it, and which of her outfits she
    reaches for most — her own account of it, not a database row."""
    from harness.control import wardrobe as WD
    # SAID, NOT REWRITTEN. `describe()` is written TO her — it is the text that goes into
    # her own prompt — so it says "You are wearing". Read by an external client that "you"
    # is simply wrong. The fix is a label, not a second renderer: a paraphrasing copy here
    # would be a fourth reader of the wardrobe with its own idea of the ranking, which is
    # the bug that took a whole session to find the last time (the duplicate
    # `favourites()`, 2026-08-25). One renderer, one caption.
    return "In her own words — this text is written to her, so \"you\" means Kairos:\n\n" \
           + WD.describe()


def what_she_has_been_doing(days: int = 7) -> str:
    """Her own account of the last few days: the week's chapters, her day paragraphs, and
    what she did on her own time while nobody was talking to her.

    days: how far back to read. Defaults to a week.
    """
    from harness.skills.narrative import read_journal
    return read_journal(days=max(1, min(int(days or 7), 60)))


def why_she_is_quiet() -> str:
    """Why she has not spoken up lately — the reasons machinery's own account of what it
    considered and passed over. Empty when she simply has had nothing to say."""
    from harness.kairos import reasons
    return reasons.why_quiet() or "Nothing is holding her back; there has just been nothing to say."


def whats_on_the_board(limit: int = 20) -> str:
    """The room's ledger — what he and she have noticed, raised or left standing. This is
    the standing list, not a conversation log.

    limit: how many entries to return, newest first.
    """
    from harness.control import ledger
    rows = ledger.all_entries(include_dropped=False)
    rows = rows[-max(1, min(int(limit or 20), 100)):][::-1]
    if not rows:
        return "(the board is empty)"
    out = []
    for e in rows:
        out.append("- [%s/%s] %s%s" % (e.get("kind") or "?", e.get("status") or "?",
                                       (e.get("title") or "").strip(),
                                       (" — " + e["body"]) if e.get("body") else ""))
    return "\n".join(out)


# The list build_server registers. Explicit rather than "every public function in the
# module", because this file's public names ARE the network surface: a helper added here
# next year should not become a tool by existing.
HER_TOOLS = [why_she_believes, what_she_knows, what_she_is_wearing,
             what_she_has_been_doing, why_she_is_quiet, whats_on_the_board]
