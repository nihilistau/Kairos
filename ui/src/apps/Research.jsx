import { useState } from 'react'
import { usePoll, Body } from './panel.jsx'
import { LookRows, AskRow } from './looks.jsx'
import { Chip } from '../kit/parts.jsx'
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
  const [mode, setMode] = useState('research')
  return (
    <div className="pad">
      <Body state={s}>{d => {
        const rows = d.looks || []
        const inf = d.inflight
        const co = d.consult || {}
        return (
          <>
            <div className="rsc-bar">
              {d.armed
                ? <Chip tone="ok" dot>research tier on · {d.backend || 'xai'}</Chip>
                : <Chip>her research tier off — your box below still works</Chip>}
              {mode === 'consult'
                ? (co.available
                    ? <Chip tone="ok" dot>consult · {co.model || 'claude'}</Chip>
                    : <Chip tone="warn" title={co.why || ''}>consult unavailable{co.why ? ' — ' + co.why : ''}</Chip>)
                : null}
              {inf ? <Chip tone="accent" busy>looking up {inf.query || inf.kind}…</Chip> : null}
            </div>
            <div className="rsc-bar">
              <Chip tone={mode === 'research' ? 'accent' : 'neutral'} onClick={() => setMode('research')}>research</Chip>
              <Chip tone={mode === 'consult' ? 'accent' : 'neutral'} onClick={() => setMode('consult')}>consult</Chip>
            </div>
            {mode === 'consult'
              ? <AskRow key="consult"
                        placeholder="ask Claude a hard question yourself — billed, uncapped, logged"
                        busyLabel="consulting…"
                        run={q => api.consultRun(q)}
                        onDone={() => s.refresh()} />
              : <AskRow key="research"
                        placeholder="research something yourself — a real model call, billed, minutes not seconds"
                        busyLabel="researching…"
                        run={q => api.researchRun(q, 'normal')}
                        onDone={() => s.refresh()} />}
            <LookRows rows={rows}
                      empty="nothing researched yet — a title appears here when the tier actually returns, not when she talks about it" />
            <div className="rsc-foot">hers are her homework — you can read them, you cannot edit them</div>
          </>
        )
      }}</Body>
    </div>
  )
}
