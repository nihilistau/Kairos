/* appRegistry — apps described ONCE, for both a human and (later) for her.
 *
 * OpenRoom's appRegistry.ts is the spine of that codebase and the idea worth
 * taking: a static table of {id, title, icon, size} plus convention-driven
 * discovery, so adding an app touches one file and no wiring.
 *
 * icon: a glyph name in kit/icons.jsx (G-ROOM-TOKENS checks it exists).
 *
 * Each app here is a VIEW ONTO SOMETHING THAT ALREADY EXISTS — the board, the
 * memory registry, her senses, the tool surface. The room does not own state. It
 * is a window onto the harness, which is the whole reason it can be additive: the
 * old console pages keep working, unchanged, because nothing moved.
 */
import Senses from './apps/Senses.jsx'
import Tools from './apps/Tools.jsx'
import Board from './apps/Board.jsx'
import BodyPanel from './apps/Body.jsx'
import House from './apps/House.jsx'
import Memory from './apps/Memory.jsx'
import Decisions from './apps/Decisions.jsx'
import Room from './apps/Room.jsx'
import Presence from './apps/Presence.jsx'
import Librarians from './apps/Librarians.jsx'   // not Aux.jsx: 'aux' is a Windows reserved device name
import Models from './apps/Models.jsx'
import Music from './apps/Music.jsx'
import Journal from './apps/Journal.jsx'
import Story from './apps/Story.jsx'
import Files from './apps/Files.jsx'
import Ledger from './apps/Ledger.jsx'
import Stage from './apps/Stage.jsx'
import Games from './apps/Games.jsx'
import Wardrobe from './apps/Wardrobe.jsx'
import Settings from './apps/Settings.jsx'
import Launch from './apps/Launch.jsx'
import Setup from './apps/Setup.jsx'
import Agency from './apps/Agency.jsx'
import Research from './apps/Research.jsx'
import Search from './apps/Search.jsx'
import Voice from './apps/Voice.jsx'
import Apps from './apps/Apps.jsx'
import Chat from './Chat.jsx'
import RoomView from './room/RoomView.jsx'
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
 * sidebar — chat only now (music and games had it too until the folders, 2026-10-29) — and the APPS LAUNCHER is where
 * he changes his mind live (deskVisibility.js, per browser). `pinned: true` means the
 * launcher itself: never hideable, because it is the way back.
 *
 * TITLE CHIPS: `TitleChip` is a tiny component the window chrome renders beside
 * the title — a glance at state/provider (titleChips.jsx). Optional per app. */
