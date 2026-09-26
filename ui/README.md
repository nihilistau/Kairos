# ui/ — the room

The React + Vite desktop you talk to her in. Built into `console/room/` (committed, so the
running stack needs no Node) and served by the gateway at `http://127.0.0.1:8800/room/`.

```bash
cd ui && npm ci && npm run build      # -> ../console/room/  (harness_tests/g_room_bundle.py proves the two agree)
npm run dev                           # dev server; proxies /v1 to :8800
```

## What is on the screen

A **top bar** (her mood and voice, her day, the machine and its stack light), a **desktop** of
loose app icons with the windows and her portrait on it, and a **taskbar** (the mark, the
Console link, a button per open window, the looked-up / in-scene / off-the-record chips, the
off-the-record switch, Shut down, the clock). There has been no dock since 2026-09-23 and no
status group in the taskbar since stage 3 of the redesign (2026-09-26). Every window, with the
route it reads, is in [`docs/PANELS.md`](../docs/PANELS.md).

Windows move, resize from eight grips, maximise (the green light, or a double-click on the
bar), minimise (the amber light, or a click on the focused window's taskbar button — it flies
to its button and back; no flight under reduced motion) and close (red). The top window that
is showing is the focused one and its bar says so. At ≤620px every window fills the desktop
and loses its grips. Chat is a window like the rest and opens itself when nothing else is open.

## The framework (one registry, rendered)

| file | role |
|---|---|
| `src/main.jsx` | the shell: the top bar, the desktop (icons, portrait, windows), the taskbar with its window buttons, off the record and Shut down. Every window body mounts inside an error boundary, so one broken window cannot blank the room |
| `src/appRegistry.jsx` | every window, declared once: id, title (sentence case — "The view", "Her own time", "The room"), `icon` (a glyph in `kit/icons.jsx`), size, component, CSS prefix, `dock: false` (starts without a desktop icon), optional `TitleChip`. Registration is not aliveness: an app can be DARK by profile (`[music].enabled = false`, `SP_GAMES` off — both true of the private stack) and their toolsets return `[]` — the icon renders over nothing. `docs/OFF-BY-DEFAULT.md` holds the arming condition |
| `src/windowManager.js` | the window store: open / focus / minimise (with its flight delay) / maximise / move-resize / close, through `useSyncExternalStore`. Keeps nothing across a reload |
| `src/dockPrefs.js` | which apps get a desktop icon — the operator's call, live, per browser (localStorage), changed in the Apps window, which is pinned. The name is the dock's; the dock is gone and the list now decides the icons |
| `src/deskIcons.js` | where each desktop icon sits, per browser. Deliberately a separate store from `dockPrefs.js`: "which" and "where" are two questions |
| `src/room/DeskIcons.jsx` | the icons: double-click (or Enter) opens, a single click selects, drag moves |
| `src/room/TopBar.jsx` | the top bar — `TopBarView` is pure (G-ROOM-KIT renders it from a fixture pulse), `TopBar` is the two polls around it (`/health`, `/v1/system`) |
| `src/room/StackLight.jsx` | the gateway's light and word; a click opens *bounce* (seconds, keeps the model warm) and *restart* (reloads the model, asks first). A disclosure, not a menu; it opens only when the stack is restartable and idle |
| `src/room/facts.js` | the room's time words ("you spoke 11m ago", "her day ends in …", "up 19m"), in one module |
| `src/room/TaskChips.jsx` | the taskbar's looked-up and in-scene chips (kit Chips) |
| `src/room/Anon.jsx` | off the record: the taskbar switch and its chip ([`docs/ANON-MODE.md`](../docs/ANON-MODE.md)) |
| `src/room/Portrait.jsx`, `Avatar.jsx` | her still or loop on the desktop, movable and resizable, remembered per browser |
| `src/room/useMood.js`, `moodTheme.js`, `roomMood.js` | her mood decided in ONE place: her live `[MOOD:]` mark beats the polled one, and `moodTheme.js` writes the hue onto `<html>` so every surface reads the same one |
| `src/room/Renderer.jsx`, `Backdrop2D.jsx`, `describe.js`, `RoomView.jsx` | the backdrop, and The view window framing the same `describeRoom` output. `describe.js` has no imports, so G-ROOM-SHELL tests the contract without a build |
| `src/Chat.jsx` | the conversation — and it is a CLIENT: it renders a stream, it decides nothing. The day read-back on mount (`GET /v1/day`, into an empty log only), and the line that hurt: **restored turns are DISPLAY, never re-sent as prompt** — sending them back cost an 11-minute cold turn. The off-the-record filter (turns made under the switch stay visible and stop being SENT once it is off — she must not carry the private hour in-context). Her thinking channel, rendered. Notice chips for engine errors and context trims — **never appended to her content**, because engine text in her mouth is its own leak. Up-arrow input history (2026-08-25) |
| `src/kit/` | the design system (redesign stage 0, 2026-09-24): `tokens.css` (the only place a colour is written — palette, roles, scale, and the legacy aliases stage 6 deletes), `kit.css` + `parts.jsx` (Chip, Button, Tabs, rows, states, Orb — every class `ui-`), `icons.jsx` (one hand-drawn glyph family; no emoji), `fonts.js` (Inter, JetBrains Mono, Source Serif 4, bundled) |
| `src/room/shell.css`, `src/room.css` | the shell's furniture (`dsk-`, `tb-`, `top-`, `por-`, `win`, `bar`, `lt`) and the windows' own styles, each under its prefix |
| `src/apps/Presence.jsx` | her modes (2026-08-22) — narration / company / lucid dream: the picker, the knobs, the shelf (`var/library/`, hand a book to her / put it down) and the honest state; `PresenceChip` in the title bar |
| `src/apps/Senses.jsx` | her senses — the capability row, the hourly look, and (2026-08-22) **which eyes**: engine / aux VL model / the seam, with the `Sight — her eyes` knobs; `SensesChip` in the title bar |
| `src/apps/Librarians.jsx` | the quiet librarians (2026-08-22) — the aux doors' state, the index, the model pickers (live choices from the door), the soft-prompt knobs, a rebuild button; `AuxChip` in the title bar. (Not `Aux.jsx`: `aux` is a Windows reserved device name.) |
| `src/apps/titleChips.jsx` | the status chip a window wears in its bar (voice on/off, search engine, research tier, wardrobe making…, stage rung, room eye), drawn as kit Chips |
| `src/apps/knobs.jsx` | the tuning registry rendered — Settings, Voice and Search all mount it (one renderer, one truth) |
| `src/apps/looks.jsx` | the shared ledger-row renderer for Search and Research (his/hers chips, manual boxes) |
| `src/room/speech.js` | her voice in the room: sentence-queued `/v1/speak`, next fetched while the current plays |
| `src/room/tags.js` | her marks (`[MOOD:]` `[WEAR:]` `[SHOW:]`…) and voice tags: stripped for his eyes, kept for the speaker — and since 2026-08-25 ONE SIDE of a two-sided contract. `strip_for_record` in Python is the other, and both are held to `harness_tests/fixtures/strip_corpus.jsonl` by G-STRIP-EQUIVALENCE. **A widening here that does not also land in Python is the drift that put markup into 26% of her recorded turns.** Edit both, or the gate goes red the same day |
| `src/apps/panel.jsx` | `usePoll` / `Body` — every window is a fetch, a loading state, an ERROR state, and a body |
| `src/api.js` | every call the room makes to the gateway, in one file |

