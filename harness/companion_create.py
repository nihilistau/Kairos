"""CREATE A COMPANION WHO IS NOT BLANK (2026-11-26).

`home.create()` makes an empty folder; a companion born from that has no voice, no face, no
wardrobe, and a persona that — copied straight from the template — tells her she is called
"Kairos". This is the one way a companion is made, by every door (the Companion window,
`tools/companion.py create`, a bundle imported without some of its parts, and the
first-time setup):

    persona   the template's fragments with HER name written in, and a persona.md that
              holds the personality-state block the persona writer keeps up to date
    face      the bundled default set laid into her avatar folder (avatar_seed's own rules:
              fills gaps, offered once, never fails) — one outfit, seven faces, six
              gestures, the reference and character.txt every later look is grown from
    voice     her own voice in her own knobs (tuning.json): LOCAL by default (LFM3 on this
              machine — offline, no key), plus a provider voice no other companion here
              already speaks with, kept ready for when you switch provider

WHAT IT DOES NOT DO. The default face is the one Kairos ships, so every new companion
starts with it until you give her her own: replace `character.txt` and `_reference.png`
together in her avatar folder and generate (the Wardrobe window / tools/avatar_gen.py).
Making a new face means calling an image service, and creating a companion must not spend
money or need a key.

Gate: G-COMPANION-CREATE (harness_tests/g_companion_create.py).
"""
from __future__ import annotations

import json
import os
import re
import shutil
from typing import Dict, Iterable, List, Optional

from harness import home as H

# The xAI voices, women's first: a companion's default is a woman's voice, as the template's
# is. The order is the order new companions are offered them.
XAI_VOICES = ["eve", "luna", "carina", "iris", "celeste", "ara", "rex", "leo"]
LFM3_VOICES = ["female", "male"]
SEEDS = ("persona", "face", "voice")


def template_dir() -> str:
    for d in (os.path.join(H.ROOT, "persona-template"),
              os.path.join(H.ROOT, "kairos-export", "persona-template")):
        if os.path.isdir(d):
            return d
    return ""


def face_dir() -> str:
    """The bundled default set: the profile's SP_AVATAR_DEFAULTS, else assets/ (the export),
    else kairos-export/ (this tree — the set has always lived there and only the export
    copies it to assets/, which is why a fresh home here used to get no face at all)."""
    for d in (os.environ.get("SP_AVATAR_DEFAULTS", ""),
              os.path.join(H.ROOT, "assets", "avatar-default"),
              os.path.join(H.ROOT, "kairos-export", "avatar-default")):
        if d and os.path.isfile(os.path.join(d, "SET.json")):
            return d
    return ""


# ── persona ──────────────────────────────────────────────────────────────────────────────
_NAMED = re.compile(r"\bYour name is \w[\w'-]*\.")


