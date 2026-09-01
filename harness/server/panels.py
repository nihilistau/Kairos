"""panels.py — the room's read-only surfaces, one function per window.

Stage 2 of the app.py split (2026-09-01). Thirty-five functions, ~850 lines, lifted out of
`app.py` **byte-identically** — every one shaped `() -> Dict[str, Any]`, almost all
documented NEVER RAISES, because a panel that throws takes the window with it and the room
would rather show a stale number than a blank pane.

WHY THIS IS THE SAFE EXTRACTION and the turn lifecycle is not: these have no callers but
the route table, they share no state but what `state.py` already holds, and they answer
questions rather than change anything. The write-side siblings that were interleaved with
them in app.py — `_wardrobe_set`, `_persona_set`, `_persona_layer_write` — deliberately did
NOT come: they are route handlers, and a module called `panels` that also writes would be
the second copy of "what a panel is".

── FOUR NAMES STAYED BEHIND, AND THESE ARE THEIR DOORS ───────────────────────────────
`_persona_path`, `_roleplay_on`, `_room_session` and `_system_profile` have non-panel
callers in app.py (the epilogue reads the persona file; the chat handler and the restart
route need the others; `harness/skills/wardrobe.py` imports `_room_session` back out of the
gateway). So they stay where their other callers are, and the shims below reach them
lazily — which is app.py's own idiom, 181 function-local `from harness.…` imports, and the
reason a reverse dependency on the gateway does not become an import cycle.

The shims exist so the thirty-five bodies could move **without a single edit inside them**.
That was the point: a moved function whose text changed is a function that has to be
re-reviewed, and 850 lines of re-review is where a twin gets born.

Import order matters and is asserted by G-SRC-TRAP: this module imports `state`, never
`app`, at module level.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

from harness.loud import swallowed as _swallowed
from harness.observability import get_logger
from harness.server import state as _state

logger = get_logger(__name__)

# ── WHAT THE MOVED BODIES REFER TO ───────────────────────────────────────────────────
# Aliases onto the one place each of these lives, so the lifted text needed no edits.
# `_state.LAST_TURN_AT` is NOT aliased — it is the rebindable scalar, and `_room_pulse`
# reads it through the module for the reason state.py's docstring gives.
_ROOT_DIR = _state.ROOT_DIR
_GEN_JOB = _state.GEN_JOB
_WARM = _state.WARM


def _persona_path():
    """app.py's — the epilogue and the chat handler read the same file."""
    from harness.server import app as _app
    return _app._persona_path()


def _roleplay_on():
    from harness.server import app as _app
    return _app._roleplay_on()


def _room_session():
    """app.py's — `harness/skills/wardrobe.py` imports this one out of the gateway."""
    from harness.server import app as _app
    return _app._room_session()


def _system_profile():
    from harness.server import app as _app
    return _app._system_profile()


def _engine_info() -> Dict[str, Any]:
    """Which backend this gateway talks to, and what it can do — for the room's chips
    and the restart controls (2026-08-21, the engine-agnostic seam)."""
    try:
        from harness.inference.client import get_client
        c = get_client()
        return {"kind": getattr(c, "kind", "sp"), "base_url": getattr(c, "base_url", ""),
                "supports": sorted(getattr(c, "supports", ())),
                "model": getattr(c, "default_model", "") or os.environ.get("SP_ENGINE_MODEL", "")}
    except Exception as exc:
        return {"kind": "?", "error": str(exc)[:120]}


def _aux_json() -> Dict[str, Any]:
    """THE LIBRARIANS (2026-08-22, D): the two doors, the index, the prefixes, the models."""
    try:
        from harness.sidecar import archive as _arc, client as _cl
        st = _arc.status()
        st["models"] = _cl.list_models()
        st["ok"] = True
        return st
    except Exception as exc:
        return {"ok": False, "armed": False, "error": str(exc)[:160]}


def _presence_json() -> Dict[str, Any]:
    """PRESENCE (2026-08-22): which mode, when her next turn may come, what she is reading,
    and the shelf — for the presence window and its chip."""
    from harness.kairos import scheduler as _ks
    from harness.skills import library as _lib
    from harness.tuning import registry as _tr
    with _ks._LOCK:
        sess = next(iter(_ks._LAST), "default")
    st = (_ks.peek_state(sess) or {}).get("presence") or {}
    knobs = {}
    for k in ("presence.mode", "presence.voice", "presence.intimate", "presence.cue", "presence.read_chance"):
        try:
            knobs[k.split(".", 1)[1]] = _tr.get(k)
        except Exception as _swx:
            _swallowed(logger, "_presence_json", _swx, lane="server")
            knobs[k.split(".", 1)[1]] = None
    try:
        shelf = _lib.books()
    except Exception as _swx:
        _swallowed(logger, "_presence_json", _swx, lane="server")
        shelf = []
    return {"ok": True, "session": sess, "state": st, "shelf": shelf, "knobs": knobs}


def _system_json() -> Dict[str, Any]:
    prof = _system_profile()
    eng = _engine_info()
    # AN EXTERNAL ENGINE IS NOT THE HARNESS'S TO RESTART (2026-08-21): under the openai
    # backend the model lives in LM Studio / llama-server / a cloud; the room may only
    # bounce the GATEWAY. `restartable` says so rather than offering a button that lies.
    ext = "restart" not in (eng.get("supports") or [])
    return {"ok": True, "profile": prof or None, "engine": eng,
            "restartable": bool(prof) and not ext,
            "gateway_bounce": bool(prof),
            "note": ("this engine is external (%s) — start and stop it yourself; the "
                     "gateway can still be bounced" % eng.get("base_url", "")) if ext else
                    ("a full restart reloads the model and takes a couple of minutes; "
                     "the gateway bounce is seconds and leaves the daemon alone")}


