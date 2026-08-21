"""G-SENSES — a sense answers to the model that is actually served. OFFLINE.

Guards the 2026-07-31 defect: `var/voice/embed_audio.npz` is the 12B's [3840,640]
audio projection; the served your model has hidden size 2816 and
`audio_config: null`. The harness emitted 3840-wide frames anyway, and neither
side caught it — native.py never compared E, and routes.rs took `e_dim` from
`frames[0].len()`, so it only ever checked the batch agreed with ITSELF.

The legs below are the properties that make that impossible to reintroduce, not
a restatement of the code. Run: python harness_tests/g_senses.py
"""
from __future__ import annotations

import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from harness.senses import capability as cap  # noqa: E402
from harness.voice import tts  # noqa: E402

_P = _F = 0


def ok(cond, name, detail=""):
    global _P, _F
    if cond:
        _P += 1
        print(f"  ok   {name}")
    else:
        _F += 1
        print(f"  FAIL {name}   {detail}")


def refuses(fn, name, needle=""):
    try:
        fn()
        ok(False, name, "did NOT refuse")
    except cap.SenseRefused as e:
        ok(needle.lower() in str(e).lower() if needle else True, name,
           f"reason lacked {needle!r}: {e}")
    except Exception as e:
        ok(False, name, f"wrong exception {type(e).__name__}: {e}")


print("1. the committed table rules")
cap.reset_cache()
os.environ["SP_MODEL_PATH"] = "D:/x/your model.sp-model"
cap.reset_cache()
c26 = cap.for_model()
ok(c26.known and c26.e == 2816, "26b is listed, hidden size 2816", f"e={c26.e}")
ok(c26.audio is None, "26b declares NO audio path")
ok(bool(c26.vision), "26b declares a vision path")
refuses(lambda: c26.require("audio"), "asking to hear on the 26b refuses", "no audio")
ok("audio_config is null" in c26.audio_absent_reason,
   "the refusal carries the evidence, not just a no")

print("\n2. THE WIDTH CHECK THAT WAS MISSING")
refuses(lambda: c26.assert_width("audio", 3840),
        "3840-wide frames into a 2816-wide model refuse", "2816")
c26.assert_width("audio", 2816)
ok(True, "2816-wide frames are accepted")

print("\n3. an unlisted model has NO senses (fail closed)")
os.environ["SP_MODEL_PATH"] = "D:/x/some-model-nobody-declared.sp-model"
cap.reset_cache()
cu = cap.for_model()
ok(not cu.known, "unlisted model reports known=False")
refuses(lambda: cu.require("vision"), "unlisted model refuses sight", "not in")
refuses(lambda: cu.require("audio"), "unlisted model refuses hearing", "not in")

print("\n4. the 12b still hears (the table is a ruling, not a blanket ban)")
os.environ["SP_MODEL_PATH"] = "D:/x/gemma4-12b.sp-model"
cap.reset_cache()
c12 = cap.for_model()
ok(bool(c12.audio) and c12.e == 3840, "12b declares audio at E=3840", f"e={c12.e}")
c12.assert_width("audio", 3840)
ok(True, "12b accepts its own 3840-wide frames")
os.environ["SP_MODEL_PATH"] = "D:/x/gemma4-12b-q4b.sp-model"
cap.reset_cache()
ok(cap.for_model().e == 3840, "alias_of resolves (q4b -> 12b)")

print("\n5. native.py CALLS the guard — checked as code, not prose")
src = open(os.path.join(ROOT, "harness", "voice", "native.py"), encoding="utf-8").read()
tree = ast.parse(src)
enc = next(n for n in ast.walk(tree)
           if isinstance(n, ast.FunctionDef) and n.name == "encode")
calls = {ast.unparse(n.func) for n in ast.walk(enc) if isinstance(n, ast.Call)}
ok(any("require" in x for x in calls), "encode() calls require()", sorted(calls))
ok(any("assert_width" in x for x in calls), "encode() calls assert_width()", sorted(calls))

print("\n6. speech-out refuses what blew up (47 min at 11.9/12 GB)")
ok(tts.MAX_CHARS > 0, "there is a cap at all")
try:
    tts.synthesize("x" * (tts.MAX_CHARS + 1))
    ok(False, "over-length utterance refused")
