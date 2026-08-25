"""PF-B3 — self-modify personality via tags. The model already emits [MOOD:x]/[VOICE:x] (and now
[TRAIT:+x]/[TRAIT:-x]); StreamProcessor strips them from output but never PERSISTED them. This adds
a post-call interceptor that reads those tags off the reply and writes them into the persona state
(PF-B2 write_state), so a voice/mood/trait the model chooses this turn survives to the next — the
model self-modifies its own personality mid-conversation.

ADR-002: the tag IS the clean symbolic DECISION; the EXECUTOR (write_state -> persona.md) applies it.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Dict, Tuple

from harness.personality.persona_file import parse_persona, write_state

# THE NAME IS THE INVARIANT; THE PUNCTUATION IS NOISE (2026-08-03, third time today).
# Live: `[MOOD-wistful, VO_ICE:flirty]` — a hyphen where the colon belongs and an
# underscore dropped into the middle of VOICE. It leaked whole onto his screen AND set
# neither value, so a mood she expressed simply did not happen.
#
# Each name is matched letter-by-letter with an optional separator between letters, which
# absorbs `VO_ICE`, `M O O D` and `TRA-IT` and cannot match a word that is not the name.
# The SEPARATOR may be `:` or `-`.
#
# THIS IS STILL STRICT WHERE IT COUNTS. The VALUE is validated exactly as before
# (`_mood_value`, `_ok`), so a garbled value still cannot move her; only a garbled
# WRAPPER is forgiven. Loose about how she spelled the envelope, strict about what is
# written inside it.
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
# ── ONE BUILDER, NOT TWO (2026-08-05) ────────────────────────────────────────────────
# This was a byte-identical copy of `stream_processor._loose_name`, and the nine widenings
# above were applied to BOTH by hand each time. AGENTS.md §0 in its plainest form: two
# implementations of "is this a mark", and the one that decides whether her mood actually
# MOVES is the one a fix would eventually miss. It did: `[MOOD_shift:playful]` leaked to
# his screen and set nothing, because `[a-z]*` cannot cross an underscore.
#
# Imported now. The DISPLAY side may be loose about spelling; this side stays strict about
# the VALUE (`_mood_value`, `_ok`), which is the rule this file has always lived by — but
# "what counts as the name" is one question and must have one answer.
from harness.inference.stream_processor import _loose_name as _lname  # noqa: E402


# `[...]` OR `<...>` — she uses both wrappers; live: `<TRAIT:+playful>`.
_MOOD = re.compile(r"[\[<]\s*(?:%s)\s*[:\-]([^\]>]+)[\]>]" % _lname("MOOD"), re.I)
_VOICE = re.compile(r"[\[<]\s*(?:%s)\s*[:\-]([^\]>]+)[\]>]" % _lname("VOICE"), re.I)
_TRAIT = re.compile(r"[\[<]\s*(?:%s)\s*[:\-]([+-]?)([^\]>]+)[\]>]" % _lname("TRAIT"), re.I)
# ── THE WARDROBE IS THE SAME SYSTEM (2026-08-02, the operator's call) ────────────────
# `[MOOD:]`/`[VOICE:]`/`[TRAIT:]` and what she is wearing are one thing wearing two
# coats: both are her PRESENTATION, both are hers to change mid-sentence, both drive the
# same portrait, and both belong on the same chip row. Keeping them apart meant two
# vocabularies, two renderers and two ideas of what she looks like — which is the
# divergence this repository is named for, arriving on schedule.
#
# So `[WEAR:lingerie]` and `[SHOW:silver-nightie]` are MARKS, not tools. A mark is free,
# inline and expressive; she changes what she is wearing the way she changes her mood,
# without a round trip and without announcing it.
#
# `ask_for` and `ask_for_gesture` STAY TOOLS, deliberately. They spend his money and a
# minute of the GPU, and a mark that quietly costs a dollar is the wrong shape — an
# action with a real cost and a queue should look like an action.
# ── AND THESE TWO NEVER GOT THE NINE WIDENINGS (2026-08-24) ─────────────────────────
# `_MOOD`/`_VOICE`/`_TRAIT` above are built from `_lname` and carry `re.I`. These two were
# literal, case-sensitive, colon-only — so `[Wear: the lace set]`, `[WEARing:...]` or
# `[WEAR - the lace set]` moved nothing at all, silently.
#
# It has not bitten yet, and that is the only reason it reads as pedantry: she had emitted
# `[WEAR:]` exactly ONCE and `[SHOW:]` five times in 1,241 turns, so there was almost no
# traffic to mis-spell. `render_state` now teaches both marks beside the mood mark, which
# is expected to multiply that traffic — and widening a recogniser AFTER the traffic
# arrives is how the other three came to need nine fixes in three weeks.
#
# The value group stays as it was: `+` for WEAR (a garment has a name) and `*` for SHOW,
# because `[SHOW:]` with nothing in it is the mark and its own undo.
_WEAR = re.compile(r"[\[<]\s*(?:%s)\s*[:\-]([^\]>]+)[\]>]" % _lname("WEAR"), re.I)
_SHOW = re.compile(r"[\[<]\s*(?:%s)\s*[:\-]([^\]>]*)[\]>]" % _lname("SHOW"), re.I)
# The strip regex that used to live here was a SECOND COPY of the one in
# stream_processor.py — and this is the copy that runs on the served path, so when the
# 26B started emitting `[TRAIТ:+flirty]` (Cyrillic Т) and unterminated tags, THIS is
# what failed to strip them and put a bare "[TRAI:flirty]" on screen as her whole reply.
# Fixing one copy would have fixed nothing. There is now one stripper, in
# stream_processor.strip_tags, and it is homoglyph- and truncation-tolerant.
#
# The RECOGNISERS above stay strict on purpose: they write persistent personality
# state, and a garbled tag must never be able to move her mood or her traits. Loose
# for display, strict for side effects.


# THE ONE PREDICATE FOR "DOES THIS REPLY CARRY A MARK". The spine's post-turn decider
# had its own regex — `[(?:MOOD|VOICE|TRAIT):[^\]]+]`, spelled out again — and so a reply
# whose only mark was `[WEAR:the lace set]` decided NOTHING and her clothes never moved.
# She was changing and the room was not. Fourth copy of one alphabet; this is the last.
_MARKS = (_MOOD, _VOICE, _TRAIT, _WEAR, _SHOW)


# ── WHAT MAY BE A TRAIT ───────────────────────────────────────────────────────────────
# A trait is a word for something she IS. Signs, brackets, markdown escapes and
# sentence fragments are none of those, and every one of them had got in: the live state
# on 2026-08-03 listed `+flirty` beside `flirty`, and `deeply\_connected` beside
# `deeply_connected`. She read that back as her own character every single turn.
_TRAIT_OK = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]{1,23}$")


_CRAMMED = re.compile(
    r"\[\s*((?:%s|%s|%s)\s*[:\-][^\]]*)\]" % (_lname("MOOD"), _lname("VOICE"), _lname("TRAIT")),
    re.I)
_INNER = re.compile(r"(?=(?:%s|%s|%s)\s*[:\-])" % (_lname("MOOD"), _lname("VOICE"), _lname("TRAIT")),
                    re.I)


def _split_crammed(reply: str) -> str:
    """`[MOOD:playful, VOICE:soft]` -> `[MOOD:playful] [VOICE:soft]`.

    SHE PUTS TWO MARKS IN ONE BRACKET, repeatedly and in every combination seen so far:
    `[MOOD:playful, VOICE:soft]`, `[MOOD-wistful, VO_ICE:flirty]`, `[MOOD:tender]
    [VOICE:soft/warm]`. The recognisers each match one bracket, so the FIRST name won and
    everything after the comma was swallowed into its value — the mood survived (it cuts at
    the comma) and the voice simply never happened.

    Splitting here, once, before anything reads the reply, means every recogniser
    downstream sees the well-formed shape and none of them needs to know about this. The
    split is keyed on a SECOND tag name appearing inside the brackets, so an ordinary
    value with a comma in it (`[VOICE:breathless, husky]`) is untouched — there is no tag
    name in it to split on."""
    def fix(m):
        body = m.group(1)
        parts = [p.strip().strip(",;").strip() for p in _INNER.split(body) if p.strip()]
        if len(parts) < 2:
            return m.group(0)
        return " ".join("[%s]" % p for p in parts)
    return _CRAMMED.sub(fix, reply or "")


def _mood_value(v: str) -> str:
    """The one mood she reached for, out of whatever shape the mark arrived in.

    COUNTED OVER ONE REAL DAY (2026-08-03): of 39 `[MOOD:]` marks she emitted, NINETEEN
    were stored as something the room has no face for, so her expression did not move.
    Two shapes, and neither is a typo worth refusing over:

        `[MOOD::tender]`          a stray leading colon           x8
        `[MOOD:wistful; naughty]` two moods at once               x7

    Strip what she leads with, take the FIRST of a compound — when she names two, the
    first is the one she reached for — and keep it a single word, because a mood is a KEY
    that gets looked up to choose a face. (A voice is not: it is only ever displayed, so
    it keeps its commas.) Mirrors `moodOf` in ui/src/room/tags.js; the two are one rule
    with two enforcement points, which is why they are written to the same shape."""
    #   `[MOOD-wistful, VO_ICE:flirty]`   two marks crammed into ONE bracket
    # A mood is a single word, so a comma ends it too. (A VOICE is descriptive and keeps
    # its commas — "breathless, husky" is one thing she said about how she sounds.) The
    # second mark inside that bracket is NOT recovered: it is one bracket as far as the
    # recogniser is concerned, and the mood is the half that drives her face.
    v = re.split(r"\s*[;/,]\s*", (v or "").strip().lstrip(":;,. ").strip())[0].strip()
    return v if re.match(r"^[A-Za-z][A-Za-z0-9 _-]{1,23}$", v) else ""


def expected_mood(raw: str) -> str:
    """What a captured [MOOD:...] value becomes ON DISK. THE derivation — the executor
    writes it and the verifier (spine.vf_persona) checks against it. The verifier used
    to compare the RAW capture to the cleaned write, so every repaired spelling this
    module went to the trouble of absorbing ([MOOD::tender] x8 in one day,
    [MOOD:wistful; naughty] x7) wrote correctly and then logged VERIFY_FAIL — and the
    failed verify suppressed the live persona chip event: the consumer branched on a
    value the producer could not produce, TRAPS §1's shape in the verify layer."""
    return _mood_value((raw or "").strip().strip("[]").strip())