## Rules the gates hold

- **CSS ownership (G-ROOM-CSS):** a class an app uses is shared furniture (the committed list),
  its own prefix (`css:` in the registry), or part of a shared family rendered by exactly one
  module (`st-` knobs, `rsc-` looks, `ui-` the kit — and a `ui-` rule is written in
  `kit/kit.css` and nowhere else). `main.jsx`, `Chat.jsx` and every `room/*.jsx` are one owner,
  the shell. The `tc` title-chip family was retired in stage 2: title chips draw kit Chips.
  Two owners of one name is how the ledger's rows once rendered as 8px dots.
- **The design system keeps its promises (G-ROOM-TOKENS):** every text role meets contrast on
  every surface, every registry icon names a glyph, only `room/useMood.js` reads the live mood,
  and raw colour literals outside `kit/tokens.css` may only fall (a ratchet).
- **The kit renders (G-ROOM-KIT):** the real source is bundled and rendered under node — the
  kit parts, the top bar, the stack light, the minimise flight and the apps moved onto the kit.
- **The committed bundle is the source (G-ROOM-BUNDLE):** a source edit without a rebuild fails.
- **The two strippers are one contract (G-STRIP-EQUIVALENCE):** `room/tags.js::extractTags` and
  Python's `strip_for_record` are driven over the same corpus, asserting REMOVAL of every measured
  leak shape and SURVIVAL of every pass-through control, in both directions. The room strips for
  what he reads; Python strips for what she keeps. A shape added to one side only goes red.
- **No hardcoded ceilings, no hardcoded `max_tokens`** — the room sends what the knobs say.
