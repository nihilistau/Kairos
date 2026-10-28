/* deskDrag — ONE drag controller for everything on the desktop that can be picked up
 * (2026-10-29, folders + dock): a loose icon, a folder icon, an app inside an open folder,
 * and (task 3) the dock's entries. One controller, because two would disagree about what a
 * click is and where a drop lands.
 *
 * WHAT IT OWNS: the slack that tells a click from a drag, which DROP ZONE is under the
 * pointer, and handing the item to that zone on release. WHAT IT DOES NOT: where anything
 * is drawn, or what a drop means — a zone's own `drop` says that, and a drop on no zone goes
 * to the caller's `onDrop` (the desktop: "put it here").
 *
 * A zone: { id, z, hit(x, y) -> bool, accepts(item) -> bool, drop(item, x, y), over?(on) }
 *   x, y are client coordinates. The highest `z` that is hit AND accepts wins, so an open
 *   folder panel (drawn over the icons) takes a drop before the folder icon beneath it.
 * An item: { kind: 'app' | 'folder' | 'dock', id, from: folderId | null, index? }
 *   ('dock' is a dock entry, carrying its `index` there; only the dock itself accepts one.)
 * A zone with `alias: true` (the dock) keeps a COPY: the item stays where it came from, so
 * the caller's `onZone(zone)` hook puts a carried icon back where it was picked up.
 *
 * `start` is the pure core (the gate drives it with numbers); `begin` wires it to the window's
 * mouse events for the components.
 */
export const SLACK = 4   // px — the tremor in a double-click is not a drag

const zones = new Set()
let current = null

export function addZone(z) { zones.add(z); return () => { zones.delete(z) } }

export function zoneAt(x, y, item) {
  let best = null
  for (const z of zones) {
    let ok = false
    try { ok = z.hit(x, y) && z.accepts(item) } catch { ok = false }
    if (ok && (!best || (z.z || 0) > (best.z || 0))) best = z
  }
  return best
}

/* Is anything being dragged right now (moved past the slack)? The folder panel asks, so a
 * drag that wanders outside it does not close it under the pointer. */
export const dragging = () => !!(current && current.moved)

/* ...and told, for a component that draws differently mid-drag (after the folders undo, an
 * empty folder shows only as a drop target). Fires when a drag passes the slack, and at its end. */
const watchers = new Set()
export function subscribe(fn) { watchers.add(fn); return () => { watchers.delete(fn) } }
const tell = () => watchers.forEach(fn => { try { fn() } catch { /* a watcher's fault is not ours */ } })

export function start(item, x0, y0, hooks = {}) {
  let hover = null
  const setHover = (z) => {
    if (z === hover) return
    if (hover && hover.over) hover.over(false)
    hover = z
    if (hover && hover.over) hover.over(true)
  }
  const ctl = {
    item, moved: false,
    move(x, y) {
      const dx = x - x0, dy = y - y0
      if (!ctl.moved && Math.abs(dx) < SLACK && Math.abs(dy) < SLACK) return
      if (!ctl.moved) { ctl.moved = true; tell(); if (hooks.onStart) hooks.onStart() }
      if (hooks.onMove) hooks.onMove(dx, dy, x, y)
      setHover(zoneAt(x, y, item))
    },
    up(x, y) {
      let result
      if (!ctl.moved) {
        result = 'click'
        if (hooks.onClick) hooks.onClick()
      } else {
        const z = zoneAt(x, y, item)
        if (z) { z.drop(item, x, y); if (hooks.onZone) hooks.onZone(z); result = 'zone:' + z.id }
        else { if (hooks.onDrop) hooks.onDrop(x, y); result = 'desk' }
      }
      end()
      return result
    },
    cancel() { end(); if (hooks.onCancel) hooks.onCancel() },
  }
  const end = () => {
    setHover(null)
    const was = current === ctl && ctl.moved
    if (current === ctl) current = null
    if (was) tell()
    if (hooks.onEnd) hooks.onEnd()
  }
  current = ctl
  return ctl
}

/* From a mousedown: follow the pointer on the window until release. */
export function begin(item, e, hooks = {}) {
  if (e.button !== 0) return null
  if (current && current.abandon) current.abandon()    // a stale drag (its mouseup was lost) is over
  const ctl = start(item, e.clientX, e.clientY, hooks)
  // a lost mouseup (Alt-Tab mid-drag) must not leave the drag armed for the next release anywhere:
  // a move with no button held, or the window losing focus, ends it as a cancel
  const move = (ev) => { if (ev.buttons === 0) { off(); ctl.cancel(); return } ctl.move(ev.clientX, ev.clientY) }
  const up = (ev) => { if (ev.button !== 0) return; off(); ctl.up(ev.clientX, ev.clientY) }
  const lost = () => { off(); ctl.cancel() }
  ctl.abandon = lost
  // Escape mid-drag puts it back, and is spent here: the open panel must not also close on it
  const key = (ev) => { if (ev.key === 'Escape' && ctl.moved) { ev.stopPropagation(); off(); ctl.cancel() } }
  const off = () => {
    window.removeEventListener('mousemove', move)
    window.removeEventListener('mouseup', up)
    window.removeEventListener('keydown', key, true)
    window.removeEventListener('blur', lost)
    document.body.classList.remove('resizing')
  }
  document.body.classList.add('resizing')      // kill text selection mid-drag
  window.addEventListener('blur', lost)
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', up)
  window.addEventListener('keydown', key, true)
  return ctl
}
