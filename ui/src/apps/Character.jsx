import { useCallback, useEffect, useState } from 'react'
import * as api from '../api.js'
import { usePoll, Body } from './panel.jsx'
import { Button, Input, Select, TextArea } from '../kit/parts.jsx'
import { open } from '../windowManager.js'

/* CHARACTER — make her, a question at a time (2026-11-26, design §7b).
 *
 * The flow is DATA (harness/personality/character_flow.json): each step is a question
 * with why it matters, a hint, examples you can click, and the persona section the answer
 * becomes — shown live under the question, so you see what she will read about herself.
 * Every step but her name can be skipped; a skipped step leaves the template's own
 * section standing, so skipping is always safe.
 *
 * Two ends: a NEW companion (create), or THIS companion's persona rewritten section by
 * section (apply — each replaced section is retired, never deleted; Persona window has
 * them). Good practice sits in a side panel, said once, not repeated on every step.
 *
 * Prefix `ch-` (G-ROOM-CSS).
 */

const slug = (s) => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40)

function answerText(a) { return typeof a === 'string' ? a : (a && a.text) || '' }

function Step({ st, value, onChange }) {
  const v = value || (st.kind === 'line' || st.kind === 'text' || st.kind === 'lines' ? '' : {})
  const text = answerText(v)
  const setText = (t) => onChange(typeof v === 'string' || st.kind === 'line' || st.kind === 'text' || st.kind === 'lines' ? t : { ...v, text: t })
  const addExample = (ex) => setText(text ? text.replace(/\s*$/, st.kind === 'lines' ? '\n' : ' ') + ex : ex)
  return (
    <div className="ch-step">
      <div className="ch-q">{st.question}</div>
      {st.why ? <div className="ch-why">{st.why}</div> : null}
      {st.hint ? <div className="ch-hint"><b>Tip:</b> {st.hint}</div> : null}

      {st.kind === 'chips+text' ? (
        <div className="ch-chips">
          {st.chips.map(c => {
            const on = (v.chips || []).includes(c)
            return <button key={c} type="button" className={'ch-chip' + (on ? ' ch-on' : '')} aria-pressed={on}
                           onClick={() => onChange({ ...v, chips: on ? v.chips.filter(x => x !== c) : [...(v.chips || []), c] })}>{c}</button>
          })}
        </div>
      ) : null}
      {st.kind === 'choice+text' ? (
        <div className="ch-chips">
          {st.choices.map(c => {
            const on = v.choice === c
            return <button key={c} type="button" className={'ch-chip' + (on ? ' ch-on' : '')} aria-pressed={on}
                           onClick={() => onChange({ ...v, choice: on ? '' : c })}>{c}</button>
          })}
        </div>
      ) : null}

      {st.kind === 'line' ? <Input value={text} placeholder={st.examples ? 'e.g. ' + st.examples.slice(0, 3).join(', ') : ''}
                                   onChange={e => setText(e.target.value)} autoFocus /> : null}
      {st.kind === 'text' || st.kind === 'chips+text' || st.kind === 'choice+text'
        ? <TextArea rows={4} value={text} onChange={e => setText(e.target.value)} placeholder="in your own words — or click an example" /> : null}
      {st.kind === 'voice' ? <VoiceStep v={v} onChange={onChange} /> : null}
      {st.kind === 'you' ? (
        <div className="ch-row">
          <Input className="ch-grow" value={v.name || ''} onChange={e => onChange({ ...v, name: e.target.value })} placeholder="your name" aria-label="your name" />
          <Select className="ch-grow" value={v.pronouns || ''} onChange={e => onChange({ ...v, pronouns: e.target.value })} aria-label="your pronouns">
            <option value="">pronouns…</option>
            <option value="he/him/his">he / him</option>
            <option value="she/her/her">she / her</option>
            <option value="they/them/their">they / them</option>
          </Select>
        </div>
      ) : null}
      {st.kind === 'lines' ? <TextArea rows={5} value={text} onChange={e => setText(e.target.value)} placeholder={'one per line: name — who they are to you'} /> : null}

      {st.examples && st.kind !== 'line' ? (
        <div className="ch-ex">
          <div className="ch-ex-t">Examples — click to use</div>
          {st.examples.map(ex => <button key={ex} type="button" className="ch-ex-b" onClick={() => addExample(ex)}>{ex}</button>)}
        </div>
      ) : null}
      {st.kind === 'line' && st.examples ? (
        <div className="ch-chips">{st.examples.map(ex => <button key={ex} type="button" className="ch-chip" onClick={() => setText(ex)}>{ex}</button>)}</div>
      ) : null}
    </div>
  )
}

