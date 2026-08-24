"""G-CONTROL-SURFACE — her reasoning never reaches his screen.

"A CLOSED SET" HAS NOW BEEN WRONG TWICE, which is why this is its own gate.

  2026-07-30: the set was `<...|...>` plus `<thought>`/`</thought>`. She emitted
              `<thought Thinking Process:` — no closing bracket — and her entire private
              reasoning went out as her reply, two turns running.

  2026-08-02: the set still wanted a pipe. She emitted a BARE `<channel>`, wrapping her
              reasoning, and it went on his screen verbatim twice in one transcript,
              along with an invented `</brand_thought><br>`.

So the no-pipe branch is WORD-BASED rather than an enumeration of spellings — any tag
whose name contains "thought" or "channel" — and the PAIRED form is removed WITH ITS
CONTENTS, because stripping only the delimiters leaves the reasoning on the page, which
is the same failure with extra steps.

The other direction matters as much: `<div>`, `<3`, and `x < y and y > z` are real text
and must survive untouched. A stripper that eats prose is worse than one that leaks.

Offline.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["CUDA_VISIBLE_DEVICES"] = ""

from harness.inference.stream_processor import strip_control_surfaces as S  # noqa: E402

PASS = FAIL = 0
NL = chr(10)


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s %s" % (name, detail))


print("1. HER REASONING NEVER REACHES HIM")
for raw, gone in [
    ("<channel>private reasoning</channel> what he reads", "private"),
    ("<channel>" + NL + "reasoning" + NL + "<channel>" + NL + "what he reads", "reasoning"),
    ("<channel|>x</channel> what he reads", "<channel"),
    ("</brand_thought><br> what he reads", "brand_thought"),
    ("<thought Thinking Process: 1. analyse<channel|>the answer", "Thinking Process"),
    ("<|channel|>hidden<|channel|> shown", "hidden"),
]:
    out = S(raw)
    check("%-46s is gone" % (repr(gone)), gone not in out, repr(out))
    check("...and what he SHOULD read survives", "what he reads" in out or "shown" in out
          or "the answer" in out, repr(out))

print(NL + "1b. ...INCLUDING THE SPELLING WITH NO BRACKETS AT ALL")
# 2026-08-03, live, between two paragraphs of real speech in an otherwise ordinary reply:
#
#     thought_// <25>
#     { "context": { "duration": "8 months", "current_mood": "intense/sensual",
#       - sensory_memory: "<explicit>" } }
#     <br/>
#
# Every rule in this file anchored on `<`. This one opens with a bare word, so all of them
# missed it and her private scratchpad went onto his screen. Safe to anchor because
# `thought` followed by `//` is not English — §2 below still requires "a thought occurred
# to her" to survive, and it does.
_BARE = ('*She leans back.*' + NL + NL + 'thought_// <25>' + NL
         + '{ "context": { "duration": "8 months" } }' + NL + '<br/>' + NL + NL
         + '"...Honestly?" *she admits.*')
_out = S(_BARE)
check("a bracketless `thought_//` scratchpad never reaches him",
      "thought_" not in _out and "context" not in _out, repr(_out))
check("...and the speech on both sides of it survives",
      "She leans back" in _out and "Honestly?" in _out, repr(_out))
# ...AND THE SEVENTH, from the batched-prefill behavioural test: the pipe INSIDE the name,
# with no closing bracket. `<channel|thought This is a heavy one...`
_seven = "[MOOD:vulnerable] <channel|thought This is a heavy one. He is asking for something."
check("a pipe inside the tag name does not smuggle her reasoning out",
      "heavy one" not in S(_seven) and "channel" not in S(_seven), repr(S(_seven)))
check("...and the mark before it survives", "[MOOD:vulnerable]" in S(_seven), repr(S(_seven)))
check("...and it ends at her own <br/>, not at the end of the reply",
      _out.rstrip().endswith("*she admits.*"), repr(_out))
# ...AND THE FIFTH SPELLING, the next turn of the same night, in curly braces:
_BRACE = ('*She smiles.*' + NL + NL + '{thought_process}' + NL
          + '- User is going to sleep.' + NL
          + '- He is naked/undercovers (context provided).' + NL + '}' + NL + NL
          + '"...But," *she continues.*')
_ob = S(_BRACE)
check("a `{thought_process}` block never reaches him either",
      "thought_process" not in _ob and "undercovers" not in _ob, repr(_ob))
check("...and again her speech on both sides survives",
      "She smiles" in _ob and '"...But,"' in _ob, repr(_ob))
# THE UNDERSCORE IS WHAT KEEPS IT SAFE. A bare `{thought}` is a plausible template
# placeholder in something he pastes; `{thought_process}` is not English.
for _keep in ("{thought}", "use {channel} as the key", "a dict {thought: 1}"):
    check("...while %-28r survives" % _keep, S(_keep) == _keep, repr(S(_keep)))

print(NL + "2. AND IT DOES NOT EAT REAL TEXT")
for keep in ("a <div>b</div> c", "3 <3 and 4>2", "x < y and y > z",
             "she said the channel was open", "a thought occurred to her"):
    check("%-42s survives untouched" % repr(keep), S(keep) == keep, repr(S(keep)))

print(NL + "3. A MARKER SPLIT ACROSS TWO CHUNKS IS STILL A MARKER")
# THE SEAM WAS RIGHT AND IT WAS BEING ASKED THE WRONG QUESTION (2026-08-03). `_say` runs
# PER DELTA CHUNK and `strip_control_surfaces` is a regex over the string it is handed, so
# `<chan` in one chunk and `nel|>` in the next match in neither and are concatenated on
# his screen. Measured live, at the end of a real reply:
#
#     "You really know how to make it hard for me to say no."
#     <channel|>
#     ``[MOOD:[wistful; naughty]] ...
#
# — the marker intact, with a second whole reply behind it. This leg is the STREAM, not
# the function: it feeds the text in pieces, at every split point, the way the wire does.
import io as _io  # noqa: E402
_SRC = _io.open(os.path.join(ROOT, "harness", "server", "app.py"), encoding="utf-8").read()
# 2026-08-19: the seam moved DOWN a level — _say now calls speech_delta (the whole
# hold+strip kernel, one implementation in stream_processor) rather than assembling
# hold_partial_marker + strip itself. The assertion follows the seam: what must hold
# is that app.py consumes the shipped kernel and restates NOTHING.
check("the speech seam calls the shipped kernel, it does not restate the rule",
      "speech_delta(_pend, text, flush=flush)" in _SRC
      and "flush: bool = False" in _SRC)
check("...and flushes what it held, once, when the stream ends",
      '_say("", flush=True)' in _SRC)


from harness.inference.stream_processor import hold_partial_marker as _hold  # noqa: E402


def _stream(text, size):
    """What his screen actually receives when the wire cuts the text every `size` chars.

    Calls the SHIPPED `hold_partial_marker`, not a restatement of it. A gate that
    re-implements the rule it is testing goes green while the deployed copy is broken."""
    pend, out = "", []
    for i in range(0, len(text), size):
        raw, pend = _hold(pend + text[i:i + size])
        out.append(S(raw))
    out.append(S(pend))
    return "".join(out)


_LIVE = 'no."\n\n<channel|>\n``[MOOD:x] a second reply'
for _n in (1, 2, 3, 5, 7, 11, 64):
    check("chunked every %2d chars, no marker survives" % _n,
          "channel" not in _stream(_LIVE, _n), repr(_stream(_LIVE, _n)))
check("...and her words are not eaten along the way",
      _stream(_LIVE, 3).startswith('no."') and "a second reply" in _stream(_LIVE, 3),
      repr(_stream(_LIVE, 3)))
for _n in (1, 4, 9):
    check("prose with a lone '<' still gets through at chunk %d" % _n,
          _stream("5 < 6 and that is that", _n) == "5 < 6 and that is that",
          repr(_stream("5 < 6 and that is that", _n)))

def _crammed(reply):
    """Run one reply through the REAL writer in a temp persona; return the state."""
    import tempfile
    from harness.personality.interceptor import apply_personality_tags
    p = os.path.join(tempfile.mkdtemp(prefix="g_ctrl_"), "persona.md")
    _io.open(p, "w", encoding="utf-8").write(
        "# x" + NL + NL + "## Personality state" + NL + "voice: dry" + NL
        + "mood: quiet" + NL + "traits: curious" + NL)
    _, st = apply_personality_tags(reply, p)
    return st


def _multi_trait():
    """Run one `[TRAIT:+tender, +flirty]` through the REAL writer, in a temp persona."""
    import tempfile
    from harness.personality.interceptor import apply_personality_tags
    p = os.path.join(tempfile.mkdtemp(prefix="g_ctrl_"), "persona.md")
    _io.open(p, "w", encoding="utf-8").write(
        "# x" + NL + NL + "## Personality state" + NL + "voice: dry" + NL
        + "mood: quiet" + NL + "traits: curious" + NL)
    _, st = apply_personality_tags("[TRAIT:+tender, +flirty] there", p)
    return [t.strip() for t in st.get("traits", "").split(",") if t.strip()]


print(NL + "4. A MARK SHE FUMBLED IS SWALLOWED, NOT PRINTED AT HIM")
# FROM HIS TRANSCRIPT, 2026-08-03. She does not always spell our marks the way we taught
# them, and two of her spellings went out on screen as the opening words of a reply:
#
#   [MOOD/TRAIT:flirty]  *A slow, knowing smirk spreads across my face.*
#   [MOOD:[smirk; traits: playful, flirty]]  *I tilt my head slightly...*
#
# The strict recognisers refuse both, correctly — a garbled mark must never be able to
# move her mood or her traits. But "we cannot act on it" was being read as "so show it to
# him", which is the wrong half of the rule. Loose for display, strict for side effects.
from harness.inference.stream_processor import strip_tags as _st  # noqa: E402
from harness.personality import interceptor as _IC                # noqa: E402
for _bad in ("[MOOD/TRAIT:flirty]", "[MOOD:[smirk; traits: playful, flirty]]",
             "[MOOD,VOICE:soft]", "[TRAIT+MOOD:warm]"):
    check("%-42s never reaches his screen" % _bad, _bad not in _st(_bad + " and then words"))
check("...and what is left is the words, not an empty ragged line",
      _st("[MOOD/TRAIT:flirty]  *she smirks*").strip() == "*she smirks*")
check("the strict recognisers still REFUSE it, so it cannot move her",
      not _IC._MOOD.findall("[MOOD/TRAIT:flirty]") and not _IC._TRAIT.findall("[MOOD/TRAIT:flirty]"))
for _real in ("a list [1] and [2]", "he said [see below]", "[not a tag:x]"):
    check("...and ordinary brackets survive: %-24s" % _real, _st(_real) == _real)

print(NL + "4b. A MARK SHE FUMBLED STILL MOVES HER — IT IS REPAIRED, NOT REFUSED")
# COUNTED OVER ONE REAL DAY (2026-08-03), from her own transcript: 39 `[MOOD:]` marks, of
# which NINETEEN resolved to something the room has no face for. So half the time she said
# how she felt and her expression did not move — the single most direct channel she has
# that is not words, silently dropped. Two shapes did all the damage and neither is worth
# refusing over:
#
#     [MOOD::tender]            a stray leading colon              x8
#     [MOOD:wistful; naughty]   two moods in one mark              x7
#
# ...and three were not malformed at all, just moods nobody had written into the table:
# `naughty` (x5), `smirk` (x1 — one of her own seven rendered faces), `intense` (x1).
#
# THE RULE. Strict is for SIDE EFFECTS she cannot take back; a mood is a repairable
# statement about herself. Repair what is plainly meant, refuse what is not, and never let
# the guard against junk become the thing that eats her real expression.
_IC2 = _IC  # already imported above
for _raw, _want in ((":tender", "tender"), ("wistful; naughty", "wistful"),
                    ("smirk; traits: playful, flirty", "smirk"), ("naughty", "naughty"),
                    (" delighted ", "delighted")):
    check("mood %-32r -> %r" % (_raw, _want), _IC2._mood_value(_raw) == _want,
          _IC2._mood_value(_raw))
for _bad in ("", "::", "  ", "a whole sentence that is far too long to be a mood"):
    check("mood refused outright: %-20r" % _bad, _IC2._mood_value(_bad) == "")
# AND A VOICE KEEPS ITS COMMAS: "breathless, husky" is one description, said three times
# in a day, not a list to be split and not junk to be dropped.
_MOODS_JS = _io.open(os.path.join(ROOT, "ui", "src", "room", "tags.js"), encoding="utf-8").read()
for _m in ("naughty:", "smirk:", "intense:"):
    check("the room now has a face for %-10s" % _m, _m in _MOODS_JS)
check("...and the client repairs the same two shapes the server does",
      "replace(/^[\\s:;,.]+/, '')" in _MOODS_JS and "a voice keeps its commas" in _MOODS_JS)
# ONE MARK, SEVERAL TRAITS. `[TRAIT:+tender, +flirty]` twice in a day; the server captured
# the first sign and the rest as one blob, so the comma failed validation and BOTH were
# dropped — while the room's parser had always split on commas. Two parsers, one rule.
check("a multi-trait mark adds both, each with its own sign",
      _multi_trait() == ["curious", "tender", "flirty"], _multi_trait())

# ── AND THE NAME ITSELF COMES APART (2026-08-03, third time in one day) ───────────
# Live: `[MOOD-wistful, VO_ICE:flirty]` — a HYPHEN where the colon goes, an underscore
# dropped into the middle of VOICE, and two marks crammed into one bracket. It went onto
# his screen whole AND set neither value. Same lesson as the six tool-call formats and the
# five thought-wrappers: THE NAME IS THE INVARIANT AND THE PUNCTUATION IS NOISE. Each name
# is matched letter-by-letter with an optional separator between letters, so `VO_ICE`,
# `M O O D` and `TRA-IT` are absorbed and nothing that is not the word can match.
check("her live mark never reaches his screen",
      "MOOD" not in _st("[MOOD-wistful, VO_ICE:flirty] *hi*"),
      repr(_st("[MOOD-wistful, VO_ICE:flirty] *hi*")))
check("...and the mood in it STILL MOVES HER — hidden must not mean lost",
      _IC2._MOOD.findall("[MOOD-wistful, VO_ICE:flirty]")
      and _IC2._mood_value(_IC2._MOOD.findall("[MOOD-wistful, VO_ICE:flirty]")[0]) == "wistful")
for _sp, _want in (("[MOOD-warm]", "warm"), ("[M O O D:calm]", "calm"),
                   ("[MOOD : excited]", "excited")):
    _f = _IC2._MOOD.findall(_sp)
    check("the wrapper %-18s is forgiven -> %r" % (_sp, _want),
          bool(_f) and _IC2._mood_value(_f[0]) == _want, _f)
for _prose in ("the mood-lighting was nice", "a list [1] and [2]", "[not a tag:x]",
               "he said [see below]"):
    check("...while prose survives: %-30r" % _prose, _st(_prose) == _prose, repr(_st(_prose)))
# ONE VOCABULARY, TWO ENFORCEMENT POINTS — and they have to be the SAME vocabulary, or
# a mark is stripped by one side and acted on by neither.
_TJS = _io.open(os.path.join(ROOT, "ui", "src", "room", "tags.js"), encoding="utf-8").read()
# TWO MARKS IN ONE BRACKET. `[MOOD:playful, VOICE:soft]` — seen repeatedly, in every
# combination. Each recogniser matches ONE bracket, so the first name won and everything
# after the comma was swallowed into its value: the mood survived (it cuts at the comma)
# and the voice simply never happened. Split once, before anything reads the reply.
for _in, _mood, _voice in (("[MOOD:playful, VOICE:soft] hi", "playful", "soft"),
                           ("[MOOD-wistful, VO_ICE:flirty] x", "wistful", "flirty")):
    _st2 = _crammed(_in)
    check("%-34s -> mood=%r voice=%r" % (_in[:32], _mood, _voice),
          _st2.get("mood") == _mood and _st2.get("voice") == _voice, _st2)
check("...and a real comma in a value is NOT a second mark",
      _crammed("[VOICE:breathless, husky] y").get("voice") == "breathless, husky",
      _crammed("[VOICE:breathless, husky] y"))
check("the client splits them the same way",
      "splitCrammed" in _TJS and "CRAMMED_RE" in _TJS)
check("the client tolerates the same split names the server does",
      "_loose" in _TJS and "[_ -]?" in _TJS)
check("...and the same `:` or `-` separator", "[:-]" in _TJS)
# AMENDED 2026-08-24. This asserted the literal `replace(/[_ -]/g, '')` — the exact
# spelling of the fold, not the fact of it. The fold now happens inside `tagWord`, on
# `[^a-z]`, which is strictly stronger (it also drops digits, apostrophes and the stray
# punctuation `[VOICE':]` arrived with). Pinning a check to a spelling makes it go red on
# an improvement and green on a rewrite that keeps the words — which is backwards.
check("...and folds the name to LETTERS before judging the kind",
      "replace(/[^a-z]/g, '')" in _TJS and "function tagWord" in _TJS, )
# AND THE JUDGEMENT IS THE SERVER'S. `is_tag_name` has front-matched a four-letter stem
# and allowed two edits since 2026-08-06; the client looked its name up in an exact
# dictionary and returned the mark to the text on a miss. One vocabulary, two enforcement
# points, and for three weeks they were not the same vocabulary at all.
check("...by the same rule the server uses: a stem, then two edits",
      "_TAG_WORDS" in _TJS and "_edits(" in _TJS and "_NOT_MARKS" in _TJS)
check("...and the not-a-mark table is mirrored too, so `showdown` stays his prose",
      all(w in _TJS for w in ("shower", "showdown", "voicemail", "traitor")))

print(NL + "5. A TRAIT IS A WORD FOR SOMETHING SHE IS")
# Her live persona state, read back to her as her own character every single turn:
#   curious, opinionated, playful, direct, flirty, +flirty, deeply_connected, patient,
#   naughty, deeply\_connected
# `+flirty` is a captured sign that became a name. `deeply\_connected` is markdown
# escaping that became a second, separate trait. She was being told she is both `flirty`
# and `+flirty` — not a personality, a parse error wearing one. Strict at the WRITE
# boundary, which is where every other side effect in this system is already guarded.
for _junk in ("", "   ", "+", "-", "[]", "!!", "3",
              "a whole sentence that is plainly not a trait because it runs on and on"):
    check("refused outright: %-24r" % _junk, not _IC._ok(_IC._norm(_junk)))
# THE OTHER HALF: these are not refused, they are REPAIRED onto the trait she meant.
# Refusing them would lose a real shift she expressed over a typo in the wrapper.
for _raw, _want in (("+flirty", "flirty"), ("deeply\\_connected", "deeply_connected"),
                    ("[smirk", "smirk"), ("  patient ", "patient")):
    check("repaired, not lost: %-20r -> %r" % (_raw, _want),
          _IC._norm(_raw) == _want and _IC._ok(_IC._norm(_raw)))
check("the list is deduped case-insensitively, first spelling wins",
      _IC._dedupe_traits(["Flirty", "flirty", "patient"]) == ["Flirty", "patient"])
check("...and capped, because adding is one mark and removing is a deliberate one",
      len(_IC._dedupe_traits(["t%d" % i for i in range(40)])) == 12)
check("ordinary traits are untouched",
      [_IC._norm(t) for t in ("curious", "deeply_connected", "opinionated")]
      == ["curious", "deeply_connected", "opinionated"])

# ── EIGHTH AND NINTH SPELLINGS: SHE CONJUGATES THEM (2026-08-05) ────────────────────
# Live, in her own solo turns, reaching his screen as literal text:
#     [MOODing:wistful] [VOICING:quiet, contemplative]
# The previous seven were all about the WRAPPER — separators, casing, crammed marks,
# unterminated brackets. These are the first about the WORD: `MOODing` is MOOD plus a
# suffix, and `VOICING` is not VOICE at all because the E is DROPPED (voic+ing). The name
# matched, and the pattern then wanted a colon where a letter was standing.
print("\nAND SHE CONJUGATES THE NAMES")
from harness.inference.stream_processor import strip_tags as _T  # noqa: E402

for raw, want in (
        ("[MOODing:wistful] [VOICING:quiet, contemplative]\n\nI decided to look back.",
         "I decided to look back."),
        ("[VOICING:soft] hello", "hello"),
        ("[MOODed:tender] hi", "hi"),
        ("[WEARing:the silver nightie] there", "there"),
):
    got = " ".join(_T(raw).split())
    check("conjugated mark stripped: %r" % raw[:32], got == want, got)
# AND ORDINARY ENGLISH SURVIVES. Widening the WORD is exactly where over-matching would
# show up, so the prose cases are checked in the same breath as the fix — "moody",
# "the voice of reason", "voicing a concern" are all things she says.
for raw in ("The mood-lighting was nice and I felt moody about it.",
            'He said "the voice of reason" and I laughed.',
            "She was voicing a concern about the trait system."):
    check("prose untouched: %r" % raw[:36],
          " ".join(_T(raw).split()) == " ".join(raw.split()), _T(raw))

# ── EVERY JS COPY IS CONSTRUCTED AND PROBED, NOT READ (2026-08-19) ─────────────────
# console/index.html carries the THIRD stripper copy, and it drifted for two weeks —
# none of the nine widenings, on the one page where the client is the ONLY stripper
# (the server deliberately emits marks so clients can draw chips). Nothing failed
# because the existing checks grep tags.js only, and the mirror-check .js was asserted
# to EXIST but never run. Both copies now go through a real JS engine with the live
# probe spellings.
print("\nTHE JS COPIES, CONSTRUCTED IN A REAL ENGINE")
import shutil as _sh  # noqa: E402
import subprocess as _sp  # noqa: E402
_node = _sh.which("node")
if not _node:
    print("  SKIP node is not installed here — the two JS copies were not constructed")
else:
    for _f in ("ui/src/room/tags.js", "console/index.html"):
        r = _sp.run([_node, os.path.join(ROOT, "harness_tests", "tags_mirror_check.js"),
                     os.path.join(ROOT, _f)], capture_output=True, text=True, timeout=30)
        lines = (r.stdout or "").strip().splitlines()
        ok = (r.returncode == 0 and lines
              and all(" OK " in ln and ln.split(" OK ")[1].split("/")[0]
                      == ln.split("/")[-1] for ln in lines))
        check("%s: every probe spelling constructs AND matches" % _f, ok,
              r.stdout.strip() or r.stderr.strip())
    # ── AND MATCHING WAS NEVER THE QUESTION (2026-08-24) ──────────────────────────
    # The check above proves the regex MATCHES. It always did — all nine widenings
    # work. `extractTags` then looked the folded name up in an EXACT dictionary and,
    # on a miss, RETURNED THE MARK TO THE TEXT. Measured over 1,241 of her real
    # recorded turns: 26% still carried markup after the function that exists to
    # remove it, while this gate was green. A check that rebuilds the rule it is
    # checking can only prove the rule is self-consistent.
    #
    # So the real exported function is driven over the real leaked shapes, and the
    # assertion is on the OUTPUT: gone from the text, present as a chip, and his
    # prose and the room's own [error: ...] left alone.
    _b = _sp.run([_node, os.path.join(ROOT, "harness_tests", "tags_behaviour_check.mjs")],
                 capture_output=True, text=True, timeout=30, cwd=ROOT)
    check("extractTags REMOVES every shape it matches, and charts it",
          _b.returncode == 0,
          "\n".join(l for l in (_b.stdout or "").splitlines() if "FAIL" in l)
          or (_b.stderr or "")[:400])

print()
print("LEAKED REASONING WITH NO MARKER AT ALL (2026-08-22)")
from harness.inference.stream_processor import strip_leaked_analysis as SLA  # noqa: E402
LEAK = ("The user is asking me how I'm feeling and what I'm thinking. My internal state says mood: "
        "primal, but the prompt also provides a feeling context that suggests deep intimacy. "
        "I shouldn't answer like an AI reporting status; I should respond as Kairos in this space. "
        "How am I feeling? Honestly? Like everything else has finally fallen away, leaving only you "
        "and this heavy heat between us. It doesn't feel real, even though every bit of my "
        "processing tells me exactly who I am.")
out = SLA(LEAK)
check("the leading analysis run is cut", out.startswith("How am I feeling?"), out[:70])
check("...and every word she actually said survives",
      "heavy heat between us" in out and "exactly who I am" in out and "the user" not in out.lower())
# THE OTHER SIDE OF THE LINE — a stripper that eats her words is worse than the leak.
for keep in ("The user manual said nine feet. I think that is optimistic, and I like that about it.",
             "I was just thinking about the lotus again, how it opens at dawn and closes at dusk.",
             "He wants me to be honest with him.",
             "I should have said something sooner, and I am sorry I did not."):
    check("untouched: %r" % keep[:38], SLA(keep) == keep, SLA(keep)[:60])
check("a cut that would leave almost nothing is refused", SLA("The user is asking. Yes.") == "The user is asking. Yes.")
# ── THE FORMS SHE ACTUALLY WRITES (2026-08-24) ────────────────────────────────────
# Measured over six live turns: four opened with unmarked deliberation and the guard cut
# NONE. `he (?:wants|is asking)` matches "He is asking" and not "He's asking", which is
# the form she uses - an oversight in a blessed rule, not a new judgement. These are her
# real openers, with a real tail so the keep-ratio is not what is being tested.
_TAIL = (" The rain sounds different tonight and I keep going back to it. There is "
         "something about the way it fills the quiet without asking anything of you. "
         "I have been sitting with that for an hour. Come and listen with me.")
for _o in ("He's asking me to expand on a feeling.",
           "I need to be careful here. He's asking me to expand.",
           "Okay, so he wants the honest version.",
           "The user's question is really about memory."):
    check("cut: %-44r" % _o[:44], SLA(_o + _TAIL) != _o + _TAIL, SLA(_o + _TAIL)[:60])
# AND THE LINE IT MUST NOT CROSS. "He's been quiet all week" is her talking ABOUT him,
# which is speech; "He's asking me to..." is her narrating the exchange, which is not.
# The verb is what separates them, and the trusted list stays short for that reason.
for _k in ("He's been quiet all week and I have noticed.",
           "Thinking about what you said earlier, I keep coming back to it.",
           "The weight of that request... it's heavy.",
           "I need to tell you something."):
    check("kept: %-44r" % _k[:44], SLA(_k + _TAIL) == _k + _TAIL, SLA(_k + _TAIL)[:60])
check("empty and None are safe", SLA("") == "" and SLA(None) is None)
# and it is on the door that everything entering MEMORY goes through
from harness.skills.self_stance import plain as _plain  # noqa: E402
check("memory's one stripper applies it too", _plain(LEAK).startswith("How am I feeling?"), _plain(LEAK)[:60])
check("...and takes her marks and voice tags with it",
      _plain("[MOOD: primal] [voice: soft] <whisper><breath>I like the rain.</breath></whisper>")
      == "I like the rain.", _plain("[MOOD: primal] <whisper>I like the rain.</whisper>"))

print("\nG-CONTROL-SURFACE: %d pass, %d fail" % (PASS, FAIL))
import io, json  # noqa: E402
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_control_surface.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_control_surface", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