except tts.TTSError as e:
    ok("over the" in str(e), "over-length utterance refused with the reason", str(e)[:80])
except Exception as e:
    ok(False, "over-length utterance refused", f"{type(e).__name__}: {e}")
parts = tts.split_sentences("One. Two! Three? " + "word " * 200)
ok(parts and all(len(p) <= tts.MAX_CHARS for p in parts),
   "split_sentences never emits an over-cap chunk",
   f"max={max((len(p) for p in parts), default=0)}")
ok(parts[:3] == ["One.", "Two!", "Three?"], "sentence boundaries are respected", parts[:3])

print("\n7. the ambient eye reads its own clock off DISK, not off this process")
# THE DEFECT (2026-08-03): the loop counted the hour from process boot, and the status
# read the last look from a module global. So a night of gateway bounces produced an eye
# that never fired and a panel that said it had never opened — while ambient.jsonl held
# an unbroken hourly run. Both halves are now the SAME reader, which is the only shape
# in which they cannot disagree.
import importlib  # noqa: E402
import json as _json  # noqa: E402
import tempfile  # noqa: E402
import time as _time  # noqa: E402

_dir = tempfile.mkdtemp(prefix="g_senses_amb_")
os.environ["SP_AMBIENT_LOG"] = os.path.join(_dir, "ambient.jsonl")
os.environ["SP_AMBIENT"] = "1"
# ...AND THE KNOB, since 2026-08-03. The eye now takes TWO switches — the env arms it, the
# `senses.ambient` knob can veto it without a restart — so a fixture that arms only the env
# measures whatever the operator last set. This leg is about the CLOCK, so it arms both and
# puts the knob back afterwards.
from harness.tuning import registry as _tune7  # noqa: E402
# chosen(), not get(): get() answers the DEFAULT when he never touched the knob,
# and "restoring" that default MATERIALIZES an override he never made (caught
# 2026-08-21, minutes after the re-arm: this gate wrote senses.ambient into a
# store the operator had just deliberately cleaned).
_knob_was = _tune7.chosen("senses.ambient")
_tune7.set_many({"senses.ambient": True})
os.environ["SP_AMBIENT_S"] = "3600"
from harness.senses import ambient as amb  # noqa: E402

importlib.reload(amb)
ok(amb.status()["last"] is None and amb.status()["next_in_s"] is None,
   "an empty log means the eye honestly has not looked", amb.status())
_half = _time.time() - 1800
with open(amb.LOG, "w", encoding="utf-8") as _f:
    _f.write(_json.dumps({"at": _half, "iso": "x", "seen": "a man at a desk"}) + "\n")
_st = amb.status()
ok((_st["last"] or {}).get("seen") == "a man at a desk",
   "the last look is read back after a restart, with its words", _st["last"])
ok(_st["next_in_s"] is not None and 1500 < _st["next_in_s"] < 2100,
   "...and the next look is half an hour away, not a fresh full hour", _st["next_in_s"])
ok(abs(amb._last_at() - _half) < 1.0,
   "the SCHEDULE reads the same row the readout does", (amb._last_at(), _half))
for _k in ("SP_AMBIENT_LOG", "SP_AMBIENT", "SP_AMBIENT_S"):
    os.environ.pop(_k, None)
importlib.reload(amb)

print("\n8. THE TIMER CAN BE STOPPED WITHOUT BLINDING HER")
# 2026-08-03. A webcam capture landed at the tail of a lockup, and the hourly eye is the
# one background actor that fires a VISION forward from a timer thread — unasked, into
# whatever else is running. So it is switchable off, and the switch had to be reachable
# WITHOUT A RESTART, because a camera is the thing you most want to stop now rather than
# after a bounce.
#
# THE SEPARATION IS THE POINT. Off must stop the CLOCK and leave HER EYES alone: if the
# room then stays healthy and only faults when she chooses to look, the fault is in the
# vision forward; if it faults either way, the camera is exonerated. A switch that took her
# sight with it would answer neither question.
os.environ["SP_AMBIENT_LOG"] = os.path.join(tempfile.mkdtemp(prefix="g_sense_amb2_"), "a.jsonl")
os.environ["SP_AMBIENT"] = "1"
importlib.reload(amb)
_tune7.set_many({"senses.ambient": True})
ok(amb.enabled(), "armed: the env arms it and the knob is not vetoing")
_tune7.set_many({"senses.ambient": False})
ok(not amb.enabled(), "the knob VETOES a live timer — no restart needed")
os.environ["SP_AMBIENT"] = "0"
_tune7.set_many({"senses.ambient": True})
ok(not amb.enabled(), "...and the knob cannot ARM what the env has not: it only subtracts")

