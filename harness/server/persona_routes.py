"""persona_routes — the Persona window and the Character window (2026-11-26, design §7b).

    GET  /v1/persona/sections      her persona as titled sections, the retired ones, the
                                   template sections she lacks, and good practice
    POST /v1/persona/sections      {op: save|add|reorder|retire|restore|reset|add_template, ...}
    GET  /v1/character/flow        the creation flow (questions, hints, examples)
    POST /v1/character/preview     {answers} -> the sections they would make
    POST /v1/character/create      {answers, id, voice} -> a NEW companion from the flow
    POST /v1/character/apply       {answers} -> the flow's sections into THIS companion

Every write retires what it replaces (sections.py); every reply that changed her persona
says it applies from her next session, because her prefix is cached until then.
"""
from __future__ import annotations

import re

from harness.personality import character as C
from harness.personality import sections as S

NEXT = "saved — she reads it from her next session (her prefix is cached until then)"
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


def _err(code, msg):
    return code, {"ok": False, "error": msg}


def get_sections():
    try:
        return 200, {"ok": True, "sections": S.list_sections(), "retired": S.retired()[:30],
                     "missing": S.missing_from_template(),
                     "good_practice": C.flow().get("good_practice", [])}
    except Exception as e:                 # a broken persona folder is shown, not hidden
        return 500, {"ok": False, "error": str(e)}


def post_sections(body: dict):
    op = str(body.get("op") or "")
    try:
        if op == "save":
            r = S.save(str(body.get("file") or ""), str(body.get("title") or ""), str(body.get("text") or ""))
        elif op == "add":
            r = S.add(str(body.get("title") or ""), str(body.get("text") or ""),
                      order=int(body.get("order") or 500))
        elif op == "reorder":
            r = S.reorder([str(f) for f in body.get("files") or []])
        elif op == "retire":
            r = S.retire(str(body.get("file") or ""))
        elif op == "restore":
            r = S.restore(str(body.get("name") or ""))
        elif op == "reset":
            r = S.reset(str(body.get("file") or ""))
        elif op == "add_template":
            r = S.add_from_template(str(body.get("file") or ""))
        else:
            return _err(400, "op must be save, add, reorder, retire, restore, reset or add_template")
    except (S.SectionError, ValueError, OSError) as e:
        return _err(400, str(e))
    return 200, {**r, "note": NEXT}


def get_flow():
    from harness import companion_create as CC
    f = C.flow()
    f["voices"] = {"xai": CC.XAI_VOICES, "lfm3": CC.LFM3_VOICES, "suggested_xai": CC.pick_voice()}
    return 200, {"ok": True, **f}


def post_preview(body: dict):
    return 200, {"ok": True, "sections": C.preview(body.get("answers") or {})}


def post_create(body: dict):
    from harness import home as H
    cid = str(body.get("id") or "").strip().lower()
    if not _ID.match(cid):
        return _err(400, "a companion id is lower-case letters, digits, - and _ (up to 40)")
    try:
        return 200, C.create(body.get("answers") or {}, cid, voice=str(body.get("voice") or ""))
    except (H.HomeError, S.SectionError, OSError) as e:
        return _err(400, str(e))


def post_apply(body: dict):
    try:
        return 200, C.apply(body.get("answers") or {})
    except (S.SectionError, OSError) as e:
        return _err(400, str(e))
