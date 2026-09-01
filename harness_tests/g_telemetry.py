"""G-TELEMETRY — his body reaches her as facts with edges, never as a feed. OFFLINE.

WHAT THIS HOLDS, and the order is the order of how badly it is needed:

  §1 ONE DOOR. `ingest.record` is the only writer; `store._append` is private. The anon
     gate, the one clock and the shape rules all live at that door, so a second writer
     would be a second set of rules inside a month (G-ANON §5b holds the anon half).
  §2 SILENCE IS AN ANSWER. Stale data, no watch, off the wrist -> she is told NOTHING.
     A companion who says "you seem calm" from readings taken at lunch is worse than one
     who says nothing, and it is the failure that would never look like a bug.
  §3 OBSERVED IS NOT INFERRED. `observed` is what the watch measured; `facts` is what was
     concluded. Collapsing them is how "he is stressed" ends up wearing a measurement's
     clothes, and verdict.may_supersede exists because that matters.
  §4 THE TAIL SHOWS WHEN IT MOVES (2026-08-26, the operator's ask: "she can see my heart pacing").
     Three real readings, so the noticing is HERS. Hidden when flat, because "58, 58, 58"
     spends her budget to say nothing and teaches her the number is furniture.
  §5 ONE SEAM FOR THE ROOM AND FOR HER. /v1/telemetry/now renders what body.read() decides
     and body.present() says. Two readers would let the panel and her prefix describe two
     different bodies, and he would have no way to tell which was lying.

MUTANTS, run in-gate: show a flat tail (§4 goes red on the noise she would have been fed),
and age a reading past its freshness window (§2 goes red on the confident stale sentence).

    python harness_tests/g_telemetry.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _src as _srcmod  # noqa: E402
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_telemetry")            # FIRST — redirects SP_TELEMETRY_DIR
os.environ["SP_ENGINE_KIND"] = "openai"
os.environ.setdefault("SP_DAEMON_URL", "http://127.0.0.1:9")

import io                                                          # noqa: E402
import time                                                        # noqa: E402
import time as _t_mod                                              # noqa: E402
from harness.telemetry import body, ingest, store                   # noqa: E402

print("1. ONE DOOR, AND IT IS THE ONE WITH THE RULES ON IT")
_src = open(os.path.join(ROOT, "harness", "telemetry", "store.py"), encoding="utf-8").read()
check("the store's writer is PRIVATE", "def _append(" in _src and "\ndef append(" not in _src)
_isrc = open(os.path.join(ROOT, "harness", "telemetry", "ingest.py"), encoding="utf-8").read()
check("...and the door calls it", "store._append(" in _isrc)
check("...and the anon gate is AT the door, before any shaping",
      _isrc.index('holds("telemetry.sample"') < _isrc.index("_shape(s, source, at)"))
_bsrc = open(os.path.join(ROOT, "harness", "telemetry", "body.py"), encoding="utf-8").read()
check("the reader never writes", "_append" not in _bsrc)
# THE OTHER HALF of "one door": nothing outside the package may reach the private writer.
_reach = []
for _base, _dirs, _files in os.walk(os.path.join(ROOT, "harness")):
    _dirs[:] = [d for d in _dirs if d != "__pycache__"]
    for _f in _files:
        _p = os.path.join(_base, _f)
        if not _f.endswith(".py") or os.sep + "telemetry" + os.sep in _p:
            continue
        # PRECISE, because the first cut was not: it flagged any file containing both
        # "_append(" and the word "telemetry", and convicted semindex.py, which has its own
        # private appender and merely mentions SP_TELEMETRY_OKF_ROOT. A conservation check
        # that cries wolf gets switched off, so it looks for the actual reach: THIS store's
        # writer, called through this store's name.
        _t = open(_p, encoding="utf-8", errors="replace").read()
        if "store._append(" in _t or ("harness.telemetry" in _t and "._append(" in _t):
            _reach.append(os.path.relpath(_p, ROOT))
check("nothing outside harness/telemetry/ reaches the private writer", not _reach, _reach)

print("\n2. SILENCE IS AN ANSWER")
check("empty store: she is told nothing", body.present() == "", repr(body.present()))
_now = time.time()
ingest.record([{"kind": "heart_rate", "value": 74}, {"kind": "motion", "value": "still"}],
              source="watch")
check("...and a FRESH reading is readable", body.latest("heart_rate") is not None)
# AGE IT PAST THE WINDOW. Not by sleeping — by asking with a `now` far enough ahead, which
# is the same arithmetic the live path does and takes no wall-clock.
_stale = _now + body.FRESH_S["heart_rate"] + 60
check("a reading past its freshness window is NOT current",
      body.latest("heart_rate", None, _stale) is None,
      "this is the 'you seem calm' from lunchtime bug")
check("...and read() says nothing rather than guessing",
      body.read(_stale).get("facts", {}).get("heart_rate") is None)
# OFF THE WRIST is a full stop, not a caveat.
ingest.record([{"kind": "on_body", "value": "off"}], source="watch")
_off = body.read()
check("watch off his wrist: no facts at all", _off["facts"] == {}, _off["facts"])
check("...and it SAYS why", "off his wrist" in _off["why"], _off["why"])
check("...and she reads nothing", body.present() == "")

# ── THE PACKAGE HAS TWO TENANTS, AND I BROKE ONE GETTING IN (2026-08-26) ────────────
# harness/telemetry/ predates this work: it held the engine's LM-B2 flywheel sink. My
# __init__.py REPLACED it and deleted its re-exports, and NOTHING FAILED -- every consumer
# imports harness.telemetry.sink directly, so the whole suite stayed green over an API that
# no longer existed. A green suite is not an audit. This is the check that would have said.
from harness import telemetry as _pkg                                      # noqa: E402
check("the flywheel sink's public API survived the body work",
      hasattr(_pkg, "TelemetrySink") and hasattr(_pkg, "sink_record"),
      "colliding a new subsystem into an existing package silently removed its exports")
check("...and the package docstring names BOTH tenants, so the next one does not collide",
      "TENANT 1" in (_pkg.__doc__ or "") and "TENANT 2" in (_pkg.__doc__ or ""))
check("...and it says their stores are different roots",
      "SP_TELEMETRY_OKF_ROOT" in (_pkg.__doc__ or "")
      and "SP_TELEMETRY_DIR" in (_pkg.__doc__ or ""))

_TEL_MAIN = os.environ["SP_TELEMETRY_DIR"]   # restored at the end of 2b
print("\n2b. A COUNT IS NOT A SPAN — THE RESTING BASELINE NEEDS BREADTH")
# CAUGHT LIVE, 2026-08-26, within an hour of the watch going on his wrist. It posted a
# backlog of 663 heart-rate samples taken over about ten minutes while he was up and
# moving, and resting() returned 110 — the 10th percentile of a window containing no rest.
# That is worse than no baseline: every later reading is measured against a number saying
# he is always calm, so `worked_up` can never fire and the feature disables itself.
#
# Same shape as the bug becoming.py fixed on 2026-08-22 and wrote down — a cap on VOLUME
# says nothing about SPAN — four days later, in a different file.
os.environ["SP_TELEMETRY_DIR"] = os.path.join(SB, "onehour")
for _i in range(300):
    ingest.record([{"kind": "heart_rate", "value": 108 + (_i % 5)}], source="watch")
check("300 samples from ONE day is not a resting rate", body.resting() is None,
      body.resting())
check("...and nothing that leans on it fires",
      body.read().get("facts", {}).get("worked_up") is None)

# Back-date the same volume across enough days and it IS one. Written straight to the
# store because ingest stamps `now` on purpose — the door is not the thing under test.
import json as _json2                                                      # noqa: E402
_bd = os.path.join(SB, "spread")
os.environ["SP_TELEMETRY_DIR"] = _bd
os.makedirs(_bd, exist_ok=True)
for _d, _day in enumerate(("2026-08-20", "2026-08-21", "2026-08-22")):
    with io.open(os.path.join(_bd, _day + ".jsonl"), "w", encoding="utf-8",
                 newline="\n") as _f:
        for _i in range(100):
            _f.write(_json2.dumps({"at": "%sT12:00:%02d.000Z" % (_day, _i % 60),
                                   "source": "watch", "kind": "heart_rate",
                                   "value": 56 + (_i % 9)}) + "\n")
_rest = body.resting(_t_mod.mktime(_t_mod.strptime("2026-08-22T13:00:00", "%Y-%m-%dT%H:%M:%S")))
check("300 samples across THREE days is", _rest is not None, _rest)
check("...and it is a RESTING number, not the mean", _rest is not None and _rest <= 60, _rest)
# A SECTION MUST NOT LEAVE THE STORE POINTED SOMEWHERE ELSE. Section 3 reads what 2
# built, and this one moved the fixture out from under it -- the same shape as a
# gate supplying its own precondition, wearing a different hat.
os.environ["SP_TELEMETRY_DIR"] = _TEL_MAIN

print("\n3. OBSERVED IS NOT INFERRED")
ingest.record([{"kind": "on_body", "value": "on"}], source="watch")
for _v in (70, 78, 92):
    ingest.record([{"kind": "heart_rate", "value": _v}], source="watch")
_r = body.read()
check("what was MEASURED is in observed", "heart_rate" in _r["observed"], _r["observed"])
check("...and the tail with it (three things the watch measured)",
      len(_r["observed"].get("heart_rate_tail") or []) >= 2)
check("what was CONCLUDED is in facts", "hr_trend" in _r["facts"], _r["facts"])
check("...and the two dicts are not the same dict",
      "hr_trend" not in _r["observed"] and "heart_rate_tail" not in _r["facts"])
check("every sentence she reads is hedged or a plain reading",
      "seems" in body.present() or "readings:" in body.present(), body.present())

print("\n4. THE TAIL SHOWS WHEN IT MOVES, AND HIDES WHEN IT DOES NOT")
check("a climbing heart reaches her AS READINGS",
      "70, 78, 92" in body.present() and "climbing" in body.present(), body.present())
check("...and the trend word is derived, not asserted", body.read()["facts"]["hr_trend"] == "climbing")
# FLAT: the mutant is the behaviour we are refusing.
_sb2 = os.path.join(SB, "flat")
os.environ["SP_TELEMETRY_DIR"] = _sb2
for _v in (61, 61, 62):
    ingest.record([{"kind": "heart_rate", "value": _v}], source="watch")
ingest.record([{"kind": "on_body", "value": "on"}, {"kind": "motion", "value": "moving"}],
              source="watch")
_flat = body.present()
check("a FLAT tail is not shown — it would be furniture", "61, 61, 62" not in _flat, _flat)
check("mutant(show it anyway): that is the noise she would have been fed",
      body.read()["facts"].get("hr_swing", 0) < body._TAIL_WORTH_SHOWING["heart_rate"],
      "swing under the bar is exactly the case the bar exists for")
_fall = os.path.join(SB, "fall")
os.environ["SP_TELEMETRY_DIR"] = _fall
for _v in (104, 88, 71):
    ingest.record([{"kind": "heart_rate", "value": _v}], source="watch")
ingest.record([{"kind": "on_body", "value": "on"}], source="watch")
check("a FALLING heart reads as falling", body.read()["facts"]["hr_trend"] == "falling")

print("\n5. MOVEMENT IS A FEELING, NOT A UNIT")
_mv = os.path.join(SB, "mv")
os.environ["SP_TELEMETRY_DIR"] = _mv
ingest.record([{"kind": "on_body", "value": "on"}], source="watch")
for _g in (1.3, 1.5, 1.7):
    ingest.record([{"kind": "gyro_rms", "value": _g}], source="watch")
_m = body.read()["facts"]
check("gyro becomes a word she can use", _m.get("movement_word") == "moving a lot", _m)
check("...and she says it", "moving a lot" in body.present(), body.present())
os.environ["SP_TELEMETRY_DIR"] = os.path.join(SB, "still")
ingest.record([{"kind": "on_body", "value": "on"}, {"kind": "gyro_rms", "value": 0.02}],
              source="watch")
check("still is still, and is not narrated at her",
      "moving" not in body.present(), body.present())

print("\n6. ONE SEAM FOR THE ROOM AND FOR HER")
from harness.server import app as _app                              # noqa: E402
os.environ["SP_TELEMETRY_DIR"] = _mv
_n = _app._telemetry_now_json()
check("/v1/telemetry/now serves what SHE reads, verbatim",
      _n.get("she_reads") == body.present(), (_n.get("she_reads"), body.present()))
check("...and the same observed/facts split", _n["observed"] == body.read()["observed"])
_h = _app._telemetry_history_json(6.0)
check("history returns a per-minute series", _h.get("ok") and "gyro_rms" in _h["series"])
check("...down-sampled, not raw (a chart of 21,600 points is not more honest)",
      all("n" in p for p in _h["series"]["gyro_rms"]))
_ui = open(os.path.join(ROOT, "ui", "src", "apps", "Body.jsx"), encoding="utf-8").read()
check("the panel shows HER SENTENCE, so he can see what she was handed",
      "she_reads" in _ui and "she reads" in _ui)
check("...and renders the tail as readings, not an average",
      "heart_rate_tail" in _ui)

print("\n7. THE SHAPE RULES REFUSE WHAT WOULD POISON THE HISTORY")
_bad = ingest.record([{"kind": "heart_rate", "value": 4000},
                      {"kind": "charging", "value": "asleep"},
                      {"kind": "heart_rate", "value": 70, "source": "fridge"}], source="watch")
check("instrument noise is refused with a reason", len(_bad["rejected"]) == 3, _bad["rejected"])
check("...and a state outside its vocabulary too",
      any("on/off" in r["why"] for r in _bad["rejected"]))
check("...and an unknown source", any("fridge" in r["why"] for r in _bad["rejected"]))
_ok = ingest.record([{"kind": "a_kind_invented_next_year", "value": 1.0}], source="watch")
check("an UNKNOWN KIND is stored anyway (losing data is worse than not knowing it)",
      _ok["stored"] == 1, _ok)
check("...and reported, so the omission is visible",
      "a_kind_invented_next_year" in store.verify()["unknown_kinds"])

print("\n8. SHE IS ACTUALLY HANDED IT — THE TURN NOTE AND THE REASON")
# THE TWO WRONG PLACES ARE BOTH ALREADY KNOWN, so this asserts the third.
_app_src = _srcmod.pkg("harness", "server")
check("the note is a SYSTEM row, not a staple on his words",
      '"role": "system", "_tel": 1' in _app_src,
      "the wardrobe staple was measured out on 2026-08-19: she read a parenthetical on "
      "his message as his assertion and as an order, and streamed 4,435 characters of "
      "scratchpad instead of talking")
# THE STAPLE IS THE THING BEING REFUSED, so it is asserted directly: the `_tel` row is
# built with a role, and no line in app.py concatenates a body note onto a user message.
check("...and no body note is ever concatenated onto his message",
      not [ln for ln in _app_src.splitlines()
           if "_tel_b.present()" in ln and "content" in ln and "role" not in ln],
      "riding on his words is what made the wardrobe note read as an order")
# ── THIS CHECK USED TO ASSERT THE BUG (2026-08-28) ───────────────────────────────────
# It required `msgs[:] = [m for m in msgs if not m.get("_tel")]` — strip last turn's note,
# insert a fresh one — on the reasoning that "stacked notes diverge the persist-KV cache
# at the insert point". That is exactly backwards, and it cost three minutes a turn on his
# machine: the commit was built WITH the note, so REMOVING it is what makes this turn's
# prompt differ from the commit. Twelve tokens of divergence, a refused rewind, and a
# 9,000-token re-prefill at 13 ms/tok.
#
#     PERSIST-KV: rewind(12) refused — full-prefill floor
#     TURN-PHASE: prefill 8875 tok in 114781 ms
#
# The note's TEXT was not even changing; five reads in a row said the same thing. Its
# POSITION did, because the list grows. So the invariant is inverted: an unchanged note
# stays exactly where it is, and nothing is ever removed.
#
# COMMENTS ARE STRIPPED BEFORE THIS IS CHECKED. The old string still appears above, in the
# prose explaining why it is gone — and a source check that cannot tell code from a comment
# is how the first version of this passed against the fix.
_code = chr(10).join(ln.split("#", 1)[0] for ln in _app_src.splitlines())
check("last turn's note is NOT removed — removing it is what diverges the cache",
      'msgs[:] = [m for m in msgs if not m.get("_tel")]' not in _code,
      "the committed KV was built with it; deleting it invalidates from that point on")
check("...and an unchanged note is not said twice",
      "_said in _prev_tel" in _code,
      "re-inserting the same text at a new index costs the whole prefix")
check("...and the previous note is read before the new one is built",
      _code.index("_prev_tel = next(") < _code.index('"role": "system", "_tel": 1'))
check("...and it never goes in the CACHED prefix",
      "_tel" not in open(os.path.join(ROOT, "harness", "agent.py"), encoding="utf-8").read(),
      "a heart rate at KV token 0 is stale within the minute or re-prefills every turn")

# SELF-LIMITING is what makes this safe where the wardrobe note was not.
os.environ["SP_TELEMETRY_DIR"] = os.path.join(SB, "quiet")
check("nothing happening -> present() is EMPTY, so the turn costs zero tokens",
      body.present() == "", repr(body.present()))
os.environ["SP_TELEMETRY_DIR"] = _mv
check("...and it is non-empty exactly when there IS something", body.present() != "")

print("\n   the kairos reason")
from harness.kairos import reasons as _R, impulse as _I            # noqa: E402
check("`body` is a reason, and it is FIRST", _R._ORDER[0] == "body", _R._ORDER)
check("...because a heart rate is stale in minutes, not days",
      "stale" in open(os.path.join(ROOT, "harness", "kairos", "reasons.py"),
                      encoding="utf-8").read().split("_ORDER =")[0][-900:])
# ITS OWN STORE. `_mv` carries movement and no heart rate, so `resting` is None there and
# no heart reason could ever fire — reusing it would have been a gate grading a fixture
# that cannot exhibit the thing under test.
# BACK-DATED ACROSS DAYS, because the breadth guard added in 2b is real and this fixture
# has to be a life rather than an instant. 270 samples recorded in one moment is exactly
# what resting() now refuses, and it refused this fixture the moment the guard landed --
# which is the gate and the code agreeing, not fighting.
_rsb = os.path.join(SB, "reason")
os.makedirs(_rsb, exist_ok=True)
os.environ["SP_TELEMETRY_DIR"] = _rsb
import json as _json8                                                      # noqa: E402
import datetime as _dt8                                                    # noqa: E402
_today8 = _dt8.datetime.utcnow().date()
for _back in (3, 2, 1):
    _day8 = (_today8 - _dt8.timedelta(days=_back)).strftime("%Y-%m-%d")
    with io.open(os.path.join(_rsb, _day8 + ".jsonl"), "w", encoding="utf-8",
                 newline="\n") as _f8:
        for _i in range(100):
            _f8.write(_json8.dumps({"at": "%sT09:%02d:%02d.000Z" % (_day8, _i // 60, _i % 60),
                                    "source": "watch", "kind": "heart_rate",
                                    "value": 57 + (_i % 8)}) + "\n")
ingest.record([{"kind": "on_body", "value": "on"}], source="watch")
for _v in (79, 93, 108):
    ingest.record([{"kind": "heart_rate", "value": _v}], source="watch")
_rd = body.read()
check("the fixture has a learned resting baseline", body.resting() is not None, body.resting())
_r8 = _R.from_body(_rd, set())
check("a heart well above HIS resting is a reason to speak",
      _r8 and _r8["event"] == "worked_up", _r8)
check("...and she is handed the READINGS, not a conclusion",
      len(_r8.get("tail") or []) >= 2 and "stressed" not in _r8["text"], _r8["text"])
check("...bounded to once an hour by its raise key",
      _R.from_body(_rd, {_r8["raise_key"]}) is None,
      "noticing must not become nagging")
_n8 = _I.muse_nudge(_r8)
check("the nudge forbids a diagnosis, in as many words",
      "Do NOT diagnose him" in _n8 and "say nothing at all" in _n8, _n8[:120])
check("...and allows the numbers, because they are why she noticed",
      "You may use the numbers" in _n8)
# OFF THE WRIST is a full stop for the reason too, not just for present().
os.environ["SP_TELEMETRY_DIR"] = os.path.join(SB, "offwrist")
ingest.record([{"kind": "on_body", "value": "off"}, {"kind": "heart_rate", "value": 150}],
              source="watch")
check("off his wrist: no reason to speak, whatever the numbers say",
      _R.from_body(body.read(), set()) is None)

print("\n   and both halves are switchable")
from harness.tuning import registry as _TR                          # noqa: E402
for _k in ("telemetry.turn_note", "telemetry.reasons"):
    check("%s is a real knob" % _k, _TR.get(_k) is not None)
check("the turn note reads its knob", '"telemetry.turn_note"' in _app_src)
check("the reason reads its knob",
      '"telemetry.reasons"' in open(os.path.join(ROOT, "harness", "kairos", "reasons.py"),
                                    encoding="utf-8").read())

print("\n8b. A PHONE ON A DESK IS NOT A MAN SITTING STILL")
# The phone agent posts `motion`, `gyro_rms` and `steps` under the SAME KIND NAMES the watch
# uses, and they are not the same claim. A still watch on his wrist means HE is still; a
# still phone means the phone is on a table, which is perfectly compatible with him being
# out for a run in the watch. Caught in testing before it ever ran: the watch said still,
# the phone was moved, and she said "he is moving a lot".
_ss = os.path.join(SB, "sources")
os.environ["SP_TELEMETRY_DIR"] = _ss
ingest.record([{"kind": "on_body", "value": "on"}, {"kind": "motion", "value": "still"},
               {"kind": "heart_rate", "value": 58}], source="watch")
ingest.record([{"kind": "gyro_rms", "value": 2.4}, {"kind": "motion", "value": "moving"},
               {"kind": "steps", "value": 9999}], source="phone")
_f8b = body.read()["facts"]
check("the PHONE moving does not make HIM moving",
      _f8b.get("moving") is False and "movement_word" not in _f8b, _f8b)
check("...and she says nothing about his body from it", "moving" not in body.present(),
      body.present())
ingest.record([{"kind": "gyro_rms", "value": 1.6}], source="watch")
check("...but the WATCH moving does", "moving" in body.present(), body.present())
check("body claims are sourced to the wrist, structurally",
      body.BODY_SOURCE == "watch" and body.DEVICE_SOURCE == "phone")

print("\n   the phone's screen is the cheapest truth in the building")
# A screen that came on two minutes ago is a man who is awake, and it beats any amount of
# stillness inferred from an accelerometer. This is the case the crude sleep rule gets
# wrong on its own: a man reading in bed is still, and his heart is at his resting band.
_sc = os.path.join(SB, "screen")
os.environ["SP_TELEMETRY_DIR"] = _sc
import json as _json8b                                                     # noqa: E402
import datetime as _dt8b                                                   # noqa: E402
os.makedirs(_sc, exist_ok=True)
_t8b = _dt8b.datetime.utcnow().date()
for _bk in (3, 2, 1):
    _dy = (_t8b - _dt8b.timedelta(days=_bk)).strftime("%Y-%m-%d")
    with io.open(os.path.join(_sc, _dy + ".jsonl"), "w", encoding="utf-8", newline="\n") as _fh:
        for _i in range(100):
            _fh.write(_json8b.dumps({"at": "%sT09:%02d:%02d.000Z" % (_dy, _i // 60, _i % 60),
                                     "source": "watch", "kind": "heart_rate",
                                     "value": 57 + (_i % 8)}) + "\n")
_today8b = _t8b.strftime("%Y-%m-%d")
_now8b = time.time()
with io.open(os.path.join(_sc, _today8b + ".jsonl"), "a", encoding="utf-8",
             newline="\n") as _fh:
    for _mins in (45, 30, 15):                       # his wrist, still, for three quarters
        _fh.write(_json8b.dumps({"at": store.now_iso(_now8b - _mins * 60),
                                 "source": "watch", "kind": "motion",
                                 "value": "still"}) + "\n")
ingest.record([{"kind": "on_body", "value": "on"}, {"kind": "motion", "value": "still"},
               {"kind": "heart_rate", "value": 58}], source="watch")

# THE WATCH ALONE CANNOT CONCLUDE SLEEP, and that is the honest answer rather than a gap.
# A still wrist and a resting heart rate describe a man asleep and a man reading in a chair
# equally well. The phone is what tells them apart, so without it the seam sits in the
# unsure band and she says nothing -- which is the whole doctrine, applied to a number.
_f1 = body.read()["facts"]
check("wrist-only: still 45 min at his resting band is NOT enough to call it sleep",
      _f1.get("sleep_confidence") is not None
      and body.SLEEP_AWAKE < _f1["sleep_confidence"] < body.SLEEP_SURE, _f1)
check("...so `asleep` is left unset and she says nothing either way",
      "asleep" not in _f1 and "asleep" not in body.present(), (_f1, body.present()))

# ADD THE PHONE and it becomes sayable.
with io.open(os.path.join(_sc, _today8b + ".jsonl"), "a", encoding="utf-8",
             newline="\n") as _fh:
    _fh.write(_json8b.dumps({"at": store.now_iso(_now8b - 60 * 60), "source": "phone",
                             "kind": "screen", "value": "off"}) + "\n")
_f1b = body.read()["facts"]
check("...but an untouched phone for an hour on top of it is",
      _f1b.get("asleep") is True and _f1b.get("sleep_confidence", 0) >= body.SLEEP_SURE, _f1b)
check("...labelled as ours, not as a measurement", _f1b.get("sleep_source") == "inferred"
      and _f1b.get("crude") is True, _f1b)

ingest.record([{"kind": "screen", "value": "on"}], source="phone")
_f2 = body.read()["facts"]
check("...and his SCREEN coming on vetoes the lot", _f2.get("asleep") is False, _f2)
check("...saying why, so the veto is visible", _f2.get("awake_by_screen") is True)
check("...and she stops saying he is asleep", "asleep" not in body.present(), body.present())

print("\n   one agent, two bodies")
_ag = open(os.path.join(ROOT, "harness", "telemetry", "watch-agent", "java", "com",
                        "telemetry", "agent", "AgentService.java"), encoding="utf-8").read()
check("the agent DETECTS which device it is on", "FEATURE_WATCH" in _ag and 'source = ' in _ag,
      "a second phone app would be a second implementation of read-reduce-batch-retry")
check("...and declares it in the batch", '"source":"" + source' in _ag or "+ source +" in _ag)
_mf = open(os.path.join(ROOT, "harness", "telemetry", "watch-agent", "AndroidManifest.xml"),
           encoding="utf-8").read()
check("...and the watch feature is NOT required, or it could not install on a phone",
      'android.hardware.type.watch" android:required="false"' in _mf)
check("the phone's device state is broadcasts, not sensors",
      "ACTION_SCREEN_ON" in _ag and "ACTION_BATTERY_CHANGED" in _ag)
check("...and ambient light is rate-limited (a room does not change sixty times a minute)",
      "lastLight" in _ag)

print("\n8c. SLEEP HAS THREE SOURCES AND THEY ARE NOT THE SAME CLAIM")
# The best answer (the watch's own staging) is unavailable: every sleep-capable sensor on
# the Watch4 sits behind com.samsung.permission.SSENSOR, verified by enumerating the device.
# The second best (Google's Sleep API, which is what Home Assistant's "Sleep Confidence"
# sensor is) lives in Play Services on the phone and nothing fills it yet. So the seam has
# to rank three sources and be honest about which one answered.
_sl = os.path.join(SB, "sleep")
os.environ["SP_TELEMETRY_DIR"] = _sl
import json as _js8c                                                       # noqa: E402
import datetime as _dt8c                                                   # noqa: E402
os.makedirs(_sl, exist_ok=True)
# three days of his own resting data, so resting() will answer at all
_td8c = _dt8c.datetime.utcnow().date()
for _bk in (3, 2, 1):
    _dy = (_td8c - _dt8c.timedelta(days=_bk)).strftime("%Y-%m-%d")
    with io.open(os.path.join(_sl, _dy + ".jsonl"), "w", encoding="utf-8", newline="\n") as _fh:
        for _i in range(100):
            _fh.write(_js8c.dumps({"at": "%sT09:%02d:%02d.000Z" % (_dy, _i // 60, _i % 60),
                                   "source": "watch", "kind": "heart_rate",
                                   "value": 57 + (_i % 8)}) + "\n")

check("`sleep_confidence` is a first-class kind, so a classifier has somewhere to land",
      "sleep_confidence" in store.KINDS and "sleep_confidence" in ingest.BOUNDS)
_r = ingest.record([{"kind": "sleep_confidence", "value": 140}], source="phone")
check("...and it is bounded — 140% asleep is refused", _r.get("stored") == 0, _r)

print("\n   none is not zero")
# An empty store must not read as "he is awake". "We have no idea" and "he is up" are
# different claims and only the first is supportable from nothing.
_c, _t = body.sleep_estimate([], 0.0)
check("too little to say -> None, NOT a low confidence", _c is None and _t == [], (_c, _t))

print("\n   the number arrives with its reasons")
_now8c = time.time()
# THE ROWS THE AGENT ACTUALLY SENDS. The first version of this fixture posted a `motion`
# state, which nothing on any device has ever produced — 0 rows in 6,820 live samples — so
# it proved the estimate worked on data that does not exist.
_rows8c = [{"at": store.now_iso(_now8c - 4 * 3600), "source": "phone", "kind": "screen",
            "value": "off"}]
_rows8c += [{"at": store.now_iso(_now8c - _m * 60), "source": "watch", "kind": "gyro_rms",
             "value": 0.02} for _m in range(180, -1, -10)]
_c, _t = body.sleep_estimate(_rows8c, _now8c,
                             hr={"at": store.now_iso(_now8c - 60), "value": 58}, rest=58.0)
check("a confident reading is produced from real evidence", _c is not None and _c >= 70, _c)
check("...and every term that produced it comes back with it", len(_t) >= 3, _t)
check("...naming the phone, the wrist and his own resting band — not a magic number",
      any("phone" in x for x in _t) and any("wrist" in x for x in _t)
      and any("resting" in x for x in _t), _t)

print("\n   between the bands she says nothing")
ingest.record([{"kind": "on_body", "value": "on"}, {"kind": "motion", "value": "still"},
               {"kind": "heart_rate", "value": 58}], source="watch")
_f8c = body.read()["facts"]
check("an UNSURE reading leaves `asleep` unset rather than False",
      _f8c.get("sleep_confidence") is not None
      and (_f8c["sleep_confidence"] < body.SLEEP_SURE), _f8c)
check("...and she does not claim either way", "asleep" not in body.present(), body.present())
check("...while the source of the guess is named as ours", _f8c.get("sleep_source") == "inferred"
      and _f8c.get("crude") is True, _f8c)

print("\n   a real classifier outranks our guess")
ingest.record([{"kind": "sleep_confidence", "value": 91}], source="phone")
_f8c = body.read()["facts"]
check("a classifier's confidence wins over our own estimate",
      _f8c.get("sleep_source") == "classifier" and _f8c.get("sleep_confidence") == 91.0, _f8c)
check("...and it is NOT labelled crude, because it was not our guess",
      "crude" not in _f8c and "sleep_terms" not in _f8c, _f8c)
check("...and at 91% she may say it", _f8c.get("asleep") is True)
ingest.record([{"kind": "sleep_stage", "value": "deep"}], source="watch")
check("the watch's own staging outranks even that",
      body.read()["facts"].get("sleep_source") == "watch")

print("\n   he looked at his watch")
_wt = os.path.join(SB, "tilt")
os.environ["SP_TELEMETRY_DIR"] = _wt
_c, _t = body.sleep_estimate(_rows8c, _now8c,
                             hr={"at": store.now_iso(_now8c - 60), "value": 58}, rest=58.0,
                             awake_now=True)
check("a wrist tilt vetoes the whole accumulation, it does not merely subtract",
      _c is not None and _c <= 5.0, _c)
check("`wrist_tilt` is a kind, and it is the wrist's answer to the phone screen",
      "wrist_tilt" in store.KINDS and body.FRESH_S.get("wrist_tilt", 99999) <= 15 * 60)
_ag8c = open(os.path.join(ROOT, "harness", "telemetry", "watch-agent", "java", "com",
                          "telemetry", "agent", "AgentService.java"), encoding="utf-8").read()
check("...and the agent actually registers it (type 26, the one Samsung left unlocked)",
      "TYPE_WRIST_TILT_GESTURE = 26" in _ag8c and "wrist_tilt" in _ag8c)

print("\n   no time-of-day prior, on purpose")
# Every sleep model wants one. For a man who is routinely working at 03:00 it would make her
# confidently wrong at exactly the hour she is most likely to be talking to him.
import inspect as _insp8c                                                  # noqa: E402
_src8c = _insp8c.getsource(body.sleep_estimate)
# Named APIs, not the word "hour" -- the first spelling of this check matched the comment
# "...and for over three hours" and went red on its own documentation.
check("the estimate never looks at the clock",
      not any(x in _src8c for x in ("localtime", "gmtime", "datetime", ".hour", "strftime")),
      "a 3am prior would be wrong for this user specifically")

print("\n   the run-length reads one wrist, not two devices")
# _run_length was the SIBLING that got missed when latest() was made source-aware: it read
# the same mixed rows, so "still for two hours" could come off a phone on a desk.
# THE SHAPE THAT ACTUALLY BITES, and the first fixture here did not have it. A run is the
# NEWEST run, so interleaving the two devices just truncates it and looks harmless. The
# dangerous case is the quiet one: the phone reports stillness for hours and the WATCH SAYS
# NOTHING AT ALL -- exactly what happens when it is on the charger or out of range. Read
# unsourced, a phone on a desk becomes two hours of HIS stillness, and that is the number
# the sleep estimate would have leaned on.
_mixed = [{"at": store.now_iso(_now8c - 7200), "source": "phone", "kind": "motion",
           "value": "still"},
          {"at": store.now_iso(_now8c - 3600), "source": "phone", "kind": "motion",
           "value": "still"},
          {"at": store.now_iso(_now8c - 60), "source": "phone", "kind": "motion",
           "value": "still"}]
check("a phone lying still does not become HIS two hours of stillness",
      body._run_length(_mixed, "motion", "still", _now8c, body.BODY_SOURCE) == 0,
      body._run_length(_mixed, "motion", "still", _now8c, body.BODY_SOURCE))
check("...while unsourced it reads as two hours, which is why every call site names one",
      body._run_length(_mixed, "motion", "still", _now8c) >= 7200,
      body._run_length(_mixed, "motion", "still", _now8c))

# ── AND NOW THE PATH THAT ACTUALLY RUNS ─────────────────────────────────────────────
# The two checks above call `_run_length` directly with the source spelled out, which
# proves the function can do it and proves nothing about whether anybody asks. A mutant
# that dropped BODY_SOURCE from the CALL SITE inside sleep_estimate left this gate green:
# the rule was enforced in the path the test drove and not in the path the product uses,
# which is the house bug (AGENTS.md §0) caught in its natural habitat.
_desk = [{"at": store.now_iso(_now8c - 90 * 60), "source": "phone", "kind": "screen",
          "value": "off"}]
_desk += [{"at": store.now_iso(_now8c - _m * 60), "source": "phone", "kind": "gyro_rms",
           "value": 0.01} for _m in range(120, -1, -10)]      # the phone, flat on a desk
_c, _t = body.sleep_estimate(_desk, _now8c,
                             hr={"at": store.now_iso(_now8c - 60), "value": 58}, rest=58.0)
check("the ESTIMATE names the source too — a desk phone cannot lend him its stillness",
      _c is not None and _c < body.SLEEP_SURE, (_c, _t))
check("...so no duration term appears in its reasons at all",
      not any("still for" in x for x in _t), _t)

print("\n   `motion` is a phantom kind, so stillness comes from what arrives")
# ZERO `motion` rows in 6,820 live samples. The agent posts `gyro_rms` once per window and
# has never posted a motion STATE, so `moving`, `motion_for_s` and the stillness term were
# all reading a key that is never there — on every real turn — while this gate stayed green,
# because the gate recorded `motion` itself before asking. A gate that supplies its own
# precondition is testing the fixture.
_gyro = [{"at": store.now_iso(_now8c - _m * 60), "source": "watch", "kind": "gyro_rms",
          "value": 0.02} for _m in range(120, -1, -10)]
_st, _run = body.still_run(_gyro, _now8c, body.BODY_SOURCE)
check("stillness is derived from gyro_rms when no `motion` row exists — which is always",
      _st is True and _run >= 110 * 60, (_st, _run))
check("...and a classified `motion` state still wins when something posts one",
      body.still_run(_gyro + [{"at": store.now_iso(_now8c), "source": "watch",
                               "kind": "motion", "value": "moving"}],
                     _now8c, body.BODY_SOURCE)[0] is False)
check("...and a phone's rows are never his wrist's",
      body.still_run([dict(r, source="phone") for r in _gyro], _now8c,
                     body.BODY_SOURCE) == (None, 0))
check("...and a wrist that is moving reports no run at all",
      body.still_run([{"at": store.now_iso(_now8c), "source": "watch", "kind": "gyro_rms",
                       "value": 1.4}], _now8c, body.BODY_SOURCE) == (False, 0))
check("one threshold and one band table, not a number copied twice",
      body.MOVE_RMS == 0.15 and body._move_word(0.02) == "still"
      and body._move_word(1.5) == "moving a lot")

# the other call site, through read(), for the same reason
_ds = os.path.join(SB, "desk")
os.environ["SP_TELEMETRY_DIR"] = _ds
os.makedirs(_ds, exist_ok=True)
_dnow = time.time()
with io.open(os.path.join(_ds, _dt8c.datetime.utcnow().strftime("%Y-%m-%d") + ".jsonl"),
             "a", encoding="utf-8", newline="\n") as _fh:
    for _secs in (7200, 3600, 600):
        _fh.write(_js8c.dumps({"at": store.now_iso(_dnow - _secs), "source": "phone",
                               "kind": "motion", "value": "still"}) + "\n")
ingest.record([{"kind": "on_body", "value": "on"}, {"kind": "motion", "value": "still"}],
              source="watch")
_fd = body.read()["facts"]
check("`motion_for_s` is his wrist's run, not the phone's two hours on a desk",
      _fd.get("motion_for_s", 0) < 300, _fd.get("motion_for_s"))

print("\n   freshness answers a different question from duration")
_old = [{"at": store.now_iso(_now8c - 3 * 3600), "source": "phone", "kind": "screen",
         "value": "off"}]
check("a screen-off three hours stale is invisible to latest()",
      body.latest("screen", _old, _now8c, body.DEVICE_SOURCE) is None)
_row, _age8c = body._last_state(_old, "screen", _now8c, body.DEVICE_SOURCE)
check("...and readable by _last_state, which is the row the sleep estimate needs",
      _row is not None and _age8c >= 3 * 3600 - 5, _age8c)

print("\n9. WHERE SHE LISTENS IS A DECISION, AND IT IS WRITTEN DOWN")
# The watch reached her through `adb reverse` until 2026-08-26, which dies with the adb
# session — so the telemetry lane was only alive while a cable-equivalent was attached. He
# asked for the LAN and accepted the exposure ("I am the only one who uses the network").
#
# WHAT THIS SECTION EXISTS FOR is the OTHER reader: anybody who runs this framework and has
# not made that decision. Loopback is the security model here — `_origin_ok` returns True
# when there is no Origin header, so the origin check defends against a browser and nothing
# else — and a default that quietly widened would hand them shell access over their LAN.
_asrc = _srcmod.pkg("harness", "server")
check("the DEFAULT bind is still loopback, for everyone who has not decided",
      'os.environ.get("SP_GATEWAY_BIND") or "127.0.0.1"' in _asrc,
      "a widened default is shell access over somebody else's LAN")
check("...and it is a knob, mapped in serve.py (the one door)",
      '"SP_GATEWAY_BIND"' in open(os.path.join(ROOT, "serve.py"), encoding="utf-8").read())
check("...and the code says WHY loopback is the model, not just that it is",
      "_origin_ok" in _asrc.split('SP_GATEWAY_BIND')[0][-2000:]
      or "no Origin" in _asrc.split('SP_GATEWAY_BIND')[0][-2000:])

# THE PROFILE THAT WIDENS IT HAS TO SAY SO. A bind that changed without a sentence beside
# it is the drift this repo's ledger exists to stop.
_prof = open(os.path.join(ROOT, "profiles", "companion.toml"), encoding="utf-8").read()
if "bind" in _prof:
    check("the profile that widens it explains itself in the file",
          "bind =" in _prof and "127.0.0.1" in _prof.split("bind =")[0][-900:],
          "a widened bind with no reason beside it is drift")
_led = open(os.path.join(ROOT, "docs", "OFF-BY-DEFAULT.md"), encoding="utf-8").read()
check("...and it carries a ledger row with an arming condition",
      "[serve].bind" in _led and "What would disarm it" in _led.split("[serve].bind")[1][:4000])
check("...and the row is honest that no auth exists",
      "no shared secret" in _led.split("[serve].bind")[1][:4000]
      or "unbuilt" in _led.split("[serve].bind")[1][:4000])

# AND THE SCOPING IS CHECKABLE, because a firewall rule nobody can verify is a rule nobody
# should be told about. The tool must not claim to know the GATEWAY's bind from its own env.
check("there is a tool that reports the real scoping",
      os.path.isfile(os.path.join(ROOT, "tools", "lan_bind.py")))
_lb = open(os.path.join(ROOT, "tools", "lan_bind.py"), encoding="utf-8").read()
check("...and it reads what is LISTENING, not its own environment",
      "Get-NetTCPConnection" in _lb and 'os.environ.get("SP_GATEWAY_BIND")' not in _lb,
      "printing this shell's variable next to a question about hers reports the wrong "
      "process")
check("...and it warns when another rule also allows the port",
      "ANOTHER RULE ALSO ALLOWS THIS PORT" in _lb,
      "on Windows an allow does not deny; a subnet limit beside a broad allow is decorative")
check("...and it never runs itself from serve.py",
      "lan_bind" not in open(os.path.join(ROOT, "serve.py"), encoding="utf-8").read(),
      "a firewall rule is a change to his machine outside this repo")

finish("G-TELEMETRY")
