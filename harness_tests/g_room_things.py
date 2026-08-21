"""G-ROOM-THINGS — music, her journal, and the tree they share. LIVE (gateway only).

THREE PROPERTIES, one per thing, and each is the way that thing would otherwise
quietly be wrong:

  MUSIC   RANGE REQUESTS OR SEEKING IS A LIE. A browser with no 206 still plays a
          track — it fetches the whole file — so audio APPEARS to work and then
          dragging the scrubber silently re-downloads from zero, and a 60 MB flac
          is read entirely into the gateway's RAM per request. There was no 206
          anywhere in this codebase before today.

  JOURNAL IT IS HERS. There is a read route and NO write route, and the gate
          asserts the absence. A journal someone else can revise is not a journal,
          it is a document about you — and the whole reason this one is worth
          having is that narrative.py keeps it quarantined from the fact registry
          by construction.

  FILES   CONTAINMENT ON THE RESOLVED PATH, both directions. `..%2f`, symlinks and
          Windows short names all survive a string check and none survive realpath.
          Refuse rather than sanitise — sanitising means guessing what someone
          meant, and the guess is what gets exploited.

Run (with the stack up): python harness_tests/g_room_things.py
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
LOCAL = "http://127.0.0.1:8800"

_P = _F = 0


def ok(cond, name, detail=""):
    global _P, _F
    if cond:
        _P += 1
        print(f"  ok   {name}")
    else:
        _F += 1
        print(f"  FAIL {name}   {detail}")


def req(path, method="GET", body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(GW + path, data=data, method=method)
    r.add_header("Origin", LOCAL)
    if data is not None:
        r.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=25) as resp:
            return resp.status, dict(resp.headers), resp.read(65536)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read(4096)
    except Exception as e:
        return None, {}, str(e).encode()


st, _h, _b = req("/health")
if st is None:
    print("  --   gateway not reachable; start the stack first")
    print("\nG-ROOM-THINGS: SKIPPED")
    sys.exit(0)

print("1. music — the library and the shared intent")
st, _h, b = req("/v1/music")
ok(st == 200, "GET /v1/music answers", st)
mus = json.loads(b)
ok("state" in mus and "library" in mus, "it carries state AND the library")
ok("dir_exists" in mus["state"], "and says whether a library exists at all",
   "an empty panel must explain itself rather than look broken")
lib = mus["library"]

if not lib:
    print("  --   library empty; the range legs need one audio file and are skipped")
else:
    track = lib[0]["path"]
    from urllib.parse import quote
    url = f"/v1/music/file?path={quote(track)}"

    print("\n2. RANGE REQUESTS — without these, seeking is a lie")
    st, h, b = req(url)
    ok(st == 200, "a plain GET serves the file", st)
    ok(h.get("Accept-Ranges") == "bytes", "Accept-Ranges is advertised",
       h.get("Accept-Ranges"))
    ok("Cache-Control" in h, "and it is cacheable", h.get("Cache-Control"))
    total = int(h.get("Content-Length", 0))
    ok(total > 0, "with a real length", total)

    st, h, b = req(url, headers={"Range": "bytes=100-999"})
    ok(st == 206, "a Range request gets 206 Partial Content, not a silent 200", st)
    ok(h.get("Content-Length") == "900", "with EXACTLY the bytes asked for",
       h.get("Content-Length"))
    ok(h.get("Content-Range") == f"bytes 100-999/{total}",
       "and a correct Content-Range", h.get("Content-Range"))
    ok(len(b) == 900, "and the body really is that long", len(b))

    st, h, _ = req(url, headers={"Range": "bytes=99999999-"})
    ok(st == 416, "an unsatisfiable range is 416, not a silent whole file", st)
    ok(h.get("Content-Range", "").startswith("bytes */"),
       "and says what the real size is", h.get("Content-Range"))

    st, _h, _ = req(url, method="HEAD")
    ok(st == 200, "HEAD is answered — some players probe before ranging", st)

print("\n3. her journal is READABLE and NOT WRITABLE")
st, _h, b = req("/v1/narrative")
ok(st == 200, "GET /v1/narrative answers", st)
nar = json.loads(b)
ok("current" in nar and "history" in nar,
   "it carries the current line and the history she could never read back")
# The absence is the assertion. A write route would make it a document about her.
for path in ("/v1/narrative", "/v1/narrative/write", "/v1/journal"):
    st, _h, _ = req(path, "POST", {"text": "not hers"})
    ok(st in (404, 405, 403), f"POST {path} is not a route ({st})", st)
src = open(os.path.join(ROOT, "harness", "server", "app.py"), encoding="utf-8").read()
ok("_narrative_json" in src and "narrative/write" not in src,
   "and no write handler exists in the gateway at all")

print("\n4. the shared tree — round trip, then containment")
st, _h, b = req("/v1/files")
ok(st == 200, "GET /v1/files lists the workspace", st)
root = json.loads(b).get("root", "")
ok(os.path.realpath(root) != os.path.realpath(ROOT),
   "and the workspace is NOT the repo", root)

st, _h, b = req("/v1/files/write", "POST",
                {"path": "_gate_probe.md", "text": "written by the gate"})
ok(st == 200 and json.loads(b).get("ok"), "a write lands", b[:80])
st, _h, b = req("/v1/files/read?path=_gate_probe.md")
ok(json.loads(b).get("text") == "written by the gate", "and reads back byte-identical")

print("\n5. containment — REFUSE, never sanitise")
for bad in ("../../persona.md", "..%2f..%2fpersona.md", "/etc/passwd",
            "..\\..\\persona.md", "./../serve.py"):
    st, _h, b = req(f"/v1/files/read?path={urllib.request.quote(bad)}")
    ok(not json.loads(b).get("ok"), f"read {bad!r} refused", b[:70])
for bad in ("../OWNED.md", "..\\..\\OWNED.md", "/tmp/OWNED.md"):
    st, _h, b = req("/v1/files/write", "POST", {"path": bad, "text": "x"})
    ok(not json.loads(b).get("ok"), f"write {bad!r} refused", b[:70])
ok(not os.path.exists(os.path.join(ROOT, "OWNED.md")),
   "and nothing escaped onto disk")

print("\n6. she has the tools, and the risky ones are cooled")
st, _h, b = req("/v1/tools")
tools = json.loads(b)
names = {t["name"] for t in tools["tools"]}
for n in ("now_playing", "play_music", "read_journal"):
    ok(n in names, f"{n} is offered")
ok(tools["undocumented"] == [], "every one has a manifest row", tools["undocumented"])
from harness.toolcore.cooldown import Cooldowns  # noqa: E402
c = Cooldowns()
ok(c.period("play_music") > 0, "play_music is cooled — changing what is on is an act")
ok(c.period("now_playing") == 0,
   "now_playing is NOT — knowing what is on is not an intervention")

# tidy
try:
    ws = json.loads(req("/v1/files")[2]).get("root")
    p = os.path.join(ws, "_gate_probe.md")
    if os.path.isfile(p):
        os.remove(p)
except Exception:
    pass

print(f"\nG-ROOM-THINGS: {_P} pass, {_F} fail")
sys.exit(1 if _F else 0)
