import { useState } from 'react'
import { usePoll, Body } from './panel.jsx'
import * as api from '../api.js'

/* DECISIONS — the things only he can settle, with a button each.
 *
 * WHY IT EXISTS (2026-08-23, his ask). A running companion accumulates questions that
 * are not engineering and not hers: arm this knob or not, is this row mislabelled,
 * should she keep doing X. They used to live in three bad places — a reply that scrolls
 * away, a ledger row that says "owed" forever, or my head between sessions. None of
 * those is a queue and none of them tells you what is waiting.
 *
 * WHAT IT IS NOT. Not her memory: nothing here reaches her prefix, her recall or her
 * journal. Not the ledger either — docs/OFF-BY-DEFAULT.md records what is OFF and why,
 * permanently, for a reader; this records what is UNDECIDED, transiently, for a decider.
 *
 * `kind` is the contract and it is shown on every card, because "what happens when I
 * click this" should never be a guess:
 *    once   a one-off. The answer IS the deliverable; I read it and do the work.
 *    route  applied by code the moment it is chosen (a knob, a relabel).
 *    note   a judgement recorded for the record, nothing to execute.
 *
 * Deciding APPENDS. The question and every previous verdict stay on disk, so changing
 * his mind is history rather than a rewrite — the same discipline as the memory store. */
const KIND_HELP = {
  once: 'one-off — your answer is the deliverable; I pick it up and do the work',
  route: 'applied immediately by code when you choose',
  note: 'recorded for the record; nothing runs',
}

function Card({ d, onDone }) {
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [note, setNote] = useState('')

  async function choose(choice) {
    setBusy(choice); setErr('')
    try {
      const res = await api.decide(d.id, choice, note)
      if (!res || res.ok === false) setErr((res && res.error) || 'refused')
      else onDone()
    } catch (e) { setErr(String(e).slice(0, 90)) }
    setBusy('')
  }

  return (
    <div className="dec">
      <div className="dec-head">
        <span className={'dec-kind dec-k-' + d.kind} title={KIND_HELP[d.kind] || ''}>{d.kind}</span>
        {d.area ? <span className="dec-area">{d.area}</span> : null}
        <span className="dec-title">{d.title}</span>
      </div>
      {d.body ? <div className="dec-body">{d.body}</div> : null}
      {d.detail ? <pre className="dec-detail">{d.detail}</pre> : null}
      <div className="dec-actions">
        {(d.options || []).map(o => (
          <button key={o} disabled={!!busy} className={busy === o ? 'on' : ''}
                  onClick={() => choose(o)}>{o}</button>
        ))}
        <input placeholder="why (optional, kept with the answer)" value={note}
               onChange={e => setNote(e.target.value)} />
        {err ? <span className="err">{err}</span> : null}
      </div>
    </div>
  )
}

export default function Decisions() {
  const s = usePoll(api.decisions, 20000)
  const [showPast, setShowPast] = useState(false)
  return (
    <div className="pad">
      <Body state={s}>{d => {
        const open = d.open || []
        const past = d.decided || []
        return (
          <>
            <div className="chips">
              <button className="on">{open.length} waiting on you</button>
              <button className={showPast ? 'on' : ''} onClick={() => setShowPast(!showPast)}>
                {past.length} decided</button>
            </div>
            {open.length === 0 ? (
              <p className="muted">Nothing is waiting. Anything I cannot settle myself
                lands here rather than in a reply that scrolls away.</p>
            ) : null}
            {open.map(x => <Card key={x.id} d={x} onDone={() => s.refresh && s.refresh()} />)}
            {showPast && past.length ? <h4 className="muted">decided — kept, never removed</h4> : null}
            {showPast ? past.slice().reverse().map(x => (
              <div key={x.id} className="dec dec-done">
                <div className="dec-head">
                  <span className="dec-choice">{x.choice}</span>
                  <span className="dec-title">{x.title}</span>
                </div>
                {x.note ? <div className="dec-body muted">{x.note}</div> : null}
                <div className="muted">{String(x.decided_at || '').slice(0, 10)}</div>
              </div>
            )) : null}
          </>
        )
      }}</Body>
    </div>
  )
}
