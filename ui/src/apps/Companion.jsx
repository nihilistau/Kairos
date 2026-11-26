import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from '../api.js'
import { usePoll, Body } from './panel.jsx'
import { Button, Chip, Input, Row, Select, State, Tabs } from '../kit/parts.jsx'
import { open } from '../windowManager.js'

/* COMPANION — who she is, as a thing you can save, carry, restart and undo.
 *
 * Three tabs, one rule each:
 *   Back up & export   a .kairos bundle of the parts you tick; it runs NOW (it only reads)
 *   Load & reset       SCHEDULED: this gateway has her stores open and never moves them;
 *                      serve.py applies the change between this gateway and the next, so
 *                      the window says "at the next start" and offers the restart
 *   Companions         every home on this machine; a NEW one can be made from a bundle now
 *
 * NOTHING IS DELETED, and the window says so where it matters: a reset moves the old
 * contents into the home's archive and writes a bundle of them first, and "Undo last
 * change" puts them back (harness/bundle.py). A reset asks you to type her name — the one
 * action here you cannot take by a stray click.
 *
 * Prefix `cp-` (G-ROOM-CSS: one owner per prefix).
 */

const mb = (n) => (n >= 1e9 ? (n / 1e9).toFixed(1) + ' GB' : (n / 1e6).toFixed(1) + ' MB')
const LABEL = { personality: 'Personality', history: 'History', working: 'Receipts & logs',
  face: 'Face & wardrobe', episodes: 'Episodes' }
const OPWORD = { reset: 'Reset', load: 'Load', undo: 'Undo the last change' }

function Parts({ parts, value, onChange, only }) {
  return (
    <div className="cp-parts">
      {parts.filter(p => !only || only(p)).map(p => (
        <label key={p.id} className="cp-part">
          <input type="checkbox" checked={value.includes(p.id)}
                 onChange={e => onChange(e.target.checked ? [...value, p.id] : value.filter(x => x !== p.id))} />
          <span className="cp-part-t">{LABEL[p.id] || p.id}</span>
          <span className="cp-part-b">{p.about}</span>
        </label>
      ))}
    </div>
  )
}

function Msg({ m }) {
  if (!m) return null
  return <div className={'cp-msg ' + (m.ok ? 'cp-ok' : 'cp-err')} role={m.ok ? 'status' : 'alert'}>{m.text}</div>
}

function Pending({ d, refresh }) {
  const [busy, setBusy] = useState(false)
  const [m, setM] = useState(null)
  const p = d.pending
  if (!p) return null
  const restart = async () => {
    setBusy(true)
    const r = await api.systemWrite({ op: 'restart_gateway' }).catch(e => ({ ok: false, error: String(e) }))
    setBusy(false)
    setM(r.ok === false ? { ok: false, text: r.error || 'the restart was refused' }
      : { ok: true, text: 'Restarting — the change is applied before she comes back. This window reconnects by itself.' })
  }
  const cancel = async () => { await api.companionCancel(); refresh() }
  return (
    <div className="cp-pending" role="status">
      <div><b>Scheduled:</b> {OPWORD[p.op]}{p.parts && p.parts.length ? ' — ' + p.parts.map(x => LABEL[x] || x).join(' and ') : ''}
        {p.bundle ? ' from ' + p.bundle : ''}. It happens the next time she starts.</div>
      <div className="cp-row">
        <Button variant="primary" size="sm" disabled={busy} onClick={restart}>Restart her now (about 20 s)</Button>
        <Button size="sm" variant="ghost" onClick={cancel}>Cancel</Button>
      </div>
      <Msg m={m} />
    </div>
  )
}

