import { useState } from 'react'
import { usePoll, Body } from './panel.jsx'
import * as api from '../api.js'

/* LEDGER — the plan, the parked, and everything noticed and not touched.
 *
 * WHY IT EXISTS. Commits keep the work; nothing kept the rest. The plan lived in a
 * plan file that went stale the moment the plan changed, and everything spotted in
 * passing lived in the last paragraph of a reply and then scrolled away. In one
 * evening that channel carried the deferred shared browser, the idea of replacing
 * the avatar's vector art with a generated image set, a gate failing on a Windows
 * console encoding, and fourteen unindexed gates — all real, none of them anywhere
 * a later session would look.
 *
 * IT IS A VIEW, LIKE EVERY OTHER PANEL. The room owns no state: rows live in
 * harness/control/ledger.py and arrive over /v1/ledger. What is different is that
 * this one is WRITABLE, so it carries the one rule the store enforces and the UI
 * must not contradict — REMOVE IS A TOMBSTONE. `drop` sets status and keeps the
 * row; there is no delete anywhere beneath this button. Dropped rows are hidden
 * behind a toggle rather than gone, because an idea that keeps coming back is
 * itself information.
 */

const KIND_HUE = { plan: 200, parked: 265, noticed: 45, idea: 160, risk: 8 }
const STATUS_MARK = { open: '○', doing: '◐', done: '●', dropped: '✕' }

function Row({ e, onSave, onDrop, onRestore }) {
  const [open, setOpen] = useState(false)
  const [d, setD] = useState(null)          // non-null while editing
  const hue = KIND_HUE[e.kind] ?? 205
  const edit = d || e

  return (
    <div className={'lgr ' + e.status} style={{ '--h': hue }}>
      <div className="lgr-head" onClick={() => setOpen(o => !o)}>
        <span className="lgr-mark" title={e.status}>{STATUS_MARK[e.status] || '○'}</span>
        <span className="lgr-title">{e.title}</span>
        {e.pinned ? <span className="lgr-pin" title="pinned">★</span> : null}
        <span className="lgr-owner" title={'raised by ' + e.owner}>{e.owner}</span>
      </div>

      {open ? (
        <div className="lgr-body">
          {d ? (
            <>
              <input className="lgr-in" value={edit.title}
                     onChange={ev => setD({ ...edit, title: ev.target.value })} />
              <textarea className="lgr-in" rows={4} value={edit.body || ''}
                        onChange={ev => setD({ ...edit, body: ev.target.value })} />
              <div className="lgr-ctl">
                <select value={edit.kind} onChange={ev => setD({ ...edit, kind: ev.target.value })}>
                  {Object.keys(KIND_HUE).map(k => <option key={k}>{k}</option>)}
                </select>
                <select value={edit.status} onChange={ev => setD({ ...edit, status: ev.target.value })}>
                  {['open', 'doing', 'done', 'dropped'].map(s => <option key={s}>{s}</option>)}
                </select>
                <label className="lgr-chk">
                  <input type="checkbox" checked={!!edit.pinned}
                         onChange={ev => setD({ ...edit, pinned: ev.target.checked })} /> pin
                </label>
                <button className="on" onClick={() => { onSave(edit); setD(null) }}>save</button>
                <button onClick={() => setD(null)}>cancel</button>
              </div>
            </>
          ) : (
            <>
              {e.body ? <p className="lgr-txt">{e.body}</p> : null}
              {e.refs?.length ? (
                <div className="lgr-refs">{e.refs.map((r, i) => <code key={i}>{r}</code>)}</div>
              ) : null}
              <div className="lgr-ctl">
                <button onClick={() => setD({ ...e })}>edit</button>
                {e.status === 'dropped'
                  ? <button onClick={() => onRestore(e.id)}>restore</button>
                  : <button className="r-off" onClick={() => onDrop(e.id)}
                            title="tombstoned, not deleted — it stays in the file">remove</button>}
                <span className="lgr-when">
                  {new Date(e.updated * 1000).toLocaleString()}
                </span>
              </div>
            </>
          )}
        </div>
      ) : null}
    </div>
  )
}

