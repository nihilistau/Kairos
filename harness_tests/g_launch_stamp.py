"""G-LAUNCH-STAMP — what she was launched with, and the fingerprint on every reply. OFFLINE.

`harness/launch/stamp.py` records, at every full launch, the resolved profile values and the
build_env she was started with (`var/launched.json`), and reduces that plus the live tuning
overrides to an 8-hex fingerprint stamped on each reply. The full set behind a fingerprint is
kept once in `var/config-fingerprints.jsonl`.

  (a) FINGERPRINT is stable across dict order and moves with one env value or one override.
  (b) ROUND TRIP: write_launched -> read_launched keeps setup, values["decode.attn_split"], fp.
  (c) ABSENT FILE: read_launched() is None; current_stamp()["setup"] == "unknown".
  (d) REMEMBER is idempotent per fingerprint (one line), including across a fresh process.
  (e) SECRETS: a KEY/TOKEN/SECRET/PASSWORD env value is never stored; a key FILE path is.
  (f) serve.py calls write_launched on the full-launch path, never under --gateway-only.

    python harness_tests/g_launch_stamp.py
"""
from __future__ import annotations

import ast
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
sandbox("g_launch_stamp")

VAR = tempfile.mkdtemp(prefix="g_launch_stamp_var_")
os.environ["SP_LAUNCH_VAR"] = VAR

from harness.launch import stamp  # noqa: E402
from harness.tuning import registry  # noqa: E402

# the registry must be reading the sandbox's file, never her real var/tuning.json
check("the tuning registry is sandboxed", "var" + os.sep + "tuning.json" not in registry.STORE
      or os.environ.get("SP_TUNING_FILE") == registry.STORE, registry.STORE)

# ── (a) fingerprint
env = {"SP_A": "1", "SP_B": "2"}
ov = {"kairos.max_chain": 3}
fp = stamp.fingerprint(env, ov)
check("fingerprint is 8 hex", len(fp) == 8 and all(ch in "0123456789abcdef" for ch in fp), fp)
check("fingerprint ignores dict order",
      fp == stamp.fingerprint({"SP_B": "2", "SP_A": "1"}, {"kairos.max_chain": 3}))
check("one env value changes it", fp != stamp.fingerprint({"SP_A": "1", "SP_B": "3"}, ov))
check("one override changes it", fp != stamp.fingerprint(env, {"kairos.max_chain": 4}))

# ── (b) round trip
check("launched_path lives under the var root",
      os.path.dirname(stamp.launched_path()) == VAR, stamp.launched_path())
check("(c) absent -> read_launched() is None", stamp.read_launched() is None)
check("(c) absent -> setup is 'unknown'", stamp.current_stamp()["setup"] == "unknown")

profile = {"_profile_name": "fx", "paths": {"model": "m.sp-model"},
           "decode": {"attn_split": 2, "_note": "dropped"}, "_private": {"x": 1},
           "deep": {"a": {"b": {"c": 7}}}}
env2 = {"SP_X": "1", "SP_API_KEY": "sk-live-abc123", "SP_TOKEN_FILE": __file__,
        "SP_PASSWORD": "hunter2", "PATH_LIKE": "yes"}
rec = stamp.write_launched(profile, env2, "my setup")
back = stamp.read_launched()
check("round trip keeps setup", back and back["setup"] == "my setup", back)
check("round trip keeps values['decode.attn_split']",
      back and back["values"].get("decode.attn_split") == 2, back and back["values"])
check("round trip keeps the fingerprint", back and back["fingerprint"] == rec["fingerprint"])
check("profile name recorded", back and back["profile"] == "fx")
check("_-prefixed keys dropped", back and not any("_note" in k or "_private" in k
                                                  for k in back["values"]), back and back["values"])
check("deeper tables flatten as a.b.c", back and back["values"].get("deep.a.b.c") == 7)
check("no stray temp file left", sorted(os.listdir(VAR)) == sorted(
    n for n in os.listdir(VAR) if not n.endswith(".tmp")), os.listdir(VAR))

# ── (g) a restart is a settings change: old fingerprint -> new, with the setup's name
from harness.launch import changes  # noqa: E402
_r = [x for x in changes.tail(50) if x["source"] == "launch" and x["what"] == "restart"]
check("the first launch is logged as a restart from None",
      len(_r) == 1 and _r[0]["old"] is None and _r[0]["new"] == rec["fingerprint"]
      and _r[0].get("setup") == "my setup", _r)
