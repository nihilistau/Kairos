import { useCallback, useState } from 'react'
import * as api from '../api.js'
import { usePoll, Body } from './panel.jsx'
import { Button, Chip, Input, State, TextArea } from '../kit/parts.jsx'
import { open } from '../windowManager.js'

/* PERSONA — who she is, as titled sections you can edit (2026-11-26, design §7b).
 *
 * Her persona is a folder of fragments (persona/); each is one card here, in the order she
 * reads them. Edit a title or the text, move it up or down, add a section, put a template
 * section back, or retire one. NOTHING IS DELETED: an edit keeps the previous text in the
 * retired list, retiring moves the file aside, and both come back with Restore
 * (harness/personality/sections.py).
 *
 * Sections the machine needs (memory, the board, sight, thinking…) are hers too and are
 * shown the same way; the ones that switch on with a feature say so (`when`).
 *
 * Edits apply from her NEXT session: her prefix is cached for the life of the process, and
 * the window says so rather than pretending otherwise.
 *
 * Prefix `ps-` (G-ROOM-CSS).
 */

function Card({ s, i, n, move, refresh, setM }) {
  const [edit, setEdit] = useState(false)
  const [title, setTitle] = useState(s.title)
  const [text, setText] = useState(s.text)
  const op = async (b, ok) => {
    const r = await api.personaSectionsOp(b)
    setM(r.ok ? { ok: true, text: ok + ' ' + (r.note || '') } : { ok: false, text: r.error })
    refresh()
    return r.ok
  }
  return (
    <div className={'ps-card' + (s.included ? '' : ' ps-off')}>
      <div className="ps-head">
        <span className="ps-title">{s.title}</span>
        <span className="ps-meta">{s.file}{s.when ? ' · only when ' + s.when : ''}</span>
        {!s.included ? <Chip tone="neutral">not in use now</Chip> : null}
        {s.from_template && s.as_template ? <Chip tone="neutral">as shipped</Chip> : null}
      </div>
      {edit ? (
        <div className="ps-edit">
          <Input value={title} onChange={e => setTitle(e.target.value)} aria-label="title" />
          <TextArea rows={Math.min(14, Math.max(4, text.split('\n').length + 1))} value={text} onChange={e => setText(e.target.value)} aria-label="text" />
          <div className="ps-row">
            <Button variant="primary" size="sm" onClick={async () => { if (await op({ op: 'save', file: s.file, title, text }, 'Saved.')) setEdit(false) }}>Save</Button>
            <Button size="sm" variant="ghost" onClick={() => { setEdit(false); setTitle(s.title); setText(s.text) }}>Cancel</Button>
          </div>
        </div>
      ) : <div className="ps-text">{s.text}</div>}
      {!edit ? (
        <div className="ps-row">
          <Button size="sm" onClick={() => setEdit(true)}>Edit</Button>
          <Button size="sm" variant="ghost" disabled={i === 0} onClick={() => move(i, -1)} aria-label="move up">↑</Button>
          <Button size="sm" variant="ghost" disabled={i === n - 1} onClick={() => move(i, 1)} aria-label="move down">↓</Button>
          {s.from_template && !s.as_template ? <Button size="sm" variant="ghost" onClick={() => op({ op: 'reset', file: s.file }, 'Back to the template (your text is in Retired).')}>Reset to template</Button> : null}
          <Button size="sm" variant="ghost" onClick={() => op({ op: 'retire', file: s.file }, 'Retired — restore it below if you change your mind.')}>Retire</Button>
        </div>
      ) : null}
    </div>
  )
}

export default function Persona() {
  const state = usePoll(useCallback(() => api.personaSections(), []), 0)
  const [m, setM] = useState(null)
  const [nt, setNt] = useState('')
  const [nx, setNx] = useState('')
  const [showRetired, setShowRetired] = useState(false)
  return (
    <Body state={state}>
      {d => {
        const secs = d.sections || []
        const move = async (i, dir) => {
          const files = secs.map(s => s.file)
          const j = i + dir
          ;[files[i], files[j]] = [files[j], files[i]]
          const r = await api.personaSectionsOp({ op: 'reorder', files })
          setM(r.ok ? { ok: true, text: 'Moved. ' + r.note } : { ok: false, text: r.error })
          state.refresh()
        }
        const add = async () => {
          const last = secs.length ? secs[secs.length - 1].order : 0
          const r = await api.personaSectionsOp({ op: 'add', title: nt, text: nx, order: Math.min(999, last + 5) })
          setM(r.ok ? { ok: true, text: 'Added. ' + r.note } : { ok: false, text: r.error })
          if (r.ok) { setNt(''); setNx('') }
          state.refresh()
        }
        const simple = async (b, ok) => {
          const r = await api.personaSectionsOp(b)
          setM(r.ok ? { ok: true, text: ok + ' ' + (r.note || '') } : { ok: false, text: r.error })
          state.refresh()
        }
        return (
          <div className="ps pad">
            <div className="ps-lead">
              Who she is, in the order she reads it. Changes apply from her next session.
              <Button size="sm" variant="ghost" onClick={() => open('character')}>Guided: answer questions instead</Button>
            </div>
            {m ? <div className={'ps-msg ' + (m.ok ? 'ps-ok' : 'ps-err')} role={m.ok ? 'status' : 'alert'}>{m.text}</div> : null}
            {secs.length ? secs.map((s, i) => <Card key={s.file + s.order} s={s} i={i} n={secs.length} move={move} refresh={state.refresh} setM={setM} />)
              : <State title="No sections yet">Add one below, or use the guided flow.</State>}

            <div className="ps-sec">
              <div className="ps-sec-t">Add a section</div>
              <Input value={nt} onChange={e => setNt(e.target.value)} placeholder="title, e.g. What makes you laugh" aria-label="new section title" />
              <TextArea rows={4} value={nx} onChange={e => setNx(e.target.value)} placeholder="write to her: “You…”" aria-label="new section text" />
              <div className="ps-row"><Button disabled={!nt.trim()} onClick={add}>Add section</Button></div>
            </div>

            {(d.missing || []).length ? (
              <div className="ps-sec">
                <div className="ps-sec-t">From the template, not in her persona</div>
                {d.missing.map(x => (
                  <div key={x.file} className="ps-row">
                    <span className="ps-title">{x.title}</span>
                    <Button size="sm" variant="ghost" onClick={() => simple({ op: 'add_template', file: x.file }, 'Added from the template.')}>Add it</Button>
                  </div>
                ))}
              </div>
            ) : null}

            {(d.retired || []).length ? (
              <div className="ps-sec">
                <button type="button" className="ps-toggle" onClick={() => setShowRetired(v => !v)}>
                  Retired and earlier versions ({d.retired.length}) {showRetired ? '▴' : '▾'}</button>
                {showRetired ? d.retired.map(x => (
                  <div key={x.name} className="ps-row">
                    <span className="ps-title">{x.title || x.file}</span><span className="ps-meta">{x.name}</span>
                    <Button size="sm" variant="ghost" onClick={() => simple({ op: 'restore', name: x.name }, 'Restored.')}>Restore</Button>
                  </div>
                )) : null}
              </div>
            ) : null}

            <div className="ps-sec">
              <div className="ps-sec-t">Good practice</div>
              <ul className="ps-tips">{(d.good_practice || []).map(g => <li key={g}>{g}</li>)}</ul>
            </div>
          </div>
        )
      }}
    </Body>
  )
}
