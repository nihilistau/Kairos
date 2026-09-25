/* moodTheme — THE ONE PLACE her mood's precedence is decided (2026-09-24).
 *
 * Her live [MOOD:] mark (roomMood, published by Chat) beats the polled pulse, which only
 * moves when the curator writes persona.md. The shell and RoomView each worked that out
 * for themselves — two paths for one rule, AGENTS.md §0 in miniature. Now both ask here.
 *
 * Pure, and imports only tags.js, so G-ROOM-TOKENS drives it under node. The React side
 * is room/useMood.js; keeping it out of this file is what keeps this file testable.
 *
 * AN UNKNOWN WORD STAYS HERS. If she says "sleepy" the room shows "sleepy" — it is what
 * she said — and borrows quiet's hue, because there is no colour on file for it.
 */
import { MOODS, moodWord } from './tags.js'

export const DEFAULT_MOOD = 'quiet'

export function resolveMood(live, pulse) {
  const liveWord = moodWord(live && typeof live.mood === 'string' ? live.mood : '')
  const her = pulse && typeof pulse.her === 'object' && pulse.her ? pulse.her : {}
  const polledWord = moodWord(typeof her.mood === 'string' ? her.mood : '')
  const word = liveWord || polledWord || DEFAULT_MOOD
  const known = Object.prototype.hasOwnProperty.call(MOODS, word)
  const entry = known ? MOODS[word] : MOODS[DEFAULT_MOOD]
  return {
    word, known,
    hue: entry.hue, glow: entry.glow, face: entry.face,
    thinking: !!(live && live.thinking),
  }
}

/* Written on <html> by the shell, once per change. Everything else reads the variables. */
export function applyMood(el, m) {
  if (!el || !m) return
  el.style.setProperty('--mood-h', String(m.hue))
  el.style.setProperty('--mood-glow', String(m.glow))
  el.dataset.mood = m.word
  el.classList.toggle('mood-thinking', !!m.thinking)
}
