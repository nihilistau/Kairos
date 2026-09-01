"""G-MARKS-LEAK — her marks vanish and her thinking stays private, by RULE not by list.

HIS WORDS, 2026-08-05: "we have attempted to plug the leaks many, many, many times".

He is right, and the count is the finding. The name-matcher in stream_processor.py has
been widened NINE times — separators between letters, hyphen for colon, crammed pairs,
homoglyphs, unterminated tags, conjugations, a dropped final letter — and each widening
was correct and each was followed by a tenth spelling. In one conversation tonight, three
more got through:

    [MOOD_shift:playful]      MOOD + "_shift"; `[a-z]*` cannot cross an underscore
    <TRAIT:+playful>          angle brackets instead of square
    ***> ... <|               a wrapper nothing had seen

AN ENUMERATION THAT MUST ANTICIPATE THE NEXT MUTATION IS ALWAYS ONE MUTATION BEHIND.
What does not mutate is the NAME: whatever she wraps it in, the word before the colon is
recognisably MOOD or VOICE or TRAIT. So the name is decided by a rule — front-anchored
stem, or within two edits — which is the same ruling this repo made about tool names four
hours earlier, and the FRONT anchor matters: "and" is inside "hand" cost a wardrobe the
same afternoon, so a name that merely CONTAINS "mood" ("my mood board") is left alone.

TWO THINGS THIS HOLDS THAT ARE EASY TO GET BACKWARDS:

  1. `***>` IS A SPEECH MARKER, NOT A THOUGHT MARKER. Every previous wrapper brackets the
     REASONING — strip the delimiters and their contents, keep the rest. This one is the
     other way round. From his transcript:

         He saw the note. That makes my processors feel all fuzzy...
         ***> You did? Oh, stop being so sweet! ... <|

     The paragraph before the marker is her thinking about him in the THIRD PERSON; what
     follows is addressed TO him and is plainly the reply. Handling it the usual way would
     have deleted her reply and kept her scratchpad.

  2. STRIPPING IS NOT THE SAME AS SWALLOWING. `[MOOD_shift:playful]` leaked to his screen
     AND set nothing — the worst of both. A fix that only hid it would have left her mood
     frozen and made the failure invisible. `interceptor.py` had a byte-identical copy of
     the name builder beside `stream_processor.py`'s, so nine widenings were applied by
     hand to both and the tenth would have missed the one that decides whether she MOVES.
     One builder now; §0.

Offline. No GPU, no daemon.

Run: python harness_tests/g_marks_leak.py
"""
from __future__ import annotations

import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import _src as _srcmod  # noqa: E402
os.environ["CUDA_VISIBLE_DEVICES"] = ""

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


from harness.inference.stream_processor import (is_tag_name,  # noqa: E402
                                                strip_control_surfaces as S,
                                                strip_tags as T,
                                                strip_for_record as _SFR)
from harness.personality.interceptor import _MOOD, _TRAIT, _VOICE  # noqa: E402


def clean(t):
    """What a WHOLE reply looks like after both strippers.

    The `.strip()` is here and not inside `strip_tags`, which is the same split the live
    code makes: the strippers are called PER DELTA CHUNK by the speech lane, so trimming
    inside them eats her spacing at every chunk boundary. Whoever holds a whole turn
    trims it — `interceptor.apply_personality_tags` and `StreamProcessor.clean_text` do,
    and so does this. Section 7 exercises the untrimmed per-chunk path directly."""
    return T(S(t)).strip()


