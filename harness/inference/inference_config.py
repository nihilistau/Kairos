"""
Inference Configuration
========================

Backend-agnostic generation parameters and their projection onto the
Kairos ``sp-daemon`` ``POST /v1/chat`` request schema.

This is the single place that knows what knobs exist. Clients, the router and
the orchestrator all pass an :class:`InferenceConfig` and never hand-build
backend payloads.
"""

from __future__ import annotations

import logging as _logging
import os as _os
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

_log = _logging.getLogger(__name__)
_WARNED = {"bx": False}


def _warn_unconfigured_byteexact() -> None:
    """Say it once per process: nobody configured byteexact, so we chose the safe value.

    Once, not per call — a per-request warning in a 20-turn scoreboard is noise, and noise
    is how the empty replies went unnoticed for twenty turns in the first place.
    """
    if _WARNED["bx"]:
        return
    _WARNED["bx"] = True
    _log.warning(
        "[InferenceConfig] byteexact unset and SP_GATEWAY_BYTEEXACT absent (not launched via "
        "serve.py) — sending byteexact=False. On a MoE model the daemon's ON default is "
        "REFUSED and answers with an empty 200, so False is the only value that produces "
        "output. Pass byteexact= explicitly if you need exactness.")


# ──── Config ──────────────────────────────────────────────────────────────
@dataclass
class InferenceConfig:
    """Unified, backend-agnostic generation config.

    Every field maps cleanly onto the sp-daemon ``/v1/chat`` schema via
    :meth:`to_sp_chat`. Unset (``None``) fields are omitted so the daemon's
    own defaults apply.
    """

    # Sampling
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    repetition_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    seed: Optional[int] = None
    max_tokens: Optional[int] = 512
    stop: Optional[List[str]] = None

    # Kairos native knobs (the levers LMStudio never had)
    byteexact: Optional[bool] = None        # exact-integer islands, bit-deterministic
    raw_logits: Optional[bool] = None       # disable control-token suppression (null floor)
    auto_recall: Optional[bool] = None      # autonomous W_c episodic recall head
    replay: Optional[str] = None            # explicit episode dir to replay
    replay_npos: Optional[int] = None
    single_entry: Optional[bool] = None     # route text via residual seam
    eot_bias: Optional[float] = None        # logit bias on stop tokens so the model STOPS cleanly
    # SELF-REPEAT BAN: N-grams from HER PREVIOUS REPLY only are forbidden (not from the
    # whole prompt -- that was no_repeat_ngram, which banned QUOTING and had to go).
    self_repeat_ngram: Optional[int] = None
    self_repeat_text: Optional[str] = None
    # CONSTRAINED TOOL DECODING. The harness owns the grammar (harness/mcp/grammar.py); this
    # is the part of it the ENGINE can enforce — the set of names that exist. With it, a
    # hallucinated tool is not a typo to be healed in a regex, it is a token sequence the
    # sampler cannot produce. Empty (the default) = the engine masks nothing, so no caller
    # that does not ask for this is affected in any way.
    tool_names: Optional[list] = None
                                            # (without this the gateway path never terminates)

    # Routing / model selection (harness-side, not sent to daemon)
    model: Optional[str] = None

    def to_sp_chat(
        self,
        *,
        prompt: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        prompt_tokens: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Build the sp-daemon ``/v1/chat`` request body.

        Exactly one of ``prompt`` / ``messages`` / ``prompt_tokens`` must be
        supplied (the daemon enforces this).
        """
        # ── THE PROFILE'S ANSWER, FOR EVERY LANE (2026-07-30) ────────────────────────
        # byteexact defaults to None = "don't send it" = the DAEMON decides, and the
        # daemon's default is ON. On your model the MoE FFN seam REFUSES byteexact
        # outright (the exact-integer islands cover the dense FFN only) and answers with
        # an empty 200. So every lane that did not explicitly pass byteexact=False got
        # silence on this model.
        #
        # Two lanes in harness/server/app.py DID pass it, via _bx_default(). Everything
        # else did not: the kairos CONTINUATION (which is why she stopped speaking
        # unprompted — "DROPPED: she had nothing to add after all :: ''", every time,
        # because the continuation was refused before it ever generated), reflection,
        # agency, task_loop and the CLI coder. The fix for the silent console was applied
        # to the two builders I was looking at, and the other five kept the bug — the same
        # shape this file's whole history is made of.
        #
        # So resolve it HERE, where the body is built and every lane must pass. An
        # explicit value still wins; None now means "what the profile said" instead of
        # "whatever the daemon happens to default to".
        # ── AND THE FIX ITSELF ONLY WORKED UNDER serve.py (2026-07-30, same day) ─────
        # The block above resolves None from SP_GATEWAY_BYTEEXACT — a variable ONLY
        # serve.py sets. So the fix held for the gateway and for nothing else: any
        # process started by hand inherited no such variable, `eff_bx` stayed None,
        # the key was omitted, the daemon applied its ON default, and the MoE answered
        # with an empty 200 again.
        #
        # MEASURED: `voice_score.py 26b` — twenty turns, 32 s each, EVERY REPLY EMPTY,
        # exit code 0. A scoreboard reporting len_median 0.0 as a finding about her
        # voice. The same probe straight through `client.chat` was empty too, which is
        # what proved it was the body and not the rig.
        #
        # So the last resort is now a VALUE, not a shrug. Sending nothing means silence
        # on the live model, and silence is the worst available outcome: it looks like
        # she had nothing to say. False is the only value that produces output on an MoE
        # seam that refuses exactness, so False is what an unconfigured caller gets, and
        # it says so out loud once per process.
        #
        # This cannot weaken the exactness anyone relies on: an explicit `byteexact=`
        # still wins, serve.py still sets the profile's answer, and G-VERBATIM — the one
        # gate whose whole subject is bit-determinism — negotiates it explicitly (it had
        # to learn that on this model, at 0/6).
        eff_bx = self.byteexact
        if eff_bx is None:
            _env = _os.environ.get("SP_GATEWAY_BYTEEXACT")
            if _env is not None:
                eff_bx = _env.strip() == "1"
            else:
                eff_bx = False
                _warn_unconfigured_byteexact()

        body: Dict[str, Any] = {}
        if prompt is not None:
            body["prompt"] = prompt
        if messages is not None:
            body["messages"] = messages
        if prompt_tokens is not None:
            body["prompt_tokens"] = prompt_tokens

        for k in (
            "temperature", "top_p", "top_k", "repetition_penalty",
            "frequency_penalty", "seed", "max_tokens",
            "byteexact", "raw_logits", "auto_recall",
            "replay", "replay_npos", "single_entry", "eot_bias",
            "self_repeat_ngram", "self_repeat_text",
            "tool_names",
        ):
            v = eff_bx if k == "byteexact" else getattr(self, k)
            if v is not None:
                body[k] = v
        if self.stop:
            body["stop"] = self.stop
        return body

    # ── PORTABLE vs SP-ONLY (2026-08-21, the engine-agnostic seam) ─────────────────
    # Two sets, declared once, so the OpenAI projection and the gate that holds it read
    # the same list. A field in neither is a bug report against this file.
    PORTABLE = ("temperature", "top_p", "top_k", "repetition_penalty", "frequency_penalty",
                "seed", "max_tokens", "stop", "model")
    SP_ONLY = ("byteexact", "raw_logits", "auto_recall", "replay", "replay_npos",
               "single_entry", "eot_bias", "self_repeat_ngram", "self_repeat_text",
               "tool_names")

    def to_openai_chat(
        self,
        messages: List[Dict[str, Any]],
        supports=frozenset(),
        *,
        stream: bool = True,
    ) -> Dict[str, Any]:
        """Build a /v1/chat/completions body for ANY OpenAI-compatible server.

        Only PORTABLE fields are sent. `top_k` and `repetition_penalty` (as llama.cpp's
        `repeat_penalty`) are sent ONLY when the backend declares `llama_extras` — a
        cloud endpoint 400s on unknown fields. Every SP_ONLY field is dropped, and the
        drop is logged once per process so the loss is a recorded fact, not a silence:
        byteexact / raw_logits / auto_recall / replay / single_entry have no analogue;
        eot_bias would need a stop-token id the caller does not have; self_repeat_* is
        re-done post hoc by quality/repeat_guard; tool_names falls back to the harness's
        own grammar + regex healing.
        """
        body: Dict[str, Any] = {"messages": messages, "stream": bool(stream)}
        if self.model:
            body["model"] = self.model
        for k in ("temperature", "top_p", "frequency_penalty", "seed", "max_tokens"):
            v = getattr(self, k)
            if v is not None:
                body[k] = v
        if self.stop:
            body["stop"] = self.stop
        if "llama_extras" in supports:
            if self.top_k is not None:
                body["top_k"] = self.top_k
            if self.repetition_penalty is not None:
                body["repeat_penalty"] = self.repetition_penalty
        dropped = [k for k in self.SP_ONLY if getattr(self, k) is not None]
        if dropped and not _WARNED.get("openai_drop"):
            _WARNED["openai_drop"] = True
            _log.info("[InferenceConfig] openai backend: sp-only fields dropped from the "
                      "wire (recorded once): %s", dropped)
        return body

    @classmethod
    def merge(cls, base: "InferenceConfig", override: "InferenceConfig") -> "InferenceConfig":
        """Return a new config where non-``None`` override fields win."""
        merged = asdict(base)
        for k, v in asdict(override).items():
            if v is not None:
                merged[k] = v
        return cls(**merged)
