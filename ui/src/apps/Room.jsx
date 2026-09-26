import { usePoll, Body } from './panel.jsx'
import * as api from '../api.js'
import { When } from '../room/When.jsx'
import { KnobGroups } from './knobs.jsx'
import { Chip, State } from '../kit/parts.jsx'

/* THE ROOM — her hourly notes.
 *
 * The ambient eye: one webcam frame an hour, described by her own vision tower,
 * one dated sentence in a rolling log. Shown oldest-first, in order, rather than
 * as a reverse-chron feed: one line an hour is a THREAD, not a snapshot, and the
 * shape of the day is the thing worth seeing. He was at the desk at two and the
 * room was empty at five.
 *
 * RE-ARMED 2026-08-21 with the quiet guard: a due capture waits until his turns,
 * her kairos/solo work and the daemon have all been idle for the quiet window
 * (a knob, below and in Settings) — so the status here has three honest states:
 * looking on schedule, DUE BUT WAITING for quiet (with why), or off. An empty or
 * stale panel that does not say which is the bug this panel had twice.
 */
/* The window's body, split out so G-ROOM-KIT leg 10 can render it with a fixture.
 * The state line is a kit Chip: warn when off or waiting for quiet, ok when looking.
 * It is a sentence, so the chip wraps (final review, M6). */
export function RoomView({ d }) {
  const rows = d.ambient_recent || []
  const a = d.ambient || {}
  const state = !a.enabled
    ? <Chip tone="warn" wrap title="disarmed state — the profile carries the arming condition">
        the hourly look is off{rows.length ? ' — below is its last day' : ''}
      </Chip>
    : a.waiting
      ? <Chip tone="warn" dot wrap title={'due for ' + a.waiting.for_s + 's — holds the shutter, does not push the schedule'}>
          due — waiting for quiet ({a.waiting.why})
        </Chip>
      : <Chip tone="ok" dot wrap>
          looking hourly{a.next_in_s != null ? ' — next in ~' + Math.max(0, Math.round(a.next_in_s / 60)) + 'm' : ''}
          {a.quiet_s ? ' after ' + Math.round(a.quiet_s / 60) + 'm of quiet' : ''}
        </Chip>
  return (
    <>
      <div className="rm-state">{state}</div>
      {!rows.length ? (
        <State kind="empty">nothing written yet — the first look lands within the hour</State>
      ) : rows.map((r, i) => (
        <div key={i} className="obs">
          <When at={r.iso} bare />
          <span className={r.error ? 'err' : ''}>{r.seen || r.error}</span>
        </div>
      ))}
      <details className="rm-knobs">
        <summary>eye settings</summary>
        <KnobGroups only={['Senses — the room on a timer']} />
      </details>
    </>
  )
}

export default function Room() {
  const s = usePoll(api.senses, 20000)
  return <div className="pad"><Body state={s}>{d => <RoomView d={d} />}</Body></div>
}
