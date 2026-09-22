/* deskIcons — where each icon sits on the desktop, HIS arrangement, per browser.
 *
 * His ask (2026-09-23): "move the room icons from a side bar on the left so that they
 * are actual free desktop like icons". A desktop icon that forgets where it was put is
 * not a desktop icon, it is a button in a list — so position persists, the same way the
 * Portrait's box does and for the same reason: a panel that resets to the corner every
 * reload is one he stops arranging.
 *
 * Shape: localStorage 'sp-desk-icons' = { [appId]: {x, y} }. An id with no entry has
 * never been dragged and gets the default column (see DeskIcons.jsx) — so a NEW app
 * appears in a sensible place instead of at 0,0 under the brand, and one he has already
 * placed never moves because the registry grew.
 *
 * Deliberately NOT merged into dockPrefs.js. That file answers "which apps earn a
 * slot"; this one answers "where does this icon sit". One store for two questions is
 * how a toggle starts silently moving things.
 */
const KEY = 'sp-desk-icons'
const listeners = new Set()
let cache = null

function load() {
  if (cache) return cache
  try {
    const raw = localStorage.getItem(KEY)
    const parsed = raw ? JSON.parse(raw) : null
    cache = (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) ? parsed : {}
  } catch { cache = {} }          // private mode, or a hand-edited value
  return cache
}

export const positions = () => load()
export const posOf = (id) => load()[id] || null

export function place(id, x, y) {
  const cur = load()
  cur[id] = { x: Math.round(x), y: Math.round(y) }
  cache = { ...cur }
  try { localStorage.setItem(KEY, JSON.stringify(cache)) } catch { /* private mode */ }
  bump()
}

/* THE WAY BACK. If every icon is dragged somewhere unreachable — or a display shrinks
 * and the clamp cannot save them all — this puts the whole desktop back to the default
 * column. The apps launcher is the other way back, and having two is the point: this is
 * the one control that cannot itself be lost behind a misplaced icon. */
export function resetAll() {
  cache = {}
  try { localStorage.removeItem(KEY) } catch { /* private mode */ }
  bump()
}

export function subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn) }

let version = 0
const bump = () => { version++; listeners.forEach(fn => fn()) }
export const getVersion = () => version
