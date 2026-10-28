"""G-MODELS-WINDOW — one status route for every model job, the Models window, the strip (2026-10-29).

Six jobs run on six different doors (her mind on the engine, the librarian on LM Studio or the
LFM3-1.7B door, the memory index on the embed door, ears and the local voice on the LFM3-Audio
door, eyes on whichever `sight.backend` names). Before this, each had its own window and its own
idea of "up"; nothing answered "what is loaded right now" in one place. `harness/server/models_status.py`
is that one reader: `snapshot()` for GET /v1/models/status, `test(job)` for POST /v1/models/test.

What this holds: every job is reported in one shape; a missing model file is named in `why` (the
operator's first question is WHICH file); mind and memory are read-only (restart-owned); the voice
row's `busy` IS tts._LOCK (one voice at a time, visible); the voice Test goes through the real
tts.synthesize chain and says which engine spoke; no API key and no audio ever reaches the payload.
Plus the wiring the room needs: the routes, the app, the strip in the taskbar, reduced motion.

Every door is stubbed — no server is started, nothing leaves the machine.
Lane: OFFLINE.
"""
import io
import json
import os
import re
import struct
import sys
import tokenize as _tok
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from harness_tests._gate import sandbox, check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
_SB = sandbox("g_models_window")  # FIRST, before any harness. import

SECRET = "sk-MODELS-GATE-0123456789abcdef"
_keyf = os.path.join(_SB, "aux.key")
open(_keyf, "w").write(SECRET)
os.environ["SP_AUX_API_KEY_FILE"] = _keyf
os.environ["XAI_API_KEY"] = SECRET
os.environ["SP_AUX"] = "1"
os.environ["SP_LFM3"] = "1"
for _n in ("audio.gguf", "mm.gguf", "embed.gguf", "brain.sp-model"):
    open(os.path.join(_SB, _n), "wb").write(b"x")
os.environ["SP_LFM3_AUDIO_GGUF"] = os.path.join(_SB, "audio.gguf")
os.environ["SP_LFM3_AUDIO_MMPROJ"] = os.path.join(_SB, "mm.gguf")
os.environ["SP_AUX_EMBED_GGUF"] = os.path.join(_SB, "embed.gguf")
os.environ["SP_MODEL_PATH"] = os.path.join(_SB, "brain.sp-model")
os.environ.pop("SP_LFM3_CHAT_GGUF", None)
os.environ["SP_TTS_METHOD"] = "xai"
os.environ["SP_TTS_LOCAL"] = "lfm3"
os.environ["SP_TTS_ENABLED"] = "1"


def wav_bytes(rate=24000, secs=0.2):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", (i * 37) % 2000 - 1000) for i in range(int(rate * secs))))
    return buf.getvalue()


from harness.voice import lfm3, tts  # noqa: E402
from harness.sidecar import client  # noqa: E402
from harness.server import models_status as ms  # noqa: E402

# ---- the doors, stubbed at their OWNERS (a patch on an alias reaches nobody) ------------
HEALTH = {"lfm3": 200}
lfm3._GET = lambda url, timeout=5: HEALTH["lfm3"]
LFM3_POSTS = []


def _lfm3_post(url, body, timeout=120):
    LFM3_POSTS.append(url)
    if url.endswith("/tts"):
        return wav_bytes()
    return json.dumps({"choices": [{"message": {"content": "Turn the lights down a little, please."}}]}).encode()


lfm3._POST = _lfm3_post
DOORS = {"embed": True, "chat": True}
client.reachable = lambda door: DOORS[door]
client.list_models = lambda ttl_s=60.0: ["liquidai/lfm2.5-1.2b-instruct"]
CHAT_POSTS = []


def _chat_post(url, body, timeout, auth=False):
    CHAT_POSTS.append((url, body))
    return {"choices": [{"message": {"content": "ready"}}]}


client._post = _chat_post

JOBS = ["mind", "librarian", "memory", "ears", "voice", "eyes"]
STATES = {"loaded", "loading", "off", "missing", "error"}
KEYS = {"id": str, "title": str, "model": str, "state": str, "why": str, "detail": str,
        "switchable": bool, "choices": list, "busy": bool, "degraded": bool}


def jobs():
    return {j["id"]: j for j in ms.snapshot()["jobs"]}


