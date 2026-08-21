/* describe.js — the ONLY thing that crosses the renderer seam.
 *
 * Plain JS, no JSX, no React, no imports: so it is testable in node without a
 * browser or a build, which is what makes the seam a real contract rather than a
 * comment. A renderer implements this vocabulary or it does not; nothing else in
 * the room knows the difference between a canvas and a three.js scene.
 *
 * IT MUST NEVER THROW AND NEVER RETURN UNDEFINED FIELDS. The room paints before
 * the first pulse arrives, paints while the gateway is restarting, and paints when
 * the daemon is down — a backdrop that blanks on a missing field turns a slow
 * backend into a black screen, which reads as broken rather than as waiting.
 * Every access here is defensive on purpose.
 */

export const MOOD_KEYS = ['peaceful', 'playful', 'wistful', 'tender', 'sharp', 'quiet']

/** How long without a word before the room reads as empty. Ten minutes: long
 *  enough that reading a reply does not dim the lights, short enough to mean
 *  something by the time you come back to it. */
export const ALONE_AFTER_S = 600

export function describeRoom(pulse) {
  const p = pulse || {}
  const clock = p.clock || {}
  const her = p.her || {}
  const pres = p.presence || {}

  // Fall back to the browser's clock ONLY when the server has not spoken yet.
  // The server's hour is authoritative: if the two disagree, the machine is the
  // one that decides when her day ends.
  const hour = Number.isInteger(clock.hour) ? clock.hour : new Date().getHours()

  // Night is long here on purpose — this is a machine someone talks to at 3am.
  const phase =
    hour < 5 ? 'night' : hour < 8 ? 'dawn' : hour < 17 ? 'day' :
    hour < 21 ? 'dusk' : 'night'

  // Mood may be a bare word or a modified one ("warm, +tender"); take the first
  // token so the renderer always gets something it can look up.
  const mood = String(her.mood || 'quiet').split(/[,+]/)[0].trim().toLowerCase() || 'quiet'

  const silent = pres.since_last_turn_s
  const alone = silent == null ? true : silent > ALONE_AFTER_S

  return {
    phase,
    mood,
    // 0..1 — how awake the room looks. Warm and recently spoken to = brighter.
    energy: (pres.warm ? 0.55 : 0.2) + (alone ? 0 : 0.3),
    alone,
    // one slow breath for the whole room, so it reads as a single thing
    breath: 1 / 9,
  }
}

export default describeRoom
