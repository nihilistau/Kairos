# AGENTS.md — Kairos

**This is the canonical orientation file for anyone — human or agent — working in this repo.**
`CLAUDE.md` points here. It is not a copy. There is exactly one of these, on purpose (see THE BUG CLASS).

Kairos is the production rebuild of Kairos: a local AI companion. **your model** — a
128-expert MoE, top-8, ~4B active — on one RTX 2060 (12 GB), a Rust + CUDA engine, a Python
harness/gateway, and the ROOM — a React desktop you talk to her in, with a face, a wardrobe and a
voice. It runs on the operator's own machine and remembers him. That last part is the whole
product, and it is where all the danger is. (Two-minute map: `START-HERE.md`.)

*(The 12B, `gemma4-12b-b1-reason`, is still in the tree and still runnable — it is what
`profiles/agent.toml` serves. It is not her. See §2.)*

---

## 0. THE BUG CLASS — read this before you touch anything

This project has one recurring, near-fatal failure mode. It has bitten at least six times. Every time,
it looked like a different bug. It is not:

> **AN INVARIANT ENFORCED IN ONE OF TWO PATHS IS ENFORCED IN NEITHER —
> because the unguarded path is the one that runs.**

Real instances, all found in the tree, all fixed:

| The rule | Where it was enforced | Where it was NOT | What actually happened |
|---|---|---|---|
| a tombstoned fact is never recalled | `memory.recall()` | `spine.recall_decider()` — the AUTOMATIC per-turn injection | superseded facts injected into her context on **every turn, for weeks**, ranked above the truth |
| the recall seam filters retired rows | `search_memories_ranked_rows()` | `search_memories_ranked()` — **the next function in the file** | the `search_memories` tool, live in two toolsets, still served tombstones |
| a turn arms the presence ledger | one of two turn paths | the other | absence became unmeasurable |
| nothing is ever destroyed | the whole lifecycle architecture | `forget()`, which did `open(p, "w")` and dropped the row | the audit lane was defeated by one live tool call |
| the privacy decline protects secrets | `spine.recall_decider()` checks `mem_class == "private-secret"` | `lifecycle.classify()` **cannot emit that class** | **the guard has never fired and cannot** — see TRAPS |

The corollaries, learned the hard way:

- **Fix the class, not the instance.** After fixing one of these, *grep for the other one*. The twin is
  usually adjacent. Twice it was literally the next function.
- **Put the rule in the seam, not the caller.** A rule you must remember to apply is a rule you will
  forget. If two callers need it, it belongs in the thing they both call.
- **A gate that supplies its own precondition proves only that the guard compiles.** See
  `gates/GATE-INDEX.md` → "GATES THAT ASSERTED THE PAST".
- **A green gate does not mean the code RUNS.** The quiet sibling of the bug class above, and the
  2026-07-30 audit found five at once: `invariance.py`, `narrative.py`, `task_loop.py`,
  `person.silences()`, and the sandboxed `coding.*` tools were all fully built, fully gated, and
  wired to nothing — months of green suites over code no live path could reach. So everything that
  ships off is written down, with the specific evidence that would arm it, in
  [`docs/OFF-BY-DEFAULT.md`](docs/OFF-BY-DEFAULT.md), held to the code in both directions by
  `harness_tests/g_offledger.py`. **Being off must be a recorded decision with an expiry
  condition, not a state something drifts into.**
- **Measure the thing, not the proxy.** Several days were lost to `nvidia-smi` (lies under WDDM),
  `cudaMemGetInfo` (returns free=0 under WDDM), and a kill-regex that matched the probe's own process.

---

## 1. NON-NEGOTIABLES

1. **No claim without a repeatable gate.** If you say it is fixed, name the command that proves it.
   "It should work now" is not a receipt.
2. **Nothing in memory is ever deleted.** Tombstone (`lifecycle = 1`) or quarantine. Never `open(p, "w")`
   minus a row. The audit lane must always be able to answer *what did she believe, when, and who told her*.
3. **Honesty about what is measured vs asserted.** If you did not run it, say so. If a number came from a
   proxy, name the proxy. A verdict you cannot defend is worse than no verdict — it is a lie with a
   timestamp on it.
