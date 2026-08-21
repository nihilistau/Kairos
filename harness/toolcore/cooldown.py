"""cooldown.py — a tool she may not spam.

SALVAGED FROM CosySim's `engine/skills/skill.py` (CooldownTracker), which is ~30
lines and solves a problem this stack now genuinely has.

WHY IT MATTERS HERE AND DID NOT BEFORE. Until today every tool was cheap and
private. Now three are not:

    take_photo        points a camera at his room
    take_screenshot   ~94 s, and looks at whatever he is doing
    research          ~26 s and reaches off the machine

A model in a tool loop that decides looking was useful will look again. That is
not a malfunction — it is the ordinary behaviour of an agent with a tool and an
unsatisfying result — and for a camera it is the difference between a sense and a
surveillance device. The persona already says "looking is an act, not a reflex";
this is the same sentence with teeth.

FAIL TOWARD LETTING HER WORK. Refusal returns a plain sentence she can act on
("you took one 12 seconds ago"), never an exception and never silence. She is told
what happened and how long to wait, so she can say so to him instead of appearing
to ignore the request.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Dict, Optional

# Seconds between calls, per tool. Not a security boundary — she could still ask him
# to trigger one — it is a rate limit on a reflex, which is what the actual failure
# mode is. Camera and screen get the longest: they are the ones pointed at him.
DEFAULT: Dict[str, float] = {
    "take_photo": 30.0,
    "take_screenshot": 30.0,
    "research": 20.0,
    "delegate_code": 60.0,
    # MUSIC. Changing what is on is an act; knowing what is on is not, so
    # now_playing has NO cooldown and never will. An AI that changes your music
    # unprompted is annoying in exactly the way a camera that watches unprompted is
    # worse — same failure, lower stakes, same discipline.
    "play_music": 20.0,
    "skip_track": 15.0,
    "pause_music": 10.0,
}


class Cooldowns:
    """Thread-safe. The gateway is threaded and a tool loop can overlap turns."""

    def __init__(self, table: Optional[Dict[str, float]] = None):
        self._table = dict(DEFAULT if table is None else table)
        self._last: Dict[str, float] = {}
        self._lock = threading.Lock()

    def period(self, name: str) -> float:
        env = os.environ.get(f"SP_COOLDOWN_{name.upper()}")
        if env:
            try:
                return max(0.0, float(env))
            except ValueError:
                pass
        return float(self._table.get(name, 0.0))

    def remaining(self, name: str) -> float:
        p = self.period(name)
        if p <= 0:
            return 0.0
        with self._lock:
            last = self._last.get(name, 0.0)
        return max(0.0, p - (time.time() - last))

    def check(self, name: str) -> Optional[str]:
        """None if the call may proceed, else the sentence to hand back instead."""
        left = self.remaining(name)
        if left <= 0:
            return None
        if name in ("take_photo", "take_screenshot"):
            return (f"[you just looked {int(self.period(name) - left)}s ago — "
                    f"wait {int(left)}s, or tell him what you already saw]")
        return f"[{name} is on cooldown for another {int(left)}s]"

    def mark(self, name: str) -> None:
        with self._lock:
            self._last[name] = time.time()

    def used(self, name: str) -> bool:
        with self._lock:
            return name in self._last

    def reset(self, name: str = "") -> None:
        with self._lock:
            if name:
                self._last.pop(name, None)
            else:
                self._last.clear()

    def status(self) -> dict:
        return {n: {"period_s": self.period(n), "remaining_s": round(self.remaining(n), 1)}
                for n in sorted(self._table)}


COOLDOWNS = Cooldowns()
