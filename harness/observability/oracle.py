"""
Oracle — Observability
=====================

Lightweight structured logging + error aggregation, modeled on CosySim's
Oracle. Log messages follow the format::

    [MODULE] Description (operation=X): detail

so the aggregator can fingerprint and count errors by ``[prefix]`` + ``operation``.
Call :func:`get_logger` per module; call :func:`diagnose` for a quick snapshot.
"""

from __future__ import annotations

import logging
import re
import threading
from collections import Counter
from typing import Dict, List

_FINGERPRINT = re.compile(r"\[([^\]]+)\].*?\(operation=([^),]+)")


class ErrorAggregator(logging.Handler):
    """Counts ERROR+ records by (module, operation) fingerprint."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self._counts: Counter = Counter()
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        m = _FINGERPRINT.search(msg)
        key = f"{m.group(1)}:{m.group(2)}" if m else record.name
        with self._lock:
            self._counts[key] += 1

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def top(self, n: int = 20) -> List[tuple]:
        with self._lock:
            return self._counts.most_common(n)


_AGG = ErrorAggregator()
_INITIALIZED = False


def ensure_initialized() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        )
    root.addHandler(_AGG)
    _INITIALIZED = True


def get_logger(name: str) -> logging.Logger:
    ensure_initialized()
    return logging.getLogger(name)


def get_error_aggregator() -> ErrorAggregator:
    return _AGG


def diagnose() -> None:
    ensure_initialized()
    top = _AGG.top()
    print("=== Oracle ===")
    if not top:
        print("no errors recorded")
        return
    for key, count in top:
        print(f"  {count:5d}  {key}")


def run() -> None:  # entrypoint stub for the control registry
    ensure_initialized()
    diagnose()
