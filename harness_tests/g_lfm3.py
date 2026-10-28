"""G-LFM3 — the one LFM3-Audio client (her ears and her local voice), 2026-10-29.

harness/voice/lfm3.py talks to the single resident llama-server (CPU). The transport is
stubbed (`_POST` / `_GET`): no server is started, nothing leaves the machine. What this holds:
a recording is resampled to 16 kHz mono IN MEMORY before it is sent, ASR runs at temperature 0
with the ASR prompt, speech comes back as WAV bytes, a door that is not ready is an honest
LFM3Error (and no request is made), nothing is written to disk, and the voice knob reaches
the call.

Lane: OFFLINE.
"""
import base64
import io
import json
import os
import struct
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from harness_tests._gate import sandbox, check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
_SB = sandbox("g_lfm3")  # FIRST, before any harness. import

os.environ["SP_LFM3"] = "1"
os.environ["SP_LFM3_AUDIO_URL"] = "http://127.0.0.1:8813"
os.environ["SP_LFM3_AUDIO_GGUF"] = os.path.join(_SB, "a.gguf")
os.environ["SP_LFM3_AUDIO_MMPROJ"] = os.path.join(_SB, "m.gguf")
for _n in ("a.gguf", "m.gguf"):
    open(os.path.join(_SB, _n), "wb").write(b"x")

from harness.voice import lfm3  # noqa: E402


def wav_bytes(rate, channels, secs=0.5):
    n = int(rate * secs)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", (i * 37) % 2000 - 1000) * channels for i in range(n)))
    return buf.getvalue()


CALLS = []
HEALTH = {"code": 200}


def fake_post(url, body, timeout=120):
    CALLS.append((url, body))
    if url.endswith("/tts"):
        return wav_bytes(24000, 1, 0.2)
    return json.dumps({"choices": [{"message": {"content": " hello there "}}]}).encode()


lfm3._POST = fake_post
lfm3._GET = lambda url, timeout=5: HEALTH["code"]


def files_in(d):
    return sorted(os.path.join(r, f) for r, _, fs in os.walk(d) for f in fs)


# ---- transcribe --------------------------------------------------------------------
before = files_in(_SB)
text = lfm3.transcribe(wav_bytes(44100, 2))
url, body = CALLS[-1]
check("transcribe returns the stripped text", text == "hello there", repr(text))
check("transcribe posts to the chat door", url == "http://127.0.0.1:8813/v1/chat/completions", url)
part = body["messages"][1]["content"][0]
sent = base64.b64decode(part["input_audio"]["data"])
with wave.open(io.BytesIO(sent)) as w:
    fmt = (w.getframerate(), w.getnchannels(), w.getsampwidth())
    nfr = w.getnframes()
# the header alone can lie (a skipped resample still writes 16000): 0.5 s must be ~8000 frames
check("transcribe sends 16k mono", fmt == (16000, 1, 2) and abs(nfr - 8000) <= 8, "%s %d frames" % (fmt, nfr))
check("asr uses temp 0 and the ASR prompt",
      body.get("temperature") == 0 and body["messages"][0] == {"role": "system", "content": "Perform ASR in English."}
      and part["type"] == "input_audio" and part["input_audio"]["format"] == "wav", json.dumps(body)[:160])

# ---- speak -------------------------------------------------------------------------
out = lfm3.speak("Hello there.")
check("speak returns wav bytes", out[:4] == b"RIFF" and out[8:12] == b"WAVE")
url, body = CALLS[-1]
check("speak posts /tts with the default voice",
      url == "http://127.0.0.1:8813/tts" and body == {"input": "Hello there.", "voice": "female"}, str(body))

# ---- voice follows the knobs -------------------------------------------------------
from harness.tuning import registry as R  # noqa: E402
_orig = R.tune_or_env
R.tune_or_env = lambda knob, env, default=None: "male" if knob == "voice.lfm3_voice" else _orig(knob, env, default)
try:
    lfm3.speak("Hi.")
    check("voice and lang follow the knobs (voice.lfm3_voice=male reaches the call)",
          CALLS[-1][1]["voice"] == "male", str(CALLS[-1][1]))
    check("an explicit voice argument beats the knob", (lfm3.speak("Hi.", voice="female"), CALLS[-1][1]["voice"] == "female")[1])
    check("status reports the knob's voice", lfm3.status()["voice"] == "male")
