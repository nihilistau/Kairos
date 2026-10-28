"""tts.py — SPEECH OUT. She gets a voice.

Until now there was none: `console/index.html` called the browser's
`speechSynthesis` and the comment beside it said "stopgap". Everything in
`harness/voice/` was input.

TWO BACKENDS BEHIND ONE SEAM, and the seam is the point:

  SERVER (preferred)   POST {SP_TTS_URL}/speak -> WAV bytes. A voxtral process
                       that stays resident, so the ~5 s model load and the
                       shader-cache warm-up are paid once for the life of the
                       daemon instead of once per sentence.
  CLI (fallback)       `voxtral speak --gguf ... --output x.wav`, one process per
                       utterance. Correct, and slow in a way you can feel.

Callers never learn which ran. When the server bin lands, `SP_TTS_URL` is set and
nothing else in the tree changes — that is the whole reason this file exists
rather than a subprocess call at the call site.

(2026-10-29) That seam now fronts THREE engines — xai (remote), lfm3 and voxtral (local,
the server/CLI pair above) — and callers DO learn which one spoke: meta["backend"] and
meta["fell_back_from"], because a silent fallback is how Grok went quiet on him unnoticed.

MEASURED ON THIS BOX (2026-07-31, RTX 2060, Q4 GGUF, 3 Euler steps, wgpu
discrete): a 4.3 s utterance cost 63 s cold, 45 s, then 28 s as the shader cache
warmed — RTF 12.9x -> 9.0x -> 6.1x. The published figure is RTF 0.97 on
mid-to-long generations; that is NOT what this hardware and this build produce
for short ones, where fixed overhead dominates. The `--device integrated` path
panics outright (cubecl refuses a 1.5 GiB allocation), so the iGPU escape from
GPU contention is not available as built.

Which is why the CACHE is not an optimisation here, it is the feature: her
greetings, her acknowledgements, anything she says twice, are free the second
time. Keyed on (text, voice, steps) so a persona change does not serve stale audio.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from typing import Optional

from harness.store_io import replace_atomic

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# the sibling checkout, by RELATIVE position (no absolute path in a public tree); the profile's
# SP_TTS_ROOT overrides
VOX_ROOT = os.environ.get("SP_TTS_ROOT", os.path.join(_ROOT, "..", "voxtral-mini-realtime-rs"))
VOX_EXE = os.environ.get("SP_TTS_EXE", os.path.join(VOX_ROOT, "target", "release", "voxtral.exe"))
VOX_GGUF = os.environ.get("SP_TTS_GGUF", os.path.join(VOX_ROOT, "models", "voxtral-tts-q4.gguf"))
TTS_URL = os.environ.get("SP_TTS_URL", "").rstrip("/")
VOICE = os.environ.get("SP_TTS_VOICE", "casual_female")
STEPS = int(os.environ.get("SP_TTS_STEPS", "3"))
DEVICE = os.environ.get("SP_TTS_DEVICE", "discrete")
TIMEOUT = int(os.environ.get("SP_TTS_TIMEOUT", "600"))
CACHE_DIR = os.environ.get("SP_TTS_CACHE", os.path.join(_ROOT, "var", "voice", "tts"))
CACHE_MAX = int(os.environ.get("SP_TTS_CACHE_MAX", "512"))

# One synthesis at a time. Two concurrent voxtral processes contend for the same
# GPU the daemon is using, and the second one is not faster for having started.
_LOCK = threading.Lock()

# WHICH ENGINE HOLDS IT (2026-10-29, the Models window): set inside the lock for each engine
# attempt and cleared in a finally before the next one, so "one voice at a time" can say WHICH.
# A one-slot list, written only under _LOCK; readers take whatever is there (a str swap is atomic).
_SPEAKING: list[str] = [""]


# ── WHICH VOICES OFF THE RECORD SKIPS, AND WHY — ONE SPELLING (2026-10-29) ──────────────
# tts.synthesize (the X-TTS-Fallback entry) and the Models window's voice row (models_status)
# both read these, so the room's chip, the row and the voice can never disagree.
#   xai      leaves the machine (net.voice)
#   voxtral  leaves a trace: its CLI can only write its audio to a file (a temp wav), and its
#            resident tts-server prints the first 48 characters of every sentence to its log
#            (voxtral-mini-realtime-rs, src/bin/tts-server.rs). Arming condition: tts-server
#            stops logging the text — then its server leg can run off the record.
# Off the record, lfm3 is the one voice that speaks.
_VOXTRAL_TRACE = "its server logs the sentence, its CLI writes a temp wav"
OFF_RECORD_SKIPS = {
    "xai": "would send each sentence to a third party",
    "voxtral": "leaves a trace (%s)" % _VOXTRAL_TRACE,
}
OFF_RECORD_VOICE = "lfm3"


def off_record_fell(engine: str) -> str:
    """The X-TTS-Fallback / meta["fell_back_from"] entry for a voice skipped off the record:
    "xai: off the record", "voxtral: off the record (its server logs ...)"."""
    return "%s: off the record" % engine + (" (%s)" % _VOXTRAL_TRACE if engine == "voxtral" else "")


def off_record_reason(method: str, local: str = OFF_RECORD_VOICE) -> str:
    """The Models row's why for a voice skipped off the record (operator, 2026-10-29: "switch
    to local for OTR" — she no longer goes quiet; her local voice speaks instead)."""
    return ("off the record — speaking locally (%s): her voice is %s, which %s, so her local "
            "voice speaks until the switch is off." % (local, method, OFF_RECORD_SKIPS.get(method, "is held")))


