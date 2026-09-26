/* roomMood — her live mood, published by whoever is rendering her reply.
 *
 * WHY THIS EXISTS (2026-09-23). Chat used to hand its `[MOOD:]` reads upward through
 * an `onMood` prop, and `Room` fed that to the backdrop and the Portrait. That wire
 * only works while Chat is a child of Room. Chat is a WINDOW now, mounted by the
 * registry like every other app, and the registry mounts components with no props —
 * so the prop had to become something both ends can reach without being related.
 *
 * A module-level store with a listener Set, read through useSyncExternalStore: the
 * same shape as windowManager.js, deliberately. No context, no reducer, no library.
 * The room already made this choice once and a second idiom for the same job is the
 * thing this codebase keeps getting hurt by.
 *
 * WHY IT MATTERS THAT IT IS LIVE. The pulse reads persona.md, which only changes when
 * the curator writes. Her `[MOOD:]` mark in the reply on screen is what she is feeling
 * RIGHT NOW, and that is what the room should be wearing — so this beats the polled
 * value, exactly as it did when it was a prop.
 *
 * The snapshot is a CACHED OBJECT, not a fresh one per read. useSyncExternalStore
 * compares by identity and re-renders forever if getSnapshot allocates.
 */
let state = { mood: null, thinking: false }
const listeners = new Set()

export const subscribe = (fn) => { listeners.add(fn); return () => listeners.delete(fn) }
export const get = () => state

/* Same call shape Chat always used: `set(mood)`, `set(null, true)` when she starts
 * generating, `set(null, false)` when she stops. A null mood LEAVES the last one
 * standing — she is still wearing what she was wearing while she thinks, and blanking
 * the room between turns reads as a flicker.
 *
 * AN OMITTED `thinking` KEEPS THE CURRENT ONE (2026-09-26, the stage-1/2 live check).
 * It used to default to false, and the gateway's persona event arrives at the TOP of a
 * turn carrying her mood — so `set(mood)` ended "thinking" before the prefill had, and
 * the orb and busy cursor never showed during a 3-minute turn (0 of 803 samples).
 * Only Chat's `finally` ends it now. */
export function set(mood, thinking) {
  const next = { mood: mood ?? state.mood, thinking: thinking ?? state.thinking }
  if (next.mood === state.mood && next.thinking === state.thinking) return
  state = next
  listeners.forEach(fn => fn())
}
