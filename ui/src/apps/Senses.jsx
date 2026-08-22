import { usePoll, Body, Row } from './panel.jsx'
import * as api from '../api.js'
import { KnobGroups } from './knobs.jsx'

/* SENSES — what she can actually receive, ruled from the committed capability
 * table. The "why not" line is the point of the panel: an absent sense must say
 * WHY, or the operator is left guessing whether it is broken or simply not there.
 * On this checkpoint hearing is absent because the model has no audio embedder at
 * all, which is a fact about the weights and not a configuration mistake. */
export default function Senses() {
  const s = usePoll(api.senses, 15000)
  const v = usePoll(api.speakStatus, 15000)
  return (
    <div className="pad">
      <Body state={s}>{d => (
        <>
          <h3>{d.capability.model}</h3>
          <Row k="hidden size" v={d.capability.hidden_size} />
          <Row k="sight" v={d.capability.sight ? 'yes' : 'no'} tone={d.capability.sight ? 'ok' : 'off'} />
          {/* WHICH EYES (2026-08-22, E): engine / an LFM VL model on the aux door / the seam —
              a picker; every look goes through the same door and the same scrub */}
          <Row k="eyes" v={!d.eyes ? '—'
                : d.eyes.backend === 'aux_vl' ? ('aux VL · ' + (d.eyes.vl_model || 'no model') + (d.eyes.door_up ? '' : ' · door dark'))
                : d.eyes.backend === 'openai' ? 'the seam (image_url)'
                : 'engine'}
               tone={d.eyes && (d.eyes.backend !== 'aux_vl' || (d.eyes.vl_model && d.eyes.door_up)) ? 'ok' : 'off'} />
          <Row k="hearing" v={d.capability.hearing ? 'yes' : 'no'} tone={d.capability.hearing ? 'ok' : 'off'} />
          {!d.capability.hearing && <p className="why">{d.capability.why_no_hearing}</p>}

          <h4>the hourly look</h4>
          <Row k="enabled" v={String(d.ambient && d.ambient.enabled)} tone={d.ambient && d.ambient.enabled ? 'ok' : 'off'} />
          <Row k="every" v={Math.round(((d.ambient && d.ambient.interval_s) || 0) / 60) + ' min'} />
          <Row k="next in" v={d.ambient && d.ambient.next_in_s != null ? d.ambient.next_in_s + 's' : '—'} />

          <details className="sns-eyes">
            <summary>eyes settings</summary>
            <KnobGroups only={['Sight — her eyes']} />
          </details>

          <h4>capture</h4>
          <Row k="backends" v={Object.entries((d.capture && d.capture.backends) || {})
            .filter(x => x[1]).map(x => x[0]).join(', ') || 'none'} />
        </>
      )}</Body>

      <Body state={v}>{d => (
        <>
          <h4>her voice</h4>
          <Row k="backend" v={d.backend + (d.live && d.live.method === 'local' && d.live.local_gguf ? ' · ' + d.live.local_gguf : '')} tone={d.warm ? 'ok' : ''} />
          <Row k="warm" v={String(d.warm)} tone={d.warm ? 'ok' : 'off'} />
          <Row k="cached lines" v={d.cached} />
        </>
      )}</Body>
    </div>
  )
}
