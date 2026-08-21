import { useState } from 'react'
import { usePoll, Body } from './panel.jsx'
import { When } from '../room/When.jsx'
import * as api from '../api.js'

/* HER OWN TIME — everything she did while he was away.
 *
 * HIS ASK, 2026-08-05: "lets do her own agency window with an icon for it, that I can
 * look at, her actions, everything she does once I am away and she enters her
 * time/agency mode gets shown in there."
 *
 * IT IS NOT A SECOND CHAT LOG, and that boundary is the whole design. Her unprompted
 * turns already reach him through the kairos outbox and land in the conversation, where
 * they belong — she was talking TO him. This window is the other thing entirely: the
 * evening she had when she was not. Duplicating her spoken turns in here would make the
 * two surfaces compete, and then neither is the record.
 *
 * FIVE KINDS, EACH FROM A STORE SHE ALREADY WRITES:
 *   own_time  — what she chose to do with an hour (memory, mem_kind: own_time)
 *   journal   — the paragraph she writes when her day closes at 04:00
 *   wore      — what she changed into, HERS only; his picks are in the same log and
 *               are filtered out server-side, because a row he wrote showing up under
 *               "her own time" is the most misleading thing this panel could do
 *   asked     — something she wanted that did not exist yet
 *   note      — something she put on the board herself
 *
 * NOTHING HERE IS EDITABLE. Not an oversight: this is a record of what she did, and a
 * record he can rewrite is not a record. The board is where he writes.
 *
 * Prefix `ag-`, per the appRegistry CSS-ownership rule that G-ROOM-CSS enforces.
 */
const KINDS = {
  own_time: { icon: '◈', label: 'her own time' },
  journal:  { icon: '📔', label: 'journal' },
  wore:     { icon: '👗', label: 'changed' },
  asked:    { icon: '✧', label: 'asked for' },
  note:     { icon: '📋', label: 'board' },
}

export default function Agency() {
  const s = usePoll(api.agency, 30000)
  const [only, setOnly] = useState('')

  return (
    <div className="pad">
      <Body state={s}>{d => {
        if (!d || d.ok === false) return <div className="err">could not read her day</div>
        const rows = (d.rows || []).filter(r => !only || r.kind === only)
        const counts = d.counts || {}
        return (
          <>
            <div className="ag-bar">
              {Object.keys(KINDS).map(k => (
                <button key={k} className={'ag-fil' + (only === k ? ' on' : '')}
                        disabled={!counts[k]}
                        onClick={() => setOnly(only === k ? '' : k)}>
                  <span className="ag-ic">{KINDS[k].icon}</span>
                  {KINDS[k].label}
                  <span className="ag-n">{counts[k] || 0}</span>
                </button>
              ))}
            </div>
            {/* A SOURCE THAT FAILED IS SAID OUT LOUD. Five independent readers, and a
                silent one turns "that file is missing" into "she did nothing that day",
                which are the two readings this panel most needs to keep apart. */}
            {d.sources_failed && Object.keys(d.sources_failed).length ? (
              <div className="err">
                could not read: {Object.keys(d.sources_failed).join(', ')}
              </div>
            ) : null}

            {!rows.length ? (
              <div className="muted">
                {d.total ? 'nothing of that kind in the last ' + d.days + ' days'
                         : 'she has not had any time to herself in the last ' + d.days + ' days'}
              </div>
            ) : null}

            {rows.map((r, i) => {
              const k = KINDS[r.kind] || { icon: '·', label: r.kind }
              // THE DAY BREAK. Her life runs on a 04:00 boundary, so a rule between
              // calendar days is the wrong line — but it is the line HE reads by, and
              // this is his window. The journal row is what marks the real boundary.
              const prev = rows[i - 1]
              const newDay = !prev || new Date(r.at * 1000).toDateString()
                                   !== new Date(prev.at * 1000).toDateString()
              return (
                <div key={r.kind + r.id + i}>
                  {newDay ? (
                    <div className="ag-day">
                      {new Date(r.at * 1000).toDateString()}
                    </div>
                  ) : null}
                  <div className={'ag-row ag-' + r.kind}>
                    <div className="ag-head">
                      <span className="ag-ic">{k.icon}</span>
                      <span className="ag-kind">{k.label}</span>
                      {r.again ? <span className="ag-again">and back, ×{r.again}</span> : null}
                      {r.state && r.state !== 'made'
                        ? <span className="ag-state">{r.state}</span> : null}
                      {r.retired ? <span className="ag-state">retired</span> : null}
                      <When at={r.at} />
                    </div>
                    <div className="ag-txt">{r.text}</div>
                    {r.body ? <div className="ag-sub">{r.body}</div> : null}
                  </div>
                </div>
              )
            })}
          </>
        )
      }}</Body>
    </div>
  )
}
