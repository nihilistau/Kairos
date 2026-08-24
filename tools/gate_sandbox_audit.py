"""gate_sandbox_audit — does any gate write into HER stores?

WHY (2026-08-24). `memory-okf-personality/full/` held `dupe00.md` .. `dupe05.md` and one
note reading "I sat with the rain for a while and did not think about much." Those are
G-JOURNAL-LOOP's fixtures. An early draft of that gate ran before it set
`SP_PERSONALITY_TIER`, so seven test rows landed in her real journal and showed up in his
agency panel as things she had done. He read them as hers, which they were not.

A gate that can write to her store is a gate that can rewrite her. This runs each one and
DIFFS HER REAL STORES around it — filenames and bytes, not counts — and names the gate
that moved anything. No gate is trusted to sandbox itself; the disk is the witness.

    python tools/gate_sandbox_audit.py                 (every OFFLINE gate)
    python tools/gate_sandbox_audit.py g_journal_loop  (just these)
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# HER STORES. Everything a gate must never touch. `var/memory` holds the registry, the
# transcripts and the speech log; the okf tiers hold her journal, her self-model and the
# conversation archive.
WATCH = ["memory-okf-personality", "memory-okf", "memory-okf-conv", "memory-okf-self",
         "var/memory", "var/room", "var/tuning.json", "persona.md"]


def snapshot() -> dict:
    out = {}
    for rel in WATCH:
        p = os.path.join(ROOT, rel)
        if os.path.isfile(p):
            out[rel] = hashlib.md5(io.open(p, "rb").read()).hexdigest()
            continue
        for base, _d, files in os.walk(p):
            for f in files:
                fp = os.path.join(base, f)
                try:
                    out[os.path.relpath(fp, ROOT)] = "%d" % os.path.getsize(fp)
                except OSError:
                    pass
    return out


def offline_gates() -> list:
    idx = io.open(os.path.join(ROOT, "gates", "GATE-INDEX.md"), encoding="utf-8").read()
    out = []
    for line in idx.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 6 or "OFFLINE" not in cells[4]:
            continue
        m = re.search(r"`(harness_tests/[a-z0-9_]+\.py)`", cells[2])
        if m and os.path.exists(os.path.join(ROOT, m.group(1))):
            out.append(m.group(1))
    return sorted(set(out))


def main() -> int:
    want = sys.argv[1:]
    gates = [g for g in offline_gates()
             if not want or any(w.replace(".py", "") in g for w in want)]
    print("auditing %d gate(s) against %d watched paths\n" % (len(gates), len(WATCH)))
    dirty = []
    before = snapshot()
    for i, g in enumerate(gates, 1):
        subprocess.run([sys.executable, g], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=900)
        after = snapshot()
        added = sorted(set(after) - set(before))
        changed = sorted(k for k in before if k in after and before[k] != after[k])
        gone = sorted(set(before) - set(after))
        if added or changed or gone:
            dirty.append((g, added, changed, gone))
            print("  [%3d/%d] !! %s" % (i, len(gates), g))
            for k in (added + changed + gone)[:6]:
                print("            %s" % k)
        before = after
    print("\n%d of %d gates touched her stores" % (len(dirty), len(gates)))
    for g, a, c, d in dirty:
        print("  %s  +%d ~%d -%d" % (g, len(a), len(c), len(d)))
    return 1 if dirty else 0


if __name__ == "__main__":
    raise SystemExit(main())
