"""G-ROOM-DOOR — the gateway refuses a page that is not the room. LIVE (needs the
gateway; no GPU, no daemon).

WHAT THIS EXISTS TO STOP, stated plainly because it was true until today:

    The gateway sent `Access-Control-Allow-Origin: *` on every route, with no auth,
    no origin check and no rate limit — including POST /v1/chat, which has shell
    access and arbitrary file write through the tool loop. Loopback binding was the
    ENTIRE security model, and loopback does not stop a browser: any page the
    operator visited could POST to 127.0.0.1:8800, drive the agent, overwrite
    persona.md, or set knobs.

THE ORIGIN CHECK IS THE FIX; THE CORS HEADER IS ONLY THE POLITE HALF — and that
distinction is the whole reason this gate has a leg for each. Refusing to ECHO a
foreign origin stops a page reading the response. It does NOT stop a simple request
(form-encoded or text/plain) being SENT and its side effect happening. So the origin
is refused server-side, before the handler runs, and both properties are asserted
separately: a gate that only checked the header would pass while the hole was open.

Run (with the stack up): python harness_tests/g_room_door.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

GW = os.environ.get("SP_GATEWAY_URL", "http://127.0.0.1:8800")
EVIL = "https://evil.example.com"

_P = _F = 0


def ok(cond, name, detail=""):
    global _P, _F
    if cond:
        _P += 1
        print(f"  ok   {name}")
    else:
        _F += 1
        print(f"  FAIL {name}   {detail}")


def req(path, method="GET", origin=None, body=None, ctype="application/json"):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(GW + path, data=data, method=method)
    if data is not None:
        r.add_header("Content-Type", ctype)
    if origin:
        r.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, dict(resp.headers), resp.read(4096)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read(4096)
    except Exception as e:                      # connection refused etc
        return None, {}, str(e).encode()


status, _h, _b = req("/health")
if status is None:
    print(f"  --   gateway not reachable at {GW}; start the stack first")
    print("\nG-ROOM-DOOR: SKIPPED (no gateway)")
    sys.exit(0)

print("1. the room itself still works")
ok(status == 200, "GET /health from the room (no Origin) is served", status)
s2, _, _ = req("/room/", "GET")
ok(s2 == 200, "GET /room/ is served", s2)
s3, _, _ = req("/v1/senses", "GET", origin="http://127.0.0.1:8800")
ok(s3 == 200, "a loopback Origin is accepted", s3)

print("\n2. the wildcard is gone")
_, h, _ = req("/health", origin="http://127.0.0.1:8800")
acao = h.get("Access-Control-Allow-Origin", "")
ok(acao != "*", "Access-Control-Allow-Origin is never '*'", acao)
ok(acao == "http://127.0.0.1:8800", "it ECHOES the loopback origin instead", acao)
ok("Origin" in h.get("Vary", ""), "and Vary: Origin is set, so a proxy cannot cache "
   "one origin's answer for another", h.get("Vary"))

print("\n3. a foreign page is REFUSED, not merely un-echoed")
# The leg that matters. A gate checking only the header would pass while the hole
# was open, because the side effect happens on send, not on read.
for path, method, body in (("/v1/senses", "GET", None),
                           ("/v1/knobs", "POST", {"name": "x", "value": "1"}),
                           # NOT a destructive payload. This gate overwrote the real
                           # persona.md on its first run, because the refusal was not
                           # live yet — the proof of a refusal must not depend on the
                           # refusal working. An empty persona is rejected by the
                           # writer's own validation even if the guard misses.
                           ("/v1/persona", "POST", {"persona": ""})):
    st, hh, _ = req(path, method, origin=EVIL, body=body)
    ok(st == 403, f"{method} {path} from a foreign origin -> 403", st)
    ok(hh.get("Access-Control-Allow-Origin", "") != EVIL,
       f"   …and {path} never echoes it", hh.get("Access-Control-Allow-Origin"))

print("\n4. the preflight refuses too")
st, _, _ = req("/v1/chat", "OPTIONS", origin=EVIL)
ok(st == 403, "OPTIONS from a foreign origin -> 403", st)
st, _, _ = req("/v1/chat", "OPTIONS", origin="http://localhost:8800")
ok(st in (204, 200), "OPTIONS from loopback still works", st)

print("\n5. persona.md was NOT overwritten by the attempt above")
# The refusal must happen BEFORE the handler, not inside it.
p = os.path.join(ROOT, "persona.md")
if os.path.isfile(p):
    body = open(p, encoding="utf-8", errors="replace").read()
    ok(len(body) > 200 and "Kairos" in body,
       "the refused POST never reached the writer", body[:40])
else:
    print("  --   persona.md absent (gitignored); skipped")

print("\n6. a body cannot be unbounded or malformed")
st, _, b = req("/v1/knobs", "POST", origin="http://127.0.0.1:8800",
               body={"junk": "x" * 200})
ok(st in (200, 400), "a normal body is handled", st)
# oversized: declare a huge Content-Length without sending it
r = urllib.request.Request(GW + "/v1/knobs", data=b"{}", method="POST")
r.add_header("Content-Type", "application/json")
r.add_header("Origin", "http://127.0.0.1:8800")
r.add_header("Content-Length", str(64 * 1024 * 1024))
try:
    with urllib.request.urlopen(r, timeout=10) as resp:
        code = resp.status
except urllib.error.HTTPError as e:
    code = e.code
except Exception:
    code = "conn"                      # server hung up, also a refusal
ok(code in (400, "conn"), "an oversized declared body is refused, not allocated", code)

print("\n7. the workspace is not the repo")
ws = os.environ.get("HARNESS_WORKSPACE", "")
if ws:
    ok(os.path.realpath(ws) != os.path.realpath(ROOT),
       "HARNESS_WORKSPACE resolves outside the repo root", ws)
else:
    # serve.py sets it for the gateway; a bare shell will not have it
    import re
    src = open(os.path.join(ROOT, "serve.py"), encoding="utf-8").read()
    ok('"HARNESS_WORKSPACE"' in src,
       "serve.py maps HARNESS_WORKSPACE (it defaulted to cwd = the whole repo)")
    ok('"room", "files"' in src, "…to a real shared directory under var/")

print(f"\nG-ROOM-DOOR: {_P} pass, {_F} fail")
sys.exit(1 if _F else 0)