def _avatar_rung_and_ceiling():
    """The live heat rung and the operator's ceiling, both from the systems that already
    own them — the roleplay scene if one is running, and the tuning registry. The avatar
    does not get its own idea of either."""
    rung, ceiling = 0, 7
    try:
        from harness.tuning import registry as tune
        ceiling = int(tune.get("roleplay.max_heat"))
    except Exception as _swx:
        _swallowed(logger, "_avatar_rung_and_ceiling", _swx, lane="server")
    try:
        from harness.roleplay import engine as rp
        # OFF MEANS OFF DOWNSTREAM TOO (2026-08-03). `roleplay.enabled` gated the
        # PRE-TURN — the place a scene is entered and its prompt injected — and nothing
        # else. A scene that was already running kept driving her AVATAR RUNG after the
        # feature was switched off, because this reader asked the engine "is a scene
        # active" without ever asking "is the feature on". Half a switch is not a switch.
        if _roleplay_on():
            sc = rp.active(_room_session())
            if sc is not None:
                rung = int(sc.heat.level)
    except Exception as _swx:
        _swallowed(logger, "_avatar_rung_and_ceiling", _swx, lane="server")
    return rung, ceiling


def _wardrobe_json() -> Dict[str, Any]:
    """What she is wearing, what else is hanging there, and who decided.

    (The ceiling/rung pair this used to thread through died with the tiers,
    2026-08-21 — the panel shows everything she owns, because everything she owns
    is servable.)"""
    try:
        from harness.control import wardrobe as WD
        rung, ceiling = _avatar_rung_and_ceiling()
        st = WD.status()
        st["rung"] = rung
        st["genstatus"] = dict(_GEN_JOB)
        st["describe"] = WD.describe()
        return st
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:160]}


def _avatar_json() -> Dict[str, Any]:
    try:
        from harness.control import avatar as AV
        rung, ceiling = _avatar_rung_and_ceiling()
        st = AV.status()
        st["rung"] = rung
        # Which faces can actually be shown right now, resolved through the same
        # function the file route uses — so the panel never offers what the server
        # would refuse.
        st["ready"] = sorted({r["face"] for r in AV.manifest()
                              if r["kind"] == "still" and r["have"]})
        # WHICH FACES HAVE MOTION, reported separately. The resolver degrades a missing
        # loop to the still, which is right for bytes and wrong for the client: a <video>
        # handed a PNG renders nothing at all. So the panel is told which faces it may
        # ask for as video, rather than discovering it by getting an image back.
        st["ready_loop"] = sorted({r["face"] for r in AV.manifest()
                                   if r["kind"] == "loop" and r["have"]})
        st["ok"] = True
        return st
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _setup_key(path_env: str, default_rel: str = "") -> Dict[str, Any]:
    """Is the key file there — and NOTHING about what is in it.

    THE VALUE NEVER LEAVES THIS PROCESS. The panel needs exactly three facts to guide
    somebody through setup: where the file should be, whether it exists, and whether it
    has anything in it. A length is reported because "I pasted it but it is empty" and
    "I have not made it yet" are different problems with different fixes; the bytes
    themselves are not, and a route that returned a prefix "just to help you check" is a
    route that writes your API key into a browser's network log.
    """
    rel = (os.environ.get(path_env) or default_rel or "").strip()
    if not rel:
        return {"path": "", "configured": False, "present": False, "bytes": 0}
    p = rel if os.path.isabs(rel) else os.path.join(_ROOT_DIR, rel)
    try:
        n = len(open(p, encoding="utf-8").read().strip())
    except Exception as _swx:
        _swallowed(logger, "_setup_key", _swx, lane="server")
        n = -1
    return {"path": rel.replace("\\", "/"), "configured": True,
            "present": n > 0, "bytes": max(0, n)}


