"""setup_routes — the Get set up window (2026-11-26, design §4; harness/setup/installer.py).

    GET  /v1/setup/kit        the kits, this machine, a suggestion, the job's state
    POST /v1/setup/plan       {model, engine, dest} -> files, sizes, hashes (live catalogues)
    POST /v1/setup/start      {licence_ok} -> downloads begin in the background
    POST /v1/setup/cancel
    POST /v1/setup/approve    {sha256} -> the engine executable (then its transcoder) may run
    POST /v1/setup/convert    {} -> GGUF -> .sp for her native engine, in the background
    POST /v1/setup/profile    {name, companion, user_name, user_pronouns, base_url}

The plan is kept in memory between /plan and /start, so the browser never sends back URLs
or paths for the gateway to fetch or write — it can only start the plan it was shown.
"""
from __future__ import annotations

import os

from harness.setup import installer as I
from harness.setup.net import CatalogueError

_PLAN = {"p": None}


def _err(code, msg):
    return code, {"ok": False, "error": msg}


def get_kit():
    k = I.kits()
    hw = I.hardware()
    st = I.status()
    p = _PLAN["p"] or (st.get("plan") if isinstance(st.get("plan"), dict) else None)
    appr = I.pending_approval(p) if p and st.get("finished") else None
    conv = {"needed": bool(p and st.get("finished") and I.needs_convert(p)),
            "running": bool(st.get("converting") and st.get("running")),
            "error": st.get("convert_error") or "", "to": I.sp_paths(p)[1] if I.native(p) else ""}
    return 200, {"ok": True, "models": k["models"], "engines": k["engines"], "licences": k["licences"],
                 "warning": k["uncensored_warning"], "hardware": hw, "suggest": I.suggest(hw),
                 "default_dest": os.path.join(I.H.ROOT, "data"), "state": st, "plan": p,
                 "approval": appr, "convert": conv, "transcoder": bool(I.transcoder(p))}


def post_plan(body: dict):
    dest = str(body.get("dest") or "").strip()
    if not dest or not os.path.isabs(dest):
        return _err(400, "choose a folder (a full path) for the downloads")
    try:
        os.makedirs(dest, exist_ok=True)
        reuse = [d for d in str(body.get("reuse") or "").split(";") if d.strip()] or None
        p = I.plan(str(body.get("model") or ""), str(body.get("engine") or ""), dest, reuse=reuse)
    except (I.SetupError, CatalogueError, OSError) as e:
        return _err(400, str(e))
    _PLAN["p"] = p
    return 200, {"ok": True, "plan": p}


def post_start(body: dict):
    if not _PLAN["p"]:
        return _err(400, "make a plan first")
    try:
        return 200, I.start(_PLAN["p"], licence_ok=bool(body.get("licence_ok")))
    except I.SetupError as e:
        return _err(400, str(e))


def post_cancel(_body: dict):
    return 200, I.cancel()


def post_approve(body: dict):
    try:
        return 200, I.approve(str(body.get("sha256") or ""))
    except I.SetupError as e:
        return _err(400, str(e))


def post_convert(_body: dict):
    p = _PLAN["p"] or I.status().get("plan")
    if not p:
        return _err(400, "make a plan first")
    try:
        return 200, I.start_convert(p)
    except I.SetupError as e:
        return _err(400, str(e))


def post_profile(body: dict):
    p = _PLAN["p"] or I.status().get("plan") or {"engine": "external", "items": []}
    if p.get("items") and I.pending_approval(p):
        return _err(400, "approve the engine first")
    if I.needs_convert(p):
        return _err(400, "convert her model for the native engine first")
    try:
        path = I.write_profile(str(body.get("name") or ""), p, companion=str(body.get("companion") or ""),
                               user_name=str(body.get("user_name") or ""),
                               user_pronouns=str(body.get("user_pronouns") or ""),
                               base_url=str(body.get("base_url") or ""))
    except I.SetupError as e:
        return _err(400, str(e))
    name = os.path.basename(path)[:-5]
    comp = str(body.get("companion") or "")
    return 200, {"ok": True, "profile": name, "path": path,
                 "start": "kairos.bat start --profile=%s%s" % (name, (" --companion=" + comp) if comp else "")}
