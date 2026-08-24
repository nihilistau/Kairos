---
type: design
title: "SEMANTICS — the SEM stack (S0–S4)"
status: PHASE 2 MEASURED (2026-07-14); S0 index live. S1 rank was default-off with the
        receipt until 2026-08-23, when §S0b ARMED it on `aux-1024-v1` — seam recall@1
        0.46 -> 0.53, decider hit 0.06 -> 0.17, both foreign-noise metrics unchanged.
        `/v1/capture`'s refusal, which that finding rests on, was fixed the same day and
        the l5/l5 re-measurement it made due was run and lost (l5 0.10) — both corrected
        in place in §S0b, 2026-08-25.
---

# SEMANTICS.md — the SEM stack (S0–S4)

**Status: PHASE 2 MEASURED — THE τ-GATE LOST, ON THE RECORD (2026-07-14). Phases 0–1 complete
(corpus frozen; baseline receipt: decider hit **0.06**, foreign precision 0.8667; S0 index 81/81,
G-SEM-INDEX 21/21). Phase 2: the S1 dual-admission machinery is shipped default-off (G-SEM-RANK,
G-SEM-CLAIM 6/6, G-SEM-CONSERVE), the engine seams are live (`/v1/embed` with QKEY chat-template
provenance; `SP_CAPTURE_L5` mints `ep.l5` on `/v1/capture` — grown episodes are no longer
L5-invisible), and the scoreboard was run against every reachable embedding space: hash-space
(= lexical exactly), l5 raw (hit 0.14 but precision 0.0167), l5 centered (precision 0.0000),
l5 re-provenanced (argmax 2/10). **Full negatives + diagnosis: [`gates/G-SEM-SCOREBOARD.md`](../gates/G-SEM-SCOREBOARD.md).**
The two findings: L5 cosine is a ranking signal the engine only uses inside its learned selector,
and foreign-query rejection is an ABSENCE judgment no similarity threshold can make.
**A fourth contender was run and lost, 2026-07-30** — query→keyword expansion from store
co-occurrence (`harness/skills/expand.py`, receipt `harness_tests/fixtures/sem/expand-receipt.json`).
It is the only contender so far that improved recall: **+0.04 decider hit (0.06 → 0.10)**. It paid
**−0.1167 foreign precision (0.8667 → 0.75)** for it, and the ship condition is both numbers, so
it joins the negatives. Its ceiling is structural rather than tunable: the association table is
keyed on words the store has SEEN, and a paraphrase is by construction made of words it has not —
**240 of 280 paraphrase query words have never appeared in the registry**, and at the safe setting
it fired on **0 of 100** queries, which is no result rather than a negative one. Expansion needs a
bridge built from something other than the store's own vocabulary. Phase 3 is
therefore revised: expose the engine's learned W_c + (E+1)-NULL selector (G-CHAT-B3-WC-DIV2:
360/361 + 50/50 reject) as the admission oracle via a read-only `/v1/recall_rank` route, into the
same seam, behind the same flag, held to the same scoreboard. `[sem].rank` stays FALSE until a
`ships: true` receipt exists. Live status: `python tools/sem_dash.py`.**

This is the Friedman stack — PPT-ARM Papers III/IV, the KSTE encoder, the dominance sieve, the
WKL₀/PRA conservation asymmetry — lifted from the engine's KV cache to the fact registry. Paper III
built order-invariant memory for *tokens*; this document builds it for *facts*: semantics, memory,
and recall across every surface (spine, tools, kairos scheduler, notes, MEM-OKF).

Companion reading, in order:

- [`INVARIANT-MEMORY.md`](INVARIANT-MEMORY.md) — **the foundation (2026-07-14):** the memory
  system as a finite mathematical object — order-invariant verdict tables, invariant maximality,
  the PRA entry bar, oracle quarantine. This stack is now an instance of that discipline.
- [`AGENTS.md`](../AGENTS.md) — the bug class, the non-negotiables. This design is shaped around them.
- [`docs/MEMORY-AND-RECALL.md`](MEMORY-AND-RECALL.md) — the current registry, the one seam.
- PPT-ARM-III-Friedman.md / PPT-ARM-IV-KSTE.md (Position_Is_Arithmetic, `Archived/SP-PPT-ARM/`) —
  the prior Friedman work this extends.
- Friedman, *Invariant Maximality and Incompleteness* (2014) — the epistemic template.

---

## 0. THE THESIS, AND THE TWO FACTS THAT CONSTRAIN IT

**Thesis.** Recall today is lexical: token overlap gated at `min_overlap`, salience as a tie-break
prior. It cannot recall a paraphrase. The relevance term the `salience()` docstring already names as
missing (the Generative-Agents triad: recency + importance + **relevance**) is the semantic layer.
This document specifies where it lives, what it is allowed to do, and what proves it.

