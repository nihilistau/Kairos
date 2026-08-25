# ui/ — the room

The React + Vite desktop you talk to her in. Built into `console/room/` (committed, so the
running stack needs no Node) and served by the gateway at `http://127.0.0.1:8800/room/`.

```bash
cd ui && npm ci && npm run build      # -> ../console/room/  (harness_tests/g_room_bundle.py proves the two agree)
npm run dev                           # dev server; proxies /v1 to :8800
```

## The framework (one registry, rendered)

| file | role |
|---|---|
| `src/Chat.jsx` | the conversation — and it is a CLIENT: it renders a stream, it decides nothing. The day read-back on mount (`GET /v1/day`, into an empty log only), and the line that hurt: **restored turns are DISPLAY, never re-sent as prompt** — sending them back cost an 11-minute cold turn. The off-the-record filter (turns made under the switch stay visible and stop being SENT once it is off — she must not carry the private hour in-context). Her thinking channel, rendered. Notice chips for engine errors and context trims — **never appended to her content**, because engine text in her mouth is its own leak. Up-arrow input history (2026-08-25) |
| `src/appRegistry.jsx` | every window, declared once: id, title, icon, size, component, CSS prefix, `dock` default, optional `TitleChip`. Registration is not aliveness: some apps are DARK by profile on companion (`[music].enabled = false`, `SP_GAMES` off) and their toolsets return `[]` — the icon renders over nothing. `docs/OFF-BY-DEFAULT.md` holds the arming condition |
| `src/main.jsx` | the shell: dock (filtered by `dockPrefs.js`), windows, taskbar, shutdown control |
| `src/dockPrefs.js` | which apps live in the dock — his call, live, per browser (localStorage); the apps launcher (⊞) is pinned |
| `src/apps/Presence.jsx` | her modes (2026-08-22) — narration / company / lucid dream: the picker, the knobs, the shelf (`var/library/`, hand a book to her / put it down) and the honest state; `PresenceChip` in the title bar |
| `src/apps/Senses.jsx` | her senses — the capability row, the hourly look, and (2026-08-22) **which eyes**: engine / aux VL model / the seam, with the `Sight — her eyes` knobs; `SensesChip` in the title bar |
| `src/apps/Librarians.jsx` | the quiet librarians (2026-08-22) — the aux doors' state, the index, the model pickers (live choices from the door), the soft-prompt knobs, a rebuild button; `AuxChip` in the title bar. (Not `Aux.jsx`: `aux` is a Windows reserved device name.) |
| `src/apps/titleChips.jsx` | the status chip a window wears in its bar (voice on/off, search engine, research tier, wardrobe making…, stage rung, room eye) |
| `src/apps/knobs.jsx` | the tuning registry rendered — Settings, Voice and Search all mount it (one renderer, one truth) |
| `src/apps/looks.jsx` | the shared ledger-row renderer for Search and Research (his/hers chips, manual boxes) |
| `src/room/speech.js` | her voice in the room: sentence-queued `/v1/speak`, next fetched while the current plays |
| `src/room/tags.js` | her marks (`[MOOD:]` `[WEAR:]` `[SHOW:]`…) and voice tags: stripped for his eyes, kept for the speaker — and since 2026-08-25 ONE SIDE of a two-sided contract. `strip_for_record` in Python is the other, and both are held to `harness_tests/fixtures/strip_corpus.jsonl` by G-STRIP-EQUIVALENCE. **A widening here that does not also land in Python is the drift that put markup into 26% of her recorded turns.** Edit both, or the gate goes red the same day |
| `src/apps/panel.jsx` | `usePoll` / `Body` — every panel is a fetch, a loading state, an ERROR state, and a body |
| `src/api.js` | every call the room makes to the gateway, in one file |

## Rules the gates hold

- **CSS ownership (G-ROOM-CSS):** a class an app uses is shared furniture (the committed list),
  its own prefix (`css:` in the registry), or part of a shared family rendered by exactly one
  module (`st-` knobs, `rsc-` looks, `tc` chips). Two owners of one name is how the ledger's rows
  once rendered as 8px dots.
- **The committed bundle is the source (G-ROOM-BUNDLE):** a source edit without a rebuild fails.
- **The two strippers are one contract (G-STRIP-EQUIVALENCE):** `room/tags.js::extractTags` and
  Python's `strip_for_record` are driven over the same corpus, asserting REMOVAL of every measured
  leak shape and SURVIVAL of every pass-through control, in both directions. The room strips for
  what he reads; Python strips for what she keeps. A shape added to one side only goes red.
- **No hardcoded ceilings, no hardcoded `max_tokens`** — the room sends what the knobs say.
