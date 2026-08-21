import { usePoll, Body } from './panel.jsx'
import { LookRows, AskRow } from './looks.jsx'
import { KnobGroups } from './knobs.jsx'
import * as api from '../api.js'

/* SEARCH — the web_search half of the looking ledger, as its own window
 * (2026-08-21, his ask: "a dedicated ... search panel ... similar to the
 * Research panel but include the settings, provider etc and make both have a
 * place that I can use them to search and research manually").
 *
 * Same format as research — title rows that expand — with a manual box (HIS
 * lane: rows land by="him"), the provider knob inline (still in Settings too;
 * same renderer, one truth), and chips for status. Her rows and his share the
 * ledger; the chips keep whose-is-whose visible.
 *
 * Prefix `sr-`; rows and box borrow the rsc- furniture from the research window.
 */
export default function Search() {
  const s = usePoll(api.search, 8000)
  return (
    <div className="pad">
      <Body state={s}>{d => {
        const rows = d.looks || []
        // search_engines is {name: available} — the seam's status() shape
        const up = Object.entries(d.search_engines || {})
          .filter(([, ok]) => ok).map(([n]) => n)
        return (
          <>
            <div className="rsc-bar">
              <span className="rsc-arm">engine · {d.search_backend || 'ddg'}</span>
              {up.length ? (
                <span className="sr-eng" title="engines with a key or no key needed">
                  ready: {up.join(', ')}
                </span>
              ) : null}
              {d.inflight ? <span className="rsc-now">she is looking up {d.inflight.query}…</span> : null}
            </div>
            <AskRow placeholder="search the web yourself — lands in the shared ledger as yours"
                    busyLabel="searching…"
                    run={q => api.searchRun(q, 6)}
                    onDone={() => s.refresh()} />
            <LookRows rows={rows}
                      empty="no searches yet — hers appear when web_search returns, yours when you use the box above" />
            <details className="sr-knobs">
              <summary>engine settings</summary>
              <KnobGroups only={['Web search']} />
            </details>
          </>
        )
      }}</Body>
    </div>
  )
}
