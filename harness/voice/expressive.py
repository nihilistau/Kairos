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


def for_display(text: str) -> str:
    """The display edge: every voice tag gone, known or not, whitespace tidied."""
    t = _INLINE_ANY.sub("", text or "")
    t = _WRAP_ANY.sub("", t)
    return re.sub(r"[ \t]{2,}", " ", t).strip()


def for_tts(text: str, method: str = "xai") -> str:
    """The TTS edge. xai: known tags pass, unknown tag-shapes are removed. Anything
    else: every tag stripped — the local chain would read the brackets aloud."""
    if (method or "").strip().lower() != "xai":
        return for_display(text)
    t = _INLINE_ANY.sub(lambda m: m.group(0) if m.group(1) in INLINE else "", text or "")
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
