"""
Skill Decorator
==============

The ``@skill`` decorator registers a plain Python function as a harness skill
(an LLM-callable tool with metadata: pack, category, cooldown, cost,
prerequisites). Ported from CosySim; the function is returned unchanged so it
stays directly callable.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


# ──── Categories ──────────────────────────────────────────────────────────
class SkillCategory:
    COMMUNICATION = "communication"
    MEMORY = "memory"
    MEDIA = "media"
    GAME = "game"
    SOCIAL = "social"
    ENVIRONMENT = "environment"
    SYSTEM = "system"
    NARRATIVE = "narrative"
    CODE = "code"


@dataclass
class SkillMeta:
    func: Callable
    name: str
    pack: str
    description: str
    tags: List[str] = field(default_factory=list)
    category: str = ""
    cooldown_secs: float = 0.0
    prerequisites: List[str] = field(default_factory=list)
    cost: float = 1.0
    pillar: str = ""


# ──── Cooldown enforcement ────────────────────────────────────────────────
class CooldownTracker:
    """Thread-safe cooldown + prerequisite bookkeeping."""

    def __init__(self) -> None:
        self._last: Dict[str, float] = {}
        self._lock = threading.Lock()

    def can_use(self, name: str, cooldown_secs: float) -> bool:
        if cooldown_secs <= 0:
            return True
        with self._lock:
            last = self._last.get(name, 0.0)
            return (time.time() - last) >= cooldown_secs

    def mark_used(self, name: str) -> None:
        with self._lock:
            self._last[name] = time.time()

    def was_used(self, name: str) -> bool:
        with self._lock:
            return name in self._last

    def get_remaining(self, name: str, cooldown_secs: float) -> float:
        with self._lock:
            last = self._last.get(name, 0.0)
        return max(0.0, cooldown_secs - (time.time() - last))

    def reset(self, name: str = "") -> None:
        with self._lock:
            if name:
                self._last.pop(name, None)
            else:
                self._last.clear()


def skill(
    func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    description: str = "",
    pack: str = "default",
    tags: Optional[List[str]] = None,
    category: str = "",
    cooldown: float = 0.0,
    prerequisites: Optional[List[str]] = None,
    cost: float = 1.0,
    pillar: str = "",
) -> Callable:
    """Register a function as a skill. Returns the function unchanged.

    Usage::

        @skill(pack="coder", description="Read a file", category="CODE")
        def read_file(path: str) -> str:
            ...
    """

    def _wrap(fn: Callable) -> Callable:
        from harness.skills.registry import SKILL_REGISTRY  # late import to avoid cycle

        meta = SkillMeta(
            func=fn,
            name=name or fn.__name__,
            pack=pack,
            description=description or (fn.__doc__ or "").strip().split("\n")[0],
            tags=list(tags or []),
            category=(category or "").lower(),
            cooldown_secs=cooldown,
            prerequisites=list(prerequisites or []),
            cost=cost,
            pillar=pillar,
        )
        SKILL_REGISTRY.register(meta)
        fn.__skill_meta__ = meta  # type: ignore[attr-defined]
        return fn

    if func is not None:  # bare @skill
        return _wrap(func)
    return _wrap
