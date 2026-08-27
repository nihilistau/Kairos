#!/usr/bin/env python
"""G-HOUSE-HANDS — she may touch the lights, and nothing else, and only when he is here.

WHAT THIS ANSWERS. `house.py` promised in its own docstring that acting "gets its own
design, its own gate and its own row in OFF-BY-DEFAULT". This is the gate half.

THE GUARD THAT IS NOT A LIST. His `switch.*` entities include a KETTLE, a 3D-printer plug
and a fingerbot. The first design leaned on Home Assistant's Assist exposure as the
boundary, on the reasoning that it lives where the house lives and the owner edits it in a
UI. Read against his real machine on 2026-08-27, that list had FORTY-FOUR entities exposed
that nobody chose — `expose_new` defaults ON — including `switch.kettle_start`. A boundary
that admits new things by default is not a boundary, so the floor is a CLOSED SET OF
DOMAINS in code, and the allowlist only makes it specific.

  1. OFF BY DEFAULT, and off means the verbs are ABSENT rather than present-and-refusing.
  2. THE DOMAIN FLOOR HOLDS even when the allowlist says otherwise — a mistyped row must
     not be able to boil water.
  3. AN EMPTY OR MISSING LIST DENIES, rather than allowing.
  4. ON REQUEST ONLY — an autonomous lane reaching this tool is a different product, and
     it gets its own arming when it is wanted.
  5. NOTHING IS CALLED when a guard refuses. A refusal that still POSTs is not a refusal.

OFFLINE. No GPU, no daemon, no Home Assistant — the HTTP door is replaced and asserted on.
"""
import io
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from _gate import sandbox   # noqa: E402
sandbox("g_house_hands")

os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"

from harness.homeassistant import hands as H   # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


# ── THE HTTP DOOR IS REPLACED, and every call it receives is recorded. A guard that
# refuses in its return value while still reaching Home Assistant has not refused.
CALLS = []


def _fake_call(service, entity_id, data=None):
    CALLS.append((service, entity_id, data))
    return True, ""


H._call = _fake_call

ALLOW = os.path.join(os.environ["SP_BACKUP_DIR"], "..", "house-allow.json")
ALLOW = os.path.abspath(ALLOW)
os.environ["SP_HOUSE_ALLOW"] = ALLOW


def write_allow(d):
    with io.open(ALLOW, "w", encoding="utf-8") as f:
        json.dump(d, f)


GOOD = {"the lamp": "light.lamp", "the fan": "fan.desk"}

print("1. OFF BY DEFAULT, and off means ABSENT")
os.environ["SP_HOUSE_HANDS"] = "0"
write_allow(GOOD)
check("the knob reads off", not H.armed())
r = H.act("the lamp", on=True, _present=1.0)
check("...so an act refuses", not r["ok"], r)
check("...and nothing was called", not CALLS, CALLS)
from harness.skills.house import house_tools   # noqa: E402
check("...and she is offered no house verbs at all", house_tools() == [],
      [getattr(t, "name", "?") for t in house_tools()])
os.environ["SP_HOUSE_HANDS"] = "1"
check("armed, the verbs appear", len(house_tools()) == 3,
      [getattr(t, "name", "?") for t in house_tools()])

print("\n2. THE DOMAIN FLOOR HOLDS, whatever the list says")
# HIS ACTUAL SWITCHES. The list is wrong here on purpose: this is the case where somebody
# put a row in the file that should not be there, and the floor has to catch it anyway.
write_allow({"the kettle": "switch.kettle_start",
             "the fingerbot": "switch.fingerbot_switch",
             "the printer": "switch.3d_printer_plug",
             "the lamp": "light.lamp"})
CALLS[:] = []
for name in ("the kettle", "the fingerbot", "the printer"):
    r = H.act(name, on=True, _present=1.0)
    check("%-14s is refused even though it is IN the list" % name, not r["ok"], r.get("why"))