function VoiceStep({ v, onChange }) {
  const [voices, setVoices] = useState(null)
  useEffect(() => { api.characterFlow().then(f => setVoices(f.voices)).catch(() => {}) }, [])
  const method = v.method || 'lfm3'
  return (
    <div className="ch-voice">
      <label className="ch-radio"><input type="radio" checked={method === 'lfm3'} onChange={() => onChange({ ...v, method: 'lfm3' })} />
        <span><b>Local</b> — on this machine, offline, free</span></label>
      {method === 'lfm3' ? (
        <Select value={v.lfm3 || 'female'} onChange={e => onChange({ ...v, lfm3: e.target.value })} aria-label="local voice">
          {(voices ? voices.lfm3 : ['female', 'male']).map(x => <option key={x} value={x}>{x}</option>)}
        </Select>
      ) : null}
      <label className="ch-radio"><input type="radio" checked={method === 'xai'} onChange={() => onChange({ ...v, method: 'xai' })} />
        <span><b>xAI</b> — richer, needs your key (Setup window)</span></label>
      <Select value={v.xai || (voices && voices.suggested_xai) || ''} onChange={e => onChange({ ...v, xai: e.target.value })} aria-label="xAI voice">
        {(voices ? voices.xai : []).map(x => <option key={x} value={x}>{x}{voices && x === voices.suggested_xai ? ' (not used by anyone here yet)' : ''}</option>)}
      </Select>
      <div className="ch-why">The xAI voice is kept for her either way, so switching later in the Voice window just works.</div>
    </div>
  )
}

function Preview({ answers, stepId }) {
  const [secs, setSecs] = useState([])
  useEffect(() => {
    const t = setTimeout(() => { api.characterPreview(answers).then(r => setSecs(r.sections || [])).catch(() => {}) }, 250)
    return () => clearTimeout(t)
  }, [answers])
  const mine = stepId ? secs.filter(s => s.step === stepId) : secs
  if (!mine.length) return stepId ? <div className="ch-prev-empty">Skipped or empty: her template's own section stays.</div> : null
  return mine.map(s => (
    <div key={s.file} className="ch-prev">
      <div className="ch-prev-h">She will read <span className="ch-file">{s.file}</span></div>
      <div className="ch-prev-t">## {s.title}</div>
      <div className="ch-prev-b">{s.text}</div>
    </div>
  ))
}

