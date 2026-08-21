#!/usr/bin/env python
"""sem_dash.py — one JSON status document for the SEM stack (docs/SEMANTICS.md).

Scans repo state and emits everything the live dashboard renders: phase status,
gate receipts, fixture presence, registry counts, semindex coverage. READ-ONLY.

Privacy rule: this script emits COUNTS about the live registry, never fact text.
The dashboard must be safe to have open on a screen.

Usage:
    python tools/sem_dash.py --json     # sentinel-wrapped JSON for machine callers
    python tools/sem_dash.py            # pretty-printed
"""
import glob
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "harness_tests", "fixtures", "sem")
RECEIPTS = os.path.join(ROOT, "var", "sem", "receipts")
REGISTRY = os.environ.get("SP_RECALL_REGISTRY") or os.path.join(ROOT, "var", "memory", "registry.jsonl")
SEMINDEX = os.environ.get("SP_SEM_INDEX") or os.path.join(ROOT, "var", "memory", "semindex.jsonl")

SENTINEL_A, SENTINEL_B = "<<<SEMDASH", "SEMDASH>>>"


def _git(*args):
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT,
                                       stderr=subprocess.DEVNULL, timeout=10).decode().strip()
    except Exception:
        return ""


def _jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def registry_stats():
    rows = _jsonl(REGISTRY)
    live = [r for r in rows if not r.get("lifecycle")]
    by = lambda key, rs: sorted(
        {r.get(key) or "?" for r in rs} and
        [[k, sum(1 for r in rs if (r.get(key) or "?") == k)]
         for k in sorted({r.get(key) or "?" for r in rs})]) or []
    return {
        "path_exists": os.path.exists(REGISTRY),
        "total": len(rows), "live": len(live), "retired": len(rows) - len(live),
        "by_class": by("mem_class", live), "by_speaker": by("speaker", live),
        "by_status": by("status", live),
    }


def semindex_stats(reg):
    rows = _jsonl(SEMINDEX)
    models = sorted({r.get("model") or "?" for r in rows})
    live = reg["live"]
    return {
        "exists": os.path.exists(SEMINDEX), "rows": len(rows), "models": models,
        "coverage": (round(min(len(rows), live) / live, 4) if live else None),
    }


def receipts():
    out = {}
    for p in sorted(glob.glob(os.path.join(RECEIPTS, "*.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                out[os.path.splitext(os.path.basename(p))[0]] = json.load(f)
        except Exception as e:
            out[os.path.basename(p)] = {"error": str(e)}
    return out


def fixtures():
    names = ["registry_snapshot.jsonl", "paraphrase.jsonl", "foreign.jsonl",
             "golden-lexical.json", "baseline-receipt.json", "gen_corpus.py"]
    return {n: os.path.exists(os.path.join(FIX, n)) for n in names}


def gates():
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "harness_tests", "g_sem_*.py"))):
        out.append(os.path.basename(p))
    return out


def sem_flag_mapped():
    """Is the Phase 2 RANK knob mapped in serve.py build_env (G-ONEDOOR: unmapped ==
    nonexistent)? S0's mint/index knobs land in Phase 1 and do not count."""
    p = os.path.join(ROOT, "serve.py")
    try:
        with open(p, encoding="utf-8") as f:
            return '"SP_SEM_RANK"' in f.read()   # the mapping KEY, not the comment naming it
    except Exception:
        return False


def _green(rc, name):
    r = rc.get(name)
    return bool(r) and r.get("fail", 1) == 0 and r.get("pass", 0) > 0


def phases(fx, rc, sem_idx, flag_mapped):
    p0 = all(fx[n] for n in ("registry_snapshot.jsonl", "paraphrase.jsonl",
                             "foreign.jsonl", "baseline-receipt.json")) and _green(rc, "g_sem_conserve")
    p1 = sem_idx["exists"] and (sem_idx["coverage"] or 0) >= 1.0 and _green(rc, "g_sem_index")
    # Phase 2 completes only when the SHIP CONDITION is met: gates green AND the
    # scoreboard receipt says it beats the baseline (ships: true). Machinery landing
    # is "in-progress"; a negative receipt keeps it there, honestly.
    p2 = (flag_mapped and _green(rc, "g_sem_rank") and _green(rc, "g_sem_claim")
          and rc.get("sem_rank_score", {}).get("ships") is True)
    p3 = _green(rc, "g_sem_dominate") and _green(rc, "g_sem_whistle")
    p4 = _green(rc, "g_sem_stable")
    started = {
        0: any(fx.values()) or "g_sem_conserve" in rc,
        1: sem_idx["exists"], 2: flag_mapped or "g_sem_rank" in rc,
        3: "g_sem_dominate" in rc, 4: "g_sem_stable" in rc,
    }
    done = {0: p0, 1: p1, 2: p2, 3: p3, 4: p4}
    names = {0: "Phase 0 — prerequisites, corpus, baseline receipt, G-SEM-CONSERVE",
             1: "Phase 1 — S0 sidecar index + async mint",
             2: "Phase 2 — S1 semantic rank behind SP_SEM_RANK",
             3: "Phase 3 — S2 dominance proposals + whistle",
             4: "Phase 4 — S3 verdict table across surfaces"}
    return [{"phase": i, "name": names[i],
             "status": "complete" if done[i] else ("in-progress" if started[i] else "pending")}
            for i in range(5)]


def build():
    reg = registry_stats()
    fx = fixtures()
    rc = receipts()
    idx = semindex_stats(reg)
    flag = sem_flag_mapped()
    return {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "commit": _git("rev-parse", "--short", "HEAD"),
        "branch": _git("branch", "--show-current"),
        "dirty": bool(_git("status", "--porcelain")),
        "registry": reg, "semindex": idx, "fixtures": fx,
        "gates_present": gates(), "receipts": rc,
        "sem_flag_mapped_in_serve": flag,
        "phases": phases(fx, rc, idx, flag),
    }


if __name__ == "__main__":
    doc = build()
    if "--json" in sys.argv:
        print(SENTINEL_A + json.dumps(doc, separators=(",", ":")) + SENTINEL_B)
    else:
        print(json.dumps(doc, indent=2))