def only_off_record_falls(fell: str) -> bool:
    """True when every entry of a fell_back_from is a voice SKIPPED off the record — the
    designed path, not a failure (the Models Test passes on it)."""
    parts = [p.strip() for p in str(fell or "").split("; ") if p.strip()]
    return bool(parts) and all(p == off_record_fell(p.split(":", 1)[0]) for p in parts)


# ── WHAT OFF THE RECORD KEEPS OF A FAILURE: ITS TYPE, NOTHING ELSE (2026-10-29) ─────────
# An engine's error can quote its input back — whole, truncated, or JSON-escaped — and a
# matcher for "her sentence in this message" misses at least one of those. So off the record
# a failure reaches the log, the room, the header and the raised error as its exception TYPE
# only ("lfm3: LFM3Error"). On the record the reason is kept verbatim (it is what tells him
# why Grok went quiet).


class _HeldError(Exception):
    """A swallowed engine error off the record: its message is the original TYPE name only."""


def speaking_engine() -> str:
    """The engine synthesising right now (xai | lfm3 | voxtral), "" when the voice is idle."""
    return _SPEAKING[0]


class TTSError(RuntimeError):
    pass


# ── SENTENCE CHUNKING, AND WHY IT IS THE ARCHITECTURE AND NOT AN OPTIMISATION ──
#
# Measured 2026-07-31: a ~55-word paragraph (about 20 s of speech) sent as ONE
# utterance ran 47 minutes at 100% GPU and 11.9 of 12 GB VRAM before it was
# killed. A 4.3 s utterance costs ~28 s warm. The cost is not linear in length —
# it blows up — so long input is not slow, it is a hazard.
#
# Chunking is also simply the right shape for how this gets used: she starts
# speaking one sentence after she finishes writing it, while the next one is
# still being made. Time-to-first-audio becomes one sentence instead of a whole
# reply, and `console/speech.js`'s serial queue pipelines the rest for free.
MAX_CHARS = int(os.environ.get("SP_TTS_MAX_CHARS", "240"))

_ENDS = ".!?…"


def split_sentences(text: str, max_chars: int | None = None) -> list[str]:
    """Split a reply into utterance-sized pieces on sentence boundaries.

    Falls back to comma, then to a hard character cut, so a wall of text with no
    punctuation still yields bounded chunks rather than one catastrophic one."""
    limit = MAX_CHARS if max_chars is None else max_chars
    text = " ".join((text or "").split())
    if not text:
        return []
    # first pass: sentence ends
    parts, buf = [], ""
    for ch in text:
        buf += ch
        if ch in _ENDS and len(buf.strip()) > 1:
            parts.append(buf.strip())
            buf = ""
    if buf.strip():
        parts.append(buf.strip())
    # second pass: anything still over the limit gets cut at a comma, then hard
    out: list[str] = []
    for p in parts:
        while len(p) > limit:
            cut = p.rfind(",", 0, limit)
            if cut < limit // 3:
                cut = p.rfind(" ", 0, limit)
            if cut < limit // 3:
                cut = limit
            out.append(p[:cut + 1].strip())
            p = p[cut + 1:].strip()
        if p:
            out.append(p)
    return out


