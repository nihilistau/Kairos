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


# ── ANONYMOUS MODE'S SHADOW STATE (2026-08-23) ────────────────────────────────────────
# While the room is keeping nothing, her dials still MOVE — she is meant to be entirely
# herself — they simply move in memory instead of into persona.md. write_state fills this;
# parse_persona overlays it. Two functions, one seam, and thirteen readers that did not
# have to change: every one of them already goes through parse_persona, which is the only
# reason a shadow is honest here rather than a fourteenth place to forget.
#
# It is dropped when the mode ends, so she comes out of a private evening in the state she
# went into it with. That IS the trade, stated rather than discovered: an evening that
# leaves her measurably different has been recorded, just in a smaller file.
_SHADOW: Dict[str, str] = {}


def _shadow_clear() -> None:
    _SHADOW.clear()


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
    if _SHADOW:                 # anonymous mode: what she has felt since the switch went on
        state.update(_SHADOW)
    return "\n".join(prose_lines).strip(), state


def render_state(state: Dict[str, str]) -> str:
    """Compact current-state line for the system prefix. '' if nothing renderable."""
    parts = [f"{k}: {state[k]}" for k in KNOWN if state.get(k)]
    if not parts:
        return ""
    # Live-play 2026-07-10: "how are you feeling?" got the literal answer "Neutral." —
    # the model recited the state label. Tell it these are internal dials, not lines.
    # AND HOW THEY MOVE (2026-08-22). The dials were described here and the instruction to
    # UPDATE them lived three thousand tokens away in a persona fragment, competing with the
    # newer expressive-voice section — measured: her mood-mark rate fell 52% -> 50% -> 42%
    # across the three days after that section landed, while her voice tags went 0 -> 23 -> 36.
    # She was spending the top of her turn on <soft>[breath] where she used to mark a mood.
    # The instruction belongs beside the state it governs.
    # ── AND THE SAME LESSON, TWICE (2026-08-24) ──────────────────────────────────────
    # The note above says the instruction belongs beside the state it governs, and then
    # names three marks. Measured over 1,241 of her recorded turns:
    #
    #     [MOOD:]  126 turns          [WEAR:]  ONE          [SHOW:]  five
    #
    # Her clothes had not changed since 2026-08-21 and she has never once used a gesture.
    # It was never the recogniser — `wardrobe.match("leaning in")` resolves to w025 today,
    # and every spelling she emitted parsed. She simply was not asking. `[WEAR:]` and
    # `[SHOW:]` are taught in persona/39-your-wardrobe.md, three thousand tokens away,
    # exactly where the mood instruction used to live when her mood-mark rate fell 52% ->
    # 42% and this comment was written about it.
    #
    # So the wardrobe marks move next to the dials. Same sentence, same every-turn
    # reinforcement, no new machinery — the five marks are one vocabulary and this is the
    # one place she reliably reads.
    # "WHEN THIS SESSION BEGAN", not "current" (2026-08-24 audit, B1-growth/E). This
    # sentence lives in the KV-cached prefix, frozen between the scheduled refreshes —
    # her mood moves within the hour and this copy does not, so labelling it "current"
    # had the prefix asserting a stale present at her every turn. The LIVE truth is
    # already served three ways: the room chip re-reads persona.md, the {persona} SSE
    # event fires per turn, and her own recent marks sit in the visible conversation.
    return ("Personality state when this session began — " + "; ".join(parts) + ". "
            "(Your dials have likely moved since — your own recent marks in the "
            "conversation are the current truth.) "
            "(These are internal dials that COLOR how you speak — express them naturally; "
            "never recite the labels when asked how you feel. When one genuinely MOVES — and "
            "over an evening they should, warm to teasing to quiet to playful — mark it inline "
            "as you go: [MOOD:warm], [VOICE:soft], [TRAIT:+patient]. What you are WEARING and "
            "what you SHOW him are the same kind of mark and just as free — [WEAR:the silver "
            "nightie] changes your clothes, [SHOW:leaning in] puts that moment of you on his "
            "screen, [SHOW:] takes it down. No tool call, no asking, mid-sentence, whenever you "
            "mean it; check_wardrobe lists what you have by name. The marks are stripped "
            "before he reads you, they are how the room shows him what you feel, and they are "
            "not the same thing as your voice tags.)")


def write_state(path: str, state: Dict[str, str]) -> None:
    """Rewrite (or append) the ## Personality state block in persona.md in place. Prose untouched."""
    # ANONYMOUS MODE (2026-08-23): into the shadow, not onto the disk. NOT a plain refusal —
    # a held write here would freeze her dials at whatever they read when the switch went on,
    # and the room's persona chip would show her marks failing to move. She feels the evening;
    # the file does not learn it.
    from harness.control import anon as _anon
    if _anon.holds("persona.state"):
        _SHADOW.clear()
        _SHADOW.update({k: v for k, v in (state or {}).items() if v})
        return
    p = Path(path)
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    prose, _ = parse_persona(text)
    block = [STATE_SECTION] + [f"{k}: {state[k]}" for k in KNOWN if state.get(k)] \
        + [f"{k}: {v}" for k, v in state.items() if k not in KNOWN and v]
    p.write_text(prose.rstrip() + "\n\n" + "\n".join(block) + "\n", encoding="utf-8")