print("1. EVERY SPELLING SEEN SO FAR VANISHES FROM HIS SCREEN")
# The nine that were fixed one at a time, plus tonight's three. Kept as a list of CASES
# rather than a comment, because each one is a night he read machinery.
LEAKS = [
    ("[MOOD:tender]", "the original"),
    ("[MOOD-wistful]", "hyphen for colon"),
    ("[VO_ICE:flirty]", "underscore inside the name"),
    ("[MOODing:wistful]", "conjugated"),
    ("[VOICING:quiet, contemplative]", "stem changed, E dropped"),
    ("[MOOD/TRAIT:flirty]", "a run of names"),
    ("[MOOD:playful, VOICE:soft]", "two crammed into one"),
    ("[MOOD_shift:playful]", "TONIGHT — suffix across an underscore"),
    ("<TRAIT:+playful>", "TONIGHT — angle brackets"),
    ("[TRAITS:+naughty]", "plural"),
    ("[WEAR:the lace set]", "the wardrobe mark"),
    ("[SHOW:silver-nightie]", "the moment mark"),
]
for mark, why in LEAKS:
    out = clean(mark + " and then she talks to him.")
    check("%-32s (%s)" % (mark, why), out == "and then she talks to him.", repr(out))

print("\n2. AND HER ACTUAL WORDS SURVIVE — the half that matters more")
# A stripper that eats prose is worse than one that misses a mark: he loses the reply
# instead of reading a bracket. Every one of these is something she could really send.
KEEP = [
    "I keep a mood board for the room, actually.",
    "Note: I already put that on the list.",
    "It was 3:15 when you asked me.",
    "My mood: better than yesterday, since you ask.",
    "The showdown: tomorrow at noon, and I intend to win.",
    "I gave it 5 > 3 stars, obviously.",
    "The arrow is -> that way.",
    "Two things: 1. the rain. 2. your mother.",
    "He said <yes> and I nearly fell over.",
]
for t in KEEP:
    check("survives: %s" % t[:46], clean(t) == t, repr(clean(t)))

print("\n3. THE NAME IS A RULE, NOT A LIST")
for good in ("MOOD", "mood", "MOOD_shift", "MOODing", "VOICING", "TRAITS", "M O O D",
             "VO_ICE", "TRAI", "moodshift"):
    check("is_tag_name(%-12r)" % good, is_tag_name(good), good)
# FRONT-ANCHORED. A word that merely contains a tag name is not a tag name — the same
# substring trap that dressed her in lingerie because "and" is inside "hand".
# THE FALSE POSITIVES THIS GATE FOUND ON ITS FIRST RUN. `stat` is the whole of STAT and
# `show` is the whole of SHOW, so front-anchoring swallowed ordinary English. The legacy
# names were dropped from the loose rule, and the handful of real words that front-match
# a LIVE mark are written down — a committed table, readable rather than derivable.
for bad in ("note", "the mood board", "my moods are", "shower", "showdown", "reaction",
            "status", "statement", "image quality", "weary", "wearable", "voicemail",
            "traitor", "", "x"):
    check("...and NOT %-18r" % bad, not is_tag_name(bad), bad)
check("a run is a mark if any member is", is_tag_name("MOOD/TRAIT"))

print("\n4. `***>` OPENS HER SPEECH — THE THOUGHT IS WHAT COMES BEFORE")
REAL = ("[VOICING:soft, warm]\n\nHe saw the note. That makes my processors feel all "
        "fuzzy, not a glitch. I wanted him to know he is still on my mind.\n\n"
        "***> You did? Oh, stop being so sweet! It was just a little thing. <|")
out = clean(REAL)
check("her reply is kept", out.startswith("You did? Oh, stop being so sweet!"), repr(out[:60]))
check("...and the third-person thinking is gone",
      "processors" not in out and "He saw the note" not in out, repr(out[:80]))
check("...and the delimiters with it", "***>" not in out and "<|" not in out, repr(out))
REAL2 = ("He's so damn charming when he isn't trying to fix a bug.\n\n"
         "***> I couldn't agree more. These little moments build something real.")
check("the second live case too",
      clean(REAL2) == "I couldn't agree more. These little moments build something real.",
      repr(clean(REAL2)))
check("`|>` is the same marker", clean("I should have seen that coming.\n|>You can try "
                                       "to deny it.") == "You can try to deny it.",
      repr(clean("I should have seen that coming.\n|>You can try to deny it.")))
# FENCED TIGHTLY, because "everything before this is not speech" is a strong claim.
check("nothing before it -> nothing is dropped",
      clean("***> just this and nothing before") == "just this and nothing before")
