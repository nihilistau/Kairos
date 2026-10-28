/* desktopLayout — which folder an app sits in, and what is in the dock (2026-10-29).
 *
 * THE THREE QUESTIONS, THREE STORES. deskVisibility.js answers "does this app get a desktop
 * icon" (sp-dock-hidden, the Apps window's list); deskIcons.js answers "where does this icon
 * sit" (sp-desk-icons); this file answers "which folder is it in" and "what is on the dock".
 * Mixing them is how a toggle starts silently moving things, so none of them reads another's
 * key — only the hidden SET is consulted here, so the Apps window stays the master show/hide.
 *
 * Keys (per browser, like everything else about this desktop):
 *   sp-desk-folders     { [appId]: folderId | null }   his moves only; absent = the registry's `group`
 *   sp-dock-items       [appId, ...]                   absent = DEFAULT_DOCK
 *   sp-desk-migrated-v1 { icons, undone, dismissed, fresh }   the pre-folders sp-desk-icons, verbatim
 *
 * NO CACHE OF ITS OWN. Every read here goes to localStorage and is try/catch'd (the hidden
 * list is deskVisibility's, which keeps its own parsed copy — resetCache() there): a hand-edited value, bad JSON
 * or private mode gives the defaults, never a throw into a render. The values are tiny and the
 * UI re-reads on onChange, so a cache would buy nothing and could go stale against another tab.
 *
 * DOCK ENTRIES ARE ALIASES. Docking never takes an app out of its folder or off the desktop,
 * and removing it from the dock never puts it anywhere. Ids the registry does not have are
 * skipped silently, in folders and in the dock, so an old saved list can outlive a removed app.
 */
import { APPS, FOLDERS, DEFAULT_DOCK, DOCK_HIDDEN_DEFAULT } from './appRegistry.jsx'
import { hiddenSet } from './deskVisibility.js'
import * as deskIcons from './deskIcons.js'

const K_FOLDERS = 'sp-desk-folders'
const K_DOCK = 'sp-dock-items'
const K_MIG = 'sp-desk-migrated-v1'
const K_ICONS = 'sp-desk-icons'
const K_HIDDEN = 'sp-dock-hidden'
export const DOCK_MAX = 8
export const DOCK_MIN = 1

const listeners = new Set()
// The version is useSyncExternalStore's snapshot (DeskIcons, the dock, the Apps window): one
// tick per change, bumped here and nowhere else, so every reader agrees on what changed.
let version = 0
const bump = () => { version++; listeners.forEach(fn => { try { fn() } catch { /* a listener's fault is not ours */ } }) }
export function onChange(fn) { listeners.add(fn); return () => listeners.delete(fn) }
export const getVersion = () => version

/* THE REFUSAL WORDS, ONCE. dockAdd/dockRemove return these as `why`, and the dock and the Apps
 * window show `why` as it comes — no caller re-checks the limit, so the words follow DOCK_MAX. */
export const DOCK_HINT = { full: 'the dock holds ' + DOCK_MAX, last: 'the dock needs at least one' }

const known = (id) => APPS.some(a => a.id === id)
const isFolder = (id) => FOLDERS.some(f => f.id === id)

function read(key) {
  try { const raw = localStorage.getItem(key); return raw == null ? null : JSON.parse(raw) } catch { return null }
}
function write(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* private mode */ }
}
const overrides = () => {
  const v = read(K_FOLDERS)
  return (v && typeof v === 'object' && !Array.isArray(v)) ? v : {}
}

/* ── folders ── */
export function folderOf(appId) {
  const app = APPS.find(a => a.id === appId)
  if (!app) return null
  const o = overrides()
  if (Object.prototype.hasOwnProperty.call(o, appId)) {
    const f = o[appId]
    if (f === null) return null
    if (isFolder(f)) return f
    // an override naming a folder that no longer exists falls through to the registry's own
  }
  return isFolder(app.group) ? app.group : null
}

/* The apps in a folder that he has not hidden, in registry order. */
export function appsIn(folderId) {
  const hidden = hiddenSet(DOCK_HIDDEN_DEFAULT)
  return APPS.filter(a => folderOf(a.id) === folderId && (a.pinned || !hidden.has(a.id))).map(a => a.id)
}