finally:
    R.tune_or_env = _orig
os.environ["SP_LFM3_LANG"] = "es"
lfm3.transcribe(wav_bytes(16000, 1))
check("lang follows the env into the ASR prompt", "Spanish" in CALLS[-1][1]["messages"][0]["content"],
      CALLS[-1][1]["messages"][0]["content"])
os.environ["SP_LFM3_LANG"] = "en"

check("nothing touches disk", files_in(_SB) == before, str(set(files_in(_SB)) ^ set(before)))

# ---- his audio never leaves the machine (final review, 2026-10-29) -------------------
# serve.py binds the LFM3-Audio door to 127.0.0.1 whatever the profile says. A profile
# audio_url naming another host is therefore never OUR door — and following it would send
# his recorded voice across the network. It refuses loudly and calls nothing.
_GETS = []
_get0 = lfm3._GET
lfm3._GET = lambda url, timeout=5: (_GETS.append(url), HEALTH["code"])[1]
for _far in ("http://192.168.1.20:8813", "http://127.0.0.1.nip.io:8813", "http://localhost.example.com:8813"):
    os.environ["SP_LFM3_AUDIO_URL"] = _far
    _n0, _g0 = len(CALLS), len(_GETS)
    _why = []
    for fn, arg in ((lfm3.transcribe, wav_bytes(16000, 1)), (lfm3.speak, "x")):
        try:
            fn(arg)
            _why.append("")
        except lfm3.LFM3Error as e:
            _why.append(str(e))
    _st = lfm3.status()
    check("an audio_url off this machine refuses, and nothing is sent (%s)" % _far,
          all("audio_url is not on this machine" in w for w in _why) and len(CALLS) == _n0 and len(_GETS) == _g0
          and _st["state"] == "error" and "audio_url is not on this machine" in _st["why"], (_why, _st["state"], [u for u, _ in CALLS[_n0:]]))
for _near in ("http://localhost:8813", "http://[::1]:8813", "http://127.0.0.1:8813"):
    os.environ["SP_LFM3_AUDIO_URL"] = _near
    check("...and %s is this machine" % _near, lfm3.status()["state"] == "loaded", lfm3.status())
lfm3._GET = _get0
os.environ["SP_LFM3_AUDIO_URL"] = "http://127.0.0.1:8813"

# ---- not ready is an honest error --------------------------------------------------
n = len(CALLS)
HEALTH["code"] = 503
for fn, arg in ((lfm3.transcribe, wav_bytes(16000, 1)), (lfm3.speak, "x")):
    try:
        fn(arg)
        msg = ""
    except lfm3.LFM3Error as e:
        msg = str(e)
    check("not ready is an honest error (%s)" % fn.__name__, "loading" in msg, msg)
check("not ready makes no request", len(CALLS) == n)
check("ready() is False while loading", lfm3.ready() is False)
check("status loading", lfm3.status()["state"] == "loading")
HEALTH["code"] = 200
check("status loaded", lfm3.status()["state"] == "loaded" and lfm3.ready())
HEALTH["code"] = 500
check("status error on 500", lfm3.status()["state"] == "error")
HEALTH["code"] = 200

# ---- off / missing -----------------------------------------------------------------
os.environ["SP_LFM3"] = "0"
check("status off", lfm3.status()["state"] == "off" and not lfm3.ready())
os.environ["SP_LFM3"] = "1"
os.environ["SP_LFM3_AUDIO_MMPROJ"] = os.path.join(_SB, "nope.gguf")
st = lfm3.status()
check("status missing names the file", st["state"] == "missing" and "nope.gguf" in st["why"], str(st))
os.environ["SP_LFM3_AUDIO_MMPROJ"] = os.path.join(_SB, "m.gguf")

# ---- bad input / empty replies are errors, not inventions ---------------------------
for label, thunk in (("empty text", lambda: lfm3.speak("  ")), ("not a wav", lambda: lfm3.transcribe(b"junk"))):
    try:
        thunk()
        ok = False
    except lfm3.LFM3Error:
        ok = True
    check("%s raises LFM3Error" % label, ok)

