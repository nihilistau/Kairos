"""THE MATCH — one record per game in progress, and the only place a move is admitted.

Every game here answers the same three questions: what are the LEGAL moves, what does
applying one do, and is it OVER. That is the whole protocol, and it is deliberately the
same shape as the roleplay ladder: the model proposes, a committed table rules. She never
"decides" a move is legal. She names one, and this file either admits it or refuses it
with a reason she can read.

WHY THAT MATTERS MORE HERE THAN ANYWHERE. A 26B asked to play chess produces moves that
look like chess: bishops that change colour, a king that strolls out of check, a piece
that was captured four moves ago reappearing. She is not reasoning about legality — she
is completing text that resembles a game, and no amount of prompting fixes it because the
prompt is not where the rule lives. Here it is `chess.parse()` filtering the legal list,
so an illegal move is a refusal, not a corrupted board.

THREEFOLD REPETITION LIVES HERE, not in chess.py. It is a property of the game's HISTORY,
and a position does not know how it got here — so the position rules on itself and the
match rules on the story.

Persistence follows scenes: one JSON file per match under var/room/games/, written
atomically, state only. A restart mid-game must not lose the board.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional

from harness.store_io import replace_atomic
from harness.games import chess as CH
from harness.games import holdem as HE
from harness.games import words as WD

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

KINDS = ("chess", "wordle", "holdem")

_LOCK = threading.RLock()
_CACHE: Dict[str, dict] = {}


def games_dir() -> str:
    d = os.environ.get("SP_GAMES_DIR")
    if d:
        return d
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "var", "room", "games")


def _safe(mid: str) -> str:
    """A match id becomes a FILENAME, so anything that is not a plain token is HASHED
    rather than sanitised — the same rule as the scene store, for the same reason."""
    t = str(mid or "default")
    if re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", t) and not t.startswith("."):
        return t
    return "h" + hashlib.sha256(t.encode("utf-8")).hexdigest()[:24]


def _path(mid: str) -> str:
    return os.path.join(games_dir(), _safe(mid) + ".json")


def _write(m: dict) -> None:
    p = _path(m["id"])
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        # `_mtime` is cache bookkeeping, not match state. It must never reach the file
        # (where it would be stale by definition) nor a payload.
        json.dump({k: v for k, v in m.items() if k != "_mtime"}, f)
    replace_atomic(tmp, p)
    try:
        m["_mtime"] = os.path.getmtime(p)     # keep the writer's own cache entry valid
    except OSError:
        m.pop("_mtime", None)


def load(mid: str) -> Optional[dict]:
    """Read a match, preferring the cache ONLY while the file has not moved under it.

    THE CACHE WAS A SECOND COPY OF THE TRUTH. A plain memoise made `load()` answer from
    memory forever while `listing()` read the directory, so the two disagreed the moment
    anything wrote the file from outside this process — which is exactly what happened
    the first time a board was driven from a script while the room had it open: the panel
    showed move 1 of a five-move game and was perfectly confident about it.

    Validating on mtime costs one stat per read on a file measured in hundreds of bytes,
    and removes the whole divergence class rather than the one symptom.
    """
    with _LOCK:
        p = _path(mid)
        try:
            stamp = os.path.getmtime(p)
        except OSError:
            _CACHE.pop(mid, None)          # the file is gone; so is the memory of it
            return None
        m = _CACHE.get(mid)
        if m is not None and m.get("_mtime") == stamp:
            return m
        try:
            with open(p, "r", encoding="utf-8") as f:
                m = json.load(f)
        except Exception as _swx:
            _swallowed(_swlog, "load", _swx, lane="games")
            return None
        m["_mtime"] = stamp
        _CACHE[mid] = m
        return m


def listing() -> List[dict]:
    out = []
    try:
        names = sorted(os.listdir(games_dir()))
    except Exception:
        return out
    for n in names:
        if not n.endswith(".json"):
            continue
        try:
            with open(os.path.join(games_dir(), n), "r", encoding="utf-8") as f:
                m = json.load(f)
            out.append({"id": m.get("id"), "kind": m.get("kind"),
                        "over": bool(m.get("over")), "result": m.get("result"),
                        "moves": len(m.get("history") or []), "started": m.get("started")})
        except Exception:
            continue
    return out


def new(kind: str, mid: str, seed: str = "") -> dict:
    if kind not in KINDS:
        raise ValueError("unknown game %r (want one of %s)" % (kind, ", ".join(KINDS)))
    m: Dict[str, Any] = {"id": mid, "kind": kind, "history": [], "started": int(time.time()),
                         "over": False, "result": None, "reason": None}
    if kind == "chess":
        m["fen"] = CH.START
        m["seen"] = [CH.Position(CH.START).fen().rsplit(" ", 2)[0]]
    elif kind == "holdem":
        # Heads-up, him against her/me. The engine seats N and does side pots properly,
        # so a third chair is a config change rather than a rewrite — but two is the
        # form worth playing first, and the one where the blind rules are inverted.
        m["stacks"] = [200, 200]
        m["names"] = ["sam", "kairos"]
        m["button"] = 0
        m["hand_no"] = 0
        m["hand"] = HE.new_hand(m["names"], m["stacks"], m["button"],
                                "%s#%d" % (seed or mid, 0))
    else:
        m["answer"] = WD.pick(seed or mid)
        m["marks"] = []
    with _LOCK:
        _CACHE[mid] = m
    _write(m)
    return m


def drop(mid: str) -> None:
    with _LOCK:
        _CACHE.pop(mid, None)
    try:
        os.remove(_path(mid))
    except OSError:
        pass


def legal(m: dict) -> List[str]:
    """What may be played right now. For chess this is the actual legal move list, which
    is also what gets handed to her — naming the options beats hoping she infers them."""
    if m["over"]:
        return []
    if m["kind"] == "chess":
        return [CH.uci(mv) for mv in CH.Position(m["fen"]).legal()]
    return []          # wordle: any word in the closed vocabulary, too many to list


def play(mid: str, move: str) -> dict:
    """Admit a move, or refuse it with a reason. THE ONLY WRITE PATH."""
    m = load(mid)
    if m is None:
        return {"ok": False, "error": "no such match"}
    if m["over"]:
        return {"ok": False, "error": "the game is over (%s)" % (m.get("reason") or m["result"])}

    if m["kind"] == "chess":
        pos = CH.Position(m["fen"])
        mv = CH.parse(pos, move)
        if mv is None:
            # The refusal CARRIES THE LEGAL LIST. A bare "illegal move" teaches her
            # nothing and she will propose the same one again; the alternatives are the
            # single most useful thing to say back.
            opts = [CH.uci(x) for x in pos.legal()]
            return {"ok": False, "error": "%r is not legal here" % move,
                    "legal": opts[:40], "legal_count": len(opts)}
        nxt = pos.apply(mv)
        m["fen"] = nxt.fen()
        m["history"].append(CH.uci(mv))
        key = m["fen"].rsplit(" ", 2)[0]          # position + side + castling + ep
        m["seen"].append(key)
        v = nxt.verdict()
        if not v["over"] and m["seen"].count(key) >= 3:
            v = {"over": True, "result": "1/2-1/2", "reason": "threefold repetition"}
        m.update(over=bool(v["over"]), result=v["result"], reason=v["reason"])
    elif m["kind"] == "holdem":
        h = m["hand"]
        if h["over"]:
            return {"ok": False, "error": "the hand is over — deal the next one"}
        parts = (move or "").strip().lower().split()
        act = parts[0] if parts else ""
        amt = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        r = HE.act(h, h["to_act"], act, amt)
        if not r["ok"]:
            return r
        if h["over"]:
            # The stacks live on the MATCH, not the hand — a hand is one deal, a match
            # is the money. Folding that back is what makes the next hand continue the
            # story instead of resetting it.
            m["stacks"] = [x["stack"] for x in h["seats"]]
            m["over"] = any(x <= 0 for x in m["stacks"])
            if m["over"]:
                win = 0 if m["stacks"][0] > 0 else 1
                m["result"] = m["names"][win]
                m["reason"] = "%s is out of chips" % m["names"][1 - win]
    else:
        g = (move or "").strip().lower()
        if not WD.valid(g):
            return {"ok": False, "error": "%r is not in the word list" % move}
        m["history"].append(g)
        m["marks"].append(WD.score(g, m["answer"]))
        v = WD.verdict(m["history"], m["answer"])
        m.update(over=bool(v["over"]), result=v["result"], reason=v["reason"])

    # A DRAW OFFER LAPSES WHEN A MOVE IS PLAYED. That is the actual rule, not a
    # simplification: an offer is made alongside a move and dies with the reply.
    # Leaving it standing would let an offer from twenty moves ago be accepted in a
    # position nobody offered it in.
    m.pop("draw_offer", None)

    with _LOCK:
        _CACHE[mid] = m
    _write(m)
    return {"ok": True, "state": public(m)}


# ── THE THREE THINGS PLAYING A REAL GAME FOUND MISSING ───────────────────────────
# The rules were complete and the game was still unplayable as a GAME: there was no
# way to give up, to agree a draw, or to take a move back. "gg" had nowhere to live,
# so a resigned match sat in the listing forever with no result. None of these are
# derivable from the position, which is exactly why the position-based verdict never
# produced them and why no gate missed them — they are agreements between players,
# and the board cannot know about an agreement.

def _resign_result(m: dict, side: str) -> tuple:
    if m["kind"] != "chess":
        return "lost", "resigned — it was %s" % m["answer"]
    return ("0-1" if side == "white" else "1-0"), "%s resigned" % side


def resign(mid: str, side: str = "") -> dict:
    """Give up. `side` defaults to whoever is on move, which is nearly always right."""
    m = load(mid)
    if m is None:
        return {"ok": False, "error": "no such match"}
    if m["over"]:
        return {"ok": False, "error": "the game is already over (%s)" % m["reason"]}
    who = (side or "").strip().lower()
    if m["kind"] == "chess" and who not in ("white", "black"):
        who = "white" if CH.Position(m["fen"]).side == "w" else "black"
    result, reason = _resign_result(m, who)
    m.update(over=True, result=result, reason=reason)
    m.pop("draw_offer", None)
    with _LOCK:
        _CACHE[mid] = m
    _write(m)
    return {"ok": True, "state": public(m)}


def offer_draw(mid: str, side: str = "") -> dict:
    """Offer. It stands until the opponent accepts, declines, or a move is played."""
    m = load(mid)
    if m is None:
        return {"ok": False, "error": "no such match"}
    if m["over"]:
        return {"ok": False, "error": "the game is over"}
    if m["kind"] != "chess":
        return {"ok": False, "error": "a draw needs two players; wordle has one"}
    who = (side or "").strip().lower()
    if who not in ("white", "black"):
        who = "white" if CH.Position(m["fen"]).side == "w" else "black"
    m["draw_offer"] = who
    with _LOCK:
        _CACHE[mid] = m
    _write(m)
    return {"ok": True, "state": public(m)}


def answer_draw(mid: str, accept: bool, side: str = "") -> dict:
    """Accept or decline. AN OFFER CANNOT BE ACCEPTED BY THE PLAYER WHO MADE IT.

    I wrote that rule in a docstring first and did not implement it, which made
    "offer, accept" a one-sided button that ended any game as a draw — the check
    existed only as a sentence, which is the same failure as a knob that is declared
    and read by nothing.

    `side` defaults to the opposite of the offer, so the ordinary path needs no
    argument and an explicit self-accept is refused. Being straight about the limit:
    with one person at the keyboard this prevents a MISTAKE, not a cheat. There are
    no player identities here and inventing them to police a two-player game on one
    machine would be ceremony, not security.
    """
    m = load(mid)
    if m is None:
        return {"ok": False, "error": "no such match"}
    if m["over"]:
        return {"ok": False, "error": "the game is over"}
    offer = m.get("draw_offer")
    if not offer:
        return {"ok": False, "error": "no draw has been offered"}
    who = (side or "").strip().lower() or ("black" if offer == "white" else "white")
    if who == offer:
        return {"ok": False,
                "error": "%s offered the draw and cannot accept it" % offer}
    if not accept:
        m.pop("draw_offer", None)
    else:
        m.update(over=True, result="1/2-1/2", reason="draw agreed")
        m.pop("draw_offer", None)
    with _LOCK:
        _CACHE[mid] = m
    _write(m)
    return {"ok": True, "state": public(m)}


def rewind(mid: str, plies: int = 1) -> dict:
    """Take back `plies` half-moves.

    BY REPLAY, NOT BY SNAPSHOT. The move list is the source of truth and the position
    is derived from it, so the position is rebuilt by replaying a shorter list from the
    start. Storing a stack of previous FENs would be a second copy of the same truth,
    and the two would disagree the first time anything else touched the record.

    A takeback UN-ENDS a game: `over`, `result` and `reason` are recomputed, so taking
    back the mating move really does resume play — and for wordle the answer goes back
    into hiding, which a naive implementation forgets because it only thinks about the
    board.
    """
    m = load(mid)
    if m is None:
        return {"ok": False, "error": "no such match"}
    n = max(1, int(plies or 1))
    if n > len(m["history"]):
        return {"ok": False, "error": "only %d move(s) have been played" % len(m["history"])}
    keep = m["history"][:len(m["history"]) - n]

    if m["kind"] == "chess":
        pos = CH.Position(CH.START)
        seen = [pos.fen().rsplit(" ", 2)[0]]
        for u in keep:
            mv = CH.parse(pos, u)
            if mv is None:                     # a corrupt history must not half-apply
                return {"ok": False, "error": "cannot replay history at %r" % u}
            pos = pos.apply(mv)
            seen.append(pos.fen().rsplit(" ", 2)[0])
        m["fen"] = pos.fen()
        m["seen"] = seen
        v = pos.verdict()
        if not v["over"] and seen.count(seen[-1]) >= 3:
            v = {"over": True, "result": "1/2-1/2", "reason": "threefold repetition"}
    else:
        m["marks"] = m["marks"][:len(keep)]
        v = WD.verdict(keep, m["answer"])

    m["history"] = keep
    m.update(over=bool(v["over"]), result=v["result"], reason=v["reason"])
    m.pop("draw_offer", None)
    with _LOCK:
        _CACHE[mid] = m
    _write(m)
    return {"ok": True, "state": public(m)}


def public(m: dict) -> dict:
    """What a player may see. THE ANSWER IS WITHHELD until the game ends — a state
    payload that leaks the hidden word to the panel that renders it is a game with no
    game in it, and this is the one field where being careless is unrecoverable."""
    d = {k: m[k] for k in ("id", "kind", "history", "over", "result", "reason", "started")}
    d["draw_offer"] = m.get("draw_offer")
    if m["kind"] == "holdem":
        # NO ALL-SEEING PAYLOAD. Poker state is a function of the game AND WHO IS
        # LOOKING, so this returns the SPECTATOR view (no hole cards at all) and the
        # caller must ask holdem_view(m, seat) for a player's. A public() that quietly
        # picked a seat would be the leak, and it would never look like one.
        d.update(HE.view(m["hand"], None))
        d["stacks"] = m["stacks"]
        d["names"] = m["names"]
        d["hand_no"] = m["hand_no"]
        return d
    if m["kind"] == "chess":
        pos = CH.Position(m["fen"])
        d.update(fen=m["fen"], side="white" if pos.side == "w" else "black",
                 in_check=pos.in_check(), legal=legal(m), ascii=ascii_board(pos))
    else:
        d.update(marks=m["marks"], tries_left=WD.TRIES - len(m["history"]))
        if m["over"]:
            d["answer"] = m["answer"]
    return d


def ascii_board(pos: CH.Position) -> str:
    """A text board, for her and for the log. The PNG is the better channel — she has a
    vision tower and reading a picture of a board is the point — but text always works,
    including when the render path is unavailable, and a fallback that only exists in
    theory is not a fallback."""
    rows = []
    for r in range(8):
        rows.append("%d  %s" % (8 - r, " ".join(pos.board[r * 8 + f] for f in range(8))))
    rows.append("   a b c d e f g h")
    return "\n".join(rows)


def holdem_view(m: dict, seat: int) -> dict:
    """One seat's view of a poker match. Separate from public() ON PURPOSE — the only
    safe shape for hidden information is an API that cannot be called without saying
    who is asking."""
    d = {k: m[k] for k in ("id", "kind", "over", "result", "reason", "started")}
    d.update(HE.view(m["hand"], seat))
    d.update(stacks=m["stacks"], names=m["names"], hand_no=m["hand_no"], seat=seat)
    return d


def deal_next(mid: str) -> dict:
    """Next hand: button moves, stacks carry over, a fresh seeded deck."""
    m = load(mid)
    if m is None or m["kind"] != "holdem":
        return {"ok": False, "error": "not a poker match"}
    if not m["hand"]["over"]:
        return {"ok": False, "error": "finish the current hand first"}
    if m["over"]:
        return {"ok": False, "error": "the match is over (%s)" % m["reason"]}
    m["hand_no"] += 1
    m["button"] = (m["button"] + 1) % len(m["names"])
    m["hand"] = HE.new_hand(m["names"], m["stacks"], m["button"],
                            "%s#%d" % (m["id"], m["hand_no"]))
    with _LOCK:
        _CACHE[mid] = m
    _write(m)
    return {"ok": True, "state": public(m)}