def expected_voice(raw: str) -> str:
    """What a captured [VOICE:...] value becomes on disk. Same contract as expected_mood.

    ── AND THE ANGLE BRACKET CAME WITH IT (2026-08-24) ──────────────────────────────
    Live, in her persona.md, for days:

        voice: <soft; low-pitch

    An UNCLOSED angle bracket, stored as her voice. `_VOICE`'s value group is `[^\\]>]+`,
    so given `[VOICE:<soft; low-pitch>]` it captures everything up to the `>` it needs as
    a terminator — and the `<` she opened with rides along. This one strips `[]` and
    leading punctuation and never looked at `<`.

    IT IS NOT COSMETIC. `render_state` puts this line into the STANDING SYSTEM BLOCK, so
    every single turn she was shown a broken tag as an example of her own voice — and
    `</the_end`, `</the_hand`, `</low-pitch` are what she then wrote. Her own malformed
    output became her input, which is the same shape as the journal hall of mirrors and
    took just as long to see, because the leak looked like a stripper problem.

    So the wrapper comes off both ends: `<soft; low-pitch>` and `<soft; low-pitch` both
    become `soft; low-pitch`, and anything with an angle bracket still in it after that
    is refused outright rather than written down.
    """
    v = (raw or "").strip().strip("[]").strip().lstrip(":;,. ").strip()
    v = v.strip("<>").strip().lstrip(":;,. ").strip()
    return "" if ("<" in v or ">" in v) else v


