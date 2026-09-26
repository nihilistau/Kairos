/* windowManager — a plain module-level store, deliberately trivial.
 *
 * Lifted in spirit from OpenRoom's lib/windowManager.ts (115 lines, and right to
 * be that small): an array of window states plus a listener Set, driven through
 * useSyncExternalStore. No context, no reducer, no library. A window manager that
 * needs a state library is a window manager that has grown opinions it should not
 * have.
 */
let windows = []
let z = 10
const listeners = new Set()

const emit = () => { windows = [...windows]; listeners.forEach(f => f()) }

export const subscribe = (f) => { listeners.add(f); return () => listeners.delete(f) }
export const getWindows = () => windows

export function open(appId, opts = {}) {
  const found = windows.find(w => w.appId === appId)
  if (found) {
    stopTimer(appId)
    if (found.minimized) found.restoredAt = Date.now()
    found.minimized = false; found.minimizing = false
    found.z = ++z; emit(); return
  }
  windows.push({
    appId, z: ++z, minimized: false,
    // CLEAR OF THE ICONS (2026-09-23). The stagger started at x:60, which was empty
    // when a dock owned the left edge and is now the icon column (DeskIcons: COL_X 18 +
    // ICON_W 88 = 106). Measured in the browser: chat opened at 60,50 and buried the
    // first column on every load. Windows start to the right of them instead.
    x: 132 + (windows.length % 6) * 34,
    y: 50 + (windows.length % 6) * 28,
    w: opts.w || 620, h: opts.h || 460,
  })
  emit()
}
export const close = (id) => { stopTimer(id); windows = windows.filter(w => w.appId !== id); emit() }
export function focus(id) {
  const w = windows.find(x => x.appId === id)
  if (!w) return
  stopTimer(id)
  if (w.minimized) w.restoredAt = Date.now()
  w.minimized = false; w.minimizing = false
  w.z = ++z; emit()
}

/* MINIMISE ANIMATES (redesign stage 3, spec §8 — his call). The window stays on the page,
 * marked `minimizing`, for MIN_MS while the shell flies it toward its taskbar button, then
 * it is minimised. This module holds the flag and the timer, never geometry: where the
 * button is, and what "flying" looks like, is the shell's business. A caller that wants
 * no flight (reduced motion) passes delay 0. */
export const MIN_MS = 200
const timers = new Map()
function stopTimer(id) { const t = timers.get(id); if (t) { clearTimeout(t); timers.delete(id) } }

export function minimize(id, { delay = MIN_MS } = {}) {
  const w = windows.find(x => x.appId === id)
  if (!w || w.minimized || w.minimizing) return
  if (!delay) { w.minimized = true; emit(); return }
  w.minimizing = true
  emit()
  timers.set(id, setTimeout(() => {
    timers.delete(id)
    const cur = windows.find(x => x.appId === id)
    if (cur && cur.minimizing) { cur.minimizing = false; cur.minimized = true; emit() }
  }, delay))
}

/* MAXIMISE — a toggle that REMEMBERS (2026-09-23, his ask). The three lights in the
 * title bar were close, minimise, and a green ornament labelled "focused" that did
 * nothing. Now they are three controls.
 *
 * The pre-maximise box is stashed on the window rather than recomputed, because the
 * only honest restore is the box he actually arranged. Without it, un-maximising has
 * to guess a size, and a guess here throws away the one thing he did by hand.
 *
 * Geometry stays OUT of this module: it stores the flag and the old box, and main.jsx
 * decides what "maximised" looks like in CSS. A window manager that knows about the
 * taskbar's height is a window manager with opinions about furniture.
 */
export function maximize(id) {
  const w = windows.find(x => x.appId === id)
  if (!w) return
  // a maximise mid-flight cancels the minimise, as open/focus/close do (final review, M1):
  // without this the flight's timer fired afterwards and minimised the window just maximised
  stopTimer(id)
  if (w.max) { Object.assign(w, w.pre || {}, { max: false, pre: null }) }
  else { w.pre = { x: w.x, y: w.y, w: w.w, h: w.h }; w.max = true }
  w.minimized = false; w.minimizing = false
  w.z = ++z
  emit()
}

export function moveResize(id, patch) {
  const w = windows.find(x => x.appId === id)
  if (!w) return
  // DRAGGING A MAXIMISED WINDOW RESTORES IT, which is what every desktop does and
  // what the hand expects. Without this the drag silently edits the hidden pre-box
  // and the window does not move, which reads as a frozen UI.
  if (w.max) { Object.assign(w, w.pre || {}, { max: false, pre: null }) }
  Object.assign(w, patch)
  emit()
}