print("1. EVERY JOB IS REPORTED, IN ONE SHAPE")
snap = ms.snapshot()
ids = [j.get("id") for j in snap.get("jobs", [])]
check("every job is reported", ids == JOBS, ids)
bad = [(j.get("id"), k) for j in snap.get("jobs", []) for k, t in KEYS.items()
       if not isinstance(j.get(k), t)]
bad += [(j.get("id"), "knob") for j in snap.get("jobs", [])
        if not (j.get("knob") is None or isinstance(j.get("knob"), str))]
check("every row carries every field with its type", not bad, bad)
check("every state is one of the five",
      all(j.get("state") in STATES for j in snap.get("jobs", [])), [j.get("state") for j in snap.get("jobs", [])])
J = jobs()
check("the ears are loaded when the door says 200", J["ears"]["state"] == "loaded", J["ears"])
check("the memory index names its gguf", J["memory"]["model"] == "embed.gguf", J["memory"]["model"])

print("\n2. A MISSING FILE IS NAMED")
_gone = os.path.join(_SB, "nowhere", "LFM3-Audio-2B-Q8_0.gguf")
os.environ["SP_LFM3_AUDIO_GGUF"] = _gone
J = jobs()
check("missing file is named", J["ears"]["state"] == "missing" and _gone in J["ears"]["why"], J["ears"])
os.environ["SP_LFM3_AUDIO_GGUF"] = os.path.join(_SB, "audio.gguf")
_gone_e = os.path.join(_SB, "nowhere", "embed-350m.gguf")
os.environ["SP_AUX_EMBED_GGUF"] = _gone_e
J = jobs()
check("a missing embed gguf is named too", J["memory"]["state"] == "missing" and _gone_e in J["memory"]["why"],
      J["memory"])
os.environ["SP_AUX_EMBED_GGUF"] = os.path.join(_SB, "embed.gguf")
HEALTH["lfm3"] = 503
check("a door answering 503 is loading", jobs()["ears"]["state"] == "loading")
HEALTH["lfm3"] = 200
DOORS["embed"] = False
J = jobs()
check("a dark embed door is an error that says so", J["memory"]["state"] == "error" and J["memory"]["why"], J["memory"])
DOORS["embed"] = True

print("\n3. MIND AND MEMORY ARE READ-ONLY")
J = jobs()
check("mind and memory are read-only",
      J["mind"]["switchable"] is False and J["memory"]["switchable"] is False
      and J["mind"]["knob"] is None and not J["mind"]["choices"] and not J["memory"]["choices"],
      (J["mind"], J["memory"]))
check("the switchable rows name a real knob and offer choices",
      all(J[k]["switchable"] and J[k]["knob"] and J[k]["choices"] for k in ("librarian", "voice", "eyes")),
      {k: (J[k]["knob"], J[k]["choices"]) for k in ("librarian", "voice", "eyes")})
check("a switchable row's value is one of its choices (the picker shows what is live)",
      all(J[k]["value"] in J[k]["choices"] for k in ("librarian", "voice", "eyes")),
      {k: (J[k]["value"], J[k]["choices"]) for k in ("librarian", "voice", "eyes")})
check("the voice picker offers the three methods", J["voice"]["choices"] == ["xai", "lfm3", "voxtral"],
      J["voice"]["choices"])
from harness.tuning import registry as _tr  # noqa: E402
_known = _tr.by_key()
check("every knob a row names exists in the registry",
      all(j["knob"] in _known for j in J.values() if j["knob"]), [j["knob"] for j in J.values()])

# A FAILED PREWARM IS NOT LOADED (final review, 2026-10-29). app.py releases WARM in a
# `finally` so a failed prewarm cannot wedge the gateway — which made WARM alone say "loaded"
# over a daemon that had refused her prefix. PREWARM.ok is the record of whether it worked.
from harness.server import state as _st  # noqa: E402
_was_warm, _was_pw = _st.WARM.is_set(), dict(_st.PREWARM)
_st.WARM.set()
_st.PREWARM.update(ok=False, error="daemon stream error: prefix refused", at=1.0)
_m_bad = jobs()["mind"]
_st.PREWARM.update(ok=True, error="", at=2.0)
_m_ok = jobs()["mind"]
_st.PREWARM.clear()
_m_none = jobs()["mind"]
_st.PREWARM.update(_was_pw)
if not _was_warm:
    _st.WARM.clear()
check("a failed prewarm makes the mind row an error that carries the daemon's reason",
      _m_bad["state"] == "error" and "prefix refused" in _m_bad["why"], _m_bad)
