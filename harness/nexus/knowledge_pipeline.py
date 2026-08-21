"""
Knowledge Pipeline
=================

Unified ingest path: validate -> dedup -> quality-score -> store -> embed ->
auto-Q&A. Ported (slimmed) from CosySim's KnowledgePipeline. Returns a
structured :class:`PipelineResult`.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional

from harness.nexus.client import get_nexus_client

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    success: bool = False
    entry_id: str = ""
    qa_pairs_generated: int = 0
    was_duplicate: bool = False
    quality_score: float = 0.0
    embedded: bool = False
    error: str = ""
    duration_ms: float = 0.0


class KnowledgePipeline:
    def __init__(self) -> None:
        self._seen: set[str] = set()

    def ingest(
        self,
        title: str,
        content: str,
        content_type: str = "note",
        category: str = "general",
        tags: Optional[List[str]] = None,
        agent_id: str = "system",
        auto_qa: bool = True,
    ) -> PipelineResult:
        t0 = time.time()
        res = PipelineResult()

        # 1. validate
        if not title or len(content) < 20:
            res.error = "title required and content must be >= 20 chars"
            return res

        # 2. dedup
        fp = hashlib.sha256((title + content[:500]).encode()).hexdigest()
        if fp in self._seen:
            res.was_duplicate = True
            res.success = True
            res.duration_ms = (time.time() - t0) * 1000
            return res
        self._seen.add(fp)

        # 3. quality score (cheap heuristic)
        res.quality_score = self._score(content, content_type)

        # 4. store (+ embed happens inside the embedded store)
        client = get_nexus_client()
        entry_id = client.add_entry(title, content, content_type, category, tags or [], agent_id)
        if not entry_id:
            res.error = "store failed"
            return res
        res.entry_id = entry_id
        res.embedded = True

        # 5. auto-Q&A
        if auto_qa:
            qa_id = client.add_qa(f"What is {title}?", content[:400], category)
            res.qa_pairs_generated = 1 if qa_id else 0

        res.success = True
        res.duration_ms = (time.time() - t0) * 1000
        logger.info("[KnowledgePipeline] ingested (operation=ingest, id=%s, q=%.2f)",
                    entry_id, res.quality_score)
        return res

    @staticmethod
    def _score(content: str, content_type: str) -> float:
        score = 0.5
        if len(content) > 200:
            score += 0.2
        if content_type in ("document", "research", "code"):
            score += 0.2
        if "\n" in content:
            score += 0.1
        return min(1.0, score)


_PIPELINE: Optional[KnowledgePipeline] = None


def get_knowledge_pipeline() -> KnowledgePipeline:
    global _PIPELINE
    if _PIPELINE is None:
        _PIPELINE = KnowledgePipeline()
    return _PIPELINE
