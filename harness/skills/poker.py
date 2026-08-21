"""poker.py — the table, as tools she can reach for.

SHE SITS IN SEAT 1 AND CANNOT LEAVE IT. Every tool here resolves her view through
`match.holdem_view(m, HER_SEAT)`, and that function is the only way in — there is no
argument for "which seat", and no tool returns the raw hand record. So she cannot see
his hole cards, cannot see the deck, and cannot be talked into it either. The protection
is structural rather than behavioural, which matters more here than anywhere else in
this codebase: a model asked nicely enough will usually do the thing, and "don't look at
the opponent's cards" is exactly the instruction a persuasive turn could erode.

It is worth being plain that this cuts both ways and is meant to. The same design that
stops her peeking is what stops the room showing her cards to him — the panel asks for
seat 0 and gets seat 0. Neither side is trusted; neither side needs to be.

WHAT SHE ACTUALLY NEEDS TO PLAY WELL is not the cards, it is the numbers that make a
decision: what it costs to call, what is already in the pot, and therefore the price she
is being offered. `poker_state` computes the pot odds and says them out loud, because a
model that has to derive them mid-sentence will sometimes derive them wrong, and a wrong
price is a wrong fold.
"""
from __future__ import annotations

import os
from typing import List

HER_SEAT = 1          # seat 0 is his chair. This is not configurable on purpose.


def _table(name: str = "poker"):
    """HER VIEW, AND NOTHING ELSE.

    The first cut returned `(match, view)`. Nothing used the match — but handing back
    the record that CONTAINS both players' cards means the leak is one careless edit
    away, and G-HOLDEM said so. Returning only the view means the raw hand never enters
    this module's scope at all.
    """
    from harness.games import match as M
    m = M.load(name)
    if m is None or m.get("kind") != "holdem":
        return None
    return M.holdem_view(m, HER_SEAT)


def poker_state(name: str = "poker") -> str:
    """Where the hand stands: your cards, the board, the pot, and what it costs to play."""
    v = _table(name)
    if v is None:
        return "No poker match called %r. start_game('holdem') deals one." % name
    me = v["seats"][HER_SEAT]
    him = v["seats"][1 - HER_SEAT]
    lines = [
        "%s — hand %d, %s" % (name, v["hand_no"], v["street"]),
        "board: %s" % (" ".join(v["board"]) if v["board"] else "(none yet)"),
        "your cards: %s" % " ".join(me["hole"] or []),
        "pot: %d   you: %d chips   %s: %d chips"
        % (v["pot"], me["stack"], him["name"], him["stack"]),
    ]
    if v["over"]:
        for w in v["winners"]:
            lines.append("HAND OVER — %s wins %d%s"
                         % (v["seats"][w["seat"]]["name"], w["amount"],
                            (" with %s" % w["hand"]) if w["hand"] else ""))
        lines.append("poker_deal() starts the next hand.")
    elif v["to_act"] != HER_SEAT:
        lines.append("waiting for %s to act." % him["name"])
    else:
        o = v.get("options") or {}
        lines.append("YOUR ACTION: %s" % ", ".join(o.get("actions", [])))
        call = o.get("to_call", 0)
        if call:
            # THE PRICE, stated rather than left to be derived mid-sentence. Calling
            # `call` to win `pot` needs equity of call/(pot+call) to break even.
            need = 100.0 * call / (v["pot"] + call) if (v["pot"] + call) else 0.0
            lines.append("it costs %d to call into a pot of %d — you need about %.0f%% "
                         "to break even" % (call, v["pot"], need))
        else:
            lines.append("checking is free.")
        if "min_raise_to" in o:
            lines.append("a raise must be to between %d and %d"
                         % (o["min_raise_to"], o["max_raise_to"]))
    if v["log"]:
        lines.append("recent: " + " | ".join(v["log"][-4:]))
    return "\n".join(lines)


def poker_act(action: str, amount: int = 0, name: str = "poker") -> str:
    """Act: fold, check, call, or raise with an amount (the total you are raising TO)."""
    from harness.games import match as M
    v = _table(name)
    if v is None:
        return "No poker match called %r." % name
    if v["over"]:
        return "The hand is finished. poker_deal() starts the next one."
    if v["to_act"] != HER_SEAT:
        return "Not your turn — it is %s to act." % v["seats"][1 - HER_SEAT]["name"]
    a = (action or "").strip().lower()
    move = a if not amount else "%s %d" % (a, int(amount))
    r = M.play(name, move)
    if not r["ok"]:
        # The refusal names what WAS available, same discipline as the chess legal list.
        opts = ", ".join((r.get("actions") or []))
        return "[refused: %s]%s" % (r["error"], ("\navailable: " + opts) if opts else "")
    return poker_state(name)


def poker_deal(name: str = "poker") -> str:
    """Deal the next hand once the current one is finished."""
    from harness.games import match as M
    r = M.deal_next(name)
    if not r["ok"]:
        return "[%s]" % r["error"]
    return poker_state(name)


POKER_TOOLS = [poker_state, poker_act, poker_deal]


def poker_tools() -> List:
    """[] unless games are armed — same rule as sight and the board tools. A tool that
    always answers 'not armed' is worse than one that is absent."""
    if os.environ.get("SP_GAMES", "0") != "1":
        return []
    from harness.toolcore.tools import ToolSpec
    return [ToolSpec.from_callable(fn) for fn in POKER_TOOLS]