**Constraint 1 — the signal already exists and is measured-good; it is simply not consumed.**
The engine's `recall.rs::l5_query_embed()` produces a 512-dim, mean-over-heads, L2-normalised
layer-5 last-token embedding; `cos512()` over these recalls paraphrases at **88.5% vs Jaccard 8%**
(G-REP-LAYER-L5). `/v1/capture` already mints K/V episodes for every remembered fact (async since
G-CAPTURE-ASYNC), and `Projection::signature()` already packs a 256-bit C2 SimHash. On the live
profile the harness reads none of it. Phase 1 is therefore *plumbing, not invention*.

**Constraint 2 — the boundary thesis.** The core repo's hard-won result (ARM/W_c, repeated across
`core/`): a **learned selector on diverse data beats every hand-designed number-theoretic signal**;
each structure-on-content lever tried was measured-inert and is kept as an honest negative. And
Paper III §11.6: strict Kruskal embedding ⪯ on KSTE trees discriminated *nothing* on real keys
(AUC 0.500); the operational relation that shipped is **Dickson dominance ⪯_d on the (σ₀, σ₁) ∈ ℕ¹⁴
signature** — 17× intra/inter separation, 0.95 µs p99, and a cache that settles instead of churning.
Consequence for this design: the *ranking* signal is the learned/model-native one (L5 embeddings);
the WQO machinery is used only where it is provably the right tool — **lifecycle, subsumption,
and termination** — and every SEM feature ships default-off until it beats the lexical baseline
on a fixed corpus. No exceptions. That is not caution theatre; it is the repo's own measured history.

---

## 1. THE EPISTEMIC CONTRACT (read this even if you skip the rest)

The reverse-mathematics spine of the design, stated as engineering rules. This is what the
Friedman/Harrington material actually buys us — not decoration, a contract:

1. **Conservation (WKL₀ ⇾ PRA, Harrington–Friedman).** Ideal, global, non-constructive reasoning
   (embeddings, dominance frontiers, ultrafilter-style merges) is admissible **inside ranking and
   organization only**. It may reorder, propose, and frame. It may never, on its own authority,
   create, retire, or reclassify a fact. Every state change still goes through `memory.remember()`
   and the supersede machinery, with provenance. The ideal tier is conservative over the ground
   tier: turn `SP_SEM_*` off and every existing gate is green, byte-identical behaviour.
