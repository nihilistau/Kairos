"""
NexusPromptInterceptor (priority 6)
==================================

Pre-call knowledge hydration. Queries NEXUS for context relevant to the user
message and appends it to the system prompt before the LLM call. Ported from
CosySim's NexusPromptInterceptor; short TTL cache to avoid hammering the KMS.
"""

from __future__ import annotations

import time
from typing import Dict, Tuple

from harness.toolcore.comms_framework import InterceptorBase, ResponseContext


class NexusPromptInterceptor(InterceptorBase):
    name = "nexus_prompt"
    priority = 6
    _TTL = 300.0

    def __init__(self) -> None:
        self._cache: Dict[str, Tuple[float, str]] = {}

    def pre_call(self, ctx: ResponseContext) -> None:
        query = ctx.get("user_message", "")
        if not query:
            return
        ctx_text = self._lookup(query)
        if ctx_text:
            ctx.system_prompt = (ctx.get("system_prompt", "") +
                                 f"\n\n# Relevant knowledge\n{ctx_text}").strip()

    def _lookup(self, query: str) -> str:
        now = time.time()
        hit = self._cache.get(query)
        if hit and (now - hit[0]) < self._TTL:
            return hit[1]
        try:
            from harness.nexus import get_query_router
            result = get_query_router().query(query, min_confidence=0.4)
            text = result.answer if result.confidence >= 0.4 else ""
        except Exception:
            text = ""
        self._cache[query] = (now, text)
        return text
