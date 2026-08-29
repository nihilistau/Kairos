"""context — the prompt has a hard ceiling, and nothing was counting.

THE NIGHT THIS EXISTS FOR (2026-08-23, 05:18–05:20 local). Three messages of his in a
row came back as silence. The daemon log says exactly what happened, three times:

    05:18:22  S1 prompt ids: n=12200 ... BATCH-PREFILL declined (exceeds Pmax) -> per-token
    05:18:37  S1 prompt ids: n=12300 ... exceeds Pmax
    05:19:44  S1 prompt ids: n=12400 ... exceeds Pmax        <- his message

`pmax` was 12096 on this profile that night (raised to 20000 on 2026-08-23 by the tiled
decode/prefill kernels — the guard below reads the live value and does not care which).
Every one of those returned an EMPTY stream in ~11 ms;
the gateway saw no words and printed the only notice it has for a wordless turn — "she
was still thinking when the ceiling stopped her" — which named the 128-token THINK budget
for a failure of the CONTEXT budget. Then the watchdog counted three empty generations,
concluded the CUDA context was wedged, and restarted the stack. It was not wedged. The
restart happened to help only because it reseeded the session with 8 rows.

WHY NOTHING CAUGHT IT. `_CHAT_SESSIONS_MAX = 32` caps the number of SESSIONS, not the
turns inside one, and the room resends its entire scrollback on every send (Chat.jsx
`const history = [...turns...]`). So a long evening walks the prompt up 100–400 tokens a
turn until it crosses 12096, and from that moment forward every further message makes it
worse. Typing more is the one thing that cannot help.

WHAT THIS DOES. Counts the prompt at the one door to the engine and drops the OLDEST
conversation turns until it fits, keeping the system prefix and the newest turns. That is
a loss and it is named out loud in the room rather than absorbed silently — a companion
who quietly forgets the first half of the evening while appearing to remember it is worse
than one who says "the first six turns are out of my reach now".

THREE THINGS THAT MAKE IT SAFE:

  1. THE SYSTEM PREFIX IS NEVER DROPPED. It is msgs[0] — persona + tools, ~7 973 tokens of
     the budget, and it is also the KV prefix the whole snapshot machinery is built on.
     Dropping it would cost a cold prefill AND change who she is. At the 12096 ceiling it
     was 66% of the budget — the real reason that night ran out of room so fast; at the
     2026-08-23 ceiling of 20000 it is ~40%, still the single largest consumer, and
     `prefix_tokens()` below is the instrument that keeps that number measured rather
     than asserted.
  2. THE ESTIMATE OVER-COUNTS, ALWAYS. There is no tokenizer on this side of the wire (the
     daemon owns it and exposes no /v1/tokenize), so this counts characters. MEASURED
     against three live prompts on 2026-08-23, from the gateway's own [DAEMON-CALL] line
     paired with the daemon's `S1 prompt ids: n=`:

         msgs=2   chars=30959  ->  n=7973    (3.883 chars/token)
         msgs=4   chars=32467  ->  n=8353    (3.887)
         msgs=34  chars=48718  ->  n=12400   (3.929)

     Dividing by 3.6 and adding 6 tokens of template per message therefore over-estimates
     by 8–11% on every one of them, which is the direction that is safe: an under-estimate
     is the silence this file exists to stop. G-CONTEXT-FIT holds those three samples.
  3. IT TRIMS IN A CHUNK, NOT A TOKEN AT A TIME. Trimming to exactly the limit would move
     the trim point every single turn, and the trim point is where the KV prefix match
     ends — so every turn would re-prefill the whole conversation. Trimming down to
     TRIM_TO of the budget leaves several turns of headroom, so the kept window is STABLE
     and the next turns extend it normally.

WHAT IS DELIBERATELY NOT COVERED. `/v1/oneshot` — the judge, the summariser, the
classifier. It opens its OWN scratch session sized to its own prompt and never touches the
resident cache, so it cannot walk into the conversation's ceiling; and its prompts are
~1 450 tokens by construction. Guarding it would be a rule with no failure behind it.

THE HOLE THAT IS LEFT, NAMED. `pmax` here is the profile's value. The engine's autofit
(gemma4_kv_open) may clamp it DOWN at boot to whatever VRAM was actually free, and it
prints the effective number as `(Pmax=NNNN)` in var/daemon.log — which is why this reads
that line when it can find it. If the log is unavailable the profile value stands, and a
clamped daemon could still be over its real ceiling with this guard satisfied. THE PROPER
FIX is the daemon reporting effective pmax in /v1/metrics; that is Rust and a rebuild.
ARMING CONDITION for deleting the log-scrape: `pmax` present in the /v1/metrics payload.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

# The profile default (profiles/*.toml `pmax`), used when serve.py's env is absent —
# a gate, a test or an import outside the served stack.
PMAX_DEFAULT = 12096

# Chars per token, deliberately BELOW every measured value (3.883 / 3.887 / 3.929) so the
# estimate errs high. Plus a flat per-message allowance for the chat template's own
# tokens (`<start_of_turn>user\n` and its closer), which the character count cannot see.
CHARS_PER_TOKEN = 3.6
PER_MSG_TOKENS = 6

# How much of the budget to trim down to when the ceiling is hit. 0.80 of ~11 300 leaves
# roughly 2 200 tokens — six to ten turns at the sizes measured that night — before the
# window has to move again. See point 3 above.
TRIM_TO = 0.80

# The sticky cut (see fit()): (role, content fingerprint) of the first kept message from
# the last fresh cut, KEYED BY CONVERSATION (2026-08-29 audit, B6). One process-wide slot
# served every session — his chat, her kairos lane, the OpenAI mouth — and each fresh cut
# overwrote the others' marker, so two long conversations clobbered each other into a
# full re-prefill per turn: the exact 235/222/207 s failure the sticky was written to
# end, resurrected by the singleton. The key is the conversation's FIRST message (the one
# row that never changes for a session); a bounce clears the table, a miss falls through
# to a fresh cut, and the table is capped so abandoned sessions cannot grow it forever.
_STICKY_CUTS: dict = {}
_STICKY_MAX = 64

# THE BUDGET THE STICKY TEST SEES MUST NOT FLIP MID-TURN (2026-08-29 audit, B7, observed
# live): budget() subtracts the caller's max_tokens, and the answering round bumps
# 120→512 — a window sized in the band between them passed the test on one call of a
# turn and failed on the next, and the re-cut cost an 8,160-token boundary drop (82
# messages of her memory) over a knob that has nothing to do with context. fit()
# reserves at least this floor, so both rounds of a turn measure the same budget.
STICKY_HEADROOM_FLOOR = 768


def reset_sticky() -> None:
    """Forget every cut marker. Called at the day boundary and the operator refresh:
    the canons are rebuilt from the durable transcript with the SAME message contents,
    and yesterday's marker matching a row in the rebuilt canon would cut history that
    fits (2026-08-29 audit, B12)."""
    _STICKY_CUTS.clear()


def _fp(m) -> str:
    import hashlib
    return hashlib.md5((m.get("content") or "").encode("utf-8", "replace")).hexdigest()[:12]

# What the reply needs. The ceiling is on POSITIONS, not on the prompt: prompt + generated
# must both fit under pmax. The last turn that worked that night went in at 11 864 and
# came out at exactly 12 096 with `eot_margin=-17.855` — she was cut off mid-sentence by
# the same ceiling, one turn before it stopped her entirely.
DEFAULT_REPLY_HEADROOM = 768


def _pmax_from_daemon_log() -> Optional[int]:
    """The EFFECTIVE pmax the engine reported at boot, or None.

    `WIRE-CUDA-DECODE: ... OK on TARGET session (Pmax=12096)` is printed once per daemon
    start, AFTER autofit has clamped it. The last one in the file is the running one.
    Any failure at all returns None and the caller falls back to the profile value —
    an instrument that can throw is worse than one that can be absent."""
    try:
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), "var", "daemon.log")
        with open(path, "rb") as f:                      # the tail only: it is ~30 MB
            f.seek(0, os.SEEK_END)
            back = min(f.tell(), 2_000_000)
            f.seek(-back, os.SEEK_END)
            blob = f.read().decode("utf-8", "replace")
        hits = re.findall(r"\(Pmax=(\d+)\)", blob)
        return int(hits[-1]) if hits else None
    except Exception:
        return None


def pmax() -> int:
    """The position ceiling this stack is actually running under."""
    try:
        env = int(os.environ.get("SP_DAEMON_KVDECODE_PMAX", "") or PMAX_DEFAULT)
    except ValueError:
        env = PMAX_DEFAULT
    live = _pmax_from_daemon_log()
    # NEVER RAISE on the log. autofit only ever clamps DOWN, so a log value above the
    # profile means the log is stale (a previous profile), not that we have more room.
    return min(env, live) if live else env


def est_tokens(msgs: List[Dict[str, Any]]) -> int:
    """A deliberate OVER-estimate of what the daemon will tokenize this into."""
    chars = sum(len(m.get("content") or "") for m in (msgs or []))
    return int(chars / CHARS_PER_TOKEN) + PER_MSG_TOKENS * len(msgs or [])


def prefix_tokens(system_content: str) -> int:
    """The system prefix's estimated token cost — the single largest consumer of the
    ceiling, and until 2026-08-24 the only one with NO instrument on it: the ~7 973
    figure above was hand-measured once into a docstring and nothing ever computed it
    again ("measure the thing, not the proxy", unarmed). Same estimator as est_tokens,
    so the number is comparable with what fit() budgets against."""
    return est_tokens([{"role": "system", "content": system_content or ""}])


def budget(reply_headroom: int = DEFAULT_REPLY_HEADROOM,
           limit: Optional[int] = None) -> int:
    return max(1, (limit if limit is not None else pmax()) - max(0, reply_headroom))


def fit(msgs: List[Dict[str, Any]],
        reply_headroom: int = DEFAULT_REPLY_HEADROOM,
        limit: Optional[int] = None) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Return (messages that fit, trim record or None).

    The record — `{"dropped", "kept", "before", "after", "budget"}` — is what the room is
    told. None means nothing was dropped, which must stay the common case: a guard that
    fires every turn is a window, and a window that silently slides is the failure mode
    this file is named after, not the fix for it."""
    msgs = list(msgs or [])
    b = budget(max(int(reply_headroom or 0), STICKY_HEADROOM_FLOOR), limit)
    before = est_tokens(msgs)
    if before <= b or len(msgs) <= 2:
        return msgs, None

    head = msgs[:1] if (msgs[0].get("role") == "system") else []
    tail = msgs[len(head):]
    target = max(1, int(b * TRIM_TO))

    # ── THE CUT IS STICKY, OR EVERY TURN PAYS FOR IT (2026-08-28, live) ──────────────
    # The evening his conversation first crossed pmax, this function re-cut newest-first
    # on EVERY call — so each turn kept a slightly different window (23 dropped, then 23,
    # then 26...), the front of the prompt shifted, and the daemon's committed KV found
    # no seam: PERSIST-KV RESEAM refused (drop 437), the rewind fell to the full-prefill
    # floor, and every turn re-prefilled ~10,300 tokens at 20 ms/tok. MEASURED: 235.4 s,
    # 222.5 s, 207.4 s per ordinary turn — which he reported as the gateway itself frozen,
    # because a four-minute reply and a hang are indistinguishable from the room.
    #
    # So once a cut exists, LATER CALLS CUT AT THE SAME MESSAGE for as long as the window
    # still fits the full budget. The window's front is then byte-stable across turns, the
    # seam holds, and the cost of a moving boundary is paid once per genuine overflow —
    # TRIM_TO's slack (20% of budget, several thousand tokens) is what buys the dozen-odd
    # quiet turns between cuts. The marker is the first kept message's identity, not an
    # index: prepended or vanished history (a bounce, a different session) simply misses
    # and falls through to a fresh cut.
    _skey = (tail[0].get("role"), _fp(tail[0])) if tail else None
    _marker = _STICKY_CUTS.get(_skey)
    if _marker is not None:
        idx = next((i for i, m in enumerate(tail)
                    if (m.get("role"), _fp(m)) == _marker), None)
        if idx is not None and idx > 0:
            kept = head + tail[idx:]
            # A KEPT WINDOW STARTS WITH HIM on this path too (2026-08-29, B10): the
            # fresh cut popped leading non-user rows and the sticky return did not.
            while len(kept) > len(head) + 1 and kept[len(head)].get("role") != "user":
                kept.pop(len(head))
            after = est_tokens(kept)
            if after <= b:
                return kept, {"dropped": len(msgs) - len(kept), "kept": len(kept),
                              "before": before, "after": after, "budget": b,
                              "sticky": True}

    # Newest first, stopping before the target — but ALWAYS keeping the last message,
    # which is what he just said. If his own message alone does not fit, sending it and
    # letting the engine refuse is still better than us refusing on his behalf: the
    # refusal is at least visible in a log he can be pointed at.
    keep: List[Dict[str, Any]] = []
    total = est_tokens(head)
    for m in reversed(tail):
        cost = est_tokens([m])
        if keep and total + cost > target:
            break
        keep.append(m)
        total += cost
    keep.reverse()

    # A KEPT WINDOW STARTS WITH HIM. Leading with one of her replies gives her an answer
    # to a question that is no longer there, and reads to the template as a turn out of
    # order. Drop leading non-user rows — never to empty.
    while len(keep) > 1 and keep[0].get("role") != "user":
        keep.pop(0)

    out = head + keep
    if _skey is not None and keep:
        if len(_STICKY_CUTS) >= _STICKY_MAX and _skey not in _STICKY_CUTS:
            _STICKY_CUTS.pop(next(iter(_STICKY_CUTS)))
        _STICKY_CUTS[_skey] = (keep[0].get("role"), _fp(keep[0]))
    return out, {"dropped": len(msgs) - len(out), "kept": len(out),
                 "before": before, "after": est_tokens(out), "budget": b}


def notice(rec: Dict[str, Any]) -> str:
    """One line for the room. Says what was lost and why, in his terms."""
    n = int(rec.get("dropped") or 0)
    return ("the thread was trimmed to fit her context: %d older %s dropped "
            "(~%d of %d tokens). She has the recent turns and her memory, not the "
            "start of this conversation."
            % (n, "turn" if n == 1 else "turns",
               int(rec.get("after") or 0), int(rec.get("budget") or 0)))
