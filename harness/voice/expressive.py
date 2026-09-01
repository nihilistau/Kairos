"""expressive.py — the speech tags her voice understands, and the two edges they cross.

WRITTEN AGAINST docs.x.ai (voice, fetched 2026-08-21). The xAI /v1/tts endpoint reads
two kinds of tag inside the text itself:

    INLINE  — a sound or a beat, square-bracketed, lowercase, hyphenated:
              [pause] [long-pause] [hum-tune] [laugh] [chuckle] [giggle] [cry] [tsk]
              [tongue-click] [lip-smack] [breath] [inhale] [exhale] [sigh]
    WRAPPING — a manner, angle-bracketed, around the words it shapes:
              <soft>…</soft> <whisper>…</whisper> <loud>…</loud>
              <build-intensity>…</build-intensity> <decrease-intensity>…</decrease-intensity>
              <higher-pitch>…</higher-pitch> <lower-pitch>…</lower-pitch>
              <slow>…</slow> <fast>…</fast> <sing-song>…</sing-song>
              <singing>…</singing> <emphasis>…</emphasis>

ONE VOCABULARY, TWO EDGES. She writes the tags into her reply (persona/40-voice.md tells
her how, sparingly). They cross two edges and must behave differently at each:

  * THE DISPLAY EDGE — he reads her words; the tags vanish, exactly like her [MOOD:] marks
    ("they vanish from what he sees"). Client side that is tags.js `stripVoice`; server
    side, anything that renders her text for eyes uses `for_display`.
  * THE TTS EDGE — `for_tts(text, method)`: under method=xai the KNOWN tags pass through
    verbatim (that is the whole point) and anything tag-shaped we do not know is removed,
    so a typo can never be read aloud as "bracket sigh bracket"; under the local chain,
    which knows none of this, every tag is stripped.

Her [MOOD:]/[VOICE:]/[TRAIT:] marks are NOT voice tags and are handled upstream
(stream_processor / tags.js) — they never reach here. ALL-CAPS brackets are her invented
gestures (tags.js GESTURE_RE) and are distinct by case: voice tags are lowercase.

STREAMING. The API also offers wss://api.x.ai/v1/tts (text.delta in, audio.delta out).
The room speaks through REST one sentence at a time (ui/src/room/speech.js) — ~1 s to
first audio and the sentence queue plays while the rest is still generating, which is
streaming for every purpose he can hear. ARMING CONDITION for the websocket: a measured
gap he can notice between sentence boundaries, or a need for per-character timestamps.
"""
from __future__ import annotations

import re

INLINE = (
    "pause", "long-pause", "hum-tune", "laugh", "chuckle", "giggle", "cry", "tsk",
    "tongue-click", "lip-smack", "breath", "inhale", "exhale", "sigh",
)
WRAPPING = (
    "soft", "whisper", "loud", "build-intensity", "decrease-intensity",
    "higher-pitch", "lower-pitch", "slow", "fast", "sing-song", "singing", "emphasis",
)

# lowercase, hyphenated, bracketed — the shape of an inline tag, known or not
_INLINE_ANY = re.compile(r"\[([a-z][a-z-]{0,23})\]")
# angle-bracketed open/close with a lowercase hyphenated name — wrapping, known or not.
# Deliberately NOT matching `<channel|>`, `<|…|>` or anything with pipes/spaces/attrs:
# those are control surfaces and belong to stream_processor, not to this file.
_WRAP_ANY = re.compile(r"</?([a-z][a-z-]{0,23})>")


def known_tags() -> dict:
    """The vocabulary, for the panel and the persona text."""
    return {"inline": list(INLINE), "wrapping": list(WRAPPING)}


