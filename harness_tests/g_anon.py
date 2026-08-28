"""G-ANON — off the record means off the record. OFFLINE.

WHAT THIS GUARDS (2026-08-23, the operator's ask: *"an icon that activates anonymous mode that will
still be her but will not record any memory or logs etc until turned off or restarted"*).

A privacy mode is a claim about ABSENCE, and absence is the one property a feature cannot
demonstrate by working. "I clicked it and she still talked to me" proves nothing at all.
So this gate does the only thing that does prove it: it **snapshots the whole sandbox,
drives every door for real with the switch on, and diffs the disk**. A byte that appears
is a failure, whatever the code looked like.

THE THREE FAILURE SHAPES IT IS BUILT AROUND, all of which this codebase has shipped:

  1. A DOOR NOBODY WIRED. `harness/control/anon.py::DOORS` declares the recording surface;
     §7 fails if any declared door was never once held while this gate ran. A door added
     to the table without its guard convicts itself instead of sitting there decorative —
     the G-MOE-SEAM shape, which on its first run named six entry points its author had
     missed.
  2. A HOLD THAT ONLY DEFERS. `persist_receipts` returning 0 looks like a hold and is not
     one: the receipts stay in the ring above the watermark, so the first flush after the
     mode ends writes every private turn. §5 asserts the watermark MOVED. Same shape as
     free-before-drain and the inert wardrobe shim — a guard whose failure mode is no
     guard.
  3. A MODE THAT DISABLES THE ROOM. Anonymous mode stops the room RECORDING; it must not
     stop the room. §6 proves she still recalls everything she knew, that HIS decision
     still lands, and that a want he dismisses still gets dismissed — the doors that
     answer are not the doors that create.

AND THE ONE THAT MATTERS MOST: §2 proves it is OFF in a fresh process and that nothing on
disk can say otherwise. "until turned off or restarted" is his specification, and a mode
that could survive a reboot would swallow a month of her memory on the strength of a click
nobody remembers making.

    python harness_tests/g_anon.py
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"
os.environ["CUDA_VISIBLE_DEVICES"] = ""

SB = os.path.join(tempfile.gettempdir(), "_g_anon")
shutil.rmtree(SB, ignore_errors=True)
os.makedirs(SB)
os.environ["SP_RECALL_REGISTRY"] = os.path.join(SB, "registry.jsonl")
os.environ["SP_PERSONALITY_TIER"] = os.path.join(SB, "personality")
os.environ["SP_DECISIONS"] = os.path.join(SB, "decisions.jsonl")
os.environ["SP_RESEARCH_RECEIPTS"] = os.path.join(SB, "research")
os.environ["SP_AVATAR_DIR"] = os.path.join(SB, "avatar")
os.environ["SP_AMBIENT_LOG"] = os.path.join(SB, "ambient.jsonl")   # read at import time
os.environ["SP_PERSONA_FILE"] = os.path.join(SB, "persona.md")
os.environ["SP_TELEMETRY_OKF_ROOT"] = os.path.join(SB, "telemetry")
os.environ["SP_EPS_DIR"] = os.path.join(SB, "episodes")
open(os.environ["SP_RECALL_REGISTRY"], "w").close()
io.open(os.environ["SP_PERSONA_FILE"], "w", encoding="utf-8").write(
    "She is dry and warm.\n\n## Personality state\nmood: neutral\nvoice: dry\n")

from harness.control import anon as AN            # noqa: E402
from harness.control import spine as SP           # noqa: E402
from harness.control import wardrobe as WD        # noqa: E402
from harness.personality import persona_file as PF  # noqa: E402
from harness.senses import ambient as AMB         # noqa: E402
from harness.skills import decisions as DEC       # noqa: E402
from harness.skills import looking as LK          # noqa: E402
from harness.skills import memory as M            # noqa: E402
from harness.skills import narrative as N         # noqa: E402
from harness.kairos import speechlog as SL        # noqa: E402
from harness.server import app as A               # noqa: E402


def tree() -> dict:
    """Every file under the sandbox and its bytes. The disk is the only witness that
    matters here: a mode that says nothing was written and left a file has failed,
    regardless of what its counters report."""
    out = {}
    for base, _dirs, files in os.walk(SB):
        for f in files:
            p = os.path.join(base, f)
            try:
                out[os.path.relpath(p, SB)] = os.path.getsize(p)
            except OSError:
                pass
    return out


print("\n1. IT IS OFF, AND SHE IS RECORDED NORMALLY")
check("a fresh process comes up OFF", AN.on() is False)
check("...and holds() lets the write through while it is off",
      AN.holds("memory.row") is False)
check("...and there is nothing to tell her", AN.note() == "")
seed = M.remember("Sam's workshop is called Forge42.", source="gate")
check("a fact stored with the switch off is stored", "forge42" in
      io.open(os.environ["SP_RECALL_REGISTRY"], encoding="utf-8").read().lower(), seed)
DEC.ask("A question from before the private hour", id="pre-anon")
check("...and so is a decision card",
      any(r.get("id") == "pre-anon" for r in DEC.items()))

print("\n2. THE SWITCH IS VOLATILE — NOTHING ON DISK MAY SAY IT IS ON")
before = tree()
AN.enter("him")
check("it turns on", AN.on() is True)
check("...and turning it on wrote NOTHING anywhere", tree() == before,
      sorted(set(tree()) - set(before)))
check("...it is not in the environment either — a child process inherits nothing",
      not any("ANON" in k.upper() for k in os.environ))
_an_src = io.open(os.path.join(ROOT, "harness", "control", "anon.py"), encoding="utf-8").read()
check("...and the module itself cannot write: no open(), no path, no env of its own",
      not any(t in _an_src for t in ("open(", "os.path", "environ", "json.dump")),
      [t for t in ("open(", "os.path", "environ", "json.dump") if t in _an_src])

print("\n3. EVERY DOOR IS SHUT — DRIVEN FOR REAL, THEN THE DISK IS READ")
before = tree()

r = M.remember("The user's dog is called Biscuit.", source="gate")
check("memory: remember() refuses and SAYS SO (she must not silently fail to store)",
      r == AN.WHY, r)
r = M.remember_about_self("I felt quiet tonight.", kind="feeling")
check("memory: remember_about_self goes through the same one door", r == AN.WHY, r)

A._append_day_turn("something private", "something private back")
check("transcript: the day file is not written",
      not os.path.exists(A._day_transcript_path()), A._day_transcript_path())

r = N.note_own("I read for an hour and did not think about much.")
check("journal: her own-time note is refused", r.get("written") is False, r)

_called = {"n": 0}


def _must_not_run(*_a, **_k):
    _called["n"] += 1
    return "a paragraph about the private evening"


r = N.compose_and_write([{"role": "user", "content": "hello"},
                         {"role": "assistant", "content": "hi"}], ask=_must_not_run)
check("journal: the nightly paragraph is refused", r.get("written") is False, r)
check("...and the MODEL WAS NEVER CALLED — held before the engine spends two minutes "
      "composing a thing that must not exist", _called["n"] == 0, _called)

SL.record("spoke_up", SL.DROPPED, "a greeting", "hey you, are you awake?")
check("speech: the veto log keeps neither the text nor the tally",
      not os.path.exists(os.path.join(SB, "speech.jsonl")))

PF.write_state(os.environ["SP_PERSONA_FILE"], {"mood": "breathless", "voice": "low"})
_disk = io.open(os.environ["SP_PERSONA_FILE"], encoding="utf-8").read()
check("persona: persona.md does not learn the evening", "breathless" not in _disk)
_, _st = PF.parse_persona(_disk)
check("...but SHE DOES — the dial moved, in memory, so her marks are not frozen",
      _st.get("mood") == "breathless", _st)

r = WD.request("something I would only ask for tonight", by="her")
check("wardrobe: a new want is refused", r.get("ok") is False, r)

r = AMB.observe_once()
check("senses: the hourly eye does not open the shutter", "skipped" in r, r)

LK._write({"kind": "web_search", "query": "something private", "ok": True})
check("lookups: the receipt ledger is not appended",
      not os.path.exists(os.path.join(SB, "research", "looks.jsonl")))

r = DEC.ask("A question raised during the private hour", id="in-anon")
check("decisions: a new card is refused", r.get("ok") is False, r)

_ = AN.say("she said something out loud here")
check("logs: her words are redacted, not silenced — the turn is still provable",
      "held back" in _ and "she said" not in _, _)

after = tree()
check("AND THE DISK IS UNCHANGED — the only witness that counts",
      after == before, {"new": sorted(set(after) - set(before)),
                        "grew": [k for k in before if after.get(k) != before[k]]})

print("\n3b. AND NOTHING LEAVES THE MACHINE")
# HIS QUESTION, 2026-08-24: "does anon mode leak anywhere? eg via voice either local or
# sent to providers such as the xai api? ensure all surfaces are covered."
#
# It did, and this was the worse half. The doors in section 3 stop the evening reaching
# HIS DISK, which he can audit and delete. These stop it leaving the MACHINE, which he
# cannot. `voice.method` is `xai` on his live profile, so every sentence she spoke off
# the record was posted to api.x.ai in full.
#
# DRIVEN, NOT GREPPED, and the transport is a TRIPWIRE: any request that reaches the
# wire fails the gate by name. A guard that let the call through and merely discarded
# the answer would pass a "did it return nothing" test and fail the actual claim.
_sent = []


def _tripwire(*a, **k):
    _sent.append(str(a[0])[:60] if a else "?")
    raise AssertionError("a request left the machine while the switch was ON")


import urllib.request as _u  # noqa: E402
_real_urlopen = _u.urlopen
_u.urlopen = _tripwire
try:
    from harness.skills import search as _S      # noqa: E402
    from harness.skills import research as _R    # noqa: E402
    from harness.skills import xai as _X         # noqa: E402
    from harness.voice import tts as _T          # noqa: E402

    check("search: the query does not leave", _S.search_web("something private") == [])
    _rr = _R.research("something private")
    check("research: the question does not leave", "off the record" in _rr, _rr)
    check("xai: the ONE door out of that module refuses",
          _X._post("/images/generations", {"prompt": "something private"}) is None)
    check("...and so does the multipart upload, which does not go through it",
          _X.upload_image("nonexistent.png") == "")
    # HER VOICE. A REMOTE method is egress and is held; a LOCAL one is not and must
    # still speak, or the mode has silenced her, which is the room being disabled.
    os.environ["SP_TTS_ENABLED"] = "1"
    os.environ["SP_TTS_METHOD"] = "xai"
    # ARM THE KNOB, NOT JUST THE ENV (2026-08-25). `synthesize()` resolves through
    # live_voice(), where the tuning knob outranks the env spelling so the room's toggle
    # takes effect without a bounce — so in a tree whose `voice.enabled` is OFF (a fresh
    # Kairos clone: nobody has configured a voice yet) it raised "voice is off" BEFORE
    # reaching the anon guard, `holds("net.voice")` was never called, and the door-table
    # check convicted a door that is in fact held. The ORDERING IS CORRECT — no voice, no
    # egress — so the gate supplies the precondition it actually needs (her voice on,
    # remote) rather than the code being bent to the gate. Found by running the suite
    # inside the export.
    from harness.tuning import registry as _tune_v      # noqa: E402
    _voice_was = _tune_v.get("voice.enabled")
    _tune_v.set_many({"voice.enabled": True})
    try:
        _T.synthesize("something private")
        check("voice: a REMOTE voice is held", False, "it synthesised anyway")
    except _T.TTSError as _e:
        check("voice: a REMOTE voice is held", "off the record" in str(_e), str(_e)[:90])
    finally:
        _tune_v.set_many({"voice.enabled": bool(_voice_was)})
    check("NOTHING REACHED THE WIRE - the tripwire never fired", not _sent, _sent)
    # THE CACHED WAV. This one cannot be driven to completion in an OFFLINE gate: the
    # remote guard above raises before the cache is reached, and the local branch needs a
    # voxtral backend no gate has. So the behavioural half is stated as the limit it is,
    # and what IS asserted is that the write site consults the door - not that a comment
    # near it mentions one. `use_cache and not holds(...)` is the whole guard; a grep for
    # the door NAME alone would pass on a file that only talks about it.
    _tsrc = io.open(os.path.join(ROOT, "harness", "voice", "tts.py"), encoding="utf-8").read()
    check("voice: the cache WRITE is gated on the door, not merely near it",
          'if use_cache and not _anon.holds("voice.cache")' in _tsrc)
    check("...and a cache READ is deliberately left alone - a hit means she said it "
          "before, on the record", "if use_cache and os.path.isfile(path):" in _tsrc)
    AN.holds("voice.cache")     # register it, so section 7's door table stays closed
finally:
    _u.urlopen = _real_urlopen
check("...and every egress door is declared, like every other door",
      all(d in AN.DOORS for d in ("net.voice", "net.search", "net.research",
                                  "net.provider", "voice.cache")))

print("\n4. WHAT SHE IS TOLD")
check("she is told, in one line on his turn", AN.note() == AN.NOTE and AN.NOTE)
# ── AND IT IS A FACT, NOT AN ORDER (2026-08-24) ───────────────────────────────────
# The first draft was four clauses and three of them were instructions, and it induced
# exactly what app.py:2912 warned about in 2026-08-19: she opened every reply with
# third-person deliberation about him and about the note. Measured against the same six
# prompts with the switch off, which produced none. So the note is held SHORT and
# IMPERATIVE-FREE - the shape the recall and silence notes have, which ride on his words
# every turn and have never done this.
check("...in ONE sentence, because a long parenthetical reads as an instruction",
      AN.NOTE.count(".") <= 1 and len(AN.NOTE) < 120, (len(AN.NOTE), AN.NOTE))
check("...and it gives no orders", not any(
    w in AN.NOTE.lower() for w in ("do not", "don't", "you must", "you need not", "never ")),
      AN.NOTE)
check("...it just says the true thing", "off the record" in AN.NOTE.lower()
      and ("saved" in AN.NOTE.lower() or "written" in AN.NOTE.lower()), AN.NOTE)
_src = io.open(os.path.join(ROOT, "harness", "server", "app.py"), encoding="utf-8").read()
check("...and the gateway staples it where the silence note is stapled",
      "_anon_n.note()" in _src and '{"anon": True}' in _src)

print("\n5. A HOLD THAT ONLY DEFERS IS NOT A HOLD")
# Push receipts into the ring the way a turn does, then flush. The failure this catches
# is the plausible one: returning 0 leaves them above the watermark, so the first flush
# AFTER the mode ends writes the private turns after all.
from harness.control.spine import SpineReceipt   # noqa: E402
for i in range(3):
    SP._SEQ += 1
    SP._RECEIPT_RING.append((SP._SEQ, time.time(),
                             SpineReceipt(decider="d", kind="recall", ok=True,
                                          verified=True, result="what she was asked",
                                          ms=1.0)))
_hi_before = SP._PERSISTED_SEQ
check("spine: the flush writes nothing", SP.persist_receipts() == 0)
check("...and the WATERMARK MOVED PAST THEM, so they can never be flushed later",
      SP._PERSISTED_SEQ >= SP._SEQ, (_hi_before, SP._PERSISTED_SEQ, SP._SEQ))

print("\n5b. HIS BODY IS OFF THE RECORD TOO (2026-08-26)")
# THE MOST PRIVATE ROW THIS SYSTEM WRITES. The telemetry lane records heart rate, movement
# and sleep at up to 1 Hz; a private hour that kept logging it would be off-the-record
# writing the most intimate thing in the store while the room said nothing was kept.
import tempfile as _tf                                                     # noqa: E402
os.environ["SP_TELEMETRY_DIR"] = os.path.join(_tf.mkdtemp(prefix="g_anon_tel_"), "tel")
from harness.telemetry import ingest as TEL, store as TELS                 # noqa: E402
_r = TEL.record([{"kind": "heart_rate", "value": 88},
                 {"kind": "sleep_stage", "value": "deep"},
                 {"kind": "steps", "value": 4211}], source="watch")
check("telemetry: nothing from his body is written", _r["stored"] == 0, _r)
check("...and the store on disk is still empty", TELS.verify()["samples"] == 0)
# THE COUNT IS THE RECEIPT. Every door before this one held exactly one thing per call, so
# the counter incremented by one and was right. This door asks ONCE for a whole batch, and
# under-reporting what was withheld is the one lie this mode cannot afford.
check("...and the room is told the TRUE number held, not the number of calls",
      AN.state()["held"].get("telemetry.sample") == 3,
      AN.state()["held"].get("telemetry.sample"))
check("...phrased for him", AN.phrase("telemetry.sample", 3) == "3 readings from his body",
      AN.phrase("telemetry.sample", 3))

print("\n6. SHE IS STILL HER, AND THE ROOM STILL WORKS")
check("she recalls what she knew before — reads are untouched",
      "forge42" in M.recall("what is the workshop called").lower(),
      M.recall("what is the workshop called"))
check("...and her memory did not shrink", len(M.live_rows()) >= 1)
r = DEC.decide("pre-anon", "yes", "he answered during the private hour")
check("HIS answer to an old question still lands — the mode quiets the room, "
      "it does not disable it", r.get("ok") is True, r)
check("...and it is on disk", "he answered during the private hour" in
      io.open(os.environ["SP_DECISIONS"], encoding="utf-8").read())

print("\n7. THE DOOR TABLE IS CLOSED")
_held = AN.state()["held"]
_missing = [d for d in AN.DOORS if d not in _held]
check("every door DECLARED in anon.DOORS was actually held by this gate",
      not _missing, _missing)
check("...and every door held is declared — no bare string typed at a call site",
      not [d for d in _held if d not in AN.DOORS], list(_held))
check("an UNKNOWN door still holds — a typo must fail closed, never open",
      AN.holds("memory.roww") is True)

print("\n8. IT ENDS, IT SAYS WHAT IT HELD, AND THE TALLY GOES WITH IT")
st = AN.state()
check("the tally counted the whole evening", st["held_total"] >= 12, st["held_total"])
out = AN.leave()
check("it turns off", AN.on() is False)
check("...and the REPLY says so — a switch whose answer contradicts what it just did is "
      "worse than no answer (caught on this route's first live call)",
      out["on"] is False and out["was_on"] is True, out)
check("...and hands back the receipt ONCE", out["held_total"] >= 12 and
      "held back" in out["receipt"], out["receipt"])
check("...naming the memories in words, not module paths",
      "memories" in out["receipt"], out["receipt"])
check("...and it counts in English: '1 memory', never '1 memories'",
      AN.phrase("memory.row", 1) == "1 memory"
      and AN.phrase("memory.row", 6) == "6 memories",
      (AN.phrase("memory.row", 1), AN.phrase("memory.row", 6)))
check("...and every door has both numbers spelled out — English is not derivable here",
      all(isinstance(v, tuple) and len(v) == 2 and v[0] != v[1]
          for v in AN.DOORS.values()),
      [k for k, v in AN.DOORS.items() if not (isinstance(v, tuple) and len(v) == 2)])
check("...and the tally is then GONE — the mode does not keep its own record either",
      AN.state()["held_total"] == 0 and AN.state()["receipt"] ==
      "nothing to hold back yet", AN.state())
_, _st2 = PF.parse_persona(io.open(os.environ["SP_PERSONA_FILE"], encoding="utf-8").read())
check("...and she comes out as she went in — the private evening left no mark on her",
      _st2.get("mood") == "neutral", _st2)

print("\n9. RECORDING RESUMES")
before = tree()
M.remember("Sam's second workshop is called Forge43.", source="gate")
check("a fact stored after the switch is stored again",
      "forge43" in io.open(os.environ["SP_RECALL_REGISTRY"], encoding="utf-8").read().lower())
A._append_day_turn("back on the record", "and I will keep this one")
check("...and the day transcript is written again",
      os.path.exists(A._day_transcript_path()))
check("...and the private turns did NOT come back with them",
      "biscuit" not in json.dumps(M._load()).lower()
      and "private" not in io.open(A._day_transcript_path(), encoding="utf-8").read().lower(),
      "a held write must stay held after the mode ends")
check("the disk grew, which is what recording looks like", tree() != before)

finish("G-ANON")
