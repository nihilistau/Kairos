"""G-LOBBY — the lobby page: a choice made there starts the companion you chose, and no other
web page can drive it. OFFLINE. (harness/lobby.py; the RunPod half is G-RUNPOD, which stays
in his tree with his pod's profile.)

  1. a RunPod profile: its pod details come from the profile's [runpod] table into runpod.ps1
     (nothing personal in the script); start = `runpod.ps1 up` then serve.py; stop =
     `runpod.ps1 down` (day pass, stop, TERMINATE) — never a bare serve.py --stop
  2. runpod-31b is HER: same companion home, an openai engine, no daemon paths
  3. the lobby: one page; state lists companions, users, profiles and status; a POST from
     another origin is refused; choose writes the launcher's state; start/stop go through the
     launcher (subprocess stubbed)
  4. runpod.ps1 keeps the safety rules of the original: the keyless-answer check terminates
     the pod; down consolidates before it terminates; keys come from files

Run: python harness_tests/g_lobby.py
"""
from __future__ import annotations

import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_lobby")
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"

from harness import launcher as L  # noqa: E402

L.STATE = os.path.join(SB, "launcher.json")
import subprocess  # noqa: E402

import subprocess  # noqa: E402

print("\n3. the lobby")
from harness import lobby  # noqa: E402
from harness import home as H  # noqa: E402
H.COMPANIONS_DIR = os.environ["SP_COMPANIONS_DIR"]
H.create("kairos", "Kairos")                 # the sandbox's own companion of that id
st = lobby.state()
check("state lists companions, profiles and status", st["companions"] and any(p["id"] == "companion" for p in st["profiles"])
      and isinstance(st["status"], list))


class Fake:
    def __init__(self, path, body, origin):
        raw = json.dumps(body).encode()
        self.path, self.headers = path, {"Origin": origin, "Content-Length": str(len(raw))}
        self.rfile, self.wfile, self.sent = io.BytesIO(raw), io.BytesIO(), None

    def _send(self, code, body, ctype="application/json"):
        self.sent = (code, body)


def post(path, body, origin=lobby.ORIGIN):
    f = Fake(path, body, origin)
    lobby.Handler.do_POST(f)
    return f.sent


check("a POST from another page is refused", post("/api/start", {}, origin="http://evil.example")[0] == 403)
check("…and with no Origin at all", post("/api/start", {}, origin="")[0] == 403)
post("/api/choose", {"profile": "companion", "companion": "kairos"})
check("choose writes the launcher's state", L.load_state().get("profile") == "companion")
ran = []
_run = lobby._run
lobby._run = lambda label, argv: ran.append((label, argv))
try:
    code, r = post("/api/start", {})
    import time
    time.sleep(0.3)
finally:
    lobby._run = _run
check("start goes through the launcher with the chosen profile and companion",
      code == 200 and ran and ran[0][1][2:] == ["harness.launcher", "start", "--profile=companion", "--companion=kairos"], ran)
check("the page is one page, loopback, and links to her room", "open her room" in lobby.PAGE and lobby.ORIGIN.startswith("http://127.0.0.1"))

finish("G-LOBBY")
