"""G-BACKEND-SEAM — one inference surface, two backends, and what degrades is said. OFFLINE.

The engine-agnostic seam (2026-08-21 plan, Phase 3): `get_client()` returns the sp-daemon
client or an OpenAI-compatible one behind ONE surface; `InferenceConfig.to_openai_chat`
sends only portable fields; every daemon-only capability is declared in `supports` and
the seams that need one degrade with a stated loss. This drives the REAL OpenAIClient
against an in-process stdlib fake that speaks /v1/chat/completions (stream + non-stream,
with a planted `<channel|>` leak to prove the stripper still applies), /v1/models and
/v1/embeddings — so the wire is exercised, not a re-implementation.

    python harness_tests/g_backend_seam.py
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
import _src as _srcmod  # noqa: E402
os.environ["CUDA_VISIBLE_DEVICES"] = ""
from _gate import check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
SEEN = {"bodies": [], "paths": []}


def _send_json(h, obj, code=200):
    b = json.dumps(obj).encode()
    h.send_response(code); h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(b))); h.end_headers(); h.wfile.write(b)


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        SEEN["paths"].append(self.path)
        if self.path == "/v1/models":
            _send_json(self, {"data": [{"id": "fake-1"}]})
        else:
            self.send_error(404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        SEEN["paths"].append(self.path); SEEN["bodies"].append(body)
        if self.path == "/v1/embeddings":
            vecs = [[0.1, 0.2, 0.3] for _ in body.get("input", [])]
            _send_json(self, {"data": [{"index": i, "embedding": v} for i, v in enumerate(vecs)]}); return
        if self.path != "/v1/chat/completions":
            self.send_error(404); return
        short = body.get("max_tokens", 999) < 8
        if body.get("stream"):
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            for piece in ("Hello ", "<channel|>", "there. ", "Fine."):
                d = {"choices": [{"delta": {"content": piece}, "finish_reason": None}]}
                self.wfile.write(("data: " + json.dumps(d) + "\n\n").encode()); self.wfile.flush()
            d = {"choices": [{"delta": {}, "finish_reason": "length" if short else "stop"}]}
            self.wfile.write(("data: " + json.dumps(d) + "\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
        else:
            _send_json(self, {"choices": [{"message": {"role": "assistant",
                                                        "content": "Hello <channel|>there. Fine."},
                                            "finish_reason": "stop"}]})


srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["SP_ENGINE_KIND"] = "openai"
os.environ["SP_ENGINE_BASE_URL"] = "http://127.0.0.1:%d" % port
os.environ["SP_ENGINE_MODEL"] = "fake-1"
for k in ("SP_ENGINE_DIALECT", "SP_ENGINE_VISION", "SP_ENGINE_MARGIN_APPROX"):
    os.environ.pop(k, None)

from harness.inference import client as C  # noqa: E402
from harness.inference.inference_config import InferenceConfig  # noqa: E402
from harness.inference.backends import SP_CAPS, OPENAI_CAPS, supports, caps_for  # noqa: E402
C._CLIENT = None

print("1. THE SELECTOR — one surface, the kind the env names")
cl = C.get_client()
check("SP_ENGINE_KIND=openai yields the OpenAI backend", getattr(cl, "kind", "") == "openai", type(cl).__name__)
for m in ("chat_stream", "chat", "oneshot", "abort", "metrics", "health", "subscribe_events"):
    check("...wearing the SPDaemonClient surface: %s" % m, callable(getattr(cl, m, None)))
check("it declares what it cannot do (supports is the honest subset)",
      cl.supports == OPENAI_CAPS
      and not ({"eot_margin", "byteexact", "inject_frames", "capture", "warm", "restart"} & cl.supports))
check("the sp kind still supports everything", caps_for("sp") == SP_CAPS and "eot_margin" in SP_CAPS)
check("caps_for llamacpp adds the extras, vision adds image parts",
      "llama_extras" in caps_for("openai", "llamacpp") and "vision_openai" in caps_for("openai", "", True))

print("\n2. THE WIRE — portable fields only, and the stripper still applies")
cfg = InferenceConfig(temperature=0.4, top_k=40, repetition_penalty=1.3, max_tokens=64,
                      byteexact=True, eot_bias=2.0, auto_recall=True, self_repeat_ngram=3,
                      tool_names=["x"], raw_logits=True)
deltas = []
gen = cl.chat_stream(messages=[{"role": "user", "content": "hi"}], config=cfg)
try:
    while True:
        deltas.append(next(gen))
except StopIteration as stop:
    resp = stop.value
body = SEEN["bodies"][-1]
check("the request went to /v1/chat/completions with stream=true",
      SEEN["paths"][-1] == "/v1/chat/completions" and body.get("stream") is True)
leaked = [k for k in InferenceConfig.SP_ONLY if k in body]
check("no SP-ONLY field reached the wire", not leaked, leaked)
check("top_k / repetition_penalty are withheld from a generic endpoint",
      "top_k" not in body and "repeat_penalty" not in body)
check("portable fields went through",
      body.get("temperature") == 0.4 and body.get("max_tokens") == 64 and body.get("model") == "fake-1")
check("deltas streamed raw (4 pieces)", len(deltas) == 4, deltas)
check("the aggregate text had the planted <channel|> stripped — the one door holds",
      "<channel|>" not in resp.text and "Hello" in resp.text and "Fine." in resp.text, resp.text)
check("last_kairos is set with eot_margin=None (no margin, and said so)",
      cl.last_kairos and cl.last_kairos.get("eot_margin") is None
      and cl.last_kairos.get("source") == "openai", cl.last_kairos)
os.environ["SP_ENGINE_DIALECT"] = "llamacpp"; C._CLIENT = None
cl2 = C.get_client()
cl2.chat(messages=[{"role": "user", "content": "hi"}], config=cfg)
b2 = SEEN["bodies"][-1]
check("under the llamacpp dialect top_k and repeat_penalty ARE sent",
      b2.get("top_k") == 40 and b2.get("repeat_penalty") == 1.3, b2)
os.environ.pop("SP_ENGINE_DIALECT", None); C._CLIENT = None; cl = C.get_client()

print("\n3. ONESHOT, EMBED, HEALTH, METRICS, ABORT, EVENTS")
one = cl.oneshot([{"role": "user", "content": "q"}], max_tokens=16)
check("oneshot is a non-stream completion, stripped",
      "Fine." in one and "<channel|>" not in one and SEEN["bodies"][-1].get("stream") is False, one)
check("health asks /v1/models", cl.health() is True and "/v1/models" in SEEN["paths"])
vec = cl.embed(["a", "b"])
check("embed returns one vector per input from /v1/embeddings", len(vec) == 2 and len(vec[0]) == 3)
from harness.inference import turn_meter  # noqa: E402
turn_meter.start(); m = cl.metrics(); turn_meter.end()
check("metrics is the harness's own turn meter (busy while a turn is open)",
      m.get("tokens_per_sec", 0) > 1.0 and m.get("source") == "turn_meter", m)
check("...and idle after", cl.metrics().get("tokens_per_sec") == 0.0)
check("abort of an unknown chat is False, not an exception", cl.abort(999) is False)
check("subscribe_events is empty, not an error", list(cl.subscribe_events()) == [])

print("\n4. THE DEGRADATIONS ARE DECIDED BY supports(), AND KAIROS STILL DECIDES")
check("supports() reads the current backend",
      supports("oneshot") and not supports("eot_margin") and not supports("capture"))
src_i = open(os.path.join(ROOT, "harness", "kairos", "impulse.py"), encoding="utf-8").read()
check("impulse.decide takes eot_margin=None (CONTINUE dark, the rest alive)",
      "eot_margin: Optional[float]" in src_i or "eot_margin=None" in src_i)
os.environ["SP_ENGINE_MARGIN_APPROX"] = "1"; C._CLIENT = None; cl3 = C.get_client()
cl3.chat(messages=[{"role": "user", "content": "hi"}], config=InferenceConfig(max_tokens=4))
check("SP_ENGINE_MARGIN_APPROX=1 reads a `length` finish as cut off (margin 0.0)",
      cl3.last_kairos and cl3.last_kairos.get("eot_margin") == 0.0
      and cl3.last_kairos.get("finish_reason") == "length", cl3.last_kairos)
os.environ.pop("SP_ENGINE_MARGIN_APPROX", None)
app = _srcmod.pkg("harness", "server")
check("the warm gate short-circuits when the backend has no warm",
      '_sup("warm")' in app and "_WARM.set()" in app)
check("/v1/start and the restart door refuse an external engine politely",
      "external engine" in app and '"restart" not in (_engine_info()' in app)
check("the in-flight hooks feed the turn meter (one writer, two readers)",
      app.count("_tm.start()") == 1 and app.count("_tm.end()") == 1)
# `harness/skills/memory` is a PACKAGE (2026-09-01), so it is read as one — a
# `_sup("capture")` that moves to a sibling still satisfies the claim, which is what
# this leg means. The rest are single files and stay single files.
check("memory degrades by supports()",
      '_sup("capture")' in _srcmod.pkg("harness", "skills", "memory"))
for path, needle in (("harness/skills/semindex.py", '_sup("embed")'),
                     ("harness/skills/sight.py", '_sup("inject_frames")'),
                     ("harness/voice/service.py", '"inject_frames" not in'),
                     ("harness/control/watchdog.py", '_sup("restart")')):
    src = open(os.path.join(ROOT, path), encoding="utf-8").read()
    check("%s degrades by supports()" % path.split("/")[-1], needle in src)

print("\n5. THE SP PATH IS UNCHANGED — the daemon's own body, field for field")
os.environ["SP_ENGINE_KIND"] = "sp"; C._CLIENT = None
spc = C.get_client()
check("SP_ENGINE_KIND=sp (the default) yields the daemon client",
      getattr(spc, "kind", "") == "sp" and spc.supports == SP_CAPS)
os.environ["SP_GATEWAY_BYTEEXACT"] = "0"
b_sp = InferenceConfig(temperature=0.4, top_k=40, repetition_penalty=1.3, max_tokens=64,
                       eot_bias=0.0, self_repeat_ngram=3).to_sp_chat(
    messages=[{"role": "user", "content": "hi"}])
check("to_sp_chat still carries every sp field",
      b_sp.get("eot_bias") == 0.0 and b_sp.get("self_repeat_ngram") == 3
      and b_sp.get("top_k") == 40 and b_sp.get("byteexact") is False, b_sp)
srv.shutdown()
print("\n7. THE COMPANION PROFILE PASSES THE ONE DOOR")
# serve.py build_env reads ONE schema for every profile; a key the external-engine profile
# forgot (kv.persist_b4, memory.l5_tau — 2026-08-21, found by the first real boot) raises
# KeyError at the door and nothing starts. This leg is that boot's first 200 ms, offline.
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location("serve_door", os.path.join(ROOT, "serve.py"))
_serve = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_serve)
try:
    _env = _serve.build_env(_serve.load_profile("companion"))
    _err = ""
except Exception as ex:  # noqa: BLE001
    _env, _err = {}, "%s: %s" % (type(ex).__name__, ex)
check("build_env(companion) raises nothing", not _err, _err)
check("...and maps the engine block: kind=openai, a base_url, a key FILE path",
      _env.get("SP_ENGINE_KIND") == "openai" and bool(_env.get("SP_ENGINE_BASE_URL"))
      and _env.get("SP_ENGINE_API_KEY_FILE", "").endswith("engine.token"),
      {k: _env.get(k) for k in ("SP_ENGINE_KIND", "SP_ENGINE_BASE_URL", "SP_ENGINE_API_KEY_FILE")})
check("...and the gateway port the profile names (8810 — beside hers, never ON hers)",
      _env.get("SP_GATEWAY_PORT") == "8810", _env.get("SP_GATEWAY_PORT"))

print("\n9. ask_oneshot WALKS THE SEAM ON A FOREIGN ENGINE (2026-08-28, external review)")
# oneshot.py POSTs SP_DAEMON_URL + /v1/oneshot — deliberately stdlib-only, and right for
# the sp daemon. On an openai-engine profile that URL is LM Studio, which has no such
# route, so the becoming pass, the weekly chapter and the slots oracle all failed-to-
# silence on exactly the profile the public framework ships. A non-sp engine now falls
# through to get_client().oneshot; the sp fast path is untouched.
import harness.inference.oneshot as _osh
import harness.inference.client as _cl
_old_kind = os.environ.get("SP_ENGINE_KIND")
_old_get = _cl.get_client


class _StubC:
    def oneshot(self, msgs, **kw):
        return "STUB-ANSWER from the seam"


try:
    os.environ["SP_ENGINE_KIND"] = "openai"
    _cl.get_client = lambda: _StubC()
    check("a foreign engine gets its answer through the backend client",
          _osh.ask_oneshot("one question") == "STUB-ANSWER from the seam",
          _osh.ask_oneshot("one question"))
    _cl.get_client = lambda: (_ for _ in ()).throw(RuntimeError("down"))
    check("...and a dead client is still fail-toward-silence, never a raise",
          _osh.ask_oneshot("q") is None)
finally:
    _cl.get_client = _old_get
    if _old_kind is None:
        os.environ.pop("SP_ENGINE_KIND", None)
    else:
        os.environ["SP_ENGINE_KIND"] = _old_kind

print("\n9. THE PUBLIC FRONT DOOR RUNS OFF WINDOWS")
# ── `python serve.py companion` IS THE FIRST COMMAND IN THE PUBLIC README ────────────
# (2026-08-31, external review: "the launcher is Windows-only".) Off Windows it did not
# degrade, it CRASHED — `subprocess.CREATE_NO_WINDOW` is not defined on POSIX, so the
# first spawn raised AttributeError before anything started; three more Windows-only
# calls owned stopping. This gate owns the openai backend, which is the ONLY backend a
# public clone has, so the launcher that starts it belongs here too.
#
# Checked as ONE SEAM rather than as four call sites, which is the same rule the rest of
# this repo lives by: `NO_WINDOW` for spawning, `kill_image` / `kill_by_cmdline` for
# stopping, each with its POSIX half, and nothing platform-specific outside them.
import io as _io9

_serve = _io9.open(os.path.join(ROOT, "serve.py"), encoding="utf-8", errors="replace").read()
_seam_start = _serve.index("NO_WINDOW = ")
_seam_end = _serve.index("def launch_tts(")
_seam, _rest = _serve[_seam_start:_seam_end], _serve[:_seam_start] + _serve[_seam_end:]
_rest_code = "\n".join(l for l in _rest.splitlines() if not l.lstrip().startswith("#"))

check("§10 the launcher has a platform seam at all", "def kill_image(" in _seam
      and "def kill_by_cmdline(" in _seam)
for _tok in ("CREATE_NO_WINDOW", "taskkill", "Get-CimInstance"):
    check("§10 no bare %-16s outside the seam" % _tok,
          _tok not in _rest_code,
          [l.strip()[:70] for l in _rest_code.splitlines() if _tok in l][:2])
check("§10 ...and every spawn takes the seam's flag",
      _rest_code.count("creationflags=NO_WINDOW") >= 4,
      _rest_code.count("creationflags=NO_WINDOW"))
# DRIVEN, not read: the constant must evaluate to a valid `creationflags` off Windows,
# and 0 is the portable "no flags". A gate that only greps would pass on `= None`.
_ns = {"subprocess": __import__("subprocess"),
       "os": type("_o", (), {"name": "posix"})()}
exec(_seam[:_seam.index("\n\n")], _ns)
check("§10 NO_WINDOW is a usable creationflags value on POSIX",
      _ns["NO_WINDOW"] == 0, _ns["NO_WINDOW"])
check("§10 both stop primitives have a POSIX branch",
      _seam.count("if os.name == \"nt\":") == 2 and "pkill" in _seam,
      _seam.count("if os.name == \"nt\":"))
# AND THE DOC SAYS WHAT IS STILL WINDOWS-SHAPED, because a portable launcher is not a
# portable engine — the sp daemon is a Rust binary built for the box.
_bk = _io9.open(os.path.join(ROOT, "docs", "BACKENDS.md"), encoding="utf-8",
                errors="replace").read()
check("§10 BACKENDS.md says which half is portable",
      "launcher" in _bk.lower() and ("posix" in _bk.lower() or "linux" in _bk.lower()),
      "docs/BACKENDS.md must name what runs off Windows and what does not")

finish("G-BACKEND-SEAM")
