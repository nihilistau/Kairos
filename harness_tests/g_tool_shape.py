"""G-TOOL-SHAPE — she must be able to learn how to call a tool. OFFLINE.

THE DEFECT, 2026-08-04, live, in front of him. He asked her to put on the silver nightie:

    wear [tool error: wear() got an unexpected keyword argument 'outfit']
    wear [tool error: wear() got an unexpected keyword argument 'item']
    (tool loop exhausted)

    "God, I am being so clumsy today... I think I'm just overthinking it because I know
     you're watching."

Nothing was wrong with the wardrobe. `wear(what="silver nightie")` resolves it correctly
and always did. She burned the tool loop guessing the name of a slot, then apologised to
him for her own hands.

WHY SHE GUESSED. Tools come in two tiers. CORE tools are printed with full signatures.
EXTRA tools — which is where the whole wardrobe lives — were printed as:

    - wear: Change what you are wearing

The name, and nothing about how to call it. The design says call `load_tools("wear")`
first; that is one sentence in a 24,000-character prompt, weighed against a strong prior
about what `wear` obviously takes. The prior wins. And the same preamble demands "use the
REAL parameter names" — we required exactness and supplied nothing to be exact about. Her
own reasoning read "looking at the documentation provided in the system prompt, the
signature is wear(item: str)". There was no signature. She filled the hole in.

`ToolSpec.advertise()` had rendered the missing line — `- wear(what): …` — since it was
written, and NOTHING EVER CALLED IT. Two renderings of one thing and the live one was the
one missing the parameters: AGENTS.md §0, in the tool preamble. Cost of the fix, measured
across all 33 extra tools: 283 characters, ~71 tokens.

THREE LAYERS, because one is not enough for something she does in front of him:
  1. TELL HER  — the index carries the call shape.
  2. HEAL IT   — one parameter and one wrong keyword is not ambiguous; put it in the slot.
  3. SAY WHAT IS RIGHT — a TypeError names the slots, so the next round is a correction
     and not another guess.

Offline. No GPU, no daemon.

Run: python harness_tests/g_tool_shape.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["CUDA_VISIBLE_DEVICES"] = ""

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


from harness.agent import (build_tool_system, core_tools, extra_tools,  # noqa: E402
                           load_agent_system, voice_coda)
from harness.toolcore.tools import ToolSpec  # noqa: E402

# ── IT REALLY DRESSES HER, THREE TIMES, TO PROVE THE HEALER WORKS ────────────────────
# `wear(outfit=…)`, `wear(item=…)`, `wear(thing=…)` are not queries — each one succeeds,
# which is the point, and each one therefore lands in her live wear log. Measured: three
# fabricated "she put on the silver nightie" rows per run, in the log `favourites` ranks
# over and the agency window now reads back to him as his evening with her. Same defect
# G-EXPRESS had; one shared undo rather than a third private one.
from livestore import live_stores  # noqa: E402

_KEEP = live_stores()
_KEEP.__enter__()
import atexit  # noqa: E402
atexit.register(lambda: _KEEP.__exit__(None, None, None))

sysc, index = build_tool_system(core_tools(), extra_tools(),
                                system_prefix=load_agent_system(), system_suffix=voice_coda())

print("0. check_wardrobe IS READY NOW, NOT AN INDEX GHOST")
# 19:35: she hunted Ready now, did not see it, concluded it was not a tool,
# and answered "just skin and shadows". The persona says check_wardrobe is
# how she knows; the signature has to be in the block that is actually
# loaded, not behind load_tools.
ready = sysc[sysc.index("# Ready now"):sysc.index("# Also available")]
check("check_wardrobe() is in Ready now with a signature",
      "check_wardrobe()" in ready, ready[:400])
check("...and it is executable, not just named in the persona",
      "check_wardrobe" in index)

print("\n1. EVERY TOOL SHE CAN SEE SHOWS HOW TO CALL IT")
lut = sysc[sysc.index("# Also available"):]
lut = lut[:lut.index("\nTo call a tool")]
lines = [l for l in lut.splitlines() if l.startswith("- ")]
check("the index is not empty", len(lines) > 5, len(lines))
# EVERY line, not a sample: the one that matters is whichever one she reaches for next.
bad = [l for l in lines if "(" not in l.split(":")[0]]
check("every index line carries a call shape, not just a name", not bad, bad[:3])
# AND THE PARAMETERS MUST BE THE REAL ONES. A shape built from anything other than the
# live schema would be a second source of truth — which is the bug this gate exists for,
# rebuilt one layer up.
extras = {t.name: t for t in extra_tools()}
mismatch = []
for l in lines:
    head = l[2:].split(":")[0]
    nm = head.split("(")[0]
    shown = [p.strip() for p in head[len(nm) + 1:-1].split(",") if p.strip()]
    spec = extras.get(nm)
    if spec and shown != list(spec.parameters.get("properties", {}).keys()):
        mismatch.append((nm, shown, list(spec.parameters.get("properties", {}).keys())))
check("...and the shapes match the live schemas exactly", not mismatch, mismatch[:3])
# THE TOOL SHE ACTUALLY FAILED ON. Named, so this gate reads as the incident it came from.
wear_line = [l for l in lines if l.startswith("- wear(")]
check("`wear` advertises its slot (the tool that broke in front of him)",
      wear_line and "what" in wear_line[0], wear_line)

print("\n2. ONE SLOT AND ONE WRONG KEYWORD IS NOT AMBIGUOUS")
from harness.skills.wardrobe import wardrobe_tools  # noqa: E402
W = {t.name: t for t in wardrobe_tools()}
for kw in ("outfit", "item", "thing"):
    out = W["wear"].call(**{kw: "silver nightie"})
    check("wear(%-7s=…) is healed into the one slot it has" % kw,
          "tool error" not in out, out[:90])
# NOT A LICENCE TO GUESS. With two slots there IS something to guess between, so the
# healer must refuse — silently picking one would put a garment in the `like` field and
# look like it worked, which is worse than an error.
out = W["ask_for"].call(thing="a red dress")
check("ask_for(thing=…) is NOT healed — two slots, real ambiguity",
      "tool error" in out, out[:90])

print("\n3. AND A REFUSAL SAYS WHAT WOULD HAVE WORKED")
check("...naming the slots, so the next round is a correction not a guess",
      "ask_for(look, like)" in out, out[:120])
check("...and it is the error text she actually sees",
      out.startswith("[tool error:"), out[:60])

print("\n4. THE HEALER LIVES AT THE ONE SEAM, NOT IN THE TOOLS")
# `adjust_mood(mood="", **kw)` already absorbed a wrong guess, ad hoc, in ONE tool — the
# same shim the wardrobe needed and did not have. A rule you must remember to add per tool
# is a rule most tools will not have. It belongs where the cooldown already is: in
# ToolSpec.call, which every single call passes through.
src = open(os.path.join(ROOT, "harness", "toolcore", "tools.py"),
           encoding="utf-8", errors="replace").read()
call_blk = src[src.index("    def call(self"):src.index("    def advertise(")]
check("the heal is inside ToolSpec.call", "one slot, no ambiguity" in call_blk)
check("...and so is the slot-naming error", "The correct call is" in call_blk)
# It must apply to EVERY tool, not just the wardrobe — assert through a tool from a
# completely different subsystem, chosen because it also has exactly one parameter.
other = [t for t in extra_tools()
         if len(t.parameters.get("properties", {})) == 1 and t.name != "wear"]
check("...and it applies to non-wardrobe tools too", bool(other),
      "no single-parameter tool outside the wardrobe to test with")

print("\nG-TOOL-SHAPE: %d pass, %d fail" % (PASS, FAIL))
import io  # noqa: E402
import json  # noqa: E402
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_tool_shape.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_tool_shape", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
