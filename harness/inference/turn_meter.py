"""turn_meter — is she generating RIGHT NOW, as the harness itself knows it.

The engine-agnostic answer to the daemon's `/v1/metrics tokens_per_sec`. Three
callers only ever used that number as a boolean — agency's idle gate, the ambient
eye's quiet guard, the CLI — and a foreign endpoint has no metrics door. The
gateway already counts turns in flight for graceful shutdown (`_sd_turn_start` /
`_sd_turn_end`, harness/control/shutdown._IN_FLIGHT); this is the same count,
owned by the inference package so a backend can report it without importing the
gateway. One writer (the gateway's turn hooks), any reader.
"""
from __future__ import annotations

import threading
import time

_LOCK = threading.Lock()
_IN_FLIGHT = 0
_LAST_START = 0.0
_LAST_END = 0.0


def start() -> None:
    global _IN_FLIGHT, _LAST_START
    with _LOCK:
        _IN_FLIGHT += 1
        _LAST_START = time.monotonic()


def end() -> None:
    global _IN_FLIGHT, _LAST_END
    with _LOCK:
        _IN_FLIGHT = max(0, _IN_FLIGHT - 1)
        _LAST_END = time.monotonic()


def in_flight() -> int:
    with _LOCK:
        return _IN_FLIGHT


def busy() -> bool:
    return in_flight() > 0


def metrics() -> dict:
    """The daemon-shaped readout: callers test `tokens_per_sec > 1.0` for "busy"."""
    n = in_flight()
    return {"tokens_per_sec": 10.0 if n else 0.0, "in_flight": n,
            "phase": "busy" if n else "idle", "source": "turn_meter"}
