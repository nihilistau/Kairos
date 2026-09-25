import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import * as wm from '../windowManager.js'
import * as deskIcons from '../deskIcons.js'
import * as dockPrefs from '../dockPrefs.js'
import { APPS, DOCK_HIDDEN_DEFAULT } from '../appRegistry.jsx'
import { Icon } from '../kit/icons.jsx'

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
 * (dockPrefs, still, unchanged — the apps launcher keeps working exactly as it did,
 * and hiding an icon here means the same thing it meant in the dock).
 *
 * CSS PREFIX `dsk-`. G-ROOM-CSS treats main.jsx, Chat.jsx and every room/*.jsx as ONE
 * owner called `shell`, so these classes are the shell's and need no registry row — the
 * rule they must satisfy is that no OTHER owner uses the name, and no app does.
 */
const ICON_W = 88
const ICON_H = 84
const COL_X = 18            // the column starts where the dock used to be
const TOP_Y = 16
const GAP_Y = 6

/* An id that has never been dragged gets a slot in the default column, in registry
 * order, wrapping to a second column before it would run off the bottom. Computed from
 * the CURRENT viewport rather than stored, so a new app on a short screen still lands
 * somewhere visible instead of below the fold. */
function defaultPos(index) {
  const perCol = Math.max(1, Math.floor((window.innerHeight - TOP_Y - 120) / (ICON_H + GAP_Y)))
  const col = Math.floor(index / perCol)
  const row = index % perCol
  return { x: COL_X + col * (ICON_W + 10), y: TOP_Y + row * (ICON_H + GAP_Y) }
}

export default function DeskIcons() {
  useSyncExternalStore(deskIcons.subscribe, deskIcons.getVersion)
  useSyncExternalStore(dockPrefs.subscribe, dockPrefs.getVersion)
  const windows = useSyncExternalStore(wm.subscribe, wm.getWindows)
  const openIds = new Set(windows.filter(w => !w.minimized).map(w => w.appId))
  const hidden = dockPrefs.hiddenSet(DOCK_HIDDEN_DEFAULT)
  const shown = APPS.filter(a => a.pinned || !hidden.has(a.id))

  const [sel, setSel] = useState(null)
  const [dragId, setDragId] = useState(null)
  const drag = useRef(null)

  /* NOTHING MAY BE STRANDED. A window shrunk since he arranged these — or a laptop
   * after a desktop — can leave an icon beyond the right or bottom edge with no way to
   * reach it. Clamp on resize, keeping the whole icon on screen. The Portrait does the
   * same thing for the same reason; that one only had to save a person, this has to
   * save the way into every app. */
  useEffect(() => {
    const clamp = () => {
      const maxX = Math.max(0, window.innerWidth - ICON_W - 8)
      const maxY = Math.max(0, window.innerHeight - ICON_H - 46)   // taskbar
      let moved = false
      for (const [id, p] of Object.entries(deskIcons.positions())) {
        const x = Math.min(p.x, maxX), y = Math.min(p.y, maxY)
        if (x !== p.x || y !== p.y) { deskIcons.place(id, x, y); moved = true }
      }
      return moved
    }
    window.addEventListener('resize', clamp)
    return () => window.removeEventListener('resize', clamp)
  }, [])

  const onDown = (app, pos) => (e) => {
    if (e.button !== 0) return
    setSel(app.id)
    const start = { mx: e.clientX, my: e.clientY, ...pos, moved: false }
    drag.current = start
    const move = (ev) => {
      const d = drag.current
      if (!d) return
      const dx = ev.clientX - d.mx, dy = ev.clientY - d.my
      // A few pixels of slack: without it, the tremor in a double-click registers as a
      // drag and the icon creeps across the desktop every time he opens something.
      if (!d.moved && Math.abs(dx) < 4 && Math.abs(dy) < 4) return
      if (!d.moved) { d.moved = true; setDragId(app.id) }
      deskIcons.place(app.id,
        Math.max(0, Math.min(window.innerWidth - ICON_W - 8, d.x + dx)),
        Math.max(0, Math.min(window.innerHeight - ICON_H - 46, d.y + dy)))
    }
    const up = () => {
      drag.current = null
      setDragId(null)
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
      document.body.classList.remove('resizing')
    }
    document.body.classList.add('resizing')      // kill text selection mid-drag
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
  }

  return (
    <div className="dsk-layer" onMouseDown={(e) => { if (e.target === e.currentTarget) setSel(null) }}>
      {shown.map((app, i) => {
        const pos = deskIcons.posOf(app.id) || defaultPos(i)
        return (
          <button key={app.id}
                  className={'dsk-icon'
                             + (sel === app.id ? ' dsk-sel' : '')
                             + (openIds.has(app.id) ? ' dsk-open' : '')
                             + (dragId === app.id ? ' dsk-drag' : '')}
                  style={{ left: pos.x, top: pos.y, width: ICON_W }}
                  title={app.blurb}
                  onMouseDown={onDown(app, pos)}
                  onDoubleClick={() => wm.open(app.id, app)}
                  /* KEYBOARD IS NOT AN AFTERTHOUGHT: a double-click is unreachable
                     from the keyboard, so Enter opens the selected icon. */
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); wm.open(app.id, app) } }}>
            <span className="dsk-tile"><Icon name={app.icon} size={26} /></span>
            <span className="dsk-lb">{app.title}</span>
          </button>
        )
      })}
    </div>
  )
}
