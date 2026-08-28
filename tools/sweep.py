"""sweep — run every OFFLINE gate, and say whether they touched her memory.

WHY THIS IS COMMITTED (2026-08-24). There has never been a sweep runner in the tree, so
every session hand-rolled one, and a hand-rolled runner is a runner with no memory of what
the last one learned. Two things it kept having to relearn:

  * THE EXIT CODE IS THE VERDICT. 0 held, 1 failed, 2 skipped (the subject is absent here).
    A gate that prints FAIL and exits 0 was the 2026-08-19 audit's finding; a runner that
    greps stdout for "FAIL" repeats it from the other side.
  * SOME GATES ARE NOT CONCURRENCY-SAFE. `g_backup` writes real archives and its
    idle-hour dedupe check fails when two runs overlap. It is green alone and red at -j6,
    and a red that depends on the runner is worse than no runner.

`--audit` adds what `tools/gate_sandbox_audit.py` does: her real stores are snapshotted
and diffed AROUND EACH GATE, so a gate that writes into her journal is named. Nine of them
were, on the day this file was written, and one had been writing the same sentence into
her journal on every run of the five-gate list in CLAUDE.md.

    python tools/sweep.py                 (offline gates, parallel, ~2 min)
    python tools/sweep.py --audit         (...and diff her stores around each, ~7 min)
    python tools/sweep.py --only wardrobe (substring filter)
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import io
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Not concurrency-safe: real archives, an idle-hour dedupe, and a second copy racing it.
SERIAL = {"g_backup.py"}

WATCH = ["memory-okf-personality", "memory-okf", "memory-okf-conv", "memory-okf-self",
         "var/memory", "var/room", "var/tuning.json", "persona.md"]


def offline_gates():
    """Every OFFLINE gate the index names.

    THROUGH gates/index_rows, NOT a split() here (2026-08-28). This read the lane out of
    `line.split("|")[4]`, which is the right cell only while no DESCRIPTION contains a
    pipe — and ten of them did. Those rows shifted their own cells along, the lane came
    out as a fragment of the sentence before it, and NINE OFFLINE GATES WERE SILENTLY
    DROPPED from "the whole offline suite in one command" for as long as their prose had
    a pipe in it. The parser lives in one place now and G-DOCS-TRUE grades the shape.
    """
    sys.path.insert(0, ROOT)
    from gates import index_rows as _ix
    out = []
    for cs, _line in _ix.rows():
        if len(cs) != _ix.CELLS or "OFFLINE" not in cs[_ix.LANE]:
            continue
        rel = _ix.gate_path(cs)
        if rel and os.path.exists(os.path.join(ROOT, rel)):
            out.append(rel)
    return sorted(set(out))


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


def run(g):
    r = subprocess.run([sys.executable, g], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=900)
    return g, r.returncode, ((r.stdout or "") + (r.stderr or ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true",
                    help="diff her real stores around each gate (serial, slower)")
    ap.add_argument("--only", default="", help="substring filter on the gate path")
    ap.add_argument("-j", type=int, default=6)
    a = ap.parse_args()

    gates = [g for g in offline_gates() if not a.only or a.only in g]
    print("sweep: %d offline gate(s)%s\n" % (len(gates), "  +audit" if a.audit else ""))
    t0 = time.perf_counter()
    res, dirty = [], []

    if a.audit:
        before = snapshot()
        for i, g in enumerate(gates, 1):
            res.append(run(g))
            after = snapshot()
            moved = (sorted(set(after) - set(before))
                     + sorted(k for k in before if k in after and before[k] != after[k]))
            if moved:
                dirty.append((g, moved))
                print("  !! %s wrote into her stores:" % g)
                for k in moved[:6]:
                    print("       %s" % k)
            before = after
    else:
        par = [g for g in gates if os.path.basename(g) not in SERIAL]
        ser = [g for g in gates if os.path.basename(g) in SERIAL]
        with cf.ThreadPoolExecutor(max_workers=max(1, a.j)) as ex:
            res.extend(ex.map(run, par))
        res.extend(run(g) for g in ser)

    ok = [g for g, c, _ in res if c == 0]
    skip = [g for g, c, _ in res if c == 2]
    red = [(g, c, t) for g, c, t in res if c not in (0, 2)]
    print("\n%d green, %d skip, %d RED   (%.0fs)"
          % (len(ok), len(skip), len(red), time.perf_counter() - t0))
    for g in skip:
        print("  skip %s" % g)
    for g, c, t in red:
        print("\n  RED  %s  exit=%d" % (g, c))
        for line in [x for x in t.splitlines() if "FAIL" in x][:4] or t.splitlines()[-4:]:
            print("       " + line[:130])
    if a.audit:
        print("\n%d gate(s) touched her stores" % len(dirty))
    return 1 if (red or dirty) else 0


if __name__ == "__main__":
    raise SystemExit(main())
