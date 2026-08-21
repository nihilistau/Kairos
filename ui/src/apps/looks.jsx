import { useState } from 'react'
import { When } from '../room/When.jsx'

/* looks.jsx — SHARED row renderer for the search and research windows (2026-08-21).
 *
 * One ledger feeds both windows, so one component renders its rows — two copies
 * of the row is the house bug class in miniature. Each row carries a HIS/HERS
 * chip (`by` on the ledger row): his manual lookups and her tool calls live in
 * the same record, she may read and use his, but hers are her activity and the
 * chip is what keeps that distinction visible instead of tribal knowledge.
 *
 * Prefix `rsc-` — the research window owns the style, search borrows it whole.
 */
export function ByChip({ by }) {
  const him = by === 'him'
  return (
    <span className={'rsc-by ' + (him ? 'rsc-him' : 'rsc-hers')}
          title={him ? 'you looked this up' : 'she looked this up — hers'}>
      {him ? 'his' : 'hers'}
    </span>
  )
}

export function LookRows({ rows, empty }) {
  const [open, setOpen] = useState(null)
  if (!rows.length) return <div className="muted">{empty}</div>
  return rows.map((r, i) => {
    const id = r.receipt || (r.ended + ':' + i)
    const expanded = open === id
    return (
      <div key={id} className={'rsc-row' + (expanded ? ' on' : '')}>
        <button className="rsc-head" onClick={() => setOpen(expanded ? null : id)}>
          <span className="rsc-k">{r.kind || 'look'}</span>
          <ByChip by={r.by} />
          <span className="rsc-t">{r.title || r.query || '(untitled)'}</span>
          {r.ended ? <When at={r.ended} /> : null}
          <span className="rsc-ok">{r.ok === false ? 'failed' : ''}</span>
        </button>
        {expanded ? (
          <div className="rsc-body">
            {r.query && r.query !== r.title ? <div className="rsc-q">{r.query}</div> : null}
            <pre>{r.summary || '(no text came back)'}</pre>
            {(r.sources || []).length ? (
              <ul className="rsc-src">
                {r.sources.map(u => <li key={u}><a href={u} target="_blank" rel="noreferrer">{u}</a></li>)}
              </ul>
            ) : null}
            {r.provenance ? <div className="muted">{r.provenance}</div> : null}
          </div>
        ) : null}
      </div>
    )
  })
}

/* The manual box — his lane into the same ledger. `run` does the POST and
 * resolves when the answer is in; the ledger poll behind the panel picks the
 * new row up on its next beat. */
export function AskRow({ placeholder, busyLabel, run, onDone }) {
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const go = async () => {
    const query = q.trim()
    if (!query || busy) return
    setBusy(true); setErr('')
    try {
      const r = await run(query)
      if (r && r.ok === false) setErr(r.error || 'failed')
      else setQ('')
      onDone && onDone()
    } catch (e) {
      setErr(String(e).slice(0, 120))
    } finally { setBusy(false) }
  }
  return (
    <div className="rsc-askrow">
      <input className="rsc-ask" value={q} placeholder={placeholder}
             disabled={busy}
             onChange={e => setQ(e.target.value)}
             onKeyDown={e => e.key === 'Enter' && go()} />
      <button className="rsc-go" disabled={busy || !q.trim()} onClick={go}>
        {busy ? busyLabel : 'go'}
      </button>
      {err ? <span className="rsc-err">{err}</span> : null}
    </div>
  )
}