def available() -> bool:
    return bool(TTS_URL) or (os.path.isfile(VOX_EXE) and os.path.isfile(VOX_GGUF))


def status() -> dict:
    n = 0
    if os.path.isdir(CACHE_DIR):
        n = sum(1 for f in os.listdir(CACHE_DIR) if f.endswith(".wav"))
    return {
        "available": available(),
        "backend": "server" if TTS_URL else ("cli" if os.path.isfile(VOX_EXE) else "none"),
        "url": TTS_URL or None,
        "exe": VOX_EXE if not TTS_URL else None,
        "voice": VOICE, "euler_steps": STEPS, "device": DEVICE,
        "cached": n, "cache_dir": CACHE_DIR,
        "warm": bool(TTS_URL),
    }


def _key(text: str, voice: str, steps: int) -> str:
    h = hashlib.sha256(f"{voice}\x00{steps}\x00{text}".encode("utf-8")).hexdigest()
    return h[:32]


def _cache_path(k: str) -> str:
    return os.path.join(CACHE_DIR, f"{k}.wav")


def _trim_cache() -> None:
    """Oldest-first eviction. Audio is regenerable, so this deletes freely — the
    no-delete law is about MEMORY, and a cached waveform is not a memory."""
    try:
        files = [(os.path.getmtime(os.path.join(CACHE_DIR, f)), f)
                 for f in os.listdir(CACHE_DIR) if f.endswith(".wav")]
        for _, f in sorted(files)[:max(0, len(files) - CACHE_MAX)]:
            os.remove(os.path.join(CACHE_DIR, f))
    except OSError:
        pass


def _tune(key, env_key, env_default):
    """OVERRIDE-ONLY: the store answers only if he explicitly chose in the panel;
    otherwise the boot env (the profile) rules. A knob DEFAULT that answered here
    would override the profile on every box, panel touched or not — the gates
    caught exactly that on day one (2026-08-21)."""
    try:
        from harness.tuning import registry as _t
        v = _t.chosen(key)
        if v is not None:
            return v
    except Exception as _swx:
        _swallowed(_swlog, "_tune", _swx, lane="voice")
    return os.environ.get(env_key, env_default)


# THE VOICE METHODS (2026-10-29, LFM3): xai is the remote one; lfm3 and voxtral are
# both on this machine. `local` is no longer an engine — it is "whichever local voice the
# profile chose" ([tts].local -> SP_TTS_LOCAL), so a stored or env `local` keeps working.
METHODS = ("xai", "lfm3", "voxtral")
_LOCALS = ("lfm3", "voxtral")


def live_voice() -> dict:
    """The voice chain's LIVE resolution — what would actually speak right now.
    One reader for synthesize() and the status route, so the panel's chips and
    the next sentence can never disagree."""
    enabled = _tune("voice.enabled", "SP_TTS_ENABLED", "1") in (True, "1", 1)
    local_default = (os.environ.get("SP_TTS_LOCAL", "") or "lfm3").strip().lower()
    if local_default not in _LOCALS:
        local_default = "lfm3"
    method = str(_tune("voice.method", "SP_TTS_METHOD", "")).strip().lower() or "local"
    if method not in METHODS:            # `local`, or a spelling no engine answers to
        method = local_default
    xai_voice = str(_tune("voice.xai_voice", "SP_TTS_XAI_VOICE", "ara"))
    lfm3_voice = str(_tune("voice.lfm3_voice", "SP_LFM3_VOICE", "female") or "female")
    try:
        speed = float(_tune("voice.speed", "SP_TTS_SPEED", "1.0"))
    except (TypeError, ValueError):
        speed = 1.0
    return {"enabled": enabled, "method": method, "local_default": local_default,
            "xai_voice": xai_voice, "lfm3_voice": lfm3_voice,
            "speed": max(0.5, min(1.5, speed)),
            "local_gguf": os.path.basename(VOX_GGUF or ""),      # the Voice section names its model (E)
            "speaking_as": _engine_voice(method, {"xai_voice": xai_voice, "lfm3_voice": lfm3_voice}, None)}