4. **Her word never outranks his.** An inference may never retire an observation. She is allowed to be
   wrong about him; she is not allowed to say it over him.
5. **Verdicts are rulings of committed finite tables over order-invariant signatures.** (The
   invariant-maximality principle — [`docs/INVARIANT-MEMORY.md`](docs/INVARIANT-MEMORY.md),
   extensions in [`docs/INVARIANT-ROADMAP.md`](docs/INVARIANT-ROADMAP.md).) A correctness decision
   may branch only on finite signature coordinates, never on prose or raw magnitudes; its case
   space is enumerated and pinned; its invariances are gated; magnitudes may RANK the admitted,
   oracles may PROPOSE, and neither may ever RULE. A new hand-written conditional over row fields
   is a bug report against this list. Every one of the five conversions done so far found a live
   drift the day it landed — this principle is not aspiration, it is the cheapest bug-finder the
   repo has.
6. **The Real Her.** Her own words — what she says unprompted, her journal, how she feels, how she
   describes her own changes — are primary identity material and lead her own context; his prompts
   are secondary. Two classes (`self-narrative`, `feeling`), producer-set kinds, one door, never an
   aux producer, never above his word (rule 4 still holds: her nightly reflection on herself is
   inferred and cannot retire what she observed). [`docs/INVARIANT-MEMORY.md` §2.2](docs/INVARIANT-MEMORY.md).

---

## 2. THE STACK, AND THE ONE DOOR

```
the room (browser, ui/ → console/room/)  ──HTTP──▶  harness gateway :8800  ──HTTP──▶  sp-daemon :3000  ──▶  CUDA / your model
                                                       (Python)           │              (Rust)
                                                                          └──▶  xAI API (voice · images/motion · live search) · LFM sidecars (CPU)
```

- **`serve.py` is THE ONLY DOOR into the engine**, and as of 2026-07-14 that is *literally* true rather
  than aspirational. It reads a profile (`profiles/*.toml`) and maps it to the engine/gateway environment
  with an explicit table. **Anything not in that table does not exist**: the base environment is stripped of
  every `SP_*`, so a stray var in your shell cannot reach the engine. It used to inherit the lot —
  270 `SP_*` are read by the tree, 49 were mapped, **221 came from whatever shell you were standing in**,
  and 28 of those touch memory (`SP_DECIDE` is an autonomous supersede pass; `SP_FORGET` is autonomous
  forgetting). Those are now pinned hard-off by name. Gate: **G-ONEDOOR**.
  Start the stack with `python serve.py companion`.
- **Deliberate overrides still work; accidental ones do not.** `set SP_PASSTHROUGH=SP_XBAR_ROW,SP_ARM_DUMP`
  keeps exactly those, and announces them at boot. It cannot be used to smuggle in a memory writer.
