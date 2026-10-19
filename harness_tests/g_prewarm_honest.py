"""G-PREWARM-HONEST — a daemon that failed her prefix is not reported as hot. OFFLINE.

THE BUG (2026-10-19, measured on her live boot). The daemon failed the load-time prefill
of her 9,029-token prefix twice (`cublasSgemm FAILED status=13`, then every allocation
`out of memory`; the cause was the Windows commit limit). The gateway logged

    prefill complete in 5s ... base snapshot ready in 0s; prefix is HOT

and serve.py printed `prefix HOT in 18s`. The stack looked healthy, and the first message
would have gone to a daemon that could not open a 4-token scratch.

Why: /v1/chat is a stream. On a failed prefill the daemon sends
`data: {"error":"kvdecode prefill head: ..."}` and closes it, and SPDaemonClient.chat_stream
read only `delta`s, so the error was dropped and the call returned EMPTY TEXT as if it had
worked. That is not only the boot: any turn the daemon failed came back as silence. And
/health's `warm` is the warm GATE (always released, success or not), which serve.py read as
success.

WHAT THIS HOLDS:
  §1 the client raises on an in-stream error, by name, and still returns text when there is none;
  §2 _prewarm records the outcome (ok / the daemon's error) in state.PREWARM, and still
     releases the gate either way (a failed prewarm must not wedge the gateway);
  §3 serve.py's verdict on /health says FAILED, with the error, when the prewarm failed,
     says hot when it worked, and says unknown for an older gateway with no field.

    python harness_tests/g_prewarm_honest.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness_tests._gate import sandbox, check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
sandbox("g_prewarm_honest")  # FIRST, before any harness. import

from harness.inference import client as C  # noqa: E402

ERR = "kvdecode prefill head: gemma4: CUDA fault detected at phase 'prefill_pertok:entry': out of memory"


class _Stream:
    def __init__(self, lines): self.lines = lines
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def raise_for_status(self): pass
    def iter_lines(self): return iter(self.lines)


class _Http:
    def __init__(self, lines): self.lines = lines
    def stream(self, *a, **k): return _Stream(self.lines)


def _client(lines):
    c = C.SPDaemonClient.__new__(C.SPDaemonClient)
    c.base_url = "http://127.0.0.1:9"; c.timeout = 1; c.default_model = ""
    c.last_kairos = None; c.last_trim = None; c._client = _Http(lines)
    return c


print("1. AN ERROR INSIDE THE STREAM IS AN ERROR, NOT SILENCE")
raised = None
try:
    out = _client(['data: {"error":"%s"}' % ERR.replace('"', "'")]).chat(messages=[{"role": "user", "content": "hi"}])
except Exception as e:      # noqa: BLE001 — the exception IS the subject
    raised = e
    out = None
check("the daemon's in-stream error raises", raised is not None,
      "returned %r — the 2026-10-19 boot: empty text read as success" % (getattr(out, "text", out),))
check("...as DaemonStreamError", isinstance(raised, getattr(C, "DaemonStreamError", ())), type(raised))
check("...carrying the daemon's words", raised is not None and "out of memory" in str(raised), raised)
ok = _client(['data: {"delta":"Hel"}', 'data: {"delta":"lo"}', "data: [DONE]"]).chat(
    messages=[{"role": "user", "content": "hi"}])
check("a normal stream still returns its text", ok.text == "Hello", ok.text)


print("\n2. THE PREWARM RECORDS WHETHER IT WORKED")
from harness.server import app as A  # noqa: E402
from harness.server import state as S  # noqa: E402
import harness.agent as _agent  # noqa: E402
import harness.inference.client as _cl  # noqa: E402
import threading  # noqa: E402


class _FakeDaemon:
    def __init__(self, fail): self.fail = fail; self.calls = 0
    def health(self): return True
    def chat(self, messages=None, config=None):
        self.calls += 1
        if self.fail:
            raise C.DaemonStreamError(ERR) if hasattr(C, "DaemonStreamError") else RuntimeError(ERR)
        return C.InferenceResponse(text="")


_real = (threading.Thread, _cl.get_client, _agent.system_bundle)


class _Inline:
    def __init__(self, target=None, daemon=None, **k): self.t = target
    def start(self): self.t()


try:
    threading.Thread = _Inline
    _agent.system_bundle = lambda *a, **k: ("SYSTEM", None)
    for fail in (True, False):
        S.WARM.clear()
        if hasattr(S, "PREWARM"):
            S.PREWARM.clear()
        _cl.get_client = lambda fail=fail: _FakeDaemon(fail)
        A._prewarm()
        pw = dict(getattr(S, "PREWARM", {}) or {})
        if fail:
            check("a failed prefill is recorded as failed", pw.get("ok") is False, pw)
            check("...with the daemon's error", "out of memory" in str(pw.get("error", "")), pw)
            check("...and the gate is still released (a failed prewarm must not wedge her)",
                  S.WARM.is_set())
        else:
            check("a good prefill is recorded as ok", pw.get("ok") is True, pw)
finally:
    threading.Thread, _cl.get_client, _agent.system_bundle = _real


print("\n3. serve.py SAYS WHAT HAPPENED")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import serve  # noqa: E402

v = getattr(serve, "prewarm_verdict", None)
check("serve.py has a verdict for /health", callable(v))
if callable(v):
    st, msg = v({"warm": True, "prewarm": {"ok": False, "error": ERR}})
    check("a failed prewarm reads FAILED, not hot", st == "failed", (st, msg))
    check("...and names the daemon's error", "out of memory" in msg, msg)
    st, _ = v({"warm": True, "prewarm": {"ok": True}})
    check("a good one reads hot", st == "hot", st)
    st, _ = v({"warm": True})
    check("an older gateway with no field reads unknown, not hot", st == "unknown", st)
    st, _ = v({"warm": False})
    check("a gate still closed reads waiting", st == "waiting", st)

print("\n4. THE BOOT SAYS THE COMMIT NUMBER (the limit that actually failed)")
h = serve.commit_headroom_gb() if hasattr(serve, "commit_headroom_gb") else "missing"
if os.name == "nt":
    check("commit headroom is read on Windows", isinstance(h, tuple) and len(h) == 2, h)
    if isinstance(h, tuple):
        free, limit = h
        check("...as free <= limit, both positive", 0 < free <= limit, h)
    import io, contextlib  # noqa: E401
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        serve.report_commit_headroom()
    check("the boot line names free, limit and her stack's share",
          "GB free of a" in buf.getvalue() and "her stack takes" in buf.getvalue(), buf.getvalue())
    _real_h = serve.commit_headroom_gb
    try:
        serve.commit_headroom_gb = lambda: (1.0, 52.2)       # the 2026-10-19 afternoon
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            serve.report_commit_headroom()
        check("a short headroom is shouted, not just printed", "!! commit headroom is short" in buf.getvalue(),
              buf.getvalue())
    finally:
        serve.commit_headroom_gb = _real_h
else:
    check("off Windows there is no commit number to read", h is None, h)

finish("G-PREWARM-HONEST")