def _engine_voice(engine: str, lv: dict, voice: str | None) -> str:
    """The cache-key spelling of WHO speaks: `xai:<id>`, `lfm3:<female|male>`, or voxtral's
    own voice name. A caller's voice applies to the engine its prefix names; an unprefixed
    one is a voxtral voice (the /v1/speak contract before LFM3)."""
    v = voice or ""
    if engine == "xai":
        return v if v.startswith("xai:") else "xai:" + lv["xai_voice"]
    if engine == "lfm3":
        return v if v.startswith("lfm3:") else "lfm3:" + lv["lfm3_voice"]
    return v if (v and ":" not in v) else VOICE


def _backend_of(voice: str) -> str:
    return voice.split(":", 1)[0] if voice.startswith(("xai:", "lfm3:")) else "voxtral"


def _speak_with(engine: str, text: str, voice: str, steps: int, speed: float) -> bytes:
    """One engine, one utterance. Raises with the engine's own reason; never returns b""."""
    if engine == "xai":
        from harness.skills import xai as _xai
        wav = _xai.tts(text, voice_id=voice.split(":", 1)[1], fmt="wav", speed=speed)
        if not wav:
            raise TTSError(_xai.tts_last_error() or "no audio came back")
        return wav
    if engine == "lfm3":
        from harness.voice import lfm3 as _lfm3
        return _lfm3.speak(text, voice=voice.split(":", 1)[1])
    return _via_server(text, voice, steps) if TTS_URL else _via_cli(text, voice, steps)


