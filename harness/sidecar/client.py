"""AUX transport — the only file that talks HTTP to the sidecar models.

Env is read PER CALL (no import-time capture — the serve.py restart lesson), URLs
and models are knobs, and failure is EMPTY, never invented: a dead sidecar returns
[] / "" / None and the caller says so. The 26B path must keep working with every
aux knob dark, which is also what the offline gate asserts.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from typing import List, Optional

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

_TIMEOUT_EMBED = 60
_TIMEOUT_CHAT = 120


def _embed_url() -> str:
    return os.environ.get("SP_AUX_EMBED_URL", "http://127.0.0.1:8811").rstrip("/")


def _chat_url() -> str:
    return os.environ.get("SP_AUX_CHAT_URL", "http://127.0.0.1:1234").rstrip("/")


def chat_model() -> str:
    """The judge/extract model on the chat door — the panel's choice if he made one, else the
    profile (registry.tune_or_env, 2026-08-22)."""
    try:
        from harness.tuning import registry as _tr
        return str(_tr.tune_or_env("aux.chat_model", "SP_AUX_CHAT_MODEL",
                                   "liquidai/lfm2.5-1.2b-instruct") or "liquidai/lfm2.5-1.2b-instruct")
    except Exception as _swx:
        _swallowed(_swlog, "chat_model", _swx, lane="sidecar")
        return os.environ.get("SP_AUX_CHAT_MODEL", "liquidai/lfm2.5-1.2b-instruct")


def _api_key() -> str:
    """Bearer token for the chat door (LM Studio requires one since ~0.3.3x).
    A FILE path, not the token itself — the profile is committed to a public
    repo and var/ is not. Empty string = no Authorization header."""
    p = os.environ.get("SP_AUX_API_KEY_FILE", "")
    if not p or not os.path.exists(p):
        return ""
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    except Exception as _swx:
        _swallowed(_swlog, "_api_key", _swx, lane="sidecar")
        return ""


def _post(url: str, body: dict, timeout: int, auth: bool = False) -> Optional[dict]:
    headers = {"Content-Type": "application/json"}
    if auth:
        k = _api_key()
        if k:
            headers["Authorization"] = "Bearer " + k
    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                     headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as _swx:
        _swallowed(_swlog, "_post", _swx, lane="sidecar")
        return None


def _get(url: str, timeout: int = 5, auth: bool = False) -> Optional[dict]:
    headers = {}
    if auth:
        k = _api_key()
        if k:
            headers["Authorization"] = "Bearer " + k
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as _swx:
        _swallowed(_swlog, "_get", _swx, lane="sidecar")
        return None


_MODELS_CACHE: dict = {"at": 0.0, "ids": []}


def list_models(ttl_s: float = 60.0) -> List[str]:
    """The chat door's model ids (LM Studio /v1/models), cached; [] when dark."""
    if _MODELS_CACHE["ids"] and time.monotonic() - _MODELS_CACHE["at"] < ttl_s:
        return list(_MODELS_CACHE["ids"])
    d = _get(_chat_url() + "/v1/models", auth=True)
    ids: List[str] = []
    try:
        ids = [m["id"] for m in (d or {}).get("data", []) if m.get("id")]
    except Exception as _swx:
        _swallowed(_swlog, "list_models", _swx, lane="sidecar")
        ids = []
    _MODELS_CACHE.update(at=time.monotonic(), ids=ids)
    return list(ids)


def reachable(door: str) -> bool:
    """Is the door answering right now? ("embed" | "chat")"""
    if door == "embed":
        return _get(_embed_url() + "/health") is not None
    return _get(_chat_url() + "/v1/models", auth=True) is not None


def available() -> bool:
    """The master knob AND the health of the embed door. SP_AUX=1 arms the aux
    surface; anything else leaves every caller on its pre-aux behavior."""
    return os.environ.get("SP_AUX", "0") == "1"


def embed(texts: List[str]) -> List[List[float]]:
    """Embed texts via the llama-server embedding door. Returns [] on ANY failure
    (dead server, bad payload) — the caller must treat empty as 'no aux', not
    as 'no results'. Order-preserving, one vector per input."""
    if not texts:
        return []
    d = _post(_embed_url() + "/v1/embeddings", {"input": texts}, _TIMEOUT_EMBED)
    if not d or "data" not in d or len(d.get("data", [])) != len(texts):
        return []
    try:
        rows = sorted(d["data"], key=lambda r: r.get("index", 0))
        return [r["embedding"] for r in rows]
    except Exception as _swx:
        _swallowed(_swlog, "embed", _swx, lane="sidecar")
        return []


def chat(messages: List[dict], max_tokens: int = 256, temperature: float = 0.0,
         model: str = "") -> str:
    """One aux completion. Returns '' on any failure. The aux model's words are
    NEVER her words — callers fold the result into context or judgments, they do
    not emit it as speech."""
    body = {"model": model or chat_model(), "messages": messages,
            "max_tokens": max_tokens, "temperature": temperature}
    d = _post(_chat_url() + "/v1/chat/completions", body, _TIMEOUT_CHAT, auth=True)
    if not d:
        return ""
    try:
        return (d["choices"][0]["message"]["content"] or "").strip()
    except Exception as _swx:
        _swallowed(_swlog, "chat", _swx, lane="sidecar")
        return ""


_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def chat_json(messages: List[dict], keys: List[str], max_tokens: int = 256,
              temperature: float = 0.0, model: str = "") -> Optional[dict]:
    """STRUCTURED OUTPUT ONLY — the silent librarian (2026-08-22). The last user message is
    suffixed with a JSON-only instruction naming the keys; the reply is parsed and validated;
    ANY failure is None (callers fall back to their pre-aux behaviour, never to prose)."""
    if not messages or not keys:
        return None
    msgs = [dict(m) for m in messages]
    msgs[-1]["content"] = (str(msgs[-1].get("content", "")) +
                           "\n\nReply with ONE JSON object and nothing else, with exactly these keys: "
                           + ", ".join('"%s"' % k for k in keys) + ".")
    out = chat(msgs, max_tokens=max_tokens, temperature=temperature, model=model)
    if not out:
        return None
    t = _FENCE.sub("", out.strip()).strip()
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        d = json.loads(t[i:j + 1])
    except Exception as _swx:
        _swallowed(_swlog, "chat_json", _swx, lane="sidecar")
        return None
    if not isinstance(d, dict) or any(k not in d for k in keys):
        return None
    return d


def judge(question: str) -> Optional[bool]:
    """A YES/NO ruling from the small model. None = the sidecar could not answer (dead, or
    the reply was neither) — callers MUST treat None as 'no ruling' and fall back to whatever
    they did before aux existed. JSON first (the silent-librarian shape), the one-word ask as
    the fallback for a model that ignores the JSON instruction."""
    d = chat_json([{"role": "user", "content": question}], keys=["answer"], max_tokens=24)
    if d is not None:
        a = str(d.get("answer", "")).strip().lower()
        if a.startswith("yes"):
            return True
        if a.startswith("no"):
            return False
    out = chat([{"role": "user",
                 "content": question + "\n\nAnswer with exactly one word: YES or NO."}],
               max_tokens=8)
    word = out.strip().upper().rstrip(".!")
    if word.startswith("YES"):
        return True
    if word.startswith("NO"):
        return False
    return None