def _setup_json() -> Dict[str, Any]:
    """WHAT IS SET UP AND WHAT IS NOT — the panel behind `docs/SETUP.md`.

    ONBOARDING IS A DIAGNOSIS, NOT A LEAFLET. A page of instructions cannot tell you
    which step you are on; this route can. It reports the engine actually in force, each
    optional key as present/absent, whether the sidecars answer, and whether the room
    has a face — so the panel says "your endpoint is not answering on :1234" rather than
    "check that your endpoint is running".

    IT READS, IT NEVER WRITES. Nothing here arms a knob or creates a file: a setup
    surface that could turn things on would need an authority story, and the profile
    plus the settings registry already own that. It is a mirror.
    """
    out: Dict[str, Any] = {"ok": True, "root": _ROOT_DIR.replace("\\", "/")}
    out["profile"] = os.environ.get("SP_PROFILE", "") or ""
    # THE RECOMMENDED MODELS COME FROM THE FILE, not from a copy in the panel. Two
    # lists of model ids is the duplicate that goes stale silently — the one nobody
    # re-checks is the one somebody follows (AGENTS.md §0).
    try:
        with open(os.path.join(_ROOT_DIR, "config", "models.json"), encoding="utf-8") as f:
            out["models"] = json.load(f)
    except Exception as exc:
        out["models"] = {"error": str(exc)[:160]}
    # ── THE ENGINE, AND WHETHER IT IS ACTUALLY THERE ────────────────────────────────
    eng = _engine_info()
    eng["dialect"] = os.environ.get("SP_ENGINE_DIALECT", "generic")
    eng["vision"] = (os.environ.get("SP_ENGINE_VISION", "") or "").lower() in ("1", "true", "yes")
    eng["key"] = _setup_key("SP_ENGINE_API_KEY_FILE")
    # A LIVE PROBE, SHORT AND UNAUTHENTICATED. `/v1/models` is the one endpoint every
    # OpenAI-compatible server answers, and the reachability question ("is anything
    # listening") is answered by a connection, not by a 200 — a server with auth on
    # returns 401 and is nonetheless plainly running, which is a different message to
    # show than "nothing is there".
    eng["reachable"], eng["probe"] = False, ""
    base = (eng.get("base_url") or "").rstrip("/")
    if base:
        try:
            import urllib.error
            import urllib.request
            try:
                with urllib.request.urlopen(base + "/v1/models", timeout=1.5) as r:
                    eng["reachable"], eng["probe"] = True, "HTTP %d" % r.status
            except urllib.error.HTTPError as he:
                eng["reachable"] = True
                eng["probe"] = "HTTP %d (listening; %s)" % (
                    he.code, "needs a key" if he.code in (401, 403) else "no /v1/models")
        except Exception as exc:
            eng["probe"] = type(exc).__name__
    out["engine"] = eng
    # ── THE OPTIONAL xAI SURFACE ────────────────────────────────────────────────────
    # One key, four features. Reported per feature rather than as one boolean because
    # the key being present is not the same as the feature being armed — voice reads
    # `tts.method`, search reads `search.backend`, and research ships off.
    xkey = _setup_key("SP_XAI_KEY_FILE", "var/secrets/Xapi.txt")
    if not xkey["present"] and (os.environ.get("SP_XAI_API_KEY") or
                                os.environ.get("XAI_API_KEY")):
        # The announced HOST_KEYS exception: an env key outranks the file. Saying so
        # stops somebody hunting for a file that is deliberately not there.
        xkey.update({"present": True, "path": "(host environment)", "bytes": 0})
    out["xai"] = {
        "key": xkey,
        "voice": {"method": os.environ.get("SP_TTS_METHOD", ""),
                  "voice_id": os.environ.get("SP_TTS_XAI_VOICE", "ara"),
                  "armed": os.environ.get("SP_TTS_METHOD", "") == "xai" and xkey["present"]},
        "images": {"image_model": os.environ.get("SP_XAI_IMAGE_MODEL", ""),
                   "video_model": os.environ.get("SP_XAI_VIDEO_MODEL", ""),
                   "armed": xkey["present"]},
        "search": {"backend": os.environ.get("SP_SEARCH_BACKEND", "ddg"),
                   "armed": os.environ.get("SP_SEARCH_BACKEND", "") == "xai" and xkey["present"]},
        "research": {"backend": os.environ.get("SP_RESEARCH_BACKEND", ""),
                     "armed": (os.environ.get("SP_RESEARCH", "") or "").lower()
                     in ("1", "true", "yes")},
    }
    # ── THE CPU SIDECARS ────────────────────────────────────────────────────────────
    aux_on = (os.environ.get("SP_AUX", "") or "").lower() in ("1", "true", "yes")
    out["sidecars"] = {"enabled": aux_on,
                       "embed_url": os.environ.get("SP_AUX_EMBED_URL", ""),
                       "chat_url": os.environ.get("SP_AUX_CHAT_URL", ""),
                       "chat_model": os.environ.get("SP_AUX_CHAT_MODEL", ""),
                       "key": _setup_key("SP_AUX_API_KEY_FILE")}
    if aux_on:
        try:
            from harness.sidecar import archive as _arc
            out["sidecars"]["status"] = _arc.status()
        except Exception as exc:
            out["sidecars"]["status"] = {"error": str(exc)[:160]}
    # ── HER IDENTITY, AND HER FACE ──────────────────────────────────────────────────
    try:
        from harness.personality import persona_layers as _PL
        pdir = _PL.persona_dir()
        out["persona"] = {"dir": os.path.relpath(pdir, _ROOT_DIR).replace("\\", "/"),
                          "present": os.path.isdir(pdir),
                          "fragments": len([f for f in os.listdir(pdir)
                                            if f.endswith(".md")]) if os.path.isdir(pdir) else 0}
    except Exception as exc:
        out["persona"] = {"present": False, "error": str(exc)[:160]}
    try:
        from harness.control import avatar_seed as _seed
        out["avatar"] = _seed.status()
    except Exception as exc:
        out["avatar"] = {"error": str(exc)[:160]}
    # ── AND THE ONE RULE. Row counts, so the panel can say the memory is live. ───────
    try:
        from harness.skills import memory as _mem
        reg = os.environ.get("SP_RECALL_REGISTRY", "")
        out["memory"] = {"registry": reg.replace("\\", "/"),
                         "present": bool(reg) and os.path.exists(reg),
                         # live_rows() is THE non-ranking read seam; counting the file's
                         # lines here would count tombstones and report a memory that
                         # only ever grows.
                         "rows": len(_mem.live_rows())}
    except Exception as exc:
        out["memory"] = {"error": str(exc)[:160]}
    return out


