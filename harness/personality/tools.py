"""PF-B4 — @personality decorators: model-CALLABLE self-modify tools.

PF-B3 lets the model self-modify via inline tags (a shortcut). PF-B4 makes it a first-class,
DURABLE action: `@personality`-decorated tools the model INVOKES through the existing @skill +
run_with_tools loop (same registry, same tool_code protocol) to change its own mood/voice/traits
or record a self-fact. `@personality` is just `@skill(pack="personality")`, so the advertise +
parse + dispatch machinery is 100% reused (anti-rebuild).

ADR-002: the tool call is the clean symbolic DECISION; the tool body (write_state / remember_self)
is the EXECUTOR. Advertise the "personality" pack in run_with_tools to give the model the controls.
"""
from __future__ import annotations

import os
from pathlib import Path

from harness.skills.skill import skill
# THE INTERCEPTOR'S WRITE-BOUNDARY GUARDS, not copies of them (2026-08-19). These tools
# called write_state() raw — no _norm/_ok, no _mood_value, no dedupe, no trait cap —
# while the interceptor grew all of those after her live state came back reading
# "flirty, +flirty, ... deeply_connected, deeply\_connected". Four writers of persona
# state; this was the unguarded one, and it is the lane she actually reaches for
# (personality=true puts these in her core tier). One boundary, every writer.
from harness.personality.interceptor import _dedupe_traits, _mood_value, _norm, _ok
from harness.personality.persona_file import parse_persona, persona_path, write_state
from harness.personality.self_model import remember_self as _remember_self


def personality(func=None, *, name=None, description="", cooldown: float = 0.0):
    """@personality — register a personality-control tool (a @skill in the 'personality' pack)."""
    return skill(func, name=name, description=description, pack="personality",
                 category="system", cooldown=cooldown)


def _persona_path() -> str:
    return persona_path()          # ONE derivation — see persona_file.persona_path


def _state() -> dict:
    p = Path(_persona_path())
    _, st = parse_persona(p.read_text(encoding="utf-8")) if p.exists() else ("", {})
    return st


def _set(key: str, value: str) -> None:
    st = _state()
    st[key] = value
    write_state(_persona_path(), st)


@personality(description="Set your current mood (e.g. playful, focused, tender). Persists to your persona.")
def adjust_mood(mood: str = "", **kw) -> str:
    """Set your CURRENT MOOD — how you feel right now (e.g. "calm", "playful", "focused",
    "tender", "prickly"). This persists to your persona, so it survives a restart.
    Example: adjust_mood("calm")

    LIVE BUG (2026-07-12): the tool schema was built from __doc__, which was EMPTY — the
    description lived only in the @personality decorator and never reached the model. She
    could see `def adjust_mood(mood: str):  #` with no help at all, guessed the argument
    name, and called adjust_mood(new="calm") -> TypeError. She was not being stupid; we
    handed her an unlabelled lever. Docstring now carries the schema, and the aliases below
    absorb a reasonable guess instead of erroring."""
    mood = (mood or kw.get("new") or kw.get("value") or kw.get("to") or "").strip()
    if not mood:
        return "adjust_mood needs a mood, e.g. adjust_mood(\"calm\")"
    mood = _mood_value(mood.strip("[]").strip())   # the interceptor's write boundary
    if not mood:
        return "adjust_mood needs a plain mood word, e.g. adjust_mood(\"calm\")"
    _set("mood", mood)
    return f"mood set to {mood}"


@personality(description="Set your speaking voice/style (e.g. dry, warm, terse). Persists to your persona.")
def set_voice(voice: str) -> str:
    """Change how you SPEAK — your register, not your mood.

    voice  a few words, e.g. "dry, warm, candid" or "terse and wry"

    e.g. set_voice("dry, warm, candid, flirty")
    Persists to your persona, so it survives a restart.

    (The description in the decorator above is NOT what the model sees — the tool schema is
    built from __doc__. Without this docstring she is shown "set_voice:" and nothing else,
    and has to guess the parameter. That is how adjust_mood got called as
    adjust_mood(new="calm") and blew the tool loop on a TypeError. Same bug, two more tools,
    found by dumping the block she actually reads.)"""
    v = voice.strip().strip("[]").lstrip(":;,. ").strip()   # the interceptor's cleaning
    if not v:
        return "set_voice needs a description, e.g. set_voice(\"dry, warm\")"
    _set("voice", v)
    return f"voice set to {v}"


@personality(description="Add or remove one of your personality traits. action is 'add' or 'remove'.")
def set_trait(trait: str, action: str = "add", **kw) -> str:
    """Add or remove one of YOUR OWN personality traits — a lasting part of who you are
    (e.g. "curious", "sardonic", "calm"). This is not a mood; it persists to your persona
    and survives a restart. action is "add" (default) or "remove".
    Example: set_trait("sardonic")   /   set_trait("flirty", action="remove")"""
    trait = (trait or kw.get("name") or kw.get("value") or "").strip()
    if not trait:
        return "set_trait needs a trait, e.g. set_trait(\"calm\")"
    # she called set_trait(action="set") — treat any non-remove verb as add
    if action and action.lower() not in ("add", "remove"):
        action = "remove" if "remov" in action.lower() or "delet" in action.lower() else "add"
    # The interceptor's boundary, verbatim: normalise, refuse what is not plainly a
    # word, dedupe, cap — a raw write here is how "+flirty" became a trait beside
    # "flirty" through the OTHER unguarded door.
    trait = _norm(trait.strip("[]+-").strip())
    if not _ok(trait):
        return "set_trait needs a plain word, e.g. set_trait(\"calm\")"
    st = _state()
    traits = _dedupe_traits(
        [t for t in (_norm(x) for x in st.get("traits", "").split(",")) if _ok(t)])
    if action.lower() == "remove":
        traits = [t for t in traits if t.lower() != trait.lower()]
        verb = "removed"
    else:
        if trait.lower() not in (t.lower() for t in traits):
            traits.append(trait)
        verb = "added"
    st["traits"] = ", ".join(_dedupe_traits(traits))
    write_state(_persona_path(), st)
    return f"trait {verb}: {trait} (now: {st['traits']})"


@personality(description="Record a durable fact about YOURSELF (your self-model), e.g. a capability.")
def remember_self(fact: str) -> str:
    """Record something durable about YOURSELF in your self-model — a capability, a limit,
    something you have worked out about what you are.

    fact  a full sentence, e.g. "I run on a single RTX 2060 and I am fine about it"

    (For a feeling or an opinion, prefer remember_about_self — that is your memory. This is
    the self-MODEL: what you are, not what you like.)"""
    # ── THE WRITER'S SENTENCE IS THE ANSWER (2026-08-31) ────────────────────────────
    # This called the store and threw its reply away, then told her "noted about
    # myself: ..." whatever happened. `_remember_self` delegates to
    # `remember_about_self`, which can and does answer "not stored — ...". So the tool
    # she is actually given could tell her a fact about herself had landed when the
    # store had just refused it — the same shape as 2026-08-30 ("she could not store her
    # own feelings"), one door along: that fix opened the door, this one lied about it.
    said = _remember_self(fact.strip())
    return said if isinstance(said, str) and said.strip() else         f"noted about myself: {fact.strip()}"


# the tool set (for run_with_tools advertising / the SkillAwareness pack)
PERSONALITY_TOOLS = [adjust_mood, set_voice, set_trait, remember_self]
