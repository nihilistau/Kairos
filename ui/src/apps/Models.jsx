import { useState } from 'react'
import { usePoll, Body } from './panel.jsx'
import * as api from '../api.js'
import { open } from '../windowManager.js'
import { Chip, Button, Select } from '../kit/parts.jsx'
import * as ears from '../room/ears.js'
import * as speech from '../room/speech.js'
import { readyCount } from '../room/ModelStrip.jsx'

/* MODELS — every model job she runs, one row each (2026-10-29, the approved mockup A).
 *
 * Row: what the job is · the model behind it (a picker where the job can switch live) ·
 * whether it is loaded · Test. Everything comes from GET /v1/models/status, which asks each
 * job's OWNER (harness/server/models_status.py) — so this window cannot disagree with Voice,
 * Librarians, Senses or Launch. Pickers write the same knobs those windows write, through
 * /v1/tuning (override-only: an untouched picker leaves the profile in charge).
 *
 * Her mind and the memory index are read-only: both change only at a restart, and a picker
 * that "worked" until the next bounce would be a lie. The mind row sends him to Launch. */

/* state -> the kit chip that says it. Loading pulses (busy); the rest hold still. */
export const STATE_TONE = { loaded: 'ok', loading: 'accent', off: 'neutral', missing: 'warn', error: 'warn' }

const LABELS = {
  xai: 'Grok · cloud', lfm3: 'LFM3-Audio · local', voxtral: 'Voxtral · local',
  engine: 'her own vision', aux_vl: 'VL model on the aux door', openai: 'image_url via the seam',
}

function StatePill({ j }) {
  const tone = j.degraded ? 'warn' : (STATE_TONE[j.state] || 'warn')
  const word = j.state === 'loading' && typeof j.progress === 'number'
    ? 'loading ' + Math.round(j.progress * 100) + '%' : j.state
  return <Chip tone={tone} dot busy={j.state === 'loading'} title={j.why || j.state}>{word}</Chip>
}

function Picker({ j, busy, onPick }) {
  if (!j.switchable) return <div className="mdl-name">{j.model || '—'}</div>
  return (
    <Select className="mdl-sel" value={j.value || ''}
            disabled={busy} aria-label={j.title + ' model'}
            onChange={e => onPick(j.knob, e.target.value)}>
      {j.choices.map(c => <option key={c} value={c}>{LABELS[c] || c}</option>)}
    </Select>
  )
}

/* HER EARS, TWO WAYS (2026-10-29): how the room's mic listens (ears.mode — push to talk, or
 * always while Chat is open), and a Test that records three seconds of HIM and shows what
 * she heard, beside the bundled-clip Test that proves the door without a mic. */
function EarsMode({ j, busy, onPick }) {
  return (
    <Select className="mdl-sel" value={j.mode || 'push'} disabled={busy === 'ears.mode'}
            aria-label="how her ears listen" onChange={e => onPick('ears.mode', e.target.value)}>
      <option value="push">push to talk</option>
      <option value="always">always listening (while Chat is open)</option>
    </Select>
  )
}

function Slot({ j, busy, onPick, onTest, tested, here, onRecord }) {
  return (
    <div className="mdl-slot" data-job={j.id}>
      <div className="mdl-lbl">{j.title}</div>
      <div className="mdl-mid">
        <Picker j={j} busy={busy === j.knob} onPick={onPick} />
        {j.switchable && j.model && j.model !== j.value ? <div className="mdl-name">{j.model}</div> : null}
        {j.id === 'ears' ? <EarsMode j={j} busy={busy} onPick={onPick} /> : null}
        <div className="mdl-meta">
          {j.detail}
          {j.id === 'mind' ? <>{' · '}<button type="button" className="mdl-link"
                                              onClick={() => open('launch')}>change in Launch</button></> : null}
        </div>
        {j.why && (j.state !== 'loaded' || j.degraded) ? <div className="mdl-why">{j.why}</div> : null}
        {j.state === 'loading'
          ? <div className="mdl-bar">{typeof j.progress === 'number'
              ? <i style={{ width: Math.round(j.progress * 100) + '%' }} />
              : <i className="mdl-bar-ind" />}</div>
          : null}
        {tested ? <div className={'mdl-test' + (tested.ok ? '' : ' mdl-test-bad')}>
          {tested.running ? 'testing…' : (tested.ok ? '✓ ' : '✗ ') + tested.result
            + (tested.seconds != null && !tested.running ? ' · ' + tested.seconds + ' s' : '')}
        </div> : null}
      </div>
      <div className="mdl-end">
        <StatePill j={j} />
        <Button size="sm" variant="ghost" disabled={!!(tested && tested.running)}
                title={j.id === 'mind' || j.id === 'memory' || j.id === 'eyes'
                  ? 'reports status only' : 'one small real request'}
                onClick={() => onTest(j.id)}>▶ Test</Button>
        {j.id === 'ears' ? (
          <Button size="sm" variant="ghost" disabled={!here || !!(tested && tested.running)}
                  title={here ? 'record 3 s from your mic and show what she heard' : ears.NOT_HERE}
                  onClick={onRecord}>● Record</Button>
        ) : null}
      </div>
    </div>
  )
}

