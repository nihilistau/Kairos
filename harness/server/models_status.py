"""models_status.py — ONE reader for every model job she runs (2026-10-29, the Models window).

Six jobs, six doors: her mind (the engine), the librarian (LM Studio, or the LFM3-1.7B door),
the memory index (the embed door), her ears and her local voice (the LFM3-Audio door), her eyes
(whatever `sight.backend` names). Each already had a status somewhere — /v1/launch/status,
/v1/aux, /v1/speak/status, /v1/senses — and each window had its own idea of "up". This module
asks the OWNERS (lfm3.status, tts.live_voice, sidecar.client, launch_routes.get_status, the
sight knobs) and answers in one shape, so the Models window and the taskbar strip cannot
disagree with the windows they summarise.

    snapshot() -> {"jobs": [{id, title, model, state, why, detail, switchable, knob, choices, busy}]}
    test(job)  -> {"ok", "seconds", "result"}

state is loaded | loading | off | missing | error. A `missing` row names the file in `why`:
the operator's first question is WHICH file. Mind and memory are read-only (restart-owned —
the row links to Launch). No key ever goes into either payload, and no audio into the snapshot;
the voice test's own response carries the wav it made (`audio_b64`) so the click can play it.
"""
from __future__ import annotations

import base64
import os
import time

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

VOICE_LINE = "This is how I sound right now."
LIBRARIAN_ASK = "Reply with the word ready."
_EARS_CLIP = os.path.join(os.path.dirname(os.path.dirname(__file__)), "voice", "assets", "ears_test.wav")
_METHODS = ["xai", "lfm3", "voxtral"]


def _row(id_, title, model="", state="off", why="", detail="", knob=None, choices=None, busy=False,
         value="", degraded=False):
    """`value` is the knob's live value (what the picker shows selected) — for the librarian it
    is the model id; for voice and eyes it is the method/backend, while `model` is the words."""
    return {"id": id_, "title": title, "model": model or "", "state": state, "why": why or "",
            "detail": detail or "", "switchable": bool(knob) and bool(choices), "knob": knob,
            "choices": list(choices or []), "busy": bool(busy),
            "value": (value or model or "") if knob and choices else "",
            # loaded but its last request failed (Grok answering 402): the strip shows amber
            "degraded": bool(degraded)}


def _base(p: str) -> str:
    return os.path.basename(p or "")


def _file_state(path: str, what: str):
    """(state, why) for a model file, or None when it is on disk."""
    if not path:
        return "missing", "%s is unset" % what
    if not os.path.exists(path):
        return "missing", "file not found: %s" % path
    return None


# ── HER MIND — read-only; the facts /v1/launch/status reads, read the same way ──────────
def _mind() -> dict:
    model = _base(os.environ.get("SP_MODEL_PATH", "")) or os.environ.get("SP_ENGINE_MODEL", "")
    try:
        from harness.server import launch_routes as _lr
        _code, st = _lr.get_status()
    except Exception as _swx:
        _swallowed(_swlog, "_mind", _swx, lane="server")
        st = {}
    from harness.server import state as _state
    detail = "setup %s" % (st.get("setup") or "unknown")
    if st.get("launched_at"):
        detail += " · launched %s" % st["launched_at"]
    # WARM is released in a `finally` (app.py _prewarm), so it is set after a FAILED prewarm
    # too; PREWARM.ok is False then, and the row says so (final review, 2026-10-29).
    if _state.WARM.is_set() and _state.PREWARM.get("ok") is False:
        state, why = "error", "prewarm failed: %s" % (_state.PREWARM.get("error") or "no reason recorded")
    elif _state.WARM.is_set():
        state, why = "loaded", ""
    elif st.get("launched_at"):
        state, why = "loading", "not warm yet — her prefix is still being read"
    else:
        state, why = "off", "no launch record — the stack has not been started from serve.py"
    return _row("mind", "Her mind", model, state, why, detail)


# ── THE LIBRARIAN — aux.chat_model, one picker over two doors ───────────────────────────
def _librarian() -> dict:
    from harness.sidecar import client as _cl
    model = _cl.chat_model()
    try:
        choices = _cl.chat_choices()
    except Exception as _swx:
        _swallowed(_swlog, "_librarian", _swx, lane="server")
        choices = []
    if model not in choices:
        choices = choices + [model]
    if model == _cl.LFM3_CHAT_ID:
        detail = "CPU · llama-server %s" % _cl._lfm3_url()
        if os.environ.get("SP_LFM3", "") != "1":
            return _row("librarian", "Librarian", model, "off", "SP_LFM3 is not 1", detail,
                        "aux.chat_model", choices)
        miss = _file_state(os.environ.get("SP_LFM3_CHAT_GGUF", ""), "SP_LFM3_CHAT_GGUF")
        if miss:
            return _row("librarian", "Librarian", model, miss[0], miss[1], detail, "aux.chat_model", choices)
        if not _cl._lfm3_url():
            return _row("librarian", "Librarian", model, "error",
                        "chat_url is not on this machine (%s)" % os.environ.get("SP_LFM3_CHAT_URL", ""),
                        detail, "aux.chat_model", choices)
        up = _cl._get(_cl._lfm3_url() + "/health") is not None
        return _row("librarian", "Librarian", model, "loaded" if up else "error",
                    "" if up else "the LFM3 chat door is not answering", detail, "aux.chat_model", choices)
    detail = "CPU · chat door %s" % _cl._chat_url()
    if not _cl.available():
        return _row("librarian", "Librarian", model, "off", "SP_AUX is off in the profile", detail,
                    "aux.chat_model", choices)
    up = _cl.reachable("chat")
    return _row("librarian", "Librarian", model, "loaded" if up else "error",
                "" if up else "the chat door is not answering", detail, "aux.chat_model", choices)


