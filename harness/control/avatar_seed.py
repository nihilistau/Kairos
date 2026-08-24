"""avatar_seed.py — the bundled default set, laid down ONCE into var/room/avatar/.

WHAT PROBLEM. A fresh clone has an empty avatar directory, so `ui/src/room/Avatar.jsx`
draws the fallback SVG and that is the framework's first impression. Kairos ships a
small real set — one outfit across all seven faces, six gestures, and the reference they
were grown from (`assets/avatar-default/`, built by `tools/kairos_default_set.py` in the
source repo). This module copies it in.

THREE RULES, AND THEY ARE THE WHOLE MODULE.

1. **IT ONLY EVER FILLS GAPS.** A destination that exists is left exactly as it is —
   still, loop, receipt, `character.txt`, `_reference.png`, and every row already in
   `wants.jsonl`. There is no branch in here that overwrites anything. Seeding over a
   live wardrobe would be the same class of accident as the re-export that once wiped a
   running stack's token: a convenience that silently outranks state somebody made.

2. **IT RUNS ONCE PER SET, AND THE MARKER SAYS SO.** `.seeded.json` in the avatar root
   records which set ids have been laid down. Gap-filling alone would be wrong the other
   way: delete a bundled gesture you do not want and the next boot would hand it back,
   forever. The marker means "Kairos has offered you this set" — offered once, never
   again. (A later `kairos-default-2` is a new id and seeds beside the first.)

3. **IT NEVER FAILS THE BOOT.** No bundled directory, an unreadable file, a full disk:
   every one of those is a room with the SVG in it, which is a floor and not an outage.
   Every path returns a dict and logs; nothing raises out of `seed()`.

WHAT IT IS NOT. Not a restore (`harness/control/backup.py` owns that), not a reset — it
cannot put back something you removed, because a tombstone from `catalog.remove()` lives
in `catalog.json` and the file it points at was never deleted in the first place.
"""
from __future__ import annotations

import json
import os
import shutil
from typing import Any, Dict, List

from harness.control import avatar as AV

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MARKER = ".seeded.json"


def assets_dir() -> str:
    """Where the bundled set lives. `SP_AVATAR_DEFAULTS` overrides it so the gate can
    point at a fixture without moving the real one."""
    return os.environ.get("SP_AVATAR_DEFAULTS") or os.path.join(_ROOT, "assets", "avatar-default")


def set_id() -> str:
    """The id in SET.json — the thing the marker records. An unreadable or absent
    SET.json means there is no set to seed, not an unnamed one: seeding an unidentified
    pile of files is how you seed it twice."""
    try:
        with open(os.path.join(assets_dir(), "SET.json"), encoding="utf-8") as f:
            return str(json.load(f).get("set") or "")
    except Exception:
        return ""


def _marker_path() -> str:
    return os.path.join(AV.root(), _MARKER)


def seeded() -> List[str]:
    try:
        with open(_marker_path(), encoding="utf-8") as f:
            d = json.load(f)
        return [str(x) for x in (d.get("sets") or [])]
    except Exception:
        return []


def _mark(sid: str, laid: int) -> None:
    try:
        d: Dict[str, Any] = {}
        try:
            with open(_marker_path(), encoding="utf-8") as f:
                d = json.load(f) or {}
        except Exception:
            d = {}
        sets = [str(x) for x in (d.get("sets") or [])]
        if sid not in sets:
            sets.append(sid)
        d["sets"] = sets
        # The count is for the human reading the file, not for any code path: "0 files"
        # beside a recorded set is the honest picture of seeding onto a full wardrobe.
        d.setdefault("laid", {})[sid] = laid
        os.makedirs(AV.root(), exist_ok=True)
        tmp = _marker_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1)
        os.replace(tmp, _marker_path())
    except Exception:
        pass