# =====================================================================================
# HER VOICE PIPELINE LEARNS LFM3 (Task 4, 2026-10-29). tts.synthesize with every engine
# stubbed: lfm3.speak and tts._via_cli on the module that OWNS each (synthesize imports the
# module at call time, so a patch reaches the call). Grok is NOT stubbed at xai.tts: the REAL
# xai.tts runs and urlopen, as xai.py sees it, answers — so the reason in fell_back_from is
# the one xai.py itself recorded (round 1: a stub that wrote the reason hid that tts() never did).
# =====================================================================================
import threading  # noqa: E402
import time  # noqa: E402

os.environ["SP_TTS_ENABLED"] = "1"
os.environ["SP_TTS_URL"] = ""
os.environ["SP_TTS_CACHE"] = os.path.join(_SB, "tts-cache")
os.environ["SP_TTS_LOCAL"] = "lfm3"
os.environ["SP_TTS_METHOD"] = "local"
from harness.voice import tts as T  # noqa: E402
from harness.skills import xai as X  # noqa: E402
from harness.control import anon as AN  # noqa: E402
T.TTS_URL = ""
T.CACHE_DIR = os.environ["SP_TTS_CACHE"]

WAV = wav_bytes(24000, 1, 0.1)
SAID = []                               # (engine, text, voice, t_start, t_end)
FAIL = {"xai": "", "lfm3": "", "voxtral": ""}    # xai: "" or (http code, body bytes)
os.environ["SP_XAI_API_KEY"] = "gate-not-a-key"  # never the key file; urlopen below is the wire


class _Resp:
    def __init__(self, b):
        self._b = b

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _xai_urlopen(req, timeout=None):
    url = getattr(req, "full_url", str(req))
    if not url.endswith("/tts"):
        raise AssertionError("unexpected wire call in G-LFM3: %s" % url)
    body = json.loads(req.data.decode("utf-8"))
    t0 = time.perf_counter()
    SAID.append(("xai", body["text"], body["voice_id"], t0, time.perf_counter()))
    if FAIL["xai"]:
        code, payload = FAIL["xai"]
        raise urllib.error.HTTPError(url, code, "err", {}, io.BytesIO(payload))
    return _Resp(WAV)


def _lfm3_speak(text, voice="", lang=""):
    t0 = time.perf_counter()
    if FAIL["lfm3"]:
        SAID.append(("lfm3", text, voice, t0, time.perf_counter()))
        raise lfm3.LFM3Error(FAIL["lfm3"])
    time.sleep(SLEEP["s"])
    SAID.append(("lfm3", text, voice, t0, time.perf_counter()))
    return WAV


def _vox(text, voice, steps):
    t0 = time.perf_counter()
    SAID.append(("voxtral", text, voice, t0, time.perf_counter()))
    if FAIL["voxtral"]:
        raise T.TTSError(FAIL["voxtral"])
    return WAV


SLEEP = {"s": 0.0}
import urllib.error  # noqa: E402
X.urllib.request.urlopen = _xai_urlopen      # the name xai.tts resolves at call time
lfm3.speak = _lfm3_speak
T._via_cli = _vox


def say(text, method, use_cache=False):
    os.environ["SP_TTS_METHOD"] = method
    return T.synthesize(text, use_cache=use_cache)


# ---- local reads as the local default ---------------------------------------------
os.environ["SP_TTS_METHOD"] = "local"
os.environ["SP_TTS_LOCAL"] = "lfm3"
lv = T.live_voice()
check("local reads as the local default (lfm3)", lv["method"] == "lfm3" and lv.get("local_default") == "lfm3",
      str(lv))
os.environ["SP_TTS_LOCAL"] = "voxtral"
check("local reads as the local default (voxtral)", T.live_voice()["method"] == "voxtral", str(T.live_voice()))
os.environ["SP_TTS_LOCAL"] = "lfm3"
os.environ["SP_TTS_METHOD"] = ""
check("an unset method is the local default too", T.live_voice()["method"] == "lfm3")
os.environ["SP_TTS_METHOD"] = "lfm3"
check("speaking_as names the lfm3 voice", T.live_voice()["speaking_as"] == "lfm3:female", T.live_voice()["speaking_as"])

# ---- lfm3 speaks, and under the one lock -------------------------------------------
del SAID[:]
wav, meta = say("Hello there.", "lfm3")
check("lfm3 is a voice method: it speaks and meta says so",
      wav == WAV and meta.get("backend") == "lfm3" and [s[0] for s in SAID] == ["lfm3"]
      and SAID[0][2] == "female" and not meta.get("fell_back_from"), "%s %s" % (meta, SAID))
