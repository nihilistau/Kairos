"""launch_routes — the gateway side of the Launch window.

Plain functions: each takes the request body (a dict) and returns `(status, response)`.
app.py only dispatches to them and writes the JSON, so the gate calls them directly and the
route table in app.py stays small. Errors are `{"ok": false, "error": str}`: 400 for a bad
request, 409 for a stale file or a mid-turn restart.

`loaded` — which saved setup was last applied to the profile and not touched since — lives
in this module, mirrored to `var/launch-loaded.json` so a gateway bounce does not forget it.
`_do_restart` hands it to serve.py as SP_LAUNCH_SETUP, which is how a reply later says which
setup produced it.
"""
from __future__ import annotations

import json
import os
import re

from harness.launch import changes, setups, stamp, var_dir
from harness.loud import swallowed as _swallowed
from harness.observability import get_logger
from harness.store_io import replace_atomic

logger = get_logger(__name__)

# tomlkit IS OPTIONAL (extra `launch`), AND THE PATHS THAT MUST NOT NEED IT RUN THROUGH THIS
# MODULE: restart_refusal, the loaded-setup state, get_status, and (via app.py) every knob
# write. So profile_doc, the one importer of tomlkit, is imported guarded: without it the
# profile handlers answer 503 with the install line and nothing else changes.
profile_doc = None                               # stays None when tomlkit is absent
try:
    from harness.launch import profile_doc
except ImportError:
    pass

NEEDS_TOMLKIT = 'the Launch window needs tomlkit — pip install -e ".[launch]"'

_PROFILE = re.compile(r"^[A-Za-z0-9_-]+$")

# (key, label, tag, kind). The four kernels carry the tag that says what flipping them does
# to her wording; the rest are plain.
_NEAR = "changes wording at near-ties"
_SAME = "bit-identical"
CONTROLS = [
    ("paths.model", "Model", "", "model"),
    ("decode.attn_split", "Split-K decode attention", _NEAR, "bool01"),
    ("decode.attn_prefill_gemm", "GEMM prefill attention", _NEAR, "bool01"),
    ("decode.dequant_h8", "Eight-wide dequant", _SAME, "bool01"),
    ("decode.moe_overlap_prefill", "Prefill copy overlap", _SAME, "bool"),
    ("kv.moe_cache_gb", "Expert cache (GB)", "", "float"),
    ("decode.moe_cpu_threads", "CPU expert threads", "", "int"),
    ("decode.moe_pf_lane", "Prefill lane (slots)", "", "int"),
]
COST = {"same_model": "about 1–2 min",
        "model_change": "cold persona load, about 2–5 min"}

_LOADED = {"v": None, "read": False}


def _err(code: int, msg: str):
    return code, {"ok": False, "error": msg}


def _no_toml():
    return _err(503, NEEDS_TOMLKIT) if profile_doc is None else None


def _loaded_path() -> str:
    return os.path.join(var_dir(), "launch-loaded.json")


def get_loaded():
    if not _LOADED["read"]:
        _LOADED["read"] = True
        try:
            with open(_loaded_path(), encoding="utf-8") as f:
                v = json.load(f).get("loaded")
            _LOADED["v"] = v if isinstance(v, str) and v else None
        except (OSError, ValueError, AttributeError):
            _LOADED["v"] = None
    return _LOADED["v"]


def set_loaded(name) -> None:
    _LOADED["v"], _LOADED["read"] = name, True
    try:
        path = _loaded_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"loaded": name}, f)
        replace_atomic(tmp, path)
    except OSError as _swx:
        _swallowed(logger, "set_loaded", _swx, lane="server")   # the in-memory value still serves


def profile_name():
    """-> (name, None) or (None, (status, response)). The name comes from the running
    stack; it is checked here because it becomes a path component."""
    from harness.server import app
    name = (app._system_profile() or "").strip()
    if not name:
        return None, _err(400, "cannot tell which profile this stack uses")
    if not _PROFILE.match(name):
        return None, _err(400, "profile name is not a plain name")
    return name, None


def _models(values: dict) -> list:
    cur = values.get("paths.model")
    if not cur:
        return []
    d = os.path.dirname(str(cur).replace("\\", "/"))
    try:
        return sorted(f for f in os.listdir(d or ".") if f.endswith(".sp-model"))
    except OSError:
        return []


def get_launch(_body=None):
    if profile_doc is None:
        return _no_toml()
    name, bad = profile_name()
    if bad:
        return bad
    try:
        doc = profile_doc.read(name)
    except (OSError, ValueError) as e:
        return _err(400, "cannot read the profile: %s" % e)
    return 200, {
        "ok": True, "profile": name, "doc": doc, "launched": stamp.read_launched(),
        "controls": [{"key": k, "label": lb, "tag": tg, "kind": kd}
                     for k, lb, tg, kd in CONTROLS if k in doc["values"]],
        "models": _models(doc["values"]), "setups": setups.list_all(name),
        "loaded": get_loaded(), "cost": dict(COST),
    }