def _games_json() -> Dict[str, Any]:
    try:
        from harness.games import match as M
        rows = M.listing()
        # EVERY match's public state in ONE call, rather than a `?name=` the GET table
        # cannot pass anyway (it maps paths to zero-argument lambdas). There are a
        # handful of matches, not thousands, so the whole thing is cheaper than the
        # query-string plumbing would have been — and the panel stops needing a second
        # round trip to show a board.
        states = {}
        for r in rows:
            m = M.load(r["id"])
            if m is None:
                continue
            # POKER IS SEATED, NOT PUBLIC. The room is seat 0 (his chair), so the
            # listing hands back HIS view — his hole cards, never hers. There is no
            # payload here that could show both, which is the point: the leak is not
            # guarded against, it is unrepresentable.
            states[r["id"]] = (M.holdem_view(m, 0) if m["kind"] == "holdem"
                               else M.public(m))
        return {"ok": True, "kinds": list(M.KINDS), "games": rows, "states": states}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _roleplay_status() -> Dict[str, Any]:
    """What the stage panel reads. The tuning values are folded in here rather than in
    the engine, because the engine must not depend on the knob registry — it is the
    gateway that owns "what is switched on"."""
    try:
        from harness.roleplay import engine as rp
        from harness.tuning import registry as tune
        d = rp.status(_room_session())
        d["enabled"] = _roleplay_on()
        # ...AND THE PANEL IS TOLD WHAT IS ACTUALLY IN FORCE. Reporting a live scene while
        # the feature is off would put the taskbar chip on screen for a scene that no
        # longer steers anything — a chip that lies is worse than no chip.
        if not d["enabled"]:
            d["scene"] = None
            d["pending"] = False
        d["max_heat"] = int(tune.get("roleplay.max_heat"))
        d["dwell_scale"] = float(tune.get("roleplay.dwell_scale") or 1.0)
        d["ok"] = True
        return d
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


# ──── PK2 §U: read-only introspection surfaces for the operator UI ─────────
# The console needs to SHOW the new subsystems (memory, task queue, persona). These are
# small JSON endpoints the UI polls; all read-only except persona POST (the editor).
def _decisions_json() -> Dict[str, Any]:
    """The operator's queue. NOT her memory and not the ledger: what is UNDECIDED, for a
    decider, as against what is off and why, for a reader."""
    try:
        from harness.skills import decisions as _dec
        rows = _dec.items()
        return {"ok": True, "open": [r for r in rows if r["status"] == "open"],
                "decided": [r for r in rows if r["status"] == "decided"][-40:],
                "path": _dec.path()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200], "open": [], "decided": []}


