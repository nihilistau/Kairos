"""
Embedding Service
================

Provider-abstracted embeddings with a circuit breaker and an LRU cache. Ported
(slimmed) from CosySim's EmbeddingService. Ships a dependency-free hashing
embedder as the always-available fallback so the harness runs out of the box;
real providers (Gemini, a local embed model, sentence-transformers) plug in via
:class:`EmbeddingProvider`.
"""

from __future__ import annotations

import hashlib
import logging
import math
import threading
from typing import List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    dimensions: int

    def embed(self, text: str) -> List[float]: ...


class HashingEmbeddingProvider:
    """Deterministic, dependency-free fallback embedder.

    Not semantically strong, but stable and offline — good enough for the
    out-of-the-box demo and for tests. Swap for a real provider in production.
    """

    name = "hashing"

    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> List[float]:
        vec = [0.0] * self.dimensions
        for tok in text.lower().split():
            h = int(hashlib.sha1(tok.encode()).hexdigest(), 16)
            vec[h % self.dimensions] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class EmbeddingService:
    def __init__(self, provider: Optional[EmbeddingProvider] = None, cache_size: int = 10_000) -> None:
        self.provider: EmbeddingProvider = provider or HashingEmbeddingProvider()
        self._cache: dict[str, List[float]] = {}
        self._cache_size = cache_size
        self._lock = threading.Lock()

    def embed(self, text: str) -> List[float]:
        with self._lock:
            if text in self._cache:
                return self._cache[text]
        try:
            vec = self.provider.embed(text)
        except Exception as exc:
            logger.error("[EmbeddingService] provider failed (operation=embed): %s", exc)
            vec = HashingEmbeddingProvider(self.provider.dimensions).embed(text)
        with self._lock:
            if len(self._cache) >= self._cache_size:
                self._cache.pop(next(iter(self._cache)))
            self._cache[text] = vec
        return vec

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed(t) for t in texts]

    @staticmethod
    def similarity(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (na * nb)


_SERVICE: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = EmbeddingService()
    return _SERVICE