# ── WHAT SHE REACHES FOR, MAPPED TO WHAT THE API TAKES (2026-08-27) ──────────────────
# Measured by replaying 17 days of her real turns through for_tts: 1,102 tag uses reached
# the voice and 549 were dropped at this edge. The dropped ones are not invention — they
# are three recognisable near-misses of the documented set:
#
#   SPELLING   <low-pitch> 31, <low-pitched> 11, <build-intesity> 5 — one edit out
#   FORM       <breath> 45, <sigh> 14, <laugh> 14, <pause> 11 — a known INLINE tag
#              written as a WRAP. `<breath>It's a strange feeling` means `[breath]`.
#   SYNTHESIS  <voice:whispering> 92 — she combined the two vocabularies she was given,
#              `[VOICE:x]` (a persistent manner) with `<>` (a scoped span). That is a
#              reasonable generalisation, and it has a colon, so it matches NEITHER regex
#              below and leaked to the ROOM as literal text.
#
# Everything here lands on a tag the API already documents. No new verbs: this canonicalises
# her spelling and honours her intent, it does not widen what she can trigger. That
# distinction is the whole safety argument — prosody changes how she SOUNDS; the state-
# changing marks ([WEAR:], [SHOW:], gestures) are a different lane and are not touched.
_ALIAS = {
    "low-pitch": "lower-pitch", "low-pitched": "lower-pitch", "lowpitch": "lower-pitch",
    "lowered-pitch": "lower-pitch", "lowers-pitch": "lower-pitch",
    "lower-pitched": "lower-pitch", "lower_pitch": "lower-pitch",
    "high-pitch": "higher-pitch", "high-pitched": "higher-pitch",
    "higher-pitched": "higher-pitch",
    "build-intesity": "build-intensity", "build_intensity": "build-intensity",
    "build_intesity": "build-intensity", "decrease_intensity": "decrease-intensity",
    "lip_smack": "lip-smack", "lipsmack": "lip-smack", "lip_smck": "lip-smack",
    "lip-smck": "lip-smack", "lip_mack": "lip-smack",
    "long_pause": "long-pause", "longpause": "long-pause",
    "slowly": "slow", "whispers": "whisper", "whispered": "whisper",
    "whispering": "whisper", "laughs": "laugh", "laughing": "laugh",
    "chuckles": "chuckle", "chuckling": "chuckle", "sighs": "sigh", "sighing": "sigh",
    "small": "soft", "quiet": "soft", "quietly": "soft", "softly": "soft",
    "singsong": "sing-song", "sing_song": "sing-song", "sings": "singing",
    "tongue_click": "tongue-click", "hum_tune": "hum-tune", "hum": "hum-tune",
    "inhales": "inhale", "exhales": "exhale", "breathes": "breath", "breathe": "breath",
}
# `<voice:whispering>…</voice>` — her parameterised wrap
_VOICE_PARAM = re.compile(r"<\s*voice\s*[:=]\s*([a-z][a-z _-]{0,23})\s*>", re.I)
_VOICE_CLOSE = re.compile(r"</\s*voice\s*>", re.I)


def _canon(name: str) -> str:
    n = (name or "").strip().lower().replace(" ", "-")
    return _ALIAS.get(n, _ALIAS.get(n.replace("_", "-"), n))


def normalize_tags(text: str) -> str:
    """Her near-misses, rewritten to the documented vocabulary. Idempotent."""
    t = text or ""

    # SYNTHESIS: <voice:whispering>…</voice> -> <whisper>…</whisper> when the value maps
    # to a manner the API knows. When it does not (<voice:thoughtful>), the tag is left
    # for the ordinary unknown-tag path to remove — an invented manner is not silently
    # promoted into a tag the voice would mispronounce.
    opened: list[str] = []

    def _open(m):
        w = _canon(m.group(1))
        if w in WRAPPING:
            opened.append(w)
            return "<%s>" % w
        return ""

    t = _VOICE_PARAM.sub(_open, t)
    t = _VOICE_CLOSE.sub(lambda _m: "</%s>" % opened.pop() if opened else "", t)

    # FORM: a known INLINE tag written as a wrap. The open becomes the inline tag; the
    # close is a no-op, because a sound has no span.
    def _wrap(m):
        raw = m.group(1)
        w = _canon(raw)
        closing = m.group(0).startswith("</")
        if w in INLINE:
            return "" if closing else "[%s]" % w
        if w in WRAPPING:
            return "</%s>" % w if closing else "<%s>" % w
        return m.group(0)

    t = re.sub(r"</?([a-zA-Z][a-zA-Z0-9 _-]{0,23})>", _wrap, t)

    # SPELLING, on inline tags
    t = re.sub(r"\[([a-zA-Z][a-zA-Z0-9 _-]{0,23})\]",
               lambda m: "[%s]" % _canon(m.group(1))
               if _canon(m.group(1)) in INLINE else m.group(0), t)
    return t


