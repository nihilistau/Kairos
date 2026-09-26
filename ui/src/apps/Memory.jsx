import { useState, useEffect } from 'react'
import { usePoll, Body } from './panel.jsx'
import { Button, Chip, Input, Select, State, Tabs } from '../kit/parts.jsx'
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

/* What a conclusion rests on, split out so G-ROOM-KIT leg 12 can render it. Reading and
 * failing are the kit's states; a retired support keeps the SHARED `gone` (struck through
 * exactly as a retired row is), and each support's kind is a quiet kit chip. */
export function WhyView({ d, err, onClose }) {
  if (err) return <div className="mem-why"><State kind="error">{err}</State></div>
  if (!d) return <div className="mem-why"><State kind="loading">reading the receipts…</State></div>
  if (d.ok === false) return <div className="mem-why"><State kind="error">{d.error}</State></div>
  const sup = d.supports || []
  const dead = sup.filter(s => s.lifecycle)
  const dep = d.dependents || []
  return (
    <div className="mem-why">
      <div className="mem-why-head">
        {'drawn from ' + sup.length + ' row' + (sup.length === 1 ? '' : 's')
          + (d.row.support_days ? ' across ' + d.row.support_days + ' days' : '')
          + (dead.length ? ' — ' + dead.length + ' since retired' : '')
          + ((d.missing_supports || []).length ? ' — ' + d.missing_supports.length + ' no longer findable' : '')}
        <Button size="sm" variant="ghost" aria-label="close" onClick={onClose}>×</Button>
      </div>
      {sup.map((s, i) => (
        <div key={s.name || i} className={'mem-why-row' + (s.lifecycle ? ' gone' : '')}>
          <Chip>{s.kind || s.mem_class}</Chip>
          <span>{s.text}</span>
          {s.lifecycle ? <em className="muted">{' — retired' + (s.retired_because ? ': ' + s.retired_because : '')}</em> : null}
        </div>
      ))}
      {dep.length ? (
        <div className="mem-why-head">
          {dep.length} conclusion{dep.length === 1 ? '' : 's'} rest on this row — retiring it
          may orphan {dep.length === 1 ? 'it' : 'them'}
        </div>
      ) : null}
      {dep.map((s, i) => (
        <div key={'d' + i} className={'mem-why-row mem-why-dep' + (s.lifecycle ? ' gone' : '')}>
          <Chip>{s.kind || s.mem_class}</Chip><span>{s.text}</span>
        </div>
      ))}
    </div>
  )
}

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
  return <WhyView d={d} err={err} onClose={onClose} />
}

/* A row of memory — hers or his, and the text is theirs: drawn verbatim, never edited here
 * except through the wording box, which keeps the old words in `src`. The text is a
 * disclosure button (a keyboard opens the re-file box now). The class and status marks are
 * app-owned (`mem-c-*`: a class is a category whose colour is its legend, not a status);
 * the kind is a quiet kit chip. The core star is a pressed toggle named "core"; why and
 * re-file flip their text to ×, so each carries a steady name and aria-expanded.
 * `startOpen` lets G-ROOM-KIT draw the box: a server render never runs a click. */
