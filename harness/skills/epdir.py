"""epdir.py — where a registry row's episode actually is.

THE EPISODE ROOT MOVED (2026-09-06; found stale 2026-10-19). The operator moved her
episode store from F:/kairos-eps to C:/kairos-eps because F: is a 27 GB drive. Registry rows are
append-only and carry an ABSOLUTE `dir`, so 1,287 rows still named F:, where nothing is
left. The row is never rewritten: the path is resolved at READ, by basename under the
configured root (`SP_EPS_DIR`). The daemon's twin is `recall.rs::resolve_episode_dir`;
the rule is the same on both sides and each side has exactly one.

An episode whose dir exists nowhere is MISSING. On 2026-10-19 every such row on her
store had `npos=0` — the KV was never minted, so the row already says "no episode" in
the field that owns it. The operator's ruling on any that did have one: lost in testing
and moving, not important. Readers skip them; `census()` counts them once per process.

Imports nothing that can reach the registry: `semindex` uses this, and semindex's first
rule is that it cannot write the registry.
"""
from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)

AS_WRITTEN, MOVED, MISSING = "as-written", "moved", "missing"


def configured_root() -> str:
    """`SP_EPS_DIR`, normalised; "" when unset. The one reader of that variable."""
    return (os.environ.get("SP_EPS_DIR") or "").strip().replace("\\", "/").rstrip("/")


def resolve(d: str, root: str = None):
    """(path, how). `how` is AS_WRITTEN (the row's dir exists, or it has none — left as
    it was), MOVED (found as <root>/<basename>) or MISSING (path is None)."""
    if not d or os.path.isdir(d):
        return d, AS_WRITTEN
    root = configured_root() if root is None else root.replace("\\", "/").rstrip("/")
    base = os.path.basename(d.replace("\\", "/").rstrip("/"))
    if root and base:
        moved = root + "/" + base
        if os.path.isdir(moved):
            return moved, MOVED
    return None, MISSING


_CENSUS = None


def census(rows) -> dict:
    """{as_written, moved, missing, missing_names} over `rows`' dirs. Computed and logged
    ONCE per process — it is a boot fact, and the health poll that surfaces it runs every
    fifteen seconds."""
    global _CENSUS
    if _CENSUS is None:
        c = {AS_WRITTEN: 0, MOVED: 0, MISSING: 0, "missing_names": []}
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
                  "%d missing everywhere (skipped)",
                  c[AS_WRITTEN], c[MOVED], configured_root(), c[MISSING])
    return _CENSUS
