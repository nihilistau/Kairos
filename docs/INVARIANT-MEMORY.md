---
type: foundation
title: "INVARIANT-MEMORY — the memory system as a finite mathematical object"
status: FOUNDATION (2026-07-14) — normative for every verdict; MEMORY-AND-RECALL.md is the operational reference over it
---

# INVARIANT-MEMORY.md — the memory system as a finite mathematical object

**Status: FOUNDATION (2026-07-14). This document is the basis the SEM stack builds on, stated
after the Phase 2 measurements made the alternative untenable. [`SEMANTICS.md`](SEMANTICS.md)
remains the stack (S0–S4, phases, receipts); THIS file owns the why and the invariant discipline.
No content is duplicated between them on purpose — one truth, one owner.**

---

## 0. THE DIAGNOSIS: WHY MEMORY WORK HAS BEEN WHACK-A-MOLE

Count the rules the memory system enforces today: the tombstone filter, testimony-over-inference,
speaker lanes, the identity firewall, attribute-slot supersede, property accumulation, the privacy
decline, counterfact framing, pronoun scoping, the relationship-noun penalty, admission
(is_memorable), quoted-speech stripping, reflection evidence-gating. Every one is a Python
conditional at a seam. Every one was added after a failure. Every one has the two-paths failure
mode this repo's AGENTS.md §0 exists to warn about, and several have had it.

The reason it never converges: **rules written as code have an unbounded case space.** A
conditional over free text and ad hoc fields can meet a new input shape forever; each fix creates
new boundary behaviour; regression gates pin the cases we have MET, and nothing bounds the cases we
have not. That is the whack-a-mole machine, and no amount of discipline dismantles it — discipline
only slows it.

The Phase 2 scoreboard (gates/G-SEM-SCOREBOARD.md) showed the same disease in its purest form:
"semantically similar" as a cosine threshold has no finite refutation semantics — no witness you
can put in a gate that proves a similarity verdict wrong — so building POLICY on it guarantees an
eternity of tuning. It measured 0.0167 precision and lost, and the loss generalizes:

> **A correctness rule may only be built on structure whose case space is finite and enumerable.
> Anything built on magnitudes is a preference, never a verdict.**

The mathematics this project already leans on (Friedman's invariant maximality, order-invariant
relations on Q^k, WQO theory, PRA-grade conservation) is not decoration for that principle — it IS
that principle, developed for eighty years precisely because "strong and provable" requires it.

---

## 1. THE BASIS, IN FOUR MOVES

### 1.1 Order invariance: rules become finite objects

Friedman's central device: a relation on Q^k is **order invariant** iff membership depends only on
the ORDER TYPE of the tuple — the pattern of <, =, > among coordinates — never on the values. An
order-invariant relation on an infinite domain is therefore a **finite object**: a set of order
types, of which there are finitely many for each k, all enumerable.

The memory translation. Give every fact a **signature** σ(row): a tuple over finite vocabularies
plus rational time coordinates —

```
σ(row) = ( speaker ∈ {user, self},
           status  ∈ {observed, inferred, confirmed},
           lifecycle ∈ {0, 1},
           mem_class ∈ C            (ONE vocabulary — SEMANTICS.md §4 prerequisite 1),
           slot ∈ S ∪ {⊥}           (attribute key, if any),
           t_first, t_last, t_retired ∈ Q ∪ {⊥} )
```

and require: **every verdict-level decision is a function of the order type of a small tuple of
signatures.** Admit-to-speech is a ruling on (query-context, σ(row)); supersede-permission is a
ruling on (σ(new), σ(old)); merge verdicts are rulings on (σ(a), σ(b)). The rulings form a
**decision table over order types — data, not code — evaluated by ONE evaluator at the one seam.**

What this buys, and it is the whole point:

- **The case space is finite.** Every combination of the finite coordinates × every order pattern
  of the time coordinates is a cell. A "fringe case" is an unclassified cell, and the cells can be
  ENUMERATED. The game board has edges.
- **Completeness is a theorem you check by running a loop:** every reachable cell has exactly one
  ruling. Offline, no GPU, finite. (Reachable = producible by the real writer — the
  producer/consumer closure of G-SECRET §4, promoted from one lesson to the general law.)
- **Consistency is the same loop:** no cell carries two rulings.
- **`src` stays prose and policy stays blind to it** — already law (TRAP: branching on src), now a
  corollary: prose has no order type, so the table cannot see it.

### 1.2 Invariant maximality: the store's view is a maximal object, and its invariances are chosen from the provable class

Friedman's deep result-shape: *maximality* (greedy, cheap, trivial) plus an *invariance demand* on
the maximal object is where all the content lives — and which invariances you may demand is
delicate: some are provable low (finite strictly-increasing embeddings), some cost large cardinals
(tail-identity), i.e. are not obtainable inside your working theory at all.

