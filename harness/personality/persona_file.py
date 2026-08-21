"""PF-B2 — structured, live-editable personality state inside persona.md.

persona.md stays pure VOICE prose, but MAY carry an optional machine-parseable block:

    ## Personality state
    voice: dry, warm
    mood: neutral
    traits: curious, candid, playful

`parse_persona` splits the prose from the state dict (never throws — a malformed block just yields
an empty state, so the prose always loads). `render_state` turns the state into a compact line for
the system prefix. `write_state` rewrites the block in place (the seam PF-B3/PF-B4 use for the model
to self-modify its own mood/voice/traits). Human-editable AND machine-editable, live on the next turn.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Tuple


def persona_path() -> str:
    """THE path to persona.md — SP_PERSONA_FILE, else <repo-root>/persona.md.

    One derivation (2026-08-19). SEVEN copies of this line existed — agent.py (twice),
    wardrobe.py, interceptor.py, tools.py, app.py, memory.py — each hand-counting its
    own dirname chain, and app.py's omitted abspath: the drifted copy proving why a
    path four different writers mutate gets resolved in exactly one place. This module
    is that place; it is the file's own module."""
    return (os.environ.get("SP_PERSONA_FILE")
            or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), "persona.md"))


STATE_SECTION = "## Personality state"
# recognised keys (rendered in this order); unknown keys are preserved but not rendered
KNOWN = ["voice", "mood", "traits"]


def parse_persona(text: str) -> Tuple[str, Dict[str, str]]:
    """Return (prose_without_state_block, state_dict). Robust: never raises."""
    lines = text.splitlines()
    state: Dict[str, str] = {}
    prose_lines = []
    i, n = 0, len(lines)
    while i < n:
        if lines[i].strip().lower() == STATE_SECTION.lower():
            i += 1
            while i < n and not lines[i].lstrip().startswith("## "):
                ln = lines[i].strip().lstrip("-").strip()
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    k, v = k.strip().lower(), v.strip()
                    if k and v:
                        state[k] = v
                i += 1
            continue
        prose_lines.append(lines[i])
        i += 1
    return "\n".join(prose_lines).strip(), state


def render_state(state: Dict[str, str]) -> str:
    """Compact current-state line for the system prefix. '' if nothing renderable."""
    parts = [f"{k}: {state[k]}" for k in KNOWN if state.get(k)]
    if not parts:
        return ""
    # Live-play 2026-07-10: "how are you feeling?" got the literal answer "Neutral." —
    # the model recited the state label. Tell it these are internal dials, not lines.
    return ("Current personality state — " + "; ".join(parts) + ". "
            "(These are internal dials that COLOR how you speak — express them naturally; "
            "never recite the labels when asked how you feel.)")


def write_state(path: str, state: Dict[str, str]) -> None:
    """Rewrite (or append) the ## Personality state block in persona.md in place. Prose untouched."""
    p = Path(path)
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    prose, _ = parse_persona(text)
    block = [STATE_SECTION] + [f"{k}: {state[k]}" for k in KNOWN if state.get(k)] \
        + [f"{k}: {v}" for k, v in state.items() if k not in KNOWN and v]
    p.write_text(prose.rstrip() + "\n\n" + "\n".join(block) + "\n", encoding="utf-8")
