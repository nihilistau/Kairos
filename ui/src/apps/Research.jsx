import { usePoll, Body } from './panel.jsx'
import { LookRows, AskRow } from './looks.jsx'
import * as api from '../api.js'

/* RESEARCH — the paid-tier half of the looking ledger.
 *
 * The ledger: what actually ran and returned, never her opinions about it.
 * Since 2026-08-21 the window also has HIS lane — a manual box that runs the
 * same backend her research tool uses (not gated on SP_RESEARCH: that knob
 * governs whether SHE may reach for the paid tier unprompted; his click is its
 * own authorization). Rows carry his/hers chips; plain web searches moved to
 * the search window. He reads hers; he does not edit the homework.
 *
 * Prefix `rsc-`, per G-ROOM-CSS.
 */
export default function Research() {
  const s = usePoll(api.research, 8000)
  return (
    <div className="pad">
      <Body state={s}>{d => {
        const rows = d.looks || []
        const inf = d.inflight
        return (
          <>
            <div className="rsc-bar">
              {d.armed
                ? <span className="rsc-arm">research tier on · {d.backend || 'xai'}</span>
                : <span className="rsc-arm rsc-off">her research tier off — your box below still works</span>}
              {inf ? <span className="rsc-now">looking up {inf.query || inf.kind}…</span> : null}
            </div>
            <AskRow placeholder="research something yourself — a real model call, billed, minutes not seconds"
                    busyLabel="researching…"
                    run={q => api.researchRun(q, 'normal')}
                    onDone={() => s.refresh()} />
            <LookRows rows={rows}
                      empty="nothing researched yet — a title appears here when the tier actually returns, not when she talks about it" />
            <div className="rsc-foot muted">
              hers are her homework — you can read them, you cannot edit them
            </div>
          </>
        )
      }}</Body>
    </div>
  )
}
