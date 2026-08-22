---
type: ledger
title: "OFF-BY-DEFAULT — what is built, gated, and not running, and what would arm it"
date: 2026-07-30
status: LIVE DOCUMENT — every knob that ships off gets a row here, in the same commit that adds it
---

# docs/OFF-BY-DEFAULT.md

AGENTS.md §0 names this repo's signature bug: an invariant enforced in one of two paths is
enforced in neither. It has a quieter sibling, and the 2026-07-30 audit found **five** instances
of it at once — `invariance.py`, `narrative.py`, `task_loop.py`, `person.silences()`, and the
sandboxed `coding.*` tools were all **fully built, fully gated, and wired to nothing**. Green
suites, months of them, over code no live path could reach.

The cure for that is not "turn everything on". Several of the things below are off for good
reasons, and one of them is off because the measurement said so. The cure is that **being off
must be a recorded decision with an expiry condition, not a state something drifts into**.

So: every knob that ships off gets a row here, and every row names the specific evidence that
would arm it. A row whose "what would arm it" is vague is a row that will never be revisited —
if you cannot say what would change your mind, you have not made a decision, you have deferred
one.

`harness_tests/g_offledger.py` holds this file to the code in **both directions**: every
default-off knob in `serve.py` has a row here, and every row here names a knob that exists and a
gate file that exists. Neither can drift without a red gate.

---

## ARMED — what came out of the dark, when, and what to watch

Kept here rather than deleted. A ledger that only ever grows is a list of excuses; the useful
thing is the record of what graduated, so the *next* arming decision has precedent. These rows
are no longer "off", so they are deliberately not §-headed with their knob name — `G-OFFLEDGER`
asserts that no ledger section describes a knob that is actually ON, and it caught exactly that
the moment these three flipped.

**Armed 2026-07-30, operator's call, live profile `companion`:**

| Knob | What it does now | Watch for |
|---|---|---|
| `task_bridge` + `agency_tasks` | A `category="task"` note is promoted to a real `TaskState` at the day boundary, worked, and the verdict written back to the note. Armed together on purpose: the bridge alone enqueues work nothing drains, and the drain alone drains an empty queue — which is what it did for its entire life until Phase 3, because `post_task()` had no caller anywhere in the tree. | **Ownership.** A note's `speaker` becomes the task's `owner`; `task_table.may_close` is what stops her closing what he asked for, and an unknown speaker defaults to `operator` (less authority for her, never more). Also watch that the first promotion is something he actually wanted promoted — the board is now load-bearing, so a casual note can become work. |
| `delegate` (+ `SP_DELEGATE_WORKTREES`) | `delegate_code()` hands a goal to the Grok CLI in a worktree **this code creates**, runs the portable gate set inside it, and reports. She never merges. The diff verdict refuses anything outside `harness/ harness_tests/ docs/ profiles/ gates/ fixtures/`; the engine is read-only. Ran live end to end once before arming: worktree created, one docs file written, verdict CLEAN, 16 gates run, nothing merged, live tree byte-identical throughout. | (a) `--permission-mode auto` is the only headless mode that *executes* — more permissive than wanted, which is exactly why the diff verdict is the authority and not the flags. (b) `~/.grok/config.toml` sets `permission_mode = "always-approve"`; every call must keep passing `--permission-mode` explicitly. (c) `--worktree` is inert headless — if the code ever regresses to trusting that flag, isolation disappears **silently**. (d) The delegated gate set is the *portable* 16; `g_durability` and `g_onedoor` cannot run in a worktree because `var/memory/` is gitignored, so a delegated change is never checked against the live store. |

**Armed 2026-08-23, on `fixtures/sem/aux-receipt.json`:**

| Knob | What it does now | Watch for |
|---|---|---|
| `rank` + `aux_embed` + `tau_aux` (`SP_SEM_RANK` / `SP_SEM_AUX_EMBED` / `SP_SEM_TAU_AUX`) | A row may now be admitted at the recall seam by MEANING as well as by shared words: cosine >= 0.40 against its `aux-1024-v1` vector, from the CPU sidecar - the only real embedder this box has. Measured through the real seam on the same frozen 160-query corpus that set the bar: `seam_recall_at_1` 0.46 -> **0.53**, `decider_hit_rate` 0.06 -> **0.17** (what actually reaches her context), and **both** foreign-noise metrics **identical** to lexical. It was off for a month against four committed negatives - and the finding that changed it is that all four were measured against a bag-of-words index: `/v1/capture` refuses on the model MoE (ADR-013), so no `ep.l5` has been minted in three weeks and 253 of 253 recent rows carry `npos=0`. There was no semantic index to compete against. | (a) **tau is a real dial and the first answer was wrong.** A top-1-only calculation said 0.20; through the seam - which admits every row over tau - 0.20 injects an unrelated fact on 55% of foreign queries. 0.40 is the most recall for which nothing degrades. 0.35 buys 41% more true injections for one extra foreign injection in sixty. (b) **RAW cosine, never centered** - `centered_cosine` is an l5 fix and collapses this space to 0.29, worse than lexical. (c) **The query/document asymmetry**: `/v1/embed` works (~1.47 s) and `/v1/capture` does not, so the engine can embed a query and not a document; `query_embed` prefers aux while this is armed, and **if capture is ever fixed that order must be measured again**. (d) The doc side needs `semindex.backfill_aux` to have run, or the gate is live with nothing to match. |

**Armed 2026-07-30 21:00, after the thinking-off receipt:**

