"""dominance — Dickson subsumption over a 14-byte structural signature (docs/SEMANTICS.md §S2.1).

WHAT THIS IS FOR, AND WHAT IT IS NOT FOR
────────────────────────────────────────
Supersede matching today is `lifecycle.find_superseded`, which fires only when two facts share
an EXACT `attribute_key`. It therefore cannot see this pair:

    held    "Sam has a cat."
    new     "Sam's cat Tuffy is a female tabby."

Nothing retires the vaguer row, and both render. This module is a CANDIDATE GENERATOR with better
recall than exact-slot matching: the new row's structural signature DOMINATES the held row's, so
the held row is *proposed* as subsumed.

**Dominance proposes; testimony disposes.** Every proposal is still ruled on by
`verdict.may_supersede` — an inference may never retire an observation (non-negotiable 4) — and
the write still goes through `memory.remember()`. This file writes nothing, retires nothing, and
holds no authority. It is an oracle-layer proposer (INVARIANT-MEMORY.md §1.3), and the *verdict*
layer above it is unchanged.

THE ORDER, AND WHY IT IS DICKSON AND NOT KRUSKAL
───────────────────────────────────────────────
`Position_Is_Arithmetic/Archived/SP-PPT-ARM/PPT-ARM-III-Friedman.md` §11.6. Strict Kruskal tree
embedding was MEASURED on the encoder there and scored **AUC 0.500 — it discriminates nothing**;
elementwise dominance on σ ∈ ℕ¹⁴ replaced it. Dickson's lemma (1913) gives the wqo on
(ℕ¹⁴, ≤_elem); the image is bounded (every cell is a u8) so the antichain is finite; and
**Dickson is provable in PRA** where Kruskal–Friedman's TREE(3) is not — the refutation property
is strengthened by the move, not weakened.

    Q ⪯_d K   ⟺   ∀i ∈ [0,14) :  K.sig[i] ≥ Q.sig[i]          (fourteen byte compares)

DIRECTION. The NEW row absorbs the HELD row when the NEW row's signature dominates it — richer
subsumes poorer. It is trivial to invert and catastrophic if inverted, so `compare()` returns a
named relation rather than a bool, and the proposer never takes a bare comparison result.

TRI-STATE, NOT BOOLEAN. Borrowed from the v1 `kste.h` header (whose FORMAT is wrong for us — 13-node
tree, 6 order statistics, 64-byte wire image — but whose discipline is right): INCOMPARABLE is a
genuinely different answer from DOMINATED, and a supersede decision needs the distinction. A
boolean loses it and silently reads "incomparable" as "not subsumed", which is true but throws away
the fact that the two rows are about structurally unrelated things.

THE ENCODER: φ : text → labelled tree
─────────────────────────────────────
Dickson operates on ℕ¹⁴ and σ₀/σ₁ are counts over ANY labelled tree, so the layer is
carrier-agnostic. Paper IV's ℝ¹²⁸ → 𝒯₆₀,₃ front end exists because the ENGINE's carrier is Key
vectors; a fact row is not a Key vector, and it does not need the Möbius/knight-mask step (see
docs/SEMANTICS.md §S2.1 — "do not call kste.h"). What a fact row has instead is clause structure,
which the repo can already see with `lifecycle.topic_of`.

    root                     depth 0, UNLABELLED — not counted in max_depth, absent from σ₁
      A  clause              depth 1 (deeper when subordinate: see below)
        B  topic word        the clause's content words, `topic_of`, distinct
          C  qualifier       the specificity markers: numbers and proper nouns

A clause opening with a SUBORDINATOR ("because", "which", "who", "when", "that", …) attaches to
the PRECEDING clause instead of to the root. That is what makes A→A pairs and depth > 3 reachable;
without it σ₁ would be permanently degenerate in six of its nine cells.

SET SEMANTICS AT EVERY LEVEL — distinct labels per parent. This is what buys the property the
proposer actually rests on: **the encoder is monotone under content EXTENSION.** Add a clause, or
add words to a clause, and no signature cell decreases. (It is NOT monotone under arbitrary
rewriting, and the gate says so out loud rather than leaving it to be discovered.)

FOUR THINGS NO PAPER SPECIFIES. Chosen here, written down, versioned:
  1. σ₁ is ROW-MAJOR — index 5 + 3*ancestor + descendant, A=0 B=1 C=2.
  2. ROOT DOES NOT COUNT toward max_depth (root is depth 0 and unlabelled, so it cannot appear
     in σ₁ either); a one-clause fact has max_depth 1.
  3. Paper III's `uint64` + 16-byte structs repack as 14 flat u8; EVERY cell saturates at 255,
     σ₀ included — the paper only says σ₁ saturates, but σ₀ is a u8 in the same array and an
     unsaturated overflow there would WRAP, turning a huge fact into a tiny one. Saturation is
     the only direction that keeps ⪯_d sound: a saturated cell can lose a true dominance
     (a missed proposal, harmless) but can never invent one.
  4. `d_tree` (a fuzzy radius) is undefined in the papers and is NOT implemented here.

SIGNATURES ARE NOT PORTABLE ACROSS ENCODERS (Paper IV §9.5). `LAYOUT_VERSION` is carried with
every signature and `compare()` REFUSES a cross-version pair, the same way `ep.l5.geom` refuses a
cross-model recall key. A silent comparison across encoder versions is a wrong answer with a
confident type.

HONEST LIMITS (Paper IV's own measurements, repeated here so they are not rediscovered)
──────────────────────────────────────────────────────────────────────────────────────
⪯_d earned its place at cos ≥ 0.995 (17× intra/inter separation) and DECAYS TO 1.4× at σ = 0.05.
Measured eviction was 93.86%, which is ABOVE Paper IV §9.2's own 80% "losing novel structure"
alarm. The paper's ship gate (T2.3) passed only in OBSERVER mode — hard eviction during attention
was "too aggressive on real activations". None of that transfers directly (different carrier,
different task) but the direction of the risk does: dominance over-proposes. Which is exactly why
it proposes and does not rule.
"""
from __future__ import annotations