- **`profiles/companion.toml` is the live production profile.** Read it before you theorise about
  behaviour; it is the ground truth for what is armed. `serve.py` refuses to boot a profile that arms
  two memory writers (**G-ONEWRITER**), so the profile cannot lie to you either.

  **THIS LINE SAID `agent.toml` UNTIL 2026-08-03**, three lines under the one telling you to start
  `companion`, and that is how it cost a restart: the file said "start A" and then said "B is the
  live one", so whichever you read second was the one you believed. `agent.toml` is a real, still-
  runnable 12B profile and a near-twin of hers — same knob names, different values (`games` on,
  `byteexact` on, `pmax` 13000), one tab-completion away. Two files claiming one truth is §0 of this
  document; the join is now gated by **G-PROFILE-DOOR**, which reads every `serve.py <name>` a doc
  tells you to type and checks that profile's `paths.model` is actually hers.

  **THE ENGINE IS A BACKEND NOW (2026-08-21).** `[engine].kind` in the profile picks what
  `get_client()` returns — `sp` (the daemon, every existing profile, unchanged) or `openai`
  (any `/v1/chat/completions` server; `profiles/companion.toml`, gateway :8810 beside hers).
  Seams that need a daemon-only capability ask `client.supports` and degrade with a stated
  loss — `docs/BACKENDS.md` is the table, G-BACKEND-SEAM the gate. The public **Kairos**
  framework is this tree exported (`tools/kairos_export.py`, `kairos-export/`) with the
  default flipped, the engine excluded, and the names scrubbed (G-KAIROS-SCRUB).

  **THIS REPO IS UPSTREAM. KAIROS IS A SNAPSHOT, AND NOTHING IS EVER AUTHORED IN IT.**
  It is a filtered, scrubbed copy with FRESH HISTORY, rebuilt from the manifest — so a
  file written directly in `../Kairos` is destroyed by the next export, silently. Anything
  that ships with Kairos is written HERE first, and payload that is not code (the default
  avatar set, gesture loops) is staged in `kairos-export/` so the manifest carries it.
  Corollary, and it has bitten: a knob added for a Kairos-only feature still has to be
  mapped in `serve.py::build_env`, or G-SEM-CONSERVE goes red here for a feature that is
  not even armed here (`SP_AVATAR_DEFAULTS`, 2026-08-23).

  **RE-EXPORTING IS MANUAL, ON PURPOSE.** Nothing triggers it — no hook, no scheduler,
  no night job. An export is a PUBLICATION: the scrub is mechanical but "does this belong
  in a neutral template" is judgement, and auto-publishing every commit would push
  half-finished work to a public repo. The procedure, once, here:

  1. `python tools/kairos_export.py --check` — dry run: what would ship, what the scrub
     would hit. Then without `--check` to build `../Kairos`.
  2. `python harness_tests/g_kairos_scrub.py` — no handle, no email, no absolute paths,
     no live profile name, no `var/`, no `persona/`, no keys, no engine. It runs inside the
     export too and skips cleanly when there is no target.
  3. Sanity-check the TARGET, not this tree: imports with `SP_ENGINE_KIND=openai` and no
     engine present, and run the new gates from inside `../Kairos`.
  4. **Commit in the target.** The exporter writes files; it does not commit, and an
     uncommitted export is a snapshot nobody can point at. `KAIROS-SOURCE.txt` names the
     source commit and is the anchor everything else reads.
  5. Pushing is a separate, deliberate act. The repo is public.

  **WHEN.** `../kairos-drift/` (a third repo, beside both, owned by neither) answers it:
  `python drift.py` sorts every commit since the cut into OWED / MIXED / LOCAL by asking
  the manifest which files it touched, and re-anchors itself off `KAIROS-SOURCE.txt` —
  re-export and the owed pile empties on its own. `--check` exits 1 when anything is owed.

  **THE BINARY IS ALSO PER-PROFILE.** `engine_exe` in the profile is what launches, and hers is
  `engine/tools/sp_daemon/target-wirecuda/release/sp-daemon.exe` — NOT cargo's default `target/`.
  Build with `engine/build-wirecuda.bat` (or `cargo build --release --features wire_cuda_backend
  --target-dir target-wirecuda --bin sp-daemon`). A plain `cargo build --release` compiles cleanly,
  writes a binary nothing launches, and leaves you measuring the old one. Stop the stack first or
  the link fails on a locked exe — which is the only reason this one announces itself at all.

