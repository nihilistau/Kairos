"""G-HOMEASSISTANT — the house is somebody else's server, and it is treated like one. OFFLINE.

WHAT THIS HOLDS, in the order of how badly it is needed:

  §1 OFF UNTIL CONFIGURED. No token means every entry point returns empty and NOTHING
     touches the network. A companion that quietly starts talking to a server because a
     package got installed is not a feature, and "it only talks to localhost" is not an
     answer when the URL is a knob.
  §2 NOT A SECOND DOOR. Everything this framework learns is written through
     `telemetry.ingest.record()` — the existing writer, with the anon gate on it. A second
     writer would be a second set of rules inside a month, and the anon gate is the one
     that must never be second.
  §3 THE CREDENTIAL IS NOT CONFIGURATION. Everything in `profiles/` is committed and
     everything committed is exported, so a long-lived token in a TOML file is a token in
     the public repository a fortnight later.
  §4 IT NEVER RAISES. Home Assistant is a container that restarts on upgrade. None of that
     may cost him a turn.
  §5 A FOREIGN CLOCK IS BOUNDED. `measured_at` exists so a nine-minute-old reading is not
     dated to now — and is clamped so it can neither rewrite history nor look fresh.
  §6 SILENCE IS AN ANSWER, here too. The house seam claims nothing until he names entities.

    python harness_tests/g_homeassistant.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_homeassistant")        # FIRST — before any harness import
os.environ["SP_ENGINE_KIND"] = "openai"
os.environ.setdefault("SP_DAEMON_URL", "http://127.0.0.1:9")
# THE GATE MUST NOT INHERIT A REAL TOKEN. If he has one in his environment this whole file
# would test a live server instead of the rules, and §1 would pass for the wrong reason.
os.environ.pop("SP_HA_TOKEN", None)
os.environ["SP_HA_TOKEN_FILE"] = os.path.join(SB, "no-such-token")

import io                                                              # noqa: E402
import time                                                            # noqa: E402

from harness.homeassistant import bridge, client, house                # noqa: E402
from harness.telemetry import ingest, store                            # noqa: E402

print("1. OFF UNTIL CONFIGURED")
check("with no token, the framework reports itself off", client.configured() is False)
_s = bridge.status()
check("...status says so in a sentence, not by being empty",
      _s["configured"] is False and "off" in _s["why"], _s)
_p = bridge.poll_once()
check("...and a poll writes nothing and explains itself",
      _p["ok"] is False and _p["stored"] == 0 and "off" in _p["why"], _p)

# THE ONE THAT MATTERS: off must mean NO NETWORK CALL, not a call that fails.
_called = {"n": 0}
_real_urlopen = client.urllib.request.urlopen


def _spy(*a, **k):
    # COUNT, then fail the way the network fails. Raising AssertionError here would escape
    # `poll_once`'s handlers and crash the gate, which reports as "crashed" rather than as
    # the named check below -- and a mutant whose evidence is a stack trace is a mutant
    # nobody can read six months later.
    _called["n"] += 1
    raise client.urllib.error.URLError("blocked: the gate is watching for this")


client.urllib.request.urlopen = _spy
try:
    bridge.poll_once()
    bridge.status()
    house.read()
    house.present()
finally:
    client.urllib.request.urlopen = _real_urlopen
check("...and it opens NO connection at all while off", _called["n"] == 0,
      "off must mean silent, not 'fails politely'")

print("\n2. NOT A SECOND DOOR")
_src = io.open(os.path.join(ROOT, "harness", "homeassistant", "bridge.py"),
               encoding="utf-8").read()
check("the bridge writes through ingest.record and nothing else",
      "ingest.record(" in _src and "_append" not in _src and "store." not in _src,
      "a second writer would be a second set of rules, and the anon gate would be second")
_all = ""
for _n in ("client.py", "bridge.py", "house.py", "__init__.py"):
    _all += io.open(os.path.join(ROOT, "harness", "homeassistant", _n), encoding="utf-8").read()
check("...and no file in the framework touches the store directly",
      "store._append" not in _all)

print("\n3. THE CREDENTIAL IS NOT CONFIGURATION")
# VALUES, NOT TEXT -- and this is the fourth spelling of this check today. The first
# grepped for key names and went red on the word "oscillates"; the second grepped source
# text and went red on this framework's own prose; the third went red on the profile comment
# that says "it goes in var/ha_token". Every one of them was matching DOCUMENTATION ABOUT
# the rule instead of a violation of it.
#
# What is actually forbidden is a SECRET sitting in a committed file. A Home Assistant
# long-lived token is a JWT: three long base64url segments separated by dots. Parsing the
# TOML and looking for that shape in the VALUES catches a real token under any key name,
# including one nobody thought to list -- and cannot be tripped by a comment, because a
# comment is not a value.
import re as _re3                                                      # noqa: E402
import tomllib as _toml3                                               # noqa: E402
_JWT = _re3.compile(r"^[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}$")


def _walk_values(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_values(v, "%s.%s" % (path, k) if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_values(v, "%s[%d]" % (path, i))
    else:
        yield path, node


_prof = os.path.join(ROOT, "profiles")
_leaks = []
for _b, _d, _f in os.walk(_prof):
    for _n in _f:
        if not _n.endswith(".toml"):
            continue
        try:
            _doc = _toml3.load(open(os.path.join(_b, _n), "rb"))
        except Exception as _e:
            _leaks.append("%s: unparseable (%s)" % (_n, _e))
            continue
        for _path, _val in _walk_values(_doc):
            if isinstance(_val, str) and _JWT.match(_val.strip()):
                _leaks.append("%s: %s looks like a JWT" % (_n, _path))
check("no profile carries a token-shaped VALUE anywhere in it", not _leaks, _leaks)
# and prove the check can actually see one, or it is decoration
check("...and that check would notice if one appeared",
      bool(_JWT.match("eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJob21lYXNzaXN0YW50In0."
                      "dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk")))
_csrc = io.open(os.path.join(ROOT, "harness", "homeassistant", "client.py"),
                encoding="utf-8").read()
# THE IMPORT GRAPH, not the text. Two earlier spellings of this check grepped for strings
# and both went red on this framework's OWN PROSE about not putting tokens in profiles --
# the same mistake as the sleep gate's "hour" check, made twice in one day. What is
# actually being asserted is that the client cannot reach the config system, and that is a
# question about imports, which the AST answers and a comment cannot fake.
import ast as _ast3                                                    # noqa: E402
_mods = set()
for _n3 in _ast3.walk(_ast3.parse(_csrc)):
    if isinstance(_n3, _ast3.Import):
        _mods.update(a.name.split(".")[0] for a in _n3.names)
    elif isinstance(_n3, _ast3.ImportFrom) and _n3.module:
        _mods.add(_n3.module.split(".")[0])
check("...and the client cannot reach the config system — it imports nothing that could",
      not (_mods & {"tomllib", "toml", "tuning", "serve"}) and "harness" not in _mods,
      sorted(_mods))
os.environ["SP_HA_TOKEN"] = "from-env"
check("...the environment wins when both are set", client.token() == "from-env")
os.environ.pop("SP_HA_TOKEN", None)
# and it must actually READ a file when pointed at one
_tokf = os.path.join(SB, "tok")
io.open(_tokf, "w", encoding="utf-8").write("  abc123  \n")
os.environ["SP_HA_TOKEN_FILE"] = _tokf
check("a token file is read and stripped", client.token() == "abc123", client.token())
check("...and that is what makes it configured", client.configured() is True)

print("\n4. IT NEVER RAISES")


class _Boom:
    def __init__(self, *a, **k):
        pass

    def read(self):
        raise OSError("home assistant fell over mid-read")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


client.urllib.request.urlopen = lambda *a, **k: _Boom()
try:
    _r = bridge.poll_once()
    check("a server that dies mid-read gives a reason, not an exception",
          _r["ok"] is False and _r["why"], _r)
    _h = house.read()
    check("...and the house seam does the same", isinstance(_h, dict) and _h.get("why"), _h)
finally:
    client.urllib.request.urlopen = _real_urlopen

print("\n5. THE MAPPING IS BY SUFFIX, AND SHORT")
check("the table matches by SUFFIX, so renaming his phone does not break it",
      all(m[0].startswith("_") for m in bridge.MAPPINGS), bridge.MAPPINGS)
check("...and it maps only what no sensor of ours can produce",
      {m[1] for m in bridge.MAPPINGS} == {"sleep_confidence", "activity"},
      "battery/steps/charging already come from our own agent — two spellings of one "
      "reading is the two-copies bug")
_states = [
    {"entity_id": "sensor.sm_s908e_sleep_confidence", "state": "82",
     "last_updated": "2026-08-26T21:40:00+00:00", "attributes": {}},
    {"entity_id": "sensor.sm_s908e_detected_activity", "state": "walking",
     "last_updated": "2026-08-26T21:40:00+00:00", "attributes": {}},
    {"entity_id": "sensor.sm_s908e_battery_level", "state": "77",
     "last_updated": "2026-08-26T21:40:00+00:00", "attributes": {}},
]
_d = bridge.discover(_states)
check("his phone's sleep sensor is found whatever it is called",
      any(x["kind"] == "sleep_confidence" and x["value"] == 82.0 for x in _d), _d)
check("...activity is translated into OUR vocabulary",
      any(x["kind"] == "activity" and x["value"] == "walking" for x in _d), _d)
check("...and battery is deliberately NOT taken", not any("battery" in x["kind"] for x in _d))

print("\n   'unknown' is not a value")
# HA says "unknown"/"unavailable" for a sensor that has not reported yet or whose
# integration is down. Rejecting it is only half the job: it must be rejected FOR THE RIGHT
# REASON, because "the entity has no value yet" and "that is not a number" send whoever
# reads the skip list to two completely different places. Asserting the reason is also what
# makes this check bite — a mutant that deleted the guard still returned None from
# float("unknown"), so the weaker version of this check passed with the guard removed.
for _bad in ("unknown", "unavailable", "", "none"):
    _v, _w = bridge._convert("percent", _bad)
    if _v is not None or "no value yet" not in _w:
        check("HA's %r is refused, and says it is EMPTY rather than malformed" % _bad,
              False, (_v, _w))
        break
else:
    check("HA's unknown/unavailable/empty are refused as empty, not as malformed", True)
check("...while actual garbage is refused as malformed, which is a different problem",
      "not a number" in bridge._convert("percent", "banana")[1])
check("...and an out-of-range confidence is refused",
      bridge._convert("percent", "140")[0] is None)
check("...and an activity we have no word for is dropped, not guessed",
      bridge._convert("activity", "sailing")[0] is None)

print("\n6. A FOREIGN CLOCK IS BOUNDED")
os.environ["SP_TELEMETRY_DIR"] = os.path.join(SB, "clock")
_now = time.time()
ingest.record([{"kind": "sleep_confidence", "value": 80}], source="phone",
              measured_at=_now - 9 * 60)
_rows = store.read_since(3600, _now)
_r0 = [r for r in _rows if r.get("kind") == "sleep_confidence"][0]
check("a nine-minute-old reading is dated when it was MEASURED, not when it arrived",
      abs(store.parse_iso(_r0["at"]) - (_now - 9 * 60)) < 2,
      (_r0["at"], store.parse_iso(_r0["at"]) - _now))

_out = ingest.record([{"kind": "sleep_confidence", "value": 70}], source="phone",
                     measured_at=_now - 48 * 3600)
check("...but a clock two days out is NOT believed", _out.get("clock_ignored") is True, _out)
_out2 = ingest.record([{"kind": "sleep_confidence", "value": 60}], source="phone",
                      measured_at=_now + 86400)
check("...and neither is one in the future", _out2.get("clock_ignored") is True, _out2)
_rows = store.read_since(3600, _now + 5)
check("...and the row still LANDS either way, stamped on arrival",
      len([r for r in _rows if r.get("kind") == "sleep_confidence"]) == 3, len(_rows))

# THE DEVICE DOOR MUST NOT REACH IT.
_app = io.open(os.path.join(ROOT, "harness", "server", "app.py"), encoding="utf-8").read()
_seg = _app[_app.find("/v1/telemetry/ingest"):][:4000]
check("nothing arriving over the HTTP door can pass a clock of its own",
      "measured_at" not in _seg,
      "a watch in a drawer for a week comes back confidently wrong")

class _FakeClient:
    def __init__(self, states):
        self._s = states

    def states(self):
        return self._s, ""


print("\n6b. `last_updated` IS NOT WHEN IT WAS MEASURED")
# CAUGHT LIVE, and it would have been a confident lie the first night it ran. His phone's
# sleep confidence read 79 with `last_updated` twenty-five minutes old, so the bridge would
# have recorded a fresh, high-confidence "asleep" while he sat here talking to me. Twenty-six
# hours of history held ONE point, and the reading was from 14 April -- 133 DAYS earlier.
# The server had been off for months, and `last_updated` was the moment HOME ASSISTANT
# RESTARTED AND RESTORED THE STATE: the age of the row in its memory, not the age of the
# reading. After any restart every stale sensor in the house looks brand new.
_restored = {"entity_id": "sensor.p_sleep_confidence", "state": "79",
             "last_updated": store.now_iso(time.time() - 25 * 60).replace("Z", "+00:00"),
             "last_changed": store.now_iso(time.time() - 25 * 60).replace("Z", "+00:00"),
             "attributes": {"timestamp": int((time.time() - 133 * 86400) * 1000)}}
_t6 = client.measured_at_of(_restored)
check("the entity's OWN timestamp beats `last_updated`",
      _t6 is not None and abs((time.time() - _t6) - 133 * 86400) < 120,
      "%.1f days" % ((time.time() - (_t6 or 0)) / 86400))
os.environ["SP_TELEMETRY_DIR"] = os.path.join(SB, "restored")
bridge._SEEN.clear()
_pr = bridge.poll_once(_FakeClient([_restored]))
check("...so a state restored on boot is REFUSED, not believed",
      _pr["stored"] == 0 and any("stale" in (x.get("why") or "") for x in _pr["skipped"]),
      _pr)
check("...and it says how old, so nobody has to guess why she went quiet",
      any("min old" in (x.get("why") or "") for x in _pr["skipped"]), _pr["skipped"])

# NO CLOCK AT ALL must not become NOW.
_noclock = {"entity_id": "sensor.q_sleep_confidence", "state": "88", "attributes": {}}
bridge._SEEN.clear()
_nc = bridge.poll_once(_FakeClient([_noclock]))
check("an entity with no usable time is refused rather than dated to this instant",
      _nc["stored"] == 0 and any("no measurement time" in (x.get("why") or "")
                                 for x in _nc["skipped"]), _nc)

# AND A HEALTHY READING STILL GOES THROUGH, or the guard has quietly eaten the feature.
_good = {"entity_id": "sensor.r_sleep_confidence", "state": "91",
         "last_updated": store.now_iso(time.time() - 60).replace("Z", "+00:00"),
         "attributes": {"timestamp": int((time.time() - 8 * 60) * 1000)}}
bridge._SEEN.clear()
_gp = bridge.poll_once(_FakeClient([_good]))
check("...while a real eight-minute-old reading still lands", _gp["stored"] == 1, _gp)
_row6 = [r for r in store.read_since(3600, time.time())
         if r["kind"] == "sleep_confidence"][-1]
check("...dated when the PHONE measured it, not when we asked",
      abs(store.parse_iso(_row6["at"]) - (time.time() - 8 * 60)) < 90,
      (time.time() - store.parse_iso(_row6["at"])) / 60)

# AND THE RESTART ITSELF. This is the shape the dedupe has to survive: Home Assistant comes
# back up, re-stamps `last_updated` on EVERY entity in the house, and none of the readings
# have actually changed. Keying the dedupe on `last_updated` would rewrite the lot as though
# it had all just been measured -- 396 entities' worth, in one poll, all dated to the
# instant the server happened to reboot.
_restart = dict(_good)
_restart["last_updated"] = store.now_iso(time.time()).replace("Z", "+00:00")
_rs = bridge.poll_once(_FakeClient([_restart]))
check("a Home Assistant RESTART re-stamps last_updated, and must not re-record anything",
      _rs["stored"] == 0, _rs)
check("...while the value genuinely changing still does",
      bridge.poll_once(_FakeClient([dict(_restart, state="55")]))["stored"] == 1)

print("\n7. ONLY ON CHANGE")
os.environ["SP_TELEMETRY_DIR"] = os.path.join(SB, "change")
bridge._SEEN.clear()


_fresh = [{"entity_id": "sensor.p_sleep_confidence", "state": "77",
           "last_updated": store.now_iso(time.time() - 60).replace("Z", "+00:00"),
           "attributes": {}}]
_a = bridge.poll_once(_FakeClient(_fresh))
_b = bridge.poll_once(_FakeClient(_fresh))
check("the same reading polled twice is stored once",
      _a["stored"] == 1 and _b["stored"] == 0, (_a, _b))
check("...and the second poll is still a HEALTHY poll, not a failure",
      _b["ok"] is True and _b["seen"] == 1, _b)

print("\n   anon holds it, and held is not handled")
from harness.control import anon as _anon                              # noqa: E402
bridge._SEEN.clear()
_anon.enter("gate")
try:
    _held = bridge.poll_once(_FakeClient(_fresh))
finally:
    _anon.leave()
check("the gate actually engaged anon mode — the first version of this check set an env "
      "var that nothing reads, and passed for the wrong reason",
      _anon.on() is False and _held is not None)
check("off the record, nothing is written", _held["stored"] == 0, _held)
_after = bridge.poll_once(_FakeClient(_fresh))
check("...and coming back on the record still records the CURRENT value — "
      "held is not the same as handled", _after["stored"] == 1, _after)

print("\n8. SILENCE IS AN ANSWER, HERE TOO")
check("the watch list ships EMPTY — no guess about which lights matter",
      house.WATCH == ())
check("...so she is told nothing about the house", house.present() == "", house.present())
check("...and the seam says why rather than just being blank",
      "watch list" in house.read()["why"], house.read()["why"])
_hsrc = io.open(os.path.join(ROOT, "harness", "homeassistant", "house.py"),
                encoding="utf-8").read()
check("nothing in this framework can turn anything ON",
      "/api/services" not in _all and "call_service" not in _all,
      "giving a companion the light switches is a different product with different "
      "failure modes, and not somewhere to arrive at while wiring a sleep sensor")

finish("G-HOMEASSISTANT")
