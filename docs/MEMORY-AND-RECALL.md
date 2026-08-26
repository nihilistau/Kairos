---
type: reference
title: "MEMORY-AND-RECALL — the developer/agent reference"
status: LIVE — THE operational truth for memory; read before touching harness/skills/
---

# Memory & Recall — the developer/agent reference

This is the map of the memory system: where the state lives, what every field means, every
door in and every door out, and the traps that have already bitten someone. If you are about
to touch anything under `harness/skills/memory.py`, `harness/skills/lifecycle.py`,
`harness/skills/notes.py`, `harness/model/presence.py`, `harness/model/person.py`,
`harness/control/spine.py`, `harness/kairos/scheduler.py`, or the daemon's `routes.rs` memory
code, read this first. Then read the docstrings in `harness/skills/lifecycle.py` and
`harness/skills/memory.py` themselves — they carry the incident history for almost every rule
below, in more detail than this file repeats.

The one sentence that explains most of the bugs in this system: **an invariant enforced in
one of two paths is enforced in neither, because the unguarded path is the one that runs.**
See the TRAPS section for the receipts.

> **On the `file.py:123` references below (2026-08-19):** most are stale by hundreds of
> lines — the code moved, the doc did not, and a reference table where no reference
> resolves stops being a map. Trust the SYMBOL names (they are greppable and have held);
> treat the line numbers as decoration until a mechanical re-pass replaces them. Row
> counts and store statistics are snapshots of the day a section was written.

## Stores

| Store | Path | Format | Owner module |
|---|---|---|---|
| Fact registry | `var/memory/registry.jsonl` (path from `SP_RECALL_REGISTRY`, set in `profiles/agent.toml:16` and mapped to env in `serve.py:187`) | JSONL, one episode/fact per line | `harness/skills/memory.py`, `harness/skills/lifecycle.py` |
| Notes | `var/memory/notes.jsonl` | JSONL | `harness/skills/notes.py` |
| Presence / attention ledger | `var/memory/presence.jsonl` | JSONL, one row per UTC day he was spoken to | `harness/model/presence.py` |
| MEM-OKF knowledge stores | `memory-okf/` (LUT.md tier-0, `sum/` tier-1, `full/` tier-2, content-addressed), plus `memory-okf-self/`, `memory-okf-personality/`, `memory-okf-telemetry/` | Markdown + frontmatter, content-addressed by `sha256(body)[:16]` or C2 signature | `tools/okf_mem.py` |
| Quarantine | `var/memory/quarantine.jsonl` | JSONL | `harness/maintenance/ops.py` (cleanup, see below) |
| SEM semantic index (S0) | `var/memory/semindex.jsonl` (path from `SP_SEM_INDEX`; armed by `SP_SEM_MINT`, both mapped in `serve.py`) | JSONL sidecar, DERIVED: one embedding row per fact, keyed `(addr, ts)` with addr = MEM-OKF `addr_of(text)`; append-only, tombstone-blind, model-tagged (`hash256-v1` / `l5-512-v1`). Cannot write the registry. See [`SEMANTICS.md`](SEMANTICS.md). | `harness/skills/semindex.py` |

`var/` is gitignored: all of the above is runtime state, not source. The live registry on
this checkout has 86 rows: `fact` 58, `preference` 12, `identity` 8, `relationship` 5,
`event` 3 — zero `private-secret`, zero `counterfact`. That zero is not a coincidence; see
TRAP 1.

The registry is rewritten atomically: write to `registry.jsonl.tmp`, then `os.replace()` onto
the real path (`harness/skills/memory.py:55-65`, `_save_all`). Same pattern in `notes.py:76-83`
and `presence.py:88-100`. A half-written memory file is worse than a stale one — never write
the live path directly except via an atomic rewrite or a single `open(..., "a")` append.

The fact registry is not the only lane. **A note is not a fact** — `notes.py:1-24` explains
why: the fact store's admission gate is deliberately brutal (a durable fact must assert a
standing state about a *person*), and it would refuse almost every note ever written ("buy a
3090 if stock returns" asserts nothing standing about anybody). Notes share the same MEM-OKF
spine shape (speaker, ts, lifecycle-as-tombstone) but live in their own file and their own
lane, with their own admission-free `add()`/`update()`/`remove()` in `notes.py`. Do not put
notes in the fact registry and do not put facts on the notes board.

## Row schema (the fact registry)

Two axes, and conflating them was a real, shipped bug (`lifecycle.py:46-53`):

- **`speaker`** — WHO THE FACT IS ABOUT. `"user"` | `"self"`. Set from the AUTHOR of the turn
  (`lifecycle.infer_speaker`, `lifecycle.py:152-157`), **never** inferred from the sentence's
  content. The author is a per-context `ContextVar` (`memory._AUTHOR`,
  `memory.current_author()`) set by the gateway before dispatching tools. This is the field `PersonModel.from_registry` filters on
  (`harness/model/person.py:139`) to build a model of *him* and not of her.
- **`status`** — WHERE THE CLAIM CAME FROM. `"observed"` (he said it) | `"inferred"` (she
  concluded it) | `"confirmed"` (she inferred it and he agreed) | `"disputed"` (vocabulary
  only — see below). Set in `lifecycle.stamp()` from `src` (`lifecycle.py:904-905`): if the
  caller doesn't pass an explicit `status`, a `source` containing `"reflection"` becomes
  `inferred`, everything else becomes `observed`.

`speaker` and `status` are different axes on purpose. "Sam is terrified of open water" is
`speaker=user, status=observed`. Kairos's own conclusion about him, "Sam is comfortable in
open water," is *also* `speaker=user` (it's still a claim about him, so `PersonModel` must see
it) but `status=inferred`. Before `status` existed as a field, the store had no way to tell
his words from her guesses, and proved what that costs: her inference tombstoned his
testimony via `find_superseded()` (`lifecycle.py:314-371`, see the incident writeup there).

