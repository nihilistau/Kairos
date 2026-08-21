"""xai.py — ONE transport for the xAI API: key, chat, images, video, speech.

WRITTEN AGAINST THE REST DOCS (docs.x.ai, fetched 2026-08-21), replacing the Grok
CLI agent as the generation backend. The CLI was probed-and-working but carried the
worst dependency shape in this repo: a GUI login's auth.json, an undocumented agent
interface, and "ask the agent and hope it writes the file". The REST API is a
contract; this module is its one door.

THE KEY IS A FILE, NEVER A VALUE. SP_XAI_KEY_FILE points at var/secrets/ (ignored);
this repo is public. The old env spellings (SP_XAI_API_KEY / XAI_API_KEY) still win
when set — host-env keys were already an announced HOST_KEYS exception.

EMPTY IS EMPTY. A dead API returns None/b""/[] and the caller says so. Every helper
is synchronous and honest about cost: images are ~seconds, video is an async JOB
(submit -> poll), speech is ~a second. Receipts are the CALLER's job — this module
does transport, not bookkeeping.

Endpoints (all under https://api.x.ai/v1):
    POST /chat/completions      chat (research uses /responses via research.py)
    POST /images/generations    model grok-imagine-image-2.0 -> b64 or url
    POST /videos/generations    model grok-imagine-video-1.5, image-in -> request_id
    GET  /videos/{request_id}   poll: pending/done/failed + video.url
    POST /tts                   voice_id (ara/eve/...), wav/mp3 out, base64 in JSON
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

BASE = "https://api.x.ai/v1"

IMAGE_MODEL = os.environ.get("SP_XAI_IMAGE_MODEL", "grok-imagine-image-2.0")
VIDEO_MODEL = os.environ.get("SP_XAI_VIDEO_MODEL", "grok-imagine-video-1.5")


def image_model() -> str:
    """WHICH IMAGINE ANSWERS, per call (2026-08-21). His panel pick — override-only,
    tune.chosen(), so an untouched panel leaves the profile's boot default alone —
    else the env that IMAGE_MODEL froze at import. Read per call because avatar_gen
    runs as a subprocess: the store file is what crosses the process line."""
    try:
        from harness.tuning import registry as _tune
        c = _tune.chosen("xai.image_model")
        if c:
            return str(c)
    except Exception:
        pass
    return IMAGE_MODEL


def video_model() -> str:
    """Same rule as image_model, for the motion half."""
    try:
        from harness.tuning import registry as _tune
        c = _tune.chosen("xai.video_model")
        if c:
            return str(c)
    except Exception:
        pass
    return VIDEO_MODEL


def api_key() -> str:
    """Env spellings first (announced HOST_KEYS), then the key FILE."""
    k = (os.environ.get("SP_XAI_API_KEY") or os.environ.get("XAI_API_KEY") or "").strip()
    if k:
        return k
    p = os.environ.get("SP_XAI_KEY_FILE", "")
    if not p:
        _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        p = os.path.join(_root, "var", "secrets", "Xapi.txt")
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def available() -> bool:
    return bool(api_key())


_LAST_ERROR: List[str] = [""]     # the most recent failure's text, for callers that
                                  # must tell a rate limit from an ordinary failure
                                  # (avatar_gen's delayed-vs-asked ruling)


def last_error() -> str:
    return _LAST_ERROR[0]


def _post(path: str, body: dict, timeout: float = 120.0) -> Optional[dict]:
    k = api_key()
    if not k:
        _LAST_ERROR[0] = "no api key"
        return None
    try:
        req = urllib.request.Request(
            BASE + path, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + k})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            _LAST_ERROR[0] = ""
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            _LAST_ERROR[0] = ("http %d: " % e.code) + e.read().decode("utf-8", "replace")[:300]
        except Exception:
            _LAST_ERROR[0] = "http %d" % e.code
        return None
    except Exception as exc:
        _LAST_ERROR[0] = "%s: %s" % (type(exc).__name__, str(exc)[:200])
        return None


def _get(path: str, timeout: float = 60.0) -> Optional[dict]:
    k = api_key()
    if not k:
        return None
    try:
        req = urllib.request.Request(BASE + path,
                                     headers={"Authorization": "Bearer " + k})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def _fetch(url: str, timeout: float = 120.0) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read()
    except Exception:
        return b""


# ── SPEECH ───────────────────────────────────────────────────────────────────────


def tts(text: str, voice_id: str = "", fmt: str = "wav",
        speed: float = 1.0, timeout: float = 60.0) -> bytes:
    """Text -> audio bytes in `fmt` (wav for the room's player, mp3 if asked).
    b'' on any failure — the voice stack falls through to the local method."""
    if not (text or "").strip():
        return b""
    body = {
        "text": text[:15000],
        "voice_id": voice_id or os.environ.get("SP_TTS_XAI_VOICE", "ara"),
        "language": "en",
        "output_format": {"codec": fmt, "sample_rate": 24000},
    }
    if speed and speed != 1.0:
        body["speed"] = float(speed)
    # MEASURED 2026-08-21: the endpoint returns RAW AUDIO BYTES (RIFF/ID3/MP3 frame),
    # not the docs' {"audio": <base64>} JSON. Accept both shapes — the docs' shape may
    # yet ship, and a probe against the real API beats a probe against its manual.
    k = api_key()
    if not k:
        return b""
    try:
        req = urllib.request.Request(
            BASE + "/tts", data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + k})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except Exception:
        return b""
    if not raw:
        return b""
    if raw[:4] in (b"RIFF", b"ID3\x03", b"ID3\x04") or raw[:2] == b"\xff\xfb" \
            or raw[:4] == b"OggS":
        return raw
    try:
        d = json.loads(raw.decode("utf-8", "replace"))
        return base64.b64decode(d.get("audio", "")) if d.get("audio") else b""
    except Exception:
        return raw          # unknown container: hand it to the player as-is


# ── IMAGES ───────────────────────────────────────────────────────────────────────


def image(prompt: str, aspect_ratio: str = "1:1", resolution: str = "1k",
          n: int = 1, timeout: float = 180.0) -> List[bytes]:
    """Prompt -> list of PNG/JPEG bytes (b64 transport; nothing touches disk here).
    [] on failure. The identity clause and the reference belong to the PROMPT the
    caller builds (avatar_gen's character.txt discipline is unchanged)."""
    if not (prompt or "").strip():
        return []
    d = _post("/images/generations", {
        "model": image_model(), "prompt": prompt, "n": max(1, int(n)),
        "aspect_ratio": aspect_ratio, "resolution": resolution,
        "response_format": "b64_json"}, timeout)
    if not d or "data" not in d:
        return []
    out: List[bytes] = []
    for row in d.get("data", []):
        b64 = row.get("b64_json")
        if b64:
            try:
                out.append(base64.b64decode(b64))
                continue
            except Exception:
                pass
        if row.get("url"):
            blob = _fetch(row["url"])
            if blob:
                out.append(blob)
    return out


def image_edit(prompt: str, image_file_id: str = "", image_url: str = "",
               timeout: float = 240.0) -> bytes:
    """Edit FROM a source image — the identity anchor. PROBED 2026-08-21: the
    endpoint takes {"image": {"file_id"|"url"}} (b64 refused with a 400 naming
    the two accepted forms), returns data[0].b64_json or .url. b'' on failure.
    The identity clause belongs to the PROMPT; the source image is what makes
    "the same woman" mean the same woman."""
    if not (prompt or "").strip():
        return b""
    body: Dict[str, Any] = {"model": image_model(), "prompt": prompt,
                            "response_format": "b64_json"}
    if image_file_id:
        body["image"] = {"file_id": image_file_id}
    elif image_url:
        body["image"] = {"url": image_url}
    else:
        return b""
    d = _post("/images/edits", body, timeout)
    if not d or not d.get("data"):
        return b""
    row = d["data"][0]
    if row.get("b64_json"):
        try:
            return base64.b64decode(row["b64_json"])
        except Exception:
            return b""
    if row.get("url"):
        return _fetch(row["url"])
    return b""


_REF_CACHE: Dict[str, str] = {}     # sha1(path bytes) -> file_id, per process


def reference_file_id(path: str) -> str:
    """Upload-once file_id for a local reference image, keyed by content hash so a
    changed reference re-uploads and a rerun does not. '' on failure."""
    import hashlib
    try:
        raw = open(path, "rb").read()
    except Exception:
        return ""
    h = hashlib.sha1(raw).hexdigest()
    fid = _REF_CACHE.get(h, "")
    if fid:
        return fid
    fid = upload_image(path)
    if fid:
        _REF_CACHE[h] = fid
    return fid


# ── VIDEO (async job: submit -> poll) ────────────────────────────────────────────


def video_submit(prompt: str, image_url: str = "", image_file_id: str = "",
                 duration: int = 6, aspect_ratio: str = "1:1",
                 resolution: str = "480p") -> str:
    """Submit an image->video (or text->video) job. Returns request_id or ''.
    MOTION IS GROWN FROM THE STILL: pass the approved still via image_*, never
    generate frames independently — independently generated frames are
    independently generated PEOPLE (avatar.py's own law, kept under the API)."""
    body: Dict[str, Any] = {
        "model": video_model(), "prompt": prompt or "subtle natural motion",
        "duration": max(1, min(15, int(duration))),
        "aspect_ratio": aspect_ratio, "resolution": resolution,
    }
    if image_url:
        body["image"] = {"url": image_url}
    elif image_file_id:
        body["image"] = {"file_id": image_file_id}
    d = _post("/videos/generations", body, 60.0)
    if not d:
        return ""
    return str(d.get("request_id") or d.get("id") or "")


def video_poll(request_id: str) -> Dict[str, Any]:
    """One poll. {'status': pending|done|failed|unknown, 'progress': int, 'url': str}."""
    if not request_id:
        return {"status": "unknown", "progress": 0, "url": ""}
    d = _get("/videos/" + request_id)
    if not d:
        return {"status": "unknown", "progress": 0, "url": ""}
    vid = d.get("video") or {}
    return {"status": d.get("status", "unknown"),
            "progress": int(d.get("progress") or 0),
            "url": vid.get("url", "")}


def video(prompt: str, image_url: str = "", duration: int = 6,
          aspect_ratio: str = "1:1", resolution: str = "480p",
          timeout: float = 600.0, poll_s: float = 5.0) -> bytes:
    """Submit + poll + fetch, one call. b'' on failure or timeout."""
    rid = video_submit(prompt, image_url=image_url, duration=duration,
                       aspect_ratio=aspect_ratio, resolution=resolution)
    if not rid:
        return b""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        st = video_poll(rid)
        if st["status"] == "done" and st["url"]:
            return _fetch(st["url"])
        if st["status"] == "failed":
            return b""
        time.sleep(poll_s)
    return b""


# ── FILE UPLOAD (for image->video from a LOCAL still) ────────────────────────────


def upload_image(path: str, timeout: float = 120.0) -> str:
    """Upload a local image, return its file_id ('' on failure). Multipart by hand —
    the one place urllib needs help; no new dependency for one endpoint."""
    try:
        raw = open(path, "rb").read()
    except Exception:
        return ""
    k = api_key()
    if not k or not raw:
        return ""
    boundary = "----spkairos%d" % int(time.time() * 1000)
    name = os.path.basename(path)
    ctype = "image/png" if name.lower().endswith(".png") else "image/jpeg"
    body = (("--%s\r\nContent-Disposition: form-data; name=\"file\"; "
             "filename=\"%s\"\r\nContent-Type: %s\r\n\r\n" % (boundary, name, ctype))
            .encode("utf-8") + raw + ("\r\n--%s--\r\n" % boundary).encode("utf-8"))
    try:
        req = urllib.request.Request(
            BASE + "/files", data=body,
            headers={"Authorization": "Bearer " + k,
                     "Content-Type": "multipart/form-data; boundary=" + boundary})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        return str(d.get("id") or d.get("file_id") or "")
    except Exception:
        return ""