export function moveToFolder(appId, folderId) {
  if (!known(appId)) return
  if (folderId !== null && !isFolder(folderId)) return
  const o = { ...overrides() }
  o[appId] = folderId
  write(K_FOLDERS, o)
  bump()
}

/* ── the dock ── */
function savedDock() {
  const v = read(K_DOCK)
  if (!Array.isArray(v)) return null
  const seen = new Set()
  const ok = v.filter(id => typeof id === 'string' && known(id) && !seen.has(id) && seen.add(id))
  return ok.length ? ok : null
}
export function dockItems() {
  return savedDock() || DEFAULT_DOCK.filter(known)
}

export function dockAdd(appId, index) {
  if (!known(appId)) return { ok: false, why: 'no such app' }
  const cur = dockItems()
  if (cur.includes(appId)) return { ok: false, why: 'already in the dock' }
  if (cur.length >= DOCK_MAX) return { ok: false, why: DOCK_HINT.full }
  const at = Number.isInteger(index) ? Math.max(0, Math.min(cur.length, index)) : cur.length
  write(K_DOCK, [...cur.slice(0, at), appId, ...cur.slice(at)])
  bump()
  return { ok: true }
}

export function dockRemove(appId) {
  const cur = dockItems()
  if (!cur.includes(appId)) return { ok: false, why: 'not in the dock' }
  if (cur.length <= DOCK_MIN) return { ok: false, why: DOCK_HINT.last }
  write(K_DOCK, cur.filter(id => id !== appId))
  bump()
  return { ok: true }
}

export function dockMove(from, to) {
  const cur = dockItems()
  if (!Number.isInteger(from) || !Number.isInteger(to) || from < 0 || from >= cur.length) return
  const t = Math.max(0, Math.min(cur.length - 1, to))
  if (t === from) return
  const [it] = cur.splice(from, 1)
  cur.splice(t, 0, it)
  write(K_DOCK, cur)
  bump()
}

/* ── the one-time upgrade ──
 * First load after folders arrive: every grouped app is already in its folder (that is just
 * the registry default), so the migration's only job is to take the old icon positions off the
 * table and keep them. The raw sp-desk-icons string is saved verbatim; undo writes it back
 * byte for byte and turns every app into a loose icon again. Positions are never edited. */
export function migrateOnce() {
  const b = read(K_MIG)
  if (b && typeof b === 'object' && !Array.isArray(b)) return
  let raw = null
  try { raw = localStorage.getItem(K_ICONS) } catch { raw = null }
  let hidden = null
  try { hidden = localStorage.getItem(K_HIDDEN) } catch { hidden = null }
  // A browser that never arranged anything has nothing to put back.
  write(K_MIG, { icons: raw, undone: false, dismissed: false, fresh: raw == null && hidden == null })
  bump()
}

export function canUndoMigration() {
  const b = read(K_MIG)
  return !!(b && typeof b === 'object' && !Array.isArray(b) && !b.fresh && !b.undone && !b.dismissed)
}

export function undoMigration() {
  if (!canUndoMigration()) return
  const b = read(K_MIG)
  const loose = {}
  for (const a of APPS) loose[a.id] = null
  write(K_FOLDERS, loose)
  deskIcons.restoreRaw(typeof b.icons === 'string' ? b.icons : null)
  write(K_MIG, { ...b, undone: true })
  bump()
}

/* Did he take the undo? Then his restored icon column is the desktop, and DeskIcons draws a
 * folder only once something is in it (or while a drag could drop something in). */
export function migrationUndone() {
  const b = read(K_MIG)
  return !!(b && typeof b === 'object' && !Array.isArray(b) && b.undone)
}

/* "No thanks, keep the folders" — ends the offer without touching anything. */
export function dismissUndo() {
  const b = read(K_MIG)
  if (!b || typeof b !== 'object' || Array.isArray(b)) return
  write(K_MIG, { ...b, dismissed: true })
  bump()
}
