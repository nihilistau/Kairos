"""
Port Registry
============

Canonical port assignments for harness services and external dependencies.
Single source of truth; resolve with :func:`get_port`. Config overrides via
``ports.<target>`` in the loaded config.
"""

from __future__ import annotations

from typing import Dict

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

_DEFAULT_PORTS: Dict[str, int] = {
    # Harness services
    "gateway": 8800,        # OpenAI-compatible SSE gateway (harness.server)
    "control": 8810,        # control-plane API / dashboard
    "oracle": 8820,         # observability
    # External dependencies
    "sp_daemon": 3000,      # Kairos inference daemon (/v1/chat)
    "nexus_kms": 8700,      # optional remote Nexus KMS
}

_ALIASES = {"nexus": "nexus_kms", "daemon": "sp_daemon"}


def get_port(target: str) -> int:
    target = _ALIASES.get(target, target)
    try:
        from harness.config import get_config
        override = get_config().get(f"ports.{target}")
        if override:
            return int(override)
    except Exception as _swx:
        _swallowed(_swlog, "get_port", _swx, lane="control")
    return _DEFAULT_PORTS.get(target, 0)


def get_service_url(target: str, host: str = "127.0.0.1") -> str:
    return f"http://{host}:{get_port(target)}"


def all_ports() -> Dict[str, int]:
    return dict(_DEFAULT_PORTS)
