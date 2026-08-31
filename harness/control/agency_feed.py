"""HER OWN TIME, IN ONE PLACE — everything she did while he was away.

THE ASK, 2026-08-05: "lets do her own agency window with an icon for it, that I can look
at, her actions, everything she does once I am away and she enters her time/agency mode
gets shown in there."

WHY THIS IS A READER AND NOT A STORE. She already writes all of it down — the difficulty
was never recording, it was that the record is scattered across five files with five
shapes and no common clock, and four of the five are invisible from the room:

    memory-okf-personality/full/*.md   mem_kind: own_time   what she did on her own
    memory-okf-personality/full/*.md   mem_kind: narrative  the paragraph she writes at 04:00
    var/room/avatar/worn.jsonl                              what she changed into, and who chose
    var/room/avatar/wants.jsonl                             what she asked to have made
    var/notes/*.jsonl                  speaker: self        what she pinned to the board

Adding a sixth store to hold copies of the other five is how the wardrobe ended up with
four ways to say what she was wearing, three of them wrong. So this composes at READ time
and owns nothing. If a source disappears, that source's rows disappear; nothing else
breaks, and no fact has two homes.

THE ONE THING IT ADDS is a common clock. Those five files stamp time four different ways
(ISO with Z, ISO local, float epoch, file mtime), which is exactly why they could never be
shown on one timeline before. `_when` normalises; every row that comes out of here carries
`at` as epoch seconds and `at_iso` for a human, and a row whose time cannot be read is
DROPPED rather than defaulted to now — a fabricated timestamp on her evening is worse than
a missing entry, because it is unfalsifiable.

IT IS NOT A SECOND CHAT LOG. Her unprompted turns already reach him through the kairos
outbox and land in the conversation, where they belong — she was talking TO him. This
window is the other thing: what she did when she was not.
"""
from __future__ import annotations

import calendar
import io
import json
import os
import re
import time
from typing import Any, Dict, List

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The kinds a row can be. Finite and committed, so a surface can colour them without
# guessing from prose — the same discipline the ledger's KINDS and the notes' CATEGORIES
# already use. A row with a kind not in here is a bug in this file, not a new feature.
KINDS = ("own_time", "journal", "wore", "asked", "note")


