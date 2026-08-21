"""
ResponseShaperInterceptor (priority 80)
======================================

Post-call hygiene: strips leaked system scaffolding and special-token
artifacts from the reply. Ported from CosySim's ResponseShaperInterceptor.
"""

from __future__ import annotations

import re

from harness.toolcore.comms_framework import InterceptorBase, ResponseContext

_LEAK_MARKERS = (
    "# Relevant knowledge",
    "# Available skills",
    "Available tools:",
    "REQUIRED:",
)
_SPECIAL = re.compile(r"<\|[^|]*\|>|</?s>")


class ResponseShaperInterceptor(InterceptorBase):
    name = "response_shaper"
    priority = 80

    def post_call(self, ctx: ResponseContext) -> None:
        reply = ctx.get("reply", "") or ""
        for marker in _LEAK_MARKERS:
            idx = reply.find(marker)
            if idx != -1:
                reply = reply[:idx].rstrip()
        reply = _SPECIAL.sub("", reply).strip()
        ctx.reply = reply
