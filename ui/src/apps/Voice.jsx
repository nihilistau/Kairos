import { KnobGroups } from './knobs.jsx'
import { usePoll } from './panel.jsx'
import * as api from '../api.js'

/* VOICE — a dedicated panel for her voice (2026-08-21, his ask: "add a dedicated
 * voice panel ... but still keep them in settings").
 *
 * The same knobs Settings shows under Voice, through the same shared renderer —
 * one truth, two windows — plus the LIVE status of the speech chain. The chips
 * read /v1/speak/status `live`, which is the same live_voice() resolution
 * synthesize() consults: what the chips say and what would speak next cannot
 * disagree. All the knobs are LIVE — on/off and provider apply to the next
 * sentence she speaks, no bounce.
 *
 * Prefix `vc-`, per G-ROOM-CSS; the knob rows borrow the shared st- furniture.
 */
export default function Voice() {
  const s = usePoll(api.speakStatus, 15000)
  const st = s.data || {}
  const lv = st.live || {}
  return (
    <div className="vc">
      <div className="vc-bar">
        <span className={'vc-chip ' + (lv.enabled === false ? 'vc-off' : 'vc-on')}>
          {lv.enabled === false ? 'voice off' : 'voice on'}
        </span>
        {lv.method ? <span className="vc-chip" title="provider">{lv.method}</span> : null}
        {lv.speaking_as ? (
          <span className="vc-chip" title="who would speak the next sentence">
            {String(lv.speaking_as).replace(/^xai:/, '')}
          </span>
        ) : null}
        {lv.method === 'local' && st.available === false ? (
          <span className="vc-chip vc-off">local chain dark</span>
        ) : null}
        {typeof st.cached === 'number' ? (
          <span className="vc-chip" title="synthesized sentences on disk">{st.cached} cached</span>
        ) : null}
      </div>
      <KnobGroups only={['Voice']} extras={{ Voice: 'voice-test' }} />
      <div className="vc-foot muted">
        on/off and provider are live — the next sentence she speaks honors them
      </div>
    </div>
  )
}
