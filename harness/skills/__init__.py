"""Skills — the ``@skill`` decorator, registry, and built-in packs."""

from harness.skills.skill import skill, SkillCategory, SkillMeta, CooldownTracker
from harness.skills.registry import SkillRegistry, SKILL_REGISTRY, get_skill_registry

# Import built-in packs so their @skill registrations fire on package import.
from harness.skills import builtin  # noqa: F401

__all__ = [
    "skill",
    "SkillCategory",
    "SkillMeta",
    "CooldownTracker",
    "SkillRegistry",
    "SKILL_REGISTRY",
    "get_skill_registry",
]