2. **The gate is the miniaturization (Friedman's finite forms).** Every "eventually/always" claim
   this design makes has a bounded, machine-checkable instance in `harness_tests/`. A SEM claim
   without a gate does not ship. Failures must be *cheap finite witnesses* — a row id, a query, a
   score pair — never "the embedding felt wrong".
3. **Producer/consumer closure (the Benzmüller lesson, already paid for here as G-SECRET §4).**
   Gödel's own axiom set sat inconsistent for 40 years until a model finder looked. Our version:
   every value any decider branches on must be one some writer can produce, and the gate asserts
   the *producer*, not a hand-built row. SEM extends this check to every new vocabulary it adds.
4. **The principal ultrafilter is named, not implied (Łoś).** Merging verdicts across sources is
   only coherent under an ultrafilter; over finitely many sources every ultrafilter is principal —
   a dictator per decision context. Ours is already law: **his testimony is the dictator on facts
   about him** (`testimony_wins()`, non-negotiable 4). SEM formalizes the remaining contexts
   (§5) and, where no dictator exists, returns an explicit *undecided* verdict at read time
   rather than papering over it. First-order verdicts survive merge; global properties
   (no orphaned supersede chains, tombstone reachability) do not, and are re-gated after any merge.
5. **Repair loops carry a termination ordinal (ε-substitution, Ackermann 1940).** Any loop that
   revises provisional referents or consolidates memory must name its well-founded measure. Ours
   is the WQO: Dickson's lemma bounds the antichain, so the frontier settles (§4). A loop without
   a named measure does not ship.

---

## 2. THE SEM STACK

| Tier | Name | What it does | Math it stands on | Ships in |
|---|---|---|---|---|
| S0 | Semantic signature | every fact gets a content address + L5 embedding + C2 sig + (σ₀,σ₁) dominance signature, minted async at write | KSTE encoder, Dickson ℕᵏ | Phase 1 |
| S1 | Semantic rank | relevance term composed into THE seam; paraphrase recall | learned selector (boundary thesis) | Phase 2 |
| S2 | Subsumption & consolidation | dominance proposes supersede; the whistle generalizes reflection chains | ⪯_d wqo, Higman/Kruskal whistle + msg | Phase 3 |
| S3 | Verdict semantics | one named merge rule per decision context, across all surfaces | Łoś, principal ultrafilter, filters ⇒ undecided | Phase 4 |
| S4 | Conservation gate | the standing proof that S0–S3 changed nothing they may not change | WKL₀/PRA conservation | every phase |

(Naming note: tiers are S0–S4, *not* L-numbers — "L5" in this repo means transformer layer 5.)

### S0 — Semantic signature (the sidecar index)

New file: `var/memory/semindex.jsonl` (path from `SP_SEM_INDEX`). One row per signed fact:

```
{ "addr":   sha256(norm(text))[:16],   // MEM-OKF addr_of(); the join key everywhere
  "ts":     <registry row ts>,          // joins to the registry row; registry is unchanged
  "model":  "<engine model build tag>", // the knight-mask lesson: an embedding is a MODEL ARTIFACT
  "l5":     [512 × f16],                // l5_query_embed of the fact text, via /v1/capture path
  "c2":     [4 × u64],                  // 256-bit SimHash
  "sig":    [14 × u8]                   // (σ₀, σ₁) KSTE dominance signature
}
```

**WHAT ACTUALLY SHIPS TODAY (audited 2026-07-30).** `harness/skills/semindex.py:167` writes
`{addr, ts, model, vec}` — **`c2` and `sig` have never been minted**, and `l5` ships as the generic
`vec` (tagged `hash256-v1` or `l5-512-v1`). The row above is the *design*; treat the two fields as
TODO, not as a description of the file on disk. `sig` is now fully specified — see **§S2.1** — and
is the prerequisite for everything in §S2. Note also that on the live profile `SP_SEM_RANK=false`,
so the one vector consumer never runs: the index is **minted every write and read by nothing**.

Rules, each one a bug this repo has already had:

- **The registry schema does not change in Phase 1.** Sidecar only. The join is `(addr, ts)`.
- **Append-only, tombstone-blind by design.** The index never encodes lifecycle; `lifecycle` is
  read from the registry row *at the seam*, at read time. A second copy of the tombstone flag is
  the two-paths bug with a new hat on.
- **Minted on the existing async `/v1/capture` path** (G-CAPTURE-ASYNC). No new writer: the index
  is derived data, recomputable from registry + model. `verify` recomputes and diffs — that is
  the integrity gate, same shape as MEM-OKF conformance.
- **`model` is checked at read.** Embeddings from a different model build are dead rows: skipped,
  never compared, re-minted by a maintenance pass. Cosine between two models' spaces is noise
  with a confidence interval.
- **Offline fallback.** With no daemon, S0 falls back to the dormant Nexus `HashingEmbeddingProvider`
  (256-dim, honest about being weak) or skips minting. Offline gates run with recorded fixtures —
  never a live GPU (gate doctrine: OFFLINE means offline).

### S0b — `aux-1024-v1`, and the finding that reopened S1 (2026-08-23)

**S1 was off for a month against four committed negatives, and all four were measured
against a bag-of-words index.**

`/v1/capture` **refused** on the model MoE — *gemma4_decode_cuda: gemma4-MoE not
supported on this path (ADR-013)* — from the day the model landed until 2026-08-23. Measured on
the live store while it was refusing: **253 of the 253 rows written since 2026-08-19 carry `npos=0`**, no `ep.l5`
sidecar has been minted in three weeks, and **641 of 747** directories under
`var/memory/eps/` are empty shells of failed mints. The document index was 753 hash rows to
57 stale l5 rows. Cosine 0.0167, `W_c` 0.02, the LLM judge, `frame_link` 0.625 —
every one of those contenders was ranking against bag-of-words vectors. There was no
semantic index for them to compete with.

> **CORRECTED 2026-08-25, and the refusal above is history rather than status: `/v1/capture`
> WORKS on the model, and has since 2026-08-23.** The MoE FFN seam landed the same night this
> section was written (`3ee6333`, plus two CUDA lifetime bugs that were never about MoE) —
> her memories mint real episodes again, `ep.k` / `ep.v` / `ep.mf` / `ep.q` and **`ep.l5`**,
> the last of which had not been written in three weeks. Receipt:
> [`ENGINE-SESSION-2026-08-23.md`](ENGINE-SESSION-2026-08-23.md); the 247 owed episodes were
> backfilled the same day ([`../gates/EPISODE-BACKFILL-2026-08-23.md`](../gates/EPISODE-BACKFILL-2026-08-23.md),
> L5 coverage 21% → 95%). **The finding above survives the correction and is not weakened by
> it**: the four contenders WERE measured against a bag-of-words floor, because at the time
> they were measured there was no document index to compete with. That is why S1 was reopened,
> and it stays the reason. What the fix changed is which space then had to prove itself — see
> the note under point 3 below, and the l5 space's first real measurement in
> [`../gates/SEM-L5-VS-AUX-2026-08-23.md`](../gates/SEM-L5-VS-AUX-2026-08-23.md) (l5 0.10
> against aux's 0.53 — measured, not assumed).

It failed silently because `_mint_now` wrapped the whole call in a bare `except`, which
cannot tell *the daemon is down* from *the engine says never*. Those now get different
answers: a transport failure is quiet and retried; a REFUSAL is logged once with the
engine's own words, never asked again this process, and surfaced by
`memory.capture_status()` and `verify_registry()`.

**The space.** `aux-1024-v1` is the CPU sidecar's LFM embedding — the same door the
archive uses, off the GPU, ~13 s to embed the whole live store. It was the only real
embedder this box had while capture was refused — and it stayed the armed one after capture
came back, on a measurement rather than on inertia: the l5 space, scored for the first time
once there were fresh `ep.l5` rows to score, came in at **0.10 against aux's 0.53**
(2026-08-23, [`../gates/SEM-L5-VS-AUX-2026-08-23.md`](../gates/SEM-L5-VS-AUX-2026-08-23.md)).

**The receipt** (`fixtures/sem/aux-receipt.json`, scored by `harness_tests/sem_aux.py`
through the REAL seam, on the same frozen 160-query corpus that set the bar):

| | lexical | aux @ tau 0.40 |
|---|---|---|
| `seam_recall_at_1` | 0.4600 | **0.5300** |
| `decider_hit_rate` (what reaches her context) | 0.0600 | **0.1700** |
| `foreign_seam_false_hit_rate` | 0.5333 | 0.5333 |
| `foreign_decider_false_injection_rate` | 0.1333 | 0.1333 |

More recall at identical noise. Armed 2026-08-23. Three things make it work, and each one
was a wrong answer first:

1. **Raw cosine, never centered.** `centered_cosine` against `space_mean()` is an *l5*
   fix for *l5*'s anisotropy. On this space it measures recall@1 **0.29** — worse than
   lexical. Wiring the new space through the existing centred branch for consistency would
   have shipped a measured regression.
2. **Tau is per space, and the first tau was wrong.** A top-1-only calculation put the
   operating point at 0.20. The seam admits EVERY row over tau, not just the best, so 0.20
   injected an unrelated fact on **55%** of foreign queries — the *she recited a memory
   nobody asked about* bug, bought back. 0.40 is the most recall for which not one metric
   degrades. The sweep is in `semindex.aux_tau()`.
3. **The query must land where the DOCUMENTS are.** As written on 2026-08-23: `/v1/embed`
   worked (~1.47 s) while `/v1/capture` did not, so the engine could embed a QUERY and not a
   DOCUMENT. Preferring it would have spent 1.47 s of every turn on a vector with 57 stale
   rows to match. `query_embed` prefers aux while armed — **and if capture is ever fixed,
   that order must be measured again, not assumed back.**

   > **THAT DEBT CAME DUE THE SAME DAY, AND IT WAS PAID — recorded here 2026-08-25 because
   > this bullet was still describing the asymmetry as live.** Capture came back on
   > 2026-08-23 (see the correction above) and the backfill gave 259 of her 274 live rows an
   > `ep.l5` vector, so the stated reason for preferring aux at query time — *there is nothing
   > on the document side to match* — stopped holding within hours. The re-measurement the
   > clause demanded was then actually run, l5 query against l5 documents through the REAL
   > seam, on the same frozen corpus:
   > [`../gates/SEM-L5-VS-AUX-2026-08-23.md`](../gates/SEM-L5-VS-AUX-2026-08-23.md) —
   > **l5 `seam_recall@1` 0.10, against lexical 0.46 and aux 0.53.** `query_embed`'s order is
   > therefore **re-earned rather than inherited**, which is the whole thing this escape hatch
   > was written to prevent, and the correct reading of the bullet above is now *"aux wins on
   > quality"* and no longer *"aux wins because the alternative is empty"*.
   >
   > It was worth running for a second reason: the same measurement caught a regression the
   > backfill had just created. `load()` kept one row per `(addr, ts)` with later-in-
   > `KNOWN_MODELS` winning, and the tuple was ordered by when each space was ADDED
   > (`HASH, AUX, L5`) — harmless while l5 was empty, and the instant it filled, her document
   > index silently swapped to the space that measures 0.10 (`aux wins 274 → 19`,
   > `l5 wins 53 → 308`). Nothing failed; she would simply have got quietly worse at
   > remembering. Corrected to `(HASH, L5, AUX)` — precedence by MEASURED quality, in
   > agreement with `query_embed` — and verified by mutation. **An assumed-back ordering would
   > not have been caught by anything.**

The S0 contract is untouched: derived, append-only, tombstone-blind, recomputable, cannot
write the registry. An upgrade is an APPEND (`semindex.backfill_aux`), never an edit.

### S1 — Semantic rank (inside the seam, nowhere else)

The change lands **inside `memory.search_memories_ranked_rows()`** and no caller. Every read
surface — `recall()`, `search_memories*()`, `spine.recall_decider()`, `forget()` matching,
kairos reflection reads — inherits it by construction. Adding it anywhere else is the exact bug
this repo has three tombstones for.

Scoring, composed with (not replacing) what exists:

```
candidate admission:   ov  = _overlap(query, text)            # unchanged lexical gate
                       cos = cos512(l5(query), row.l5)         # NEW, only if index row valid
                       admit iff ov >= min_overlap  OR  cos >= SP_SEM_TAU     # dual gate
rank:                  score = max(novᵢ, ncosᵢ) + 0.22 * lc.salience(e) + existing adjustments
                       (_target_and_rank pronoun/relationship/identity terms unchanged)
then, unchanged:       lifecycle filter (already first), testimony_wins(), k-truncation
```

- **Semantic admission is admission by MATCH, not by salience.** The G-SALIENCE law — salience
  never resurrects unmatched chatter — stands untouched: salience remains a tie-break on *admitted*
  rows. A paraphrase admitted at `cos ≥ τ` **is** a match; that is the entire point (8% → 88.5%).
- **τ is calibrated against a negative corpus, precision-first.** G-RECALL-PRECISION is the gate
  most at risk: a foreign query must not hijack an unrelated stored fact. τ ships at the value
  giving ≥ 98% precision on the fixed foreign-query fixture, measured, in the receipt.
- **Query embedding cost:** one `l5_query_embed` per recall. `recall_decider` runs per turn; the
  budget is the async-capture discipline — embed the query on the same warm forward the turn
  already pays for, or skip semantics for that turn (degrade to lexical, never block speech).
  Latency receipt required (the 1,702 ms → 29 ms lesson).
- **Flag:** `SP_SEM_RANK=0|1`, default 0, **mapped in serve.py's `build_env` or it does not exist**
  (G-ONEDOOR). Same for `SP_SEM_TAU`, `SP_SEM_INDEX`. Nothing reaches the engine from a stray shell.

### S2 — Subsumption and consolidation (dominance proposes; testimony disposes)

Two uses of the WQO, both lifecycle-side, neither on the speech path:

**STATUS 2026-07-30, item 1: BUILT, GATED, MEASURED, AND DELIBERATELY NOT ARMED.**
`harness/skills/dominance.py` + `harness_tests/g_sem_dominate.py` (62/62, OFFLINE), wired into
`memory.remember()` beside `find_superseded` behind `SP_SEM_DOMINATE`, **default false on every
profile**. The read-only run over his live registry is frozen at `harness_tests/fixtures/sem/dominate-receipt.json`:

> 84 live rows → **7 supersede proposals**, of which **4 good, 3 bad** (adjudicated by hand — seven
> pairs is far too small to call a precision figure, so it is reported as counts with every pair
> listed). The bad three would each have tombstoned the wrong row, including "My cat Tuffy is
> female." proposing to retire "Sam is a cat person."

So it ships as a proposer nothing consumes. **No bar was invented to sit just under the
measurement** — a real one needs supersede-labelled pairs on the frozen corpus, which do not exist
yet. Two genuine bugs were found and fixed by that run and are recorded in the receipt: content
containment was ignoring names (`lifecycle.topic_of` drops "sam" and "kairos" by design, which
made "I am Kairos" reduce to the EMPTY SET — contained in everything), and a contentless row was
subsumable by anything at all.

**Item 2, the whistle: SOURCED, NOT BUILT.** No implementation, no `G-SEM-WHISTLE`.

The grounding for both is solid and is *ours*:
**`Position_Is_Arithmetic/Archived/SP-PPT-ARM/PPT-ARM-III-Friedman.md` §11.6**, which defines ⪯_d,
proves the settling argument, and carries the measured receipts. See §S2.1 for the signature spec.

1. **Supersede candidate generation.** Today supersede matching is bag-of-words. Add: new fact F
   whose signature dominates an old live row R (`sig(R) ⪯_d sig(F)`, same slot, same speaker)
   is *proposed* as superseding R. Proposed — the existing rules dispose: an inference never
   retires an observation (non-negotiable 4), `speaker` lanes never cross, the write still goes
   through `memory.remember()`, provenance appended to `src` as prose. Dominance is a candidate
   generator with better recall than substring matching; it holds no authority.
2. **The whistle (Sørensen–Glück / Leuschel, the operational Kruskal).** Reflection and any future
   consolidation pass keep the sequence of structured states they generate; before appending a
   near-duplicate conclusion, test embedding against ancestors. On whistle: **generalize** —
   write the most-specific-generalization as one new `inferred` row citing its parents in `src`,
   instead of accumulating the chain. Nothing is destroyed; the parents stay live unless the
   normal supersede rules retire them.

   **TERMINATION ORDINAL CORRECTED 2026-07-30.** This said "Higman/Kruskal is the termination
   ordinal". For *our* structure it is **Dickson (1913)**, and the difference is load-bearing:
   Paper III §11.6 measured strict Kruskal tree embedding on the encoder and got **AUC 0.500 — it
   discriminates nothing** — then replaced it with elementwise dominance on `σ ∈ ℕ¹⁴`. Dickson's
   lemma gives the wqo on `(ℕ¹⁴, ≤_elem)`, the image is bounded in `[0,60]¹⁴` so the antichain is
   finite, and **Dickson's lemma is provable in PRA** where Kruskal–Friedman's TREE(3) is not — so
   the refutation property is *strengthened*, not weakened, by the move. The whistle's own
   citation (supercompilation) is unaffected; only the ordinal it appeals to changes. The cache
   plateau (~307/512, and it *settles* rather than churning) is the physical manifestation.

### S2.1 — `sig[14]`, specified (Paper III §11.6)

**First, the trap.** There are two unrelated 14s in the ARM corpus and conflating them produces a
wrong implementation. The **14 fp16 anchors** are the encoder's *input* (bytes 0–27 of the 63-byte
Spinor block, from the Knight-skeleton selection). **`sig[14 × u8]` is its *output***, and has
nothing to do with VHT2, the Möbius reorder, or squarefree indices.

```
sig[0..4]   σ₀ ∈ ℕ⁵ : (A-count, B-count, C-count, max_depth, node_count)
sig[5..13]  σ₁ ∈ ℕ⁹ : 3×3 counts of PROPER ancestor→descendant pairs by label pair,
                      row-major (ancestor label, descendant label), A=0 B=1 C=2,
                      each cell saturating at 255

Q ⪯_d K   ⟺   ∀i ∈ [0,14) :  K.sig[i] ≥ Q.sig[i]
```

Fourteen byte compares. Termination is **Dickson** on `(ℕ¹⁴, ≤_elem)`; the image is bounded in
`[0,60]¹⁴` so the antichain is finite. `⪯ ⟹ ⪯_d` and the converse fails — dominance is a sound
**over-approximation** of tree embedding (measured: 0 false negatives over 10 000 pairs), which is
exactly the shape a *proposer* should have.

**Direction is easy to invert and matters:** the NEW row is absorbed when an EXISTING row dominates
it — richer subsumes poorer.

**Four things no paper specifies. We choose them, we write them down, we version them:**
the row-major convention above; whether root counts toward `max_depth` (it does not — root is
depth 0 and is unlabelled, so it cannot appear in σ₁ either); the 14-byte repacking of Paper III's
`uint64` + 16-byte structs; and `d_tree` if a fuzzy radius is ever wanted (undefined in the papers).

**Signatures are not portable across encoders** (Paper IV §9.5: the encoder is deterministic *given
the calibration knight-mask*; "ship the knight-mask with the model; treat it as a model artefact").
The `model` field above is where that lives — tag it `sig-v1` and refuse cross-version comparison,
the same way `ep.l5.geom` now refuses a cross-model recall key.

**Honest limits, to be repeated in the gate's docstring rather than discovered later:** ⪯_d earned
its place at cos ≥ 0.995 (17× intra/inter) and decays to 1.4× at σ = 0.05; measured eviction was
93.86%, which is *above* Paper IV §9.2's own 80% "losing novel structure" alarm; and the paper's
ship gate (T2.3) passed only in OBSERVER mode — hard eviction during attention was found "too
aggressive on real activations". All of which is why, here, **dominance proposes and testimony
disposes**: our supersede rate needs its own bar, measured on the frozen corpus.

**TWO THINGS THE BUILD FOUND THAT THE SPEC ABOVE DOES NOT SAY, both load-bearing:**

1. **Structure alone is not subsumption.** `compare(sig("He drinks Oolong tea."),
   sig("Sam has a cat."))` is `DOMINATES`. Fourteen counts cannot see topic, because here A/B/C
   are structural *roles* — Paper III's labels come out of a quantizing encoder over Key vectors,
   where the label itself carries signal, and a text encoder does not get that for free. So
   subsumption is the **conjunction of two dominances on two carriers**: content containment
   (`content_of(held) ⊆ content_of(new)`) *and* `sig(held) ⪯_d sig(new)`. Containment of a finite
   set is elementwise dominance of indicator vectors, so this is one order over a product, not a
   heuristic bolted onto a theorem. Both halves are necessary: content alone fires on any
   restatement, structure alone fires across unrelated topics.
2. **The encoder's image is near-totally-ordered**, measured: over 200 synthetic texts spanning
   86 distinct signatures, the retained antichain is **1**. Every σ cell scales with clause count,
   so the widest text in a family dominates the rest. That is *fine for a supersede proposer* — an
   antichain is exactly the set of pairs dominance has nothing to say about — but it means the text
   image cannot demonstrate termination, and `g_sem_dominate.py` §7a therefore tests settling over
   signature vectors (a 364-element antichain that fully absorbs a second wave) rather than over
   text. Three drafts of that section "passed" over a degenerate one-element stream first.

**Do not call `kairos-system/include/sp/kste.h`.** It is an unrelated v1 — 13-node tree,
6 quantized order statistics per label, 64-byte wire image — whose "Tier-0/Tier-1" mean different
things. Two things there *are* worth stealing: its **tri-state** outcome (`INCOMPARABLE` is a
genuinely different answer from `DOMINATED`, and a supersede decision needs that distinction — the
paper's boolean loses it), and its `LAYOUT_VERSION` discipline.

### S3 — Verdict semantics across surfaces (the Łoś layer)

Every decision context that merges sources gets a **named** rule, in one table, in this file:

| Context | Sources merged | Rule | Undecided possible? |
|---|---|---|---|
| fact about HIM | his testimony vs her inference | principal: he is the dictator (`testimony_wins`) | no |
| fact about HERSELF | her self-rows vs her inferences | principal: `observed/confirmed` self-rows win | no |
| conflicting same-status rows | two live observations, same slot | most recent `last_seen` wins the *rank*; neither is retired without supersede | **yes** — render both, framed |
| cross-store (registry vs MEM-OKF vs notes) | different lanes | lanes do not merge; registry is authoritative for facts, notes are not facts (existing law) | n/a |

"Undecided" is a **read-time verdict, never a written status**: `render()` frames the conflict
("Sam has told me both … and …") and the seam returns both rows. Nothing writes
`status: disputed` — the write-time contradiction detector was deleted deliberately and stays
deleted; the rule lives at the read seam, where it has always actually worked.

### S4 — The conservation gate

The standing, executable form of §1.1: with all `SP_SEM_*` off, the full offline suite runs
byte-identical to pre-SEM behaviour; with SEM on, no row that both gates would exclude is ever
admitted, and no existing gate regresses. This gate exists from Phase 1, before any behaviour
changes — it is the harness the rest is built inside.

---

## 3. WHAT SEM MAY NEVER DO (the blast-radius clause)

Written down because §3 of AGENTS.md says the imprecise version of this is a bug generator:

- SEM never writes the registry. It writes one sidecar file, derived, recomputable.
- SEM never deletes anything, including its own index rows (dead-model rows are skipped, kept).
- SEM never retires a row: it proposes; `remember()`/supersede/testimony rules dispose.
- SEM never crosses `speaker` lanes. Her self-rows and his rows never compare for supersede.
- SEM never touches `private-secret` dispatch: the policy decline (G-SECRET) runs *after* ranking,
  unchanged. A secret recalled more accurately is still declined.
- SEM never blocks speech: any semantic component missing/slow/dead degrades to today's lexical
  path, silently, with a telemetry counter — not an error in her mouth.
- SEM never branches on `src` (it is prose), and any new enum it introduces enters the
  producer/consumer closure gate the day it is written.

The worst case that must stay impossible: an embedding-similarity pass concluding two identity
rows are "the same" and merging them — that is the identity-slot bug with a cosine on top.
The `speaker`-lane and propose-only rules above are the guards; G-SEM-CLAIM (below) is the proof.

---

## 4. PREREQUISITES (blocking, before Phase 1 code)

1. **One mem_class vocabulary.** Three exist today: `lifecycle.classify()`,
   `recall.rs::classify_mem_class()`, MEM-OKF `MEM_CLASSES`. SEM adds signatures keyed to classes
   (half-lives already branch on them), so the divergence becomes load-bearing. Unify to one
   table, one owner, consumed by all three — then the closure gate (§1.3) covers all of it.
2. **Fixed benchmark corpus.** DONE (v1): 50 synthetic facts written through the real writer
   (`fixtures/sem/gen_corpus.py` — 18 phrasings were declined by `is_memorable()` and rephrased,
   not hand-inserted), 100 paraphrase + 60 foreign queries, frozen under `harness_tests/fixtures/sem/`.
   Lexical baseline receipt committed first, per the boundary thesis: seam recall@1 0.46,
   **decider hit rate 0.06**, foreign decider precision 0.8667. Grow toward ~200/~200 in v2.
3. **The engine L5 seam (blocks the Phase 2 win, found during Phase 1).** `/v1/capture` writes
   only `ep.k`/`ep.v`/`ep.mf`; `ep.l5` is minted only by `routes.rs::mint_ep_l5` on the **retired
   daemon-writer path**, and no route returns an embedding to a caller. So today S0 indexes in
   hash-space (honest, weak — it will not beat the lexical baseline and is not expected to).
   Phase 2 needs two small engine seams: (a) call `mint_ep_l5` from `v1_capture` (flag-gated;
   the harness `upgrade()` hook already reads the sidecar the day it appears), and (b) a query-time
   embed route (e.g. `/v1/embed` returning the `l5_query_embed` of a text) for the seam's cosine.
   Both reuse existing engine functions; neither adds a memory writer.

---

## 5. THE GATES (no claim without one)

| Gate | Tier | Proves | Mode |
|---|---|---|---|
| G-SEM-CONSERVE | S4 | flags off ⇒ byte-identical suite; flags on ⇒ no existing gate regresses | OFFLINE |
| G-SEM-INDEX | S0 | index rows recomputable (verify), model-tag honored, tombstone-blind (lifecycle read from registry at seam) | OFFLINE (fixtures) |
| G-SEM-RANK | S1 | paraphrase recall beats lexical baseline on the fixed corpus; foreign-query precision ≥ 98% at shipped τ | OFFLINE (fixtures) |
| G-SEM-CLAIM | S1/S2 | through the REAL path (`spine.recall_decider`): tombstones stay dead, testimony still wins, speaker lanes never cross, secrets still decline — with SEM on | OFFLINE |
| G-SEM-DOMINATE | S2 | dominance proposals: an inference never retires an observation; every supersede has provenance; proposals against the real producer, no hand-built rows | OFFLINE |
| G-SEM-WHISTLE | S2 | consolidation terminates (frontier settles ≤ N steps on adversarial input); every generalization row cites parents | OFFLINE |
| G-SEM-STABLE | S3 | Friedman stability as a predicate: appending unrelated facts / advancing the clock does not flip recall verdicts on old queries (tail-shift invariance) | OFFLINE |
| G-SEM-CLOSURE | all | every enum any SEM decider branches on has a producer; asserted against the producer | OFFLINE |
| G-SEM-LIVE | S1 | end-to-end on `serve.py companion`: paraphrase recalled in her actual reply; latency receipt; degrade-to-lexical when daemon starved | LIVE |

Gate-writing rules apply in full: assert through the real path; never supply your own precondition.
G-SEM-STABLE is the novel one — it is Friedman's invariant-maximality condition scaled down to a
unit test, and it is exactly the property a memory that lives across months must have: *decisions
about old data do not flip because time passed.*

---

## 6. PHASES

| Phase | Lands | Ship condition |
|---|---|---|
| 0 | prerequisites (§4), G-SEM-CONSERVE, benchmark corpus + lexical baseline receipt | baseline receipt committed |
| 1 | S0 sidecar index, async mint, verify; G-SEM-INDEX | index for 100% of live rows, verify green, zero registry diffs |
| 2 | S1 rank behind `SP_SEM_RANK`; G-SEM-RANK, G-SEM-CLAIM, G-SEM-LIVE | **beats lexical baseline on the fixed corpus** (boundary thesis) — else it stays off and the negative result is committed, honestly, like every ARM negative before it |
| 3 | S2 dominance proposals + whistle; G-SEM-DOMINATE, G-SEM-WHISTLE | zero supersedes without provenance across the suite |
| 4 | S3 verdict table wired across spine/kairos/notes/MEM-OKF lookup; G-SEM-STABLE | MEM-OKF `lookup` gains the same dual gate (its C2 addrs are already the join key) |

Each phase updates `AGENTS.md` §3, `docs/MEMORY-AND-RECALL.md`, and `gates/GATE-INDEX.md`
**in the same commit** (AGENTS.md §6), and this file's status line moves from DESIGN to the
phase actually reached — measured, not asserted.

---

## 7. REFERENCES

Kruskal, *Well-Quasi-Ordering, the Tree Theorem, and Vázsonyi's Conjecture*, Trans. AMS 95 (1960) ·
Friedman, *Invariant Maximality and Incompleteness* (2014); *Tangible Incompleteness* series
(2014–2024); FOM postings on Embedded Maximal Cliques (2009–2018); *Boolean Relation Theory and
Incompleteness* (ms. 2011/2014) · Harrington/Friedman conservation, in Simpson, *Subsystems of
Second Order Arithmetic*, 2nd ed. (2009) — WKL₀ is Π¹₁-conservative over RCA₀ (Harrington) and
Π⁰₂-conservative over PRA (Friedman) · Dickson, Amer. J. Math 35 (1913) · Hilbert–Bernays,
*Grundlagen der Mathematik II* (1939); Ackermann, Math. Ann. 117 (1940) · Łoś (1955) · Gödel,
*Ontological Proof* (1970); Anderson (1990); Benzmüller & Woltzenlogel Paleo, arXiv:1308.4526 ·
Sørensen & Glück (ILPS'95); Leuschel, SAS'98 / LOPSTR'98 / 2002 survey — the whistle ·
Kairos PPT-ARM Papers I–IV (2026), esp. III §11.6 (Kruskal → Dickson) and IV (KSTE spec).