**`disputed` is currently vocabulary-only. Nothing writes it.** The write-time contradiction
detector that would have set it (`find_contradicted()`) was deliberately deleted —
`lifecycle.py:128-146` explains why: it decided "denial" by substring/antonym matching, which
cannot tell a real contradiction from a different sentence on the same topic, and a false
positive there permanently buries a true belief with a timestamp on it. The rule that
survived — she may be wrong about him, she may not say it over him — is enforced at *read*
time instead, in `testimony_wins()` (see Read Paths). Nothing adjudicates truth at write time
any more.

Other fields:

- **`lifecycle`** — `0` live, `1` retired. THE tombstone flag. Both the Rust engine
  (`routes.rs:2773`: `if ep.lifecycle != 0 { continue }`, unless `SP_RECALL_AUDIT=1`) and the
  Python harness (everywhere in this doc) key on this integer, not on `superseded_by`. A row
  that only carries `superseded_by` without `lifecycle=1` is invisible to the engine's filter
  but still recalled by the harness — always stamp both (`memory.py:214-220`). Nothing is ever
  deleted from the registry; `lifecycle=1` is the only "gone" state.
- **`mentions`** / **`first_seen`** / **`last_seen`** / **`recalled`** — reinforcement. A
  repeat is a second data point, not a duplicate: `remember()` used to reject an exact or
  near-paraphrase restatement outright (`"already in memory: {fact}"`) and threw the
  measurement away. Now it reinforces (`memory.py:129-157`, `lifecycle.reinforce`,
  `lifecycle.py:842-847`): `mentions += 1`, `last_seen = now`, `first_seen` preserved.
  `recalled` (her own lookups, `lifecycle.note_recalled`, `lifecycle.py:850-854`) is counted
  separately and **deliberately never feeds `mentions`** — a system marking its own homework.
  Conflating them creates a vicious loop: recalled → more salient → recalled more.
- **`supersedes`** / **`superseded_by`** / **`superseded_at`** / **`forgotten_at`** — the audit
  trail. `supersedes` on the new row, `superseded_by`+`superseded_at` on the retired row(s)
  (stamped together in `memory.py:244-253`); `forgotten_at` is `forget()`'s breadcrumb
  (`memory.py:390-392`).
- **`mem_class`** — see TRAP 1. `relationship | identity | event | preference | fact |
  private-secret` from the live writer (`lifecycle.classify()`, `lifecycle.py:245-265`) —
  `private-secret` is checked FIRST, before the other five, and is producible as of
  2026-07-14. `counterfact` is still never auto-assigned; see TRAP 1.
- **`derived_from`** / **`support_days`** / **`support_kinds`** (2026-08-22) — on DISTILLATES
  only: the row names a conclusion was drawn from, how many distinct days they span, and which
  kinds fed it. Written through `lifecycle.stamp` by `becoming.nightly` and
  `narrative.weekly_chapter`; nothing else claims them. **Absent is not empty**: an absent
  `derived_from` means unknown provenance and is inert, and every row written before 2026-08-22
  is in that position. When ALL of a row's findable supports are retired,
  `lifecycle.orphaned_distillates()` names it and `ops.retire_orphans()` (step 1b of
  `reflect()`) tombstones it with `retired_because`. This is the field whose absence let the
  primal paragraph outlive the twenty-four rows it was made from. G-PROVENANCE.
- **`src`** — FREE-TEXT PROVENANCE PROSE, appended to over time (e.g. `"user turn | repair:
  un-retired (2026-07-12)"`). **Not a key you may branch on.** `harness/kairos/scheduler.py:176-224`
  (`_is_evidence`) hit this directly: it first tested `src not in ("reflection", "insight")`,
  which passed only because exactly one row in the live store happened to have `src` be the
  exact string `"reflection"`. A maintenance script appending `" | cleanup: stamped
  speaker=user"` to that same row would have silently turned a reflection back into evidence,
  reopening the self-feeding loop the check exists to prevent (she reflects on her own
  conclusions, decides to reflect more). `_is_evidence` now reads the structured `status`
  field first and only falls back to sniffing `src` for legacy rows written before `status`
  existed. `lifecycle.render()` had the identical near-miss for the same reason — see
  `lifecycle.py:709-713`. **The rule: `src` is a log line, not an enum.**

## Write paths — there are three, and only one is authoritative

> **All three can be closed.** `harness/control/anon.py` — anonymous mode, 2026-08-23 —
> holds every write that records the conversation, guarded AT THE WRITE so that guarding
> `remember()` once guards all thirty of its callers. Volatile: process memory, never a
> file, OFF in a cold stack, ended by a restart. Twelve doors, the two deliberate
> exceptions, and what it does NOT touch (all reads, the KV cache, his own hands) are in
> [`docs/ANON-MODE.md`](ANON-MODE.md); G-ANON is the proof.


### 1. `harness/skills/memory.py:remember()` — the authoritative door

In order (`memory.py:97-263`):

