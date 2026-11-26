import { useCallback, useEffect, useState } from 'react'
import * as api from '../api.js'
import { usePoll, Body } from './panel.jsx'
import { Button, Chip, Input, Select } from '../kit/parts.jsx'
import { open } from '../windowManager.js'

/* GET SET UP — everything she needs, fetched and configured (2026-11-26, design §4;
 * harness/setup/, ported from the Illustrated Primer's setup centre).
 *
 * Steps: this machine (what it can run, and a suggestion) → an engine → a model (the
 * uncensored ones behind a plain warning) → where to put it (sizes against free space) →
 * download (resumable, each file checked against its published hash) → approve the engine
 * (nothing downloaded runs until you say so, by its SHA-256) — for her native engine, then its
 * transcoder, and convert the model to .sp → write the profile, and make her (Character) or pick
 * a companion → the command that starts her.
 *
 * The browser never sends a URL or a path to fetch: it asks for a plan by ids and can only
 * start the plan it was shown.
 *
 * Prefix `in-` (G-ROOM-CSS).
 */

const gb = (b) => (b / 2 ** 30).toFixed(1) + ' GB'

function Step({ n, title, done, children }) {
  return (
    <div className={'in-step' + (done ? ' in-done' : '')}>
      <div className="in-st"><span className="in-n">{n}</span>{title}{done ? <Chip tone="ok">done</Chip> : null}</div>
      {children}
    </div>
  )
}

