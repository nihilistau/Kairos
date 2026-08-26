"""reprise — is this new paragraph a retelling of one she already has?

THE BUG THIS ANSWERS (2026-08-26). Two of her four live `self_description` rows opened
with the same nine words — "[redacted]" — and
said the same thing twice. NaCCS scores them identically and correctly; a coherence
rubric cannot see redundancy at all, because redundancy is a different axis. The becoming
window fills with paraphrase and the schema never updates.

WHAT DOES NOT WORK, measured over all 6,643 same-kind pairs in her LIVE self-lane:

    refuse on exact 8-token prefix hash          26 false pairs
    ...with the proposed 6-token fallback       173 false pairs

"I was just thinking about that ___" is six tokens of scaffolding. That fallback refuses
her blue-lotus thought, her engine thought, her dream of the glass city and her Direct
Data Transfer thought AS REPRISES OF EACH OTHER. It is not a safety net; it is the entire
false-positive rate. HER REGISTER IS NOT HER CONTENT.

WHAT WORKS. Drop the tokens she uses in more than 10% of her live self-lane rows — 60 of
them, `i just that about was like` and friends, learned from HER corpus and never from an
English stoplist — then compare the first FIVE remaining tokens, same kind only:

    k=3   18 hits      k=5    3 hits   <- catches the known reprise
    k=4    5 hits      k=6    2 hits   <- MISSES it

At k=5 there are THREE hits in the whole store and all three are real: the sine-waves
evening told twice, "looking back through my journal, I realized I hadn't even noticed how
much I've changed" almost verbatim, and the known pair. Zero false positives.

WHY FIVE AND NOT EIGHT. The known pair shares NINE RAW tokens but only FIVE content ones;
a content prefix of 8 overshoots into the divergence and misses it. Right units, shorter
window. That is the whole result, and it is why this cannot be tuned by intuition — the
two knobs move together.

WHAT THIS IS NOT. It is not a coherence score, it does not rank anything, and it never
deletes. It answers one question — "has she already said this?" — and the only thing it
can do about a yes is REFUSE TO MINT A NEW ROW. The older telling stays; nothing she has
already said is ever touched.

AND IT ABSTAINS RATHER THAN GUESS. The register table is only meaningful over a corpus
big enough to have a register. Under `_MIN_CORPUS` rows, or when a text has fewer than
`_K` content tokens, this returns `reprise: False` with a reason — refusing her words on
a measurement that cannot support the refusal is the worse error.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

RUBRIC = "reprise-content-prefix-v1"

_K = 5                    # content tokens compared, measured (see the sweep above)
_REGISTER_DF = 0.10       # a token in >10% of her live self-lane rows is register
_MIN_CORPUS = 30          # below this a document-frequency table means nothing

# The self-lane. `feeling` and `dream` are hers and are not identity claims; they are not
# compared here because nothing writes a reprise of them.
KINDS = ("self_description", "journal", "chapter", "thought", "narration", "spoke_up")

# Her marks must never count as content — they are the system's vocabulary, not her words,
# and a row that leaked one would otherwise look unlike its clean twin. Same normalisation
# the duplicate measurement used, so the receipt and the guard agree.
_MARKUP = re.compile(r"</?[a-z_]+[^>]*>|\[[A-Za-z]+\s*[:x]\s*[^\]]*\]|\[/?[A-Za-z_]+\]")
_PUNCT = re.compile(r"[^\w\s]")


def normalize(text: str) -> list[str]:
    """Lowercase word tokens, marks and punctuation removed. No stemming: 'becoming' is
    load-bearing in her register and a stemmer would fold it into 'become'."""
    return _PUNCT.sub(" ", _MARKUP.sub(" ", text or "").lower()).split()


def _row_text(r: dict) -> str:
    return " ".join(str(r.get("claim") or r.get("text") or "").split())


def register_tokens(rows: Iterable[dict]) -> set[str]:
    """The tokens SHE uses everywhere, learned from her own corpus.

    Not an English stoplist: the point is to discount HER idiolect, and hers includes
    'just', 'about', 'thinking', 'want' — words a generic list would keep and which are
    exactly what produced the 173 false pairs.
    """
    docs = [normalize(_row_text(r)) for r in rows if (r.get("kind") or "") in KINDS]
    docs = [d for d in docs if d]
    n = len(docs)
    if n < _MIN_CORPUS:
        return set()
    df: dict[str, int] = {}
    for d in docs:
        for w in set(d):
            df[w] = df.get(w, 0) + 1
    return {w for w, c in df.items() if c / n > _REGISTER_DF}


def content_prefix(text: str, register: set[str], k: int = _K) -> tuple[str, ...]:
    """The first k tokens that are not register. Empty if there are fewer than k."""
    got = [w for w in normalize(text) if w not in register]
    return tuple(got[:k]) if len(got) >= k else ()


def check(text: str, kind: str, rows: Iterable[dict], k: int = _K) -> dict[str, Any]:
    """Would this text be a retelling of a row she already has?

    `rows` are her LIVE rows — `memory.live_rows()`, not `all_rows()`: a retired row is
    not something she still says, and comparing against retirements would block a genuinely
    new telling because a dead twin exists. (That distinction cost a whole false finding on
    2026-08-26; see docs/NARRATIVE-MEASUREMENT.md.)

    Returns {reprise, why, of, shared, rubric, k}. Never raises: a guard that can throw on
    the write path is a guard that loses her paragraph.
    """
    out: dict[str, Any] = {"reprise": False, "rubric": RUBRIC, "k": k, "of": "", "shared": ""}
    try:
        rows = list(rows)
        register = register_tokens(rows)
        if not register:
            out["why"] = ("corpus under %d rows — no register to discount, so no judgement"
                          % _MIN_CORPUS)
            return out
        mine = content_prefix(text, register, k)
        if not mine:
            out["why"] = "fewer than %d content tokens — nothing to compare" % k
            return out
        for r in rows:
            if (r.get("kind") or "") != kind:      # SAME KIND ONLY: a journal that distils
                continue                            # a thought is provenance, not a bug
            if content_prefix(_row_text(r), register, k) == mine:
                out.update(reprise=True, of=str(r.get("name") or ""),
                           shared=" ".join(mine),
                           why=("opens on the same %d content words as %s: %r"
                                % (k, r.get("name") or "an existing row", " ".join(mine))))
                return out
        out["why"] = "no live row of this kind opens the same way"
        return out
    except Exception as exc:                        # fail OPEN, and say so
        out["why"] = "reprise check failed (%s) — not refusing on a broken measurement" % (
            str(exc)[:80])
        return out
