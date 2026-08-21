"""watcher.py — stop a generation that has come off the rails, mid-stream.

SALVAGED FROM CosySim's `engine/pipeline/` (stream_watcher.py + kill_switch.py),
which is the best idea in that codebase per line: watch the tokens as they arrive
and abort the ones that are going nowhere, instead of waiting for a finished
paragraph of nonsense.

NOT A DUPLICATE OF repeat_guard. They catch different failures at different moments
and neither subsumes the other:

    repeat_guard   ACROSS turns — she emitted her previous reply verbatim. Post-hoc,
                   and it re-rolls.
    watcher        WITHIN one generation — this reply is degenerating right now.
                   Mid-stream, and it stops.

THE EVIDENCE IS FROM TODAY, all of it real output from this stack:

    "develooper-mode-enabler-enabler-enabler-enthoughtersmautleringly-..."
    "Deny-ed Deny-ed Deny-ed Deny-ed Deny-ed ..."
    "doppel doppel doppel doppel doppel doppel ..."
    "line-work-work; thoughtful-thoughtful-thoug"
    "- un de forma-seja-sólo-una-de-las-opciones ownleserelation-propiedad-..."

Every one of those ran to the token limit. The operator watched them arrive. A
sampler fix (repetition_penalty) helps and did not prevent any of these, because by
the time a generation is looping the sampler has already lost — the loop IS the
high-probability continuation.

WHAT IT DELIBERATELY DOES NOT DO. CosySim's version also runs a second MODEL as a
watcher (a fine-tuned Gemma 270M) for intent classification and quality scoring.
Not ported: on this box the 2060 is Gemma's, entirely, and this morning proved what
happens when something else takes 2 GB of it — a CUDA fault that took the daemon
down. Rules only. They are free, they are deterministic, and they catch every
example above.

FAIL TOWARD LETTING HER TALK. Every threshold is deliberately loose. A watcher that
truncates a good answer is far worse than one that lets a bad answer finish: the
first breaks something that was working, the second wastes tokens she was going to
waste anyway. When in doubt this returns None.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Optional

ARMED = os.environ.get("SP_WATCHER", "1") != "0"

# Trigram repeats before we call it a loop. CosySim used 3. Ours is looser because
# real prose repeats short phrases legitimately ("I think that", "one of the") and
# this stack has a persona that circles back on purpose.
NGRAM_LIMIT = int(os.environ.get("SP_WATCHER_NGRAM", "6"))
# Below this many words nothing is judged. A short answer has no room to loop, and
# early judgement is how you truncate "yes." into nothing.
#
# 20, NOT 40 — set from the fixtures rather than from taste. Four of the five real
# degenerations captured today were SHORTER than 40 words ("Deny-ed" x30, the hyphen
# salad at ~20, "I cannot see the picture." x6 at 30), so a 40-word floor sailed
# straight past the actual evidence. The specific checks below are unambiguous
# enough not to need the length cushion: no genuine sentence repeats one word five
# times in a row, and the longest good reply in the fixtures has no run at all.
MIN_WORDS = int(os.environ.get("SP_WATCHER_MIN_WORDS", "20"))
# A single token repeated back to back — "Deny-ed Deny-ed Deny-ed". Distinct from
# n-gram repetition and much more obviously terminal.
RUN_LIMIT = int(os.environ.get("SP_WATCHER_RUN", "5"))
# The run check has its OWN floor, much lower than MIN_WORDS. "no no no no no" is
# five identical words and is perfectly ordinary emphasis — a person writes that and
# means it. "encontrado" six times inside fourteen words is not. 12 admits both real
# fixtures (17 and 14 words) and spares the emphatic case, which is the only place
# these two collide.
RUN_MIN_WORDS = int(os.environ.get("SP_WATCHER_RUN_MIN_WORDS", "12"))


@dataclass
class Verdict:
    kill: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.kill


OK = Verdict(False)


def _repeated_ngram(words: list) -> Optional[str]:
    """The classic loop: the same three words, over and over."""
    if len(words) < MIN_WORDS:
        return None
    grams = [" ".join(words[i:i + 3]) for i in range(len(words) - 2)]
    if not grams:
        return None
    gram, n = Counter(grams).most_common(1)[0]
    if n >= NGRAM_LIMIT:
        return f"the phrase {gram!r} {n} times"
    return None


def _stuck_token(words: list) -> Optional[str]:
    """The same word, consecutively — 'doppel doppel doppel'.

    Checked separately from n-grams because it is unambiguous: no sentence repeats
    one word five times in a row and means it."""
    run, prev, worst, worst_w = 1, None, 1, ""
    for w in words:
        if w == prev:
            run += 1
            if run > worst:
                worst, worst_w = run, w
        else:
            run, prev = 1, w
    if worst >= RUN_LIMIT:
        return f"{worst_w!r} {worst} times in a row"
    return None


def _same_sentence(text: str) -> Optional[str]:
    """Three identical sentences in a row — a longer-period loop."""
    parts = [s.strip() for s in re.split(r"[.!?\n]+", text) if len(s.strip()) > 8]
    if len(parts) >= 3 and parts[-1] == parts[-2] == parts[-3]:
        return f"the same sentence three times ({parts[-1][:40]!r})"
    return None


def check(accumulated: str) -> Verdict:
    """Judge a partial generation. Cheap enough to call on every flush.

    Order is deliberate: the unambiguous checks run first so the REASON given is
    the most specific one available. An operator reading 'the phrase X 6 times'
    when the real problem was one token stuck learns less."""
    if not ARMED:
        return OK
    text = accumulated or ""
    words = text.split()
    # A LITERAL RUN NEEDS NO LENGTH FLOOR. MIN_WORDS exists so that STATISTICAL
    # measures (n-gram frequency) are not computed over too little text — but a
    # token repeated five times consecutively is not a statistic, it is a fact, and
    # it is degenerate at any length. Two of the five real fixtures were under 20
    # words ("encontrado" x6, the enabler/building salad at 17) and the floor was
    # sailing straight past them.
    stuck = _stuck_token(words) if len(words) >= RUN_MIN_WORDS else None
    if stuck:
        return Verdict(True, stuck)
    if len(words) < MIN_WORDS:
        return OK
    for probe in (_same_sentence(text), _repeated_ngram(words)):
        if probe:
            return Verdict(True, probe)
    return OK


def note(reason: str) -> str:
    """What replaces the truncated tail.

    SHE SAYS SO HERSELF rather than the text simply stopping. A reply that ends
    mid-word looks like a crash and invites him to wonder what went wrong; a reply
    that says it got stuck is the truth and is also just what a person would say."""
    return " … (I was starting to repeat myself, so I stopped.)"


def status() -> dict:
    return {"armed": ARMED, "ngram_limit": NGRAM_LIMIT, "min_words": MIN_WORDS,
            "run_limit": RUN_LIMIT, "run_min_words": RUN_MIN_WORDS}
