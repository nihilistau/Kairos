"""health.py — registry hygiene: the ONE computation behind the report and the verdict.

`_registry_health()` returns `(stats, status)` and both the human report (`verify_registry`,
a model-callable tool) and the machine verdict (`registry_status`, the operator panel) are
projections of it — Tier 2 in `docs/INVARIANT-ROADMAP.md`. Before that it was two
computations, and the hygiene decider disagreed with the report it was printed beside.

Cached by FILE IDENTITY `(mtime_ns, size)`, not by mtime: an mtime-keyed cache in the
semindex once served a dead vector, and the scan is O(n²) over live rows while the panel
polls every 15 s.

`compact_registry()` writes, so it takes the registry lock through `_store` — same module
rule as everywhere else in this package.

Extracted from `memory.py` on 2026-09-02, byte-identical.
"""
from __future__ import annotations

import json
import logging
import os

from harness.skills.memory import store as _store
# `_registry_health` reports the capture backlog beside the row counts.
# FOUND BY G-SRC-TRAP §6, not by reading: the extraction stranded this name and the
# static resolver named the file and the name before anything ran.
from harness.skills.memory.mint import capture_status
from harness.skills.memory.words import _text, _toks

_log = logging.getLogger("harness.memory")     # the same object; see store.py's note


# ──── MEM-OKF v2 §M3: registry hygiene (verify + compaction) ────────────────
# CACHED BY FILE IDENTITY (mtime_ns, size) — the semindex cache-key lesson (an
# mtime-keyed cache once served a dead vector; ns+size is the honest key). The health
# scan is O(n²) over live rows and the operator panel polls /v1/memory every 15 s:
# measured 129 ms per call at 165 rows BEFORE the token precompute, and still a whole
# re-scan per poll after it, for a file that changes a few times an hour.
_HEALTH_CACHE: dict = {"key": None, "value": None}


def _registry_health():
    """(stats dict, status enum). The ONE computation behind both the human report and
    the machine verdict — Tier 2 (INVARIANT-ROADMAP.md): the hygiene decider used to
    sniff 'NEEDS COMPACTION' out of the report STRING, which is branching on a
    paragraph, the src-trap in a lab coat. Status is an enum now; the prose is for
    people."""
    p = _store._reg_path()
    if not p or not os.path.exists(p):
        return None, "unconfigured"
    try:
        st = os.stat(p)
        key = (p, st.st_mtime_ns, st.st_size)
    except OSError:
        key = None
    if key is not None and _HEALTH_CACHE["key"] == key:
        return _HEALTH_CACHE["value"]
    rows, malformed = 0, 0
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows += 1
            try:
                json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
    eps = _store._load()
    # Duplicates are counted among LIVE rows only. A tombstone sharing text with a live
    # row is HISTORY (forgotten-then-restated; a retired duplicate), not a pending chore —
    # counting it made the tombstone-based compactor structurally unable to ever satisfy
    # its own verifier: every tick decided compaction, forever. Malformed still counts
    # over the raw file.
    live = [e for e in eps if not e.get("lifecycle")]
    texts = [_text(e).strip() for e in live]
    exact_dups = len(texts) - len(set(texts))
    # _toks once per row, not once per PAIR — the inner loop retokenized texts[j] for
    # every i, ~n²/2 tokenizations: 129 ms measured at 165 rows, on a 15-second poll.
    toksets = [_toks(t) for t in texts]
    near = 0
    for i in range(len(live)):
        ti = toksets[i]
        if not ti:
            continue
        for j in range(i + 1, len(live)):
            tj = toksets[j]
            if tj and len(ti & tj) / len(ti) >= 0.9 and len(ti & tj) / len(tj) >= 0.9:
                near += 1
    no_ep = sum(1 for e in eps if not e.get("dir") or int(e.get("npos", 0) or 0) <= 0)
    no_prov = sum(1 for e in eps if not e.get("src"))
    stats = {"path": p, "rows": rows, "parsed": len(eps), "malformed": malformed,
             "exact_dups": exact_dups, "near_dups": near, "unminted": no_ep,
             "no_provenance": no_prov}
    # `unminted` has been in this dict since it was written and has never reached a surface
    # or the verdict, which is how 253 consecutive unminted rows went unnoticed. The REASON
    # rides along now — when the engine has refused, that string is the whole diagnosis.
    # The verdict is deliberately NOT changed: 'needs-compaction' means compact() would help,
    # and compact() cannot mint an episode. A refusal is news, not a chore.
    _cap = capture_status()
    if _cap.get("why"):
        stats["capture_refused"] = _cap["why"]
        stats["capture_skipped"] = _cap.get("n", 0)
    status = "ok" if (malformed == 0 and exact_dups == 0) else "needs-compaction"
    if key is not None:
        _HEALTH_CACHE["key"], _HEALTH_CACHE["value"] = key, (stats, status)
    return stats, status


