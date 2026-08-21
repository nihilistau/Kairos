"""
Kairos Daemon Client
===========================

The harness's replacement for the LMStudio REST/SDK client. Talks to the
Kairos universal resident daemon (``sp-daemon``) over HTTP:

    POST /v1/chat        — SSE token stream  (one ``{"delta": ...}`` per token)
    POST /v1/abort/{id}  — cancel an in-flight generation
    GET  /v1/metrics     — tokens/sec, session position, phase
    GET  /v1/debug/backend_counts — which wire backend is live

The daemon stream is Kairos native (NOT OpenAI ``/v1/chat/completions``).
This client adapts it into the harness's :class:`StreamEvent` shape, which the
:class:`~harness.inference.stream_processor.StreamProcessor` then mines for
inline tags. The OpenAI-compatible surface lives one layer up in
``harness.server`` so external callers get a familiar API while the daemon stays
native.

Launch reference (the daemon this client targets)::

    sp-daemon start --model gemma4-12b-b1.sp-model \\
        --tokenizer gemma4-12b-b1.sp-tokenizer --port 3000
    # env: SP_DAEMON_BACKEND=cuda SP_DAEMON_KVDECODE=1 SP_CUDA_DECODE_INT8=1
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, List, Optional

from harness.inference.inference_config import InferenceConfig

# NOTE: `strip_control_surfaces` is imported at its two CALL SITES, not here.
# stream_processor imports StreamEvent from this module, so a module-level import
# would be a cycle (and `harness/__init__` pulls this in first, so it is a hard
# ImportError, not a latent one).

logger = logging.getLogger(__name__)

try:  # httpx is the preferred transport; degrade gracefully if absent
    import httpx
except Exception:  # pragma: no cover - import guard
    httpx = None  # type: ignore


DEFAULT_DAEMON_URL = "http://127.0.0.1:3000"


# ──── Event / response shapes ─────────────────────────────────────────────
@dataclass
class StreamEvent:
    """One normalized streaming event.

    The sp-daemon only emits ``delta`` token events plus a terminal ``[DONE]``;
    this dataclass keeps the richer LMStudio-style event surface so downstream
    processors (and the SSE server) don't need to change when the backend's
    event vocabulary grows (tool calls, reasoning deltas, etc.).
    """

    event_type: str            # "message.delta" | "message.end" | "chat.start" | "error"
    content: str = ""
    chat_id: Optional[int] = None
    error: Optional[Dict[str, Any]] = None
    stats: Dict[str, Any] = field(default_factory=dict)
    is_done: bool = False


@dataclass
class InferenceResponse:
    """Aggregated result of a completed generation."""

    text: str = ""
    chat_id: Optional[int] = None
    model: str = ""
    finish_reason: str = "stop"
    stats: Dict[str, Any] = field(default_factory=dict)
    # KAIROS: the turn's continuation impulse, straight from the forward —
    # {"eot_margin": float, "n_gen": int, "eot_bias": float}. None when SP_KAIROS is off.
    # eot_margin is the RAW logit gap (best stop token − best continue token) at the step
    # that ended the turn:  >>0 = done and knows it;  ~0 = stopped mid-thought;
    # <0 = she only stopped because eot_bias tipped her, i.e. she was CUT OFF.
    kairos: Optional[Dict[str, Any]] = None


# ──── Client ──────────────────────────────────────────────────────────────
class SPDaemonClient:
    """Thin HTTP client over the Kairos daemon.

    CONNECTS: InferenceConfig, StreamProcessor
    CALLED BY: InferenceRouter, InferenceOrchestrator, tool-calling loop, SSE server
    EMITS: StreamEvent stream
    """

    def __init__(
        self,
        base_url: str = DEFAULT_DAEMON_URL,
        timeout: float = 300.0,
        default_model: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.default_model = default_model
        # KAIROS: the last turn's continuation impulse from the daemon's `kairos` SSE
        # event ({"eot_margin", "n_gen", "eot_bias"}), or None when SP_KAIROS is off.
        self.last_kairos: Optional[Dict[str, Any]] = None
        self._client = httpx.Client(timeout=timeout) if httpx else None
        # THE SEAM, NAMED (2026-08-21): every backend says what it is and what it can
        # do; the sp-daemon can do everything (harness/inference/backends).
        from harness.inference.backends import SP_CAPS
        self.kind = "sp"
        self.supports = SP_CAPS

    # ---- core: streaming chat -------------------------------------------
    def chat_stream(
        self,
        *,
        prompt: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        prompt_tokens: Optional[List[int]] = None,
        config: Optional[InferenceConfig] = None,
        on_event: Optional[Callable[[StreamEvent], None]] = None,
    ) -> Generator[str, None, InferenceResponse]:
        """Stream tokens from ``POST /v1/chat``.

        Yields the text delta of each token; returns the aggregated
        :class:`InferenceResponse` when the stream closes. ``on_event`` (if
        given) receives the normalized :class:`StreamEvent` for each line.
        """
        if self._client is None:
            raise RuntimeError("httpx is required for SPDaemonClient (pip install httpx)")

        cfg = config or InferenceConfig()
        body = cfg.to_sp_chat(prompt=prompt, messages=messages, prompt_tokens=prompt_tokens)
        logger.info("[SPDaemonClient] -> daemon: keys=%s eot_bias=%s max_tokens=%s temp=%s rep=%s msgs=%d",
                    sorted(body.keys()), body.get("eot_bias"), body.get("max_tokens"),
                    body.get("temperature"), body.get("repetition_penalty"),
                    len(body.get("messages") or []))
        # ── WHO SENT THIS PROMPT (2026-08-04) ────────────────────────────────────────
        # There is exactly ONE resident KV cache and several callers reaching for it: the
        # turn, its tool rounds, the kairos continuation, the speak-up. Each commits, so
        # each leaves the cache holding a shape the next one may not extend — and the
        # daemon log records only `S1 prompt ids: n=6831`, a number with no name on it.
        #
        # MEASURED across what the client experienced as two user turns: six prompts, at
        # 6531 / 6697 / 7204 / 6831 / 6822 / 7010 tokens. The sizes go UP AND DOWN, so
        # they are not tool rounds (those only grow) — they are different HISTORIES. Which
        # ones, though, was guesswork from length, and I spent most of a night guessing
        # wrong twice: first blaming the recall note, then the speak-up, when it was the
        # cut-off continuation reading the client's echo.
        #
        # So: name the caller at the door. Two frames of the harness stack is enough to
        # tell `_continue` from `_native_chat_sse` from `_generate`, and correlating this
        # against the daemon's own PREFIX-MATCH line by timestamp turns attribution from
        # inference into reading. MEASURE BEFORE BUILDING — the whole session's lesson.
        #
        # Deliberately not a request field: that would change the prompt bytes and cost a
        # cache miss, which is a fine way to break the thing you are measuring.
        try:
            import traceback as _tb
            _all = [f for f in _tb.extract_stack()[:-1]
                    if "client.py" not in (f.filename or "")]
            # Prefer harness frames, but NEVER report "?" — an instrument that can come
            # back empty is one you cannot trust when it does. Falling back to whatever
            # frames exist still names the caller; it just names it less prettily.
            _frames = [f for f in _all if "harness" in (f.filename or "")] or _all
            _who = " <- ".join("%s:%s" % (os.path.basename(f.filename), f.name)
                               for f in reversed(_frames[-3:])) or "?"
            _chars = sum(len(m.get("content") or "") for m in (body.get("messages") or []))
            logger.info("[DAEMON-CALL] %s | msgs=%d chars=%d last=%s",
                        _who, len(body.get("messages") or []), _chars,
                        (body.get("messages") or [{}])[-1].get("role", "?"))
        except Exception:
            pass                       # instrumentation must never break a turn

        text_parts: List[str] = []
        chat_id: Optional[int] = None
        resp = InferenceResponse(model=cfg.model or self.default_model)

        if on_event:
            on_event(StreamEvent("chat.start"))

        url = f"{self.base_url}/v1/chat"
        # KAIROS: the daemon emits a named `kairos` SSE event carrying the turn's
        # continuation impulse (the raw stop-vs-continue logit margin). This loop used to
        # drop every `event:` line on the floor — only `data:` lines were read — so a
        # named event was invisible no matter what the engine sent. Track the event name.
        sse_event = "message"
        try:
            with self._client.stream("POST", url, json=body) as stream:
                stream.raise_for_status()
                for line in stream.iter_lines():
                    if not line:
                        continue
                    if line.startswith("event:"):
                        sse_event = line[len("event:"):].strip()
                        continue
                    if not line.startswith("data:"):
                        continue
                    payload = line[len("data:"):].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        evt = json.loads(payload)
                    except json.JSONDecodeError:
                        logger.warning("[SPDaemonClient] bad SSE line (operation=parse): %s", payload[:120])
                        continue
                    if chat_id is None:
                        chat_id = evt.get("chat_id")
                    name, sse_event = sse_event, "message"   # the name applies to THIS data line
                    if name == "kairos":
                        resp.kairos = evt          # the continuation impulse for this turn
                        # also stash it on the client: agent_chat_stream() yields raw text
                        # deltas and never surfaces the InferenceResponse, so the gateway
                        # needs somewhere to read the turn's impulse from after the fact.
                        self.last_kairos = evt
                        if on_event:
                            on_event(StreamEvent("kairos", content=payload, chat_id=chat_id))
                        continue
                    delta = evt.get("delta", "")
                    if delta:
                        text_parts.append(delta)
                        if on_event:
                            on_event(StreamEvent("message.delta", content=delta, chat_id=chat_id))
                        yield delta
        except Exception as exc:  # surface, do not swallow (Oracle convention)
            logger.error("[SPDaemonClient] stream failed (operation=chat): %s", exc)
            if on_event:
                on_event(StreamEvent("error", error={"message": str(exc)}, is_done=True))
            raise

        # ── CONTROL SURFACES ARE STRIPPED HERE, AT THE ONE DOOR TEXT COMES THROUGH ────
        # your model imitates its own control markup in prose — "<channel|>", "<|think|>",
        # "<thought>", homoglyph variants — because the thought channel is part of its
        # template. Every lane that generates text has to remove them, and I fixed them one
        # at a time, four times:
        #   1. the native SSE stream            3. the kairos continuation
        #   2. the OpenAI /v1/chat/completions  4. …and then the NIGHT NARRATIVE, which
        #      arrived as "As of Wednesday 29 July 2026: <channel|>Sam finally got…"
        #      in her permanent journal, because the composer calls the client directly.
        # There are at least two more lanes behind it (ops.insight, the conversation
        # summariser). Patching the fifth would be the same mistake a fifth time.
        #
        # So: strip where the daemon's text ENTERS the harness. Every lane — chat, stream,
        # oneshot, judges, curators, the narrator — is downstream of this line. A control
        # marker is never speech in any of them, so there is no caller that wants them kept.
        from harness.inference.stream_processor import strip_control_surfaces
        resp.text = strip_control_surfaces("".join(text_parts))
        resp.chat_id = chat_id
        if on_event:
            on_event(StreamEvent("message.end", chat_id=chat_id, is_done=True))
        return resp

    # ---- convenience: blocking chat -------------------------------------
    def chat(
        self,
        *,
        prompt: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        config: Optional[InferenceConfig] = None,
    ) -> InferenceResponse:
        """Run a generation to completion and return the aggregated response."""
        gen = self.chat_stream(prompt=prompt, messages=messages, config=config)
        try:
            while True:
                next(gen)
        except StopIteration as stop:
            return stop.value  # type: ignore[return-value]

    # ---- one-shot: a call that is never continued -------------------------
    def oneshot(
        self,
        messages: List[Dict[str, Any]],
        *,
        max_tokens: int = 160,
        temperature: float = 0.0,
        timeout: float = 300.0,
    ) -> str:
        """A model call that answers ONCE and is never continued. Its own scratch cache.

        USE THIS FOR EVERY AUXILIARY CALL — the watch judge, the reflection, the summariser,
        the classifier. Anything that asks the model a question and throws the session away.

        WHY IT EXISTS, MEASURED
        ───────────────────────
        Those calls used to go through `chat()`, which lands in THE ONE RESIDENT KV SLOT — the
        same slot holding his conversation. Two things followed, and both were invisible:

          1. THE CALL ITSELF WAS ABSURD. Its ~1450-token prompt shares almost nothing with the
             persona preamble, so the cache's longest-common-prefix collapses and it pays a full
             PER-TOKEN prefill: 1450 x 60 ms = 78 SECONDS, to produce one YES/NO token. The
             engine's batched prefill — its own comment promises "~5-7x faster" — was declined,
             because the guard tested a PROCESS-WIDE SP_PERSIST_KV. The chat path needs
             persistence, so the judge (which has nothing whatsoever to continue) was
             disqualified along with it.

          2. IT EVICTED HIS CONVERSATION. The aux prompt became the committed cache, so his next
             turn was no longer a strict extension of anything and re-prefilled from token 0.

        A one-shot has no continuation to protect. It gets its own scratch session, sized to its
        own prompt, marked one_shot in the engine (which legalises the batched prefill), decoded,
        and released. THE RESIDENT CACHE IS NOT READ, NOT WRITTEN, AND NOT EVICTED.

        Falls back to `chat()` if the daemon is old and has no /v1/oneshot — slower and it will
        evict, but it will never simply fail. An optimisation that can take the system down is
        not an optimisation.
        """
        if self._client is None:
            raise RuntimeError("client not connected")
        try:
            r = self._client.post(
                f"{self.base_url}/v1/oneshot",
                json={"messages": messages, "max_tokens": int(max_tokens),
                      "temperature": float(temperature)},
                timeout=timeout,
            )
            if r.status_code == 404:
                raise FileNotFoundError("no /v1/oneshot on this daemon")
            r.raise_for_status()
            j = r.json()
            logger.info("[oneshot] %d prompt tok, %s, %d ms — resident cache untouched",
                        j.get("prompt_tokens", -1),
                        "BATCHED" if j.get("batched") else "per-token",
                        j.get("ms", -1))
            from harness.inference.stream_processor import strip_control_surfaces
            return strip_control_surfaces(j.get("text", ""))
        except FileNotFoundError:
            logger.warning("[oneshot] daemon has no /v1/oneshot — falling back to chat() "
                           "(this WILL evict the conversation cache)")
            cfg = InferenceConfig(max_tokens=max_tokens, temperature=temperature)
            return self.chat(messages=messages, config=cfg).text

    # ---- control / health -----------------------------------------------
    def abort(self, chat_id: int) -> bool:
        """Cancel a running generation. Returns True on 204."""
        if self._client is None:
            return False
        try:
            r = self._client.post(f"{self.base_url}/v1/abort/{chat_id}")
            return r.status_code == 204
        except Exception as exc:
            logger.error("[SPDaemonClient] abort failed (operation=abort, id=%s): %s", chat_id, exc)
            return False

    def metrics(self) -> Dict[str, Any]:
        """Return ``GET /v1/metrics`` (tokens_per_sec, session_pos, phase)."""
        if self._client is None:
            return {}
        try:
            return self._client.get(f"{self.base_url}/v1/metrics").json()
        except Exception as exc:
            logger.error("[SPDaemonClient] metrics failed (operation=metrics): %s", exc)
            return {}

    def health(self) -> bool:
        """True if the daemon answers ``/v1/metrics``."""
        return bool(self.metrics())

    def backend_counts(self) -> Dict[str, Any]:
        """Return wire-backend dispatch counters (diagnostic)."""
        if self._client is None:
            return {}
        try:
            return self._client.get(f"{self.base_url}/v1/debug/backend_counts").json()
        except Exception:
            return {}

    # ---- daemon-wide event stream (LM-B2 SSE telemetry sink) -------------
    def subscribe_events(
        self,
        *,
        want: Optional[List[str]] = None,
        timeout: Optional[float] = None,
    ) -> Generator[StreamEvent, None, None]:
        """Subscribe to the daemon-wide ``GET /v1/events`` SSE bus and yield each
        event as a :class:`StreamEvent` (``event_type`` = the SSE ``event:`` name,
        ``content`` = the raw ``data:`` payload). This is a LONG-LIVED stream
        (chat lifecycle + PoUW mints + LM-B2 ``telemetry`` records), distinct from
        the per-request ``chat_stream``. ``want`` filters to the given event names
        (e.g. ``["telemetry"]``); ``None`` yields all. The telemetry payload is
        already class-redacted by the engine — the harness only sinks it.
        """
        if self._client is None:
            raise RuntimeError("httpx is required for SPDaemonClient (pip install httpx)")
        url = f"{self.base_url}/v1/events"
        # /v1/events is unbounded — do not inherit the chat timeout.
        client = httpx.Client(timeout=timeout) if timeout is not None else \
            httpx.Client(timeout=httpx.Timeout(None))
        try:
            with client.stream("GET", url) as stream:
                stream.raise_for_status()
                ev_name: Optional[str] = None
                for line in stream.iter_lines():
                    if line.startswith("event:"):
                        ev_name = line[len("event:"):].strip()
                    elif line.startswith("data:"):
                        data = line[len("data:"):].strip()
                        if data == "keepalive" or data == "[DONE]":
                            continue
                        name = ev_name or "message"
                        if want is None or name in want:
                            yield StreamEvent(name, content=data)
                        ev_name = None
                    elif line == "":
                        ev_name = None
        except Exception as exc:  # surface, do not swallow (Oracle convention)
            logger.error("[SPDaemonClient] events stream failed (operation=events): %s", exc)
            raise
        finally:
            client.close()


# ──── Singleton ───────────────────────────────────────────────────────────
_CLIENT: Optional[SPDaemonClient] = None


def get_client(base_url: Optional[str] = None):
    """Return the process-wide inference client — ONE of two backends behind one surface.

    SP_ENGINE_KIND picks it: "sp" (default — the Rust sp-daemon, unchanged behaviour)
    or "openai" (any /v1/chat/completions server; harness/inference/backends/openai.py).
    Nothing downstream of agent.py knows which; seams that need a daemon-only capability
    ask `client.supports` and degrade with a stated loss. The engine-agnostic Kairos
    framework is this selector with the default flipped (2026-08-21 plan, Phase 3)."""
    global _CLIENT
    kind = (os.environ.get("SP_ENGINE_KIND") or "sp").strip().lower()
    if kind == "openai":
        from harness.inference.backends.openai import OpenAIClient
        want = base_url or os.environ.get("SP_ENGINE_BASE_URL") or ""
        if _CLIENT is None or getattr(_CLIENT, "kind", "") != "openai" \
                or (want and want.rstrip("/") != _CLIENT.base_url):
            _CLIENT = OpenAIClient(want)
        return _CLIENT
    if _CLIENT is None or getattr(_CLIENT, "kind", "sp") != "sp" \
            or (base_url and base_url != _CLIENT.base_url):
        _CLIENT = SPDaemonClient(base_url or DEFAULT_DAEMON_URL)
    return _CLIENT
