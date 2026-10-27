"""setups — named sets of profile values, kept as key -> value diffs.

A setup is `var/launch-setups/<slug>.json` = {"name", "values": {"section.key": v}}. Loading
one is two steps on purpose: `resolve` says which edits it means for the CURRENT profile
(and which keys the profile no longer has); the caller applies them through profile_doc.
The model is stored as a FILENAME so a setup survives the models directory moving.
"""
from __future__ import annotations

import json
import os
import re

from harness.launch import var_dir
from harness.store_io import replace_atomic

_NAME = re.compile(r"^[A-Za-z0-9 ,._-]{1,60}$")
_MODEL = "paths.model"


def _dir() -> str:
    return os.path.join(var_dir(), "launch-setups")


def _check_name(name) -> str:
    if not isinstance(name, str) or not _NAME.match(name):
        raise ValueError("setup name must be 1-60 of letters, digits, space , . _ -")
    return name


def _slug(name: str) -> str:
    s = re.sub(r"[ ,]", "-", name.lower())
    s = re.sub(r"[^a-z0-9._-]", "", s)
    return re.sub(r"-{2,}", "-", s).strip("-") or "setup"


def _path(name: str) -> str:
    return os.path.join(_dir(), _slug(_check_name(name)) + ".json")


def _base(p) -> str:
    return str(p).replace("\\", "/").rsplit("/", 1)[-1]


def _write(name: str, values: dict) -> None:
    path = _path(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"name": name, "values": values}, f, indent=1, sort_keys=True)
    replace_atomic(tmp, path)


def _load(name: str) -> dict:
    try:
        with open(_path(name), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        raise KeyError(name)
    if not isinstance(d, dict) or not isinstance(d.get("values"), dict):
        raise KeyError(name)
    return d


def _same(key: str, mine, theirs) -> bool:
    if key == _MODEL:
        return _base(mine) == _base(theirs)
    return mine == theirs


def list_all(profile: str) -> list:
    from harness.launch import stamp
    rec = stamp.read_launched()
    live = (rec or {}).get("values") if rec else None
    out = []
    try:
        names = sorted(os.listdir(_dir()))
    except OSError:
        return []
    for fn in names:
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(_dir(), fn), encoding="utf-8") as f:
                d = json.load(f)
            name, values = d["name"], d["values"]
            if not isinstance(name, str) or not isinstance(values, dict):
                continue
        except (OSError, ValueError, KeyError, TypeError):
            continue
        # An empty setup matches everything vacuously; it is not "running".
        running = bool(live is not None and values and all(
            k in live and _same(k, v, live[k]) for k, v in values.items()))
        out.append({"name": name, "values": values, "running": running})
    return out


def save(name: str, values: dict) -> None:
    _check_name(name)
    # TWO NAMES CAN SHARE A SLUG ("Fast split" / "Fast, split"; "Old" / "old"), and a save
    # onto the other's file would silently replace a DIFFERENT setup. Same name = update.
    try:
        with open(_path(name), encoding="utf-8") as f:
            held = json.load(f).get("name")
    except (OSError, ValueError, AttributeError):
        held = None
    if held is not None and held != name:
        raise ValueError("a setup named %r already uses that file name" % held)
    vals = dict(values or {})
    if _MODEL in vals and vals[_MODEL] is not None:
        vals[_MODEL] = _base(vals[_MODEL])
    _write(name, vals)


def delete(name: str) -> None:
    _load(name)
    os.remove(_path(name))


def rename(old: str, new: str) -> None:
    d = _load(old)
    _check_name(new)
    if os.path.exists(_path(new)):
        raise ValueError("a setup named %r already exists" % new)
    _write(new, d["values"])
    if _path(new) != _path(old):
        os.remove(_path(old))


def resolve(profile: str, name: str) -> dict:
    from harness.launch import profile_doc
    values = _load(name)["values"]
    cur = profile_doc.read(profile)["values"]
    edits, skipped = {}, []
    for k, v in values.items():
        if k not in cur:
            skipped.append(k)
            continue
        if k == _MODEL:
            # Swap ONLY the basename inside the current string: its directory text and
            # separator stay as written (os.path.join put a backslash into a '/' path).
            s = str(cur[k])
            cut = max(s.rfind("/"), s.rfind("\\"))
            v = s[:cut + 1] + _base(v) if cut >= 0 else _base(v)
        edits[k] = v
    return {"edits": edits, "skipped": skipped}