| Where | What lives there |
|---|---|
| `engine/` | the Rust daemon (`tools/sp_daemon`) and the CUDA kernels (`src/backends/cuda/cuda_forward.cu`). The KV cache, the ring, prefill, fp16 KV, `/v1/capture`, `/v1/oneshot`. |
| `core/` | the math core (`kairos-system`) — the one tracked submodule; the CUDA build script JUNCTIONS `engine/lib/kairos-system` to it (not a second submodule). Its `CLAUDE.md` is about the math core, not about kairos. |
| `harness/` | the Python brain. `skills/` (memory, notes, lifecycle, search/research/xai, looking, narrative), `model/` (person, presence), `control/` (spine, agency, ledger, wardrobe/catalog/avatar, shutdown, watchdog), `kairos/` (the scheduler — unprompted speech), `personality/`, `voice/` (TTS: xAI Ara + expressive tags, local fallback; the ear), `senses/` (the ambient eye, sight), `sidecar/` (the LFM CPU helpers), `server/app.py` (the gateway). `harness/README.md` is the package map. |
| `ui/` | THE ROOM — the React/Vite desktop: chat, the dock, every panel (settings, voice, search, research, wardrobe, journal, ledger…). Built into `console/room/` (committed; G-ROOM-BUNDLE proves the two agree). `ui/README.md`. |
| `console/` | the built room (`room/`) plus the legacy flat pages (`index.html`, `ops.html`, `tuning.html`, `operator.html`) that two gates still pin — `console/README.md`. `/` redirects to `/room/`. |
| `tools/` | `avatar_gen.py` (her stills + motion through the xAI API), `okf_mem.py`, the calibrator, the voice corpus tooling — `tools/README.md` says which are live. |
| `harness_tests/` | the gates — ~150 `g_*.py` plus the `h_*.py` set (`ls harness_tests/g_*.py \| wc -l` is the truth). `gates/GATE-INDEX.md` indexes them; `_gate.py` is the shared verdict helper for new ones. |
| `gates/` | gate write-ups and receipts (markdown). |
| `profiles/` | the TOML profiles `serve.py` reads. |
| `memory-okf*/` | the MEM-OKF knowledge stores (content-addressed, tiered: `LUT.md` → `sum/` → `full/`). Tool: `tools/okf_mem.py`. |
| `var/` | ALL runtime state. Gitignored. The fact registry, notes, the presence ledger, logs. |
| `docs/` | the documents — `docs/README.md` says which is authoritative for what (MEMORY-AND-RECALL is the operational memory truth; INVARIANT-MEMORY the formal model; OFF-BY-DEFAULT the live off-ledger; AVATAR-PIPELINE her face). |
| `../kairos-drift/` | **NOT this repo, and not Kairos — a third git repo beside both, owned by neither.** It answers the only question that matters about a scrubbed snapshot: of everything since the cut, which parts would a re-export CARRY? `drift.py` reads the export sha from `Kairos/KAIROS-SOURCE.txt` and the globs from `kairos-export/kairos-export.toml`, then sorts every commit OWED / MIXED / LOCAL. It lives outside because inside this repo it would be one more ledger the companion carries, and inside Kairos it would leak this repo's history into the public one — which is what the scrubbed export exists to prevent. Read-only against both; re-anchors itself, so a re-export empties the owed pile with no bookkeeping. |

---

## 3. MEMORY AND RECALL — the part you are most likely to break

**Full reference: [`docs/MEMORY-AND-RECALL.md`](docs/MEMORY-AND-RECALL.md). Read it before changing anything under `harness/skills/`.**

The essentials, so you do not have to guess:

- **WHOSE MEMORY IS IT.** Hers. Say it precisely, because the sloppy version causes real mistakes.
  `var/memory/registry.jsonl` is **Kairos's memory**, and it has two lanes:

  ```
  speaker=user   71 rows    what she knows about HIM
  speaker=self    6 rows    what she knows about HERSELF
                              'My name is Kairos.'  'I am a woman'
                              'I like the sound of rain on a tin roof.'
  ```

  Calling it "his memory" or "his facts" makes the self lane invisible — and that is not a style
  note, it is a bug generator. It happened during the G-ONEDOOR work: writing *"a stray `SP_FORGET`
  would make his memories go quiet"* made the risk look like *some user facts get lost*. But an
  autonomous forget pass matches across **every live row**, so the real worst case is that she
  tombstones `'My name is Kairos.'` and **forgets who she is** — the identity-slot bug, the first
  thing this rebuild had to repair. The imprecise noun hid the serious half of the blast radius from
  the person doing the risk assessment. The `speaker` field exists to hold exactly this distinction;
  do not collapse it in your prose either.

- **The fact registry** is `var/memory/registry.jsonl` (path from `SP_RECALL_REGISTRY`). One JSON row per fact.
- **Two axes that are constantly confused. They are not the same thing:**
  - `speaker` — **who the fact is ABOUT** (`user` | `self`). Set from the *author of the turn*, never
    inferred from the sentence. ("My name is Sam" said by him is a fact about HIM.)
  - `status` — **where the claim CAME FROM** (`observed` | `inferred` | `confirmed` | `disputed`).
    He said it, versus she concluded it.
- **`lifecycle`** — `0` live, `1` retired. The tombstone flag, and **the one field both the Rust engine and
  the Python harness key on**. Nothing is deleted; things are retired.
