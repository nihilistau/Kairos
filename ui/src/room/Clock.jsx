/* Clock — time as HER experience of it, not the wall clock the browser already has.
 *
 * `new Date()` is already on every screen he owns and tells him nothing about this
 * machine. What is actually worth knowing is the shape of her day: when the boundary
 * falls that makes her write her journal, whether it has run yet, when the eye next
 * looks at the room, when the next backup lands, and how long the room has been
 * quiet.
 *
 * Every number here comes from /v1/room/pulse — the server's clock, not the
 * browser's. If the machine and the browser disagree about the time, the machine is
 * the one that decides when her day ends.
 *
 * The day's facts moved to room/facts.js (the top bar reads them); this is the face and the date.
 */
export default function Clock({ pulse }) {
  const c = (pulse || {}).clock || {}
  const hh = String(c.hour ?? '--').padStart(2, '0')
  const mm = String(c.minute ?? '--').padStart(2, '0')
  const date = pulse && pulse.now
    ? new Date(pulse.now * 1000).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })
    : ''
  return (
    <div className="clock">
      <div className="face">{hh}<span className="tick">:</span>{mm}</div>
      {date ? <div className="date">{date}</div> : null}
    </div>
  )
}