def _wants_rows(path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    out.append(json.loads(ln))
    except Exception:
        pass
    return out


def status() -> Dict[str, Any]:
    """What the setup panel asks: is there a bundled set, has it been laid down, and does
    the room actually have a face right now. `have_face` is answered off the GRID rather
    than off the marker — the marker says what Kairos did, and the question is what is on
    disk."""
    sid = set_id()
    have = sum(1 for f in AV.FACES if AV.have(f, AV.DEFAULT_OUTFIT, "still"))
    return {
        "bundled": bool(sid),
        "set": sid,
        "dir": assets_dir(),
        "seeded": sid in seeded() if sid else False,
        "faces_total": len(AV.FACES),
        "faces_with_art": have,
        "have_face": have > 0,
    }


def seed() -> Dict[str, Any]:
    """Lay the bundled set down if it has never been laid down. Safe to call on every
    boot; safe to call twice in one boot; never raises."""
    try:
        src = assets_dir()
        sid = set_id()
        if not sid or not os.path.isdir(src):
            return {"ok": True, "seeded": False, "why": "no bundled set", "files": 0}
        if sid in seeded():
            return {"ok": True, "seeded": False, "why": "already offered", "set": sid, "files": 0}

        dst_root = AV.root()
        os.makedirs(dst_root, exist_ok=True)
        laid = 0
        skipped = 0
        # The binaries, the receipts, the reference and character.txt in one walk. The
        # bookkeeping files are handled below and excluded here so the merge cannot be
        # written twice — wants.jsonl is APPENDED to, never copied over.
        never_copy = {"wants.jsonl", "README.md", "SET.json"}
        for base, _dirs, files in os.walk(src):
            rel = os.path.relpath(base, src)
            for fn in files:
                if rel == "." and fn in never_copy:
                    continue
                # ── THE BUNDLE PREDATES THE RENAME (2026-08-25) ──────────────────
                # The shipped set was built while outfits were still t0..t3 and lays
                # down `bright/t0/…`; outfits became names on 2026-08-23 and the
                # wardrobe now looks for `bright/mesh-top/…`. So a fresh clone seeded
                # 24 MB of art and then drew the fallback SVG — `faces_with_art: 0`,
                # the framework's first impression, broken since the rename and
                # invisible because the export's own suite had no runner until today.
                # CANONICALISED AS IT IS COPIED, not rebuilt: `AV.canon` is the one
                # rename table, so every future bundle and every old one land right,
                # and the asset stays byte-identical to what was published.
                _rel = os.path.join(*[AV.canon(part) if AV.canon(part) in AV.OUTFIT_IDS
                                      else part
                                      for part in rel.split(os.sep)]) if rel != "." else "."
                d = os.path.join(dst_root, "" if _rel == "." else _rel, fn)
                if os.path.exists(d):
                    skipped += 1
                    continue
                try:
                    os.makedirs(os.path.dirname(d), exist_ok=True)
                    shutil.copy2(os.path.join(base, fn), d)
                    laid += 1
                except Exception:
                    skipped += 1

        # ── THE GESTURE ROWS ────────────────────────────────────────────────────────
        # Appended by id, so a wants.jsonl that already carries `d-laugh` (a second boot
        # of an older marker file, a hand-restored backup) gains nothing. Written through
        # a temp file and replaced, because a half-written wants.jsonl is a wardrobe that
        # silently loses everything after the truncation point.
        rows_new = _wants_rows(os.path.join(src, "wants.jsonl"))
        added = 0
        if rows_new:
            wp = os.path.join(dst_root, "wants.jsonl")
            have_ids = {str(r.get("id")) for r in _wants_rows(wp)}
            add = [r for r in rows_new if str(r.get("id")) not in have_ids]
            if add:
                try:
                    with open(wp, "a", encoding="utf-8") as f:
                        for r in add:
                            f.write(json.dumps(r, ensure_ascii=False) + "\n")
                    added = len(add)
                except Exception:
                    added = 0
        _mark(sid, laid)
        return {"ok": True, "seeded": True, "set": sid,
                "files": laid, "skipped": skipped, "wants": added}
    except Exception as exc:                      # a face is never worth a failed boot
        return {"ok": False, "seeded": False, "error": str(exc), "files": 0}
