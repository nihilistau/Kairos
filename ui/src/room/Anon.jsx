import { useState } from 'react'
import * as api from '../api.js'

/* OFF THE RECORD — the switch, and the two places it has to be visible.
 *
 * (2026-08-23, his ask: "an icon that activates anonymous mode that will still be her
 * but will not record any memory or logs etc until turned off or restarted.")
 *
 * THE DANGEROUS DIRECTION IS THE QUIET ONE. A private mode you forget you left ON costs
 * an evening of her memory; a private mode you forget you turned OFF costs the privacy
 * you asked for. Both are the same bug — the switch not looking like its state — so it
 * is drawn three times over: the dock button, a taskbar chip that only exists while it
 * is on, and a red rule around the whole room (`.an-on` in room.css). None of those is
 * decoration; a mode with one small indicator is a mode that gets misread.
 *
 * NO CONFIRM ON THE WAY IN, and that is deliberate. Turning it ON fails safe — the worst
 * case is an evening he wanted kept and did not get. A modal in front of "stop recording
 * me" is the wrong instinct: it is the one control here that should be reachable in a
 * hurry.
 *
 * IT SAYS WHAT IT HELD ON THE WAY OUT. `leave()` returns the tally, and it is the ONLY
 * time that tally will ever exist — it is process memory, it is cleared on the same call,
 * and nothing about it is written down. So the receipt is shown for a while and then it
 * is genuinely gone, which is the honest rendering of what just happened.
 */
export default function Anon({ anon, refresh }) {
  const [busy, setBusy] = useState(false)
  const [held, setHeld] = useState('')
  const on = !!(anon && anon.on)

  const toggle = async () => {
    if (busy) return
    setBusy(true)
    try {
      const r = await api.anonSet(!on)
      // The reply IS the state, so the button never has to guess at what it just did —
      // and on the way out it carries the one and only copy of the receipt.
      setHeld(!on ? '' : (r && r.held_total ? r.receipt : 'nothing was written down'))
      if (refresh) refresh()
    } catch (e) {
      setHeld('the switch did not answer: ' + (e.message || e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="an-wrap">
      <button className={'an-btn' + (on ? ' on' : '')} disabled={busy} onClick={toggle}
              title={on
                ? 'she is still her; nothing is being written down. click to start keeping the evening again'
                : 'off the record — she stays entirely herself, but no memory, journal, transcript or receipt is written until you turn it off or restart'}>
        <span className="dock-ic">{on ? '🕶' : '👤'}</span>
        <span className="dock-lb">{on ? 'off the record' : 'anonymous'}</span>
      </button>
      {held ? <div className="an-receipt" onClick={() => setHeld('')}>{held}</div> : null}
    </div>
  )
}

/* THE CHIP. Lives in the taskbar beside the scene chip, for the same reason that one
 * does: a running scene changes who she is and he did not know for 17 beats. A mode
 * that changes what survives the evening deserves at least as much. It carries the
 * elapsed time and the live tally, so "is this actually doing anything" has an answer
 * on the screen rather than in a log. */
export function AnonChip({ anon }) {
  if (!anon || !anon.on) return null
  const m = Math.round((anon.for_s || 0) / 60)
  return (
    <span className="an-chip" title={anon.receipt || 'nothing held back yet'}>
      <b>off the record</b>
      <span className="an-held">
        {m >= 1 ? m + 'm' : 'just now'}
        {anon.held_total ? ' · ' + anon.held_total + ' held' : ''}
      </span>
    </span>
  )
}
