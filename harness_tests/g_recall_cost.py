"""G-RECALL-COST — one recall reads the registry a BOUNDED number of times, and the
bound does not grow with the store.

THE DEFECT (found 2026-09-11, fixed the same day). `rank._idf_table()` and
`rank._person_model()` used `len(_store._load())` as their cache-validity key: a full
read and parse of the whole registry, performed in order to decide whether a parse was
still needed. `_evidence()` calls the first once per candidate row and `_surprisal_of()`
called the second once per candidate row, so ONE recall re-parsed the whole registry
once per candidate. MEASURED through the real seam on a copy of the live registry:

    rows        _load calls per recall        wall time
     250                          ~470           0.97 s
   1,561                       145-479        2.1-7.1 s      <- the live store
   2,500                        ~3,900          56.7 s

Quadratic, on the automatic per-turn injection path, in a store whose founding rule is
that it only ever grows. After the fix the same six questions cost 1-3 calls and
5-107 ms, and returned byte-identical rows (12 queries plus list_memories, live_rows
and search_memories, diffed against the tree at HEAD).

WHY THIS GATE COUNTS CALLS AND NOT MILLISECONDS. Wall time is a property of the box; the
call count is the thing that actually regressed and it is the same number on any machine.
It is also the assertion a future "let's just re-read, it's only a few ms" would trip.

WHY THE SECOND LEG IS THE IMPORTANT ONE. A constant bound could be met by a store that
happens to be small. Leg 2 runs the SAME query against a registry four times the size and
requires the call count not to move — that is the O(N) claim stated as a finite check, and
it is the one that fails if the cache key goes back to being derived from the rows.

LEG 4 GUARDS THE FIX'S OWN RISK. `_load` now serves a memoised parse, and `commit_row`,
`forget` and the reinforce branch all mutate the rows it returns before rewriting them. So
the contract is that every caller gets rows it OWNS. If a later change hands out the cached
list itself, one writer's half-finished mutation becomes every reader's view of the store —
so the gate mutates a returned row and requires the next call not to have heard about it.

MUTANTS (each verified red by name when this gate landed, then restored):
    rank._idf_table:   key back to `len(rows)`      -> "call count is bounded" and
                                                       "cost does not grow with the store" go red
    rank._person_model: key back to `len(_load())`  -> same two go red
    store._load:       return the cached list itself (drop the row-wise copy)
                                                    -> "rows are the caller's to mutate" goes red
    store._save_all:   delete the invalidate_cache() call
                                                    -> "the writer invalidates the memo" goes red

THE FOURTH MUTANT PASSED THE FIRST VERSION OF THIS GATE, 8/8. The leg meant to cover the
invalidation asserted that an ordinary write is visible to the next read — which the STAMP
already guarantees, so it held with `invalidate_cache()` deleted and was testing nothing.
The leg it became constructs the one case the stamp is blind to: a rewrite of exactly the
same byte count with mtime restored, so (path, mtime_ns, size) is unchanged and only the
writer can know. That is the case the explicit invalidation exists for, and it is now the
case the gate drives.

OFFLINE. No GPU, no daemon, no sidecar.
    python harness_tests/g_recall_cost.py
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _gate import check, finish, sandbox, utf8_stdout   # noqa: E402

utf8_stdout()
SBOX = sandbox("g_recall_cost")                 # FIRST, before any harness import
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"         # no capture socket per write (gates/README)
os.environ["SP_CAPTURE_ASYNC"] = "0"
for _k in ("SP_SEM_RANK", "SP_SEM_MINT", "SP_SEM_AUX_EMBED"):
    os.environ.pop(_k, None)                    # the lexical path only: this is about I/O

import harness.skills.memory as M               # noqa: E402
from harness.skills.memory import rank as _rank  # noqa: E402

# The vocabulary is shared between the rows and the query ON PURPOSE: a query that matches
# nothing admits nothing, calls neither _evidence nor _surprisal_of, and would have passed
# over the defect with one _load. The expensive case is the ordinary one — a question whose
# words reach the store.
_WORDS = ("radiographer hospital lamb rogan josh open water terrified workshop forge gpu "
          "rtx nvidia sister melbourne coffee espresso guitar telescope orion diving fear "
          "ocean curry dinner shift roster scanner").split()
QUERY = "radiographer hospital telescope orion"
SMALL, LARGE = 400, 1600                        # 4x, and both far above any fixture


def write_registry(n, path, seed=0):
    rnd = random.Random(seed)
    with open(path, "w", encoding="utf-8") as f:
        for i in range(n):
            text = "Sam " + " ".join(rnd.sample(_WORDS, 6)) + " %d" % i
            f.write(json.dumps({
                "name": "ep_%d" % i, "text": text, "topic": text[:40],
                "speaker": "user", "mem_class": "fact", "src": "user turn",
                "status": "observed", "mentions": rnd.randint(1, 5), "recalled": 0,
                "ts": "2026-08-%02dT0%d:00:00Z" % (rnd.randint(1, 28), rnd.randint(0, 9)),
                "first_seen": "2026-01-01T00:00:00Z", "last_seen": "2026-09-01T00:00:00Z",
                "lifecycle": 0,
            }) + "\n")


# ── the instrument: count calls at the OWNER, not at the façade ───────────────────────
# `_load` lives in memory/store.py and every door calls it as `_store._load()`. Rebinding
# the façade's re-exported `M._load` would patch an alias nothing calls — the counter would
# read zero and this gate would go green over any regression at all. G-REGISTRY-RMW's
# header records the version of that trap which printed a silent 6/6.
_ORIG_LOAD = M.store._load
_CALLS = {"n": 0}


def _counting_load(path: str = ""):
    _CALLS["n"] += 1
    return _ORIG_LOAD(path)


M.store._load = _counting_load


def cold_caches():
    """The state after any write: nothing memoised, nothing derived."""
    _rank._IDF_CACHE[:] = []
    _rank._PM_CACHE[:] = []
    _rank._SURP_CACHE.clear()
    M.store.invalidate_cache()


def recall_cost(rows, path, seed=0):
    write_registry(rows, path, seed)
    os.environ["SP_RECALL_REGISTRY"] = path
    cold_caches()
    _CALLS["n"] = 0
    hits = M.search_memories_ranked_rows(QUERY, k=5)
    return _CALLS["n"], hits


BOUND = 8            # generous: the honest cost is 1-3. The defect was 145-3,900.
small_path = os.path.join(SBOX, "reg_small.jsonl")
large_path = os.path.join(SBOX, "reg_large.jsonl")

n_small, hits_small = recall_cost(SMALL, small_path, seed=1)
n_large, hits_large = recall_cost(LARGE, large_path, seed=2)

check("the seam actually matched something (else this gate proves nothing)",
      len(hits_small) > 0 and len(hits_large) > 0,
      "small=%d large=%d hits" % (len(hits_small), len(hits_large)))

check("call count is bounded: one recall reads the registry <= %d times" % BOUND,
      n_small <= BOUND and n_large <= BOUND,
      "%d rows -> %d calls; %d rows -> %d calls" % (SMALL, n_small, LARGE, n_large))

check("cost does not grow with the store: 4x the rows, same number of reads",
      n_large <= n_small,
      "%d rows -> %d calls but %d rows -> %d calls" % (SMALL, n_small, LARGE, n_large))

# ── the caches are keyed on the FILE, not on how many rows are in it ──────────────────
os.environ["SP_RECALL_REGISTRY"] = large_path
cold_caches()
M.search_memories_ranked_rows(QUERY, k=5)          # warm everything
stamp_before = M.store.registry_stamp()
_CALLS["n"] = 0
M.search_memories_ranked_rows(QUERY, k=5)          # ...and again, nothing changed
warm = _CALLS["n"]
check("a second identical recall re-reads no more than the first",
      warm <= BOUND, "%d calls on the warm repeat" % warm)

# A relabel changes a row WITHOUT changing how many rows there are — the case the old
# row-count key could not see, and the reason the stamp is the better key rather than
# merely the cheaper one.
rows = M.store._load(large_path)
rows[0]["mentions"] = rows[0].get("mentions", 1) + 7
os.environ["SP_RECALL_REGISTRY"] = large_path
M.store._save_all(rows)
check("a write is seen by the next read (the memo is invalidated, count unchanged)",
      M.store.registry_stamp() != stamp_before
      and any(r.get("name") == rows[0]["name"] and r.get("mentions") == rows[0]["mentions"]
              for r in M.store._load()),
      "stamp did not move, or the edit was not visible")

check("an in-place edit invalidates the derived caches too",
      _rank._idf_table()[0] is not None and (not _rank._IDF_CACHE
                                             or _rank._IDF_CACHE[0] == M.store.registry_stamp()),
      "idf table still keyed on a stale stamp")

# ── THE INVALIDATION ITSELF, WHERE THE STAMP CANNOT HELP ──────────────────────────────
# The leg above passes whether or not `_save_all` invalidates, because the stamp moves on
# any ordinary write and catches it either way — which makes it a test of the stamp, not of
# the invalidation. MEASURED: with `invalidate_cache()` deleted from `_save_all`, this gate
# printed 8/8. A leg that cannot fail is not a leg.
#
# So this one constructs the ONE case the stamp is blind to and the explicit invalidation
# exists for: a rewrite of exactly the same byte count, with mtime put back to what it was.
# Same (path, mtime_ns, size), different content. Nothing on disk can tell the difference;
# only the writer knows, which is why the writer is the one that has to say so.
rows = M.store._load(large_path)
before_stat = os.stat(large_path)
marker = "ZZTOPICMARKER"
victim = rows[0]["topic"]
rows[0]["topic"] = marker + victim[len(marker):]        # SAME LENGTH, different bytes
M.store._save_all(rows)
os.utime(large_path, ns=(before_stat.st_atime_ns, before_stat.st_mtime_ns))
check("the writer invalidates the memo — a same-size, same-mtime rewrite is still seen",
      M.store.registry_stamp() == (large_path, before_stat.st_mtime_ns, before_stat.st_size)
      and M.store._load()[0].get("topic", "").startswith(marker),
      "the stamp moved (test is not exercising the blind case) or the rewrite was not seen")

# ── leg 4: the rows a caller gets are the caller's ────────────────────────────────────
a = M.store._load()
a[0]["text"] = "MUTATED BY THE GATE"
a[0].setdefault("supersedes", []).append("MUTATED")
b = M.store._load()
check("rows are the caller's to mutate — the memo hands out copies",
      b[0].get("text") != "MUTATED BY THE GATE"
      and "MUTATED" not in (b[0].get("supersedes") or []),
      "a mutation of returned rows leaked into the next read")

check("the copy is faithful: same rows, same order as a direct parse",
      [r.get("name") for r in b] == [json.loads(l)["name"]
                                     for l in open(large_path, encoding="utf-8") if l.strip()],
      "memoised order or content differs from the file")

M.store._load = _ORIG_LOAD
finish("G-RECALL-COST")
