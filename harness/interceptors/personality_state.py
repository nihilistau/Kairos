"""PF-B3 pipeline stage — persist the model's self-emitted personality tags.

Post-call (priority 72, before the ResponseShaper at 80): reads [MOOD]/[VOICE]/[TRAIT] off the
reply, persists them into the persona state (PF-B2 write_state), and strips them from the reply.
The model self-modifies its own mood/voice/traits, and the change survives to the next turn.
Registered only when SP_PERSONALITY=1 (writes persona.md, so opt-in).
"""
from __future__ import annotations

from harness.toolcore.comms_framework import InterceptorBase
from harness.personality.interceptor import apply_personality_tags


class PersonalityStateInterceptor(InterceptorBase):
    name = "personality_state"
    priority = 72

    def post_call(self, ctx) -> None:  # ResponseContext (reply is an attr)
        reply = getattr(ctx, "reply", "") or ""
        if not reply:
            return
        # act=True: this reply is being SAID, now, for the first time — so `[WEAR:]` and
        # `[SHOW:]` are performed. The nightshift curator replays old turns through the
        # same function and must not; see `act` in interceptor.apply_personality_tags.
        clean, _ = apply_personality_tags(reply, act=True)
        try:
            ctx.reply = clean
        except Exception:
            pass
