"""
Interceptors — built-in pipeline stages.

Each interceptor subclasses :class:`~harness.toolcore.comms_framework.InterceptorBase`
and declares a ``priority`` (lower runs first). The default registry mirrors the
CosySim ordering: knowledge hydration early (pre-call), shaping/sync late
(post-call).

Build a pipeline from config with :func:`build_pipeline`.
"""

from __future__ import annotations

import os
from typing import Dict, List, Type

from harness.toolcore.comms_framework import InterceptorBase, InterceptorPipeline
from harness.interceptors.nexus_prompt import NexusPromptInterceptor
from harness.interceptors.response_shaper import ResponseShaperInterceptor
from harness.interceptors.skill_awareness import SkillAwarenessInterceptor

# name -> class registry (extend by importing + appending here or via register())
_REGISTRY: Dict[str, Type[InterceptorBase]] = {
    NexusPromptInterceptor.name: NexusPromptInterceptor,
    SkillAwarenessInterceptor.name: SkillAwarenessInterceptor,
    ResponseShaperInterceptor.name: ResponseShaperInterceptor,
}

# PF-B3: the self-modify-personality stage writes persona.md, so it is OPT-IN (SP_PERSONALITY=1).
if os.environ.get("SP_PERSONALITY", "0") == "1":
    from harness.interceptors.personality_state import PersonalityStateInterceptor
    _REGISTRY[PersonalityStateInterceptor.name] = PersonalityStateInterceptor


def register_interceptor(cls: Type[InterceptorBase]) -> None:
    _REGISTRY[cls.name] = cls


def available() -> List[str]:
    return list(_REGISTRY.keys())


def build_pipeline(enabled: Dict[str, bool] | None = None) -> InterceptorPipeline:
    """Build a pipeline from an enable-map (defaults: all on)."""
    pipe = InterceptorPipeline()
    for name, cls in _REGISTRY.items():
        if enabled is None or enabled.get(name, True):
            pipe.add(cls())
    return pipe


__all__ = [
    "InterceptorBase",
    "NexusPromptInterceptor",
    "SkillAwarenessInterceptor",
    "ResponseShaperInterceptor",
    "register_interceptor",
    "available",
    "build_pipeline",
]
