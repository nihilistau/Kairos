"""TEXAS HOLD'EM — the betting engine, where the real difficulty lives.

Hand strength (cards.py) is the easy half: a total order over score tuples, checkable
against rankings the world agreed on. THIS file is the half that is hard, and it is hard
for reasons that have nothing to do with cards.

FOUR RULES THAT ALMOST EVERY HOME-GROWN IMPLEMENTATION GETS WRONG. Each one is asserted
in G-HOLDEM, because each produces a game that looks like poker and is not:

  1. HEADS-UP BLINDS ARE BACKWARDS. With two players the BUTTON posts the SMALL blind
     and acts FIRST preflop — then acts LAST on every later street. Implementations
     generalise the multi-way rule ("button is last, blinds are left of the button") and
     get heads-up exactly inverted, which changes every preflop decision in the game.

  2. WHEN A BETTING ROUND ENDS is not "everyone has matched the bet". It is "everyone
     still in has acted AND matched the current bet". A big blind who is merely called
     has matched it without having acted — the option to raise is theirs and the round
     is not over. Miss this and you silently rob the big blind of the option, every hand.

  3. AN ALL-IN FOR LESS THAN A FULL RAISE DOES NOT REOPEN THE BETTING. If a short stack
     puts in a raise smaller than the minimum, players who already acted may call it but
     may not re-raise. Getting this wrong lets a tiny all-in be used to reopen a pot.

  4. SIDE POTS. When players are all in for different amounts, the pot splits into
     layers, and each layer is contested only by the players who paid into it. A short
     stack cannot win chips they were never able to cover. This is the single most
     commonly broken rule in amateur poker code, and it is silently broken — the chips
     still add up, they just go to the wrong person.

AND THE STRUCTURAL DIFFERENCE FROM CHESS: hidden information. A chess `public()` could
hand everyone the same payload. Here the state is a function of the game AND WHO IS
LOOKING — you see your hole cards, not mine, and neither of us sees the deck. So the
view is per-seat by construction, and there is no all-seeing payload to leak from.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from harness.games import cards as C

STREETS = ("preflop", "flop", "turn", "river", "showdown")
ACTIONS = ("fold", "check", "call", "bet", "raise", "allin")


# ── setup ────────────────────────────────────────────────────────────────────────
def new_hand(names: List[str], stacks: List[int], button: int,
             seed: str, sb: int = 1, bb: int = 2) -> Dict[str, Any]:
    deck = C.shuffled(seed)
    n = len(names)
    seats = []
    for i, (nm, st) in enumerate(zip(names, stacks)):
        seats.append({"name": nm, "stack": int(st), "hole": [], "folded": False,
                      "allin": False, "street_bet": 0, "committed": 0})
    for _ in range(2):                       # deal one at a time, as at a table
        for s in seats:
            s["hole"].append(deck.pop())

    h: Dict[str, Any] = {
        "seats": seats, "button": button % n, "street": "preflop", "board": [],
        "deck": deck, "sb": sb, "bb": bb, "pots": [], "log": [],
        "current_bet": 0, "min_raise": bb, "last_aggressor": None,
        "acted": [], "to_act": None, "over": False, "result": None, "winners": [],
    }

    # HEADS-UP IS INVERTED. With two players the button IS the small blind; with three
    # or more the blinds sit to its left. Rule 1 above.
    if n == 2:
        sb_seat, bb_seat = h["button"], (h["button"] + 1) % n
    else:
        sb_seat, bb_seat = (h["button"] + 1) % n, (h["button"] + 2) % n
    _post(h, sb_seat, sb)
    _post(h, bb_seat, bb)
    h["current_bet"] = bb
    h["min_raise"] = bb
    h["last_aggressor"] = bb_seat
    # ...and preflop, the button acts first heads-up; otherwise it is left of the BB.
    h["to_act"] = h["button"] if n == 2 else (bb_seat + 1) % n
    h["bb_seat"] = bb_seat
    h["log"].append("blinds %d/%d posted" % (sb, bb))
    return h


def _post(h: Dict[str, Any], i: int, amount: int) -> None:
    s = h["seats"][i]
    pay = min(amount, s["stack"])
    s["stack"] -= pay
    s["street_bet"] += pay
    s["committed"] += pay
    if s["stack"] == 0:
        s["allin"] = True


def _live(h) -> List[int]:
    """Seats still in the hand (not folded)."""
    return [i for i, s in enumerate(h["seats"]) if not s["folded"]]


def _can_act(h) -> List[int]:
    return [i for i in _live(h) if not h["seats"][i]["allin"]]


def legal_actions(h: Dict[str, Any]) -> Dict[str, Any]:
    """What the player to act may do, with the exact amounts. Naming the options and
    their sizes is the same discipline as handing back chess's legal move list — a
    refusal that does not say what WAS possible teaches nobody anything."""
    if h["over"] or h["to_act"] is None:
        return {"actions": [], "to_call": 0}
    i = h["to_act"]
    s = h["seats"][i]
    to_call = max(0, h["current_bet"] - s["street_bet"])
    acts = ["fold"]
    if to_call == 0:
        acts.append("check")
    elif s["stack"] > 0:
        acts.append("call")
    # A raise must reach current_bet + min_raise, unless the player is going all in
    # for less — which is allowed, and by rule 3 does not reopen the betting.
    min_to = h["current_bet"] + h["min_raise"]
    max_to = s["street_bet"] + s["stack"]
    if s["stack"] > to_call:
        acts.append("raise" if h["current_bet"] > 0 else "bet")
    if s["stack"] > 0:
        acts.append("allin")
    return {"actions": acts, "to_call": min(to_call, s["stack"]),
            "min_raise_to": min(min_to, max_to), "max_raise_to": max_to,
            "stack": s["stack"], "pot": pot_total(h)}


def pot_total(h) -> int:
    return sum(s["committed"] for s in h["seats"])


def act(h: Dict[str, Any], seat: int, action: str, amount: int = 0) -> Dict[str, Any]:
    """Apply one action, or refuse it with a reason and the legal set."""
    if h["over"]:
        return {"ok": False, "error": "the hand is over"}
    if h["to_act"] != seat:
        return {"ok": False, "error": "it is %s to act" % h["seats"][h["to_act"]]["name"]}
    la = legal_actions(h)
    a = (action or "").strip().lower()
    if a not in la["actions"]:
        return {"ok": False, "error": "%r is not available" % action, **la}

    s = h["seats"][seat]
    to_call = max(0, h["current_bet"] - s["street_bet"])

    if a == "fold":
        s["folded"] = True
        h["log"].append("%s folds" % s["name"])
    elif a == "check":
        h["log"].append("%s checks" % s["name"])
    elif a == "call":
        _post(h, seat, to_call)
        h["log"].append("%s calls %d" % (s["name"], min(to_call, to_call)))
    elif a in ("bet", "raise", "allin"):
        if a == "allin":
            target = s["street_bet"] + s["stack"]
        else:
            target = int(amount or 0)
            if target < la["min_raise_to"] or target > la["max_raise_to"]:
                return {"ok": False,
                        "error": "raise must be to between %d and %d"
                                 % (la["min_raise_to"], la["max_raise_to"]), **la}
        raise_by = target - h["current_bet"]
        _post(h, seat, target - s["street_bet"])
        if raise_by >= h["min_raise"]:
            # A FULL raise reopens the betting: everyone must act again.
            h["min_raise"] = raise_by
            h["last_aggressor"] = seat
            h["acted"] = []
            h["log"].append("%s %ss to %d" % (s["name"], "raise" if a != "bet" else "bet",
                                              target))
        else:
            # RULE 3: an all-in for less than a full raise does NOT reopen betting.
            # The bet to match goes up; the right to re-raise does not come back.
            h["log"].append("%s is all in for %d (under a full raise)" % (s["name"], target))
        if target > h["current_bet"]:
            h["current_bet"] = target

    if seat not in h["acted"]:
        h["acted"].append(seat)
    _advance(h)
    return {"ok": True}


def _round_closed(h) -> bool:
    """RULE 2. Not "everyone matched the bet" — everyone still able to act must have
    ACTED and matched. A big blind who was merely called has matched without acting,
    and the option to raise is theirs."""
    able = _can_act(h)
    if len(able) <= 1 and len(_live(h)) > 1:
        # nobody left who can act (all but one all-in): the street is done
        return all(h["seats"][i]["street_bet"] == h["current_bet"] or
                   h["seats"][i]["allin"] for i in _live(h))
    for i in able:
        if i not in h["acted"]:
            return False
        if h["seats"][i]["street_bet"] != h["current_bet"]:
            return False
    return True


def _advance(h) -> None:
    live = _live(h)
    if len(live) == 1:
        _award_uncontested(h, live[0])
        return
    if not _round_closed(h):
        h["to_act"] = _next_to_act(h)
        return
    _next_street(h)


def _next_to_act(h) -> Optional[int]:
    n = len(h["seats"])
    i = h["to_act"]
    for step in range(1, n + 1):
        j = (i + step) % n
        s = h["seats"][j]
        if s["folded"] or s["allin"]:
            continue
        if j not in h["acted"] or s["street_bet"] != h["current_bet"]:
            return j
    return None


def _next_street(h) -> None:
    for s in h["seats"]:
        s["street_bet"] = 0
    h["current_bet"] = 0
    h["min_raise"] = h["bb"]
    h["acted"] = []
    order = STREETS.index(h["street"])
    nxt = STREETS[order + 1] if order + 1 < len(STREETS) else "showdown"
    h["street"] = nxt
    if nxt == "flop":
        h["deck"].pop()                                   # burn
        h["board"] = [h["deck"].pop() for _ in range(3)]
    elif nxt in ("turn", "river"):
        h["deck"].pop()
        h["board"].append(h["deck"].pop())
    if nxt == "showdown" or len(_can_act(h)) <= 1:
        if nxt != "showdown":
            # everyone is all in: run the rest of the board out, no more betting
            while len(h["board"]) < 5:
                h["deck"].pop()
                h["board"].append(h["deck"].pop())
            h["street"] = "showdown"
        _showdown(h)
        return
    # POSTFLOP the button acts LAST, so action starts to its left — which heads-up
    # means the non-button player, the exact inversion of the preflop order.
    n = len(h["seats"])
    start = (h["button"] + 1) % n
    for step in range(n):
        j = (start + step) % n
        if not h["seats"][j]["folded"] and not h["seats"][j]["allin"]:
            h["to_act"] = j
            return
    h["to_act"] = None


# ── the pot ──────────────────────────────────────────────────────────────────────
def side_pots(h) -> List[Dict[str, Any]]:
    """RULE 4. Split the money into layers by how much each player could cover.

    Everyone who paid at least X into the hand contests the layer up to X. A player who
    was all in for less simply is not eligible for the layers above their contribution —
    they cannot win chips they were never able to cover.

    Folded players' chips STAY in the pot (they are dead money) but folded players are
    never eligible to win any of it.
    """
    levels = sorted({s["committed"] for s in h["seats"] if s["committed"] > 0})
    pots: List[Dict[str, Any]] = []
    prev = 0
    for lv in levels:
        amount = 0
        eligible = []
        for i, s in enumerate(h["seats"]):
            paid = min(s["committed"], lv) - min(s["committed"], prev)
            amount += max(0, paid)
            if s["committed"] >= lv and not s["folded"]:
                eligible.append(i)
        if amount > 0:
            pots.append({"amount": amount, "eligible": eligible})
        prev = lv
    return pots


def _award_uncontested(h, winner: int) -> None:
    total = pot_total(h)
    h["seats"][winner]["stack"] += total
    h["winners"] = [{"seat": winner, "amount": total, "hand": None}]
    h["log"].append("%s wins %d (everyone else folded)" % (h["seats"][winner]["name"], total))
    h["over"] = True
    h["street"] = "done"
    h["to_act"] = None


def _showdown(h) -> None:
    board = h["board"]
    scores: Dict[int, Any] = {}
    for i in _live(h):
        sc, five = C.best_of(h["seats"][i]["hole"] + board)
        scores[i] = {"score": sc, "five": five, "text": C.describe(sc)}
    awarded: Dict[int, int] = {}
    for pot in side_pots(h):
        contenders = [i for i in pot["eligible"] if i in scores]
        if not contenders:
            continue
        best = max(scores[i]["score"] for i in contenders)
        winners = [i for i in contenders if scores[i]["score"] == best]
        share, rem = divmod(pot["amount"], len(winners))
        for k, i in enumerate(winners):
            # An odd chip goes to the first winner left of the button — arbitrary but it
            # has to go SOMEWHERE, and silently dropping it loses money from the table.
            awarded[i] = awarded.get(i, 0) + share + (1 if k < rem else 0)
    for i, amt in awarded.items():
        h["seats"][i]["stack"] += amt
    h["winners"] = [{"seat": i, "amount": amt, "hand": scores[i]["text"],
                     "five": scores[i]["five"]} for i, amt in sorted(awarded.items())]
    for w in h["winners"]:
        h["log"].append("%s wins %d with %s"
                        % (h["seats"][w["seat"]]["name"], w["amount"], w["hand"]))
    h["over"] = True
    h["street"] = "done"
    h["to_act"] = None
    h["showdown"] = {i: scores[i]["text"] for i in scores}


# ── what a given seat may SEE ────────────────────────────────────────────────────
def view(h: Dict[str, Any], seat: Optional[int]) -> Dict[str, Any]:
    """The state AS SEEN BY `seat`. There is deliberately no all-seeing payload.

    You see your own hole cards. You never see anyone else's until showdown, and nobody
    ever sees the deck. `seat=None` is a spectator and sees neither. This is the whole
    reason chess's single `public()` could not be reused: the correct payload depends on
    who is asking, so the only safe design is one that cannot be asked the wrong way.
    """
    shown = h["over"] and bool(h.get("showdown"))
    seats = []
    for i, s in enumerate(h["seats"]):
        mine = (seat is not None and i == seat)
        seats.append({
            "name": s["name"], "stack": s["stack"], "folded": s["folded"],
            "allin": s["allin"], "street_bet": s["street_bet"], "committed": s["committed"],
            "hole": s["hole"] if (mine or (shown and not s["folded"])) else None,
            "you": mine,
        })
    d = {
        "street": h["street"], "board": list(h["board"]), "pot": pot_total(h),
        "seats": seats, "button": h["button"], "to_act": h["to_act"],
        "over": h["over"], "winners": h["winners"], "log": h["log"][-12:],
        "sb": h["sb"], "bb": h["bb"],
    }
    if seat is not None and h["to_act"] == seat and not h["over"]:
        d["options"] = legal_actions(h)
    return d
