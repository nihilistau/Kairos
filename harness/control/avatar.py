"""THE AVATAR MANIFEST — what she can look like, and what exists to show.

THE GRID IS FACES x OUTFITS. Seven faces (her moods, mapped from the room's own
MOODS table) by four outfits (real garments, real files). It used to be called
faces x TIERS, with the outfit axis doubling as a HEAT LADDER: `tier_of_rung`
mapped scene heat onto clothing and `allowed_tiers(max_heat)` clamped what could
appear. That censor is GONE (2026-08-21, operator: "remove heat ceilings all
together and tiers. let her generate what she wishes. She or I decide any
ceilings."). An outfit is clothing, not a level; she wears what she chooses, he
asks in words if he wants something different, and no arithmetic in this module
arbitrates between them. (The roleplay ladder still paces SCENES; it no longer
gates a pixel here.)

WHAT SURVIVED, because it was never about the censor:

  * `MOODS` in `ui/src/room/tags.js` maps her moods onto SEVEN faces. G-AVATAR
    holds the two tables together in BOTH directions.
  * The OUTFIT ids (t0..t3) survive as OPAQUE PATH KEYS because they name 41
    files on disk; their WORDS live in wardrobe.OUTFITS and that is what anyone
    ever sees. No order, no ranges, no notes about heat.
  * VIDEO IS GROWN FROM THE STILL — image-to-video on the approved still, never
    frames generated independently: independently generated frames are
    independently generated PEOPLE.
  * THE REFERENCE ANCHORS EVERYTHING: one `_reference.png`, one `character.txt`.

Beside the grid: `looks/<id>.png|.webm` — open-ended looks (her wants made real,
his requests, moments). The wardrobe inventories those; this module only carries
the systematic grid.

NOTHING HERE GENERATES ANYTHING. This module answers "what is needed", "what
exists" and "where it lives". Generation is tools/avatar_gen.py and the gateway's
generate-now route.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The seven faces `MOODS` maps onto. Mirrored from ui/src/room/tags.js and held to it
# by G-AVATAR in both directions: a mood pointing at a face missing here fails, and a
# face here that no mood reaches fails too. A mirror nobody checks is just a second copy.
FACES: tuple = ("bright", "smirk", "soft", "calm", "wide", "down", "sharp")

# ── AND WHICH FEELING REACHES WHICH FACE (2026-08-04) ────────────────────────────────
# Same contract as FACES above, same gate, both directions. NINETEEN, NOT FOURTEEN —
# the five she uses MOST (naughty, smirk, intense, soft, amused) were once truncated
# off by a regex and her face was wrong precisely when she was most herself.
MOOD_FACE: Dict[str, str] = {
    "delighted": "bright", "excited": "bright",
    "playful": "smirk", "flirty": "smirk", "naughty": "smirk",
    "smirk": "smirk", "amused": "smirk",
    "tender": "soft", "warm": "soft", "soft": "soft",
    "peaceful": "calm", "quiet": "calm", "thoughtful": "calm",
    "wistful": "down", "sad": "down",
    "irritated": "sharp", "sharp": "sharp", "intense": "sharp",
    "curious": "wide",
}

# The outfit axis: OPAQUE PATH KEYS. Words, garments and choosing live in
# harness/control/wardrobe.py (OUTFITS). "t0" is the default only in the sense
# that it is what she wears at the desk when nothing else was chosen.
OUTFIT_IDS: tuple = ("t0", "t1", "t2", "t3")
DEFAULT_OUTFIT = "t0"

# What an asset can be. `still` is the anchor; `loop` and `clip` are grown from it.
KINDS: tuple = ("still", "loop", "clip")
EXT = {"still": ".png", "loop": ".webm", "clip": ".webm"}

# Gestures worth pre-rendering. Her invented ones (`[LAUGHING_GENTLY]` arrived
# unbidden) fall back to the still; the chip renders either way.
GESTURES: tuple = ("laughing", "thinking", "leaning_in", "looking_away", "blushing")


def root() -> str:
    return os.environ.get("SP_AVATAR_DIR") or os.path.join(_ROOT, "var", "room", "avatar")


def rel_path(face: str, outfit: str, kind: str = "still", gesture: str = "") -> str:
    if kind == "clip":
        return "%s/%s/clip-%s%s" % (face, outfit, gesture, EXT["clip"])
    return "%s/%s/%s%s" % (face, outfit, kind, EXT[kind])


def abs_path(face: str, outfit: str, kind: str = "still", gesture: str = "") -> str:
    return os.path.join(root(), *rel_path(face, outfit, kind, gesture).split("/"))


def have(face: str, outfit: str, kind: str = "still", gesture: str = "") -> bool:
    try:
        return os.path.getsize(abs_path(face, outfit, kind, gesture)) > 0
    except OSError:
        return False


def manifest() -> List[Dict[str, Any]]:
    """Every slot the grid could contain, and whether it exists yet. The generator
    reads this to know what is missing; the gate reads it to know nothing outside
    the committed tables ever appears. Looks are open-ended and inventoried by the
    wardrobe, not here."""
    rows: List[Dict[str, Any]] = []
    for face in FACES:
        for outfit in OUTFIT_IDS:
            for kind in ("still", "loop"):
                rows.append({"face": face, "outfit": outfit, "kind": kind,
                             "gesture": "", "path": rel_path(face, outfit, kind),
                             "have": have(face, outfit, kind)})
            for g in GESTURES:
                rows.append({"face": face, "outfit": outfit, "kind": "clip",
                             "gesture": g, "path": rel_path(face, outfit, "clip", g),
                             "have": have(face, outfit, "clip", g)})
    return rows


def resolve(face: str, outfit: str = "", kind: str = "still",
            gesture: str = "") -> Optional[Dict[str, Any]]:
    """The asset to show for this face in this outfit — or None, and the renderer
    keeps the SVG. NO CLAMPING: the outfit that arrives is the outfit looked up.
    A missing outfit cell falls back to the default outfit's cell (she is still
    HER even where the set is incomplete); a missing loop or clip degrades to the
    still before it degrades to the SVG — which is why a half-generated set is
    usable from the very first image."""
    if face not in FACES:
        face = "calm"
    outfit = outfit if outfit in OUTFIT_IDS else DEFAULT_OUTFIT
    for cand in dict.fromkeys((outfit, DEFAULT_OUTFIT)):
        if have(face, cand, kind, gesture):
            return {"face": face, "outfit": cand, "kind": kind, "gesture": gesture,
                    "path": rel_path(face, cand, kind, gesture)}
        if kind != "still" and have(face, cand, "still"):
            return {"face": face, "outfit": cand, "kind": "still", "gesture": "",
                    "path": rel_path(face, cand, "still")}
    return None


def status() -> Dict[str, Any]:
    rows = manifest()
    return {
        "faces": list(FACES),
        "outfits": list(OUTFIT_IDS),
        "gestures": list(GESTURES),
        "root": root(),
        "total": len(rows),
        "present": sum(1 for r in rows if r["have"]),
        # The reference image every prompt is anchored to. Until it exists and he has
        # approved it, nothing else should be generated.
        "reference": os.path.exists(os.path.join(root(), "_reference.png")),
    }