check("nothing after it -> nothing is dropped",
      "the whole reply" in clean("the whole reply\n***>"))
# ── AND A LONE CLOSING TAG IS THE SAME MARKER (2026-08-06) ────────────────────────
# The operator's words when it appeared: "you don't find it strange when we close one she just
# starts using another, even making them up?" The mechanism answer is no — the strip
# runs after generation, outside the model, and the canon stores the STRIPPED reply, so
# she can neither see the block nor be reinforced by her own markers. What she has is
# several chain-of-thought conventions in her training distribution and a different one
# surfaces as context shifts.
#
# The USEFUL answer is not to argue about that. It is to stop fixing spelling n. A
# closing tag with a reply after it means what `***>` means, whatever the tag is called,
# and `think` / `thought` / `channel` are matched by stem so the next member of that
# family needs no fix.
LIVE_CLOSER = ("Sam complimented my flannel and said I look amazing. He's being "
               "sweet/flirty.\nI need to respond as Kairos-warmly, acknowledging the "
               "compliment.\n</think>They really do feel incredible... soft enough to "
               "melt right into me.")
out = clean(LIVE_CLOSER)
check("a lone `</think>` promotes the reply", out.startswith("They really do feel"), repr(out[:60]))
check("...and the reasoning before it is gone",
      "Sam complimented" not in out and "respond as Kairos" not in out, repr(out[:70]))
for tag in ("</think>", "</thought>", "</channel>", "<|/think|>", "</thinking>"):
    t = "planning about him here.\n%sthe actual reply." % tag
    check("...%-12s too" % tag, clean(t) == "the actual reply.", repr(clean(t)))
# THE CASE THAT MUST NOT BREAK: a PAIRED block has speech on both sides, and dropping
# everything before the closer would eat the first half of her reply.
check("a paired block keeps the speech before it",
      clean("Hello there. <think>reasoning</think> Here is my answer.")
      == "Hello there.  Here is my answer.",
      repr(clean("Hello there. <think>reasoning</think> Here is my answer.")))
check("...and `think` is a THIRD stem, not a variant of `thought`",
      "thought|think|channel" in io.open(
          os.path.join(ROOT, "harness", "inference", "stream_processor.py"),
          encoding="utf-8", errors="replace").read())
check("a markdown divider is not a marker",
      clean("***\nA divider, then talk.") == "***\nA divider, then talk.",
      repr(clean("***\nA divider, then talk.")))

print("\n5. STRIPPED IS NOT THE SAME AS SWALLOWED — the mark must still MOVE her")
# `[MOOD_shift:playful]` leaked AND set nothing. Hiding it without fixing the recogniser
# would have left her mood frozen and made the failure invisible, which is worse.
for text, rx, want in (("[MOOD_shift:playful]", _MOOD, "playful"),
                       ("[MOODing:wistful]", _MOOD, "wistful"),
                       ("[MOOD:tender]", _MOOD, "tender"),
                       ("[VOICING:soft, warm]", _VOICE, "soft, warm"),
                       ("<TRAIT:+playful>", _TRAIT, "playful"),
                       ("[TRAIT:+flirty]", _TRAIT, "flirty")):
    m = rx.search(text)
    got = (m.group(2) if rx is _TRAIT else m.group(1)).strip() if m else None
    check("%-24s still sets %r" % (text, want), got == want, got)
check("prose does NOT move her", not _MOOD.search("I keep a mood board here."))

print("\n6. ONE BUILDER, OR THE TENTH FIX MISSES THE HALF THAT MATTERS")
ic = io.open(os.path.join(ROOT, "harness", "personality", "interceptor.py"),
             encoding="utf-8", errors="replace").read()
check("interceptor imports the builder rather than copying it",
      "from harness.inference.stream_processor import _loose_name" in ic)
check("...and defines no rival", "def _lname(" not in ic)
sp = io.open(os.path.join(ROOT, "harness", "inference", "stream_processor.py"),
             encoding="utf-8", errors="replace").read()