# HER EYES ARE NOT THE TIMER, asserted structurally: none of the three tools she calls may
# consult the ambient switch, or "stop photographing my room on a clock" quietly becomes
# "you may not look".
import inspect as _insp  # noqa: E402
from harness.skills import sight as _sight  # noqa: E402
for _fn in ("take_photo", "look_at", "room_history"):
    _f = getattr(_sight, _fn, None)
    _src = _insp.getsource(_f) if _f else ""
    ok(_f is not None and "ambient.enabled" not in _src and "SP_AMBIENT" not in _src,
       "%s stays hers to call, whatever the timer is doing" % _fn)
if _knob_was is None:
    _tune7.reset("senses.ambient")     # he had no override; leave none behind
else:
    _tune7.set_many({"senses.ambient": bool(_knob_was)})
for _k in ("SP_AMBIENT_LOG", "SP_AMBIENT"):
    os.environ.pop(_k, None)
importlib.reload(amb)

print("\n§ THE QUIET GUARD (2026-08-21, the re-arm's condition) — due is not NOW")
# Re-armed on his order with the guard: a due capture waits for a window of no
# activity (his turns, her kairos/solo work, the daemon) and the wait holds the
# shutter without pushing the schedule. _beat is the REAL loop body, factored so
# this drives it rather than a re-implementation.
import tempfile as _tf8
import time as _t8
os.environ["SP_AMBIENT"] = "1"
os.environ["SP_AMBIENT_LOG"] = os.path.join(_tf8.mkdtemp(prefix="g-amb-quiet-"),
                                            "ambient.jsonl")
# HIS LIVE KNOBS MUST NOT DECIDE THIS LEG (2026-08-21 20:xx: he had just vetoed the
# eye in the panel — senses.ambient=False — and five checks here went red measuring
# HIS CHOICE rather than the guard). Save the overrides, arm for the leg, restore.
_qg_amb = _tune7.chosen("senses.ambient")
_qg_boot = _tune7.chosen("senses.ambient_on_boot")
_tune7.set_many({"senses.ambient": True})
_tune7.reset("senses.ambient_on_boot")
importlib.reload(amb)
ok(60.0 <= amb.quiet_s() <= 1800.0, "quiet_s is bounded to a sane window")
os.environ["SP_AMBIENT_QUIET_S"] = "240"
ok(amb.quiet_s() == 240.0, "…and the env boot default reaches it")
os.environ.pop("SP_AMBIENT_QUIET_S", None)
_shots = []
amb.observe_once = lambda: _shots.append(1)      # the camera is not part of this leg
amb._activity = lambda: "his turn is in flight"
_due = _t8.time() - 1.0
_n2 = amb._beat(_due)
ok(not _shots and _n2 == _due, "due + activity: no capture, and the schedule is HELD, not pushed")
ok(amb._WAITING.get("since") and amb._WAITING.get("why") == "his turn is in flight",
   "…and the deferral is visible — since + why")
_st8 = amb.status()
ok(_st8.get("waiting") and "his turn" in _st8["waiting"]["why"],
   "status() reports the wait so the panel can say it")
amb._activity = lambda: ""
_n3 = amb._beat(_due)
ok(len(_shots) == 1 and _n3 > _t8.time() - 1.0,
   "the first quiet beat fires the capture and only then advances the schedule")