def synthesize(text: str, voice: str | None = None, steps: int | None = None,
               use_cache: bool = True) -> tuple[bytes, dict]:
    """text -> (wav_bytes, meta). Raises TTSError with a readable reason."""
    text = (text or "").strip()
    if not text:
        raise TTSError("nothing to say (empty text)")
    if len(text) > MAX_CHARS:
        # Hard refusal, not a silent truncation. The 47-minute run happened because
        # nothing here said no; callers split with split_sentences() and queue.
        raise TTSError(
            f"utterance is {len(text)} chars, over the {MAX_CHARS} limit. Long input "
            f"does not degrade gracefully on this build — it blows up (measured: a "
            f"20 s paragraph ran 47 min at 11.9/12 GB VRAM). Use split_sentences() "
            f"and queue the pieces.")
    # ── LIVE KNOBS FIRST (2026-08-21, the settings window): voice.enabled /
    # voice.method / voice.xai_voice are read from the tuning store on every call,
    # so the room's toggle takes effect on her next sentence — no bounce. The env
    # spellings are the boot defaults the knobs fall back to. The resolution
    # lives in live_voice() — the voice panel's status chips read the SAME
    # function, so what the panel says and what would speak can never disagree.
    lv = live_voice()
    if not lv["enabled"]:
        raise TTSError("voice is off (voice.enabled) — text only")
    _method = lv["method"]
    # ── ANONYMOUS MODE AND HER VOICE (2026-08-24, his question) ──────────────────
    # "does anon mode leak anywhere? eg via voice either local or sent to providers
    # such as the xai api?" It did. `voice.method` is `xai` on his profile, so every
    # sentence she spoke off the record was POSTED TO api.x.ai in full — the one leak
    # he could neither audit nor delete, and much worse than a row on his own disk.
    #
    # A LOCAL VOICE IS NOT A LEAK and is not held: the audio is synthesised on this
    # machine and played. Silencing her would be the mode disabling the room, which
    # is the failure the whole design is written against. A REMOTE voice is held. Until
    # 2026-10-29 it RAISED (the room showed the reason); since then it is skipped and the
    # local voice speaks instead — see below. If nothing local can speak it still raises,
    # with every reason, so "she has gone quiet" is never "she had nothing to say".
    from harness.control import anon as _anon
    # (2026-10-29) lfm3 joined voxtral as a LOCAL voice: only xai leaves the machine, so
    # only xai is held — and the fallback chain below never reaches xai, so a held remote
    # voice cannot be smuggled out through a local one failing.
    # (2026-10-29, operator: "switch to local for OTR, but ensure obviously nothing is logged
    # or kept anywhere") HELD NO LONGER MEANS SILENT. The remote voice is skipped — counted
    # once on net.voice, here, before anything else can run — and the sentence is spoken by
    # the local default instead, the room told why ("xai: off the record"). From here on the
    # chosen method IS the local one: cache key, tags and chain all follow it.
    fell: list[str] = []
    if _method == "xai" and _anon.holds("net.voice"):
        fell.append(off_record_fell(_method))
        _method = OFF_RECORD_VOICE          # the one voice that leaves no trace (voxtral is held)
    otr = _anon.on()
    # THE TTS EDGE (2026-08-21, the expressive-voice framework): her [laugh] / <soft>
    # tags pass to the xAI voice verbatim and are stripped for the local chain, which
    # would read the brackets aloud. Unknown tag-shapes never reach any voice. Done
    # BEFORE the cache key so a tagged and an untagged line are different utterances.
    from harness.voice.expressive import for_tts as _for_tts
    raw = text
    text = _for_tts(text, _method)
    if not text:
        raise TTSError("nothing to say once the tags are removed")
    # The cache key must carry WHICH voice would speak: `xai:ara`, `lfm3:female` and
    # voxtral's `casual_female` are three different recordings of the same words — one
    # key for two of them would serve her old voice from cache after a switch.
    # _engine_voice() spells each one apart.
    voice = _engine_voice(_method, lv, voice)
    steps = STEPS if steps is None else steps
    k = _key(text, voice, steps)
    path = _cache_path(k)

    if use_cache and os.path.isfile(path):
        with open(path, "rb") as f:
            return f.read(), {"cached": True, "key": k, "seconds": 0.0, "voice": voice,
                              "backend": _backend_of(voice), "fell_back_from": "; ".join(fell)}

    # ── THE CHAIN, AND IT SAYS WHO SPOKE (2026-10-29) ─────────────────────────────────
    # Chosen method -> the profile's local default -> voxtral. Grok went silent on him
    # with nothing in the room saying why; now every engine that fails leaves its reason
    # ("xai: http 402: ..."), meta names the engine that actually spoke, and /v1/speak
    # hands both to the room. Each fallback re-strips the tags from the RAW text for
    # its own engine — a local voice handed xai's tagged line would read "[laugh]" aloud.
    chain = []
    # off the record lfm3 is always in the chain — it is the one voice that leaves no trace,
    # so a voxtral local default (held) must not leave her silent while lfm3 could speak
    for e in (_method, lv["local_default"]) + ((OFF_RECORD_VOICE,) if otr else ()) + ("voxtral",):
        if e not in chain:
            chain.append(e)
    t0 = time.perf_counter()
    # ONE VOICE AT A TIME (operator, 2026-10-29): every engine — xai, lfm3, voxtral —
    # synthesises inside this one lock. It is about ordering, not just GPU contention.
    with _LOCK:
        # re-check: another thread may have synthesised the same line while we waited
        if use_cache and os.path.isfile(path):
            with open(path, "rb") as f:
                return f.read(), {"cached": True, "key": k, "seconds": 0.0, "voice": voice,
                                  "backend": _backend_of(voice), "fell_back_from": "; ".join(fell)}
        # ── THE API VOICE COMES FIRST WHEN ARMED (2026-08-21, operator's call) ──────
        # MEASURED on the first probe: 1.1 s for a sentence, real 24 kHz WAV, ZERO VRAM.
        # Fail-through, never fail-dead: a dark Grok falls to the local chain — she never
        # loses her voice to an outage, it just changes, and now the room is told.
        backend = ""
        for eng in chain:
            etext = text if eng == _method else _for_tts(raw, eng)
            evoice = voice if eng == _method else _engine_voice(eng, lv, None)
            if not etext:
                fell.append("%s: nothing to say once the tags are removed" % eng)
                continue
            if eng != _method:
                k = _key(etext, evoice, steps)
                path = _cache_path(k)
                if use_cache and os.path.isfile(path):
                    with open(path, "rb") as f:
                        wav = f.read()
                    return wav, {"cached": True, "key": k, "seconds": 0.0, "voice": evoice,
                                 "backend": eng, "fell_back_from": "; ".join(fell)}
            # VOXTRAL LEAVES A TRACE, SO OFF THE RECORD IT IS HELD (2026-10-29 audit). Its
            # CLI can only write to a file (`--output x.wav`, a temp wav on disk), and its
            # resident server prints the first 48 characters of every sentence to its own
            # log (voxtral-mini-realtime-rs, src/bin/tts-server.rs). Neither can be told not
            # to from here. Arming condition: tts-server stops logging the text — then the
            # server leg can run off the record (docs/ANON-MODE.md).
            if otr and eng == "voxtral":
                fell.append(off_record_fell(eng))
                continue
            _SPEAKING[0] = eng
            try:
                wav = _speak_with(eng, etext, evoice, steps, speed=lv["speed"])
            except Exception as e:
                if otr:
                    # an engine may quote her sentence back in its error: off the record a
                    # swallowed error is logged, and handed to the room, without it
                    _swallowed(_swlog, "synthesize:" + eng, _HeldError(type(e).__name__), lane="voice")
                    fell.append("%s: %s" % (eng, type(e).__name__))
                else:
                    _swallowed(_swlog, "synthesize:" + eng, e, lane="voice")
                    fell.append("%s: %s" % (eng, str(e) or type(e).__name__))
                continue
            finally:
                _SPEAKING[0] = ""
            backend, voice = eng, evoice
            break
        if not backend:
            raise TTSError("no voice could speak — " + "; ".join(fell))
    dt = time.perf_counter() - t0

    # A CACHED WAV IS A RECORDING. Keyed by a hash of the text, but the FILE is her
    # voice saying the private thing, and it outlives the mode by design (the cache
    # is trimmed by size, not by age). Held; she still speaks, the bytes go to the
    # room and nowhere else. A cache READ is left alone: a hit means she has said
    # this before, on the record, so there is nothing new to protect.
    # The write lands under the key of the engine that SPOKE, so a fallback's audio is
    # never served later as if the chosen voice had made it.
    if use_cache and not _anon.holds("voice.cache"):
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            f.write(wav)
        replace_atomic(tmp, path)          # atomic: a reader never sees a partial wav
        _trim_cache()
    return wav, {"cached": False, "key": k, "seconds": round(dt, 2), "voice": voice,
                 "backend": backend, "fell_back_from": "; ".join(fell)}


