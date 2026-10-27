"""changes — the append-only log of settings changes (`var/settings-changes.jsonl`).

Recording a change must never be the reason the change fails, so `log` swallows.
"""
from __future__ import annotations

import json
import logging
import os
import time

from harness.launch import var_dir

_log = logging.getLogger(__name__)


def _path() -> str:
    return os.path.join(var_dir(), "settings-changes.jsonl")


def log(source: str, what: str, old, new, **extra) -> None:
    try:
        path = _path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        row = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "source": source,
               "what": what, "old": old, "new": new, **extra}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    except Exception as e:                                       # noqa: BLE001
        try:
            _log.warning("settings change not logged: %s", e)
        except Exception:                                        # noqa: BLE001
            pass


def log_tuning(old: dict, new: dict) -> None:
    """One line per knob that moved (source `settings`). Lives here, not in the launch
    routes, so a knob write never needs tomlkit."""
    for k, v in new.items():
        log("settings", k, old.get(k), v)


def tail(n: int = 50) -> list:
    rows = []
    try:
        with open(_path(), encoding="utf-8") as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(r, dict):
                    rows.append(r)
    except OSError:
        return []
    return rows[-n:] if n > 0 else []
