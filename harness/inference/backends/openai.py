"""OpenAIClient — the engine-agnostic backend: any /v1/chat/completions server.

MODELLED ON harness/sidecar/client.py, the one OpenAI-compatible door the tree already
had and trusted: stdlib urllib, env read PER CALL (the serve.py restart lesson), the
bearer token from a FILE path and never a value (the repo is public), and failure that
is EMPTY and said — never invented. It wears the SPDaemonClient surface exactly
(chat_stream / chat / oneshot / abort / metrics / health / subscribe_events /
last_kairos) so nothing downstream of get_client() changes; `supports` says honestly
what it cannot do (harness/inference/backends/__init__.py).

WHAT DEGRADES, STATED: no kairos eot_margin (CONTINUE/EXPAND go dark; REMIND / SOLO /
MUSE / CHECK_IN survive — impulse.decide already takes None); no byteexact, eot_bias,
raw_logits, auto_recall, replay, frame injection; no /v1/capture mint (memory rows still
land); embeddings come from the sidecar or the hash space; `metrics()` is the harness's
own turn meter; `abort()` closes the stream; `subscribe_events()` is empty.

Env: SP_ENGINE_BASE_URL (http://127.0.0.1:1234 is LM Studio's default; llama-server uses
:8080), SP_ENGINE_MODEL, SP_ENGINE_API_KEY_FILE, SP_ENGINE_DIALECT (llamacpp|generic),
SP_ENGINE_VISION (1), SP_ENGINE_MARGIN_APPROX (1: a `length` finish counts as cut off).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Generator, List, Optional

from harness.inference.inference_config import InferenceConfig
from harness.inference.backends import caps_for

from harness.loud import swallowed as _swallowed

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:1234"


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _api_key() -> str:
    p = _env("SP_ENGINE_API_KEY_FILE")
    if not p or not os.path.exists(p):
        return ""
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    except Exception as _swx:
        _swallowed(logger, "_api_key", _swx, lane="inference")
        return ""


class OpenAIClient:
    kind = "openai"

    def __init__(self, base_url: str = "", timeout: float = 300.0, default_model: str = "") -> None:
        self.base_url = (base_url or _env("SP_ENGINE_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        if self.base_url.endswith("/v1"):
            self.base_url = self.base_url[:-3]
        self.timeout = timeout
        self.default_model = default_model or _env("SP_ENGINE_MODEL", "")
        self.last_kairos: Optional[Dict[str, Any]] = None
        # ALWAYS None here, and that is the honest answer rather than a missing attribute.
        # The context trim (harness/inference/context.py) is a fact about the sp-daemon's
        # pmax — a fixed position ceiling with no truncation of its own. A foreign endpoint
        # has its own window and its own policy for overrunning it, and inventing a trim
        # on its behalf would be this harness lying about someone else's engine.
        self.last_trim: Optional[Dict[str, Any]] = None
        self.supports = caps_for("openai", _env("SP_ENGINE_DIALECT"),
                                 _env("SP_ENGINE_VISION", "0") == "1")
        self._open: Dict[int, Any] = {}          # chat_id -> the live response (for abort)
        self._next_id = 1
        self._lock = threading.Lock()

    # ── transport ─────────────────────────────────────────────────────────────
    def _req(self, path: str, body: Optional[dict] = None, timeout: Optional[float] = None):
        headers = {"Content-Type": "application/json",
                   "Accept": "text/event-stream, application/json"}
        k = _api_key()
        if k:
            headers["Authorization"] = "Bearer " + k
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers,
                                     method="POST" if data is not None else "GET")
        return urllib.request.urlopen(req, timeout=timeout or self.timeout)

    def _model(self, cfg: InferenceConfig) -> str:
        return cfg.model or self.default_model or _env("SP_ENGINE_MODEL", "")

    # ── the surface ────────────────────────────────────────────────────────────
    def chat_stream(self, *, prompt: Optional[str] = None,
                    messages: Optional[List[Dict[str, Any]]] = None,
                    prompt_tokens: Optional[List[int]] = None,
                    config: Optional[InferenceConfig] = None,
                    on_event: Optional[Callable] = None):
        """Yield text deltas from /v1/chat/completions (stream=true); return the
        InferenceResponse. `prompt_tokens` is unsupported here (dropped with a log line);
        a bare `prompt` becomes one user message."""
        from harness.inference.client import InferenceResponse, StreamEvent
        cfg = config or InferenceConfig()
        if messages is None:
            messages = [{"role": "user", "content": prompt or ""}]
        if prompt_tokens is not None:
            logger.info("[OpenAIClient] prompt_tokens is not supported on this backend — using messages")
        body = cfg.to_openai_chat(messages, self.supports, stream=True)
        # the model id is the BACKEND's default when the config names none — set on the
        # body, not merged into the config (merge() would also import the dataclass's
        # max_tokens default over the caller's value)
        if not body.get("model") and self._model(cfg):
            body["model"] = self._model(cfg)
        with self._lock:
            chat_id = self._next_id
            self._next_id += 1
        resp = InferenceResponse(model=body.get("model", ""), chat_id=chat_id)
        if on_event:
            on_event(StreamEvent("chat.start", chat_id=chat_id))
        parts: List[str] = []
        finish = "stop"
        try:
            r = self._req("/v1/chat/completions", body)
            with self._lock:
                self._open[chat_id] = r
            try:
                for raw in r:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        evt = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    ch = (evt.get("choices") or [{}])[0]
                    if ch.get("finish_reason"):
                        finish = ch["finish_reason"]
                    delta = ch.get("delta") or {}
                    # reasoning_content (DeepSeek/vLLM/llama.cpp spelling) is THOUGHT, not
                    # speech: it goes out as an event for a lane that wants it and is never
                    # yielded as text — the private channel stays private.
                    if delta.get("reasoning_content") and on_event:
                        on_event(StreamEvent("thinking", content=delta["reasoning_content"],
                                             chat_id=chat_id))
                    text = delta.get("content") or ""
                    if text:
                        parts.append(text)
                        if on_event:
                            on_event(StreamEvent("message.delta", content=text, chat_id=chat_id))
                        yield text
            finally:
                with self._lock:
                    self._open.pop(chat_id, None)
                try:
                    r.close()
                except Exception as _swx:
                    _swallowed(logger, "chat_stream", _swx, lane="inference")
        except Exception as exc:
            logger.error("[OpenAIClient] stream failed (operation=chat): %s", exc)
            if on_event:
                on_event(StreamEvent("error", error={"message": str(exc)}, is_done=True))
            raise
        # the one door text comes through — same stripper as the daemon path
        from harness.inference.stream_processor import strip_control_surfaces
        resp.text = strip_control_surfaces("".join(parts))
        resp.finish_reason = finish
        # NO MARGIN HERE, and the harness is told so rather than handed a number: kairos
        # decides with eot_margin=None (CONTINUE/EXPAND dark). SP_ENGINE_MARGIN_APPROX=1
        # lets a `length` finish read as "cut off" — crude, no magnitude, opt-in.
        margin = None
        if _env("SP_ENGINE_MARGIN_APPROX", "0") == "1" and finish == "length":
            margin = 0.0
        resp.kairos = {"eot_margin": margin, "finish_reason": finish, "source": "openai"}
        self.last_kairos = resp.kairos
        if on_event:
            on_event(StreamEvent("message.end", chat_id=chat_id, is_done=True))
        return resp

    def chat(self, *, prompt: Optional[str] = None,
             messages: Optional[List[Dict[str, Any]]] = None,
             config: Optional[InferenceConfig] = None):
        gen = self.chat_stream(prompt=prompt, messages=messages, config=config)
        try:
            while True:
                next(gen)
        except StopIteration as stop:
            return stop.value

    def oneshot(self, messages: List[Dict[str, Any]], *, max_tokens: int = 160,
                temperature: float = 0.0, timeout: float = 300.0) -> str:
        """A one-shot is just a non-stream completion here — the foreign server owns its
        own cache discipline, so there is nothing to protect from eviction."""
        cfg = InferenceConfig(max_tokens=int(max_tokens), temperature=float(temperature))
        body = cfg.to_openai_chat(messages, self.supports, stream=False)
        if not body.get("model") and self._model(cfg):
            body["model"] = self._model(cfg)
        try:
            with self._req("/v1/chat/completions", body, timeout=timeout) as r:
                j = json.loads(r.read().decode("utf-8", "replace"))
            text = ((j.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        except Exception as exc:
            logger.error("[OpenAIClient] oneshot failed: %s", exc)
            return ""
        from harness.inference.stream_processor import strip_control_surfaces
        return strip_control_surfaces(text)

    def embed(self, texts: List[str]) -> List[List[float]]:
        """/v1/embeddings if the server has it; [] on any failure (the caller falls
        through to the sidecar or the hash space)."""
        if not texts:
            return []
        try:
            with self._req("/v1/embeddings",
                           {"input": texts, "model": self.default_model or "default"},
                           timeout=60) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            rows = sorted(d.get("data") or [], key=lambda x: x.get("index", 0))
            out = [row["embedding"] for row in rows]
            return out if len(out) == len(texts) else []
        except Exception as _swx:
            _swallowed(logger, "embed", _swx, lane="inference")
            return []

    def abort(self, chat_id: int) -> bool:
        """Cancel = close the stream; every OpenAI-compatible server treats a dropped
        connection as the cancel signal."""
        with self._lock:
            r = self._open.pop(int(chat_id), None)
        if r is None:
            return False
        try:
            r.close()
        except Exception as _swx:
            _swallowed(logger, "abort", _swx, lane="inference")
        return True

    def metrics(self) -> Dict[str, Any]:
        from harness.inference import turn_meter
        return turn_meter.metrics()

    def health(self) -> bool:
        try:
            with self._req("/v1/models", timeout=5) as r:
                return r.status == 200
        except Exception as _swx:
            _swallowed(logger, "health", _swx, lane="inference")
            return False

    def backend_counts(self) -> Dict[str, Any]:
        return {}

    def subscribe_events(self, *, want: Optional[List[str]] = None,
                         timeout: Optional[float] = None) -> Generator:
        """No event bus on a foreign endpoint. An empty generator, not an exception — the
        telemetry sink and the watchdog must tolerate silence here."""
        return iter(())