check("...and not one of them was called", not CALLS, CALLS)
r = H.act("the lamp", on=True, _present=1.0)
check("...while the light in the same list still works", r["ok"], r)
check("switch is not an actable domain", "switch" not in H.ACTABLE_DOMAINS,
      H.ACTABLE_DOMAINS)

print("\n3. AN EMPTY OR MISSING LIST DENIES")
CALLS[:] = []
write_allow({})
check("empty list: nothing resolves", not H.act("the lamp", on=True, _present=1.0)["ok"])
os.remove(ALLOW)
check("missing file: nothing resolves", not H.act("the lamp", on=True, _present=1.0)["ok"])
with io.open(ALLOW, "w", encoding="utf-8") as f:
    f.write("{ this is not json")
check("malformed file: nothing resolves", not H.act("the lamp", on=True, _present=1.0)["ok"])
check("...and nothing was called through any of it", not CALLS, CALLS)

print("\n4. ON REQUEST ONLY")
write_allow(GOOD)
CALLS[:] = []
r = H.act("the lamp", on=True, _present=H.present_window() + 60)
check("he spoke too long ago -> refused", not r["ok"] and r.get("not_present"), r)
r = H.act("the lamp", on=True, _present=None)
check("nothing can say when he last spoke -> refused", not r["ok"], r)
check("...and nothing was called", not CALLS, CALLS)
r = H.act("the lamp", on=True, _present=5.0)
check("he is here -> it acts", r["ok"] and CALLS, r)
check("...and it used the entity id, not the spoken name",
      CALLS[-1][1] == "light.lamp", CALLS[-1:])
# ONE CLOCK. A second "when did he last speak" would be two truths about one fact.
_src = io.open(os.path.join(ROOT, "harness", "homeassistant", "hands.py"),
               encoding="utf-8").read()
check("...read from the clock the room veto already uses",
      "_seconds_since_he_spoke" in _src)
check("...and the window is that module's number, not a second copy",
      "ROOM_VETO_S" in _src and "PRESENT_S = 15" not in _src,
      "a fallback constant is a second truth about one fact")
# ...and if that module cannot be read at all, it must REFUSE rather than pick a number.
_real = H.present_window
try:
    H.present_window = lambda: None
    check("...and an unreadable window refuses the act",
          not H.act("the lamp", on=True, _present=5.0)["ok"])
finally:
    H.present_window = _real

print("\n5. WHAT IT ACTUALLY SENDS")
CALLS[:] = []
H.act("the lamp", colour="red", _present=5.0)
check("a colour turns it on and sends rgb", CALLS and CALLS[-1][0] == "turn_on"
      and CALLS[-1][2].get("rgb_color") == [255, 0, 0], CALLS[-1:])
H.act("the lamp", brightness=40, _present=5.0)
check("brightness is sent as a percentage", CALLS[-1][2].get("brightness_pct") == 40,
      CALLS[-1:])
r = H.act("the lamp", colour="ultraviolet", _present=5.0)
check("an unknown colour refuses and names the ones it knows",
      not r["ok"] and "red" in r["why"], r.get("why"))
r = H.act("the fan", colour="red", _present=5.0)
check("a fan has no colour, and says so", not r["ok"], r.get("why"))
CALLS[:] = []
H.act("the lamp", on=False, _present=5.0)
check("off is turn_off with no payload",
      CALLS[-1][0] == "turn_off" and not CALLS[-1][2], CALLS[-1:])
r = H.act("the lamp", _present=5.0)
check("neither on nor off nor anything else -> it asks", not r["ok"], r.get("why"))
r = H.act("the trebuchet", on=True, _present=5.0)
check("a name he never listed refuses and offers what it has",
      not r["ok"] and "the lamp" in r["why"], r.get("why"))

print("\nG-HOUSE-HANDS: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_house_hands.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_house_hands", "pass": PASS, "fail": FAIL,
               "domains": list(H.ACTABLE_DOMAINS),
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
sys.exit(1 if FAIL else 0)
