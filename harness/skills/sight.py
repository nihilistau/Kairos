"""sight.py — her eyes, as tools she can reach for.

THREE TOOLS, ONE SHAPE: capture pixels, run them through the model's own vision
tower (harness/senses/vision.py), inject the soft tokens at image token 258880,
and return what she saw as text.

WHY THE TOOL DOES THE FULL ROUND TRIP. Frames cannot be handed back through a
tool result — a tool returns a string, and the injection happens at the request
layer. Rather than thread a pending-frames buffer through the whole chat path
(and risk it leaking into a turn nobody asked for), each tool makes its own
daemon call with the frames attached and returns the description. Looking is one
complete act with a beginning and an end, which is also the honest shape for a
sense: she asked to look, she looked, here is what was there.

CAPTURE IS EXPLICIT, ALWAYS. Nothing here runs on a tick or a heartbeat. A camera
that might be on is a different object in a house than one that turns on when
asked, and no amount of convenience is worth blurring that.

Costs, measured on this box: ~5 s to encode, plus one daemon turn.
"""
from __future__ import annotations

import json
import os
import urllib.request

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

_DAEMON = os.environ.get("SP_DAEMON_URL", "http://127.0.0.1:3000").rstrip("/")

# eot_bias at its default of 4 biases hard toward end-of-turn and the reply comes
# back as a bare `<channel|>`. The voice path has passed 1.0 since it was built;
# this cost two rounds of debugging before it was noticed.
# repetition_penalty is NOT optional here. Without it an open-ended "describe this
# completely" degenerates into "line-work-work; thoughtful-thoughtful-thoug" and she
# reports only the first thing she saw. 1.15 is what harness/voice/service.py uses on
# the audio path for the same reason. Measured: with it, all three shapes; without,
# one shape and word salad.
_LOOK = {"max_tokens": 220, "byteexact": False, "temperature": 0.3,
         "eot_bias": 0.0, "repetition_penalty": 1.15}


def _look_tokens() -> int:
    """The description's token CEILING — not a target; a one-sentence answer still
    stops at one sentence (decode.max_tokens' own lesson).

    2026-08-21, the operator's report: he attached a photo of her in the white jumper and her
    description arrived truncated. The chip was the obvious suspect and was
    innocent — it slices for display at its own edge ([:400], app.py) while she
    gets the full string. The cut was HERE: 220 tokens, sized for the hourly
    room sentence, silently capping "describe this plainly and completely"
    mid-thought. 512 default now; his knob (senses.look_tokens) rules live."""
    try:
        from harness.tuning import registry as tune
        c = tune.chosen("senses.look_tokens")
        if c is not None:
            return max(64, min(2048, int(c)))
    except Exception as _swx:
        _swallowed(_swlog, "_look_tokens", _swx, lane="skills")
    try:
        return max(64, min(2048, int(os.environ.get("SP_SIGHT_LOOK_TOKENS", "512"))))
    except ValueError:
        return 512


def _backend() -> str:
    """Which eyes (Sight — her eyes, 2026-08-22): engine | aux_vl | openai; engine = today's logic."""
    try:
        from harness.tuning import registry as _tr
        b = str(_tr.get("sight.backend", "engine") or "engine")
        return b if b in ("engine", "aux_vl", "openai") else "engine"
    except Exception:
        return "engine"