del SAID[:]
SLEEP["s"] = 0.25
_ths = [threading.Thread(target=say, args=("Line %d." % i, "lfm3")) for i in range(2)]
for _t in _ths:
    _t.start()
for _t in _ths:
    _t.join()
SLEEP["s"] = 0.0
_iv = sorted((s[3], s[4]) for s in SAID)
check("lfm3 speaks under the one lock (the second synthesis waits for the first)",
      len(_iv) == 2 and _iv[1][0] >= _iv[0][1], str(_iv))

# ---- grok failure says why and who spoke --------------------------------------------
del SAID[:]
X._LAST_ERROR[0] = "http 429: a stale image-generation reason"   # must not leak into her voice
FAIL["xai"] = (402, b"credits exhausted")
wav, meta = say("Are you there?", "xai")
check("grok failure says why and who spoke",
      wav == WAV and meta.get("backend") == "lfm3"
      and str(meta.get("fell_back_from", "")).startswith("xai: http 402"), str(meta))
check("a stale image error does not leak into the TTS reason",
      "stale image" not in str(meta.get("fell_back_from", ""))
      and meta.get("fell_back_from") == "xai: http 402: credits exhausted", str(meta))
FAIL["lfm3"] = "loading"
wav, meta = say("Are you there now?", "xai")
check("two fallbacks chain their reasons and voxtral speaks",
      meta.get("backend") == "voxtral"
      and meta.get("fell_back_from") == "xai: http 402: credits exhausted; lfm3: loading", str(meta))
FAIL["voxtral"] = "no voxtral binary"
try:
    say("Anyone?", "xai")
    msg = ""
except T.TTSError as e:
    msg = str(e)
check("every engine failing raises and names every reason",
      "xai: http 402" in msg and "lfm3: loading" in msg and "voxtral: no voxtral binary" in msg, msg)
FAIL.update(xai="", lfm3="", voxtral="")
wav, meta = say("Fine again.", "xai")
check("a healthy grok speaks and nothing fell", meta.get("backend") == "xai" and meta.get("fell_back_from") == "",
      str(meta))
check("a healthy grok leaves no TTS reason behind (the 402 from before is cleared)",
      X.tts_last_error() == "", X.tts_last_error())

# ---- lfm3 tags stripped like voxtral ------------------------------------------------
del SAID[:]
say("[laugh] Come here. <soft>I did say so.</soft>", "lfm3")
_t = SAID[-1][1]
check("lfm3 tags stripped like voxtral", SAID[-1][0] == "lfm3" and "[" not in _t and "<" not in _t
      and "Come here." in _t and "I did say so." in _t, _t)
del SAID[:]
FAIL["xai"] = (500, b"oops")
say("[laugh] Come here.", "xai")
FAIL["xai"] = ""
check("a grok fallback strips her tags before the local voice reads them",
      [s[0] for s in SAID] == ["xai", "lfm3"] and "[laugh]" in SAID[0][1] and "[" not in SAID[1][1],
      str([(s[0], s[1]) for s in SAID]))

# ---- OFF THE RECORD SHE SPEAKS LOCALLY, AND NOTHING IS KEPT (2026-10-29, operator) -------
# "switch to local for OTR, but ensure obviously nothing is logged or kept anywhere." With
# voice.method = xai and the switch on, synthesize no longer raises: Grok is skipped (no request
# to api.x.ai, net.voice counted ONCE so his receipt stays honest) and the local default speaks.
# What is KEPT is proven by the witnesses, not by reading the code: every log record any logger
# emits (captured at DEBUG on the root), every file under the sandbox (scanned for a sentinel),
# and the cache directory itself.
import logging  # noqa: E402

_SENT = "Zephyrine-otr-4471 is the private word"
_REC = []


class _Catch(logging.Handler):
    def emit(self, record):
        try:
            _REC.append(record.getMessage())
        except Exception:
            _REC.append(str(record.msg))


_root = logging.getLogger()
_lvl0 = _root.level
_catch = _Catch(level=logging.DEBUG)
_root.addHandler(_catch)
_root.setLevel(logging.DEBUG)


def _kept_anywhere(s):
    """Where the sentinel survives: log records, and any file under the sandbox."""
    hits = ["log: " + r[:80] for r in _REC if s in r]
    for p in files_in(_SB):
        try:
            if s.encode("utf-8") in open(p, "rb").read():
                hits.append("file: " + p)
        except OSError:
            pass
    return hits


