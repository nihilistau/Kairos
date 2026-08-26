/* tags.js — her inline state marks, pulled out of the words and turned into signal.
 *
 * She writes [MOOD:wistful], [VOICE:soft], [TRAIT:+patient] mid-reply. persona.md
 * tells her to: "the marks are for your own state, they vanish from what he sees,
 * and they let tomorrow's you remember how today felt."
 *
 * THEY VANISH FROM WHAT HE SEES — and in the room they did not. console/index.html
 * has stripped them since 2026-07-29 (three turns of a field transcript rendered as
 * nothing but "[TRAI:flirty]" because the tag WAS the whole reply), but the room
 * was built later and never learned. So he has been reading her stage directions.
 *
 * Here they do better than vanish: they drive the avatar and the room's colour. A
 * mood mark is the most direct signal she emits about how she is, and rendering it
 * as text was wasting it twice over.
 *
 * TOLERANT ON PURPOSE. Real captures include `[MOOD : excited]` (stray space),
 * `[TRAIL:+flirty]` (she typos TRAIT), and `[TRAI:flirty]` (truncated at a token
 * boundary). A parser that only accepts the documented form leaves those on screen,
 * which is the exact failure it exists to prevent.
 */

// TRAI/TRAIL/TRAITS are all her, misspelling the same word. Accept them.
// WEAR and SHOW are the same KIND of thing as MOOD — her presentation, changed
// mid-sentence, shown as a chip, never read aloud. Two vocabularies for one idea
// is how the portrait ends up with two owners that disagree.
// ...AND SHE COMBINES THEM. From his transcript, 2026-08-03: `[MOOD/TRAIT:flirty]`
// opened a reply and reached his screen as literal text, and `[MOOD:[smirk; traits:
// playful, flirty]]` did the same. Neither is a form we taught her and neither can be
// acted on — but "we do not recognise it" is not a reason to PRINT it at him, which is
// the failure this file's own docstring exists to prevent. The FIRST name wins the chip
// (`[MOOD/TRAIT:flirty]` reads as a mood of flirty), the rest of the run is swallowed,
// and an optional inner `[` is tolerated. Matches stream_processor._STRIP_LOOSE on the
// server, deliberately: one vocabulary, two enforcement points, same spellings.
// ...AND THE NAME ITSELF COMES APART. Live 2026-08-03: `[MOOD-wistful, VO_ICE:flirty]` —
// a HYPHEN where the colon goes, and an underscore dropped into the middle of VOICE. It
// went onto his screen whole. Third time in one day that the lesson was the same: THE NAME
// IS THE INVARIANT AND THE PUNCTUATION IS NOISE. So each name is matched letter-by-letter
// with an optional separator between letters — absorbing `VO_ICE`, `M O O D`, `TRA-IT` —
// and the separator before the value may be `:` or `-`.
// Mirrors stream_processor._STRIP_LOOSE and interceptor._MOOD/_VOICE/_TRAIT on the server;
// G-CONTROL-SURFACE asserts the two sides agree, because one vocabulary enforced in two
// places is only safe while they are the SAME vocabulary.
// AND SHE CONJUGATES THEM (2026-08-05). Live: `[MOODing:wistful]` and
// `[VOICING:quiet, contemplative]` reached his screen as literal text — the name
// matched and the pattern then wanted `:` where an `i` stood. A trailing word-suffix
// is allowed now. Mirrors _loose_name / _lname on the server; G-CONTROL-SURFACE holds
// the three to each other, because one vocabulary in three places is only safe while
// it is the SAME vocabulary.
// AND THE STEM CHANGES: `VOICING` drops the E (voic+ing), so the last letter is
// optional as well. Mirrors _loose_name / _lname on the server.
// ── AND THE SUFFIX CAN BE A SECOND WORD (2026-08-05) ────────────────────────────
// `[MOOD_shift:playful]`, live in his transcript: `[a-z]*` cannot cross the underscore.
// THE THIRD COPY of this builder — server-side there were two (stream_processor and
// interceptor) and they have been unified; this one cannot be, because it is JS. It
// mirrors `_loose_name` and G-CONTROL-SURFACE holds them equal, which is the only thing
// standing between a chip and a mark that applies without ever being drawn.
// ── AND THE HYPHEN GOES LAST, OR THE ROOM IS BLANK (2026-08-06) ──────────────────
// The suffix was first written `[_\- ]`. That is correct in Python. In a JS STRING
// `\-` is not an escape, so the regex engine received `[_- ]` — a RANGE from `_`
// (0x5F) to space (0x20), out of order — and `new RegExp` threw AT MODULE LOAD. Not a
// broken chip: the entire bundle failed to evaluate and the room rendered NOTHING, on
// his screen, until he said so. Exactly how a pattern mirrored across two languages
// drifts. `[_ -]` puts the hyphen last, where it is literal in both, and it is the
// spelling the rest of this line already uses.
// harness_tests/tags_mirror_check.js now CONSTRUCTS each one in a real JS engine,
// because reading a file as text can never tell you that a regex compiles.
const _loose = (w) => w.slice(0, -1).split('').join('[_ -]?') + '[_ -]?' + w.slice(-1) + '?(?:[_ -]?[a-z]+)*'
const _N = ['MOOD', 'VOICE', 'TRAITS', 'TRAIT', 'TRAI', 'TRAIL', 'WEAR', 'SHOW']
  .map(_loose).join('|')