export function MemRow({ r, onDone, startOpen = false }) {
  const [open, setOpen] = useState(startOpen)
  const [why, setWhy] = useState(false)
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [txt, setTxt] = useState(null)    // a WORDING correction; null = untouched
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
    <div className={'mem-row' + (open ? ' mem-open' : '')}>
      <button type="button" className="mem-t" aria-expanded={open} onClick={() => setOpen(!open)}
              title="click to re-file">{r.text}</button>
      <div className="mem-meta">
        <span className={'mem-cls mem-c-' + (r.mem_class || 'fact')}>{r.mem_class}</span>
        {r.kind ? <Chip>{r.kind}</Chip> : null}
        <span className={'mem-who mem-w-' + (r.speaker || 'user')}>{hers ? 'hers' : 'his'}</span>
        {/* CORE (2026-08-28): pinned identity. Leads the self block, never folded into a
            chapter. The star toggles it, through the same relabel door as everything. */}
        <Button size="sm" variant="ghost" disabled={!!busy} aria-pressed={!!r.core} aria-label="core"
                title={r.core ? 'core — pinned; click to unpin' : 'pin as core'}
                onClick={e => { e.stopPropagation(); send({ core: !r.core }) }}>
          {r.core ? '★' : '☆'}</Button>
        {r.ts ? <span>{String(r.ts).slice(0, 10)}</span> : null}
        {r.mentions > 1 ? <span title="times he said it">×{r.mentions}</span> : null}
        {r.recalled ? <span title="times recalled">↺{r.recalled}</span> : null}
        {r.salience != null ? (
          <span className="mem-sal" title={'salience ' + r.salience}>
            <i style={{ width: Math.min(100, r.salience * 14) + '%' }} /></span>
        ) : null}
        {/* STATUS, which this panel could never see. lifecycle.render frames from it and
            verdict.may_supersede rules on it — an inference must never look like
            testimony here, of all places, where he decides what to keep. */}
        {r.status && r.status !== 'observed' && r.status !== 'confirmed'
          ? <span className={'mem-cls mem-c-st-' + r.status} title="how this claim was arrived at">
              {r.status}</span> : null}
        <span className="mem-acts">
          {derived
            ? <Button size="sm" variant="ghost" aria-expanded={why} aria-label="why" onClick={() => setWhy(!why)}
                      title="what this conclusion was drawn from">{why ? '×' : 'why'}</Button>
            : null}
          <Button size="sm" variant="ghost" aria-expanded={open} aria-label="re-file"
                  onClick={() => setOpen(!open)}>{open ? '×' : 're-file'}</Button>
        </span>
      </div>
      {why ? <Why name={r.name} onClose={() => setWhy(false)} /> : null}
      {open ? (
        <div className="mem-edit-box">
          <label className="mem-lbl">whose
            <Select className="mem-sel" value={r.speaker || 'user'} disabled={!!busy}
                    onChange={e => send({ speaker: e.target.value })}>
              <option value="user">his</option>
              <option value="self">hers</option>
            </Select>
          </label>
          <label className="mem-lbl">class
            <Select className="mem-sel" value={r.mem_class || 'fact'} disabled={!!busy}
                    onChange={e => send({ mem_class: e.target.value })}>
              {CLASSES.map(c => <option key={c} value={c}>{c}</option>)}
            </Select>
          </label>
          <label className="mem-lbl">kind
            <Select className="mem-sel" value={r.kind || ''} disabled={!!busy}
                    onChange={e => send({ kind: e.target.value })}>
              {KINDS.map(k => <option key={k || 'none'} value={k}>{k || '(none)'}</option>)}
            </Select>
          </label>
          {/* THE WORDING ITSELF (2026-08-28). 25 rows said "The user ..." and the only
              remedy was retire-and-re-add, which loses mentions, first_seen and
              provenance to fix a phrasing. ops.relabel carries text now; the old words
              go into the src breadcrumb, so the history keeps what it used to say. */}
          <Input className="mem-txt" aria-label="correct the wording — Enter saves"
                 placeholder="correct the wording — Enter saves"
                 /* null = untouched (shows the row); '' = deliberately cleared.
                     `txt || r.text` snapped back the moment the field was emptied,
                     so the text could never be cleared to retype (2026-08-29 audit). */
                 value={txt === null ? (r.text || '') : txt} disabled={!!busy}
                 onChange={e => setTxt(e.target.value)}
                 onKeyDown={e => {
                   if (e.key === 'Enter' && txt && txt.trim() && txt.trim() !== r.text) {
                     send({ text: txt.trim() }); setTxt(null)
                   }
                 }} />
          <Button size="sm" variant="danger" onClick={retire} disabled={!!busy}>retire</Button>
          {busy ? <span className="muted">{busy}</span> : null}
          {err ? <span className="mem-err"><Chip tone="err" wrap>{err}</Chip></span> : null}
          {/* kind only means something in her lane; say so rather than hiding the box */}
          {!hers && r.kind ? <span className="muted">kind is her lane's label</span> : null}
        </div>
      ) : null}
    </div>
  )
}

/* The window's body, split out so G-ROOM-KIT leg 12 can render it with a fixture. Whose
 * rows is the kit's Tabs (it was already select-only). Core and retired were buttons with
 * no handler — pressing them did nothing — so they are count chips now. Add is the
 * window's one primary. Every row, live or retired, is her words or his, verbatim. */
