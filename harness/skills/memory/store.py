"""store.py — the registry file: where it is, how it is read, and the lock over it.

Six names and one invariant. Every mutation of the fact registry is **load-all / change /
rewrite-all**, and the gateway is a ThreadingHTTPServer with the mint worker beside it, so two
of those interleaving is a LOST WRITE — thread A loads 86 rows, B loads the same 86, A appends
and rewrites 87, B appends its own and rewrites 87, and A's fact is gone with no error and no
tombstone. `os.replace` being atomic is a guarantee about BYTES, not about facts. The lock is
the one about facts, and `registry_lock()` exports it so the other writer
(`harness/maintenance/ops.py`) takes the same one — one lock, both writers, or it guards one
of two paths and therefore neither.

── AND THIS MODULE IS REACHED AS A MODULE (2026-09-01) ───────────────────────────────
`harness_tests/g_registry_rmw.py` replaces `_load` with a deliberately sluggish version to
hold the read-modify-write window open, then drives `remember`, `recall` and `forget` and
requires the concurrent write to survive. If any door bound `_load` BY NAME, the patch would
be inert on that door, the race would never open — and the gate would go **quietly green**,
because "the concurrent fact survived" is trivially true when nothing was concurrent. That is
worse than g_secret's version of the same trap, which at least goes red.

So `_load`, `_save_all` and the lock are called as `_store.<name>` by every caller in this
package, and the gate patches the OWNER. G-MEMORY-PACKAGE §5 holds it, with the watched set
DERIVED from what the gates actually rebind. Extracted from `memory.py` byte-identical.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import List

from harness.store_io import replace_atomic, rescue_stray_tmp

# ONE LOGGER, NOT A COPY OF ONE: `logging.getLogger` is idempotent by contract, so every
# module in this package naming `"harness.memory"` gets the SAME object. That is the standard
# idiom and the reason G-MEMORY-PACKAGE's two-copies leg checks the ARGUMENT rather than
# forbidding the name.
_log = logging.getLogger("harness.memory")


def _reg_path() -> str:
    return os.environ.get("SP_RECALL_REGISTRY", "")


def _load(path: str = "") -> List[dict]:
    # `path` (2026-08-24 audit, C): callers with an explicit registry (gates, PersonModel
    # pointed at a fixture) come through the same parser as everyone else instead of
    # keeping a private JSONL loop. Default is the live registry, as ever.
    p = path or _reg_path()
    if not p or not os.path.exists(p):
        return []
    eps = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                eps.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return eps


# ── THE REGISTRY IS READ-MODIFY-WRITTEN FROM SEVERAL THREADS (2026-07-14) ──────────────
# The gateway is a ThreadingHTTPServer — a thread per request — and the mint worker below is
# another. Every mutation here is load-all / change / rewrite-all. Two of those interleaving is a
# LOST WRITE: thread A loads 86 rows, thread B loads the same 86, A appends and rewrites 87, B
# appends its own and rewrites 87 — and A's fact is gone, silently, with no error and no tombstone.
#
# os.replace is atomic, so the FILE is never half-written. That is a guarantee about bytes, not
# about facts, and it is the guarantee we already had. The one we need is that a read-modify-write
# is not interleaved with another, and that takes a lock.
#
# It has to be an RLock: remember() takes it and calls _save_all(), which takes it again.
_REG_LOCK = threading.RLock()


def registry_lock():
    """The registry's read-modify-write lock, exported for the OTHER writer
    (harness/maintenance/ops.py). ops loaded, mutated and rewrote the store holding
    NOTHING, while the scheduler runs ops.compact() unattended DURING live turns —
    the exact interleaving the comment above describes, on the path that touches the
    most rows at once. One lock, both writers, or the lock guards one of two paths
    and therefore neither."""
    return _REG_LOCK


def _save_all(rows: List[dict]) -> None:
    """Rewrite the registry. Atomic via os.replace — a half-written memory file is worse
    than a stale one, and this is now called on the hot path (every reinforcement)."""
    p = _reg_path()
    if not p:
        return
    with _REG_LOCK:
        rescue_stray_tmp(p)               # BEFORE open(tmp,"w") clobbers the evidence (H4)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        replace_atomic(tmp, p)
