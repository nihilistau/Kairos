/* When — the one time chip, on every line either of them produces.
 *
 * HIS ASK, 2026-08-05: "for both there and the main dialog lets add a date and time chip
 * to all actions/dialog, both mine and hers".
 *
 * ONE COMPONENT, DELIBERATELY. There were already four different renderings of a
 * timestamp in this UI — `String(n.due_at).slice(0, 16)` on the board, a bare `toLocale`
 * in the chat, `ago()` in the Clock, and raw epoch seconds in a couple of panels. Four
 * readings of one fact is the bug class this whole repo is annotated with, and here it
 * has a mild but real consequence: he reads "18:31" in one place and "2026-08-05T18:31"
 * in another and cannot tell at a glance whether they are the same moment.
 *
 * WHAT IT SAYS, AND WHY IT CHANGES:
 *   • today          — "18:31" plus the relative gap, because within a conversation what
 *                      he actually wants is "how long ago", and the clock time is the
 *                      thing he cross-references against a log.
 *   • yesterday      — "yesterday 18:31". A day boundary is the unit her life runs on
 *                      (consolidation at 04:00), so "yesterday" is a real word here.
 *   • older          — "3 Aug 18:31", and the year too once it is not this one.
 * The full ISO stamp is always in the title attribute, so hovering gives the exact thing
 * a log line would say. Nothing is ever rounded away — the chip is a summary, and the
 * precise value is one hover from it.
 *
 * IT ACCEPTS ANYTHING THE HARNESS EMITS, because the stores genuinely disagree: notes
 * write ISO-8601 local strings, the ledger writes integer epoch seconds, kairos writes
 * float epoch, and a couple of places write ISO with a trailing Z. Normalising at the
 * READER is the right seam — the alternative is a migration across five stores to fix a
 * label, and a reader that throws on an unfamiliar shape puts a red box in his chat.
 *
 * `bare` drops the relative half — for places that already say "due" or "at" in front of
 * it and would otherwise read "due in 3 days ago".
 */
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
             'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/* Epoch seconds, epoch ms, ISO with or without a zone, or a Date. Anything else -> null,
 * and a null renders NOTHING rather than "Invalid Date" — an unparseable stamp is a
 * missing chip, never a broken-looking line in his conversation. */
export function toDate(at) {
  if (at == null || at === '') return null
  if (at instanceof Date) return isNaN(at) ? null : at
  if (typeof at === 'number') {
    // Seconds vs milliseconds: anything below ~1e11 could not be a plausible ms stamp
    // (it would be 1973), and anything above could not be plausible seconds (year 5138).
    const d = new Date(at < 1e11 ? at * 1000 : at)
    return isNaN(d) ? null : d
  }
  const s = String(at).trim()
  if (/^\d+(\.\d+)?$/.test(s)) return toDate(parseFloat(s))
  const d = new Date(s)
  return isNaN(d) ? null : d
}

function hhmm(d) {
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0')
}

export function relative(d, now) {
  const s = Math.round((now - d) / 1000)
  if (s < 0) {
    // A FUTURE STAMP IS NOT AN ERROR — a due date is one, and so is a clock skew of a
    // few seconds between the gateway and the browser. Say it forwards.
    const a = -s
    if (a < 90) return 'in a moment'
    if (a < 3600) return `in ${Math.round(a / 60)}m`
    if (a < 86400) return `in ${Math.round(a / 3600)}h`
    return `in ${Math.round(a / 86400)}d`
  }
  if (s < 45) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  if (s < 86400) return `${Math.round(s / 3600)}h ago`
  if (s < 7 * 86400) return `${Math.round(s / 86400)}d ago`
  return ''
}

/* The words, without the element — for anywhere that needs the text alone. */
export function whenWords(at, now) {
  const d = toDate(at)
  if (!d) return ''
  const n = now || new Date()
  const sameDay = d.toDateString() === n.toDateString()
  const y = new Date(n.getTime() - 86400000)
  if (sameDay) return hhmm(d)
  if (d.toDateString() === y.toDateString()) return `yesterday ${hhmm(d)}`
  const dm = `${d.getDate()} ${MON[d.getMonth()]}`
  return (d.getFullYear() === n.getFullYear() ? dm : `${dm} ${d.getFullYear()}`) + ` ${hhmm(d)}`
}

export function When({ at, bare, className }) {
  const d = toDate(at)
  if (!d) return null
  const now = new Date()
  const rel = bare ? '' : relative(d, now)
  return (
    <span className={'when' + (className ? ' ' + className : '')}
          title={d.toISOString()}>
      {whenWords(at, now)}
      {rel ? <span className="when-ago">{rel}</span> : null}
    </span>
  )
}

export default When
