"""G-EARS — her ears in the room, and a voice that says why it is quiet (2026-10-29).

Two things the operator could not have before this:

  * HE COULD NOT SPEAK TO HER IN THE ROOM. LFM3-Audio could hear (harness/voice/lfm3.py,
    `transcribe`), but nothing in the room recorded him and no route took his audio. Now the
    Chat composer has a mic (push-to-talk, or always-listening when `ears.mode = always`),
    `POST /v1/listen` takes the WAV bytes and answers with text, and the text goes through the
    SAME `send()` a typed line uses — so off the record, history and queuing are identical.
  * GROK WENT SILENT AND NOTHING SAID WHY. `/v1/speak` has named the engine and the failure
    since Task 4 (`X-TTS-Backend` / `X-TTS-Fallback` / a 503 with the reason), and the room's
    player swallowed every one of them: `.catch(() => null)`, `a.play().catch(() => ...)`,
    `onerror` that resolved quietly. Every failure path in speech.js now names itself.

What this holds:
  1. /v1/listen transcribes through the real lfm3 client (doors stubbed at their owner) and
     WRITES NOTHING: a census of the sandbox before and after is equal and no file is opened
     for writing during the call. His recorded audio never touches a disk.
  2. It is honest when the ears are warming (503 + the reason), refuses an oversized body with
     413 before reading it into memory, refuses an empty or non-WAV body with 400.
  3. Off the record, listening still returns text and holds no door: transcription is local;
     the TURN that follows is what OTR governs, and it goes through the typed path.
  4. Source legs (comments stripped): every speech.js failure reaches a visible reason; the
     mic is gated while she speaks; the spoken line uses send(); opening the mic stops her;
     the mic is localhost-only, with the exact copy.

Lane: OFFLINE. No server, no browser, no microphone.
"""
import builtins
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
sys.path.insert(0, os.path.join(ROOT, "harness_tests"))
from harness_tests._gate import sandbox, check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
_SB = sandbox("g_ears")  # FIRST, before any harness. import
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"
os.environ["SP_LFM3"] = "1"
for _n in ("audio.gguf", "mm.gguf"):
    open(os.path.join(_SB, _n), "wb").write(b"x")
os.environ["SP_LFM3_AUDIO_GGUF"] = os.path.join(_SB, "audio.gguf")
os.environ["SP_LFM3_AUDIO_MMPROJ"] = os.path.join(_SB, "mm.gguf")


def wav_bytes(rate=48000, secs=0.3, ch=1):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", (i * 37) % 2000 - 1000) for i in range(int(rate * secs) * ch)))
    return buf.getvalue()


from harness.voice import lfm3  # noqa: E402
from harness.control import anon as _anon  # noqa: E402
from harness.server import app as A  # noqa: E402
import _src as _srcmod  # noqa: E402

# ---- the ears' door, stubbed at its OWNER (a patch on an alias reaches nobody) -------------
HEALTH = {"code": 200}
lfm3._GET = lambda url, timeout=5: HEALTH["code"]
ASKED = []


def _post(url, body, timeout=120):
    ASKED.append((url, body))
    return json.dumps({"choices": [{"message": {"content": "Turn the lights down a little."}}]}).encode()


lfm3._POST = _post


def listen(raw: bytes, declared=None):
    """Drive the route's whole body: a declared length and the socket's read()."""
    stream = io.BytesIO(raw)
    reads = []

    def _read(n=-1):
        reads.append(n)
        return stream.read(n)
    fn = getattr(A, "_listen_op", None)
    if fn is None:
        return 0, {"ok": False, "error": "no _listen_op in harness.server.app"}, reads
    code, res = fn(len(raw) if declared is None else declared, _read)
    return code, res, reads


def census(root):
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            try:
                st = os.stat(p)
                out[p] = (st.st_size, st.st_mtime_ns)
            except OSError:
                pass
    return out


print("1. LISTEN TRANSCRIBES AND WRITES NOTHING")
WRITES = []
_real_open = builtins.open


def _spy_open(file, mode="r", *a, **k):
    if any(c in str(mode) for c in "wax+"):
        WRITES.append((str(file), mode))
    return _real_open(file, mode, *a, **k)


clip = wav_bytes(rate=48000, ch=2)    # what a browser hands over: 48 kHz, maybe stereo
before = census(_SB)
builtins.open = _spy_open
try:
    code, res, _ = listen(clip)
finally:
    builtins.open = _real_open
after = census(_SB)
check("listen transcribes and writes nothing",
      code == 200 and res == {"ok": True, "text": "Turn the lights down a little."}
      and before == after and not WRITES
      and ASKED and ASKED[-1][0].endswith("/v1/chat/completions"),
      (code, res, sorted(set(after) ^ set(before))[:5], WRITES[:3]))
_sent = (ASKED[-1][1] if ASKED else {}).get("messages", [{}, {}])[-1].get("content", [{}])[0]
try:
    import base64 as _b64
    with wave.open(io.BytesIO(_b64.b64decode(_sent["input_audio"]["data"])), "rb") as _w:
        _shape = (_w.getframerate(), _w.getnchannels())
