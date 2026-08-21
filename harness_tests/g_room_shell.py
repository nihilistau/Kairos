"""G-ROOM-SHELL — the room is a place, and a dead backend never blanks it. OFFLINE
(the node legs need node; the pulse leg needs a gateway and skips without one).

TWO PROPERTIES, and the second is the one that matters:

  1. /v1/room/pulse is ONE call carrying everything the shell needs — the day
     boundary that drives her journal, her mood, when the eye next looks, how long
     he has been quiet. Five separate polls for a heartbeat is how a UI ends up
     with five different ideas of what time it is.

  2. THE ROOM DEGRADES, NEVER BLANKS. It paints before the first pulse arrives,
     while the gateway restarts, and when the daemon is down. A backdrop that
     throws on a missing field turns a slow backend into a black screen, which
     reads as broken rather than as waiting — and the backend is slow here
     routinely (a 26B load-time prefill is minutes).

The renderer seam is asserted too. "2D now, 3D later" is only real if the later
layer can arrive without touching a panel, and the way to keep that true is for the
contract to be one small plain-JS function that a gate can exercise in node.

Run: python harness_tests/g_room_shell.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

GW = os.environ.get("SP_GATEWAY_URL", "http://127.0.0.1:8800")
UI = os.path.join(ROOT, "ui", "src", "room")

_P = _F = 0


def ok(cond, name, detail=""):
    global _P, _F
    if cond:
        _P += 1
        print(f"  ok   {name}")
    else:
        _F += 1
        print(f"  FAIL {name}   {detail}")


print("1. the seam exists and is plain, testable JS")
ok(os.path.isfile(os.path.join(UI, "describe.js")),
   "describe.js is the contract, with no JSX and no imports")
ok(os.path.isfile(os.path.join(UI, "Renderer.jsx")), "Renderer.jsx is the seam")
ok(os.path.isfile(os.path.join(UI, "Backdrop2D.jsx")), "Backdrop2D is one implementation")
src = open(os.path.join(UI, "describe.js"), encoding="utf-8").read()
# Structural, not textual: the file's own comment says "imports nothing", and a
# substring check on the word matched its own documentation. Look for a real import
# STATEMENT at the start of a line.
_imports = [l for l in src.splitlines()
            if l.strip().startswith("import ") or l.strip().startswith("import{")]
ok(not _imports, "describe.js imports nothing — it can be exercised without a build",
   _imports[:2])
rsrc = open(os.path.join(UI, "Renderer.jsx"), encoding="utf-8").read()
ok("3d slots in here" in rsrc, "the renderer names where a 3D implementation lands")

print("\n2. THE CONTRACT SURVIVES ANYTHING (node)")
node = shutil.which("node")
if not node:
    print("  --   node absent; the degradation legs are skipped")
else:
    probe = r"""
import { describeRoom, ALONE_AFTER_S } from './ui/src/room/describe.js'
const cases = {
  null: null, undefined: undefined, empty: {},
  partial: { clock: {} },
  nulls: { clock: { hour: null }, her: { mood: null }, presence: {} },
  wrongtypes: { clock: 'nope', her: 5, presence: [] },
  modified_mood: { her: { mood: 'warm, +tender' } },
  real: { clock: { hour: 3 }, her: { mood: 'peaceful' },
          presence: { warm: true, since_last_turn_s: 4 } },
}
const out = {}
for (const [k, v] of Object.entries(cases)) {
  try {
    const r = describeRoom(v)
    out[k] = { ok: true, phase: r.phase, mood: r.mood,
               energy: r.energy, alone: r.alone,
               finite: Number.isFinite(r.energy),
               keys: ['phase','mood','energy','alone','breath'].every(x => r[x] !== undefined) }
  } catch (e) { out[k] = { ok: false, err: String(e) } }
}
console.log(JSON.stringify(out))
"""
    p = os.path.join(ROOT, "_g_room_probe.mjs")
    try:
        with open(p, "w", encoding="utf-8") as f:
            f.write(probe)
        r = subprocess.run([node, p], capture_output=True, text=True, cwd=ROOT, timeout=60)
        data = json.loads((r.stdout or "{}").strip().splitlines()[-1])
    except Exception as exc:
        data = {}
        ok(False, "the node probe ran", f"{type(exc).__name__}: {exc} {r.stderr[:200] if 'r' in dir() else ''}")
    finally:
        if os.path.exists(p):
            os.remove(p)

    for case in ("null", "undefined", "empty", "partial", "nulls", "wrongtypes"):
        d = data.get(case, {})
        ok(d.get("ok"), f"describeRoom({case}) does not throw", d.get("err"))
        ok(d.get("keys"), f"   …and still returns every field", d)
        ok(d.get("finite"), f"   …with a finite energy", d.get("energy"))
    ok(data.get("null", {}).get("alone") is True,
       "no pulse reads as ALONE, not as company", data.get("null"))
    ok(data.get("modified_mood", {}).get("mood") == "warm",
       "a modified mood ('warm, +tender') resolves to a lookup-able word",
       data.get("modified_mood"))
    ok(data.get("real", {}).get("phase") == "night",
       "3am is night — the night is long here on purpose", data.get("real"))
    ok(data.get("real", {}).get("alone") is False,
       "someone who spoke 4 seconds ago is company", data.get("real"))

print("\n3. the pulse is one call with the whole room in it")
try:
    with urllib.request.urlopen(GW + "/v1/room/pulse", timeout=15) as r:
        pulse = json.loads(r.read())
except Exception as exc:
    print(f"  --   gateway not reachable ({type(exc).__name__}); pulse legs skipped")
    pulse = None

if pulse:
    ok(pulse.get("ok"), "it answers")
    for key in ("clock", "her", "presence", "journal", "backup", "research"):
        ok(key in pulse, f"carries {key}")
    c = pulse["clock"]
    ok("boundary_hour" in c and "consolidated_today" in c,
       "the clock is HER day — the boundary that drives her journal", c)
    ok("next_boundary_in_s" in c, "and how long until it falls")
    ok("since_last_turn_s" in pulse["presence"],
       "presence knows how long he has been quiet")
    ok(pulse["journal"].get("present") is not None,
       "and whether she has written")
    # the room must be able to paint from exactly this
    ok(isinstance(c.get("hour"), int), "hour is an int the renderer can use", c.get("hour"))

print("\n4. the built room is served and still additive")
# console/tuning.html was deleted in the 2026-08-21 clean-up (the room's Settings panel is the
# tuning surface now); this probe said 404 against the live gateway for a day before anyone read it.
for path, what in (("/room/", "the room"), ("/index.html", "the console redirect stub")):
    try:
        with urllib.request.urlopen(GW + path, timeout=10) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception:
        code = None
    if code is None:
        print(f"  --   {what} not checked (no gateway)")
    else:
        ok(code == 200, f"{what} serves ({path})", code)

print(f"\nG-ROOM-SHELL: {_P} pass, {_F} fail")
sys.exit(1 if _F else 0)