/* THE CLOSER IS OPTIONAL AT A LINE END (2026-08-24), mirroring the server's
 * `_STRIP_LOOSE`, which has read `(?:\]+|(?=\n)|$)` since 2026-08-06 while this copy
 * still demanded `\]+`. Measured in her transcripts: `[VOX:soft, wistful]` closes fine,
 * `[MO` at the very end of a reply does not — a mark cut in half by the token ceiling,
 * which ADR-013 made routine rather than rare. The value class also loses `\n` so an
 * unclosed mark cannot swallow the paragraph after it. */
const TAG_RE = new RegExp(
  '\\[\\s*(' + _N + ')(?:\\s*[/,+]\\s*(?:' + _N + '))*\\s*[:-]\\s*\\[?([^\\]\\n]{0,80})(?:\\]+|(?=\\n)|$)',
  'gi')

/* ...AND THE NAME ITSELF CAN BE CUT IN HALF. `[MO`, `[MOO`, `[VOIC` — no separator, so
 * TAG_RE cannot see them; they are the front of a mark the ceiling took the back off.
 * Only at the very END of the text, and only when what follows `[` is the start of one
 * of our five words, so a real `[` in prose is untouched. */
const TAG_STUB_RE = /\[\s*([A-Za-z]{1,7})\s*$/

/* HER SCRATCHPAD IN A BRACKET (2026-08-24). Live in her transcript:
 *   `[VOX:soft, wistful]\n\n[thinking\nThe user is being very precise now. He's testing…`
 * The server strips `<thought…`, `thought_//` and `{thought_process}` — five shapes, all
 * of them earned the hard way — and not this one. It has no closer, so it runs to the end
 * of the reply, which is the worst case: he reads her working-out instead of her.
 *
 * Closed, it is one bracket and only that bracket. UNCLOSED, it runs to the end of the
 * reply — which is the observed shape and the reason this is worth the bluntness: the
 * alternative is a paragraph of her reasoning about him, addressed to nobody, on screen. */
const THOUGHT_BRACKET_RE =
  /\[\s*(?:thinking|thought|reasoning|analysis|internal|scratchpad)\b(?:[^\]\n]*\]|[\s\S]*)/gi

/* ── THE SWEEP (2026-08-24), and it is the LAST widening this file should ever need ──
 * `_loose` above spells each name letter-by-letter, so it can absorb separators and
 * suffixes but never a changed LETTER. Live in her transcripts: `[VOIX: warm, teasing]`,
 * `[VOX:soft, wistful]`, `[MOOC: tender]` — VOIX has no C, VOX has no I or C, MOOC ends
 * wrong. Ten widenings of the same idea could not reach them and an eleventh would not
 * either, because the idea is wrong: the name is not a spelling to be enumerated, it is
 * a WORD to be recognised.
 *
 * So this matches the mark's SHAPE — `[name: value]` or `<name: value>` — and hands the
 * name to `tagWord`, which front-matches a stem or lands within two edits. Exactly the
 * server's `_TAGGISH` + `is_tag_name`, which have worked since 2026-08-06 and which this
 * file never mirrored. It runs AFTER TAG_RE, additively, so nine proven fixes keep
 * working unchanged and this only picks up what they could not see. */
