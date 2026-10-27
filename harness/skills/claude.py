"""claude.py — ONE transport for the Anthropic API: key, client, one `ask()`.

WRITTEN 2026-10-21 beside xai.py and in its register: every Claude feature (research,
search, consult) reaches api.anthropic.com through THIS door, so one guard covers every
one of them including the ones added next year. Receipts are the CALLER's job; this
module does transport, not bookkeeping.

THE KEY IS A FILE, NEVER A VALUE. SP_CLAUDE_KEY_FILE points at var/secrets/claude.txt
(ignored; this repo is public). SP_CLAUDE_API_KEY, when set in the host environment,
outranks the file — the same announced HOST_KEYS exception the xAI key has.

THE AMBIENT ENVIRONMENT IS IGNORED ON PURPOSE. The SDK would quietly read
ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL if we let it. Her machine is also the operator's
dev box, where those variables belong to other tools — and a stray ANTHROPIC_BASE_URL
would send her questions to a host nobody chose. So the client is always built with
`api_key=` and `base_url=` passed explicitly; neither ambient variable is read here.
The only base-url override is SP_CLAUDE_BASE_URL.

BUT THE SDK READS A THIRD ONE REGARDLESS: ANTHROPIC_CUSTOM_HEADERS (anthropic/_client.py)
is folded into the client's default headers even when api_key= and base_url= are explicit
(proved 2026-10-21 with a recording transport). A launching shell's value would ride every
request to api.anthropic.com. So _default_factory masks it out of os.environ for the
instant of construction (under a lock), and serve.py's build_env drops every ANTHROPIC_*
from the gateway env besides. Two doors, because either alone is one launch path short.

A DEAD PATH NEVER RAISES INTO HER MOUTH. Every failure comes back as Reply(ok=False)
with the reason in last_error() — no SDK, no key, anonymous mode, a refusal, a
rate limit, a dead network. The key is scrubbed from that text.

Request shape (docs fetched 2026-10-21): no `thinking` (adaptive is the default on every
model used), `output_config={"effort": ...}` set explicitly, never `budget_tokens`, never
a forced `tool_choice`, never an assistant prefill. Server-side refusal fallback rides
only on the three models that support it, never on Haiku.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

BASE_URL = "https://api.anthropic.com"

FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_MAX_RESUMES = 3          # pause_turn: the server paused a long turn; we may continue it
_MAX_SOURCES = 8


_SDK_MOD: Any = None
_ENV_LOCK = threading.Lock()


def _sdk() -> Any:
    """The anthropic module, or None when the optional extra is not installed. A seam:
    the gate swaps it to prove the 'no sdk' leg without uninstalling anything.

    An ABSENT SDK is a normal state, not a fault (2026-10-21): panels poll this every
    8 s, and ImportError is in loud.OURS, so logging it was one WARNING per poll
    forever. find_spec answers 'absent' silently; any other failure still logs. A
    successful import is cached."""
    global _SDK_MOD
    if _SDK_MOD is not None:
        return _SDK_MOD
    try:
        import importlib.util
        if importlib.util.find_spec("anthropic") is None:
            return None
        import anthropic
        _SDK_MOD = anthropic
        return anthropic
    except Exception as _swx:
        _swallowed(_swlog, "_sdk", _swx, lane="skills")
        return None


def _default_factory(key: str, base_url: str) -> Any:
    import anthropic
    # ANTHROPIC_CUSTOM_HEADERS is read by the SDK constructor whatever api_key=/base_url=
    # say; mask it for the construction only, restore it after (see module docstring).
    with _ENV_LOCK:
        hidden = os.environ.pop("ANTHROPIC_CUSTOM_HEADERS", None)
        try:
            return anthropic.Anthropic(api_key=key, base_url=base_url, max_retries=2)
        finally:
            if hidden is not None:
                os.environ["ANTHROPIC_CUSTOM_HEADERS"] = hidden


# (key, base_url) -> client. Test seam; the default builds the real SDK client.
_CLIENT_FACTORY: Callable[[str, str], Any] = _default_factory


def api_key() -> str:
    """SP_CLAUDE_API_KEY first (announced HOST_KEYS), then the key FILE. Never
    ANTHROPIC_API_KEY."""
    k = (os.environ.get("SP_CLAUDE_API_KEY") or "").strip()
    if k:
        return k
    p = os.environ.get("SP_CLAUDE_KEY_FILE", "")
    if not p:
        _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        p = os.path.join(_root, "var", "secrets", "claude.txt")
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    except Exception as _swx:
        _swallowed(_swlog, "api_key", _swx, lane="skills")
        return ""


def why_unavailable() -> str:
    """'' when a call can go out; else 'no sdk' or 'no key' (the SDK is checked first —
    a key without the library is still a dead path, and the fix differs)."""
    if _sdk() is None:
        return "no sdk"
    if not api_key():
        return "no key"
    return ""


def available() -> bool:
    return why_unavailable() == ""


_LAST_ERROR: List[str] = [""]     # the most recent failure's text, key scrubbed


def last_error() -> str:
    return _LAST_ERROR[0]


def _base_url() -> str:
    return (os.environ.get("SP_CLAUDE_BASE_URL") or "").strip() or BASE_URL


@dataclass
class Reply:
    text: str = ""
    sources: List[str] = field(default_factory=list)
    stop_reason: str = ""
    refusal: str = ""
    model: str = ""
    usage: Dict[str, int] = field(default_factory=dict)
    seconds: float = 0.0
    ok: bool = False


def _fail(why: str, key: str = "", t0: float = 0.0) -> Reply:
    if key:
        why = why.replace(key, "***")
    _LAST_ERROR[0] = why[:300]
    return Reply(ok=False, seconds=(time.monotonic() - t0) if t0 else 0.0)


def _sources(content: Any) -> List[str]:
    out: List[str] = []

    def add(u: Any) -> None:
        if isinstance(u, str) and u and u not in out and len(out) < _MAX_SOURCES:
            out.append(u)

    for b in content or []:
        t = getattr(b, "type", "")
        if t == "web_search_tool_result":
            inner = getattr(b, "content", None)
            if isinstance(inner, list):          # an error object is not a list
                for r in inner:
                    add(getattr(r, "url", None))
        elif t == "text":
            for c in (getattr(b, "citations", None) or []):
                add(getattr(c, "url", None))
    return out


def ask(messages: List[dict], *, model: str, door: str, system: str = "",
        tools: Optional[List[dict]] = None, effort: str = "medium",
        max_tokens: int = 16000, timeout: float = 600.0) -> Reply:
    """One question to Claude. `door` is the anon door id the caller is spending
    (net.research, net.search, ...). Returns Reply(ok=False) on every failure."""
    # ANONYMOUS MODE. THE ONE DOOR OUT of this module, checked before the key or the
    # SDK is even looked at, so nothing is built that could be leaked.
    from harness.control import anon as _anon
    if _anon.holds(door):
        _LAST_ERROR[0] = _anon.WHY
        return Reply(ok=False)
    why = why_unavailable()
    if why:
        _LAST_ERROR[0] = why
        return Reply(ok=False)
    key = api_key()
    t0 = time.monotonic()
    try:
        client = _CLIENT_FACTORY(key, _base_url())
        kw: Dict[str, Any] = {"model": model, "max_tokens": int(max_tokens),
                              "messages": list(messages),
                              "output_config": {"effort": effort}}
        if system:
            kw["system"] = system
        if tools:
            kw["tools"] = tools
        if model in FALLBACK_MODELS:
            kw["betas"] = [_FALLBACK_BETA]
            kw["fallbacks"] = "default"
        # `timeout` is honoured by the SDK per request, not baked into the client.
        kw["timeout"] = float(timeout)
        resumes = 0
        while True:
            with client.beta.messages.stream(**kw) as s:
                m = s.get_final_message()
            if getattr(m, "stop_reason", "") == "pause_turn" and resumes < _MAX_RESUMES:
                resumes += 1
                kw["messages"] = list(kw["messages"]) + [
                    {"role": "assistant", "content": m.content}]
                continue
            break
    except Exception as exc:
        return _fail(_describe(exc), key, t0)

    stop = str(getattr(m, "stop_reason", "") or "")
    det = getattr(m, "stop_details", None)
    refusal = str(getattr(det, "category", "") or "") if stop == "refusal" else ""
    text = "".join(getattr(b, "text", "") or "" for b in (m.content or [])
                   if getattr(b, "type", "") == "text")
    u = getattr(m, "usage", None)
    usage = {"input": int(getattr(u, "input_tokens", 0) or 0),
             "output": int(getattr(u, "output_tokens", 0) or 0),
             "cache_read": int(getattr(u, "cache_read_input_tokens", 0) or 0)}
    ok = stop not in ("refusal", "pause_turn")
    _LAST_ERROR[0] = "" if ok else ("refusal: " + refusal if stop == "refusal"
                                    else "paused: out of resumes")
    return Reply(text=text, sources=_sources(m.content), stop_reason=stop,
                 refusal=refusal, model=str(getattr(m, "model", "") or model),
                 usage=usage, seconds=time.monotonic() - t0, ok=ok)


def _describe(exc: Exception) -> str:
    """The SDK's typed errors, most specific first, then anything. FULL text, untruncated:
    _fail scrubs the key and THEN truncates, because a key straddling the cut would
    survive as a partial key that no replace can match."""
    sdk = _sdk()
    for name, label in (("AuthenticationError", "auth"), ("RateLimitError", "rate limit"),
                        ("APIStatusError", "http"), ("APIConnectionError", "connection")):
        cls = getattr(sdk, name, None) if sdk is not None else None
        if isinstance(cls, type) and isinstance(exc, cls):
            code = getattr(exc, "status_code", "")
            return "%s%s: %s" % (label, (" %s" % code) if code else "", str(exc))
    return "%s: %s" % (type(exc).__name__, str(exc))