def _telemetry_now_json() -> Dict[str, Any]:
    """What his body is doing, for the room AND for her — the same seam.

    Two panels reading two different functions is how the chip and the prefix end up
    describing different people. `body.read()` decides; this renders; `body.present()` is
    the same decision rendered for her instead of for a screen."""
    try:
        from harness.telemetry import body as _b
        from harness.telemetry import store as _s
        r = _b.read()
        return {"ok": True, "observed": r.get("observed", {}), "facts": r.get("facts", {}),
                "why": r.get("why", ""), "since": r.get("since", {}),
                "she_reads": _b.present(), "resting": _b.resting(),
                "health": _s.verify()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _telemetry_history_json(hours: float = 6.0, kind: str = "") -> Dict[str, Any]:
    """The series behind the chart. Down-sampled per minute, because a browser asked for
    six hours of 1 Hz heart rate is a browser that stops responding — and because a chart
    with 21,600 points is not more honest than one with 360, it is just slower."""
    try:
        from harness.telemetry import store as _s
        rows = _s.read_since(max(0.0, min(float(hours), 24 * 14)) * 3600.0)
        if kind:
            rows = [r for r in rows if r.get("kind") == kind]
        buckets: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            k, at = r.get("kind", "?"), (r.get("at") or "")[:16]     # to the minute
            key = "%s|%s" % (k, at)
            b = buckets.setdefault(key, {"kind": k, "at": at, "n": 0,
                                         "sum": 0.0, "min": None, "max": None,
                                         "state": None})
            b["n"] += 1
            v = r.get("value")
            if isinstance(v, (int, float)):
                b["sum"] += float(v)
                b["min"] = float(v) if b["min"] is None else min(b["min"], float(v))
                b["max"] = float(v) if b["max"] is None else max(b["max"], float(v))
            else:
                b["state"] = v
        series: Dict[str, list] = {}
        for b in sorted(buckets.values(), key=lambda x: x["at"]):
            point = {"at": b["at"] + "Z", "n": b["n"]}
            if b["min"] is not None:
                point.update({"avg": round(b["sum"] / b["n"], 2),
                              "min": b["min"], "max": b["max"]})
            if b["state"] is not None:
                point["state"] = b["state"]
            series.setdefault(b["kind"], []).append(point)
        return {"ok": True, "hours": hours, "series": series,
                "kinds": sorted(series.keys())}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _mem_row_json(e: Dict[str, Any]) -> Dict[str, Any]:
    """ONE registry row as the panel's JSON — the single shape (2026-08-25).

    Lifted out of `_memory_json` when /v1/memory/why arrived, because the alternative was
    a second hand-kept spelling of the same object, which is this repo's signature bug
    with a fresh date on it: a field added to the listing and forgotten in the walk would
    render a support with no salience and no status and look like a data problem."""
    from harness.skills import lifecycle as lc
    from harness.skills.memory import _text
    return {
        "name": e.get("name", ""),
        "text": lc.strip_prefix(_text(e)),        # drop the legacy "The user said: "
        "speaker": e.get("speaker", ""),
        "mem_class": e.get("mem_class", ""),
        # her lane's second label (2026-08-23): the panel cannot re-file what it
        # cannot see, and `kind` is what decides durability now
        # (lifecycle._HALF_LIFE_BY_KIND), not mem_class alone.
        "kind": e.get("kind", ""),
        "lifecycle": e.get("lifecycle", 0),
        "src": e.get("src", ""),
        "ts": e.get("ts", ""),
        # SALIENCE, ON THE PANEL. What she thinks matters, and WHY — how many times
        # he said it, how long ago, how often she has reached for it. A ranking you
        # cannot see is a ranking you cannot argue with, and the first thing this
        # one showed us when it was switched on is that the store's idea of what
        # matters was wrong (chatter outranking his GPU). That is the panel doing
        # its job: it made a bad ranking visible instead of quietly acting on it.
        "mentions": e.get("mentions", 1),
        "recalled": e.get("recalled", 0),
        "last_seen": e.get("last_seen", e.get("ts", "")),
        "salience": lc.salience(e),
        # ── THE EPISTEMIC FIELDS (2026-08-25 audit) ─────────────────────────
        # The panel could not tell an OBSERVED row from an INFERRED one, could
        # not see that a conclusion was drawn from other rows, and rendered a
        # tombstone as bare text with no cause of death — while every one of
        # those fields sat on the row it was already reading. `status` is what
        # lifecycle.render() frames from and what verdict.may_supersede rules
        # on; a curate panel that cannot see it is arguing with a ranking
        # blindfolded. Names only for `derived_from` — /v1/memory/why resolves
        # them, so a 37-support row does not carry 37 texts into every listing.
        "status": e.get("status", ""),
        "derived_from": e.get("derived_from") or [],
        "support_days": e.get("support_days", 0),
        "superseded_by": e.get("superseded_by", ""),
        "retired_because": e.get("retired_because", ""),
        # CORE (2026-08-28): the write landed on his FIRST click and the panel showed
        # nothing — this serializer is a fixed field list, and `core` was not on it.
        # The star wrote the row, the read hid it, and "pin as core" looked dead while
        # three rows sat pinned on disk. The panel cannot toggle what it cannot see.
        "core": 1 if e.get("core") else 0,
    }


def _memory_why_json(name: str) -> Dict[str, Any]:
    """"Why do you believe X?", answered in rows — the READ side of provenance.

    `derived_from` had been written, enforced by the nightly orphan sweep and gated for
    three days before anything could read it back (2026-08-25 audit). This is that read:
    the conclusion, the rows it was drawn from with their CURRENT liveness, the support
    names that resolve to nothing, and — the direction the curate panel actually needs —
    what would be orphaned if he retired this row.

    Tombstones are included on purpose. This is the audit lane, not a door she speaks
    from: `memory.provenance` is the one with the no-quoting-the-dead rule, and it counts
    retired supports rather than reading them aloud."""
    try:
        from harness.skills import memory as M
        rows = M.all_rows()
        hit = next((r for r in rows if r.get("name") == name), None)
        if hit is None:
            return {"ok": False, "error": "no row named %r" % name}
        return {
            "ok": True,
            "row": _mem_row_json(hit),
            "supports": [_mem_row_json(r) for r in M.supports_of(hit)],
            "missing_supports": M.missing_supports(hit),
            "dependents": [_mem_row_json(r) for r in M.dependents_of(hit)],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _story_json() -> Dict[str, Any]:
    """THE STORY PANEL'S DATA (2026-08-28, his ask): what stands in her prefix, line by
    line, each line naming the registry row it came from — plus the backup receipt, so
    "is all of this backed up" is answered on the same screen that shows it.

    The block comes from self_block_lines(), THE SAME assembly render_self_model() joins
    for the prefix — one truth, verified byte-identical at the refactor. The rows
    themselves come from /v1/memory (the panel joins on name), so this endpoint carries
    structure, not a second copy of the store."""
    out: Dict[str, Any] = {"ok": True, "block": [], "backup": {}}
    try:
        from harness.personality.self_model import self_block_lines
        from harness.tuning import registry as _tr_s
        _b = int(_tr_s.get("memory.self_budget", 2400) or 2400)
        out["block"] = [{"section": s_, "name": n_, "label": l_}
                        for s_, n_, l_ in self_block_lines(budget_chars=_b)]
    except Exception as exc:
        out["block_error"] = str(exc)[:120]
    try:
        from harness.control import backup as _bk
        st = _bk.status() or {}
        # the fields status() actually serves (checked live 2026-08-29: the first cut
        # filtered for at/iso/files, keys status() has never had, and the panel said
        # "no backup receipt" over 65 archives and an 00:15 newest)
        out["backup"] = {"ok": bool(st.get("enabled")) and bool(st.get("newest")),
                         "enabled": bool(st.get("enabled")),
                         "newest": st.get("newest") or "",
                         "count": st.get("count", 0),
                         "bytes": st.get("total_bytes", 0)}
    except Exception as exc:
        out["backup"] = {"error": str(exc)[:120]}
    return out


def _memory_json() -> Dict[str, Any]:
    """The fact registry as JSON rows for the operator's memory pane.

    It used to return only {text, src, ts, npos} — no `name`, so the panel could SHOW a
    memory but never RETIRE one (forget() keys on name), and no `speaker`/`mem_class`/
    `lifecycle`, so a SELF memory looked exactly like one of Sam's and a tombstoned row
    looked live. A browser you cannot act from is a report, not a panel."""
    try:
        from harness.skills.memory import _load, verify_registry
        rows = [_mem_row_json(e) for e in _load()]
        rows.sort(key=lambda r: -r["salience"])
        return {"count": len(rows), "facts": rows, "health": verify_registry()}
    except Exception as exc:
        return {"error": str(exc), "count": 0, "facts": []}


def _tasks_json() -> Dict[str, Any]:
    """The agentic work queue (task_loop states) for the task pane."""
    try:
        from harness.control.task_loop import list_tasks
        ts = list_tasks()
        return {"count": len(ts), "tasks": [
            {"id": t.task_id, "goal": t.goal, "status": t.status,
             "steps": len(t.steps), "result": t.result} for t in ts]}
    except Exception as exc:
        return {"error": str(exc), "count": 0, "tasks": []}


def _persona_get() -> Dict[str, Any]:
    try:
        with open(_persona_path(), encoding="utf-8") as f:
            return {"ok": True, "persona": f.read(), "path": _persona_path()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _spine_json() -> Dict[str, Any]:
    """ADR-008: the recent spine receipts (decide→execute→verify audit trail) for the panel."""
    try:
        from harness.control.spine import get_recent_receipts
        rs = get_recent_receipts(50)
        return {"count": len(rs), "receipts": rs}
    except Exception as exc:
        return {"error": str(exc), "count": 0, "receipts": []}


def _progress_json() -> Dict[str, Any]:
    """HINDSIGHT build progress (phases, migration map, git lanes). Its page, dashboard.html,
    went 2026-08-21; the data route stays."""
    try:
        from harness.observability.progress import progress_json
        return progress_json()
    except Exception as exc:
        return {"error": str(exc)}


def _persona_layers() -> Dict[str, Any]:
    """Which persona fragments composed into her prefix THIS session, and why not.

    Answers the one question the monolithic persona.md could never answer: "the section
    that teaches X is missing — is that deliberate?" Each row carries its `when`, the
    include decision, and its size. Bodies are truncated on purpose: this is a diagnostic,
    not an editor, and dumping every fragment produces a page nobody reads.

    Reports `stale: true` when the composition would differ from what is actually in her
    prefix — the prefix is snapshot-cached for the process lifetime (the KV-prefix law), so
    editing a fragment does NOT take effect until a restart, and a panel that implied
    otherwise would be the same lie the tuning page was telling about eot_bias.
    """
    try:
        from harness.personality import persona_layers as PL
        rows = PL.plan()
        live_now = PL.compose()
        # WHAT IS ACTUALLY IN HER HEAD (2026-08-24 audit, H1). This used to call
        # load_agent_system() — which RE-READS every file on every call — and label the
        # result "what the running process actually put in the prefix". It was a fresh
        # compose compared against a fresh compose, so `stale` was False precisely when
        # the prefix WAS stale: the same lie the docstring above says this flag exists
        # to avoid. cached_system_content() is the string the turns really serve.
        try:
            from harness.agent import _SYS as _sys_meta
            from harness.agent import cached_system_content
            in_prefix = cached_system_content()
        except Exception as _swx:
            _swallowed(logger, "_persona_layers", _swx, lane="server")
            in_prefix, _sys_meta = None, {"version": 0, "built_at": 0.0}
        stale = bool(live_now and in_prefix and live_now not in in_prefix)
        try:
            from harness.inference import context as _ctxq
            _ptok = _ctxq.prefix_tokens(in_prefix) if in_prefix else 0
        except Exception as _swx:
            _swallowed(logger, "_persona_layers", _swx, lane="server")
            _ptok = 0
        return {
            "ok": True,
            "dir": PL.persona_dir(),
            "knobs": {k: PL.knob_on(k) for k in sorted(PL.KNOBS)},
            "stale": stale,
            "prefix_version": _sys_meta.get("version", 0),
            "prefix_built_at": _sys_meta.get("built_at", 0.0),
            "prefix_tokens_est": _ptok,
            "composed_chars": len(live_now or ""),
            "knob_names": sorted(PL.KNOBS),
            "fragments": [{"file": r["file"], "order": r["order"], "when": r["when"],
                           "included": r["included"], "chars": r["chars"],
                           # THE WHOLE BODY, not a 140-char teaser. The operator's note:
                           # a preview of "1 and a half lines" tells you nothing you could
                           # act on. These files are ~200-1700 chars; the entire persona is
                           # 6.5 KB. Sending all of it costs nothing and is the only version
                           # of this panel that answers "what is actually in her head".
                           "body": r["body"] or ""} for r in rows],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "fragments": []}


def _persona_state() -> Dict[str, Any]:
    """The parsed ## Personality state block (voice/mood/traits) — the UI's personality chip."""
    try:
        from harness.personality.persona_file import parse_persona
        with open(_persona_path(), encoding="utf-8") as f:
            _, state = parse_persona(f.read())
        return {"ok": True, "state": state}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "state": {}}


def _house_now_json() -> Dict[str, Any]:
    """One seam for the room, exactly as /v1/telemetry/now is. NEVER RAISES.

    What Home Assistant is, whether it is reachable, which of his entities this framework
    would take and what each becomes. The last part is the useful one: it answers "why is
    she not being told I am asleep" without anyone having to read the mapping table."""
    try:
        from harness.homeassistant import house as _house
        return _house.status()
    except Exception as exc:
        return {"configured": False, "alive": False,
                "why": "the framework failed to load: %s" % str(exc)[:160]}


def _voice_status() -> Dict[str, Any]:
    """ADR-KAI4: is the GNA ear loadable, and on which device?"""
    try:
        from harness.voice.service import voice_status
        return voice_status()
    except Exception as exc:
        return {"ear": {"ok": False, "error": str(exc)}}


def _voice_corpus() -> Dict[str, Any]:
    """ADR-KAI4 P1.6: the in-vocab sentences to read aloud for real-voice training."""
    import os as _os
    p = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))),
                      "var", "voice", "corpus.jsonl")
    try:
        sents = [json.loads(l)["text"] for l in open(p, encoding="utf-8") if l.strip()]
        # a compact, phonetically varied reading set (prioritize wake + questions)
        import random
        wake = [s for s in sents if "kairos" in s]
        rest = [s for s in sents if "kairos" not in s]
        random.Random(7).shuffle(rest)
        pick = wake[:15] + rest[:85]
        return {"ok": True, "sentences": pick, "total_corpus": len(sents)}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "sentences": []}


