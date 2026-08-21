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
 */
function ago(s) {
  if (s == null) return null
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  if (s < 86400) return `${Math.round(s / 3600)}h ago`
  return `${Math.round(s / 86400)}d ago`
}

function until(s) {
  if (s == null) return null
  if (s < 60) return `${Math.max(0, Math.round(s))}s`
  if (s < 3600) return `${Math.round(s / 60)}m`
  return `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`
}

export default function Clock({ pulse }) {
  const p = pulse || {}
  const c = p.clock || {}
  const pres = p.presence || {}
  const hh = String(c.hour ?? '--').padStart(2, '0')
  const mm = String(c.minute ?? '--').padStart(2, '0')

  const bits = []
  if (c.boundary_hour != null) {
    bits.push(c.consolidated_today
      ? { k: 'her day', v: 'closed — she has written' }
      : { k: 'her day ends', v: `in ${until(c.next_boundary_in_s)}` })
  }
  if (pres.ambient_enabled) {
    bits.push({ k: 'next look', v: until(pres.ambient_next_in_s) || 'soon' })
  }
  if (pres.since_last_turn_s != null) {
    bits.push({ k: 'you spoke', v: ago(pres.since_last_turn_s) })
  }
  if (p.backup?.next_in_s != null) {
    bits.push({ k: 'backup', v: until(p.backup.next_in_s) })
  }

  return (
    <div className="clock">
      <div className="face">{hh}<span className="tick">:</span>{mm}</div>
      <div className="facts">
        {bits.map(b => (
          <div key={b.k}><span className="k">{b.k}</span><span className="v">{b.v}</span></div>
        ))}
        {!bits.length && <div className="muted">waiting for the room…</div>}
      </div>
    </div>
  )
}