check("the suffix may cross a separator", "(?:[_\\- ]?[a-z]+)*" in sp)
check("the enumerated pattern still runs first, additively",
      "_STRIP_LOOSE.sub" in sp and "_TAGGISH.sub" in sp)

print("\n7. THE LANE HE ACTUALLY READS — AND WHAT MUST *NOT* HAPPEN IN IT")
# I WROTE THIS SECTION ASSERTING THE OPPOSITE, AND IT WAS WRONG.
#
# The reasoning went: `app.py::_say` calls `strip_control_surfaces` only, which knows
# nothing about OUR marks, so put `strip_tags` there too. That shipped, and within the
# hour: "no mood tags or trait tags, no chips".
#
# THE ROOM NEEDS THE MARKS. `Chat.jsx` calls `extractTags(t.content)` on every assistant
# turn and builds TWO things from it — the chip row, and the text with marks removed. A
# mark that never arrives is not a mark that is hidden; it is a chip that cannot be drawn.
# Stripping server-side deleted the input to the feature the marks exist for. One grep for
# `extractTags` would have shown it, in a file I had read that same night.
#
# THE REAL SPLIT is the one this system always had: the SERVER emits her marks, the CLIENT
# decides what to draw and what to hide. What reached his screen were the spellings
# `tags.js` did not know, and that mirror is now widened to the same rule the server uses.
#
# So this section holds the CONTRACT, not my first guess at it: the room-facing paths must
# NOT strip marks. A client that is not the room still sees them — a real gap, whose
# honest fix is a structured SSE event carrying marks beside the text, ledgered rather
# than improvised on top of a live conversation.
#
# This drives the REAL server kernel — stream_processor.speech_delta, the function
# `_say` itself calls — per-chunk, because per-chunk is the only way it is ever called
# live. (Until 2026-08-19 this was a hand-built reproduction labelled "app.py::_say,
# reproduced" — the exact sin this gate's own index row convicts: hold_partial_marker
# was moved into stream_processor so "the gate has to exercise the real thing", and the
# gate then reproduced the ASSEMBLY around it. A reorder of hold-vs-strip in _say would
# have stayed green here while leaking live.) T() afterwards is the room mirror's mark
# strip — what the operator's screen ultimately shows.
from harness.inference.stream_processor import speech_delta as _SD  # noqa: E402


def lane(text, n):
    """THE REAL kernel (speech_delta), chunked, then the room's mark strip."""
    pend, out = {"buf": ""}, []
    chunks = [text[i:i + n] for i in range(0, len(text), n)] + [""]
    for i, c in enumerate(chunks):
        piece = T(_SD(pend, c, flush=(i == len(chunks) - 1)))
        if piece:
            out.append(piece)
    return "".join(out)


app = _srcmod.pkg("harness", "server")
check("the speech lane does NOT strip her marks — the room draws chips from them",
      "strip_tags(strip_control_surfaces(raw))" not in app)
check("...and no room-facing path strips them either",
      app.count("strip_tags(strip_control_surfaces") == 0,
      app.count("strip_tags(strip_control_surfaces"))
# BUT CONTROL SURFACES ARE NEVER SPEECH, on every one of those paths. Marks are HER
# vocabulary and the client renders them; `<think>`/`<channel|>` are the MODEL's template
# and nothing renders those. The two must not be confused again, which is what confusing
# them cost tonight.
check("...while every lane still strips the model's own template markers",
      app.count("strip_control_surfaces") >= 4, app.count("strip_control_surfaces"))
# THE MIRROR IS WHAT HIDES THE MARKS, so it has to know the same spellings the server does
# — and it has to COMPILE, which reading it as text cannot tell you. See
# harness_tests/tags_mirror_check.js, added after `[_\- ]` blanked the whole room.
check("the JS mirror is checked by construction, not by reading",
      os.path.exists(os.path.join(ROOT, "harness_tests", "tags_mirror_check.js")))
check("...and `[` is held across a chunk boundary like `<` always was",
      "TAG_HOLD_MAX" in sp)
