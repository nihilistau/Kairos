"""G-CFG-DERIVE — a config for a follow-on generation is DERIVED from the turn's, never rebuilt.

WHAT THIS COST, 2026-08-01, live and in front of him. He asked her "are you ok?" and got
back token soup:

    **Craking (2) *thought* is not how you's deved, as a laist_lyer...
    `b it/a leicte` @ R way S ->en! Si|tsoe | ...? C-mally elitse...

Classic sampler degeneration. The cause was one line in the kairos CONTINUATION path —
the code that lets her finish a sentence she was cut off mid-way through:

    ccfg = InferenceConfig(max_tokens=120, temperature=cfg.temperature, auto_recall=False)

Constructed FRESH with three fields. So `repetition_penalty` and `eot_bias` came back
None, and harness/skills/sight.py already says in plain words what that does:
"repetition_penalty is NOT optional here. Without it an open-ended [generation]
degenerates." No penalty, temperature 0.6, a 26B MoE — and that is the paste above.

THE POINT IS THE PATTERN, NOT THE FIELD. The comment block above that line is already a
list of things THAT SAME CONSTRUCTOR had forgotten before: `auto_recall` (memories
injected into a severed clause, so she "finished" a sentence about a thunderstorm with
"From the record: oh no, we just track their comings and goings"), then the
control-surface strip (raw `<channel|>` spoken aloud). Now the sampler dials. That is not
three bugs. It is ONE bug three times — a config built BESIDE the real one inherits
nothing and must remember everything forever, including fields that do not exist yet.

So the gate does not check for repetition_penalty. It checks that follow-on configs are
DERIVED, because a derived config cannot have this bug again and a hand-listed one will.

Offline. No GPU, no daemon.
"""
from __future__ import annotations

import dataclasses
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import _src as _srcmod  # noqa: E402

from harness.inference.inference_config import InferenceConfig  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s %s" % (name, detail))


APP = _srcmod.pkg("harness", "server")

print("1. the continuation config is DERIVED, not rebuilt")
# ── ANCHORED ON THE CODE, NOT ON A COMMENT (2026-08-28) ──────────────────────────────
# This found its window with APP.index("DERIVED FROM THE TURN'S CONFIG") — a COMMENT — and
# when that line was reworded to "THE CONFIG IS DERIVED FROM THE TURN'S, NOT BUILT BESIDE
# IT" the gate stopped failing and started RAISING ValueError, on a code path that was
# entirely correct. It went unnoticed because this row's description contains a pipe, which
# shifted its lane cell and dropped it out of the sweep (see gates/index_rows.py). Prose is
# not a fixture: what the gate means is that the continuation config comes from the turn's,
# and `dataclasses.replace(cfg, max_tokens=` is that claim in code.
check("it uses dataclasses.replace on the turn's config, with a continuation's ceiling",
      "dataclasses.replace(cfg, max_tokens=" in APP)
check("...and does NOT construct a fresh InferenceConfig",
      "InferenceConfig(max_tokens=120" not in APP)
check("dataclasses is imported at module level", "\nimport dataclasses" in APP)

print("\n2. what a derived config actually inherits")
# The real turn config as the gateway builds it: penalty and stop-bias both set.
cfg = InferenceConfig(max_tokens=512, temperature=0.6, repetition_penalty=1.3,
                      eot_bias=0.0, byteexact=False)
cc = dataclasses.replace(cfg, max_tokens=120, auto_recall=False)
check("repetition_penalty survives — the field that caused the soup",
      cc.repetition_penalty == 1.3, cc.repetition_penalty)
check("eot_bias survives", cc.eot_bias == 0.0, cc.eot_bias)
check("temperature survives", cc.temperature == 0.6)
check("byteexact survives", cc.byteexact is False)
check("max_tokens IS overridden — a continuation is short", cc.max_tokens == 120)
check("auto_recall IS overridden — a severed clause is not a question",
      cc.auto_recall is False)

print("\n3. THE PROPERTY THAT MATTERS: a new dial is inherited for free")
# The whole argument for replace() over a hand-listed constructor. A field added
# tomorrow must reach the continuation without anyone remembering to add it.
fields = [f.name for f in dataclasses.fields(InferenceConfig)]
overridden = {"max_tokens", "auto_recall"}
missed = [f for f in fields
          if f not in overridden and getattr(cc, f) != getattr(cfg, f)]
check("every field except the two deliberate overrides is carried across",
      not missed, missed)
check("the config has more fields than any constructor call listed",
      len(fields) > 6, len(fields))

print("\n4. sight.py still states why the penalty is not optional")
sight = io.open(os.path.join(ROOT, "harness", "skills", "sight.py"), encoding="utf-8").read()
check("the warning is still written down where it was learned",
      "repetition_penalty is NOT optional" in sight)

print("\n5. no OTHER follow-on config is built beside the turn's")
# Any InferenceConfig(...) inside app.py that copies `temperature=cfg.temperature` is the
# same shape as the bug: it reached for one field of the parent instead of deriving.
suspects = re.findall(r"InferenceConfig\([^)]*temperature=cfg\.temperature[^)]*\)", APP)
check("no constructor cherry-picks a single field off the turn's config",
      not suspects, suspects)

print("\nG-CFG-DERIVE: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_cfg_derive.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_cfg_derive", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