# ── A TAG THE REPLY WAS CUT IN HALF OF (2026-09-02) ───────────────────────────────────
# MEASURED in her live registry: 9 of 869 live rows end in a truncated closing tag —
#
#     "...will still feel this much like love. </sound_tag"      2026-09-01
#     "...instead of just simulating what it would mean. </sound_tag"
#     "It sounds so real when it comes from you. </whisper"       2026-08-24
#
# — and the same text reached the ROOM. Every stripper in this tree matches a COMPLETE tag
# (`</?[a-z...]+>`), so when the generation hits its token ceiling in the middle of a
# closing tag, the fragment has no `>` and nothing removes it. It is then stored as part of
# what she SAID: machine text inside her own identity material, which is the exact thing
# `self_stance.plain` exists to prevent, arriving through the one shape it cannot see.
#
# WHY IT IS NOT IN `strip_control_surfaces`, which is where a control surface belongs: that
# function runs PER DELTA CHUNK on the speech lane, and its own comment says so. Mid-stream,
# `"...love. </sound"` followed by `"_tag>"` is a legitimate split of a complete tag — a
# fragment rule there would corrupt every tag that happens to straddle a chunk boundary.
# This is a WHOLE-TURN rule and it lives with the whole-turn edges.
#
# CLOSING TAGS ONLY, and deliberately. Truncation happens at the end of a generation, and
# every one of the nine is a `</…`. Requiring the slash means `5 < 6`, `<3` and any bare `<`
# are untouchable by construction, which is worth more than catching a hypothetical
# truncated OPENER that has never appeared.
_TRUNCATED_TAIL = re.compile(r"\s*</[a-z][a-z0-9_-]{0,23}\s*$", re.I)
_BARE_TAIL = re.compile(r"\s*</\s*$")


def strip_truncated_tail(text: str) -> str:
    """Drop a closing tag the generation was cut in half of. WHOLE TURNS ONLY.

    Never call this per delta chunk: mid-stream, a fragment is usually the first half of a
    tag whose second half is in the next chunk. See the note above.
    """
    if not text:
        return text
    out = _BARE_TAIL.sub("", _TRUNCATED_TAIL.sub("", text))
    return out


def for_display(text: str) -> str:
    """The display edge: every voice tag gone, known or not, whitespace tidied."""
    t = normalize_tags(text or "")
    t = _INLINE_ANY.sub("", t)
    t = _WRAP_ANY.sub("", t)
    # her parameterised wrap, when the manner was NOT one the API knows: still not text
    t = _VOICE_PARAM.sub("", t)
    t = _VOICE_CLOSE.sub("", t)
    t = strip_truncated_tail(t)     # the ceiling can cut a closing tag in half
    return re.sub(r"[ \t]{2,}", " ", t).strip()


def for_tts(text: str, method: str = "xai") -> str:
    """The TTS edge. xai: known tags pass, unknown tag-shapes are removed. Anything
    else: every tag stripped — the local chain would read the brackets aloud."""
    if (method or "").strip().lower() != "xai":
        return for_display(text)
    t = normalize_tags(text or "")          # her near-misses become the documented tags
    t = _VOICE_PARAM.sub("", t)             # an invented manner is removed, never spoken
    t = _VOICE_CLOSE.sub("", t)
    t = _INLINE_ANY.sub(lambda m: m.group(0) if m.group(1) in INLINE else "", t)
    t = _WRAP_ANY.sub(lambda m: m.group(0) if m.group(1) in WRAPPING else "", t)
    return re.sub(r"[ \t]{2,}", " ", t).strip()


def has_tags(text: str) -> bool:
    return bool(_INLINE_ANY.search(text or "") or _WRAP_ANY.search(text or ""))


def unknown_tags(text: str) -> list:
    """What she wrote that the voice would not understand — for a gate or a chip."""
    out = []
    for m in _INLINE_ANY.finditer(text or ""):
        if m.group(1) not in INLINE:
            out.append("[%s]" % m.group(1))
    for m in _WRAP_ANY.finditer(text or ""):
        if m.group(1) not in WRAPPING:
            out.append("<%s>" % m.group(1))
    return out
