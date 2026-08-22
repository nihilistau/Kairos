import { usePoll, Body } from './panel.jsx'
import * as api from '../api.js'
import { KnobGroups } from './knobs.jsx'

/* THE LIBRARIANS — the aux (LFM2.5) CPU helpers (2026-08-22, sub-project D).
 *
 * They embed, retrieve, judge, compress and parse; they never speak as her. This window
 * is the honest state of the two doors, the index, the model pickers (choices are what
 * the door lists right now), the soft-prompt knobs, and a rebuild button.
 * (Librarians.jsx, not Aux.jsx — `aux` is a Windows reserved device name; git cannot
 * open a file called that.) */
export default function Librarians() {
  const s = usePoll(api.aux, 15000)
  return (
    <div className="pad">
      <Body state={s}>{d => {
        const line = !d.armed
          ? <span className="muted">off — SP_AUX is off in the profile; every caller keeps its pre-aux behaviour</span>
          : <span className={d.embed_up && d.chat_up ? 'good' : 'warn'}>
              armed · embed {d.embed_up ? '✓' : 'dark'} · chat {d.chat_up ? '✓' : 'dark'}
              {' · '}{d.chunks} chunks in {d.files} files
              {d.last_refresh_s_ago != null ? ' · refreshed ' + Math.round(d.last_refresh_s_ago / 60) + 'm ago' : ''}
              {d.warming ? ' · warming…' : ''}
            </span>
        return (
          <>
            <div className="lib-state">{line}</div>
            <div className="lib-row">
              <span className="muted">judge / extract model: </span>{d.chat_model || '—'}
              {' '}<button onClick={() => api.auxRebuild().then(s.refresh)}>rebuild index</button>
            </div>
            <div className="lib-row muted" title={d.index_key}>
              query soft-prompt: “{(d.query_prefix || '').slice(0, 80)}{(d.query_prefix || '').length > 80 ? '…' : ''}”
              {d.doc_prefix ? ' · doc prefix: “' + d.doc_prefix + '”' : ''}
            </div>
            <KnobGroups only={['Aux — the quiet librarians']} />
            {(d.models || []).length ? (
              <div className="lib-row muted">the door lists: {(d.models || []).join(' · ')}</div>
            ) : null}
          </>
        )
      }}</Body>
    </div>
  )
}