ok(not amb._WAITING, "…and the wait state clears")
os.environ["SP_AMBIENT"] = "0"
amb._WAITING["since"] = _t8.time()
amb._beat(_t8.time() - 1.0)
ok(not amb._WAITING, "switching the eye off clears a pending wait")
# the guard fails OPEN: a broken signal must not blind the eye forever
importlib.reload(amb)          # restore the real _activity/observe_once
os.environ["SP_AMBIENT"] = "0"
ok(amb._activity() == "" or isinstance(amb._activity(), str),
   "_activity never raises — every broken signal fails open")
for _k8 in ("SP_AMBIENT", "SP_AMBIENT_LOG"):
    os.environ.pop(_k8, None)
importlib.reload(amb)

print("\n§ BOOT COUNTS AS ACTIVITY (2026-08-21) — unless he flips the knob")
# A bounce empties the kairos state, so the recency signal cannot testify and the
# guard fails open — one capture fired 11 minutes into a boot before this. Same
# shape as the kairos act-first-at-bounce knobs: default off, boot holds a full
# quiet window; the toggle restores fire-when-due.
os.environ["SP_AMBIENT"] = "1"
os.environ.pop("SP_AMBIENT_ON_BOOT", None)
importlib.reload(amb)               # a fresh module IS a fresh boot (_BOOT_AT = now)
ok(amb._activity() == "the stack just started",
   "straight after boot, the guard holds even with no other signal")
os.environ["SP_AMBIENT_ON_BOOT"] = "1"
ok(amb._activity() != "the stack just started",
   "…and the knob restores fire-when-due (boot no longer blocks)")
os.environ.pop("SP_AMBIENT_ON_BOOT", None)
amb._BOOT_AT -= amb.quiet_s() + 1.0
ok(amb._activity() != "the stack just started",
   "a stack up longer than the quiet window is not 'just started'")
os.environ.pop("SP_AMBIENT", None)
# put his overrides back exactly as they were (None = no override)
if _qg_amb is None:
    _tune7.reset("senses.ambient")
else:
    _tune7.set_many({"senses.ambient": bool(_qg_amb)})
if _qg_boot is None:
    _tune7.reset("senses.ambient_on_boot")
else:
    _tune7.set_many({"senses.ambient_on_boot": bool(_qg_boot)})
importlib.reload(amb)

print("\n§ HER ROOM NOTE IS PERSONAL — the door's prompt, not a surveyor's")
# 2026-08-21, his ask: the eye is her window into HIS world. The door default
# names Sam (never "a man"), makes the room's things his, and keeps the
# stranger clause — which is also the seed of "notice if others are here".
_serve8 = open(os.path.join(ROOT, "serve.py"), encoding="utf-8").read()
ok("SP_AMBIENT_ON_BOOT" in _serve8, "the boot knob is mapped through the one door")
_pi = _serve8.index('"SP_AMBIENT_PROMPT"')
_pchunk = _serve8[_pi:_pi + 900]
ok("Sam" in _pchunk and "never" in _pchunk,
   "the door's prompt names him — Sam, never 'a man'")
ok("his desk" in _pchunk and "his bed" in _pchunk,
   "…and his room's things are HIS, not 'a desk'")
ok("not Sam" in _pchunk,
   "…and the stranger clause survives — anyone else is said plainly")

print("\n§ THE LOOK'S CEILING IS A KNOB, AND A CEILING IS NOT A TARGET")
# 220 tokens — sized for the hourly one-sentence room note — silently cut the
# description of an attached photo mid-thought (the white-jumper report). The
# chip was innocent: it slices for display at its own edge; SHE gets the full
# string. The budget is his knob now, read per look.
from harness.skills import sight as _sg8
ok(64 <= _sg8._look_tokens() <= 2048, "the default budget is sane and bounded")
ok(_sg8._look_tokens() >= 512, "…and no longer the 220 that cut the description")
os.environ["SP_SIGHT_LOOK_TOKENS"] = "96"
ok(_sg8._look_tokens() == 96, "the env boot default reaches it")
os.environ.pop("SP_SIGHT_LOOK_TOKENS", None)
_src8 = _insp.getsource(_sg8._describe)
ok("_look_tokens()" in _src8, "_describe reads the budget per call, not at import")

print(f"\nG-SENSES: {_P} pass, {_F} fail")
sys.exit(1 if _F else 0)
