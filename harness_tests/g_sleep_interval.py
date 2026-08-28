#!/usr/bin/env python
"""G-SLEEP-INTERVAL — when he fell asleep is a band, and when he woke is a ceiling.

WHAT THIS ANSWERS. "What time did I fall asleep?" was only answerable from the classifier's
instantaneous confidence, and that number lags in both directions. MEASURED against his own
account on 2026-08-27 (asleep "about" 15:30-20:00):

    15:33  15     he says he is going under; the phone says awake
    16:22  87     first crossing        -- ~50 min late
    20:05  95     he is up by now
    20:59  53     finally drops         -- ~60 min late

Any single minute read off that curve is wrong twice a night, stated confidently. And his
truth is itself fuzzy — falling asleep can take an hour or two, and a night can be an hour
of sleep, then waking, then a long time turning over — so a band is the honest SHAPE of the
answer, not a hedge about the instrument.

  1. IT ABSTAINS rather than invent a night, and "I cannot see one" is not "you had none".
  2. THE BOUNDS ARE HIS WORDS, not the phone's opinion. A low reading is an inference and a
     bound built on one can put the truth OUTSIDE the band — the first cut did exactly that.
  3. WAKING IS ONE-SIDED. The classifier lags both ways, so both its edges are UPPER
     bounds; falling asleep gets a band and waking gets a ceiling. Wakefulness is provable
     and sleep is not, and that asymmetry is real rather than a gap in the instrument.
  4. A TURN INSIDE A RUN BREAKS IT, so "slept an hour, woke, tossed and turned" survives
     instead of being smoothed into one long sleep he did not have.
  5. THROUGH THE REAL SKILL, with the store and the transcript it actually reads.

OFFLINE. No GPU, no daemon.
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
sandbox("g_sleep_interval")

os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"

from harness.telemetry import body as B     # noqa: E402
from harness.telemetry import store as S    # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


NOW = time.time()
M = 60.0


def conf(mins_ago, value):
    return {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - mins_ago * M)),
            "kind": "sleep_confidence", "source": "phone", "value": float(value)}


# ── HIS NIGHT, to scale: awake, a slow slide, four hours sure, then a lagging tail ──
NIGHT = ([conf(m, 20) for m in (400, 395, 390)]          # plainly awake
         + [conf(m, 88) for m in range(380, 140, -10)]   # four hours of sure sleep
         + [conf(m, 75) for m in (135, 130)]             # the tail that runs late
         + [conf(m, 20) for m in (100, 95, 90)])         # phone finally agrees
SAID_UP = NOW - 398 * M          # his last message, BEFORE the phone's last low
                                 # (16:00 vs 16:04 on the night this was measured)
SAID_BACK = NOW - 60 * M         # his first message after

print("1. IT ABSTAINS rather than invent a night")
check("an empty store says nothing", B.sleep_interval([], NOW) is None)
check("...and a handful of awake readings is not a night",
      B.sleep_interval([conf(30, 10), conf(20, 12)], NOW) is None)
check("...nor is a still half-hour on the sofa",
      B.sleep_interval([conf(m, 90) for m in (40, 35, 30)], NOW, min_run_s=20 * 60) is None,
      "a 10-minute run cleared the floor")

print("\n2. THE BOUNDS ARE HIS WORDS, not the phone's opinion")
v = B.sleep_interval(NIGHT, NOW, awake_at=[SAID_UP, SAID_BACK])
check("a night is found", bool(v))
check("the lower bound IS the moment he last spoke",
      abs(v["asleep_after"] - SAID_UP) <= 1.5, (v["asleep_after"], SAID_UP))
check("...and it is EARLIER than the phone's last awake reading, so the band is wider",
      v["asleep_after"] < v["phone_awake_until"],
      "phone %.0f vs said %.0f" % (v["phone_awake_until"], v["asleep_after"]))
check("...and says what it rests on", v["bounded_by"] == "the operator's own words", v["bounded_by"])
# THE POINT OF THE BAND IS THAT THE ANSWER IS INSIDE IT. He went under somewhere after his
# last word and before the phone was sure; both ends must admit that.
check("the band CONTAINS the interval he could have fallen asleep in",
      v["asleep_after"] < v["asleep_before"])
n = B.sleep_interval(NIGHT, NOW)
check("with no testimony it says so plainly", n["bounded_by"] == "the phone alone",
      n["bounded_by"])
check("...and offers no lower bound it cannot support", n["asleep_after"] is None,
      n["asleep_after"])

print("\n3. WAKING IS A CEILING, NOT A BAND")
check("it reports woke_by", "woke_by" in v)
check("...and no 'woke_after', which would be the same error mirrored",
      "woke_after" not in v, sorted(v))
# The classifier's last sure reading is AFTER he actually woke, so it is an upper bound.
# His next message is too. The ceiling is the tighter of the two.
#
# NOTE the run ends at 130, not 140: the "lagging tail" in the fixture reads 75, which is
# still over SLEEP_SURE. That IS the lag being modelled — the phone stays sure for a while
# after he is up — and it is why the ceiling can only ever be an upper bound.
# The store stamps whole seconds, so this is a tolerance and not an equality.
_LAST_SURE = NOW - 130 * M
check("the ceiling is the tighter of last-sure and his next word",
      abs(v["woke_by"] - min(_LAST_SURE, SAID_BACK)) <= 1.5,
      "%.0f vs %.0f" % (v["woke_by"], min(_LAST_SURE, SAID_BACK)))
check("...and a real waking BEFORE the ceiling is admitted",
      (NOW - 150 * M) <= v["woke_by"])

print("\n3b. A RUN THAT ENDS BECAUSE THE DATA ENDED IS NOT A WAKING")
# HIS NIGHT, 2026-08-28: high from 23:04 to 01:25, then a 188-MINUTE HOLE, then 48 at 04:34
# with the battery back at 100%. The phone had died. The ceiling read "up by 01:25" —
# confident, and false by about three hours. Absence of data is not evidence of waking,
# which is the same rule this whole area runs on one level up.
DEAD = ([conf(m, 20) for m in (400, 395, 390)]
        + [conf(m, 90) for m in range(380, 200, -10)]   # sure sleep...
        + [conf(m, 40) for m in (12,)])                 # ...then nothing for three hours
d = B.sleep_interval(DEAD, NOW)
check("a night is still found", bool(d))
check("it does NOT assert a ceiling it never observed", d["woke_by"] is None, d["woke_by"])
check("...and says where it lost the thread", d["blind_after"] is not None, d)
check("...and when the readings came back", d["blind_until"] is not None, d)
check("...and does NOT call him still asleep, which is a different claim",
      not d["still_asleep"], d)
d2 = B.sleep_interval(DEAD, NOW, awake_at=[NOW - 5 * M])
check("his own word after the hole DOES bound it",
      d2["woke_by"] is not None and abs(d2["woke_by"] - (NOW - 5 * M)) <= 1.5, d2["woke_by"])
check("an unbroken stream still yields a ceiling",
      B.sleep_interval(NIGHT, NOW)["woke_by"] is not None)

print("\n4. A TURN INSIDE A RUN BREAKS IT")
# he woke mid-way and said something; that is two sleeps, not one long one
mid = NOW - 260 * M
two = B.sleep_interval(NIGHT, NOW, awake_at=[SAID_UP, mid, SAID_BACK])
check("the run is cut at his turn, so the night is shorter",
      two["hours"] < v["hours"], "%s vs %s" % (two["hours"], v["hours"]))
check("...and the reported sleep is the one AFTER he settled again",
      abs(two["asleep_after"] - mid) <= 1.5, (two["asleep_after"], mid))

print("\n5. THROUGH THE REAL SKILL")
# the store and transcript the skill actually reads, inside the sandbox
S._append(NIGHT)
tdir = os.path.join(os.path.dirname(os.environ["SP_RECALL_REGISTRY"]), "transcripts")
os.makedirs(tdir, exist_ok=True)
day = time.strftime("%Y-%m-%d", time.gmtime(NOW))
with io.open(os.path.join(tdir, "%s.jsonl" % day), "w", encoding="utf-8") as f:
    for t in (SAID_UP, SAID_BACK):
        f.write(json.dumps({"role": "user", "at": t * 1000.0,
                            "content": "still up"}) + "\n")
from harness.skills.body import when_he_slept   # noqa: E402
got = when_he_slept()
check("the skill finds the night", got.get("ok") and got.get("found"), got)
check("...and answers in bounds, not a minute",
      isinstance(got.get("asleep_between"), list) and len(got["asleep_between"]) == 2,
      got.get("asleep_between"))
check("...on his own clock, not the store's UTC",
      all(x and ":" in x for x in got["asleep_between"]), got.get("asleep_between"))
check("...and names what bounded it", got.get("bounded_by") == "the operator's own words",
      got.get("bounded_by"))
check("...and the ceiling rides along", bool(got.get("up_by")), got.get("up_by"))
check("the tool is offered to her", any(
    getattr(t, "name", "") == "when_he_slept" for t in __import__(
        "harness.skills.body", fromlist=["body_tools"]).body_tools()))

print("\nG-SLEEP-INTERVAL: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_sleep_interval.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_sleep_interval", "pass": PASS, "fail": FAIL,
               "run_floor_s": B._SLEEP_RUN_S,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
sys.exit(1 if FAIL else 0)