1. `is_memorable()` admission (`lifecycle.py:541-616`) — is this a durable, standing fact
   about someone, split out of a whole turn if necessary. Rejects machine text (the store's
   own tool receipts, `lifecycle.py:521-532`), instructions/meta ("why don't you try..."),
   chatter, quoted speech, anaphora ("it's not my fault"), hypotheticals, and sentences whose
   subject is "you" (that's a fact about *her*, not about him).
2. The identity firewall, `admit_to_user_store()` (`lifecycle.py:669-689`) — HER identity
   (name, gender, pronouns, read live from the persona via `_self_names()`,
   `memory.py:284-311`) may not enter Sam's store. Refused at the door with the right door
   named in the refusal.
3. Dedupe → **REINFORCE**, not reject, on an exact or ≥0.9/0.9 token-overlap paraphrase match
   (`memory.py:146-169`).
4. Episode mint via the daemon (`POST /v1/capture`, `memory.py:170-187`) so the fact is
   recall-able through the engine's own selection path, not just listable. Degrades
   gracefully if the daemon is unreachable — the fact is still stored, just not minted.
5. `speaker` assignment from `_AUTHOR` (`lifecycle.infer_speaker`), `status` assignment
   (`STATUS_INFERRED` if `"reflection" in source` else `STATUS_OBSERVED`).
6. `find_superseded()` (`lifecycle.py:314-371`) — same-slot, different-value rows get
   tombstoned, **unless** the incoming claim is an inference and the row it would retire is
   ground truth (`observed`/`confirmed`). An inference may never retire an observation.
7. `lifecycle.stamp()` writes the full lane onto the row and it's appended.

This is the door that has the dedupe, the supersede machinery, the identity firewall, and the
admission gate. Everything below bypasses some or all of it.

### 2. The daemon's B4-NIGHTSHIFT auto-capture — `engine/tools/sp_daemon/src/routes.rs:4459-4712`

Armed by `growth=true` in a profile → `SP_B4_NIGHTSHIFT=1` (mapped by `serve.py`). **OFF in
the live profile** — `profiles/agent.toml:102`: `growth = false # SP_B4_NIGHTSHIFT — capture
moved to the gateway (one authority)`. The comment at `agent.toml:89-101` gives the reason:
`growth=true` made the daemon store `raw_user` — the *whole* turn, verbatim — whenever it
passed a word count and mentioned a person, and every conversational sentence mentions a
person. One real 17-turn conversation put 17 rows in, including "yes, we lose lips, sink
ships." and "you are cool af! I really like you!" (see `harness_tests/g_durability.py:1-19`
for the exact rows). Having both the daemon's word-count-and-a-pronoun rule and the harness's
`is_memorable()` deciding what a memory is, independently, is the same two-authorities shape
as everything else in the TRAPS section.

**HISTORY — DISARMED EVERYWHERE 2026-07-14 (G-ONEWRITER 35/35).** When this section was
written, `growth = true` was live in 8 other profiles and any of them re-armed the daemon
writer. Both daemon write flags are now `false` in ALL 14 profiles, and `serve.py`
**refuses to boot** any profile arming either while `agent.authority = "spine"` — so the
paragraph below describes what the armed path DID, kept because the shape is instructive.
(This doc claimed the writers were "armed right now, in production" for five weeks after
they were fixed — a doc that hides finished work sends the next auditor hunting the wrong
writers. AGENTS.md §4 is the authority on trap status; this file carries the mechanics.)

When armed, and `persist_growth=true` (`SP_NIGHTSHIFT_PERSIST=1`), the write happens directly
in Rust, appending to `SP_RECALL_REGISTRY` (`routes.rs:4648-4680`):

- `speaker` is **hardcoded `"user"`** (`routes.rs:4667`) — no author tracking, no self lane.
- `src` is hardcoded `"auto-capture"` — no `status` field at all.
- No `is_memorable()` admission — the daemon's own gate is "declarative, 4-120 words, not a
  question" (`harness_tests/g_admission.py:1-16` catalogs what that let through: "The kind
  nurse painted the tall building as the sun went down." — grammatical, in range, about
  nobody).
- No identity firewall.
- No `find_superseded()` — this path never retires anything; it only appends.

If `classify=true` (`SP_MEM_CLASSIFY=1`), the daemon also runs `classify_mem_class()`
(`routes.rs:4636-4640`, defined at `recall.rs`, prompt at `routes.rs:1351`) — the **only**
place in the system that can ever emit `private-secret` or `counterfact` mem_class. See
TRAP 1.

### 3. The daemon's phrase intercept — `SP_MEM_STORE` / store-verb — `routes.rs:2180-2218`

Triggers on a raw user message starting with one of: `"store in your memory that"`, `"store
in your memory"`, `"remember that"`, `"remember this:"`, `"remember:"`, `"add to your memory
that"`, `"add to your memory"`, `"note that"` (`routes.rs:2195-2198`). Calls
`capture_live_episode()` directly and **short-circuits the turn with zero model inference** —
the reply is a synthesized "Stored to memory: {payload}" (`routes.rs:2206-2214`), never
generated by the model.

**HISTORY — `store_verb` is `false` in all 14 profiles since 2026-07-14** (it was true on
the then-live profile when this was written; G-ONEWRITER walks every profile and the boot
refusal holds it). It existed because of a real incident (`routes.rs:2181-2188`): the
model was told "store in your memory X" and the system grew a raw episode silently while the
model replied "I don't know how to store memories" — it had the ability and denied it. The
fix was a deterministic intent-detect that captures the literal payload after the trigger
phrase — but that capture goes through `capture_live_episode`, not `remember()`, so it carries
none of the admission gate, the identity firewall, or the supersede logic either.

