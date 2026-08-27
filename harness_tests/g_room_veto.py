#!/usr/bin/env python
"""G-ROOM-VETO — a turn in the room outranks any reading of his phone.

WHAT THIS ANSWERS. Every sleep signal in telemetry/body.py is about a PHONE: screen,
charger, wrist, a classifier reading a handset. None of them is about HIM, and once he is
at the desktop the phone lies on a charger looking exactly like a phone whose owner is
asleep. On 2026-08-27 at 03:38 she wished him goodnight while he was awake and
typing, because that is what she had been told.

MEASURED against the only ground truth that costs nothing — a message from him is proof he
was awake that minute:

    46 samples within 15 min of one of his messages   MEDIAN 61%
    01:00-03:50 while he typed continuously            76-95%
    at SLEEP_SURE (70) it calls him asleep for         30% of proven-awake minutes

So the room outranks the phone, and it is not a tie-break: a turn is OBSERVED, a
classifier is INFERRED, which is this store's oldest rule reaching the one seam that had
not heard it. His words for the same thing: "50/50 would lean towards awake."

  1. THE VETO FIRES on a recent turn, whatever the phone says.
  2. IT DOES NOT FIRE on an old turn — this is not "always awake".
  3. IT ABSTAINS when nothing can say, leaving every other signal untouched.
  4. SHE IS TOLD WHY, and the number is named as being about the PHONE.

OFFLINE. No GPU, no daemon.
"""
import dataclasses
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from _gate import sandbox   # noqa: E402
sandbox("g_room_veto")

os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"

from harness.kairos import impulse as imp        # noqa: E402
from harness.kairos import scheduler as ks       # noqa: E402
from harness.telemetry import body as TB         # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


def _state():
    cand = [v for v in vars(imp).values()
            if dataclasses.is_dataclass(v)
            and "last_user_at" in getattr(v, "__dataclass_fields__", {})]
    assert cand, "no session state carries last_user_at"
    return cand[0]()


def spoke(seconds_ago):
    """Put a session in the scheduler as if he spoke `seconds_ago`. None clears it."""
    with ks._LOCK:
        ks._STATE.clear()
        if seconds_ago is not None:
            st = _state()
            st.last_user_at = time.monotonic() - seconds_ago
            ks._STATE["g_room_veto"] = st


print("1. the helper reads the SAME clock the room already uses")
spoke(120)
got = TB._seconds_since_he_spoke()
check("it reports roughly two minutes", got is not None and 110 <= got <= 180, got)
spoke(None)
check("...and None when no session can say", TB._seconds_since_he_spoke() is None)
# ONE CLOCK, NOT TWO. app.py's _quiet_for reads this same expression to decide whether the
# room is still enough to take the GPU; a second "when did he last speak" would be two
# truths about one fact.
_app = open(os.path.join(ROOT, "harness", "server", "app.py"), encoding="utf-8").read()
check("...the same expression app.py's _quiet_for uses",
      "st.last_user_at for st in" in _app)

print("\n2. THE VETO FIRES, whatever the phone says")
# ── DRIVEN THROUGH THE REAL read(), NOT A COPY OF ITS RULE ───────────────────────────
# The first cut of this gate reimplemented the veto here and asserted on its own copy —
# so it would have gone GREEN on a tree where the veto was never wired into
# telemetry/body.py at all. Two implementations of one rule is the bug this repo is
# named after in its own AGENTS.md; writing one INSIDE the gate for the rule is worse,
# because it launders the absence as a pass. The store is fed instead, and the real
# function reads it.
_now = time.time()


def _rows():
    """A phone shouting 'asleep' as loudly as it can."""
    def at(sec_ago):
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_now - sec_ago))
    out = []
    for age in (60, 300, 600):
        out.append({"at": at(age), "kind": "sleep_confidence", "source": "phone",
                    "value": 88.0})
        out.append({"at": at(age), "kind": "heart_rate", "source": "watch", "value": 66.0})
    out.append({"at": at(60), "kind": "screen", "source": "phone", "value": "off"})
    out.append({"at": at(60), "kind": "charging", "source": "phone", "value": "on"})
    return out


_ROWS = _rows()
_real_read_since = TB.store.read_since
TB.store.read_since = lambda *_a, **_k: list(_ROWS)


def read(seconds_ago):
    """THE REAL read(), with the room told what it should know."""
    spoke(seconds_ago)
    r = TB.read(now=_now)
    return r.get("facts", {}), str(r.get("why") or "")


