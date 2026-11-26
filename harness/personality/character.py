"""THE CHARACTER CREATION FLOW — answers in, persona sections out (2026-11-26, design §7b).

`character_flow.json` is the flow: questions, hints, examples, good practice, and for each
answer the persona section it becomes. This module turns a dict of answers into sections,
and applies them two ways:

    create(answers, cid)   a NEW companion (companion_create), her sections written first so
                           the template only fills what the flow left out
    apply(answers)         THIS companion's persona: each section the flow writes replaces
                           the one of the same name, which is RETIRED, never deleted

Skipping a step writes nothing (or the step's default, when it has one), so the template's
own section stands — "skip" is always safe.

Gate: G-CHARACTER-FLOW (harness_tests/g_character_flow.py).
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

from harness.personality import sections as S

FLOW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "character_flow.json")


def flow() -> dict:
    with open(FLOW, encoding="utf-8") as f:
        return json.load(f)


def _clean(s) -> str:
    return re.sub(r"[ \t]+", " ", str(s or "")).strip()


def sections_for(answers: Dict[str, object]) -> List[dict]:
    """The sections the answers make: [{file, order, title, text, step}]. A step with no
    answer (and no default) makes none."""
    out = []
    name = _clean(answers.get("name")) or "she"
    for st in flow()["steps"]:
        sec = st.get("section")
        if not sec:
            continue
        a = answers.get(st["id"])
        if isinstance(a, dict):
            text, chips, choice = _clean(a.get("text")), a.get("chips") or [], _clean(a.get("choice"))
        else:
            text, chips, choice = _clean(a), [], ""
        if not (text or chips or choice):
            text = _clean(st.get("default"))
            if not text:
                continue
        words = [c for c in chips if c in (st.get("chips") or [])]
        body = st.get("write", "{answer}")
        if "{chips}" in body:
            body = body.replace("{chips}", ", ".join(words[:-1]) + (" and " + words[-1] if len(words) > 1 else (words[0] if words else ""))) \
                if words else re.sub(r"You are \{chips\}\.\s*", "", body)
        if "{choice}" in body:
            body = body.replace("{choice}", choice) if choice else re.sub(r"[^.]*\{choice\}[^.]*\.\s*", "", body)
        body = body.replace("{answer}", text).replace("{name}", name).strip()
        if not body:
            continue
        out.append({"file": sec["file"], "order": sec["order"], "title": sec["title"],
                    "text": body, "step": st["id"]})
    return out


def preview(answers: Dict[str, object]) -> List[dict]:
    return sections_for(answers)


def _write_sections(secs: List[dict], directory: str) -> List[str]:
    written = []
    for s in secs:
        p = S._path(s["file"], directory)
        if os.path.exists(p):
            S._retire(p)                       # the old one kept, never overwritten in place
        S._write(p, S.render(s["title"], s["text"], s["order"]))
        written.append(s["file"])
    return written


def _character_draft(answers: Dict[str, object], avatar_dir: str) -> str:
    """The look, saved where the face generator will find it — as a DRAFT beside the
    shipped character.txt, because character.txt must match _reference.png (its own header
    says so), and her reference is still the default until a face of her own is made."""
    a = answers.get("look")
    text = _clean(a.get("text") if isinstance(a, dict) else a)
    if not text:
        return ""
    os.makedirs(avatar_dir, exist_ok=True)
    p = os.path.join(avatar_dir, "character-draft.txt")
    S._write(p, "# Her look, from the character flow. To make a face from it: put these words\n"
                "# into character.txt together with a new _reference.png (Wardrobe window).\n\n"
                + text + "\n")
    return p


def create(answers: Dict[str, object], cid: str, *, voice: str = "") -> dict:
    """A new companion from the flow."""
    from harness import companion_create as CC
    from harness import home as H
    name = _clean(answers.get("name"))
    if not name:
        raise H.HomeError("she needs a name")
    home = H.create(cid, name)
    paths = H.resolve(home)
    written = _write_sections(sections_for(answers), paths["persona_dir"])
    vo = answers.get("voice") if isinstance(answers.get("voice"), dict) else {}
    res = CC.fill(home, name, voice=str((vo or {}).get("xai") or voice or ""))
    if vo and vo.get("method") in ("xai", "lfm3"):
        _set_knob(paths["tuning"], "voice.method", vo["method"])
    if vo and vo.get("lfm3") in ("female", "male"):
        _set_knob(paths["tuning"], "voice.lfm3_voice", vo["lfm3"])
    draft = _character_draft(answers, paths["avatar_dir"])
    ppl = apply_people(answers, paths["people"], make_active=True)
    return {"ok": True, "id": cid, "name": name, "home": home, "sections": written,
            "character_draft": bool(draft), **res, **ppl}


def apply(answers: Dict[str, object], directory: Optional[str] = None) -> dict:
    """The flow's sections into THIS companion's persona (old ones retired)."""
    d = directory or S._dir()
    written = _write_sections(sections_for(answers), d)
    from harness import home as H
    draft = _character_draft(answers, H.path("avatar_dir"))
    ppl = apply_people(answers, H.path("people"), make_active=False)
    return {"ok": True, "sections": written, "character_draft": bool(draft), **ppl,
            "note": "saved — she reads it from her next session (her prefix is cached until then)"}


def _set_knob(path: str, key: str, value) -> None:
    cur = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            cur = json.load(f)
    cur[key] = value
    S._write(path, json.dumps(cur, indent=1) + "\n")


# ── WHO YOU ARE, AND THE PEOPLE IN YOUR LIFE (2026-11-26, the flow's last two steps) ────
_PET = re.compile(r"\b(cat|dog|pet|puppy|kitten|horse|pony|bird|parrot|budgie|rabbit|bunny|"
                  r"hamster|guinea pig|fish|lizard|snake|tortoise|turtle|ferret|chicken)s?\b", re.I)
_PLACE = re.compile(r"\b(house|home|cabin|cottage|flat|apartment|garden|beach|office|farm|town|"
                    r"city|village|place|shop|cafe|café|bar|pub|school|work)\b", re.I)


def people_lines(text: str) -> List[tuple]:
    """'Tuffy — my cat' -> ('Tuffy', 'pet', 'my cat'). One per line; a line with no
    separator is a bare name. The kind is a GUESS from the relation words, and the People
    window is where it is corrected."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip(" -•*\t")
        if not line:
            continue
        parts = re.split(r"\s+[—–-]\s+|\s*:\s+|,\s+", line, maxsplit=1)
        name = parts[0].strip()[:60]
        rel = parts[1].strip()[:200] if len(parts) > 1 else ""
        kind = "pet" if _PET.search(rel) else "place" if _PLACE.search(rel) or name.lower().startswith("the ") else "person"
        if name:
            out.append((name, kind, rel))
    return out


def apply_people(answers: Dict[str, object], people_path: str, *, make_active: bool) -> dict:
    """The 'you' and 'your_people' steps into a people log. Existing names are left alone."""
    from harness import people as PP
    saved = os.environ.get("SP_PEOPLE")
    os.environ["SP_PEOPLE"] = people_path
    added, you = [], None
    try:
        y = answers.get("you") if isinstance(answers.get("you"), dict) else {}
        yname = _clean(y.get("name"))
        if yname:
            you = next((u for u in PP.users() if yname.lower() in [n.lower() for n in u["names"]]), None) \
                or PP.add_user(yname, _clean(y.get("pronouns")))
            if make_active or not PP.active():
                PP.set_active(you["id"])
        lines = answers.get("your_people")
        lines = lines.get("text") if isinstance(lines, dict) else lines
        for name, kind, rel in people_lines(str(lines or "")):
            if PP.find(name):
                continue
            try:
                added.append(PP.add(name, kind=kind, relation=rel)["names"][0])
            except PP.PeopleError:
                continue
    finally:
        if saved is None:
            os.environ.pop("SP_PEOPLE", None)
        else:
            os.environ["SP_PEOPLE"] = saved
    return {"user": (you or {}).get("handle", ""), "people_added": added}