The memory translation. **Her spoken view of a topic = the maximal subset of matched rows
consistent under an order-invariant priority relation.** Testimony-over-inference stops being a
special-cased speech filter and becomes a property of the relation: on a shared slot,
(status=observed) dominates (status=inferred) at every order type — so the maximal consistent view
provably never contains her guess over his word. Same for lanes: cross-speaker tuples carry no
compatible order types, so lanes cannot merge in any view, ever, on any path.

And the engineering reading of Friedman's warning: **choose the invariances you demand of the
maximal view DELIBERATELY, from the provable class.** The ones we demand, each a gate:

| Invariance (provable class) | Meaning here | Gate |
|---|---|---|
| time translation (order-preserving shift of all t) | verdicts depend on the ORDER of events, never the calendar | G-SEM-STABLE §1 |
| future extension (append rows with later t) | verdicts about the past do not flip because the world grew | G-SEM-STABLE §2 |
| unrelated retirement | tombstoning X changes no verdict that never involved X | G-SEM-STABLE §3 |

What we deliberately do NOT demand (the tail-identity analogue — attractive, unaffordable):
invariance under *reordering* of observations. What he said SECOND superseding what he said first
is load-bearing; a memory invariant under observation order would be a memory that cannot learn.

### 1.3 PRA / conservation: the admission criterion for mechanisms

Already stated as the epistemic contract (SEMANTICS.md §1); promoted here to the **entry bar**:

> A mechanism may participate in verdicts iff its correctness claim is Π⁰₂-shaped — every
> violation has a finite, primitive-recursive witness (a cell, a row id, a tuple) that a gate can
> print. If a mechanism's failure cannot be exhibited finitely, the mechanism may rank, propose,
> and decorate — it may never rule.

This single sentence sorts everything we have:

- order-type tables, dominance checks, lifecycle, lanes, slots → verdict layer (witnesses: cells).
- salience, recency decay, cosine, W_c scores, any learned signal → **rank layer** (order among
  already-admitted rows; magnitudes allowed, invariance NOT required — recency decay is the rank
  layer doing its job).
