"""WORDLE — the word game, which needs almost no engine and exactly one hard rule.

The plan said word games "need almost no engine — state plus a scoreboard", and that is
true of nearly all of this file. The exception is `score()`, and it is the reason this
game is here rather than something looser like word association: duplicate letters make
the scoring genuinely subtle, and subtle-but-decidable is precisely what belongs in code
instead of in a model's head.

THE RULE THAT CATCHES EVERYONE. Yellows are drawn from a POOL of the answer's unmatched
letters, and greens are taken out of that pool FIRST. So against the answer `ABBEY`:

    guess BOBBY -> B is green at index 2, and of the remaining two B's in the guess only
                   ONE can be yellow, because the answer has only one unmatched B left.

Implementations that scan left to right and mark "is this letter in the answer" report
three marked B's, which tells the player the answer holds three B's. That is not a
cosmetic bug — it is a lie about the hidden state, in the one place the player has no
way to check. Two passes, greens first, pool second.

The answer list is small and deliberately committed here: no dictionary file to ship, no
network, and a guess is checked against the same closed vocabulary so the game cannot be
lost to a word nobody agrees is a word.
"""
from __future__ import annotations

import hashlib
from typing import List, Tuple

# Answers. Common, unambiguous, no proper nouns, no plurals of three-letter words.
ANSWERS: Tuple[str, ...] = (
    "abbey", "adore", "amber", "anvil", "arbor", "ardor", "aroma", "audio", "aught",
    "beach", "began", "belly", "birch", "blade", "blaze", "bloom", "blunt", "brave",
    "briar", "brine", "brisk", "brook", "cabin", "candy", "canoe", "cedar", "chalk",
    "charm", "chase", "chess", "chill", "cider", "civil", "cliff", "cloak", "clove",
    "coast", "cobra", "comet", "coral", "crane", "crisp", "crown", "crypt", "curve",
    "dance", "dealt", "delta", "dense", "depth", "diner", "ditch", "dizzy", "dodge",
    "drift", "drove", "dusky", "eager", "eagle", "ebony", "elbow", "elder", "ember",
    "empty", "equal", "ether", "exact", "fable", "faith", "fancy", "fault", "feast",
    "fence", "ferry", "fiber", "field", "fiery", "flame", "fleet", "flint", "flock",
    "flour", "focal", "forge", "found", "frost", "fudge", "gauge", "ghost", "giant",
    "glade", "gleam", "globe", "glove", "grace", "grain", "grasp", "grave", "grief",
    "grove", "guard", "habit", "hasty", "haven", "heart", "hedge", "hinge", "hoard",
    "honey", "horse", "house", "hover", "human", "humid", "ideal", "index", "inlet",
    "ivory", "jelly", "jewel", "joint", "jolly", "judge", "juice", "knack", "knife",
    "known", "label", "lance", "larch", "later", "laugh", "layer", "leash", "ledge",
    "lemon", "level", "lever", "light", "lilac", "linen", "livid", "llama", "lodge",
    "lofty", "lunar", "lyric", "maple", "march", "marsh", "medal", "melon", "mercy",
    "mirth", "moral", "motor", "mound", "mount", "mourn", "mouse", "movie", "music",
    "naval", "nerve", "niche", "night", "noble", "nudge", "nurse", "oasis", "ocean",
    "olive", "onset", "orbit", "organ", "otter", "ought", "ounce", "paint", "panel",
    "pause", "peach", "pearl", "pedal", "penny", "perch", "petal", "phase", "piano",
    "pilot", "pinch", "plaid", "plank", "plaza", "plumb", "poise", "polar", "porch",
    "prism", "probe", "prone", "proud", "prowl", "pulse", "purse", "quart", "queen",
    "quest", "quiet", "quill", "quirk", "quote", "radar", "raven", "reach", "realm",
    "rebel", "relic", "renew", "ridge", "rigid", "rinse", "risen", "rival", "river",
    "roast", "robin", "rogue", "rough", "round", "rouse", "royal", "rugby", "runic",
    "saber", "salty", "sandy", "scale", "scarf", "scent", "scope", "score", "scout",
    "shade", "shale", "shard", "shore", "siege", "sight", "silky", "siren", "sixth",
    "skate", "slate", "sleek", "slope", "smoke", "snake", "solar", "solid", "sound",
    "spade", "spark", "spice", "spine", "spire", "spoke", "spool", "spore", "staff",
    "stage", "stark", "steam", "steel", "stern", "stone", "storm", "stove", "strap",
    "straw", "surge", "swamp", "swift", "sword", "table", "tempo", "tenor", "thorn",
    "three", "throw", "tidal", "tiger", "timid", "toast", "token", "tonic", "torch",
    "tower", "trace", "track", "trail", "trawl", "tread", "trend", "tribe", "trout",
    "truce", "trunk", "tulip", "tutor", "twine", "ultra", "umbra", "uncle", "under",
    "union", "unite", "upper", "urban", "usher", "vague", "valve", "vapor", "vault",
    "velum", "venue", "verse", "vigil", "vinyl", "viola", "vivid", "vocal",
    "vowel", "wagon", "waltz", "waste", "watch", "water", "weary", "wedge", "whale",
    "wharf", "wheat", "wheel", "whisk", "widow", "wince", "witty", "woven", "wrist",
    "yacht", "yield", "young", "zebra",
)

WORDS = frozenset(ANSWERS)
LEN = 5
TRIES = 6


def pick(seed: str) -> str:
    """Deterministic from a seed, so a match can be replayed and a gate can assert one.
    Randomness that cannot be reproduced is randomness that cannot be debugged."""
    h = hashlib.sha256(seed.encode("utf-8")).digest()
    return ANSWERS[int.from_bytes(h[:8], "big") % len(ANSWERS)]


def score(guess: str, answer: str) -> str:
    """Return five marks: `g` exact, `y` present-elsewhere, `.` absent.

    TWO PASSES, GREENS FIRST. See the module docstring — a single left-to-right pass
    over-reports duplicates and thereby lies about the hidden word.
    """
    g, a = guess.lower(), answer.lower()
    marks = ["."] * LEN
    pool: dict = {}
    for i in range(LEN):
        if g[i] == a[i]:
            marks[i] = "g"
        else:
            pool[a[i]] = pool.get(a[i], 0) + 1      # only UNMATCHED letters are claimable
    for i in range(LEN):
        if marks[i] == "g":
            continue
        if pool.get(g[i], 0) > 0:
            marks[i] = "y"
            pool[g[i]] -= 1
    return "".join(marks)


def valid(guess: str) -> bool:
    return isinstance(guess, str) and guess.lower() in WORDS


def verdict(guesses: List[str], answer: str) -> dict:
    if guesses and guesses[-1].lower() == answer.lower():
        return {"over": True, "result": "won", "reason": "guessed in %d" % len(guesses)}
    if len(guesses) >= TRIES:
        return {"over": True, "result": "lost", "reason": "out of tries — it was %s" % answer}
    return {"over": False, "result": None, "reason": None}
