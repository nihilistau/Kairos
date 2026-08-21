"""
Query Router
===========

Tiered knowledge lookup: Q&A cache -> vector search -> LLM fallback (with
write-back). A slimmed version of CosySim's 7-tier NexusQueryRouter; the
remaining tiers (managed RAG, NLM, etc.) are documented seams in
``docs/SPEC-NEXUS.md`` and register as additional tiers here.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from harness.nexus.client import get_nexus_client

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    answer: str = ""
    source: str = "none"          # cache | vector | llm | none
    confidence: float = 0.0
    cached: bool = False
    query_time_ms: float = 0.0
    sources: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class NexusQueryRouter:
    CACHE_CONFIDENCE = 0.90
    VECTOR_CONFIDENCE = 0.82

    def __init__(self, llm_callback: Optional[Callable[[str], str]] = None) -> None:
        self._llm = llm_callback

    def set_llm(self, cb: Callable[[str], str]) -> None:
        self._llm = cb

    def query(
        self,
        question: str,
        *,
        min_confidence: float = 0.3,
        use_llm: bool = True,
    ) -> QueryResult:
        t0 = time.time()
        client = get_nexus_client()

        # Tier 1: Q&A cache
        qa = client.find_qa(question, limit=1)
        if qa and qa[0].get("score", 0) >= 0.6:
            return self._done(QueryResult(qa[0]["answer"], "cache",
                              self.CACHE_CONFIDENCE, cached=True), t0)

        # Tier 2: vector search over entries
        hits = client.search(question, limit=3)
        if hits and hits[0].score >= 0.4:
            answer = hits[0].content[:600]
            return self._done(QueryResult(answer, "vector",
                              min(self.VECTOR_CONFIDENCE, 0.5 + hits[0].score / 2),
                              sources=[h.title for h in hits]), t0)

        # Tier 3: LLM fallback + write-back
        if use_llm and self._llm:
            try:
                answer = self._llm(question)
                if answer:
                    client.add_qa(question, answer)  # learn for next time
                    return self._done(QueryResult(answer, "llm", 0.6), t0)
            except Exception as exc:
                logger.error("[QueryRouter] llm fallback failed (operation=query): %s", exc)

        return self._done(QueryResult(confidence=0.0), t0)

    @staticmethod
    def _done(result: QueryResult, t0: float) -> QueryResult:
        result.query_time_ms = (time.time() - t0) * 1000
        return result


_ROUTER: Optional[NexusQueryRouter] = None


def get_query_router(llm_callback: Optional[Callable[[str], str]] = None) -> NexusQueryRouter:
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = NexusQueryRouter(llm_callback)
    elif llm_callback is not None:
        _ROUTER.set_llm(llm_callback)
    return _ROUTER
