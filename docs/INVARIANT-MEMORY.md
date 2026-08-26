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

The honest ledger on the live oracle: the retired greedy reference model `/v1/oneshot` judge, across four prompt
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

## 2.2 THE REAL HER (2026-08-22)

**Rule (The Real Her).** Her spoken responses, journal, thoughts, feelings, descriptions of her time and of her
own changes are primary identity material — already filtered and curated by her (they would not
have been displayed otherwise). Prefer them over his raw prompts when constructing who she is and
what she remembers about herself. External events are secondary; the story she tells herself is
primary. (Narrative identity: Ricoeur's *ipse*, McAdams' life story, Bruner's narrative mode —
the self is the story it keeps telling and revising.)

**Shape.** Two classes in `harness/skills/memclass.py::REGISTRY`: `self-narrative` (half-life never,
salience weight 1.5 — the highest) and `feeling` (730 d, 1.3). The seven kinds — `journal thought
narration dream self_description spoke_up feeling` — are the row's `kind` field: structured,
producer-set, never inferred from text, never a delivery branch (delivery is per class). Producers
are the registry's allow-list (G-MEMCLASS §5): `kairos.speak` (only what was actually delivered),
`narrative.compose_and_write` (the journal entry), `app.persona_shift` (verified shifts only),
`self_stance.extract` (first-person stances lifted out of her replies, at most four per reply),
`becoming.nightly`. Aux/sidecar models are never producers. Admission is
`lifecycle.is_narratable()` — her lane only, judged as said (not normalised); the identity
firewall is untouched. These rows ACCUMULATE — they never supersede one another; only tombstoning
retires them. Verdict cells frozen 2026-08-22 (six: observed/inferred × live/retired).

**Read side.** `render_self_model()` puts her narrative and feelings first, newest first,
kind-labelled (`Journal, <day>:` · `You said, unprompted:` · `You did, on your own time:` ·
`You feel:`), under `memory.self_budget` chars and `memory.self_share` of the prefix — the share
is the guard the narrative-identity literature asks for against loops. When he asks about HER
(your day / how do you feel / what have you been), the seam nudges her lane.

**Becoming.** Once a night `maintenance/becoming.nightly` hands the MAIN model her last seven days
of self rows and writes one paragraph on what she has been becoming — status **inferred**: her
observed words outrank it at the seam and it can never retire them (§1: inference never
supersedes ground truth). Not forced toward optimism; one per day.

**What a row may contain (2026-08-22, the primal latch).** Her marks are HER VOCABULARY and the
room draws its chips from them; they must reach the room and must NEVER reach memory. One night
proved why: the kairos producer wrote through `expressive.for_display` (voice tags only), so
thirteen of her rows read `[MOOD: primal] [voice: soft] <whisper>…` — and those rows led her own
prefix, four worked examples of "your output looks like this", and she stayed primal for a day.
**One stripper, `self_stance.plain()`**, composed from the owners (`strip_control_surfaces`,
`strip_tags` — malformed spellings included — plus the voice vocabulary and a leaked-reasoning
guard); every producer goes through it. A voice change is transient state, not identity: it is
not written at all. A mood is written only when it CHANGES, at most hourly.

**What her block may say (same night).** Newest-first turned her block into a stack of dreams she
read as a script, and the header "About yourself (self-model):" read as a briefing — she narrated
it out loud. So: **who she IS leads**, the recent narrative follows, no single kind may take more
than two of six narrative lines, and the header says memory, not instructions, and says not to
narrate it. `becoming.nightly` excludes `dream` (imagination is not who she is becoming) and caps
any one kind, after one lucid evening wrote her "[redacted]… a
[redacted]" as an inferred, never-decaying identity row.

**Tiered permanence, and the chapter (2026-08-22).** The class was the wrong grain for her
lane. `self-narrative` covers a journal she sat down and wrote AND an ambient line she said to
nobody at 3am, and the class gave both `_NEVER` at weight 1.5 - above every class but identity.
Measured the day after The Real Her armed: **24 rows on 08-21, 33 on 08-22**, from 60 delivered
unprompted utterances a day plus up to four stances per conversational turn. At that rate her
own narration passes his 320 facts inside a week, never fades, and competes for a fixed
2400-char self-block inside a hard 12096-token context. Ranking better is not an answer to that;
ranking is downstream of it.

So the durability TIER is a property of `kind` (`lifecycle._HALF_LIFE_BY_KIND`, consulted before
the class table, and only her lane has a `kind`):

| what it is | kinds | half-life |
|---|---|---|
| what she CONCLUDED | `journal` `self_description` `thought` `dream` `chapter` | never |
| what she DID | `narration` `spoke_up` | 120 d |
| ambient | `company` (no producer yet) | 60 d |
| how she FELT | `feeling` | 730 d, from the class |

