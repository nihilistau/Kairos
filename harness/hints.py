"""FIRST-RUN HINTS — the room shows you around a clean setup (2026-11-26, design §7b).

The words are DATA (`config/hints.json`); the progress is per companion home (`hints` in
harness/home.py — per user once users exist, P4). A hint is shown on a CLEAN home only — her
registry has fewer than `clean_below_rows` rows — so a companion who already knows you is
never lectured, and once every hint is done, dismissed, or hints are switched off, nothing
shows.

DONE WHEN DONE: a hint carries `done_when: "open:<window>"`; the room reports each window it
opens and the matching hints are marked done. Dismissing is the other way out. Turning hints
off is one switch, and on again from the Companion window.

Gate: G-HINTS (harness_tests/g_hints.py).
"""
from __future__ import annotations

import json
import os
import time
from typing import Dict, List

from harness import home as H

HINTS = os.path.join(H.ROOT, "config", "hints.json")


def catalogue() -> dict:
    with open(HINTS, encoding="utf-8") as f:
        return json.load(f)


def _state_path() -> str:
    return H.path("hints")


def state() -> dict:
    try:
        with open(_state_path(), encoding="utf-8") as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    return {"done": list(s.get("done") or []), "dismissed": list(s.get("dismissed") or []),
            "off": bool(s.get("off")), "force": bool(s.get("force"))}


def _save(s: dict) -> None:
    p = _state_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({**s, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}, f, indent=1)
    from harness.store_io import replace_atomic
    replace_atomic(tmp, p)


def _rows() -> int:
    """Lines in her registry (a count, not a parse: this runs on every room load)."""
    reg = H.path("registry")
    try:
        with open(reg, "rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def clean(cat: dict = None) -> bool:
    cat = cat or catalogue()
    return _rows() < int(cat.get("clean_below_rows", 25))


def view() -> dict:
    """What the room shows: the pending hints in order, or none, and why."""
    cat = catalogue()
    s = state()
    gone = set(s["done"]) | set(s["dismissed"])
    pending = [h for h in cat["hints"] if h["id"] not in gone]
    active = not s["off"] and (s["force"] or clean(cat))
    why = ("off" if s["off"] else "shown" if active else "she already knows you (not a clean setup)")
    return {"ok": True, "active": active and bool(pending), "why": why if pending else "all done",
            "pending": pending if active else [], "total": len(cat["hints"]),
            "done": len(gone & {h["id"] for h in cat["hints"]}), "state": s}


def op(body: Dict) -> dict:
    """done | dismiss | opened (a window opened) | off | on | reset (show them all again)."""
    kind = str(body.get("op") or "")
    s = state()
    cat = catalogue()
    ids = {h["id"] for h in cat["hints"]}
    if kind in ("done", "dismiss"):
        hid = str(body.get("id") or "")
        if hid not in ids:
            raise ValueError(f"no hint {hid!r}")
        key = "done" if kind == "done" else "dismissed"
        if hid not in s[key]:
            s[key].append(hid)
    elif kind == "opened":
        win = "open:" + str(body.get("window") or "")
        for h in cat["hints"]:
            if h.get("done_when") == win and h["id"] not in s["done"]:
                s["done"].append(h["id"])
    elif kind == "off":
        s["off"] = True
    elif kind == "on":
        s["off"] = False
        s["force"] = True              # on by request shows them even on a home that is not new
    elif kind == "reset":
        s = {"done": [], "dismissed": [], "off": False, "force": True}
    else:
        raise ValueError("op must be done, dismiss, opened, off, on or reset")
    _save(s)
    return view()
