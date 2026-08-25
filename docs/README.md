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
| [`SEMANTICS.md`](SEMANTICS.md) | design | PHASE 2 MEASURED | The SEM stack S0–S4: the sidecar index, the rank experiment and its receipt (the τ-gate lost, on the record). |
| [`ANON-MODE.md`](ANON-MODE.md) | reference | **LIVE** | **Off the record** (2026-08-23, his ask): the dock switch that keeps her entirely herself and writes nothing down. The seventeen doors in `anon.DOORS` (twelve write, five egress, count checked 2026-08-25) and where each is guarded, the third door class that is neither — her PROMPT, which the room kept re-sending after the switch went off, the two deliberate exceptions, the persona shadow, the line she is told, and the table of what it does NOT touch. Volatile by design — a restart ends it. `g_anon.py` diffs the disk. |
| [`OFF-BY-DEFAULT.md`](OFF-BY-DEFAULT.md) | ledger | **LIVE** | Every knob that ships off, and the evidence that would arm it. `g_offledger.py` holds it to the profile. |
| [`AVATAR-PIPELINE.md`](AVATAR-PIPELINE.md) | design | LIVE (xAI API era) | Her face, wardrobe and motion: the grid, wants, the catalog (clothing/gestures/moments), prompt anchoring, moderation, generate-now. |
| [`AUX-MODELS.md`](AUX-MODELS.md) | design | LIVE | The LFM2.5 CPU sidecars — deep recall, page reading, judges — and what stays dark. |
| [`MCP.md`](MCP.md) | reference | LIVE | The FastMCP server and bridge: her hands over MCP, and other servers' tools into her. |
| [`BACKENDS.md`](BACKENDS.md) | reference | LIVE (2026-08-21) | One inference surface, two backends (sp-daemon / any OpenAI-compatible server) and the honest table of what degrades without the custom engine. |
| `superpowers/plans`, `superpowers/specs` | design notes | tool output | The 2026-08-06 shutdown design. Reference, not canon. |

Outside `docs/`: [`../README.md`](../README.md) (front door), [`../START-HERE.md`](../START-HERE.md)
(the two-minute map), [`../AGENTS.md`](../AGENTS.md) (rules, bug class, traps),
[`../gates/GATE-INDEX.md`](../gates/GATE-INDEX.md) (every gate), `../HINDSIGHT.md` and
`../MIGRATION-MAP.md` (the July 2026 charter — historical), the component
READMEs (`harness/`, `engine/`, `ui/`, `console/`, `tools/`), and `papers/` (the ADRs that are
lattice research, not kairos policy).

Convention: every file here carries front matter with `type`, `title`, `status`. A doc whose status
is HISTORICAL is kept for the reasoning, not the instructions.

*Some documents listed in the source tree are not carried in this export (engine ADRs, session receipts, research essays); their rows are omitted here rather than left as dead links.*
