"""NEXUS — knowledge management (embedded SQLite store or remote KMS)."""

from harness.nexus.client import NexusClient, NexusEntry, get_nexus_client
from harness.nexus.knowledge_pipeline import (
    KnowledgePipeline,
    PipelineResult,
    get_knowledge_pipeline,
)
from harness.nexus.query_router import NexusQueryRouter, QueryResult, get_query_router
from harness.nexus.embedding_service import (
    EmbeddingService,
    EmbeddingProvider,
    HashingEmbeddingProvider,
    get_embedding_service,
)

__all__ = [
    "NexusClient",
    "NexusEntry",
    "get_nexus_client",
    "KnowledgePipeline",
    "PipelineResult",
    "get_knowledge_pipeline",
    "NexusQueryRouter",
    "QueryResult",
    "get_query_router",
    "EmbeddingService",
    "EmbeddingProvider",
    "HashingEmbeddingProvider",
    "get_embedding_service",
]
