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
| [`SETUP.md`](SETUP.md) | reference | LIVE (2026-08-23) | **THE onboarding truth**: the endpoint, where every key file goes, the model cards, what each setting affects, and the symptom table. The room's setup panel (`/v1/setup`) reports the same facts live; where they differ, the panel is describing the running stack and this describes the design. |
| [`MEMORY-AND-RECALL.md`](MEMORY-AND-RECALL.md) | reference | LIVE | **THE operational truth for memory**: fields, doors in and out, the one read seam, the traps. Read before touching `harness/skills/`. |
| [`INVARIANT-MEMORY.md`](INVARIANT-MEMORY.md) | foundation | FOUNDATION (2026-07-14) | **Normative for verdicts** — the memory system as a finite mathematical object. MEMORY-AND-RECALL describes the machinery built on it. |
| [`INVARIANT-ROADMAP.md`](INVARIANT-ROADMAP.md) | roadmap | ROADMAP | Where the foundation goes next; the inventory of decision sites still ruling by hand. Wins over CONTINUITY where they conflict on verdicts. |
| [`CONTINUITY.md`](CONTINUITY.md) | roadmap | HISTORICAL ROADMAP (2026-07-15) | The "memory as a life" plan — N1 (world) and N2 (narrative/journal) shipped 2026-07-30. Read for intent; the operational truth is MEMORY-AND-RECALL. |
| [`PAPER-INVARIANT-MEMORY-POST.md`](PAPER-INVARIANT-MEMORY-POST.md) | essay | PUBLIC TWIN | The public essay of INVARIANT-MEMORY. Non-normative; may lag. |
| [`SEMANTICS.md`](SEMANTICS.md) | design | PHASE 2 MEASURED | The SEM stack S0–S4: the sidecar index, the rank experiment and its receipt (the τ-gate lost, on the record). |
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
