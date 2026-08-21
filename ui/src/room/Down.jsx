import { useState } from 'react'
import * as api from '../api.js'

/* SHE IS OFF — AND THAT MUST NOT LOOK LIKE A CRASH.
 *
 * When the stack stops, every poll in the room starts failing and the panels fill with
 * connection errors. That is indistinguishable from the night a bad regex blanked the
 * whole bundle, and "is it broken or did I turn it off" is not a question he should have
 * to answer by reading a log.
 *
 * So a deliberate stop paints a deliberate screen. `her` leaves the gateway up, which is
 * the only reason a start button can exist at all; `all` takes the room with it, so the
 * honest instruction is the terminal.
 */
export default function Down({ mode, onBack }) {
  const [starting, setStarting] = useState(false)
  const [err, setErr] = useState('')
  const start = async () => {
    setStarting(true); setErr('')
    try {
      const r = await api.startHer()
      if (r && r.ok === false) { setErr(r.error || 'could not start her'); setStarting(false) }
    } catch (e) { setErr(String(e.message || e)); setStarting(false) }
  }
  return (
    <div className="sd-down">
      <div className="sd-down-mark">⏻</div>
      <div className="sd-down-t">she is shut down</div>
      {mode === 'her' ? (
        <>
          <div className="sd-down-b">The room is still up. She can come back whenever you want her.</div>
          <button className="sd-opt" disabled={starting} onClick={start}>
            {starting ? 'starting her — about 90 seconds…' : 'start her'}
          </button>
          {starting ? <button className="sd-opt sd-cancel" onClick={onBack}>back to the room</button> : null}
        </>
      ) : (
        <div className="sd-down-b">
          Everything stopped, including this room. Start it again with
          <code> python serve.py &lt;profile&gt;</code> in a terminal.
        </div>
      )}
      {err ? <div className="err">{err}</div> : null}
    </div>
  )
}