def _voice_record_status() -> Dict[str, Any]:
    try:
        from harness.voice.record import record_status
        return record_status()
    except Exception as exc:
        return {"total": 0, "error": str(exc)}


def _research_json() -> Dict[str, Any]:
    """The research window: receipts from the paid tier, hers AND his (`by` says
    whose). Plain web_search rows moved to /v1/search when the search panel became
    its own window (2026-08-21) — one kind per window, chips for the rest."""
    try:
        from harness.skills import looking as L
        st = L.status()
        looks = [r for r in L.list_looks(60) if r.get("kind") == "research"][:40]
        return {"ok": True, **st, "looks": looks}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200], "looks": [], "inflight": None}


def _search_json() -> Dict[str, Any]:
    """The search window: every outward look that is NOT the research tier —
    web_search above all — plus which engine answers and who else could."""
    try:
        from harness.skills import looking as L
        st = L.status()
        looks = [r for r in L.list_looks(60) if r.get("kind") != "research"][:40]
        return {"ok": True, **st, "looks": looks}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200], "looks": [], "inflight": None}


def _narrative_json() -> Dict[str, Any]:
    """Her journal: the current line plus every snapshot ever taken of it.

    HISTORY comes from memory-okf-personality/full/ filtered on `mem_kind:
    narrative` — the content-addressed store the composer already snapshots into, so
    nothing new is written to serve this. It is a READ surface only: there is no
    write route and there will not be one. The journal is hers by construction, and
    that is the entire reason it is worth having."""
    out: Dict[str, Any] = {"ok": True, "current": "", "history": []}
    try:
        from harness.skills import narrative as _nar
        out["current"] = _nar.current() or ""
    except Exception as exc:
        out["error"] = str(exc)[:200]
    try:
        root = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))),
            "memory-okf-personality", "full")
        rows = []
        for fn in os.listdir(root):
            if not fn.endswith(".md"):
                continue
            fp = os.path.join(root, fn)
            try:
                with open(fp, encoding="utf-8") as f:
                    body = f.read()
            except OSError:
                continue
            if "mem_kind: narrative" not in body:
                continue
            text = body.split("---", 2)[-1].strip()
            rows.append({"id": fn[:-3], "at": os.path.getmtime(fp), "text": text})
        rows.sort(key=lambda r: r["at"], reverse=True)
        # ONE ENTRY PER DAY, AND THE TOP ONE ONLY ONCE (2026-08-21) — the dedupe
        # lives in narrative.collapse_history, pure and gated by G-NARRATIVE,
        # because a fix that only exists inside a route closure is a fix no gate
        # can reach. Same-day drafts collapse to the newest; `current_id` names
        # the row that IS the current line so the panel marks it instead of
        # rendering the same paragraph twice.
        from harness.skills.narrative import collapse_history
        kept, cur_id = collapse_history(rows, out.get("current") or "")
        out["current_id"] = cur_id
        out["history"] = kept[:60]
    except Exception as _swx:
        _swallowed(logger, "_narrative_json", _swx, lane="server")
    return out


