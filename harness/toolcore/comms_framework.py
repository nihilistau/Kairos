"""
Comms Framework — Interceptor Pipeline + Governor
================================================

The governance core. Every model interaction flows through a priority-ordered
:class:`InterceptorPipeline`: pre-call interceptors hydrate the system prompt
and messages; the LLM is called; post-call interceptors shape and sync the
reply. The :class:`AgentGovernor` wraps an agent with this pipeline plus the
skill manifest and policy.

Ported from CosySim; the data carrier is :class:`ResponseContext` (a dict
subclass) so interceptors stay loosely coupled.
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ──── Context ─────────────────────────────────────────────────────────────
class ResponseContext(dict):
    """Mutable bag carrying one interaction through the pipeline.

    Well-known keys: ``system_prompt``, ``user_message``, ``messages``,
    ``reply``, ``session``, ``agent_id``, ``agent_name``, ``policy``,
    ``auto_results``, ``abort``, ``skip_llm``, ``tool_calls``, ``mood_tags``.
    """

    def __getattr__(self, item: str) -> Any:
        try:
            return self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


# ──── Interceptor base ────────────────────────────────────────────────────
class InterceptorBase(abc.ABC):
    """Base for all interceptors. Override ``pre_call`` and/or ``post_call``."""

    name: str = "base"
    priority: int = 50                       # lower runs first
    applicable_sessions: Optional[Set[str]] = None  # None = all

    def applies(self, ctx: ResponseContext) -> bool:
        if self.applicable_sessions is None:
            return True
        return ctx.get("session") in self.applicable_sessions

    def pre_call(self, ctx: ResponseContext) -> None:  # noqa: B027
        """Run before the LLM call. Modify system_prompt / messages."""

    def post_call(self, ctx: ResponseContext) -> None:  # noqa: B027
        """Run after the LLM call. Read / modify reply."""


# ──── Pipeline ────────────────────────────────────────────────────────────
class InterceptorPipeline:
    """Ordered chain of interceptors (ascending priority)."""

    def __init__(self) -> None:
        self._items: List[InterceptorBase] = []

    def add(self, interceptor: InterceptorBase) -> "InterceptorPipeline":
        self._items.append(interceptor)
        self._items.sort(key=lambda i: i.priority)
        return self

    def remove(self, name: str) -> None:
        self._items = [i for i in self._items if i.name != name]

    @property
    def names(self) -> List[str]:
        return [i.name for i in self._items]

    def run_pre(self, ctx: ResponseContext) -> None:
        for i in self._items:
            if ctx.get("abort"):
                return
            if i.applies(ctx):
                try:
                    i.pre_call(ctx)
                except Exception as exc:
                    logger.error("[Pipeline] pre_call failed (operation=pre, interceptor=%s): %s", i.name, exc)

    def run_post(self, ctx: ResponseContext) -> None:
        for i in self._items:
            if i.applies(ctx):
                try:
                    i.post_call(ctx)
                except Exception as exc:
                    logger.error("[Pipeline] post_call failed (operation=post, interceptor=%s): %s", i.name, exc)


# ──── Policy + manifest ───────────────────────────────────────────────────
@dataclass
class InteractionPolicy:
    max_reply_tokens: int = 512
    enforce_in_character: bool = True
    allow_explicit: bool = False
    required_tone: str = ""
    forbidden_topics: List[str] = field(default_factory=list)
    tool_call_limit: int = 6
    append_to_system: str = ""


TRIGGER_AUTO = "auto"
TRIGGER_OPTIONAL = "optional"
TRIGGER_REQUIRED = "required"


@dataclass
class SkillEntry:
    name: str
    trigger: str = TRIGGER_OPTIONAL
    description: str = ""


@dataclass
class SessionManifest:
    session: str
    skills: List[SkillEntry] = field(default_factory=list)

    def auto_skills(self) -> List[SkillEntry]:
        return [s for s in self.skills if s.trigger == TRIGGER_AUTO]

    def optional_skills(self) -> List[SkillEntry]:
        return [s for s in self.skills if s.trigger == TRIGGER_OPTIONAL]

    def required_skills(self) -> List[SkillEntry]:
        return [s for s in self.skills if s.trigger == TRIGGER_REQUIRED]


# ──── Governor ────────────────────────────────────────────────────────────
class AgentGovernor:
    """Wrap an agent's reply path with the interceptor pipeline + policy.

    The agent need only expose ``reply(user_message, system_prompt=..., messages=...)``.
    CONNECTS: InterceptorPipeline, SessionManifest, InteractionPolicy
    """

    def __init__(
        self,
        agent: Any,
        *,
        session: str = "default",
        pipeline: Optional[InterceptorPipeline] = None,
        policy: Optional[InteractionPolicy] = None,
        manifest: Optional[SessionManifest] = None,
    ) -> None:
        self.agent = agent
        self.session = session
        self.pipeline = pipeline or InterceptorPipeline()
        self.policy = policy or InteractionPolicy()
        self.manifest = manifest or SessionManifest(session)

    def _build_context(self, user_message: str, history: Optional[List] = None) -> ResponseContext:
        ctx = ResponseContext()
        ctx.session = self.session
        ctx.agent_id = getattr(self.agent, "agent_id", "")
        ctx.agent_name = getattr(self.agent, "name", ctx.agent_id)
        ctx.system_prompt = getattr(self.agent, "system_prompt", "") or ""
        ctx.user_message = user_message
        ctx.messages = list(history or [])
        ctx.policy = self.policy
        ctx.auto_results = {}
        ctx.reply = ""
        ctx.abort = False
        ctx.skip_llm = False
        return ctx

    def reply(self, user_message: str, *, history: Optional[List] = None, skip_gov: bool = False) -> str:
        if skip_gov:
            return self.agent.reply(user_message)
        ctx = self._build_context(user_message, history)
        self._run_auto_skills(ctx)
        self.pipeline.run_pre(ctx)
        if ctx.get("abort"):
            return ctx.get("reply", "")
        if not ctx.get("skip_llm"):
            ctx.reply = self.agent.reply(
                ctx.user_message,
                system_prompt=ctx.system_prompt,
                messages=ctx.messages,
            )
        self.pipeline.run_post(ctx)
        return ctx.reply

    def _run_auto_skills(self, ctx: ResponseContext) -> None:
        from harness.skills.registry import SKILL_REGISTRY
        for entry in self.manifest.auto_skills():
            try:
                ctx.auto_results[entry.name] = SKILL_REGISTRY.execute_skill(entry.name)
            except Exception as exc:
                logger.warning("[Governor] auto skill failed (operation=auto_skill, skill=%s): %s", entry.name, exc)

    def context_dump(self, user_message: str = "") -> ResponseContext:
        """Dry-run: build the context and run pre-call only (no LLM)."""
        ctx = self._build_context(user_message)
        self.pipeline.run_pre(ctx)
        return ctx


def get_governor(agent: Any, *, session: str = "default", **kwargs: Any) -> AgentGovernor:
    return AgentGovernor(agent, session=session, **kwargs)