- LLM/embedding judgments ("same slot?", "paraphrase?") → **oracle layer**: fallible proposers.
  An oracle output is an edge with an order-typed label; it may cause a PROPOSAL (a supersede
  candidate, a recall candidate) that then flows through the verdict table like anything else.
  Oracle off ⇒ every verdict identical (conservation, G-SEM-CONSERVE's law); oracle wrong ⇒ a
  worse ranking or a missed proposal, never a false verdict.

The strength claim of the whole design is exactly this: **correctness is a theorem about the
verdict layer alone.** Oracles and rankers can be arbitrarily clever, arbitrarily wrong, or
switched off entirely, and no non-negotiable can be violated — not because a guard remembered to
fire, but because the violating object has no cell to live in.

### 1.4 WQO: the termination ordinals

Unchanged from SEMANTICS.md (S2): Dickson dominance for supersede proposals and frontier
settlement; the Higman/Kruskal whistle for consolidation loops. Their role in the foundation:
**every repair or growth loop names its well-founded measure** (§1.5 of the contract), and the WQO
is what makes "the store settles" a theorem instead of an observation.

---

## 2. WHAT CHANGES, CONCRETELY (the phase plan)

**Phase A — draw the game board (no behaviour change). DONE 2026-07-14.** The de facto decision
table is committed (`harness_tests/fixtures/sem/verdict-table.json`: 19 cells, 0 refusals,
0 conflicts, enumerated by `harness_tests/sem_enum.py` through the real writer/seam/decider) and
the meta-gates are green: **G-SEM-TABLE 13/13** (COMPLETE: the ∀-theorems hold over every cell —
tombstones silent on every path, live testimony always admitted, attr-absent secrets never spoken,
covered inferences never take the floor, nothing spoken bypasses the seam; CONSISTENT: zero
prose-dependent rulings, regeneration matches the committed table cell-for-cell) and
**G-SEM-STABLE 9/9** (the §1.2 invariances). Every future "fringe case" is now a diff against a
committed table, visible in review.

Two structural findings from the first enumeration, both recorded in the table's notes:
(1) **the topic relation is PROSE** — an inference sharing one content word with his testimony is
operationally "uncovered" and lawfully takes the floor ("wary of ladders after a fall" vs "relaxed
about ladders these days"). Topic-equivalence must become a signature coordinate (a slot),
oracle-PROPOSED and table-consumed — that is Phase C's first job. (2) `counterfact` remains
consumer-branched with no producer, flagged by the closure survey — vocabulary-only by design,
watched by the gate. The enumeration method itself earned two corrections that are now doctrine in
`sem_enum.py`: **cell coordinates are computed from the system's operational relations
(`attr_absent`, `topic_of`, the store at observation time), never from recipe intent** — intent
labels produced one phantom leak and one phantom conflict before this was law.

**Phase B — the table becomes the law. SHADOW LANDED 2026-07-14.** `harness/skills/verdict.py`
is THE evaluator: the one implementation of the signature (σ, competition, attr — the enumerator
now imports it; a second copy would be the two-paths bug in a mathematician's hat), rules as data
from the committed table, and a **shadow at the seam** (`SP_SEM_LAW`, armed on the live profile):
everything admitted must be table-admissible, checked read-only on every recall, divergences as
counters plus witness lines. The evaluator NEVER guesses — an unmapped cell returns None and gets
counted, not ruled. Normalization law read off the running code: missing status → observed,
missing speaker → user, missing class → fact (77 of her 81 live rows predate the status field).
Gate: **G-SEM-LAW 11/11** (off-is-off; zero divergence on modern AND legacy-shaped worlds; the
alarm demonstrably fires; ruling() never guesses).

**The shadow paid for itself within minutes of first contact with her live registry:** 29 checks,
0 divergent, **2 unmapped** — her self-lane *preference* rows and his *event* rows lived in cells
the board never had, because the first templates never landed in those classes ("I am fond of X"
classifies FACT; "daughter starts school" classifies RELATIONSHIP). Probe-verified producers were
added, the board re-frozen at **23 cells**, and the live registry now runs entirely inside the
mapped board: 29/0/0. Completeness stopped being an assumption the moment the field could falsify
it — and it did, and the fix was a diff against a committed table.

**Phase B2 — cutover. ARMED 2026-07-14.** `verdict.enforce()` at the seam behind `SP_SEM_VERDICT`
(true on the live profile). Three deliberate properties: the law can only EXCLUDE (it cannot admit
around the match gate, cannot reorder — authority moved, code did not get deleted); an UNMAPPED
cell is KEPT and counted, loudly (unlegislated is not forbidden — her self-preference rows were one
field-run away from being muted for MY enumeration gap); a missing table disables enforcement.
The receipt behind arming it: **G-SEM-VERDICT** — all 160 corpus queries byte-identical (addrs AND
scores) with the flag on while slots are empty, the drop mechanism demonstrably firing with a
witness, k-window refill shown to be the seam's, not the law's. Plus the 29/0/0 live shadow.

**Phase C — topic-equivalence as a consumed relation. ARCHITECTURE SHIPPED 2026-07-14; the live
oracle is the open calibration item.** `harness/skills/slots.py`: same-subject LINKS in a derived
append-only sidecar (`SP_SEM_SLOTS`), keyed by content addr, proposed by an oracle, consumed by
`verdict.competition()` as a second detector feeding the SAME coordinate (the board did not grow —
the relation grew eyes). Quarantine direction proven: a link can only push toward competition=1 —
silence — so a wrong link costs a sentence and can never make her speak over him, admit, or
retire. **G-SEM-SLOT 11/11** is the ladders finding end-to-end: leak reproduced, then closed by a
link + enforcement, his words standing, registry byte-identical.

The honest ledger on the live oracle: the greedy 12B `/v1/oneshot` judge, across four prompt
designs, produced **zero false "same" verdicts and zero true ones** — every miss fell in the safe
direction (unparseable/NO ⇒ no link ⇒ today's behaviour), and the boundary thesis holds one more
time: a hand-worded prompt is a hand-built signal. Successors, in order: an OPERATOR oracle (the
sidecar accepts any oracle tag — a human-proposed link works today); a judged eval with a fixture
pair-corpus and a yield/precision scoreboard (the S1 pattern, applied to the judge); or the
learned-selector route (the W_c pattern). Until then the scan runs, proposes nothing wrongly, and
the mechanism waits armed.

Existing gates (G-CLAIM, G-SECRET, G-DURABILITY...) stay green — they are corollaries of table
cells now, and the meta-gates prove there are no cells they missed.

**Phase C — maximal-consistent-view recall.** The recall result set is defined as the maximal
table-consistent subset of matched rows (testimony_wins et al. become properties of the view), with
the rank layer ordering it and oracles proposing candidates into it. This is where the Phase 3
`/v1/recall_rank` oracle (G-SEM-SCOREBOARD's direction) plugs in — as a proposer under quarantine,
held to the same scoreboard.

---

## 2.1 WHERE IT GOES NEXT

The extension map — the updated mathematics (OC/MAX/f usability, FIN/USE admissibility, the
φ-form gate language with bounded negation) mapped onto every remaining hand-ruled decision site
in this tree — lives in [`INVARIANT-ROADMAP.md`](INVARIANT-ROADMAP.md). Rows move from there to
phases here, with gates, one at a time.

## 3. HONESTY CLAUSE

What is proved is exactly this and no more: properties of the verdict layer over the signature
vocabulary, by finite enumeration, under the invariances of §1.2. Nothing here proves the ORACLES
right (nothing can — that is the point of quarantining them), nothing here makes recall
semantically better by itself (that is the rank/oracle layers' job, measured by the scoreboard),
and the enumeration is only as good as the signature: a policy-relevant distinction missing from
σ is invisible to every meta-gate. Adding a coordinate to σ is therefore a REVIEWED event — it
multiplies the game board, and the meta-gates must be re-run and re-committed in the same change.
