"""catalog.py — everything she can wear, do, or show: ONE list, and the acts on it.

HIS OVERHAUL (2026-08-21): "add a way to remove clothing, gestures and moments (both
delete and hide/unhide from the UI)... a way for me to take video I have generated from
grok (or elsewhere), place them in the folder structure, title them, describe them,
categorize them as clothing, gestures or moments, run the loop and other tooling... edit
the title, description and category of current ones... and for her to use them
effectively."

THREE STORES, ONE SHAPE. The grid (avatar.py), her wants (wants.jsonl) and his clips
(clips.json) stay the truth about what EXISTS — wardrobe.looks()/clips() already read
them — and wardrobe's catalog.json is his OVERLAY (title, description, category, tags,
hidden, removed). This module is the façade: the unified rows the panel renders, the
edit/hide/remove/restore/import operations, and `for_her()` — the compact, category-
grouped text that tells her what she owns and which act reaches for each kind:

    CLOTHING  — a way she IS.            wear("…")        / [WEAR:…]
    GESTURE   — a thing she DOES.        express("…") or gesture("…")
    MOMENT    — a thing she SHOWS on his screen.  show_him("…") / [SHOW:…]

NOTHING IS DELETED. remove() writes `removed_at` — a tombstone; the file stays, the
row stays, restore() brings it back. hide() is the softer version (still hers, just not
offered). Both flow through wardrobe.looks()/clips(), the readers every consumer uses,
so a hidden asset is hidden for her tools, the panel, the portrait and the matcher at
once and nothing can re-admit it by a side door.

IMPORT RUNS THE SAME TOOLING AS A MADE LOOK. A video he drops in var/room/avatar/inbox/
is copied (never moved), converted to webm, optionally ping-ponged into a seamless loop,
given a poster frame, and registered as a MADE want (by=him, imported) — so the
portrait, the /v1/wardrobe/look route, the matcher and her tools all see it exactly as
they see one the generator made. A still image imports as a still-only want: the
motion can then be grown from it by the generator ("make it now"), which IS the loop
tooling he asked it to pass through. A file categorized `moment` goes to the clips
store instead (import_clip) — a thing she puts on his screen.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

from harness.control import avatar as AV
from harness.control import wardrobe as WD

CATEGORIES = WD.CATEGORIES
INBOX = "inbox"
_VIDEO = (".mp4", ".webm", ".mov", ".mkv", ".m4v")
_IMAGE = (".png", ".jpg", ".jpeg", ".webp")

ACT = {
    "clothing": 'wear("…") or [WEAR:…] — a way you are',
    "gesture": 'express("…") or gesture("…") — a thing you do, on your face',
    "moment": 'show_him("…") or [SHOW:…] — a thing you put on his screen',
}


def inbox_dir() -> str:
    return os.path.join(WD.root(), INBOX)


def inbox() -> List[Dict[str, Any]]:
    """Files he has dropped in, waiting to be named and placed. Never auto-imported:
    a title and a category are HIS call, and the import is the click."""
    d = inbox_dir()
    os.makedirs(d, exist_ok=True)
    out = []
    for fn in sorted(os.listdir(d)):
        ext = os.path.splitext(fn)[1].lower()
        if ext not in _VIDEO + _IMAGE:
            continue
        p = os.path.join(d, fn)
        out.append({"file": fn, "kind": "video" if ext in _VIDEO else "image",
                    "bytes": os.path.getsize(p),
                    "guess": WD.describe_file(fn)})
    return out


# ── THE UNIFIED ROWS ──────────────────────────────────────────────────────────────────
def _outfit_rows() -> List[Dict[str, Any]]:
    out = []
    for t in AV.OUTFIT_IDS:
        o = WD.OUTFITS.get(t, {})
        r = {"id": t, "source": "grid", "kind": "outfit",
             "label": o.get("name") or t, "tags": list(o.get("calls") or [])[:6],
             "have": AV.have("calm", t, "still"), "moves": AV.have("calm", t, "loop"),
             "still_url": "/v1/wardrobe/outfit?tier=%s" % t,
             "loop_url": "/v1/wardrobe/outfit?tier=%s&kind=loop" % t}
        r = WD._apply_overlay(r, "clothing")
        if not r["description"]:
            r["description"] = o.get("wearing", "")
        out.append(r)
    return out


def _look_rows() -> List[Dict[str, Any]]:
    out = []
    for l in WD.looks(all=True):
        r = dict(l)
        if l.get("kind") == "clip":
            r["still_url"] = ""
            r["loop_url"] = "/v1/wardrobe/file?id=%s" % l["id"]
            r["moves"] = True
        else:
            r["still_url"] = "/v1/wardrobe/look?id=%s" % l["id"]
            r["loop_url"] = ("/v1/wardrobe/look?id=%s&kind=loop" % l["id"]) if l.get("moves") else ""
        out.append(r)
    return out


def rows(include_hidden: bool = False, include_removed: bool = False) -> List[Dict[str, Any]]:
    """Everything, one shape. `hidden` and `removed_at` ride on every row so the
    panel can always offer the way back."""
    st = WD.current()
    on_look, on_clip, on_tier = st.get("look") or "", st.get("clip") or "", st.get("tier") or ""
    out = []
    for r in _outfit_rows() + _look_rows():
        if r.get("removed_at") and not include_removed:
            continue
        if r.get("hidden") and not r.get("removed_at") and not include_hidden:
            continue
        r["on"] = (r["id"] == on_look) or (r["id"] == on_clip) or \
                  (r.get("kind") == "outfit" and r["id"] == on_tier and not on_look and not on_clip)
        out.append(r)
    order = {c: i for i, c in enumerate(CATEGORIES)}
    out.sort(key=lambda r: (order.get(r.get("category"), 9), r.get("kind") != "outfit", r["id"]))
    return out


def by_category(include_hidden: bool = False) -> Dict[str, List[Dict[str, Any]]]:
    d: Dict[str, List[Dict[str, Any]]] = {c: [] for c in CATEGORIES}
    for r in rows(include_hidden=include_hidden):
        d.setdefault(r.get("category") or "clothing", []).append(r)
    return d


# ── THE ACTS ON A ROW ─────────────────────────────────────────────────────────────────
def _known(aid: str) -> bool:
    return any(r["id"] == aid for r in rows(include_hidden=True, include_removed=True))


def edit(aid: str, title: Optional[str] = None, description: Optional[str] = None,
         category: Optional[str] = None, tags: Optional[List[str]] = None) -> Dict[str, Any]:
    if not _known(aid):
        return {"ok": False, "error": "no asset %r" % aid}
    f: Dict[str, Any] = {}
    if title is not None:
        f["title"] = title.strip() or None
    if description is not None:
        f["description"] = description.strip() or None
    if category is not None:
        if category not in CATEGORIES:
            return {"ok": False, "error": "category must be one of %s" % ", ".join(CATEGORIES)}
        f["category"] = category
    if tags is not None:
        f["tags"] = [str(t).strip() for t in tags if str(t).strip()][:12]
    WD.set_overlay(aid, **f)
    return {"ok": True, "id": aid, **WD.overlay_for(aid)}


def hide(aid: str) -> Dict[str, Any]:
    if not _known(aid):
        return {"ok": False, "error": "no asset %r" % aid}
    WD.set_overlay(aid, hidden=True)
    _take_off_if_on(aid)
    return {"ok": True, "id": aid, "hidden": True}


def unhide(aid: str) -> Dict[str, Any]:
    if not _known(aid):
        return {"ok": False, "error": "no asset %r" % aid}
    WD.set_overlay(aid, hidden=None)
    return {"ok": True, "id": aid, "hidden": False}


def remove(aid: str, by: str = "him") -> Dict[str, Any]:
    """TOMBSTONE. The row and the file stay; the offer stops. restore() undoes it."""
    if not _known(aid):
        return {"ok": False, "error": "no asset %r" % aid}
    if aid in AV.OUTFIT_IDS:
        return {"ok": False, "error": "the standard set cannot be removed — hide it instead"}
    WD.set_overlay(aid, removed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   removed_by=by)
    _take_off_if_on(aid)
    return {"ok": True, "id": aid, "removed": True}


def restore(aid: str) -> Dict[str, Any]:
    if not _known(aid):
        return {"ok": False, "error": "no asset %r" % aid}
    WD.set_overlay(aid, removed_at=None, removed_by=None, hidden=None)
    return {"ok": True, "id": aid, "removed": False}


def _take_off_if_on(aid: str) -> None:
    """Hiding or removing what she has ON takes it off her — a portrait wearing a
    thing that is no longer offered is the one inconsistency this must not leave."""
    st = WD.current()
    if st.get("look") == aid:
        WD.choose(look="", by="him")
    if st.get("clip") == aid:
        WD.choose(clip="", by="him")


# ── IMPORT: his files, through the same tooling ───────────────────────────────────────
def _ffmpeg(args: List[str], timeout: int = 600) -> bool:
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-y"] + args,
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0
    except Exception:
        return False


def _poster(video: str, png: str) -> bool:
    return _ffmpeg(["-i", video, "-frames:v", "1", png]) and os.path.exists(png)


def _pingpong(path: str) -> bool:
    """Same seamless forward+back the generator applies (tools/avatar_gen.pingpong),
    called here so an import and a generation are indistinguishable downstream."""
    try:
        from tools import avatar_gen as G
        return bool(G.pingpong(path))
    except Exception:
        return False


def import_file(name: str, category: str, title: str = "", description: str = "",
                tags: Optional[List[str]] = None, loop: bool = True,
                by: str = "him") -> Dict[str, Any]:
    """One inbox file -> one catalogued asset, through the tooling a made look passes
    through. Returns the catalogued row or {"ok": False, "error"}."""
    name = os.path.basename(name or "")
    src = os.path.join(inbox_dir(), name)
    if not name or not os.path.isfile(src):
        return {"ok": False, "error": "no such file in the inbox: %r" % name}
    if category not in CATEGORIES:
        return {"ok": False, "error": "category must be one of %s" % ", ".join(CATEGORIES)}
    ext = os.path.splitext(name)[1].lower()
    stem = re.sub(r"\.[a-z0-9]+$", "", name, flags=re.I)
    title = (title or "").strip() or re.sub(r"[-_]+", " ", stem).strip()
    tags = [str(t).strip() for t in (tags or []) if str(t).strip()][:12]

    if category == "moment":
        if ext not in _VIDEO:
            return {"ok": False, "error": "a moment is a video"}
        row = WD.import_clip(src, label=title)
        WD.set_overlay(row["id"], title=title, description=description.strip() or None,
                       category="moment", tags=tags or None, source="imported")
        return {"ok": True, "id": row["id"], "category": "moment", "title": title, "moves": True}

    # clothing / gesture -> a MADE want, so every reader already knows how to serve it
    kind = "gesture" if category == "gesture" else "look"
    tier = WD.current().get("tier") or AV.DEFAULT_OUTFIT
    r = WD.request(title, tier=tier, by=by, kind=kind, calls=tags)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error", "could not register")}
    wid = r["id"]
    looks_dir = os.path.join(WD.root(), "looks")
    os.makedirs(looks_dir, exist_ok=True)
    still = os.path.join(looks_dir, wid + ".png")
    loopf = os.path.join(looks_dir, wid + ".webm")
    made_loop = ""
    if ext in _VIDEO:
        if ext == ".webm":
            shutil.copy2(src, loopf)                 # COPIES — his file stays where he put it
            ok_conv = True
        else:
            # the generator's own encoder: vp9 webm, no audio
            ok_conv = _ffmpeg(["-i", src, "-c:v", "libvpx-vp9", "-crf", "34", "-b:v", "0",
                               "-an", loopf])
        if not ok_conv:
            WD.fulfil(wid, state="refused")
            return {"ok": False, "error": "could not convert %s to webm (ffmpeg)" % name}
        if loop:
            _pingpong(loopf)
        made_loop = wid + ".webm"
        _poster(loopf, still)
    else:
        shutil.copy2(src, still)                     # a still-only look; motion can be grown later
    WD.fulfil(wid, file=wid + ".png", state="made", loop=made_loop)
    WD.set_overlay(wid, title=title, description=description.strip() or None,
                   category=category, tags=tags or None, source="imported")
    return {"ok": True, "id": wid, "category": category, "title": title,
            "moves": bool(made_loop),
            "note": "" if made_loop else "a still — 'make it now' grows the motion from it"}


# ── WHAT SHE IS TOLD ──────────────────────────────────────────────────────────────────
def for_her(limit: int = 14) -> str:
    """The compact, category-grouped account of what she owns and how to reach for
    each kind — appended to describe(), which is what check_wardrobe hands her.
    Titles are HIS titles when he gave one; the act for each kind is named."""
    d = by_category()
    out = ["BY KIND — what you own, and the act that reaches for it:"]
    for cat in CATEGORIES:
        items = d.get(cat) or []
        if not items:
            out.append("  %s: none yet (%s)" % (cat.upper(), ACT[cat]))
            continue
        names = []
        for r in items[:limit]:
            t = (r.get("title") or r.get("label") or r["id"]).strip()
            names.append(t + (" (on you now)" if r.get("on") else ""))
        more = "" if len(items) <= limit else " …and %d more" % (len(items) - limit)
        out.append("  %s (%d) — %s:\n    %s%s"
                   % (cat.upper(), len(items), ACT[cat], "; ".join(names), more))
    return "\n".join(out)