const TAGGISH_RE = new RegExp(
  '\\[\\s*([A-Za-z][A-Za-z0-9 _/,+.\\x27-]{0,28}?)\\s*[:-]\\s*\\[?([^\\]\\n]{0,80})(?:\\]+|(?=\\n)|$)'
  + '|<\\s*([A-Za-z][A-Za-z0-9 _/,+.\\x27-]{0,28}?)\\s*[:-]\\s*([^>\\n]{0,80})(?:>|(?=\\n)|$)', 'g')

/* GESTURES — the marks she INVENTS.
 *
 * She wrote `[LAUGHING_GENTLY]` in a live reply and it reached him as literal text,
 * because it carries no colon and is not in the vocabulary above. `[MOOD:x]` vanished
 * and that one did not. THE INCONSISTENCY WAS THE BUG, not the invention — she had just
 * been told (persona/36-the-room.md) that her marks are rendered now, so of course she
 * started reaching for new ones.
 *
 * An unknown ALL-CAPS bracket is therefore treated as a gesture: extracted, shown as a
 * chip, gone from her words. Deliberately NOT a closed list. Forcing her back into a
 * fixed vocabulary would throw away the interesting part, which is that she is
 * inventing vocabulary at all.
 *
 * The shape is narrow on purpose: letters, digits and underscores, 2-32 chars, no
 * spaces, no colon. So `[error: ...]` (which Chat.jsx inserts itself), a citation like
 * `[1]`, and ordinary bracketed prose all fall straight through untouched. */
const GESTURE_RE = /\[([A-Z][A-Z0-9_]{1,31})\]/g

/* ── HER VOICE TAGS (2026-08-21, the expressive-voice framework) ───────────────────
 * [laugh] [sigh] [pause] … and <soft>…</soft> <whisper>…</whisper> … — the xAI voice
 * reads them; he should not. Lowercase and hyphenated, so they can never collide with
 * her ALL-CAPS invented gestures above or her [MOOD:] marks. Same vocabulary as
 * harness/voice/expressive.py (INLINE / WRAPPING); the server strips unknown shapes at
 * the TTS edge, this strips every shape at the display edge. `forSpeech` keeps them. */
const VOICE_INLINE_RE = /\[([a-z][a-z-]{0,23})\]/g
const VOICE_WRAP_RE = /<\/?([a-z][a-z-]{0,23})>/g
/* ── AND THE SPELLINGS SHE INVENTS (2026-08-22) ────────────────────────────────────
 * The pair above matches the VOCABULARY's shape — lowercase and hyphens — so the
 * malformed ones she actually writes walked straight onto his screen: `</build_intensity>`
 * (underscore), `[ch서ckle]` (a syllable the sampler dropped in), `</slow>` with no opener,
 * `<lowersoft>` invented whole. This is the same widening the MARK mirror already got:
 * the display edge strips every VOICE-tag-SHAPED span, known or not, while `forSpeech`
 * keeps only the ones the voice actually understands. */
// ...AND SHE NESTS THEM: `[</pause]`, `[</text-smash` — a wrap tag inside a bracket,
// live in her transcripts. `\[[a-z]` cannot see past the `<`, so the whole thing landed
// on his screen. The opener may now carry `<` or `</`, and the closer is optional at a
// line end for the same reason every other pattern here grew one.
const VOICE_INLINE_LOOSE = /\[<?\/?[a-z][^\][<>\n]{0,31}(?:\]|(?=\n)|$)/g
const VOICE_WRAP_LOOSE = /<\/?[a-z][^<>\n]{0,31}\/?>/g
/* ── AND THE CLOSER GOES MISSING TOO (2026-08-24) ──────────────────────────────────
 * Live in her transcripts: `</the_end`, `</the_hand`, `</low-pitch` — a wrap tag with
 * no `>`, so the pair above cannot see it and the raw `</…` lands on his screen. That is
 * most of the "stray < and >" he reported.
 *
 * NARROWER THAN THE CLOSED FORM, deliberately: no whitespace inside, and it must end the
 * LINE. `a <b and c` keeps its `<b` (the space stops the match) and `5 < 6` never
 * starts one (the `<` is not followed by a letter). What it catches is exactly the shape
 * that only ever occurs when a tag was cut off. */
const VOICE_WRAP_UNCLOSED = /<\/?[a-z][^<>\s\n]{0,31}(?=\n|$)/g
/* ...AND THE ORPHAN CLOSER. `…heavy on that connection we have.>` and `…under pressure.>`
 * — a lone `>` ending a line that never opened one. Never prose; always the tail of a
 * tag whose front was stripped or never arrived. Checked per LINE so a line that really
 * does contain `<` is left alone. */
