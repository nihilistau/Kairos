import { useState, useEffect } from 'react'
import { usePoll, Body as PanelBody } from './panel.jsx'
import * as api from '../api.js'

/* BODY — his heart, his movement, and what she is reading off them (2026-08-26).
 *
 * TWO HALVES, and the top one is the point. The live strip shows the LAST FEW READINGS,
 * not an average: "72, 81, 94 — climbing" is a thing you can feel; "average 82 bpm" is a
 * number on a form. His words for why this exists: "she can see my heart pacing... a
 * bridge to the real world, to me."
 *
 * AND IT SHOWS HER SENTENCE, verbatim, at the top. That is deliberate and it is the most
 * useful widget on the panel: it is the ONLY place you can see exactly what she was handed
 * about your body. If it ever says something you would not say about yourself, you can see
 * it here before she says it to you — /v1/telemetry/now serves the room and her prefix from
 * the same seam, so there is no second version to go looking for. */

const KIND_LABEL = {
  heart_rate: 'heart', gyro_rms: 'movement', accel_rms: 'motion', steps: 'steps',
  spo2: 'SpO2', skin_temp: 'skin', battery: 'battery', sleep_stage: 'sleep',
  on_body: 'on wrist', motion: 'state', hr_variability: 'HRV',
}

/* A sparkline over the minute-buckets. SVG and no library: one polyline is the whole
   requirement, and a charting dependency for this would outweigh the feature. */
function Spark({ points, w = 260, h = 44 }) {
  const vals = points.map(p => p.avg).filter(v => typeof v === 'number')
  if (vals.length < 2) return <div className="tel-spark-empty">not enough yet</div>
  const lo = Math.min(...vals), hi = Math.max(...vals), span = (hi - lo) || 1
  const step = w / (vals.length - 1)
  const d = vals.map((v, i) => `${(i * step).toFixed(1)},${(h - ((v - lo) / span) * h).toFixed(1)}`).join(' ')
  return (
    <svg className="tel-spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <polyline points={d} />
      <text x="1" y="9" className="tel-spark-hi">{hi.toFixed(0)}</text>
      <text x="1" y={h - 2} className="tel-spark-lo">{lo.toFixed(0)}</text>
    </svg>
  )
}

/* THE LIVE TAIL. Each reading as its own pill so a rise reads as a rise. */
function Tail({ vals, trend, unit }) {
  if (!vals || vals.length < 2) return null
  const arrow = trend === 'climbing' ? '↑' : trend === 'falling' ? '↓' : '·'
  return (
    <div className={'tel-tail t-' + (trend || 'steady')}>
      {vals.map((v, i) => (
        <span key={i} className={'tel-beat' + (i === vals.length - 1 ? ' now' : '')}>
          {typeof v === 'number' ? (Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(2)) : String(v)}
        </span>
      ))}
      <span className="tel-trend">{arrow} {trend}{unit ? ' ' + unit : ''}</span>
    </div>
  )
}

export default function Body() {
  // 5s: fast enough that a climbing heart is visibly climbing, slow enough that the panel
  // is not a load generator. The store is a file read; this is not free.
  const s = usePoll(api.telemetryNow, 5000)
  const [hours, setHours] = useState(6)
  const [hist, setHist] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    let live = true
    api.telemetryHistory(hours)
      .then(h => { if (live) setHist(h) })
      .catch(e => { if (live) setErr(String(e).slice(0, 90)) })
    return () => { live = false }
  }, [hours])

  return (
    <div className="pad">
      <PanelBody state={s}>{d => {
        if (d.ok === false) return <p className="err">{d.error}</p>
        const o = d.observed || {}, f = d.facts || {}
        const hasBody = Object.keys(o).length > 0
        return (
          <>
            {/* WHAT SHE IS READING. Empty is a real answer and says so. */}
            <div className="tel-hers">
              <span className="tel-hers-k">she reads</span>
              {d.she_reads
                ? <span className="tel-hers-v">{d.she_reads}</span>
                : <span className="tel-hers-v muted">
                    nothing — {d.why || 'no fresh readings, so she is told nothing'}
                  </span>}
            </div>

            {!hasBody ? (
              <p className="muted">
                No readings yet. The watch agent posts to <code>/v1/telemetry/ingest</code>.
              </p>
            ) : (
              <>
                <div className="tel-live">
                  <div className="tel-card">
                    <div className="tel-k">heart{d.resting ? ` · resting ${d.resting}` : ''}</div>
                    <div className="tel-big">
                      {o.heart_rate != null ? Math.round(o.heart_rate) : '—'}
                      <em>bpm</em>
                    </div>
                    <Tail vals={o.heart_rate_tail} trend={f.hr_trend} />
                    {f.hr_swing ? <div className="tel-sub">swing {f.hr_swing} bpm</div> : null}
                  </div>

                  <div className="tel-card">
                    <div className="tel-k">movement</div>
                    <div className="tel-big">
                      {f.movement != null ? f.movement : '—'}
                      <em>rad/s</em>
                    </div>
                    <Tail vals={o.movement_tail} trend={null} />
                    {f.movement_word ? <div className="tel-sub">{f.movement_word}</div> : null}
                  </div>

                  <div className="tel-card">
                    <div className="tel-k">state</div>
                    <div className="tel-states">
                      {o.on_body ? <span className={'tel-pill p-' + o.on_body}>
                        {o.on_body === 'on' ? 'on wrist' : 'off wrist'}</span> : null}
                      {f.asleep === true ? <span className="tel-pill p-sleep">
                        asleep{f.crude ? '?' : ''}</span> : null}
                      {o.sleep_stage ? <span className="tel-pill">{o.sleep_stage}</span> : null}
                      {o.motion ? <span className="tel-pill">{o.motion}</span> : null}
                    </div>
                    {/* INFERRED IS SAID OUT LOUD, here as everywhere else. */}
                    {f.crude ? <div className="tel-sub">
                      sleep inferred from stillness — the watch did not say
                    </div> : null}
                  </div>
                </div>
                {d.why ? <div className="tel-why">{d.why}</div> : null}
              </>
            )}

            <div className="tel-hist-head">
              <span>history</span>
              {[1, 6, 24, 168].map(h => (
                <button key={h} className={hours === h ? 'on' : ''} onClick={() => setHours(h)}>
                  {h < 24 ? h + 'h' : (h / 24) + 'd'}
                </button>
              ))}
              {d.health ? <span className="muted">
                {d.health.samples} samples · {d.health.days} day(s)
                {d.health.malformed ? ` · ${d.health.malformed} malformed` : ''}
              </span> : null}
            </div>
            {err ? <p className="err">{err}</p> : null}
            {hist && hist.ok ? (
              hist.kinds.length === 0
                ? <p className="muted">nothing recorded in this window.</p>
                : hist.kinds.map(k => (
                    <div key={k} className="tel-series">
                      <div className="tel-series-k">{KIND_LABEL[k] || k}</div>
                      <Spark points={hist.series[k]} />
                      <div className="tel-series-n">{hist.series[k].length} min</div>
                    </div>
                  ))
            ) : <p className="muted">reading history…</p>}
          </>
        )
      }}</PanelBody>
    </div>
  )
}
