/* appRegistry — apps described ONCE, for both a human and (later) for her.
 *
 * OpenRoom's appRegistry.ts is the spine of that codebase and the idea worth
 * taking: a static table of {id, title, icon, size} plus convention-driven
 * discovery, so adding an app touches one file and no wiring.
 *
 * Each app here is a VIEW ONTO SOMETHING THAT ALREADY EXISTS — the board, the
 * memory registry, her senses, the tool surface. The room does not own state. It
 * is a window onto the harness, which is the whole reason it can be additive: the
 * old console pages keep working, unchanged, because nothing moved.
 */
import Senses from './apps/Senses.jsx'
import Tools from './apps/Tools.jsx'
import Board from './apps/Board.jsx'
import Memory from './apps/Memory.jsx'
import Decisions from './apps/Decisions.jsx'
import Room from './apps/Room.jsx'
import Presence from './apps/Presence.jsx'
import Librarians from './apps/Librarians.jsx'   // not Aux.jsx: 'aux' is a Windows reserved device name
import Music from './apps/Music.jsx'
import Journal from './apps/Journal.jsx'
import Files from './apps/Files.jsx'
import Ledger from './apps/Ledger.jsx'
import Stage from './apps/Stage.jsx'
import Games from './apps/Games.jsx'
import Wardrobe from './apps/Wardrobe.jsx'
import Settings from './apps/Settings.jsx'
import Setup from './apps/Setup.jsx'
import Agency from './apps/Agency.jsx'
import Research from './apps/Research.jsx'
import Search from './apps/Search.jsx'
import Voice from './apps/Voice.jsx'
import Apps from './apps/Apps.jsx'
import { VoiceChip, SearchChip, ResearchChip, WardrobeChip, StageChip,
         MusicChip, GamesChip, RoomChip, PresenceChip, AuxChip, SensesChip } from './apps/titleChips.jsx'

/* CSS OWNERSHIP. `css` is the class-name prefix this app owns, and it is not
 * decoration — G-ROOM-CSS reads it. The ledger's first cut called a row `.led`,
 * which room.css already used for the 8px status dot in the header, so every row
 * rendered as an 8x8 circle with overflow:hidden and clipped itself to nothing.
 * One name, two meanings, and the one that ran was the other one.
 *
 * The rule: a class an app uses must be SHARED furniture (the committed list in
 * the gate), or carry that app's prefix. A name used by two owners and blessed by
 * neither is the collision, and it fails.
 */
/* DOCK MEMBERSHIP (2026-08-21, his call): `dock: false` starts an app out of the
 * sidebar — music and games, his ask, same day — and the APPS LAUNCHER is where
 * he changes his mind live (dockPrefs.js, per browser). `pinned: true` means the
 * launcher itself: never hideable, because it is the way back.
 *
 * TITLE CHIPS: `TitleChip` is a tiny component the window chrome renders beside
 * the title — a glance at state/provider (titleChips.jsx). Optional per app. */
