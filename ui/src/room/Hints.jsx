import { useEffect, useRef, useState } from 'react'
import * as api from '../api.js'
import * as wm from '../windowManager.js'
import { byId } from '../appRegistry.jsx'
import { Button } from '../kit/parts.jsx'

/* FIRST-RUN HINTS (2026-11-26, design §7b; harness/hints.py, words in config/hints.json).
 *
 * One card at a time, bottom right, on a CLEAN setup only (the server decides: a companion
 * whose memory already holds you is never lectured). "Show me" opens the window the hint
 * is about; opening that window — by any route — marks the hint DONE, because the point is
 * that you tried it, not that you clicked a button on a card. "Got it" dismisses; "No
 * more hints" turns them off (on again from the Companion window).
 *
 * Prefix `hn-` (G-ROOM-CSS).
 */
export default function Hints() {
  const [v, setV] = useState(null)
  // FOLDED: on a small screen the card sits over windows' buttons, so it folds into a pill.
  // A per-browser convenience only (try/catch: storage can be missing or blocked).
  const [folded, setFolded] = useState(() => { try { return localStorage.getItem('sp-hints-folded') === '1' } catch { return false } })
  const fold = (f) => { setFolded(f); try { localStorage.setItem('sp-hints-folded', f ? '1' : '0') } catch { /* no storage */ } }
  const seen = useRef(new Set())
  useEffect(() => { api.hints().then(setV).catch(() => {}) }, [])
  // Every window that opens tells the server once; it marks any hint that was waiting on it.
  useEffect(() => wm.subscribe(() => {
    for (const w of wm.getWindows()) {
      if (w.minimized || seen.current.has(w.appId)) continue
      seen.current.add(w.appId)
      api.hintsOp({ op: 'opened', window: w.appId }).then(r => { if (r && r.ok) setV(r) }).catch(() => {})
    }
  }), [])
  if (!v || !v.active || !v.pending.length) return null
  const h = v.pending[0]
  const app = h.open ? byId(h.open) : null
  const op = (b) => api.hintsOp(b).then(r => { if (r && r.ok) setV(r) }).catch(() => {})
  if (folded) {
    return <button type="button" className="hn hn-pill" onClick={() => fold(false)}
                   aria-label={'show hint ' + (v.done + 1) + ' of ' + v.total}>Hint {v.done + 1} of {v.total}: {h.title}</button>
  }
  return (
    <aside className="hn" role="note" aria-label="hint">
      <div className="hn-top"><span className="hn-count">{v.done + 1} of {v.total}</span>
        <button type="button" className="hn-fold" onClick={() => fold(true)} aria-label="fold the hint away">–</button></div>
      <div className="hn-title">{h.title}</div>
      <div className="hn-body">{h.body}</div>
      <div className="hn-row">
        {app ? <Button size="sm" variant="primary" onClick={() => wm.open(h.open)}>Show me</Button> : null}
        <Button size="sm" onClick={() => op({ op: h.done_when === 'manual' ? 'done' : 'dismiss', id: h.id })}>Got it</Button>
        <Button size="sm" variant="ghost" onClick={() => op({ op: 'off' })}>No more hints</Button>
      </div>
    </aside>
  )
}