| Knob | What it does now | Watch for |
|---|---|---|
| `thinking` + `think_max_tokens` + `think_max_ms` | The private thought channel is back, **bounded**. It was off because it cost 258 s / 256 s / 308 s turns and because `<thought ` (space, no closing bracket) leaked her entire reasoning into the transcript as speech. The leak is fixed and pinned (G-NARRATIVE §6); the cost now has a ceiling at 128 tokens / 30 s, and the first 19 turns of the paired run came back **within ~10-15% of thinking-off** — so the ceiling holds. `persona/50-thinking.md` carries `when: thinking` and composes itself; no hand-editing either way. | **Whether it earns its cost.** The channel exists to catch confabulation before she speaks it, and the one confabulation the paired runs actually produced — *"Classic Tuffy. **He's** lucky he's cute"* about a cat recorded female, with the fact ambient in her prefix — happened with thinking BOTH off AND on. On that class, on that evidence, the channel did not help. The `26b_think` receipt is still owed: the run died on turn 20 of 20 when the stack was restarted under it (2026-07-30; still owed 2026-08-21 — thinking has run armed since without the paired measurement, so the honest status is "armed on a 19-turn receipt"). |

**Armed by PRESENCE, not by a boolean (recorded 2026-08-19):** three path-shaped knobs arm
their feature the moment the profile sets a path, so no `true` ever appears for a boolean scan
to find. `SP_SEM_INDEX` (the S0 sidecar index — gate `harness_tests/g_sem_index.py`),
`SP_SEM_SLOTS` (Phase C slot links feeding `verdict.competition()` on every recall — gate
`harness_tests/g_sem_slot.py`), and `SP_SEM_LAW_LOG` (witness lines on seam divergence) are all
SET on `companion`.

> **MEASURED 2026-08-23, and the answer is better than the correction it replaces.**
> `SP_SEM_SLOTS` is set, `var/memory/slots.jsonl` does not exist, and the scan has now
> been RUN rather than merely owed. It proposed **nothing**.
>
> - **132 gap-zone pairs** on her live store (overlap exactly 1); frame proposed **0**.
>   **110 of them (83%) stop at *no stative frame on one side*** — her testimony is
>   narrative now (*Sam stayed up all night to work on...*), and the frame test needs
>   `subject + copula + value`. The other 22 are correctly rejected as different subjects.
>   The file was never missing a run; it was missing anything to put in it. Same shape as
>   the dominance finding the same day: a mechanism built for ATTRIBUTIVE facts meeting a
>   store that is mostly prose.
> - **The oracle column is filled for the first time since 2026-07-14** (it read
>   `absent (no daemon)` for five weeks). It got **the ladders pair itself wrong** — the
>   one case this whole phase exists to close. Diagnosed: BOTH few-shot exemplars were
>   *compatible* statements, so nothing taught the judge that two statements which
>   DISAGREE are still about one subject — and by construction that is the only kind of
>   pair the gap zone contains. One competing exemplar fixed it, measured like-for-like
>   with the frame control identical across both runs: **0.5333/0.80 -> 0.6061/1.00**,
>   better on every metric.
> - **No single arm clears the pre-registered 0.80/0.80 bar.** frame gap 0.625/1.00;
>   oracle 0.6061/1.00; frame+oracle-veto gap 0.625/1.00 (the veto changes nothing in the
>   gap zone); aux cosine alone, best gap 0.75/0.90.
> - **The COMPOSITION does: `frame AND aux_cos >= 0.70` -> gap 0.8182/0.90**, all-pairs
>   0.8889/0.80. The first configuration in this repo's history to clear C2. It works
>   because frame supplies recall 1.0 and the aux space supplies the DIMENSION the
>   bag-of-words arms cannot see — every false positive is one shape: *beach/happy* vs
>   *beach/tall*, *coffee/fussy* vs *coffee/allergic*, *month/broke* vs *month/busy*.
>
> **Still not armed, for two reasons and either would be enough.** `AUX_TAU = 0.70` was
> chosen on the same 40 pairs it is scored against — that is fitting, even against a bar
> registered in advance; it needs a second corpus. And it would do NOTHING on her live
> store, because frame proposes zero there. The knob stays set so it starts working the
> moment a file appears; the receipt (`fixtures/sem/pair-receipt.json`, four arms, all
> generated by `harness_tests/sem_pair_score.py`) now says exactly why there isn't one.