export const APPS = [
  { id: 'apps', title: 'apps', icon: '⊞', w: 480, h: 520, Component: Apps, css: 'ap',
    pinned: true,
    blurb: 'every window there is, and which of them live in this dock — change it live' },
  { id: 'settings', title: 'settings', icon: '⚙', w: 660, h: 620, Component: Settings, css: 'st',
    blurb: 'every knob, grouped — voice, search, research, kairos, the lot. live ones apply on the next call' },
  { id: 'setup', title: 'setup', icon: '⚑', w: 660, h: 640, Component: Setup, css: 'su',
    blurb: 'what is configured and what is not — your endpoint, your keys, her face, the model cards. reads only' },
  { id: 'voice', title: 'voice', icon: '🎙', w: 560, h: 460, Component: Voice, css: 'vc',
    TitleChip: VoiceChip,
    blurb: 'her voice — on/off, provider, who speaks. live, and a button to hear it' },
  { id: 'search', title: 'search', icon: '🔍', w: 640, h: 560, Component: Search, css: 'sr',
    TitleChip: SearchChip,
    blurb: 'web searches, hers and yours — and a box to run your own' },
  { id: 'wardrobe', title: 'wardrobe', icon: '👗', w: 620, h: 560, Component: Wardrobe, css: 'wr',
    TitleChip: WardrobeChip,
    blurb: 'what she is wearing, what else she could be, and the moments she can show you' },
  { id: 'senses', title: 'senses',  icon: '👁', w: 560, h: 520, Component: Senses, css: 'sns',
    TitleChip: SensesChip,
    blurb: 'what she can see and hear, and what the room has looked like' },
  { id: 'tools',  title: 'tools',   icon: '🛠', w: 720, h: 520, Component: Tools, css: 'tl',
    blurb: 'every tool she has, by family and by risk' },
  { id: 'board',  title: 'board',   icon: '📋', w: 560, h: 440, Component: Board, css: 'bd',
    blurb: 'notes, reminders, things either of you wants kept in view' },
  { id: 'memory', title: 'memory',  icon: '🧠', w: 700, h: 560, Component: Memory, css: 'mem',
    blurb: 'what she knows — live rows and retired ones, and re-filing them' },
  { id: 'decisions', title: 'decisions', icon: '⚖', w: 620, h: 540, Component: Decisions, css: 'dec',
    blurb: 'what is waiting on you' },
  { id: 'music',  title: 'music',   icon: '♪', w: 560, h: 520, Component: Music, css: 'mus',
    dock: false, TitleChip: MusicChip,
    blurb: 'the record player — hers to reach for too' },
  { id: 'agency', title: 'her own time', icon: '◈', w: 620, h: 560, Component: Agency, css: 'ag',
    blurb: 'everything she did while you were away — hers, and not editable' },
  { id: 'research', title: 'research', icon: '⌕', w: 640, h: 560, Component: Research, css: 'rsc',
    TitleChip: ResearchChip,
    blurb: 'the paid tier, hers and yours — titles expand to the returned text' },
  { id: 'journal',title: 'journal', icon: '📔', w: 600, h: 500, Component: Journal, css: 'jr',
    blurb: 'what she writes at the end of a day — hers, you can only read it' },
  { id: 'files',  title: 'files',   icon: '📁', w: 620, h: 500, Component: Files, css: 'fl',
    blurb: 'the tree you share — drag something in and she can read it' },
  // THE LEDGER is the one app that is not purely a window onto the harness — it is
  // the only place the plan, the parked and the noticed are written down at all.
  // Wide and tall by default because it is meant to be read, not glanced at.
  { id: 'stage',  title: 'stage',   icon: '🎭', w: 620, h: 560, Component: Stage, css: 'stg',
    TitleChip: StageChip,
    blurb: 'the scene, the rung it is on, and a stop that is always one click' },
  { id: 'games',  title: 'games',   icon: '♟', w: 560, h: 640, Component: Games, css: 'gm',
    dock: false, TitleChip: GamesChip,
    blurb: 'a board you both touch — the rules belong to the engine, not the page' },
  { id: 'ledger', title: 'ledger',  icon: '🗂', w: 760, h: 620, Component: Ledger, css: 'lgr',
    blurb: 'the plan, what we parked, and everything noticed and not touched' },
  { id: 'room',   title: 'the room',icon: '🏠', w: 560, h: 460, Component: Room, css: 'rm',
    TitleChip: RoomChip,
    blurb: 'her hourly notes on the room — the eye waits for quiet before it looks' },
  { id: 'presence', title: 'presence', icon: '☾', w: 600, h: 560, Component: Presence, css: 'prs',
    TitleChip: PresenceChip,
    blurb: 'narration, company, lucid dream — her modes of being there out loud, and the shelf she reads from' },
  { id: 'librarians', title: 'librarians', icon: '📚', w: 620, h: 560, Component: Librarians, css: 'lib',
    TitleChip: AuxChip,
    blurb: 'the quiet librarians — the small CPU models that embed, retrieve, judge and read for her; never her voice' },
]

export const byId = (id) => APPS.find(a => a.id === id)

/* The ids whose registry row starts them out of the dock — dockPrefs' defaults
 * until he touches a toggle, at which point his saved list rules. */
export const DOCK_HIDDEN_DEFAULT = APPS.filter(a => a.dock === false).map(a => a.id)
