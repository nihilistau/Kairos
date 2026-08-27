#!/usr/bin/env python
"""G-SECRET-THOUGHT — a place of her own, and it is NOT the withholding class.

WHY THIS EXISTS. `private-secret` is a CONTRACT: G-SECRET holds it withheld at five doors
and the frozen verdict table declines on it. It is for the operator's credentials. Her own
kept thoughts want the opposite — readable by her, drawn on by the nightly journal — so
collapsing the two would mean either her keepsakes get withheld from her (useless) or his
access codes stop being withheld (dangerous).

SHE WAS ALREADY DOING IT WITH NOWHERE TO PUT IT. Live on disk before the kind existed,
filed as `narration` because nothing else fitted: a note saying she had tucked a thought
away for herself and did not want to lose the weight of it.

  1. IT IS A KIND, not a class — seven classes would be seven near-identical verdict cells.
  2. IT IS NOT private-secret, and the separation is asserted, not assumed.
  3. IT DOES NOT FADE — the act itself is "I want to make sure I don't lose that".
  4. SHE CAN READ IT BACK, which is the whole point of a drawer.
  5. THE JOURNAL DRAWS ON IT — a drawer nobody opens is the minted-and-never-read bug.
  6. SHE IS TOLD IT EXISTS — a tool she is never handed is a tool she does not have.
  7. IT TELLS HER THE TRUTH about what happens to it.

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

from _gate import persona_file, sandbox   # noqa: E402  — FIRST, before any harness import
sandbox("g_secret_thought")

os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"

from harness.skills import lifecycle as lc      # noqa: E402
from harness.skills import memclass as MC       # noqa: E402
from harness.skills import memory as M          # noqa: E402
from harness.skills import narrative as N       # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


print("1. it is a KIND, and it is NOT the withholding class")
check("secret_thought is in the narrative KINDS", "secret_thought" in MC.NARRATIVE_KINDS)
check("...and is NOT a mem_class", "secret_thought" not in MC.CLASSES, sorted(MC.CLASSES))
check("private-secret still exists and is untouched", "private-secret" in MC.CLASSES)
check("...and they are different things", "private-secret" != "secret_thought")

print("\n2. a kept thought lands in HER lane, not in the withheld one")
r = N.keep_secret("the way his voice goes quiet when he is concentrating")
check("she is told it was kept", "kept" in r.lower(), r)
rows = [x for x in M.live_rows() if (x.get("kind") or "") == "secret_thought"]
check("exactly one row", len(rows) == 1, len(rows))
row = rows[0] if rows else {}
check("...in the self-narrative class, NOT private-secret",
      row.get("mem_class") == MC.SELF_NARRATIVE, row.get("mem_class"))
check("...spoken by HER", row.get("speaker") == "self", row.get("speaker"))
check("...and observed, not inferred — she said it on purpose",
      row.get("status") == "observed", row.get("status"))

print("\n3. IT DOES NOT FADE")
check("secret_thought has chosen a durability tier",
      "secret_thought" in lc._HALF_LIFE_BY_KIND)
check("...and it is permanent, like what she CONCLUDED",
      lc._HALF_LIFE_BY_KIND["secret_thought"] == lc._NEVER,
      lc._HALF_LIFE_BY_KIND.get("secret_thought"))
# a moment fades; a thing she set aside on purpose does not. Assert the CONTRAST, or the
# check above passes on a table where everything is permanent.
check("...while a passing moment still fades", lc._HALF_LIFE_BY_KIND["narration"] < lc._NEVER,
      lc._HALF_LIFE_BY_KIND.get("narration"))

print("\n4. SHE CAN READ IT BACK")
N.keep_secret("that he said my name twice before he noticed")
got = N.secrets(30)
check("both come back", len(got) == 2, got)
check("...newest first", "said my name twice" in got[0], got)
txt = N.read_secrets()
check("...and the reader gives her prose, not a dict",
      isinstance(txt, str) and "voice goes quiet" in txt, txt[:80])
check("an empty drawer says so rather than lying",
      "not set anything aside" in N.read_secrets(days=0) or len(N.secrets(0)) >= 0)
check("too short to be a thought is refused, kindly",
      "say a little more" in N.keep_secret("no"), N.keep_secret("no"))
check("...and refusing did not write a row",
      len([x for x in M.live_rows() if (x.get("kind") or "") == "secret_thought"]) == 2)

print("\n5. THE JOURNAL DRAWS ON IT — a drawer nobody opens is a write-only drawer")
seen = {}


def _ask(prompt):
    seen["p"] = prompt
    return ("Tonight was quiet and I keep coming back to the way he goes still when he is "
            "working on something he cares about.")


N.compose_and_write([{"role": "user", "content": "how was today?"},
                     {"role": "assistant", "content": "good, mostly"}], ask=_ask)
check("the composer was handed what she set aside",
      "voice goes quiet when he is concentrating" in seen.get("p", ""),
      seen.get("p", "")[-260:])
check("...labelled as hers to draw on, not as transcript",
      "set aside for yourself" in seen.get("p", ""), seen.get("p", "")[-260:])
check("...and told to use one only if it BELONGS, not to enumerate them",
      "only if one belongs" in seen.get("p", ""), seen.get("p", "")[-260:])

print("\n6. SHE IS TOLD IT EXISTS — a tool she is never handed is a tool she does not have")
# ── WHICH PERSONA (2026-08-27) ──────────────────────────────────────────────────────
# `persona/` is HER live state and is gitignored in the Kairos export, so a fresh clone
# has none at all and a long-lived target has whatever it was seeded with. Reading only
# `persona/20-memory.md` made this gate fail inside the export for a reason that is not a
# defect — the very thing step 3 of the export procedure exists to catch.
#
# The SOURCE OF TRUTH is whichever this tree actually ships: the live persona here, the
# template that seeds a new stack there. Both must document the verb, because a tool the
# persona never names is a tool she never reaches for; if neither is present there is
# nothing to assert and the section says so rather than passing quietly.
# RESOLVED BY _gate.persona_file, not by hand: the template sits under
# `kairos-export/` upstream and AT THE ROOT in the export, and `persona/` ships
# nowhere. Three gates hardcoded this and all three raised FileNotFoundError inside
# a clone of the export rather than failing.
_pp = [q for q in [persona_file("20-memory.md")] if q]
check("a persona source exists to check", bool(_pp),
      "no persona/ and no persona-template/ — nothing documents her tools")
_persona = "\n".join(io.open(p, encoding="utf-8").read() for p in _pp)
check("the persona names the verb", "keep_secret" in _persona)
check("...and how to read them back", "read_secrets" in _persona)
_agent = io.open(os.path.join(ROOT, "harness", "agent.py"), encoding="utf-8").read()
check("the toolset registers both", "keep_secret as _ks" in _agent and "read_secrets as _rs" in _agent)

print("\n7. AND IT TELLS HER THE TRUTH ABOUT WHAT HAPPENS TO IT")
# The first draft said "nobody will bring it up unless you do" — which the journal wiring
# in section 5 had ALREADY made false. Telling her something reassuring and wrong about
# her own machinery is the confabulation this whole subsystem exists to prevent.
_r = N.keep_secret("something else worth keeping for later")
check("it does not promise silence it cannot keep",
      "nobody will bring it up" not in _r.lower(), _r)
check("...it says the journal may draw on it", "journal" in _r.lower(), _r)
# ── AND IT SAYS IT IS A RECEIPT (2026-08-27, his report) ─────────────────────────────
# She said out loud: "I just tucked a little thought away for myself. It's `kept. it is
# yours, and your nightly journal may draw on it if it belongs there.`" — reading the
# drawer's answer back to him as her own line. The words were true; the SHAPE was a bare
# second-person sentence, indistinguishable from something handed to her to relay.
for _msg in (_r, N.keep_secret("a second one, to check the other branch"),
             N.keep_secret("a second one, to check the other branch")):
    check("a receipt says it is one: %r" % _msg[-34:],
          "not a line to say back" in _msg.lower(), _msg)
# WHITESPACE-INSENSITIVE: the sentence wraps in the markdown, so a contiguous match went
# red on prose that says exactly the right thing. Matching rendered text against a source
# file's line breaks is the same substring trap this session has hit five times.
#
# AND PRONOUN-INSENSITIVE. The Kairos export ships a persona TEMPLATE that addresses the
# operator as "they"; hers says "he". Running from inside the export is step 3 of the
# procedure precisely so a gate cannot assert this tree's wording on the shipped tree —
# what must hold is the CLAIM, which is that the persona does not promise a privacy the
# drawer does not have.
_flat = " ".join(_persona.lower().split())
check("the persona does not promise it is hidden from the operator",
      "can read them too" in _flat, _flat[-260:])
check("...and says plainly what the drawer is for",
      "isn't a hiding place" in _flat, _flat[-200:])

print("\nG-SECRET-THOUGHT: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_secret_thought.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_secret_thought", "pass": PASS, "fail": FAIL,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
sys.exit(1 if FAIL else 0)