function ExportTab({ d, refresh }) {
  const [parts, setParts] = useState(d.parts.filter(p => p.default).map(p => p.id))
  const [busy, setBusy] = useState(false)
  const [m, setM] = useState(null)
  const fileRef = useRef(null)
  const go = async () => {
    setBusy(true); setM(null)
    const r = await api.companionExport(parts)
    setBusy(false)
    setM(r.ok ? { ok: true, text: `Saved ${r.name} — ${r.files} files, ${mb(r.bytes)}.` }
      : { ok: false, text: r.error })
    refresh()
  }
  const upload = async (e) => {
    const f = e.target.files && e.target.files[0]
    if (!f) return
    setBusy(true); setM({ ok: true, text: `Uploading ${f.name}…` })
    const r = await api.companionUpload(f)
    setBusy(false); e.target.value = ''
    setM(r.ok ? { ok: true, text: `${r.name} is checked and ready to load (${r.parts.join(', ')}).` }
      : { ok: false, text: r.error })
    refresh()
  }
  return (
    <div className="cp-tab">
      <div className="cp-sec">
        <div className="cp-title">Save her as a bundle</div>
        <div className="cp-hint">A <code>.kairos</code> file you can keep, move to another machine, or load later. Saving only reads, so it is safe while she is running.</div>
        <Parts parts={d.parts} value={parts} onChange={setParts} />
        <div className="cp-row">
          <Button variant="primary" disabled={busy || !parts.length} onClick={go}>Save bundle</Button>
          <Button disabled={busy} onClick={() => fileRef.current && fileRef.current.click()}>Add a bundle from this computer…</Button>
          <input ref={fileRef} type="file" accept=".kairos" onChange={upload} hidden />
        </div>
        <Msg m={m} />
      </div>
      <div className="cp-sec">
        <div className="cp-title">Bundles</div>
        <div className="cp-hint">Kept in <code>{d.bundle_dir}</code>. The ones named <i>before-…</i> were written automatically before a reset or load.</div>
        {d.bundles.length ? d.bundles.map(b => (
          <Row key={b.name} title={b.name}
               meta={(b.error ? '!! ' + b.error : (b.parts || []).map(x => LABEL[x] || x).join(' + ')) + ' · ' + mb(b.size)}
               trail={<a className="cp-link" href={api.companionBundleUrl(b.name)} download={b.name}>Download</a>} />
        )) : <State title="No bundles yet">Save one above.</State>}
      </div>
    </div>
  )
}

function ResetTab({ d, refresh }) {
  const name = d.current.name
  const [rparts, setRparts] = useState([])
  const [typed, setTyped] = useState('')
  const [bundle, setBundle] = useState('')
  const [lparts, setLparts] = useState([])
  const [m, setM] = useState(null)
  const usable = d.bundles.filter(b => !b.error)
  const chosen = usable.find(b => b.name === bundle)
  const sched = async (b) => {
    setM(null)
    const r = await api.companionSchedule(b)
    setM(r.ok ? { ok: true, text: 'Scheduled. Restart her (button at the top) to apply it.' } : { ok: false, text: r.error })
    refresh()
  }
  const last = (d.history || []).find(h => h.op === 'reset' || h.op === 'load')
  return (
    <div className="cp-tab">
      <Msg m={m} />
      <div className="cp-sec">
        <div className="cp-title">Start fresh</div>
        <div className="cp-hint">Clears what you tick, back to a blank slate. Nothing is deleted: the old contents move to her archive, a bundle of them is saved first, and <b>Undo</b> below puts them back.</div>
        <Parts parts={d.parts} value={rparts} onChange={setRparts} only={p => p.changeable} />
        <div className="cp-row">
          <Input className="cp-grow" placeholder={`type ${name} to confirm`} value={typed} onChange={e => setTyped(e.target.value)} />
          <Button variant="danger" disabled={!rparts.length || typed.trim() !== name}
                  onClick={() => sched({ op: 'reset', parts: rparts })}>Reset at next start</Button>
        </div>
      </div>
      <div className="cp-sec">
        <div className="cp-title">Load from a bundle</div>
        <div className="cp-hint">Replaces the parts you tick with the bundle's. Her current ones go to the archive, as with a reset.</div>
        <div className="cp-row">
          <Select className="cp-grow" value={bundle} onChange={e => { setBundle(e.target.value); setLparts([]) }}>
            <option value="">choose a bundle…</option>
            {usable.map(b => <option key={b.name} value={b.name}>{b.name}</option>)}
          </Select>
        </div>
        {chosen ? <Parts parts={d.parts} value={lparts} onChange={setLparts}
                         only={p => p.changeable && (chosen.parts || []).includes(p.id)} /> : null}
        <div className="cp-row">
          <Button disabled={!chosen || !lparts.length}
                  onClick={() => sched({ op: 'load', bundle, parts: lparts })}>Load at next start</Button>
        </div>
      </div>
      <div className="cp-sec">
        <div className="cp-title">Undo</div>
        {last ? <>
          <div className="cp-hint">Last change: {OPWORD[last.op]} of {last.parts.map(x => LABEL[x] || x).join(' and ')} on {last.ts}.</div>
          <Button onClick={() => sched({ op: 'undo' })}>Undo it at next start</Button>
        </> : <div className="cp-hint">Nothing to undo.</div>}
      </div>
      {(d.history || []).length ? (
        <div className="cp-sec">
          <div className="cp-title">What has changed</div>
          {d.history.map(h => <Row key={h.ts + h.op} title={OPWORD[h.op] || h.op}
                                   meta={h.ts + ' · ' + (h.parts || []).map(x => LABEL[x] || x).join(', ')} />)}
        </div>
      ) : null}
    </div>
  )
}