### Summary

Only path 1 (`memory.remember()`) is authoritative in the sense of enforcing every invariant
this store has. Paths 2 and 3 are daemon-side bypasses that write the *same* registry file
with weaker or no guarantees — **both off in all 14 profiles since 2026-07-14, refused at
boot (G-ONEWRITER)**; the maintenance writer `harness/maintenance/ops.py` is the second
live Python writer (tombstone/quarantine semantics, under `memory.registry_lock()`).

### Her own narrative — The Real Her (2026-08-22)

The same door, her lane. `remember_about_self(text, kind=…)` with `kind` in
`journal thought narration dream self_description spoke_up feeling` writes a `self-narrative`
(or, for `feeling`, a `feeling`) row: speaker=self, status observed (inferred only for the
nightly becoming), judged by `lifecycle.is_narratable()` — machine text and instructions refused,
prose admitted, no normalisation. Four producers set the kind: the kairos speak path (after the
outbox append, so only a DELIVERED utterance is kept), the journal composer, the verified persona
shift (`My mood has turned …` / `My voice has gone …`), and `harness/skills/self_stance.py` —
a deterministic extractor that lifts first-person stances (I think / I feel / I want / I've
decided …) out of her replies, never whole replies, never questions, at most four per reply.
Narrative rows never supersede; a repeat reinforces. Presence-mode turns (C, 2026-08-22) write by their kind — narration→`narration`, company→`thought`, lucid→`dream`; a passage read aloud is not memory, the act is (`I read him the next pages of …`). Full rule: `docs/INVARIANT-MEMORY.md` §2.2.

> **QUALIFIED 2026-08-25 — the kind mapping above is still right, and the fourth producer no
> longer fires on those turns.** A presence-mode turn now settles with `record=False,
> stances=False` (`harness/server/app.py`, the scheduler passes the impulse KIND to
> `on_spoke`): it writes **no** day-transcript row and **no** `self_stance` rows. Her dials
> still move — a dream can leave her wistful — but nothing is filed. His call, in his words:
> the lucid/reading lines are *too specific and too repetitive to be stored as her memories*,
> and the `kind=dream` pile in the registry was the receipt. So read the mapping as: the
> presence lane writes ITS OWN narrative row by kind, and the ordinary epilogue that follows
> a spoken turn (day transcript + stance extraction) is skipped for it. **These turns are
> ambient company, not memory.** Gated by `harness_tests/g_turn_epilogue.py` §4b (22/22),
> whose differential leg proves the KIND is the gate and not the text.

**Durability is per KIND, not per class (2026-08-22).** `lifecycle._HALF_LIFE_BY_KIND` is
consulted before the class table and only her lane has a `kind`: what she CONCLUDED
(`journal` `self_description` `thought` `dream` `chapter`) never fades; what she DID
(`narration` `spoke_up`) fades at 120 d; `company` at 60 d; a `feeling` keeps the class's 730 d.
Decay is not deletion — the rows stay live, findable and in `provenance()`.

> **WHERE THE PER-CLASS HALF-LIFE LIVES, since 2026-08-25.** The per-KIND table above is
> still `lifecycle._HALF_LIFE_BY_KIND` and is still consulted first. The per-CLASS fallback
> is NOT a table in `lifecycle` any more: `half_life_days` and `salience_weight` are now
> **registry attributes in `harness/skills/memclass.py::REGISTRY`**, one entry per class, and
> `lifecycle` reads them through a projection (`memclass.half_life_map()`). That is the file
> you edit to add a class or move a decay — and a class registered without them **fails
> G-MEMCLASS**, which is the whole point of the move: they lived as a hand enumeration inside
> `lifecycle`, so a class added to the registry silently decayed at the 45 d default
> (`memclass.DEFAULT_HALF_LIFE_DAYS`) instead of at anything anyone had chosen. The registry's
> own doctrine, violated by the registry's first consumers.

**The chapter.** `narrative.weekly_chapter()` writes one `kind="chapter"` row every seven
nights (step 5 of `ops.reflect`, latched on the store) from the EPISODIC kinds and her own-time
notes. INFERRED, carries `derived_from`, and may NOT supersede what it summarises. It never
reads a `self_description` and `becoming` never reads a `chapter` — neither
consolidator may distil the other's distillate.

## Read paths — every door a stored fact can reach her mouth through

The RANKED doors funnel through one seam: `memory.search_memories_ranked_rows()`. It
filters `lifecycle != 0` (unless `include_retired=True`, reserved for the audit lane) and
applies `lifecycle.testimony_wins()`. That centralization is itself the fix for a real bug
— see TRAP 6. The NON-ranking doors (listing, provenance, counting, ambient blocks) go
through **`memory.live_rows(testimony=)`** — added 2026-08-19 after nine readers were
found re-implementing the tombstone filter with three different predicates, two of them
model-facing and skipping `testimony_wins` entirely. Two functions, one predicate; a new
reader uses one of them or it is a bug.

