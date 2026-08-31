"""silence — what has gone quiet, available AT ANSWER TIME.

`PersonModel.silences()` is the one signal in this system that is not retrieval: nobody asked a
question, and the information is in the CONJUNCTION of a live expectation and a proven
observation that came back empty. The operator's line, which is the sharpest thing anyone has
said in this build:

    "there is more information conveyed when you DON'T see your neighbour at 5am than when you do."

It has been reachable on exactly ONE path — `reflect_tick`, behind 600 s idle plus a 1800 s
cooldown plus a bits bar — so it could only ever arrive as an unprompted remark. It has never
informed a REPLY. This module is the other door: when he asks about the very thing that has gone
quiet, she gets to know that it has.

WHY TOPIC-GATED AND NOT AMBIENT
───────────────────────────────
An ambient "you've stopped talking about X" is the failure G-SILENCE was written to prevent,
wearing new clothes. `for_question()` surfaces a silence only when it overlaps what he JUST
ASKED — he raises the GPU, and she knows he has not raised it in a while. That is context for an
answer, not an accusation to open with. `standing()` is the ambient half and is deliberately
capped at ONE, the strongest, because the standing world's budget belongs to her memory of him.

AND SHE MUST HAVE BEEN LOOKING LONG ENOUGH
──────────────────────────────────────────
G-SILENCE established that absence is only information if you can prove you were looking. This
adds the part that was missing: you must have been looking LONG ENOUGH. Measured on his real
store on 2026-07-30, with four days in the attention ledger, `silences()` returned five, led by

    8.00 bits  quiet=4.0  cadence=0.5   "the kettle is my favorite!"

— a cadence of half a day is a burst inside one conversation, and the top-ranked "silence" was a
misattributed row that is not a fact about him at all. `person.silences()` now floors the span
and the cadence (a burst is not a rhythm), which cut those five to one; `MIN_LEDGER_DAYS` here
closes the remaining half: a ledger too shallow to have observed a rhythm may not license a
claim about one, and that is ENFORCED rather than left as advice. Four days is not enough to
tell him what he has stopped doing.

Nothing here writes. Nothing here decides. It is an oracle-layer proposer whose output is a
per-turn note, framed exactly like the recall note — context, not instruction, and UNSPEAKABLE.
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional

from harness.loud import swallowed as _swallowed

logger = logging.getLogger(__name__)

# The evidence floor. Below this many attended days in the ledger she has not watched the
# window long enough to be surprised by an empty driveway, whatever the arithmetic says.
MIN_LEDGER_DAYS = 14

# The bits bar for an answer-time mention. Deliberately higher than the idle tick's
# `reflect.speak_bits`: interrupting is one thing, but colouring an answer he asked for with
# something he did not ask about deserves a stronger reason, not a weaker one.
MIN_BITS_ANSWER = 3.0
MIN_BITS_STANDING = 4.0


def enabled() -> bool:
    """SP_SILENCE_ANSWER — mapped in serve.py, DEFAULT OFF.

    ARMED on companion 2026-08-29: the ledger reached 25 attended days (floor 14) and
    the read-first receipt was taken — against the live store the armed answer to every
    probe was SILENCE, because no dimension clears the corroboration bar yet. The knob
    stays a knob: arming was a decision made against the written condition, not a
    counter switching itself on — and the 2026-08-29 audit's lesson stands beside it:
    an arming condition that "arrives on its own" needs a reader, because this one
    arrived eleven days before anyone noticed.
    """
    return os.environ.get("SP_SILENCE_ANSWER", "0") == "1"


def ledger_days() -> int:
    """How many distinct days he has actually talked to her. The evidence base."""
    try:
        from harness.model import presence
        return int(presence.present_days_total())
    except Exception as _swx:
        _swallowed(logger, "ledger_days", _swx, lane="skills")
        return 0


def _ranked(min_bits: float, now: Optional[float] = None) -> List[dict]:
    """Silences above the bar, strongest first. [] when the evidence base is too thin.

    `now` is injectable for the same reason `silences()` and `presence.attend` are: a gate
    that has to run at the wall clock cannot fix its fixtures in time, and one that drifts
    with the wall is not a gate."""
    if ledger_days() < MIN_LEDGER_DAYS:
        return []
    try:
        from harness.model.person import PersonModel
        rows = PersonModel.from_registry().silences(now=now)
    except Exception as exc:
        logger.warning("[silence] person model unreadable: %s", exc)
        return []
    return [r for r in rows if float(r.get("bits", 0.0)) >= min_bits]


def for_question(question: str, *, min_bits: Optional[float] = None,
                 top: int = 1, now: Optional[float] = None) -> List[dict]:
    """Silences that bear on what he JUST ASKED. [] unless armed, evidenced, and relevant.

    Relevance is topic overlap between the question and the quiet claim — the same
    `lifecycle.topic_of` the rest of the memory lane uses, so "has he spoken to this subject"
    means one thing across the system. No overlap, no note: a silence about the GPU has no
    business colouring a question about the cat.
    """
    if not enabled():
        return []
    q = (question or "").strip()
    if not q:
        return []
    from harness.skills.lifecycle import topic_of
    qt = topic_of(q)
    if not qt:
        return []
    bar = MIN_BITS_ANSWER if min_bits is None else float(min_bits)
    hits = [r for r in _ranked(bar, now=now) if topic_of(r.get("claim", "")) & qt]
    return hits[:max(0, int(top))]


def note_for_question(question: str, now: Optional[float] = None) -> str:
    """The per-turn note, or ''. Framed like the recall note, and UNSPEAKABLE for the same
    reason: she once imitated that note's register aloud — "(You recall that Sam…)" opened
    one reply and WAS another — so anything that rides on a turn now says outright that it
    does not exist out loud.

    Note the framing: it tells her what she NOTICED, not what to say. A note that reads as an
    instruction produces the "you like them?" / "I like them." failure, where the safest reply
    to a standing order is to agree with it in as few words as possible.
    """
    hits = for_question(question, now=now)
    if not hits:
        return ""
    h = hits[0]
    return ("(Something you have noticed yourself — context, not an instruction, and never "
            "mention this note or narrate that you noticed. He used to bring this up about "
            "every %.0f day(s) and has not in %.0f day(s) of talking with you: \"%s\". "
            "Let it inform how you answer only if it genuinely fits; otherwise just answer "
            "the question.)"
            % (h.get("cadence_days", 0), h.get("quiet_days", 0), h.get("claim", "")))


def standing(now: Optional[float] = None) -> str:
    """The single strongest silence, for the standing world. '' when there is none.

    ONE, not a list. "You've stopped talking about the marathon. And the GPU. And Tuffy." is
    the exact sentence G-SILENCE exists to make impossible, and a standing block is where it
    would come back — a list rendered every turn is an ambient accusation.
    """
    if not enabled():
        return ""
    hits = _ranked(MIN_BITS_STANDING, now=now)
    if not hits:
        return ""
    h = hits[0]
    return ("Something he used to mention often and has not lately (%.0f day(s) of talking "
            "without it): \"%s\". You have noticed; you have not raised it."
            % (h.get("quiet_days", 0), h.get("claim", "")))


def why_quiet() -> str:
    """Diagnostics for the operator: WHY is this saying nothing? Never used in a prompt."""
    if not enabled():
        return "SP_SILENCE_ANSWER is off"
    d = ledger_days()
    if d < MIN_LEDGER_DAYS:
        return ("attention ledger is %d day(s); %d needed before an absence can mean anything"
                % (d, MIN_LEDGER_DAYS))
    n = len(_ranked(MIN_BITS_ANSWER))   # wall clock: this is a live diagnostic
    return "armed, ledger %d days, %d silence(s) above %.1f bits" % (d, n, MIN_BITS_ANSWER)