import os
import re
from typing import Dict, Iterable, List, Optional, Tuple

from harness.skills.lifecycle import topic_of

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

LAYOUT_VERSION = "sig-v1"
SIG_LEN = 14
SAT = 255                      # every cell is a u8

# label ids — the σ₁ row/column order. Changing these changes the layout: bump LAYOUT_VERSION.
LBL_A, LBL_B, LBL_C = 0, 1, 2
_LABEL_NAME = {LBL_A: "A", LBL_B: "B", LBL_C: "C"}

# relations. Named, never bare booleans — see the module docstring on direction.
EQUAL = "equal"
DOMINATES = "dominates"            # self dominates other: self is the RICHER one
DOMINATED = "dominated"            # self is dominated BY other
INCOMPARABLE = "incomparable"
RELATIONS = (EQUAL, DOMINATES, DOMINATED, INCOMPARABLE)

# A clause opening with one of these is SUBORDINATE — it hangs off the previous clause.
_SUBORDINATORS = frozenset("""because since although though while whereas which who whom whose
    that when where why if unless until after before so as""".split())

# Clause boundaries. Deliberately shallow: this is a counting encoder, not a parser.
_CLAUSE_SPLIT = re.compile(r"[;,.!?]+|\s+(?=(?:and|but|or|because|since|although|though|while|"
                           r"whereas|which|who|whom|whose|that|when|where|why|if|unless|until|"
                           r"after|before|so)\s)", re.IGNORECASE)
_WORD = re.compile(r"[A-Za-z0-9'][A-Za-z0-9'-]*")


class SigVersionMismatch(ValueError):
    """Two signatures from different encoder versions were compared. Never answer that."""


# ──── the encoder ─────────────────────────────────────────────────────────────────────
def _clauses(text: str) -> List[str]:
    """Split into clauses, keeping order. Empty pieces dropped."""
    parts = _CLAUSE_SPLIT.split(text or "")
    return [p.strip() for p in parts if p and p.strip()]


def _qualifiers(clause: str) -> List[str]:
    """The SPECIFICITY MARKERS of a clause: numbers, and proper nouns that are not sentence-initial.

    "Sam's cat Tuffy is a 2060" -> Tuffy, 2060. These are what make a fact more specific than
    its vaguer sibling, so they get their own label and their own tier of the tree. Sentence-initial
    capitals are excluded because capitalisation there carries no information.
    """
    words = _WORD.findall(clause)
    out = []
    for i, w in enumerate(words):
        if any(ch.isdigit() for ch in w):
            out.append(w.lower())
        elif i > 0 and w[:1].isupper() and not w.isupper():
            out.append(w.lower())
    seen, uniq = set(), []
    for w in out:
        if w not in seen:
            seen.add(w)
            uniq.append(w)
    return uniq


