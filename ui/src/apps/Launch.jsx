import { useEffect, useRef, useState } from 'react'
import * as api from '../api.js'
import { usePoll, Body } from './panel.jsx'
import { Chip, Button, Select, TextArea, Tabs } from '../kit/parts.jsx'
import LaunchSections, { differs } from './LaunchSections.jsx'

/* LAUNCH — which model and kernels she runs, saved setups, and the restart that applies
 * them (2026-10-27, his ask; layout A of the brainstorm: setups on top, one list of
 * controls, one bar that says what a restart would change).
 *
 * THE FILE IS THE TRUTH. Every edit goes to profiles/<name>.toml through
 * /v1/launch/edit carrying the hash this window loaded; a changed file answers 409 and
 * the window says so rather than overwrite. "Running" is `var/launched.json`, written
 * by serve.py at the last full launch, so "changed" means file vs what is actually up.
 * Restart is always the full one, through /v1/system, and the server refuses mid-turn.
 *
 * Prefix `ln-`, per the appRegistry CSS-ownership rule.
 */
const GAVE_UP_MS = 10 * 60 * 1000
const base = (p) => String(p ?? '').split(/[\\/]/).pop()
const isOn = (v) => v === true || v === 1 || v === '1'
// "2026-10-27T12:00:00+0100" -> ms. Date.parse wants the colon in the offset.
const ms = (s) => Date.parse(String(s || '').replace(/([+-]\d\d)(\d\d)$/, '$1:$2'))

