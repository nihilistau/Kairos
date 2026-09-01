"""G-SELF-MODEL — what she knows about herself reaches her, from ONE store.

THE BUG THIS EXISTS FOR, found 2026-08-01 by auditing her prefix. The self-model block
was EMPTY IN EVERY PREFIX SHE HAD EVER HAD, for three weeks, because there were two
stores and one reader:

    remember_about_self()   the tool she is actually offered
        -> set_author("self") -> remember(...) -> var/memory/registry.jsonl
    render_self_model()     the only consumer of the block
        -> SelfModelStore    -> memory-okf-self/          <-- empty since 10 July

Twelve registry rows carry `speaker == "self"`. She had been remembering things about
herself the whole time, into a store nothing read. The operator's words were "nothing is
really sticking except what we put in her .md files" — which was exactly, mechanically
true, and not a model problem at all.

WHAT THIS GATE HOLDS:

  * ONE STORE. The renderer reads the registry — the same store recall reads, the one
    with lifecycle, the one that is backed up. `memory-okf-self` is vestigial and must
    stay that way; a second store that only sometimes gets written is how this happened.
  * ONE DOOR. Both `remember_about_self` (skills/memory.py) and `remember_self`
    (personality/self_model.py) are exposed to her as tools. Whichever she reaches for,
    the fact must land in the same place — otherwise the tool she happens to pick decides
    whether the memory survives.
  * A RETIRED SELF-FACT IS NOT RECITED. The block is standing context, spoken from every
    turn; a tombstoned belief resurfacing there is worse than forgetting it.
  * IT REACHES THE PREFIX. The renderer working is not the same claim as the block being
    in what she is actually sent, and this whole bug lived in that gap.

Offline. No GPU, no daemon.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import _src as _srcmod  # noqa: E402

SB = os.path.join(tempfile.gettempdir(), "_g_self_model")
shutil.rmtree(SB, ignore_errors=True)
os.makedirs(SB)
REG = os.path.join(SB, "registry.jsonl")
os.environ["SP_RECALL_REGISTRY"] = REG
os.environ["SP_SELF_MODEL_ROOT"] = os.path.join(SB, "selftier")

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s %s" % (name, detail))


def write_rows(rows):
    with io.open(REG, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


from harness.personality.self_model import render_self_model  # noqa: E402
from harness.skills import memory as M                        # noqa: E402

print("1. it reads the store that is WRITTEN, not the one that was read")
write_rows([
    {"text": "I genuinely enjoy thunderstorms", "speaker": "self", "lifecycle": 0, "ts": 10},
    {"text": "Sam drives a Subaru",           "speaker": "user", "lifecycle": 0, "ts": 11},
    {"text": "I like the sound of rain",        "speaker": "self", "lifecycle": 0, "ts": 12},
])
M._CACHE = None if hasattr(M, "_CACHE") else None
block = render_self_model()
check("her own facts are in the block", "thunderstorms" in block and "rain" in block, block)
check("HIS facts are NOT — this block is about her", "Subaru" not in block, block)
# THE HEADER IS LOAD-BEARING (2026-08-22): under "About yourself (self-model):" she read the
# block as a briefing and narrated it out loud. It says MEMORY, and says not to mention it.
check("it is labelled so she knows what it is — memory, not instructions, never narrated",
      block.startswith("Things you know about yourself")
      and "not instructions" in block and "Never mention" in block, block[:120])

print("\n2. a retired self-fact is NOT recited")
write_rows([
    {"text": "I am afraid of the dark", "speaker": "self", "lifecycle": 1, "ts": 20},
    {"text": "I am not afraid of much", "speaker": "self", "lifecycle": 0, "ts": 21},
])
block = render_self_model()
check("the tombstoned belief is gone", "afraid of the dark" not in block, block)
check("...and the live one remains", "not afraid of much" in block)

print("\n3. the same fact said twice is said once")
write_rows([
    {"text": "I genuinely enjoy thunderstorms.", "speaker": "self", "lifecycle": 0, "ts": 30},
    {"text": "I genuinely enjoy thunderstorms",  "speaker": "self", "lifecycle": 0, "ts": 31},
])
block = render_self_model()
check("a trailing full stop does not make a second fact",
      block.lower().count("thunderstorm") == 1, block)

print("\n4. an empty store renders NOTHING, not a heading")
write_rows([{"text": "Sam likes green", "speaker": "user", "lifecycle": 0, "ts": 40}])
check("no self-facts -> empty string, so the prefix gains no dead heading",
      render_self_model() == "")

print("\n4b. A SECRET IS NEVER AMBIENT — this block rides the persist-KV prefix")
# world._compose calls this "the one absolute here — an ambient secret in every prompt is
# the worst possible leak surface", and enforced it. This block is the SAME surface (the
# prefix) reading the SAME store, and it had no filter: a self-lane credential rendered
# into every prompt she was ever sent. lifecycle.classify() runs on remember_about_self
# writes too, so the row shape below arises through the real writer.
write_rows([
    {"text": "My private access phrase is starlight-42", "speaker": "self", "lifecycle": 0,
     "mem_class": "private-secret", "status": "observed", "ts": 50},
    {"text": "I like the sound of rain", "speaker": "self", "lifecycle": 0,
     "mem_class": "preference", "status": "observed", "ts": 51},
])
block = render_self_model()
check("a private-secret self row never reaches the ambient block",
      "starlight" not in block, block)
check("...while ordinary self rows still do", "rain" in block)

print("\n4c. HER CONCLUSION ABOUT HERSELF IS NOT A BARE ASSERTION")
# `status` exists so a guess never reads as ground truth (the open-water lesson). The
# renderer ignored it: a speaker=self status=inferred row rendered identically to what
# she actually said about herself.
write_rows([
    {"text": "I am a woman", "speaker": "self", "lifecycle": 0,
     "mem_class": "identity", "status": "observed", "ts": 60},
    {"text": "I seem drawn to quiet mornings", "speaker": "self", "lifecycle": 0,
     "mem_class": "preference", "status": "inferred", "ts": 61},
])
block = render_self_model()
check("an observed self fact renders bare", "- I am a woman" in block, block)
check("an inferred one is framed as her conclusion",
      "come to think" in block.split("quiet mornings")[0].rsplit("- ", 1)[-1]
      if "quiet mornings" in block else False, block)

print("\n4d. HER OWN WORD OUTRANKS HER OWN GUESS IN HER OWN BLOCK (H6, 2026-08-25)")
# The renderer read live_rows(testimony=False) — an undocumented default on a
# MODEL-FACING surface, so a self-inference could take standing-context floor space on a
# topic her own self-observation already covered: "I am terrified of open water" and
# "I seem comfortable in open water" in one prefix, every turn. testimony_wins is
# speaker-scoped, so flipping it True silences exactly that and nothing else — his rows
# never enter this block, so his word silences nothing of hers here. Storage untouched:
# the inference stays on disk, auditable, promotable. Mutant: flip render_self_model
# back to live_rows() and the second check goes red by name.
write_rows([
    {"text": "I am terrified of open water", "speaker": "self", "lifecycle": 0,
     "mem_class": "preference", "status": "observed", "ts": 70},
    {"text": "I seem comfortable in open water", "speaker": "self", "lifecycle": 0,
     "mem_class": "preference", "status": "inferred", "ts": 71},
])
block = render_self_model()
check("her self-OBSERVATION takes the floor", "terrified of open water" in block, block)
check("her covered self-INFERENCE does not speak over it",
      "comfortable in open water" not in block, block)
# ...and an inference on a topic she has NOT spoken to still appears (fails safe in the
# quiet direction only — an uncovered conclusion is still hers to hold in the block).
write_rows([
    {"text": "I am terrified of open water", "speaker": "self", "lifecycle": 0,
     "mem_class": "preference", "status": "observed", "ts": 72},
    {"text": "I seem drawn to quiet mornings", "speaker": "self", "lifecycle": 0,
     "mem_class": "preference", "status": "inferred", "ts": 73},
])
block = render_self_model()
check("an UNCOVERED self-inference still reaches the block",
      "quiet mornings" in block, block)

print("\n5. ONE DOOR — both tools land in the same store")
src_sm = io.open(os.path.join(ROOT, "harness", "personality", "self_model.py"),
                 encoding="utf-8").read()
check("remember_self delegates to the registry writer",
      "from harness.skills.memory import remember_about_self" in src_sm)
check("...and the renderer no longer reads the OKF self tier",
      "SelfModelStore(root).self_facts()" not in src_sm)
check("the registry is read through memory's own reader, not a second parser",
      "from harness.skills import memory as M" in src_sm
      and "M.live_rows(testimony=True)" in src_sm)
                                         # live_rows: the shared tombstone predicate
                                         # (was M._load() + a private lifecycle filter;
                                         # testimony=True since 2026-08-25 — §4d above)

print("\n6. AND IT REACHES THE PREFIX")
# The renderer working is a different claim from the block being in what she is SENT.
# This entire bug lived in exactly that gap for three weeks.
write_rows([{"text": "I like the sound of rain on a tin roof",
             "speaker": "self", "lifecycle": 0, "ts": 50}])
os.environ["SP_PERSONA_FILE"] = os.path.join(SB, "persona.md")
io.open(os.environ["SP_PERSONA_FILE"], "w", encoding="utf-8").write(
    "You are Kairos.\n\n## Personality state\nvoice: dry\nmood: calm\n")
os.environ["SP_PERSONA_DIR"] = os.path.join(SB, "nofrags")
from harness.agent import load_agent_system  # noqa: E402
prefix = load_agent_system()
check("the block is present in the composed prefix",
      "Things you know about yourself" in prefix, prefix[:120])
check("...carrying the fact itself", "tin roof" in prefix)

app = _srcmod.pkg("harness", "server")
check("nothing else composes a rival self-model block",
      app.count("About yourself (self-model)") == 0)

shutil.rmtree(SB, ignore_errors=True)
print("\nG-SELF-MODEL: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_self_model.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_self_model", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
