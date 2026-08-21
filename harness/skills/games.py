"""games.py — the board, as tools she can reach for.

FOUR TOOLS, AND ONE OF THEM IS THE POINT. `see_board` renders the position to a PNG and
runs it through her own vision tower, so she LOOKS at the board instead of parsing a FEN.
That is the most direct use of sight built so far, and it is the reason the first game is
chess rather than something cheaper: a FEN is a string she is bad at in exactly the way
she is bad at legality, and a board is a thing to see.

SHE PROPOSES; THE ENGINE RULES. `play_move` hands the move to harness/games/match.py,
which admits it or refuses it. A refusal comes back WITH THE LEGAL LIST — telling a model
"illegal move" and nothing else guarantees it proposes the same move again, and the
alternatives are the single most useful sentence to say back. Nothing here can corrupt a
board, because nothing here writes one.

SHE CANNOT SEE THE ANSWER. `game_state` returns match.public(), which withholds the
wordle word until the game ends. That is not politeness — a player who can read the
hidden state is not playing, and she would have no way to un-know it.
"""
from __future__ import annotations

import os
from typing import List

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _shot_path(mid: str) -> str:
    return os.path.join(_ROOT, "var", "room", "games", "shots", "%s.png" % mid.replace(os.sep, "_"))


def list_games() -> str:
    """List the games in progress and how far along each one is."""
    from harness.games import match as M
    rows = M.listing()
    if not rows:
        return "No games in progress. start_game('chess') or start_game('wordle') begins one."
    return "\n".join(
        "%s — %s, %d move(s)%s" % (r["id"], r["kind"], r["moves"],
                                   (", over: %s" % r["result"]) if r["over"] else "")
        for r in rows)


def start_game(kind: str = "chess", name: str = "") -> str:
    """Start a game. kind is 'chess' or 'wordle'; name is an optional id for the match."""
    from harness.games import match as M
    mid = (name or kind).strip() or kind
    try:
        M.new(kind.strip().lower(), mid)
    except ValueError as exc:
        return "[%s]" % exc
    return "Started %s as %r. game_state(%r) to see it." % (kind, mid, mid)


def game_state(name: str = "chess") -> str:
    """Where a game stands: whose turn, the board, and what may legally be played."""
    from harness.games import match as M
    m = M.load(name)
    if m is None:
        return "No game called %r. list_games() shows what is running." % name
    st = M.public(m)
    if st["kind"] == "chess":
        head = "%s to move%s" % (st["side"], " — IN CHECK" if st["in_check"] else "")
        if st["over"]:
            head = "over: %s (%s)" % (st["result"], st["reason"])
        legal = st["legal"]
        return "%s\n\n%s\n\nlegal (%d): %s" % (
            head, st["ascii"], len(legal), " ".join(legal[:60]))
    lines = ["%s  %s" % (g, m2) for g, m2 in zip(st["history"], st["marks"])]
    tail = ("over: %s (%s)" % (st["result"], st["reason"])) if st["over"] \
        else "%d tries left. g=right letter right place, y=right letter wrong place, .=absent" \
             % st["tries_left"]
    return ("\n".join(lines) + "\n\n" + tail) if lines else tail


def play_move(move: str, name: str = "chess") -> str:
    """Play one move. Chess takes e2e4 or Nf3 or O-O; wordle takes a five-letter word."""
    from harness.games import match as M
    r = M.play(name, move)
    if not r["ok"]:
        extra = ""
        if r.get("legal"):
            extra = "\nlegal here (%d): %s" % (r["legal_count"], " ".join(r["legal"]))
        return "[refused: %s]%s" % (r["error"], extra)
    st = r["state"]
    if st["over"]:
        return "%s\n\nGAME OVER — %s (%s)" % (game_state(name), st["result"], st["reason"])
    return game_state(name)


def see_board(name: str = "chess", question: str = "") -> str:
    """LOOK at the board with your own eyes — renders it and describes what is there."""
    from harness.games import match as M
    from harness.games import render as R
    m = M.load(name)
    if m is None:
        return "No game called %r." % name
    if m["kind"] != "chess":
        return "Only the chess board can be looked at; %r is a word game." % name
    last = (m["history"] or [None])[-1]
    path = R.board_png(m["fen"], _shot_path(name), last=last)
    if not path:
        # PIL absent. Say so and hand back the text board rather than an empty string —
        # a sense that fails silently is worse than one that is missing.
        return "[cannot draw the board here — reading it as text instead]\n\n" + game_state(name)
    from harness.skills.sight import look_at
    q = question or ("A chess board. Read it rank by rank and say which pieces are where, "
                     "using the coordinates printed in the margin. The gold square is the "
                     "move just played.")
    return look_at(path, q)


GAME_TOOLS = [list_games, start_game, game_state, play_move, see_board]


def game_tools() -> List:
    """ToolSpecs, or [] when games are not armed. A tool that always answers 'not armed'
    is worse than one that is absent — she keeps reaching for it. Same rule as sight."""
    if os.environ.get("SP_GAMES", "0") != "1":
        return []
    from harness.toolcore.tools import ToolSpec
    return [ToolSpec.from_callable(fn) for fn in GAME_TOOLS]
