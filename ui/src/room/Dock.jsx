import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import * as wm from '../windowManager.js'
import * as layout from '../desktopLayout.js'
import * as drag from './deskDrag.js'
import { APPS } from '../appRegistry.jsx'
import { Icon } from '../kit/icons.jsx'

/* THE DOCK (2026-10-29, his approved mockup "desktop-groups-v2": the same dock in both cards).
 *
 * Bottom centre, above the taskbar: a short row of the apps he reaches for most (six to start —
 * chat, voice, music, search, memory, models — eight at most, one at least). The entries are
 * ALIASES (desktopLayout.js): docking never takes an app out of its folder or off the desktop.
 *
 * WHAT IT DOES:
 *   - SINGLE CLICK OPENS — unlike a desk icon, nothing here is selected first. An app with a
 *     window is focused or restored by wm.open, never opened twice. Enter and Space too.
 *   - A DOT under every app with a window, minimised included.
 *   - MAGNIFY: the tile under the pointer grows (CSS transforms only, peak 1.45×), its
 *     neighbours ease (1.2×), and it glows in her mood colour. Phone width: no magnify.
 *   - DRAG: an app from the desktop or a folder dropped on the dock is added where it lands;
 *     an entry dragged along the dock moves; dragged off onto anything else it leaves the dock.
 *     The ninth and the last are refused with a short line beside the dock. One controller
 *     for all of it — deskDrag.js — so a click and a drop mean the same here as on the desktop.
 *   - IT SLIDES AWAY while a window is maximised (at phone width, where every window fills
 *     the desktop, while any window shows) and comes back while the pointer rests at the
 *     bottom edge, while it is hovered or holds focus, and while a drag is in flight.
 *   - ABOVE NORMAL WINDOWS: it is mounted outside .desktop (main.jsx), whose stacking context
 *     holds every window, with a z between the desktop and the taskbar (shell.css).
 *
 * CSS prefix `dock-`, a shell family registered in G-ROOM-CSS §4d (this file draws it alone).
 */
export const HINT = layout.DOCK_HINT   // the store's words; the dock shows r.why as it comes
export const EDGE = 6          // px from the bottom edge that call a hidden dock back
const REST_MS = 220            // ...after the pointer has rested there this long
const HINT_MS = 2600
const PHONE = '(max-width: 620px)'

/* Is the dock showing? Always, unless a window is maximised; then only on call. */
export function dockShown({ maxed, near, over, dragging, focused }) {
  return !maxed || !!(near || over || dragging || focused)
}

/* Only KEYBOARD focus calls the dock back. A mouse press gives a button focus too, and windows
 * never take DOM focus, so counting that left the dock up over a maximised window's composer. */
export function keyboardFocus(e) {
  try { return !!(e && e.target && e.target.matches && e.target.matches(':focus-visible')) } catch { return false }
}

/* Where a drop at client x lands: the number of entries whose centre is left of it. */
export const insertAt = (x, centers) => centers.filter(c => c < x).length

/* The drop zone (deskDrag.js). `indexAt(x)` is the insertion index under the pointer. An app
 * already in the dock moves to where it was dropped; a refused add says why through onHint. */
export function dockZone({ hit, indexAt, onHint, over }) {
  return {
    id: 'dock', z: 5, alias: true, hit, over,
    accepts: (it) => it.kind === 'app' || it.kind === 'dock',
    drop(it, x) {
      const at = indexAt(x)
      const cur = layout.dockItems()
      const from = it.kind === 'dock' ? it.index : cur.indexOf(it.id)
      if (from >= 0) { layout.dockMove(from, at > from ? at - 1 : at); return }
      const r = layout.dockAdd(it.id, at)
      if (!r.ok && onHint) onHint(r.why)
    },
  }
}

/* A press on a dock entry: a click opens, a drag carries it (deskDrag.begin). Dropped on no
 * zone — the desktop, a window, a folder — it leaves the dock, unless it is the last one. */
export function dockPress(app, index, e, { onHint, onGhost, onDrag } = {}) {
  return drag.begin({ kind: 'dock', id: app.id, index }, e, {
    onStart: () => { if (onDrag) onDrag(app.id) },
    onMove: (dx, dy, x, y) => { if (onGhost) onGhost({ app, x, y }) },
    onClick: () => wm.open(app.id, app),
    onDrop: () => {
      const r = layout.dockRemove(app.id)
      if (!r.ok && onHint) onHint(r.why)
    },
    onEnd: () => { if (onGhost) onGhost(null); if (onDrag) onDrag(null) },
  })
}

/* One entry. No hooks: the gate calls it as a function and presses its keys. */
export function DockItem({ app, index, open, at, lift, onOpen, onDown }) {
  return (
    <button className={'dock-item' + (open ? ' dock-open' : '') + (at ? ' dock-at' : '') + (lift ? ' dock-lift' : '')}
            type="button" data-app={app.id} data-index={index}
            aria-label={app.title + (open ? ', open' : '')}
            onMouseDown={onDown}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen() } }}>
      <span className="dock-tile"><Icon name={app.icon} size={22} /></span>
      <span className="dock-tip" aria-hidden="true">{app.title}</span>
    </button>
  )
}

/* The bar itself, drawn from what it is handed. The hint line is always in the tree (empty when
 * quiet) so a screen reader hears it arrive. */