def _cache_now():
    d = os.environ["SP_TTS_CACHE"]
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


AN.enter("gate")
try:
    del SAID[:]
    del _REC[:]
    _c0, _h0 = _cache_now(), dict(AN._HELD)
    _m = None
    try:
        _w, _m = say(_SENT + ".", "xai", use_cache=True)
    except T.TTSError as e:
        _m = {"err": str(e)}
    _h1 = dict(AN._HELD)
    check("off the record with xai chosen: she SPEAKS, through the local default (lfm3)",
          (_m or {}).get("backend") == "lfm3" and [s[0] for s in SAID] == ["lfm3"], str(_m))
    check("...and the room is told why: X-TTS-Fallback reads 'xai: off the record'",
          (_m or {}).get("fell_back_from") == "xai: off the record", str(_m))
    check("...zero requests to api.x.ai", not [s for s in SAID if s[0] == "xai"], SAID)
    check("...net.voice held exactly once for the sentence (his receipt stays honest)",
          _h1.get("net.voice", 0) - _h0.get("net.voice", 0) == 1, (_h0, _h1))
    check("...the cache write is held (voice.cache +1) and the cache dir is unchanged",
          _h1.get("voice.cache", 0) - _h0.get("voice.cache", 0) == 1 and _cache_now() == _c0,
          (_c0, _cache_now()))
    check("...and her sentence is in no log record and no file", not _kept_anywhere("Zephyrine-otr-4471"),
          _kept_anywhere("Zephyrine-otr-4471"))

    # lfm3 FAILS, and its reason ECHOES her sentence (a server that quotes its input back). The
    # swallowed error must not carry the text into any log, and the voxtral fallback leaves no
    # trace: its CLI writes a temp wav and its server prints the sentence to its own log, so off
    # the record voxtral is HELD rather than run (docs/ANON-MODE.md, the arming condition).
    del SAID[:]
    del _REC[:]
    _c0 = _cache_now()
    FAIL["lfm3"] = "server said: could not voice %r" % (_SENT + " again.")
    try:
        say(_SENT + " again.", "xai", use_cache=True)
        _err = ""
    except T.TTSError as e:
        _err = str(e)
    FAIL["lfm3"] = ""
    check("lfm3 failing off the record: voxtral is held, not run (no temp wav, no server log line)",
          [s[0] for s in SAID] == ["lfm3"] and "voxtral: off the record" in _err, (SAID, _err))
    check("...the swallowed lfm3 error carries no sentence text into any log or file",
          not _kept_anywhere("Zephyrine-otr-4471"), _kept_anywhere("Zephyrine-otr-4471"))
    check("...nor into the reason handed back to the room", "Zephyrine" not in _err, _err)
    check("...and the cache dir is unchanged", _cache_now() == _c0, (_c0, _cache_now()))
    # THE SCRUB IS TOTAL (review round 1): a TRUNCATED echo (<16 chars) and a JSON-ESCAPED one
    # must reach nothing either — off the record a failure is its exception TYPE and no text.
    del SAID[:]
    del _REC[:]
    _esc = "Zéphyrïne-q9 whispers"
    FAIL["lfm3"] = 'bad input {"input": %s} near "%s"' % (json.dumps(_esc), _esc[:9])
    try:
        say(_esc + ".", "xai", use_cache=True)
        _err = ""
    except T.TTSError as e:
        _err = str(e)
    FAIL["lfm3"] = ""
    _bits = ("phyr", "q9 whispers", "Z\\u00e9", "u00ef", "Zéphy")
    _left = [b for b in _bits if b in _err or _kept_anywhere(b)]
    check("off the record a failure is its TYPE only: no truncated or escaped echo anywhere",
          "lfm3: LFM3Error" in _err and not _left, (_err, _left))
    check("...and the log line is the type too",
          any("synthesize:lfm3" in r and r.rstrip().endswith("LFM3Error") for r in _REC), _REC[-3:])
    del SAID[:]
    _w, _m = say("something private", "lfm3")
    check("a local method off the record still speaks, untouched", _m.get("backend") == "lfm3"
          and _m.get("fell_back_from") == "", str(_m))
    # voxtral CHOSEN, or the local default: off the record it is skipped and lfm3 speaks
    del SAID[:]
    _w, _m = say("something private too", "voxtral")
    check("voxtral chosen off the record: skipped with its trace named, and lfm3 speaks",
          _m.get("backend") == "lfm3" and [s[0] for s in SAID] == ["lfm3"]
          and _m.get("fell_back_from") == T.off_record_fell("voxtral")
          and "logs the sentence" in _m.get("fell_back_from", ""), str(_m))
    os.environ["SP_TTS_LOCAL"] = "voxtral"
    del SAID[:]
    try:
        _w, _m = say("and more", "xai")
    finally:
        os.environ["SP_TTS_LOCAL"] = "lfm3"
    os.environ["SP_TTS_LOCAL"] = "voxtral"
    del SAID[:]
    try:
        _w2, _m2 = say("voxtral all round", "voxtral")
    except T.TTSError as e:
        _m2 = {"err": str(e)}
    finally:
        os.environ["SP_TTS_LOCAL"] = "lfm3"
    check("voxtral chosen AND the local default off the record: lfm3 is still in the chain and speaks",
          _m2.get("backend") == "lfm3" and [s[0] for s in SAID] == ["lfm3"], str(_m2))
    check("xai off the record with a VOXTRAL local default still speaks through lfm3",
          _m.get("backend") == "lfm3" and [s[0] for s in SAID] == ["lfm3"]
          and _m.get("fell_back_from") == "xai: off the record", str(_m))