def _mark_edited() -> None:
    cur = get_loaded()
    if cur and not cur.endswith(" (edited)"):
        set_loaded(cur + " (edited)")


def _apply(name: str, edits: dict, base_hash: str, source: str = "launch"):
    old = profile_doc.read(name)["values"]
    doc = profile_doc.apply(name, edits, base_hash)
    for k, v in edits.items():
        changes.log(source, k, old.get(k), doc["values"].get(k, v))
    return doc


def _guarded(fn):
    try:
        return fn()
    except profile_doc.StaleError as e:
        return _err(409, str(e))
    except KeyError as e:
        return _err(400, str(e.args[0]) if e.args else "unknown key")
    except (ValueError, TypeError, OSError) as e:
        return _err(400, str(e))


def post_edit(body):
    if profile_doc is None:
        return _no_toml()
    name, bad = profile_name()
    if bad:
        return bad
    edits = body.get("edits")
    if not isinstance(edits, dict) or not edits:
        return _err(400, "edits must be a non-empty object")

    def go():
        doc = _apply(name, edits, str(body.get("base_hash") or ""))
        _mark_edited()
        return 200, {"ok": True, "doc": doc}
    return _guarded(go)


def post_raw(body):
    if profile_doc is None:
        return _no_toml()
    name, bad = profile_name()
    if bad:
        return bad
    text = body.get("text")
    if not isinstance(text, str):
        return _err(400, "text must be a string")

    def go():
        old = profile_doc.read(name)["hash"]
        doc = profile_doc.save_raw(name, text, str(body.get("base_hash") or ""))
        # THE HASHES, NOT THE FILE: a whole profile as old/new made every raw save a
        # 2x-profile-sized line in a log that is meant to be skimmed.
        changes.log("launch", "profile (raw)", old, doc["hash"])
        _mark_edited()
        return 200, {"ok": True, "doc": doc}
    return _guarded(go)


def post_setup(body):
    if profile_doc is None:
        return _no_toml()
    name, bad = profile_name()
    if bad:
        return bad
    op, sname = str(body.get("op") or ""), body.get("name")

    def go():
        if op == "save":
            vals = body.get("values")
            if vals is None:                       # snapshot the labelled controls as they are
                cur = profile_doc.read(name)["values"]
                vals = {k: cur[k] for k, *_ in CONTROLS if k in cur}
            if not isinstance(vals, dict):
                return _err(400, "values must be an object")
            setups.save(sname, vals)
            return 200, {"ok": True, "setups": setups.list_all(name)}
        if op == "delete":
            setups.delete(sname)
            if get_loaded() in (sname, "%s (edited)" % sname):
                set_loaded(None)
            return 200, {"ok": True, "setups": setups.list_all(name)}
        if op == "rename":
            setups.rename(sname, str(body.get("new") or ""))
            if get_loaded() == sname:
                set_loaded(str(body["new"]))
            return 200, {"ok": True, "setups": setups.list_all(name)}
        if op == "load":
            r = setups.resolve(name, sname)
            cur = profile_doc.read(name)
            bh = str(body.get("base_hash") or "")
            if bh != cur["hash"]:       # a load is a save: it carries the hash it was shown
                return _err(409, "the file changed — reload")
            doc = _apply(name, r["edits"], bh, "launch (setup %s)" % sname) \
                if r["edits"] else cur
            set_loaded(sname)
            return 200, {"ok": True, "doc": doc, "skipped": r["skipped"]}
        return _err(400, "op must be save, delete, rename or load")

    return _guarded(go)


def get_status(_body=None):
    rec = stamp.read_launched() or {}
    tail = []
    try:
        with open(os.path.join(var_dir(), "serve-restart.log"), encoding="utf-8",
                  errors="replace") as f:
            tail = [ln.rstrip("\n") for ln in f.readlines()[-20:]]
    except OSError:
        pass
    try:
        cur = stamp.current_stamp()           # what a live reply finishing now would wear
    except Exception as _swx:
        _swallowed(logger, "get_status", _swx, lane="server")
        cur = {}
    return 200, {"ok": True, "launched_at": rec.get("at"),
                 "fingerprint": rec.get("fingerprint"), "log_tail": tail,
                 "setup": cur.get("setup"), "cfg": cur.get("cfg")}


def restart_refusal():
    """-> None, or `(409, response)` when she is mid-turn. Asked BEFORE anything is
    spawned: a full restart cuts the turn off, and the operator should hear about it first."""
    from harness.kairos import scheduler
    busy = scheduler.in_flight()[0]
    if busy:
        return _err(409, "she's mid-turn — try again when she finishes")
    return None


def restart_env_setup() -> str:
    return get_loaded() or "custom"
