"""sweep — run every OFFLINE gate, and say whether they touched her memory.

WHY THIS IS COMMITTED (2026-08-24). There has never been a sweep runner in the tree, so
every session hand-rolled one, and a hand-rolled runner is a runner with no memory of what
the last one learned. Two things it kept having to relearn:

  * THE EXIT CODE IS THE VERDICT. 0 held, 1 failed, 2 skipped (the subject is absent here).
    A gate that prints FAIL and exits 0 was the 2026-08-19 audit's finding; a runner that
    greps stdout for "FAIL" repeats it from the other side.
  * SOME GATES WERE NOT CONCURRENCY-SAFE. `g_backup` backed up her REAL tree, and its
    idle-hour dedupe check failed whenever anything wrote between two runs. Running it
    serially hid the other writer (another gate) but never the one that mattered — her own
    stack — so on 2026-09-26 it moved to a sandbox and left the serial list. The mechanism
    stays for the next gate that needs it; a red that depends on the runner is worse than
    no runner.

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

# Gates that must not run beside the others. Empty since g_backup went hermetic (2026-09-26).
SERIAL: set = set()

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
    # ── `-u`, SO A GATE THAT DIES STILL SAYS WHAT IT GOT TO (2026-09-11) ─────────────
    # Captured stdout is block-buffered, so a gate killed by a signal loses everything it
    # printed. In CI a gate segfaulted (exit=-11) and the only surviving lines were the
    # LOGGING ones — logging goes to stderr and is not held — so the report showed four
    # INFO lines from the middle of the run and no verdict, and there was no way to tell
    # whether the gate had finished its work and died on the way out or fallen over in the
    # middle of it. Those are completely different bugs.
    #
    # Unbuffered costs nothing here (the child's output goes to a pipe either way) and it
    # is the difference between a signal number and a location. Applies to every gate, not
    # only the crashing one, because the next crash will be somewhere else.
    r = subprocess.run([sys.executable, "-u", g], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=900)
    return g, r.returncode, ((r.stdout or "") + (r.stderr or ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true",
                    help="diff her real stores around each gate (serial, slower)")
    ap.add_argument("--only", default="", help="substring filter on the gate path")
    # ── PARALLELISM COMES FROM THE MACHINE, NOT FROM A CONSTANT (2026-09-11) ─────────
    # This was a flat 6 on every box. A number chosen for the operator's sixteen cores is
    # the same number on a runner with four, which is what a hosted one actually reports
    # (measured, not assumed — the first version of this comment guessed two).
    #
    # Capped at 6 rather than uncapped because these are gates, not a build: several drive
    # real HTTP servers and temp stores, and the cap is what the operator's box has been
    # running all along. `-j` still overrides for anyone who wants to push it.
    #
    # THIS DID NOT FIX THE CI FLAKE, AND THE COMMENT THAT SAID IT WOULD IS GONE. It was
    # written as a contention story — one job per run going red on a different gate, twice
    # with SIGSEGV, "red in the parallel sweep but green alone". Then CI ran the suite at
    # `-j 1` and a gate segfaulted anyway, with nothing else running. No contention theory
    # survives that. The change is kept because deriving from the machine is right on its
    # own terms; the explanation it shipped with was wrong and is not left standing.
    # Where the evidence actually points is in CHANGELOG.md for 2026-09-11.
    _def_j = max(1, min(6, os.cpu_count() or 2))
    ap.add_argument("-j", type=int, default=_def_j,
                    help="parallel gates (default: min(6, cpu_count) = %d here)" % _def_j)
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
