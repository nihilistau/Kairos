---
type: index
title: "docs/ — every document, and which one is authoritative for what"
status: LIVE — g_docs_true.py fails if a docs/*.md is missing from this table
---

# docs/ — the index

One truth per fact. Where two documents cover one subject, the **authority** column says which
wins; the other is a register (formal / public / historical), not a second opinion.

| doc | type | status | authority |
|---|---|---|---|
| [`CHANGELOG.md`](CHANGELOG.md) | changelog | **LIVE** | **What changed, by the day it changed** — dated rather than versioned, because this tree is a living system. The index into the commit log, which carries the reasoning; where an entry names a number, that number was measured. Behaviour a reader would notice gets an entry in the same commit (AGENTS.md §6). The exported public framework keeps the semver changelog (`../kairos-export/CHANGELOG.md`). |
| [`SETUP.md`](SETUP.md) | reference | LIVE (2026-08-23) | **THE onboarding truth**: the endpoint, where every key file goes, the model cards, what each setting affects, and the symptom table. The room's setup panel (`/v1/setup`) reports the same facts live; where they differ, the panel is describing the running stack and this describes the design. |
| [`MEMORY-AND-RECALL.md`](MEMORY-AND-RECALL.md) | reference | LIVE | **THE operational truth for memory**: fields, doors in and out, the one read seam, the traps. Read before touching `harness/skills/`. |
| [`../gates/PMAX-20000-2026-08-23.md`](../gates/PMAX-20000-2026-08-23.md) | receipt | RECEIPT (2026-08-23) | pmax 12096 -> 20000. Three stacked ceilings (decode attention, prefill scratch, prefill attention); 15,633-token prompt batched and correct. |
| [`../gates/ATTN-TILE-2026-08-23.md`](../gates/ATTN-TILE-2026-08-23.md) | receipt | RECEIPT (2026-08-23) | Tiled decode attention: pmax stops being a 48 KB shared-memory limit. Identical output. The VRAM contention it exposed (the batched prefill wanting the same GB) was real and was solved the same day by `prefill_chunk` — **pmax is 20000**, see the row above; the "stays 12096" sentence in that receipt was true for hours and is corrected in place. |
| [`../gates/SEM-L5-VS-AUX-2026-08-23.md`](../gates/SEM-L5-VS-AUX-2026-08-23.md) | receipt | RECEIPT (2026-08-23) | The l5 space measured for the first time (capture was dead): 0.10 against aux's 0.53. Precedence corrected. |
| [`../gates/EPISODE-BACKFILL-2026-08-23.md`](../gates/EPISODE-BACKFILL-2026-08-23.md) | receipt | RECEIPT (2026-08-23) | The 247 episodes the engine owed, minted onto the Optane; L5 coverage of her live memory 21% -> 95%. |
| [`ENGINE-SESSION-2026-08-23.md`](ENGINE-SESSION-2026-08-23.md) | receipt | RECEIPT (2026-08-23) | The night `/v1/capture` came back on the model: the FFN seam, two CUDA lifetime/ownership bugs that were never about MoE, the disk floor under the mint — and the ranked list of what to do next. |
| [`INVARIANT-MEMORY.md`](INVARIANT-MEMORY.md) | foundation | FOUNDATION (2026-07-14) | **Normative for verdicts** — the memory system as a finite mathematical object. MEMORY-AND-RECALL describes the machinery built on it. |
| [`INVARIANT-ROADMAP.md`](INVARIANT-ROADMAP.md) | roadmap | ROADMAP | Where the foundation goes next; the inventory of decision sites still ruling by hand. Wins over CONTINUITY where they conflict on verdicts. |
| [`CONTINUITY.md`](CONTINUITY.md) | roadmap | HISTORICAL ROADMAP (2026-07-15) | The "memory as a life" plan — N1 (world) and N2 (narrative/journal) shipped 2026-07-30. Read for intent; the operational truth is MEMORY-AND-RECALL. |
| [`PAPER-INVARIANT-MEMORY-POST.md`](PAPER-INVARIANT-MEMORY-POST.md) | essay | PUBLIC TWIN | The public essay of INVARIANT-MEMORY. Non-normative; may lag. |
| [`SEMANTICS.md`](SEMANTICS.md) | design | PHASE 2 MEASURED | The SEM stack S0–S4: the sidecar index, the rank experiment and its receipt (the τ-gate lost, on the record). |
| [`SWEEP-2026-08-24.md`](SWEEP-2026-08-24.md) | receipt | **LIVE** | The 2026-08-24 deep sweep: nine gates writing into her real memory (and the false 'repetitive loop' memory that came of it), the 26% of her turns that leaked markup because the client's widenings were inert, the unclosed angle bracket stored in her persona, and what was found for gestures, wardrobe and first-turn latency. |
| [`ANON-MODE.md`](ANON-MODE.md) | reference | **LIVE** | **Off the record** (2026-08-23, his ask): the dock switch that keeps her entirely herself and writes nothing down. The seventeen doors in `anon.DOORS` (twelve write, five egress, count checked 2026-08-25) and where each is guarded, the third door class that is neither — her PROMPT, which the room kept re-sending after the switch went off, the two deliberate exceptions, the persona shadow, the line she is told, and the table of what it does NOT touch. Volatile by design — a restart ends it. `g_anon.py` diffs the disk. |
| [`OFF-BY-DEFAULT.md`](OFF-BY-DEFAULT.md) | ledger | **LIVE** | Every knob that ships off, and the evidence that would arm it. `g_offledger.py` holds it to the profile. |
| [`AVATAR-PIPELINE.md`](AVATAR-PIPELINE.md) | design | LIVE (xAI API era) | Her face, wardrobe and motion: the grid, wants, the catalog (clothing/gestures/moments), prompt anchoring, moderation, generate-now. |
| [`AUX-MODELS.md`](AUX-MODELS.md) | design | LIVE | The LFM2.5 CPU sidecars — deep recall, page reading, judges — and what stays dark. |
| [`NARRATIVE-IDENTITY-AND-FOM.md`](NARRATIVE-IDENTITY-AND-FOM.md) | design | DESIGN (2026-08-22) | Narrative identity as the memory model: the classes, presence modes, coherence and the order-invariant core. Design, not yet wired. |
| [`MIXED-FOM-SKETCH.md`](MIXED-FOM-SKETCH.md) | design | SKETCH (2026-08-22) | Redemption/contamination sequence detection and the mixed-FOM sketches — code to be dropped in, nothing wired yet. |
| [`MCP.md`](MCP.md) | reference | LIVE | The FastMCP server and bridge: her hands over MCP, and other servers' tools into her. |
| [`BACKENDS.md`](BACKENDS.md) | reference | LIVE (2026-08-21) | One inference surface, two backends (sp-daemon / any OpenAI-compatible server) and the honest table of what degrades without the custom engine. |
| [`ADR-013-gemma4-moe-ar.md`](ADR-013-gemma4-moe-ar.md) | adr | IN PROGRESS → landed | Gemma-4 MoE on the autoregressive path — the engine decision behind the model. |
| [`ADR-012-fp16-kv.md`](ADR-012-fp16-kv.md) | adr | HISTORICAL | fp16 vs int8 KV, with the refutation. |
| [`COSYSIM-SALVAGE.md`](COSYSIM-SALVAGE.md) | ledger | DECIDED | What came across from CosySim and why the rest did not. |
| `superpowers/plans`, `superpowers/specs` | design notes | tool output | The 2026-08-06 shutdown design. Reference, not canon. |

Outside `docs/`: [`../README.md`](../README.md) (front door), [`../START-HERE.md`](../START-HERE.md)
(the two-minute map), [`../AGENTS.md`](../AGENTS.md) (rules, bug class, traps),
[`../gates/GATE-INDEX.md`](../gates/GATE-INDEX.md) (every gate), [`../HINDSIGHT.md`](../HINDSIGHT.md) and
[`../MIGRATION-MAP.md`](../MIGRATION-MAP.md) (the July 2026 charter — historical), the component
READMEs (`harness/`, `engine/`, `ui/`, `console/`, `tools/`), and `papers/` (the ADRs that are
lattice research, not kairos policy).

Convention: every file here carries front matter with `type`, `title`, `status`. A doc whose status
is HISTORICAL is kept for the reasoning, not the instructions.