check("...and a prewarm that worked (or never ran) is loaded",
      _m_ok["state"] == "loaded" and _m_none["state"] == "loaded", (_m_ok, _m_none))

print("\n4. VOICE BUSY REFLECTS THE LOCK")
_idle = jobs()["voice"]["busy"]
with tts._LOCK:
    _held = jobs()["voice"]["busy"]
check("voice busy reflects the lock", _idle is False and _held is True, (_idle, _held))

print("\n5. TESTS")
SPOKE = []


def _speak_with(engine, text, voice, steps, speed):
    SPOKE.append((engine, text))
    if engine == "xai":
        raise RuntimeError("http 402: out of credit")
    return wav_bytes()


tts._speak_with = _speak_with
r = ms.test("voice")
# A FALLBACK IS NOT A PASS (final review, 2026-10-29): the strip shows Grok amber on a 402, and
# the Test said a tick for the same failure. The chosen voice did not speak, so the Test fails —
# and still says who spoke instead, and still carries that wav so he hears it.
check("test voice reports who spoke, and a fallback is not a pass",
      r.get("ok") is False and "lfm3" in r.get("result", "") and "xai" in r.get("result", "")
      and SPOKE and SPOKE[-1] == ("lfm3", "This is how I sound right now."), (r, SPOKE))
check("a test carries ok / seconds / result",
      isinstance(r.get("ok"), bool) and isinstance(r.get("seconds"), float) and isinstance(r.get("result"), str), r)
r_voice = r
_sw = tts._speak_with
tts._speak_with = lambda engine, text, voice, steps, speed: wav_bytes()
_r_ok = ms.test("voice")
tts._speak_with = _sw
check("...while the chosen voice speaking is a pass",
      _r_ok.get("ok") is True and not _r_ok.get("fell_back_from") and "xai spoke" in _r_ok.get("result", ""),
      {k: v for k, v in _r_ok.items() if k != "audio_b64"})
import base64 as _b64  # noqa: E402
try:
    _heard = _b64.b64decode(r.get("audio_b64") or "")
except Exception:
    _heard = b""
check("the voice test is audible: its response carries the wav it tested",
      _heard[:4] == b"RIFF" and r.get("backend") == "lfm3" and "xai" in r.get("fell_back_from", ""),
      (r.get("backend"), r.get("fell_back_from"), _heard[:4]))
r = ms.test("ears")
check("test ears transcribes the bundled clip",
      r.get("ok") is True and "lights" in r.get("result", "").lower()
      and LFM3_POSTS and LFM3_POSTS[-1].endswith("/v1/chat/completions"), (r, LFM3_POSTS[-1:]))
r_ears = r
r = ms.test("librarian")
check("test librarian asks for the word ready",
      r.get("ok") is True and "ready" in r.get("result", "")
      and CHAT_POSTS and "Reply with the word ready." in json.dumps(CHAT_POSTS[-1][1]), (r, CHAT_POSTS[-1:]))
_n = len(CHAT_POSTS) + len(LFM3_POSTS) + len(SPOKE)
r_rest = [ms.test(j) for j in ("mind", "memory", "eyes")]
check("mind, memory and eyes report status only (no door is called)",
      len(CHAT_POSTS) + len(LFM3_POSTS) + len(SPOKE) == _n and all("result" in x for x in r_rest), r_rest)
r = ms.test("nonsense")
check("an unknown job is refused, not run", r.get("ok") is False and "unknown" in r.get("result", ""), r)

print("\n6. NO KEY OR AUDIO IN THE PAYLOAD")
# THE SNAPSHOT IS AUDIO-FREE; the voice test's response carries its wav on purpose (ruling,
# 2026-10-29), so that one field is set aside here and everything else is scanned.
_rv = {k: v for k, v in r_voice.items() if k != "audio_b64"}
blob = json.dumps([ms.snapshot(), _rv, r_ears, r_rest])
check("no key or audio in the payload",
      SECRET not in blob and SECRET not in json.dumps(r_voice)
      and "RIFF" not in blob and not re.search(r"[A-Za-z0-9+/=]{200,}", blob),
      blob[:200])