finally:
    AN.leave()
    _root.removeHandler(_catch)
    _root.setLevel(_lvl0)
del SAID[:]
FAIL["lfm3"] = "server said: %s" % _SENT
try:
    _w, _m = say("On the record.", "lfm3")
finally:
    FAIL["lfm3"] = ""
check("on the record, an lfm3 failure's reason is kept verbatim and voxtral runs",
      _m.get("backend") == "voxtral" and _SENT in _m.get("fell_back_from", ""), str(_m))

# ---- cache keys keep voices apart ---------------------------------------------------
_keys = {}
for _m in ("xai", "lfm3", "voxtral"):
    _w, _meta = say("The same words.", _m, use_cache=True)
    _keys[_m] = (_meta["key"], _meta["voice"])
check("cache keys keep voices apart",
      len({v[0] for v in _keys.values()}) == 3
      and _keys["xai"][1] == "xai:ara" and _keys["lfm3"][1] == "lfm3:female"
      and _keys["voxtral"][1] == T.VOICE, str(_keys))
_w, _meta = say("The same words.", "lfm3", use_cache=True)
check("a cache hit reports the backend that made it", _meta.get("cached") and _meta.get("backend") == "lfm3",
      str(_meta))

# ---- the room is told: /v1/speak carries backend and fallback ----------------------
import inspect  # noqa: E402,F401
import io as _io  # noqa: E402
import tokenize as _tok  # noqa: E402


def code_only(text):
    starts = (_tok.INDENT, _tok.DEDENT, _tok.NEWLINE, _tok.NL, _tok.ENCODING)
    out, prev = [], _tok.ENCODING
    for t in _tok.tokenize(_io.BytesIO(text.encode("utf-8")).readline):
        if t.type == _tok.COMMENT:
            continue
        if t.type == _tok.STRING and prev in starts:
            prev = t.type
            continue
        prev = t.type
        out.append(t.string)
    return " ".join(out)


# the PACKAGE, not app.py (G-SRC-TRAP): the route may move to a sibling. .index() is loud.
sys.path.insert(0, os.path.join(ROOT, "harness_tests"))
import _src as _srcmod  # noqa: E402
_app = code_only(_srcmod.pkg("harness", "server"))
_sp = _app[_app.index('self . path == "/v1/speak"'):]
_sp = _sp[:_sp.index("elif self . path ==")]
check("/v1/speak sends X-TTS-Backend and X-TTS-Fallback from meta",
      '"X-TTS-Backend"' in _sp and '"X-TTS-Fallback"' in _sp and 'meta . get ( "fell_back_from"' in _sp, _sp[:0])

# ---- the registry knows the methods ------------------------------------------------
_kn = R.by_key()
check("voice.method is xai | lfm3 | voxtral", _kn["voice.method"].choices == ["xai", "lfm3", "voxtral"])
check("voice.lfm3_voice is female | male, default female",
      "voice.lfm3_voice" in _kn and _kn["voice.lfm3_voice"].choices == ["female", "male"]
      and _kn["voice.lfm3_voice"].default == "female")