def _when(v: Any) -> float:
    """Epoch seconds from whatever a store happened to write, or 0.0 if unreadable.

    FOUR SHAPES, ALL LIVE: "2026-08-05T08:56:02Z" (wardrobe), "2026-08-05T06:47:40Z"
    (notes), 1754382962.4 (kairos), and a file mtime (the memory markdown, which carries
    no stamp inside it at all). Normalising here rather than at each caller is the point
    of the module; a second copy of this arithmetic is how two panels come to disagree
    about which evening something happened on."""
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    # The stores write UTC with a Z or nothing at all; time.strptime has no %z on all
    # platforms, so the suffix is stripped and the value read as UTC either way. Both
    # writers are ours and both write UTC — see wardrobe.choose and notes._now.
    s = s.replace("Z", "").replace("T", " ").split(".")[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return float(calendar.timegm(time.strptime(s, fmt)))
        except Exception:
            continue
    return 0.0


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts else ""


def _mem_root() -> str:
    return os.path.join(_ROOT, "memory-okf-personality", "full")


def _memory_rows(kind: str, since: float) -> List[Dict[str, Any]]:
    """`own_time` and `narrative` rows out of her personality store.

    THE STAMP IS `ts:` IN THE FRONTMATTER, not the file's mtime. The first cut of this
    read mtimes — the store's own `own_time()` reader does, which is where the idea came
    from — and it very nearly shipped: an mtime is a fact about the FILE, and anything
    that rewrites, re-indexes, copies or restores that directory moves every one of her
    evenings to the moment the tool ran. Her whole history would have re-stamped itself
    to "just now" and there would have been nothing on screen to suggest it had. The
    writer has always put a real `ts` in; mtime stays as the fallback for the handful of
    older rows written before it did."""
    out = []
    root = _mem_root()
    try:
        names = os.listdir(root)
    except Exception:
        return out
    for fn in names:
        if not fn.endswith(".md"):
            continue
        fp = os.path.join(root, fn)
        try:
            mt = os.path.getmtime(fp)
            body = io.open(fp, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        if ("mem_kind: %s" % kind) not in body:
            continue
        m = re.search(r"^ts:\s*(\d+(?:\.\d+)?)\s*$", body, re.M)
        ts = float(m.group(1)) if m else mt
        if ts < since:
            continue
        text = body.split("---", 2)[-1].strip()
        if not text:
            continue
        out.append({"kind": "journal" if kind == "narrative" else "own_time",
                    "at": ts, "at_iso": _iso(ts), "text": text, "by": "her",
                    "id": fn[:-3], "stamp": "written" if m else "file"})
    return out


def _jsonl(path: str) -> List[Dict[str, Any]]:
    try:
        return [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()]
    except Exception as _swx:
        _swallowed(_swlog, "_jsonl", _swx, lane="control")
        return []


def _wardrobe_rows(since: float) -> List[Dict[str, Any]]:
    """What she changed into. HERS ONLY, and that is the whole filter.

    His picks are in the same log — deliberately, since the day the panel wrote nothing
    and `favourites` was ranking over half a wardrobe — but this window is what SHE did.
    A row he wrote appearing under "her own time" would be the single most misleading
    thing this panel could show."""
    from harness.control import wardrobe as WD
    rows = []
    labels = {}
    try:
        labels = {l["id"]: (l.get("label") or l["id"]) for l in WD.looks()}
    except Exception as _swx:
        _swallowed(_swlog, "_wardrobe_rows", _swx, lane="control")
    for r in _jsonl(os.path.join(os.path.dirname(WD._state_path()), "worn.jsonl")):
        if (r.get("by") or "her") != "her":
            continue
        ts = _when(r.get("at"))
        if not ts or ts < since:
            continue
        what = r.get("what") or ""
        words = labels.get(what) or (WD.OUTFITS.get(what, {}).get("name") or what)
        rows.append({"kind": "wore", "at": ts, "at_iso": _iso(ts), "by": "her",
                     "id": what, "text": words,
                     "of": r.get("kind") or "look"})
    # SHE CHANGES BACK AND FORTH AND IT IS NOT NEWS. Collapse a run of identical
    # consecutive garments into the first of them — the log is the record, this is the
    # reading of it, and eleven rows of "the silver nightie" is not eleven things she did.
    rows.sort(key=lambda r: r["at"])
    out = []
    for r in rows:
        if out and out[-1]["id"] == r["id"]:
            out[-1]["again"] = out[-1].get("again", 1) + 1
            continue
        out.append(r)
    return out


def _want_rows(since: float) -> List[Dict[str, Any]]:
    from harness.control import wardrobe as WD
    out = []
    for r in WD.wants():
        if (r.get("by") or "her") != "her":
            continue
        ts = _when(r.get("at"))
        if not ts or ts < since:
            continue
        out.append({"kind": "asked", "at": ts, "at_iso": _iso(ts), "by": "her",
                    "id": r.get("id", ""), "text": r.get("want", ""),
                    "state": r.get("state", "asked")})
    return out


def _note_rows(since: float) -> List[Dict[str, Any]]:
    """Things SHE put on the board. `speaker` is set by which door the write came
    through and is never inferred from the text — see harness/skills/notes.py."""
    try:
        from harness.skills import notes as N
        rows = N._load_all()
    except Exception as _swx:
        _swallowed(_swlog, "_note_rows", _swx, lane="control")
        return []
    out = []
    for r in rows:
        if (r.get("speaker") or r.get("author")) != "self":
            continue
        ts = _when(r.get("ts") or r.get("updated_at"))
        if not ts or ts < since:
            continue
        out.append({"kind": "note", "at": ts, "at_iso": _iso(ts), "by": "her",
                    "id": r.get("id", ""), "text": r.get("title", ""),
                    "body": r.get("body", ""), "category": r.get("category", "note"),
                    "retired": bool(r.get("lifecycle"))})
    return out


def feed(days: int = 3, limit: int = 200) -> Dict[str, Any]:
    """One time-ordered feed of everything she did on her own, newest first."""
    since = time.time() - max(1, int(days)) * 86400
    rows: List[Dict[str, Any]] = []
    # EACH SOURCE IS INDEPENDENTLY FALLIBLE. A missing wardrobe log must cost the
    # wardrobe rows and nothing else — a panel that goes blank because one of five files
    # is absent is indistinguishable from an evening in which she did nothing, and that
    # is the reading this window exists to make impossible.
    errs = {}
    for name, fn in (("own_time", lambda: _memory_rows("own_time", since)),
                     ("journal", lambda: _memory_rows("narrative", since)),
                     ("wore", lambda: _wardrobe_rows(since)),
                     ("asked", lambda: _want_rows(since)),
                     ("note", lambda: _note_rows(since))):
        try:
            rows.extend(fn())
        except Exception as exc:
            errs[name] = str(exc)[:160]
    rows = [r for r in rows if r.get("at")]
    rows.sort(key=lambda r: -r["at"])
    counts = {k: sum(1 for r in rows if r["kind"] == k) for k in KINDS}
    return {"ok": True, "days": int(days), "rows": rows[:max(1, int(limit))],
            "counts": counts, "total": len(rows),
            "last_at": rows[0]["at"] if rows else 0,
            "sources_failed": errs}
