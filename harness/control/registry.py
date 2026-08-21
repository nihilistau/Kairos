"""
Control Plane Registry
====================

Single source of truth for harness launch targets (services + the inference
daemon). Ported from CosySim's control_plane_registry. The launcher and the
control API read this to know what to start, in what order, and on what port.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from harness.control.port_registry import get_port


@dataclass
class TargetDef:
    name: str
    type: str                      # "daemon" | "service" | "external"
    label: str
    auto_start: bool = False
    start_priority: int = 50       # lower starts first
    entrypoint: str = ""           # import path "module:callable" or binary
    port_key: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def port(self) -> int:
        return get_port(self.port_key) if self.port_key else 0


# The canonical catalogue. Extend by appending TargetDef entries.
TARGETS: Dict[str, TargetDef] = {
    "sp_daemon": TargetDef(
        name="sp_daemon", type="external", label="Kairos Daemon",
        auto_start=True, start_priority=0, port_key="sp_daemon",
        entrypoint="sp-daemon",
        meta={"note": "launched via harness.inference.ServerController"},
    ),
    "gateway": TargetDef(
        name="gateway", type="service", label="OpenAI-compat SSE Gateway",
        auto_start=True, start_priority=10, port_key="gateway",
        entrypoint="harness.server.app:run",
    ),
    "oracle": TargetDef(
        name="oracle", type="service", label="Observability",
        auto_start=False, start_priority=20, port_key="oracle",
        entrypoint="harness.observability.oracle:run",
    ),
}


def all_targets() -> Dict[str, TargetDef]:
    return dict(TARGETS)


def autostart_targets() -> List[TargetDef]:
    return sorted([t for t in TARGETS.values() if t.auto_start],
                  key=lambda t: t.start_priority)


def get_target(name: str) -> TargetDef | None:
    return TARGETS.get(name)
