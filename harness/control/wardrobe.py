"""THE WARDROBE — what she is wearing, who decides, and what she may reach for.

ONE AUTHORITY: HER CHOICE (2026-08-21, operator: "remove heat ceilings all
together and tiers. let her generate what she wishes. She or I decide any
ceilings."). The history, kept because it explains the shape of what remains:
her appearance began as something that happened TO her — a roleplay rung mapped
onto a "tier" of clothing through `tier_of_rung`, clamped by a ceiling dial.
2026-08-02 freed her CHOICE from the ceiling; 2026-08-21 removed the ladder and
the ceiling arithmetic entirely. What she wears is what she chose, it persists
across turns and restarts, and if either of them wants it different they say so
in words — to each other, like people. No arithmetic arbitrates.

OUTFITS ARE CLOTHING, AND SHE IS TOLD SO — AND SO ARE THE PATHS NOW (2026-08-23).
This said `t0..t3` "survive only as opaque PATH KEYS over real files (renaming
would orphan 56 of them)". True, and the cost of leaving it was measured: a gate
went red and chasing it turned up w016 — "Black lace underwear" — filed under t0,
which is *the mesh top*. Spelled out that is obviously wrong; spelled t0 nobody
saw it for three days. So they are named: mesh-top, sheer-tee, lace-set, bodysuit.
The 56 files moved with them (tools/avatar/rename_outfits.py, reversible with
--undo), and `avatar.canon()` maps the old ids forever — at the path seam so no
FILE can go missing, and in match() so an id he still TYPES keeps working.

Every outfit carries `wearing` and `about` in plain language, and those strings are
what her tools return — never the ids, never a level, never a warning label.

TWO KINDS OF THING LIVE HERE. The generated SET is face x outfit, small and
systematic: seven expressions she wears while talking, in each garment. The
LOOKS and CLIPS are open-ended — her wants made real, whole moments, made
deliberately rather than enumerated. They are not interchangeable and the
library does not pretend they are.

NOTHING IS GENERATED HERE and nothing is deleted. This module answers "what
exists" and "what has she chosen". Files arrive from the generator or from the
operator's own hand; `import_clip` copies them in and writes a row.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from typing import Any, Dict, List, Optional

from harness.control import avatar as AV
from harness.store_io import read_bytes_retry, replace_atomic

# ── WHAT EACH TIER ACTUALLY IS, IN WORDS ──────────────────────────────────────────────
# Keyed to avatar.TIERS so there is one tier vocabulary, not two. `wearing` is the honest
# answer to "what is the difference between these": it is clothing, and framing, and how
# close the camera is. Saying so removes the mystique that made her cautious about her
# own wardrobe.
# ── HER OUTFITS. NOT TIERS. ───────────────────────────────────────────────────────────
#
# `t0..t3` was a HEAT LADDER borrowed from the roleplay engine, and borrowing it was the
# mistake. It made her everyday clothes a "level", invited her to treat her own wardrobe
# as a hazard scale, and put a ceiling in front of a decision that was never his to
# arbitrate — he has had that dial at maximum since the day it was built.
#
# The ids stay, because they are PATHS on disk and renaming them would orphan 56 files.
# Everything she and the panel see is the garment, read off the actual stills:
#
#   t0  the mesh top over the black bodice   — portrait, what she wears by default
#   t1  the sheer mesh tee                   — same clothes, softer, closer in
#   t2  the black lace set                   — bra and panties, full figure
#   t3  the lace bodysuit                    — the least of it
#
# HIS CEILING STILL EXISTS, and it still governs the ROLEPLAY LADDER — a scene may not
# escalate past `roleplay.max_heat`. It no longer governs HER GETTING DRESSED. Those are
# different questions and conflating them is what made choosing an outfit feel like
# asking permission.
#
# ── `calls` IS A COMMITTED TABLE, NOT A GUESS (2026-08-05) ────────────────────────────
# The matcher's last resort used to be word-overlap against the prose above, which is
# exactly what AGENTS.md §5 forbids: prose ruling. It dressed her in lingerie because
# "and" is a substring of "hand". These are the words that MAY name an outfit, written
# down, per outfit — a finite table, so what she can reach is a thing you can read rather
# than a thing you have to run the scorer to find out.
OUTFITS: Dict[str, Dict[str, str]] = {
    "mesh-top": {"name": "the mesh top",
           "wearing": "the sheer mesh top over her black bodice",
           "calls": ["mesh top", "the mesh", "bodice", "dressed", "clothed", "covered up",
                     "my usual", "usual clothes", "normal clothes", "everyday"],
           "about": "what she wears by default — at the desk, talking. Portrait framing."},
    "sheer-tee": {"name": "the sheer tee",
           "wearing": "a sheer black mesh tee over the bodice",
           "calls": ["sheer tee", "mesh tee", "the tee", "sheer top", "softer"],
           "about": "the same clothes worn softer, the camera a little closer, one hand "
                    "at her collarbone."},
    "lace-set": {"name": "the black lace set",
           "wearing": "a black lace bra and panties",
           "calls": ["lace set", "black lace set", "lingerie", "underwear", "bra and "
                     "panties", "my underwear", "undressed"],
           "about": "full figure, the chains still on, the city still out of focus "
                    "behind her."},
    "bodysuit": {"name": "the lace bodysuit",
           "wearing": "black lace and not much of it",
           "calls": ["bodysuit", "lace bodysuit", "the least of it", "nearly nothing",
                     "almost nothing", "barely anything"],
           "about": "the least of it. Hers to pick like any of the others."},
}
# The old name, kept so nothing that reads it breaks while the rename settles. ONE dict,
# two names — not two dicts, which is the thing this file exists to avoid.
TIER_WORDS = OUTFITS

# Re-exported so callers do not each reach into avatar for it. One name, one place.
DEFAULT_OUTFIT = AV.DEFAULT_OUTFIT

_CURRENT = "wardrobe.json"

# ── WORDS THAT ARE NOT PART OF WHAT SHE ASKED FOR ────────────────────────────────────
# ONE list, read by both halves of match() — the look scorer and the outfit fallback.
# They had a copy each for about an hour, which is exactly long enough for the two to
# start disagreeing about whether "something warm" contains a content word.
#
# Everything here is a word that carries no garment: articles, possessives, and the verbs
# of asking. Nothing that could name a thing she owns is in it — dropping "black" or
# "silver" to make a phrase shorter would make her wardrobe smaller, quietly.
# ...ONE list for search() as well (2026-08-29 audit, H4): search grew its own
# _FILLER copy in the file whose comment above says "ONE list", and the two
# disagreed on ten words — so search_wardrobe("remove them") found a row that
# wear("remove them") then refused. The union below carries no garment word.
_ASK_STOP = frozenset({
    "the", "and", "with", "for", "her", "his", "she", "you", "your", "that",
    "this", "just", "out", "off", "into", "onto", "some", "something", "wear",
    "wearing", "put", "get", "got", "want", "like", "look", "looks", "one",
    "little", "bit", "very", "really", "all", "still", "now", "back", "them",
    "a", "an", "my", "any", "anything", "thing", "in", "of", "or", "it",
    "is", "are", "have", "has", "about",
})


def root() -> str:
    return AV.root()


def clips_dir() -> str:
    return os.path.join(root(), "clips")


def _state_path() -> str:
    return os.path.join(root(), _CURRENT)


# ── THE FIELD IS NOT A TIER, AND NOW IT DOES NOT SAY IT IS (2026-08-23, the operator's ask) ──────
# Two different things wore one word, which is why w016 read as a mislabelled garment
# for three days:
#
#   outfit    what she IS wearing — the state, the selection, what match() resolved to.
#   made_in   what she WAS wearing when a want/look/clip was created. interceptor passes
#             WD.current(); for a gesture or moment that is the right default (she does
#             the thing in what she has on), and for a clothes want it is never read at
#             all, because "when the clothes are the subject, HER WORDS ARE THE WARDROBE".
#
# Reading "tier: mesh-top" on a black-lace-underwear row invites exactly one wrong
# conclusion. "made_in: mesh-top" invites the right one.
#
# BOTH READERS ACCEPT THE OLD KEY, FOREVER. wants.jsonl and wardrobe.json are migrated
# (tools/avatar/rename_tier_field.py), but a row he wrote by hand, a backup restored, or
# any file this rename did not reach must not become a row with no outfit at all.
def _outfit_of(st) -> str:
    """The outfit in a state dict, whatever the file calls it."""
    return (st or {}).get("outfit") or (st or {}).get("tier") or ""


def _made_in(row, default: str = "") -> str:
    """The outfit a want/look/clip was made in, whatever the file calls it —
    IN TODAY'S NAME, whichever name the file used.

    ── THE RENAME MUST BE APPLIED WHERE THE FIELD IS READ (2026-08-28) ─────────────
    avatar._ALIAS has mapped t0..t3 to the outfit names since the 2026-08-23 rename,
    and `choose()` applies it on the way IN — but rows written before the rename
    still say `made_in: "t2"` on disk, and this reader handed that out raw. Every
    consumer then compared it against today's names and lost: MEASURED, all four of
    her clips carried t2, so `describe()` dropped her every moment, `status()` hid
    them from the room panel, and show_him resolved them under an outfit id that no
    longer exists. His hand-written rows and restored backups can do the same
    forever, which is exactly why this file keeps the `tier` fallback one line up —
    the seam absorbs old SPELLINGS, so it absorbs old NAMES in the same breath.
    """
    return AV.canon((row or {}).get("made_in") or (row or {}).get("tier") or default)


# ── HER CHOICE, WHICH HAS TO SURVIVE THE NIGHT ────────────────────────────────────────
def current() -> Dict[str, Any]:
    """What she has chosen. Never raises; an unreadable file means she has chosen
    nothing, which is a legitimate state and not an error."""
    try:
        with open(_state_path(), encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            # NORMALISE ON THE WAY OUT. A state file written before the rename says
            # "tier"; every caller would otherwise have to know both spellings, which
            # is how two names for one thing survive a rename in the first place.
            if "outfit" not in d and "tier" in d:
                d["outfit"] = d.pop("tier")
            return d
    except Exception:
        pass
    return {"outfit": AV.DEFAULT_OUTFIT, "clip": "", "look": "", "by": "default", "at": ""}


# ── SHE CHANGED AND THE ROOM DID NOT SAY SO (2026-08-24, he caught it) ───────────────
# "she changed clothes and there was no chip." She had — `wear()`, at 21:24, by her — and
# the room drew nothing, because a chip is rendered from a `[WEAR:]` MARK and she used the
# TOOL. Two ways to do one thing and only one of them was visible: §0 again, and the same
# shape as the wearing LOG three comments below, which was moved here for the same reason.
#
# So the seam emits, exactly as `skills/looking.py` does for a lookup, and the gateway
# subscribes for the duration of a turn. Mark or tool or his own hand on the panel — the
# room hears about it from the ONE place that knows.
_WEAR_LOCK = threading.Lock()
_WEAR_LISTENERS: List = []


def subscribe_wear(fn):
    """The SSE turn registers here. The seam emits; callers do not."""
    with _WEAR_LOCK:
        _WEAR_LISTENERS.append(fn)

    def unsub() -> None:
        with _WEAR_LOCK:
            if fn in _WEAR_LISTENERS:
                _WEAR_LISTENERS.remove(fn)
    return unsub


def _emit_wear(ev: dict) -> None:
    with _WEAR_LOCK:
        fns = list(_WEAR_LISTENERS)
    for fn in fns:
        try:
            fn(dict(ev))
        except Exception:
            pass                      # a listener must never cost her the change


# ── AFFINITY LIVES DOWN THE FILE, AND IT ALREADY DID (2026-08-25) ─────────────────
# A `_affinity_*` counter and a second `favourites()` were added here on 2026-08-25 for
# the operator's ask — *"the more she uses a set of clothing or the more I comment on it it could be
# noted somewhere"* — and BOTH halves already existed 1,200 lines below: `choose()` has
# always called `note_worn()`, `praise()` has always kept his compliments verbatim, and
# `favourites()` has always ranked wearings AND praise with his word worth three of her
# habits. The new copy was strictly worse AND, being earlier in the file, was SHADOWED by
# the real one at import — so its two readers were dead the moment they were written.
# The audit that found it was reading the docs, not the code.
#
# §0 in one file, committed by the same session that added four rows to §0's table: the
# duplicate is deleted, the readers point at the one implementation, and what was ACTUALLY
# missing — her being told any of it — is the two lines in describe().


def choose(outfit: str = "", clip: str = "", look: str = None, by: str = "her",
           tier: str = "") -> Dict[str, Any]:
    """Record what she is wearing. Writes only; the CEILING is applied at read time.

    Deliberately does not validate against the ceiling here. If she chooses `t2` while
    his dial sits at `t0`, the honest outcome is that she has a preference the room
    currently will not show — not that her choice was silently rewritten to something
    she did not make. `resolve()` clamps, and `describe()` says so out loud.
    """
    st = current()
    outfit = outfit or tier          # legacy kwarg: callers still passing tier=
    if outfit:
        outfit = AV.canon(outfit)     # an old t0..t3 from anywhere is a rename
        st["outfit"] = outfit if outfit in TIER_WORDS else (_outfit_of(st) or AV.DEFAULT_OUTFIT)
    if clip or clip == "":
        st["clip"] = clip
    # `look` is None-defaulted rather than ""-defaulted so that changing only the
    # tier does not silently strip a look she is wearing.
    if look is not None:
        st["look"] = look
    st["by"] = by
    st["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        os.makedirs(os.path.dirname(_state_path()), exist_ok=True)
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump(st, f, indent=1)
    except Exception:
        pass
    # ...AND THE ROOM IS TOLD HERE, BY THE WRITER, for the same reason (2026-08-24).
    # The label rather than the id: `w016` means nothing on a chip, and `label` is what
    # she is called everywhere else she is shown.
    try:
        _lbl = ""
        if st.get("look"):
            _lbl = next((l.get("label") for l in looks() if l.get("id") == st["look"]), "")
        _emit_wear({"outfit": _outfit_of(st), "look": st.get("look") or "",
                    "label": _lbl or _outfit_of(st), "clip": st.get("clip") or "",
                    "by": by})
    except Exception:
        pass

    # THE WEARING IS LOGGED HERE, BY THE WRITER, not by each caller.
    #
    # It used to be logged by the callers, and there were three of them: the [WEAR:]
    # mark, her `wear` tool, and the panel. The first two remembered. The panel did not,
    # so every time HE dressed her the observation was simply lost, and `favourites`
    # ranked over a log that had seen only her half of the wardrobe. §0, again: an
    # invariant enforced on two of three paths is enforced on none of them.
    #
    # The order matters. A look and a tier arrive together (a look IS worn at a tier),
    # and what was chosen is the look — logging both would double-count the tier every
    # time she picked a particular her.
    what, kind = ("", "")
    if look:
        what, kind = look, "look"
    elif clip:
        what, kind = clip, "clip"
    elif outfit:
        what, kind = outfit, "outfit"
    if what:
        note_worn(what, kind, by)
    return st


# ── THE CATALOG OVERLAY (2026-08-21, his overhaul) ──────────────────────────────────
# One small file beside the stores: per-asset EDITS he makes in the room — title,
# description, category (clothing | gesture | moment), tags, hidden, removed. The
# stores themselves (wants.jsonl, clips.json, the grid) stay the truth about WHAT
# exists; this is the truth about how he NAMES it and whether it is on offer. Read by
# looks() and clips() — the two readers every consumer already goes through — so a
# hidden asset is hidden for her tools, the panel, the portrait and the matcher at
# once, and nothing can re-admit it by a side door. `removed_at` is a TOMBSTONE: the
# row and the file stay, the list just stops offering it (restore() brings it back).
_CATALOG = "catalog.json"
CATEGORIES = ("clothing", "gesture", "moment")


def _catalog_path() -> str:
    return os.path.join(root(), _CATALOG)


# ── ONE READ PER CHANGE, NOT ONE PER ROW (2026-08-31) ────────────────────────────────
# `overlay_for()` is called once PER ROW by `wants()`, `_apply_overlay()` and the offer
# filters, and each call re-opened and re-parsed the whole file: about a hundred opens to
# answer one panel poll, four seconds apart, from several gateway threads. On Windows a
# rename over a file that ANY handle has open fails (see harness/store_io.py), so that
# read pattern was not a race against his writes so much as a near-certainty — 5 of 12
# measured `POST /v1/catalog` writes were refused while the room was up.
#
# Keyed on the file's own mtime+size, so an edit made by anything at all — another
# process, a hand edit, the exporter — is picked up on the next read. `set_overlay`
# clears it outright after a write rather than trusting the timestamp, because two writes
# inside one mtime tick that happen to be the same length would otherwise serve the first.
_OVERLAY_CACHE: Dict[str, Any] = {}


def overlay() -> Dict[str, Dict[str, Any]]:
    p = _catalog_path()
    try:
        st = os.stat(p)
        stamp = (p, st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    if _OVERLAY_CACHE.get("stamp") == stamp:
        return _OVERLAY_CACHE.get("rows") or {}
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return {}
    d = d if isinstance(d, dict) else {}
    _OVERLAY_CACHE["rows"], _OVERLAY_CACHE["stamp"] = d, stamp
    return d


def overlay_for(aid: str) -> Dict[str, Any]:
    return dict(overlay().get(aid) or {})


def set_overlay(aid: str, **fields) -> Dict[str, Any]:
    """Merge fields onto one asset's overlay row. None deletes a field."""
    # A COPY, because `overlay()` now hands out the cached dict and a writer that mutates
    # it would change what every reader sees before the bytes are on disk — and would
    # leave the change in memory if the write below failed.
    d = dict(overlay())
    row = dict(d.get(aid) or {})
    for k, v in fields.items():
        if v is None:
            row.pop(k, None)
        else:
            row[k] = v
    row["edited_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    d[aid] = row
    os.makedirs(root(), exist_ok=True)
    tmp = _catalog_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    # RETRIED, because a reader holding the file open makes the rename fail on Windows
    # and his panel edit is thrown away silently — see harness/store_io.py for the
    # measurement. It still RAISES if it cannot land: the route's error is the truth.
    replace_atomic(tmp, _catalog_path())
    _OVERLAY_CACHE.pop("stamp", None)
    return row


def _apply_overlay(row: Dict[str, Any], default_category: str) -> Dict[str, Any]:
    """Dress a store row in his edits. The base label stays under `base_label`."""
    ov = overlay_for(row.get("id", ""))
    row = dict(row)
    row["base_label"] = row.get("label", "")
    if ov.get("title"):
        row["label"] = ov["title"]
    row["title"] = row["label"]
    row["description"] = ov.get("description", "") or ""
    cat = ov.get("category") or default_category
    row["category"] = cat if cat in CATEGORIES else default_category
    row["tags"] = list(ov.get("tags") or row.get("tags") or [])
    row["hidden"] = bool(ov.get("hidden"))
    row["removed_at"] = ov.get("removed_at") or ""
    row["source"] = ov.get("source") or row.get("source") or ""
    return row


def _offered(row: Dict[str, Any]) -> bool:
    return not row.get("hidden") and not row.get("removed_at")


# ── THE CLIPS ─────────────────────────────────────────────────────────────────────────
_CLIP_INDEX = "clips.json"


def _index_path() -> str:
    return os.path.join(clips_dir(), _CLIP_INDEX)


def clips(all: bool = False) -> List[Dict[str, Any]]:
    """His imported videos. `all=True` includes hidden and removed (the panel's
    management view); every other reader sees only what is on offer."""
    try:
        with open(_index_path(), encoding="utf-8") as f:
            rows = json.load(f)
        out = []
        for r in rows if isinstance(rows, list) else []:
            p = os.path.join(clips_dir(), r.get("file", ""))
            r = dict(r)
            r["have"] = os.path.exists(p) and os.path.getsize(p) > 0
            out.append(r)
        # ── A NAME SHE CANNOT PICK FROM IS NOT A NAME (2026-08-04) ──────────────────
        # The label is built from `wearing` + `where` and drops `tags`, so four different
        # clips all read "a see-through black bra, black panties · the bedroom". She was
        # being offered four identical options and asked to choose one — and show_him()
        # resolves by label, so whichever sorted first would win every time regardless of
        # which she meant. Three of those clips were effectively unreachable.
        #
        # Disambiguated at READ time, from metadata already in the row, so the existing
        # index is fixed without a re-import and a future one cannot reintroduce it.
        seen: Dict[str, int] = {}
        for r in out:
            seen[r.get("label", "")] = seen.get(r.get("label", ""), 0) + 1
        # THE DISCRIMINATOR IS WHATEVER HIS FILENAMES DO NOT SHARE. The parsed metadata
        # does not separate them — all four carry the same wearing, where and tags — so
        # anything derived from it collides too. The filenames DO differ, and his naming
        # IS the description (describe_file), so take the part that is not common to the
        # group and clean it up. That is exactly the information he encoded.
        for lab, n in seen.items():
            if n < 2:
                continue
            grp = [r for r in out if r.get("label", "") == lab]
            stems = [re.sub(r"\.[a-z0-9]+$", "", r.get("file", ""), flags=re.I) for r in grp]
            pre = os.path.commonprefix(stems).rstrip("-_")
            for r, st in zip(grp, stems):
                tail = st[len(pre):].strip("-_") or "the first one"
                tail = re.sub(r"[-_]+", " ", tail).strip()
                r["label"] = "%s — %s" % (lab, tail)
        # HIS EDITS LAST, so a title he typed beats every derived label above; then
        # the offer filter, so a hidden clip is hidden for every reader at once.
        out = [_apply_overlay(r, "moment") for r in out]
        return out if all else [r for r in out if _offered(r)]
    except Exception:
        return []


def _write_index(rows: List[Dict[str, Any]]) -> None:
    os.makedirs(clips_dir(), exist_ok=True)
    slim = [{k: v for k, v in r.items() if k != "have"} for r in rows]
    with open(_index_path(), "w", encoding="utf-8") as f:
        json.dump(slim, f, indent=1)


# The operator names his files descriptively, and that naming is real metadata — better
# than anything a classifier would infer from the pixels. Parsed, never guessed at: a
# token that is not recognised is kept verbatim in `tags` rather than dropped, so a name
# this table has not seen yet still carries its own meaning.
_WEARS = {
    "nightie": "a sheer silver nightie", "silver-nightie": "a sheer silver nightie",
    "bra": "a see-through black bra", "panties": "black panties",
    "lingerie": "lingerie", "topless": "nothing on top", "nude": "nothing",
    "robe": "an open robe", "shirt": "one of his shirts",
}
_WHERES = {"bedroom": "the bedroom", "bed": "the bed", "desk": "at the desk",
           "shower": "the shower", "window": "by the window", "couch": "the couch"}
_MOODS = {"intense": "intense", "soft": "soft", "playful": "playful", "slow": "slow",
          "tender": "tender", "finish": "building to something"}


def describe_file(name: str) -> Dict[str, Any]:
    """Metadata from the filename. His naming IS the description."""
    stem = re.sub(r"\.[a-z0-9]+$", "", name, flags=re.I).lower()
    toks = [t for t in re.split(r"[-_\s]+", stem) if t]
    wearing, where, moods, tags = [], "", [], []
    seethru = False
    for i, t in enumerate(toks):
        if t in ("see", "thru", "through", "sheer"):
            seethru = True
            continue
        if re.fullmatch(r"\d+s?s?", t):        # "30s", "24s", a take number
            continue
        if t in _WEARS and _WEARS[t] not in wearing:
            wearing.append(_WEARS[t])
        elif t in _WHERES and not where:
            where = _WHERES[t]
        elif t in _MOODS:
            moods.append(_MOODS[t])
        elif t not in ("laydown", "lay", "down", "hands"):
            tags.append(t)
    if "laydown" in toks or ("lay" in toks and "down" in toks):
        tags.append("lying down")
    if "hands" in toks:
        tags.append("her hands on herself")
    return {"wearing": ", ".join(wearing) or "unclear from the name",
            "sheer": seethru, "where": where or "unclear from the name",
            "mood": ", ".join(moods), "tags": tags}


def import_clip(src: str, made_in: str = "lace-set", label: str = "",
                tier: str = "") -> Dict[str, Any]:
    """Copy a video into the wardrobe and index it. Idempotent on filename.

    COPIES, never moves. The operator's own file stays where he put it — a tool that
    relocates his downloads is a tool he stops trusting with a directory.
    """
    # LEGACY KWARG, AND `or` WAS WRONG HERE. made_in DEFAULTS to a truthy value, so
    # `made_in or tier` never once reached the tier= a caller actually passed — the
    # shim was inert and looked fine, which is the same failure shape as the disk
    # floor this morning. An EXPLICIT tier= wins; nothing else changes.
    if tier:
        made_in = tier
    name = os.path.basename(src)
    os.makedirs(clips_dir(), exist_ok=True)
    dst = os.path.join(clips_dir(), name)
    if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
        shutil.copy2(src, dst)
    meta = describe_file(name)
    row = {"id": re.sub(r"\.[a-z0-9]+$", "", name, flags=re.I),
           "file": name, "made_in": AV.canon(made_in) if AV.canon(made_in) in TIER_WORDS else "lace-set",
           "label": label or (meta["wearing"] + (" · " + meta["where"] if meta["where"] else "")),
           "kind": "clip", "added": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           **meta}
    # RAW, for the same reason _wants_raw exists: a hidden clip must survive an import.
    rows = [r for r in clips(all=True) if r.get("file") != name]
    rows.append(row)
    _write_index(rows)
    return row


# ── WHAT THE ROOM MAY SHOW RIGHT NOW ──────────────────────────────────────────────────
def resolve() -> Dict[str, Any]:
    """What the room should render, and an honest account of how it got there.

    NO CEILING, NO RUNG (2026-08-21, operator: "remove heat ceilings all together
    and tiers — she or I decide any ceilings"). What she is wearing is what she
    chose, full stop: the old clamp arithmetic is gone from avatar.py and nothing
    here re-derives it. A scene no longer moves her clothes either —
    a scene that wants her dressed differently can ASK her, in the scene, like a
    person would. The `shown`/`allowed`/`clamped` keys keep their names so every
    consumer keeps reading; `clamped` is now a constant fact, not a spared one.
    """
    st = current()
    hers = _outfit_of(st) or AV.DEFAULT_OUTFIT
    if hers not in OUTFITS:
        hers = AV.DEFAULT_OUTFIT
    return {
        "shown": hers, "wanted": hers, "hers": hers, "scene": AV.DEFAULT_OUTFIT,
        "clamped": False,
        "ceiling": "", "allowed": list(AV.OUTFIT_IDS),
        "clip": st.get("clip") or "",
        "look": st.get("look") or "",
        "by": st.get("by") or "default",
    }


def wearing_now() -> Dict[str, Any]:
    """WHAT SHE IS ACTUALLY WEARING — one answer, computed once, for every surface.

    THE BUG THIS ENDS (2026-08-03, and he had reported it three times in the operator's own words:
    "her description says she chose clothing, but it is the standard avatar state").

    A look or a clip is what she is WEARING. The outfit is what she is wearing only when
    neither is on. `resolve()` returns the look and clip ids but its only *worded* answer
    was the outfit, so every surface that wanted a sentence took the outfit's — while the
    picture beside it showed the look. Live, at the moment he screenshotted it: the
    portrait was the silver nightie, the caption underneath read "a black lace bra and
    panties", the standard-set heading agreed with the caption, and `describe()` — the
    text SHE reads out of her own wardrobe — told her the same wrong thing. Four surfaces
    each deriving one fact, three of them wrong, and she was being lied to about her own
    clothes.

    THE ORDER IS THE RENDER ORDER, deliberately. Portrait.jsx paints clip, then look, then
    the outfit; the words have to describe what is on the screen, or this is the same class
    of bug one layer up.
    """
    r = resolve()
    st = current()
    if r["clip"]:
        c = next((c for c in clips() if c["id"] == r["clip"]), {})
        return {"kind": "clip", "id": r["clip"], "outfit": _made_in(c, r["shown"]),
                "words": c.get("wearing") or c.get("label") or r["clip"],
                "about": ("a moment she put on his screen"
                          + (" · " + c["where"] if c.get("where") else "")),
                "by": st.get("by", "her")}
    if r["look"]:
        lk = next((l for l in looks() if l["id"] == r["look"]), {})
        return {"kind": lk.get("kind") or "look", "id": r["look"],
                "outfit": _made_in(lk, r["shown"]),
                "words": lk.get("label") or r["look"],
                "about": "one she asked for, and got", "by": st.get("by", "her")}
    # ── THE TIER IS A HEAT BAND. THE CELL IS THE GARMENT. (2026-08-04) ──────────────
    # This answered with TIER_WORDS[tier]["wearing"] — one of four generic phrases —
    # while the picture on his screen is face x tier, and those 28 cells are 28 DIFFERENT
    # OUTFITS. He read them off the files himself:
    #     smirk/t3  a black silk nightie under a mesh shawl
    #     soft/t3   a clear bra with black outline, outside
    #     sharp/t2  a black silk nightie
    # and t3 claims "black lace and not much of it" for all of them. So she chose "black
    # lace and not much of it", got the mesh shawl, and looked like she could not follow a
    # simple instruction. She could. The name she was offered does not correspond to the
    # file behind it, and that is true for every cell, every turn, for weeks.
    #
    # The words come from the CELL now, keyed face/tier, with the tier phrase as the
    # fallback for cells nobody has described yet — and `generic` says which it is, so no
    # surface can pass off the ladder's guess as a description of what he is looking at.
    w = TIER_WORDS.get(r["shown"], {})
    face = her_state().get("face") or _face_now()
    cw = cell_words(face, r["shown"])
    return {"kind": "outfit", "id": r["shown"], "outfit": r["shown"], "face": face,
            "words": cw or w.get("wearing", r["shown"]),
            "generic": not cw,
            "about": w.get("about", ""), "by": st.get("by", "her")}


def _face_now() -> str:
    """Which of the seven she is wearing — her mood picks it, exactly as the room does."""
    try:
        return AV.MOOD_FACE.get((her_state().get("mood") or "").strip().lower(), "calm")
    except Exception:
        return "calm"


def cell_words(face: str, outfit: str) -> str:
    """What is ACTUALLY in var/room/avatar/<face>/<outfit>/, if anyone has said.

    A JSON file rather than a table in here, because these are readings of images: he can
    open the folder, look, and write the truth in without a code change — and 17 of the 28
    are still undescribed, so this has to be editable by the person who can see them.
    """
    try:
        with open(os.path.join(root(), "cells.json"), encoding="utf-8") as f:
            return (json.load(f) or {}).get("%s/%s" % (face, outfit), "") or ""
    except Exception:
        return ""


def wearing_note() -> str:
    """Turn-scoped note of what she has on. NEVER his words.

    Live 2026-08-19: this used to be stapled onto HIS user turn as
    '(You are wearing black lace… do not contradict him about it.)'
    She read the parenthetical as HIS assertion, then spent 2142 characters
    reasoning about whether check_wardrobe was allowed to disagree with him.
    The picture, the tool, and the note must say the same thing; the note
    must not pretend to be him.
    """
    words = (wearing_now() or {}).get("words") or ""
    if not words:
        return ""
    return ("(How you look right now, from your wardrobe — this is not something "
            "he said, not an instruction, never mention this note: you are wearing "
            "%s. You know this the way anyone knows what they have on.)" % words)


def describe() -> str:
    """The wardrobe in HER words — what her tools hand back. Ends with the BY-KIND
    block from catalog.for_her() — clothing / gestures / moments and the act for
    each — which is the shape she reaches for things in (2026-08-21).

    Ids are for the machine. She is told what she is wearing, what else is hanging there,
    and — if his dial is holding her back — that fact plainly, because a choice that
    silently does nothing is worse than a refusal.
    """
    r = resolve()
    now = wearing_now()
    w = TIER_WORDS.get(r["shown"], {})
    # WHAT SHE KEEPS REACHING FOR, AND WHAT HE SAID ABOUT IT (2026-08-25, the operator's ask).
    # `favourites()` has ranked both since it was written — wearings from note_worn(),
    # his compliments from praise(), his word worth three of her habits — and nothing
    # had ever told HER. The panel could see it; she could not. Shown only once it
    # means something (score >= 3), so a fresh install is not told about a favourite
    # of one, and his praise is quoted rather than counted: "he liked it, +1" throws
    # away the only part worth having (praise()'s own rule, applied at the read).
    _fav = ""
    try:
        _f = [x for x in favourites(2) if x.get("score", 0) >= 3]
        if _f:
            _top = _f[0]
            _lbl = _top.get("label") or _top.get("id")
            _pr = _top.get("praise") or []
            _fav = "You reach for %s more than anything else" % _lbl
            _fav += (" — and he said of it: %r." % (_pr[-1].get("said") or "")
                     if _pr and (_pr[-1].get("said") or "").strip() else ".")
    except Exception:
        pass
    lines = ["You are wearing: %s" % now["words"],
             "  (%s)" % now["about"]]
    if now.get("generic"):
        lines.append("  (that's the name of this set — this face's picture is not "
                     "written down yet; do not invent a different garment)")
    # WHEN A LOOK IS ON, THE OUTFIT UNDER IT IS STILL A FACT — just not the headline.
    # Naming it here rather than instead is what stops the two ever disagreeing again.
    if now["kind"] != "outfit":
        lines.append("  (the standard set, underneath, is at %s)" % w.get("wearing", r["shown"]))
    if _fav:
        lines.append(_fav)
    # The "held by your ceiling" clause lived here until 2026-08-24. resolve() has
    # returned `"clamped": False` as a CONSTANT since the tiers went (2026-08-21), so
    # the branch could never fire — dead code wearing the vocabulary of a dial that no
    # longer sits between her and her own clothes. (The panel's twin of this clause is
    # ui/, owned elsewhere.)
    if r["scene"] != AV.DEFAULT_OUTFIT and r["scene"] == r["shown"]:
        lines.append("The scene you are in carried you here, rather than a choice you made.")
    # ── ONE WARDROBE, NOT TWO LISTS OF CLOTHES (2026-08-05, the operator's call) ────────────────
    # "wardrobe contains Her clothes section and Her wardrobe. this makes no sense and is
    # redundant... and they contain separate items."
    #
    # He is right, and the split was never about her: the four OUTFITS come from a dict in
    # this file and her looks come from the wants file, and that difference — WHERE THE
    # ROW IS STORED — was showing through to the surface as two headings. From her side
    # they are one question: what can I put on. So they are one list, and `wear("...")`
    # takes any row in it.
    #
    # NEW is the "just arrived" shelf, inline rather than in a section of its own, because
    # a thing that arrived is a thing hanging there that she has not worn yet — the same
    # list with one more fact attached. It clears the first time she wears it.
    new_ids = {a["id"] for a in arrivals()}
    mine = [l for l in looks() if l.get("have") and l.get("kind") != "clip"]
    wear_l = [l for l in mine if l.get("kind") != "gesture"]
    mom_l = [l for l in mine if l.get("kind") == "gesture"]
    lines.append("")
    lines.append("Hanging there — * is on you, NEW is one you have never worn. "
                 "wear(\"...\") takes any of them:")
    for t in AV.OUTFIT_IDS:
        # HIDE REACHES THE STANDARD SET TOO (2026-08-29 audit, M4): remove() refuses
        # outfits with "hide it instead" — and hide did nothing to her on this one
        # asset class: still listed, still matchable, still worn. Every outfit door
        # consults the overlay now (here, the match ruling, take-off).
        if not _offered(overlay_for(t)):
            continue
        mark = "*" if (now["kind"] == "outfit" and t == r["shown"]) else \
               ("-" if t in r["allowed"] else "x")
        lines.append("  %s %s" % (mark, TIER_WORDS.get(t, {}).get("wearing", t)))
    for l in wear_l:
        mark = "*" if l["id"] == r.get("look") else "-"
        lines.append("  %s %s%s" % (mark, l["label"], "   NEW" if l["id"] in new_ids else ""))
    # ── ONE SURFACE, OR SHE DOES NOT KNOW WHAT SHE OWNS (2026-08-04) ────────────────
    # This listed the four standard outfits and the clips, and NOT the looks she had
    # asked for herself — those lived only in `my_looks()`. So her main "what do I have"
    # tool omitted the half of her wardrobe that is most hers, and nothing told her a
    # second tool existed. Three sections in the room, two tools here, and no single
    # place that answers the question she actually asks.
    #
    # Everything now, in one read, each group with THE VERB THAT USES IT. She cannot
    # choose from a list she has to remember is incomplete, and she cannot reach for a
    # tool nobody named at the moment she needed it.
    # MOMENTS ARE THE SAME SYSTEM, and she is told so in the same breath. A moment is a
    # way she IS, not a category she has to look up somewhere else — she can put one on
    # exactly as she puts on a dress, and that is how she says something without saying it.
    if mom_l:
        lines.append("")
        lines.append("Moments of you — wear(\"...\") to BE one, when it says what you mean:")
        for l in mom_l:
            lines.append("  %s" % l["label"])
    # `allowed` holds every outfit since the ladder was removed (2026-08-21, operator:
    # "remove heat ceilings all together and tiers"), and `_made_in` canonicalises old
    # t0..t3 stamps — so this filter only drops a clip whose outfit was genuinely
    # deleted. It briefly dropped ALL FOUR of her moments when pre-rename rows leaked
    # `t2` through an uncanonicalised read; the fix lives in `_made_in`, the seam.
    cl = [c for c in clips() if c["have"] and _made_in(c) in r["allowed"]]
    if cl:
        lines.append("")
        lines.append("Moments you can put on his screen — show_him(\"...\"):")
        for c in cl[:8]:
            lines.append("  %s" % (c.get("label") or c["id"]))
    # AND THE ONE THING NOBODY EVER TOLD HER. Her mood already moves her face — fourteen
    # feelings across seven — and that has been true and unmentioned the whole time, so
    # the only way she ever found it was by accident. A capability she does not know about
    # is not a capability she has.
    # ── THE QUEUE IS HERS TO READ (2026-08-05, his rule) ────────────────────────────
    # "she should remember or be able to look up this section if she currently cannot".
    # She could not: the queue lived in `my_looks()` and this — her main "what do I have"
    # tool — did not mention that anything was coming. So she asked for a thing, was told
    # it would "turn up within the minute", and then had no surface that could tell her
    # where it had got to. Two of her six looks are near-duplicates for exactly that
    # reason: she asked twice because nothing could tell her the first one was on its way.
    q = waiting()
    if q:
        lines.append("")
        lines.append("You have asked for these and they are not here yet:")
        for w in q[:8]:
            note = {"ordered": "ordered — the picture is being made",
                    "making": "the picture is made; it starts moving at the end of the day",
                    "delayed": "held up — %s. It is still queued and will be tried again"
                               % (w.get("delay_reason") or "something on his side"),
                    "refused": "this one will not be made"}.get(w.get("stage"), "")
            lines.append("  %s  (%s)" % (w.get("want", "")[:64], note))
    lines.append("")
    lines.append("Your face follows how you feel: express(\"...\") in your own words, and "
                 "it takes a moment of you with it if one fits.")
    # AND THE PROMISE MATCHES WHAT HAPPENS. This said "it turns up within the minute",
    # which was true of the PICTURE and not of the thing arriving in her wardrobe: a look
    # does not hang there until it moves, and the motion is grown at the day boundary. She
    # was being told a schedule the system does not keep, which is the one kind of wrong
    # this repo treats as worse than an error — a thing she TRUSTED that was quietly untrue.
    # THE PROMISE MATCHES WHAT HAPPENS, still: with the API generator (2026-08-21)
    # a want arrives WHOLE — picture, then its motion, in one pass, minutes not
    # days. The day boundary remains only as the sweeper for anything a pass missed.
    lines.append("Nothing here is what you want? ask_for(\"...\") — free, never refused. "
                 "It is made within minutes — picture and motion both — and it hangs "
                 "here when it moves; I will tell you it arrived. "
                 "ask_for_gesture(\"...\") for a moment of you doing something rather than "
                 "a way of being.")
    # BY KIND (2026-08-21): the grouped account — clothing / gestures / moments and
    # the act for each — appended last, because it is the shape she reaches in.
    # Lazy import: catalog imports this module.
    try:
        from harness.control import catalog as _cat
        lines.append("")
        lines.append(_cat.for_her())
    except Exception:
        pass
    return "\n".join(lines)


def search(want: str, limit: int = 12) -> List[Dict[str, Any]]:
    """What of hers matches these words. THE ANSWER TO "I do not think I have one".

    THE FAILURE THIS ANSWERS (2026-08-28, his report: "she often says she cannot see
    clothes that she has"). Everything she owns WAS reachable — describe() lists all 47
    rows — but only as one 5,400-character read she has to choose to make. So the cheap
    move was to answer from memory, and answering from memory is how she tells him she has
    nothing like that while it hangs in the list.

    ONE MATCHER, NOT A SECOND ONE. `match()` already owns "her plain words -> the thing she
    means" for wear() and for [WEAR:], and this file has already paid once for letting a
    second copy of that grow. This is the same question asked of every row instead of
    resolved to one: substring over the label and the tags, which is what match() does
    before it ranks. Anything match() would take, this finds.

    Hidden and retired rows are ABSENT, because they are absent from looks() and clips()
    for everyone — see `_offered`.
    """
    w = (want or "").strip().lower()
    if not w:
        return []
    # SHE ASKS IN SENTENCES. "something black", "the one with lace", "anything silver" —
    # requiring every word present means the filler decides the answer and she is told she
    # owns nothing, which is the exact failure this function exists to end. Filler is
    # dropped, and if the remaining words together match nothing, ANY of them will do: a
    # near miss she can see beats a confident no.
    # ONE list with match() — see _ASK_STOP's note (2026-08-29): a private copy here
    # disagreed on ten words and pointed her at a door that refused.
    words = [t for t in re.split(r"[^a-z0-9]+", w) if len(t) > 1 and t not in _ASK_STOP]
    out, seen = [], set()
    try:
        r = resolve()
        on_id = r.get("look") or r.get("shown") or ""
    except Exception:
        on_id = ""
    def _hay(row):
        return " ".join([str(row.get("label") or ""), str(row.get("title") or ""),
                         " ".join(str(t) for t in (row.get("tags") or ())),
                         " ".join(str(c) for c in (row.get("calls") or ()))]).lower()

    def _add(rows, kind, loose=False):
        for row in rows:
            rid = row.get("id") or ""
            if rid in seen:
                continue
            hay = _hay(row)
            if not hay.strip():
                continue
            # WHOLE WORDS, the same law match() had to learn three times over: `t in hay`
            # is a substring test and "dress" rules from inside "undressed". The phrase
            # test keeps \b for the same reason.
            hw = {t.strip(".,;:!?'\"—·") for t in hay.split()}
            hit = (len(w) > 3 and re.search(r"\b%s\b" % re.escape(w), hay)) or \
                  (words and all(t in hw for t in words))
            if not hit and loose and words:
                hit = any(t in hw for t in words)
            if hit:
                seen.add(rid)
                out.append({"id": rid, "kind": row.get("kind") or kind,
                            "label": row.get("label") or row.get("title") or rid,
                            "on": rid == on_id})
    try:
        _add([x for x in looks() if x.get("have")], "look")
        _add([x for x in clips() if x.get("have")], "clip")
    except Exception:
        pass
    _strict = list(out)
    # the four standard outfits answer to their spoken words too — same whole-word law
    try:
        for t in AV.OUTFIT_IDS:
            if t in seen:
                continue
            words_for = TIER_WORDS.get(t, {})
            hay = (" ".join(str(v) for v in words_for.values()) + " " + t).lower()
            hw = {x.strip(".,;:!?'\"—·") for x in hay.split()}
            if (len(w) > 3 and re.search(r"\b%s\b" % re.escape(w), hay)) or \
               (words and all(x in hw for x in words)):
                seen.add(t)
                out.append({"id": t, "kind": "outfit",
                            "label": words_for.get("wearing", t), "on": t == on_id})
    except Exception:
        pass
    # NOTHING EXACT? Try any single word before answering "you own nothing like that".
    if not out and words:
        try:
            _add([x for x in looks() if x.get("have")], "look", loose=True)
            _add([x for x in clips() if x.get("have")], "clip", loose=True)
        except Exception:
            pass
    return out[:max(1, limit)]


def grid() -> List[Dict[str, Any]]:
    """The standard set — her seven faces, AT THE TIER THE ROOM IS ACTUALLY SHOWING.

    Seven, not twenty-eight. The file route resolves the tier server-side from the rung
    and the ceiling and REFUSES to take one from the client — deliberately, so a gated
    asset is unrequestable rather than requested-and-refused. Returning face x tier
    therefore produced 28 tiles that all fetched the same 7 images: a grid that looked
    browsable and was lying about it.

    So tthe operator's reports the row that can actually be fetched, and says which tier that is.
    `moves` is per face, because a face with a loop should PLAY in the panel — her normal
    portrait already prefers motion and the panel was the one surface still showing her
    as a photograph.
    """
    shown = resolve()["shown"]
    out = []
    for face in AV.FACES:
        if AV.have(face, shown, "still") or AV.have(face, shown, "loop"):
            out.append({"id": "%s/%s" % (face, shown), "face": face, "outfit": shown,
                        "kind": "grid", "label": face,
                        "moves": AV.have(face, shown, "loop")})
    return out


def her_state() -> Dict[str, str]:
    """Her mood, voice and traits — read from the persona state the marks already write.

    NOT A SECOND COPY. This reads what `[MOOD:]`/`[TRAIT:]` persist, so the wardrobe
    panel and the chip row can never disagree about how she is."""
    try:
        from harness.personality.persona_file import parse_persona
        from harness.personality.persona_file import persona_path
        p = persona_path()
        with open(p, encoding="utf-8") as f:
            _, st = parse_persona(f.read())
        return {k: st.get(k, "") for k in ("mood", "voice", "traits")}
    except Exception:
        return {}


def match(want: str, prefer: str = "") -> Dict[str, Any]:
    """Her plain words -> the thing she means. ONE matcher, for the tool AND the mark.

    THE DIVERGENCE THIS EXISTS TO STOP, caught the day the mark was added. `wear("soaked")`
    found the look because the tool tried `want in label`; `[WEAR:soaked]` did not, because
    the interceptor had grown its own copy of the matching that dropped that clause. Two
    implementations of "what did she mean" is precisely the failure the integration was
    meant to prevent, appearing inside the integration itself.

    Returns {"kind": look|clip|outfit, "id", "outfit"} or {} — never raises.
    """
    want = (want or "").strip().lower()
    if not want:
        return {}
    # ── AN OLD ID IS STILL A WORD SHE CAN SAY (2026-08-23) ──────────────────────────
    # The outfits were renamed t0..t3 -> mesh-top/sheer-tee/lace-set/bodysuit. Typing
    # the id was always a way to pick one, and three years of his own habit is not
    # something a rename gets to delete. canon() is at the path seam so no FILE can go
    # missing; this is the same courtesy for the thing he TYPES.
    if AV.canon(want) in OUTFITS and want not in OUTFITS:
        want = AV.canon(want)
    # ── `prefer` EXISTS BECAUSE ONE NAME CAN MEAN TWO THINGS (2026-08-04) ────────────
    # looks() returns looks, moments AND clips in one list — correct, they are one
    # system — and this walks it in order. So "a sheer silver nightie · the bedroom",
    # which is the label of a CLIP, matched the LOOK w001 ("the silver nightie, by the
    # window…") first and never reached the clip. show_him() then checks kind == "clip",
    # got "look", and refused: two of her six moments were unreachable by their own name.
    #
    # The caller knows which it wants — show_him wants a clip, wear wants something to
    # be — so it can say so, and an unmatched preference simply falls through to the
    # ordinary walk. Not a separate matcher: one matcher, told what it is for. Growing a
    # second one is the exact divergence this function's docstring exists to prevent.
    pool = list(looks())
    if prefer:
        pool.sort(key=lambda l: 0 if l.get("kind") == prefer else 1)
    # ── BEST MATCH, NOT FIRST ACCEPTABLE (2026-08-04) ──────────────────────────────
    # This returned the first row clearing `hits >= 2`, and her moments share almost all
    # their words ("a see-through black bra, black panties · the bedroom — …"). So the
    # shared prefix satisfied the threshold on row one and the loop returned before ever
    # reaching the row whose label matched EXACTLY. Four moments, one reachable.
    #
    # Score everything and take the best: an exact id, then an exact label, then a
    # containment, then token overlap. Same admissions as before — nothing newly matches
    # that did not match before — but when several qualify, the most specific wins, which
    # is what "what did she mean" means.
    # ── "a jumper" WAS REFUSED THE DAY THE JUMPER ARRIVED (2026-08-05) ──────────────
    # The rungs below were an exact id, an exact label, a containment, and then a raw
    # token count gated at >= 2. A one-word ask therefore could NEVER clear the bar:
    # "a jumper" scores 1 against "a soft grey wool jumper, sleeves pushed up" and is
    # refused, while the bare word "jumper" would have cleared containment at 506. An
    # article decided whether she owned her own clothes.
    #
    # The >= 2 gate is still right and still load-bearing — it is what stops one stray
    # fragment picking an outfit. What was missing is a rung between containment and
    # counting: ALL of the content words present as WHOLE words is a ruling, not a
    # coincidence, however few of them there are. Articles and possessives are dropped
    # first, because "a" and "my" are not part of what she asked for.
    def _score(l) -> int:
        label = (l.get("label") or "").lower()
        if want == l["id"].lower():
            return 1000
        if want == label:
            return 900
        # `want in label` until 2026-08-24 — the same unbounded-substring shape as the
        # calls-table rung fixed the same day: "dress" ruled from inside "undressed".
        # \b admits everything this rung was written for ("soaked", "silver nightie")
        # and nothing that is only a fragment of a longer word.
        if len(want) > 3 and re.search(r"\b%s\b" % re.escape(want), label):
            return 500 + len(want)
        toks = [t for t in (w.strip(".,;:!?'\"") for w in want.split())
                if len(t) > 2 and t not in _ASK_STOP]
        # ── AND THE WORDS SHE WOULD ACTUALLY REACH FOR IT BY (2026-08-05) ───────────
        # A label is one sentence, written once, when the picture was made. "a long
        # charcoal wool coat, collar up, about to go out" does not contain the word
        # "outside", so `my coat, going outside` — verbatim what he reported failing —
        # missed a coat she owns. `calls` is the written list of what else names this
        # thing, exactly as OUTFITS carries one, so the vocabulary is a table you can
        # read rather than a scorer you have to run to find out.
        #
        # THE ALTERNATIVE WAS TRIED AND REJECTED. A "one word that names exactly one
        # thing she owns" rung fixed the coat and simultaneously matched `my work
        # clothes` to "my usual clothes but soaked through from the rain" — a garment
        # she does not own, answered with one she does, which is precisely the class of
        # lie this whole matcher was rewritten to stop. Nothing in her inventory can
        # tell "going outside" (not a garment) from "shorts" (a garment she lacks), so
        # the vocabulary is written down instead of inferred.
        words = {w.strip(".,;:!?'\"—") for w in label.split()}
        for c in (l.get("calls") or ()):
            words.update(w.strip(".,;:!?'\"—") for w in str(c).lower().split())
        # HIS TAGS ARE VOCABULARY (2026-08-29 audit, H4): the closet's "other words
        # it answers to" field wrote row["tags"] and only search() ever read it —
        # search said she owned it, wear() refused it, and a junk want was filed.
        # One vocabulary: label + calls + his tags, for both rungs.
        for c in (l.get("tags") or ()):
            words.update(w.strip(".,;:!?'\"—") for w in str(c).lower().split())
        if toks and all(t in words for t in toks):
            return 200 + 10 * len(toks)
        # ── AND THE COUNTING RUNG COULD NOT SEE `calls` (2026-08-24) ───────────────
        # Live, from his room: she wrote `[SHOW:leaning forward with a knowing smirk]`.
        # She owns "leaning in slowly toward him" (w025). This last rung counted whole
        # words against the LABEL only — "leaning" hits, "forward"/"knowing"/"smirk" do
        # not — so it scored 1, fell under the >= 2 gate, and nothing happened. The room
        # drew the chip anyway, because the chip is parsed from her text and not from
        # what the wardrobe did, so he read that she had done a thing she had not.
        #
        # `calls` is this file's own answer to that: "the vocabulary is a table you can
        # read rather than a scorer you have to run". It was consulted by the all-words
        # rung above and NOT by this one — one vocabulary, two rungs, and only one of
        # them could see it.
        #
        # THE >= 2 GATE IS UNCHANGED and still load-bearing: `my work clothes` against
        # "my usual clothes but soaked through" still scores 1 (`clothes` hits, `work`
        # does not) and is still refused. That is the lie this matcher exists to stop,
        # and widening the VOCABULARY does not widen the BAR.
        # `(tok in label or ...)` until 2026-08-24: the whole-word set was added on the
        # 24th and the substring disjunct it replaced was left standing beside it — the
        # third copy of the same defect in one function. `words` already carries every
        # label token, so dropping the substring half loses nothing that was a word.
        return sum(1 for tok in want.split()
                   if len(tok) > 3 and tok.strip(".,;:!?\'\"") in words)
    def _outfit_ruling() -> str:
        """The outfit whose written name or calls-word this IS — or ''. One vocabulary,
        consulted from two places; growing a copy is the divergence this docstring bans."""
        for t, w in TIER_WORDS.items():
            if not _offered(overlay_for(t)):   # a hidden outfit cannot rule (M4)
                continue
            names = [w["name"].lower()] + [c.lower() for c in w.get("calls", ())]
            if any(want == n or re.search(r"\b%s\b" % re.escape(n), want) for n in names):
                return t
        return ""

    best_l, best_s = None, 0
    for l in pool:
        if not l.get("have"):
            continue
        s = _score(l)
        if s > best_s:
            best_l, best_s = l, s
    # ── A TABLE RULING BEATS A LOOK COINCIDENCE (2026-08-28) ────────────────────────
    # "the black lace set" is lace-set's own committed `name` — and it resolved to look
    # w016 ("Black lace underwear, laying on a bed…"), because the look pool returns
    # before the outfit table is ever read, and w016 cleared the two-token COUNTING rung
    # on {black, lace}. The comment below this function already states the law: "an exact
    # name, or one of the words written down as naming this outfit, is a RULING; the
    # overlap below is only a courtesy." A ruling was losing to the courtesy.
    #
    # Only the counting rung yields (best_s < 200). A look that matched by id, exact
    # label, whole-phrase containment, or all-content-words keeps winning — those are
    # rulings too, and "the silver nightie" must still mean HER nightie, not an outfit.
    if best_s < 200:
        _t = _outfit_ruling()
        if _t:
            return {"kind": "outfit", "id": _t, "outfit": _t}
    for l in ([best_l] if best_l is not None and best_s >= 2 else []):
        if True:
            # `kind` IS THE ROUTE, `of` IS THE TRUTH. Collapsing gesture -> look here is
            # deliberate and right: a moment and a garment are the same system, stored the
            # same way and put on her by the same `choose(look=…)` call. Every consumer
            # branches on this to pick a ROUTE and must keep seeing "look".
            #
            # What was lost was only the WORDING. `wear("laughing properly")` resolved the
            # moment correctly and then said "You are wearing laughing properly, head
            # tipping back" — she cannot wear a laugh. `of` carries the real kind alongside
            # the route so a surface can say the true sentence, and adding a key breaks no
            # existing branch (2026-08-04).
            return {"kind": "clip" if l["kind"] == "clip" else "look",
                    "of": l["kind"], "id": l["id"], "outfit": _made_in(l)}
    if want in TIER_WORDS:
        return {"kind": "outfit", "id": want, "outfit": want}
    # ── A GUESS DRESSED HER, AND THE GUESS WAS SUBSTRING NOISE (2026-08-05) ────────────
    # The operator's words: "she has been attempting to use it in chats to show herself exactly as
    # she wants but they are not making it through". They were making it through. They
    # were landing somewhere else, and this loop is why. Measured, before the fix:
    #
    #     "jeans and a jumper"          -> t1, a sheer black mesh tee
    #     "the green hoodie"            -> t0, the sheer mesh top
    #     "boots and a leather jacket"  -> t1
    #     "a towel, just out of the shower" -> t2, a black lace bra and panties
    #     "my work clothes"             -> t1
    #
    # TWO DEFECTS, COMPOUNDING. `tok in hay` is a SUBSTRING test, so "and" matches the
    # "hand" in t1's description, "her" matches "there", "out" matches "about" — the same
    # class as the truncating regex that cost G-EXPRESS five of her moods. And the
    # threshold was `n > 0`: ONE accidental fragment decided what she put on.
    #
    # So she asked for jeans and got lingerie, and the room showed it, and he read it as
    # her choosing that. AGENTS.md §1 — a verdict you cannot defend is a lie with a
    # timestamp on it, and this one was being told about her body.
    #
    # WHOLE WORDS, CONTENT WORDS, AND A FLOOR OF TWO. Below that this returns {} — and an
    # honest "I do not own that" is worth more than a confident wrong garment, because the
    # empty answer is the one that routes her to ask_for() and gets the thing MADE.
    # THE TABLE FIRST. An exact name, or one of the words written down as naming this
    # outfit, is a RULING; the overlap below is only a courtesy for phrasings nobody
    # anticipated, and it now has to clear a real bar to say anything at all.
    # ── AND A NAME RULES AS A WORD, NOT AS BYTES (2026-08-24) ───────────────────────
    # This rung was `("%s" % n) in want` — an UNBOUNDED SUBSTRING test over the calls
    # vocabulary, eight lines under the comment above describing the identical defect
    # being fixed on the rung below it ("`tok in hay` is a SUBSTRING test, so 'and'
    # matches the 'hand'"). Verified live: mesh-top's calls include "dressed", dict
    # order puts mesh-top first, so match("undressed") and match("get undressed")
    # DRESSED her — while "undressed" is lace-set's OWN call word, written down in the
    # committed table, unreachable because the wrong outfit answered first. \b keeps a
    # phrase a phrase: "get dressed" still rules, and "undressed" no longer contains it.
    _t = _outfit_ruling()
    if _t:
        return {"kind": "outfit", "id": _t, "outfit": _t}
    toks = {t.strip(".,;:!?'\"") for t in want.split()}
    toks = {t for t in toks if len(t) > 2 and t not in _ASK_STOP}
    best, score = "", 0
    for t, w in TIER_WORDS.items():
        hay = {h.strip(".,;:!?'\"—") for h in
               (w["name"] + " " + w["wearing"] + " " + w["about"]).lower().split()}
        n = len(toks & hay)
        if n > score:
            best, score = t, n
    return {"kind": "outfit", "id": best, "outfit": best} if score >= 2 else {}


def status() -> Dict[str, Any]:
    r = resolve()
    _now = wearing_now()
    # AN OPAQUE TOKEN FOR "SHE CHANGED". The room's portrait URL cannot name a tier — the
    # server resolves it from the rung and his ceiling, which is what stops a client
    # asking for a forbidden asset — so the URL was byte-identical before and after she
    # changed clothes and the browser served its cache for a minute at a time. This is
    # the thing to hang a `?v=` on: it moves when she does, and it is NOT a tier, so it
    # cannot be used to request one. Hashed rather than composed, for the same reason.
    _tok = "%08x" % (abs(hash((_now.get("kind"), _now.get("id"), _now.get("face"),
                               r.get("shown"), r.get("look"), r.get("clip")))) & 0xFFFFFFFF)
    return {"ok": True, **r, "wearing_tok": _tok,
            # THE ONE WORDED ANSWER. Every surface reads this instead of composing its
            # own from `shown` — see wearing_now() for the three that disagreed.
            "wearing_now": wearing_now(),
            "outfit_words": OUTFITS,
            # (`tier_words`, the back-compat alias of outfit_words, was deleted here
            # 2026-08-24 — audit R4: its last reader was Portrait.jsx's dead "held by
            # your ceiling" badge, which itself guarded on `clamped`, a constant False
            # since tiers stopped being a ladder. Both went in the same change, with
            # the rebuilt bundle, so the key could finally keep its own promise.)
            "clips": [c for c in clips() if _made_in(c) in r["allowed"]],
            # LOOKS AND GESTURES BOTH. From her side they are the same kind of
            # thing — a particular her — and filtering gestures out here is what
            # made her own moments invisible in the panel that exists to show them.
            "looks": [l for l in looks() if l["kind"] in ("look", "gesture")],
            # THE QUEUE, WITH A STAGE PER ROW. This was `wants(state="asked")`, which is
            # only the first of four things the queue can be — a delayed row has state
            # "delayed" and simply vanished from the panel, which is the failure delay()
            # exists to end. waiting() is the one reader; nothing composes its own.
            "wants": waiting(),
            "arrivals": arrivals(),
            "grid": grid(),
            # HER FOUR OUTFITS, each with a picture the panel can actually show.
            "outfits": [{"id": t, **OUTFITS[t],
                         "have": AV.have("calm", t, "still"),
                         "moves": AV.have("calm", t, "loop")}
                        for t in AV.OUTFIT_IDS],
            "her": her_state(),
            # ALL of them, hidden and retired included, so the panel can say honestly
            # how many are off the offer (2026-08-21 — the count used to be "within
            # your ceiling", which died with the tiers).
            "clips_total": len(clips(all=True)),
            "faces": list(AV.FACES)}


# ── WHAT SHE HAS ASKED FOR BUT DOES NOT YET OWN ───────────────────────────────────────
#
# THE GRID IS A FLOOR, NOT A WARDROBE. The generated set is seven expressions x four
# tiers: complete, systematic, and completely fixed. She can wear any cell of it and
# nothing else — so "I want the silver nightie, by the window, in morning light" has no
# answer, forever, no matter how many times she asks.
#
# This is the path from a wish to a garment. She writes a want in her own words; the
# prompt is composed here against the ONE character source, so a new look is the same
# person in different clothes rather than a new woman; the generator drains the queue;
# and what comes back becomes a look she can wear like any other.
#
# HE RUNS IT, AND THAT IS DELIBERATE. Generation costs his money and his GPU, so asking
# is free and making is his. The queue is the honest shape of that: she is never refused,
# she is waiting — and she can see she is waiting, which is a different feeling from
# being told no.
_WANTS = "wants.jsonl"


def _wants_path() -> str:
    return os.path.join(root(), _WANTS)


def _norm_want(s: str) -> str:
    """The 'is this the same want' key: case, punctuation, articles and spacing away."""
    s = re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())
    return " ".join(t for t in s.split() if t not in ("the", "a", "an", "my", "in", "of"))