def encode(text: str) -> List[Tuple[int, int, int]]:
    """φ: text → labelled tree, as a flat node list of (node_id, parent_id, label).

    Node 0 is the unlabelled root (label None is encoded as -1 and never enters σ₁).
    Exposed because a gate that can only see the signature cannot tell a right tree from a
    wrong one with the same counts.
    """
    nodes: List[Tuple[int, int, int]] = [(0, -1, -1)]        # (id, parent, label)
    prev_clause_id: Optional[int] = None

    def add(parent: int, label: int) -> int:
        nid = len(nodes)
        nodes.append((nid, parent, label))
        return nid

    for clause in _clauses(text):
        head = _WORD.findall(clause)
        head_word = head[0].lower() if head else ""
        subordinate = head_word in _SUBORDINATORS and prev_clause_id is not None
        parent = prev_clause_id if subordinate else 0
        cid = add(parent, LBL_A)
        if not subordinate:
            prev_clause_id = cid

        quals = _qualifiers(clause)
        topics = sorted(topic_of(clause))
        b_ids: Dict[str, int] = {}
        for t in topics:
            if t not in b_ids:                                # set semantics per parent
                b_ids[t] = add(cid, LBL_B)

        if b_ids:
            # Each qualifier hangs off ONE topic node: the topic it is a token of if the
            # qualifier survived topic_of, else the clause's first topic. Deterministic
            # either way, which is what the signature needs — it counts, it does not parse.
            first = b_ids[topics[0]]
            for q in quals:
                add(b_ids.get(q, first), LBL_C)
        else:
            for q in quals:                                   # a clause of nothing but names
                add(cid, LBL_C)
    return nodes


def _depths(nodes) -> Dict[int, int]:
    depth = {0: 0}
    for nid, parent, _lbl in nodes[1:]:
        depth[nid] = depth.get(parent, 0) + 1
    return depth


def sig_of_tree(nodes) -> bytes:
    """σ₀ ⊕ σ₁ as 14 saturating bytes (docs/SEMANTICS.md §S2.1)."""
    depth = _depths(nodes)
    label = {nid: lbl for nid, _p, lbl in nodes}
    parent = {nid: p for nid, p, _l in nodes}

    counts = [0, 0, 0]
    for nid, _p, lbl in nodes:
        if lbl in (LBL_A, LBL_B, LBL_C):
            counts[lbl] += 1
    labelled = [nid for nid, _p, lbl in nodes if lbl >= 0]
    max_depth = max((depth[n] for n in labelled), default=0)
    node_count = len(labelled)                 # root is unlabelled and does not count

    pairs = [0] * 9
    for nid in labelled:
        d = label[nid]
        anc = parent[nid]
        while anc is not None and anc >= 0:
            a = label.get(anc, -1)
            if a >= 0:                          # the root is not an ancestor for σ₁ purposes
                pairs[3 * a + d] += 1
            anc = parent.get(anc, -1)
            if anc == -1:
                break

    raw = counts + [max_depth, node_count] + pairs
    return bytes(min(v, SAT) for v in raw)


def signature(text: str) -> Dict[str, object]:
    """The versioned signature of a fact's text: {"v": LAYOUT_VERSION, "sig": bytes(14)}."""
    return {"v": LAYOUT_VERSION, "sig": sig_of_tree(encode(text))}


def sig_hex(sig: Dict[str, object]) -> str:
    """Storage/receipt form: 'sig-v1:0a0b…' — self-describing, so a stored signature can
    never be silently read under a different layout."""
    return "%s:%s" % (sig["v"], bytes(sig["sig"]).hex())


def from_hex(s: str) -> Dict[str, object]:
    v, _, h = (s or "").partition(":")
    b = bytes.fromhex(h)
    if len(b) != SIG_LEN:
        raise ValueError("signature is %d bytes, expected %d" % (len(b), SIG_LEN))
    return {"v": v, "sig": b}


