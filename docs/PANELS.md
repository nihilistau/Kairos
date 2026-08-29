---
type: reference
title: "PANELS — every window in the room, what it reads, and what it can change"
status: LIVE (2026-08-26)
---

# PANELS

The room is a set of windows over one gateway. Each one is listed here with the **route it
reads**, whether it can **write**, and — the column that matters most — **whose it is**.

Some of these are hers. `journal` and `her own time` are read-only *by construction*: they
compose stores she writes and there is no POST behind them. That is not a missing feature.
A companion whose diary the operator can edit does not have a diary.

Registered in `ui/src/appRegistry.jsx`; every panel is a component in `ui/src/apps/`.

---

## Her, and what she is doing

| Panel | Reads | Writes | Notes |
|---|---|---|---|
| **body** ♥ | `/v1/telemetry/now`, `/v1/telemetry/history` | — | His heart and his movement, live, plus **the exact sentence she is handed** about them. That last part is the most useful widget in the room: it is the only place to see what she was told about your body *before* she says anything. Same seam as her prefix (`body.read()`/`present()`), so the panel and she can never describe two different people. |
| **memory** 🧠 | `/v1/memory`, `/v1/memory/why` | relabel, add, retire | Live rows and retired ones, because rendering the dead is what makes "nothing is ever deleted" legible rather than merely true. A row she *concluded* carries a **why** button: what it was drawn from, each support's current liveness, and what would be orphaned if you retired it. |
| **journal** 📔 | `/v1/narrative` | **none** | What she writes at the end of a day. Hers. You can only read it. |
| **story** 📖 | `/v1/story`, `/v1/memory` | relabel, forget | Her prefix line by line, each line attributed to the registry row it came from (the SAME assembly the prefix renders, byte-checked by G-MEMORY-STORY §5); the chapters with the rows the fold archived into them as footnotes; the narrative lanes by kind; the backup receipt on the same screen. Edits go through the memory panel's two doors — the panel owns no verbs. *(Added 2026-08-29 to this file; the panel shipped 2026-08-28.)* |
| **house** 🏠 | `/v1/house/now` | — | The Home Assistant beachhead: is it reachable, which entities cross the bridge and what each becomes, and the link out. Readings themselves live in ♥ body. *(Row added 2026-08-29 — the audit found the panel had never once mounted AND was missing here; both fixed the same night.)* |
| **her own time** ◈ | `/v1/agency` | **none** | Everything she did while you were away — journal lines, own-time notes, what she wore, what she asked for. Not editable, on purpose. |
| **presence** | `/v1/room/pulse`, tuning | mode enter/leave | Narration, company, lucid dream — her modes of being there out loud, and the shelf she reads from. |
| **wardrobe** | `/v1/wardrobe`, `/v1/catalog` | wear, want, generate, dismiss | What she has on, what else she could be, the moments she can show you. Her wants queue here; the generate button is the same door she uses. |
| **stage** | roleplay state | scene control, **stop** | The scene and the rung it is on. The stop is always one click, at any heat, no exceptions. |

## What she knows and what is owed

| Panel | Reads | Writes | Notes |
|---|---|---|---|
| **board** 📋 | `/v1/notes` | add, update, remove, restore | Notes and reminders either of you wants kept in view. `remove` tombstones — a note taken down still exists. |
| **decisions** ⚖ | `/v1/decisions` | decide | What is waiting on *you*. |
| **ledger** | `/v1/ledger` | add, edit, drop | The plan, what we parked, and everything noticed and not touched. Where a finding goes when it is real but not now. |
| **research** ⌕ | `/v1/research` | run | The paid tier, hers and yours. Titles expand to the returned text. |
| **search** | `/v1/search` | run | Web searches, hers and yours, and a box to run your own. |
| **files** 📁 | `/v1/files` | write, upload | The tree you share. Drag something in and she can read it. |

## The machine

| Panel | Reads | Writes | Notes |
|---|---|---|---|
| **settings** | `/v1/tuning`, `/v1/knobs` | set | Every knob, grouped. Self-rendering: add a row to the registry and it appears with no UI edit. `live` knobs apply on the next turn; `restart` knobs are **refused with a reason** rather than silently ignored. |
| **setup** | `/v1/setup` | — | What is configured and what is not — endpoint, keys, her face, the model cards. |
| **tools** | `/v1/tools` | — | Every tool she has, by family and by risk. |
| **senses** | `/v1/senses` | — | What she can see and hear, and what the room has looked like. |
| **room** | `/v1/agency` (room kind) | — | Her hourly notes on the room. The eye waits for quiet before it looks. |
| **voice** | `/v1/speak/status` | on/off, provider, test | Her voice, live, and a button to hear it. |
| **music** ♪ | `/v1/music` | control | The record player — hers to reach for too. |
| **librarians** | aux status | — | The small CPU models that embed, retrieve, judge and read for her. |
| **games** | game state | play | A board you both touch; the rules belong to the engine, not the page. |
| **apps** | — | dock layout | Every window there is, and which of them live in this dock. |

---

## How a panel is added

1. A component in `ui/src/apps/Name.jsx`, using `usePoll` + `Body` from `panel.jsx`.
2. A door in `ui/src/api.js` — **one file on purpose**, so a route is never invented in two
   places with two spellings.
3. A row in `appRegistry.jsx` (`id`, `title`, `icon`, `w`, `h`, `Component`, `css`, `blurb`).
4. Styles in `ui/src/room.css`.
5. `npm run build` in `ui/` — the bundle is committed, and **G-ROOM-BUNDLE fails if the
   committed bundle does not match a rebuild of the committed source**.

## The rules panels follow

- **Read from the same seam she does.** The body panel calls the function that builds her
  prefix note. Two readers is how a chip and a prefix end up describing different people.
- **A failure is rendered, never silently degraded.** `Body` shows the error. A panel that
  quietly falls back to stale data is worse than one that says it is broken.
- **Show the dead.** Retired memory rows, tombstoned notes, dropped ledger items. Hiding
  them makes the never-delete promise unverifiable.
- **Say what is inferred.** A conclusion is labelled as one wherever it is shown — the
  panel is where you argue with a ranking, and you cannot argue with one you cannot see.
- **Hers is hers.** If there is no POST behind a panel, that is the feature.