**What she is told about the hands** lives in `persona.md` ("Your hands, and how far they
reach") — gitignored and operator-owned, so its substance is also recorded in
`harness/skills/delegate.py` for a fresh clone. Every hard guarantee is in code; the prompt is
responsible for exactly one thing, which is whether she describes the outcome truthfully.

---

## The ledger

*(Section numbers 2, 3 and 4 are absent on purpose — those three graduated to the ARMED table
above on 2026-07-30. The gaps are the record, and renumbering would erase it.)*

### 1. `SP_SEM_DOMINATE` — Dickson subsumption as a supersede proposer *(recorded 2026-07-30; measured again 2026-08-23 — lost worse)*

| | |
|---|---|
| **Code** | `harness/skills/dominance.py`, consulted in `memory.remember()` beside `find_superseded` |
| **Gate** | `harness_tests/g_sem_dominate.py` — 73/73 |
| **Why off** | **MEASURED AGAINST IT.** `harness_tests/fixtures/sem/dominate-receipt.json`: 84 live rows → 7 proposals, **4 good, 3 bad**. The bad three would each have tombstoned the wrong row, including "My cat Tuffy is female." proposing to retire "Sam is a cat person." |
| **What would arm it** | A supersede-labelled corpus large enough for a real precision figure — seven hand-adjudicated pairs is not one — and a rate measured on it that beats exact-slot matching without retiring testimony. **No bar was invented to sit just under the current number**, deliberately. |
| **Known failure mode** | Both remaining bad proposals are "a long row swallows a short one on a single shared content word". A minimum-content-overlap rule is the obvious next lever, but tuning it on seven examples is fitting, not fixing. |
| **Second measurement, 2026-08-23: HER OWN LANE, and the hypothesis lost badly** | The guess was that her narrative would be dominance's BEST case — near-duplicate restatement is rife there (all four *good* pairs in the 2026-07-30 receipt were restatements) and retiring one of her own repeated lines is low-stakes where retiring his testimony is not. `fixtures/sem/dominate-self-receipt.json`, on her real store: **12 proposals over 27 rows — 0.44 per row against 0.083 on his facts, and TWELVE OF TWELVE WRONG.** Not one genuine duplicate. |
| **Why it fails on prose specifically** | dominance's content carrier is `topic_of` plus names and numbers, built for ATTRIBUTIVE facts (*Sam owns a blue kettle*: a subject and an attribute). Her narrative is EXPRESSIVE PROSE with almost no attributive content — *[redacted]* reduces to roughly `{love}` — so any longer sentence containing *love* dominates it structurally. **The measured proposal is that *[redacted]* should retire *[redacted]*** The first half of the hypothesis was right; the second does not follow. Dominance cannot IDENTIFY a near-duplicate in her lane. It identifies *shares a content word and is longer* — on the material where being wrong costs the most. |
| **Now defended, not incidental** | `remember()` already handed dominance nothing from her lane, as a consequence of *narrative accumulates*. It is now a rule with its evidence beside it and a **behavioural** gate (G-SEM-DOMINATE §10): with the knob forced ON, her second *I love* line must retire nothing, and the mutant that removes the exclusion really does tombstone *[redacted]* |
| **What would change THIS verdict** | A content carrier that means something for prose, not a bigger structural signature. `aux-1024-v1` (armed 2026-08-23) is the obvious candidate: cosine over her own rows, measured against a hand-labelled set of real duplicates from her store. That set does not exist yet, and a bar invented to sit under a measurement is not a bar. |
| **Note** | The layer itself is sound and the order is proven (reflexive, antisymmetric, transitive, tri-state, settles). What is unproven is whether its proposals are *good*. Off costs nothing: `find_subsumed` returns `[]` and every verdict is byte-identical (the G-SEM-CONSERVE law). |

### 5. `SP_SILENCE_ANSWER` — what has gone quiet, at answer time

| | |
|---|---|
| **Code** | `harness/skills/silence.py`; per-turn note in `app.py`, one standing-world line |
| **Gate** | `harness_tests/g_silence_answer.py` — 32/32 |
| **Why off** | **THE EVIDENCE BASE IS TOO THIN, and this is enforced rather than trusted.** `MIN_LEDGER_DAYS = 14`; the attention ledger is **5 days** deep. With the knob forced on today the module still returns nothing and says why: *"attention ledger is 5 day(s); 14 needed before an absence can mean anything."* |
| **What would arm it** | Nine more days of `presence.jsonl`. That is the whole condition, and it arrives on its own — check `silence.why_quiet()`. Then read what it would actually say before arming, because the store still contains misattributed rows (below). **Revisited 2026-08-21: THE CONDITION HAS ARRIVED** — `presence.present_days_total()` = 17 attended days (the ledger skipped 2026-07-16 → 2026-08-19 while the presence write was armed on one of two turn paths; fixed 2026-08-19, rows resume 08-20). Not armed yet, on purpose: the row's own second step — *read what it would actually say before arming* — is still owed. Arming condition now: run `silence.what_she_would_say()` against the live store once, read it, and if it names only real silences, set `SP_SILENCE_ANSWER=1` in the profile with the receipt here. |
| **Blocker — CLEARED 2026-07-30** | Registry rows stored as `speaker=user` that were plainly hers or junk. Silence QUOTES the claim, so a misattributed row becomes *her noticing a sentence he never said*. **Curated: 7 rows tombstoned** (86 live → 79) — "I can take a look if you like ;)" and "I was silent because I was asleep" (her voice as his testimony), "I am excited." (a mood, not a fact), and four garbled or truncated captures. Nothing deleted: all went through `memory.forget()`, which tombstones. Deliberately KEPT: "the kettle is my favorite!" — plausibly a real preference of his, consistent with his other rows about small tactile rituals, and the span/cadence floors already stopped it topping the ranking. |
| **Still worth watching** | The capture path produced 3 rows from one short conversation and **2 were junk** ("I am excited.", "as much I as I want to have some fun together."). Curation is a mop; the admission filter is the leak. |
| **Already fixed here** | `person.silences()` now floors the span (two separate attended days) and the cadence (never sub-day) — a burst inside one conversation is not a rhythm. That cut five junk silences to one on the live store. |

### 6. semantic ranking at the recall seam — **ARMED 2026-08-23**

Moved to the ARMED table above. The row is kept, not deleted: it is the record of four
contenders that lost, and of the reason the fifth won, which was not that it was
cleverer.

### 6b. `SP_SEM_EXPAND` — query→keyword expansion from store co-occurrence

| | |
|---|---|
| **Code** | `harness/skills/expand.py` |
| **Gate** | scoreboard `harness_tests/sem_expand.py`; receipt `harness_tests/fixtures/sem/expand-receipt.json` |
| **Why off** | **MEASURED AND LOST**, and the shape of the loss is the useful part. At its only firing setting (`MIN_PAIR=1, k=3`) it buys **+0.04 decider hit** (0.06 → 0.10, a 67% relative gain) and spends **0.1167 of foreign precision** (0.8667 → 0.75). The ship condition is BOTH numbers, deliberately: that trade — recall up, precision down — is the same failure that killed the cosine contenders, and taking it would move the failure rather than fix it. |
| **The ceiling, and it is structural** | It can only expand words the store has **seen**, and a paraphrase is by construction made of words it has not. **240 of 280** paraphrase query words have never appeared in the registry; **66 of 100** queries contain no store word at all. At the safe setting (`MIN_PAIR=2`) it fired on **0 of 100** queries — which is *no result*, not a negative one. The 34 it can touch are exactly the ones lexical recall already handles, and its expansions there are noise: *"which dish does he enjoy most"* → *"birds chess evenings naming online visit"*. |
| **What would arm it** | Nothing about `k` or `MIN_PAIR` — no setting can expand a word the corpus has never contained. It would need a bridge built from something other than store co-occurrence (an embedding neighbourhood, a thesaurus, a model call), at which point it is a different contender and gets its own scoreboard run. |
| **Kept because** | The rig is the asset. `sem_expand.py` reproduces the committed baseline as a control before it measures anything — the first version of it swept `k`, reported four identical rows as four measured losses, and expansion had not fired once. **An unchanged number is not a negative result; it is no result.** |
| **AND it is currently WIRED TO NOTHING (2026-08-19)** | `expand.py` has no importer outside the scoreboard: the knob is mapped in `serve.py` and shown on the operator panel, but flipping it moves no live machinery. This row's own preamble calls "wired to nothing" the bug class this ledger exists to close — so it is written here, in the row, rather than left for the next audit. Wiring it into the seam is part of any future contender run, not a knob flip. |

### 7. `SP_MCP_REFRESH`, `SP_TOOL_MASK` — tool-surface knobs *(recorded 2026-07-30; no measurement pending as of 2026-08-21)*

| | |
|---|---|
| **Code** | `harness/agent.py` (tool assembly), `harness/mcp_server/bridge.py` |
| **Gate** | `harness_tests/g_toolsafety.py` — 14/14 (what the assembled set resolves to) |
| **Why off** | **CAPABILITY**, and the smaller kind: both were unreachable until mapped on 2026-07-30, and off preserves today's behaviour exactly. Neither has a pending measurement — they are overrides waiting for a reason, not features waiting for evidence. |
| **What would arm it** | `SP_MCP_REFRESH`: an MCP server whose tool list changes while the stack is up. `SP_TOOL_MASK`: a measured case where the live tool count hurts selection — `g_notes_tools` is the instrument that would show it, since agent.py:220 already warns the set is past where a small model picks reliably. |

### 8. Engine-side — off, and out of scope for the memory work

| Knob | Why off | What would arm it |
|---|---|---|
| `SP_EAGLE_ACCEPT`, `SP_SPECTEST` | **MEASURED AGAINST.** MTP/speculative decode: 36.1% single-token acceptance, 0.576 mean accept length at k=4 — net *slower* at every k (0.44×–0.92×), because MoE verify cost dominates. A committed negative, not a pending experiment. | A draft head that changes the arithmetic — acceptance well above 60%, or a verify path that does not pay full expert traffic per candidate. Not a knob flip. Recorded in `profiles/companion.toml`. |
| `SP_MOE_TRACE` | **CAPABILITY** (a diagnostic tap). It logs per-token expert routing; on in normal operation it is noise. | Hunting an expert-routing question, for the duration of the hunt. |
| `SP_G4_KV_AUTOFIT` | **MEASURED**: superseded on this profile by explicit KV sizing. `pmax` 12096 is a hard sm_75 shared-memory ceiling (`pmax × 4 B` static shared, 49,152 B available), not a tuning choice, and the ~3.5 GB of slack is deliberately reserved for WDDM. Note this one defaults **ON** in `build_env` and is turned off by the live profile. | A decode attention kernel that pages the score array, which is what raising `pmax` actually requires. |
| `SP_KV_PREFILL_BATCH_SUFFIX` | **ARMED 2026-08-20 05:45, condition met the same night it was built.** Upgrades the CONT arm from full re-batch to SUFFIX-ONLY batch: `gemma4_kv_prefill_batched_from` ropes/attends/sinks the n new tokens at absolute positions `[P, P+n)` against the live prefix (globals extend the linear cache in place; SWA-under-ring attends a gathered `[prefix-tail \| suffix]` comb because sinking would overwrite slots the batch still needs), then the same continuation-safe snapshot round-trip. RECEIPTS — kvdiff `mode=suffix` (n=1200): control byte-identical, `live_k_first_bad_pos == split` EXACTLY (prefix untouched at the byte level), differing values 10.6% ≈ the suffix fraction, divergence at or below the proven-coherent cold-batch baseline. LIVE (20:00Z): two `mode=suffix-batch` firings at prefix 6687 — suffix 1499 in 31.6 s and suffix 4346 in 92.1 s (21 ms/suffix-tok blended), the 1499 turn read by eye: coherent, in voice. Same shape cost 96 s full-rebatch the night before. | (Now ON on companion.) Disarm only with a degenerate `mode=suffix-batch` turn's receipt — CONT then falls back to full-rebatch. WIDENED 2026-08-20 06:46, arming condition met the same hour: five decomposed timing lines showed the snap dance is 248–315 ms flat (NOT the blend's bogeyman) and the batch forward runs ~19 ms/tok + ~2 s setup — so the trigger dropped from `full_rebatch_min_suffix` (~1,300 at a 6.7k prefix) to the 64-token alloc floor (`suffix_batch_min_suffix`, break-even n≈38). Measured live at the common shape: 111-tok suffix 4.4 s (was ~10), 291-tok 7.6 s (was ~24). A declined suffix batch below the full-rebatch break-even falls straight to per-token — a fallback that costs more than what it replaces is not a fallback. |
| `SP_KV_PREFILL_BATCH_CONT` | **RE-ARMED 2026-08-20 — the arming condition was met, and the row's history is the lesson.** The 2026-08-03 02:40 word salad (suffixes of 5309) happened BEFORE that same day's 16:0x fix that made the snapshot capture mint the prefix with the same kernel as the suffixes — the salad's cache was float-prefix/int8-suffix mixed, and the arm was never retried after the cure. Condition met in full: kvdiff sweeps on `/v1/debug/kvdiff_batch` (pos0 bit-stable across n=1..128; the n-growing deep-layer divergence is GEMV-int8/GEMM-float regime chaos, self-consistent, same as the proven-coherent cold batch), plus a live warm turn — `warm_suffix=1396, prefix=6518, 12.1 ms/tok` — read by eye: coherent, in voice. Receipt in `profiles/companion.toml`. Gate: `g_kvdiff_batch.py`, `g_batch_cont_guard.py`. | (Now ON on companion.) Disarm again only with a degenerate BATCH-PREFILL-CONT turn's receipt in hand — not on vibes. |

