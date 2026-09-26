---
type: reference
title: "PANELS — every window in the room, what it reads, and what it can change"
status: LIVE (re-checked against ui/src/api.js and appRegistry.jsx 2026-09-26, after redesign stage 3)
---

# PANELS

The room is a set of windows over one gateway. Each one is listed here by the title its
window wears, with the **route it reads**, whether it can **write**, and — the column that
matters most — **whose it is**.

Some of these are hers. Journal and Her own time are read-only *by construction*: they
compose stores she writes and there is no POST behind them. That is not a missing feature.
A companion whose diary the operator can edit does not have a diary.

Registered in `ui/src/appRegistry.jsx`; every window is a component in `ui/src/apps/`, except
Chat (`ui/src/Chat.jsx`) and The view (`ui/src/room/RoomView.jsx`). Every call a window makes
is a door in `ui/src/api.js`.

---

## Around the windows: the shell

Not windows, but they are where most of the room's state is shown, so they are listed here
once (`ui/src/main.jsx` and `ui/src/room/`):

| Surface | Reads | Controls | Notes |
|---|---|---|---|
| **the desktop icons** (`room/DeskIcons.jsx`) | the registry | open a window | Loose, draggable, positions kept per browser (`deskIcons.js`). Double-click (or Enter) opens, a single click selects. Which apps get an icon is the Apps window's list (`dockPrefs.js` — the file kept its name when the dock went, 2026-09-23). |
| **the top bar** (`room/TopBar.jsx`) | `/v1/room/pulse`, `/health`, `/v1/system` | the stack light | Her on the left (the mood pill, her voice word and the presence note), her day in the centre ("you spoke …", "her day ends in …" / "her day closed — she has written", "next look …", from `room/facts.js`), the machine on the right (the profile chip, "up …" — the gateway's uptime — the stack light, "backup in …"). |
| **the stack light** (`room/StackLight.jsx`) | `/health` | bounce, restart | A disclosure, opened by a click when the stack is restartable and idle: *bounce* (the gateway only, seconds, keeps the model warm) and *restart* (reloads the model, ~2 min, asks first). |
| **the taskbar** (the footer in `main.jsx`) | `/v1/room/pulse` | windows, off the record, Shut down | The KAIROS mark and the Console link; a button per open window (clicking the focused one minimises it, and a minimised window flies to its button); the looked-up, in-scene and off-the-record chips (`room/TaskChips.jsx`, `room/Anon.jsx`); **Anonymous / Off the record** ([`ANON-MODE.md`](ANON-MODE.md)); **Shut down** (*her only* / *everything* / *kill*); the clock and date. |
| **the portrait** (`room/Portrait.jsx`) | the pulse and her live mood | drag, resize | Her current still or loop, captioned with her mood and what she has on. |

At phone width (≤620px) every window fills the desktop and loses its resize grips; the bars
shed glances by width and never shed a control (the widths are in the 2026-09-26 stage-3
entry of `CHANGELOG.md`).

## Her, and what she is doing

| Window | Reads | Writes | Notes |
|---|---|---|---|
| **Chat** | `/v1/chat` (SSE), `/v1/day`, `/v1/kairos/outbox`, `/v1/anon` | a message | The conversation, and a window like the others since 2026-09-23 — it opens itself when nothing else is open. It is a client: it renders a stream and decides nothing. The day is read back on mount, into an empty log only, and restored turns are display, never re-sent as prompt. |
| **Body** | `/v1/telemetry/now`, `/v1/telemetry/history` | — | His heart and his movement, live, plus **the exact sentence she is handed** about them. That last part is the most useful widget in the room: it is the only place to see what she was told about your body *before* she says anything. Same seam as her prefix (`body.read()`/`present()`), so the window and she can never describe two different people. |
| **Memory** | `/v1/memory`, `/v1/memory/why` | relabel, add, retire | Live rows and retired ones, because rendering the dead is what makes "nothing is ever deleted" legible rather than merely true. A row she *concluded* carries a **why** button: what it was drawn from, each support's current liveness, and what would be orphaned if you retired it. |
| **Journal** | `/v1/narrative` | **none** | What she writes at the end of a day. Hers. You can only read it. |
| **Story** | `/v1/story`, `/v1/memory` | relabel, forget | Her prefix line by line, each line attributed to the registry row it came from (the SAME assembly the prefix renders, byte-checked by G-MEMORY-STORY §5); the chapters with the rows the fold archived into them as footnotes; the narrative lanes by kind; the backup receipt on the same screen. Edits go through Memory's two doors — the window owns no verbs. |
| **House** | `/v1/house/now` | — | The Home Assistant beachhead: is it reachable, which entities cross the bridge and what each becomes, and the link out. Readings themselves live in Body. |
| **Her own time** | `/v1/agency` | **none** | Everything she did while you were away — journal lines, own-time notes, what she wore, what she asked for. Not editable, on purpose. |
| **Presence** | `/v1/presence` | enter / leave a mode, hand her a book / put it down | Narration, company, lucid dream — her modes of being there out loud, and the shelf she reads from. |
| **Wardrobe** | `/v1/wardrobe`, `/v1/catalog` | wear, want, accept, dismiss, generate, catalog edits | What she has on, what else she could be, the moments she can show you. Her wants queue here; the generate button is the same door she uses. |
| **Stage** | `/v1/roleplay` | scene control, **stop** | The scene and the rung it is on. The stop is always one click, at any heat, no exceptions. |

## What she knows and what is owed

| Window | Reads | Writes | Notes |
|---|---|---|---|
| **Board** | `/v1/notes` | add, update, remove, restore | Notes and reminders either of you wants kept in view. `remove` tombstones — a note taken down still exists. |
| **Decisions** | `/v1/decisions` | decide | What is waiting on *you*. |
| **Ledger** | `/v1/ledger`, `/v1/health/gates` | add, edit, drop | The plan, what we parked, and everything noticed and not touched. Where a finding goes when it is real but not now. |
| **Research** | `/v1/research` | run | The paid tier, hers and yours. Titles expand to the returned text. The backend is the live `research.backend` knob (`xai` or the local `sidecar`). |
| **Search** | `/v1/search`, `/v1/tuning` | run; the engine knob | Web searches, hers and yours, a box to run your own, and the engine section of the knobs. |
| **Files** | `/v1/files` | write, upload | The tree you share. Drag something in and she can read it. |

## The machine

| Window | Reads | Writes | Notes |
|---|---|---|---|
| **Settings** | `/v1/tuning` | set | Every knob, grouped. Self-rendering: add a row to the registry (`harness/tuning/registry.py`) and it appears with no UI edit. `live` knobs apply on the next call; profile-scope knobs show a *restart to change* chip and are **refused with a reason** rather than silently ignored; a knob you have overridden from the room says *changed*. |
| **Setup** | `/v1/setup` | — | What is configured and what is not — endpoint, keys, her face, the model cards. |
| **Tools** | `/v1/tools` | — | Every tool she has, filtered by risk (all / write / read / private / world / machine / act). |
| **Senses** | `/v1/senses`, `/v1/speak/status` | — | What she can see and hear, which eyes she is using, and what the room has looked like. |
| **The room** | `/v1/senses` | — | Her hourly notes on the room. The eye waits for quiet before it looks. |
| **The view** | `/v1/room/pulse` | — | The room's weather in a frame — phase, her mood, whether anyone is about. The same `describeRoom` output the backdrop paints, with the reading written underneath. |
| **Voice** | `/v1/speak/status`, `/v1/tuning` | on/off, provider, pace, test | Her voice, live, and a button to hear it. |
| **Music** | `/v1/music` | control | The record player — hers to reach for too. Starts without a desktop icon; its tools are dark when the profile sets `[music].enabled = false` (the private stack's does, since 2026-08-25). |
| **Librarians** | `/v1/aux` | rebuild | The small CPU models that embed, retrieve, judge and read for her. |
| **Games** | `/v1/games` | play | A board you both touch; the rules belong to the engine, not the page. Starts without a desktop icon; its tools are dark unless `SP_GAMES` is on. |
| **Apps** | — | which apps have a desktop icon | Every window there is, always listed; tick one to keep its icon on the desktop. Per browser, live. It is pinned: it cannot hide itself, because it is the way back. |

---

## How a window is added

1. A component in `ui/src/apps/Name.jsx`, using `usePoll` + `Body` from `panel.jsx`, and the
   kit's shared parts (`ui/src/kit/parts.jsx` — Chip, Button, Tabs, rows, states) rather than
   its own spelling of them.
2. A door in `ui/src/api.js` — **one file on purpose**, so a route is never invented in two
   places with two spellings.
3. A row in `appRegistry.jsx` (`id`, `title` in sentence case, `icon` — a glyph name in
   `ui/src/kit/icons.jsx`, `w`, `h`, `Component`, `css`, `blurb`; `dock: false` if it should
   start without a desktop icon; optional `TitleChip`).
4. Styles in `ui/src/room.css` under the window's own `css` prefix (G-ROOM-CSS), colours from
   `ui/src/kit/tokens.css` only (G-ROOM-TOKENS ratchets raw colour literals down).
5. `npm run build` in `ui/` — the bundle is committed, and **G-ROOM-BUNDLE fails if the
   committed bundle does not match a rebuild of the committed source**.

## The rules windows follow

- **Read from the same seam she does.** The Body window calls the function that builds her
  prefix note. Two readers is how a chip and a prefix end up describing different people.
- **A failure is rendered, never silently degraded.** `Body` shows the error, and every
  window mounts inside a boundary, so one broken window shows its error in its own frame and
  the rest of the room keeps working. A window that quietly falls back to stale data is worse
  than one that says it is broken.
- **Show the dead.** Retired memory rows, tombstoned notes, dropped ledger items. Hiding
  them makes the never-delete promise unverifiable.
- **Say what is inferred.** A conclusion is labelled as one wherever it is shown — the
  window is where you argue with a ranking, and you cannot argue with one you cannot see.
- **Hers is hers.** If there is no POST behind a window, that is the feature.
