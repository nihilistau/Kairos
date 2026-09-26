/* facts — THE ROOM'S TIME WORDS, in one place (redesign stage 3, spec §8).
 *
 * Clock.jsx computed these and the taskbar never had room to show them; the top bar
 * does. The top bar's time words live here, in one module — NOT YET THE ONLY OWNER of
 * "46m ago": room/When.jsx's relative() still spells ages for the panels, and Librarians
 * builds its own "Nm ago" (both ledgered for stage 6). Time here is HER experience of it
 * (when he last spoke, when her day closes), from the pulse. */

export function ago(s) {
  if (s == null) return null
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  if (s < 86400) return `${Math.round(s / 3600)}h ago`
  return `${Math.round(s / 86400)}d ago`
}

export function until(s) {
  if (s == null) return null
  if (s < 60) return `${Math.max(0, Math.round(s))}s`
  if (s < 3600) return `${Math.round(s / 60)}m`
  return `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`
}

/* An uptime as a person says it: minutes, then hours and minutes, then days and hours. */
export function upFor(s) {
  if (s == null || s < 0) return null
  if (s < 3600) return Math.max(1, Math.round(s / 60)) + 'm'
  if (s < 86400) return Math.floor(s / 3600) + 'h ' + Math.round((s % 3600) / 60) + 'm'
  return Math.floor(s / 86400) + 'd ' + Math.floor((s % 86400) / 3600) + 'h'
}

/* Her day, in the order the top bar reads it: he spoke, her day, the eye. The WORDS are
 * Clock.jsx's, verbatim — copy about her is not ours to rephrase (G-ROOM-KIT leg 8). */
export function dayFacts(pulse) {
  const p = pulse || {}
  const c = p.clock || {}
  const pres = p.presence || {}
  const out = []
  if (pres.since_last_turn_s != null) out.push({ k: 'you spoke', v: ago(pres.since_last_turn_s) })
  if (c.boundary_hour != null) {
    out.push(c.consolidated_today
      ? { k: 'her day', v: 'closed — she has written' }
      : { k: 'her day ends', v: `in ${until(c.next_boundary_in_s)}` })
  }
  if (pres.ambient_enabled) out.push({ k: 'next look', v: until(pres.ambient_next_in_s) || 'soon' })
  return out
}
