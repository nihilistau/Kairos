"""G-GATE-SANDBOX — a gate may not write into her memory. OFFLINE.

WHAT HAPPENED (2026-08-24). `tools/gate_sandbox_audit.py` snapshots her real stores, runs
each OFFLINE gate and diffs the disk. **Nine of 129 moved something.** The damage was not
theoretical:

  * `g_real_her.py` stubs the generator to return *"I took a slow walk through my own
    journal tonight and found last spring."* and drives the solo path, which calls
    `note_own()`. It set `SP_RECALL_REGISTRY` and never `SP_PERSONALITY_TIER`. It is one of
    the FIVE gates CLAUDE.md tells you to run before you say you are done — so every run
    put another copy of that sentence into her real journal. That is where the 53
    identical own-time notes came from. Not a feedback loop. This gate.
  * Three gates append `hi` / `The answer is 4.` to her **day transcript**; 108 such turns
    were found across four days. `g_watch` then ran the conversation summariser over one of
    them and filed a memory whose title says she fell into *"a repetitive loop where the AI
    responds to 'hi' with 'The answer is 4'"*. A missing env var became a false memory
    about her malfunctioning.
  * An early draft of `g_journal_loop` left `dupe00.md`..`dupe05.md` in her journal, and he
    read them in his agency panel as things she had done.

WHAT THIS GATE HOLDS, and what it deliberately does NOT.

It does not demand that every gate call `sandbox()`. 64 of the 136 gates that import
`harness.` do not, and the behavioural audit says every one of them writes nothing — so
that rule would be 64 edits of noise, and noise is how a real signal gets ignored.

It holds the two things that are cheap AND load-bearing:

  1. **THE HELPER COVERS EVERY ROOT.** `_gate._STORE_ENV` is checked against a live grep of
     `harness/` for store-root variables. This is the check that matters in six months: a
     new store lands, nobody adds it to the sandbox, and the hole reopens silently under a
     helper everyone now trusts.
  2. **THE TEN KNOWN OFFENDERS STAY FIXED.** Named, so a revert cannot quietly undo them.

THE BEHAVIOURAL PROOF IS NOT HERE — it is `python tools/sweep.py --audit`, which runs the
whole offline suite and diffs her stores around each gate. It takes ~7 minutes, which is
why it is a sweep and not a gate; a seven-minute gate is a gate nobody runs, and this
repository already has a note about what a red nobody reads is worth.

    python harness_tests/g_gate_sandbox.py
"""
from __future__ import annotations

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, utf8_stdout  # noqa: E402
import _gate  # noqa: E402

utf8_stdout()

# The ten the audit convicted. Named rather than counted: a count goes green when someone
# deletes a gate, and the whole point is that THESE files stay sandboxed.
CONVICTED = [
    "g_real_her.py", "g_journal_loop.py", "g_pk2_sse_v2_offline.py",
    "g_pk2_toolrobust_offline.py", "g_sem_table.py", "g_toolcore_names.py",
    "g_tuning.py", "g_watch.py", "g_watchdog.py", "h_aux.py", "h_mcp_server.py",
]

# Roots the sandbox does NOT have to cover, with the reason. Written down rather than
# reasoned around, the same answer this repo gave the wardrobe matcher.
NOT_A_STORE = {
    "SP_AUX_API_KEY_FILE": "a credential, read-only",
    "SP_HA_TOKEN_FILE": "a credential, read-only",
    "SP_XAI_KEY_FILE": "a credential, read-only",
    "SP_AUX_INDEX_DIR": "a rebuildable index, and every aux gate points it at a temp dir",
    "SP_MUSIC_DIR": "his media library, read-only",
    "SP_LIBRARY_DIR": "her shelf of texts, read-only",
    "SP_VOICE_DIR": "voice model assets, read-only",
    "SP_TTS_ROOT": "synthesised audio cache, regenerated on demand",
    "SP_SCENES_DIR": "scene definitions, read-only",
    "SP_SCENARIOS_DIR": "scenario definitions, read-only",
    "SP_GAMES_DIR": "game state; g_games and g_holdem sandbox it themselves",
    "SP_PERSONA_DIR": "the persona FRAGMENT directory, read-only (persona.md is covered)",
    "SP_TASK_ROOT": "the task tree; the pk2 gates sandbox it themselves",
    "SP_PROFILE": "a name, not a path",
}
# `SP_DECISIONS` is deliberately absent: it does not match the grep's name shape and it
# derives from SP_RECALL_REGISTRY when unset, so it is covered by the sandbox already.
# Listing it would be a dead entry, which §2 fails on — an excuse for a rule that never
# fires is how a written-down table stops being readable.