rec_b = stamp.write_launched(profile, dict(env2, SP_X="2"), "other")
_r = [x for x in changes.tail(50) if x["source"] == "launch" and x["what"] == "restart"]
check("the next launch is logged old = the previous fingerprint, new = this one",
      len(_r) == 2 and _r[1]["old"] == rec["fingerprint"] and _r[1]["new"] == rec_b["fingerprint"]
      and _r[1]["old"] != _r[1]["new"] and _r[1].get("setup") == "other", _r)
rec = stamp.write_launched(profile, env2, "my setup")        # back to the state the rest expects
back = stamp.read_launched()

# ── (e) secrets
raw = open(stamp.launched_path(), encoding="utf-8").read()
check("a KEY value is not stored", "sk-live-abc123" not in raw)
check("a PASSWORD value is not stored", "hunter2" not in raw)
check("a key FILE path is kept", back and back["env"].get("SP_TOKEN_FILE") == __file__)
check("ordinary env kept", back and back["env"].get("SP_X") == "1")
check("the fingerprint is over the redacted env",
      back and back["fingerprint"] == stamp.fingerprint(back["env"], registry._load()))

# ── (c) stamp from a launch record
cs = stamp.current_stamp()
check("current_stamp reports the launch setup", cs["setup"] == "my setup", cs)
check("current_stamp cfg is the fingerprint now", cs["cfg"] == back["fingerprint"], cs)

# ── (d) remember
fpath = os.path.join(VAR, "config-fingerprints.jsonl")


def _lines():
    return [json.loads(x) for x in open(fpath, encoding="utf-8") if x.strip()] \
        if os.path.exists(fpath) else []


n0 = len(_lines())
stamp.remember("deadbeef", {"SP_A": "1"}, {})
stamp.remember("deadbeef", {"SP_A": "1"}, {})
check("remember twice leaves one line", len([r for r in _lines() if r["fp"] == "deadbeef"]) == 1)
stamp._SEEN = None                                    # a fresh process: the scan must find it
stamp.remember("deadbeef", {"SP_A": "1"}, {})
check("remember across a fresh process leaves one line",
      len([r for r in _lines() if r["fp"] == "deadbeef"]) == 1)
check("a new fingerprint appends", len(_lines()) == n0 + 1, _lines())
check("the stored set has fp/env/tune/at", set(_lines()[-1]) == {"fp", "env", "tune", "at"})

# ── (c') no launch record: SP_* from os.environ, secrets redacted
os.remove(stamp.launched_path())
os.environ["SP_PROBE_VALUE"] = "v"
os.environ["SP_PROBE_API_KEY"] = "sk-should-not-be-stored"
cs2 = stamp.current_stamp()
check("no record -> unknown", cs2["setup"] == "unknown" and len(cs2["cfg"]) == 8, cs2)
check("no record -> the fallback env never stores a secret",
      "sk-should-not-be-stored" not in open(fpath, encoding="utf-8").read())

# ── (f) serve.py wiring
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "serve.py"), encoding="utf-8").read()
tree = ast.parse(src)
main = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "main")
parents = {}
for p in ast.walk(main):
    for ch in ast.iter_child_nodes(p):
        parents[ch] = p
calls = [n for n in ast.walk(main) if isinstance(n, ast.Call)
         and getattr(n.func, "id", getattr(n.func, "attr", "")) == "write_launched"]
check("serve.py main() calls write_launched once", len(calls) == 1, len(calls))


def _under_gateway_only(node):
    while node in parents:
        node = parents[node]
        if isinstance(node, ast.If) and "--gateway-only" in ast.dump(node.test):
            return True
    return False


check("...and not under the --gateway-only branch",
      bool(calls) and not _under_gateway_only(calls[0]))
ready = [n for n in ast.walk(main) if isinstance(n, ast.Constant) and isinstance(n.value, str)
         and "READY." in n.value]
check("...before the READY line", bool(calls) and bool(ready)
      and calls[0].lineno < max(r.lineno for r in ready), (calls and calls[0].lineno))

finish("G-LAUNCH-STAMP")
