"""SELF-REPEAT GUARD — she may not say the same thing twice.

THE LIVE BUG (2026-07-12, operator transcript). Three different user messages, three
BYTE-IDENTICAL replies:

    you  07:41:16  "you can"
    her            "That's fascinating! I didn't realize that was a feature..."
    you  07:41:25  "you can"
    her            "That's fascinating! I didn't realize that was a feature..."     (identical)
    you  07:42:05  "I can influence mine a little bit, but i am human..."
    her            "That's fascinating! I didn't realize that was a feature..."     (identical)

and again four times running at 07:45-07:46.

NOT a stale prompt — the daemon log proves she saw the new words:
    S1 prompt ids: n=4563 ... 4672 ... 4781        (the prompt grows)
    PERSIST-KV: reuse 4705 of 4705; prefill suffix 76   (the new text is prefilled)
She read the new message and CHOSE to emit her previous reply verbatim. A degeneration
attractor: on a low-content turn ("you can", "cool huh?") the highest-probability
continuation is the thing she just said, and nothing stopped her.

WHY IT SURFACED NOW — AND WHY I AM NOT PUTTING THE OLD FIX BACK.
`no_repeat_ngram=3` used to make this impossible: it banned re-emitting ANY 3-token
sequence already in context, which included her own last reply. It was also strangling
the entire system — it banned her from quoting a number back (G-VERBATIM: she wanted '7'
at a logit margin of 9.0 and the sampler masked it, so "4471" came out "4417"). Turning
it off fixed memory, tools and persona, and unmasked this.

Both things are true. The old fix was a sledgehammer that happened to sit on this bug.
The right fix is narrow: she may not repeat HER OWN LAST MESSAGE. She may still quote the
user, quote a memory, quote a tool result, and say a number twice — all of which the
n-gram ban forbade.

Mechanism: detect, then RE-ROLL once with a nudge and some temperature. If the re-roll is
still a repeat, fall back to a short honest acknowledgement rather than parroting.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

_WORD = re.compile(r"[a-z0-9']+")


def _toks(s: str) -> list[str]:
    return _WORD.findall((s or "").lower())


def similarity(a: str, b: str) -> float:
    """Bag-of-words overlap, symmetric. 1.0 = she said exactly the same thing."""
    ta, tb = set(_toks(a)), set(_toks(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def is_self_repeat(reply: str, previous_reply: str, *, threshold: float = 0.85) -> bool:
    """Is this her previous message again? Short replies are exempted by length: "ok",
    "yeah", "haha" legitimately recur in conversation and are not degeneration."""
    r, p = (reply or "").strip(), (previous_reply or "").strip()
    if not r or not p:
        return False
    if len(_toks(r)) < 5:          # short acks may repeat; that is just talking
        return False
    if r == p:
        return True
    return similarity(r, p) >= threshold


REROLL_NUDGE = (
    "(You have just repeated your previous message almost word for word. Do not do that. "
    "Respond to what he ACTUALLY said this time — react to it, disagree, ask, or move the "
    "conversation on. Say something you have not already said.)"
)


def guard(
    reply: str,
    previous_reply: str,
    reroll: Optional[Callable[[str], str]] = None,
    *,
    threshold: float = 0.85,
) -> tuple[str, str]:
    """Returns (final_reply, note). `note` is '' when nothing was wrong — it is the
    receipt when we intervened, so the operator can see it happened."""
    if not is_self_repeat(reply, previous_reply, threshold=threshold):
        return reply, ""

    sim = similarity(reply, previous_reply)
    if reroll is None:
        return reply, f"self-repeat detected ({sim:.0%}) but no re-roll available"

    try:
        second = (reroll(REROLL_NUDGE) or "").strip()
    except Exception as exc:
        return reply, f"self-repeat ({sim:.0%}); re-roll failed: {exc}"

    if second and not is_self_repeat(second, previous_reply, threshold=threshold):
        return second, f"self-repeat ({sim:.0%}) -> re-rolled"

    # Still parroting. Do NOT ship the parrot: say something honest and short instead.
    # Silence-with-an-acknowledgement beats a model stuck in a loop, and it is visibly
    # different, so the operator can SEE the guard fired rather than wonder why she is odd.
    return ("(I've said that already — say more and I'll pick it up from there.)",
            f"self-repeat ({sim:.0%}); re-roll also repeated -> fell back")
