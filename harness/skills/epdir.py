"""epdir.py — where a registry row's episode actually is.

THE EPISODE ROOT MOVED (2026-09-06; found stale 2026-10-19). The operator moved her
episode store from one disk to another because the old one was too small. Registry rows are
append-only and carry an ABSOLUTE `dir`, so 1,287 rows still named the old root, where nothing is
left. The row is never rewritten: the path is resolved at READ, by basename under the
configured root (`SP_EPS_DIR`). The daemon's twin is `recall.rs::resolve_episode_dir`;
the rule is the same on both sides and each side has exactly one.

THE COLD TIER (D2, 2026-10-19). harness/maintenance/eps_cold.py moves long-dead episodes
to `SP_EPS_COLD_DIR` and appends one row per move to `eps-moves.jsonl`, beside the
registry. A resolver learns that an episode went cold from that ledger and from nothing
else. The cold root is configuration, so a store carried to another machine resolves under
that machine's root. An absolute `to` would go stale exactly as the old-root rows did.

An episode whose dir exists nowhere is MISSING. On 2026-10-19 every such row on her
store had `npos=0` — the KV was never minted, so the row already says "no episode" in
the field that owns it. The operator's ruling on any that did have one: lost in testing
and moving, not important. Readers skip them; `census()` counts them once per process.

Imports nothing that can reach the registry: `semindex` uses this, and semindex's first
rule is that it cannot write the registry.
"""
from __future__ import annotations

import json
import logging
import os

_log = logging.getLogger(__name__)

AS_WRITTEN, MOVED, COLD, MISSING = "as-written", "moved", "cold", "missing"


def _norm_root(r: str) -> str:
    return (r or "").strip().replace("\\", "/").rstrip("/")


def configured_root() -> str:
    """`SP_EPS_DIR`, normalised; "" when unset. The one reader of that variable."""
    return _norm_root(os.environ.get("SP_EPS_DIR") or "")


def cold_root() -> str:
    """`SP_EPS_COLD_DIR`, normalised; "" when unset (the cold tier is off). The one reader."""
    return _norm_root(os.environ.get("SP_EPS_COLD_DIR") or "")


def ledger_path() -> str:
    """The move ledger, beside the registry so it travels with it. "" with no registry."""
    reg = os.environ.get("SP_RECALL_REGISTRY") or ""
    return os.path.join(os.path.dirname(reg), "eps-moves.jsonl") if reg else ""


def ep_key(base: str) -> str:
    """How two episode names compare: case-folded where the OS folds case (Windows)."""
    return os.path.normcase(base)


_MOVED = {"stamp": None, "names": frozenset()}


def moved_names() -> frozenset:
    """Every episode the cold tier has recorded as moved, by ep_key. Re-read only when
    the ledger's (mtime, size) changes, so a resolve per row costs one stat."""
    p = ledger_path()
    try:
        st = os.stat(p) if p else None
    except OSError:
        st = None
    stamp = (p, st.st_mtime_ns, st.st_size) if st else (p, None, None)
    if _MOVED["stamp"] != stamp:
        names = set()
        if st:
            with open(p, encoding="utf-8", errors="replace") as f:
                for ln in f:
                    try:
                        row = json.loads(ln)
                    except ValueError:
                        continue
                    if isinstance(row, dict) and row.get("ep"):
                        names.add(ep_key(str(row["ep"])))
        _MOVED["stamp"], _MOVED["names"] = stamp, frozenset(names)
    return _MOVED["names"]


def resolve(d: str, root: str = None, cold: str = None, moved=None):
    """(path, how). AS_WRITTEN (the row's dir exists, or it has none — left as it was),
    MOVED (found as <root>/<basename>), COLD (the ledger names it and it is found as
    <cold>/<basename>) or MISSING (path is None)."""
    if not d or os.path.isdir(d):
        return d, AS_WRITTEN
    root = configured_root() if root is None else _norm_root(root)
    base = os.path.basename(d.replace("\\", "/").rstrip("/"))
    if root and base:
        p = root + "/" + base
        if os.path.isdir(p):
            return p, MOVED
    cold = cold_root() if cold is None else _norm_root(cold)
    if cold and base:
        if ep_key(base) in (moved_names() if moved is None else moved):
            p = cold + "/" + base
            if os.path.isdir(p):
                return p, COLD
    return None, MISSING


_CENSUS = None


def census(rows) -> dict:
    """{as_written, moved, cold, missing, missing_names} over `rows`' dirs. Computed and
    logged ONCE per process — it is a boot fact, and the health poll that surfaces it runs
    every fifteen seconds."""
    global _CENSUS
    if _CENSUS is None:
        c = {AS_WRITTEN: 0, MOVED: 0, COLD: 0, MISSING: 0, "missing_names": []}
        for r in rows:
            d = r.get("dir") or ""
            if not d:
                continue
            _p, how = resolve(d)
            c[how] += 1
            if how == MISSING:
                c["missing_names"].append(os.path.basename(d.replace("\\", "/").rstrip("/")))
        _CENSUS = c
        _log.info("episode dirs: %d as written, %d resolved under SP_EPS_DIR=%r, "
                  "%d in the cold tier under SP_EPS_COLD_DIR=%r, %d missing everywhere (skipped)",
                  c[AS_WRITTEN], c[MOVED], configured_root(), c[COLD], cold_root(), c[MISSING])
    return _CENSUS