def _files_json() -> Dict[str, Any]:
    """List the shared workspace — the same tree her file tools resolve against."""
    ws = os.environ.get("HARNESS_WORKSPACE") or os.getcwd()
    root = os.path.realpath(ws)
    out: Dict[str, Any] = {"ok": True, "root": root, "files": []}
    if not os.path.isdir(root):
        out["ok"], out["error"] = False, f"no workspace at {root}"
        return out
    rows = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")][:64]
        for fn in filenames:
            ap = os.path.join(dirpath, fn)
            try:
                st = os.stat(ap)
            except OSError:
                continue
            rows.append({"path": os.path.relpath(ap, root).replace("\\", "/"),
                         "bytes": st.st_size, "at": st.st_mtime})
            if len(rows) >= 500:
                break
        if len(rows) >= 500:
            break
    rows.sort(key=lambda r: r["at"], reverse=True)
    out["files"] = rows
    return out


def _room_pulse() -> Dict[str, Any]:
    """ONE call with everything the room's shell needs to feel like a place.

    Deliberately an AGGREGATOR, not a new source of truth: every field below comes
    from a function that already owns it. The shell beats once a second, and five
    separate polls for a heartbeat is how a UI ends up with five different ideas of
    what time it is.

    Time here is HER experience of it, not the wall clock the browser already has:
    when the day boundary falls, whether it has run, when she last wrote in her
    journal, when the eye next looks, how long he has been quiet."""
    import time as _t
    now = _t.time()
    out: Dict[str, Any] = {"ok": True, "now": now,
                           "iso": _t.strftime("%Y-%m-%dT%H:%M:%S", _t.localtime(now))}

    # the day boundary that actually drives consolidation
    try:
        hour = int(os.environ.get("SP_CONSOLIDATE_HOUR", "-1"))
    except ValueError:
        hour = -1
    lt = _t.localtime(now)
    nxt = None
    if hour >= 0:
        nxt = _t.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hour, 0, 0, 0, 0, -1))
        if nxt <= now:
            nxt += 86400
    day_state = {}
    try:
        with open(os.path.join(os.path.dirname(
                os.environ.get("SP_RECALL_REGISTRY", "")) or ".",
                "consolidate.json"), encoding="utf-8") as f:
            day_state = json.load(f)
    except Exception as _swx:
        _swallowed(logger, "_room_pulse", _swx, lane="server")
    out["clock"] = {"hour": lt.tm_hour, "minute": lt.tm_min,
                    "boundary_hour": hour if hour >= 0 else None,
                    "next_boundary_in_s": round(nxt - now) if nxt else None,
                    "last_consolidated_day": day_state.get("last_day"),
                    "consolidated_today": day_state.get("last_day") ==
                                          _t.strftime("%Y-%m-%d", lt)}

    # ANONYMOUS MODE — in the HEARTBEAT and not only on its own route, because the one
    # thing this mode must never do is be on without looking on. The shell beats every 5s
    # and paints the whole room from this; a switch he has to open a window to check is a
    # switch he will forget he threw, and the failure that costs is the other direction —
    # believing an evening was kept when it was not.
    try:
        from harness.control import anon as _anon_p
        out["anon"] = _anon_p.state()
    except Exception as _swx:
        _swallowed(logger, "_room_pulse", _swx, lane="server")
        out["anon"] = {"on": False}

    # her state — mood/voice/traits drive the backdrop's palette.
    # Through _persona_state(), which already owns this: it opens the right file and
    # calls parse_persona(text) correctly. My first cut called parse_persona() with
    # no argument and silently produced {} — a second implementation of a thing that
    # already worked, which is the exact rule this repo is organised around.
    try:
        out["her"] = (_persona_state().get("state") or {})
    except Exception as _swx:
        _swallowed(logger, "_room_pulse", _swx, lane="server")
        out["her"] = {}

    # her journal — when she last wrote, and the line itself
    try:
        from harness.skills import narrative as _nar
        cur = _nar.current() or ""
        out["journal"] = {"present": bool(cur), "text": cur[:400]}
    except Exception as _swx:
        _swallowed(logger, "_room_pulse", _swx, lane="server")
        out["journal"] = {"present": False}

    # looking up — in-flight or last finished. The taskbar chip reads this.
    try:
        from harness.skills import looking as _look
        st = _look.status()
        inf = st.get("inflight")
        last = st.get("last")
        out["research"] = {
            "inflight": bool(inf),
            "kind": (inf or last or {}).get("kind"),
            "query": (inf or last or {}).get("query") or "",
            "title": (last or {}).get("title") or "",
            "armed": st.get("armed"),
            "search_backend": st.get("search_backend") or "ddg",
        }
    except Exception as _swx:
        _swallowed(logger, "_room_pulse", _swx, lane="server")
        out["research"] = {"inflight": False, "armed": False}

    # presence
    pres: Dict[str, Any] = {"warm": _WARM.is_set(),
                            "since_last_turn_s": round(now - _state.LAST_TURN_AT)
                                                 if _state.LAST_TURN_AT else None}
    try:
        from harness.senses import ambient as _amb
        a = _amb.status()
        pres["ambient_enabled"] = a.get("enabled")
        pres["ambient_next_in_s"] = a.get("next_in_s")
        last = (a.get("last") or {})
        pres["ambient_last"] = last.get("seen") or last.get("error")
        pres["ambient_last_at"] = last.get("iso")
    except Exception as _swx:
        _swallowed(logger, "_room_pulse", _swx, lane="server")
    out["presence"] = pres

    try:
        from harness.control import backup as _bk
        b = _bk.status()
        out["backup"] = {"count": b.get("count"), "next_in_s": b.get("next_in_s"),
                         "newest": b.get("newest")}
    except Exception as _swx:
        _swallowed(logger, "_room_pulse", _swx, lane="server")
    return out


def warm_state() -> dict:
    return {"warm": _WARM.is_set()}


def _models_json() -> dict:
    """OpenAI-shaped /v1/models naming the container THIS daemon loaded.

    SP_MODEL_PATH is set by serve.py from the active profile's [paths] model, so it
    tracks the profile by construction and cannot drift the way a config default can.
    Falls back to the family name — true of every model here — rather than guessing a
    specific one, because a confidently wrong model name is what caused this route to
    exist (see the comment on the route table)."""
    import os as _os
    p = _os.environ.get("SP_MODEL_PATH", "")
    name = _os.path.basename(p).replace(".sp-model", "") if p else "gemma-4"
    return {"object": "list", "data": [{"id": name or "gemma-4", "object": "model"}]}
