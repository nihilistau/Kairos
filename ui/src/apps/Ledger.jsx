import { useState } from 'react'
import { usePoll, Body } from './panel.jsx'
import { Button, Chip, Input, Select, TextArea } from '../kit/parts.jsx'
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

/* A ledger row. The head is a disclosure button (a keyboard opens it now; it was a
 * clickable div) that says whether it is open. Status is `lgr-s-<status>` — the bare
 * open/doing/done/dropped classes were built at runtime, where G-ROOM-CSS cannot see
 * them. Remove is danger and still only tombstones. `startOpen`/`startEdit` let G-ROOM-KIT
 * draw the body and the editor: a server render never runs a click. */
export function LedgerRow({ e, onSave, onDrop, onRestore, startOpen = false, startEdit = false }) {
  const [open, setOpen] = useState(startOpen || startEdit)
  const [d, setD] = useState(startEdit ? { ...e } : null)          // non-null while editing
  const hue = KIND_HUE[e.kind] ?? 205
  const edit = d || e

  return (
    <div className={'lgr lgr-s-' + e.status} style={{ '--h': hue }}>
      <button type="button" className="lgr-head" aria-expanded={open} onClick={() => setOpen(o => !o)}>
        <span className="lgr-mark" title={e.status}>{STATUS_MARK[e.status] || '○'}</span>
        <span className="lgr-title">{e.title}</span>
        {e.pinned ? <span className="lgr-pin" title="pinned">★</span> : null}
        <span className="lgr-owner" title={'raised by ' + e.owner}>{e.owner}</span>
      </button>

      {open ? (
        <div className="lgr-body">
          {d ? (
            <>
              <Input className="lgr-in" aria-label="title" value={edit.title}
                     onChange={ev => setD({ ...edit, title: ev.target.value })} />
              <TextArea className="lgr-in" aria-label="body" rows={4} value={edit.body || ''}
                        onChange={ev => setD({ ...edit, body: ev.target.value })} />
              <div className="lgr-ctl">
                <Select className="lgr-sel" aria-label="kind" value={edit.kind}
                        onChange={ev => setD({ ...edit, kind: ev.target.value })}>
                  {Object.keys(KIND_HUE).map(k => <option key={k}>{k}</option>)}
                </Select>
                <Select className="lgr-sel" aria-label="status" value={edit.status}
                        onChange={ev => setD({ ...edit, status: ev.target.value })}>
                  {['open', 'doing', 'done', 'dropped'].map(s => <option key={s}>{s}</option>)}
                </Select>
                <label className="lgr-chk">
                  <input type="checkbox" checked={!!edit.pinned}
                         onChange={ev => setD({ ...edit, pinned: ev.target.checked })} /> pin
                </label>
                <Button size="sm" onClick={() => { onSave(edit); setD(null) }}>save</Button>
                <Button size="sm" variant="ghost" onClick={() => setD(null)}>cancel</Button>
              </div>
            </>
          ) : (
            <>
              {e.body ? <p className="lgr-txt">{e.body}</p> : null}
              {e.refs?.length ? (
                <div className="lgr-refs">{e.refs.map((r, i) => <code key={i}>{r}</code>)}</div>
              ) : null}
              <div className="lgr-ctl">
                <Button size="sm" variant="ghost" onClick={() => setD({ ...e })}>edit</Button>
                {e.status === 'dropped'
                  ? <Button size="sm" onClick={() => onRestore(e.id)}>restore</Button>
                  : <Button size="sm" variant="danger" onClick={() => onDrop(e.id)}
                            title="tombstoned, not deleted — it stays in the file">remove</Button>}
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

/* The gates' health, split out so G-ROOM-KIT leg 12 can render it. The numbers are kit
 * Chips: red err (with a still dot), green ok, stale warn, and each red gate an err chip
 * carrying its failing count. They were bare good/bad/warn spans in literal colours. */
export function HealthView({ d }) {
  // gates only — measurement receipts assert nothing, so they are neither
  // green nor red and must not pad either number.
  const gates = (d.receipts || []).filter(r => r.kind !== 'measurement')
  const red = gates.filter(r => !r.ok)
  const stale = gates.filter(r => r.stale && r.ok)
  return (
    <div className="lgr-health" title={d.note}>
      {red.length
        ? <Chip tone="err" dot>{red.length + ' red'}</Chip>
        : <Chip tone="ok" dot>{d.total + ' green'}</Chip>}
      {stale.length ? <Chip tone="warn">{stale.length + ' stale'}</Chip> : null}
      {/* THE AGE IS NOT DECORATION. These are receipts of past runs, not a live
          verdict — the whole G-PF-PERSONA lesson was a green that meant nothing. */}
      <span className="muted">last recorded runs, not a live verdict</span>
      {red.map(r => <Chip key={r.name} tone="err" title={`${r.fail} failing`}>{r.name}</Chip>)}
    </div>
  )
}

function Health() {
  const h = usePoll(api.gateHealth, 60000)
  return <Body state={h}>{d => <HealthView d={d} />}</Body>
}

/* The window's body, split out so G-ROOM-KIT leg 12 can render it with a fixture. The
 * bar was a .chips row, but it was never a filter: "+ add" is an action, "N dropped" ADDS
 * the tombstoned rows to the list, and "N shown" is a count. So: a kit button, a pressed
 * toggle, and a count chip. The add form's "add" is the window's one primary. */
export function LedgerView({ d, showDropped, setShowDropped, adding, setAdding, act }) {
  const rows = (d.entries || []).filter(e => showDropped || e.status !== 'dropped')
  const kinds = d.kinds || Object.keys(KIND_HUE)
  return (
    <>
      <div className="lgr-bar">
        <Button size="sm" onClick={() => setAdding({ kind: 'noticed', title: '', body: '' })}>+ add</Button>
        <Button size="sm" variant="ghost" aria-pressed={showDropped} onClick={() => setShowDropped(v => !v)}>
          {(d.counts?.dropped || 0) + ' dropped'}
        </Button>
        <span className="lgr-count"><Chip>{rows.length + ' shown'}</Chip></span>
      </div>

      {adding ? (
        <div className="lgr lgr-adding" style={{ '--h': KIND_HUE[adding.kind] ?? 205 }}>
          <Input className="lgr-in" autoFocus aria-label="what is it, in one line"
                 placeholder="what is it, in one line" value={adding.title}
                 onChange={e => setAdding({ ...adding, title: e.target.value })} />
          <TextArea className="lgr-in" rows={3} aria-label="why it matters, and what would settle it"
                    placeholder="why it matters, and what would settle it" value={adding.body}
                    onChange={e => setAdding({ ...adding, body: e.target.value })} />
          <div className="lgr-ctl">
            <Select className="lgr-sel" aria-label="kind" value={adding.kind}
                    onChange={e => setAdding({ ...adding, kind: e.target.value })}>
              {kinds.map(k => <option key={k}>{k}</option>)}
            </Select>
            <Button size="sm" variant="primary" disabled={!adding.title.trim()}
                    onClick={() => { act({ op: 'add', ...adding }); setAdding(null) }}>add</Button>
            <Button size="sm" variant="ghost" onClick={() => setAdding(null)}>cancel</Button>
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
              <LedgerRow key={e.id} e={e}
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
              <LedgerRow key={e.id} e={e}
                         onSave={row => act({ op: 'edit', ...row })}
                         onDrop={id => act({ op: 'drop', id })}
                         onRestore={id => act({ op: 'restore', id })} />
            ))}
          </section>
        )
      })()}
    </>
  )
}

export default function Ledger() {
  const s = usePoll(api.ledger, 30000)
  const [showDropped, setShowDropped] = useState(false)
  const [adding, setAdding] = useState(null)

  async function act(payload) { await api.ledgerWrite(payload); s.refresh() }

  return (
    <div className="pad">
      <Health />
      <Body state={s}>{d => <LedgerView d={d} showDropped={showDropped} setShowDropped={setShowDropped}
                                        adding={adding} setAdding={setAdding} act={act} />}</Body>
    </div>
  )
}
