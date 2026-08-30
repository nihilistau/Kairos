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
    except Exception:
        pass
    return os.environ.get(env_key, env_default)


def live_voice() -> dict:
    """The voice chain's LIVE resolution — what would actually speak right now.
    One reader for synthesize() and the status route, so the panel's chips and
    the next sentence can never disagree."""
    enabled = _tune("voice.enabled", "SP_TTS_ENABLED", "1") in (True, "1", 1)
    method = str(_tune("voice.method", "SP_TTS_METHOD", "")).strip() or "local"
    xai_voice = str(_tune("voice.xai_voice", "SP_TTS_XAI_VOICE", "ara"))
    try:
        speed = float(_tune("voice.speed", "SP_TTS_SPEED", "1.0"))
    except (TypeError, ValueError):
        speed = 1.0
    return {"enabled": enabled, "method": method, "xai_voice": xai_voice,
            "speed": max(0.5, min(1.5, speed)),
            "local_gguf": os.path.basename(VOX_GGUF or ""),      # the Voice section names its model (E)
            "speaking_as": ("xai:" + xai_voice) if method == "xai" else VOICE}


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
    # is the failure the whole design is written against. A REMOTE voice is held, and
    # it RAISES rather than returning silence — the room shows the reason, so "she has
    # gone quiet" can never be mistaken for "she had nothing to say".
    from harness.control import anon as _anon
    if _method != "local" and _anon.holds("net.voice"):
        raise TTSError(
            "off the record — her voice is %s, which would send this sentence to a "
            "third party. Switch voice.method to local to hear her while the switch "
            "is on." % _method)
    # THE TTS EDGE (2026-08-21, the expressive-voice framework): her [laugh] / <soft>
    # tags pass to the xAI voice verbatim and are stripped for the local chain, which
    # would read the brackets aloud. Unknown tag-shapes never reach any voice. Done
    # BEFORE the cache key so a tagged and an untagged line are different utterances.
    from harness.voice.expressive import for_tts as _for_tts
    text = _for_tts(text, _method)
    if not text:
        raise TTSError("nothing to say once the tags are removed")
    voice = voice or VOICE
    # The cache key must carry WHICH voice would speak: under method=xai the audible
    # voice is Ara (or the knob), not the voxtral voice name — one key for both
    # would serve her old voice from cache after the switch, or the new one after
    # a rollback. The "xai:" prefix keys them apart for free.
    if _method == "xai" and not (voice or "").startswith("xai:"):
        voice = "xai:" + lv["xai_voice"]
    steps = STEPS if steps is None else steps
    k = _key(text, voice, steps)
    path = _cache_path(k)

    if use_cache and os.path.isfile(path):
        with open(path, "rb") as f:
            return f.read(), {"cached": True, "key": k, "seconds": 0.0, "voice": voice}

    t0 = time.perf_counter()
    backend = "server" if TTS_URL else "cli"
    with _LOCK:
        # re-check: another thread may have synthesised the same line while we waited
        if use_cache and os.path.isfile(path):
            with open(path, "rb") as f:
                return f.read(), {"cached": True, "key": k, "seconds": 0.0, "voice": voice}
        # ── THE API VOICE COMES FIRST WHEN ARMED (2026-08-21, operator's call) ──────
        # SP_TTS_METHOD=xai: POST api.x.ai/v1/tts, voice "ara" by default. MEASURED on
        # the first probe: 1.1 s for a sentence, real 24 kHz WAV, ZERO VRAM — against
        # voxtral's 21-28 s warm and the 2026-07-31 CUDA fault a resident voice cost.
        # It goes through the same cache and the same one-at-a-time lock (the lock is
        # now about ordering, not GPU contention). Fail-through, never fail-dead: an
        # empty reply (key gone, API down, network) falls to the local chain exactly
        # as if the method had never been set — she never loses her voice to an
        # outage, it just gets slower.
        wav = b""
        if _method == "xai":
            try:
                from harness.skills import xai as _xai
                wav = _xai.tts(text, voice_id=voice.split(":", 1)[1] if ":" in voice else "",
                               fmt="wav", speed=lv["speed"])
                if wav:
                    backend = "xai"
            except Exception:
                wav = b""
        if not wav:
            # the local chain never sees the "xai:" spelling — it has its own voices
            lvoice = VOICE if voice.startswith("xai:") else voice
            wav = _via_server(text, lvoice, steps) if TTS_URL else _via_cli(text, lvoice, steps)
    dt = time.perf_counter() - t0

    # A CACHED WAV IS A RECORDING. Keyed by a hash of the text, but the FILE is her
    # voice saying the private thing, and it outlives the mode by design (the cache
    # is trimmed by size, not by age). Held; she still speaks, the bytes go to the
    # room and nowhere else. A cache READ is left alone: a hit means she has said
    # this before, on the record, so there is nothing new to protect.
    if use_cache and not _anon.holds("voice.cache"):
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            f.write(wav)
        replace_atomic(tmp, path)          # atomic: a reader never sees a partial wav
        _trim_cache()
    return wav, {"cached": False, "key": k, "seconds": round(dt, 2), "voice": voice,
                 "backend": backend}


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
