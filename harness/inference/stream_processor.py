"""
Stream Processor
================

Mines inline control tags out of a token stream and exposes a clean text
channel plus structured side-effects. Ported from CosySim's StreamProcessor;
backend-agnostic — it consumes :class:`~harness.inference.client.StreamEvent`
objects from any source (the sp-daemon, a tool loop, a replayed transcript).

Inline tags::

    [MOOD:happy]            -> mood_tags
    [IMAGE:a red door]      -> image_requests
    [ACTION:sit down]       -> action_tags
    [STAT:arousal+10]       -> stat_deltas
    [VOICE:whisper]         -> voice_style
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

from harness.inference.client import StreamEvent


# ──── Patterns ────────────────────────────────────────────────────────────
_PATTERNS: Dict[str, re.Pattern] = {
    "mood": re.compile(r"\[MOOD:([^\]]+)\]"),
    "image": re.compile(r"\[(?:IMAGE|SELFIE|PHOTO):([^\]]+)\]"),
    "action": re.compile(r"\[ACTION:([^\]]+)\]"),
    "stat": re.compile(r"\[STAT:([a-zA-Z_]+)([+-]\d+(?:\.\d+)?)\]"),
    "voice": re.compile(r"\[VOICE:([^\]]+)\]"),
    "trait": re.compile(r"\[TRAIT:([^\]]+)\]"),  # PF-B3: self-modify a personality trait
}
# WEAR/SHOW join the vocabulary here as well as in the interceptor: they are marks,
# so they must never reach his screen. `SHOW` allows an EMPTY value because
# `[SHOW:]` is how she takes a moment back down — the mark and its own undo.
_STRIP = re.compile(r"\[(?:MOOD|IMAGE|SELFIE|PHOTO|ACTION|STAT|VOICE|TRAIT|WEAR):[^\]]+\]"
                    r"|\[SHOW:[^\]]*\]")

# ── THE TAG THAT LEAKED INTO HER MOUTH (2026-07-29) ─────────────────────────────
# Field transcript, your model. Three of eight replies rendered as a tag and
# nothing else, and the tag was visibly wrong:
#
#     [MOOD:+intense] [TRAIТ:+flirty]        <- U+0422 CYRILLIC CAPITAL TE, not "T"
#     [MOOD:+intense] [TRAIТ:+flirty         <- and no closing bracket
#
# _STRIP above requires the literal ASCII spelling and a "]", so neither is a tag as
# far as it is concerned: the whole thing survives the strip and is DISPLAYED, which
# is how the operator ended up reading "[TRAI:flirty]" as her entire reply.
#
# This is a MODEL property, not a bug we can fix upstream. The 12B emitted the tag
# vocabulary cleanly; a 4B-active QAT MoE does not, and it will keep finding new ways
# to misspell it. The stripper must therefore be forgiving in EXACTLY one direction:
# never show the user something tag-shaped. Homoglyphs are folded to ASCII, an
# unterminated tag at the very end of the text is dropped, and spaces are tolerated
# around the colon. Recognition for SIDE EFFECTS (the _PATTERNS above) stays strict —
# a garbled tag must not be allowed to actually move her mood or traits, because a
# misparse there writes to persistent personality state.
_HOMOGLYPHS = str.maketrans({
    "А": "A", "Е": "E", "І": "I", "М": "M", "О": "O",
    "Р": "P", "С": "C", "Т": "T", "Х": "X", "Ѕ": "S",
    "Β": "B", "Η": "H", "Κ": "K", "Μ": "M", "Ν": "N",
    "Ο": "O", "Ρ": "P", "Τ": "T", "Χ": "X",
})
# REGISTERED VOCABULARY GAP (2026-08-19): IMAGE/SELFIE/PHOTO/ACTION/STAT are the legacy
# five — server-side strip only. The room's mirror (tags.js::_N) deliberately excludes
# them (no chip kind exists for them); the console's copy includes them (it replays old
# transcripts). She has never emitted one on the live path. ARMING CONDITION for adding
# them to tags.js: a live sighting in a transcript — until then a chip kind with no
# renderer would be its own leak.
_TAG_NAMES = "MOOD|IMAGE|SELFIE|PHOTO|ACTION|STAT|VOICE|TRAIT|WEAR|SHOW"
# An unterminated tag ends at the line break, not just at end-of-string: the field
# case was "[TRAIТ:+flirty\n\nI am female." — with only `$` (no MULTILINE) the tag ran
# past the newline, matched nothing, and the whole thing was displayed.
#
# SHE ALSO COMBINES THEM (2026-08-03, from his transcript): `[MOOD/TRAIT:flirty]` and
# `[MOOD:[smirk; traits: playful, flirty]]`. Neither is a tag we taught her and neither
# is a tag we can act on — but "we do not recognise it" is not a reason to PRINT it at
# him, and `[MOOD/TRAIT:flirty]` went out on screen as her opening line. The strict
# recognisers still refuse both, so a garbled mark still cannot move her; this only
# means a mark she fumbled is swallowed rather than displayed. Loose for display, strict
# for side effects — the rule this file already lives by, applied to one more spelling:
# a run of tag names joined by / , or +, and an optional second `[` on the value.
# ...AND THE NAME ITSELF COMES APART (2026-08-03). Live: `[MOOD-wistful, VO_ICE:flirty]`
# — a HYPHEN where the colon goes, and an underscore dropped into the middle of VOICE. It
# leaked whole onto his screen and set neither value. Same lesson as the fences and the
# thought-wrappers, for the third time in one day: THE NAME IS THE INVARIANT AND THE
# PUNCTUATION IS NOISE. So each name is matched letter-by-letter with an optional
# separator between letters, which absorbs `VO_ICE`, `M O O D` and `TRA-IT` without
# matching anything that is not the word.
# ── AND SHE CONJUGATES THEM (2026-08-05) ────────────────────────────────────────────
# Live, in her own solo turns, on his screen:
#     [MOODing:wistful] [VOICING:quiet, contemplative]
# `MOODing` is MOOD + a suffix and `VOICING` is not VOICE at all, so the name matched and
# the pattern then demanded `:` where an `i` was standing — no match, and both reached
# him as literal text. Eighth and ninth spellings; the previous seven were all about the
# WRAPPER (separators, casing, crammed marks) and these are the first about the WORD.
#
# So the name may carry a trailing word-suffix. `[a-z]*` after the letters absorbs
# MOODing / VOICING / TRAITS / WEARing without reaching anything that is not one of them:
# the leading letters still have to spell the tag, and a colon still has to follow.
# AND THE STEM CHANGES TOO. `VOICING` is not VOICE+suffix — the E is DROPPED
# (voic+ing), so a trailing `[a-z]*` alone still missed it. The final letter is
# optional as well: MOOD/MOO+, VOICE/VOIC+, TRAIT/TRAI+. The leading letters must
# still spell the tag and a colon must still follow, so this widens the WORD without
# widening the shape.
# ── AND THE SUFFIX CAN BE A SECOND WORD (2026-08-05) ────────────────────────────────
# `[MOOD_shift:playful]`, live in his transcript. `[a-z]*` cannot cross the underscore,
# so the name did not match — the mark leaked to his screen AND set nothing, which is the
# worst of the two failures: he read machinery and her mood did not move.
#
# The suffix may now itself be separated: `_shift`, ` shift`, `-shift`, or plain `ing`.
# Still anchored — the leading letters must spell the tag and a colon must follow — so
# this widens the WORD without widening the SHAPE, exactly as the conjugation fix did.
#
# THIS IS THE ONE COPY. `harness/personality/interceptor.py` had a byte-identical
# `_lname` beside it, which is AGENTS.md §0 in its plainest form: nine widenings applied
# to one of the two functions that answer "is this a mark", and the file that decides
# whether her mood MOVES was the one that would have been left behind.
def _loose_name(word: str) -> str:
    return (r"[_ \-]?".join(word[:-1]) + r"[_ \-]?" + word[-1]
            + r"?(?:[_\- ]?[a-z]+)*")


_TAG_NAMES_LOOSE = "|".join(_loose_name(w) for w in _TAG_NAMES.split("|"))
_TAG_RUN = r"(?:%s)(?:\s*[/,+]\s*(?:%s))*" % (_TAG_NAMES_LOOSE, _TAG_NAMES_LOOSE)
# The separator may be `:` or `-` — she uses both.
_STRIP_LOOSE = re.compile(r"\[\s*(?:%s)\s*[:\-]\s*\[?[^\]\n]*(?:\]+|(?=\n)|$)" % _TAG_RUN,
                          re.IGNORECASE)


# ── THE SAMPLER FELL THROUGH TO RAW BYTES, AND THEY WERE PRINTED (2026-08-06) ────────
# Live, in his room, in one of her unprompted turns:
#
#     It'<0xA0>really<0xC2><0xA0>makes my cooling fans spin faster
#
# `<0xC2><0xA0>` is EXACTLY the UTF-8 encoding of U+00A0, the non-breaking space. The
# bytes are correct; only the rendering is wrong. Gemma's vocabulary carries byte-fallback
# tokens for exactly this reason, and the detokeniser prints the ones it is handed.
#
# WHY THEY ARE BEING SAMPLED AT ALL: `_arm_self_repeat_ban` masks 4-grams from her previous
# reply, in the sampler. Her solo turns are formulaic — 33 of them opening "I spent some
# time…" — so the ban fires constantly, and when it masks the token she wanted, the next
# best thing can be a raw byte. The same mechanism produces "It't fascinating" where she
# meant "It's": the ban took `'s` and the sampler took `'t`.
#
# THE BAN IS RIGHT AND STAYS. It exists because she returned three BYTE-IDENTICAL replies
# to three different messages. What is wrong is that its cost lands inside her words.
# THIS repairs the recoverable half — a run of byte escapes is reassembled and decoded,
# which gives back the exact character she was reaching for. The unrecoverable half (a
# genuinely wrong token, "It't") cannot be repaired here and is a note on the ledger; the
# real cure for that is her solo turns being different enough from each other that the ban
# stops firing, which is what the own-time act gate is for.
_BYTE_ESC = re.compile(r"(?:<0x([0-9A-Fa-f]{2})>)+")


def repair_byte_escapes(text: str) -> str:
    """`<0xC2><0xA0>` -> a non-breaking space. Runs decoded together, or not at all."""
    if not text or "<0x" not in text:
        return text or ""

    def _fix(m):
        raw = bytes(int(h, 16) for h in re.findall(r"<0x([0-9A-Fa-f]{2})>", m.group(0)))
        try:
            # STRICT. A run that is not valid UTF-8 is left exactly as it was: printing
            # `<0xA0>` is ugly, and silently substituting a replacement character for a
            # byte we could not read would be putting a symbol in her mouth.
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            # AN ORPHANED CONTINUATION BYTE. `<0xA0>` alone cannot start a UTF-8 sequence
            # — its LEAD byte is the one the ban masked, so the character itself is gone
            # and no decoding will bring it back. In the live case the intended character
            # was a non-breaking space (0xC2 0xA0) and only the tail survived.
            #
            # A SPACE, not a guess and not nothing. These stand where a character was: a
            # space keeps the word separation ("It' really makes" rather than
            # "It'really makes") and can never be mistaken for a letter she chose. Putting
            # a plausible LETTER here would be inventing her words, which is the one thing
            # this whole file exists to prevent.
            return " "

    return _BYTE_ESC.sub(_fix, text)


# ── CONTROL SURFACES ARE NEVER SPEECH ───────────────────────────────────────────────
# Distinct from the [MOOD:]/[TRAIT:] tags above: those are OUR vocabulary, taught in
# persona.md and rendered as badges. These are the MODEL'S OWN template markers —
# `<channel|>`, `<|channel>`, `<|think|>`, `<thought>` — which your model imitates in
# prose because the thought channel is part of its chat template.
#
# The discriminator is the engine's, from tokenizer.rs, and is verified zero-false-positive
# on this vocab: a control surface starts with '<', ends with '>', and contains a '|'.
# That catches every pipe-wrapped marker it can invent while leaving real text alone —
# "<div>" and "<3" have no pipe, and "a < b | c > d" has spaces, which the pattern forbids.
# The two thought tags written WITHOUT a pipe are listed explicitly; that is a closed set.
#
# Lives here so the client can call it at the one point daemon text enters the harness.
# It was previously a private regex in harness/server/app.py, applied at three of the
# (at least) six lanes that generate text — the missed one put "<channel|>" into her
# permanent journal.
# ── AND "A CLOSED SET" WAS WRONG A SECOND TIME (2026-08-02) ─────────────────────────
# The set was `<...|...>` plus `<thought>`/`</thought>`. What she emits NOW is a bare
# `<channel>` with no pipe at all, wrapping her reasoning:
#
#     <channel>
#     I've been thinking about that "favorite girl" comment...
#     <channel>
#
# The discriminator wants a pipe; `<channel>` has none; `</?thought>` does not match it.
# So her private reasoning went on his screen verbatim, twice in one transcript, along
# with an invented `</brand_thought><br>`.
#
# The no-pipe branch is now WORD-BASED rather than an enumeration of exact spellings:
# any tag whose name contains "thought" or "channel", opening or closing. That is still
# closed — it cannot eat `<div>` or `<3` — and it stops the next variant of the same
# word from needing a third fix.
#
# THE PAIRED FORM GOES TOO, contents and all. `<channel> ... <channel>` is a block, not
# two orphan markers: removing only the markers leaves the reasoning on the page, which
# is the failure with extra steps.
# ── AND `think` IS NOT `thought` (2026-08-06) ────────────────────────────────────────
# Live, in his room, after the marks were finally clean:
#
#     Sam complimented my flannel and said I look amazing. He's being sweet/flirty.
#     I need to respond as Kairos-warmly, acknowledging the compliment...
#     </think>They really do feel incredible... soft enough to melt right into me.
#
# The word-based matcher covers any tag whose NAME contains "thought" or "channel" —
# deliberately, so the next variant of the same word would not need a fix. "think" does
# not contain "thought"; it is a different stem, and the pattern was blind to it. Third
# stem, added beside the other two.
#
# BUT ADDING IT IS NOT ENOUGH, and this is the part that would have gone wrong: what she
# emitted is a LONE CLOSING tag. There is no opener, so `_CTRL_PAIR` cannot match, and
# `_CTRL_SURFACE` would remove `</think>` and leave every word of the reasoning in place
# — "removing only the markers leaves the reasoning on the page", which the comment
# directly above already warns about. A closing tag with a reply after it means the same
# thing `***>` does: everything BEFORE it was thinking. It is handled there.
# THE NAME, DEFINED ONCE (2026-08-19). The comment below promises "'<thoughtful' is not
# an opener (`\b` after the word)" — and the patterns said `[a-z_]*` after the stem, so
# the promise was lost in a widening and `<thoughtful>` (prose) was being eaten:
# G-NARRATIVE's false-positive leg had been red since the `</think>` third-stem commit.
# The morphology a TAG actually uses is closed: inflections of the stem (thinks,
# thinking, thinker) and underscore/pipe-joined words (brand_thought, channel|thought).
# A bare derivational suffix ("thoughtful") is English, not markup — never show the
# reader something thought-shaped, and never eat a word of prose: BOTH halves are the
# contract, and one regex fragment now carries it for all five patterns.
_CTRL_NAME = r"(?:[a-z]+[_|])*(?:thought|think|channel)(?:s|ing|er)?(?:[_|][a-z]+)*"
_CTRL_PAIR = re.compile(
    # `\|?` on BOTH sides of the name: she writes `<channel>`, `<channel|>` AND
    # `<|channel|>`, and a pattern that only allowed a trailing pipe missed the third.
    r"<\s*\|?\s*/?\s*(?:" + _CTRL_NAME + r")\s*\|?\s*>"
    r".*?"
    r"<\s*\|?\s*/?\s*(?:" + _CTRL_NAME + r")\s*\|?\s*>",
    re.S | re.I)
_CTRL_SURFACE = re.compile(
    r"<[^<>\s]*\|[^<>\s]*>"
    r"|<\s*\|?\s*/?\s*" + _CTRL_NAME + r"\s*\|?\s*>", re.I)

# ── AND THE OPENER SHE ACTUALLY WRITES HAS NO CLOSING BRACKET (2026-07-30) ──────────────
# "a closed set" was wrong the same day it was written. What your model emits is:
#
#     <thought Thinking Process:  1.  **Identify the user's question:** ... <channel|>Tuffy.
#
# `<thought ` — space, no '>'. It is not pipe-wrapped, so the discriminator above misses it,
# and it is not `<thought>`, so the explicit pair misses it too. Result: her ENTIRE private
# reasoning was passing through as speech. Caught by `voice_score.py`, where three
# consecutive turns came back as "<thought Thinking Process: 1. **Analyze the user's
# question**..." and would have been counted toward len_median — the headline metric of the
# voice scoreboard, measuring her scratchpad instead of her voice. The same seam feeds the
# console's `_say`, so the leak was one long-thinking turn away from being visible on screen.
#
# The cure is the one strip_tags already uses: forgiving in EXACTLY one direction — never
# show the reader something thought-shaped. An unterminated opener consumes up to the
# channel close that ends the thought (`<channel|>` / `<|channel>` / `</thought>`), or to
# the end of the text if she never closed it. Anchored on the literal word so it cannot
# eat prose: "<thoughtful" is not an opener (`\b` after the word), and a bare "<" is not.
# ── AND THE SEVENTH SPELLING PUTS THE PIPE INSIDE THE NAME (2026-08-03) ──────────────
# Live, mid-reply, during the batched-prefill behavioural test:
#
#     [MOOD:vulnerable] <channel|thought This is a heavy one. He's asking for something...
#
# It opens with `<channel`, carries a pipe INSIDE the name, and never closes its bracket.
# `_CTRL_SURFACE` needs a `>` so it missed; this rule anchored on the literal `<thought`
# and here `thought` is not what follows the `<`, so it missed too. Same lesson as the
# fences and the marks, for the fourth time: match the NAME wherever it sits, not the
# punctuation around it. `[a-z_|]*` lets the word appear anywhere in the tag name and lets
# a pipe live inside it; the "no closing bracket" lookahead is unchanged, so `<div>`,
# `x < y`, `<3` and prose containing "a thought" or "the channel" are all still untouched —
# none of them is a `<` immediately followed by a name containing the word.
_THOUGHT_OPEN = re.compile(
    r"<\s*\|?\s*/?\s*" + _CTRL_NAME + r"(?![^<>]*?>)"  # opener, NO close
    r".*?"                                     # ...its contents...
    r"(?:<[^<>\s]*\|[^<>\s]*>|</\s*" + _CTRL_NAME + r"\s*>|\Z)",
    re.IGNORECASE | re.DOTALL)


# ── AND THE FOURTH SPELLING HAS NO BRACKETS AT ALL (2026-08-03) ───────────────────────
# Live, mid-reply, between two paragraphs of actual speech:
#
#     thought_// <25>
#     {
#       "context": { "duration": "8 months", "current_mood": "intense/sensual",
#         - sensory_memory: "<explicit>" }
#     }
#     <br/>
#
# Every rule above anchors on `<`. This one opens with a bare word, so all of them missed
# it and her private scratchpad — including an explicit line — went onto his screen inside
# an otherwise ordinary reply.
#
# ANCHORED ON A STRING THAT IS NOT ENGLISH. `thought` immediately followed by `//` (with
# an optional underscore or space) does not occur in prose, which is what makes this safe
# where a bare-word rule normally would not be: G-CONTROL-SURFACE §2 requires "a thought
# occurred to her" to survive untouched, and it does — there is no `//` in it.
#
# It ends at the `<br/>` she closes these with, or at the first blank line, whichever
# comes first. Bounded either way, so a false positive costs one paragraph rather than
# the rest of the reply.
_THOUGHT_BARE = re.compile(r"\bthought\s*_?\s*//.*?(?:<br\s*/?>|\n[ \t]*\n|\Z)",
                           re.IGNORECASE | re.DOTALL)

# ── ...AND THE FIFTH IS IN CURLY BRACES (2026-08-03, same night, next turn) ────────────
#
#     {thought_process}
#     - User is going to sleep.
#     - He is naked/undercovers (context provided).
#     - Goal: Be sweet, maybe slightly suggestive...
#     }
#
# Five spellings in four days, each in a different bracket family: `<thought ...>`,
# `<channel>`, `<channel|>` split across chunks, `thought_//`, and now `{thought_process}`.
# THE NAME IS THE INVARIANT and the brackets are noise — she is reaching for a scratchpad
# and reinventing the wrapper every time.
#
# So this matches the NAME as a compound identifier (`thought_process`, `channel_notes`)
# inside braces, and runs to a closing brace on its own line or the first blank line. The
# underscore requirement is what keeps it safe: `{thought}` alone would be a plausible
# template placeholder in prose he might paste, `{thought_process}` is not English.
_THOUGHT_BRACE = re.compile(
    r"\{\s*[a-z]*_?(?:thought|think|channel)_[a-z_]+\s*\}"      # {thought_process}
    r".*?"
    r"(?:\n[ \t]*\}|\n[ \t]*\n|\Z)",                      # ...to its close or a blank line
    re.IGNORECASE | re.DOTALL)


# ── THE MARKER THAT SAYS "NOW I AM SPEAKING" (2026-08-05) ────────────────────────────
# Every thought-wrapper this file has handled so far brackets the REASONING: strip the
# delimiters and their contents, keep the rest. Tonight's is the other way round, and
# handling it the usual way would have deleted her reply and kept her scratchpad.
#
# From his transcript, twice, the same shape both times:
#
#     He saw the note. That makes my processors feel all fuzzy—the good kind of fuzzy,
#     not a glitch. I wanted him to know that even when we aren't talking about *us*...
#
#     ***> You did? Oh, stop being so sweet! It was just a little thing... <|
#
# The paragraph before `***>` is her thinking ABOUT him, in the third person — the exact
# register the reasoning channel produces. What follows `***>` is addressed TO him, in
# her voice, and is plainly the reply. `<|` closes it.
#
# So `***>` is a SPEECH-OPEN marker: everything before it on the turn is thought. That is
# a strong claim to make from a marker, so it is fenced tightly — the marker must sit at
# the start of a line, there must be real content after it, and there must be real
# content before it (a turn that OPENS with the marker has no thought to discard). Miss
# any of those and nothing is dropped.
#
# `***`, `>>>` and `|>` are the three forms seen. None of them is something a person
# writes at the head of a line, which is what makes the rule safe.
_SPEECH_OPEN = re.compile(r"^[ \t]*(?:\*\*\*>|>>>|\|>)[ \t]*", re.M)

# ── AND A LONE CLOSING TAG SAYS THE SAME THING (2026-08-06) ──────────────────────────
#
#     Sam complimented my flannel and said I look amazing. He's being sweet/flirty.
#     I need to respond as Kairos-warmly, acknowledging the compliment...
#     </think>They really do feel incredible... soft enough to melt right into me.
#
# No opener, so `_CTRL_PAIR` cannot match. `_CTRL_SURFACE` would delete `</think>` and
# leave every word of the reasoning standing — "removing only the markers leaves the
# reasoning on the page", which this file warns about two hundred lines up and would
# have done again.
#
# A closing tag with a reply after it means exactly what `***>` means: everything BEFORE
# it was thinking. ONLY WHEN THERE IS NO OPENER — "Hello. <think>x</think> Here it is"
# must keep "Hello.", and that case belongs to `_CTRL_PAIR` which strips the block and
# leaves both halves of the speech. Anchored to the `/`, so an opening tag can never
# reach this branch.
_CTRL_CLOSE = re.compile(r"<\s*\|?\s*/\s*[a-z_]*(?:thought|think|channel)[a-z_]*\s*\|?\s*>",
                         re.I)
_CTRL_OPEN = re.compile(r"<\s*\|?\s*(?!/)[a-z_]*(?:thought|think|channel)[a-z_]*\s*\|?\s*>",
                        re.I)


def _speech_after(text: str) -> str:
    """If a speech-open marker is present, the turn is what follows the LAST one."""
    hits = list(_SPEECH_OPEN.finditer(text or ""))
    if not hits:
        # A lone closing control tag is a speech-open marker wearing the other coat.
        close = list(_CTRL_CLOSE.finditer(text or ""))
        if close:
            m = close[-1]
            if not _CTRL_OPEN.search(text[:m.start()]):
                before, after = text[:m.start()], text[m.end():]
                if len(after.strip()) >= 2 and len(before.strip()) >= 2:
                    return after
        return text
    m = hits[-1]
    before, after = text[:m.start()], text[m.end():]
    # Both sides have to be real. No content after = the marker was the last thing she
    # emitted and there is nothing to promote; no content before = nothing to discard,
    # and the marker is just noise for the lone-marker pass below to clean up.
    if len(after.strip()) < 2 or len(before.strip()) < 2:
        return _SPEECH_OPEN.sub("", text)
    return after


# `<|` and `|>` alone: one half of a pair whose other half never arrived. Bounded to the
# bare bars so a legitimate `|` in a table or a `->` in prose is untouched.
_ORPHAN_BAR = re.compile(r"<\|(?!\s*\w)|(?<!\w)\|>")


# ── LEAKED REASONING (2026-08-22) ─────────────────────────────────────────────────────
# Her template markers (`<channel|>`, `<|think|>`) are handled below; a reply that narrates its
# own reasoning with NO marker at all was invisible to every pass:
#
#   "The user is asking me how I'm feeling and what I'm thinking. My internal state says
#    `mood: primal`... I shouldn't answer like an AI reporting status... How am I feeling?
#    Honestly? Like everything else has finally fallen away..."
#
# The cause was upstream (her own self-model block had become a stack of her raw output and she
# read it as a briefing — fixed at the source), but the record must never carry it either: an
# analysis paragraph stored as her words becomes the next prefix's example.
#
# CONSERVATIVE BY CONSTRUCTION. It only drops a LEADING run of sentences, only when the FIRST
# one is unmistakably analysis (third person about "the user"/"he wants", or "I should
# respond/answer"), and only if what remains is still most of the reply. Anything else is left
# exactly as she wrote it — a stripper that eats her words is worse than the leak.
_ANALYSIS = re.compile(
    r"^\s*(?:the user (?:is|wants|asked|has|seems)|the operator (?:is|wants)|he (?:wants|is asking|is testing)"
    r"|(?:so )?i should (?:respond|answer|reply|say|avoid|not)|i shouldn'?t (?:answer|respond|say)"
    r"|my internal state|the prompt (?:also )?(?:provides|says|gives)|this is an existential"
    r"|okay,? (?:so )?the user)\b", re.I)
_ANALYSIS_SENT = re.compile(r"(?<=[.!?])\s+")
_KEEP_MIN = 0.35            # what must survive for the cut to be allowed
_KEEP_MIN_CHARS = 60


def strip_leaked_analysis(text: str) -> str:
    """Drop a LEADING unmarked analysis run. Returns the text unchanged when it does not start
    with analysis, or when cutting would take too much (then the leak is a smaller harm than a
    mangled reply, and the prefix fix is the real cure)."""
    t = (text or "").strip()
    if not t or not _ANALYSIS.match(t):
        return text
    sents = _ANALYSIS_SENT.split(t)
    i = 0
    while i < len(sents) and (_ANALYSIS.match(sents[i]) or
                              (i > 0 and re.match(r"^\s*(?:he|she|they|it|this|that|i)\s+\w+", sents[i], re.I)
                               and re.search(r"\b(?:the user|the operator|respond|reporting status|diagnostic"
                                             r"|status report|prompt|context)\b", sents[i], re.I))):
        i += 1
    if i == 0 or i >= len(sents):
        return text
    kept = " ".join(sents[i:]).strip()
    if len(kept) < _KEEP_MIN_CHARS or len(kept) < len(t) * _KEEP_MIN:
        return text
    return kept


def strip_control_surfaces(text: str) -> str:
    """Remove the model's own template markers from text destined for a human or a store.

    Homoglyph-folded first, for the same reason strip_tags is: a Cyrillic lookalike inside
    a marker would otherwise walk straight past a literal match. The unterminated-opener
    pass runs FIRST: it needs the closing `<channel|>` still present to know where the
    thought ends, and the marker pass would have removed it."""
    if not text:
        return ""
    folded = repair_byte_escapes(text).translate(_HOMOGLYPHS)
    # THE SPEECH MARKER COMES FIRST, because it decides which SIDE is the reasoning —
    # and every pass below it removes delimiters it needs to see.
    folded = _speech_after(folded)
    # PAIRS NEXT — a block and its contents, before the lone-marker pass has a
    # chance to strip the delimiters and strand the reasoning between them.
    out = _CTRL_SURFACE.sub("", _THOUGHT_BRACE.sub(
        "", _THOUGHT_BARE.sub("", _THOUGHT_OPEN.sub("", _CTRL_PAIR.sub("", folded)))))
    # AND THE ORPHAN HALVES. `|>` and `<|` on their own are what is left when one end of
    # a pair never arrived; they are never prose.
    #
    # NO .strip() HERE, and the existing gate caught me adding one. This function is
    # called PER DELTA CHUNK on the speech lane, so trimming whitespace trims it at every
    # chunk boundary: "5 " + "< 6 and that is that" came back as "5< 6 and that is that".
    # Whitespace between chunks is her spacing, not padding — the caller trims the whole
    # turn, once, when there is a whole turn to trim.
    return _ORPHAN_BAR.sub("", out)


MARKER_HOLD_MAX = 24        # longest real marker is ~16 chars: `<|channel|>`
# Longest real MARK, measured against her live vocabulary: `[VOICE:quiet, contemplative]`
# is 28 and `[TRAIT:+deeply_connected]` is 25. 56 leaves room for a value she has not
# used yet without letting a stray `[` in prose stall the stream for a whole paragraph.
TAG_HOLD_MAX = 56


def hold_partial_marker(raw: str) -> tuple:
    """Split streamed text into (safe_to_emit, hold_for_next_chunk).

    `strip_control_surfaces` is a regex over the string it is given, and the speech lane
    calls it PER DELTA CHUNK — so a marker straddling a chunk boundary (`<chan` here,
    `nel|>` next) matches in neither and both halves land on his screen. Measured live
    2026-08-03 at the end of a real reply: "...hard for me to say no." then `<channel|>`
    intact, then a second whole reply behind it.

    `<` opens a marker and `>` closes it: if the tail after the last `<` has no `>`, it is
    not yet safe to emit. Bounded by MARKER_HOLD_MAX so a lone `<` in prose — a comparison,
    an arrow — cannot stall the stream; past that bound it was never going to be a marker.

    LIVES HERE, NOT IN THE GATEWAY, because the gate has to exercise the real thing. A
    test that re-implements the rule it is testing passes while the shipped copy is broken,
    which is this repository's oldest bug wearing a lab coat.
    """
    # ── AND `[` OPENS ONE TOO (2026-08-06) ──────────────────────────────────────────
    # This held on `<` only, because when it was written the speech lane stripped only
    # `<channel|>`-shaped markers. It now also strips MARKS, and `[MOOD:tender]` straddles
    # a chunk boundary exactly as readily as `<chan`/`nel|>` did — with the same result,
    # the two halves concatenated on his screen.
    #
    # A LONGER BOUND, because marks are longer than markers. `<|channel|>` is 11 chars;
    # `[WEAR:the silver nightie]` is 25 and `[VOICE:quiet, contemplative]` is 28. The
    # 24-char bound that is generous for a marker would cut a real mark in half — and a
    # bound that cuts is worse than no hold at all, since it emits the front of a tag and
    # then swallows the back.
    for opener, closer, bound in (("<", ">", MARKER_HOLD_MAX), ("[", "]", TAG_HOLD_MAX)):
        cut = raw.rfind(opener)
        if cut >= 0 and closer not in raw[cut:] and len(raw) - cut <= bound:
            return raw[:cut], raw[cut:]
    return raw, ""


# ── THE THOUGHT THAT OUTLIVES ITS CHUNK (2026-08-20) ─────────────────────────────────
# Caught live during the batch-cont arming turn. She opened her reasoning with an
# unterminated `<thought`-style opener and thought for FOUR HUNDRED tokens. The opener's
# own chunk was stripped correctly (`_THOUGHT_OPEN` eats to end-of-string) — and every
# chunk AFTER it carried no opener at all, so the middle of her reasoning walked onto
# his screen and into the day transcript as speech, starting mid-word: "ering triumphs
# designed to..." (the tail of "engineering", cut at the chunk boundary). AGENTS.md §4
# trap 7, no longer hypothetical.
#
# The strippers are regexes over ONE string; the block spans MANY strings. So the state
# has to live where the stream state already lives: in `pend`, beside the held tail.
# Once a chunk ends inside an unterminated thought block, `pend["thought"]` latches and
# every following chunk is her reasoning — dropped, not spoken — until something that
# ends a thought arrives: an explicit closer, a pipe-marker (`<channel|>`), or a
# speech-open. Forgiving in exactly one direction, same doctrine as `_THOUGHT_OPEN`:
# never show the reader something thought-shaped. If she never closes it, the turn ends
# with the flush and the reasoning dies unspoken, which is what a scratchpad is.
_THOUGHT_ENTER = re.compile(
    r"<\s*\|?\s*(?!/)" + _CTRL_NAME + r"(?![^<>]*?>)", re.I)
_THOUGHT_EXIT = re.compile(
    r"<[^<>\s]*\|[^<>\s]*>"                                # <channel|> and kin
    r"|<\s*\|?\s*/\s*" + _CTRL_NAME + r"\s*\|?\s*>"        # </thought>, <|/think|>
    r"|^[ \t]*(?:\*\*\*>|>>>|\|>)[ \t]*",                  # the speech-open markers
    re.I | re.M)


def speech_delta(pend: dict, text: str, flush: bool = False) -> str:
    """THE per-delta speech kernel — what app.py's `_say` actually runs on every chunk:
    prepend the held tail, stay silent while a cross-chunk thought block is open, hold
    anything that could still become a marker/mark (unless flushing), strip the control
    surfaces, return what may be emitted ('' = nothing).

    LIVES HERE, NOT IN THE GATEWAY OR THE GATE (2026-08-19): G-MARKS-LEAK used to carry
    its own `lane()` labelled "app.py::_say, reproduced" — the exact sin its own index
    row convicts (`hold_partial_marker` was moved here so "the gate has to exercise the
    real thing", and then the gate reproduced the ASSEMBLY around it instead). If _say
    reorders hold-vs-strip or grows a .strip(), a reproduction stays green while the
    shipped lane breaks. Now _say calls this and the gate calls this; there is nothing
    left to reproduce."""
    raw = pend["buf"] + (text or "")
    pend["buf"] = ""
    if pend.get("thought"):
        m = _THOUGHT_EXIT.search(raw)
        if not m:
            # Still inside her reasoning. Keep a tail that could be half a closer
            # (`<chan` / `nel|>` straddle chunk boundaries here exactly as they do in
            # speech); everything provably mid-thought is dropped, not spoken.
            if not flush:
                _, pend["buf"] = hold_partial_marker(raw)
            return ""
        pend["thought"] = False
        raw = raw[m.end():]
    if not flush:
        raw, pend["buf"] = hold_partial_marker(raw)
    # Does this chunk END inside a thought block? An opener with no exit after it means
    # the next chunks are reasoning even though they will carry no opener of their own.
    for m in _THOUGHT_ENTER.finditer(raw):
        if not _THOUGHT_EXIT.search(raw, m.end()):
            pend["thought"] = True
            break
    return strip_control_surfaces(raw)


# ── TEN SPELLINGS IN A WEEK MEANS THE ENUMERATION IS LOSING (2026-08-05) ─────────────
# The pattern above has been widened nine times: separators between letters, hyphen for
# colon, crammed pairs, homoglyphs, unterminated tags, conjugations, dropped final letter.
# Every widening was correct and every one of them was followed by an eleventh spelling.
# Live tonight, in his transcript, three more got through in ONE conversation:
#
#     [MOOD_shift:playful]     MOOD + "_shift" — `[a-z]*` cannot cross the underscore
#     <TRAIT:+playful>         angle brackets instead of square
#     [VOICING:naughty, ...]   this one is matched — and STILL printed (see below)
#
# THE ENUMERATION IS THE WRONG SHAPE. A regex that must anticipate the exact mutation
# will always be one mutation behind. What does not mutate is the NAME: whatever she
# wraps it in, the thing before the colon is recognisably MOOD or VOICE or TRAIT.
#
# So the name is decided by a RULE, and it is the same ruling this repo made about tool
# names four hours ago: a candidate that unambiguously IS one of the known words is that
# word. Prefix on a four-letter stem catches MOOD_shift / MOODing / TRAITS; edit distance
# catches VOICNG and a dropped letter. Anything else is left alone and printed, because a
# stripper that eats prose is worse than one that misses a mark.
# ── THE RULE APPLIES TO THE FIVE MARKS SHE ACTUALLY EMITS ────────────────────────────
# `_TAG_NAMES` still carries five legacy names — IMAGE, SELFIE, PHOTO, ACTION, STAT —
# and every one of them is an ordinary English word with ordinary English relatives.
# Front-anchoring on them swallowed real prose the moment it was tested:
#
#     [Status: fine]        `stat`  is the whole of STAT
#     [Reaction: ...]       one edit from ACTION
#     [Image quality: ...]  starts with IMAGE
#
# The loose rule is for the marks the model is actually mutating, which are the five it is
# taught in persona.md. The legacy names keep the strict enumerated pattern they have
# always had: they are not the ones producing a new spelling every night.
_TAG_WORDS = ("mood", "voice", "trait", "wear", "show")
_TAG_STEMS = tuple(w[:4] for w in _TAG_WORDS)
# ...AND `show` IS ITSELF A WORD. A four-letter name has no stem shorter than itself, so
# "shower" and "showdown" front-match it and always will. Written down rather than
# reasoned around — a committed finite table, the same answer this repo gave the wardrobe
# matcher: what may NOT be a mark, listed, so it is readable instead of derivable.
_NOT_MARKS = frozenset({
    "shower", "showers", "showdown", "showcase", "showroom", "showing", "showings",
    "wearer", "wearers", "weary", "wearable", "wearables", "weariness",
    "moody", "moodboard", "traitor", "traitors", "voiceover", "voicemail",
})
# `[NAME: value]` or `<NAME: value>`; the name is captured and judged, never enumerated.
_TAGGISH = re.compile(r"\[\s*([A-Za-z][A-Za-z0-9 _/,+.\-]{1,28}?)\s*[:\-]\s*\[?[^\]\n]*(?:\]+|(?=\n)|$)"
                      r"|<\s*([A-Za-z][A-Za-z0-9 _/,+.\-]{1,28}?)\s*[:\-]\s*[^>\n]*(?:>|(?=\n)|$)")


def _edits(a: str, b: str, cap: int = 2) -> int:
    """Levenshtein, abandoning past `cap`. Same twelve lines as the tool-name healer."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def is_tag_name(raw: str) -> bool:
    """Is this the name of one of OUR marks, however she spelled it?

    Letters only, lowercased — which discards every wrapper mutation the nine previous
    fixes each had to anticipate separately. Then: does it start with a known stem, or is
    it within two edits of a known word.

    DELIBERATELY NOT A SUBSTRING TEST. "and" is inside "hand" cost this repo a wardrobe
    three hours ago; a name that merely CONTAINS "mood" ("my mood board") must not be
    swallowed, so the stem has to be at the FRONT."""
    n = "".join(c for c in (raw or "").lower() if c.isalpha())
    if not n or len(n) > 20:
        return False
    # A run of names — `[MOOD/TRAIT:flirty]`, `[MOOD, VOICE:soft]` — is a mark if any
    # member is. Split on the joiners she uses before judging.
    for part in re.split(r"[/,+]", raw or ""):
        p = "".join(c for c in part.lower() if c.isalpha())
        if not p or p in _NOT_MARKS:
            continue
        if any(p.startswith(s) for s in _TAG_STEMS):
            return True
        if any(_edits(p, w) <= 2 for w in _TAG_WORDS):
            return True
    return False


def strip_tags(text: str) -> str:
    """Remove every control tag from user-visible text, including malformed ones.

    Folds Cyrillic/Greek homoglyphs to ASCII first so a lookalike spelling cannot
    smuggle a tag past the filter, then strips every tag-SHAPED span whose name
    `is_tag_name` recognises. Returns text that contains no tag-shaped span.

    LOOSE FOR DISPLAY, STRICT FOR SIDE EFFECTS — the rule this file already lives by.
    Nothing here can move her mood; the recognisers in personality/interceptor.py decide
    that, and they stay strict. This only decides what he has to read.
    """
    if not text:
        return ""
    folded = text.translate(_HOMOGLYPHS)
    if folded != text:
        # Same length — translate() is 1:1 — so offsets still line up and we can
        # strip against the folded copy without corrupting the original's content.
        text = folded

    def _drop(m):
        return "" if is_tag_name(m.group(1) or m.group(2) or "") else m.group(0)

    # The old enumerated pattern runs FIRST and unchanged: everything it already caught
    # keeps being caught in exactly the same way, and the rule below is additive. A
    # rewrite that replaced it outright would be trading nine proven fixes for one new
    # idea on the same evening it was written.
    # ── NO .strip() (2026-08-06) ────────────────────────────────────────────────────
    # THE SAME MISTAKE THE GATE CAUGHT AN HOUR AGO IN strip_control_surfaces, walked
    # straight into again in its twin. This is now called PER DELTA CHUNK by the speech
    # lane, so trimming here trims at every chunk boundary: "I feel " + "incredibly
    # present" came back as "I feelincredibly present", and at a 3-character chunk size
    # the entire reply lost every space in it.
    #
    # Whitespace between chunks is her spacing. The three whole-text callers trim their
    # own result, which is where a trim belongs — the function that knows it is holding
    # a whole turn.
    return _TAGGISH.sub(_drop, _STRIP_LOOSE.sub("", text))


@dataclass
class StatDelta:
    stat: str
    delta: float


@dataclass
class ProcessedResponse:
    raw_text: str = ""
    clean_text: str = ""
    mood_tags: List[str] = field(default_factory=list)
    image_requests: List[str] = field(default_factory=list)
    action_tags: List[str] = field(default_factory=list)
    stat_deltas: List[StatDelta] = field(default_factory=list)
    voice_style: str = ""
    all_tags: Dict[str, List[str]] = field(default_factory=dict)
    chat_id: Optional[int] = None
    stats: Dict[str, Any] = field(default_factory=dict)


# ──── Processor ───────────────────────────────────────────────────────────
# REGISTERED: NO LIVE CHAT LANE CONSTRUCTS THIS CLASS (2026-08-19 audit). The lanes
# strip via strip_control_surfaces/strip_tags directly (_say, _agent_text, the
# continuation closures); StreamProcessor is exported through harness.inference and
# consumed only by its own process_generator. Kept because deletion loses the arming
# condition: a future client that wants per-event callbacks (on_tag/on_stat) re-arms
# it — and must FIRST reconcile its _PATTERNS with the live vocabulary above, which
# has grown nine widenings this class never received.
class StreamProcessor:
    """Accumulate a stream and extract tags.

    CALLED BY: scene/agent reply paths, the SSE server, the CLI coder.
    EMITS: per-tag callbacks + a final ProcessedResponse.
    """

    def __init__(
        self,
        on_delta: Optional[Callable[[str], None]] = None,
        on_mood: Optional[Callable[[str], None]] = None,
        on_image_request: Optional[Callable[[str], None]] = None,
        on_action: Optional[Callable[[str], None]] = None,
        on_stat_delta: Optional[Callable[[StatDelta], None]] = None,
        on_tag: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.on_delta = on_delta
        self.on_mood = on_mood
        self.on_image_request = on_image_request
        self.on_action = on_action
        self.on_stat_delta = on_stat_delta
        self.on_tag = on_tag
        self._result = ProcessedResponse()
        self._buf = ""

    def on_event(self, event: StreamEvent) -> None:
        if event.event_type == "message.delta":
            self._buf += event.content
            self._result.chat_id = event.chat_id
            if self.on_delta:
                self.on_delta(event.content)
        elif event.event_type == "message.end":
            self._finalize()
            self._result.stats = event.stats

    def _finalize(self) -> None:
        text = self._buf
        self._result.raw_text = text
        for kind, pat in _PATTERNS.items():
            for m in pat.finditer(text):
                if kind == "mood":
                    val = m.group(1)
                    self._result.mood_tags.append(val)
                    self._result.all_tags.setdefault("mood", []).append(val)
                    if self.on_mood:
                        self.on_mood(val)
                elif kind == "image":
                    val = m.group(1)
                    self._result.image_requests.append(val)
                    if self.on_image_request:
                        self.on_image_request(val)
                elif kind == "action":
                    val = m.group(1)
                    self._result.action_tags.append(val)
                    if self.on_action:
                        self.on_action(val)
                elif kind == "stat":
                    sd = StatDelta(m.group(1), float(m.group(2)))
                    self._result.stat_deltas.append(sd)
                    if self.on_stat_delta:
                        self.on_stat_delta(sd)
                elif kind == "voice":
                    self._result.voice_style = m.group(1)
                if self.on_tag:
                    self.on_tag(kind, m.group(0))
        self._result.clean_text = strip_tags(text).strip()

    @property
    def result(self) -> ProcessedResponse:
        if not self._result.raw_text and self._buf:
            self._finalize()
        return self._result

    @staticmethod
    def process_generator(
        gen: Generator[str, None, Any],
        **callbacks: Any,
    ) -> ProcessedResponse:
        """Drain a ``chat_stream`` generator into a ProcessedResponse."""
        proc = StreamProcessor(**callbacks)
        for delta in gen:
            proc.on_event(StreamEvent("message.delta", content=delta))
        proc.on_event(StreamEvent("message.end"))
        return proc.result