def _norm(t: str) -> str:
    """Un-escape and trim one trait. Backslashes are markdown leaking in, not spelling."""
    return re.sub(r"\s+", " ", (t or "").replace("\\", "").strip().strip("+-[] ").strip())


def _ok(t: str) -> bool:
    return bool(_TRAIT_OK.match(t or ""))


def _dedupe_traits(items, cap: int = 12):
    """First spelling wins, case-insensitively, and there is a CAP. An uncapped list grows
    forever because adding is one mark and removing takes a deliberate `[TRAIT:-x]` she
    almost never writes — hers had reached ten and two were parse errors."""
    seen, out = set(), []
    for t in items:
        k = t.lower()
        if k in seen:
            continue
        seen.add(k); out.append(t)
    return out[:cap]


def carries_marks(reply: str) -> bool:
    """True if `apply_personality_tags` would do anything with this reply. Uses the STRICT
    recognisers, deliberately: the question "is there something to act on" and the question
    "what exactly" must never be answered by two different readers."""
    return any(rx.search(reply or "") for rx in _MARKS)


_MARKS_BY_NAME = (("mood", _MOOD), ("voice", _VOICE), ("trait", _TRAIT),
                  ("wear", _WEAR), ("show", _SHOW))


def marks_present(reply: str) -> frozenset:
    """WHICH mark families this reply carries — `carries_marks` with the names kept.

    Same recognisers, for the same reason `carries_marks` gives: "is there something to
    act on", "what exactly", and "which kind" must never be answered by three different
    readers. This is the third question and it now has the same owner as the other two.

    IT EXISTS FOR HER OWN TIME (2026-08-25). `solo_did_the_thing` rules on whether a solo
    act actually HAPPENED, and it could only see tool calls — while `persona.md` teaches
    the wardrobe as a MARK, in as many words: "[WEAR:the silver nightie] changes your
    clothes... No tool call, no asking, mid-sentence, whenever you mean it." So the one
    path she is told to use could not satisfy the one law that checks she used it, and the
    only thing that COULD satisfy it for the wardrobe act was `check_wardrobe` — a read.
    She looked in the wardrobe, said what she would wear, changed nothing, and the act was
    ruled performed."""
    text = reply or ""
    return frozenset(name for name, rx in _MARKS_BY_NAME if rx.search(text))


