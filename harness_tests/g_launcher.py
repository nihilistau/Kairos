"""G-LAUNCHER — the launcher and the companion switch start the companion you chose, the way
the one door starts anything. OFFLINE. (harness/launcher.py, kairos.bat, app._companion_switch)

  1. the launcher lists profiles (with the engine each uses) and companions
  2. start goes through serve.py with --companion=<chosen>; stop through serve.py --stop
  3. choosing who she talks to writes the home's active user; the choice survives (state)
  4. status asks each profile's port and reports down when nothing answers
  5. the switch: refuses the companion already running, an unknown one, and a mid-turn stack;
     on her own engine it is a FULL restart (the daemon holds the registry path too); on an
     external engine a gateway bounce; either way it comes back as the chosen companion
  6. kairos.bat / kairos.sh exist and call the launcher; the menu survives a cp1252 console

Run: python harness_tests/g_launcher.py
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_launcher")
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"

from harness import home as H  # noqa: E402
from harness import launcher as L  # noqa: E402

H.COMPANIONS_DIR = os.environ["SP_COMPANIONS_DIR"]
H.VAR = os.path.join(SB, "var")
L.STATE = os.path.join(SB, "var", "launcher.json")

print("1. what there is")
P = L.profiles()
names = [p["name"] for p in P]
check("profiles are listed", "companion" in names, names)
check("…each says which engine it uses", all(p["engine"] for p in P))
ivy = H.create("ivy", "Ivy")
wren = H.create("wren", "Wren")
check("companions are listed", {"ivy", "wren"} <= {h["id"] for h in H.list_homes()})

print("\n2. start and stop go through the one door")
calls = []
import subprocess  # noqa: E402
_call = subprocess.call
subprocess.call = lambda argv, **kw: calls.append(list(argv)) or 0
try:
    L.start("companion", "ivy")
    L.stop()
    rc = L.main(["start", "--profile=companion", "--companion=wren"])
    L.main(["stop"])
finally:
    subprocess.call = _call
check("start runs serve.py <profile> --companion=<id>",
      calls[0][1].endswith("serve.py") and calls[0][2:] == ["companion", "--companion=ivy"], calls[0])
check("stop runs serve.py --stop", calls[1][2:] == ["--stop"], calls[1])
# found by the fresh install: the stop forgot the profile, so a gateway on another port and the
# profile's own llama-server ([engine] command) were left running
check("stop after a start names the profile it started", calls[3][2:] == ["companion", "--stop"], calls[3:])
check("start from the command line remembers the choice (and what it started, for stop)",
      L.load_state() == {"profile": "companion", "companion": "wren", "started_profile": "companion"}, L.load_state())

print("\n3. who she talks to")
os.environ["SP_PEOPLE"] = H.resolve(ivy)["people"]
from harness import people as PP  # noqa: E402
a = PP.add_user("Ray", "he/him/his")
b = PP.add_user("Robin", "she/her/her")
PP.set_active(a["id"])
L.set_user(ivy, b["id"])
check("choosing a user writes the home's active user", PP.active()["id"] == b["id"])
check("users_of lists them", [u["names"][0] for u in L.users_of(ivy)] == ["Ray", "Robin"])

print("\n4. status")
st = L.status()
check("every profile port is asked", {s["port"] for s in st} >= {p["port"] for p in P if p["port"]})
check("nothing running here reads as down", all(not s["up"] for s in st), st)

print("\n5. the switch")
from harness.server import app as A  # noqa: E402
from harness.server import launch_routes as LR  # noqa: E402
os.environ["SP_HOME"] = ivy
saved = (A._engine_info, A._spawn_restart, A._do_restart, LR.restart_refusal)
got = {}
A._spawn_restart = lambda full: {"ok": True, "profile": "companion", "full": full, "eta_s": 180 if full else 20}
A._do_restart = lambda full, companion="": got.update(full=full, companion=companion)
LR.restart_refusal = lambda: None
try:
    code, r, after = A._companion_switch({"id": "ivy"})
    check("the companion already running is refused", code == 400 and after is None, r)
    code, r, after = A._companion_switch({"id": "nobody"})
    check("an unknown companion is refused", code == 400 and after is None, r)
    A._engine_info = lambda: {"supports": ["restart", "warm"]}
    code, r, after = A._companion_switch({"id": "wren"})
    after()
    check("her own engine: a FULL restart, as Wren", code == 200 and got == {"full": True, "companion": wren}, (r, got))
    check("…and it says the model reloads too", "model reloads" in r.get("note", ""))
    A._engine_info = lambda: {"supports": ["warm"]}
    code, r, after = A._companion_switch({"id": "wren"})
    after()
    check("an external engine: a gateway bounce, as Wren", got == {"full": False, "companion": wren}, got)
    LR.restart_refusal = lambda: (409, {"ok": False, "error": "she is mid-turn"})
    code, r, after = A._companion_switch({"id": "wren"})
    check("mid-turn: refused, nothing spawned", code == 409 and after is None)
finally:
    A._engine_info, A._spawn_restart, A._do_restart, LR.restart_refusal = saved

print("\n6. the doors on disk")
bat = open(os.path.join(ROOT, "kairos.bat"), encoding="utf-8").read()
sh = open(os.path.join(ROOT, "kairos.sh"), encoding="utf-8").read()
check("kairos.bat runs the launcher from its own folder", "harness.launcher" in bat and "%~dp0" in bat)
check("kairos.sh likewise", "harness.launcher" in sh)
src = open(os.path.join(ROOT, "harness", "launcher.py"), encoding="utf-8").read()
check("the menu survives a console that cannot show a character", 'reconfigure(errors="replace")' in src)

finish("G-LAUNCHER")