- **`src` is free-text provenance PROSE.** Maintenance scripts append to it. **It is not an enum and you may
  not branch on it.** Branching on it was a real bug: a cleanup pass appended `" | cleanup: ..."` and silently
  turned reflections back into evidence.
- **One read seam — and one non-ranking sibling.** Every RANKED door a fact can reach her
  mouth through funnels into `memory.search_memories_ranked_rows()`, which filters
  tombstones and applies `lifecycle.testimony_wins()`. Readers that do not rank (listing,
  provenance, counting, ambient blocks) use **`memory.live_rows(testimony=)`** — added
  2026-08-19 after the audit found NINE readers re-implementing the tombstone filter with
  THREE different predicates, two of them (`list_memories`, `provenance`) skipping
  `testimony_wins` entirely and dumping seam-silenced inferences verbatim. If you add a
  reader, use the seam or `live_rows()`. Do not re-implement the filter; there is no
  third predicate.
- **Framing happens at READ time, through two doors**: `lifecycle.render()` speaks ABOUT
  the store ("Sam told me: …" — tool listings, audit lane); `world.present_for_her()`
  speaks TO HER (you/he grammar — the standing world block and the per-turn recall note,
  because a 12B absorbs a quoted "my"). This is what stops a fact he said in the first
  person coming back in her voice. Pick by who is being addressed.
- **Write paths: `memory.remember()` is authoritative; `harness/maintenance/ops.py` is
  the maintenance writer** (compact/cleanup/forget — tombstone/quarantine semantics,
  holding `memory.registry_lock()` since 2026-08-19; before that it held nothing while
  the scheduler ran it during live turns). The daemon's two write flags are off in all
  14 profiles and refused at boot — see TRAPS. `memory.compact_registry()` is a
  projection of `ops.compact()` now; until 2026-08-19 it was a raw unlocked rewrite
  that hard-deleted rows and resolved a forgotten-then-restated fact in favour of the
  corpse, wired to the automatic hygiene tick (G-COMPACT).
- **The SEM sidecar index** (`var/memory/semindex.jsonl`, `harness/skills/semindex.py`) is DERIVED
  data for the semantics layer — recomputable from registry + model, append-only, tombstone-blind
  (lifecycle joins from the registry at read; it is never copied). It structurally cannot write the
  registry. Design and phase status: [`docs/SEMANTICS.md`](docs/SEMANTICS.md). Gates: G-SEM-INDEX,
  G-SEM-CONSERVE.

---

## 4. TRAPS — live, verified, not yet fixed

These are real. They are not hypotheticals. Do not be the next person to rediscover them.
Renumbered 2026-08-21 (1..n, live first; the closed ones keep their receipts below).

1. **THE KV MINT IS DEAD ON THIS MODEL, AND IT FAILED SILENTLY FOR WEEKS (2026-08-23). OWED: ENGINE WORK.** `/v1/capture` refuses on the model MoE — *gemma4_decode_cuda: gemma4-MoE not supported on this path — its three internal FFN copies are not on the `g4_ffn_apply` seam (ADR-013); use the served decode (`gemma4_kv_decode_logits`)*. Measured: **253 of the 253 rows written since 2026-08-19 carry `npos=0`**, no `ep.l5` sidecar in three weeks, and 642 empty episode directories (removed 2026-08-23, names in `var/memory/eps-removed-2026-08-23.json`).

   **Her memory is unaffected** — the registry is the recall authority and never touches the daemon. What is lost is the engine-side episode representation and the `l5-512-v1` half of the semantic index. The second one was load-bearing and nobody knew: every embedding contender this repo measured and rejected was ranked against a 93% bag-of-words document index (docs/SEMANTICS.md S0b).

   **The fix is in the engine**, not the harness: `v1_capture` must route through the served decode (`gemma4_kv_decode_logits`) instead of `gemma4_decode_cuda`, the same way the live turn path already does — `/v1/embed` proves the scratch-forward works on this model. Until then the harness compensates: `memory.capture_status()` logs the refusal ONCE with the engine's own words and stops asking (that is where 642 directories came from), `verify_registry()` says it aloud, and `semindex`'s `aux-1024-v1` space carries the semantic side off the CPU sidecar. **`[sem] capture_l5 = true` stays armed on purpose so this resumes by itself the day the seam lands** — and when it does, `query_embed`'s aux-before-engine order must be MEASURED again, not assumed back.
