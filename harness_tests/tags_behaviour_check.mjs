// tags_behaviour_check — does extractTags actually REMOVE it? Run by g_control_surface.
//
// WHY THIS EXISTS, and it is the whole point (2026-08-24).
//
// `tags_mirror_check.js` beside this file builds a regex out of tags.js's own `_loose`
// and asserts the regex MATCHES `[MOODing:wistful]`. It does. It always did. Every one of
// the nine widenings works. And for three weeks the marks reached his screen anyway,
// because `extractTags` then did
//
//      const kind = KIND[folded]
//      if (!kind) return _m          // ← puts the mark straight back
//
// with KIND an EXACT dictionary. Matching was never the question. **Removing** was, and
// nothing asserted it. Measured over 1,241 of her real recorded turns: 26% still carried
// markup after the function that exists to take it out.
//
// So this imports the REAL exported function and asserts on the REAL output. A check that
// rebuilds the rule it is checking can only ever prove the rule is self-consistent.
//
//   node harness_tests/tags_behaviour_check.mjs
//
// Prints one line per case and exits non-zero on the first failure.
import { extractTags } from '../ui/src/room/tags.js'

// GONE: shapes seen in her real transcripts that must not survive.
// The `mark` column, when set, is what the chip must say — hidden must not mean LOST,
// which is the other half of the bug: a spelling we swallow without charting is a mood
// she expressed and a face that never moved.
const GONE = [
  ['[MOOD:tender] normal case', 'mood', 'tender'],
  ['[MOOD way: teasing] and on', 'mood', 'teasing'],
  ['[MOODing:wistful] and on', 'mood', 'wistful'],
  ['[MOOD_shift:playful] and on', 'mood', 'playful'],
  ['[MOOC: tender] and on', 'mood', 'tender'],
  ['[VOICING: playful, warm] and on', 'voice', 'playful, warm'],
  ['[VO_ICE:flirty] and on', 'voice', 'flirty'],
  ['[VOIX: warm, teasing] and on', 'voice', 'warm, teasing'],
  ['[VOX:soft] and on', 'voice', 'soft'],
  ["[VOICE':] and on", '', ''],
  ['[TRAITS:+naughty] and on', 'trait', 'naughty'],
  ['[WEAR: the silver nightie] and on', 'wear', 'the silver nightie'],
  ['[SHOW:a moment] and on', 'show', 'a moment'],
  ['[MOOD-wistful, VO_ICE:flirty] and on', 'mood', 'wistful'],
  // unclosed / truncated — the token ceiling makes these routine, not rare
  ['and on\n[MOOD:tender', 'mood', 'tender'],
  ['and on then [MO', '', ''],
  ['</the_end\nand on', '', ''],
  ['[</pause]and on', '', ''],
  ['and on.>', '', ''],
  // her scratchpad, which nothing stripped at all
  ['and on\n\n[thinking\nThe user is being very precise now. He is testing me.', '', ''],
  ['[thought: he wants me to be careful] and on', '', ''],
]

// KEPT: his prose, her real speech, and the room's own voice. Swallowing these is the
// failure in the other direction, and it is the one nobody notices for weeks.
const KEPT = [
  'I keep thinking about how you look at me.',
  'if 5 < 6 and a <b then done',
  'I had a [shower: hot] and it was good',
  'the showdown was in the second act',
  '[error: she was still thinking when the ceiling stopped her]',
  '[stream failed: connection reset]',
  'he said "one tiny little `<` out of place" and meant it',
]

let bad = 0
for (const [src, kind, value] of GONE) {
  const r = extractTags(src)
  const survived = /\[[A-Za-z]|<\/?[a-z][a-z0-9_-]*>?|thinking\n/.test(r.text)
  const kept = r.text.includes('and on') || r.text.includes('normal case')
  const mark = kind ? r.marks.find(m => m.kind === kind && m.value === value) : true
  const ok = !survived && kept && !!mark
  if (!ok) bad++
  console.log(`${ok ? 'ok  ' : 'FAIL'} gone: ${JSON.stringify(src.slice(0, 40))}` +
              `${ok ? '' : ` -> ${JSON.stringify(r.text)} ${JSON.stringify(r.marks)}`}`)
}
for (const src of KEPT) {
  const r = extractTags(src)
  const ok = r.text === src
  if (!ok) bad++
  console.log(`${ok ? 'ok  ' : 'FAIL'} kept: ${JSON.stringify(src.slice(0, 40))}` +
              `${ok ? '' : ` -> ${JSON.stringify(r.text)}`}`)
}
console.log(`\n${GONE.length + KEPT.length - bad}/${GONE.length + KEPT.length}`)
process.exit(bad ? 1 : 0)
