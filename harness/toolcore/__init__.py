"""
MCP layer — framework singleton, interceptor/governor pipeline, tool calling.

Public singletons mirror CosySim's surface:

    get_framework()      -> MCPFramework (root state tree)
    get_governor(agent)  -> AgentGovernor (interceptor pipeline + policy)
    get_tool_registry()  -> ToolRegistry (ephemeral tools)
"""

from harness.toolcore.framework import (
    MCPFramework,
    AgentNode,
    SessionNode,
    FrameworkEvent,
    get_framework,
)
from harness.toolcore.comms_framework import (
    ResponseContext,
    InterceptorBase,
    InterceptorPipeline,
    AgentGovernor,
    InteractionPolicy,
    SessionManifest,
    SkillEntry,
    TRIGGER_AUTO,
    TRIGGER_OPTIONAL,
    TRIGGER_REQUIRED,
    get_governor,
)
from harness.toolcore.tools import (
    ToolSpec,
    ToolRegistry,
    run_with_tools,
    get_tool_registry,
)

__all__ = [
    "MCPFramework",
    "AgentNode",
    "SessionNode",
    "FrameworkEvent",
    "get_framework",
    "ResponseContext",
    "InterceptorBase",
    "InterceptorPipeline",
    "AgentGovernor",
    "InteractionPolicy",
    "SessionManifest",
    "SkillEntry",
    "TRIGGER_AUTO",
    "TRIGGER_OPTIONAL",
    "TRIGGER_REQUIRED",
    "get_governor",
    "ToolSpec",
    "ToolRegistry",
    "run_with_tools",
    "get_tool_registry",
]