def _describe(img, question: str, detail: int | None = None) -> str:
    """pixels + a question -> what she saw. Raises with a readable reason.

    `detail` is the soft-token budget: 280 (default) or 1120 for anything whose
    content is small. At 280 tokens a 1912x1072 screen gets ~48 px per token after
    3x3 pooling, which is fine for a room and useless for 12 px text — measured:
    screenshots at 280 came back as "Please provide more context" or word salad,
    which reads like a broken encoder and is actually just an under-resolved
    picture. 1120 is ~4x the compute and near-native for a screen."""
    from harness.senses import vision
    from harness.inference.inference_config import InferenceConfig
    # NO RESIDUAL FRAMES ON A FOREIGN ENGINE (2026-08-21): if the backend declares
    # vision_openai, the picture goes as a standard image_url content part through the
    # same client everything else uses; if it declares neither, she is told plainly.
    try:
        from harness.inference.backends import supports as _sup
        _frames_ok = _sup("inject_frames")
    except Exception:
        _frames_ok = True
    backend = _backend()
    if backend == "aux_vl":
        # HER EYES THROUGH THE LIBRARIANS' DOOR (2026-08-22, E): an LFM2.5-VL model on the aux
        # chat door; the 2060 stays the model's. Same scrub as every other eye.
        from harness.skills import sight_vl as _vl
        if not _vl.vl_model() or not _vl.door_up():
            return ("[sight is not available — the VL door is dark or no VL model is chosen "
                    "(Sight — her eyes)]")
        raw = _vl.describe(img, question, max_tokens=_vl.vl_max_tokens(), detail=_vl.vl_detail())
        return _scrub(raw) if raw else "[sight error: the VL door returned nothing]"
    if backend == "openai" or (backend == "engine" and not _frames_ok):
        if not _sup("vision_openai"):
            return "[sight is not available on this engine — no frame injection and no image_url vision]"
        import base64 as _b64, io as _io
        from PIL import Image as _PIL
        buf = _io.BytesIO(); _PIL.fromarray(img).save(buf, format="PNG")
        url = "data:image/png;base64," + _b64.b64encode(buf.getvalue()).decode("ascii")
        from harness.inference.client import get_client
        cfg = InferenceConfig(**{**_LOOK, "max_tokens": _look_tokens()})
        r = get_client().chat(messages=[{"role": "user", "content": [
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": {"url": url}}]}], config=cfg)
        return _scrub(r.text or "")
    frames = vision.encode(img, max_soft=detail)
    # THROUGH THE ONE DOOR. g_byteexact caught this file hand-building a /v1/chat
    # body — the exact "second door" that let `<channel|>` into her journal and
    # that made every non-gateway lane get an empty 200 from the MoE seam. Every
    # sampler default and the byteexact resolution now come from the same builder
    # the rest of the tree uses; tthe operator's call only ADDS the two fields that are
    # genuinely its own.
    req_body = InferenceConfig(**{**_LOOK, "max_tokens": _look_tokens()}).to_sp_chat(
        messages=[{"role": "user", "content": question}])
    req_body["inject_frames"] = frames.tolist()
    req_body["inject_ph"] = int(vision.cap.for_model().vision["image_token"])
    body = json.dumps(req_body).encode()
    req = urllib.request.Request(f"{_DAEMON}/v1/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    out: list[str] = []
    with urllib.request.urlopen(req, timeout=600) as r:
        for line in r:
            s = line.decode("utf-8", "replace").strip()
            if not s.startswith("data:"):
                continue
            p = s[5:].strip()
            if p == "[DONE]":
                break
            try:
                d = json.loads(p)
            except Exception:
                continue
            if "delta" in d:
                out.append(d["delta"])
            if "error" in d:
                return f"[sight error: {d['error']}]"
    text = "".join(out).strip()
    return _scrub(text)


def _scrub(text: str) -> str:
    """Post-processing shared by EVERY eye (2026-08-22): the engine's frames, the seam's image_url
    and the VL door all come through here — one function, so a planted <channel|> or a thinking
    prefix is stripped the same whichever model looked."""
    text = (text or "").strip()
    # THE THOUGHT CHANNEL IS NOT THE ANSWER. This is a RAW daemon call, so it
    # bypasses the gateway's stream_processor and the private channel arrives
    # verbatim. Everything up to and including the close marker is scratch — take
    # what comes AFTER it, not the whole string with the marker deleted, which is
    # what leaked "- Blue circle, blue deen ( -thought" into a description.
    for marker in ("<channel|>", "<|think|>"):
        if marker in text:
            text = text.split(marker)[-1]
    # ...and then the REAL stripper. harness/inference/stream_processor.py exists
    # precisely for this and handles the unterminated `<thought ` case that cost a
    # commit of its own; a raw daemon call bypasses the gateway, so call it here
    # rather than re-inventing a worse version.
    try:
        from harness.inference.stream_processor import strip_control_surfaces
        text = strip_control_surfaces(text)
    except Exception as _swx:
        _swallowed(_swlog, "_scrub", _swx, lane="skills")
    # Some replies open with an unmarked thinking preamble ("thought Thinking
    # Process: 1. **Analyze...") and put the description after it. Keep the last
    # paragraph when that shape appears rather than handing back the reasoning.
    # Gemma likes to open a look with a grounding-style ```json block
    # ({"point": [x,y], "label": ...}) before prose. That is a real output format,
    # not noise, but it is not an answer to "what do you see" — drop leading fences.
    # NEVER STRIP TO NOTHING. Each of these cleanups is only applied if it leaves
    # something behind — the first cut deleted the whole reply whenever she answered
    # entirely inside a fence, and take_photo returned "(nothing came back)" while
    # _describe on the same frame was fine. A tidier that can empty its input is a
    # bug that looks exactly like a broken camera.
    import re as _re

    def _keep(new: str, old: str) -> str:
        return new.strip() if new.strip() else old

    text = _keep(_re.sub(r"^\s*```[a-z]*\s*.*?```\s*", "", text, flags=_re.S | _re.I), text)
    if text.lstrip().lower().startswith("thought") or "Thinking Process" in text:
        parts = [p.strip() for p in text.splitlines() if p.strip()]
        if parts:
            text = _keep(parts[-1], text)
    return " ".join(text.split()) or "(nothing came back)"

def look_at(path: str, question: str = "Describe this image plainly.") -> str:
    """Look at an image file on disk and describe what is in it."""
    from harness.senses import capture
    try:
        return _describe(capture.load_image(path), question)
    except Exception as e:
        return f"[cannot look at {path}: {e}]"


def take_photo(question: str = "Describe what you can see plainly.") -> str:
    """Take one photo with the webcam and describe what is in front of it."""
    from harness.senses import capture
    try:
        return _describe(capture.photo(), question)
    except Exception as e:
        return f"[camera unavailable: {e}]"


def take_screenshot(question: str = "Describe what is on this screen plainly.") -> str:
    """Take a screenshot of his screen and describe what is on it."""
    from harness.senses import capture
    try:
        # 560, not 280 and not 1120. A screen is mostly small text: at 280 it is
        # not representable at all (measured — "Please provide more context", or
        # word salad, which reads like a broken encoder and is just an
        # under-resolved picture). MEASURED COST on a 1912x1072 screen, because
        # this encoder's attention is O(n^2) in numpy and the budgets are not
        # linear:  280 -> 34 s,  560 -> 94 s,  1120 -> 350 s.
        # 1120 is near-native and unusable; 560 is twice the detail for a wait a
        # person will actually tolerate.
        return _describe(capture.screenshot(), question, detail=560)
    except Exception as e:
        return f"[cannot capture the screen: {e}]"


def room_history(hours: int = 12) -> str:
    """Read your own notes about the room from the last N hours."""
    import time as _t
    try:
        from harness.senses import ambient
        rows = [r for r in ambient.recent(200)
                if r.get("at", 0) >= _t.time() - max(1, int(hours)) * 3600]
    except Exception as e:
        return f"[cannot read the room notes: {e}]"
    if not rows:
        return (f"No notes from the last {hours} hours. The hourly look may be off, "
                f"or nothing has been written yet.")
    out = []
    for r in rows:
        when = r.get("iso", "")[11:16] or "??:??"
        out.append(f"{when} — {r.get('seen') or '[' + str(r.get('error', 'no look')) + ']'}")
    return os.linesep.join(out[-40:])


def _specs():
    from harness.toolcore.tools import ToolSpec
    return [ToolSpec.from_callable(f) for f in (look_at, take_photo, take_screenshot, room_history)]


# Armed only when the served model HAS a vision path and SP_SIGHT is on — an
# unarmed tool that returns "sight is not armed" every time is worse than absent,
# because she will keep reaching for it.
def sight_tools():
    try:
        from harness.senses import capability as cap, vision
        if not vision.ARMED:
            return []
        # A VL DOOR MAKES HER SIGHTED ON A MODEL THAT IS NOT (2026-08-22, E): the served
        # checkpoint's vision row, OR an LFM2.5-VL model chosen on the aux chat door.
        if cap.for_model().vision:
            return _specs()
        try:
            from harness.skills import sight_vl as _vl
            if _vl.armed():
                return _specs()
        except Exception as _swx:
            _swallowed(_swlog, "sight_tools", _swx, lane="skills")
        return []
    except Exception as _swx:
        _swallowed(_swlog, "sight_tools", _swx, lane="skills")
        return []


SIGHT_TOOLS = sight_tools()
