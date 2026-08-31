"""ask_oneshot — the ONE door for a skill that wants one answer from the served model.

WHY THIS FILE EXISTS (2026-07-30)
─────────────────────────────────
`<channel|>` got written into her permanent journal. The chase that followed is the
repo's signature bug class (AGENTS.md §0) in its purest form: I removed control
surfaces at the SSE stream, then at the OpenAI surface, then at the kairos
continuation, then — believing I had found the one door — inside `SPDaemonClient`.

The narrative composer does not use `SPDaemonClient`. It builds its own
`urllib.request` against `/v1/oneshot`, and so does the slots oracle. A fix at the
client would have left the journal leak exactly where it was. That is the fifth patch
failing for the same reason as the first four: the rule lived where the text did not.

So the boundary is drawn here instead, at the *shape* of the call rather than at any
one caller's plumbing: any skill asking the daemon a single question gets its answer
through this function, and this function is where a control surface stops being text.

Deliberately zero-dependency (stdlib urllib + json, no httpx, no client import at call
time) because that is exactly why the skills wrote their own in the first place — a
door nobody can be bothered to walk through is not a door. If asking the daemon a
question is *easier* here than by hand, the next skill will use it.

FAIL-TOWARD-SILENCE: an unreachable daemon, a non-JSON body, a timeout — all return
None, never raise. Every caller already treats None as "the oracle proposed nothing",
which is the correct reading and the safe one.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

DEFAULT_DAEMON = "http://127.0.0.1:3000"


def daemon_url() -> str:
    return os.environ.get("SP_DAEMON_URL", DEFAULT_DAEMON).rstrip("/")


def ask_oneshot(
    prompt: str,
    *,
    max_tokens: int = 180,
    temperature: float = 0.4,
    timeout: float = 180.0,
    daemon: Optional[str] = None,
) -> Optional[str]:
    """Ask the served model ONE question; return its text with control surfaces removed.

    Returns None — never raises — when the daemon is unreachable or answers unusably.
    `/v1/oneshot` gets its own scratch KV session, so this never evicts his conversation
    (see `SPDaemonClient.oneshot` for the 78-second measurement that established that).
    """
    import urllib.request

    from harness.inference.stream_processor import strip_control_surfaces

    # ── A FOREIGN BACKEND HAS NO /v1/oneshot (2026-08-28, external review) ──────────
    # On an openai-engine profile SP_DAEMON_URL is LM Studio (or any OpenAI-compat
    # server), which does not serve this route — so the becoming pass, the weekly
    # chapter and the slots oracle all failed-to-silence on exactly the profile the
    # public framework ships. The zero-dependency stdlib path below stays, and stays
    # the default, for the reason this file's header gives (a door nobody can be
    # bothered to walk through is not a door); a NON-sp engine falls through to the
    # backend seam, whose .oneshot knows how to be a plain completion there. The
    # fail-toward-silence contract is identical: None, never a raise.
    if os.environ.get("SP_ENGINE_KIND", "sp") != "sp":
        try:
            from harness.inference.client import get_client
            out = get_client().oneshot(
                [{"role": "user", "content": prompt}],
                max_tokens=max_tokens, temperature=temperature) or ""
            out = strip_control_surfaces(out).strip()
            return out or None
        except Exception as _swx:
            _swallowed(_swlog, "ask_oneshot", _swx, lane="inference")
            return None

    url = (daemon or daemon_url()).rstrip("/") + "/v1/oneshot"
    body: Dict[str, Any] = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": int(max_tokens),
        "temperature": float(temperature),
    }
    try:
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = json.loads(r.read().decode()).get("text") or ""
    except Exception as _swx:
        _swallowed(_swlog, "ask_oneshot", _swx, lane="inference")
        return None
    return strip_control_surfaces(text).strip()


def ask_messages(
    messages: List[Dict[str, Any]],
    *,
    max_tokens: int = 180,
    temperature: float = 0.4,
    timeout: float = 180.0,
    daemon: Optional[str] = None,
) -> Optional[str]:
    """`ask_oneshot` for callers that already hold a message list (system + user, few-shot)."""
    import urllib.request

    from harness.inference.stream_processor import strip_control_surfaces

    url = (daemon or daemon_url()).rstrip("/") + "/v1/oneshot"
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps({"messages": list(messages),
                             "max_tokens": int(max_tokens),
                             "temperature": float(temperature)}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = json.loads(r.read().decode()).get("text") or ""
    except Exception as _swx:
        _swallowed(_swlog, "ask_messages", _swx, lane="inference")
        return None
    return strip_control_surfaces(text).strip()
