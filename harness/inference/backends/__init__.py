"""backends — the inference seam, named (2026-08-21, the engine-agnostic Kairos plan).

ONE SURFACE, TWO BACKENDS. Everything in the harness that talks to a model goes
through `harness.inference.client.get_client()`, which returns an object with the
SPDaemonClient surface:

    chat_stream(prompt=|messages=|prompt_tokens=, config=, on_event=) -> Generator[str] (returns InferenceResponse)
    chat(...) -> InferenceResponse        oneshot(messages, max_tokens=, temperature=, timeout=) -> str
    abort(chat_id) -> bool                metrics() -> dict        health() -> bool
    subscribe_events(want=, timeout=) -> Generator[StreamEvent]
    last_kairos: dict | None              kind: str               supports: frozenset[str]
    last_trim: dict | None                what the last call dropped to fit pmax (sp only;
                                          always None on openai — see that file's note)

`kind` is "sp" (the Rust sp-daemon — everything) or "openai" (any /v1/chat/completions
server: llama.cpp, vLLM, LM Studio, a cloud). `supports` is the honest list of what the
backend can do; every seam that needs a daemon-only capability checks it and DEGRADES
with a stated loss instead of failing or pretending. The capability names:

    eot_margin     the raw stop-vs-continue logit gap -> kairos CONTINUE/EXPAND
    byteexact      exact-integer islands            eot_bias       logit bias on stop tokens
    raw_logits     control-token suppression off    auto_recall    engine-side W_c recall head
    replay         episode replay                   single_entry   residual-seam text entry
    inject_frames  residual vision/audio frames     tool_names     engine-enforced tool grammar
    prompt_tokens  pre-tokenized input              oneshot        a scratch-session one-shot
    capture        /v1/capture episode mint         embed          /v1/embed L5 vector
    events         /v1/events bus                   metrics_tps    tokens_per_sec from the engine
    warm           the load-time prefix prefill     restart        the harness may (re)start the engine
    abort          cancel a running generation      llama_extras   top_k / repeat_penalty accepted
    vision_openai  multimodal image_url parts

SP_CAPS is all of the first group; OPENAI_CAPS is what a generic endpoint gets, plus
`llama_extras` when SP_ENGINE_DIALECT=llamacpp and `vision_openai` when SP_ENGINE_VISION=1.
"""
from __future__ import annotations

SP_CAPS = frozenset({
    "eot_margin", "byteexact", "eot_bias", "raw_logits", "auto_recall", "replay",
    "single_entry", "inject_frames", "tool_names", "prompt_tokens", "oneshot",
    "capture", "embed", "events", "metrics_tps", "warm", "restart", "abort",
})

OPENAI_CAPS = frozenset({"oneshot", "abort", "metrics_tps"})

KINDS = ("sp", "openai")


def caps_for(kind: str, dialect: str = "", vision: bool = False) -> frozenset:
    if kind == "sp":
        return SP_CAPS
    extra = set()
    if (dialect or "").lower() in ("llamacpp", "llama.cpp", "llama-server"):
        extra.add("llama_extras")
    if vision:
        extra.add("vision_openai")
    return OPENAI_CAPS | extra


def supports(cap: str) -> bool:
    """Does the CURRENT backend support `cap`? Fails closed (False) if the client
    cannot be built — a seam that needs a capability must not assume it."""
    try:
        from harness.inference.client import get_client
        return cap in getattr(get_client(), "supports", SP_CAPS)
    except Exception:
        return False
