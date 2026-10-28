"""lfm3.py — the ONE client for the LFM3-Audio server: her ears (transcribe) and her local voice (speak).

One resident llama-server (CPU, `--mmproj`) serves both (docs/bench/2026-10-29-lfm3-spike.md):
  ASR  POST /v1/chat/completions  system "Perform ASR in English." + an `input_audio` part, temp 0
  TTS  POST /tts  {"input", "voice"} -> a 24 kHz mono WAV body
Env is read PER CALL (the serve.py restart lesson). Unlike the sidecar client, failure here RAISES
LFM3Error(reason): tts.py turns that into a fallback that says why, and the ears path surfaces it.

His recorded audio is resampled in memory and sent to localhost only — nothing is written to disk.
"""
from __future__ import annotations

import base64
import io
import json
import os
import urllib.error
import urllib.request
import warnings
import wave

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)  # audioop: gone in 3.13; fine on the 3.11 floor
    import audioop

_ASR_RATE = 16000
_TIMEOUT_ASR = 120
_TIMEOUT_TTS = 180
_LANGS = {"en": "English", "es": "Spanish", "fr": "French", "de": "German", "it": "Italian",
          "pt": "Portuguese", "ja": "Japanese", "ko": "Korean", "zh": "Chinese", "ar": "Arabic"}


class LFM3Error(RuntimeError):
    """The reason is the message: `off`, `missing ...`, `loading`, or what the server said."""


_HERE = ("127.0.0.1", "localhost", "::1")


def on_this_machine(url: str) -> bool:
    """True when `url` names this machine (127.0.0.1 / localhost / ::1) and nothing else."""
    try:
        from urllib.parse import urlsplit
        return (urlsplit(url).hostname or "") in _HERE
    except ValueError:
        return False


def _url() -> str:
    """THIS MACHINE ONLY (final review, 2026-10-29). serve.py's _lfm3_door binds 127.0.0.1
    whatever [lfm3].audio_url says, so a URL naming another host is never her door — and
    following it would send his recorded voice across the network. It fails loudly instead."""
    u = os.environ.get("SP_LFM3_AUDIO_URL", "http://127.0.0.1:8813").rstrip("/")
    if not on_this_machine(u):
        raise LFM3Error("audio_url is not on this machine (%s)" % u)
    return u


def _lang() -> str:
    return os.environ.get("SP_LFM3_LANG", "en") or "en"


def _voice() -> str:
    """The panel's choice if he made one, else the profile (registry.tune_or_env)."""
    try:
        from harness.tuning import registry as _tr
        return str(_tr.tune_or_env("voice.lfm3_voice", "SP_LFM3_VOICE", "female") or "female")
    except Exception as _swx:
        _swallowed(_swlog, "_voice", _swx, lane="voice")
        return os.environ.get("SP_LFM3_VOICE", "female") or "female"


def _GET(url: str, timeout: int = 5) -> int:
    """HTTP status of a GET; 0 when nothing answers. (Test seam.)"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as _swx:
        _swallowed(_swlog, "_GET", _swx, lane="voice")
        return 0


def _POST(url: str, body: dict, timeout: int = 120) -> bytes:
    """POST JSON, return the response body; raises LFM3Error on any failure. (Test seam.)"""
    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise LFM3Error("server answered %d" % e.code) from e
    except Exception as e:
        raise LFM3Error("server unreachable: %s" % type(e).__name__) from e


def status() -> dict:
    gguf = os.environ.get("SP_LFM3_AUDIO_GGUF", "")
    mm = os.environ.get("SP_LFM3_AUDIO_MMPROJ", "")
    out = {"state": "off", "model": gguf, "mmproj": mm, "why": "", "voice": _voice()}
    if os.environ.get("SP_LFM3", "") != "1":
        out["why"] = "SP_LFM3 is not 1"
        return out
    for p in (gguf, mm):
        if not p or not os.path.exists(p):
            out.update(state="missing", why="file not found: %s" % (p or "(unset)"))
            return out
    try:
        url = _url()
    except LFM3Error as e:
        out.update(state="error", why=str(e))
        return out
    code = _GET(url + "/health")
    if code == 200:
        out["state"] = "loaded"
    elif code == 503:
        out.update(state="loading", why="loading")
    else:
        out.update(state="error", why="health answered %s" % (code or "nothing"))
    return out


def ready() -> bool:
    return status()["state"] == "loaded"


def _require_ready() -> None:
    st = status()
    if st["state"] != "loaded":
        raise LFM3Error("%s%s" % (st["state"], (": " + st["why"]) if st["why"] and st["why"] != st["state"] else ""))


def _to_16k_mono(wav: bytes) -> bytes:
    try:
        with wave.open(io.BytesIO(wav), "rb") as w:
            ch, width, rate, pcm = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.readframes(w.getnframes())
    except Exception as e:
        raise LFM3Error("not a PCM WAV: %s" % type(e).__name__) from e
    if ch > 1:
        pcm = audioop.tomono(pcm, width, 0.5, 0.5) if ch == 2 else audioop.tomono(pcm[: len(pcm) // ch * ch], width, 1, 0)
    if width != 2:
        pcm = audioop.lin2lin(pcm, width, 2)
    if rate != _ASR_RATE:
        pcm, _ = audioop.ratecv(pcm, 2, 1, rate, _ASR_RATE, None)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_ASR_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def transcribe(wav: bytes) -> str:
    """Any PCM WAV in, text out. Resampled to 16 kHz mono in memory; temp 0."""
    _require_ready()
    data = base64.b64encode(_to_16k_mono(wav)).decode("ascii")
    body = {
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "Perform ASR in %s." % _LANGS.get(_lang().lower()[:2], "English")},
            {"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": data, "format": "wav"}}]},
        ],
    }
    raw = _POST(_url() + "/v1/chat/completions", body, _TIMEOUT_ASR)
    try:
        return str(json.loads(raw)["choices"][0]["message"]["content"] or "").strip()
    except Exception as e:
        raise LFM3Error("unreadable ASR reply: %s" % type(e).__name__) from e


def speak(text: str, voice: str = "", lang: str = "") -> bytes:
    """24 kHz WAV bytes. `lang` is accepted for the caller's symmetry; the server's /tts takes only
    text and voice (the spike), so it does not change the request."""
    if not (text or "").strip():
        raise LFM3Error("nothing to say")
    _require_ready()
    out = _POST(_url() + "/tts", {"input": text, "voice": voice or _voice()}, _TIMEOUT_TTS)
    if out[:4] != b"RIFF":
        raise LFM3Error("the server's /tts reply was not a WAV")
    return out
