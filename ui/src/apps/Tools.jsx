import { useState } from 'react'
import { usePoll, Body } from './panel.jsx'
import * as api from '../api.js'

/* TOOLS — the answer to "i dont even know what they are offering", rendered.
 *
 * Grouped by family, coloured by RISK, with the arming knob shown where there is
 * one. Reflects LIVE state, so a knob that is off shows its tools absent rather
 * than listing capabilities she does not currently have.
 *
 * The risk filter exists because the useful question is almost never "what tools
 * are there" — it is "what can she do to my machine", and that was previously
 * unanswerable at any speed. */
const RISK_TONE = {
  read: 'r-read', write: 'r-write', world: 'r-world',
  machine: 'r-machine', private: 'r-private',
}

export default function Tools() {
  const s = usePoll(api.tools, 30000)
  const [filter, setFilter] = useState('')

  return (
    <div className="pad">
      <Body state={s}>{d => {
        const groups = {}
        for (const t of d.tools) {
          if (filter && t.risk !== filter) continue
          if (!groups[t.group]) groups[t.group] = []
          groups[t.group].push(t)
        }
        return (
          <>
            <div className="chips">
              <button className={filter ? '' : 'on'} onClick={() => setFilter('')}>
                all {d.counts.total}
              </button>
              {Object.entries(d.by_risk).map(([r, n]) => (
                <button key={r}
                        className={(filter === r ? 'on ' : '') + RISK_TONE[r]}
                        onClick={() => setFilter(filter === r ? '' : r)}>
                  {r} {n}
                </button>
              ))}
            </div>

            {Object.entries(groups).map(([g, list]) => (
              <div key={g} className="grp">
                <h4>{g} <span className="muted">— {d.groups[g]}</span></h4>
                {list.map(t => (
                  <div key={t.name} className="tool">
                    <span className={'dot ' + RISK_TONE[t.risk]} title={t.risk} />
                    <code>{t.name}</code>
                    <span className="tier">{t.tier}</span>
                    {t.arms ? <span className="arms">{t.arms}</span> : null}
                    <div className="desc">{t.note || t.description}</div>
                  </div>
                ))}
              </div>
            ))}
          </>
        )
      }}</Body>
    </div>
  )
}
