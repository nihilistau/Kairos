"""G-LAUNCH-NO-TOMLKIT — what must not need tomlkit does not. OFFLINE.

`tomlkit` is the optional extra `launch` (pyproject). Its one importer is
`harness/launch/profile_doc.py`; before 2026-10-27's final review `server/launch_routes.py`
imported that at module level, and app.py's knob writes, restart refusal and the reply chip
all go through launch_routes — so on an install without tomlkit every Settings/Voice/Search
write and every restart died with an uncaught ImportError.

A SUBPROCESS, tomlkit blocked (`sys.modules['tomlkit'] = None`, which makes `import tomlkit`
raise), a sandbox for every store:

  (a) a knob SET and a RESET through `app._tuning_op` return 200 and log one line each.
  (b) `restart_refusal()` says None when idle and 409 "mid-turn" when she is mid-turn.
  (c) `get_status()` is 200.
  (d) `GET /v1/launch` and the three POST handlers answer 503 with the install line.
  (e) the loaded-setup state still reads and writes.

    python harness_tests/g_launch_no_tomlkit.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from _gate import check, finish, utf8_stdout  # noqa: E402

utf8_stdout()

CHILD = r'''
import json, os, sys
sys.path.insert(0, %(here)r)
sys.path.insert(0, %(root)r)
from _gate import sandbox
sandbox("g_launch_no_tomlkit")
sys.modules["tomlkit"] = None               # import tomlkit -> ImportError
out = {}
from harness.server import app, launch_routes as lr
from harness.launch import changes
from harness.tuning import registry
out["profile_doc_is_none"] = lr.profile_doc is None
knob = next(k for k in registry.KNOBS if k.scope != "profile" and k.type in ("int", "float"))
newv = knob.max if (knob.max is not None and knob.max != knob.default) else knob.min
c1, r1 = app._tuning_op("/v1/tuning", {"values": {knob.key: newv}})
c2, r2 = app._tuning_op("/v1/tuning/reset", {"key": knob.key})
out["tuning"] = [c1, c2, [x["what"] for x in changes.tail(50) if x["source"] == "settings"], knob.key]
from harness.kairos import scheduler
scheduler.in_flight = lambda: (False, "")
out["idle"] = lr.restart_refusal()
scheduler.in_flight = lambda: (True, "busy")
busy = lr.restart_refusal()
out["busy"] = [busy[0], busy[1]["error"]] if busy else None
code, st = lr.get_status()
out["status"] = [code, st.get("ok")]
out["get"] = list(lr.get_launch())
out["posts"] = [lr.post_edit({"edits": {"a.b": 1}})[0], lr.post_raw({"text": ""})[0],
                lr.post_setup({"op": "save", "name": "x"})[0]]
lr.set_loaded("Fast")
lr._LOADED["read"] = False
out["loaded"] = lr.get_loaded()
print("RESULT " + json.dumps(out))
'''

env = dict(os.environ)
p = subprocess.run([sys.executable, "-c", CHILD % {"here": HERE, "root": ROOT}],
                   capture_output=True, text=True, env=env, cwd=ROOT, timeout=300)
line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), "")
check("the child ran to its result line with tomlkit blocked", bool(line), (p.stdout + p.stderr)[-1500:])
out = json.loads(line[7:]) if line else {}

check("launch_routes imported with profile_doc absent", out.get("profile_doc_is_none") is True, out)
t = out.get("tuning") or [0, 0, [], ""]
check("a knob set and a reset are 200 without tomlkit", t[0] == 200 and t[1] == 200, t)
check("...and each logged one settings line", t[2] == [t[3], t[3]], t)
check("restart_refusal is None when idle", out.get("idle") is None, out.get("idle"))
b = out.get("busy") or [0, ""]
check("restart_refusal is 409 mid-turn", b[0] == 409 and "mid-turn" in b[1], b)
check("get_status is 200", out.get("status") == [200, True], out.get("status"))
g = out.get("get") or [0, {}]
check("GET /v1/launch is 503 with the install line",
      g[0] == 503 and g[1].get("ok") is False and "tomlkit" in g[1].get("error", "")
      and "[launch]" in g[1]["error"], g)
check("the POST handlers are 503 too", out.get("posts") == [503, 503, 503], out.get("posts"))
check("the loaded-setup state still works", out.get("loaded") == "Fast", out.get("loaded"))

finish("G-LAUNCH-NO-TOMLKIT")