export function ModelsView({ d, busy, onPick, onTest, tests, note, here, onRecord }) {
  const jobs = d.jobs || []
  const ready = readyCount(jobs)
  return (
    <>
      <div className="mdl-head">
        <Chip tone={ready === jobs.length ? 'ok' : 'warn'} dot>{ready} of {jobs.length} ready</Chip>
        {note ? <span className="mdl-why">{note}</span> : null}
      </div>
      <div className="mdl-list">
        {jobs.map(j => <Slot key={j.id} j={j} busy={busy} onPick={onPick} onTest={onTest} tested={tests[j.id]}
                                    here={here} onRecord={onRecord} />)}
      </div>
    </>
  )
}

export default function Models() {
  const s = usePoll(api.modelsStatus, 4000)
  const [busy, setBusy] = useState('')
  const [note, setNote] = useState('')
  const [tests, setTests] = useState({})
  const onPick = async (knob, value) => {
    setBusy(knob)
    try {
      await api.tuningSet({ [knob]: value }); setNote(''); s.refresh()
      if (knob === 'ears.mode') ears.sync()   // an open Chat follows at once
    }
    catch (e) { setNote(String(e.message || e).slice(0, 160)) }
    finally { setBusy('') }
  }
  const onTest = async (job) => {
    setTests(t => ({ ...t, [job]: { running: true } }))
    try {
      const r = await api.modelsTest(job)
      // THE VOICE TEST IS HEARD (2026-10-29): the response carries the wav it tested; the click
      // is the user gesture autoplay wants. Through speech.js's ONE queue (final review): its
      // playNow plays a wav in hand without re-synthesising, behind whatever she is saying, and
      // the mic's gate sees it — a bare Audio here was heard by always-listening as his turn.
      // A playback failure is the taskbar's voice reason, like any sentence of hers.
      if (r && r.audio_b64) speech.playNow('data:audio/wav;base64,' + r.audio_b64)
      setTests(t => ({ ...t, [job]: { ok: r.ok, seconds: r.seconds, result: r.result } }))
    } catch (e) {
      setTests(t => ({ ...t, [job]: { ok: false, result: String(e.message || e).slice(0, 160) } }))
    }
    s.refresh()
  }
  /* THE RECORD TEST: three seconds of his voice, in memory, to /v1/listen (ears.js); the
     transcript is shown here and sent nowhere else. Opening the mic cuts her current reply,
     as in Chat (room/reply.js) — he is talking, wherever the mic was opened. */
  const onRecord = async () => {
    setTests(t => ({ ...t, ears: { running: true } }))
    if (!(await ears.start())) {
      setTests(t => ({ ...t, ears: { ok: false, result: ears.state().error } }))
      return
    }
    await new Promise(r => setTimeout(r, 3000))
    const t0 = Date.now()
    const said = await ears.stopAndSend()
    setTests(t => ({ ...t, ears: { ok: !!said, seconds: Math.round((Date.now() - t0) / 100) / 10,
                                   result: said ? 'heard: “' + said + '”' : ears.state().error } }))
  }
  return (
    <div className="pad">
      <Body state={s}>{d => <ModelsView d={d} busy={busy} onPick={onPick} onTest={onTest} tests={tests} note={note}
                                        here={ears.allowed()} onRecord={onRecord} />}</Body>
    </div>
  )
}
