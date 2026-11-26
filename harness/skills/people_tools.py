"""HER PEOPLE TOOLS — she can know the people, pets and places in {his} life (2026-11-26).

    meet(name, kind, relation)   SUGGEST someone new she has heard of. It is a proposal:
                                 {he} confirm{s} it in the People window, and until then it
                                 is not anyone. Her guess about who someone is must not become
                                 a person on her word alone.
    note_about(who, fact)        remember something about someone she knows — through
                                 remember(), so every verdict, the off-the-record door and the
                                 `about` link apply exactly as to any other fact
    who_is(name)                 what she knows of someone: kind, relation, notes

Off the record, `meet` writes nothing (the `memory.row` door: a person is a memory too).
"""
from __future__ import annotations

from harness import people as PP


def meet(name: str, kind: str = "person", relation: str = "") -> str:
    """Suggest someone new {user} mentioned (person, pet, place, thing or org) — {he} confirm{s} it in People.

    e.g. meet("Tuffy", "pet", "{his} cat"); meet("Sam", "person", "{his} brother")"""
    from harness.control import anon
    if anon.holds("memory.row"):
        return anon.WHY
    kind = (kind or "person").strip().lower()
    if kind not in PP.KINDS:
        kind = "person"
    known = PP.find(name)
    if known:
        return f"you already know {known['names'][0]} ({known['kind']}, {known.get('relation') or 'no relation noted'})"
    try:
        r = PP.add(name, kind=kind, relation=relation, status="proposed", proposed_by="her")
    except PP.PeopleError as e:
        return f"(not suggested: {e})"
    return (f"suggested {r['names'][0]} ({kind}) — it waits for a yes in the People window; "
            "you can still talk about them meanwhile")


def note_about(who: str, fact: str) -> str:
    """Remember a fact about a person, pet or place you know — it is linked to them.

    e.g. note_about("Tuffy", "Tuffy hates the vacuum cleaner")"""
    p = PP.find(who)
    if not p:
        return f"(you do not know anyone called {who!r} yet — meet() them first, or just remember() it)"
    name = p["names"][0]
    text = (fact or "").strip()
    if not text:
        return "(nothing to remember)"
    if not any(n.lower() in text.lower() for n in p["names"]):
        text = f"{name}: {text}"                   # so the `about` link finds them
    from harness.skills.memory import remember
    return remember(text)


def who_is(name: str) -> str:
    """What you know about someone: who they are to {user}, and any notes.

    e.g. who_is("Tuffy")"""
    p = PP.find(name)
    if not p:
        return f"(no one called {name!r} — not yet)"
    bits = [f"{p['names'][0]} — {p['kind']}"]
    if len(p["names"]) > 1:
        bits.append("also called " + ", ".join(p["names"][1:]))
    if p.get("relation"):
        bits.append(p["relation"])
    if p.get("user"):
        bits.append(f"a user ({p['handle']})")
    if p.get("status") == "proposed":
        bits.append("suggested by you, not yet confirmed")
    if p.get("notes"):
        bits.append("notes: " + p["notes"][:300])
    return "; ".join(bits)


PEOPLE_TOOLS = [meet, note_about, who_is]