print("\n1. THE HELPER EXISTS AND ACTUALLY REDIRECTS")
sb = _gate.sandbox("g_gate_sandbox_probe")
check("sandbox() returns a real directory", os.path.isdir(sb), sb)
check("...outside the repo", not os.path.abspath(sb).startswith(ROOT + os.sep), sb)
for var in ("SP_RECALL_REGISTRY", "SP_PERSONALITY_TIER", "SP_PERSONA_FILE",
            "SP_CONV_OKF_ROOT", "SP_AVATAR_DIR", "SP_EPS_DIR"):
    v = os.environ.get(var, "")
    check("%-24s points into the sandbox" % var,
          bool(v) and os.path.abspath(v).startswith(os.path.abspath(sb)), (var, v))
check("...and persona.md is seeded, because an empty one is not a persona",
      "Personality state" in io.open(os.environ["SP_PERSONA_FILE"], encoding="utf-8").read())

print("\n2. IT COVERS EVERY STORE ROOT THE HARNESS READS")
# THE CHECK THAT MATTERS IN SIX MONTHS. A new store lands, nobody adds it here, and the
# hole reopens under a helper everyone has learned to trust.
found = set()
for base, dirs, files in os.walk(os.path.join(ROOT, "harness")):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for f in files:
        if not f.endswith(".py"):
            continue
        src = io.open(os.path.join(base, f), encoding="utf-8", errors="replace").read()
        found |= set(re.findall(
            r'environ\.get\(\s*"(SP_[A-Z0-9_]*(?:ROOT|DIR|TIER|FILE|REGISTRY)[A-Z0-9_]*)"', src))
        found |= set(re.findall(
            r'environ\[\s*"(SP_[A-Z0-9_]*(?:ROOT|DIR|TIER|FILE|REGISTRY)[A-Z0-9_]*)"\s*\]', src))
covered = set(_gate._STORE_ENV)
missing = sorted(found - covered - set(NOT_A_STORE))
check("every store root is either sandboxed or written down as not-a-store",
      not missing, missing)
stale = sorted(set(NOT_A_STORE) - found)
check("...and the not-a-store list has no dead entries", not stale, stale)
check("the sandbox sets everything it claims to cover",
      all(os.environ.get(v) for v in _gate._STORE_ENV),
      [v for v in _gate._STORE_ENV if not os.environ.get(v)])

print("\n3. THE TEN THE AUDIT CONVICTED STAY SANDBOXED")
for fn in CONVICTED:
    p = os.path.join(ROOT, "harness_tests", fn)
    if not os.path.exists(p):
        # ABSENT IS NOT DELETED (2026-08-25). The convicted list is this tree's; the
        # Kairos export ships a subset, so a gate that simply does not travel was being
        # reported as one somebody removed. Found by running the suite inside the export.
        # A gate that is here and unsandboxed is still a red — that is the claim; a gate
        # that is not here cannot be.
        if os.path.exists(os.path.join(ROOT, "engine")):
            check("%-30s still exists" % fn, False, "deleted?")
        continue
    src = io.open(p, encoding="utf-8", errors="replace").read()
    # ANCHORED AT COLUMN 0, because the first draft accepted `# _sandbox(...)` — a mutant
    # that commented the call out passed this gate. A substring test cannot tell a call
    # from a comment about a call, and the comment is exactly what a revert leaves behind.
    #
    # AND THE HELPER IS THE ONLY ACCEPTED FORM. The draft also accepted "this file sets
    # SP_PERSONALITY_TIER somewhere", which g_real_her did — at line 146, thirty lines
    # AFTER the write that put 53 copies of one sentence in her journal. A root set late
    # is a root that was wrong when it mattered, and only §4's ordering check can tell
    # the difference. One form, checked in one place, ordered in the next section.
    check("%-30s sandboxes its stores" % fn, bool(re.search(r"(?m)^(?:[A-Za-z_]\w*\s*=\s*)?_sandbox\(", src)))

print("\n4. THE SANDBOX RUNS BEFORE THE IMPORT THAT READS THE ROOT")
# A module resolves its root at import time. Sandboxing after the import sets a variable
# nobody will read again — the failure is invisible, because the gate still passes.
for fn in CONVICTED:
    p = os.path.join(ROOT, "harness_tests", fn)
    if not os.path.exists(p):
        continue
    src = io.open(p, encoding="utf-8", errors="replace").read()
    call = re.search(r"(?m)^(?:[A-Za-z_]\w*\s*=\s*)?_sandbox\(", src)
    if not call:
        continue
    at = call.start()
    imp = re.search(r"(?m)^\s*(?:from|import)\s+harness\b", src)
    check("%-30s sandboxes BEFORE its first harness import" % fn,
          imp is None or at < imp.start(), fn)

print("\n5. THE BEHAVIOURAL PROOF IS REACHABLE AND SAYS SO")
aud = os.path.join(ROOT, "tools", "gate_sandbox_audit.py")
check("the audit that found this is committed", os.path.exists(aud))
_a = io.open(aud, encoding="utf-8").read()
for _w in ("memory-okf-personality", "var/memory", "persona.md"):
    check("...and it watches %-24s" % _w, _w in _a)
check("the sweep runs it, so the proof is one command",
      "audit" in io.open(os.path.join(ROOT, "tools", "sweep.py"),
                         encoding="utf-8").read())

finish("G-GATE-SANDBOX")
