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
  if (found) { found.minimized = false; found.z = ++z; emit(); return }
  windows.push({
    appId, z: ++z, minimized: false,
    x: 60 + (windows.length % 6) * 34,
    y: 50 + (windows.length % 6) * 28,
    w: opts.w || 620, h: opts.h || 460,
  })
  emit()
}
export const close = (id) => { windows = windows.filter(w => w.appId !== id); emit() }
export const focus = (id) => { const w = windows.find(x => x.appId === id); if (w) { w.z = ++z; w.minimized = false; emit() } }
export const minimize = (id) => { const w = windows.find(x => x.appId === id); if (w) { w.minimized = true; emit() } }
export function moveResize(id, patch) {
  const w = windows.find(x => x.appId === id)
  if (!w) return
  Object.assign(w, patch)
  emit()
}