export default function Launch() {
  const st = usePoll(api.launch, 0)
  const [tab, setTab] = useState('controls')
  const [msg, setMsg] = useState(null)        // {tone, text}
  const [stale, setStale] = useState(false)
  const [raw, setRaw] = useState(null)
  const [rawBase, setRawBase] = useState('')   // the hash the draft started from
  const [docOv, setDocOv] = useState(null)      // the newest doc a write returned
  const [rawErr, setRawErr] = useState('')
  const [rs, setRs] = useState(null)          // restart progress {at, phase, tail}
  const timer = useRef(null)

  const d = st.data
  /* THE NEWEST DOC WINS. A write returns the doc it made; a refresh can be dropped by
   * usePoll while one is in flight, and the next write would then carry the old hash and
   * 409 against our own edit. The override yields once a poll catches up to it. */
  const doc = docOv || (d && d.doc)
  const hash = doc && doc.hash
  useEffect(() => {
    if (docOv && d && d.doc.hash === docOv.hash) setDocOv(null)
  }, [d, docOv])

  useEffect(() => () => clearInterval(timer.current), [])

  /* One door for every write: 409 means the file moved under us. */
  const commit = async (fn) => {
    setMsg(null)
    let r
    try { r = await fn() } catch (e) {
      setMsg({ tone: 'err', text: 'could not reach the gateway: ' + (e.message || e) }); return false
    }
    if (r.status === 409) { setStale(true); return false }
    if (!r.ok) { setMsg({ tone: 'err', text: r.error || ('failed ' + r.status) }); return false }
    setStale(false)
    if (r.doc) setDocOv(r.doc)
    st.refresh()
    return r
  }
  const edit = (edits) => commit(() => api.launchEdit(edits, hash))

  const setupOp = async (b) => {
    const r = await commit(() => api.launchSetup({ ...b, base_hash: hash }))
    if (r && r.skipped && r.skipped.length)
      setMsg({ tone: 'warn', text: 'skipped: ' + JSON.stringify(r.skipped) })
  }
  const askName = (what, def = '') => (window.prompt(what, def) || '').trim()

  const startRestart = async () => {
    setMsg(null)
    if (rs) return
    const at = Date.now()
    setRs({ at, phase: 'requesting', tail: '', log: [] })   // before the await: no second click
    const r = await api.launchRestart().catch(() => null)
    if (!r || r.status !== 200) setRs(null)
    if (r && r.status === 409) { setMsg({ tone: 'warn', text: r.error || "she's mid-turn — try again when she finishes" }); return }
    if (!r || r.status !== 200) { setMsg({ tone: 'err', text: (r && r.error) || 'restart was not accepted' }); return }
    setRs(x => x && { ...x, phase: 'stopping' })
    clearInterval(timer.current)
    timer.current = setInterval(async () => {
      if (Date.now() - at > GAVE_UP_MS) {
        clearInterval(timer.current)
        setRs(s => s && { ...s, phase: 'gaveup' })
        return
      }
      try {
        const s = await api.launchStatus()
        const log = (s.log_tail || []).filter(Boolean)
        const tail = log.slice(-1)[0] || ''
        if (ms(s.launched_at) > at) {
          clearInterval(timer.current)
          setRs(null); st.refresh()
        } else setRs(x => x && { ...x, phase: 'loading', tail, log })
      } catch { setRs(x => x && x.phase !== 'gaveup' && { ...x, phase: 'stopping' }) }
    }, 3000)
  }

  const saveRaw = async () => {
    setRawErr('')
    let r
    try { r = await api.launchRaw(raw, rawBase) } catch (e) {
      setRawErr('could not reach the gateway: ' + (e.message || e)); return
    }
    if (r.status === 409) { setStale(true); return }
    if (!r.ok) { setRawErr(r.error || ('failed ' + r.status)); return }
    setStale(false); setRaw(null)
    if (r.doc) setDocOv(r.doc)
    st.refresh()
  }

  const reload = () => { setStale(false); setRaw(null); setDocOv(null); st.refresh() }

  return (
    <div className="ln">
      <Body state={st}>{() => {
        const vals = doc.values, run = d.launched && d.launched.values
        const ctl = d.controls
        const changed = run ? Object.keys(vals).filter(k => differs(k, vals[k], run[k])) : []
        const modelChanged = run && differs('paths.model', vals['paths.model'], run['paths.model'])
        const discard = () => {
          const edits = {}
          for (const k of changed) {
            if (!(k in run)) continue
            edits[k] = k === 'paths.model'
              ? String(vals[k]).slice(0, String(vals[k]).length - base(vals[k]).length) + base(run[k])
              : run[k]
          }
          if (Object.keys(edits).length) edit(edits)
        }
        const control = (c) => {
          const v = vals[c.key], was = run ? run[c.key] : undefined
          const ch = run && differs(c.key, v, was)
          const mark = ch
            ? <span className="ln-changed">changed — running: {c.key === 'paths.model' ? base(was) : String(was)}</span> : null
          if (c.kind === 'model') {
            const cur = base(v)
            const opts = d.models.includes(cur) ? d.models : [cur, ...d.models]
            return (
              <div className="ln-ctl" key={c.key}>
                <span className="ln-lab">{c.label}</span>
                <Select className="ln-pick" value={cur} aria-label={c.label}
                        onChange={e => edit({ [c.key]: String(v).slice(0, String(v).length - cur.length) + e.target.value })}>
                  {opts.map(m => <option key={m} value={m}>{m}</option>)}
                </Select>
                {mark}
              </div>
            )
          }
          if (c.kind === 'bool01' || c.kind === 'bool') {
            return (
              <label className="ln-ctl" key={c.key}>
                <input type="checkbox" checked={isOn(v)}
                       onChange={e => edit({ [c.key]: c.kind === 'bool01' ? (e.target.checked ? 1 : 0) : e.target.checked })} />
                <span className="ln-lab">{c.label}</span>
                {c.tag ? <small className="ln-dim">({c.tag})</small> : null}
                {mark}
              </label>
            )
          }
          return (
            <div className="ln-ctl" key={c.key}>
              <span className="ln-lab">{c.label}</span>
              <NumberBox value={v} int={c.kind === 'int'} label={c.label}
                         onSave={(n) => edit({ [c.key]: n })} />
              {mark}
            </div>
          )
        }
        const first = ctl.filter(c => c.kind === 'model' || c.kind.startsWith('bool'))
        const rest = ctl.filter(c => !first.includes(c))
        const cost = modelChanged ? d.cost.model_change : d.cost.same_model

        return (
          <>
            <div className="ln-head">
              <span>{d.profile}</span>
              {d.launched
                ? <Chip tone="neutral" title={d.launched.at}>running: {d.launched.setup || 'custom'}</Chip>
                : <Chip tone="warn">unknown — restart once to record it</Chip>}
            </div>
            <div className="ln-setups">
              {d.setups.map(s => (
                <span className="ln-setup" key={s.name}>
                  <Button size="sm" variant={s.running ? 'primary' : 'secondary'}
                          onClick={() => setupOp({ op: 'load', name: s.name })}>
                    {s.running ? '● Running: ' : ''}{s.name}
                  </Button>
                  <button type="button" className="ln-mini" title="rename"
                          onClick={() => { const n = askName('Rename setup', s.name); if (n && n !== s.name) setupOp({ op: 'rename', name: s.name, new: n }) }}>rename</button>
                  <button type="button" className="ln-mini" title="delete"
                          onClick={() => { if (window.confirm('Delete setup "' + s.name + '"?')) setupOp({ op: 'delete', name: s.name }) }}>delete</button>
                </span>
              ))}
              <Button size="sm" variant="ghost"
                      onClick={() => { const n = askName('Save the current controls as'); if (n) setupOp({ op: 'save', name: n }) }}>
                + save current as…
              </Button>
            </div>
            {d.loaded ? <div className="ln-dim ln-loaded">loaded: {d.loaded}</div> : null}

            {stale ? (
              <div className="ln-note ln-note-err" role="alert">
                the file changed — reload <Button size="sm" onClick={reload}>reload</Button>
              </div>
            ) : null}
            {msg ? <div className={'ln-note ln-note-' + msg.tone} role="alert">{msg.text}</div> : null}

            <Tabs label="Launch view" value={tab} onChange={setTab}
                  tabs={[{ id: 'controls', label: 'Controls' }, { id: 'raw', label: 'Raw toml' }]} />

            {tab === 'controls' ? (
              <div className="ln-body">
                <div className="ln-label">Model and kernels</div>
                {first.map(control)}
                <div className="ln-label">Memory and speed</div>
                {rest.map(control)}
                <details className="ln-else">
                  <summary className="ln-label">Everything else in the profile ({Object.keys(vals).length - ctl.length} values, by section)</summary>
                  <LaunchSections values={vals} help={doc.help || {}}
                                  skip={new Set(ctl.map(c => c.key))} onSave={edit} />
                </details>
              </div>
            ) : (
              <div className="ln-body">
                <TextArea className="ln-raw" spellCheck={false} aria-label="profile toml"
                          value={raw === null ? doc.text : raw}
                          onChange={e => { if (raw === null) setRawBase(hash); setRaw(e.target.value) }} />
                {rawErr ? <div className="ln-note ln-note-err" role="alert">{rawErr}</div> : null}
                <div className="ln-rawbar">
                  <Button variant="primary" disabled={raw === null || raw === doc.text} onClick={saveRaw}>Save</Button>
                  <Button variant="ghost" disabled={raw === null} onClick={() => { setRaw(null); setRawErr('') }}>revert</Button>
                </div>
              </div>
            )}

            {run && !rs && !changed.length ? null : <div className="ln-bar">
              {rs ? (
                <div className="ln-prog" role="status">
                  {rs.phase === 'stopping' ? 'stopping…'
                    : rs.phase === 'loading' ? 'loading…'
                    : rs.phase === 'requesting' ? 'asking her to restart…'
                    : 'gave up waiting after 10 minutes'}
                  {rs.phase === 'gaveup'
                    ? (rs.log && rs.log.length
                        ? <code className="ln-tail ln-log">{rs.log.join('\n')}</code>
                        : <span className="ln-dim">the gateway never came back</span>)
                    : rs.tail ? <code className="ln-tail">{rs.tail}</code> : null}
                  {rs.phase === 'gaveup' ? <Button size="sm" variant="ghost" onClick={() => { setRs(null); st.refresh() }}>dismiss</Button> : null}
                </div>
              ) : (
                <>
                  <div className="ln-count">
                    {run ? (changed.length === 1 ? '1 change not yet running'
                      : changed.length + ' changes not yet running') : 'unknown — restart once to record it'}
                  </div>
                  <div className="ln-cost ln-dim">{cost}</div>
                  <div className="ln-acts">
                    <Button variant="primary" disabled={!!rs} onClick={startRestart}>Restart her to apply</Button>
                    {run ? <Button variant="ghost" disabled={!changed.length} onClick={discard}>discard</Button> : null}
                  </div>
                </>
              )}
            </div>}
          </>
        )
      }}</Body>
    </div>
  )
}

/* A number that commits on blur or Enter, not per keystroke: every commit is a write to
 * her profile and a line in the change log. */
function NumberBox({ value, int, label, onSave }) {
  const [draft, setDraft] = useState(null)
  const commit = () => {
    const n = Number(draft)
    const shown = draft
    setDraft(null)
    if (shown === null || shown === '' || Number.isNaN(n) || n === value) return
    onSave(int ? Math.round(n) : n)
  }
  return <input className="ui-field ln-num" type="number" step={int ? 1 : 'any'} aria-label={label}
                value={draft ?? String(value ?? '')}
                onChange={e => setDraft(e.target.value)} onBlur={commit}
                onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur() }} />
}
