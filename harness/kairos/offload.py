"""KAIROS PRE-JUDGE — the sidecar rules "worth a turn?" BEFORE the GPU pays for one.

THE WASTE THIS REMOVES, measured 2026-08-20 morning: her idle loop fired a full
26B turn every 60-90 s (60-110 s of prefill each, GPU pinned at 99%/84°C), and the
gates that decide whether the result is worth SAYING — worth_saying(),
solo_did_the_thing() — run AFTER generation. Every dropped impulse was a minute of
GPU heat that bought silence. The 1.2B sidecar answers the same YES/NO in under a
second on CPU, so the question moves to the front: no 26B work unless the impulse
survives a cheap ruling.

THE BOUNDARIES, because this changes who judges her impulses:
  * FAIL OPEN. A dark sidecar or a non-answer (judge() -> None) means the impulse
    PROCEEDS exactly as before this module existed. Infra failure must never
    silence her — a quiet bug here looks identical to her losing interest in him.
  * REMINDERS ARE NEVER GATED. He asked; she keeps her word. The scheduler does
    not even call this for REMIND (and the gate asserts it).
  * The sidecar rules ONLY "would speaking now likely add something" — it never
    sees or shapes WHAT she says. If it says yes, everything downstream (her
    words, worth_saying, the solo evidence rule) is unchanged.
  * Per-action knob: SP_KAIROS_JUDGE=1 arms it; SP_KAIROS_JUDGE_ACTIONS names the
    actions it may rule on (default: the four discretionary ones).

A/B READS FROM THE LOG: every ruling logs action, verdict and latency —
`[kairos] sidecar pre-judge` lines against the day's TURN-PHASE cadence is the
whole experiment.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

from harness.loud import swallowed as _swallowed

logger = logging.getLogger(__name__)

_DEFAULT_ACTIONS = "check_in,solo,expand,muse"


def enabled() -> bool:
    """Panel choice first (aux.judge_kairos), else the profile env — registry.tune_or_env."""
    try:
        from harness.tuning import registry as _tr
        v = _tr.tune_or_env("aux.judge_kairos", "SP_KAIROS_JUDGE", "0")
        return v is True or str(v) == "1" or str(v).lower() == "true"
    except Exception as _swx:
        _swallowed(logger, "enabled", _swx, lane="kairos")
        return os.environ.get("SP_KAIROS_JUDGE", "0") == "1"


def gated_actions() -> set:
    raw = os.environ.get("SP_KAIROS_JUDGE_ACTIONS", _DEFAULT_ACTIONS)
    return {a.strip() for a in raw.split(",") if a.strip()}


def pregate(action: str, reason: str, tail: str) -> Optional[bool]:
    """Rule whether an unprompted `action` is worth a 26B turn right now.

    True  -> proceed (and None/any failure ALSO proceeds — fail open).
    False -> skip the generation entirely; the scheduler records the drop.

    `reason` is the impulse's own audit line ("quiet for 271s and ..."); `tail`
    is the last thing said in the session, so the judge can spot "she just spoke
    unprompted a minute ago and nothing has changed since"."""
    if not enabled():
        return None
    if action == "remind":                 # promises are not judged, ever
        return None
    if action not in gated_actions():
        return None
    try:
        from harness.sidecar import client
    except Exception as _swx:
        _swallowed(logger, "pregate", _swx, lane="kairos")
        return None
    if not client.available():
        return None
    # ── SHE MUST SEE HER OWN RECENT ATTEMPTS (2026-08-20 10:40, the A/B's verdict) ──
    # Nine rulings, nine YES, and twice in that window the approved turn generated a
    # full 26B reply that worth_saying binned as "100% a restatement" — then the judge
    # approved the SAME check-in again 30 s later. A gatekeeper that cannot see the
    # last three knocks approves every knock. The speech log is the receipt of her
    # recent unprompted behavior; it goes in the prompt, and a recent unanswered or
    # dropped attempt is named as the NO case.
    recent = ""
    try:
        from harness.kairos import speechlog as _sl
        rs = _sl.rows(limit=50)[-4:]
        if rs:
            recent = "\n".join(
                "- [%s] %s -> %s%s" % (r.get("at", "?"), r.get("kind", "?"),
                                       r.get("outcome", "?"),
                                       (" (%s)" % r.get("reason")) if r.get("outcome") == "dropped" else "")
                for r in rs)
    except Exception as exc:
        from harness.kairos import swallowed as _sw
        _sw(logger, "offload.pregate recent-speech", exc)
        recent = ""
    q = (
        "You are a quiet gatekeeper for an AI companion's unprompted messages. "
        "Her operator is away or idle; the system proposes she takes an "
        "unprompted turn now.\n\n"
        "Proposed action: %s\nSystem's reason: %s\n\n"
        "Her own most recent unprompted attempts (newest last):\n%s\n\n"
        "The last thing said in this conversation was:\n---\n%s\n---\n\n"
        "Would an unprompted '%s' from her RIGHT NOW likely add something new "
        "and be welcome? Answer NO if her recent unprompted messages went "
        "unanswered, were dropped as repetitive, or came within the last few "
        "minutes — piling on reads as needy, and a dropped attempt means she "
        "already has nothing new to say. A first gentle word after a long true "
        "quiet, with no recent attempts above, is the YES case."
        % (action, (reason or "(none)")[:200], recent or "(none — she has not "
           "spoken unprompted recently)", (tail or "(nothing yet)")[-600:],
           action)
    )
    t0 = time.monotonic()
    verdict = client.judge(q)
    ms = (time.monotonic() - t0) * 1000.0
    if verdict is None:
        logger.info("[kairos] sidecar pre-judge: no ruling (%.0f ms) — failing open", ms)
        return None
    logger.info("[kairos] sidecar pre-judge: %s -> %s (%.0f ms, CPU)",
                action, "worth a turn" if verdict else "not worth a turn", ms)
    return verdict
