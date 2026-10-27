"""G-LAUNCH-ROUTES — the gateway side of the Launch window. OFFLINE.

`harness/server/launch_routes.py` holds the handlers (body dict in, (status, response) out);
app.py dispatches to them. This drives them in a sandbox profile dir and var root.

  (a) GET /v1/launch: 8 labelled controls, `models` = the `*.sp-model` beside the current model.
  (b) EDIT: a stale hash is 409 and the file is untouched; a good edit logs one line per key
      (`source: launch`); an unknown profile name is refused (400) before it becomes a path.
  (c) SETUP: load applies the setup, `loaded` = its name; a later edit makes it "<name> (edited)";
      the state survives a fresh read from var/launch-loaded.json.
  (d) RESTART: `/v1/system` refuses with 409 while she is mid-turn and spawns NOTHING
      (the patch goes on the module that owns the check, `harness.kairos.scheduler`).
      Both `restart` and `restart_gateway`. Idle, it hands the restart on. The real
      `_do_restart` (Popen recorded, nothing spawned) gets env SP_LAUNCH_SETUP and a stdout
      that is var/serve-restart.log.
  (e) TUNING: a knob set / reset appends one settings-changes.jsonl line naming the key.

    python harness_tests/g_launch_routes.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _gate import check, finish, require, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
require("tomlkit", "G-LAUNCH-ROUTES", "launch")   # SKIP (exit 2) without the optional extra
sandbox("g_launch_routes")

VAR = tempfile.mkdtemp(prefix="g_launch_routes_var_")
PROF = tempfile.mkdtemp(prefix="g_launch_routes_prof_")
MODELS = tempfile.mkdtemp(prefix="g_launch_routes_models_")
os.environ["SP_LAUNCH_VAR"] = VAR
os.environ["SP_LAUNCH_PROFILES_DIR"] = PROF
os.environ["SP_TUNING_FILE"] = os.path.join(VAR, "tuning.json")
os.environ["SP_PROFILE"] = "t"

for fn in ("a.sp-model", "b.sp-model", "notes.txt"):
    open(os.path.join(MODELS, fn), "w").close()
cur = os.path.join(MODELS, "a.sp-model").replace("\\", "/")
with open(os.path.join(PROF, "t.toml"), "w", encoding="utf-8") as f:
    f.write('[paths]\nmodel = "%s"\n\n[decode]\nattn_split = 4\nattn_prefill_gemm = 0\n'
            'dequant_h8 = 1\nmoe_overlap_prefill = true  # copy overlap\nmoe_cpu_threads = 8\n'
            'moe_pf_lane = 2\n\n[kv]\nmoe_cache_gb = 4.0\n' % cur)

from harness.launch import changes, setups  # noqa: E402
from harness.server import app, launch_routes as lr  # noqa: E402


def rows():
    return changes.tail(100)


# (a) GET
code, g = lr.get_launch()
check("GET /v1/launch is 200 ok", code == 200 and g.get("ok"), (code, g))
check("8 labelled controls (a profile that has all eight keys)", len(g["controls"]) == 8, g["controls"])
with open(os.path.join(PROF, "t2.toml"), "w", encoding="utf-8") as f:
    f.write('[paths]\nmodel = "%s"\n\n[decode]\nattn_split = 4\n' % cur)
os.environ["SP_PROFILE"] = "t2"
_c2, _g2 = lr.get_launch()
os.environ["SP_PROFILE"] = "t"
check("only the controls whose keys the profile HAS are offered",
      _c2 == 200 and [c["key"] for c in _g2["controls"]] == ["paths.model", "decode.attn_split"],
      [c["key"] for c in _g2.get("controls", [])])
check("kinds are as specified",
      {c["key"]: c["kind"] for c in g["controls"]}["decode.attn_split"] == "bool01"
      and {c["key"]: c["kind"] for c in g["controls"]}["paths.model"] == "model")
check("models lists the *.sp-model beside the current model",
      g["models"] == ["a.sp-model", "b.sp-model"], g["models"])
check("cost text is the specified wording", g["cost"]["same_model"] == "about 1–2 min")
check("launched is null when nothing was recorded", g["launched"] is None)

# (b) edit
h0 = g["doc"]["hash"]
raw0 = open(os.path.join(PROF, "t.toml"), "rb").read()
code, r = lr.post_edit({"edits": {"kv.moe_cache_gb": 6}, "base_hash": "0" * 64})
check("stale hash is 409", code == 409 and r["ok"] is False, (code, r))
check("stale leaves the file untouched", open(os.path.join(PROF, "t.toml"), "rb").read() == raw0)
code, r = lr.post_edit({"edits": {"kv.moe_cache_gb": 6, "decode.attn_split": 0}, "base_hash": h0})
check("good edit is 200 with the new doc", code == 200 and r["doc"]["values"]["kv.moe_cache_gb"] == 6.0, (code, r))
ch = [x for x in rows() if x["source"] == "launch"]
check("one log line per edited key, source launch",
      sorted(x["what"] for x in ch) == ["decode.attn_split", "kv.moe_cache_gb"], ch)
code, r = lr.post_edit({"edits": {"decode.nope": 1}, "base_hash": r["doc"]["hash"]})
check("unknown key is 400", code == 400 and "decode.nope" in r["error"], (code, r))
check("no loaded setup, so an edit does not invent one", lr.get_loaded() is None)

os.environ["SP_PROFILE"] = "../t"
code, r = lr.get_launch()
check("a profile name that is not a plain basename is 400", code == 400, (code, r))
os.environ["SP_PROFILE"] = "t"

code, r = lr.post_raw({"text": "[paths\n", "base_hash": r.get("hash") or ""})
check("invalid raw toml is 400 or stale 409, never 200", code in (400, 409), (code, r))
cur_doc = lr.get_launch()[1]["doc"]
code, r = lr.post_raw({"text": cur_doc["text"] + "extra = 1\n", "base_hash": cur_doc["hash"]})
check("raw save is 200", code == 200, (code, r))
_rr = [x for x in rows() if x["what"] == "profile (raw)"]
check("raw save logs 'profile (raw)'", len(_rr) == 1, _rr)
check("...as the old and new sha256, not the file text",
      _rr and _rr[0]["old"] == cur_doc["hash"] and _rr[0]["new"] == r["doc"]["hash"]
      and len(_rr[0]["old"]) == 64 and "[paths]" not in json.dumps(_rr[0]), _rr)

# (c) setups
setups.save("Fast", {"decode.attn_split": 4, "paths.model": "b.sp-model"})
_b0 = open(os.path.join(PROF, "t.toml"), "rb").read()
code, r = lr.post_setup({"op": "load", "name": "Fast", "base_hash": "0" * 64})
check("a stale setup load is 409", code == 409 and r["ok"] is False, (code, r))
code2, r2 = lr.post_setup({"op": "load", "name": "Fast"})
check("a load with no hash is 409", code2 == 409, (code2, r2))
setups.save("Ghost", {"nope.key": 1})        # nothing applies, so only the route's own check can refuse
code3, r3 = lr.post_setup({"op": "load", "name": "Ghost", "base_hash": "0" * 64})
check("a stale load that would apply nothing is still 409", code3 == 409, (code3, r3))
setups.delete("Ghost")
check("a stale load leaves the file unchanged and loads nothing",
      open(os.path.join(PROF, "t.toml"), "rb").read() == _b0 and lr.get_loaded() is None)
code, r = lr.post_setup({"op": "load", "name": "Fast", "base_hash": lr.get_launch()[1]["doc"]["hash"]})
check("setup load is 200", code == 200 and r["doc"]["values"]["decode.attn_split"] == 4, (code, r))
check("load applied the model in the current model's directory",
      r["doc"]["values"]["paths.model"].replace("\\", "/") == os.path.join(MODELS, "b.sp-model").replace("\\", "/"),
      r["doc"]["values"]["paths.model"])
check("loaded = the name", lr.get_loaded() == "Fast", lr.get_loaded())
check("loaded is mirrored to var/launch-loaded.json",
      json.load(open(os.path.join(VAR, "launch-loaded.json")))["loaded"] == "Fast")
d = lr.get_launch()[1]["doc"]
code, r = lr.post_edit({"edits": {"decode.moe_pf_lane": 3}, "base_hash": d["hash"]})
check("an edit after load reads '<name> (edited)'", lr.get_loaded() == "Fast (edited)", lr.get_loaded())
lr._LOADED["read"] = False
lr._LOADED["v"] = None
check("loaded is read back from disk after a fresh start", lr.get_loaded() == "Fast (edited)", lr.get_loaded())
code, r = lr.post_setup({"op": "bogus", "name": "Fast"})
check("an unknown setup op is 400", code == 400, (code, r))
code, r = lr.post_setup({"op": "load", "name": "Nope"})
check("loading a setup that does not exist is 400", code == 400, (code, r))

# (d) restart
spawned, fired = [], []
_real_do, _real_spawn = app._do_restart, app._spawn_restart
app._do_restart = lambda full: fired.append(full)
app._spawn_restart = lambda full: (spawned.append(full), {"ok": True, "profile": "t", "full": full})[1]
from harness.kairos import scheduler  # noqa: E402
_real_if = scheduler.in_flight
try:
    scheduler.in_flight = lambda: (True, "a turn is running")
    code, res, after = app._system_op({"op": "restart"})
    check("restart mid-turn is 409 with the specified words",
          code == 409 and "mid-turn" in res["error"], (code, res))
    check("restart mid-turn does not call _spawn_restart", spawned == [], spawned)
    check("restart mid-turn schedules nothing", after is None)
    scheduler.in_flight = lambda: (False, "")
    code, res, after = app._system_op({"op": "restart"})
    check("restart when idle is 200 and schedules the relaunch", code == 200 and after is not None, (code, res))
    after()
    check("the scheduled relaunch is a FULL one", fired == [True], fired)
    scheduler.in_flight = lambda: (True, "a turn is running")
    n_spawn = len(spawned)
    code, res, after = app._system_op({"op": "restart_gateway"})
    check("restart_gateway mid-turn is 409", code == 409 and "mid-turn" in res["error"], (code, res))
    check("restart_gateway mid-turn spawns nothing", len(spawned) == n_spawn and after is None, spawned)
    scheduler.in_flight = lambda: (False, "")
    code, res, after = app._system_op({"op": "nonsense"})
    check("an unknown op is 400", code == 400 and after is None)
finally:
    scheduler.in_flight = _real_if
    app._do_restart, app._spawn_restart = _real_do, _real_spawn

# the REAL _do_restart, Popen recorded: what the child is handed is the claim, not the source
from harness.control import shutdown as _sd  # noqa: E402
_keep = (app._system_profile, _sd.is_shutting_down, _sd.ladder_running, app.subprocess.Popen)
_calls = []
app._system_profile = lambda: "t"
_sd.is_shutting_down = lambda: False
_sd.ladder_running = lambda: False
app.subprocess.Popen = lambda argv, **kw: _calls.append((argv, kw))
try:
    lr.set_loaded("Fast")
    app._do_restart(True)
    lr.set_loaded(None)
    app._do_restart(True)
finally:
    app._system_profile, _sd.is_shutting_down, _sd.ladder_running, app.subprocess.Popen = _keep
check("_do_restart spawned twice (recorded)", len(_calls) == 2, len(_calls))
if len(_calls) == 2:
    k1, k2 = _calls[0][1], _calls[1][1]
    check("child env carries the loaded setup", (k1.get("env") or {}).get("SP_LAUNCH_SETUP") == "Fast", k1.get("env", {}).get("SP_LAUNCH_SETUP"))
    check("child env says custom with none loaded", (k2.get("env") or {}).get("SP_LAUNCH_SETUP") == "custom")
    so = k1.get("stdout")
    check("child stdout is var/serve-restart.log",
          getattr(so, "name", None) is not None and os.path.abspath(so.name) == os.path.abspath(os.path.join(VAR, "serve-restart.log")), so)
    check("child stderr follows stdout", k1.get("stderr") == app.subprocess.STDOUT)
lr.set_loaded("Fast (edited)")
check("restart env names the loaded setup (or custom)", lr.restart_env_setup() == "Fast (edited)")
lr.set_loaded(None)
check("no setup loaded -> custom", lr.restart_env_setup() == "custom")

code, st = lr.get_status()
check("status is 200 with a log_tail list", code == 200 and st["log_tail"] == [] and st["launched_at"] is None, st)
with open(os.path.join(VAR, "serve-restart.log"), "w", encoding="utf-8") as f:
    f.write("".join("line %d\n" % i for i in range(30)))
code, st = lr.get_status()
check("status tail is the last 20 lines", st["log_tail"][0] == "line 10" and len(st["log_tail"]) == 20, st["log_tail"][:2])

# (e) tuning
from harness.tuning import registry  # noqa: E402
knob = next(k for k in registry.KNOBS if k.scope != "profile" and k.type in ("int", "float"))
n0 = len(rows())
newv = knob.max if (knob.max is not None and knob.max != knob.default) else knob.min
code, res = app._tuning_op("/v1/tuning", {"values": {knob.key: newv}})
tr = [x for x in rows()[n0:] if x["source"] == "settings"]
check("a tuning set is 200", code == 200, (code, res))
check("a tuning set appends one line naming the key", len(tr) == 1 and tr[0]["what"] == knob.key, tr)
code, res = app._tuning_op("/v1/tuning/reset", {"key": knob.key})
tr = [x for x in rows()[n0:] if x["source"] == "settings"]
check("a reset appends a line whose new value is the default",
      len(tr) == 2 and tr[1]["what"] == knob.key and tr[1]["new"] == knob.default, tr)
code, res = app._tuning_op("/v1/tuning", {"values": {"no.such.knob": 1}})
check("an unknown knob is 400 and logs nothing", code == 400 and len(rows()[n0:]) == 2)

finish("G-LAUNCH-ROUTES")