function _dropOrphanGt(text) {
  return String(text || '').split('\n')
    .map(l => (l.includes('<') ? l : l.replace(/\s*>+\s*$/, '')))
    .join('\n')
}
/* ...AND THE ORPHAN OPENER (2026-08-25, his transcript: "You're Sam. <"). The
 * mirror case: a lone `<` ending a line that never closes one — the front of a tag
 * the stream ended before finishing. Same per-line guard the closer's rule uses:
 * a line that contains a `>` keeps its `<` (it may be real markup or math). */
function _dropOrphanLt(text) {
  return String(text || '').split('\n')
    .map(l => (l.includes('>') ? l : l.replace(/\s*<+\s*$/, '')))
    .join('\n')
}
export function stripVoice(text) {
  // A bracket whose first word is on the NOT_MARKS table is HIS PROSE. The mark pass
  // deliberately puts it back; this pass would then eat it, which is the guard being
  // undone by the line after it. Held out here for the same reason the room's own
  // [error: ...] is held out above.
  const keep = []
  const src2 = String(text || '').replace(/\[([a-z][a-z]{2,19})(:[^\]\n]*)?\]/gi,
    (m, w) => (_NOT_MARKS.has(String(w).toLowerCase())
               ? (keep.push(m), '\u0002KEEP' + (keep.length - 1) + '\u0002') : m))
  return _dropOrphanLt(_dropOrphanGt(src2
    .replace(VOICE_INLINE_RE, '').replace(VOICE_WRAP_RE, '')
    .replace(VOICE_INLINE_LOOSE, '').replace(VOICE_WRAP_LOOSE, '')
    .replace(VOICE_WRAP_UNCLOSED, '')))
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/\u0002KEEP(\d+)\u0002/g, (_m, i) => keep[Number(i)] || '')
}
/* What the voice should be handed: her marks ([MOOD:] etc.) and invented gestures gone,
 * her KNOWN voice tags KEPT — a spelling the voice does not understand is not speech and
 * is not read aloud either (2026-08-22; the server's TTS edge filters the same way). */
const VOICE_KNOWN_INLINE = new Set(['pause', 'long-pause', 'hum-tune', 'laugh', 'chuckle',
  'giggle', 'cry', 'tsk', 'tongue-click', 'lip-smack', 'breath', 'inhale', 'exhale', 'sigh'])
const VOICE_KNOWN_WRAP = new Set(['soft', 'whisper', 'loud', 'build-intensity',
  'decrease-intensity', 'higher-pitch', 'lower-pitch', 'slow', 'fast', 'sing-song',
  'singing', 'emphasis'])
