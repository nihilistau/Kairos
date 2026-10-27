"""profile_doc — read and edit a profile toml without eating its comments.

The profile is hand-annotated (commented-out alternatives, a note on every kernel knob), and
a round-trip through a plain dict would drop all of it. So edits go through tomlkit, which
keeps the document's text and changes only the value being assigned.

Structured edits (`apply`) change EXISTING keys only; a new key goes through `save_raw`,
validated as toml. Every write carries the hash of the file it was loaded from, so a file
edited by hand in between is refused rather than overwritten.
"""
from __future__ import annotations

import hashlib
import os
import tomllib

import tomlkit
from tomlkit.items import String, StringType

try:
    from harness.store_io import replace_atomic
except Exception:                      # pragma: no cover - store_io is always present in-tree
    replace_atomic = os.replace

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class StaleError(Exception):
    """The file changed since it was loaded."""


def profile_path(name: str) -> str:
    base = os.environ.get("SP_LAUNCH_PROFILES_DIR") or os.path.join(_ROOT, "profiles")
    return os.path.join(base, name + ".toml")


def _load_bytes(name: str) -> bytes:
    with open(profile_path(name), "rb") as f:
        return f.read()


def _hash(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _comment_of(item) -> str:
    c = getattr(getattr(item, "trivia", None), "comment", "") or ""
    return c.lstrip("#").strip()


def _read_bytes(b: bytes) -> dict:
    text = b.decode("utf-8")
    doc = tomlkit.parse(text)
    values, help_ = {}, {}
    for k in doc:
        v = doc[k]
        if isinstance(v, dict):
            for kk in v:
                values[k + "." + kk] = v[kk].unwrap() if hasattr(v[kk], "unwrap") else v[kk]
                c = _comment_of(v.item(kk)) if hasattr(v, "item") else ""
                if c:
                    help_[k + "." + kk] = c
        else:
            values[k] = v.unwrap() if hasattr(v, "unwrap") else v
            c = _comment_of(doc.item(k))
            if c:
                help_[k] = c
    return {"text": text, "hash": _hash(b), "values": values, "help": help_}


def read(name: str) -> dict:
    return _read_bytes(_load_bytes(name))


def _coerce(existing, value, key: str):
    """Make `value` the type of the key it replaces (bool before int: bool is an int)."""
    cur = existing.unwrap() if hasattr(existing, "unwrap") else existing
    try:
        if isinstance(cur, bool):
            if isinstance(value, str):
                s = value.strip().lower()
                if s in ("true", "1", "yes", "on"):
                    return True
                if s in ("false", "0", "no", "off"):
                    return False
                raise ValueError(s)
            return bool(value)
        if isinstance(cur, int):
            if isinstance(value, float) and value != int(value):
                raise ValueError(value)
            return int(value if not isinstance(value, str) else value.strip())
        if isinstance(cur, float):
            return float(value)
        if isinstance(cur, str):
            if not isinstance(value, str):
                raise ValueError(value)
            return value
        if isinstance(cur, list):
            # A list key takes a list: the string an unparsed edit arrives as would
            # otherwise replace it and quietly turn a list into text.
            if not isinstance(value, list):
                raise ValueError(value)
            return value
        if isinstance(cur, dict):
            if not isinstance(value, dict):
                raise ValueError(value)
            return value
    except (ValueError, TypeError):
        pass
    else:
        return value
    raise ValueError("%s: %r cannot take the type of the existing value (%s)"
                     % (key, value, type(cur).__name__))


def _write(name: str, data: bytes) -> dict:
    path = profile_path(name)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    replace_atomic(tmp, path)
    return _read_bytes(data)


def _check_fresh(name: str, base_hash: str) -> bytes:
    cur = _load_bytes(name)
    if _hash(cur) != base_hash:
        raise StaleError("the file changed — reload")
    return cur


def apply(name: str, edits: dict, base_hash: str) -> dict:
    cur = _check_fresh(name, base_hash)
    doc = tomlkit.parse(cur.decode("utf-8"))
    missing = []
    for key in edits:
        sec, _, k = key.rpartition(".")
        tbl = doc.get(sec) if sec else doc
        if not isinstance(tbl, dict) or k not in tbl:
            missing.append(key)
    if missing:
        raise KeyError("not in the profile: " + ", ".join(missing))
    for key, value in edits.items():
        sec, _, k = key.rpartition(".")
        tbl = doc[sec] if sec else doc
        new = _coerce(tbl[k], value, key)
        # A literal-quoted value stays literal: tomlkit's default would rewrite '...' as
        # "..." with escapes, changing more than the edited value's text.
        if (isinstance(new, str) and "'" not in new and "\n" not in new
                and isinstance(tbl[k], String)
                and tbl[k].type == StringType.SLL):
            new = tomlkit.string(new, literal=True)
        tbl[k] = new
    return _write(name, tomlkit.dumps(doc).encode("utf-8"))


def save_raw(name: str, text: str, base_hash: str) -> dict:
    _check_fresh(name, base_hash)
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(str(e)) from None
    return _write(name, text.encode("utf-8"))
