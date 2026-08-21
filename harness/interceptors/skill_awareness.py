"""
SkillAwarenessInterceptor (priority 30)
======================================

Pre-call: injects a compact list of the skills available in this session so the
model knows what tools it may invoke. Pairs with the ephemeral tool-calling
loop in :mod:`harness.toolcore.tools`.
"""

from __future__ import annotations

from harness.toolcore.comms_framework import InterceptorBase, ResponseContext


class SkillAwarenessInterceptor(InterceptorBase):
    name = "skill_awareness"
    priority = 30

    def pre_call(self, ctx: ResponseContext) -> None:
        try:
            from harness.skills.registry import SKILL_REGISTRY
            metas = SKILL_REGISTRY.get_available()
        except Exception:
            return
        if not metas:
            return
        lines = [f"- {m.name}: {m.description}" for m in metas[:40]]
        ctx.system_prompt = (ctx.get("system_prompt", "") +
                             "\n\n# Available skills\n" + "\n".join(lines)).strip()