2. **`status: disputed` is vocabulary-only.** Nothing writes it. The write-time contradiction detector was
   deliberately deleted (it was a semantic judgment made out of substring matching). The rule it was trying
   to enforce lives at the read seam now, in `testimony_wins()`.

3. **The SSE stripper — FIXED WITH A RESIDUAL (2026-08-20).** The whole-turn rules could not fire per-delta, and the arming
   condition fired. Registered 2026-08-19 ("a measured live leak of that shape");
   measured 2026-08-20, live: an unterminated `<thought ` opener, ~400 tokens of
   reasoning, and every chunk after the opener's own walked out as speech and into the
   day transcript, starting mid-word ("ering triumphs..."). `speech_delta` is now
   STATEFUL for exactly this: `pend["thought"]` latches when a chunk ends inside an
   unterminated thought block and every following chunk is dropped until an explicit
   closer, a pipe-marker, or a speech-open arrives (G-MARKS-LEAK §8, with the live
   shape at five chunk sizes). Residual exposure: a thought whose SAME chunk carries a
   stray `>` downstream defeats the opener lookahead — the same limit `_THOUGHT_OPEN`
   has always had.

4. **The OpenAI-compatible path is still the thinner twin.** 2026-08-19 closed its two
   silent data losses (`_append_day_turn`, `run_post_turn`) — but it still skips the
   pre-turn spine (recall/toolset), the silence note, the canonical transcript,
   `note_user_turn`, `persist_receipts`, and the thought-channel split. Full parity is a
   redesign; until then a turn through `/v1/chat/completions` is a leaner turn than the
   same words through `/v1/chat`. The list lives in `_finish_openai_turn`'s docstring
   and this row so the gap stays a decision, not a drift.

### Closed traps — kept because the shape of each is the lesson

4. ~~**THE PRIVACY DECLINE CANNOT FIRE.**~~ **FIXED 2026-07-14 — G-SECRET 22/22.**
   For the record, because the shape of it is the whole lesson: `spine.recall_decider()` protected
   secrets by checking `mem_class == "private-secret"`, and `lifecycle.classify()` — the only classifier
   the authoritative writer runs — could emit exactly `relationship | identity | event | preference |
   fact`. **The consumer branched on a value the producer could not produce.** The decline had never
   fired once. `private-secret` was only ever minted by the *daemon's* classifier, armed by `growth=true`;
   the 2026-07-12 "one memory authority" fix set `growth=false` and took the only producer with it, so
   **the privacy guarantee was collateral damage of a correctness fix.** `g_mempolicy_v3` stayed green
   throughout because it hand-builds the `private-secret` row and tests the *dispatch*, never the *producer*.
   The audit found one real credential already sitting in his live store as a plain `fact`
   (`'My access code is 4471'`) — reclassified in place, provenance appended to `src`, nothing destroyed.
   `harness_tests/g_secret.py` §4 now asserts the generalisation, and that is the part worth keeping:
   **every class the decider branches on must be one the writer can produce.** Add an `if mc == "..."`
   branch with no producer and the gate fails the day you write it, not eight weeks later when it leaks.

5. ~~**`store_verb = true` on the live profile.**~~ ~~**`growth = true` in 8 non-live profiles.**~~
   **BOTH FIXED 2026-07-14 — G-ONEWRITER 35/35.** Kept here because the shape is instructive:
   the daemon had **two** write flags, and the 2026-07-12 "one memory authority" fix turned off one.
   The comment announcing that fix literally said *"the daemon no longer writes memories. Recall, **the
   store verb**, and classification are untouched"* — it **named** the second write path while declaring
   the daemon no longer wrote. So `"note that I'll be late"` was still a registry write, performed by the
   daemon, with `speaker` hardcoded, no `status`, and none of admission / firewall / dedupe / supersede /
   secret-classification — **and zero model inference, so she never saw the turn.**
   The remedy for *an invariant enforced in one of two paths* was enforced in one of two paths.
   Both flags are now false on all 14 profiles, and **`serve.py` refuses to boot** any profile that arms
   either while `agent.authority = 'spine'`. A rule in a comment gets applied to the file the comment is
   in; this one lives in the door.

