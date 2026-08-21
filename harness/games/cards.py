"""CARDS AND HAND STRENGTH — the ruling layer for poker.

WHAT MAKES THIS DIFFERENT FROM CHESS, and it is the whole design problem: chess is a
game of PERFECT INFORMATION. Every legal move can be computed from what both players
can see, so `public()` could hand the same payload to everyone and nothing leaked.

Poker is not. There are three kinds of hidden state — the undealt deck, each player's
hole cards, and every OTHER player's hole cards — and the third one is the hard case,
because the payload is no longer a property of the game, it is a property of the game
AND WHO IS LOOKING. A single `public()` cannot be correct here. Getting that wrong does
not produce a bug you notice; it produces a game that silently is not poker.

HAND STRENGTH IS A TOTAL ORDER, AND THAT IS WHAT MAKES IT GATEABLE. Every seven-card
hand maps to a score tuple, and comparing two hands is comparing two tuples. So the
committed table is a list of hands in known order — the poker world settled these
rankings long before anyone wrote them down in Python, exactly like perft counts.

The evaluation deliberately brute-forces all 21 five-card subsets rather than using a
lookup table or bit tricks. It is a few microseconds either way at this scale, and the
obvious implementation is the one whose correctness you can read off the page. A clever
evaluator that is subtly wrong about the wheel is worse than a slow one that is right.

THE TWO RULES EVERY NAIVE IMPLEMENTATION GETS WRONG, both asserted in G-HOLDEM:
  * THE WHEEL. A-2-3-4-5 is a straight, and the ace plays LOW, so it is five-high and
    loses to 2-3-4-5-6. Treating the ace as 14 makes the wheel the best straight there is.
  * FLUSH BEATS STRAIGHT, and a straight flush is neither — it is its own category
    above quads. Scoring "highest card" without categories collapses all three.
"""
from __future__ import annotations

import hashlib
from typing import Dict, List, Sequence, Tuple

RANKS = "23456789TJQKA"
SUITS = "cdhs"
RANK_VALUE: Dict[str, int] = {r: i + 2 for i, r in enumerate(RANKS)}   # 2..14
RANK_NAME = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
             8: "eight", 9: "nine", 10: "ten", 11: "jack", 12: "queen",
             13: "king", 14: "ace"}

CATEGORY = ("high card", "pair", "two pair", "three of a kind", "straight",
            "flush", "full house", "four of a kind", "straight flush")

DECK: Tuple[str, ...] = tuple(r + s for s in SUITS for r in RANKS)


def rank_of(card: str) -> int:
    return RANK_VALUE[card[0]]


def suit_of(card: str) -> str:
    return card[1]


def shuffled(seed: str) -> List[str]:
    """A deterministic shuffle from a seed.

    DETERMINISTIC ON PURPOSE, for the same reason wordle's answer is: a hand that
    cannot be replayed cannot be debugged, and a gate cannot assert anything about
    a deal it is unable to reproduce. The seed is the hand's identity.

    Fisher-Yates driven by a SHA-256 stream. Not cryptographic shuffling for money —
    it is reproducible shuffling for a game between two people on one machine, and
    pretending otherwise would be a security claim nobody asked for and I could not
    back.
    """
    deck = list(DECK)
    stream = b""
    counter = 0
    need = len(deck) * 4
    while len(stream) < need:
        stream += hashlib.sha256(("%s|%d" % (seed, counter)).encode("utf-8")).digest()
        counter += 1
    for i in range(len(deck) - 1, 0, -1):
        word = int.from_bytes(stream[i * 4:(i + 1) * 4], "big")
        j = word % (i + 1)
        deck[i], deck[j] = deck[j], deck[i]
    return deck


def _score5(cards: Sequence[str]) -> Tuple[int, ...]:
    """Score exactly five cards. Higher tuple is a better hand, compared elementwise."""
    vals = sorted((rank_of(c) for c in cards), reverse=True)
    suits = [suit_of(c) for c in cards]
    flush = len(set(suits)) == 1

    distinct = sorted(set(vals), reverse=True)
    straight_high = 0
    if len(distinct) == 5:
        if distinct[0] - distinct[4] == 4:
            straight_high = distinct[0]
        # THE WHEEL. A-2-3-4-5, and the ace plays LOW — so this is a FIVE-high straight
        # and loses to 6-5-4-3-2. Scoring the ace as 14 here would make the wheel the
        # best straight in the deck, which is the classic bug.
        elif distinct == [14, 5, 4, 3, 2]:
            straight_high = 5

    # counts, ordered by (how many, then rank) — this is what makes kickers fall out
    counts: Dict[int, int] = {}
    for v in vals:
        counts[v] = counts.get(v, 0) + 1
    grouped = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    shape = [n for _, n in grouped]
    ordered = [v for v, _ in grouped]

    if straight_high and flush:
        return (8, straight_high)
    if shape[0] == 4:
        return (7, ordered[0], ordered[1])
    if shape[0] == 3 and shape[1] == 2:
        return (6, ordered[0], ordered[1])
    if flush:
        return (5, *vals)
    if straight_high:
        return (4, straight_high)
    if shape[0] == 3:
        return (3, ordered[0], *ordered[1:])
    if shape[0] == 2 and shape[1] == 2:
        return (2, ordered[0], ordered[1], ordered[2])
    if shape[0] == 2:
        return (1, ordered[0], *ordered[1:])
    return (0, *vals)


def best_of(cards: Sequence[str]) -> Tuple[Tuple[int, ...], List[str]]:
    """Best five-card hand from five, six or seven cards: (score, the five used).

    Brute force over all subsets. At seven cards that is 21 combinations — the cost is
    invisible and the correctness is readable, which is the right trade for a rule that
    decides who wins money.
    """
    from itertools import combinations
    best: Tuple[Tuple[int, ...], List[str]] = ((-1,), [])
    for combo in combinations(cards, 5):
        s = _score5(combo)
        if s > best[0]:
            best = (s, list(combo))
    return best


def describe(score: Sequence[int]) -> str:
    """Say what the hand IS, in words. The score tuple decides who wins; this exists so
    a player can be told WHY they lost, which is most of what makes a game instructive."""
    cat = CATEGORY[score[0]]
    n = RANK_NAME
    if score[0] == 8:
        return "royal flush" if score[1] == 14 else "%s-high straight flush" % n[score[1]]
    if score[0] == 7:
        return "four %ss" % n[score[1]]
    if score[0] == 6:
        return "%ss full of %ss" % (n[score[1]], n[score[2]])
    if score[0] == 5:
        return "%s-high flush" % n[score[1]]
    if score[0] == 4:
        return "%s-high straight" % n[score[1]]
    if score[0] == 3:
        return "three %ss" % n[score[1]]
    if score[0] == 2:
        return "%ss and %ss" % (n[score[1]], n[score[2]])
    if score[0] == 1:
        return "pair of %ss" % n[score[1]]
    return "%s high" % n[score[1]]
    return cat