export const APPS = [
  /* CHAT IS A WINDOW (2026-09-23, his ask). It was a fixed div in the middle of the
     desktop — the one thing there that could not be moved, once the icons came out of
     the dock and everything else was draggable. `dock: false` because it opens itself
     on a fresh browser (main.jsx) and an icon for the thing already on screen is
     clutter; the launcher can put one on the desktop if he wants it back.

     `css: 'chat'` claims the prefix room.css has used for the conversation since the
     shell was built — G-ROOM-CSS wants one owner per name, and this is the owner. */
  { id: 'chat', title: 'Chat', icon: 'chat', w: 560, h: 560, Component: Chat, css: 'chat', dock: false,
    blurb: 'the conversation — her and him, the only thing in this room with contrast' },
  /* THE ROOM'S WEATHER, FRAMED. The full-bleed backdrop stays exactly as it was; this
     is a second render of the same `describeRoom` output with the reading written
     underneath. Closing it costs a view, never the ambience. */
  /* AN ICON BY DEFAULT, unlike chat: chat opens itself, so an icon for it is clutter,
     but this one has no other way in and the launcher is a poor place to hide the
     thing he asked to be a window. */
  { id: 'roomview', group: 'home', title: 'The view', icon: 'roomview', w: 520, h: 420, Component: RoomView, css: 'rv',
    blurb: "the room's weather in a frame — phase, her mood, whether anyone is about" },
  { id: 'apps', group: 'system', title: 'Apps', icon: 'apps', w: 480, h: 520, Component: Apps, css: 'ap',
    pinned: true,
    blurb: 'every window there is, and which of them live on this desktop — change it live' },
  { id: 'settings', group: 'system', title: 'Settings', icon: 'settings', w: 780, h: 640, Component: Settings, css: 'st',
    blurb: 'every knob in six areas, with search — the ones that apply live. live ones apply on the next call' },
  { id: 'launch', group: 'system', title: 'Launch', icon: 'launch', w: 680, h: 680, Component: Launch, css: 'ln',
    blurb: 'her model and kernels, saved setups, and a restart that applies them — what runs now vs what is saved' },
  /* EVERY MODEL JOB IN ONE WINDOW (2026-10-29, mockup A): her mind, the librarian, the
     memory index, her ears, her voice, her eyes — what each runs on, whether it is loaded,
     a picker where the job can switch live, and a Test. The taskbar strip opens it. */
  { id: 'models', group: 'system', title: 'Models', icon: 'models', w: 640, h: 560, Component: Models, css: 'mdl',
    blurb: 'every model she runs on — what is loaded, what is missing, a picker and a test for each' },
  { id: 'setup', group: 'system', title: 'Setup', icon: 'setup', w: 660, h: 640, Component: Setup, css: 'su',
    blurb: 'what is configured and what is not — your endpoint, your keys, her face, the model cards. reads only' },
  { id: 'voice', group: 'system', title: 'Voice', icon: 'voice', w: 560, h: 460, Component: Voice, css: 'vc',
    TitleChip: VoiceChip,
    blurb: 'her voice — on/off, provider, who speaks. live, and a button to hear it' },
  { id: 'search', group: 'lookup', title: 'Search', icon: 'search', w: 640, h: 560, Component: Search, css: 'sr',
    TitleChip: SearchChip,
    blurb: 'web searches, hers and yours — and a box to run your own' },
  { id: 'wardrobe', group: 'her', title: 'Wardrobe', icon: 'wardrobe', w: 620, h: 560, Component: Wardrobe, css: 'wr',
    TitleChip: WardrobeChip,
    blurb: 'what she is wearing, what else she could be, and the moments she can show you' },
  { id: 'senses', group: 'home', title: 'Senses',  icon: 'senses', w: 560, h: 520, Component: Senses, css: 'sns',
    TitleChip: SensesChip,
    blurb: 'what she can see and hear, and what the room has looked like' },
  { id: 'tools', group: 'system', title: 'Tools',   icon: 'tools', w: 720, h: 520, Component: Tools, css: 'tl',
    blurb: 'every tool she has, by family and by risk' },
  { id: 'board', group: 'lookup', title: 'Board',   icon: 'board', w: 560, h: 440, Component: Board, css: 'bd',
    blurb: 'notes, reminders, things either of you wants kept in view' },
  { id: 'body', group: 'home', title: 'Body',    icon: 'body', w: 640, h: 600, Component: BodyPanel, css: 'tel',
    blurb: 'his heart and his movement, live — and the exact sentence she is handed about them' },
  { id: 'house', group: 'home', title: 'House',   icon: 'house', w: 620, h: 460, Component: House, css: 'ha',
    blurb: 'is Home Assistant reachable, and what of it reaches her' },
  { id: 'memory', group: 'her', title: 'Memory',  icon: 'memory', w: 700, h: 560, Component: Memory, css: 'mem',
    blurb: 'what she knows — live rows and retired ones, and re-filing them' },
  { id: 'decisions', group: 'her', title: 'Decisions', icon: 'decisions', w: 620, h: 540, Component: Decisions, css: 'dec',
    blurb: 'what is waiting on you' },
  { id: 'music', group: 'together', title: 'Music',   icon: 'music', w: 560, h: 520, Component: Music, css: 'mus',
    TitleChip: MusicChip,
    blurb: 'the record player — hers to reach for too' },
  { id: 'agency', group: 'her', title: 'Her own time', icon: 'agency', w: 620, h: 560, Component: Agency, css: 'ag',
    blurb: 'everything she did while you were away — hers, and not editable' },
  { id: 'research', group: 'lookup', title: 'Research', icon: 'research', w: 640, h: 560, Component: Research, css: 'rsc',
    TitleChip: ResearchChip,
    blurb: 'the paid tier, hers and yours — titles expand to the returned text' },
  { id: 'journal', group: 'her', title: 'Journal', icon: 'journal', w: 600, h: 500, Component: Journal, css: 'jr',
    blurb: 'what she writes at the end of a day — hers, you can only read it' },
  { id: 'story', group: 'together', title: 'Story',   icon: 'story', w: 720, h: 580, Component: Story, css: 'sty',
    blurb: 'her prefix line by line, the chapters and their folds, the lanes — and the backup receipt' },
  { id: 'files', group: 'lookup', title: 'Files',   icon: 'files', w: 620, h: 500, Component: Files, css: 'fl',
    blurb: 'the tree you share — drag something in and she can read it' },
  // THE LEDGER is the one app that is not purely a window onto the harness — it is
  // the only place the plan, the parked and the noticed are written down at all.
  // Wide and tall by default because it is meant to be read, not glanced at.
  { id: 'stage', group: 'together', title: 'Stage',   icon: 'stage', w: 620, h: 560, Component: Stage, css: 'stg',
    TitleChip: StageChip,
    blurb: 'the scene, the rung it is on, and a stop that is always one click' },
  { id: 'games', group: 'together', title: 'Games',   icon: 'games', w: 560, h: 640, Component: Games, css: 'gm',
    TitleChip: GamesChip,
    blurb: 'a board you both touch — the rules belong to the engine, not the page' },
  { id: 'ledger', group: 'system', title: 'Ledger',  icon: 'ledger', w: 760, h: 620, Component: Ledger, css: 'lgr',
    blurb: 'the plan, what we parked, and everything noticed and not touched' },
  { id: 'room', group: 'home', title: 'The room',icon: 'room', w: 560, h: 460, Component: Room, css: 'rm',
    TitleChip: RoomChip,
    blurb: 'her hourly notes on the room — the eye waits for quiet before it looks' },
  { id: 'presence', group: 'her', title: 'Presence', icon: 'presence', w: 600, h: 560, Component: Presence, css: 'prs',
    TitleChip: PresenceChip,
    blurb: 'narration, company, lucid dream — her modes of being there out loud, and the shelf she reads from' },
  { id: 'librarians', group: 'lookup', title: 'Librarians', icon: 'librarians', w: 620, h: 560, Component: Librarians, css: 'lib',
    TitleChip: AuxChip,
    blurb: 'the quiet librarians — the small CPU models that embed, retrieve, judge and read for her; never her voice' },
]

/* DESKTOP FOLDERS (2026-10-29): `group` is the folder an app starts in; chat has none (it is
 * the conversation, never tucked away). The layout store (desktopLayout.js) reads this as the
 * default and keeps his own moves as overrides, so a new app lands in its folder on its own. */
export const FOLDERS = [
  { id: 'her', title: 'Her' },
  { id: 'together', title: 'Together' },
  { id: 'lookup', title: 'Look it up' },
  { id: 'home', title: 'Home' },
  { id: 'system', title: 'System' },
]

/* THE DOCK'S FIRST FILL: aliases, in this order. Ids the registry does not have are skipped. */
export const DEFAULT_DOCK = ['chat', 'voice', 'music', 'search', 'memory', 'models']

export const byId = (id) => APPS.find(a => a.id === id)

/* The ids whose registry row starts them out of the dock — deskVisibility' defaults
 * until he touches a toggle, at which point his saved list rules. */
export const DOCK_HIDDEN_DEFAULT = APPS.filter(a => a.dock === false).map(a => a.id)