function Health() {
  const h = usePoll(api.gateHealth, 60000)
  return (
    <Body state={h}>{d => {
      // gates only — measurement receipts assert nothing, so they are neither
      // green nor red and must not pad either number.
      const gates = (d.receipts || []).filter(r => r.kind !== 'measurement')
      const red = gates.filter(r => !r.ok)
      const stale = gates.filter(r => r.stale && r.ok)
      return (
        <div className="lgr-health" title={d.note}>
          <span className={red.length ? 'bad' : 'good'}>
            {red.length ? `${red.length} red` : `${d.total} green`}
          </span>
          {stale.length ? <span className="warn">{stale.length} stale</span> : null}
          {/* THE AGE IS NOT DECORATION. These are receipts of past runs, not a live
              verdict — the whole G-PF-PERSONA lesson was a green that meant nothing. */}
          <span className="muted">last recorded runs, not a live verdict</span>
          {red.map(r => <span key={r.name} className="bad" title={`${r.fail} failing`}>{r.name}</span>)}
        </div>
      )
    }}</Body>
  )
}

export default function Ledger() {
  const s = usePoll(api.ledger, 30000)
  const [showDropped, setShowDropped] = useState(false)
  const [adding, setAdding] = useState(null)

  async function act(payload) { await api.ledgerWrite(payload); s.refresh() }

  return (
    <div className="pad ledger">
      <Health />
      <Body state={s}>{d => {
        const rows = (d.entries || []).filter(e => showDropped || e.status !== 'dropped')
        const kinds = d.kinds || Object.keys(KIND_HUE)
        return (
          <>
            <div className="chips">
              <button className="on" onClick={() => setAdding({ kind: 'noticed', title: '', body: '' })}>+ add</button>
              <button className={showDropped ? 'on' : ''} onClick={() => setShowDropped(v => !v)}>
                {d.counts?.dropped || 0} dropped
              </button>
              <span className="muted">{rows.length} shown</span>
            </div>

            {adding ? (
              <div className="lgr adding" style={{ '--h': KIND_HUE[adding.kind] ?? 205 }}>
                <input className="lgr-in" autoFocus placeholder="what is it, in one line"
                       value={adding.title}
                       onChange={e => setAdding({ ...adding, title: e.target.value })} />
                <textarea className="lgr-in" rows={3} placeholder="why it matters, and what would settle it"
                          value={adding.body}
                          onChange={e => setAdding({ ...adding, body: e.target.value })} />
                <div className="lgr-ctl">
                  <select value={adding.kind}
                          onChange={e => setAdding({ ...adding, kind: e.target.value })}>
                    {kinds.map(k => <option key={k}>{k}</option>)}
                  </select>
                  <button className="on" disabled={!adding.title.trim()}
                          onClick={() => { act({ op: 'add', ...adding }); setAdding(null) }}>add</button>
                  <button onClick={() => setAdding(null)}>cancel</button>
                </div>
              </div>
            ) : null}

            {kinds.map(k => {
              const mine = rows.filter(e => e.kind === k)
              if (!mine.length) return null
              return (
                <section key={k} className="lgr-sec" style={{ '--h': KIND_HUE[k] ?? 205 }}>
                  <h4>{k} <span className="muted">{d.kind_blurb?.[k]}</span></h4>
                  {mine.map(e => (
                    <Row key={e.id} e={e}
                         onSave={row => act({ op: 'edit', ...row })}
                         onDrop={id => act({ op: 'drop', id })}
                         onRestore={id => act({ op: 'restore', id })} />
                  ))}
                </section>
              )
            })}
            {/* THE OTHER BUCKET (2026-08-24 audit, R5). Rows render only inside their
                kind's section, so a row whose kind drifted from d.kinds was counted in
                "N shown" and drawn NOWHERE — a standing list that can silently hide a
                row is the one failure a standing list exists to prevent. */}
            {(() => {
              const known = new Set(kinds)
              const stray = rows.filter(e => !known.has(e.kind))
              if (!stray.length) return null
              return (
                <section className="lgr-sec" style={{ '--h': 0 }}>
                  <h4>other <span className="muted">
                    rows whose kind the panel does not know — they are still yours
                  </span></h4>
                  {stray.map(e => (
                    <Row key={e.id} e={e}
                         onSave={row => act({ op: 'edit', ...row })}
                         onDrop={id => act({ op: 'drop', id })}
                         onRestore={id => act({ op: 'restore', id })} />
                  ))}
                </section>
              )
            })()}
          </>
        )
      }}</Body>
    </div>
  )
}