except Exception as _e:
    _shape = repr(_e)
check("...through the real client: his audio reached the ears as 16 kHz mono, in memory",
      _shape == (16000, 1), _shape)

print("\n2. HONEST REFUSALS")
HEALTH["code"] = 503
_n = len(ASKED)
code, res, _ = listen(wav_bytes())
HEALTH["code"] = 200
check("listen is honest when ears are loading",
      code == 503 and res.get("ok") is False and "loading" in str(res.get("error", ""))
      and len(ASKED) == _n, (code, res))
cap = getattr(A, "_LISTEN_MAX_BYTES", 0)
check("the body cap is about a minute at 16 kHz (2 MB)", cap == 2 * 1024 * 1024, cap)
big = b"\0" * (cap + 1 if cap else 3 * 1024 * 1024)
_n = len(ASKED)
code, res, reads = listen(big)
check("an oversized body is refused 413, says the limit, and is never transcribed",
      code == 413 and res.get("ok") is False and "MB" in str(res.get("error", ""))
      and len(ASKED) == _n and all(0 < r <= 65536 for r in reads), (code, res, reads[:3]))
code, res, _ = listen(b"")
check("an empty body is refused 400 with a reason",
      code == 400 and res.get("ok") is False and res.get("error"), (code, res))
code, res, _ = listen(b"this is not audio at all")
check("a body that is not a WAV is refused 400, naming why",
      code == 400 and "WAV" in str(res.get("error", "")), (code, res))

print("\n3. OFF THE RECORD")
_anon._ON = True
_held = dict(_anon._HELD)
try:
    code, res, _ = listen(wav_bytes())
finally:
    _held_after = dict(_anon._HELD)
    _anon._ON = False
check("listen under OTR still returns text",
      code == 200 and res.get("text") == "Turn the lights down a little."
      and _held == _held_after, (code, res, _held, _held_after))

print("\n4. THE WIRING")


def js_code(text):
    return re.sub(r"(?<![:'\"])//[^\n]*", "", re.sub(r"/\*.*?\*/", "", text, flags=re.S))


def read(*p):
    """A missing file is an empty source — its legs FAIL by name instead of crashing the gate."""
    try:
        with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


app = " ".join(t.string for t in _tok.tokenize(io.BytesIO(_srcmod.pkg("harness", "server").encode("utf-8")).readline)
               if t.type != _tok.COMMENT)
check("POST /v1/listen is routed to _listen_op with the declared length and the socket",
      re.search(r'self \. path == "/v1/listen" : .{0,200}?_listen_op \( int \( self \. headers \. get \( "Content-Length"',
                app, re.S) is not None)
_lop = re.search(r"def _listen_op \((?:(?! def ).)*", app, re.S)
check("the listen route writes no log line of what he said",
      _lop is not None and "logger" not in _lop.group(0) and "print" not in _lop.group(0), bool(_lop))

sp = js_code(read("ui", "src", "room", "speech.js"))
_emit = re.search(r"const emit = [^\n]*\n", sp)
sp_fail = sp.replace(_emit.group(0), "") if _emit else sp


def _handler(src, i):
    """The text of the failure handler starting at `i`: a catch's {block}, a .catch(...)'s
    argument, or an onerror's assigned function — balanced, so a handler cannot borrow the
    next statement's fail()."""
    j = src.find("(" if src.startswith(".catch", i - 1) or src.startswith("catch(", i) else "{", i)
    if src.startswith("onerror", i):
        j = src.find("{", i)
    opener = src[j]
    closer = {"(": ")", "{": "}"}[opener]
    depth = 0
    for k in range(j, len(src)):
        depth += src[k] == opener
        depth -= src[k] == closer
        if depth == 0:
            return src[j:k + 1]
    return src[j:]


# A handler NAMES the failure (fail / blocked), or hands it on (throw, res('blocked')) to a
# caller that does — which is asserted on its own below, so a hand-off cannot end in silence.
# (`onerror = null` is stop() letting go of a hushed element — a detach, not a handler.)
_paths = [m.start() for m in re.finditer(r"\bcatch\b|\bonerror\b(?!\s*=\s*null)", sp_fail)]
_mute = [_handler(sp_fail, i)[:80] for i in _paths
         if not re.search(r"\b(?:fail|blocked)\(|\bthrow\b|res\('blocked'\)", _handler(sp_fail, i))]
check("every speech.js failure reaches a visible reason",
      len(_paths) >= 5 and not _mute
      and re.search(r"if \((?:!item\.now && )?!\(await refreshStatus\(\)\)\) \{[^}]*fail\('voice is switched off'\)", sp) is not None
      and re.search(r"if \(got\.e\) \{ fail\(", sp) is not None
      and re.search(r"if \(how === 'blocked'\) \{ blocked\(item\)", sp) is not None
      and "'autoplay blocked — click the room once'" in sp
      and "'speak failed: ' +" in sp
      and re.search(r"`spoke with \$\{[^}]+\} — \$\{[^}]+\}: \$\{[^}]+\}`", sp) is not None,
      (len(_paths), _mute))
