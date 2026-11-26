"""WHO SHE IS TALKING TO — the user's name and pronouns, from the profile's `[user]` section.

A fresh companion used to call everyone by the operator's name, because it was a literal in
about thirty prompt-visible strings and the export's name rule only swapped one name for
another. Now there is one source: `[user] name` / `[user] pronouns` in the profile, which
serve.py carries as SP_USER_NAME / SP_USER_PRONOUNS. Unset, both are neutral: "the user",
they/them.

`say(template)` fills these tokens, and ONLY these, so a template can still hold `{t}` or
JSON braces for a later .format():

    {user} {User}        the name, or "the user" / "The user"
    {USER}               upper-cased
    {he} {He} {HE}       subject pronoun        he / they
    {him} {Him} {HIM}    object pronoun         him / them
    {his} {His} {HIS}    possessive             his / their
    {himself}            reflexive              himself / themselves
    {is} {was} {has} {does}     verb agreement     is / are, was / were, has / have, does / do
    {s} {es}             third-person -s / -es  "{he} ask{s}" -> he asks / they ask
    {IS} {HAS} {S} {ES}  the same, upper-cased
    {companion}          HER name — the companion's own (SP_COMPANION_NAME, from the home's
                         companion.toml or the profile's [companion] name). Unset: "Kairos",
                         the one literal the export's name rule rewrites to its own default.

Read at call time, not import time, so a gate can set the env and see the result. Module
constants built at import still take the boot env, which serve.py sets before the gateway
imports anything. Gate: G-USER-NAME.
"""
from __future__ import annotations

import os
import re
from typing import Dict, Tuple

DEFAULT_NAME = "the user"
# Her name when nothing configures one (2026-11-26). "You are Kairos" was a literal in
# thirteen prompt-visible strings, so a Kairos user who named their companion anything else
# still had her told she was called Kairos. ONE literal now, here; G-USER-NAME §9 scans for
# any other.
DEFAULT_COMPANION = "Kairos"

_PRONOUNS: Dict[str, Tuple[str, str, str, str]] = {
    "he": ("he", "him", "his", "himself"),
    "she": ("she", "her", "her", "herself"),
    "they": ("they", "them", "their", "themselves"),
}


def name() -> str:
    """The configured name, or '' when unset. Callers wanting a word to print use called()."""
    return (os.environ.get("SP_USER_NAME") or "").strip()


def called() -> str:
    """What she calls him in prose: the name, or 'the user'."""
    return name() or DEFAULT_NAME


def user_id() -> str:
    """The active user's person id (harness/people.py), or '' — set by serve.py from the
    home's active user. Facts he tells her are stamped with it (said_by)."""
    return (os.environ.get("SP_USER_ID") or "").strip()


def companion() -> str:
    """Her own name: SP_COMPANION_NAME, else DEFAULT_COMPANION. Read at call time."""
    return (os.environ.get("SP_COMPANION_NAME") or "").strip() or DEFAULT_COMPANION


def example_name() -> str:
    """A name for worked examples ("The user's name is X"), where 'the user' would read as
    nonsense: the configured name, else a placeholder."""
    return name() or "Alex"


def pronouns() -> Tuple[str, str, str, str]:
    """(subject, object, possessive, reflexive). Accepts 'he', 'he/him', 'he/him/his', etc.
    An unknown subject with all three forms given is used as written; anything else is they."""
    raw = (os.environ.get("SP_USER_PRONOUNS") or "").strip().lower()
    if not raw:
        return _PRONOUNS["they"]
    parts = [p.strip() for p in raw.split("/") if p.strip()]
    if parts and parts[0] in _PRONOUNS:
        return _PRONOUNS[parts[0]]
    if len(parts) >= 3:
        refl = parts[3] if len(parts) > 3 else parts[1] + "self"
        return (parts[0], parts[1], parts[2], refl)
    return _PRONOUNS["they"]


def plural() -> bool:
    """True when the verbs agree with 'they' (are / have / ask)."""
    return pronouns()[0] == "they"


def name_pattern() -> str:
    """A regex alternative matching the configured name (lower-cased, escaped), or '' when
    unset — for detectors that used to list the operator's name beside 'he' and 'the user'.
    Use as `(?:...|" + ("|" + name_pattern() if name_pattern() else "") + ")`."""
    n = name().lower()
    return re.escape(n) if n else ""


_TOKEN = re.compile(r"\{(user|User|USER|he|He|HE|him|Him|HIM|his|His|HIS|himself|"
                    r"is|was|has|does|IS|HAS|s|es|S|ES|companion)\}")


def _table() -> Dict[str, str]:
    subj, obj, poss, refl = pronouns()
    many = plural()
    who = called()
    return {
        "user": who, "User": who[:1].upper() + who[1:], "USER": who.upper(),
        "he": subj, "He": subj.capitalize(), "HE": subj.upper(),
        "him": obj, "Him": obj.capitalize(), "HIM": obj.upper(),
        "his": poss, "His": poss.capitalize(), "HIS": poss.upper(),
        "himself": refl,
        "is": "are" if many else "is", "was": "were" if many else "was",
        "has": "have" if many else "has", "does": "do" if many else "does",
        "IS": "ARE" if many else "IS", "HAS": "HAVE" if many else "HAS",
        "s": "" if many else "s", "es": "" if many else "es",
        "S": "" if many else "S", "ES": "" if many else "ES",
        "companion": companion(),
    }


def say(template: str) -> str:
    """Fill the user tokens in `template`; every other brace is left alone."""
    t = _table()
    return _TOKEN.sub(lambda m: t[m.group(1)], template)
