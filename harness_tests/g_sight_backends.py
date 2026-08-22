"""G-SIGHT-BACKENDS — which eyes she uses is a picker, and every eye comes through one scrub. OFFLINE.

sight.backend: engine (today's logic, byte-identical) | aux_vl (an LFM2.5-VL model on the aux
chat door) | openai (the seam's image_url). A fake door in-process plays the VL model; numpy
pixels stand in for the camera. Arming: a VL door makes her sighted on a model that is not.

    python harness_tests/g_sight_backends.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["SP_ENGINE_KIND"] = "openai"            # a foreign endpoint: no frames
os.environ.pop("SP_ENGINE_VISION", None)           # ...and no image_url vision unless a test says so
os.environ["SP_SIGHT"] = "1"
os.environ["SP_AUX"] = "1"
os.environ.pop("SP_AUX_API_KEY_FILE", None)
os.environ.pop("SP_AUX_VL_MODEL", None)

SEEN = {"bodies": [], "paths": []}
REPLIES: list = []


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        SEEN["paths"].append(self.path)
        if self.path == "/v1/models":
            self._send({"data": [{"id": "lfm2.5-vl-3b"}, {"id": "lfm2.5-1.2b-instruct"}, {"id": "some-vision-x"}]})
        else:
            self.send_error(404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        SEEN["paths"].append(self.path); SEEN["bodies"].append(body)
        if self.path == "/v1/chat/completions":
            reply = REPLIES.pop(0) if REPLIES else ""
            if body.get("stream"):
                self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
                self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": reply}, "finish_reason": None}]}) + "\n\n").encode())
                self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}]}) + "\n\n").encode())
                self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
            else:
                self._send({"choices": [{"message": {"role": "assistant", "content": reply}}]})
        else:
            self.send_error(404)


srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["SP_AUX_CHAT_URL"] = "http://127.0.0.1:%d" % PORT
os.environ["SP_ENGINE_BASE_URL"] = "http://127.0.0.1:%d" % PORT

import numpy as np                                 # noqa: E402
from harness.tuning import registry as R           # noqa: E402
from harness.skills import sight as S              # noqa: E402
from harness.skills import sight_vl as V           # noqa: E402

IMG = np.zeros((24, 32, 3), dtype=np.uint8)
_was = {k: R.chosen(k) for k in ("sight.backend", "sight.vl_model", "sight.vl_max_tokens", "sight.vl_detail")}
import atexit                                      # noqa: E402
atexit.register(lambda: [R.reset(k) if v is None else R.set_many({k: v}) for k, v in _was.items()])

print("1. THE KNOBS — engine by default, a VL picker that reads the door")
ks = {k.key: k for k in R.KNOBS}
check("sight.backend is an enum of engine/aux_vl/openai, default engine",
      ks["sight.backend"].type == "enum" and ks["sight.backend"].default == "engine"
      and list(ks["sight.backend"].choices) == ["engine", "aux_vl", "openai"])
check("sight.vl_model / vl_max_tokens / vl_detail exist with their defaults",
      ks["sight.vl_model"].default == "" and ks["sight.vl_max_tokens"].default == 220 and ks["sight.vl_detail"].default == "auto")
check("voice.local_gguf is a profile knob on SP_TTS_GGUF", ks["voice.local_gguf"].scope == "profile" and ks["voice.local_gguf"].env == "SP_TTS_GGUF")
ch = V.vl_choices()
check("the VL picker filters the door's list to vl/vision ids", "lfm2.5-vl-3b" in ch and "some-vision-x" in ch and "lfm2.5-1.2b-instruct" not in ch, ch)

print("\n2. THE ROUTES — one choke point, one scrub")
R.reset("sight.backend"); R.reset("sight.vl_model")
out = S._describe(IMG, "what is this?")
check("engine on a foreign endpoint without image_url vision: today's message, byte-identical",
      out.startswith("[sight is not available on this engine"), out)
R.set_many({"sight.backend": "aux_vl"})
out = S._describe(IMG, "what is this?")
check("aux_vl with no model chosen: the not-available message names the section",
      "not available" in out and "Sight" in out, out)
R.set_many({"sight.vl_model": "lfm2.5-vl-3b", "sight.vl_max_tokens": 160, "sight.vl_detail": "high"})
REPLIES[:] = ["<channel|> A small room with a lamp on the desk."]
out = S._describe(IMG, "what is this?")
b = SEEN["bodies"][-1]
parts = b["messages"][0]["content"]
check("aux_vl: the door got ONE image_url part + the question, the chosen model and the budget",
      b.get("model") == "lfm2.5-vl-3b" and b.get("max_tokens") == 160
      and any(p.get("type") == "image_url" and p["image_url"]["url"].startswith("data:image/png;base64,") for p in parts)
      and any(p.get("type") == "text" and "what is this?" in p.get("text", "") for p in parts), {k: b.get(k) for k in ("model", "max_tokens")})
check("...detail reached the request", any(p.get("type") == "image_url" and p["image_url"].get("detail") == "high" for p in parts))
check("...and the description came through the SAME scrub (the planted <channel|> is gone)",
      out == "A small room with a lamp on the desk.", out)
REPLIES[:] = [""]
out = S._describe(IMG, "what is this?")
check("an empty door answer is an honest error, not a blank", out.startswith("[sight error"), out)
R.set_many({"sight.backend": "openai"})
os.environ["SP_ENGINE_VISION"] = "1"
try:
    from harness.inference import client as _IC
    _IC._CLIENT = None
    REPLIES[:] = ["<channel|> The seam saw a desk."]
    out = S._describe(IMG, "what is this?")
    check("openai: the seam's image_url branch, scrubbed", out == "The seam saw a desk.", out)
finally:
    os.environ.pop("SP_ENGINE_VISION", None)
    _IC._CLIENT = None

print("\n3. ARMING — a VL door makes her sighted on a model that is not")
from harness.senses import capability as CAP       # noqa: E402
_real_fm = CAP.for_model
class _NoVision:
    vision = None
try:
    CAP.for_model = lambda *a, **k: _NoVision()
    R.set_many({"sight.backend": "engine"})
    check("engine + a checkpoint without vision: no sight tools", S.sight_tools() == [])
    R.set_many({"sight.backend": "aux_vl", "sight.vl_model": ""})
    check("aux_vl without a model: still none", S.sight_tools() == [])
    R.set_many({"sight.vl_model": "lfm2.5-vl-3b"})
    names = {t.name for t in S.sight_tools()}
    check("aux_vl with a model: look_at / take_photo / take_screenshot are hers",
          {"look_at", "take_photo", "take_screenshot"} <= names, names)
finally:
    CAP.for_model = _real_fm
st = V.eyes_status()
check("eyes_status reports backend, model and the door", st.get("backend") == "aux_vl" and st.get("vl_model") == "lfm2.5-vl-3b" and st.get("door_up") is True, st)

finish("G-SIGHT-BACKENDS")
