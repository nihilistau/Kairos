"""
kairos-harness
=====================

A local-first agent harness: CosySim's MCP framework, NEXUS knowledge,
interceptor pipeline, ephemeral tool calling, SSE streaming and CLI — wired to
Kairos's own inference backends (``sp-daemon``) instead of LMStudio.

Top-level convenience re-exports::

    from harness import get_client, get_orchestrator, get_framework, get_governor
    from harness import skill, get_nexus_client, run_with_tools
"""

from __future__ import annotations

__version__ = "0.1.0"

from harness.config import get_config
from harness.inference import (
    get_client,
    get_orchestrator,
    get_router,
    InferenceConfig,
    StreamProcessor,
)
from harness.toolcore import (
    get_framework,
    get_governor,
    get_tool_registry,
    run_with_tools,
)
from harness.skills import skill, get_skill_registry
from harness.nexus import (
    get_nexus_client,
    get_knowledge_pipeline,
    get_query_router,
)

__all__ = [
    "__version__",
    "get_config",
    "get_client",
    "get_orchestrator",
    "get_router",
    "InferenceConfig",
    "StreamProcessor",
    "get_framework",
    "get_governor",
    "get_tool_registry",
    "run_with_tools",
    "skill",
    "get_skill_registry",
    "get_nexus_client",
    "get_knowledge_pipeline",
    "get_query_router",
]