/* The first-run hints' one switch (harness/hints.py): show them again, or off. */
function HintsRow() {
  const [h, setH] = useState(null)
  const [m, setM] = useState('')
  const load = useCallback(() => api.hints().then(setH).catch(() => {}), [])
  useEffect(() => { load() }, [load])
  const go = async (op) => { const r = await api.hintsOp({ op }); if (r.ok) { setH(r); setM(op === 'reset' ? 'Hints are back — the first one is at the bottom right.' : 'Hints are off.') } }
  if (!h) return null
  return (
    <div className="cp-row">
      <span className="cp-hint">First-run hints: {h.state && h.state.off ? 'off' : h.active ? `on (${h.done} of ${h.total} done)` : h.why}.</span>
      <Button size="sm" variant="ghost" onClick={() => go('reset')}>Show them again</Button>
      {h.active ? <Button size="sm" variant="ghost" onClick={() => go('off')}>Turn off</Button> : null}
      {m ? <span className="cp-hint">{m}</span> : null}
    </div>
  )
}

function CompanionsTab({ d, refresh }) {
  const usable = d.bundles.filter(b => !b.error)
  const [bundle, setBundle] = useState('')
  const [id, setId] = useState('')
  const [nm, setNm] = useState('')
  const [m, setM] = useState(null)
  const make = async () => {
    const r = await api.companionNew({ bundle, id, name: nm })
    setM(r.ok ? { ok: true, text: `Made ${r.id}. Start her with: python serve.py <profile> --companion=${r.id}` }
      : { ok: false, text: r.error })
    refresh()
  }
  /* A NEW COMPANION FROM NOTHING — not blank: a persona with her name in it, the default
     face and wardrobe, and a voice no one else here uses (harness/companion_create.py).
     The id follows the name until you edit it yourself. */
  const [cName, setCName] = useState('')
  const [cId, setCId] = useState('')
  const [cIdEdited, setCIdEdited] = useState(false)
  const [cVoice, setCVoice] = useState(d.suggested_voice || '')
  const [cm, setCm] = useState(null)
  const [sm, setSm] = useState(null)
  const switchTo = async (h) => {
    if (!window.confirm(`Switch to ${h.name}? ${d.current.name} stops and ${h.name} starts in her place.`)) return
    const r = await api.companionSwitch(h.id)
    setSm(r.ok ? { ok: true, text: r.note + '. This window reconnects by itself.' } : { ok: false, text: r.error })
  }
  const slug = (s) => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40)
  const create = async () => {
    const r = await api.companionCreate({ id: cId, name: cName, voice: cVoice })
    setCm(r.ok ? { ok: true, text: `Made ${r.name}: persona named, ${r.face ? 'default face and wardrobe' : 'no face (' + r.face_why + ')'}, local voice (${r.voice} kept for xAI). Start her with: python serve.py <profile> --companion=${r.id}` }
      : { ok: false, text: r.error })
    refresh()
  }
  return (
    <div className="cp-tab">
      <div className="cp-sec">
        <div className="cp-title">Create a new companion</div>
        <div className="cp-row">
          <Button variant="primary" onClick={() => open('character')}>Guided: who is she? (recommended)</Button>
          <span className="cp-hint">A few questions with hints and examples; skip any of them. Or make her quickly below.</span>
        </div>
        <div className="cp-hint">She starts with a persona that knows her name, the default face and wardrobe (give her her own later in Wardrobe), and her own voice — the local one on this machine by default; the xAI voice you pick here is kept for when you switch. Nothing of anyone else's is touched.</div>
        <div className="cp-row">
          <Input className="cp-grow" placeholder="her name" value={cName}
                 onChange={e => { setCName(e.target.value); if (!cIdEdited) setCId(slug(e.target.value)) }} />
          <Input className="cp-grow" placeholder="id" value={cId}
                 onChange={e => { setCId(slug(e.target.value)); setCIdEdited(true) }} />
          <Select className="cp-grow" value={cVoice} onChange={e => setCVoice(e.target.value)} aria-label="voice">
            {(d.voices || []).map(v => <option key={v} value={v}>xAI voice: {v}</option>)}
          </Select>
          <Button disabled={!cName.trim() || !cId} onClick={create}>Quick create</Button>
        </div>
        <Msg m={cm} />
      </div>
      <div className="cp-sec">
        <div className="cp-title">On this machine</div>
        {d.homes.map(h => (
          <Row key={h.dir} title={h.name + (h.id !== h.name ? ' (' + h.id + ')' : '')} meta={h.error || h.dir}
               trail={<>{h.current ? <Chip tone="ok">this one</Chip> : null}{h.live && !h.current ? <Chip tone="warn">running</Chip> : null}
                 {!h.current && !h.error ? <Button size="sm" onClick={() => switchTo(h)}>Switch to {h.name}</Button> : null}</>} />
        ))}
        <HintsRow />
        <div className="cp-hint">Switching restarts her as the other companion; on this machine's own engine the model reloads too (a couple of minutes). Or start one from a terminal: <code>kairos.bat</code>.</div>
        <Msg m={sm} />
      </div>
      <div className="cp-sec">
        <div className="cp-title">A new companion from a bundle</div>
        <div className="cp-hint">Safe at any time: a new home is made beside hers, and nothing of hers is touched.</div>
        <div className="cp-row">
          <Select className="cp-grow" value={bundle} onChange={e => setBundle(e.target.value)}>
            <option value="">choose a bundle…</option>
            {usable.map(b => <option key={b.name} value={b.name}>{b.name}</option>)}
          </Select>
        </div>
        <div className="cp-row">
          <Input className="cp-grow" placeholder="id (e.g. ivy)" value={id} onChange={e => setId(e.target.value.toLowerCase())} />
          <Input className="cp-grow" placeholder="her name (optional)" value={nm} onChange={e => setNm(e.target.value)} />
          <Button disabled={!bundle || !id} onClick={make}>Make her</Button>
        </div>
        <Msg m={m} />
      </div>
    </div>
  )
}

export default function Companion() {
  const state = usePoll(useCallback(() => api.companion(), []), 15000)
  const [tab, setTab] = useState('export')
  return (
    <Body state={state}>
      {d => {
        if (!d.current) return <State title="No companion home">{d.no_home}</State>
        if (d.current.error) return <State kind="error" title="Her home could not be read">{d.current.error}</State>
        return (
          <div className="cp pad">
            <div className="cp-head">
              <span className="cp-name">{d.current.name}</span>
              <span className="cp-dim">{d.current.home}</span>
            </div>
            <Pending d={d} refresh={state.refresh} />
            <Tabs label="companion" value={tab} onChange={setTab}
                  tabs={[{ id: 'export', label: 'Back up & export' }, { id: 'reset', label: 'Load & reset' },
                         { id: 'homes', label: 'Companions' }]} />
            {tab === 'export' ? <ExportTab d={d} refresh={state.refresh} />
              : tab === 'reset' ? <ResetTab d={d} refresh={state.refresh} />
              : <CompanionsTab d={d} refresh={state.refresh} />}
          </div>
        )
      }}
    </Body>
  )
}
