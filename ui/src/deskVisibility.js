/* deskVisibility — which apps get a DESKTOP ICON, HIS call, live (2026-08-21; renamed from dockPrefs 2026-10-29 when the real dock arrived, desktopLayout.js).
 *
 * His ask: "an icon on the side bar that brings up a panel containing icons to
 * add/remove from the sidebar live". The set of apps is the registry's business;
 * which of them get a desktop icon is taste, so it lives client-side in
 * localStorage — per browser, like a real desktop's taskbar pins. Nothing here
 * can make an app unreachable: the apps launcher lists everything always, and it
 * is not itself hideable.
 *
 * Shape: localStorage 'sp-dock-hidden' = JSON array of app ids. An app is shown
 * unless hidden here; apps whose registry row says `dock: false` start hidden until he
 * toggles them in (today only chat — it opens itself). Music and games started hidden
 * from 2026-08-21 until the folders work (2026-10-29); a list he saved then still hides them.
 */
const KEY = 'sp-dock-hidden'
const listeners = new Set()
let cache = null            // the parsed array, kept in step with localStorage

function load() {
  if (cache) return cache
  try {
    const raw = localStorage.getItem(KEY)
    cache = raw ? JSON.parse(raw) : null
  } catch { cache = null }
  if (!Array.isArray(cache)) cache = null
  return cache
}

/* null means "he has never touched it" — the registry's dock:false default
 * (chat) applies. One touch materializes the full hidden list so later registry-default
 * changes never silently re-hide something he pinned. */
export function hiddenSet(defaults) {
  const saved = load()
  if (saved) return new Set(saved)
  return new Set(defaults)
}

export function toggle(id, defaults) {
  const cur = hiddenSet(defaults)
  if (cur.has(id)) cur.delete(id)
  else cur.add(id)
  cache = [...cur]
  try { localStorage.setItem(KEY, JSON.stringify(cache)) } catch { /* private mode */ }
  listeners.forEach(fn => fn())
}

/* Forget the parsed copy so the next read goes to localStorage again. Tests that swap the
 * storage under a live module need it; nothing in the app calls it. */
export function resetCache() { cache = null }

export function subscribe(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

/* useSyncExternalStore wants a stable snapshot — version counter, bumped per change */
let version = 0
listeners.add(() => { version++ })
export const getVersion = () => version
