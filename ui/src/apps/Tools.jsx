import { useState } from 'react'
import { usePoll, Body } from './panel.jsx'
import * as api from '../api.js'
import { Chip, Tabs } from '../kit/parts.jsx'

/* TOOLS — the answer to "i dont even know what they are offering", rendered.
 *
 * Grouped by family, coloured by RISK, with the arming knob shown where there is
 * one. Reflects LIVE state, so a knob that is off shows its tools absent rather
 * than listing capabilities she does not currently have.
 *
 * The risk filter exists because the useful question is almost never "what tools
 * are there" — it is "what can she do to my machine", and that was previously
 * unanswerable at any speed.
 *
 * The filter is the kit's Tabs. The old chip row toggled back to "all" on a second
 * click of the same risk; tabs SELECT, they do not toggle — "all" is the way back.
 * A tab list is the pattern a keyboard user expects: arrow keys, Home and End move
 * the selection, and the list filters as it moves. Six risks outrun a phone-width
 * window, so the strip scrolls sideways rather than wrapping a label — the kit's Tabs
 * do that for every caller now (final review, Q3; this was Tools' own .tl-tabs). */
const RISK_TONE = {
  read: 'r-read', write: 'r-write', world: 'r-world',
  machine: 'r-machine', private: 'r-private',
}

export function ToolsView({ d, filter, setFilter }) {
  const groups = {}
  for (const t of d.tools) {
    if (filter && t.risk !== filter) continue
    if (!groups[t.group]) groups[t.group] = []
    groups[t.group].push(t)
  }
  return (
    <>
      <Tabs value={filter || 'all'} label="filter by risk"
            onChange={id => setFilter(id === 'all' ? '' : id)}
            tabs={[{ id: 'all', label: 'all ' + d.counts.total },
                   ...Object.entries(d.by_risk).map(([r, n]) => ({ id: r, label: r + ' ' + n }))]} />

      {Object.entries(groups).map(([g, list]) => (
        <div key={g} className="grp">
          <h4>{g} <span className="muted">— {d.groups[g]}</span></h4>
          {list.map(t => (
            <div key={t.name} className="tool">
              <span className={'dot ' + RISK_TONE[t.risk]} title={t.risk} />
              <code>{t.name}</code>
              <Chip>{t.tier}</Chip>
              {t.arms ? <Chip tone="warm" title="the knob that arms it">{t.arms}</Chip> : null}
              <div className="desc">{t.note || t.description}</div>
            </div>
          ))}
        </div>
      ))}
    </>
  )
}

export default function Tools() {
  const s = usePoll(api.tools, 30000)
  const [filter, setFilter] = useState('')

  return (
    <div className="pad">
      <Body state={s}>{d => <ToolsView d={d} filter={filter} setFilter={setFilter} />}</Body>
    </div>
  )
}