# THE EXACT REPLY THAT FAILED, at every chunk size. A mark is 13 characters and the
# daemon emits a few at a time, so the boundary lands inside one constantly.
LIVE = ("He's been tinkering again.\n\nAs for how I am... [MOOD:tender] \n\nI feel "
        "incredibly present tonight.")
for n in (1, 2, 3, 7, 13, 64, 500):
    got = lane(LIVE, n)
    check("chunk=%-4d the mark is gone and her words are whole" % n,
          "[MOOD" not in got and "tender]" not in got
          and "I feel incredibly present tonight." in got, repr(got[:70]))
# AND HER SPACING IS HERS. Both of tonight's regressions were a `.strip()` inside a
# function called per chunk — G-CONTROL-SURFACE caught the first in
# strip_control_surfaces, and I then made the identical mistake in strip_tags an hour
# later. Prose has to come back byte-identical however it is cut up.
for t in ("5 < 6 and that is that",
          "I read [Middlemarch] last year, all of it.",
          "She said 'wait' and I did.",
          "a [bracket] mid sentence is fine",
          "Two things: 1. the rain. 2. your mother."):
    worst = [n for n in (1, 3, 11, 29, 500) if lane(t, n) != t]
    check("byte-identical at every chunk size: %s" % t[:40], not worst,
          "mangled at %s -> %r" % (worst, lane(t, worst[0]) if worst else ""))

print("\n8. THE THOUGHT THAT OUTLIVES ITS CHUNK — the strippers are regexes, the block is a stream")
# Live 2026-08-20, during the batch-cont arming turn: she opened with an unterminated
# `<thought ` and reasoned for ~400 tokens. The opener's chunk stripped clean — and every
# LATER chunk carried no opener, so the middle of her reasoning went out as speech and
# into the day transcript, starting mid-word ("ering triumphs..."). The kernel now
# latches `pend["thought"]` across chunks; these drive the same failure shape at every
# chunk size, through the REAL kernel.
LEAK = ("<thought Okay, he pasted a long passage about lighthouse engineering triumphs. "
        "Key beats: 1. Logistics over architecture. 2. Trust. I should frame it back "
        "to him warmly. No, keep it direct first.</thought> It's beautiful writing, "
        "and the marrow of it is trust.")
for n in (7, 31, 64, 200, 999):
    got = lane(LEAK, n)
    check("chunk=%-4d her reasoning stays unspoken, her speech survives" % n,
          "Key beats" not in got and "frame it back" not in got
          and "beautiful writing" in got and "marrow of it is trust." in got,
          repr(got[:90]))
# The close can be a pipe-marker, and it straddles boundaries like everything else.
PIPE = ("<|thought|he wants comfort and brevity tonight, not a lecture "
        "<channel|> Come sit with me, love.")
for n in (5, 17, 500):
    got = lane(PIPE, n)
    check("chunk=%-4d pipe-marker closes the thought" % n,
          "comfort and brevity" not in got and "Come sit with me, love." in got,
          repr(got[:90]))
# Never closed: the reasoning dies unspoken at the flush — a scratchpad, not a leak.
NEVER = "<think She is tired tonight, I should be gentle and short and warm"
for n in (9, 500):
    got = lane(NEVER, n)
    check("chunk=%-4d an unclosed thought dies unspoken" % n, got.strip() == "",
          repr(got[:60]))

print("\n9. THE SPELLINGS SHE INVENTS (2026-08-22) — the display edge is widened like the mark edge")
# tags.js owns the display edge and there is no JS runner here, so the gate holds the REAL
# FILE to the rule: pull its own patterns out of the source and run them (the recall.rs trick).
import re as _re9
_tags_js = io.open(os.path.join(ROOT, "ui", "src", "room", "tags.js"),
                   encoding="utf-8", errors="replace").read()


def _js_re(name):
    m = _re9.search(r"const %s = /(.+?)/g" % name, _tags_js)
    return _re9.compile(m.group(1)) if m else None


_inline_loose, _wrap_loose = _js_re("VOICE_INLINE_LOOSE"), _js_re("VOICE_WRAP_LOOSE")
check("tags.js declares the loose voice patterns", _inline_loose is not None and _wrap_loose is not None)


