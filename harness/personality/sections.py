"""PERSONA SECTIONS — her persona as titled cards you can edit (2026-11-26, design §7b).

The persona is the `persona/` folder: one fragment per file, frontmatter (`order`, optional
`when`) then a `## Title` and prose (persona_layers.py is the composer and the format's
owner). This module is the EDITOR's view of the same files: each fragment as a section with
a title, its text, its place in the order, and whether the template has a version of it.

NOTHING IS DELETED. "Remove" is RETIRE: the file moves to `persona/_retired/<ts>-<file>`,
which the composer never reads (it lists *.md in the folder itself), and `restore` brings it
back. "Reset to template" retires the current text first. Every write goes through a temp
file and an atomic replace, and the filename is attacker-shaped input: a plain `*.md`
basename inside the folder, or a refusal.

Edits apply from her NEXT session: the prefix is snapshot-cached for the process lifetime
(persona_layers' docstring), and every caller says so.

Gate: G-PERSONA-SECTIONS (harness_tests/g_persona_sections.py).
"""
from __future__ import annotations

import os
import re
import shutil
import time
from typing import Dict, List, Optional

from harness.personality import persona_layers as PL
from harness.store_io import replace_atomic

RETIRED = "_retired"
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.md$")
_TITLE = re.compile(r"^##\s+(.+?)\s*$", re.M)


class SectionError(ValueError):
    pass


def _dir(directory: Optional[str] = None) -> str:
    return directory or PL.persona_dir()


def template_dir() -> str:
    from harness import companion_create as CC
    return CC.template_dir()


def _path(name: str, directory: Optional[str] = None) -> str:
    d = _dir(directory)
    if not _NAME.match(name or "") or os.path.basename(name) != name:
        raise SectionError("bad section file name: %r" % (name or "")[:60])
    p = os.path.abspath(os.path.join(d, name))
    if os.path.dirname(p) != os.path.abspath(d):
        raise SectionError("that file would land outside her persona folder")
    return p


def split(body: str):
    """(title, text) from a fragment body: the first `## ` heading is the title."""
    m = _TITLE.search(body or "")
    if not m or (body[:m.start()].strip()):
        return "", (body or "").strip()
    return m.group(1).strip(), (body[m.end():]).strip()


def render(title: str, text: str, order: int, when: str = "") -> str:
    fm = "---\norder: %d\n" % int(order) + ("when: %s\n" % when if when else "") + "---\n"
    head = ("## %s\n" % title.strip()) if title.strip() else ""
    return fm + head + (text or "").strip() + "\n"


def _write(p: str, content: str) -> None:
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    replace_atomic(tmp, p)


def _template_text(name: str) -> Optional[str]:
    t = template_dir()
    p = os.path.join(t, name) if t else ""
    if p and os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            return f.read()
    return None


def list_sections(directory: Optional[str] = None) -> List[dict]:
    """Every section, in composition order, with what an editor needs."""
    out = []
    for r in PL.plan(directory=_dir(directory)):
        title, text = split(r["body"])
        tpl = _template_text(r["file"])
        tpl_body = PL.parse_fragment(tpl)[1] if tpl is not None else None
        out.append({"file": r["file"], "order": r["order"], "when": r["when"],
                    "included": r["included"], "title": title or r["file"][:-3],
                    "text": text, "chars": r["chars"],
                    "from_template": tpl is not None,
                    "as_template": tpl_body is not None and tpl_body.strip() == r["body"].strip()})
    return out


def retired(directory: Optional[str] = None) -> List[dict]:
    d = os.path.join(_dir(directory), RETIRED)
    if not os.path.isdir(d):
        return []
    rows = []
    for f in sorted(os.listdir(d), reverse=True):
        if f.endswith(".md"):
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                title, _t = split(PL.parse_fragment(fh.read())[1])
            rows.append({"name": f, "file": f.split("-", 1)[1] if "-" in f else f,
                         "title": title})
    return rows


def _retire(p: str) -> str:
    d = os.path.join(os.path.dirname(p), RETIRED)
    os.makedirs(d, exist_ok=True)
    # <stamp>-<original name>: the stamp never contains "-", so restore() can always split
    # the original back off. Two retirements in one second get distinct stamps.
    stamp = int(time.time() * 1e6)
    dst = os.path.join(d, "%d-%s" % (stamp, os.path.basename(p)))
    while os.path.exists(dst):
        stamp += 1
        dst = os.path.join(d, "%d-%s" % (stamp, os.path.basename(p)))
    shutil.move(p, dst)
    return os.path.basename(dst)


def slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return s[:40] or "section"


