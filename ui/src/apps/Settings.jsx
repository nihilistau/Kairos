import { KnobGroups } from './knobs.jsx'

/* SETTINGS — the tuning registry, rendered whole (2026-08-21, his ask: "a settings
 * icon/window that contains these things with a nice layout, sections etc and
 * include all other settings in their own sections").
 *
 * NOTHING IS HAND-BUILT PER KNOB. The registry declares {group, label, type,
 * choices, help, scope}; KnobGroups (shared with the voice and search panels)
 * renders whatever it finds, grouped. A knob added server-side appears here with
 * no UI edit — the registry's founding rule, honored by a first-class window.
 *
 * LIVE vs PROFILE, said honestly: scope="live" knobs take effect on the next
 * call that reads them (voice on her next sentence, search on her next query) —
 * the LIVE chip. scope="profile" knobs are owned by the profile through serve.py;
 * the panel shows the value in force read-only with a "restart to change" chip,
 * because a control that displays a stale number and changes nothing is worse
 * than no control (the registry's own history, End-of-turn bias 4.00).
 *
 * Prefix `st-`, per the appRegistry CSS-ownership rule.
 */
export default function Settings() {
  return (
    <KnobGroups first={['Voice', 'Web search', 'Research', 'Wardrobe']}
                extras={{ Voice: 'voice-test' }} />
  )
}
