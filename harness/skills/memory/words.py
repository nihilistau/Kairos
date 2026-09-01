"""words.py — the lexical floor: how a sentence becomes a bag of tokens.

Five names, no memory semantics at all, and **nothing in here knows what a fact is**. They
are the bottom of the package: `rank.py` matches with them, `present.py` tests an
attribute's absence with them, and `remember()` writes with them, so they cannot live
inside any of those without one of them importing another sideways.

The reason this is a module and not a section: `_toks` and `_STOP` are applied to BOTH
sides of every comparison, and *"it only has to be applied IDENTICALLY to both sides"* is
the one property `_depluralise` is documented as needing. A second tokenizer is the
two-copies bug in the place it would be hardest to see — the query would stop matching the
store and nothing would raise.

Extracted from `memory.py` on 2026-09-01, byte-identical, with the incident histories that
were already beside them (the "cats name" transcript, the P1b-2b match-noise measurement,
and the asking-about-memory-is-not-a-memory list).
"""
from __future__ import annotations


_STOP = {"the", "a", "an", "is", "are", "of", "to", "in", "on", "and", "or",
         "my", "your", "you", "it", "that", "this", "was", "were", "has", "have",
         # P1b-2b: question/aux words are MATCH NOISE — "when did my locker
         # combination last change?" scored 2/6=0.33 vs the 0.34 threshold
         # purely because "when"/"did"/"last" diluted the denominator. Facts
         # rarely contain these, so removing them sharpens matching symmetric-
         # ally (the audit gates re-ran GREEN after this change).
         "what", "who", "where", "when", "why", "how", "which",
         "did", "does", "do", "can", "could", "would", "should", "will",
         "had", "these", "those", "there", "here", "just", "please",
         # ── ASKING ABOUT MEMORY IS NOT A MEMORY (2026-07-14) ────────────────────
         # From the live transcript. He asked:
         #
         #     "do you REMEMBER what sex you are?"
         #
         # and the ranker handed her:
         #
         #     0.50  "then we can REMEMBER our idea's like this!"
         #     0.50  "REMEMBER my GPU is an RTX 2060."
         #     0.50  "REMEMBER this about me: my workshop is called Forge966733."
         #     0.00  'I am a woman'     <- speaker=self, identity, THE ACTUAL ANSWER
         #
         # THE VERB OF THE QUESTION MATCHED THE VERB OF THE JUNK. Her whole content vocabulary
         # for that question was {remember, sex}, so a row sharing the single word "remember"
         # scored 0.50 — while the row that answers it shares nothing lexically, because "sex"
         # is not "woman".
         #
         # And the junk rows contain "Remember" because they ARE captured instructions: the
         # store_verb bypass wrote "Remember my GPU is an RTX 2060." verbatim, instruction verb
         # and all. Junk begat junk. She was handed a GPU and a workshop when asked what she is,
         # and then confabulated the right answer from her persona — by luck, not memory.
         #
         # These words are how you ASK ABOUT the store. They are never what is IN it. Stopped on
         # BOTH sides, which also makes the fossil rows behave like the facts they were meant to
         # be ("Remember my GPU is an RTX 2060" -> {gpu, rtx, 2060}).
         "remember", "remembers", "remembered", "recall", "recalls", "know", "knows",
         "knew", "tell", "tells", "told", "say", "says", "said", "memory", "memories",
         "forget", "forgets", "forgot", "mention", "mentions", "mentioned", "stored"}


def _text(e: dict) -> str:
    return e.get("text") or e.get("topic") or ""


def _depluralise(w: str) -> str:
    """cats -> cat, names -> name, sensors -> sensor.

    ── HE ASKED ABOUT HIS "CATS NAME" AND GOT HIS OWN (2026-07-14) ─────────────────────
    From the live transcript, after the ownership fix landed and the question correctly scoped
    to HIM — it still answered with the wrong row:

        "do you remember my CATS name?"  ->  "The user's name is Sam"

    Because the tokenizer strips punctuation, so the STORE holds cat's -> {cat}, while the
    QUESTION holds cats -> {cats}. The possessive and the plural never touch, so the only token
    left in common with any row was `name` — and every name row matched it equally.

    The relationship penalty missed for the same reason: _REL_NOUN is \\bcat\\b, and "cats" is not
    "cat", so the cat row was never even recognised as being about a cat.

    Crude, deliberately: a real stemmer is a dependency and a new failure surface, and this is a
    bag-of-words matcher, not a linguist. It only has to be applied IDENTICALLY to both sides,
    which is the one property that actually matters. 'glass' -> 'glas' on both sides still matches
    'glass' -> 'glas'.
    """
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def _toks(s: str) -> set:
    words = "".join(c.lower() if c.isalnum() else " " for c in s).split()
    return {_depluralise(w) for w in words if len(w) >= 3 and w not in _STOP}


def _overlap(query: str, target: str) -> float:
    qt = _toks(query)
    if not qt:
        return 0.0
    return len(qt & _toks(target)) / len(qt)