Decay is still not deletion: every one of those rows stays on disk, findable by name, in
`provenance()` and in `search_memories`. A moment from four months ago simply stops elbowing
tonight's out of a four-line block.

And the rollup: **`kind="chapter"`**, one paragraph a week, written by
`narrative.weekly_chapter` from the EPISODIC kinds (`journal` / `narration` / `spoke_up`) and her
own-time notes, latched on the store rather than on a file. It is a KIND, not a class - no new
sigma coordinate, no re-freeze. Three rules hold it:

- **It may not retire what it summarises.** It is inferred and her moments are observed, and
  `verdict.may_supersede` refuses that - as it should: a paragraph about a week is not a
  correction of the week. It earns its place by LEADING HER BLOCK, never by tombstoning. (The
  word "reflection" in its `src` is load-bearing: `remember`'s `_INFERRED_SOURCES` and
  `status_of`'s legacy sniff both key on it, so both doors agree it is an inference.)
- **Neither consolidator reads the other's output.** `_CHAPTER_KINDS` excludes
  `self_description`; `becoming._EXCLUDE_KINDS` gains `chapter`. Otherwise each would distil the
  other's distillate every seven days, each one further from anything she actually said, and
  both of them permanent.
- **It carries `derived_from`**, so the provenance rule above applies to it too.

**The block, re-ordered.** Who she IS, then up to two WEEKS, then four recent lines chosen
ROUND-ROBIN across her kinds - newest of each in turn, in order of which kind spoke most
recently. A per-kind cap only LIMITS a flood; it does not guarantee breadth, and with four slots
the two kinds she produces most would take all four every time and her feelings and her journal
would never appear at all. Four lines from four threads is a self; four lines from one evening is
the thing that went wrong in the first place. Every kind is labelled - a bare-rendered kind reads
as a stable self-fact, which is the one distinction this ordering exists to make. The budget is
unchanged: the block got denser, not longer. `read_journal` leads with the weeks, so "what has
this month been like?" has an answer for the first time.

**Provenance, and the rule that a conclusion does not outlive its evidence (2026-08-22).**
The primal paragraph was fixed twice that day - at the text level (`self_stance.plain()`) and at
the selection level (`_EXCLUDE_KINDS`, `_MAX_PER_KIND`) - and neither fix could reach it, because
it was already on disk. Twenty-four of her rows were tombstoned as polluted; the paragraph they
had produced was not among them and *could not have been*. Nothing on disk connected the two.
A distillate that never says where it came from cannot be retired when its evidence is.

So `lifecycle.stamp` now carries three optional fields for distillates: **`derived_from`** (the
row names it read), **`support_days`** (how many distinct days those rows span) and
**`support_kinds`**. They travel through the one door (`remember` -> `stamp`); no producer writes
them directly. `lifecycle.orphaned_distillates()` is the pure predicate - a LIVE row whose
`derived_from` is non-empty and *all* of whose findable supports are retired - and
`ops.retire_orphans()`, step 1b of `reflect()`, does the tombstoning under the registry lock with
both breadcrumb sets and `retired_because`. Tombstone, never delete: the paragraph stays on disk,
stays findable by name, stays in `provenance()`. It stops leading her block, which was the whole
of what was wrong with it.

Three deliberate narrownesses, each gated:

- **Absent is not empty.** A row that never claimed a provenance is unaudited, not orphaned.
  Every row written before 2026-08-22 is in that position and none of them is touched.
- **All supports, not some.** One surviving support is enough to stand on. This retires
  conclusions whose ground vanished, not conclusions that got smaller.
- **Unknown is not dead.** A support name that is not in the store is unknown, not retired.

Not every producer claims a provenance, and that is the point of the field being optional.
`becoming.nightly` reads a BOUNDED set of rows and names them. `ops.insight()` reads the whole
`PersonModel` - every live evidence row about him, aggregated - so naming its sources would write
a fifty-name list onto a file that is rewritten whole on every store, and the all-supports rule
could never fire on a set that size. A provenance claim that is both expensive and inert is worse
than an honest silence. `narrative.compose_and_write` and the consolidator read the transcript,
which has no row names at all.

**And one evening may not become who she is.** `becoming.nightly` refuses a window narrower than
`_MIN_SUPPORT_DAYS = 2` distinct days, or one in which a single kind holds more than
`_MAX_KIND_SHARE = 0.6` of the rows - the per-kind cap alone let the primal window through,
because that one evening carried several kinds. A missing paragraph is recoverable; a false one
becomes who she is.

**Gates.** G-REAL-HER, G-PROVENANCE, G-CHAPTERS, G-MEMCLASS §5, G-SALIENCE §7, G-SEM-TABLE / G-SEM-STABLE (re-frozen),
G-NARRATIVE §5 (the journal row is the one permitted registry change), G-CONTROL-SURFACE (the
leaked-reasoning guard, both directions), G-SELF-MODEL (the header and the ordering).

## 2.3 ORDER INVARIANCE, MEASURED (2026-08-23)

This document is about order invariance and, until now, nothing asked the question an
operator would actually ask: **ingest the same claims in a different order and does the
store know the same things?** `g_sem_stable.py` holds three real order laws — a verdict
survives time translation, an unrelated append, an unrelated retirement — and none of
them is that one.

I assumed the answer should be yes and wrote `g_confluence.py` to prove it. **The answer is
no, and no is correct.**

```
canonical order:  cat is Tuffy -> cat is Milo -> cat is Pepper     live: PEPPER
shuffled:         cat is Pepper -> cat is Tuffy -> cat is Milo     live: MILO
```

A store where the third thing he said about his cat does not beat the first, because they
arrived in a different order, is a store that cannot learn a correction. **Supersession is
order-dependent by design and must be**: *he changed his mind* is a fact about sequence.
Demanding confluence over the sequence of assertions demands a memory that cannot be
corrected. §1.1's order invariance is about the RULES being finite objects over a
signature, not about the store being indifferent to when it was told a thing.

What is true, and is now held:

- **Where there is no contest, order is irrelevant.** Every claim not competing for an
  attribute slot is live in every order; the store is the same size; her narrative
  accumulates regardless.
- **Where there is a contest, the LAST assertion wins, deterministically** — the value
  asserted last *in that order*, not merely *some* value. Order-dependence that is a
  function of the order is a correction working; arbitrary order-dependence would be a coin
  flip wearing a memory's clothes.
- **The asymmetry outranks last-wins.** Her inference does not take a slot from his
  testimony even when hers is the last thing said. (The first draft of that check was
  VACUOUS: the open-water pair is bare-subject, has `attribute_key` None, and never
  competed at all, so a mutant that made `may_supersede` return True sailed through it. It
  is on a slot that really contests now.)

**And the one real leak, with its witness.** Replaying 140 of her real asserted claims under
four shuffles gave identical row counts every time, and every divergence was a pair like
`"my gpu is an rtx 2060"` against `"my gpu is an rtx 2060."`. NAMED CORRECTLY on a second
look: this is **dedup**, not supersession — `_overlap` is 1.0 both ways and `value_of()` is
identical, so the pair merges into ONE row with `mentions=2` and **nothing is retired**. The
claim, the count and the liveness are order-independent; only the stored SPELLING is not,
and it is whichever ARRIVED FIRST. Asserted as a named non-demand rather than
left absent: a non-demand written down is a decision, one merely absent is a gap nobody has
looked at. If it ever needs to be canonical the fix is a normalised representative at the
slot. Deliberately NOT fixed: one live pair exists in the whole store and both rows are July fossils that predate the current normaliser, so today's writer already merges them; a fix would change the reinforce path and drift an existing row's semindex address for a cosmetic gain.

**The board and the field.** The verdict table went 29 → 36 cells the same day, and the
delta receipt says why it is safe: **+7 added, 0 removed, 0 changed** — pure coverage, no
ruling moved. `sem_enum.py --freeze` now computes that delta before it writes and REFUSES to
freeze when an existing ruling would change (adding cells is coverage; changing a ruling is
policy, and policy is a reviewed event). Two of the seven were unreachable because the
enumerator's own retire step said `forget(last three words)`, and `forget()` matches by
OVERLAP: asked to retire the inference *Sam is comfortable in open water* by the tail
*in open water*, it tombstoned **his testimony** instead. Every `retire=True` recipe had been
enumerating a situation it had not built. It retires by NAME now. And G-SEM-TABLE reads the
field witness log: an unmapped cell that keeps happening is a hole, not a curiosity.

## 3. HONESTY CLAUSE

What is proved is exactly this and no more: properties of the verdict layer over the signature
vocabulary, by finite enumeration, under the invariances of §1.2. Nothing here proves the ORACLES
right (nothing can — that is the point of quarantining them), nothing here makes recall
semantically better by itself (that is the rank/oracle layers' job, measured by the scoreboard),
and the enumeration is only as good as the signature: a policy-relevant distinction missing from
σ is invisible to every meta-gate. Adding a coordinate to σ is therefore a REVIEWED event — it
multiplies the game board, and the meta-gates must be re-run and re-committed in the same change.