# ── THE MEMORY INDEX — the embed door; restart-owned, so read-only ──────────────────────
def _memory() -> dict:
    from harness.sidecar import client as _cl
    gguf = os.environ.get("SP_AUX_EMBED_GGUF", "")
    detail = "CPU · embed door %s · changes at restart" % _cl._embed_url()
    if not _cl.available():
        return _row("memory", "Memory index", _base(gguf), "off", "SP_AUX is off in the profile", detail)
    miss = _file_state(gguf, "SP_AUX_EMBED_GGUF")
    if miss:
        return _row("memory", "Memory index", _base(gguf), miss[0], miss[1], detail)
    up = _cl.reachable("embed")
    return _row("memory", "Memory index", _base(gguf), "loaded" if up else "error",
                "" if up else "the embed door is not answering", detail)


# ── EARS — LFM3-Audio, its own status ───────────────────────────────────────────────────
def _ears(st: dict) -> dict:
    row = _row("ears", "Her ears", _base(st.get("model")), st.get("state", "error"),
               "" if st.get("why") == st.get("state") else st.get("why", ""),
               "CPU · speech → text · %s" % (os.environ.get("SP_LFM3_LANG", "en") or "en"))
    # (2026-10-29) the room's mic mode rides on the row, so the window's push/always toggle
    # shows the knob's value without a second poll of /v1/tuning
    from harness.tuning import registry as _tune
    row["mode"] = _tune.get("ears.mode")
    return row


# ── HER VOICE — voice.method; busy IS the one synthesis lock ────────────────────────────
def _voice(lst: dict) -> dict:
    from harness.voice import tts as _tts
    lv = _tts.live_voice()
    method = lv["method"]
    busy = _tts._LOCK.locked()
    speaking = _tts.speaking_engine()
    if method == "xai":
        model, detail = "Grok · %s" % lv["xai_voice"], "api.x.ai · the local voice is the fallback"
    elif method == "lfm3":
        model = "LFM3-Audio · %s" % lv["lfm3_voice"]
        detail = "CPU · %s" % (_base(lst.get("model")) or "no gguf set")
    else:
        model, detail = "Voxtral · %s" % (lv.get("local_gguf") or _tts.VOICE), "local · the older chain"
    if busy:
        detail += " · speaking now: %s (one voice at a time)" % (speaking or "starting")

    def row(state, why="", degraded=False):
        return _row("voice", "Her voice", model, state, why, detail, "voice.method", _METHODS, busy, method,
                    degraded)

    if not lv["enabled"]:
        return row("off", "voice.enabled is off — text only")
    # OFF THE RECORD (2026-10-29, operator: "switch to local for OTR"): xai and voxtral are
    # SKIPPED (tts.OFF_RECORD_SKIPS — one spelling for the voice and this row) and lfm3 speaks,
    # so the light is lfm3's state; with lfm3 not loaded nothing can speak, and the row is off.
    # `anon.on()` is the NON-counting read — holds() would add a phantom entry to his
    # off-the-record receipt on every 4 s poll.
    from harness.control import anon as _anon
    if _anon.on() and method in _tts.OFF_RECORD_SKIPS:
        why = _tts.off_record_reason(method)
        lstate, lwhy = lst.get("state", "error"), lst.get("why", "")
        if lstate == "loaded":
            return row("loaded", why)
        return row("off", "%s — but %s is %s%s, so she is quiet" % (
            why, _tts.OFF_RECORD_VOICE, lstate, (": " + lwhy) if lwhy and lwhy != lstate else ""))
    if method == "lfm3":
        state, why = lst.get("state", "error"), lst.get("why", "")
        return row(state, "" if why == state else why)
    if method == "voxtral":
        return row("loaded") if _tts.available() else row(
            "missing", "no voxtral server or exe (SP_TTS_URL / the CLI)")
    # GROK, HONESTLY (2026-10-29 review): a cloud voice has no load, but it has a key and a
    # last failure. The key is only tested for presence; its bytes never touch the row.
    from harness.skills import xai as _xai
    if not _xai.api_key():
        return row("error", "no xAI key")
    last = _xai.tts_last_error()
    return row("loaded", ("last request failed: %s" % last) if last else "", degraded=bool(last))