f, w = read(120)
check("a turn two minutes ago makes him awake", f.get("asleep") is False, f.get("asleep"))
check("...and the veto is RECORDED, not silent", f.get("sleep_vetoed_by_room") is not None, f)
check("...with a reason a human can read", "outranks" in w, w[:120])
check("...and the phone's number is KEPT — it is still true about the phone",
      f.get("sleep_confidence") == 88.0, f.get("sleep_confidence"))
# and without the veto the SAME rows really would have said asleep, or this proves nothing
f_noveto, _ = read(None)
check("...and those very rows DO read as asleep without a turn in the room",
      f_noveto.get("asleep") is True, f_noveto.get("asleep"))

print("\n3. IT DOES NOT FIRE ON AN OLD TURN — this is not 'always awake'")
f, w = read(TB.ROOM_VETO_S + 600)
check("a turn well outside the window leaves the reading alone",
      f.get("asleep") is True and not f.get("sleep_vetoed_by_room"), f.get("asleep"))
check("...and says nothing about the room", "outranks" not in w, w[:120])
f, _ = read(TB.ROOM_VETO_S - 60)
check("just inside the window vetoes", f.get("asleep") is False)
f, _ = read(TB.ROOM_VETO_S + 60)
check("just outside it does not", f.get("asleep") is True)

print("\n4. IT ABSTAINS when nothing can say")
f, w = read(None)
check("no session: every phone signal survives untouched",
      f.get("asleep") is True and f.get("sleep_confidence") == 88.0, f.get("asleep"))
check("...and no veto is claimed",
      "sleep_vetoed_by_room" not in f and "outranks" not in w, f.get("sleep_vetoed_by_room"))
# it must not invent a sleep reading where the phone never gave one
TB.store.read_since = lambda *_a, **_k: [
    {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_now - 60)),
     "kind": "screen", "source": "phone", "value": "on"}]
f, _ = read(120)
check("with no sleep reading at all, the veto adds no confidence number",
      "sleep_confidence" not in f and "sleep_vetoed_by_room" not in f, f)
check("...but still records that the room saw him", f.get("awake_by_room") is True, f)
TB.store.read_since = _real_read_since

print("\n5. SHE IS TOLD WHY, and the number is named as the PHONE's")
from harness.skills import body as SB   # noqa: E402
_src = open(os.path.join(ROOT, "harness", "skills", "body.py"), encoding="utf-8").read()
check("the sentence branch exists", "sleep_vetoed_by_room" in _src)
# ── AND WHEN HE IS HERE SHE IS TOLD NOTHING ABOUT SLEEP AT ALL ──────────────────────
# His words: "it's kind of silly that she is constantly told I am awake or asleep ...
# she shouldn't need to comment constantly that I am asleep and never to me obviously."
#
# The first cut of the veto fixed only the WRONGNESS — it swapped a false claim ("he
# seems to be asleep, 82%") for a true but pointless one ("his phone's reading is about
# the phone"). Both are noise to a woman mid-sentence with the man in question. Driven
# through the real sentence builder, both ways, because "says nothing" would also be
# satisfied by a builder that says nothing ever.
# THE SANDBOX HAS NO TELEMETRY — that is the point of it — so the store is fed the same
# shouting phone section 2 used. The first cut of this section called how_is_he() against
# an empty store and asserted on "nothing is reporting", which tests the sandbox rather
# than the veto.
TB.store.read_since = lambda *_a, **_k: list(_ROWS)
spoke(120)
_here = str(SB.how_is_he().get("in_a_sentence") or "")
spoke(None)
_away = str(SB.how_is_he().get("in_a_sentence") or "")
TB.store.read_since = _real_read_since
check("with him in the room she is told NOTHING about sleep",
      "asleep" not in _here and "sleep confidence" not in _here, _here[-90:])
check("...while the rest of the reading survives", "his heart" in _here, _here[:60])
check("...and with him away the sleep reading is UNCHANGED",
      ("asleep" in _away or "sleep confidence" in _away), _away[-90:])
# The contradiction this replaces: "he is awake — sleep confidence only 88%" reads as a
# self-contradiction and invites her to split the difference.
check("...so she is never handed 'awake — confidence only 88%'",
      _src.index("sleep_vetoed_by_room") < _src.index("sleep confidence only"), "branch order")

print("\nG-ROOM-VETO: %d pass, %d fail" % (PASS, FAIL))
spoke(None)
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_room_veto.json"), "w", encoding="utf-8") as f2:
    json.dump({"name": "g_room_veto", "pass": PASS, "fail": FAIL,
               "window_s": TB.ROOM_VETO_S,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f2, indent=2)
sys.exit(1 if FAIL else 0)
