import { useEffect, useRef, useState } from 'react'
import { Icon } from '../kit/icons.jsx'
import { dragging } from './deskDrag.js'

/* FOLDER — one group of apps on the desktop (2026-10-29, his approved mockup "Folders").
 *
 * The icon is a 2×2 mini-grid of its first four apps' glyphs; double-click or Enter opens it
 * (the same as an app icon — single click selects), and its apps fan out in a frosted panel
 * beside it. Inside the panel: arrows move, Enter or a double-click opens an app, Escape or a
 * click anywhere else closes it. Dragging an app out of the panel is DeskIcons' business (the
 * shared controller in deskDrag.js); the panel only stays open while that drag is in flight.
 *
 * Which apps are in which folder is desktopLayout.js; this file draws what it is handed.
 * Classes are `dsk-fold-*`, under the shell's `dsk-` (G-ROOM-CSS).
 */
export const PANEL_COLS = 3
const ITEM_W = 76, ITEM_H = 80, GAP = 4, PAD = 12, HEAD = 24

/* Where the panel goes: to the right of its folder; flipped to the left when that runs off
 * the desktop; and when neither side fits (phone width), below the folder, inside the desktop.
 * Never above the top edge or below the bottom. `fpos` is the folder icon's top-left. */
export function panelPos(fpos, n, area, iconW = 88, iconH = 84) {
  const cols = Math.min(PANEL_COLS, Math.max(1, n))
  const rows = Math.max(1, Math.ceil(n / cols))
  const w = cols * ITEM_W + (cols - 1) * GAP + 2 * PAD
  const h = HEAD + rows * ITEM_H + (rows - 1) * GAP + 2 * PAD
  let x = fpos.x + iconW + 8
  let y = fpos.y
  if (x + w > area.w - 8) x = fpos.x - w - 8
  if (x < 8) {
    x = Math.max(0, Math.min(area.w - w - 8, fpos.x))
    y = fpos.y + iconH + 4
  }
  y = Math.max(0, Math.min(y, area.h - h - 8))
  return { x, y, w, h }
}

/* The panel's arrows, as a grid PANEL_COLS wide. Returns the new focus `{i}`, `{i, open}` for
 * Enter/Space, or null for a key that is not the panel's (Escape is watchDismiss's). */
export function panelKey(key, i, n) {
  const last = Math.max(0, n - 1)
  const to = (j) => ({ i: Math.max(0, Math.min(last, j)) })
  switch (key) {
    case 'ArrowRight': return to(i + 1)
    case 'ArrowLeft': return to(i - 1)
    case 'ArrowDown': return i + PANEL_COLS <= last ? { i: i + PANEL_COLS } : { i }
    case 'ArrowUp': return i - PANEL_COLS >= 0 ? { i: i - PANEL_COLS } : { i }
    case 'Home': return { i: 0 }
    case 'End': return { i: last }
    case 'Enter': case ' ': return { i, open: true }
    default: return null
  }
}

/* What closes an open panel: Escape anywhere, or a press outside it (and outside its own
 * folder icon, so pressing the icon does not close-then-reopen). Neither while a drag is in
 * flight — he is carrying an app out of it. Returns the unwatch. */
export function watchDismiss(doc, { inside, close, busy = () => false }) {
  const key = (e) => {
    if (e.key === 'Escape' && !e.defaultPrevented && !busy()) close('key')
  }
  const down = (e) => {
    if (!busy() && !inside(e.target)) close('outside')
  }
  doc.addEventListener('keydown', key)
  doc.addEventListener('mousedown', down, true)
  return () => {
    doc.removeEventListener('keydown', key)
    doc.removeEventListener('mousedown', down, true)
  }
}

/* The icon. No hooks: the gate calls it as a function and presses its keys. */
export function FolderIcon({ folder, apps, pos, w = 88, sel, open, drop, drag, onOpen, onDown, btnRef }) {
  const four = apps.slice(0, 4)
  const n = apps.length
  return (
    <button ref={btnRef}
            className={'dsk-icon dsk-fold'
                       + (sel ? ' dsk-sel' : '')
                       + (open ? ' dsk-fold-open' : '')
                       + (drop ? ' dsk-fold-drop' : '')
                       + (drag ? ' dsk-drag' : '')}
            style={{ left: pos.x, top: pos.y, width: w }}
            aria-label={folder.title + ' folder, ' + n + (n === 1 ? ' app' : ' apps')}
            aria-haspopup="dialog" aria-expanded={!!open}
            title={n ? apps.map(a => a.title).join(' · ') : 'Empty — drag an app here'}
            onMouseDown={onDown}
            onDoubleClick={() => onOpen()}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen() } }}>
      <span className="dsk-tile dsk-fold-tile">
        {[0, 1, 2, 3].map(i => (
          <span key={i} className="dsk-fold-g">{four[i] ? <Icon name={four[i].icon} size={13} /> : null}</span>
        ))}
      </span>
      <span className="dsk-lb">{folder.title}</span>
    </button>
  )
}

/* The open panel. `pos` is its folder's top-left on the desktop, `area` the desktop's size;
 * `inside(target)` is extended by the caller to count the folder icon too. */
export function FolderPanel({ folder, apps, pos, area, iconW, iconH, onClose, onOpenApp, onItemDown,
                              panelRef, folderEl }) {
  const [focus, setFocus] = useState(0)
  const items = useRef([])
  const own = useRef(null)
  const ref = panelRef || own
  const f = Math.min(focus, Math.max(0, apps.length - 1))
  const box = panelPos(pos, apps.length, area, iconW, iconH)

  useEffect(() => {
    const first = items.current[0]
    if (first) first.focus()
  }, [folder.id])

  useEffect(() => watchDismiss(document, {
    inside: (t) => !!((ref.current && ref.current.contains(t)) || (folderEl && folderEl() && folderEl().contains(t))),
    close: onClose,
    busy: dragging,
  }), [folder.id, onClose])

  const onKeyDown = (e) => {
    const r = panelKey(e.key, f, apps.length)
    if (!r || !apps.length) return
    e.preventDefault()
    if (r.open) { onOpenApp(apps[r.i]); return }
    setFocus(r.i)
    const el = items.current[r.i]
    if (el) el.focus()
  }

  return (
    <div ref={ref} className="dsk-fold-panel" role="dialog" aria-label={folder.title}
         style={{ left: box.x, top: box.y, width: box.w }} onKeyDown={onKeyDown}>
      <div className="dsk-fold-h">{folder.title}</div>
      {apps.length ? (
        <div className="dsk-fold-grid">
          {apps.map((a, i) => (
            <button key={a.id} ref={el => { items.current[i] = el }}
                    className={'dsk-fold-item' + (i === f ? ' dsk-sel' : '')}
                    tabIndex={i === f ? 0 : -1}
                    title={a.blurb}
                    onFocus={() => setFocus(i)}
                    onMouseDown={onItemDown(a)}
                    onDoubleClick={() => onOpenApp(a)}>
              <span className="dsk-tile"><Icon name={a.icon} size={24} /></span>
              <span className="dsk-lb">{a.title}</span>
            </button>
          ))}
        </div>
      ) : <div className="dsk-fold-empty">Empty — drag an app here.</div>}
    </div>
  )
}