# ──── the order ───────────────────────────────────────────────────────────────────────
def compare(a: Dict[str, object], b: Dict[str, object]) -> str:
    """Relation of `a` TO `b`: EQUAL | DOMINATES | DOMINATED | INCOMPARABLE.

    DOMINATES means a is the RICHER signature — every cell of a is ≥ b's, and at least one
    is strictly greater. Raises SigVersionMismatch across encoder versions.
    """
    if a.get("v") != b.get("v"):
        raise SigVersionMismatch("%r vs %r — signatures are not portable across encoders"
                                 % (a.get("v"), b.get("v")))
    sa, sb = bytes(a["sig"]), bytes(b["sig"])
    if len(sa) != SIG_LEN or len(sb) != SIG_LEN:
        raise ValueError("signature length must be %d" % SIG_LEN)
    ge = all(x >= y for x, y in zip(sa, sb))
    le = all(x <= y for x, y in zip(sa, sb))
    if ge and le:
        return EQUAL
    if ge:
        return DOMINATES
    if le:
        return DOMINATED
    return INCOMPARABLE


def dominates(rich: Dict[str, object], poor: Dict[str, object]) -> bool:
    """`poor ⪯_d rich` — true for EQUAL as well, since ⪯_d is reflexive."""
    return compare(rich, poor) in (DOMINATES, EQUAL)


# ──── the content half of the order ───────────────────────────────────────────────────
# STRUCTURAL DOMINANCE ALONE IS NOT SUBSUMPTION, and the counter-example is one line long:
#
#     compare(sig("He drinks Oolong tea."), sig("Sam has a cat."))  ->  DOMINATES
#
# Both are one clause; one has more topic words; fourteen counts cannot tell you they are
# about different things, because A/B/C are structural ROLES here, not content. (Paper III's
# labels come out of a quantizing encoder over Key vectors, where the label itself carries
# signal; a text encoder does not get that for free.) A proposer built on the signature alone
# would offer "He drinks Oolong tea" as superseding "Sam has a cat" — a candidate generator
# with perfect recall and no precision, which is worse than the exact-slot matching it augments.
#
# So subsumption is the CONJUNCTION of two dominances on two carriers:
#
#     CONTENT      topic_of(held) ⊆ topic_of(new)      the vaguer row says nothing new
#     STRUCTURE    sig(held)      ⪯_d sig(new)         the richer row says strictly more
#
# Containment of a finite set is itself elementwise dominance of indicator vectors, so it is
# the same lemma on a different (per-comparison finite) index set — this is one order over a
# product, not a heuristic bolted onto a theorem. Both halves are necessary: content alone
# fires on any restatement, structure alone fires across unrelated topics.
def content_of(text: str) -> frozenset:
    """The content of a claim FOR SUBSUMPTION PURPOSES: topic words PLUS the names.

    ── WHY THIS IS NOT topic_of (measured on the live registry, 2026-07-30) ────────────────
    `topic_of` exists to answer "has he already spoken to this subject?", and for that job it
    deliberately drops the participants — `lifecycle._STOP` contains "sam" and "kairos"
    outright. Reusing it for CONTAINMENT inherits that, and containment is the one place where
    the names are the whole point: they are what says *whose* name, *whose* cat.

    The first read-only run over his 84 live rows proposed nine supersedes, and the failures
    were all this bug:

        NEW   "My cat's name is Tuffy."     topics {cat, name, tuffy}
        HELD  "my name is Sam"            topics {name}          <- "sam" was a stopword

    {name} ⊆ {cat, name, tuffy}, so the cat's name subsumed HIS name and the proposal was to
    tombstone "my name is Sam". Worse, "I am Kairos" reduces to the EMPTY set, and the empty
    set is contained in everything — a row made entirely of stopwords could be subsumed by any
    row at all.

    So the qualifiers (numbers and proper nouns — the same specificity markers the C label is
    built from) are added back. They cost nothing: the encoder already computes them.
    """
    return frozenset(topic_of(text or "")) | frozenset(_qualifiers(text or ""))


def content_relation(new_text: str, held_text: str) -> str:
    """Relation of `new` to `held` by CONTENT, in the same vocabulary as compare()."""
    a, b = content_of(new_text), content_of(held_text)
    if a == b:
        return EQUAL
    if b < a:
        return DOMINATES
    if a < b:
        return DOMINATED
    return INCOMPARABLE


def subsumes(new_text: str, held_text: str) -> bool:
    """Does `new_text` structurally and topically subsume `held_text`?

    True only when BOTH carriers agree that new is the richer row, and at least one of them
    strictly so. This is the whole proposal test; `find_subsumed` adds only the lane rules.
    """
    # A row with NO content at all is not subsumable: the empty set is contained in everything,
    # so without this a stopword-only row ("I am here.") would be absorbed by the first fact
    # that came along. Nothing may be retired on the strength of having said nothing.
    if not content_of(held_text):
        return False
    c = content_relation(new_text, held_text)
    if c not in (DOMINATES, EQUAL):
        return False
    s = compare(signature(new_text), signature(held_text))
    if s not in (DOMINATES, EQUAL):
        return False
    return not (c == EQUAL and s == EQUAL)          # identical rows subsume nothing


