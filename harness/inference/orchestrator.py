"""
Inference Orchestrator
=====================

The single facade the rest of the harness calls for generation. Resolves an
agent profile -> InferenceConfig -> router submission, and returns either a
blocking :class:`InferenceResponse` or a streaming generator.

This is the seam CosySim downstream code expects: agents, interceptors, skills
and the SSE server all call ``orchestrator.infer(...)`` and never touch the
daemon client directly.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional

from harness.inference.client import InferenceResponse
from harness.inference.inference_config import InferenceConfig
from harness.inference.router import InferenceRequest, Priority, get_router

logger = logging.getLogger(__name__)

_PRIORITY = {
    "realtime": Priority.REALTIME,
    "interactive": Priority.INTERACTIVE,
    "background": Priority.BACKGROUND,
    "batch": Priority.BATCH,
}


class InferenceOrchestrator:
    def infer(
        self,
        *,
        agent_id: str = "",
        prompt: Optional[str] = None,
        messages: Optional[List[dict]] = None,
        priority: str = "interactive",
        config: Optional[InferenceConfig] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        on_delta: Optional[Callable[[str], None]] = None,
        timeout: float = 120.0,
    ) -> InferenceResponse:
        """Run one governed-friendly inference call and return the result."""
        cfg = config or InferenceConfig()
        if temperature is not None:
            cfg.temperature = temperature
        if max_tokens is not None:
            cfg.max_tokens = max_tokens

        req = InferenceRequest(
            priority=_PRIORITY.get(priority, Priority.INTERACTIVE),
            agent_id=agent_id,
            prompt=prompt,
            messages=messages,
            config=cfg,
            on_delta=on_delta,
        )
        return get_router().submit_sync(req, timeout=timeout)


_ORCH: Optional[InferenceOrchestrator] = None


def get_orchestrator() -> InferenceOrchestrator:
    global _ORCH
    if _ORCH is None:
        _ORCH = InferenceOrchestrator()
    return _ORCH
