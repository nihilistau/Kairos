import { useState, useEffect } from 'react'
import { usePoll, Body } from './panel.jsx'
import * as api from '../api.js'

/* MEMORY — live rows and retired ones, and showing both is the point.
 *
 * NOTHING HERE IS EVER DELETED. forget() tombstones; supersede retires and keeps
 * the old row for provenance. Rendering retired rows as a visible category rather
 * than filtering them away is what makes that promise legible instead of merely
 * true — and it is also the check on a real failure mode: an earlier console said
 * "153 live" when 73 of those were retired.
 *
 * CURATION (2026-08-23, his ask). This was read-only and /ops.html was the only place
 * he could act. Now he can re-file a row from here: whose it is, what class it is, and
 * — for her lane — which KIND, which is what decides durability now
 * (lifecycle._HALF_LIFE_BY_KIND), not mem_class alone. A relabel keeps the row: the
 * text, the name, the timestamps, mentions, recalled and every breadcrumb survive, and
 * the change appends a dated note to `src` so provenance() reads the history.
 *
 * The vocabularies below are NOT a second copy of the registry — they are the subset an
 * operator has any business assigning by hand, and the SERVER rejects anything outside
 * memclass.CLASSES / NARRATIVE_KINDS regardless of what this file sends. The panel is a
 * convenience; ops.relabel is the law. */
const CLASSES = ['fact', 'preference', 'relationship', 'identity', 'event',
                 'self-narrative', 'feeling', 'private-secret']
const KINDS = ['', 'journal', 'thought', 'narration', 'dream', 'self_description',
               'spoke_up', 'feeling', 'chapter']

/* WHY — the read side of provenance (2026-08-25).
 *
 * `derived_from` had been written through one door, enforced by the 04:00 orphan sweep and
 * gated for three days, and NOTHING COULD PRINT IT. This panel could show a conclusion she
 * had drawn and had no way to say what it was drawn from, or that two of those things were
 * no longer true. Now a row that carries supports gets a `why` button, and it shows them
 * with their CURRENT liveness plus what rests on this row if he retires it — which is the
 * question the retire button right beside it makes him ask. */
function Why({ name, onClose }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  // In an EFFECT, not in render. Fetching during render re-fires on every render and the
  // setState re-renders — an infinite request loop against her own gateway, from a panel
  // whose whole job is to be safe to open.
  useEffect(() => {
    let live = true
    api.memoryWhy(name)
      .then(r => { if (live) setD(r) })
      .catch(e => { if (live) setErr(String(e).slice(0, 90)) })
    return () => { live = false }
  }, [name])
  if (err) return <div className="mem-why err">{err}</div>
  if (!d) return <div className="mem-why muted">reading the receipts…</div>
  if (d.ok === false) return <div className="mem-why err">{d.error}</div>
  const sup = d.supports || []
  const dead = sup.filter(s => s.lifecycle)
  const dep = d.dependents || []
  return (
    <div className="mem-why">
      <div className="why-head">
        drawn from {sup.length} row{sup.length === 1 ? '' : 's'}
        {d.row.support_days ? ' across ' + d.row.support_days + ' days' : ''}
        {dead.length ? ' — ' + dead.length + ' since retired' : ''}
        {(d.missing_supports || []).length
          ? ' — ' + d.missing_supports.length + ' no longer findable' : ''}
        <button className="mem-edit" onClick={onClose}>×</button>
      </div>
      {sup.map((s, i) => (
        <div key={s.name || i} className={'why-row' + (s.lifecycle ? ' gone' : '')}>
          <span className="cls c-kind">{s.kind || s.mem_class}</span>
          <span>{s.text}</span>
          {s.lifecycle ? <em className="muted"> — retired{
            s.retired_because ? ': ' + s.retired_because : ''}</em> : null}
        </div>
      ))}
      {dep.length ? (
        <div className="why-head">
          {dep.length} conclusion{dep.length === 1 ? '' : 's'} rest on this row — retiring it
          may orphan {dep.length === 1 ? 'it' : 'them'}
        </div>
      ) : null}
      {dep.map((s, i) => (
        <div key={'d' + i} className={'why-row dep' + (s.lifecycle ? ' gone' : '')}>
          <span className="cls c-kind">{s.kind || s.mem_class}</span><span>{s.text}</span>
        </div>
      ))}
    </div>
  )
}