check("a voice reason is in the player's state, so the chip can show it",
      re.search(r"export function state\(\) \{ return \{[^}]*\breason\b", sp) is not None)

ears = js_code(read("ui", "src", "room", "ears.js"))
_gate_fn = re.search(r"function gated\(\) \{(.*?)\n\}", ears, re.S)
check("mic is gated while she speaks",
      _gate_fn is not None and "speech.state().playing" in _gate_fn.group(1)
      and re.search(r"\b300\b", _gate_fn.group(1)) is not None
      and re.search(r"onaudioprocess = [^\n]*\n(?:[^\n]*\n){0,3}?\s*if \(gated\(\)\) return", ears) is not None)
chat = js_code(read("ui", "src", "Chat.jsx").replace('accept="image/*"', 'accept=""'))
check("spoken line uses send()",
      re.search(r"function heard\(said\) \{\s*if \(!said\) return\s*const line = heardLine\(textNow\.current, said\)(?:(?!\n  \}).)*?setText\(line\)(?:(?!\n  \}).)*?send\(line\)\s*\}", chat, re.S) is not None
      and "heardNow.current = heard" in chat and "ears.onUtterance(said => heardNow.current(said))" in chat
      and re.search(r"heard\(await ears\.stopAndSend\(\)\)", chat) is not None
      and re.search(r"async function send\(said\) \{\s*const t = \(typeof said === 'string' \? said : text\)\.trim\(\)", chat) is not None)
# (2026-10-29) barge-in CUTS her reply (room/reply.js: hush + abort once + speak no more of it);
# the behaviour is driven under node in G-ROOM-KIT, this holds the wiring before the mic opens
check("barge-in cuts her reply before the mic opens",
      re.search(r"export async function start\(\) \{(?:(?!\nexport ).)*?reply\.interrupt\(\)(?:(?!\nexport ).)*?await openMic\(\)", ears, re.S) is not None
      and re.search(r"export function interrupt\(\) \{\s*speech\.stop\(\)", js_code(read("ui", "src", "room", "reply.js"))) is not None
      and re.search(r"(?<!async )function openMic\(\) \{(?:(?!\nfunction |\nasync function |\nexport ).)*?getUserMedia", ears, re.S) is not None)
check("localhost-only copy present",
      "\"voice input needs this machine's browser\"" in ears
      and re.search(r"\['localhost', '127\.0\.0\.1', '\[::1\]'\]\.includes\(", ears) is not None
      and re.search(r"export async function start\(\) \{\s*if \(!allowed\(\)\) \{ error = NOT_HERE;", ears) is not None
      and re.search(r"export async function setAlways\(on\) \{(?:(?!\nexport ).)*?if \(!allowed\(\)\) \{ error = NOT_HERE;(?:(?!\nexport ).)*?await openMic\(\)", ears, re.S) is not None)
check("his audio is posted raw to /v1/listen and kept nowhere but memory",
      re.search(r"fetch\('/v1/listen', \{ method: 'POST', headers: \{ 'Content-Type': 'audio/wav' \}, body: wav \}\)", ears) is not None
      and not re.search(r"localStorage|sessionStorage|indexedDB|createObjectURL", ears))

print("\n5. THE MODELS WINDOW'S EARS ROW")
from harness.server import models_status as _ms  # noqa: E402
from harness.tuning import registry as _tune  # noqa: E402
_k = _tune.by_key()
check("ears.mode is push|always, default push; ears.silence_ms 800 in 300..3000",
      _k.get("ears.mode") is not None and _k["ears.mode"].choices == ["push", "always"]
      and _k["ears.mode"].default == "push" and _k.get("ears.silence_ms") is not None
      and (_k["ears.silence_ms"].default, _k["ears.silence_ms"].min, _k["ears.silence_ms"].max) == (800, 300, 3000))
_er = next((j for j in _ms.snapshot()["jobs"] if j["id"] == "ears"), {})
_tune.set_many({"ears.mode": "always"})
_er2 = next((j for j in _ms.snapshot()["jobs"] if j["id"] == "ears"), {})
_tune.reset("ears.mode")
check("the ears row carries the live mic mode", _er.get("mode") == "push" and _er2.get("mode") == "always",
      (_er.get("mode"), _er2.get("mode")))
mdl = js_code(read("ui", "src", "apps", "Models.jsx"))
check("the ears row toggles push/always through the knob, and an open Chat follows",
      "onPick('ears.mode', e.target.value)" in mdl and "value={j.mode || 'push'}" in mdl
      and "if (knob === 'ears.mode') ears.sync()" in mdl)
check("the ears row records three seconds of him through ears.js and shows what she heard",
      re.search(r"await ears\.start\(\).{0,200}?setTimeout\(r, 3000\).{0,120}?await ears\.stopAndSend\(\)", mdl, re.S) is not None
      and "● Record" in mdl and "ears.NOT_HERE" in mdl and "'heard: “' + said + '”'" in mdl)

finish("G-EARS")