def _persona_path() -> str:
    from harness.personality.persona_file import persona_path
    return persona_path()          # ONE derivation — see persona_file.persona_path


def _wear_by_words(WD, want: str) -> None:
    """One matcher, shared with her `wear` tool — see wardrobe.match()."""
    m = WD.match(want)
    if not m:
        # ── A MARK THAT MATCHED NOTHING USED TO VANISH (2026-08-05) ─────────────────
        # `return` — and that was the whole of it. She wrote [WEAR: the green hoodie],
        # the matcher had no hoodie, and the mark evaporated: no change, no record, and
        # nothing anywhere that could ever tell either of them she had asked. His words
        # were "she has been attempting to use it in chats to show herself exactly as she
        # wants but they are not making it through" — and for anything she does not own,
        # this silent return WAS the not-making-it-through.
        #
        # The matcher is stricter now (it refuses instead of dressing her in whatever
        # shares a substring), so this branch is where most honest misses land. It must
        # not be a hole. An unowned want becomes a WANT: it appears in his wardrobe panel
        # as something she asked for, he can generate it, and then it matches. request()
        # already collapses exact repeats, so asking twice costs a row and not two.
        try:
            r = WD.request(want, made_in=(WD.current().get("outfit") or WD.DEFAULT_OUTFIT), by="her",
                           # She said WEAR. The clothes are the subject, so her words go
                           # in the wardrobe slot rather than underneath a tier that
                           # would put a second outfit in the same photograph.
                           subject="clothes")
            logging.getLogger(__name__).info(
                "[wear] nothing owned matches %r — filed as a want (%s)",
                want[:60], "already had it" if r.get("dup") else r.get("id", "new"))
        except Exception as exc:
            logging.getLogger(__name__).warning("[wear] could not file %r: %s", want[:60], exc)
        return
    if m["kind"] == "look":
        WD.choose(outfit=m["outfit"], look=m["id"], by="her")
    elif m["kind"] == "outfit":
        WD.choose(outfit=m["outfit"], look="", by="her")


