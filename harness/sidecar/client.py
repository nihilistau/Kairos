"""AUX transport — the only file that talks HTTP to the sidecar models.

Env is read PER CALL (no import-time capture — the serve.py restart lesson), URLs
and models are knobs, and failure is EMPTY, never invented: a dead sidecar returns
[] / "" / None and the caller says so. The 26B path must keep working with every
aux knob dark, which is also what the offline gate asserts.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import List, Optional

_TIMEOUT_EMBED = 60
_TIMEOUT_CHAT = 120


def _embed_url() -> str:
    return os.environ.get("SP_AUX_EMBED_URL", "http://127.0.0.1:8811").rstrip("/")


def _chat_url() -> str:
    return os.environ.get("SP_AUX_CHAT_URL", "http://127.0.0.1:1234").rstrip("/")


def chat_model() -> str:
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
    except Exception:
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
    except Exception:
        return None


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
    except Exception:
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
    except Exception:
        return ""


def judge(question: str) -> Optional[bool]:
    """A one-word YES/NO ruling from the small model. None = the sidecar could not
    answer (dead, or the reply was neither word) — callers MUST treat None as
    'no ruling' and fall back to whatever they did before aux existed. A judge
    that guesses on failure is how a recall filter dies."""
    out = chat([{"role": "user",
                 "content": question + "\n\nAnswer with exactly one word: YES or NO."}],
               max_tokens=8)
    word = out.strip().upper().rstrip(".!")
    if word.startswith("YES"):
        return True
    if word.startswith("NO"):
        return False
    return None