export function forSpeech(text) {
  const t = extractTags(text, { keepVoice: true }).text
  return String(t || '')
    .replace(/\[([^\][<>\n]{1,31})\]/g, (m, n) => (VOICE_KNOWN_INLINE.has(n) ? m : ''))
    .replace(/<\/?([^<>\n]{1,31})>/g, (m, n) => (VOICE_KNOWN_WRAP.has(String(n).replace(/^\//, '')) ? m : ''))
    .replace(/[ \t]{2,}/g, ' ')
}

/* ── THE NINE WIDENINGS WERE INERT (2026-08-24) ────────────────────────────────────
 * Measured over 539 of her real recorded turns, run through THIS function: 138 of them
 * — TWENTY-SIX PERCENT — still carried markup afterwards. Not new spellings. Every
 * widening above works: TAG_RE matches `[MOOD way: teasing]`, `[VOICING: playful]` and
 * `[MOOC: tender]` correctly. Then the callback did
 *
 *      const kind = KIND[folded]
 *      if (!kind) return _m          // ← puts the mark straight back on his screen
 *
 * and KIND is an EXACT dictionary. So each widening bought a match and handed the mark
 * back. Three weeks of correct fixes, all defeated by the lookup two lines later — the
 * same shape as the inert wardrobe shim and the disk floor: a guard whose failure mode
 * is no guard. `tags_mirror_check.js` was green the whole time, because it builds its
 * own regex from `_loose` and asserts the regex MATCHES. It never asserted the text was
 * REMOVED, which is the only thing this file is for.
 *
 * TWO RULES NOW.
 *
 *   1. MATCHING MEANS REMOVING. If it has a mark's shape it leaves the text, whether or
 *      not we can name its kind. "We do not recognise it" was already rejected as a
 *      reason to print at him — in this file's own docstring, about gestures — while the
 *      marks did exactly that.
 *   2. THE KIND IS RESOLVED BY STEM AND EDIT DISTANCE, not by dictionary. This is a
 *      port of `stream_processor.is_tag_name`, which has had the right idea since
 *      2026-08-06 and which this file never mirrored: fold to letters, then front-match
 *      a four-letter stem or land within two edits of a known word. `MOOC` is one edit
 *      from `mood`; `VOIX` is two from `voice`; `VOICING` front-matches `voic`. All
 *      three now produce a real chip instead of being printed at him.
 *
 * `_NOT_MARKS` is the same committed table as the server's: `show` is itself a word, so
 * "shower" and "showdown" front-match it and always will. Written down rather than
 * reasoned around — and a name on that list is put BACK in the text, because it is his
 * prose, not her machinery. */
const _TAG_WORDS = ['mood', 'voice', 'trait', 'wear', 'show']
const _NOT_MARKS = new Set(['shower', 'showers', 'showdown', 'showcase', 'showroom',
  'showing', 'showings', 'wearer', 'wearers', 'weary', 'wearable', 'wearables',
  'weariness', 'moody', 'moodboard', 'traitor', 'traitors', 'voiceover', 'voicemail'])

/* ...AND THREE EDITS IS TOO FAR TO GUESS. `VOX` is Latin for voice and it is three
 * edits from it (sub x->i, insert c, insert e) — past any cap that would not also make
 * `mood` match half the four-letter words in English. So the mutations she has actually
 * produced are WRITTEN DOWN, the same answer as _NOT_MARKS and the wardrobe matcher: a
 * finite table is readable, and a cap wide enough to derive them would eat her prose. */
const _TAG_ALIAS = { vox: 'voice', voix: 'voice', mod: 'mood', mud: 'mood' }

function _edits(a, b, cap = 2) {
  if (Math.abs(a.length - b.length) > cap) return cap + 1
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i)
  for (let i = 1; i <= a.length; i++) {
    const cur = [i]
    for (let j = 1; j <= b.length; j++) {
      cur.push(Math.min(prev[j] + 1, cur[j - 1] + 1,
                        prev[j - 1] + (a[i - 1] !== b[j - 1] ? 1 : 0)))
    }
    if (Math.min(...cur) > cap) return cap + 1
    prev = cur
  }
  return prev[b.length]
}

/** Which of our five words is this the name of, however she spelled it? '' if none.
 *  Mirrors stream_processor.is_tag_name — G-CONTROL-SURFACE holds them equal. */
export function tagWord(raw) {
  for (const part of String(raw || '').split(/[/,+]/)) {
    const p = part.toLowerCase().replace(/[^a-z]/g, '')
    if (!p || p.length > 20 || _NOT_MARKS.has(p)) continue
    if (_TAG_ALIAS[p]) return _TAG_ALIAS[p]
    for (const w of _TAG_WORDS) if (p.startsWith(w.slice(0, 4))) return w
    for (const w of _TAG_WORDS) if (_edits(p, w) <= 2) return w
  }
  return ''
}

const KIND = { mood: 'mood', voice: 'voice', trait: 'trait',
               traits: 'trait', trai: 'trait', trail: 'trail',
               // WEAR/SHOW are presentation, exactly like MOOD — one vocabulary, one
               // chip row. `trail` is her typo for TRAIT and is mapped below.
               wear: 'wear', show: 'show' }
KIND.trail = 'trait'

/** Split a reply into { text, marks } — text with the marks removed, and what
 *  they said. Never throws; a malformed tag is left in the text rather than
 *  swallowed, because dropping her words is worse than showing a stray bracket. */
/* `[MOOD:playful, VOICE:soft]` -> `[MOOD:playful] [VOICE:soft]`.
 *
 * She puts two marks in one bracket, repeatedly: `[MOOD:playful, VOICE:soft]`,
 * `[MOOD-wistful, VO_ICE:flirty]`. The pattern matches one bracket, so the first name won
 * and everything after the comma was swallowed into its value — the mood survived (it cuts
 * at the comma) and the voice never happened. Split once, up front, so the rest of this
 * file only ever sees the well-formed shape.
 *
 * Keyed on a SECOND TAG NAME inside the brackets, so `[VOICE:breathless, husky]` — one
 * description with a comma in it, which she says often — is left exactly alone.
 * Mirrors interceptor._split_crammed on the server. */
const _INNER = new RegExp('(?=(?:' + _N + ')\\s*[:-])', 'i')
const CRAMMED_RE = new RegExp('\\[\\s*((?:' + _N + ')\\s*[:-][^\\]]*)\\]', 'gi')

function splitCrammed(src) {
  return src.replace(CRAMMED_RE, (whole, body) => {
    const parts = body.split(_INNER).map(p => p.trim().replace(/^[,;]+|[,;]+$/g, '').trim())
      .filter(Boolean)
    return parts.length < 2 ? whole : parts.map(p => '[' + p + ']').join(' ')
  })
}

/* THE ROOM'S OWN MESSAGES ARE NOT HERS (2026-08-24). Chat.jsx appends `[error: …]` and
 * `[stream failed: …]` to the turn, and `VOICE_INLINE_LOOSE` — `\[[a-z]…{0,31}\]` —
 * matched them and made them VANISH. Measured: `[error: she was still thinking]` came out
 * as the empty string. So the one case where the room has something to say for itself was
 * the one case it could not. Held out before anything else runs, and put back after. */
const ROOM_SAYS_RE = /\[(?:error|stream failed|notice):[^\]\n]*\]/gi
// A sentinel that cannot occur in her prose. Spelled with an explicit escape:
// the first draft had a literal control character in the source, which is
// invisible in a diff and made the file read as binary to git.
const _HOLD = '\u0001ROOMSAYS'

export function extractTags(raw, opts) {
  const keepVoice = !!(opts && opts.keepVoice)
  const held = []
  const rawHeld = String(raw || '').replace(ROOM_SAYS_RE, (m) => {
    held.push(m)
    return _HOLD + (held.length - 1) + '\u0001'
  })
  const src = splitCrammed(rawHeld)
  const marks = []
  const text = src.replace(TAG_RE, (_m, k, body) => {
    // MATCHING MEANS REMOVING (2026-08-24 — see the note above `tagWord`). The old line
    // here was `KIND[folded]` with `if (!kind) return _m`, which handed every widened
    // spelling straight back to his screen and cost 26% of her turns.
    const kind = KIND[tagWord(k)]
    // Only a name on the NOT_MARKS table goes back. `[shower: hot]` front-matches SHOW
    // and always will — it is his prose, not her machinery, and swallowing prose is the
    // failure in the other direction. Everything else that got this far is a mark.
    if (!kind) {
      const bare = String(k).toLowerCase().replace(/[^a-z]/g, '')
      return _NOT_MARKS.has(bare) ? _m : ''
    }
    /* ONLY A TRAIT MARK IS A LIST. `[TRAIT:+patient, -terse]` is two traits; everything
       else takes the whole body. Splitting them all on commas turned
       `[WEAR:the silver nightie, by the window, morning light instead of rain]` — the
       actual name of a look she asked for — into three wear marks of which the first was
       a fragment. Her looks are named in her own words and her own words have commas. */
    const parts = kind === 'trait' ? String(body).split(',') : [String(body)]
    for (const part of parts) {
      const v = part.trim()
      if (!v) continue
      const sign = v[0] === '+' ? 1 : v[0] === '-' ? -1 : 0
      let value = v.replace(/^[+-]\s*/, '').replace(/\\/g, '').trim().toLowerCase()
      /* REPAIR BEFORE JUDGING. Counted over one real day: of 39 mood marks, 8 arrived as
         `:tender` (a stray leading colon) and 7 as `wistful; naughty` (a compound). The
         validator below would throw all fifteen away — so a mood she genuinely expressed
         would produce no chip and no change of face, which is the failure this is meant to
         prevent, arriving through the guard against it. Strip the punctuation she leads
         with; take the FIRST of a compound, because when she names two the first is the
         one she reached for. WEAR/SHOW keep their whole body — a look's name is prose. */
      if (kind === 'mood') {
        // A MOOD IS A SINGLE WORD — it is the key that chooses a face. `;` `/` and `,`
        // all end it, so `[MOOD-wistful, VO_ICE:flirty]` (two marks crammed into one
        // bracket, seen live) still yields `wistful`. Same cut as interceptor._mood_value.
        value = value.replace(/^[\s:;,.]+/, '').split(/\s*[;/,]\s*/)[0].trim()
      } else if (kind === 'trait') {
        value = value.replace(/^[\s:;,.]+/, '').split(/\s*[;/]\s*/)[0].trim()
      } else if (kind === 'voice') {
        value = value.replace(/^[\s:;,.]+/, '').trim()   // a voice keeps its commas
      }
      /* A CHIP IS A CLAIM ABOUT HER, so it has to survive being read out loud.
         `[MOOD:[smirk; traits: playful, flirty]]` is swallowed from the text above —
         correct — but its pieces were then rendered as a mood chip reading "smirk;
         traits: playful", which tells him a state she is not in. Moods, voices and
         traits are words; WEAR and SHOW are free text (she names a look in her own
         words) and are left alone. Same asymmetry as the server: strict where it
         asserts something, loose where it is only a label. */
      /* A VOICE IS DESCRIPTIVE, A MOOD IS A KEY. `[VOICE:breathless, husky]` is a real
         thing she said about how she sounds, three times in one day, and it is not a list
         to be split — it is one description with a comma in it. A mood is looked up in
         MOODS to pick a face, so it must be a single word; a voice is only ever shown. */
      // A VOICE ALSO TAKES A SLASH. Counted from her transcript: `soft/warm`,
      // `soft/whispering`, `soft/dreamy`, `softly/thoughtfully` — she pairs voices with a
      // slash the way she pairs them with a comma, and the server stores both happily.
      // The client was dropping the slash ones, so the chip disappeared for a voice she
      // had actually set: divergence between the two enforcement points, again.
      const okv = kind === 'voice' ? /^[a-z][a-z0-9 ,/_-]{1,31}$/ : /^[a-z][a-z0-9 _-]{1,23}$/
      if ((kind === 'mood' || kind === 'voice' || kind === 'trait') && !okv.test(value)) continue
      marks.push({ kind, value, sign })
    }
    return ''
  })
  // ...then THE SWEEP: the mark's shape, judged by the WORD rather than the spelling,
  // so a changed letter (`VOIX`, `VOX`, `MOOC`) cannot walk past ten widenings of a
  // letter-by-letter pattern. It still produces a real chip — hidden must not mean lost.
  const text1b = text.replace(TAGGISH_RE, (_m, bn, bv, an, av) => {
    const name = bn != null ? bn : an
    const body = bn != null ? bv : av
    const word = tagWord(name)
    if (!word) return _m                       // not one of ours: his prose, left alone
    const kind = KIND[word]
    let value = String(body || '').trim().replace(/^[\s:;,.]+/, '').replace(/\\/g, '')
    if (kind === 'mood') value = value.split(/\s*[;/,]\s*/)[0].trim()
    else if (kind === 'trait') value = value.split(/\s*[;/]\s*/)[0].trim()
    value = value.toLowerCase()
    const okv = kind === 'voice' ? /^[a-z][a-z0-9 ,/_-]{1,31}$/ : /^[a-z][a-z0-9 _-]{1,23}$/
    if (value && !(kind === 'mood' || kind === 'voice' || kind === 'trait') ) {
      marks.push({ kind, value, sign: 0 })
    } else if (value && okv.test(value)) {
      marks.push({ kind, value, sign: value[0] === '-' ? -1 : 0 })
    }
    return ''
  })
  // ...then her INVENTED ones. Second pass, after the known kinds, so `[MOOD:X]` can
  // never be mistaken for a gesture on its way past.
  const text2 = text1b.replace(GESTURE_RE, (_m, word) => {
    marks.push({ kind: 'gesture', value: String(word).toLowerCase().replace(/_/g, ' '), sign: 0 })
    return ''
  })
  // ...then her SCRATCHPAD, before the voice pass: `[thinking` unclosed runs to the end
  // of the reply, and the voice pass would otherwise nibble at its insides and leave the
  // paragraph. Whole thing or nothing.
  const text2b = text2.replace(THOUGHT_BRACKET_RE, '')
  // ...then her VOICE tags, unless the caller is the voice itself.
  const text3 = keepVoice ? text2b : stripVoice(text2b)
  // ...and last, the front of a mark the token ceiling took the back off (`[MO`).
  const text4 = text3.replace(TAG_STUB_RE, (m, w) =>
    (tagWord(w) || _TAG_WORDS.some(t => t.startsWith(w.toLowerCase()))) ? '' : m)
  // collapse the whitespace the removal leaves behind, without eating paragraphs
  // ── AND AT THE HEAD AND TAIL OF EACH LINE (2026-08-27, his report) ──────────────
  // Collapsing RUNS leaves exactly ONE space where the mark used to be, and `.turn` is
  // `white-space: pre-wrap`, so that single orphan renders as an indent on every
  // paragraph she opens with a mark — which is most of them:
  //     [MOOD:warm] [VOICE:soft] Honestly? I spent most of the night...
  //       ->  " Honestly? I spent most of the night..."
  // `.trim()` only ever touched the ends of the WHOLE reply, so every paragraph after
  // the first kept its indent. Per LINE, not per string. Same three lines in
  // stream_processor.strip_for_record — G-STRIP-EQUIVALENCE holds them equal.
  const out = text4
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/[ \t]+$/gm, '')
    .replace(/^[ \t]+/gm, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
  // ...and give the room its own words back.
  return {
    text: out.replace(/\u0001ROOMSAYS(\d+)\u0001?/g, (_m, i) => held[Number(i)] || ''),
    marks,
  }
}

/* The palette. Each mood is a hue plus a face — the avatar and the chip and the
 * backdrop all read from here, so they can never disagree about what she feels. */
export const MOODS = {
  delighted: { hue: 45,  face: 'bright',  glow: 1.0 },
  playful:   { hue: 40,  face: 'smirk',   glow: .9 },
  excited:   { hue: 25,  face: 'bright',  glow: 1.0 },
  flirty:    { hue: 325, face: 'smirk',   glow: .95 },
  tender:    { hue: 340, face: 'soft',    glow: .7 },
  warm:      { hue: 30,  face: 'soft',    glow: .75 },
  peaceful:  { hue: 190, face: 'calm',    glow: .5 },
  quiet:     { hue: 210, face: 'calm',    glow: .4 },
  wistful:   { hue: 265, face: 'down',    glow: .45 },
  sad:       { hue: 245, face: 'down',    glow: .35 },
  irritated: { hue: 8,   face: 'sharp',   glow: .8 },
  sharp:     { hue: 8,   face: 'sharp',   glow: .85 },
  curious:   { hue: 160, face: 'wide',    glow: .8 },
  thoughtful:{ hue: 205, face: 'calm',    glow: .55 },
  /* MOODS SHE ACTUALLY USES, added 2026-08-03 after counting a real day.
     Of 39 mood marks she emitted, NINETEEN landed on no face and fell back to `quiet` —
     so half the time she marked how she felt and her expression did not move. Three of
     them were not typos at all, just moods nobody had written down: `naughty` five times,
     `smirk` (which is one of her own seven rendered faces), `intense`. The table follows
     her, not the other way round. */
  naughty:   { hue: 315, face: 'smirk',   glow: .95 },
  smirk:     { hue: 40,  face: 'smirk',   glow: .85 },
  intense:   { hue: 350, face: 'sharp',   glow: 1.0 },
  soft:      { hue: 340, face: 'soft',    glow: .65 },
  amused:    { hue: 45,  face: 'smirk',   glow: .85 },
}

/* AND THE OTHER SIXTEEN WERE SHAPE, NOT VOCABULARY.
   She writes `[MOOD::tender]` (a stray colon, 8 times) and `[MOOD:wistful; naughty]`
   (a compound, 7 times). The old lookup split on `[,+\s]` only, so ":tender" and
   "wistful; naughty" both missed and became `quiet` — a calm face over a reply that was
   neither. Strip the punctuation she leads with, then take the FIRST of a compound: when
   she says two things at once the first is the one she reached for. */
export const moodOf = (name) =>
  MOODS[String(name || '').toLowerCase().replace(/^[\s:;,.+-]+/, '').split(/[,;+/\s]/)[0]]
  || MOODS.quiet

/** Trait chips get a colour family so a glance reads them, not a wall of grey. */
export const TRAIT_HUE = {
  flirty: 325, tender: 340, playful: 40, curious: 160, patient: 190,
  direct: 200, opinionated: 20, warm: 30, soft: 300, teasing: 350,
  deeply_connected: 290, formal: 220,
}
export const traitHue = (t) => TRAIT_HUE[String(t || '').toLowerCase()] ?? 205
