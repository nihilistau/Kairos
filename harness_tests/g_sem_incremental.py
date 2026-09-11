"""G-SEM-INCREMENTAL — appending a vector costs an append, not a re-read of the index.

THE COST (measured 2026-09-11 on the live index: 21.4 MB, 3,183 rows). `load_cached` is
memoized on (path, mtime, size) and `mint()` appends a row every time she remembers
anything — so the first recall after ANY write re-read and re-parsed the whole file, **264
ms**, to learn about one appended line. The same shape as `store._load`'s cache key found
the same morning: an invalidation that costs orders of magnitude more than the change it is
tracking, on a file that only ever grows.

THE SHORTCUT, AND WHY IT IS SOUND. The index is append-only. When the path and model set are
unchanged, the file has grown, and the bytes ending the region already parsed are still
byte-identical, then everything before that offset is what was already folded and only the
tail is new. `load()` is a left-to-right fold, so folding the prefix then the suffix gives
the same index as folding the whole file. `_fold` is shared by both paths, because two
implementations of that precedence rule is the bug this repo is named after, in the seam
where it would be least visible.

WHAT THIS GATE REFUSES TO LET THE SHORTCUT DO. Every leg below is a way the file can change
that is NOT an append, and each one must fall back to a full read:

    a rewrite that keeps the size      the anchor bytes move -> full read
    a shrunken file                    size went down        -> full read
    a different model set              the key changes       -> full read
    a different index path             the key changes       -> full read

And the first leg is the one that matters most: after an append, the incremental index must
equal a fresh `load()` of the same file, key for key and vector for vector. Not "close" —
equal.

NOT COMPACTION, WHICH IS WHAT THE PLAN SAID. Best-row-per-key would take 21.4 MB to 15.9 MB
— 26%, not the "two thirds" the plan claimed, because the rows it keeps are the biggest —
and it would destroy **966 `l5-512-v1` vectors** that `/v1/capture` refuses to regenerate on
this model (ADR-013). Five megabytes is not worth deleting evidence that cannot be remade.
The re-parse was the real cost; this removes it without dropping a row.

MUTANTS (each verified red by name, exit 1, then restored):
    drop the anchor check on the HIT path
        -> "a rewrite that keeps the size is not an append" red
    remove BOTH the size and the anchor guard from the incremental path
        -> that leg plus "a shorter file is never an append" red. Removing the SIZE
           comparison alone changes nothing and that is not a hole: a shorter file cannot
           produce the stored anchor either, so the anchor already covers it. The size
           check is a cheap first question, not the guarantee, and saying otherwise here
           would be claiming a mutant that does not exist.
    give the incremental path its own precedence loop with `>` instead of `>=`
        -> "a later row of the SAME model replaces the earlier one" red. Note that ONLY
           that leg catches it: a rank upgrade (hash -> aux) wins under both spellings, so
           every other equivalence check passes. It was added after the mutant walked
           through the first version of this gate untouched.

AND ONE LEG HAD TO BE PINNED TO MEAN ANYTHING. "A rewrite that keeps the size" was a coin
flip on the clock: if enough time passed between the two writes the mtime moved, the key
differed, a full read happened for THAT reason, and the leg passed without the anchor ever
being consulted — measured, with the anchor check deleted, still printing ok. It pins
(mtime, size) back with `os.utime` now, which is the only state in which "the key cannot
see this" is actually true, and a state the real world reaches whenever a rewrite lands
inside one file-time tick.

OFFLINE. No GPU, no daemon, no sidecar.
    python harness_tests/g_sem_incremental.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _gate import check, finish, sandbox, utf8_stdout   # noqa: E402

utf8_stdout()
SBOX = sandbox("g_sem_incremental")             # FIRST, before any harness import
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"

from harness.skills import semindex as SX      # noqa: E402

IDX = os.path.join(SBOX, "semindex.jsonl")
os.environ["SP_SEM_INDEX"] = IDX


def row(addr, ts, model, val):
    dim = {"hash256-v1": 4, "l5-512-v1": 4, "aux-1024-v1": 4}[model]
    return {"addr": addr, "ts": ts, "model": model, "vec": [val] * dim}


def write(rows, mode="w"):
    with open(IDX, mode, encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def cold():
    """Force the next load_cached to be a full read, so a leg can arm from a known state."""
    SX._CACHE.update(key=None, idx=None, size=0, anchor=b"")


def same(a, b):
    if set(a) != set(b):
        return False
    return all(a[k].get("model") == b[k].get("model") and a[k].get("vec") == b[k].get("vec")
               for k in a)


# ── THE LEG WITHOUT WHICH THIS GATE GRADES NOTHING ───────────────────────────────────
# Every equivalence leg below passes just as happily if `load_cached` ignores the shortcut
# and re-reads the whole file every time — "the same answer" is exactly what a full read
# gives. So the optimisation itself has to be asserted, and the only honest way is to count
# the full reads: after an append, `load()` must NOT be called. Patched at the OWNER
# (`SX.load`), never at a by-name alias, because `load_cached` calls it as a module global
# and a snapshot binding would leave the counter reading zero for the wrong reason.
_REAL_LOAD = SX.load
_FULL = {"n": 0}


def _counting_load(models=SX.KNOWN_MODELS):
    _FULL["n"] += 1
    return _REAL_LOAD(models)


SX.load = _counting_load

print("1. AN APPEND IS FOLDED, NOT RE-READ")
write([row("a%02d" % i, "2026-09-01T00:00:00Z", "hash256-v1", i) for i in range(40)])
cold()
first = dict(SX.load_cached())
check("the index loaded at all", len(first) == 40, len(first))

# ...now append, which is what mint() does
write([row("b%02d" % i, "2026-09-02T00:00:00Z", "aux-1024-v1", 100 + i) for i in range(5)],
      mode="a")
_FULL["n"] = 0
after = dict(SX.load_cached())
reads_for_the_append = _FULL["n"]
fresh = dict(_REAL_LOAD(SX.KNOWN_MODELS))       # the comparison, not counted
check("an append does NOT re-read the whole file", reads_for_the_append == 0,
      "%d full load() call(s) for one append" % reads_for_the_append)
check("the incremental index equals a fresh load of the same file", same(after, fresh),
      "%d keys vs %d" % (len(after), len(fresh)))
check("...and it saw the appended rows", len(after) == 45, len(after))

# AN UPGRADE IS AN APPEND TOO, and precedence must survive the shortcut: a better model
# for a key ALREADY in the cached prefix has to win, which is the whole reason `_fold` is
# shared rather than reimplemented.
write([row("a00", "2026-09-01T00:00:00Z", "aux-1024-v1", 999)], mode="a")
up = dict(SX.load_cached())
check("an upgrade appended for an already-cached key wins",
      up[("a00", "2026-09-01T00:00:00Z")]["model"] == "aux-1024-v1",
      up[("a00", "2026-09-01T00:00:00Z")]["model"])
check("...and still equals a fresh load", same(up, dict(_REAL_LOAD(SX.KNOWN_MODELS))))

# AND A LATER ROW OF THE SAME MODEL WINS — `load`'s other documented rule ("Later rows win
# within a model"), which is `>=` and not `>`. Without this leg the incremental path could
# be given its own loop with `>` and every other check here would still pass: a rank
# UPGRADE wins under both spellings, so only a same-model re-mint tells them apart. That is
# exactly the drift sharing `_fold` exists to prevent, so it needs an assertion that can
# see it.
write([row("b00", "2026-09-02T00:00:00Z", "aux-1024-v1", 4242)], mode="a")
again = dict(SX.load_cached())
check("a later row of the SAME model replaces the earlier one",
      again[("b00", "2026-09-02T00:00:00Z")]["vec"][0] == 4242,
      again[("b00", "2026-09-02T00:00:00Z")]["vec"][0])
check("...and still equals a fresh load", same(again, dict(_REAL_LOAD(SX.KNOWN_MODELS))))

print("\n2. EVERYTHING THAT IS NOT AN APPEND FALLS BACK TO A FULL READ")
# A rewrite that keeps the byte count: the anchor is what catches it. Same length, so
# mtime+size alone would be blind to it inside one tick.
cold()
base = [row("c%02d" % i, "2026-09-03T00:00:00Z", "hash256-v1", 7) for i in range(20)]
write(base)
_ = SX.load_cached()
_st = os.stat(IDX)
swapped = [row("c%02d" % i, "2026-09-03T00:00:00Z", "hash256-v1", 8) for i in range(20)]
write(swapped)                                   # identical length, different content
# ── THE STAT IS PUT BACK ON PURPOSE ──────────────────────────────────────────────────
# Without this the leg is a coin flip on the clock: if enough time passes between the two
# writes the mtime moves, the key differs, a full read happens for that reason, and the
# leg passes WITHOUT the anchor ever being consulted. Measured: with the anchor check
# deleted this leg still printed ok — it was grading the scheduler, not the rule. Pinning
# (mtime, size) back to what they were is the only state in which "the key cannot see
# this" is actually true, and it is a state the real world reaches whenever a rewrite
# lands inside one file-time tick (observed granularity: two consecutive writes, delta 0).
os.utime(IDX, ns=(_st.st_atime_ns, _st.st_mtime_ns))
check("the key really is blind here (same mtime, same size)",
      (os.stat(IDX).st_mtime_ns, os.stat(IDX).st_size) == (_st.st_mtime_ns, _st.st_size),
      (os.stat(IDX).st_mtime_ns, _st.st_mtime_ns))
got = dict(SX.load_cached())
check("a rewrite that keeps the size is not an append",
      got[("c00", "2026-09-03T00:00:00Z")]["vec"][0] == 8,
      got[("c00", "2026-09-03T00:00:00Z")]["vec"][0])

# A shorter file can never be an append.
cold()
write([row("d%02d" % i, "2026-09-04T00:00:00Z", "hash256-v1", 1) for i in range(30)])
_ = SX.load_cached()
write([row("d00", "2026-09-04T00:00:00Z", "hash256-v1", 2)])      # truncating rewrite
short = dict(SX.load_cached())
check("a shorter file is never an append", len(short) == 1, len(short))

# A different model set is a different question, and must not reuse the answer.
cold()
write([row("e00", "2026-09-05T00:00:00Z", "hash256-v1", 1),
       row("e01", "2026-09-05T00:00:00Z", "aux-1024-v1", 2)])
both = dict(SX.load_cached())
only_aux = dict(SX.load_cached(models=("aux-1024-v1",)))
check("a different model set is not served from the cached one",
      len(both) == 2 and len(only_aux) == 1, (len(both), len(only_aux)))

# A different path is a different file.
cold()
other = os.path.join(SBOX, "other.jsonl")
write([row("f00", "2026-09-06T00:00:00Z", "hash256-v1", 1)])
_ = SX.load_cached()
with open(other, "w", encoding="utf-8") as f:
    for i in range(3):
        f.write(json.dumps(row("g%02d" % i, "2026-09-07T00:00:00Z", "hash256-v1", 5)) + "\n")
os.environ["SP_SEM_INDEX"] = other
check("a different index path is not served from the cached one",
      len(dict(SX.load_cached())) == 3, len(dict(SX.load_cached())))
os.environ["SP_SEM_INDEX"] = IDX

print("\n3. AND NOTHING WAS DROPPED ON THE WAY")
# The whole argument for doing this instead of compaction: every row is still readable.
cold()
write([row("h00", "2026-09-08T00:00:00Z", "l5-512-v1", 1),
       row("h00", "2026-09-08T00:00:00Z", "aux-1024-v1", 2)])
idx = dict(SX.load_cached())
on_disk = [json.loads(l) for l in open(IDX, encoding="utf-8") if l.strip()]
check("a superseded l5 row is still ON DISK after the better one wins the read",
      any(r["model"] == "l5-512-v1" for r in on_disk), [r["model"] for r in on_disk])
check("...while the reader correctly serves the better one",
      idx[("h00", "2026-09-08T00:00:00Z")]["model"] == "aux-1024-v1")

finish("G-SEM-INCREMENTAL")
