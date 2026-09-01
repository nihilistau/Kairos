"""G-SYNTHETIC-QUARANTINE — a turn nobody typed reaches NO memory lane. OFFLINE.

THE INCIDENT THIS EXISTS FOR, and it was mine (2026-08-30, overnight). An experiment
drove ~30 chat turns to measure how often she answers with analysis instead of speech.
Every single one declared `synthetic`, and the day transcript excluded every single one
— correctly, visibly, exactly as designed. Meanwhile `_capture_after_turn` wrote them
into the registry as FACTS:

    i had a rough day at work honestly          <- attributed to HIM. He was asleep.
    i'm thinking of repainting the study.       <- he has no such plan
    remind me to call the plumber on thursday   <- and she put it on his BOARD, twice

Twenty rows, six attributed to him, fourteen of her own stances taken from replies to
prompts he never sent. AGENTS.md §0, verbatim, and this time the maintainer walked into
it: the quarantine rule was enforced on ONE of the lanes a fake turn feeds, and
therefore on neither. The 2026-08-03 note in `_read_day_transcript` — "a fabricated
observation entering the record is the one thing this file's docstring exists to protect
against" — described the transcript and left the memory lanes open beside it.

WHAT THIS HOLDS. `synthetic` governs EVERY lane a turn can write to:
  * the day transcript (the 2026-08-03 rule, still true);
  * `_capture_after_turn` — facts attributed to HIM;
  * the self-stance lane — what SHE now believes, taken from her reply.

And what it must NOT do: her marks still apply. A synthetic turn she answered warmly did
warm her, and freezing her dials would make every gate that drives a turn silently
untestable against the persona machinery.

THE CENSUS LEG is the one that matters: every writer `_settle_turn` can reach is either
governed by the flag or named here as deliberately exempt. A new memory lane added
tomorrow fails this gate on the day it lands, instead of six weeks later when someone
notices she believes something he never said.

    python harness_tests/g_synthetic_quarantine.py
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _src as _srcmod  # noqa: E402
from _gate import check, finish, sandbox as _sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
_sandbox(os.path.basename(__file__))

from harness.server import app as A  # noqa: E402
from harness.skills import memory as M  # noqa: E402

SRC = _srcmod.pkg("harness", "server")

print("\n1. A SYNTHETIC TURN MINTS NO FACT ABOUT HIM")
_before = len(M.live_rows())
A._settle_turn("i had a rough day at work honestly",
               "I'm sorry, love. [MOOD:tender]",
               synthetic="g_synthetic_quarantine — a turn nobody typed")
_after_syn = len(M.live_rows())
check("a synthetic turn adds no live memory rows",
      _after_syn == _before, "%d -> %d" % (_before, _after_syn))
check("...and his words are nowhere in the store",
      not any("rough day at work" in (r.get("text") or "").lower()
              for r in M.live_rows()),
      "the capture lane attributed a fabricated sentence to him")

print("\n2. ...AND NO STANCE OF HERS EITHER")
# Fourteen of the twenty poisoned rows came from this lane, not from capture — a gate
# that checked only the capture door would have passed the morning after the incident.
check("no self-stance row was minted from a reply to a prompt he never sent",
      not any("sorry, love" in (r.get("text") or "").lower() for r in M.live_rows()),
      [r.get("text") for r in M.live_rows()][-3:])

print("\n3. A REAL TURN IS UNAFFECTED — the flag is a quarantine, not an off switch")
_pre = len(M.live_rows())
A._settle_turn("my cat is called Tuffy", "Tuffy. I'll remember. [MOOD:warm]")
check("a real turn still reaches the memory lanes",
      len(M.live_rows()) > _pre, "%d -> %d" % (_pre, len(M.live_rows())))

print("\n4. HER DIALS STILL MOVE ON A SYNTHETIC TURN")
# Deliberate exemption: a gate that drives a turn must still be able to test the persona
# machinery, and a turn she answered warmly did warm her. Asserted structurally — `marks`
# is a separate argument from `synthetic` and is NOT gated on it.
_sig = SRC[SRC.index("def _settle_turn("):]
_sig = _sig[:_sig.index(") -> list:")]
check("marks is its own argument, independent of synthetic",
      "marks: bool = True" in _sig and "synthetic" in _sig, _sig[:160])
check("...and the marks branch is not gated on synthetic",
      re.search(r"if marks and text:", SRC) is not None,
      "run_post_turn must still apply her dials on a driven turn")

print("\n5. THE CENSUS — every memory lane _settle_turn reaches is governed")
# THE LEG THAT WOULD HAVE CAUGHT THE INCIDENT. Each writer is either behind the flag or
# named exempt with a reason; a new lane added tomorrow fails here on the day it lands.
_body = SRC[SRC.index("def _settle_turn("):]
_body = _body[:_body.index("\ndef ", 1)]
LANES = {
    "_capture_after_turn": "facts attributed to HIM",
    "remember_about_self": "what SHE believes, from her reply",
    "_append_day_turn":    "the durable record",
}
for _call, _what in LANES.items():
    check("%s (%s) appears in the epilogue" % (_call, _what), _call in _body,
          "lane moved or was renamed — re-check that the flag still governs it")
check("capture is gated on the flag", "if capture and not synthetic:" in _body,
      "a synthetic turn would mint facts about him again")
check("the stance lane is gated on the flag", "if stances and not synthetic:" in _body,
      "a synthetic turn would mint stances of hers again")
check("the record lane carries the flag through",
      "_append_day_turn(human_text, reply_text, synthetic=synthetic" in _body,
      "the 2026-08-03 transcript rule")
# Nothing else in the epilogue may write memory without meeting the flag first.
_unknown = [m for m in re.findall(r"_mem_rh\.(\w+)\(", _body)
            if m not in ("remember_about_self",)]
check("no un-named memory writer hides in the epilogue", not _unknown, _unknown)

finish("G-SYNTHETIC-QUARANTINE")