def seed_persona(paths: Dict[str, str], name: str) -> int:
    """The template, named. Fills gaps only: an existing fragment is never overwritten."""
    src = template_dir()
    pd, pf = paths["persona_dir"], paths["persona_file"]
    os.makedirs(pd, exist_ok=True)
    n = 0
    if src:
        for fn in sorted(os.listdir(src)):
            d = os.path.join(pd, fn)
            if not fn.endswith(".md") or os.path.exists(d):
                continue
            with open(os.path.join(src, fn), encoding="utf-8") as f:
                text = f.read()
            # Her name, where the template states one. The two template-maintenance lines
            # ("Copy persona-template/…") are about a step this module just did for you.
            text = _NAMED.sub("Your name is %s." % name, text)
            text = "\n".join(l for l in text.split("\n")
                             if not l.startswith("> Copy `persona-template/`"))
            with open(d, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            n += 1
    if not os.path.exists(pf):
        # The personality-state block lives here; the fragments above are her prose.
        with open(pf, "w", encoding="utf-8", newline="\n") as f:
            f.write("%s.\n\n## Personality state\nmood: calm\n" % name)
        n += 1
    return n


# ── face and wardrobe ────────────────────────────────────────────────────────────────────
def seed_face(paths: Dict[str, str]) -> dict:
    """avatar_seed.seed() pointed at THIS home's avatar folder and the bundled set."""
    src = face_dir()
    if not src:
        return {"ok": True, "seeded": False, "why": "no bundled set on this machine"}
    from harness.control import avatar_seed
    saved = {k: os.environ.get(k) for k in ("SP_AVATAR_DIR", "SP_AVATAR_DEFAULTS")}
    os.environ["SP_AVATAR_DIR"] = paths["avatar_dir"]
    os.environ["SP_AVATAR_DEFAULTS"] = src
    try:
        os.makedirs(paths["avatar_dir"], exist_ok=True)
        return avatar_seed.seed()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ── voice ────────────────────────────────────────────────────────────────────────────────
def voices_in_use(exclude: str = "") -> List[str]:
    """The xAI voice each other companion on this machine speaks with (her knob, or the
    knob's default when she never set one)."""
    used = []
    for h in H.list_homes():
        if h.get("error") or os.path.normcase(h["dir"]) == os.path.normcase(exclude or "~"):
            continue
        try:
            with open(H.resolve(h["dir"])["tuning"], encoding="utf-8") as f:
                used.append(str(json.load(f).get("voice.xai_voice") or "ara"))
        except (OSError, ValueError, H.HomeError):
            used.append("ara")
    return used


def pick_voice(exclude: str = "") -> str:
    used = set(voices_in_use(exclude))
    return next((v for v in XAI_VOICES if v not in used), XAI_VOICES[0])


def seed_voice(paths: Dict[str, str], voice: str = "", home: str = "") -> str:
    """Her voice, written into HER knobs. Never overwrites a voice already chosen."""
    voice = (voice or pick_voice(home)).lower()
    if voice not in XAI_VOICES:
        raise H.HomeError(f"unknown voice {voice!r}; one of {', '.join(XAI_VOICES)}")
    p = paths["tuning"]
    cur = {}
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            cur = json.load(f)
    if cur.get("voice.xai_voice"):
        return cur["voice.xai_voice"]
    cur["voice.xai_voice"] = voice
    cur.setdefault("voice.lfm3_voice", "male" if voice in ("rex", "leo") else "female")
    # LOCAL BY DEFAULT (his call, 2026-11-26): she speaks with the voice on this machine —
    # offline, no key, no cost. Her provider voice above is kept for when he switches.
    cur.setdefault("voice.method", "lfm3")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=1)
    from harness.store_io import replace_atomic
    replace_atomic(tmp, p)
    return voice


# ── the one door ─────────────────────────────────────────────────────────────────────────
def create(cid: str, name: str = "", *, voice: str = "", seeds: Iterable[str] = SEEDS) -> dict:
    """A new companion: home, persona, face, voice. Refuses an id that exists."""
    name = (name or cid).strip() or cid
    home = H.create(cid, name)
    return {"ok": True, "id": cid, "name": name, "home": home, **fill(home, name, voice=voice, seeds=seeds)}


def fill(home: str, name: str, *, voice: str = "", seeds: Iterable[str] = SEEDS) -> dict:
    """Seed what an existing home lacks (used by a bundle import that brought only some
    parts). Every seed fills gaps only."""
    paths = H.resolve(home)
    out = {}
    if "persona" in seeds:
        out["persona_files"] = seed_persona(paths, name)
    if "face" in seeds:
        r = seed_face(paths)
        out["face"] = r.get("set") if r.get("seeded") else ""
        out["face_why"] = r.get("why", "")
    if "voice" in seeds:
        out["voice"] = seed_voice(paths, voice, home)
    os.makedirs(os.path.dirname(paths["registry"]), exist_ok=True)
    open(paths["registry"], "a").close()
    return out