# ---- the librarian option: LFM3-1.7B on its own door (Task 5) -----------------------
from harness.sidecar import client as SC  # noqa: E402

_LFM3_ID = "lfm3-1.7b-uncensored"
_chat_gguf = os.path.join(_SB, "chat.gguf")
os.environ["SP_LFM3_CHAT_URL"] = "http://127.0.0.1:8814"
os.environ["SP_AUX_CHAT_URL"] = "http://127.0.0.1:1234"
os.environ["SP_LFM3_CHAT_GGUF"] = _chat_gguf
_sc_calls = []
_sc_post, _sc_get = SC._post, SC._get


def _sc_fake_post(url, body, timeout, auth=False):
    _sc_calls.append((url, body, auth))
    return {"choices": [{"message": {"content": " ok "}}]}


SC._post = _sc_fake_post
SC._get = lambda url, timeout=5, auth=False: {"data": [{"id": "liquidai/lfm2.5-1.2b-instruct"}]}
SC._MODELS_CACHE.update(at=0.0, ids=[])
try:
    SC.chat([{"role": "user", "content": "hi"}], model=_LFM3_ID)
    u, b, a = _sc_calls[-1]
    check("lfm3 id routes to its own door", u == "http://127.0.0.1:8814/v1/chat/completions", u)
    check("lfm3 door gets no LM Studio bearer token", a is False)
    check("suggested sampling applied",
          (b["temperature"], b["top_k"], b["repeat_penalty"]) == (0.1, 50, 1.1), str(b))
    SC.chat([{"role": "user", "content": "hi"}], model=_LFM3_ID, temperature=0.7)
    check("an explicit temperature wins over the suggested one", _sc_calls[-1][1]["temperature"] == 0.7)
    SC.chat([{"role": "user", "content": "hi"}], model="liquidai/lfm2.5-1.2b-instruct")
    u, b, a = _sc_calls[-1]
    check("other ids still go to LM Studio",
          u == "http://127.0.0.1:1234/v1/chat/completions" and a is True and "top_k" not in b, u)
    check("default stays lfm2.5-1.2b", SC.chat_model() == "liquidai/lfm2.5-1.2b-instruct")
    check("choice offered only when the file exists (absent)", _LFM3_ID not in SC.chat_choices())
    open(_chat_gguf, "wb").write(b"x")
    SC._MODELS_CACHE.update(at=0.0, ids=[])
    _ch = SC.chat_choices()
    check("choice offered only when the file exists (present, beside the door's list)",
          _LFM3_ID in _ch and "liquidai/lfm2.5-1.2b-instruct" in _ch, str(_ch))
    check("aux.chat_model's picker is fed by chat_choices", _LFM3_ID in R.by_key()["aux.chat_model"].choices_fn())
    # THE CHAT DOOR IS THIS MACHINE'S TOO (final review, 2026-10-29): serve.py binds it to
    # 127.0.0.1 whatever the profile says, so a far chat_url is a door nobody started — and
    # the librarian's words (his evening, folded into context) must not go there.
    _far_calls = len(_sc_calls)
    os.environ["SP_LFM3_CHAT_URL"] = "http://192.168.1.20:8814"
    _far_said = SC.chat([{"role": "user", "content": "hi"}], model=_LFM3_ID)
    check("a chat_url off this machine is a dead door: no call, empty answer",
          _far_said == "" and len(_sc_calls) == _far_calls and SC._lfm3_url() == "", (_far_said, _sc_calls[_far_calls:]))
    os.environ["SP_AUX_CHAT_MODEL"] = _LFM3_ID
    from harness.server import models_status as _MS  # noqa: E402
    _lib = _MS._librarian()
    check("...and the Models row says why", _lib["state"] == "error" and "chat_url is not on this machine" in _lib["why"], _lib)
    os.environ.pop("SP_AUX_CHAT_MODEL", None)
    os.environ["SP_LFM3_CHAT_URL"] = "http://localhost:8814"
    SC.chat([{"role": "user", "content": "hi"}], model=_LFM3_ID)
    check("...while localhost is still this machine", _sc_calls[-1][0] == "http://localhost:8814/v1/chat/completions",
          _sc_calls[-1][0])
    os.environ["SP_LFM3_CHAT_URL"] = "http://127.0.0.1:8814"
finally:
    SC._post, SC._get = _sc_post, _sc_get

finish("G-LFM3")