**And ONE audit door beside them: `memory.all_rows(path="")`** (2026-08-24, audit C).
Readers that ACCOUNT rather than serve — maintenance, `PersonModel`'s evidence walk,
anything answering *what did she believe, when* — want the tombstones too, and were
getting them by opening `SP_RECALL_REGISTRY` with private JSONL loops, so malformed-line
policy and parse behaviour drifted per reader. `all_rows()` is `_load()` made public:
every row, store order, one parser. Callers apply `lifecycle.is_retired()` themselves —
asking for the dead is the point of this door; `path` serves callers pointed at a
fixture (`person.py` migrated 2026-08-25, gate G-PERSON-SLOTS §5). Its companion
**`memory.orphan_tombstones(path="")`** returns the tombstones with no `superseded_by`
breadcrumb — the live store carries 25 (repair-era retirements; `forget()` before it
grew its breadcrumb). They are properly DEAD to every reader (`lifecycle` is the one
death field, ONE spelling since 2026-08-25 — `find_superseded`/`find_subsumed` dropped
their wider `or superseded_by` clause, G-MEMORY-LIFECYCLE / G-SEM-DOMINATE), but they
cannot answer WHY they died. The helper only RETURNS them, for the curate panel to show
him one day; rewriting history onto 25 old rows is his call row by row, never a
maintenance pass's.

