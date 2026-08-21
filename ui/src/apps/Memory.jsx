import { usePoll, Body } from './panel.jsx'
import * as api from '../api.js'

/* MEMORY — live rows and retired ones, and showing both is the point.
 *
 * NOTHING HERE IS EVER DELETED. forget() tombstones; supersede retires and keeps
 * the old row for provenance. Rendering retired rows as a visible category rather
 * than filtering them away is what makes that promise legible instead of merely
 * true — and it is also the check on a real failure mode: an earlier console said
 * "153 live" when 73 of those were retired. */
export default function Memory() {
  const s = usePoll(api.memory, 30000)
  return (
    <div className="pad">
      <Body state={s}>{d => {
        // THE SHAPE, CHECKED RATHER THAN GUESSED. /v1/memory returns `facts`, and
        // liveness is the integer `lifecycle` — falsy is live, truthy is retired,
        // exactly as harness/skills/memory.py:254 reads it. The first cut looked for
        // `rows`/`memories` and `retired_at`, none of which exist, so the panel
        // rendered empty against a store holding 180 facts. Guessing a payload is
        // the same class of mistake as guessing an API.
        const rows = d.facts || []
        const live = rows.filter(r => !r.lifecycle)
        const gone = rows.filter(r => r.lifecycle)
        return (
          <>
            <div className="chips">
              <button className="on">{live.length} live</button>
              <button className="r-off">{gone.length} retired</button>
            </div>
            {live.slice(0, 150).map((r, i) => (
              <div key={r.name || i} className="mem">
                <div className="t">{r.text}</div>
                <div className="meta">
                  <span className={'cls c-' + (r.mem_class || 'fact')}>{r.mem_class}</span>
                  <span className={'who w-' + (r.speaker || 'user')}>
                    {r.speaker === 'self' ? 'hers' : 'his'}</span>
                  {r.ts ? <span>{String(r.ts).slice(0, 10)}</span> : null}
                  {r.recalled ? <span title="times recalled">↺{r.recalled}</span> : null}
                  {r.salience != null ? (
                    <span className="sal" title={'salience ' + r.salience}>
                      <i style={{ width: Math.min(100, r.salience * 14) + '%' }} /></span>
                  ) : null}
                </div>
              </div>
            ))}
            {gone.length ? <h4 className="muted">retired — kept, never deleted</h4> : null}
            {gone.slice(0, 60).map((r, i) => (
              <div key={'g' + i} className="mem gone">{r.text}</div>
            ))}
          </>
        )
      }}</Body>
    </div>
  )
}