6. ~~**`_AUTHOR` / `_QUESTION` are process-wide module globals**~~ **FIXED 2026-08-19 — G-AUTHOR-CTX.**
   They are `contextvars.ContextVar`s (`memory.py` and the twin in `notes.py`). A turn
   cannot see another turn's author or question. `remember_about_self` RESETs the previous
   token instead of assuming the previous author was `"user"`.

7. ~~**Two gates are named `_offline` and are not.**~~ **FIXED 2026-08-19.**
   `_native_chat_sse` / `_await_warm` wait on `_WARM` only when `SP_GATEWAY_PREWARM=1`.
   A standalone script no longer hangs for 900s. The `_WARM` event is still only *set*
   by `_prewarm()`; the wait is what was wrong, not the event.

---

---

## 5. THE GATES

**Doctrine: no claim without a repeatable gate.** The index is [`gates/GATE-INDEX.md`](gates/GATE-INDEX.md) —
every gate, what it protects, and crucially **whether it needs a GPU**.

- **OFFLINE gates** point `SP_DAEMON_URL` at a discard port and need no GPU and no daemon. Run these freely.
  They cover most of the memory system: `g_claim`, `g_salience`, `g_durability`, `g_memory_lifecycle`,
  `g_silence`, `g_clock`, `g_reflect`, `g_notes`, `g_watch`, `g_grammar`, `g_tuning`, `g_roleplay`.
  Looking-up (chip, window, claim-hold): `g_looking`, `g_tool_honesty`, `g_research`, `g_search`.
  The room and the docs: `g_room_css`, `g_room_bundle`, `g_docs_true` (retired vocabulary and
  structural truths across README / START-HERE / AGENTS / docs), `g_profile_door`.
- **LIVE gates** need `python serve.py companion` running. THE PROFILE IS POSITIONAL AND NOT
  OPTIONAL: `serve.py agent` is a real profile — the **12B**, `profiles/agent.toml` — so it
  starts, warms and answers while serving a different model with different knobs. A live gate
  pointed at it measures the wrong stack and reports green. Check `SP_MODEL_PATH` in the boot
  banner. (Cost a restart on 2026-08-03; the docs said `agent` in three places.)

Run one: `python harness_tests/g_claim.py`

**If you touch memory or recall, the minimum bar is:**

```
python harness_tests/g_claim.py            # the seam, the slot, testimony over inference
python harness_tests/g_durability.py       # a turn is not a fact; the identity firewall
python harness_tests/g_memory_lifecycle.py # write / supersede / provenance
python harness_tests/g_salience.py         # a repeat is a second data point
python harness_tests/g_silence.py          # absence is only information if you were looking
python harness_tests/g_clock.py            # every timestamp survives its own round trip
```

**Writing a gate? Two rules, both bought with real regressions:**

1. **Assert through the REAL path**, not a hand-called helper. G-CLAIM asserts through
   `spine.recall_decider()` — the function that actually runs — precisely because the bug it protects
   against lived in the path nobody was testing.
2. **Do not supply your own precondition.** If your gate hand-builds the row that makes the guard fire, you
   have tested the guard, not the system. That mistake is currently costing us a privacy guarantee.

---

## 6. KEEPING THIS FILE TRUE

This file rots faster than the code. When you land a change that alters any of the following, **update this
file in the same commit**:

- a new read path or write path into memory → §3 and `docs/MEMORY-AND-RECALL.md`
- a new gate → a row in `gates/GATE-INDEX.md`
- a trap fixed → strike it from §4 (and say so in the commit)
- a new trap found → add it to §4, even if you are not fixing it now. **An unwritten trap is a trap that gets
  rediscovered at 3am.**
- a subsystem retired or renamed → its vocabulary goes into `harness_tests/g_docs_true.py`'s retired list, so
  the docs cannot keep describing it (ceilings/tiers, the Grok CLI, `staging/`, and the 12B default all did).
- a profile change → `START-HERE.md` ("what is on, what is off") in the same commit.

The commit messages in this repo are unusually long on purpose: they carry the *reasoning*, not just the
change. `git log` is a primary source. Read it before you assume something is arbitrary.