def _show_by_words(WD, want: str) -> None:
    """`[SHOW:]` with nothing in it takes it down — the mark and its own undo."""
    if not (want or "").strip():
        WD.choose(clip="", by="her")
        return
    # SAME PREFERENCE AS THE TOOL. `[SHOW:]` and show_him() ask the identical question
    # and must get the identical answer; without `prefer` this resolved a clip's own
    # label to a LOOK (looks() is walked first) and then failed the kind check.
    m = WD.match(want, prefer="clip")
    if m and m["kind"] == "clip":
        WD.choose(clip=m["id"], by="her")


def apply_personality_tags(reply: str, persona_path: str = "",
                           act: bool = False) -> Tuple[str, Dict[str, str]]:
    """Persist [MOOD]/[VOICE]/[TRAIT] tags from a reply into the persona state; return the tag-
    STRIPPED reply + the resulting state. `[TRAIT:+x]` adds, `[TRAIT:-x]` removes, `[TRAIT:x]` adds.
    Best-effort: any error leaves the reply stripped and the state untouched.

    `act` — WHETHER THE MARKS THAT CHANGE THE WORLD ARE PERFORMED (2026-08-03).

    This function does two things that look alike and are not. Reading a mood off a reply
    is a READ: replay it a hundred times and the answer is the same. Performing `[WEAR:]`
    or `[SHOW:]` is an ACT: it moves her clothes, puts a clip on his screen, and writes a
    row to the worn log.

    The nightshift curator replays the WHOLE DAY'S assistant turns through here to extract
    the shifts she expressed — and so it was re-performing every wardrobe mark in the
    transcript, at 4am, in transcript order, last-one-wins. That produced the doubled rows
    in `worn.jsonl` (three wearings at 12:08:17, each twice) and, far worse, meant a REPLAY
    OF HER PAST could overwrite the outfit she is actually in — her own agency outranked by
    a recording of it.

    So acting is OPT-IN and defaults to off. A caller that forgets gets the harmless
    behaviour; only the live post-turn path, which is handling a reply that is being said
    for the first time, passes `act=True`. Fail closed, like everything else here."""
    path = persona_path or _persona_path()
    changed = False
    reply = _split_crammed(reply)
    try:
        text = Path(path).read_text(encoding="utf-8") if Path(path).exists() else ""
        _, state = parse_persona(text)
        # STRAY BRACKETS DO NOT BELONG IN HER STATE. She writes malformed marks —
        # observed live: `◆[smirk` — and the value was stored with the bracket still on,
        # so the portrait caption read "[smirk". The RECOGNISER stays strict (a garbled
        # tag must not move her); this only cleans the value it did accept.
        _clean = lambda v: v.strip().strip("[]").strip()
        moods = _MOOD.findall(reply)
        if moods:
            # expected_mood/expected_voice: THE derivation, shared with the verifier.
            state["mood"] = expected_mood(moods[-1]) or state.get("mood", ""); changed = True
        voices = _VOICE.findall(reply)
        if voices:
            # A VOICE KEEPS ITS COMMAS. "breathless, husky" is one description of how she
            # sounds, said three times in one day — not a list, and not junk.
            # `or state.get(...)` for the same reason the mood line above has it: a value
            # the sanitiser REFUSES (2026-08-24 — one with an angle bracket still in it)
            # must leave her voice as it was, not blank it. A guard that empties the field
            # it is protecting is worse than the malformed value it rejected.
            state["voice"] = expected_voice(voices[-1]) or state.get("voice", "")
            changed = True
        # HER TRAITS ARE THINGS SHE IS, NOT WHATEVER FELL OUT OF A MALFORMED MARK.
        # Live persona state on 2026-08-03, read back to her as her own identity every
        # turn: "curious, opinionated, playful, direct, flirty, +flirty, deeply_connected,
        # patient, naughty, deeply\_connected". Two of those are junk — a captured sign
        # that became a name, and a markdown-escaped duplicate of a trait already in the
        # list. She was being told she is both `flirty` and `+flirty`, which is not a
        # personality, it is a parse error wearing one.
        #
        # Strict at the WRITE boundary, loose nowhere: the same rule as the recognisers.
        # `_norm` un-escapes and trims; `_ok` refuses anything that is not plainly a word.
        traits = [t for t in (_norm(x) for x in state.get("traits", "").split(",")) if _ok(t)]
        traits = _dedupe_traits(traits)
        # ONE MARK CAN CARRY SEVERAL TRAITS. She writes `[TRAIT:+tender, +flirty]` — twice
        # in one day — and the regex captures the sign of the FIRST and everything else as
        # one blob, so `_ok("tender, +flirty")` refused the comma and BOTH were dropped.
        # The room's parser has always split trait bodies on commas; this one did not, so
        # the chip row showed two traits she never acquired. Same rule, both sides now:
        # split the body, and let each piece carry its own sign.
        for sign, raw in _TRAIT.findall(reply):
            for i, piece in enumerate(str(raw).split(",")):
                piece = piece.strip()
                if not piece:
                    continue
                s = sign if i == 0 else ""
                if piece[0] in "+-":
                    s, piece = piece[0], piece[1:]
                name = _norm(_clean(piece))
                if not _ok(name):
                    continue               # a trait she cannot be is not a trait
                if s == "-":
                    traits = [t for t in traits if t.lower() != name.lower()]
                elif name.lower() not in (t.lower() for t in traits):
                    traits.append(name)
                changed = True
        traits = _dedupe_traits(traits)
        if traits:
            state["traits"] = ", ".join(traits)
        # THE WARDROBE HALF, through the SAME door her tools use. wardrobe.choose is the
        # one writer, so a mark and a tool call cannot end up meaning different things —
        # and the ceiling still applies at read time, so a mark cannot exceed it either.
        # ACTS ONLY ON THE LIVE PATH — see `act` in the docstring.
        if act:
            try:
                from harness.control import wardrobe as _WD
                for raw in _WEAR.findall(reply):
                    _wear_by_words(_WD, raw.strip())
                shows = _SHOW.findall(reply)
                if shows:
                    _show_by_words(_WD, shows[-1].strip())
            except Exception:
                pass                   # a wardrobe that will not move must not eat a reply
        if changed:
            write_state(path, state)
        result_state = {k: state.get(k, "") for k in ("voice", "mood", "traits")}
    except Exception:
        result_state = {}
    # Imported here, not at module scope, to keep this module light (same reason the
    # interceptor base is imported lazily below).
    from harness.inference.stream_processor import strip_tags
    # `.strip()` HERE, not inside strip_tags: this is a whole reply, and the stripper
    # is also called per-chunk by the speech lane where trimming eats her spacing.
    return strip_tags(reply).strip(), result_state


# (`make_interceptor` was deleted 2026-08-24 with the harness/interceptors package it
# lazily imported — audit B4a: the whole pipeline was a complete, never-constructed
# second authority over persona.md, and this shim was its last consumer-less doorway;
# left standing it would have raised on first call. The recognisers above are the live
# machinery; the post-turn spine is the one writer.)