def registry_status() -> str:
    """The machine verdict: 'ok' | 'needs-compaction' | 'unconfigured'."""
    return _registry_health()[1]


def verify_registry() -> str:
    """Integrity check on the fact registry: count rows, malformed lines, exact duplicates,
    near-duplicate paraphrase pairs, and rows missing an episode dir. Read-only report."""
    s, status = _registry_health()
    if s is None:
        return "[no registry configured]"
    out = (f"registry {s['path']}: rows={s['rows']} parsed={s['parsed']} "
           f"malformed={s['malformed']} exact_dups={s['exact_dups']} "
           f"near_dups={s['near_dups']} unminted={s['unminted']} "
           f"no_provenance={s['no_provenance']} "
           f"-> {'OK' if status == 'ok' else 'NEEDS COMPACTION'}")
    if s.get("capture_refused"):
        out += (f"{os.linesep}  KV MINT IS OFF - the engine refused /v1/capture: "
                f"{s['capture_refused']}{os.linesep}"
                f"  {s['unminted']} rows carry no episode and no ep.l5. The registry is "
                f"unaffected (it is the recall authority); the engine-side episode "
                f"representation and the L5 half of the semantic index are.")
    return out


def compact_registry() -> str:
    """Compact the registry: tombstone duplicates, quarantine malformed lines. Hygiene,
    not forgetting — nothing is destroyed.

    ── THIS FUNCTION HARD-DELETED ROWS, UNLOCKED, ON THE AUTOMATIC PATH (2026-08-19) ──────
    It read the file raw, dropped malformed lines and exact duplicates, and rewrote with a
    bare open(p, "w") — no _store._REG_LOCK, no tmp+replace. forget()'s conviction, three doors
    down, still live in a HYGIENE_TOOL she can call herself AND in the tick's hygiene
    executor. And its dedupe keyed on text across ALL rows keeping the FIRST — tombstones
    sort first, so a fact that was forgotten and honestly re-stated was resolved by
    DELETING THE LIVE ROW AND KEEPING THE CORPSE (G-COMPACT §4 demonstrates it).

    ops.compact() did the same job correctly the whole time: backup, tombstone with
    superseded_by, may_supersede so her paraphrase never retires his testimony. Twin
    functions, and the automatic path ran the unguarded one — so the twin no longer
    exists. This is a projection of ops.compact(), same as search_memories_ranked is a
    projection of the seam. Gate: G-COMPACT."""
    p = _store._reg_path()
    if not p or not os.path.exists(p):
        return "[no registry configured]"
    from harness.maintenance import ops
    r = ops.compact()
    return ("compacted: %d duplicates retired, %d paraphrases retired, %d conflicts "
            "superseded, %d malformed quarantined; %d live of %d"
            % (r.get("duplicates_retired", 0), r.get("paraphrases_retired", 0),
               r.get("conflicts_superseded", 0), r.get("malformed_quarantined", 0),
               r.get("live_now", 0), r.get("live_now", 0) + r.get("superseded_total", 0)))