function MemRow({ r, onDone }) {
  const [open, setOpen] = useState(false)
  const [why, setWhy] = useState(false)
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const hers = r.speaker === 'self'
  const derived = (r.derived_from || []).length > 0

  async function send(body) {
    setBusy('…'); setErr('')
    try {
      const res = await api.memoryRelabel({ name: r.name, ...body })
      if (!res || res.ok === false) setErr((res && res.error) || 'refused')
      else onDone()
    } catch (e) { setErr(String(e).slice(0, 80)) }
    setBusy('')
  }
  async function retire() {
    if (!window.confirm('Retire this row? It is tombstoned, never deleted.')) return
    setBusy('…')
    try { await api.memoryForget(r.name); onDone() } catch (e) { setErr(String(e).slice(0, 80)) }
    setBusy('')
  }

  return (
    <div className={'mem' + (open ? ' mem-open' : '')}>
      <div className="t" onClick={() => setOpen(!open)} title="click to re-file">{r.text}</div>
      <div className="meta">
        <span className={'cls c-' + (r.mem_class || 'fact')}>{r.mem_class}</span>
        {r.kind ? <span className="cls c-kind">{r.kind}</span> : null}
        <span className={'who w-' + (r.speaker || 'user')}>{hers ? 'hers' : 'his'}</span>
        {r.ts ? <span>{String(r.ts).slice(0, 10)}</span> : null}
        {r.mentions > 1 ? <span title="times he said it">×{r.mentions}</span> : null}
        {r.recalled ? <span title="times recalled">↺{r.recalled}</span> : null}
        {r.salience != null ? (
          <span className="sal" title={'salience ' + r.salience}>
            <i style={{ width: Math.min(100, r.salience * 14) + '%' }} /></span>
        ) : null}
        {/* STATUS, which this panel could never see. lifecycle.render frames from it and
            verdict.may_supersede rules on it — an inference must never look like
            testimony here, of all places, where he decides what to keep. */}
        {r.status && r.status !== 'observed' && r.status !== 'confirmed'
          ? <span className={'cls c-st-' + r.status} title="how this claim was arrived at">
              {r.status}</span> : null}
        {derived
          ? <button className="mem-edit" onClick={() => setWhy(!why)}
                    title="what this conclusion was drawn from">{why ? '×' : 'why'}</button>
          : null}
        <button className="mem-edit" onClick={() => setOpen(!open)}>{open ? '×' : 're-file'}</button>
      </div>
      {why ? <Why name={r.name} onClose={() => setWhy(false)} /> : null}
      {open ? (
        <div className="mem-edit-box">
          <label>whose
            <select value={r.speaker || 'user'} disabled={!!busy}
                    onChange={e => send({ speaker: e.target.value })}>
              <option value="user">his</option>
              <option value="self">hers</option>
            </select>
          </label>
          <label>class
            <select value={r.mem_class || 'fact'} disabled={!!busy}
                    onChange={e => send({ mem_class: e.target.value })}>
              {CLASSES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <label>kind
            <select value={r.kind || ''} disabled={!!busy}
                    onChange={e => send({ kind: e.target.value })}>
              {KINDS.map(k => <option key={k || 'none'} value={k}>{k || '(none)'}</option>)}
            </select>
          </label>
          <button className="danger" onClick={retire} disabled={!!busy}>retire</button>
          {busy ? <span className="muted">{busy}</span> : null}
          {err ? <span className="err">{err}</span> : null}
          {/* kind only means something in her lane; say so rather than hiding the box */}
          {!hers && r.kind ? <span className="muted">kind is her lane's label</span> : null}
        </div>
      ) : null}
    </div>
  )
}

export default function Memory() {
  const s = usePoll(api.memory, 30000)
  const [q, setQ] = useState('')
  const [who, setWho] = useState('all')
  const [adding, setAdding] = useState('')

  return (
    <div className="pad">
      <Body state={s}>{d => {
        const rows = d.facts || []
        const live = rows.filter(r => !r.lifecycle)
        const gone = rows.filter(r => r.lifecycle)
        const needle = q.trim().toLowerCase()
        const shown = live.filter(r =>
          (who === 'all' || (who === 'hers') === (r.speaker === 'self'))
          && (!needle || (r.text || '').toLowerCase().includes(needle)
              || (r.mem_class || '').includes(needle) || (r.kind || '').includes(needle)))

        async function add() {
          const fact = adding.trim()
          if (!fact) return
          await api.memoryAdd(fact, who === 'hers' ? 'self' : 'user')
          setAdding(''); s.refresh && s.refresh()
        }

        return (
          <>
            <div className="chips">
              <button className={who === 'all' ? 'on' : ''} onClick={() => setWho('all')}>
                {live.length} live</button>
              <button className={who === 'his' ? 'on' : ''} onClick={() => setWho('his')}>
                {live.filter(r => r.speaker !== 'self').length} his</button>
              <button className={who === 'hers' ? 'on' : ''} onClick={() => setWho('hers')}>
                {live.filter(r => r.speaker === 'self').length} hers</button>
              <button className="r-off">{gone.length} retired</button>
            </div>
            <div className="mem-tools">
              <input placeholder="filter — text, class or kind" value={q}
                     onChange={e => setQ(e.target.value)} />
              <input placeholder={'add a ' + (who === 'hers' ? 'memory of hers' : 'fact about him')}
                     value={adding} onChange={e => setAdding(e.target.value)}
                     onKeyDown={e => e.key === 'Enter' && add()} />
              <button onClick={add} disabled={!adding.trim()}>add</button>
            </div>
            {shown.length === 0 ? <p className="muted">nothing matches.</p> : null}
            {shown.slice(0, 200).map((r, i) => (
              <MemRow key={r.name || i} r={r} onDone={() => s.refresh && s.refresh()} />
            ))}
            {shown.length > 200 ? (
              <p className="muted">…{shown.length - 200} more; narrow the filter.</p>
            ) : null}
            {gone.length ? <h4 className="muted">retired — kept, never deleted</h4> : null}
            {/* ...AND WHY IT DIED (2026-08-25). A tombstone rendered as bare text answers
                the audit lane's only question with silence, while `retired_because` and
                `superseded_by` sat on the row this list was already reading. The 25 rows
                with no breadcrumb at all are the repair-era ones (memory.orphan_tombstones);
                they say nothing here because there is nothing to say, which is itself
                worth seeing. */}
            {gone.slice(0, 60).map((r, i) => (
              <div key={'g' + i} className="mem gone">
                {r.text}
                {r.retired_because || r.superseded_by ? (
                  <em className="muted"> — {r.retired_because
                    || (r.superseded_by === 'supports-retired'
                        ? 'its supports were retired'
                        : 'replaced by a later row')}</em>
                ) : null}
              </div>
            ))}
          </>
        )
      }}</Body>
    </div>
  )
}
