/* probe — a room tab that LOOKS WITHOUT TAKING (redesign stage 6).
 *
 * GET /v1/kairos/outbox drains her queue (scheduler.drain, which also empties the no-owner
 * "default" queue into whoever asks), and Chat speaks what it drains. So a new room tab
 * opened for a UI check stole her unprompted turns from his room and said them where he
 * could not hear (2026-09-26). `?probe=1` on the room URL makes a tab that never polls the
 * outbox and never speaks. His own tabs are unchanged: what the outbox SHOULD mean with
 * more than one tab is his decision, not this file's. */
export function isProbe(search = (typeof location !== 'undefined' ? location.search : '')) {
  try { return new URLSearchParams(search).get('probe') === '1' } catch (_) { return false }
}