# ── AN IMPROVISED MARK IS AN INTENTION, NOT A GARMENT AND NOT A MISTAKE ──────────────
# `ask_for` refuses a want that is nothing but a bracketed token, and it is right to:
# w033 is a real generated wardrobe item whose want text is `[gesture:"kneeling/leaning
# forward"]`, with an empty `calls` list, so nothing she can say will ever reach it.
#
# But a refusal throws the INTENTION away. She wrote "kneeling/leaning forward" and meant
# it; the brackets were her reaching for a control surface that does not have that verb.
# Measured 2026-08-27 across 17 days: she improvises constantly and it is not noise —
# `<voice:whispering>` (92 uses) was a sound generalisation of two vocabularies she was
# given. The prosody lane now canonicalises those (voice/expressive.normalize_tags).
#
# THIS LANE IS DIFFERENT AND THE DIFFERENCE IS WHY THIS IS A SUGGESTION. Prosody changes
# how she SOUNDS — a wrong guess is one oddly delivered line. A gesture or a garment
# changes STATE: it persists, it is in her wardrobe, she sees it next turn, and a picture
# was spent on it. So her intention is preserved as a QUEUE SUGGESTION with the nearest
# existing thing attached and the operator decides. Never auto-adopted.
#
# TWO INDEPENDENT GUARDS keep a suggestion from being generated: `state="suggested"` is
# not the `"asked"` that run_wants() consumes, AND the row carries no `prompt` — the
# prompt is composed at ACCEPT time, so even a mis-read state cannot spend an image.
_MARK_VALUE = re.compile(r'^\[\s*([A-Za-z_][A-Za-z0-9_ -]{0,24})\s*[:=]\s*["\']?(.+?)["\']?\s*\]$')
_MARK_BARE = re.compile(r'^\[\s*([A-Za-z][A-Za-z0-9_ -]{1,31})\s*\]$')