export function MemoryView({ d, q, setQ, who, setWho, adding, setAdding, onAdd, refresh }) {
  const rows = d.facts || []
  /* NEWEST FIRST (2026-08-28, his report: "new memories are not rendered in the
   * memories panel but are in /ops.html"). The API returns file order — append
   * order — so the newest row sat at position 517 of 518 while this panel rendered
   * the FIRST 200. Every memory made this week was below the cap: present, live,
   * recallable, and invisible in the one window built to show them. Rows with no
   * ts (five repair-era ones) sort last, which is where unknown-age belongs. */
  const byNew = (a, b) => String(b.ts || '').localeCompare(String(a.ts || ''))
  const live = rows.filter(r => !r.lifecycle).sort(byNew)
  const gone = rows.filter(r => r.lifecycle).sort(byNew)
  const needle = q.trim().toLowerCase()
  const shown = live.filter(r =>
    (who === 'all' || (who === 'hers') === (r.speaker === 'self'))
    && (!needle || (r.text || '').toLowerCase().includes(needle)
        || (r.mem_class || '').includes(needle) || (r.kind || '').includes(needle)))
  const addPh = 'add a ' + (who === 'hers' ? 'memory of hers' : 'fact about him')

  return (
    <>
      <div className="mem-bar">
        <div className="mem-tabs">
          <Tabs value={who} label="whose rows" onChange={setWho}
                tabs={[{ id: 'all', label: live.length + ' live' },
                       { id: 'his', label: live.filter(r => r.speaker !== 'self').length + ' his' },
                       { id: 'hers', label: live.filter(r => r.speaker === 'self').length + ' hers' }]} />
        </div>
        <Chip title="pinned identity — lead the self block, never folded">
          {'★' + live.filter(r => r.core).length + ' core'}
        </Chip>
        <Chip>{gone.length + ' retired'}</Chip>
      </div>
      <div className="mem-tools">
        <Input className="mem-q" aria-label="filter — text, class or kind" placeholder="filter — text, class or kind"
               value={q} onChange={e => setQ(e.target.value)} />
        <Input className="mem-add" aria-label={addPh} placeholder={addPh}
               value={adding} onChange={e => setAdding(e.target.value)}
               onKeyDown={e => e.key === 'Enter' && onAdd()} />
        <Button variant="primary" onClick={onAdd} disabled={!adding.trim()}>add</Button>
      </div>
      {shown.length === 0 ? <State kind="empty">nothing matches.</State> : null}
      {shown.slice(0, 200).map((r, i) => (
        <MemRow key={r.name || i} r={r} onDone={refresh} />
      ))}
      {shown.length > 200 ? (
        <p className="muted">{'…' + (shown.length - 200) + ' more; narrow the filter.'}</p>
      ) : null}
      {gone.length ? <h4 className="muted">retired — kept, never deleted</h4> : null}
      {/* ...AND WHY IT DIED (2026-08-25). A tombstone rendered as bare text answers
          the audit lane's only question with silence, while `retired_because` and
          `superseded_by` sat on the row this list was already reading. The 25 rows
          with no breadcrumb at all are the repair-era ones (memory.orphan_tombstones);
          they say nothing here because there is nothing to say, which is itself
          worth seeing. */}
      {gone.slice(0, 60).map((r, i) => (
        <div key={'g' + i} className="mem-row gone">
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
}

export default function Memory() {
  const s = usePoll(api.memory, 30000)
  const [q, setQ] = useState('')
  const [who, setWho] = useState('all')
  const [adding, setAdding] = useState('')
  const refresh = () => s.refresh && s.refresh()

  async function add() {
    const fact = adding.trim()
    if (!fact) return
    await api.memoryAdd(fact, who === 'hers' ? 'self' : 'user')
    setAdding(''); refresh()
  }

  return (
    <div className="pad">
      <Body state={s}>{d => <MemoryView d={d} q={q} setQ={setQ} who={who} setWho={setWho}
                                        adding={adding} setAdding={setAdding} onAdd={add} refresh={refresh} />}</Body>
    </div>
  )
}
