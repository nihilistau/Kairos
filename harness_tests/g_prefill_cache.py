"""G-PREFILL-CACHE — every turn must be a STRICT EXTENSION of the last one.

THE OPERATOR'S QUESTION: "why is it fast at first and painfully slow 6000 tokens later?"

The answer was not decay. Decode never changed — it sat at 11-21 tok/s from the first turn
to the last. What changed was the COST OF A CACHE MISS, and the misses were there all along:

    TURN-PHASE: prefill   903 ms                  <- an ordinary turn (cache hit)
    TURN-PHASE: prefill 1676 tok in 111531 ms     <- a kairos continuation
    TURN-PHASE: prefill 2628 tok in 188452 ms     <- the ordinary turn AFTER it

Two full prefills, every time she continued a cut-off thought. A miss costs O(conversation
length) — the same bug that costs 20 seconds at turn five costs six minutes at turn sixty.
Nothing degraded. The bill just grew.

THE CAUSE, in one argument: `agent_chat_stream(..., tools=[])`.

    tools is None -> the CACHED system prompt: persona + ~1.5k tokens of tool preamble.
                     Every ordinary turn uses this.
    tools == []   -> "no tools", which REBUILDS the system prompt without that preamble.

`[]` is not None. It reads like "offer her no tools this turn" and it means "hand the model
a different token 0" — and agent.py's own comment, three lines above where it did this,
already named the consequence: "a per-turn system-prompt rewrite diverges the persist-KV
cache at token 0". The kairos continuation and the repeat-guard reroll both passed `[]`.
They also left the RESIDENT cache holding the no-tools prefix, so the next ordinary turn
diverged from that and re-prefilled as well.

This gate is a lint, deliberately. The live symptom takes a long conversation and several
minutes to reproduce, which is exactly the kind of bug that survives — it is invisible
until the machine is already unusable. The seam is one keystroke wide and it is cheap to
watch.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def main() -> int:
    print("G-PREFILL-CACHE - every turn is a strict extension of the last.\n")

    # ── 1. NOBODY passes tools=[] into a chat path ──────────────────────────────
    offenders = []
    for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "harness")):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dirpath, fn)
            src = open(p, encoding="utf-8", errors="replace").read()
            for m in re.finditer(r"agent_chat(?:_stream)?\s*\((?:[^()]|\([^()]*\))*?"
                                 r"tools\s*=\s*\[\s*\]", src, re.S):
                line = src[:m.start()].count("\n") + 1
                offenders.append(f"{os.path.relpath(p, ROOT)}:{line}")
    check("no chat path passes tools=[] (it rewrites the system prompt = full re-prefill)",
          not offenders, f"{offenders}" if offenders else
          "the continuation and the reroll both did, and it cost two full prefills each")

    # ── 2. the system prompt is IDENTICAL for a normal turn and a continuation ───
    # This is the invariant that actually matters: same token 0 => strict extension =>
    # the persist-KV cache reuses everything but the new suffix.
    os.environ.setdefault("SP_RECALL_REGISTRY",
                          os.path.join(ROOT, "var", "memory", "registry.jsonl"))
    os.environ.setdefault("SP_PERSONALITY", "1")
    from harness.agent import core_tools, extra_tools, load_agent_system
    from harness.toolcore.tools import build_tool_system

    prefix = load_agent_system()
    normal, _ = build_tool_system(core_tools(), extra_tools(), system_prefix=prefix)
    notools, _ = build_tool_system([], [], system_prefix=prefix)

    check("a no-tools system prompt really IS a different prompt (this is the trap)",
          normal != notools,
          f"{len(normal)} chars with tools vs {len(notools)} without — "
          f"{len(normal) - len(notools)} chars of divergence, from token 0")

    # where it diverges — if it were only at the END, the cache would still hold
    i = next((i for i, (a, b) in enumerate(zip(normal, notools)) if a != b),
             min(len(normal), len(notools)))
    check("...and it diverges EARLY, so no prefix survives",
          i < len(normal) * 0.9,
          f"first difference at char {i} of {len(normal)} — everything after it re-prefills")

    total = len(PASS) + len(FAIL)
    print(f"\nG-PREFILL-CACHE: {'PASS' if not FAIL else 'FAIL'} ({len(PASS)}/{total})")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
