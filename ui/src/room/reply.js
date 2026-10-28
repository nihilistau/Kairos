/* reply.js — HER REPLY IN FLIGHT, AND HOW HIS VOICE CUTS IT (2026-10-29).
 *
 * The operator's call: "yes stop her reply when you speak." Before this, opening the mic
 * hushed her voice and HELD the reply while he recorded — and the moment he sent, the rest of
 * that reply was spoken over the turn he had just started, and a line said in always-mode
 * waited for her to finish. Now his voice is an interruption, the way it is in a room:
 *
 *   begin(abort)  Chat starts a reply; `abort` is the SAME control the stop button pulls.
 *   interrupt()   he started talking (ears.js: push-to-talk start, always-mode speech onset):
 *                 her voice stops, the reply is aborted ONCE, and it is marked cut.
 *   feed / flush  speech.feed / speech.flush for that reply — a no-op once it is cut, so
 *                 nothing more of it is ever spoken, during his line or after it.
 *   end(r)        the reply is over (its stream closed, however).
 *
 * A mic opened while she is idle has no reply to cut: interrupt() still hushes anything
 * playing (an unprompted line) and aborts nothing.
 */
import * as speech from './speech.js'

let live = null                // { abort, cut } — the reply streaming now, or null

export function begin(abort) { live = { abort, cut: false }; return live }

export function end(r) { if (live === r) live = null }

/* True when a reply was cut by this call; false when there was none (or it was already cut). */
export function interrupt() {
  speech.stop()
  const r = live
  if (!r || r.cut) return false
  r.cut = true
  try { r.abort() } catch (_) { /* an abort that throws has still been asked */ }
  return true
}

export function feed(r, text, cursor) {
  return r && r.cut ? (cursor || 0) : speech.feed(text, cursor)
}

export function flush(r, text, cursor) {
  return r && r.cut ? String(text || '').length : speech.flush(text, cursor)
}
