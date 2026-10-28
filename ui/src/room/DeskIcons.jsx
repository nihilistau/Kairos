import { useCallback, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import * as wm from '../windowManager.js'
import * as deskIcons from '../deskIcons.js'
import * as deskVisibility from '../deskVisibility.js'
import * as layout from '../desktopLayout.js'
import * as drag from './deskDrag.js'
import { APPS, FOLDERS, DOCK_HIDDEN_DEFAULT } from '../appRegistry.jsx'
import { Icon } from '../kit/icons.jsx'
import { FolderIcon, FolderPanel } from './Folder.jsx'

/* DESK ICONS — the apps, loose on the desktop, where he puts them.
 *
 * His ask (2026-09-23): "move the room icons from a side bar on the left so that they
 * are actual free desktop like icons". The left dock is gone; these replace it whole.
 *
 * DOUBLE-CLICK OPENS, single click selects — his call, and the one that makes this a
 * desktop rather than a column of buttons that happens to be draggable. A single-click
 * open cannot coexist with dragging: every drag would fire the click on release.
 *
 * WHAT IT DOES NOT OWN: which apps exist (the registry) and which earn a slot
 * (deskVisibility, still, unchanged — the apps launcher keeps working exactly as it did,
 * and hiding an icon here means the same thing it meant in the dock).
 *
 * CSS PREFIX `dsk-`. G-ROOM-CSS treats main.jsx, Chat.jsx and every room/*.jsx as ONE
 * owner called `shell`, so these classes are the shell's and need no registry row — the
 * rule they must satisfy is that no OTHER owner uses the name, and no app does.
 *
 * FOLDERS (2026-10-29, his approved mockup). Each group in FOLDERS is one folder icon here
 * (Folder.jsx); an app in a folder has no loose icon, an app in none (chat, or one he dragged
 * out) does. The folders take the first slots of the default column, the loose apps follow
 * (after the Apps window's undo, an empty folder is drawn only mid-drag, after the loose apps).
 * The bottom dock (Dock.jsx) is a drop zone of the same controller; it keeps an alias, so an
 * icon dropped on it goes back to where it was picked up.
 * Folder positions live in deskIcons.js under `folder:<id>`, so they clamp with everything
 * else. Every pick-up — icon, folder, an app in an open folder — goes through ONE controller,
 * deskDrag.js, and every folder (and its open panel) is a drop zone there.
 */
export const ICON_W = 88
export const ICON_H = 84
const COL_X = 18            // the column starts where the dock used to be
const TOP_Y = 16
const GAP_Y = 6

/* An id that has never been dragged gets a slot in the default column, in registry
 * order, wrapping to a second column before it would run off the bottom. Computed from
 * the CURRENT desktop rather than stored, so a new app on a short screen still lands
 * somewhere visible instead of below the fold. `h` is the desktop's own height (below
 * the top bar, above the taskbar); the 40 is slack, not a bar. */
function defaultPos(index, h) {
  const perCol = Math.max(1, Math.floor((h - TOP_Y - 40) / (ICON_H + GAP_Y)))
  const col = Math.floor(index / perCol)
  const row = index % perCol
  return { x: COL_X + col * (ICON_W + 10), y: TOP_Y + row * (ICON_H + GAP_Y) }
}

const within = (v, hi) => Math.max(0, Math.min(hi, v))
const inRect = (r, x, y) => !!r && x >= r.left && x < r.left + r.width && y >= r.top && y < r.top + r.height

/* NOTHING MAY BE STRANDED — the resize clamp, over every stored position (icons AND folders,
 * `folder:<id>`), against the desktop's own box W×H. Keeps the whole icon on screen. */
export function clampAll(W, H) {
  const maxX = Math.max(0, W - ICON_W - 8)
  const maxY = Math.max(0, H - ICON_H - 8)
  let moved = false
  for (const [id, p] of Object.entries(deskIcons.positions())) {
    const x = Math.min(p.x, maxX), y = Math.min(p.y, maxY)
    if (x !== p.x || y !== p.y) { deskIcons.place(id, x, y); moved = true }
  }
  return moved
}

/* DROP ZONES (deskDrag.js). A folder icon takes any app dropped on it; one already in that
 * folder is left where it is. The open panel sits above the icons (z 2) and takes a drop the
 * same way — so letting go of an app inside its own panel changes nothing. */
export function folderZone(folderId, hit, over, pinAt) {
  return { id: 'folder:' + folderId, z: 1, hit, over,
           accepts: (it) => it.kind === 'app',
           drop: (it) => {
             // A DROP-ONLY FOLDER STAYS WHERE IT WAS DRAWN (after the undo; see deskSlots): it was
             // placed after his column only for the drag, so the position he dropped on is pinned
             // before the app goes in — otherwise, no longer empty, it would take a default slot.
             const p = pinAt ? pinAt() : null
             if (p) deskIcons.place('folder:' + folderId, p.x, p.y)
             if (it.from !== folderId) layout.moveToFolder(it.id, folderId)
           } }
}
export function panelZone(folderId, hit) {
  return { id: 'panel:' + folderId, z: 2, hit,
           accepts: (it) => it.kind === 'app',
           drop: (it) => { if (it.from !== folderId) layout.moveToFolder(it.id, folderId) } }
}

/* Dropped on the bare desktop from a folder: a loose icon, centred under the pointer, inside
 * the desktop. `rect` is the layer's client rect; x, y are client coordinates. */
export function dropLoose(appId, x, y, rect) {
  deskIcons.place(appId,
    within(x - rect.left - ICON_W / 2, rect.width - ICON_W - 8),
    within(y - rect.top - ICON_H / 2, rect.height - ICON_H - 8))
  layout.moveToFolder(appId, null)
}

/* WHAT IS DRAWN, AND WHERE — one pure answer, read by the render and by a drop-only folder's
 * pin, so the two cannot disagree. `h` is the desktop's height; `dragging` whether a drag is in
 * flight. Returns { order: 'folders-first' | 'loose-first', folders: [{f, apps, key, pos,
 * dropOnly}], loose: [{app, pos}] }.
 *
 * BEFORE THE UNDO (and on a fresh browser) nothing changes: every folder, empty or not, takes the
 * first slots of the default column and the loose icons follow; every item uses a slot.
 *
 * AFTER "UNDO — PUT MY ICONS BACK" his restored column comes FIRST and keeps slots 0..n whatever
 * the folders do. A folder is drawn once something is in it, and an empty one only while a drag
 * is in flight (a drop target, `dropOnly`). An unplaced loose icon's slot is its index among
 * every shown app, so an app moving into a folder leaves a gap and no other icon moves. Folders
 * follow the whole column (non-empty ones first), and a folder with a position of its own takes
 * no slot — so pinning one (folderZone) never shifts another. */
export function deskSlots(h, dragging) {
  const hidden = deskVisibility.hiddenSet(DOCK_HIDDEN_DEFAULT)
  const byId = (id) => APPS.find(a => a.id === id)
  const looseApps = APPS.filter(a => (a.pinned || !hidden.has(a.id)) && layout.folderOf(a.id) === null)
  const all = FOLDERS.map(f => ({ f, apps: layout.appsIn(f.id).map(byId).filter(Boolean) }))
  const undone = layout.migrationUndone()
  let slot = 0
  const at = (key, always) => {
    const p = deskIcons.posOf(key)
    if (p && !always) return p
    const d = defaultPos(slot, h)
    slot++
    return p || d
  }
  const folder = (x) => ({ ...x, key: 'folder:' + x.f.id, pos: at('folder:' + x.f.id, !undone),
                           dropOnly: undone && !x.apps.length })
  const icon = (app) => ({ app, pos: at(app.id, true) })
  if (!undone) {
    const folders = all.map(folder)
    return { order: 'folders-first', folders, loose: looseApps.map(icon) }
  }
  // his column: an unplaced icon's slot is its place among ALL shown apps, so one that goes into
  // a folder leaves a gap and nothing else moves; the folders start after the whole column
  const shown = APPS.filter(a => a.pinned || !hidden.has(a.id))
  const loose = looseApps.map(app => ({ app, pos: deskIcons.posOf(app.id) || defaultPos(shown.indexOf(app), h) }))
  slot = shown.length
  // non-empty folders first, so a drag's drop-only ones never shift a folder that is always drawn
  const folders = [...all.filter(x => x.apps.length), ...(dragging ? all.filter(x => !x.apps.length) : [])].map(folder)
  return { order: 'loose-first', folders, loose }
}

/* Where a drop-only folder is drawn right now (mid-drag), or null when it is not one. */
export function dropOnlyPos(folderId, h) {
  const x = deskSlots(h, true).folders.find(y => y.f.id === folderId && y.dropOnly)
  return x ? x.pos : null
}

export default function DeskIcons() {
  // third arguments: the server snapshot (G-ROOM-KIT draws this under react-dom/server)
  useSyncExternalStore(deskIcons.subscribe, deskIcons.getVersion, deskIcons.getVersion)
  useSyncExternalStore(deskVisibility.subscribe, deskVisibility.getVersion, deskVisibility.getVersion)
  useSyncExternalStore(layout.onChange, layout.getVersion, layout.getVersion)
  const dragging = useSyncExternalStore(drag.subscribe, drag.dragging, drag.dragging)
  const windows = useSyncExternalStore(wm.subscribe, wm.getWindows, wm.getWindows)
  const openIds = new Set(windows.filter(w => !w.minimized).map(w => w.appId))

  const [sel, setSel] = useState(null)
  const [dragId, setDragId] = useState(null)
  const [openF, setOpenF] = useState(null)       // the one open folder's id
  const [dropOn, setDropOn] = useState(null)     // the folder a drag is over
  const [ghost, setGhost] = useState(null)       // an app being carried out of a panel
  const layer = useRef(null)
  const foldEls = useRef({})
  const panelEl = useRef(null)
  // THE DESKTOP'S BOX, measured (final review, I1). These clamps worked in window
  // coordinates minus a taskbar height; the desktop now starts below the top bar too, so
  // a low icon's label went under the taskbar. .dsk-layer fills .desktop exactly, so its
  // client box IS the room an icon has. Before the first measure: the window.
  const [area, setArea] = useState(() => ({ w: window.innerWidth, h: window.innerHeight }))
  const areaRef = useRef(area)
  areaRef.current = area
  const slots = deskSlots(area.h, dragging)

  // THE UPGRADE, once per browser: his old positions are kept for the Apps window's undo
  useEffect(() => { layout.migrateOnce() }, [])

  /* NOTHING MAY BE STRANDED. A window shrunk since he arranged these — or a laptop
   * after a desktop — can leave an icon beyond the right or bottom edge with no way to
   * reach it. Clamp on resize, keeping the whole icon on screen. The Portrait does the
   * same thing for the same reason; that one only had to save a person, this has to
   * save the way into every app. */
  useLayoutEffect(() => {
    const clamp = () => {
      const el = layer.current
      if (!el) return false
      const W = el.clientWidth, H = el.clientHeight
      setArea(a => (a.w === W && a.h === H ? a : { w: W, h: H }))
      return clampAll(W, H)
    }
    // measured on mount (the default column needs the height); positions are only
    // moved on a resize, as before — a load never rewrites his arrangement
    const el = layer.current
    if (el) setArea({ w: el.clientWidth, h: el.clientHeight })
    window.addEventListener('resize', clamp)
    return () => window.removeEventListener('resize', clamp)
  }, [])

  // every folder icon is a drop zone, for as long as the desktop is up
  useEffect(() => {
    const offs = FOLDERS.map(f => drag.addZone(folderZone(f.id,
      (x, y) => inRect(foldEls.current[f.id] && foldEls.current[f.id].getBoundingClientRect(), x, y),
      (on) => setDropOn(d => (on ? f.id : (d === f.id ? null : d))),
      () => dropOnlyPos(f.id, areaRef.current.h))))
    return () => offs.forEach(off => off())
  }, [])
  // ...and so is the open panel, above them
  useEffect(() => {
    if (!openF) return undefined
    return drag.addZone(panelZone(openF,
      (x, y) => inRect(panelEl.current && panelEl.current.getBoundingClientRect(), x, y)))
  }, [openF])

  const bounds = () => {
    const el = layer.current
    const W = el ? el.clientWidth : area.w, H = el ? el.clientHeight : area.h
    return { maxX: Math.max(0, W - ICON_W - 8), maxY: Math.max(0, H - ICON_H - 8) }
  }

  // A loose icon or a folder: it moves with the pointer. Escape mid-drag puts it back.
  const onDown = (key, item, pos) => (e) => {
    if (e.button !== 0) return
    setSel(key)
    const b = bounds()
    drag.begin(item, e, {
      onStart: () => setDragId(key),
      onMove: (dx, dy) => deskIcons.place(key, within(pos.x + dx, b.maxX), within(pos.y + dy, b.maxY)),
      onCancel: () => deskIcons.place(key, pos.x, pos.y),
      // the dock keeps an alias: the icon itself goes back where it was picked up
      onZone: (z) => { if (z.alias) deskIcons.place(key, pos.x, pos.y) },
      onEnd: () => setDragId(null),
    })
  }

  // An app inside an open panel: a ghost follows the pointer; the panel stays open.
  const onItemDown = (folderId) => (app) => (e) => {
    if (e.button !== 0) return
    const rect = () => (layer.current ? layer.current.getBoundingClientRect()
                                      : { left: 0, top: 0, width: area.w, height: area.h })
    drag.begin({ kind: 'app', id: app.id, from: folderId }, e, {
      onStart: () => setDragId(app.id),
      onMove: (dx, dy, x, y) => { const r = rect(); setGhost({ app, x: x - r.left - ICON_W / 2, y: y - r.top - ICON_H / 2 }) },
      onDrop: (x, y) => dropLoose(app.id, x, y, rect()),
      onEnd: () => { setGhost(null); setDragId(null) },
    })
  }

  const openRef = useRef(null)
  openRef.current = openF
  const closePanel = useCallback((why) => {
    // Escape hands focus back to the folder it came from; a click elsewhere keeps its own
    const cur = openRef.current
    if (why === 'key' && cur && foldEls.current[cur]) foldEls.current[cur].focus()
    setOpenF(null)
  }, [])
  const openApp = (app) => { setOpenF(null); wm.open(app.id, app) }

  // the open panel sits by its folder as DRAWN (deskSlots) — a folder not drawn has no panel
  const open = openF && slots.folders.find(x => x.f.id === openF)
  const folderIcon = ({ f, apps, key, pos }) => {
    return (
      <FolderIcon key={key} folder={f} apps={apps} pos={pos} w={ICON_W}
                  sel={sel === key} open={openF === f.id} drop={dropOn === f.id} drag={dragId === key}
                  btnRef={el => { foldEls.current[f.id] = el }}
                  onDown={onDown(key, { kind: 'folder', id: key }, pos)}
                  onOpen={() => setOpenF(f.id)} />
    )
  }
  return (
    <div className="dsk-layer" ref={layer} onMouseDown={(e) => { if (e.target === e.currentTarget) setSel(null) }}>
      {slots.order === 'folders-first' ? slots.folders.map(folderIcon) : null}
      {slots.loose.map(({ app, pos }) => {
        return (
          <button key={app.id}
                  className={'dsk-icon'
                             + (sel === app.id ? ' dsk-sel' : '')
                             + (openIds.has(app.id) ? ' dsk-open' : '')
                             + (dragId === app.id ? ' dsk-drag' : '')}
                  style={{ left: pos.x, top: pos.y, width: ICON_W }}
                  title={app.blurb}
                  onMouseDown={onDown(app.id, { kind: 'app', id: app.id, from: null }, pos)}
                  onDoubleClick={() => wm.open(app.id, app)}
                  /* KEYBOARD IS NOT AN AFTERTHOUGHT: a double-click is unreachable
                     from the keyboard, so Enter opens the selected icon. */
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); wm.open(app.id, app) } }}>
            <span className="dsk-tile"><Icon name={app.icon} size={26} /></span>
            <span className="dsk-lb">{app.title}</span>
          </button>
        )
      })}
      {slots.order === 'loose-first' ? slots.folders.map(folderIcon) : null}
      {open ? (
        <FolderPanel folder={open.f} apps={open.apps} area={area} iconW={ICON_W} iconH={ICON_H}
                     pos={open.pos}
                     panelRef={panelEl} folderEl={() => foldEls.current[open.f.id]}
                     onClose={closePanel} onOpenApp={openApp} onItemDown={onItemDown(open.f.id)} />
      ) : null}
      {ghost ? (
        <span className="dsk-icon dsk-drag dsk-fold-ghost" aria-hidden="true"
              style={{ left: ghost.x, top: ghost.y, width: ICON_W }}>
          <span className="dsk-tile"><Icon name={ghost.app.icon} size={26} /></span>
          <span className="dsk-lb">{ghost.app.title}</span>
        </span>
      ) : null}
    </div>
  )
}
