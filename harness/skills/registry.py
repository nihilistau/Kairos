"""
Skill Registry
=============

Thread-safe registry of all ``@skill``-decorated functions, grouped by pack.
Provides discovery (by pack / category / tag), JSON-schema export for tool
calling, and cooldown-enforced execution.
"""

from __future__ import annotations

import inspect
import threading
from typing import Any, Callable, Dict, List, Optional

from harness.skills.skill import CooldownTracker, SkillMeta


# ──── JSON-schema helper ──────────────────────────────────────────────────
_PY_JSON = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _schema_for(meta: SkillMeta) -> Dict[str, Any]:
    """Build an OpenAI-style function schema from a skill's signature."""
    sig = inspect.signature(meta.func)
    props: Dict[str, Any] = {}
    required: List[str] = []
    for pname, p in sig.parameters.items():
        if pname in ("self", "cls"):
            continue
        ann = p.annotation
        origin = getattr(ann, "__origin__", None)
        base = ann
        if origin is not None and getattr(ann, "__args__", None):
            # unwrap Optional[X] / List[X] to first arg's base type
            base = ann.__args__[0]
        jtype = _PY_JSON.get(base, "string")
        props[pname] = {"type": jtype}
        if p.default is inspect.Parameter.empty:
            required.append(pname)
    return {
        "type": "function",
        "function": {
            "name": meta.name,
            "description": meta.description,
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }


class SkillRegistry:
    """Maps pack -> [SkillMeta] and name -> SkillMeta."""

    def __init__(self) -> None:
        self._by_pack: Dict[str, List[SkillMeta]] = {}
        self._by_name: Dict[str, SkillMeta] = {}
        self._cooldowns = CooldownTracker()
        self._lock = threading.Lock()

    # ---- write ----------------------------------------------------------
    def register(self, meta: SkillMeta) -> None:
        with self._lock:
            self._by_pack.setdefault(meta.pack, []).append(meta)
            self._by_name[meta.name] = meta

    def reset(self) -> None:
        with self._lock:
            self._by_pack.clear()
            self._by_name.clear()
        self._cooldowns.reset()

    # ---- read -----------------------------------------------------------
    def get_skill(self, name: str) -> Optional[SkillMeta]:
        return self._by_name.get(name)

    def get_pack_metas(self, pack: str) -> List[SkillMeta]:
        return list(self._by_pack.get(pack, []))

    def get_pack_tools(self, pack: str) -> List[Callable]:
        return [m.func for m in self._by_pack.get(pack, [])]

    def all_packs(self) -> List[str]:
        return list(self._by_pack.keys())

    def get_by_category(self, category: str) -> List[SkillMeta]:
        category = category.lower()
        return [m for m in self._by_name.values() if m.category == category]

    def get_available(
        self, *, tags: Optional[List[str]] = None, category: str = ""
    ) -> List[SkillMeta]:
        out = []
        for m in self._by_name.values():
            if category and m.category != category.lower():
                continue
            if tags and not (set(tags) & set(m.tags)):
                continue
            if not self._cooldowns.can_use(m.name, m.cooldown_secs):
                continue
            out.append(m)
        return out

    # ---- schema export (for tool calling) -------------------------------
    def schemas(self, names: Optional[List[str]] = None, pack: str = "") -> List[Dict[str, Any]]:
        if names:
            metas = [self._by_name[n] for n in names if n in self._by_name]
        elif pack:
            metas = self.get_pack_metas(pack)
        else:
            metas = list(self._by_name.values())
        return [_schema_for(m) for m in metas]

    def describe(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
            pack: [
                {"name": m.name, "description": m.description, "category": m.category,
                 "cooldown": m.cooldown_secs, "cost": m.cost, "tags": m.tags}
                for m in metas
            ]
            for pack, metas in self._by_pack.items()
        }

    # ---- execution ------------------------------------------------------
    def execute_skill(self, name: str, *args: Any, **kwargs: Any) -> Any:
        meta = self._by_name.get(name)
        if meta is None:
            raise KeyError(f"unknown skill: {name}")
        if not self._cooldowns.can_use(name, meta.cooldown_secs):
            remaining = self._cooldowns.get_remaining(name, meta.cooldown_secs)
            return f"[skill on cooldown: {name} ({remaining:.1f}s)]"
        for prereq in meta.prerequisites:
            if not self._cooldowns.was_used(prereq):
                return f"[prerequisite not met: {name} needs {prereq}]"
        result = meta.func(*args, **kwargs)
        self._cooldowns.mark_used(name)
        return result


SKILL_REGISTRY = SkillRegistry()


def get_skill_registry() -> SkillRegistry:
    return SKILL_REGISTRY