print("\n6b. GROK, HONESTLY — key, off the record, last failure")
from harness.control import anon as _anon  # noqa: E402
from harness.skills import xai as _xai  # noqa: E402
os.environ["SP_TTS_METHOD"] = "xai"
_v = jobs()["voice"]
check("grok with a key and no failure is loaded, not degraded",
      _v["state"] == "loaded" and _v["degraded"] is False and not _v["why"], _v)
_saved = {k: os.environ.pop(k, None) for k in ("XAI_API_KEY", "SP_XAI_API_KEY")}
os.environ["SP_XAI_KEY_FILE"] = os.path.join(_SB, "no-such-key.txt")
_v = jobs()["voice"]
check("no xAI key is an error that says so", _v["state"] == "error" and _v["why"] == "no xAI key", _v)
for _k, _val in _saved.items():
    if _val is not None:
        os.environ[_k] = _val
os.environ.pop("SP_XAI_KEY_FILE", None)
_anon._ON = True
_held_before = dict(_anon._HELD)
_v = jobs()["voice"]
_held_after = dict(_anon._HELD)
_anon._ON = False
_ears_state = jobs()["ears"]["state"]       # the one LFM3-Audio door the local voice shares
check("off the record, grok's row reads 'speaking locally' with tts's own reason, lit by lfm3's state",
      _v["state"] == _ears_state and _v["state"] != "off" and "speaking locally" in _v["why"]
      and _v["why"].startswith(tts.off_record_reason("xai", "lfm3")), (_v, _ears_state))
check("...and reading it does not count a hold on his receipt", _held_before == _held_after,
      (_held_before, _held_after))
# VOXTRAL OFF THE RECORD (review round 1): synthesize skips it (its server logs the sentence,
# its CLI writes a temp wav) and lfm3 speaks — so its row must not stay green on its own state,
# and the Test must pass when lfm3 spoke. With lfm3 not loaded nothing can speak: off, and why.
os.environ["SP_TTS_METHOD"] = "voxtral"
_anon._ON = True
try:
    _vx = jobs()["voice"]
    del SPOKE[:]
    _rt = ms.test("voice")
    _spoke_vx = list(SPOKE)
    HEALTH["lfm3"] = 503
    _vx_down = jobs()["voice"]
finally:
    HEALTH["lfm3"] = 200
    _anon._ON = False
    os.environ["SP_TTS_METHOD"] = "xai"
check("off the record with voxtral chosen: the row reads 'speaking locally (lfm3)', lit by lfm3",
      _vx["state"] == "loaded" and _vx["why"] == tts.off_record_reason("voxtral"), _vx)
check("...the Test passes when lfm3 spoke, and voxtral was never run",
      _rt.get("ok") is True and _rt.get("backend") == "lfm3"
      and _rt.get("fell_back_from") == tts.off_record_fell("voxtral")
      and [e for e, _t in _spoke_vx] == ["lfm3"], ({k: v for k, v in _rt.items() if k != "audio_b64"}, _spoke_vx))
check("...and with lfm3 not loaded the row is off and says so",
      _vx_down["state"] == "off" and _vx_down["why"].startswith(tts.off_record_reason("voxtral"))
      and "lfm3 is loading" in _vx_down["why"], _vx_down)
_xai._TTS_ERROR[0] = "http 402: out of credit"
_v = jobs()["voice"]
_xai._TTS_ERROR[0] = ""
check("a failed last request keeps loaded, says why, and is degraded",
      _v["state"] == "loaded" and _v["degraded"] is True and "402" in _v["why"]
      and SECRET not in json.dumps(_v), _v)

print("\n6c. WHICH VOICE IS BUSY")
import threading as _th  # noqa: E402
_go, _in = _th.Event(), _th.Event()


def _blocking(engine, text, voice, steps, speed):
    if engine == "xai":
        raise RuntimeError("http 402: out of credit")
    _in.set()
    _go.wait(10)
    return wav_bytes()


tts._speak_with = _blocking
_t = _th.Thread(target=lambda: tts.synthesize("Busy line.", use_cache=False), daemon=True)
_t.start()
_in.wait(10)
_v = jobs()["voice"]
_go.set()
_t.join(10)
check("the busy voice row names the engine holding the lock",
      _v["busy"] is True and "speaking now: lfm3" in _v["detail"], _v["detail"])
check("...and the engine is cleared when the lock is released",
      tts.speaking_engine() == "" and jobs()["voice"]["busy"] is False, tts.speaking_engine())
tts._speak_with = _speak_with

print("\n7. THE WIRING")


def js_code(text):
    return re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", text, flags=re.S))


