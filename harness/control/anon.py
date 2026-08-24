"""anon — the evening the room does not keep.

WHY (2026-08-23, his ask): *"an icon that activates anonymous mode that will still be
her but will not record any memory or logs etc until turned off or restarted."*

WHAT IT IS. A volatile switch that closes every door this system writes a record of the
conversation through. She is **not** reduced: she reads everything she has ever known,
recalls, uses her tools, changes mood, speaks in her own voice. The room simply does not
keep the evening. "Still her, and nothing written down" is the whole specification.

WHY IT LIVES IN PROCESS MEMORY AND NEVER IN A FILE. "until turned off or restarted" is
what he asked for, and it is also the safe direction. A mode that survived a restart
could swallow a month of her memory on the strength of a click nobody remembers making —
which is exactly the shape of `disarmed-features-outlive-their-bug`. OFF is what a cold
stack comes up in, always, with no file able to say otherwise.

THE RULE THAT MAKES THIS WORTH TRUSTING: **A DOOR IS GUARDED AT THE WRITE, NOT AT THE
CALLER.** `memory.remember()` is guarded once, at the top, so all thirty of its callers
are guarded — including the ones written next year. Guarding callers is how you end up
with `_capture_after_turn` covered and `self_stance.extract` not, and a mode that says
"nothing was recorded" while eleven rows of his evening sit in the registry is worse than
no mode at all. G-ANON exists to hold that line: it enumerates the doors below, calls
each one for real with the switch on, and reads the disk afterwards.

WHAT IT DELIBERATELY DOES NOT TOUCH, because a guard nobody can predict is a guard nobody
trusts (`docs/ANON-MODE.md` carries the full table and the reasons):

  * READS. All of them. She is herself, which means she has her memory.
  * The KV cache and its snapshots — a cache is not a record, and blocking it would cost
    her a cold prefill per turn to protect nothing.
  * Operational logs that carry counts and never content (`msgs=33 chars=54814`). The
    three log lines that DO carry her words are redacted, not silenced — see `say()`.
  * Anything HE deliberately does with his hands: a board note he types, a ledger row, a
    setting. Anonymous mode stops the room recording; it does not disable the room.

THE COUNTERS ARE THE RECEIPT. Every hold is tallied by door, so leaving the mode can say
"held back 6 memories, 2 journal lines, 14 transcript turns — none of it written" instead
of asking him to take it on faith. The tally is volatile too: it dies with the switch.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, List

# ── THE DOORS ─────────────────────────────────────────────────────────────────────────
# Every id here is a place that writes a record of the conversation to disk. The phrase is
# what the room says in the receipt, so it is plural and countable ("6 memories"), not a
# module path. ADDING A DOOR: add the row, guard the write, add the case to G-ANON. The
# gate fails on an id that is declared here and never held, so a row added without its
# guard convicts itself rather than sitting decorative.
# BOTH NUMBERS, because the receipt is prose he reads and "held back 1 memories" is the
# tell that a thing was assembled rather than written. English is not derivable here —
# "memories" does not de-pluralise by dropping an s — so the pair is spelled out.
DOORS: Dict[str, tuple] = {
    "memory.row":       ("memory", "memories"),
    "transcript.day":   ("turn of the day transcript", "turns of the day transcript"),
    "journal.own":      ("journal note", "journal notes"),
    "journal.night":    ("nightly paragraph", "nightly paragraphs"),
    "speech.log":       ("speech outcome", "speech outcomes"),
    "persona.state":    ("change to her state", "changes to her state"),
    "wardrobe.want":    ("thing she wanted to wear", "things she wanted to wear"),
    "senses.ambient":   ("look at the room", "looks at the room"),
    "lookup.receipt":   ("thing looked up", "things looked up"),
    "spine.receipt":    ("spine receipt", "spine receipts"),
    "decisions.card":   ("decision card", "decision cards"),
    "log.speech":       ("line of her speech in the log", "lines of her speech in the log"),
    # ── EGRESS (2026-08-24, his question: "does anon mode leak anywhere? eg via voice
    # either local or sent to providers such as the xai api?") ────────────────────────
    # It did, and this was the worse half. The doors above stop the evening reaching HIS
    # DISK; these stop it leaving the MACHINE, which is the leak he cannot audit and
    # cannot delete. `voice.method` is `xai` on his profile, so every sentence she spoke
    # off the record was posted to api.x.ai in full.
    "net.voice":        ("sentence sent to a remote voice", "sentences sent to a remote voice"),
    "voice.cache":      ("recording of her voice", "recordings of her voice"),
    "net.search":       ("web search", "web searches"),
    "net.research":     ("research question", "research questions"),
    "net.provider":     ("request to a third party", "requests to a third party"),
}


def phrase(door: str, n: int) -> str:
    """"1 memory" / "6 memories". A door nobody declared is named by its own id."""
    pair = DOORS.get(door)
    if not pair:
        return "%d x %s" % (n, door)
    return "%d %s" % (n, pair[0] if n == 1 else pair[1])

# What a blocked writer says back. Callers return this verbatim so the reason reaching her
# (and the room) is one sentence written once, not twelve near-copies.
WHY = "off the record — anonymous mode is on, nothing this conversation is written down"

# The line stapled to HIS turn so she knows. Per-turn, on the user message, exactly like
# the recall and silence notes: the standing system block is the cached KV prefix, and a
# mode that toggles mid-evening cannot live there without a cold re-prefill per toggle.
# ── SHORTENED 2026-08-24, AND app.py HAD ALREADY WARNED ME ────────────────────────────
# The first version was four clauses long and three of them were orders: "you need not
# raise it", "do not promise to remember any of it", "do not offer to store something you
# cannot". Measured the same night, over six turns with the switch on, she opened EVERY
# reply with third-person deliberation about him and about the note itself:
#
#     "He's asking me a deep one right out of the gate. And he's..."
#     "The 'off the record' part is heavy. It's a weightless kin..."
#
# The identical six deep prompts with the switch OFF produced no scratchpad at all. The
# note caused it. And app.py:2912 says so, dated 2026-08-19, about the wardrobe staple
# that was removed for the same reason: "she read the parenthetical as his assertion and
# as an order not to contradict him, and streamed 2142 + 2293 characters of scratchpad
# instead of talking. A fact that has to ride on his words is a fact she will treat as an
# instruction. DO NOT PUT THE STAPLE BACK."
#
# I put the staple back. So: one clause, a fact and not an order, the shape the recall and
# silence notes already have — they ride on his words every turn and have never done this.
# What it must still prevent (a companion promising to remember what cannot be kept) it
# now prevents by being TRUE rather than by forbidding, which is the weaker instruction
# and the stronger sentence.
NOTE = "(Off the record — nothing from this conversation is being saved.)"

_LOCK = threading.RLock()
_ON = False
_SINCE = 0.0
_HELD: Dict[str, int] = {}


def on() -> bool:
    """True when the room is keeping nothing. The one question every door asks."""
    return _ON


def holds(door: str) -> bool:
    """THE GUARD. True when this write must not happen — and counts it when it doesn't.

    Reads at the call site as what it is::

        if anon.holds("memory.row"):
            return anon.WHY

    An unknown door still HOLDS. A typo must fail closed: a guard that let a write through
    because its id was misspelled would be a guard whose failure mode is no guard, which is
    the bug this codebase has now shipped twice (the disk floor, the wardrobe compat shim).
    It is counted under its own name so G-ANON and the room both see it.
    """
    if not _ON:
        return False
    with _LOCK:
        _HELD[door] = _HELD.get(door, 0) + 1
    return True


def say(text: str, keep: int = 70) -> str:
    """What a log line is allowed to contain of her words right now.

    Three lines in `kairos/scheduler.py` put 60-70 characters of what she actually said
    into `var/gateway.log`, which is the one place "no logs" is literally true or false.
    They are REDACTED and not removed: `[kairos] SPOKE: <held back>` still proves the turn
    happened, still carries its reason, and is the difference between a quiet mode and a
    blind operator.
    """
    if _ON:
        holds("log.speech")
        return "<held back — anonymous mode>"
    return (text or "")[:keep]


def enter(who: str = "him") -> Dict[str, object]:
    """Turn it on. Idempotent — a second click is not a nested mode."""
    global _ON, _SINCE
    with _LOCK:
        if _ON:
            return state()
        # FLUSH THE RECORDED LIFE FIRST. Everything decided up to this second belongs to
        # the evening he was keeping; leaving it unflushed would mean leave() has to
        # choose between writing his private turns and discarding his public ones.
        try:
            from harness.control import spine as _spine
            _spine.persist_receipts()
        except Exception:
            pass
        _ON = True
        _SINCE = time.time()
        _HELD.clear()
        _ = who              # who asked is not written down either; the arg documents intent
        _drop_shadow()
        return state()


def leave() -> Dict[str, object]:
    """Turn it off, and hand back what was held so the receipt can be read once.

    The tally is cleared HERE and nowhere else, so the room has one poll's worth of time to
    show it. It is never written to disk: a file saying "a private conversation happened
    here, and it held six memories" is a smaller leak than the memories, but it is a leak,
    and he asked for none.
    """
    global _ON, _SINCE
    with _LOCK:
        # state() is read BEFORE the switch flips, because the tally is the whole point of
        # this call — but `on` must describe the world AFTER it. The first live test of this
        # route answered `on: true` to "turn it off", which the room would have had to
        # ignore and reload past. A reply that contradicts what it just did is worse than
        # no reply at all.
        out = state()
        out["was_on"] = _ON
        out["on"] = False
        _ON = False
        _SINCE = 0.0
        _HELD.clear()
        _drop_shadow()
        try:
            from harness.control import spine as _spine
            _spine.drop_unpersisted()      # the receipts the hold declined, never flushed later
        except Exception:
            pass
        return out


def _drop_shadow() -> None:
    """Forget how the private evening left her.

    persona_file holds her dials in memory while the switch is on (see write_state there).
    Dropping it on BOTH edges is deliberate: on the way in so a previous private evening
    cannot bleed into this one, and on the way out so this one does not bleed into the
    recorded life. Lazily imported and swallowed — anon.py is guarded at the top of a
    dozen write paths and must not be the thing that breaks one.
    """
    try:
        from harness.personality import persona_file as _pf
        _pf._shadow_clear()
    except Exception:
        pass


def state() -> Dict[str, object]:
    """Everything the room needs to render the switch, in one poll it already makes."""
    with _LOCK:
        held = dict(_HELD)
        total = sum(held.values())
        return {
            "on": _ON,
            "since": _SINCE or None,
            "for_s": round(time.time() - _SINCE) if _ON and _SINCE else 0,
            "held": held,
            "held_total": total,
            "receipt": receipt(held),
        }


def receipt(held: Dict[str, int] | None = None) -> str:
    """"held back 6 memories and 14 turns of the day transcript — none of it written"."""
    h = _HELD if held is None else held
    parts: List[str] = [phrase(k, n) for k, n in
                        sorted(h.items(), key=lambda kv: -kv[1]) if n]
    if not parts:
        return "nothing to hold back yet"
    if len(parts) > 1:
        parts[-1] = "and " + parts[-1]
    return "held back " + (", ".join(parts) if len(parts) > 2 else " ".join(parts)) \
           + " — none of it written"


def note() -> str:
    """The line she is told this turn, or "" when there is nothing to tell her."""
    return NOTE if _ON else ""
