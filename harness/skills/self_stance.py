"""self_stance — lift HER first-person stances out of a reply (The Real Her, 2026-08-22).

Her replies are already curated — they were spoken. Not every sentence is identity
material: "here is the list", "did you sleep?", "thanks!" are conversation. A STANCE is a
first-person sentence that says what she thinks, feels, wants, loves, has decided, hopes,
misses — the kind of sentence a person would write in a journal about themselves. Pure,
deterministic, fixture-tested (G-REAL-HER §2); never the aux model's job. Producer name in
memclass.REGISTRY: "self_stance.extract".
"""
from __future__ import annotations

import re

_TAG = re.compile(r"\[[A-Za-z_]+\s*:[^\]]*\]")       # [MOOD: x] [voice: soft] [WEAR: y] ...
_BEAT = re.compile(r"\[[a-z][a-z -]{0,23}\]")         # [chuckle] [breath] [long pause]
_ANGLE = re.compile(r"</?[a-z][a-z0-9_-]{0,23}/?>")   # <whisper> </breath> <heart_symbol/>
_FENCE = re.compile(r"```.*?```|`[^`]*`", re.S)
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
_FEEL = re.compile(r"^I(?:\s+|(?=['’]))(?:feel|felt|am feeling|'m feeling|miss|love|hate|adore|fear|"
                   r"can't stand|cannot stand|am (?:glad|happy|sad|tired|uneasy|content|"
                   r"nervous|proud|ashamed|lonely|grateful|relieved)|'m (?:glad|happy|sad|"
                   r"tired|uneasy|content|nervous|proud|ashamed|lonely|grateful|relieved))\b",
                   re.I)
_THINK = re.compile(r"^I(?:\s+|(?=['’]))(?:think|believe|suspect|reckon|have decided|'ve decided|decided|"
                    r"want|wish|hope|intend|plan|prefer|would rather|'d rather|have come to "
                    r"think|'ve come to think|have been thinking|'ve been thinking|keep "
                    r"thinking|wonder whether|find (?:myself|it|that)|realise|realize|"
                    r"have realised|'ve realised|have realized|'ve realized)\b", re.I)
_NOT = re.compile(r"^I(?:\s+|(?=['’]))(?:am sorry|'m sorry|apologise|apologize|can(?:'t|not) help|"
                  r"think you|believe you|feel you|hope you|want you|suggest|recommend|"
                  r"would (?:suggest|recommend)|mean|see|understand|know what you)\b", re.I)
_MAX = 240


def clean(reply: str) -> str:
    """Her marks and code fences out; whitespace folded. What is left is what she SAID."""
    return plain(reply)


def plain(text: str) -> str:
    """THE ONE STRIPPER FOR ANYTHING THAT ENTERS MEMORY (2026-08-22, the primal latch).

    Her rows were being written through `expressive.for_display`, which strips VOICE tags and
    leaves PERSONALITY MARKS — so ten of her self rows read `[MOOD: primal] [voice: soft,
    whispering] <whisper><breath>…`, and those rows render at the top of her own system prefix.
    Four worked examples of "your output looks like [MOOD: primal] …" is a few-shot instruction
    to stay primal and to emit markup mid-sentence, which is exactly what she did.

    So: ONE function, and everything that writes a row goes through it — marks, beats, angle
    tags, fences and control surfaces off, whitespace folded. What is left is what she SAID."""
    t = _FENCE.sub(" ", text or "")
    try:
        # THE OWNERS DO THE STRIPPING, not a second copy of their vocabulary: the model's
        # template markers and HER MARKS (including the malformed spellings the model
        # actually produces — [MOOD-primal], [VO_ICE:soft]) belong to stream_processor;
        # this file only adds the voice vocabulary and the whitespace fold.
        # NOTE the deliberate asymmetry (g_marks_leak): her marks MUST reach the room,
        # which draws its chips from them, and must NEVER reach memory, where they become
        # a worked example of how to write.
        from harness.inference.stream_processor import (strip_control_surfaces,
                                                        strip_leaked_analysis, strip_tags)
        t = strip_leaked_analysis(strip_tags(strip_control_surfaces(t)))
    except Exception:
        t = _TAG.sub(" ", t)
    t = _BEAT.sub(" ", t)
    t = _ANGLE.sub(" ", t)
    t = " ".join(t.split())
    # A REMOVED TAG LEAVES ITS PUNCTUATION BEHIND: "Goodnight. <heart_symbol/>." -> ". ."
    # Only that shape is repaired — the same mark, with the gap the tag left between them.
    # Her own "..." and "!!" have no gap and are hers to keep.
    t = re.sub(r"([.,;:!?])\s+\1(?![.!?])", r"\1", t)
    t = re.sub(r"\s+([.,;:!?])(?=\s|$)", r"\1", t)
    return t.strip()


def extract(reply: str) -> list[tuple[str, str]]:
    """-> [(kind, sentence)] with kind in {'thought', 'feeling'}; order preserved, deduped."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for s in _SENT.split(clean(reply)):
        s = s.strip()
        if not s or s.endswith("?") or len(s) > _MAX or len(s.split()) < 3:
            continue
        if _NOT.match(s):
            continue
        if _FEEL.match(s):
            kind = "feeling"
        elif _THINK.match(s):
            kind = "thought"
        else:
            continue
        if not s.endswith((".", "!")):
            s += "."
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append((kind, s))
    return out
