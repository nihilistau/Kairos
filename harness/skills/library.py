"""library — the shelf she reads from (presence modes, 2026-08-22).

`var/library/` (SP_LIBRARY_DIR) is a folder he drops files into: .txt, .md, .epub. She may pick a
book up, read the next passage, put it down; the bookmark is a POSITION per title in
.bookmarks.json — never the text. Parsing is stdlib only (zipfile + html.parser); an aux model
may summarise 'what this book is about so far' for the cue, and its words are never spoken.
"""
from __future__ import annotations

import json
import os
import re
import time
import zipfile
from html.parser import HTMLParser
from typing import Optional

from harness.store_io import replace_atomic

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE: dict = {}


def _dir() -> str:
    d = os.environ.get("SP_LIBRARY_DIR") or os.path.join(_HERE, "var", "library")
    os.makedirs(d, exist_ok=True)
    return d


def _bm_path() -> str:
    return os.path.join(_dir(), ".bookmarks.json")


def _load_bm() -> dict:
    try:
        with open(_bm_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception as _swx:
        _swallowed(_swlog, "_load_bm", _swx, lane="skills")
        return {}


def _save_bm(d: dict) -> None:
    tmp = _bm_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, sort_keys=True)
    replace_atomic(tmp, _bm_path())


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self._skip += 1
        elif tag in ("p", "div", "br", "h1", "h2", "h3", "h4", "li", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self._skip:
            self._skip -= 1
        elif tag in ("p", "div", "h1", "h2", "h3", "h4", "li", "tr"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def _epub_text_and_title(path: str):
    title = ""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        opf = next((n for n in names if n.lower().endswith(".opf")), None)
        order = []
        if opf:
            xml = z.read(opf).decode("utf-8", "replace")
            m = re.search(r"<dc:title[^>]*>([^<]+)</dc:title>", xml)
            if m:
                title = m.group(1).strip()
            hrefs = dict(re.findall(r'<item[^>]+id="([^"]+)"[^>]+href="([^"]+)"', xml))
            if not hrefs:
                hrefs = {i: h for h, i in re.findall(r'<item[^>]+href="([^"]+)"[^>]+id="([^"]+)"', xml)}
            base = os.path.dirname(opf)
            for ref in re.findall(r'<itemref[^>]+idref="([^"]+)"', xml):
                h = hrefs.get(ref)
                if h:
                    order.append((base + "/" + h) if base else h)
        if not order:
            order = [n for n in names if n.lower().endswith((".xhtml", ".html", ".htm"))]
        out = []
        for n in order:
            try:
                p = _Text()
                p.feed(z.read(n).decode("utf-8", "replace"))
                out.append("".join(p.parts))
            except Exception as _swx:
                _swallowed(_swlog, "_epub_text_and_title", _swx, lane="skills")
                continue
    text = re.sub(r"[ \t]+", " ", "\n".join(out))
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text, title


def _read(path: str):
    """-> (title, text). Cached per (path, mtime)."""
    key = (path, os.path.getmtime(path))
    if key in _CACHE:
        return _CACHE[key]
    stem = os.path.splitext(os.path.basename(path))[0]
    if path.lower().endswith(".epub"):
        text, title = _epub_text_and_title(path)
        title = title or stem
    else:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        title = stem
    if len(_CACHE) > 8:
        _CACHE.clear()
    _CACHE[key] = (title, text)
    return _CACHE[key]


def books() -> list:
    """Every book on the shelf: title, file, length, bookmark position, done, in_hand."""
    bm = _load_bm()
    out = []
    for fn in sorted(os.listdir(_dir())):
        if fn.startswith(".") or not fn.lower().endswith((".txt", ".md", ".epub")):
            continue
        path = os.path.join(_dir(), fn)
        try:
            title, text = _read(path)
        except Exception as _swx:
            _swallowed(_swlog, "books", _swx, lane="skills")
            continue
        b = bm.get(title, {})
        out.append({"title": title, "file": fn, "chars": len(text), "pos": int(b.get("pos", 0)),
                    "done": bool(b.get("done")), "in_hand": bool(b.get("in_hand"))})
    return out


def in_hand() -> Optional[dict]:
    for b in books():
        if b["in_hand"]:
            return b
    return None


def pick_up(title: str) -> Optional[dict]:
    bm = _load_bm()
    shelf = books()
    match = next((b for b in shelf if b["title"].lower() == (title or "").lower()), None) \
        or next((b for b in shelf if (title or "").lower() and (title or "").lower() in b["title"].lower()), None)
    if not match:
        return None
    for k in bm:
        bm[k]["in_hand"] = False
    e = bm.setdefault(match["title"], {"pos": 0, "done": False})
    e["in_hand"] = True
    e["picked_up_at"] = int(time.time())
    _save_bm(bm)
    return in_hand()


def put_down() -> None:
    bm = _load_bm()
    for k in bm:
        bm[k]["in_hand"] = False
    _save_bm(bm)


def next_passage(chars: int = 700) -> str:
    """The next passage of the book in hand, ending on a sentence; '' when done or nothing in hand.
    Advances the bookmark."""
    b = in_hand()
    if not b:
        return ""
    path = os.path.join(_dir(), b["file"])
    _title, text = _read(path)
    pos = b["pos"]
    if pos >= len(text):
        bm = _load_bm()
        bm.setdefault(b["title"], {"pos": pos})["done"] = True
        _save_bm(bm)
        return ""
    end = min(len(text), pos + max(120, int(chars)))
    if end < len(text):
        cut = max(text.rfind(". ", pos, end), text.rfind("! ", pos, end), text.rfind("? ", pos, end),
                  text.rfind("\n\n", pos, end))
        if cut > pos + 80:
            end = cut + 1
    passage = " ".join(text[pos:end].split())
    bm = _load_bm()
    e = bm.setdefault(b["title"], {"pos": 0, "done": False})
    e["pos"] = end
    e["done"] = end >= len(text)
    e["in_hand"] = True
    _save_bm(bm)
    return passage


def about_so_far() -> str:
    """One line for the CUE only (never spoken): what the book in hand has been about. Uses the
    aux read_long when it is up; '' otherwise. Bounded to 160 chars."""
    b = in_hand()
    if not b or b["pos"] <= 0:
        return ""
    try:
        _t, text = _read(os.path.join(_dir(), b["file"]))
        from harness.sidecar.summarize import read_long
        s = read_long(text[max(0, b["pos"] - 6000):b["pos"]],
                      question="what has happened so far, in one line", max_words=30)
        return " ".join((s or "").split())[:160]
    except Exception as _swx:
        _swallowed(_swlog, "about_so_far", _swx, lane="skills")
        return ""


# ── her tools ───────────────────────────────────────────────────────────────────────
def books_on_the_shelf() -> str:
    """List the books on your shelf (var/library/) with how far you are in each."""
    bs = books()
    if not bs:
        return "The shelf is empty — nothing in var/library/ yet."
    return "\n".join("- %s — %s%s" % (
        b["title"],
        "finished" if b["done"] else "%d%% read" % (100 * b["pos"] // max(1, b["chars"])),
        " (in your hands)" if b["in_hand"] else "") for b in bs)


def pick_up_book(title: str) -> str:
    """Pick up a book from your shelf by title (or part of it) to read from, a passage at a time, on your own time."""
    b = pick_up(title)
    return ("You pick up %s (%d%% read)." % (b["title"], 100 * b["pos"] // max(1, b["chars"]))) if b \
        else "No book by that name on the shelf. %s" % books_on_the_shelf()


def put_down_book() -> str:
    """Put the book down; the bookmark is kept."""
    put_down()
    return "You put the book down, the bookmark where it was."


LIBRARY_TOOLS = [pick_up_book, put_down_book, books_on_the_shelf]
