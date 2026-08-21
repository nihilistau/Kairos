"""expand — query→keyword expansion from the store's own co-occurrence. ASSOCIATION, NOT JUDGMENT.

THE ONE OPEN PATH IN A STACK OF COMMITTED NEGATIVES
───────────────────────────────────────────────────
Every semantic-recall contender so far is a measured loss against the lexical baseline
(`harness_tests/fixtures/sem/baseline-receipt.json`, decider hit rate **0.06**):

    cosine over L5          precision 0.0167
    W_c selector            hit 0.02, foreign precision 0.00
    the LLM judge           declines essentially everything
    frame_link              0.625 against a 0.80 bar

They fail in two different ways, and the difference is the whole reason this file exists. The
embedding contenders fail at *precision* — they find something for every query, including the
foreign ones. The judge fails at *task shape*: asking a model "are these the same subject?" is a
JUDGMENT, it is cautious by construction, and a cautious judge says no to everything.

Expansion is a different shape from both. It does not decide anything and it does not score
anything. It answers "what words tend to travel with these words, HERE, in this store" and hands
the result to the lexical seam that already works. The ranking stays lexical; only the query gets
wider.

WHY CO-OCCURRENCE AND NOT A MODEL CALL
──────────────────────────────────────
A oneshot "list five related words" would be one more oracle, at ~1 s per turn, unmeasurable
offline, and different every run. The store is already a thesaurus of exactly the right
vocabulary: the words that co-occur in HIS facts are, by construction, the associations that
matter for HIS memory. Deterministic, no GPU, and the gate can walk it.

This is pseudo-relevance feedback with the corpus replaced by the registry, which is the honest
version of the idea for a store this small.

THE TRADE IT MAKES, NAMED IN ADVANCE
────────────────────────────────────
Expansion buys recall and spends precision — a foreign query that expands into store vocabulary
starts matching things it should not. That is the exact failure that killed the cosine
contenders, so it is the number to watch, not the hit rate. The ship condition is therefore
BOTH: beat 0.06 on paraphrases AND hold foreign decider precision at or above 0.8667. A
contender that wins one and loses the other has not won.

Off unless `SP_SEM_EXPAND=1` (mapped in serve.py). Nothing here writes.
"""
from __future__ import annotations

import math
import os
import threading
from typing import Dict, List, Optional, Set, Tuple

from harness.skills.lifecycle import topic_of

# How many expansion terms may be added. Small on purpose: the seam scores by overlap
# fraction, so every added term that does NOT match dilutes the score of one that does.
DEFAULT_K = 3
# A pair must have been seen together at least this often to count as an association. At 1 a
# single coincidence in a 50-fact store becomes a "relationship", which is how expansion
# turns into noise generation.
MIN_PAIR = 2
# ...and a word that appears in almost every fact associates with everything and discriminates
# nothing. Dropped above this document frequency.
MAX_DF = 0.30

_LOCK = threading.RLock()
_CACHE: Dict[str, object] = {"key": None, "assoc": None, "df": None, "n": 0}


def enabled() -> bool:
    return os.environ.get("SP_SEM_EXPAND", "0") == "1"


def _rows() -> List[dict]:
    from harness.skills import memory as M
    try:
        # live_rows(): the one tombstone predicate. This filtered on `superseded_by`,
        # so plain tombstones fed the co-occurrence corpus (AGENTS.md §3: `lifecycle`
        # is the death field).
        return M.live_rows()
    except Exception:
        return []


def _build(rows: List[dict]) -> Tuple[Dict[str, Dict[str, int]], Dict[str, int], int]:
    """Co-occurrence counts and document frequency over the live rows."""
    from harness.skills.lifecycle import strip_prefix
    assoc: Dict[str, Dict[str, int]] = {}
    df: Dict[str, int] = {}
    n = 0
    for r in rows:
        words = sorted(topic_of(strip_prefix(r.get("text") or r.get("topic") or "")))
        if not words:
            continue
        n += 1
        for w in words:
            df[w] = df.get(w, 0) + 1
        for i, a in enumerate(words):
            for b in words[i + 1:]:
                assoc.setdefault(a, {})[b] = assoc.setdefault(a, {}).get(b, 0) + 1
                assoc.setdefault(b, {})[a] = assoc.setdefault(b, {}).get(a, 0) + 1
    return assoc, df, n


def _tables():
    """Cached association tables, invalidated by row count. Rebuilding per query on a store
    this size is cheap, but doing it per query per turn is not."""
    rows = _rows()
    key = "%d" % len(rows)
    with _LOCK:
        if _CACHE["key"] != key:
            a, d, n = _build(rows)
            _CACHE.update({"key": key, "assoc": a, "df": d, "n": n})
        return _CACHE["assoc"], _CACHE["df"], _CACHE["n"]


def associations(word: str, k: int = DEFAULT_K) -> List[str]:
    """The k words most associated with `word` in the store, strongest first."""
    assoc, df, n = _tables()
    if not n:
        return []
    near = assoc.get(word) or {}
    scored = []
    for other, c in near.items():
        if c < MIN_PAIR:
            continue
        if df.get(other, 0) / float(n) > MAX_DF:
            continue                       # too common to mean anything
        # Pointwise-mutual-information-ish: how much more often together than chance.
        p_ab = c / float(n)
        p_a = df.get(word, 1) / float(n)
        p_b = df.get(other, 1) / float(n)
        scored.append((math.log(p_ab / max(p_a * p_b, 1e-9)), other))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [w for _s, w in scored[:max(0, int(k))]]


def expand(query: str, k: int = DEFAULT_K) -> Set[str]:
    """The query's own topic words PLUS their strongest store associations.

    Returns a SET of terms, not a rewritten string: the seam scores by overlap over term sets,
    and re-serialising into prose would only invite a second tokenizer to disagree with the
    first one.
    """
    base = set(topic_of(query or ""))
    if not enabled() or not base:
        return base
    out = set(base)
    for w in sorted(base):
        for t in associations(w, k=k):
            out.add(t)
    return out


def expanded_query(query: str, k: int = DEFAULT_K) -> str:
    """`expand()` rendered back as text, for callers that hold a string seam."""
    terms = expand(query, k=k)
    extra = sorted(terms - set(topic_of(query or "")))
    return (query or "") + ((" " + " ".join(extra)) if extra else "")


def why(query: str, k: int = DEFAULT_K) -> str:
    """Diagnostics: what would be added, and from what. Never used in a prompt."""
    if not enabled():
        return "SP_SEM_EXPAND is off"
    _a, _d, n = _tables()
    base = sorted(topic_of(query or ""))
    bits = ["store rows: %d" % n, "query terms: %s" % (", ".join(base) or "(none)")]
    for w in base:
        bits.append("  %s -> %s" % (w, ", ".join(associations(w, k=k)) or "(nothing)"))
    return "\n".join(bits)