def read(*p):
    """A missing file is an empty source — its legs FAIL by name instead of crashing the gate."""
    try:
        with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


# THE SERVER PACKAGE, not one file (G-SRC-TRAP §3: app.py was split, and a pinned file is
# green over whatever moves out of it). Comments only are stripped, NOT docstrings: a dict key
# on its own line after a comment is a STRING after a layout token, which a docstring-stripper
# drops. The regexes need the code shape (`: lambda : __import__ (`), which prose does not have.
sys.path.insert(0, os.path.join(ROOT, "harness_tests"))
import _src as _srcmod  # noqa: E402
app = " ".join(t.string for t in _tok.tokenize(io.BytesIO(_srcmod.pkg("harness", "server").encode("utf-8")).readline)
               if t.type != _tok.COMMENT)
check("GET /v1/models/status is routed to snapshot()",
      re.search(r'"/v1/models/status"\s*:\s*lambda\s*:\s*__import__\s*\(\s*"harness.server.models_status"', app) is not None)
check("POST /v1/models/test is routed to test()",
      '"/v1/models/test"' in app and re.search(r"models_status\s+as\s+\w+", app) is not None)
api = js_code(read("ui", "src", "api.js"))
check("api.js has modelsStatus and modelsTest",
      "modelsStatus" in api and "'/v1/models/status'" in api and "modelsTest" in api and "'/v1/models/test'" in api)
reg = js_code(read("ui", "src", "appRegistry.jsx"))
check("the Models app is registered", re.search(r"id: 'models',(?: group: 'system',)? title: 'Models', icon: 'models'", reg) is not None)
check("it has a glyph", re.search(r"^\s*models:\s*\[", read("ui", "src", "kit", "icons.jsx"), re.M) is not None)
mdl = js_code(read("ui", "src", "apps", "Models.jsx"))
check("the window polls every 4 s and writes knobs through /v1/tuning",
      "usePoll(api.modelsStatus, 4000)" in mdl and "api.tuningSet" in mdl and "api.modelsTest" in mdl)
check("the mind row links to Launch", "'launch'" in mdl)
# THROUGH HER ONE PLAYER (final review, 2026-10-29): a bare `new Audio` here overlapped her
# speech and was invisible to the mic's gate, so always-listening heard the test line as his.
check("the voice Test plays the wav its own response carried, through speech.js's one queue",
      "speech.playNow('data:audio/wav;base64,' + r.audio_b64)" in mdl and "new Audio" not in mdl)
strip = js_code(read("ui", "src", "room", "ModelStrip.jsx"))
main = js_code(read("ui", "src", "main.jsx"))
_tb = main[main.find('className="taskbar"'):]
check("the strip is in the taskbar and opens the Models window",
      "<ModelStrip" in _tb and "'models'" in strip and "wm.open" in strip)
check("a degraded row's light is amber",
      "j.degraded ? ' mst-degraded'" in strip
      and re.search(r"\.mst-light\.mst-degraded[^{]*\{[^}]*background:\s*var\(--warn\)",
                    read("ui", "src", "room", "shell.css")) is not None)
check("the strip's tooltip is `title: model — state`",
      re.search(r"j\.title \+ ': ' \+ \(j\.model[^)]*\) \+ ' — ' \+ j\.state", strip) is not None)
css = re.sub(r"/\*.*?\*/", "", read("ui", "src", "room.css") + read("ui", "src", "room", "shell.css"), flags=re.S)
# the WHOLE selector of every mdl-/mst- rule that animates, and it must be named verbatim in a
# reduced-motion block — a bare prefix match would pass on `.mdl-bar` for `.mdl-bar i.mdl-bar-ind`
_anims = {m.strip() for m in re.findall(r"([^{}]*\.m(?:dl|st)-[^{}]*)\{[^}]*animation:\s*(?!none)", css)}
_rm = " ".join(re.findall(r"@media \(prefers-reduced-motion: reduce\)\s*\{(.*?)\n\}", css, re.S))
check("every mdl-/mst- animation stops under reduced motion",
      _anims and all(a in _rm for a in _anims), (_anims, _rm[-300:]))
for f in ("Senses.jsx", "titleChips.jsx", "Voice.jsx"):
    check("%s no longer asks for method 'local'" % f, "=== 'local'" not in js_code(read("ui", "src", "apps", f)))

finish("G-MODELS-WINDOW")