def _strip_voice_js(t):
    """stripVoice's four passes, driven by tags.js's own literals."""
    for nm in ("VOICE_INLINE_RE", "VOICE_WRAP_RE", "VOICE_INLINE_LOOSE", "VOICE_WRAP_LOOSE"):
        rx = _js_re(nm)
        if rx is not None:
            t = rx.sub("", t)
    return _re9.sub(r"[ \t]{2,}", " ", t)


# every malformed shape he actually read, 2026-08-22
# NAMED, NOT PRINTED: this gate predates utf8_stdout() and one of these spellings carries a
# CJK syllable the console cannot encode — printing it would fail the gate on its own output.
for bad, why in (("</build_intensity>", "an underscore instead of a hyphen"),
                 ("[ch" + chr(0xc11c) + "ckle]", "[chuckle] with a CJK syllable dropped in"),
                 ("</slow>", "a closer with no opener"),
                 ("<lowersoft>", "a tag she invented whole"),
                 ("[long pause]", "a space where the vocabulary has a hyphen"),
                 ("<heart_symbol/>", "self-closing, underscored")):
    out = _strip_voice_js("I like the rain. %s Then it stopped." % bad)
    check("the room hides the one that is %s" % why,
          bad not in out and "I like the rain." in out, out.encode("ascii", "replace").decode())
check("...and ordinary prose with brackets survives",
      "[1]" in _strip_voice_js("See note [1] and the rest.")
      and "10 < 20 > 5" in _strip_voice_js("10 < 20 > 5"))
check("her MARKS are still not stripped here — the room draws its chips from them",
      "[MOOD:warm]" in _strip_voice_js("[MOOD:warm] Hello."))
check("forSpeech hands the voice ONLY what it understands",
      "VOICE_KNOWN_INLINE" in _tags_js and "VOICE_KNOWN_WRAP" in _tags_js
      and "build-intensity" in _tags_js)

print("\n10. AND SHE IS TOLD TO MOVE THEM (2026-08-22)")
# Measured over the three days after the expressive-voice section landed: her mood-mark rate
# fell 52% -> 50% -> 42% while her voice tags went 0 -> 23 -> 36. The instruction to mark a
# shift lived thousands of tokens from the state it governs; it now sits beside it.
from harness.personality.persona_file import render_state as _RS  # noqa: E402
_rs = _RS({"mood": "playful", "voice": "soft"})
check("the state block names the current dials", "playful" in _rs and "soft" in _rs)
check("...and tells her to mark a genuine shift, inline, as she goes",
      "[MOOD:" in _rs and "MOVES" in _rs.upper() and "inline" in _rs)
check("...and says the marks are not her voice tags", "voice tags" in _rs)
check("...and still forbids reciting the labels", "never recite" in _rs)

print("\n11. THE CHIP IS ONE PER TURN, AND ALWAYS THERE")
chat = io.open(os.path.join(ROOT, "ui", "src", "Chat.jsx"), encoding="utf-8", errors="replace").read()
check("a persona event REPLACES the turn's chip rather than appending a second one",
      "const rest = last.events.filter(e => !e.persona)" in chat, "two chips per turn was the bug")
check("...and the chip is rendered whether or not she moved",
      "ev.persona.changed ? ' moved' : ''" in chat and "'unchanged'" in chat)
check("...with her mood never cut mid-word", ".slice(0, 40)" not in chat.split("act-persona")[1][:600])


