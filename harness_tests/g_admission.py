"""G-ADMISSION — is the B4 firehose actually off? OFFLINE.

The registry audit found 487 rows, ~375 of them voice/ASR TEST CORPUS that the B4
auto-capture had swallowed because the admission gate was "any declarative, 4..120 words,
not a question":

    "The kind nurse painted the tall building as the sun went down."
    "A lonely sailor polished the garden as the church bells rang."

Grammatical. Declarative. In range. About NOBODY. They then surfaced mid-answer as "recalled
memories" — the recall misfire. A durable fact is ABOUT SOMEONE. So this feeds the capture
lane exactly the kind of sentence that filled the registry 404 times and asserts it is
REFUSED, while a real personal fact still lands, in the v2 schema (speaker/lifecycle) rather
than the old "The user said:" framing.

── THIS GATE HAD STOPPED MEASURING ANYTHING (found 2026-09-02, verifying the memory split) ──
It used to drive a real gateway turn over HTTP and then read her live registry. To avoid
polluting her transcript it marked the turn `synthetic` — correctly, via `_gate.probe()`. Then
the 2026-08-30 synthetic-quarantine fix landed, and `turn.py` now reads:

    if capture and not synthetic:

...so NEITHER of this gate's two sentences ever reached the store again. Leg 1 ("the
impersonal sentence is refused") passed **because nothing was captured at all** — vacuously,
over a firehose that could have been wide open — and legs 2-5 failed honestly. It printed
`FAIL (1/5)` and exited 1 for days, unnoticed, because its lane in GATE-INDEX was LIVE-SP and
the offline sweep therefore skipped it. Both halves of that are the same lesson: a gate whose
subject is quarantined for gates is a gate measuring the quarantine.

So it drives the CAPTURE DOOR directly — `turn._capture_after_turn`, the function the gateway
calls with the human's text — against a SANDBOXED registry. That keeps the door the product
uses (AGENTS.md §4) and loses the two things that broke it: no HTTP, so no synthetic flag to
suppress capture, and no live store to pollute. It is OFFLINE now, so the sweep runs it every
time instead of nobody running it at all.

    python harness_tests/g_admission.py
"""
from __future__ import annotations

import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, sandbox as _sandbox, utf8_stdout  # noqa: E402
import _src as _srcmod  # noqa: E402

utf8_stdout()
_SB = _sandbox(os.path.basename(__file__))
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"     # discard port: never needs a GPU
os.environ["SP_ENGINE_KIND"] = "openai"                # supports('capture') False: no mint
os.environ["SP_CAPTURE_ASYNC"] = "0"

REG = os.environ["SP_RECALL_REGISTRY"]

from harness.server import turn as _turn  # noqa: E402


def rows():
    if not os.path.exists(REG):
        return []
    return [json.loads(l) for l in io.open(REG, encoding="utf-8") if l.strip()]


def stored(needle):
    return [r for r in rows() if needle in (r.get("text") or "")]


def capture(text):
    open(REG, "w").close()
    _turn._capture_after_turn(text)


print("0. THE DOOR IS THE ONE THE GATEWAY CALLS, AND THE FLAG THAT BROKE THIS IS NAMED")
# ── WHY THIS LEG EXISTS (2026-09-02) ────────────────────────────────────────────────
# The previous version of this gate went through HTTP and was silently suppressed by the
# synthetic quarantine. Driving `_capture_after_turn` avoids that — but it also means this
# gate no longer proves the GATEWAY calls it, so the seam is asserted here instead of
# assumed: the gateway's turn path passes the human's text to this function, and it is the
# `synthetic` guard that stands between a driven turn and her store.
_t = _srcmod.pkg("harness", "server")
check("the gateway's turn path calls the capture lane",
      "_capture_after_turn(" in _t)
check("...and the synthetic guard is what suppresses a DRIVEN turn (the trap this gate hit)",
      "if capture and not synthetic:" in _t)
check("the capture door takes the human's text as an argument",
      "_capture_after_turn(human_text" in _srcmod.body(_turn._capture_after_turn))

print("\n1. THE EXACT SHAPE THAT FILLED THE REGISTRY 404 TIMES IS REFUSED")
capture("The kind nurse painted the tall building as the sun went down.")
_junk = stored("tall building")
check("an IMPERSONAL declarative is refused", not _junk,
      "captured anyway — the firehose is still on: %r" % (_junk[:1],) if _junk else "not captured")
capture("A lonely sailor polished the garden as the church bells rang.")
check("...and so is the second corpus shape", not stored("lonely sailor"),
      stored("lonely sailor")[:1])

print("\n2. AND THE LEG THAT MADE THAT MEANINGFUL — a real fact STILL LANDS")
# ── THE HALF THAT WAS VACUOUS (2026-09-02) ──────────────────────────────────────────
# "Refused" and "never even offered" look identical from the registry's side. Without this
# leg, §1 above is satisfied by a capture lane that is switched off entirely — which is
# EXACTLY the state this gate was in for days. So §1 is only worth reading because §2
# passes in the same run.
capture("My workshop bench is made of oak.")
_hit = stored("oak")
check("a PERSONAL fact still lands", bool(_hit),
      (_hit[0].get("text") or "")[:60] if _hit else "lost — the gate is too tight")
check("...it carries a SPEAKER (v2 schema)",
      bool(_hit) and _hit[0].get("speaker") == "user",
      _hit[0].get("speaker", "-") if _hit else "-")
check("...it carries LIFECYCLE, so it can be superseded",
      bool(_hit) and _hit[0].get("lifecycle") == 0,
      _hit[0].get("lifecycle") if _hit else "-")
check("...and the 'The user said:' framing is GONE",
      bool(_hit) and not (_hit[0].get("text") or "").startswith("The user said:"),
      (_hit[0].get("text") or "")[:40] if _hit else "-")
check("...and the episode lives with the DATA, not in the engine tree",
      bool(_hit) and "_nightshift_live" not in (_hit[0].get("dir") or "").replace("\\", "/"),
      (_hit[0].get("dir") or "")[-46:] if _hit else "-")

print("\n3. A TURN THAT IS MOSTLY BANTER YIELDS THE FACT AND NOT THE BANTER")
# The 17-row conversation the daemon swallowed whole: given a turn it had to keep all of it
# or none, so it kept all of it, and buried the real facts inside the chat.
capture("you are cool af! I really like you! anyway my NUC runs 24/7 in the cupboard.")
check("the durable sentence is kept", bool(stored("NUC")), rows())
check("...and the banter is not", not stored("cool af"), stored("cool af")[:1])

finish("G-ADMISSION")