export function DockView({ apps, openIds, hidden, hint, over, at, lift, onOpen, onDown, dockRef, ...on }) {
  return (
    <nav ref={dockRef} aria-label="Dock"
         className={'dock' + (hidden ? ' dock-hidden' : '') + (over ? ' dock-over' : '')
                    + (over && at === apps.length ? ' dock-at-end' : '')}
         {...on}>
      {apps.map((a, i) => (
        <DockItem key={a.id} app={a} index={i} open={openIds.has(a.id)} at={!!over && at === i}
                  lift={lift === a.id}
                  onOpen={() => (onOpen ? onOpen(a) : null)} onDown={onDown ? onDown(a, i) : undefined} />
      ))}
      <span className="dock-hint" role="status">{hint || ''}</span>
    </nav>
  )
}

function usePhone() {
  const mq = () => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(PHONE) : null)
  const [phone, setPhone] = useState(() => { const m = mq(); return !!(m && m.matches) })
  useEffect(() => {
    const m = mq()
    if (!m || !m.addEventListener) return undefined
    const f = () => setPhone(m.matches)
    // a resize re-reads it too: a viewport emulator (the built-in browser's) was seen to
    // change the width without firing the query's `change`, and the dock stayed hidden
    m.addEventListener('change', f)
    window.addEventListener('resize', f)
    return () => { m.removeEventListener('change', f); window.removeEventListener('resize', f) }
  }, [])
  return phone
}

export default function Dock() {
  // third arguments: the server snapshot (G-ROOM-KIT draws this under react-dom/server)
  useSyncExternalStore(layout.onChange, layout.getVersion, layout.getVersion)
  const windows = useSyncExternalStore(wm.subscribe, wm.getWindows, wm.getWindows)
  const dragging = useSyncExternalStore(drag.subscribe, drag.dragging, drag.dragging)
  const phone = usePhone()
  const apps = layout.dockItems().map(id => APPS.find(a => a.id === id)).filter(Boolean)
  const openIds = new Set(windows.map(w => w.appId))
  const maxed = wm.anyMaximized() || (phone && windows.some(w => !w.minimized))

  const ref = useRef(null)
  const [near, setNear] = useState(false)
  const [overBar, setOverBar] = useState(false)
  const [focused, setFocused] = useState(false)
  const [dropOver, setDropOver] = useState(false)
  const [at, setAt] = useState(null)
  const [hint, setHint] = useState('')
  const [ghost, setGhost] = useState(null)
  const [lift, setLift] = useState(null)

  const hintTimer = useRef(null)
  const say = useCallback((t) => {
    setHint(t || '')
    clearTimeout(hintTimer.current)
    if (t) hintTimer.current = setTimeout(() => setHint(''), HINT_MS)
  }, [])
  useEffect(() => () => clearTimeout(hintTimer.current), [])

  const centers = () => {
    const el = ref.current
    if (!el) return []
    return Array.from(el.querySelectorAll('.dock-item')).map(b => { const r = b.getBoundingClientRect(); return r.left + r.width / 2 })
  }

  // the dock is a drop zone for as long as it is up; a little slack around the bar
  useEffect(() => drag.addZone(dockZone({
    hit: (x, y) => {
      const el = ref.current
      if (!el) return false
      const r = el.getBoundingClientRect()
      const ok = x >= r.left - 8 && x < r.right + 8 && y >= r.top - 16 && y < r.bottom + 8
      if (ok) setAt(insertAt(x, centers()))
      return ok
    },
    indexAt: (x) => insertAt(x, centers()),
    onHint: say,
    over: (on) => { setDropOver(on); if (!on) setAt(null) },
  })), [say])

  /* THE BOTTOM EDGE CALLS IT BACK — only while it is away. The pointer has to REST within EDGE
   * px of the bottom for REST_MS (a pass across the taskbar is not a call); once it is up it
   * stays while the pointer is anywhere in the dock's band, so moving up to it does not chase
   * it away. */
  useEffect(() => {
    if (!maxed) { setNear(false); return undefined }
    let timer = null
    const mv = (e) => {
      const atEdge = window.innerHeight - e.clientY <= EDGE
      if (atEdge) {
        if (!timer) timer = setTimeout(() => { timer = null; setNear(true) }, REST_MS)
        return
      }
      clearTimeout(timer); timer = null
      setNear(prev => {
        if (!prev) return false
        const el = ref.current
        const r = el && el.getBoundingClientRect()
        return !!(r && e.clientY >= r.top - 16)
      })
    }
    window.addEventListener('mousemove', mv)
    return () => { clearTimeout(timer); window.removeEventListener('mousemove', mv) }
  }, [maxed])

  const shown = dockShown({ maxed, near, over: overBar, dragging, focused })
  return (
    <>
      <DockView apps={apps} openIds={openIds} hidden={!shown} hint={hint} over={dropOver} at={at} lift={lift}
                dockRef={ref}
                onOpen={(a) => wm.open(a.id, a)}
                onDown={(a, i) => (e) => dockPress(a, i, e, { onHint: say, onGhost: setGhost, onDrag: setLift })}
                onMouseEnter={() => setOverBar(true)} onMouseLeave={() => setOverBar(false)}
                onFocus={(e) => setFocused(keyboardFocus(e))}
                onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setFocused(false) }} />
      {ghost ? (
        <span className="dock-ghost" aria-hidden="true" style={{ left: ghost.x, top: ghost.y }}>
          <span className="dock-tile"><Icon name={ghost.app.icon} size={22} /></span>
        </span>
      ) : null}
    </>
  )
}