def _via_server(text: str, voice: str, steps: int) -> bytes:
    body = json.dumps({"text": text, "voice": voice, "euler_steps": steps}).encode()
    req = urllib.request.Request(f"{TTS_URL}/speak", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read()
    except urllib.error.URLError as e:
        raise TTSError(f"tts server at {TTS_URL} unreachable: {e}") from None


def _via_cli(text: str, voice: str, steps: int) -> bytes:
    if not os.path.isfile(VOX_EXE):
        raise TTSError(f"no voxtral binary at {VOX_EXE} (set SP_TTS_EXE)")
    if not os.path.isfile(VOX_GGUF):
        raise TTSError(f"no TTS weights at {VOX_GGUF} (set SP_TTS_GGUF)")
    out = os.path.join(tempfile.gettempdir(), f"sp_tts_{os.getpid()}_{int(time.time()*1000)}.wav")
    argv = [VOX_EXE, "speak", "--gguf", VOX_GGUF, "--text", text,
            "--voice", voice, "--euler-steps", str(steps),
            "--device", DEVICE, "--output", out]
    try:
        r = subprocess.run(argv, capture_output=True, text=True,
                           timeout=TIMEOUT, cwd=VOX_ROOT)
    except subprocess.TimeoutExpired:
        raise TTSError(f"voxtral timed out after {TIMEOUT}s") from None
    if r.returncode != 0 or not os.path.isfile(out):
        tail = ((r.stderr or "") + (r.stdout or "")).strip().splitlines()
        raise TTSError("voxtral failed: " + (tail[-1] if tail else f"exit {r.returncode}"))
    try:
        with open(out, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(out)
        except OSError:
            pass


def prewarm(text: str = "Mm.") -> dict:
    """Pay the load and shader-compile cost NOW, on a throwaway line, so the first
    real thing she says is not the slowest. Called at stack start."""
    try:
        _, meta = synthesize(text, use_cache=True)
        return {"ok": True, **meta}
    except Exception as e:
        return {"ok": False, "error": str(e)}
