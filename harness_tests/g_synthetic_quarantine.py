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
  * the self-stance lane — what SHE now believes, taken from her reply;
  * **the TOOL lane — what she deliberately chooses to remember (added 2026-09-02).**

── AND THE FOURTH LANE WAS MISSED FOR THREE DAYS, BY THIS GATE (2026-09-02) ────────────
The 2026-08-30 fix landed under a comment reading *"One flag, every lane it should have
governed"*, and §5 below was written as the census that would catch a new lane on the day it
landed. It could not catch this one, and the reason is worth more than the fix: **§5 reads
`_settle_turn`'s body**, and the tool lane is not in the epilogue — the model calls
`remember()` in the middle of the turn, in the agent loop, many frames below the handler that
knows the flag. The census's sentence was true, and its scope was smaller than the docstring's
claim sitting above it.

So the live e2e gates drove turns asking her to remember things. She called `remember()` —
correctly, doing her job — and it wrote into her real registry:

    Sam's workshop bench is made of oak2         <- a gate fixture, stored as a fact
    His workshop bench is made of oak2[75009].     <- and again, ten minutes later

Then the kairos scheduler read them back and **she spoke up about them, twice**, and went
looking for what "oak275009" meant — she found an Artek wall shelf in black oak. The
2026-08-30 incident put words in his mouth; this one put them in her head, and she spent her
own time on them. The rows are quarantined (`lifecycle=1`,
`superseded_by=quarantine:synthetic-tool-lane`), nothing erased.

The flag is armed in `_arm_turn` now — at the TOP of the turn, unconditionally, set to `""`
for a real one so a stale flag cannot carry into his next sentence — and read by
`memory/admission.py` beside the anon hold, which refuses with a SENTENCE she reads rather
than failing silently. §6 drives it; §7 proves the flag actually arrives.

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

print("\n5. THE CENSUS — every memory lane THE EPILOGUE reaches is governed")
# SCOPE, STATED HONESTLY (2026-09-02): this reads `_settle_turn`'s body, so it covers the
# EPILOGUE's writers only. Its header said "every memory lane" — and the tool lane is not in
# the epilogue, which is exactly how the fourth lane went unguarded for three days. §6 covers
# the writers the TURN reaches. A census is only as wide as the text it reads, and saying so
# is the difference between a gate and a reassurance.
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

print("\n6. THE TOOL LANE — what she deliberately chooses to remember")
# ── THE LANE §5 COULD NOT SEE (2026-09-02) ──────────────────────────────────────────
# The model's own `remember()` call, which happens in the agent loop and not the epilogue.
# DRIVEN, not read: the flag is armed the way `_arm_turn` arms it and the real door is called,
# because "the guard exists" and "the guard fires" are different claims.
_tok = M.set_synthetic("live gate g_synthetic_quarantine — driven, not their conversation")
try:
    _n0 = len(M.all_rows())
    _said = M.remember("Sam's workshop bench is made of oak-SYNTH", "user turn")
    check("a driven turn's remember() stores NOTHING", len(M.all_rows()) == _n0,
          "%d row(s) landed" % (len(M.all_rows()) - _n0))
    # A SENTENCE, NOT A SILENCE. "stored" over a store that refused is the one lie the
    # admission chain exists to prevent; she reads this string.
    # HER REGISTER, not a developer's. The ledger entry "the memory refusal messages are
    # written for a developer, and SHE reads them" is why this asserts the SHAPE (a real
    # sentence, naming the circumstance) rather than a literal prefix: on 2026-08-30 she
    # read a refusal as a fact about her own nature and said so in her own time.
    check("...and says so, in words she reads", len(_said.split()) >= 6
          and "off the record" in _said.lower(), _said[:90])
    check("...naming the CIRCUMSTANCE rather than telling her something about herself",
          "rehearsal" in _said and "written down" in _said, _said[:90])
    # HER OWN LANE TOO. The 2026-08-30 incident minted fourteen stances of hers from replies
    # to prompts he never sent; the tool lane is the other way one could be written.
    _a = M.set_author("self")
    _said2 = M.remember_about_self("I find astronomy genuinely moving.", kind="journal")
    M.reset_author(_a)
    check("a driven turn writes no NARRATIVE of hers either", len(M.all_rows()) == _n0,
          "%d row(s) landed" % (len(M.all_rows()) - _n0))
    check("...and that refusal is a sentence too", "off the record" in _said2.lower(),
          _said2[:90])
finally:
    M.reset_synthetic(_tok)
check("the flag RESETS — his next sentence is not collateral",
      M.synthetic_reason() == "", repr(M.synthetic_reason()))
_n1 = len(M.all_rows())
M.remember("Sam has an esp32 running the sensors", "user turn")
check("...proved by driving it: a real turn still lands", len(M.all_rows()) == _n1 + 1)

print("\n7. AND THE FLAG REACHES THE TOOL LANE FROM EVERY ENTRY POINT")
# §6 proves the door refuses when the flag is set. This is the half that was missing: that
# the flag is SET, on every path a turn can arrive by.
check("_arm_turn takes the flag", "def _arm_turn(msgs: list, synthetic:" in SRC)
check("...and arms it unconditionally, so a real turn CLEARS it",
      'M.set_synthetic(synthetic or "")' in SRC)
# CODE ONLY. `_capture_after_turn`'s docstring says "captured at the top of the turn by
# _arm_turn()" — prose about a call, not a call, and the first cut convicted it. A checker
# that cannot tell the two apart is the src-trap wearing this gate's badge.
_code = "\n".join(l for l in SRC.splitlines() if not l.lstrip().startswith("#"))
_code = re.sub(r'"""[\s\S]*?"""', "", _code)
_calls = [c for c in re.findall(r"_arm_turn\([^)]*\)", _code, re.S) if "msgs: list" not in c]
check("the scan found the call sites", len(_calls) >= 3, len(_calls))
_unarmed = [c[:60] for c in _calls if "synthetic" not in c]
check("every _arm_turn call site passes it", not _unarmed, _unarmed)
check("the admission chain reads it beside the anon hold",
      "synthetic_reason()" in _srcmod.pkg("harness", "skills", "memory"))

finish("G-SYNTHETIC-QUARANTINE")