def save(file: str, title: str, text: str, *, order: Optional[int] = None,
         directory: Optional[str] = None) -> dict:
    """Write an existing section's title and text (its order and `when` kept unless given).
    The previous text is retired first, so an edit can always be walked back."""
    p = _path(file, directory)
    if not os.path.isfile(p):
        raise SectionError(f"no section {file}")
    with open(p, encoding="utf-8") as f:
        fm, _b = PL.parse_fragment(f.read())
    o = order if order is not None else int(fm.get("order", "500") or 500)
    _retire_copy(p)
    _write(p, render(title, text, o, fm.get("when", "")))
    return {"ok": True, "file": file}


def _retire_copy(p: str) -> None:
    """Keep the previous text in _retired/ (a copy; the file stays in place to be rewritten)."""
    d = os.path.join(os.path.dirname(p), RETIRED)
    os.makedirs(d, exist_ok=True)
    stamp = int(time.time() * 1e6)
    while os.path.exists(os.path.join(d, "%d-%s" % (stamp, os.path.basename(p)))):
        stamp += 1
    shutil.copy2(p, os.path.join(d, "%d-%s" % (stamp, os.path.basename(p))))


def add(title: str, text: str, *, order: int = 500, file: str = "",
        directory: Optional[str] = None) -> dict:
    """A new section. Its file name comes from its order and title unless given."""
    if not (title or "").strip():
        raise SectionError("a section needs a title")
    d = _dir(directory)
    name = file or "%02d-%s.md" % (max(0, min(int(order), 999)), slug(title))
    p = _path(name, directory)
    n = 2
    while os.path.exists(p):
        name = "%02d-%s-%d.md" % (max(0, min(int(order), 999)), slug(title), n)
        p = _path(name, directory)
        n += 1
    os.makedirs(d, exist_ok=True)
    _write(p, render(title, text, order))
    return {"ok": True, "file": name}


def reorder(files: List[str], directory: Optional[str] = None) -> dict:
    """Give the listed sections orders 10, 20, 30… in that sequence. Sections not listed
    keep theirs. Title, text and `when` are untouched."""
    for i, name in enumerate(files):
        p = _path(name, directory)
        with open(p, encoding="utf-8") as f:
            fm, body = PL.parse_fragment(f.read())
        title, text = split(body)
        _write(p, render(title, text, (i + 1) * 10, fm.get("when", "")))
    return {"ok": True, "order": list(files)}


def retire(file: str, directory: Optional[str] = None) -> dict:
    p = _path(file, directory)
    if not os.path.isfile(p):
        raise SectionError(f"no section {file}")
    return {"ok": True, "retired_as": _retire(p)}


def restore(name: str, directory: Optional[str] = None) -> dict:
    """Bring a retired section back (under its original file name; a section that has
    taken that name since is retired in its place, so nothing is lost either way)."""
    d = _dir(directory)
    src = os.path.abspath(os.path.join(d, RETIRED, os.path.basename(name or "")))
    if os.path.dirname(src) != os.path.abspath(os.path.join(d, RETIRED)) or not os.path.isfile(src):
        raise SectionError(f"no retired section {name!r}")
    orig = os.path.basename(src).split("-", 1)[1]
    p = _path(orig, directory)
    if os.path.exists(p):
        _retire(p)
    shutil.move(src, p)
    return {"ok": True, "file": orig}


def reset(file: str, directory: Optional[str] = None) -> dict:
    """Back to the template's text for this section (the current one retired first)."""
    tpl = _template_text(file)
    if tpl is None:
        raise SectionError(f"the template has no {file}")
    p = _path(file, directory)
    if os.path.exists(p):
        _retire(p)
    _write(p, tpl if tpl.endswith("\n") else tpl + "\n")
    return {"ok": True, "file": file}


def missing_from_template(directory: Optional[str] = None) -> List[dict]:
    """Template sections this persona does not have (and has not retired): offered as
    'add back' — a new feature's fragment reaches an existing companion this way."""
    t = template_dir()
    if not t:
        return []
    have = {r["file"] for r in PL.plan(directory=_dir(directory))}
    gone = {r["file"] for r in retired(directory)}
    out = []
    for f in sorted(os.listdir(t)):
        if f.endswith(".md") and f not in have and f not in gone:
            title, _x = split(PL.parse_fragment(_template_text(f) or "")[1])
            out.append({"file": f, "title": title or f[:-3]})
    return out


def add_from_template(file: str, directory: Optional[str] = None) -> dict:
    tpl = _template_text(file)
    if tpl is None:
        raise SectionError(f"the template has no {file}")
    p = _path(file, directory)
    if os.path.exists(p):
        raise SectionError(f"{file} is already in her persona")
    _write(p, tpl if tpl.endswith("\n") else tpl + "\n")
    return {"ok": True, "file": file}