function Review({ flow, answers, back }) {
  const [mode, setMode] = useState('new')
  const name = answerText(answers.name).trim()
  const [id, setId] = useState(slug(name))
  const [m, setM] = useState(null)
  const [busy, setBusy] = useState(false)
  const [current, setCurrent] = useState(null)
  useEffect(() => { api.companion().then(d => setCurrent(d.current)).catch(() => {}) }, [])
  const go = async () => {
    setBusy(true); setM(null)
    const r = mode === 'new' ? await api.characterCreate({ answers, id }) : await api.characterApply(answers)
    setBusy(false)
    if (!r.ok) { setM({ ok: false, text: r.error }); return }
    setM({ ok: true, text: mode === 'new'
      ? `${r.name} is made: ${r.sections.length} section(s) from your answers, the rest from the template; ${r.face ? 'default face and wardrobe' : 'no face yet'}; voice ${answers.voice && answers.voice.method === 'xai' ? 'xAI ' + r.voice : 'local'}${r.user ? '; you are her ' + r.user : ''}${r.people_added && r.people_added.length ? '; she knows ' + r.people_added.join(', ') : ''}. Start her with: python serve.py <profile> --companion=${r.id}`
      : `${r.sections.length} section(s) rewritten; the old ones are in the Persona window's retired list. ${r.note}` })
  }
  return (
    <div className="ch-step">
      <div className="ch-q">Ready</div>
      <Preview answers={answers} />
      <div className="ch-modes">
        <label className="ch-radio"><input type="radio" checked={mode === 'new'} onChange={() => setMode('new')} />
          <span><b>Make her a new companion</b> — beside the one running now; nothing of hers is touched</span></label>
        {mode === 'new' ? <div className="ch-row"><Input className="ch-grow" value={id} onChange={e => setId(slug(e.target.value))} aria-label="id" placeholder="id" /></div> : null}
        {current && current.name ? (
          <label className="ch-radio"><input type="radio" checked={mode === 'this'} onChange={() => setMode('this')} />
            <span><b>Rewrite {current.name}</b> with these sections — each one it replaces is retired, never deleted</span></label>
        ) : null}
      </div>
      <div className="ch-row">
        <Button onClick={back}>Back</Button>
        <Button variant="primary" disabled={busy || !name || (mode === 'new' && !id)} onClick={go}>
          {mode === 'new' ? 'Create her' : 'Rewrite ' + (current ? current.name : 'her')}</Button>
        <Button variant="ghost" onClick={() => open('persona')}>Open the Persona window</Button>
      </div>
      {m ? <div className={'ch-msg ' + (m.ok ? 'ch-ok' : 'ch-err')} role={m.ok ? 'status' : 'alert'}>{m.text}</div> : null}
    </div>
  )
}

export default function Character() {
  const state = usePoll(useCallback(() => api.characterFlow(), []), 0)
  const [i, setI] = useState(0)
  const [answers, setAnswers] = useState({})
  const [tips, setTips] = useState(true)
  return (
    <Body state={state}>
      {flow => {
        const steps = flow.steps
        const done = i >= steps.length
        const st = steps[Math.min(i, steps.length - 1)]
        const set = (val) => setAnswers(a => ({ ...a, [st.id]: val }))
        const hasName = answerText(answers.name).trim().length > 0
        return (
          <div className="ch pad">
            <div className="ch-top">
              <ol className="ch-steps">
                {steps.map((s, k) => (
                  <li key={s.id}><button type="button" className={'ch-dot' + (k === i ? ' ch-cur' : '') + (answers[s.id] ? ' ch-done' : '')}
                                         onClick={() => setI(k)} disabled={k > 0 && !hasName} title={s.title}>{s.title}</button></li>
                ))}
                <li><button type="button" className={'ch-dot' + (done ? ' ch-cur' : '')} disabled={!hasName} onClick={() => setI(steps.length)}>Ready</button></li>
              </ol>
              <Button size="sm" variant="ghost" onClick={() => setTips(t => !t)}>{tips ? 'Hide' : 'Show'} good practice</Button>
            </div>
            <div className={'ch-body' + (tips ? ' ch-with-tips' : '')}>
              <div className="ch-main">
                {done ? <Review flow={flow} answers={answers} back={() => setI(steps.length - 1)} /> : <>
                  <div className="ch-title">{st.title} <span className="ch-n">{i + 1} of {steps.length}</span></div>
                  <Step st={st} value={answers[st.id]} onChange={set} />
                  {st.section ? <Preview answers={answers} stepId={st.id} /> : null}
                  <div className="ch-row">
                    <Button disabled={i === 0} onClick={() => setI(i - 1)}>Back</Button>
                    {!st.required ? <Button variant="ghost" onClick={() => { setAnswers(a => { const n = { ...a }; delete n[st.id]; return n }); setI(i + 1) }}>Skip</Button> : null}
                    <Button variant="primary" disabled={st.required && !answerText(answers[st.id]).trim()} onClick={() => setI(i + 1)}>Next</Button>
                  </div>
                </>}
              </div>
              {tips ? (
                <aside className="ch-tips">
                  <div className="ch-tips-t">Good practice</div>
                  <ul>{(flow.good_practice || []).map(g => <li key={g}>{g}</li>)}</ul>
                </aside>
              ) : null}
            </div>
          </div>
        )
      }}
    </Body>
  )
}
