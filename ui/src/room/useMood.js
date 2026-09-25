/* useMood — the React door onto moodTheme. The ONLY reader of roomMood.get
 * (G-ROOM-TOKENS leg 3): the live value is what precedence is computed from, so whoever
 * reads it owns the rule. Callers pass the pulse they already poll; this adds no timer. */
import { useSyncExternalStore } from 'react'
import * as roomMood from './roomMood.js'
import { resolveMood } from './moodTheme.js'

export function useMood(pulse) {
  const live = useSyncExternalStore(roomMood.subscribe, roomMood.get)
  return resolveMood(live, pulse)
}