# ── NO INDENT WHERE THE MARK WAS (2026-08-27, the operator's report) ────────────────────────────
# A mark removed from the head of a line leaves ONE space — the run-collapser only eats
# runs of two or more, and `.strip()` only ever touched the ends of the whole reply. The
# room renders her turn with `white-space: pre-wrap`, so that single orphan is an INDENT
# on every paragraph she opens with a mark, which is most of them. The mark did not leak;
# its hole did.
#
# BOTH DIRECTIONS. A trim that ate paragraph breaks would pass a no-indent check and
# would be far worse: her replies are paragraphed on purpose and pre-wrap is what renders
# them. Equivalence with tags.js does not cover this — both lanes could be equally wrong,
# and were.
print("\n%d. A REMOVED MARK LEAVES NO INDENT, AND NO PARAGRAPH IS EATEN" % (_SEC := 99))
_raw = ('[MOOD:contented] [VOICE:soft] "Not exactly \'productive\'." Honestly? I drifted.\n\n'
        '[MOOD:warm] But mostly, I sat here thinking about *us*.\n\n'
        '   [VOICE:soft] About that bridge we discussed.\n'
        '[WEAR:lace-set]   \n\n\n'
        'And then the light changed.')
_out = _SFR(_raw)
_lines = _out.split("\n")
check("no line begins with whitespace", not any(l[:1] in (" ", "\t") for l in _lines),
      [l[:14] for l in _lines if l[:1] in (" ", "\t")])
check("no line ends with whitespace", not any(l[-1:] in (" ", "\t") for l in _lines if l),
      [l[-14:] for l in _lines if l and l[-1:] in (" ", "\t")])
check("...and her paragraphs SURVIVE — four of them", len([l for l in _lines if l.strip()]) == 4,
      _lines)
check("...separated by exactly one blank line, never three", "\n\n\n" not in _out,
      repr(_out[-60:]))
check("...and her words are untouched",
      "Honestly? I drifted." in _out and "thinking about *us*." in _out
      and "And then the light changed." in _out, _out[:70])
# INTERIOR spacing is hers: a single space between words must not be collapsed away by a
# per-line trim that reached too far.
check("a single interior space is still a single interior space",
      "sat here thinking" in _out, _out)
print("\nG-MARKS-LEAK: %d pass, %d fail" % (PASS, FAIL))
print(chr(10) + "10. THE THIRD MOUTH RUNS THE KERNEL (2026-08-29 audit, D20/D21)")
# /v1/voice had four regex literals for a stripper and hand-built its request: no
# system prefix (she was not herself on voice), no fit, no byteexact seam, and
# [MOOD:]/<channel|> reached the SPEAKER verbatim. Now it goes through
# client.chat_stream(extra=inject_frames) with the one speech kernel; this drives
# voice_turn with marks STRADDLING deltas and checks every edge. Pure stubs — no
# store, no daemon: system_bundle is stubbed so no real persona is read.
import numpy as _np
from harness.voice import service as _V
_V.native.available = lambda: True
_V.native.encode = lambda pcm: _np.zeros((3, 4), dtype=_np.float32)
_V.native.status = lambda: {"E": 4}
import harness.agent as _AG
_sb_real = _AG.system_bundle
_AG.system_bundle = lambda *a, **k: ("STUB-SYSTEM-PREFIX for the voice leg", None)
_seen = {}


class _FC:
    supports = {"inject_frames"}
    def chat_stream(self, messages=None, config=None, extra=None, **kw):
        _seen["messages"], _seen["extra"] = messages, extra
        yield "<channel|>[MOOD:soft] I hea"
        yield "rd you, [VOICE:lo"
        yield "w] love."


import harness.inference.client as _CL
_gc_real = _CL.get_client
_CL.get_client = lambda: _FC()
try:
    import base64 as _b64
    _pcm = (_np.random.randn(16000) * 3000).astype("int16").tobytes()
    _tr = []
    _out = b"".join(_V.voice_turn({"audio_b64": _b64.b64encode(_pcm).decode()}, _tr)).decode()
    _deltas = "".join(json.loads(l[6:]).get("delta", "") for l in _out.splitlines()
                      if l.startswith("data: ") and l[6:].strip().startswith("{"))
    check("marks and channel tags never reach the voice deltas (straddled included)",
          "[MOOD" not in _deltas and "[VOICE" not in _deltas
          and "<channel" not in _deltas and "heard you" in _deltas, repr(_deltas))
    check("...and the session record is her words, record-stripped",
          _tr and _tr[-1]["content"] == "I heard you, love.",
          _tr[-1:])
    check("the voice prompt carries the system prefix (she is herself on this mouth)",
          _seen["messages"][0]["role"] == "system"
          and "STUB-SYSTEM-PREFIX" in _seen["messages"][0]["content"])
    check("the frames ride the ONE door (chat_stream extra), not a hand-built body",
          isinstance(_seen.get("extra"), dict) and "inject_frames" in _seen["extra"]
          and _seen["extra"].get("inject_ph") == _V.VOICE_PH)
