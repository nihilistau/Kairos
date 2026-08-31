"""
Configuration
============

Dot-path config access over a YAML file (``config/default.yaml`` by default,
override with ``HARNESS_CONFIG``). Mirrors CosySim's ``get_config().get("a.b", default)``
contract. Falls back to a built-in default dict if PyYAML or the file is absent,
so the harness never hard-fails on config.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

_DEFAULTS: Dict[str, Any] = {
    "inference": {
        "daemon_url": "http://127.0.0.1:3000",
        "default_model": "your model",
        "timeout": 300,
    },
    "ports": {},
    "nexus": {"url": "", "db_path": "data/nexus.db"},
    "comms": {
        "interceptors": {
            "nexus_prompt": True,
            "skill_awareness": True,
            "response_shaper": True,
        }
    },
    "server": {"host": "127.0.0.1"},
}


def _deep_get(d: Dict[str, Any], path: str, default: Any) -> Any:
    cur: Any = d
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


class Config:
    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = data

    def get(self, path: str, default: Any = None) -> Any:
        return _deep_get(self._data, path, default)

    @property
    def data(self) -> Dict[str, Any]:
        return self._data


_CONFIG: Optional[Config] = None
_LOCK = threading.Lock()


def _load() -> Config:
    data = dict(_DEFAULTS)
    path = os.environ.get("HARNESS_CONFIG", "config/default.yaml")
    p = Path(path)
    if p.exists():
        try:
            import yaml  # type: ignore
            with p.open(encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or {}
            data = _merge(data, loaded)
        except Exception as _swx:
            _swallowed(_swlog, "_load", _swx, lane="harness")
    return Config(data)


def _merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def get_config() -> Config:
    global _CONFIG
    if _CONFIG is None:
        with _LOCK:
            if _CONFIG is None:
                _CONFIG = _load()
    return _CONFIG