export default function Install() {
  const state = usePoll(useCallback(() => api.setupKit(), []), 2500)
  const [engine, setEngine] = useState('')
  const [model, setModel] = useState('')
  const [dest, setDest] = useState('')
  const [plan, setPlan] = useState(null)
  const [ack, setAck] = useState(false)
  const [m, setM] = useState(null)
  const [prof, setProf] = useState({ name: 'local', companion: '', base_url: '' })
  const [made, setMade] = useState(null)
  const [comps, setComps] = useState([])
  useEffect(() => { api.companion().then(d => setComps((d.homes || []).filter(h => !h.error))).catch(() => {}) }, [])
  return (
    <Body state={state}>
      {d => {
        const eng = engine || d.suggest.engine
        const mod = model || d.suggest.model
        const dst = dest || d.default_dest
        const p = plan || d.plan
        const st = d.state || {}
        const external = (d.engines.find(e => e.id === eng) || {}).external
        const mk = async () => {
          setM(null); setPlan(null)
          const r = await api.setupOp('plan', { model: mod, engine: eng, dest: dst })
          if (r.ok) setPlan(r.plan); else setM({ ok: false, text: r.error })
        }
        const go = async () => {
          const r = await api.setupOp('start', { licence_ok: ack })
          setM(r.ok ? { ok: true, text: 'Downloading — you can close this window; it carries on.' } : { ok: false, text: r.error })
          state.refresh()
        }
        const approve = async () => { const r = await api.setupOp('approve', { sha256: d.approval.sha256 }); setM(r.ok ? { ok: true, text: 'Approved.' } : { ok: false, text: r.error }); state.refresh() }
        const conv = d.convert || {}
        const convert = async () => {
          const r = await api.setupOp('convert')
          setM(r.ok ? { ok: true, text: 'Converting — a few minutes for the model; you can close this window.' } : { ok: false, text: r.error })
          state.refresh()
        }
        const write = async () => {
          const r = await api.setupOp('profile', prof)
          if (r.ok) setMade(r); else setM({ ok: false, text: r.error })
        }
        return (
          <div className="in pad">
            <Step n="1" title="This machine" done>
              <div className="in-hint">
                {d.hardware.gpus.length ? d.hardware.gpus.map(g => `${g.name} (${g.vram_gb} GB)`).join(', ') : 'No NVIDIA card found'}
                {' · '}{d.hardware.ram_gb} GB memory. <b>Suggested:</b> {d.suggest.why}
              </div>
            </Step>

            <Step n="2" title="How she runs" done={!!engine || !!p}>
              <div className="in-cards">
                {d.engines.map(e => (
                  <button key={e.id} type="button" className={'in-card' + (eng === e.id ? ' in-on' : '')} onClick={() => { setEngine(e.id); setPlan(null) }}>
                    <div className="in-ct">{e.title}{d.suggest.engine === e.id ? <Chip tone="ok">suggested</Chip> : null}</div>
                    <div className="in-cb">{e.about}</div>
                  </button>
                ))}
              </div>
            </Step>

            <Step n="3" title="Her model" done={!!model || !!p}>
              <div className="in-cards">
                {d.models.map(x => (
                  <button key={x.id} type="button" className={'in-card' + (mod === x.id ? ' in-on' : '') + (x.uncensored ? ' in-warn' : '')} onClick={() => { setModel(x.id); setPlan(null) }}>
                    <div className="in-ct">{x.title}{d.suggest.model === x.id ? <Chip tone="ok">suggested</Chip> : null}{x.uncensored ? <Chip tone="warn">uncensored</Chip> : null}</div>
                    <div className="in-cb">{x.about} About {x.approx_gb} GB; {x.min_vram_gb}+ GB card.</div>
                  </button>
                ))}
              </div>
              {(d.models.find(x => x.id === mod) || {}).uncensored ? <div className="in-warnbox" role="note">{d.warning}</div> : null}
            </Step>

            <Step n="4" title="Where it goes" done={!!p}>
              <div className="in-row">
                <Input className="in-grow" value={dst} onChange={e => { setDest(e.target.value); setPlan(null) }} aria-label="download folder" />
                <Button onClick={mk}>Check sizes</Button>
              </div>
              {p ? (
                <div className="in-plan">
                  {p.items.map(i => <div key={i.name} className="in-file"><span>{i.name}</span><span>{gb(i.size)}</span></div>)}
                  <div className={'in-hint' + (p.fits ? '' : ' in-bad')}>
                    {gb(p.need_bytes)} to download, {gb(p.free_bytes)} free there{p.fits ? '.' : ' — not enough; choose a folder on a bigger drive.'}
                  </div>
                </div>
              ) : null}
            </Step>

            <Step n="5" title="Download" done={!!st.finished}>
              {p ? <>
                <label className="in-ack"><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} />
                  <span>I accept the model's licence: <a href={p.licence.url} target="_blank" rel="noreferrer">{p.licence.name}</a>{p.uncensored ? ', and I understand it is uncensored' : ''}.</span></label>
                <div className="in-row">
                  <Button variant="primary" disabled={!ack || !p.fits || st.running} onClick={go}>Download</Button>
                  {st.running ? <Button variant="ghost" onClick={() => api.setupOp('cancel').then(state.refresh)}>Pause</Button> : null}
                </div>
                {st.running || st.done ? <div className="in-hint">{st.running ? 'Fetching ' + st.current + ' — ' + gb(st.bytes || 0) : ''} {st.done && st.done.length ? ' · done: ' + st.done.join(', ') : ''}</div> : null}
                {st.error ? <div className="in-hint in-bad">{st.error} — press Download again to resume.</div> : null}
              </> : <div className="in-hint">Check sizes first.</div>}
            </Step>

            {d.approval ? (
              <Step n="6" title={d.approval.what === 'transcoder' ? 'Approve the converter' : 'Approve the engine'}>
                <div className="in-hint">Nothing downloaded runs until you approve it. <b>{d.approval.path}</b>, from {d.approval.publisher} release {d.approval.release}.</div>
                <code className="in-sha">SHA-256 {d.approval.sha256}</code>
                <div className="in-row"><Button variant="primary" onClick={approve}>Approve it</Button></div>
              </Step>
            ) : null}

            {conv.needed || conv.running || conv.error ? (
              <Step n="6b" title="Convert her model">
                <div className="in-hint">Her native engine reads the model as .sp, converted once on this machine. It goes beside the download: <b>{conv.to}</b></div>
                <div className="in-row"><Button variant="primary" disabled={conv.running || !!d.approval} onClick={convert}>{conv.running ? 'Converting…' : 'Convert'}</Button></div>
                {conv.error ? <div className="in-hint in-bad">{conv.error}</div> : null}
              </Step>
            ) : null}

            <Step n="7" title="Her profile" done={!!made}>
              <div className="in-row">
                <Input className="in-grow" value={prof.name} onChange={e => setProf({ ...prof, name: e.target.value })} aria-label="profile name" placeholder="profile name" />
                <Select className="in-grow" value={prof.companion} onChange={e => setProf({ ...prof, companion: e.target.value })} aria-label="companion">
                  <option value="">companion…</option>
                  {comps.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </Select>
                {external ? <Input className="in-grow" value={prof.base_url} onChange={e => setProf({ ...prof, base_url: e.target.value })} placeholder="http://127.0.0.1:1234" aria-label="engine address" /> : null}
              </div>
              <div className="in-row">
                <Button variant="ghost" onClick={() => open('character')}>Make a new companion first (Character)</Button>
                <Button disabled={!prof.name || (!external && !st.finished) || !!d.approval || conv.needed || conv.running} onClick={write}>Write the profile</Button>
              </div>
              {made ? <div className="in-hint">Written: profiles/{made.profile}.toml. Start her with <code>{made.start}</code> (or the launcher, <code>kairos.bat</code>).</div> : null}
            </Step>

            {m ? <div className={'in-msg ' + (m.ok ? 'in-ok' : 'in-err')} role={m.ok ? 'status' : 'alert'}>{m.text}</div> : null}
            {!d.transcoder ? <div className="in-hint">Her native engine (.sp models) needs the Kairos engine release, which includes the converter. llama.cpp needs no conversion.</div> : null}
          </div>
        )
      }}
    </Body>
  )
}