### 9. Harness-side — dark on the live profile, surfaced by the widened G-OFFLEDGER derivation (2026-08-19)

The gate's old regex matched exactly one spelling of "boolean knob" and was blind to 26 of 54 —
including `SP_RESEARCH`, the knob whose off state is the whole G-LOOKING incident (she narrated
research she had not done because the tool was dark and nothing said so). The derivation now
walks `build_env`'s AST, and these eight surfaced on the first run. Every one was off for a
reason; none of the reasons were written down.

| Knob | Why off | What would arm it |
|---|---|---|
| `SP_RESEARCH` | **CAPABILITY, deliberately held.** Grok/xAI research tier: costs minutes per call and reaches off the machine. The honesty rule ships with it (`persona/37-thinking-tiers.md`, same knob). Gate: `harness_tests/g_research.py`. | Flip `research.enabled` when the operator wants her reaching the web; watch the first receipts in `var/research` against what she claims (`harness_tests/g_looking.py` holds the claim-hold). |
| `SP_GAMES` | **CAPABILITY, parked by the operator.** The board tools re-register from the registry on next serve; `harness_tests/g_games.py` proves the rules with perft independently. The profile's own ARMING CONDITION: "flip to true. That is genuinely all." | When he wants to play something, or the board becomes a thing in the room rather than eight names in a list. |
| `SP_AMBIENT` | **RE-ARMED 2026-08-21 (his order), with the quiet guard.** Off 2026-08-03 → 2026-08-21 as a CUDA-fault suspect (a capture landed at the tail of a lockup). Re-armed not silently: the co-suspect resident TTS server had retired to the xAI API (zero VRAM), and a due capture now WAITS for `ambient_quiet_s` of no activity — his turns, her kairos/solo work, the daemon — before the shutter opens (`harness/senses/ambient.py::_activity`), so it can never again fire into a busy GPU. Still vetoable live via `senses.ambient`. Gate: `harness_tests/g_senses.py` (§quiet guard). | **THE WATCH IS STILL OWED**: if CUDA faults resume with the timer on, back to `false` — and the fault is then the vision forward's, not the schedule's, which is the experiment's other arm answered. |
| `SP_AMBIENT_ON_BOOT` | **DELIBERATE, not deferred** (2026-08-21, his call: "if we leave it as is it will just become a possible issue down the road"). After a start/bounce the kairos activity state is empty, so the quiet guard's recency signal cannot testify and an overdue capture would fire open — one did, 11 minutes into a boot. Off means boot counts as activity: the first capture waits a full quiet window from process start. Same shape as the kairos act-first-at-bounce knobs, defaulted the same way. Live toggle `senses.ambient_on_boot`. Gate: `harness_tests/g_senses.py` (§boot counts as activity, mutant-killed). | Flip it if he decides a photo of the room right after boot is a feature ("she looks around when she wakes") rather than a leak past the guard. Nothing else is waiting on it. |
| `SP_POUW_MINING` | **MEASURED AGAINST.** Mining was an unconditional `tokio::spawn` — ~1.03 synthetic receipts/second for 773 minutes into an unbounded Vec nothing read. | The mesh/DHT work actually needing receipts, with a reader and a bound. |
| `SP_BACKUP_EPISODES` | **MEASURED — disk arithmetic.** `var/memory/eps` is 1.2 GB of KV snapshots; hourly copies would fill the disk in a day. The registry that references them IS backed up — a restore loses replay fidelity, not the record. Gate: `harness_tests/g_backup.py`. | Episode storage becoming incremental/deduplicated, or a backup target that is not the same disk. |
| `SP_SPINE_TOOLSET` | **MEASURED AGAINST (live-play 4).** The per-turn toolset swap rewrites the system prompt, diverging the persist-KV cache at token 0 — a full re-prefill of the conversation; building/code messages stalled for minutes. Coding tools live in the load-on-demand index tier instead. | A toolset swap that does not touch the system prompt (e.g. tool-tier selection below the prompt seam), measured against the persist-KV hit rate. |
| `SP_MEM_STORE` | **CAPABILITY, retired — the daemon's `store_verb` write path.** One of the two daemon writers G-ONEWRITER exists for: registry writes with `speaker` hardcoded, no status, no admission, no firewall, and zero model inference. `serve.py` refuses to boot any profile arming it while `agent.authority = "spine"`. Gate: `harness_tests/g_onewriter.py` — 35/35. | Only a deliberate move of memory authority back to the daemon (`authority != "spine"`), which is an architecture decision, not a knob flip. |
| `SP_B4_NIGHTSHIFT` | **CAPABILITY, retired — the daemon's `growth` write path.** The other daemon writer; same refusal in `serve.py`, same gate. The 2026-07-12 "one memory authority" fix turned this one off and missed `store_verb` — the pair is why the refusal walks *both* flags on *every* profile. | Same condition as `SP_MEM_STORE`, and never separately from it. |
| `SP_VOICE_EAR` | **CAPABILITY — a fallback selector.** Forces the legacy CTC "ear" over the native encoder-free audio path (`voice/service.py` prefers native — raw audio into the model's own `embed_audio` projection — when available; the CTC ear was a transcription substitute). Mapped through the door 2026-08-19; before that it was a getenv no served stack could reach. | Debugging the native audio path, for the duration of the hunt. |
| `SP_MCP_UNSANDBOXED` | **CAPABILITY, held by design (2026-08-19, operator's call: sandboxed-first).** The FastMCP server used to register the UNSANDBOXED read/write/list and run_shell/run_powershell/run_python under bare names — the exposure agent.all_tools() deliberately shadows. Default surface is now the workspace-rooted file tools + web + clock; this knob arms the executors. Gate: `harness_tests/h_mcp_server.py` (asserts both surfaces). | An external MCP client that genuinely needs shell/python on this machine, armed knowingly for that client — never as a convenience default. |
| `SP_VOICE_SOFT` | **MEASURED AGAINST (KAI-4 P1).** Restores the softmax(τ=0.2) blend of embed rows in the ear; at V=217 the blend is too blurry for the model to read, so the default hard-selects the argmax embed row — the exact row it was trained on (`voice/ear.py`). | Evidence the soft blend reads better at some future V — a paired voice run, not a hunch. |

### 10. Disconnected surface, on the record (2026-08-19 audit)

Not knobs — code with no live caller, written down so "wired to nothing" stays a recorded
state rather than a rediscovery. (The preamble's five 2026-07-30 instances got knobs or
rows; these did not.)

| Surface | State | What would arm it |
|---|---|---|
| `harness/skills/invariance.py` | Tier-3 mathematics (FIN/USE admissibility), consumed only by `harness_tests/g_sem_admissible.py` — 21/21, proven, unreachable from any live path. | The SEM invariance family reaching the phase that demands admissibility checks at runtime (docs/INVARIANT-ROADMAP.md); until then it is a proven library waiting for its consumer, and the gate keeps it true. |
| Seven daemon routes: `/v1/chat/stream`, `/v1/dialogue`, `/v1/dsp/echo`, `/v1/dsp/model_info`, `/v1/mesh/peers`, `/v1/receipts`, `/v1/debug/kdiff` | Registered in `routes.rs`, zero callers across harness/ui/tools/serve.py. Same shape as the retired PoUW spawn — live Rust surface with no consumer. | Each names its future consumer (mesh/DHT work, the DSP lane, dialogue runner). Removal is a Rust-side decision with its own commit; a route must not just fall out of the table silently. |
| `spine.recall_decider` vs `memclass.py` | The declared class→delivery registry is consumed by self_model/okf_mem/serve — and NOT by the live recall decider, which branches inline (registered at the decider itself). | A paired live run measuring the declared deliveries (`self-fact`→recite, `same-template`→systemecho) against today's plain-note behaviour. |

---

### 11. The aux sidecars (`SP_AUX*`) — LFM2.5, off in build_env, armed on companion (2026-08-20)

The full design, boundaries and roadmap live in **docs/AUX-MODELS.md**; this row keeps
the ledger's own invariant: default-off in `build_env`, on only where a profile says so.

| Knob family | Why off by default | What would arm it (and what did) |
|---|---|---|
| `SP_AUX` (+ `SP_AUX_EMBED_URL/CHAT_URL/CHAT_MODEL/API_KEY_FILE/INDEX_DIR/ARCHIVE_GLOBS`) | **CAPABILITY.** CPU sidecar models (deep recall over every transcript, web page-reading, yes/no judging). Dark sidecars are contractually invisible: every caller keeps byte-identical pre-aux behavior (H-AUX §1 proves the dark contract; §4 proves aux can never write memory). The API token travels as a FILE path because this repo is public. | `aux.enabled` in the profile. Armed on companion 2026-08-20 with the embed sidecar autostarted from LM Studio's own backend pack, CPU-pinned — the 2060 stays 100% Gemma's (ADR-KAI6). Gate: `harness_tests/h_aux.py`, 36/36 offline. |
| `SP_KAIROS_JUDGE` (+ `SP_KAIROS_JUDGE_ACTIONS`) | **CAPABILITY, and a deliberate policy change: the sidecar may veto her unprompted turns.** worth_saying()/solo_did_the_thing() rule AFTER generation, so every dropped impulse cost 60–110 s of 26B prefill — measured 2026-08-20 morning: a turn every 60–90 s, GPU pinned 99%/84 °C, much of it heat that bought silence. The pre-judge moves "worth a turn?" to the CPU 1.2B BEFORE any GPU work. Boundaries (H-AUX §6): fail-OPEN on any failure (infra must never silence her), REMIND never gated (promises are kept, not judged), and the sidecar never sees or shapes what she says. | `aux.kairos_judge` in the profile. Armed on companion 2026-08-20 09:xx on the operator's explicit call ("arm it, A/B it today"). A/B reads from `[kairos] sidecar pre-judge` lines vs TURN-PHASE cadence in var/daemon.log. Disarm: one profile line. |
| `SP_AUX_WATCH_JUDGE` | **CAPABILITY.** The watch poll's YES/NO one-shot moves to the CPU sidecar (was 6.6–78 s of GPU per poll). Safe to offload because the dangerous failure — a hallucinated YES — is caught at the DOOR: `watch.check()` re-grounds every YES against the evidence whoever judged, and a bare/ungrounded YES is refused (H-AUX §7). The 26B `_judge` remains the fallback on any sidecar failure or unrecognizable shape. | `aux.watch_judge` in the profile. Armed on companion 2026-08-20 alongside the kairos judge. |
| `SP_AUX_RERANK` (+ `SP_AUX_COLBERT_URL`) | **CAPABILITY, evidence-thin — built dark on purpose.** ColBERT late-interaction rerank over deep recall's CLS candidates (`sidecar/rerank.py`): widen to top-50, MaxSim reorders, top-k out. The contract is gate-held (H-AUX §9): any failure — knob off, dark token door, wrong response shape — returns the CLS order; rerank may reorder, never lose. Needs its own llama-server (`--pooling none`, :8812, LFM2.5-ColBERT-350M). | A measured deep_recall miss: CLS top-4 returning the wrong moment on one of his real "do you remember" queries, and this stage fixing it. Live verification of the `--pooling none` response shape is part of the same receipt. |
| `SP_AUX_CONSOLIDATE` | **CAPABILITY, dark on purpose — it writes into HER memory.** Routes the consolidator's `_chat` (summaries + fact extraction, all stamped `inferred` regardless of author) through the CPU sidecar with the model one-shot as fail-open fallback. Extraction is squarely the small model's job, but a consolidator paraphrase becomes a memory row, so the bar is higher than speed. | A side-by-side read: run one real day's consolidation both ways, compare the minted facts line by line, and arm only if the sidecar's are as faithful. The comparison is cheap now — `SP_AUX_CONSOLIDATE=1 python -m harness.skills.conversation_memory` on a copy vs the night job's output. |

### 12. The engine seam — `SP_ENGINE_KIND=openai` and its knobs (2026-08-21, the Kairos plan Phase 3)

| Knob | Why off / state | What would arm it |
|---|---|---|
| `SP_ENGINE_KIND` (`[engine].kind`) | **`sp` on every existing profile — the Rust sp-daemon, unchanged.** `openai` is what `profiles/companion.toml` sets: the harness talks to any `/v1/chat/completions` server (LM Studio, llama-server, vLLM, a cloud) through `harness/inference/backends/openai.py`, and every seam that needs a daemon-only capability checks `client.supports` and degrades with a stated loss. Gate: `harness_tests/g_backend_seam.py` (the real client against an in-process fake). | It is not "off" — it is a choice per profile. Hers stays `sp`; the public Kairos framework ships `openai` as its default. |
| `SP_ENGINE_VISION` (`[engine].vision`) | **OFF by default.** Under the openai backend, sight sends the picture as a standard `image_url` content part instead of residual frames — only if the endpoint is multimodal. | Set it on a profile whose endpoint accepts image parts (LM Studio with a vision GGUF, vLLM with a VLM); `sight._describe` then routes through `get_client().chat`. |
| `SP_ENGINE_MARGIN_APPROX` (`[engine].margin_approx`) | **OFF by default — an approximation, said so.** Without the daemon's `eot_margin` the kairos CONTINUE/EXPAND impulses are dark (REMIND / SOLO / MUSE / CHECK_IN live). On, a `finish_reason == "length"` reads as "cut off" (margin 0.0) — crude, no magnitude, the calibrated thresholds do not apply. | A measured look at how often a length-stop on the chosen endpoint is a real mid-thought cut; until then the honest default is dark. |
| voice-in under `openai` | **OFF structurally.** The ear produces residual audio frames and a foreign endpoint has no door for them; `voice/service.py` says so as a reply instead of crashing. | `[engine].asr_url` → `/v1/audio/transcriptions` then a text turn — reserved, not built. |

### 13. `presence.mode` — Narration / Company / Lucid Dream *(recorded 2026-08-22)*

| | |
|---|---|
| **Code** | `harness/kairos/impulse.py` (`MODE_TURN`, below REMIND/SOLO, above CHECK_IN), `harness/kairos/presence.py` (the three registers, the cue, the whisper/soft wrap, the question trim), `harness/skills/library.py` (the shelf: `var/library/`, bookmarks as positions), the presence window (`ui/src/apps/Presence.jsx`) |
| **Off means** | she speaks only as kairos allows — no mode turn, no reading aloud; the shelf tools still exist (`presence.read_tools`) |
| **Arming condition** | his — the presence window's **narrate now / keep me company / dream now** buttons (or Settings → "Presence — her modes" → Mode), or simply asking her (`enter_mode` / `leave_mode` are her tools): an asked-for mode starts STRAIGHT AWAY — ahead of the idle floor and quiet-after-him — and then keeps its cadence; `company` is the softest first step; drop a `.txt` / `.md` / `.epub` into `var/library/` and hand it to her (or she picks it up herself) for reading |
| **Guards that stay on** | the presence clock (A), quiet-after-him, its own hourly cap (12), `user_turn_active`, shutdown, `worth_saying` judged against her LAST MODE TURN (a dream repeated word for word is dropped); a mode never asks a question (trimmed at the seam) and never ends mid-line (`presence.finish` cuts back to the last full sentence) |
| **Ambient is not conversation** (2026-08-22) | a mode turn does NOT count as the room being busy: it bounds the cooldown (nothing speaks on top of anything) but is excluded from the presence clock the OTHER actions measure. Measured before the fix: two hours with lucid armed at 240 s = 29 mode turns, **zero** speak-ups and **zero** of her own time. After: her own time and her speak-ups keep their own cadence alongside it |
| **On a bounce** | an armed mode starts before he has spoken — the tick seeds a conversation from the day (forced; `kairos.seed_on_boot` is about her speaking first on her own) — but only once the prefix is HOT (`set_warm_ok`): she never starts a mode into a cold prefill |
| **Per mode** | cadence `presence.every_<mode>_s` (240 / 600 / 300), length `presence.len_<mode>` (320 / 90 / 700 tokens); each turn rotates a BEAT (`presence.BEATS`), names what she said last time so she does not repeat it, and carries a fresh sampler seed |
| **Watch for** | the hourly count; a mode turn landing inside his turn (it must not — G-PRESENCE-MODES §1/§5); `presence.voice` off = bubble only |
| **Gate** | `python harness_tests/g_presence_modes.py` |

### 14. `aux.auto_recall` — the candidate lane (parallel deep recall) *(recorded 2026-08-22)*

| | |
|---|---|
| **Code** | `harness/server/app.py` `_start_lane` / `_lane_lines` (the pre-turn spine block), `harness/sidecar/archive.py::search_async` |
| **Off means** | her `deep_recall` TOOL still works when she reaches for it; nothing searches the archive on its own |
| **Arming condition** | the H-AUX-RECALL receipt (`harness_tests/h_aux_recall.py`, `gates/AUX-RECALL-<date>.md`) shows the lane finds moments the spine misses on a set of her real "do you remember" questions; then flip `aux.auto_recall` in the librarians window |
| **Guards that stay on** | QONLY (only turns that ask), early exit at `aux.early_exit_hits` spine facts, a bounded 1.5 s join, a 0.30 score floor, at most two labelled moments, never a write |
| **Gate** | `python harness_tests/g_aux_librarian.py` §6 |

### 15. `sight.backend` — which eyes she uses *(recorded 2026-08-22; a CHOICE, not an off switch)*

| | |
|---|---|
| **Code** | `harness/skills/sight.py` (`_describe` routes, `_scrub` shared, `sight_tools` arms), `harness/skills/sight_vl.py` (the aux chat door with an `image_url` part), the senses window's "eyes" row and chip |
| **Default** | `engine` — today's behaviour byte-identical: the served model's frames into the engine, or the seam's `image_url` on a foreign endpoint, else "not available" |
| **The other choices** | `aux_vl` — an LFM2.5-VL GGUF served by LM Studio (`sight.vl_model`); keeps the GPU the model's, costs one CPU/GPU VL call per look; needs the door up and a model chosen (the chip says `eyes: dark` otherwise). `openai` — the seam's `image_url` regardless |
| **Why engine stays default** | the model's own vision tower is the one that knows her room; the VL door is the cheaper eye for the hourly look when the GPU is busy — his call, measured look by look |
| **Gate** | `python harness_tests/g_sight_backends.py` |

## DARK CODE — named, and given a deadline rather than a shrug

`harness/skills/invariance.py` — 170 lines implementing Friedman FIN/USE §3.6.6 and
FIN/USE* locality. **Nothing on a live path imports it.** Its only importers are its own gate
(`g_sem_admissible.py`) and `sem_transforms.py`. It was named in the 2026-07-30 dark-code
audit, and it is still dark at the third pass (2026-08-23).

This is not an off-by-default knob — there is no knob. It is a module that describes the
theory the rest of the SEM stack is built on and is consulted by none of it. Recorded here
rather than silently kept, because that is the difference between a decision and a drawer.

**The decision, dated:** it gets ONE use or it goes. The use it should have is the
admissibility check on the frozen verdict table — `sem_enum.py` now computes a delta
before every freeze and refuses one that changes a ruling, and "is the resulting table
ADMISSIBLE in the FIN/USE sense" is exactly the question `invariance.py` exists to answer.
**Arming condition:** wire it into `sem_enum.py --freeze` beside the delta, or `git rm` it
(history keeps it, and `g_sem_admissible.py` goes with it). Deferred deliberately at the end
of the 2026-08-23 pass rather than deleted in a hurry: a gated 170-line module is not
something to remove without reading it, and reading it was not this session's work.

## What "off" must never mean

- **Not "unreachable".** Five things were unreachable on 2026-07-30 — not off, *disconnected* — and every one had a green gate. A knob that is not mapped in `serve.py::build_env` does not exist; `G-ONEDOOR` and `G-SEM-CONSERVE` §1 now make that structural.
- **Not "off because I was nervous".** Every row above says measured, capability, or evidence-thin. If a future row cannot say which, that is the signal to go and find out.
- **Not "off and therefore harmless to leave rotting".** Off code still has to keep passing its gate, and the gates above all run in the offline sweep. A feature that stops being exercised stops being real.