# ── EYES — sight.backend ────────────────────────────────────────────────────────────────
def _eyes(mind: dict) -> dict:
    from harness.skills import sight_vl as _sv
    from harness.tuning import registry as _tr
    kn = _tr.by_key().get("sight.backend")
    choices = list(kn.choices) if kn else ["engine", "aux_vl", "openai"]
    es = _sv.eyes_status()
    backend = es.get("backend") or "engine"
    if backend == "aux_vl":
        model = es.get("vl_model") or ""
        if not model:
            return _row("eyes", "Eyes", "", "off", "no VL model chosen (sight.vl_model)", "aux door",
                        "sight.backend", choices, value=backend)
        from harness.sidecar import client as _cl
        if not _cl.available():
            return _row("eyes", "Eyes", model, "off", "SP_AUX is off in the profile", "aux door",
                        "sight.backend", choices, value=backend)
        up = bool(es.get("door_up"))
        return _row("eyes", "Eyes", model, "loaded" if up else "error",
                    "" if up else "the aux chat door is not answering", "aux door · LM Studio",
                    "sight.backend", choices, value=backend)
    if backend == "engine":
        try:
            from harness.senses import capability as _cap
            sees = bool(_cap.status().get("sight"))
        except Exception as _swx:
            _swallowed(_swlog, "_eyes", _swx, lane="server")
            sees = False
        if not sees:
            return _row("eyes", "Eyes", "her own vision", "off",
                        "the served model cannot see (config/model_capability.json)", "engine",
                        "sight.backend", choices, value=backend)
        return _row("eyes", "Eyes", "her own vision", mind["state"], mind["why"], "engine · the served model",
                    "sight.backend", choices, value=backend)
    return _row("eyes", "Eyes", "image_url via the seam", mind["state"], mind["why"], "openai seam",
                "sight.backend", choices, value=backend)


def snapshot() -> dict:
    from harness.voice import lfm3 as _lfm3
    lst = _lfm3.status()            # ears and the local voice share one door: ask it once
    jobs = []
    mind = None
    for name, fn in (("mind", _mind), ("librarian", _librarian), ("memory", _memory),
                     ("ears", lambda: _ears(lst)), ("voice", lambda: _voice(lst)),
                     ("eyes", lambda: _eyes(mind))):
        try:
            r = fn()
        except Exception as exc:
            _swallowed(_swlog, "snapshot:" + name, exc, lane="server")
            r = _row(name, name, state="error", why="status failed: %s" % (str(exc)[:120] or type(exc).__name__))
        if name == "mind":
            mind = r
        jobs.append(r)
    return {"ok": True, "jobs": jobs}


def test(job: str) -> dict:
    """One small real request per job. Mind, memory and eyes report status only — a test
    there would cost her a turn or a frame, and their state already says what a test would."""
    t0 = time.perf_counter()
    ok, result, extra = False, "", {}
    try:
        if job == "voice":
            from harness.voice import tts as _tts
            # /v1/speak's own path, uncached: a cache hit would prove only that she spoke once.
            # AUDIBLE (controller ruling, 2026-10-29): the wav rides back on THIS response only,
            # so the click that asked plays exactly what was tested — no second synthesis, no
            # cache write. snapshot() stays audio-free.
            wav, meta = _tts.synthesize(VOICE_LINE, use_cache=False)
            # a fallback is not a pass: the chosen voice failed (the strip shows it amber too).
            # Off the record the remote voice is SKIPPED, not failed — the local one speaking
            # is the voice working as designed (2026-10-29).
            fell = str(meta.get("fell_back_from") or "")
            ok = not fell or _tts.only_off_record_falls(fell)
            result = "%s spoke" % (meta.get("backend") or "?")
            if meta.get("fell_back_from"):
                result += " — fell back from %s" % meta["fell_back_from"]
            extra = {"audio_b64": base64.b64encode(wav).decode("ascii"),
                     "backend": meta.get("backend") or "", "fell_back_from": meta.get("fell_back_from") or ""}
        elif job == "ears":
            from harness.voice import lfm3 as _lfm3
            with open(_EARS_CLIP, "rb") as f:
                heard = _lfm3.transcribe(f.read())
            ok, result = bool(heard), "heard: %s" % (heard or "(nothing)")
        elif job == "librarian":
            from harness.sidecar import client as _cl
            said = _cl.chat([{"role": "user", "content": LIBRARIAN_ASK}], max_tokens=8)
            ok, result = bool(said), ("said: %s" % said) if said else "no answer from the door"
        elif job in ("mind", "memory", "eyes"):
            row = next(j for j in snapshot()["jobs"] if j["id"] == job)
            ok = row["state"] == "loaded"
            result = "status only — %s%s" % (row["state"], (": " + row["why"]) if row["why"] else "")
        else:
            result = "unknown job %r" % (job,)
    except Exception as exc:
        _swallowed(_swlog, "test:" + str(job), exc, lane="server")
        ok, result = False, str(exc)[:300] or type(exc).__name__
    return {"ok": ok, "seconds": round(time.perf_counter() - t0, 2), "result": result, **extra}