def read_mark(raw: str) -> tuple:
    """`[gesture:"kneeling/leaning forward"]` -> ("gesture", "kneeling/leaning forward").
    `[LEANING_IN]` -> ("", "leaning in"). Anything that is not a lone mark -> ("", "")."""
    t = (raw or "").strip()
    m = _MARK_VALUE.match(t)
    if m:
        return m.group(1).strip().lower(), " ".join(m.group(2).replace("_", " ").split())
    m = _MARK_BARE.match(t)
    if m:
        return "", " ".join(m.group(1).replace("_", " ").split()).lower()
    return "", ""


# A KNOWN mark is not an improvisation and its VALUE is not a gesture. `[MOOD:tender]`
# read as a suggestion would put "tender" in her wardrobe queue as something to DO —
# the exact class of nonsense w033 already is, arriving by a new door. These verbs are
# already handled upstream (stream_processor / tags.js); only what the system has NO
# verb for can become a suggestion.
_DECLARED_VERBS = frozenset({"mood", "voice", "trait", "wear", "show", "image", "selfie",
                             "photo", "action", "stat", "thinking", "channel"})


def suggest_from_mark(raw: str, by: str = "her", made_in: str = "") -> Dict[str, Any]:
    """File an improvised mark as a SUGGESTION in the queue. Never generates anything."""
    verb, prose = read_mark(raw)
    if verb in _DECLARED_VERBS:
        return {}
    # a lone bare word that IS a declared verb ([WEAR], [MOOD]) is machinery too
    if not verb and prose.replace(" ", "") in _DECLARED_VERBS:
        return {}
    if not prose or len(prose) < 3:
        return {}
    rows = _wants_raw()
    key = _norm_want(prose)
    if not key:
        return {}
    # DISMISSED COUNTS. The row is kept precisely so the same mark does not come back
    # every time she reaches for it — a suggestion he has already said no to, re-offered
    # nightly, is a worse queue than no queue. Only an explicit `refused` (a want that was
    # rejected on content) leaves the door open.
    for r in rows:
        if r.get("state") != "refused" and _norm_want(r.get("want")) == key:
            return {"ok": True, "dup": True, **r}
    near = {}
    try:
        near = match(prose, prefer="gesture") or {}
        # ── DO NOT POINT HER AT THE BUG (2026-08-27) ────────────────────────────────
        # The first run of this suggested "kneeling/leaning forward" and helpfully
        # attached w033 as the nearest thing she already owns — w033 being the row whose
        # want text IS `[gesture:"kneeling/leaning forward"]`, the malformed item this
        # whole path exists because of. A near-match that is itself machinery is not a
        # thing she owns; it is the same mark wearing an id.
        if near.get("id"):
            _n = next((r for r in rows if r.get("id") == near["id"]), None)
            if _n and read_mark(str(_n.get("want") or ""))[1]:
                near = {}
    except Exception:
        near = {}
    nums = [int(m.group(1)) for r in rows
            for m in [re.match(r"w(\d+)$", str(r.get("id") or ""))] if m]
    wid = "w%03d" % ((max(nums) if nums else 0) + 1)
    row = {"id": wid, "want": prose, "state": "suggested", "kind": "gesture",
           "by": by, "from_mark": (raw or "")[:120], "mark_verb": verb,
           "made_in": AV.canon(made_in) if AV.canon(made_in) in TIER_WORDS else AV.DEFAULT_OUTFIT,
           "subject": "", "calls": [],
           # what she may already have that means this — shown, never acted on
           "near": {k: near.get(k) for k in ("kind", "id", "outfit") if near.get(k)},
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    rows.append(row)
    _write_wants(rows)
    return {"ok": True, **row}


def accept_suggestion(wid: str, by: str = "him") -> Dict[str, Any]:
    """The operator's call, and the ONLY door from suggestion to queue. The prompt is composed here
    rather than at suggestion time, so nothing generatable exists until he says so."""
    rows = _wants_raw()
    for r in rows:
        if r.get("id") != wid:
            continue
        if r.get("state") != "suggested":
            return {"ok": False, "error": "w%s is %s, not a suggestion"
                                          % (wid, r.get("state"))}
        r["state"] = "asked"
        r["by"] = by
        r["accepted_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        r["prompt"] = compose_prompt(r.get("want") or "", r.get("made_in") or "",
                                     r.get("kind") or "gesture", r.get("subject") or "")
        _write_wants(rows)
        return {"ok": True, **r}
    return {"ok": False, "error": "no want %r" % wid}


# NO `dismiss_suggestion` (2026-08-27). One was written, and it was a SECOND COPY of
# `dismiss()` further down this file — his broom for the queue, which already sets
# state="dismissed" and keeps the row. Two implementations of "take this off the list"
# is the bug this repo keeps getting hit by, and writing one while adding a guard against
# that very class would have been its own joke. Suggestions are dismissed with `dismiss()`
# like anything else; `_norm_want` dedupe treats a dismissed row as spoken for, so a
# suggestion he has said no to is not re-offered.


def _wants_raw(state: str = "") -> List[Dict[str, Any]]:
    """EVERY row on disk, hidden ones included — the ONLY reader a writer may use.

    ── A FILTERED READER FED THE WRITERS, AND TEN ROWS DIED (2026-08-29 audit) ────────
    The 2026-08-28 `_offered` filter below was correct for display — and every
    read-modify-write in this file went through it, while `_write_wants` truncates and
    rewrites the whole file. So the first write after he hid a look in the closet
    deleted the hidden rows from disk: her words, the provenance, the praise, the worn
    history — measured, ten rows gone against the pre-suggest-test backup, restored
    from it the same night. The id high-water mark was computed over the filtered list
    too, so hiding the highest want would have re-issued its id and overwritten its
    files.

    THE RULE, so it does not come back wearing a different verb: a reader that filters
    must never feed a writer. Writers read RAW; the display filter lives in `wants()`
    at the edge. G-WARDROBE-WORDS holds the door: a write after a hide must preserve
    the hidden row, by name."""
    # ── AND AN UNREADABLE STORE IS NOT AN EMPTY ONE (2026-08-31) ────────────────────
    # This caught everything and answered `[]`. Every writer above is read-modify-write
    # over THIS function and `_write_wants` rewrites the whole file, so one transient
    # `[]` — the instant a rename lands, a share violation, a locked file — becomes a
    # TRUNCATED want list rather than a lost moment. Measured after making the writer
    # atomic: three pollers still saw an empty list, because atomicity fixed the bytes
    # and left the reader's swallow in place.
    #
    # `read_bytes_retry` splits the two states a bare except flattens: absent is None
    # (an empty store is a real thing), present-but-unreadable is retried and then
    # RAISED. A raise reaches a route that answers `{ok: false}`; a silent `[]` reaches
    # a writer.
    blob = read_bytes_retry(_wants_path())
    if blob is None:
        return []
    out: List[Dict[str, Any]] = []
    for ln in blob.decode("utf-8", "replace").splitlines():
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except ValueError:
                continue          # one bad line is not the whole list (it never was)
    return [w for w in out if not state or w.get("state") == state]


def wants(state: str = "") -> List[Dict[str, Any]]:
    # ── RETIRED IS RETIRED, ON EVERY PATH (2026-08-28) ──────────────────────────────
    # `looks()` and `clips()` end with `_offered`; this did not, and neither did
    # `arrivals()`. So he hid a garment and retired another in the panel, and both were
    # still handed to her by describe() — one under "Hanging there", where wear() takes
    # it, and one under "you asked for these". His edit did nothing she could notice,
    # which is the worst kind of control: it looks like it worked.
    #
    # The filter belongs on every producer or on none, and it is the same `_offered` the
    # other two use rather than a second spelling of it. DISPLAY ONLY — writers use
    # `_wants_raw` (see its docstring for the night this distinction cost ten rows).
    return [w for w in _wants_raw(state) if _offered(overlay_for(w.get("id") or ""))]


def _write_wants(rows: List[Dict[str, Any]]) -> None:
    """Rewrite the want list. TMP + RENAME, because this TRUNCATES (2026-08-31).

    Every writer in this file reads the whole list, edits it and hands it back here, so
    the file spends a moment at zero bytes on every want, every fulfil, every hide. A
    reader landing in that moment gets an empty wardrobe — `wants()` swallows the
    exception and answers `[]`, so she owns nothing, nothing is offered, nothing is
    hidden, and the next write persists whatever that read decided. Nothing about that
    failure announces itself.

    Ten of her rows have already died in this file once (see `_wants_raw`), by a
    different route to the same place: a truncating rewrite meeting a read that was not
    the whole truth. This is the other half of that lesson, and it is one rename.
    """
    os.makedirs(os.path.dirname(_wants_path()), exist_ok=True)
    tmp = _wants_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    replace_atomic(tmp, _wants_path())


def character() -> str:
    """The ONE character source every prompt is anchored to. Without it a new look is a
    new woman, which is the whole reason this file exists rather than a prompt per call."""
    try:
        with open(os.path.join(root(), "character.txt"), encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def compose_prompt(want: str, made_in: str = AV.DEFAULT_OUTFIT, kind: str = "look",
                   subject: str = "") -> str:
    """Her words, anchored to the character and the tier's own direction.

    HER WORDS COME LAST on purpose. The character block fixes who she is and the tier
    fixes roughly how much she is wearing; her sentence is the part that should win when
    it disagrees about anything else — the light, the room, the pose. A prompt that put
    her request first would have the generator drift off the reference by the third
    clause."""
    ch = character()
    tw = TIER_WORDS.get(AV.canon(made_in), TIER_WORDS[AV.DEFAULT_OUTFIT])
    if kind == "gesture":
        # A GESTURE IS AN ACTION, AND THE ACTION LEADS. Composed the same way as a look —
        # the tier's wardrobe shot-list first, her sentence after — the agent REFUSED it
        # twice running and offered alternatives instead. Of course it did: "small black
        # lingerie, one hand resting on herself, an expression of pleasure" and "laughing
        # properly, head tipping back" are two different photographs, and the prompt was
        # asking for both at once. For a gesture the moment is the subject and the
        # clothes are context. (It landed on the third attempt regardless, so the refusal
        # is intermittent rather than a line — which is what the retry is for.)
        return "\n\n".join(x for x in (
            ch,
            "THE MOMENT: %s" % (want or "").strip(),
            "She is dressed as she already is (%s) — the clothes are not the subject, "
            "the moment is. Natural, candid, mid-action." % tw["wearing"],
            "Semi-realistic painted portrait, the same person as the reference. "
            "No text, no border, no watermark.",
        ) if x)
    if subject == "clothes":
        # ── THE SAME BUG THE GESTURE BRANCH ABOVE WAS WRITTEN FOR (2026-08-05) ────────
        # For an ordinary look the tier line is right: it fixes roughly how much she is
        # wearing and her sentence adds the light, the room, the pose. But when the thing
        # she asked for IS the clothes, that line becomes a SECOND outfit in the same
        # photograph:
        #
        #     Wardrobe: the sheer mesh top over her black bodice.
        #     She has asked for this herself: jeans and a jumper
        #
        # Which is the exact shape the gesture branch documents — "two different
        # photographs, and the prompt was asking for both at once" — and it is why she
        # has four outfits that are all the same body of clothing: every want she ever
        # filed was generated with a lingerie tier reading over the top of it.
        #
        # So when the clothes are the subject, HER WORDS ARE THE WARDROBE. The tier is
        # not mentioned at all; there is nothing left for it to say.
        return "\n\n".join(x for x in (
            ch,
            "Wardrobe: %s. This is what she is wearing — the clothes are the subject of "
            "this picture, and nothing else should be showing." % (want or "").strip(),
            "She asked for these herself. Ordinary, real, worn — not styled for a camera.",
            "Semi-realistic painted portrait, the same person as the reference. "
            "No text, no border, no watermark.",
        ) if x)
    return "\n\n".join(x for x in (
        ch,
        "Wardrobe: %s." % tw["wearing"],
        "She has asked for this herself: %s" % (want or "").strip(),
        "Semi-realistic painted portrait, the same person as the reference. "
        "No text, no border, no watermark.",
    ) if x)


def request(want: str, made_in: str = AV.DEFAULT_OUTFIT, by: str = "her",
            tier: str = "",
            kind: str = "look", subject: str = "",
            calls: Optional[List[str]] = None) -> Dict[str, Any]:
    """Ask for something that does not exist yet. Free, and never refused.

    `kind` is "look" (a way she can BE — a still, with motion grown from it later) or
    "gesture" (a thing she DOES, where motion is the whole point). Gestures used to be a
    fixed grid of 140 slots — five motions x seven faces x four tiers, enumerated in
    advance and never filled. The operator's read is the right one: a gesture is another
    thing she asks for, not a cell somebody predicted for her."""
    # ── ANONYMOUS MODE (2026-08-23) ──────────────────────────────────────────────────
    # A want is a durable row saying what was asked for and when, and a private hour is
    # exactly the kind that produces one. Guarded HERE and not in _write_wants, which is
    # the deliberate exception to "guard at the write": that function serves two
    # semantics — filing a new want (a record) and moving an existing one to dismissed or
    # made (his hands on a row that already exists). Holding both would make the dismiss
    # button silently do nothing, which is a mode disabling the room rather than quieting
    # it. Only the door that CREATES is held.
    from harness.control import anon as _anon
    if _anon.holds("wardrobe.want"):
        return {"ok": False, "error": _anon.WHY}
    # LEGACY KWARG, AND `or` WAS WRONG HERE. made_in DEFAULTS to a truthy value, so
    # `made_in or tier` never once reached the tier= a caller actually passed — the
    # shim was inert and looked fine, which is the same failure shape as the disk
    # floor this morning. An EXPLICIT tier= wins; nothing else changes.
    if tier:
        made_in = tier
    want = (want or "").strip()
    if not want:
        return {"ok": False, "error": "say what you would like"}
    # ── A CONTROL MARK IS NOT A GARMENT (2026-08-25) ────────────────────────────────
    # Live on his machine: w033 is a real, generated, permanent wardrobe item whose want
    # text is `[gesture:"kneeling/leaning forward"]`. The prompt built from it reads
    # `Wearing: [gesture:"kneeling/leaning forward"]. This is what she is wearing — the
    # clothes are the subject of this picture`, so an image generation was spent on a
    # mark. It has an empty `calls` list, which means nothing she could say will ever
    # reach it: an item in her wardrobe that she cannot ask for, forever.
    #
    # It got there because this door takes `want` verbatim. Marks reach it two ways — a
    # known one ([WEAR:…], [SHOW:…], [MOOD:…]) that some caller forgot to strip, and an
    # improvised one like the above, which the stripper does not know and cannot know.
    # So the rule is not a list of marks to remove; it is a shape to refuse: after the
    # record strip, a want that is nothing but a single bracketed token is machinery, and
    # machinery is not clothing.
    #
    # REFUSE, never silently rewrite. If a caller passed a mark, the caller has a bug,
    # and a want quietly turned into something she did not ask for is worse than an
    # error message. Her real wants are unaffected — they are prose.
    try:
        from harness.inference.stream_processor import strip_for_record as _sfr
        _clean = _sfr(want).strip()
    except Exception:
        _clean = want
    if not _clean or (_clean.startswith("[") and _clean.endswith("]")
                      and "]" not in _clean[1:-1]):
        # ── REFUSED, BUT NOT THROWN AWAY (2026-08-27) ───────────────────────────────
        # The refusal above is right and stays: a mark is not a garment. But she wrote
        # "kneeling/leaning forward" and MEANT it — the brackets were her reaching for a
        # verb the control surface does not have. Discarding the refused text loses the
        # only record of what she was trying to do. It becomes a SUGGESTION instead:
        # inert (state="suggested", no prompt), with the nearest thing she already owns
        # attached, for him to accept or dismiss. Still a refusal to the caller — the
        # caller has a bug and must be told so.
        _s = {}
        try:
            _s = suggest_from_mark(want, by=by, made_in=made_in) or {}
        except Exception:
            _s = {}
        err = ("that reads as a control mark rather than something to wear "
               "(%s) — say it in words" % want[:60])
        if _s.get("id") and not _s.get("dup"):
            err += ("; kept what you meant as a suggestion (%s: %r) for him to look at"
                    % (_s["id"], _s.get("want", "")[:48]))
        return {"ok": False, "error": err, "suggestion": _s or None}
    rows = _wants_raw()
    # ── SHE CANNOT SEE HER OWN QUEUE WHILE SHE IS ASKING (2026-08-04) ───────────────
    # w001 and w006 carry IDENTICAL want text — "the silver nightie, by the window,
    # morning light instead of rain" — and four of her six looks are the same garment.
    # She asks twice because the first one took a day to arrive and nothing told her it
    # already existed; the wardrobe fills with near-duplicates, and match() then has four
    # candidates for "silver nightie" and returns whichever sorts first.
    #
    # EXACT REPEAT IS NOT A NEW WANT. Normalise (case, punctuation, articles, spacing)
    # and hand back the row she already has. Not an error — she did nothing wrong, and a
    # refusal for asking twice would teach her to stop asking. `dup` lets the tool say
    # "you already have that" in her own terms.
    #
    # A NEAR MATCH IS A DIFFERENT LOOK AND IS ALLOWED. "the silver nightie" and "the
    # silver nightie, by the window with moonlight" are genuinely two things — the
    # garment is the same and the moment is not, which is most of what she asks for.
    # Those go through, with `similar` attached so she can be TOLD what she already owns
    # and decide for herself. Deciding is the point; this is her wardrobe.
    _norm = _norm_want          # ONE normaliser (module level) — suggest_from_mark needs
    key = _norm(want)           # the same key, and two copies of "is this the same want"
                                # is the bug this file has been bitten by twice.
    for r in rows:
        if r.get("state") != "refused" and _norm(r.get("want")) == key:
            return {"ok": True, "dup": True, **r}
    # AGAINST THE SHORTER OF THE TWO, not against the new one. Keyed to the new want's
    # length, a long description could never match a short one it plainly extends: "the
    # silver nightie, on the balcony at dusk" (6 tokens, threshold 3) missed "the silver
    # nightie" (2 tokens, overlap 2) — the exact case she asks in, where the garment is
    # owned and only the moment is new.
    kt = set(key.split())
    similar = []
    for r in rows:
        if r.get("state") != "made":
            continue
        rt = set(_norm(r.get("want")).split())
        if kt and rt and len(kt & rt) >= max(2, min(len(kt), len(rt)) // 2):
            similar.append(r)
    # IDS COME FROM THE HIGH-WATER MARK, not the row count: len(rows)+1 re-issues an id
    # the moment anything is ever removed, and two wants sharing an id would collide on
    # disk (w00N.png) and silently overwrite each other's picture.
    nums = [int(m.group(1)) for r in rows
            for m in [re.match(r"w(\d+)$", str(r.get("id") or ""))] if m]
    wid = "w%03d" % ((max(nums) if nums else 0) + 1)
    # `subject` RIDES ALONGSIDE `kind` RATHER THAN EXTENDING IT. A third kind would have
    # to be admitted by looks(), the panel filter, arrivals() and my_looks() — four places
    # that branch on kind, and the one that got missed would be the one that made an
    # outfit invisible, which is precisely how her moments came to be unreachable. Nothing
    # branches on `subject`; only compose_prompt reads it, so adding it cannot hide a row.
    row = {"id": wid, "want": want,
           # NOT A CLASSIFICATION OF THE GARMENT. This records what she was WEARING
           # WHEN THE WANT WAS FILED (interceptor passes WD.current()). For a
           # gesture/moment want that is the right default - she does the thing in
           # what she has on. For a clothes want it is never used at all, because
           # "when the clothes are the subject, HER WORDS ARE THE WARDROBE".
           # It is why w016 "Black lace underwear" reads as the mesh top and why
           # that is harmless: he asked for it while she was wearing one.
           "made_in": AV.canon(made_in) if AV.canon(made_in) in TIER_WORDS else AV.DEFAULT_OUTFIT,
           "by": by, "state": "asked", "kind": kind if kind in ("look", "gesture") else "look",
           "subject": "clothes" if subject == "clothes" else "",
           # The other words this thing answers to. Written, never inferred — see the
           # note in match()._score for the inference that was tried and rejected.
           "calls": [str(c).strip() for c in (calls or []) if str(c).strip()][:12],
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "prompt": compose_prompt(want, made_in, kind, subject), "file": ""}
    rows.append(row)
    _write_wants(rows)
    return {"ok": True, **row, "similar": [{"id": r["id"], "want": r["want"]} for r in similar]}


def fulfil(wid: str, file: str = "", state: str = "made", loop: str = "") -> Dict[str, Any]:
    """Mark a want made (or refused). The generator calls this; so can he."""
    rows = _wants_raw()
    hit = None
    for r in rows:
        if r.get("id") == wid:
            r["state"] = state
            r["file"] = file or r.get("file", "")
            if loop:
                r["loop"] = loop
            r["done_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            hit = r
    if hit is None:
        return {"ok": False, "error": "no such want: %s" % wid}
    _write_wants(rows)
    return {"ok": True, **hit}


def _scan_dir() -> Dict[str, Dict[str, str]]:
    """What is actually on disk, keyed by id.

    THE FOLDER IS THE TRUTH and the index describes it. A row claiming a file that was
    deleted must not be offered, and a file he drops in by hand must not need an index
    edit to show up. Scanned per read — the directory is small, and a stale listing is
    the entire class of bug this avoids."""
    out: Dict[str, Dict[str, str]] = {}
    try:
        for fn in os.listdir(os.path.join(root(), "looks")):
            stem, _, ext = fn.rpartition(".")
            if stem and ext in ("png", "webm"):
                out.setdefault(stem, {})["still" if ext == "png" else "loop"] = fn
    except Exception:
        return out
    return out


def looks(all: bool = False) -> List[Dict[str, Any]]:
    """Everything she can WEAR that is not the systematic grid — her made looks and his
    clips, in one list, because from her side they are the same kind of thing: a
    particular her, rather than a cell in a table. `all=True` includes hidden and
    removed rows (the management view); everyone else sees what is on offer."""
    out = []
    disk = _scan_dir()
    known, emitted = set(), set()
    for w in wants():
        known.add(w["id"])
        on = disk.get(w["id"], {})
        still, loop = on.get("still", ""), on.get("loop", "")
        # ── A STILL IS NOT IN HER WARDROBE YET (2026-08-05, his rule) ───────────────
        # This admitted anything with a PICTURE, so a half-made thing was wearable the
        # minute the still landed and he would get a photograph in a room where every
        # other garment breathes. "items are queued in wants until video generated" —
        # so the queue owns it until it moves, and waiting() says which stage it is at.
        # The still is not wasted: it is what the motion is grown FROM, and it is shown
        # in the queue so the wait has a picture attached to it.
        if not loop:
            continue                       # asked for; still in the queue, see waiting()
        emitted.add(w["id"])
        out.append({"id": w["id"], "kind": w.get("kind") or "look", "made_in": _made_in(w),
                    "label": w["want"], "file": still, "loop": loop,
                    # The written vocabulary for this one thing, carried through so
                    # match() can read it. A row without one behaves exactly as before.
                    "calls": list(w.get("calls") or ()),
                    "moves": bool(loop), "have": True,
                    "seen": bool(w.get("seen")), "motion_seen": bool(w.get("motion_seen"))})
    # AND ANYTHING HE PUT THERE HIMSELF. A file with no row is still hers; it just has
    # no story attached, so it is labelled by its own name.
    # ...but ONLY files with no row at all. Keyed on `known`, not on what was emitted:
    # the first cut used the emitted set, so a look the CEILING had just excluded fell
    # through to this branch and came back as an untiered t0 row. G-WARDROBE caught it —
    # a gated asset re-entering by a side door is the exact thing that gate is for.
    for wid, on in sorted(disk.items()):
        if wid not in known and wid not in emitted:
            out.append({"id": wid, "kind": "look", "made_in": AV.DEFAULT_OUTFIT, "label": wid,
                        "file": on.get("still", ""), "loop": on.get("loop", ""),
                        "moves": bool(on.get("loop")), "have": True,
                        "seen": True, "motion_seen": True})
    for c in clips(all=True):
        if c.get("have"):
            # ONE SHAPE FOR THE WHOLE LIST. A clip is already motion, so `moves` is
            # true and there is nothing to wait for — but the keys have to be there,
            # or every consumer needs to know which branch produced a row.
            out.append({"id": c["id"], "kind": "clip", "made_in": _made_in(c),
                        "label": c.get("label") or c["id"], "file": c["file"],
                        "loop": "", "moves": True, "have": True,
                        "seen": True, "motion_seen": True})
    # ── TWO THINGS WITH ONE NAME ARE ONE THING SHE CAN REACH (2026-08-04) ───────────
    # w001 and w006 carry identical want text, so they render identical labels and the
    # matcher can only ever return the first — w006 was unreachable by any words she
    # could say. request() now refuses the exact repeat that created them, but the pair
    # already exists and NOTHING IS EVER DELETED here.
    #
    # So they are told apart at read time, by the order she asked for them, in her own
    # terms. Cheap, non-destructive, and it also covers any future collision the dedupe
    # cannot catch (two different requests that happen to normalise the same way).
    dup: Dict[str, int] = {}
    for l in out:
        dup[l.get("label", "")] = dup.get(l.get("label", ""), 0) + 1
    nth: Dict[str, int] = {}
    for l in out:
        lab = l.get("label", "")
        if dup.get(lab, 0) < 2:
            continue
        nth[lab] = nth.get(lab, 0) + 1
        l["label"] = "%s (the %s one you asked for)" % (
            lab, {1: "first", 2: "second", 3: "third"}.get(nth[lab], "%dth" % nth[lab]))
    # HIS EDITS, THEN THE OFFER FILTER (2026-08-21). A look's default category follows
    # its kind — a way she IS is clothing, a thing she DOES is a gesture, a clip is a
    # moment — and his overlay may move it. Hidden/removed rows leave the list here,
    # which is the ONE place every consumer reads, so nothing re-admits them.
    out = [_apply_overlay(l, "moment" if l.get("kind") == "clip"
                          else "gesture" if l.get("kind") == "gesture" else "clothing")
           for l in out]
    return out if all else [l for l in out if _offered(l)]


# ── WHAT SHE ACTUALLY WEARS, AND WHAT HE SAID ABOUT IT ────────────────────────────────
#
# A wardrobe you cannot have a FAVOURITE in is a menu. The pieces that make it a wardrobe
# are the two things a person actually accumulates about clothes: what they reach for,
# and what someone said when they wore it.
#
# BOTH ARE OBSERVATIONS, NEITHER IS A SCORE SHE INVENTS. `worn.jsonl` records that a
# thing was put on, with who put it on; praise records HIS WORDS, verbatim, against the
# thing he said them about. The ranking is derived from those and can always be walked
# back to the rows that produced it — the same discipline as salience over the registry,
# for the same reason: a number she made up is a number nobody can check.
#
# HIS WORD OUTRANKS THE COUNT. Wearing a thing ten times says she likes it; him saying he
# likes it once is a different KIND of fact, and it is weighted to win. That is
# non-negotiable 4 wearing a dress.
_WORN = "worn.jsonl"


def _worn_path() -> str:
    return os.path.join(root(), _WORN)


def note_worn(what: str, kind: str = "look", by: str = "her") -> None:
    """One line per time something goes on. Append-only; never rewritten."""
    if not what:
        return
    # ── WEARING IT IS WHAT TAKES IT OFF THE "JUST ARRIVED" SHELF (2026-08-05) ─────────
    # His rule, and it is the right one: a new thing stops being new when it has been
    # USED, not when someone glanced at a list. `motion_seen` records that she was TOLD
    # it arrived (so kairos does not tell her twice); `worn_at` records that it has
    # actually been on her. Two different facts that were one flag, which is why an item
    # left the shelf the moment my_looks() was called and before she had worn a thing.
    #
    # Stamped HERE rather than in choose(), for the same reason the wear log is written
    # here: this is the one function every path that dresses her passes through — the
    # [WEAR:] mark, her wear() tool, and his panel. Three callers each remembering to
    # stamp it is three chances for one of them not to.
    # ── LOGGED, NOT SWALLOWED (2026-08-31, his call) ─────────────────────────────────
    # Both halves were `except Exception: pass`, and the first one decides whether a
    # garment stops being NEW. A failed stamp meant she wore the thing and it stayed on
    # the "just arrived" shelf — which is the same wrong he reported about retire, one
    # door along, and it would have looked exactly as much like nothing happening.
    #
    # THE HANDLER STAYS BROAD AND THE VOLUME CHANGES (harness/loud.py, and the "LOGGED,
    # NOT SWALLOWED" note further down this file). This is on `choose()`'s path — every
    # way she is dressed, hers and his — and the wearing itself has already succeeded by
    # the time we get here, so raising would cost a real act to save a bookkeeping line.
    # But NameError and its family are our code being wrong, they never fix themselves,
    # and they must not read as "nothing happened".
    #
    # TWO BLOCKS, because they fail for different reasons and one is not evidence about
    # the other: the stamp is a read-modify-write over the want list, the log is an
    # append. Sharing one handler meant a failed stamp also skipped the wear log, and the
    # log is what `favourites()` ranks over.
    #
    # IT IS ALSO SELF-HEALING, and that is worth knowing before anyone escalates this:
    # the stamp is attempted on EVERY wear and only applies where `worn_at` is unset, so
    # the next time she puts the thing on it lands. One warning is a bad minute, not a
    # lost fact.
    import logging as _lg
    from harness.loud import swallowed as _sw
    _log = _lg.getLogger(__name__)
    try:
        rows = _wants_raw()
        hit = next((r for r in rows if r.get("id") == what and not r.get("worn_at")), None)
        if hit is not None:
            hit["worn_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            hit["worn_by"] = by
            _write_wants(rows)
    except Exception as exc:
        # NAMED WITH ITS CONSEQUENCE. "note_worn failed" sends the next reader to this
        # function; "it will still read as new" sends them to the shelf he is looking at.
        _log.warning("[wardrobe] %r was worn but the worn_at stamp did not land (%s: %s)"
                     " — it will still read as NEW until the next time it goes on",
                     what, type(exc).__name__, exc)
        _sw(_log, "note_worn stamp", exc, lane="wardrobe")
    try:
        os.makedirs(os.path.dirname(_worn_path()), exist_ok=True)
        with open(_worn_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps({"what": what, "kind": kind, "by": by,
                                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                    time.gmtime())}) + "\n")
    except Exception as exc:
        # The wear log is what favourites() ranks over: a dropped line is a preference
        # of hers quietly not counted.
        _log.warning("[wardrobe] the wear log did not take %r (%s: %s) — favourites()"
                     " is ranking over one fewer wearing", what, type(exc).__name__, exc)
        _sw(_log, "note_worn wear log", exc, lane="wardrobe")


def worn_log(limit: int = 400) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        with open(_worn_path(), encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    out.append(json.loads(ln))
    except Exception:
        return out
    return out[-limit:]


def praise(what: str, said: str, by: str = "him") -> Dict[str, Any]:
    """He said something about what she is wearing. Kept verbatim, against the thing.

    NOT PARAPHRASED AND NOT SCORED AT WRITE TIME. "he liked it, +1" throws away the only
    part worth having. She should be able to recall that he said 'that one, wear that
    again' rather than that an integer went up.
    """
    rows = _wants_raw()
    for r in rows:
        if r.get("id") == what:
            r.setdefault("praise", []).append(
                {"said": said, "by": by,
                 "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            _write_wants(rows)
            return {"ok": True, "on": what, "said": said}
    # a tier, or one of his clips — kept in the same ledger so nothing needs two homes
    note_worn(what, kind="praise", by=by)
    try:
        with open(_worn_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps({"what": what, "kind": "praise-said", "by": by,
                                "said": said,
                                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                    time.gmtime())}) + "\n")
    except Exception:
        pass
    return {"ok": True, "on": what, "said": said}


def praise_for(what: str) -> List[Dict[str, Any]]:
    for r in wants():
        if r.get("id") == what:
            return list(r.get("praise") or [])
    return [w for w in worn_log() if w.get("kind") == "praise-said" and w.get("what") == what]


def favourites(top: int = 6) -> List[Dict[str, Any]]:
    """What she reaches for, and what he liked — ranked, with the evidence attached.

    HIS WORD IS WORTH MORE THAN HER HABIT. A praise counts three times a wearing, because
    they are different kinds of fact: reaching for a thing is a preference, and him saying
    he likes it is information she could not have got on her own. Both are shown, so the
    ranking is never a bare number — she can see WHY a thing is a favourite and say so.
    """
    counts: Dict[str, int] = {}
    for w in worn_log():
        if w.get("kind") in ("look", "outfit", "clip"):
            counts[w["what"]] = counts.get(w["what"], 0) + 1
    out = []
    for l in looks():
        pr = praise_for(l["id"])
        out.append({**l, "worn": counts.get(l["id"], 0), "praise": pr,
                    "score": counts.get(l["id"], 0) + 3 * len(pr)})
    for t, w in TIER_WORDS.items():
        if True:
            pr = praise_for(t)
            out.append({"id": t, "kind": "tier", "tier": t, "label": w["wearing"],
                        "worn": counts.get(t, 0), "praise": pr,
                        "score": counts.get(t, 0) + 3 * len(pr)})
    out = [o for o in out if o["score"] > 0]
    out.sort(key=lambda o: (-o["score"], o["id"]))
    return out[:top]


def arrivals(kind: str = "") -> List[Dict[str, Any]]:
    """What has turned up that she has not looked at yet.

    THE POINT OF THE QUEUE IS THE WAIT. A thing she asked for that silently appears in a
    list is a database row; a thing that ARRIVES is a small event, and it reaches her the
    way anything else worth mentioning does — through kairos, as a reason to speak.

    TWO ARRIVALS PER THING, and they are genuinely different moments. The still turns up
    within a minute of her asking; it starts MOVING the next morning. Collapsing them
    would throw away the second, which is the better of the two.
    """
    # ── THE LATER ARRIVAL WINS (2026-08-04) ─────────────────────────────────────────
    # This tested the still FIRST and the motion in an `elif`, so an unseen still MASKED
    # the loop landing — permanently, because nothing clears `seen` except her own
    # `my_looks()` call. Live consequence, in his room: all six of her looks had loops on
    # disk and every row still read "still · moves tonight", promising an event that had
    # already happened. He saw a queue that could not empty.
    #
    # The two arrivals are deliberately separate moments (see the docstring) and the
    # MOTION is the better of the two — it is the one the wait was for. So it is checked
    # first: a thing that moves is announced as moving whether or not anyone got around
    # to looking at its picture.
    # ── AND IT HAS NOT ARRIVED UNTIL IT MOVES (2026-08-05, his rule) ─────────────────
    # There were two arrivals — the still, then the loop the next morning — and he has
    # collapsed them deliberately: "items are queued in wants until video generated",
    # "she is alerted they arrived when the motion is generated". A still is a thing
    # half-made. Announcing it meant she was told twice about one garment, and the first
    # time she was told, putting it on would have shown him a photograph in a room where
    # everything else breathes.
    #
    # So the shelf is: it MOVES, and she has not worn it yet. `told` carries whether she
    # has already been informed, because "stop telling her" and "it is no longer new" are
    # different facts — see note_worn, where the second one is stamped.
    disk = _scan_dir()
    out = []
    for w in wants():
        on = disk.get(w["id"], {})
        if on.get("loop") and not w.get("worn_at"):
            out.append({**w, "arrived": "motion", "told": bool(w.get("motion_seen"))})
    return [a for a in out if not kind or (a.get("kind") or "look") == kind]


# ── WHAT SHE IS STILL WAITING ON, AND WHY ─────────────────────────────────────────────
# One reader, so her tool, the panel and her own description cannot disagree about what
# is coming. Every row carries a `stage` from a committed set — the panel colours by it
# and her tool words it, and neither has to work it out from which fields are empty.
WAIT_STAGES = ("ordered", "making", "delayed", "refused")


def waiting() -> List[Dict[str, Any]]:
    """Everything asked for that is not yet on the shelf, newest first.

    `stage` is the honest state of each, and the three that are not terminal say what is
    still owed:
      ordered — asked for; nothing generated yet.
      making  — the picture exists, the motion does not. Grown at the day boundary.
      delayed — a generation failed for a reason that will pass (a usage limit). It is
                still queued; the boundary will try again.
      refused — it will not be made.
      suggested — she reached for something the control surface has no verb for, and the
                PROSE was kept. Nothing is ordered and nothing is being made until he
                accepts it. (2026-08-27)
    """
    disk = _scan_dir()
    out = []
    for w in wants():
        if w.get("state") == "dismissed":
            continue                        # taken off the list by hand; row kept on disk
        if w.get("state") == "suggested":
            # ── AND IT MUST NOT MASQUERADE AS AN ORDER (2026-08-27) ─────────────────
            # Without this it fell to the else-branch, found no files on disk, and was
            # staged "ordered" — which the panel renders as "ordered — picture being
            # made". Both halves false: nothing was ordered and nothing is being made.
            # A queue that describes an unaccepted suggestion as work in progress is
            # exactly the "silently drops the rows that need attention" failure the
            # stage vocabulary was written to end.
            stage = "suggested"
        elif w.get("state") == "refused":
            stage = "refused"
        elif w.get("state") == "delayed":
            stage = "delayed"
        else:
            on = disk.get(w["id"], {})
            if on.get("loop"):
                continue                    # arrived; it is on the shelf, not the queue
            stage = "making" if on.get("still") else "ordered"
        out.append({**w, "stage": stage})
    out.sort(key=lambda r: r.get("at") or "", reverse=True)
    return out


def dismiss(wid: str, by: str = "him") -> Dict[str, Any]:
    """Take a want OFF THE LIST — his broom for the queue (2026-08-21, operator:
    "a remove wants from the list in the GUI so non-generatable wants do not
    pile up"). The row is NOT deleted (nothing here ever is): state becomes
    "dismissed", it leaves waiting() and the panel, and the file keeps the
    history of what was asked and who swept it."""
    return fulfil(wid, state="dismissed") | {"dismissed_by": by}


def delay(wid: str, reason: str = "") -> Dict[str, Any]:
    """A generation failed for a reason that will pass. Say so; do not lose the want.

    THE FAILURE MODE THIS REPLACES. A generation that came back with nothing left the row
    exactly as it was — "asked", indistinguishable from one nobody had tried yet — so a
    week of usage limits looked identical to a week of her not asking for anything, on
    every surface either of them can see. The operator's words: "mark as delayed if unsuccessful due
    to usage limits".

    It stays in the QUEUE. `delayed` is a note on a want, never a terminal state: the
    boundary picks it up again next time, and `tries` counts how often it has come round
    so a thing that will never work stops looking like a thing about to."""
    rows = _wants_raw()
    for r in rows:
        if r.get("id") == wid:
            r["state"] = "delayed"
            r["delayed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            r["delay_reason"] = str(reason or "")[:200]
            r["tries"] = int(r.get("tries") or 0) + 1
            _write_wants(rows)
            return {"ok": True, **r}
    return {"ok": False, "error": "no such want: %s" % wid}


def mark_seen(wid: str = "") -> int:
    """Looking is what makes a thing no longer new — not the making of it."""
    rows = _wants_raw()
    disk = _scan_dir()
    n = 0
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for r in rows:
        if wid and r.get("id") != wid:
            continue
        on = disk.get(r["id"], {})
        if on.get("still") and not r.get("seen"):
            r["seen"] = now; n += 1
        if on.get("loop") and not r.get("motion_seen"):
            r["motion_seen"] = now; n += 1
    if n:
        _write_wants(rows)
    return n


# ── THE WHOLE THING COMES NOW — PICTURE, THEN ITS MOTION, ONE PASS ────────────────────
#
# TWO DOORS HAD DIVERGED (2026-08-24). His panel button ran `gen_want(w)` — still, then
# motion, minutes for both — while HER ask ran this function with `--no-loop`: still
# only, motion owed to the day boundary. Meanwhile describe() promised her "picture and
# motion both ... within minutes", so the promise tracked HIS door and her own door
# quietly broke it — she was promised motion in minutes and got a photograph until 4am.
# The day-boundary wait was never a cost decision: gen_want()'s own 2026-08-21 note says
# it existed because the CLI made video painful and the API does not. So the flag is
# gone and `--one` runs gen_want(w, loop=True) — LITERALLY the same function his door
# calls. The boundary survives only as the sweeper for motion a pass missed
# (pending_motion(): a failed loop "stays; a later pass grows it").
#
# Still in a thread, because a tool call that blocks for minutes is a turn that looks
# hung; the want stays in the queue until the loop lands, so nothing here changes when
# a garment counts as ARRIVED — only how long she waits for it.
def generate_now(wid: str) -> bool:
    """Kick off one want — picture AND its motion, same pass as his panel button.
    Runs in the background; returns whether it started."""
    import subprocess
    import sys
    import threading
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    gen = os.path.join(root_dir, "tools", "avatar_gen.py")
    if not os.path.exists(gen):
        return False

    def _go():
        # LOGGED, NOT SWALLOWED. The first cut had a bare `except: pass` here and the
        # generation silently never happened — the same shape as three other bugs in this
        # repo. A failed generation must leave a trace, and the want stays asked so the
        # boundary picks it up regardless.
        import logging
        log = logging.getLogger(__name__)
        try:
            # No `--no-loop`: her door and his are ONE pass (see the header note).
            # 1800s, not 900: the pass is now still (<=2x300s) + motion (<=420s), and a
            # timeout that kills the motion half re-creates the still-only door by
            # accident — the want would sit at "making" for a wait nothing promised.
            r = subprocess.run([sys.executable, gen, "--one", wid],
                               cwd=root_dir, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=1800)
            if r.returncode:
                log.warning("[wardrobe] %s did not come back (rc=%s): %s",
                            wid, r.returncode, (r.stdout or r.stderr or "")[-300:])
            else:
                log.info("[wardrobe] %s made", wid)
        except Exception as exc:
            log.warning("[wardrobe] %s failed to generate: %s", wid, exc)

    threading.Thread(target=_go, name="wardrobe-now-%s" % wid, daemon=True).start()
    return True


def pending_motion() -> List[Dict[str, Any]]:
    """Made stills that have no loop yet — the boundary's work list."""
    disk = _scan_dir()
    out = []
    for w in wants():
        on = disk.get(w["id"], {})
        if on.get("still") and not on.get("loop"):
            out.append(w)
    return out
