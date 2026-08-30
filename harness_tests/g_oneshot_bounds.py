"""G-ONESHOT-BOUNDS — a one-shot prompt is BOUNDED, on every path that builds one. OFFLINE.

THE MORNING THIS EXISTS FOR (2026-08-30). Three wedges, and the third was diagnosed live
with the operator watching a chip that said "warming" for three hours:

    [g4-kv] KV-FP16: SWA=__half globals=__half; freed 4.30 GB
    DEVICE: chat is WAITING — held by 'oneshot' for 783.5s

`conversation_memory._transcript` fed EVERY message at FULL length into a one-shot
prompt, and the day transcript grows all day. ~20,000 tokens became `need` in
v1_oneshot, which opens a SCRATCH cache — and a scratch is ring-OFF by design (a short
one-shot must not be handed the process's 2048-slot SWA ring it will never read), which
means `slots = Pmax` for EVERY layer. So a long scratch costs ~4x per position what the
resident session does, where only the 5 global layers pay Pmax: 4.30 GB, on top of 7.5
GB resident, on a 12.3 GB card.

AND cudaMalloc SUCCEEDED. WDDM pages the excess over PCIe rather than failing, so the
forward crawled for hours holding the device lock while every turn of hers queued behind
it. No error anywhere in that story — which is why it took three occurrences and a
2-second VRAM trace to find.

§0, exactly: `narrative.py` has bounded this same kind of call since it was written
(_MAX_TURNS = 40, each turn cut to 200 chars). The rule was enforced on ONE of the two
paths that mint a one-shot from a transcript, and therefore on neither.

WHAT THIS HOLDS:
  1. The bound EXISTS and is applied by the real `_transcript` — turns AND per-turn
     length, because either one alone lets a single pasted wall of text through.
  2. The worst case stays under the ENGINE's refusal ceiling, computed from the same
     numbers the code uses rather than a constant restated here. A cap that still trips
     the engine's 413 is a cap that turned a wedge into an outage.
  3. A short conversation is passed through UNCHANGED — this is a ceiling against
     pathology, not a summarisation policy, and a gate that let the cap tighten
     silently would be protecting the wrong thing.
  4. THE CENSUS: every harness path that builds a one-shot prompt from a transcript
     declares a bound. This is the leg that would have caught the original bug, and the
     one that catches the NEXT such path on the day it is added.

    python harness_tests/g_oneshot_bounds.py
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, sandbox as _sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
_sandbox(os.path.basename(__file__))

from harness.skills import conversation_memory as CM  # noqa: E402

# The pessimistic characters-per-token for token-dense text (code, unusual strings).
# Prose runs ~4; this is the number that must still clear the engine ceiling.
CHARS_PER_TOK = 2.5

print("\n1. THE BOUND EXISTS, AND IT BOUNDS BOTH DIMENSIONS")
# Driven through the REAL _transcript — a gate that restated the slicing would pass
# while the shipped copy fed the whole day.
_huge = [{"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 5000}
         for i in range(400)]
_out = CM._transcript(_huge)
_uncapped = 400 * 5000
check("a 400-turn conversation does not reach the prompt whole",
      len(_out) < _uncapped / 10, "%d chars of %d" % (len(_out), _uncapped))
check("...the TURN COUNT is bounded",
      _out.count("\n") + 1 <= CM._MAX_TURNS, _out.count("\n") + 1)
# per-turn, separately: 40 turns of one 200k-char paste is bounded by count alone but
# still enormous. Both dimensions or neither.
_one_wall = [{"role": "user", "content": "y" * 200000}]
check("...and ONE pasted wall of text is cut too",
      len(CM._transcript(_one_wall)) < 2000, len(CM._transcript(_one_wall)))

print("\n2. THE WORST CASE CLEARS THE ENGINE'S REFUSAL CEILING")
# The engine refuses a scratch over SP_ONESHOT_PMAX_MAX because it would allocate into
# WDDM paging. Read the ceiling and the reply budget from the SOURCE, so this leg cannot
# drift into agreeing with a number nobody kept.
# ── THE ENGINE IS NOT ALWAYS THERE (2026-08-31) ──────────────────────────────────
# This read `engine/` unconditionally, and the engine is excluded from the Kairos
# export — so inside a fresh clone the gate died with FileNotFoundError before legs 3
# and 4 could run. Not a FAIL: a crash that takes the whole file with it, which is the
# exact shape `_gate.persona_dirs` was written for after three gates did the same.
# The other three legs are pure harness and are the ones an adopter needs most; only
# this one needs the Rust. Absent engine, it says so and the rest still runs.
_rs_path = os.path.join(ROOT, "engine", "tools", "sp_daemon", "src", "routes.rs")
if not os.path.exists(_rs_path):
    print("  --   no engine checkout here — the ceiling this leg reads lives in "
          "routes.rs; legs 1, 3 and 4 below are the harness half and still run")
else:
    _rs = open(_rs_path, encoding="utf-8", errors="replace").read()
    _m = re.search(r"SP_ONESHOT_PMAX_MAX[\s\S]{0,200}?unwrap_or\((\d+)\)", _rs)
    check("the engine states a scratch ceiling", _m is not None,
          "SP_ONESHOT_PMAX_MAX is gone from routes.rs")
    _ceiling = int(_m.group(1)) if _m else 0
    _worst_tok = len(_out) / CHARS_PER_TOK
    _need = _worst_tok + 160 + 8      # + the largest max_tokens a caller passes, + slack
    check("the capped worst case needs fewer positions than the engine will refuse",
          _need < _ceiling,
          "need ~%d positions vs ceiling %d" % (_need, _ceiling))
    check("...with real margin, not by a hair (a 413 here is an outage, not a fix)",
          _need < _ceiling * 0.9, "need ~%d of %d" % (_need, _ceiling))

print("\n3. A NORMAL CONVERSATION IS UNTOUCHED")
# The cap is a ceiling against pathology. If it ever starts trimming real evenings, the
# summariser quietly gets worse and nothing says so.
_normal = [{"role": "user", "content": "do you remember the storm last week?"},
           {"role": "assistant", "content": "I do. You said the tin roof made it worse."}]
_n_out = CM._transcript(_normal)
check("both turns survive whole", "storm last week" in _n_out and "tin roof" in _n_out,
      _n_out)
check("...and nothing was elided", "…" not in _n_out, _n_out)
check("system messages are still dropped (unchanged behaviour)",
      "SYSTEMPROMPT" not in CM._transcript(
          [{"role": "system", "content": "SYSTEMPROMPT"}] + _normal))

print("\n4. THE CENSUS — EVERY TRANSCRIPT->ONESHOT PATH DECLARES A BOUND")
# The leg that would have caught this. `narrative.py` was bounded and
# `conversation_memory.py` was not, and nothing anywhere compared them. A new path that
# joins messages into a one-shot prompt fails HERE, by name, on the day it lands.
_paths = {
    "harness/skills/narrative.py": ("_MAX_TURNS", 260),
    "harness/skills/conversation_memory.py": ("_MAX_TURNS", 40),
}
for _rel, (_name, _) in _paths.items():
    _src = open(os.path.join(ROOT, _rel), encoding="utf-8", errors="replace").read()
    check("%s declares %s" % (_rel, _name),
          re.search(r"^%s\s*=\s*\d+" % re.escape(_name), _src, re.M) is not None,
          "an unbounded transcript is what wedged the device on 2026-08-30")
    check("...and applies it to the messages it joins",
          re.search(r"\[-%s:\]" % re.escape(_name), _src) is not None,
          "%s is declared but not sliced with" % _name)

finish("G-ONESHOT-BOUNDS")