# ──── the proposer (no writes, no authority) ──────────────────────────────────────────
def enabled() -> bool:
    """SP_SEM_DOMINATE — mapped in serve.py, DEFAULT OFF.

    Off means every verdict is byte-identical to pre-dominance behaviour (the G-SEM-CONSERVE
    law). It stays off until the supersede rate has a measured bar on the frozen corpus; a
    proposer with better recall than the thing it augments also has more ways to be wrong.
    """
    return os.environ.get("SP_SEM_DOMINATE", "0") == "1"


def find_subsumed(new_fact: str, speaker: str, rows: Iterable[dict],
                  status: Optional[str] = None) -> List[dict]:
    """Rows the new fact STRUCTURALLY SUBSUMES: proposals only, ruled on downstream.

    Same speaker; live; not the same row; `verdict.may_supersede` satisfied; and the new
    fact's signature strictly DOMINATES the held row's. Returns [] when the knob is off, so
    the caller needs no flag of its own.

    The `may_supersede` check is here as well as at the caller ON PURPOSE. It is the rule
    this repo has broken most often — an invariant enforced in one of two paths is enforced
    in neither — and a proposer that hands up illegal candidates is a proposer that will one
    day be trusted by a path that forgot to check.
    """
    if not enabled():
        return []
    from harness.skills import verdict as _v
    from harness.skills.lifecycle import (STATUS_OBSERVED, attribute_key, status_of,
                                          strip_prefix)

    def _attr(t, spk):
        try:
            return attribute_key(t, spk)
        except Exception as _swx:
            _swallowed(_swlog, "_attr", _swx, lane="skills")
            return None

    st = status or STATUS_OBSERVED
    new_clean = strip_prefix(new_fact or "")
    new_lower = (new_clean or "").strip().lower()
    out: List[dict] = []
    for r in rows:
        # `lifecycle` is the death field, not `superseded_by` (AGENTS.md §3) — an orphan
        # tombstone was visible to this proposer. Same fix as lifecycle.find_superseded.
        # ONE SPELLING (2026-08-25): `lifecycle` alone, matching every reader in the
        # tree. The live store holds zero superseded_by-without-lifecycle rows, and if
        # one ever existed the wide `or superseded_by` spelling would hide it from this
        # machinery while every reader still served it — the split-brain shape. The
        # reasoning lives at lifecycle.find_superseded's twin comment, same day.
        if r.get("lifecycle"):
            continue
        if r.get("speaker", "user") != speaker:
            continue
        txt = strip_prefix(r.get("text") or r.get("topic") or "")
        if not txt or txt.strip().lower() == new_lower:
            continue                                  # a restatement is not a subsumption
        if not _v.may_supersede(st, status_of(r)):
            continue
        # A SLOT DISAGREEMENT IS NOT A GAP. `find_superseded` rules on pairs that share an
        # exact attribute_key; dominance exists to reach pairs where the slot machinery has
        # NOTHING to say (one or both slots absent), not to overrule it when it has spoken.
        # Measured on the live registry: without this, "My cat Tuffy is female." (slot
        # cat.gender) proposed retiring "Sam is a cat person." (a trait) — two different
        # slots, one shared content word, and a tombstone on the wrong row.
        ka, kb = _attr(new_clean, speaker), _attr(txt, speaker)
        if ka and kb and ka != kb:
            continue
        try:
            if subsumes(new_clean, txt):
                out.append(r)
        except (SigVersionMismatch, ValueError):
            continue                                  # an unreadable signature proposes nothing
    return out


def describe(text: str) -> str:
    """Human-readable signature, for receipts and gate output."""
    nodes = encode(text)
    s = sig_of_tree(nodes)
    cells = ", ".join("%s->%s=%d" % (_LABEL_NAME[i // 3], _LABEL_NAME[i % 3], v)
                      for i, v in enumerate(s[5:]) if v)
    return ("A=%d B=%d C=%d depth=%d nodes=%d | %s" %
            (s[0], s[1], s[2], s[3], s[4], cells or "(no ancestor pairs)"))