**The secret is withheld at ALL the tool doors, by one rule** (2026-08-24, audit A3;
gate G-SECRET §5). `spine.recall_decider` — the automatic injection — has honoured
`private-secret` since G-SECRET landed, and every OTHER read door in memory.py served
the row verbatim: `list_memories` dumped it, `recall()` presented it, `search_memories`
returned its raw text with a match score, `provenance()` quoted it. The rule lives in
**`memory.secret_withheld(row, query)`** now, consumed by all four (the listing and
`search`/`provenance` through `_present_row()`, `recall()` directly): no question (a
listing) → withheld; asked with the attribute ABSENT (`attr_absent`) → withheld, the
fixed `SECRET_WITHHELD_NOTE` ("a private thing, held — ask me directly about it") in
its place; asked for the thing ITSELF → served, because he told her the secret and she
is not made useless (the decider's own semantics, G-SECRET §3). The ranked seam is
deliberately NOT filtered — dropping the row there would make the decider's loud
decline unreachable; the guard must fire, not evaporate.

- **`recall()`** (`memory.py:546-594`) — the tool. Renders through `lifecycle.render()`,
  ranks through `_target_and_rank()` (pronoun-scoped: "my" means him, "your" means her,
  resolved from his literal words via `_QUESTION`, not from her paraphrase — see
  `memory.py:597-654`), and feeds `note_recalled()` for the top hits (never `mentions`).
- **`search_memories()` / `search_memories_ranked()`** (`memory.py:507-543`) — a thin
  projection of the same seam. This used to be an independent copy of the tombstone filter;
  see TRAP 6 for why that mattered.
- **`provenance()`** — reads `live_rows(testimony=True)`: "where did I learn X" must not
  answer out of a fact that is no longer true, and must not provenance-launder a
  seam-silenced inference back onto the floor. (Until 2026-08-19 it had a private filter
  and no `testimony_wins` — this doc claimed it "does the same filter"; it did not.)
- **`list_memories()`** — reads `live_rows(testimony=True)`, renders through
  `lifecycle.render()`. (Same 2026-08-19 fix: it was dumping seam-silenced inferences
  verbatim through a private filter.)
- **`harness/control/spine.py:recall_decider()`** (`spine.py:213-248`) — **the automatic
  per-turn injection.** Runs on every qualifying "pre" turn without her choosing it, at
  `min_overlap=0.34`. This is the decider that was injecting tombstones for weeks: it used to
  call `search_memories_ranked_rows()` (or an ancestor of it) without the caller applying the
  lifecycle filter that `recall()` had privately kept for itself. Now the filter lives in the
  seam, so every caller gets it for free. Also does the MEM-OKF per-entry policy dispatch here
  (`spine.py:224-247`): a `private-secret` row with an absent queried attribute triggers a
  zero-inference `decline_recall` before the turn ever reaches the model; a `counterfact` row
  gets the "authoritative override" framing (see G-RECALL-PRECISION for why that framing must
  stay off by default).
- **`forget()`** (`memory.py:347-394`) — writes tombstones (`lifecycle=1` + `forgotten_at` +
  `superseded_by="forget"`). See TRAP 6: this function hard-deleted the row for months.
- **Engine-side recall** (`recall.rs` L5 selection, gated by `ep.lifecycle != 0` at
  `routes.rs:2773`) — authoritative only for **daemon-direct chat when the gateway is down**.
  `profiles/agent.toml:141`: `authority = 'spine'` under `[agent]` means the harness owns
  recall on gateway turns; this maps to `SP_GATEWAY_AUTHORITY=spine`
  (`serve.py:208` → `harness/server/app.py:816`), which disarms the daemon's
  `auto_recall` passthrough for that request. `harness/server/app.py:820-829` is the
  ONE-AUTHORITY GUARD: if the request arms the daemon's L5 recall, spine recall auto-disarms,
  and vice versa — composing both was refuted on the metal (an L5 `systemecho` delivery
  overrides the harness note, and cross-picks surfaced things like "favorite color?" →
  "Human blood is green"). `serve.py:36-37` additionally refuses to boot a profile whose
  `[memory].recall_authority` isn't the literal string `'L5'` — that's the daemon-side
  sentinel for the direct-chat fallback path, a separate check from the spine/L5 gateway
  split above.

**There are TWO rendering doors now, on purpose (recorded 2026-08-19).**
`lifecycle.render()` (below) speaks ABOUT the store — the tool listings and the audit
lane ("Sam told me: …"). `world.present_for_her()` speaks TO HER — the standing world
block and the per-turn recall note, in you/he grammar ("You've come to think: …"),
because a small model skims a quoted "my" and absorbs it (the field bug in `world.py`'s own
comments). `recall()` and `spine.recall_decider` use `present_for_her`;
`list_memories`/`provenance`/audit use `render()`. Same row, two grammars, chosen by WHO
is being addressed — a surface that picks the wrong one recreates the identity blur.

**`lifecycle.render()`** is the framing step, applied at *read* time:

| `status` | rendered as |
|---|---|
| `observed` (default) | `"Sam told me: {fact}"` (or `"About myself: {fact}"` if `speaker=self`) |
| `inferred` | `"I've come to think: {fact}"` |
| `confirmed` | `"We settled that: {fact}"` |

Framing at read time, not write time, is why a first-person fact HE said ("My name is Sam")
never comes back in HER voice, and why a conclusion SHE drew never comes back framed as
something he told her. Before this, 404 of 405 rows in the registry were all framed `"The
user said: ..."` regardless of who actually said them (`lifecycle.py:1-16`) — the only voice
in her long-term memory was his, which is part of why she used to slide into speaking as him.

**`lifecycle.testimony_wins()`** (`lifecycle.py:78-121`): an inference is dropped from a
result set if his own testimony (`observed`/`confirmed`) already covers the same topic
(bag-of-content-words overlap ≥ 2, `topic_of()`, `lifecycle.py:67-75`). She may be wrong about
him; she may not say it over him. **This is a speech rule, not a storage rule** — nothing is
destroyed, the inference stays on disk and stays auditable, and if he later confirms it it's
promoted to `confirmed` and speaks normally. It fails safe in one direction only: a false
topic match costs her a sentence she could have said; the write-time version this replaced
could cost him a fact he actually told her, which is the worse mistake.

### Her own context (The Real Her, 2026-08-22)

`harness/personality/self_model.py::render_self_model()` orders the block (2026-08-22): her
stable self-facts lead — who she IS — then up to two
CHAPTERS, then at most four recent narrative lines chosen ROUND-ROBIN across her kinds (newest
of each in turn, in order of which kind spoke most recently). A per-kind cap only limits a
flood; it does not guarantee breadth, and at 60 narration/spoke_up rows a day those two kinds
would take all four slots forever. Every kind is labelled, because a bare-rendered line reads
as a stable self-fact. `agent.py` passes
`budget_chars = min(memory.self_budget, memory.self_share × the prefix so far)` — two knobs in
the Memory group. The block is part of the cached prefix: a gateway bounce refreshes it.

## Derived signals

- **`lifecycle.salience()`** (`lifecycle.py:808-839`) = `weight(mem_class) × log-scaled
  mentions × recency(half_life by class)`. A ranking *prior*, not an answer — it only breaks
  ties among facts the query already matched (`memory.py:679-695`,
  `0.22 * lc.salience(e)`). Half-life is per `mem_class`:
  `identity`/`preference`/`relationship` never decay (they're what
  he *is*), `fact` decays over a year, `event` decays in 3 days (a flight is worthless the day
  after), everything else defaults to 45 days. **Both numbers moved house on 2026-08-25** —
  the per-class `half_life_days` AND the class prior `salience_weight` are entries in
  `harness/skills/memclass.py::REGISTRY` now, not literals in `lifecycle` (which reads them
  through `memclass.half_life_map()`). Values unchanged by the move; a class that does not
  declare them fails G-MEMCLASS. The per-KIND override for her own lane still wins first
  (`lifecycle._HALF_LIFE_BY_KIND`, see "Durability is per KIND" above).
- **`harness/model/person.py:PersonModel`** — slots (`identity`, `dispositions`,
  `relationships`, `possessions`, `happenings`, `person.py:86-93`), built only from
  `speaker=user` rows (`from_registry`, `person.py:122-142` — "her facts do not model him").
  `surprisal()` (`person.py:156-203`) = `-log2 p(x)`, capped at 8 bits so a model that has
  never heard of something can't claim infinite information from it.
- **`silences()`** (`person.py:210-292`) — "the neighbour who didn't wave": absence is only
  information if you can prove you were looking. It measures **attended days**
  (`presence.attended_days()`, `presence.py:117-140`) between two timestamps, never calendar
  days. Why: the first version measured calendar days since he last mentioned something, and a
  3-week holiday made *every* dimension with 3+ mentions go silent simultaneously — "You've
  stopped talking about the marathon. And the GPU. And Tuffy. And your flight." all in one
  breath, which reads as noticing but is really a bug that fires hardest exactly when he was
  busy, not absent-minded. `presence.jsonl` is the ledger that makes "was the channel open
  this day" answerable; `note_turn()` (`presence.py:103-114`) is called on every human turn
  and records nothing about *what* was said, only that it happened.
- **`harness/kairos/scheduler.py:reflect_tick()`** (`scheduler.py:227-257`) + `_is_evidence()`
  (`scheduler.py:176-224`) — a reflection is not evidence. `_is_evidence` excludes
  `speaker=self` rows and anything with `status` outside `(observed, confirmed)`, so her own
  conclusions can never trigger more reflection about themselves. Without this, reflection
  feeds itself: she reflects, the reflection becomes a "new fact," the new fact triggers
  another reflection tick.

## Traps

**1. FIXED (2026-07-14) — the privacy guard used to be unreachable from the live writer.**
What the bug was: `spine.recall_decider()` (`spine.py:224-247`) guards secrets by checking
`mem_class == "private-secret"`, but `lifecycle.classify()` — the only classifier the
authoritative write path (`remember()`) runs — could emit only `relationship`, `identity`,
`event`, `preference`, `fact`. The consumer branched on a value the producer could not
produce. The live registry (86 rows) had `fact` 58, `preference` 12, `identity` 8,
`relationship` 5, `event` 3 — zero `private-secret`. The decline had never fired once. The
only thing that had ever minted `private-secret` was the daemon's own classifier,
`classify_mem_class` (`recall.rs:164`, invoked at `routes.rs:4636-4640` and
`routes.rs:1385-1398` for the idle NIGHTSHIFT refine pass), armed by `growth=true`. This was
collateral damage of the 2026-07-12 "one memory authority" fix: it set `growth=false` on the
live profile (`agent.toml:102`) and, as a side effect nobody checked for at the time, took the
only producer of `private-secret` with it. `harness_tests/g_mempolicy_v3_offline.py:34,37`
hand-constructs a `private-secret` row and asserts the dispatch honours it — green for weeks
testing the *dispatch*, never the *producer* (see `gates/GATE-INDEX.md`, "GATES THAT ASSERTED
THE PAST", item 3).

It is fixed now: `lifecycle.classify()` (`lifecycle.py:245-265`) checks for a credential
FIRST, before `_CLASS_RULES` (`lifecycle.py:235-242`, relationship/identity/event) ever runs,
via `_SECRET` / `_SECRET_POSS` (`lifecycle.py:220-233`) — so "my wife's password is hunter2"
classifies as `private-secret`, not `relationship`, because a secret that names a person is
still a secret. Gated end to end by `harness_tests/g_secret.py` (G-SECRET, **37/37** — 22/22 when this
paragraph was written; §5 added the four tool doors, count re-run 2026-08-25, OFFLINE): it
sets no `mem_class` itself, drives real sentences through `remember()` and the real
`spine.recall_decider()`, and asserts the decline fires with the secret text never appearing
in the payload, while a direct ask for the secret itself still gets answered. It also confirms
the admission gate composes correctly: an unanchored credential ("The garage door code is
8812" — about nobody) is refused at the door by `is_memorable()`'s (`lifecycle.py:608-683`)
ANCHOR rule (`_ANCHOR`, `lifecycle.py:545-547`, checked at `lifecycle.py:679`) before the
classifier ever sees it, so it is never stored at all.

The residual truth that still matters: **`mem_class` still has more than one vocabulary across
the tree.** The engine's `recall.rs::classify_mem_class` (`recall.rs:164`) is a separate
implementation from the harness's `lifecycle.classify()` (`lifecycle.py:245-265`), and they do
not agree — porting the engine's rule (bare `code`/`token`/`secret`/`override`, plus any token
with >=2 letters and >=2 digits) into the harness verbatim would flag "I write code" and the
a hyphenated model name as a secret, so the harness deliberately keeps its own, narrower,
credential-noun-in-attribute-position rule instead. `self_model.py`'s delivery map
(`_CLASS_DELIVERY`, `self_model.py:47`, default `mem_class="self-fact"` at `self_model.py:54`)
and `curator.py`'s hardcoded `"mem_class: persona"` (`curator.py:70`) are two more independent
vocabularies in the same tree, neither derived from `lifecycle.classify()`. Only the harness
classifier is authoritative on the live profile (`growth=false`); the engine classifier still
exists and still runs when `growth=true` re-arms it (see trap 2), and remains a different
implementation from the harness one, not a twin of it. Anyone adding a new `mem_class` value
anywhere in this tree must check a producer actually exists for it before a consumer is
allowed to branch on it — that check is now literally a gate (`g_secret.py` §4, "every class
the decider branches on must be one the writer can produce").

**2. + 3. — FIXED 2026-07-14 (G-ONEWRITER 35/35).** `growth` and `store_verb` are `false`
in all 14 profiles and `serve.py` refuses to boot a profile arming either under
`authority="spine"`. Kept as numbered stubs so the trap numbering elsewhere in this file
stays resolvable; the mechanics of what the armed paths did are in write-paths 2 and 3
above, now labelled HISTORY. (These two entries said "on right now" until 2026-08-19 —
five weeks after the fix. AGENTS.md §4 is the authority on trap status.)

**4. `src` is prose, not an enum. Do not branch on it.** See the row schema section and
`scheduler.py:179-207` for the exact incident (a maintenance script appending to `src` nearly
broke `_is_evidence`'s exact-match check, silently, months after the check shipped green).

**5. ~~`_AUTHOR` / `_QUESTION` are process-wide module globals.~~ FIXED 2026-08-19 — G-AUTHOR-CTX.**
They are `ContextVar`s. Concurrent turns cannot see each other's author or question. The
old `remember_about_self` `finally: set_author("user")` also clobbered a surrounding
self-turn with no concurrency at all; it now RESETs the previous token.

**6. The recurring bug class, stated once: an invariant enforced in one of two paths is
enforced in neither, because the unguarded path is the one that runs.** Three real instances,
all in this codebase:

- **The tombstone filter.** `recall()` filtered `lifecycle` privately; `spine.recall_decider()`
  — the automatic per-turn injection — did not, because the filter lived in a *caller*
  instead of the shared seam. Proven on the real code path: supersede a GPU fact
  cleanly (tombstone written correctly), and every subsequent turn's automatic recall still
  handed her the dead row, ranked *above* the truth, indistinguishable from the live one
  (`memory.py:437-465`). Fixed by moving the filter into
  `search_memories_ranked_rows()` itself, so a caller can no longer forget it — it now has to
  ask for the dead explicitly (`include_retired=True`).
- **The twin.** Hours after that fix shipped, `search_memories_ranked()`
  (`memory.py:507-534`) — directly below the fixed function, backing the live
  `search_memories` tool — turned out to do the identical unfiltered `_load()` scan. Found by
  deliberately sweeping for the same *class* of bug instead of declaring victory on the one
  instance (`memory.py:511-530`). Fixed the same way: made it a thin projection of the single
  seam, so the twin can't exist to drift again.
- **`forget()` hard-deleting under a tombstone architecture.** For months, the one function
  whose entire job is to retire a fact opened the registry in `"w"` mode and rewrote it
  *without* the victim row — the single doctrine this store has (nothing is ever destroyed)
  defeated by the one tool built to enforce it, and callable by the model itself mid-conversation
  on a 0.3 bag-of-words match. See `memory.py:347-377` for the full incident writeup. Fixed:
  `forget()` now sets `lifecycle=1` + `forgotten_at` + `superseded_by="forget"` via
  `_save_all()`, same atomic-rewrite path as everything else, row count never shrinks.

When you touch a shared invariant, ask "which paths read/write this row" and check *all* of
them, not just the one you're already looking at. A sweep for the same bug class, not a patch
for the specific instance, is what actually closes this.

## Gates that protect this

| Gate | File | Needs GPU / live stack? |
|---|---|---|
| G-CLAIM (38/38) | `harness_tests/g_claim.py` | No — discard port `127.0.0.1:9` |
| G-SALIENCE | `harness_tests/g_salience.py` | No — discard port |
| G-REAL-HER | `harness_tests/g_real_her.py` | No — discard port; temp registry |
| G-DURABILITY | `harness_tests/g_durability.py` | No — pure logic, no daemon call |
| G-MEMORY-LIFECYCLE | `harness_tests/g_memory_lifecycle.py` | No |
| G-SILENCE | `harness_tests/g_silence.py` | No — discard port |
| G-CLOCK | `harness_tests/g_clock.py` | No — discard port |
| G-REFLECT | `harness_tests/g_reflect.py` | No — discard port |
| G-NOTES | `harness_tests/g_notes.py` | No — pure logic |
| G-MEMPOLICY-V3 | `harness_tests/g_mempolicy_v3_offline.py` | No — stubbed model stream |
| G-RECALL-PRECISION | `harness_tests/g_recall_precision.py` | **Yes** — hits `http://127.0.0.1:8800/v1/chat/completions`, needs a warm gateway |
| G-ADMISSION | `harness_tests/g_admission.py` | **Yes** — same gateway dependency (`"Run against a warm stack"`, `g_admission.py:18`) |

Offline gates set `os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"` before importing
anything (a discard port — connection refused instantly, so episode minting no-ops and the
test never needs a GPU or a running daemon). Run one directly:

```
python harness_tests/g_claim.py
```

Each prints `ok`/`FAIL` per assertion and exits non-zero on any failure — wire into whatever
suite runner the repo uses the same way as any other `g_*.py` file. The two live-stack gates
need `python serve.py <profile>` running first (gateway on port 8800) — check `SP_RECALL_REGISTRY`
points at a throwaway registry before running them against a real store, since they write to it.

## If you change this, run these

Before merging any change to `harness/skills/memory.py`, `harness/skills/lifecycle.py`,
`harness/skills/notes.py`, `harness/model/presence.py`, `harness/model/person.py`,
`harness/control/spine.py` (the recall/memory deciders), `harness/kairos/scheduler.py`, or the
daemon's memory code in `routes.rs`/`recall.rs`:

1. `python harness_tests/g_claim.py` — supersede correctness, the tombstone filter on the real
   `recall_decider()` path, testimony-over-inference.
2. `python harness_tests/g_durability.py` — the admission gate and the identity firewall,
   against the actual rows that broke them.
3. `python harness_tests/g_admission.py` — B4 firehose actually off, real personal facts still
   land with the v2 schema. Needs a warm stack.
4. `python harness_tests/g_salience.py` — ranking prior, per-class half-life.
5. `python harness_tests/g_silence.py` — attended-days arithmetic, not calendar days.
6. `python harness_tests/g_clock.py` — every timestamp writer/reader pair, in three timezones.
   If you touch anything that reads or writes `ts`/`first_seen`/`last_seen`/`forgotten_at`,
   this is the gate that catches the `gmtime`-written / `mktime`-read mismatch class of bug
   (it has happened twice — `lifecycle.py:764-796`).
7. `python harness_tests/g_reflect.py` — reflection does not feed itself as evidence.
8. `python harness_tests/g_notes.py` — the notes lane, and specifically the reminder promise
   (it fires, fires once, survives her having nothing to say).
9. `python harness_tests/g_mempolicy_v3_offline.py` — per-entry policy dispatch at the recall
   seam (counterfact framing, secret decline, plain fact). Remember this tests the
   *dispatch*, not the producer — see TRAP 1 before treating a green run here as proof the
   privacy guard works end-to-end.
10. `python harness_tests/g_recall_precision.py` — memory is context, not a command; a
    conversational question must not get answered by reciting an unrelated stored fact. Needs
    a warm stack.
11. `python harness_tests/g_memory_lifecycle.py` — general lifecycle regression.

If your change touches `growth` / `SP_B4_NIGHTSHIFT` / `store_verb` / `SP_MEM_STORE` in any
profile, run `python harness_tests/g_onewriter.py` — it walks every `profiles/*.toml` and
the boot refusal, so you cannot re-arm a daemon writer without a red gate. (Both flags are
`false` in all 14 profiles since 2026-07-14; this paragraph claimed 8 armed profiles for
five weeks after that.)