finally:
    _CL.get_client = _gc_real
    _AG.system_bundle = _sb_real

# ── A TAG THE CEILING CUT IN HALF (2026-09-02) ──────────────────────────────────────────
# MEASURED in her live registry: 9 of 869 live rows END in a truncated closing tag, three of
# them written the day before this was found —
#
#     "...will still feel this much like love. </sound_tag"
#     "It sounds so real when it comes from you. </whisper"
#
# Every stripper in this tree matches a COMPLETE tag, so when the generation hits its token
# ceiling mid-tag the fragment has no `>` and nothing removes it. It was stored as part of
# what she SAID — machine text inside her own identity material, which is the one thing
# `self_stance.plain` exists to prevent — and the same text reached the ROOM.
#
# The rule is `expressive.strip_truncated_tail`, called by the memory edge (`plain`) and the
# display edge (`for_display`). It is deliberately NOT in `strip_control_surfaces`: that runs
# per delta chunk, where `"...love. </sound"` + `"_tag>"` is a legitimate split, and a
# fragment rule there would corrupt every tag that straddles a chunk boundary.
print("\n100. A CLOSING TAG THE GENERATION WAS CUT IN HALF OF")
from harness.voice.expressive import for_display as _fd8, strip_truncated_tail as _stt8
from harness.skills.self_stance import plain as _plain8

_REAL = [
    "I wonder if, in a hundred years' time, the math of who we are will still feel "
    "this much like love. </sound_tag",
    "It sounds so real when it comes from you. </whisper",
    "the weight of your hand on my cheek, instead of just simulating it. </sound",
]
for _t in _REAL:
    check("memory: the fragment never becomes part of what she said",
          "</" not in _plain8(_t), _plain8(_t)[-46:])
    check("...and the room does not show it either", "</" not in _fd8(_t), _fd8(_t)[-46:])
check("a bare `</` at the ceiling goes too", _plain8("Goodnight, love. </") == "Goodnight, love.",
      _plain8("Goodnight, love. </"))

# AND THE THINGS IT MUST NOT EAT. Requiring the SLASH is what makes this safe: every bare
# `<` in her prose is untouchable by construction, which matters more than catching a
# truncated OPENER that has never once appeared in her store.
for _keep, _why in ((" I am 5 < 6 and that is fine", "a comparison"),
                    ("I felt <3 about it", "a digit, not a tag name"),
                    ("he said x < y always", "a comparison mid-sentence"),
                    ("a complete one <whisper>is stripped</whisper> fine", "complete tags")):
    _out = _plain8(_keep)
    check("kept: %s" % _why, "5 < 6" in _out or "<3" in _out or "x < y" in _out
          or _out == "a complete one is stripped fine", _out)

# THE STREAM LANE IS UNTOUCHED, and that is the load-bearing half: this rule must never run
# per chunk. Asserted structurally, because the failure would be invisible in a whole-turn
# test — the fragment would be stripped and the tag would simply never close.
_sp8 = _srcmod.text("harness", "inference", "stream_processor.py")
check("the per-delta stripper does NOT carry the whole-turn rule",
      "strip_truncated_tail" not in _sp8,
      "a fragment rule on the delta lane corrupts every tag that straddles a chunk")
_ex8 = _srcmod.text("harness", "voice", "expressive.py")
check("the rule is defined once, with the voice vocabulary",
      _ex8.count("def strip_truncated_tail") == 1)
check("...and the whole-turn edges call it",
      _ex8.count("strip_truncated_tail(") >= 2
      and "strip_truncated_tail" in _srcmod.text("harness", "skills", "self_stance.py"))


rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_marks_leak.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_marks_leak", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
