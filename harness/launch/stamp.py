"""stamp — what she was launched with, and the 8-hex fingerprint on every reply.

serve.py calls `write_launched` at each full launch; the gateway calls `current_stamp` per
reply. The fingerprint covers the env as launched plus the live tuning overrides, so a
reply says which configuration produced it even after a knob moved without a restart.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time

from harness.launch import var_dir
from harness.store_io import replace_atomic

# A key's VALUE must never reach disk; a key FILE (a path that exists, or a value that ends
# in an extension) is a configuration fact and is kept.
_SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)", re.I)
_EXT = re.compile(r"\.[A-Za-z0-9]{1,8}$")


def redact(env: dict) -> dict:
    out = {}
    for k, v in (env or {}).items():
        v = "" if v is None else str(v)
        if _SECRET_NAME.search(str(k)) and not (os.path.exists(v) or _EXT.search(v)):
            continue
        out[str(k)] = v
    return out


def launched_path() -> str:
    return os.path.join(var_dir(), "launched.json")


def _fp_path() -> str:
    return os.path.join(var_dir(), "config-fingerprints.jsonl")


def _flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in d.items():
        if str(k).startswith("_"):
            continue
        key = prefix + str(k)
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def fingerprint(env: dict, overrides: dict) -> str:
    blob = json.dumps({"env": env, "tune": overrides}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:8]


def _overrides() -> dict:
    from harness.tuning import registry
    return registry._load()


def write_launched(profile: dict, env: dict, setup: str) -> dict:
    env = redact(env)
    rec = {
        "profile": profile.get("_profile_name", ""),
        "setup": setup,
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "values": _flatten(profile),
        "env": env,
        "fingerprint": fingerprint(env, _overrides()),
    }
    path = launched_path()
    prev = read_launched()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1, sort_keys=True, default=str)
    replace_atomic(tmp, path)
    # A RESTART IS A SETTINGS CHANGE (spec): old = the fingerprint she ran on, new = this one.
    from harness.launch import changes
    changes.log("launch", "restart", (prev or {}).get("fingerprint"), rec["fingerprint"],
                setup=setup)
    return rec


def read_launched():
    try:
        with open(launched_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


_SEEN = None      # fingerprints already in the store; None until the first scan


def remember(fp: str, env: dict, overrides: dict) -> None:
    global _SEEN
    path = _fp_path()
    if _SEEN is None:
        _SEEN = set()
        try:
            with open(path, encoding="utf-8") as f:
                for ln in f:
                    try:
                        _SEEN.add(json.loads(ln)["fp"])
                    except (ValueError, KeyError, TypeError):
                        pass
        except OSError:
            pass
    if fp in _SEEN:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"fp": fp, "env": env, "tune": overrides,
                            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
                           sort_keys=True, default=str) + "\n")
    _SEEN.add(fp)


def current_stamp() -> dict:
    rec = read_launched()
    if rec is not None:
        setup, env = rec.get("setup") or "unknown", rec.get("env") or {}
    else:
        setup = "unknown"
        env = redact({k: v for k, v in os.environ.items() if k.startswith("SP_")})
    ov = _overrides()
    fp = fingerprint(env, ov)
    remember(fp, env, ov)
    return {"setup": setup, "cfg": fp}
