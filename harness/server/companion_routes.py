"""companion_routes — the gateway side of the Companion window (2026-11-26).

Plain functions returning `(status, response)`, like launch_routes: app.py only dispatches.

    GET  /v1/companion              who she is, the other homes, bundles, what is pending,
                                    the change history, and what each part holds
    POST /v1/companion/export       {parts}            -> a bundle of THIS home (live is fine)
    POST /v1/companion/schedule     {op, parts, bundle} -> reset / load / undo AT NEXT START
    POST /v1/companion/cancel       {}                 -> drop what was scheduled (kept on disk)
    POST /v1/companion/new          {bundle, id, name} -> a NEW companion from a bundle
    GET  /v1/companion/bundle?name= the file, to save
    POST /v1/companion/upload?name= a .kairos, streamed to the bundle folder, then checked

THIS GATEWAY NEVER CHANGES ITS OWN HOME. It has her registry open; moving it would be
corruption. A reset or load from the room is SCHEDULED, and the room then bounces the
gateway: serve.py applies it between the old gateway's exit and the new one's start
(`serve.apply_pending_home`). Making a NEW companion touches nothing that is open, so it
runs now.
"""
from __future__ import annotations

import os
import re
from typing import Tuple

from harness import bundle as B
from harness import home as H
from harness.store_io import replace_atomic

PART_INFO = {
    "personality": "who she is — her persona and its fragments, her journal and self-model, "
                   "her own-time notes, and her settings",
    "history": "what you have lived together — every remembered fact, the conversations, "
               "the board, the plan, the shared files",
    "working": "receipts and logs — research, consult, the room's sense log, telemetry, games",
    "face": "her pictures and wardrobe",
    "episodes": "her KV snapshots — large and tied to this engine and model; never moved",
}
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
UPLOAD_MAX = int(os.environ.get("SP_BUNDLE_MAX_BYTES", str(8 * 1024 ** 3)))


def _err(code: int, msg: str):
    return code, {"ok": False, "error": msg}


def get_state() -> Tuple[int, dict]:
    home = H.current()
    cur = None
    if home:
        try:
            comp = H.read(home)["companion"]
            cur = {"id": comp["id"], "name": comp.get("name") or comp["id"], "home": home}
        except (H.HomeError, OSError) as e:
            cur = {"error": str(e), "home": home}
    homes = H.list_homes()
    # A home outside companions/ (any folder --companion= named) is still the one running:
    # list it, or the window shows every companion but the one you are talking to.
    if cur and not cur.get("error") and not any(
            os.path.normcase(os.path.normpath(h["dir"])) == os.path.normcase(os.path.normpath(home))
            for h in homes):
        homes.insert(0, {"id": cur["id"], "name": cur["name"], "dir": home})
    for h in homes:
        h["live"] = bool(not h.get("error") and H.is_live(h["dir"]))
        h["current"] = bool(home and os.path.normcase(os.path.normpath(h["dir"])) ==
                            os.path.normcase(os.path.normpath(home)))
    return 200, {
        "ok": True, "current": cur, "homes": homes,
        "bundles": B.listing()[:40], "bundle_dir": B.bundle_dir(),
        "pending": B.pending(home) if home else None,
        "history": list(reversed(B.history(home)))[:20] if home else [],
        "voices": __import__("harness.companion_create", fromlist=["x"]).XAI_VOICES,
        "suggested_voice": __import__("harness.companion_create", fromlist=["x"]).pick_voice(),
        "parts": [{"id": p, "about": PART_INFO[p], "default": p in B.DEFAULT_EXPORT,
                   "changeable": p in B.CHANGEABLE} for p in B.PARTS],
        "no_home": "" if home else ("this launch has no companion home (its profile has no "
                                     "[companion] home), so there is nothing to export or reset"),
    }


def post_export(body: dict):
    home = H.current()
    if not home:
        return _err(400, "this launch has no companion home")
    try:
        return 200, B.export(home, body.get("parts") or B.DEFAULT_EXPORT)
    except (B.BundleError, H.HomeError, OSError) as e:
        return _err(400, str(e))


def post_schedule(body: dict):
    home = H.current()
    if not home:
        return _err(400, "this launch has no companion home")
    op = str(body.get("op") or "")
    try:
        bundle = B.resolve_name(body["bundle"]) if op == "load" else ""
        return 200, B.schedule(home, op, body.get("parts") or [], bundle)
    except (B.BundleError, KeyError) as e:
        return _err(400, str(e) or "name a bundle")


def post_cancel(_body: dict):
    home = H.current()
    if not home:
        return _err(400, "this launch has no companion home")
    return 200, B.cancel(home)


def post_new(body: dict):
    cid = str(body.get("id") or "").strip().lower()
    if not _ID.match(cid):
        return _err(400, "a companion id is lower-case letters, digits, - and _ (up to 40)")
    try:
        return 200, B.import_new(B.resolve_name(str(body.get("bundle") or "")), cid,
                                 str(body.get("name") or "").strip())
    except (B.BundleError, H.HomeError, OSError) as e:
        return _err(400, str(e))


def post_create(body: dict):
    """A NEW companion from nothing: named persona, the default face and wardrobe, her own
    voice (harness/companion_create.py). Touches nothing that is open, so it runs now."""
    cid = str(body.get("id") or "").strip().lower()
    if not _ID.match(cid):
        return _err(400, "a companion id is lower-case letters, digits, - and _ (up to 40)")
    from harness import companion_create as CC
    try:
        return 200, CC.create(cid, str(body.get("name") or "").strip(), voice=str(body.get("voice") or ""))
    except (H.HomeError, OSError) as e:
        return _err(400, str(e))


def bundle_path(name: str) -> str:
    """The file behind GET /v1/companion/bundle — '' when it is not a bundle we hold."""
    try:
        p = B.resolve_name(name)
    except B.BundleError:
        return ""
    return p if os.path.isfile(p) else ""


def upload(name: str, length: int, read) -> Tuple[int, dict]:
    """Stream a .kairos into the bundle folder, then inspect it. A file that fails the
    check is kept as <name>.rejected beside the others (nothing is thrown away) and refused."""
    name = os.path.basename(name or "")
    if not name.endswith(B.EXT) or not re.match(r"^[\w.\- ]+$", name):
        return _err(400, "upload a .kairos file")
    if length <= 0 or length > UPLOAD_MAX:
        return _err(413, "that file is larger than the bundle limit")
    os.makedirs(B.bundle_dir(), exist_ok=True)
    final = os.path.join(B.bundle_dir(), name)
    if os.path.exists(final):
        return _err(409, f"{name} is already in the bundle folder")
    part = final + ".part"
    left = length
    with open(part, "wb") as f:
        while left > 0:
            chunk = read(min(1 << 20, left))
            if not chunk:
                break
            f.write(chunk)
            left -= len(chunk)
    if left:
        replace_atomic(part, final + ".rejected")
        return _err(400, "the upload stopped before the end")
    try:
        man = B.inspect(part)
    except B.BundleError as e:
        replace_atomic(part, final + ".rejected")
        return _err(400, str(e))
    replace_atomic(part, final)
    return 200, {"ok": True, "name": name, "companion": man["companion"], "parts": man["parts"]}
