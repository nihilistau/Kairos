import { useState } from 'react'
import { usePoll, Body } from './panel.jsx'
import { When } from '../room/When.jsx'
import { Chip, State, Tabs } from '../kit/parts.jsx'
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
 *
 * A KIND IS A DOT IN ITS OWN COLOUR (redesign stage 4). It was a text glyph — three of the
 * five were emoji, which the icon rule retires, and the other two drew in whatever font the
 * machine had. The kind's colour already IS its legend (the rule down each row), so the dot
 * repeats that one legend rather than adding a second.
 */
const KINDS = {
  own_time: { label: 'her own time' },
  journal:  { label: 'journal' },
  wore:     { label: 'changed' },
  asked:    { label: 'asked for' },
  note:     { label: 'board' },
}
const Dot = ({ k }) => <span className={'ag-dot ag-k-' + k} aria-hidden="true" />

/* The window's body, split out so G-ROOM-KIT leg 11 can render it with a fixture. The
 * filter is the kit's Tabs: tabs SELECT, they do not toggle — "all" is the way back (the
 * old chip toggled off on a second click). A kind with no rows has no tab: it was a
 * disabled chip, Tabs has no disabled tab, and an arrow key landing on one would filter
 * the window to nothing. So a chosen kind whose tab has gone (its count fell to 0 on a
 * later poll) falls back to "all", for the rows AND the selected tab, as Story's `shown`:
 * Tabs selects its first tab for a value that names none, so filtering by the stale kind
 * showed "all" selected over an empty list. */
export function AgencyView({ d, only, setOnly }) {
  if (!d || d.ok === false) return <State kind="error">could not read her day</State>
  const counts = d.counts || {}
  const kinds = Object.keys(KINDS).filter(k => counts[k])
  const sel = kinds.includes(only) ? only : ''
  const rows = (d.rows || []).filter(r => !sel || r.kind === sel)
  const all = kinds.reduce((n, k) => n + counts[k], 0)
  return (
    <>
      <div className="ag-tabs">
        <Tabs value={sel || 'all'} label="filter by kind"
              onChange={id => setOnly(id === 'all' ? '' : id)}
              tabs={[{ id: 'all', label: 'all ' + all },
                     ...kinds.map(k => ({ id: k, label: <><Dot k={k} />{KINDS[k].label + ' ' + counts[k]}</> }))]} />
      </div>
      {/* A SOURCE THAT FAILED IS SAID OUT LOUD. Five independent readers, and a
          silent one turns "that file is missing" into "she did nothing that day",
          which are the two readings this panel most needs to keep apart. */}
      {d.sources_failed && Object.keys(d.sources_failed).length ? (
        <div className="ag-failed">
          <Chip tone="err" wrap>{'could not read: ' + Object.keys(d.sources_failed).join(', ')}</Chip>
        </div>
      ) : null}
      {!rows.length ? (
        <State kind="empty">
          {d.total ? 'nothing of that kind in the last ' + d.days + ' days'
                   : 'she has not had any time to herself in the last ' + d.days + ' days'}
        </State>
      ) : null}
      {rows.map((r, i) => {
        const k = KINDS[r.kind] || { label: r.kind }
        // THE DAY BREAK. Her life runs on a 04:00 boundary, so a rule between
        // calendar days is the wrong line — but it is the line HE reads by, and
        // this is his window. The journal row is what marks the real boundary.
        const prev = rows[i - 1]
        const newDay = !prev || new Date(r.at * 1000).toDateString()
                             !== new Date(prev.at * 1000).toDateString()
        return (
          <div key={r.kind + r.id + i}>
            {newDay ? <div className="ag-day">{new Date(r.at * 1000).toDateString()}</div> : null}
            <div className={'ag-row ag-' + r.kind}>
              <div className="ag-head">
                <Dot k={r.kind} />
                <span className="ag-kind">{k.label}</span>
                {r.again ? <span className="ag-again">and back, ×{r.again}</span> : null}
                {r.state && r.state !== 'made' ? <Chip>{r.state}</Chip> : null}
                {r.retired ? <Chip>retired</Chip> : null}
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
}

export default function Agency() {
  const s = usePoll(api.agency, 30000)
  const [only, setOnly] = useState('')
  return (
    <div className="pad">
      <Body state={s}>{d => <AgencyView d={d} only={only} setOnly={setOnly} />}</Body>
    </div>
  )
}
