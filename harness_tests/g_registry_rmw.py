"""G-REGISTRY-RMW — every read-modify-write on the registry holds the lock, PROVEN.

THE BUG CLASS (2026-08-24 audit, A2). _REG_LOCK's own comment states the invariant: a
load/change/rewrite must not interleave with another, or a write that landed between the
read and the rewrite is silently rewritten away. Three RMWs held only the WRITE half:

    remember()'s reinforce branch   loaded outside, mutated, saved the stale list —
                                    the hottest write path in the file
    forget()                        matched outside, tombstoned inside — the tool whose
                                    entire docstring is about how it used to destroy
    recall()'s note_recalled pass   a READ path that could cost a fact

All three were closed 2026-08-24 (the fix each cites this gate by name). A lost write
has no error, no tombstone, and no receipt — the only way to see one is to make the
race happen, so this gate MAKES IT HAPPEN, deterministically:

THE INSTRUMENT. memory._load is wrapped so that ONE nominated call — the RMW's own
locked read, on the main thread — parks for up to ~1.2 s while a worker thread runs a
real remember() of a fresh fact. WITH the lock, the worker blocks at the door until the
RMW completes, and the wait simply times out: both facts survive. WITHOUT the lock (the
mutant), the worker's fact lands inside the RMW's read→write window and the stale
rewrite erases it. The wrapper widens a timing window; every assertion still flows
through the real remember()/forget()/recall() — nothing here builds rows or supplies
its own precondition.

MUTANTS (verified red by name when this gate landed, then restored):
    remember(): change its `with _REG_LOCK:` (the reinforce block) to `if True:`
        -> "reinforce: the concurrent fact survived" goes red
    forget():   same lift -> "forget: the concurrent fact survived" goes red
    recall():   same lift on the counting block -> "recall: ..." goes red

OFFLINE. No GPU, no daemon.
    python harness_tests/g_registry_rmw.py
"""
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _gate import check, finish, sandbox, utf8_stdout   # noqa: E402

utf8_stdout()
sandbox("g_registry_rmw")                       # FIRST, before any harness import
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"         # no capture socket per write (gates/README)

from harness.skills import memory as M          # noqa: E402

# ── PATCHED AT THE OWNER, NOT AT THE FAÇADE (2026-09-01) ────────────────────────────
# This whole gate works by making `_load` SLUGGISH so the read-modify-write window stays
# open long enough for a second thread to land inside it. `harness/skills/memory` is a
# package now and `_load` lives in `memory/store.py`, which every door calls as
# `_store._load()`. Patching the façade's re-exported `M._load` rebinds an alias nothing
# calls — so the sluggish load never runs, the race never opens, and every check below
# reads GREEN because "the concurrent fact survived" is trivially true when nothing was
# concurrent. MEASURED: with all four RMW locks deleted from `__init__`, that version of
# this gate still printed 6/6. A silent green over the exact bug it exists to catch.
# G-MEMORY-PACKAGE §5 holds it now — a mutant on a sibling-owned name must patch the
# owner, and the set of such names is derived from what the gates actually rebind.
_ORIG_LOAD = M.store._load
_MAIN = threading.main_thread()
_ARM = {"on": False, "skip": 0, "started": None, "release": None}


def _sluggish_load(path: str = ""):
    """The real _load, except the ONE armed call (main thread, after `skip`
    pass-throughs) parks inside the RMW's read so a worker write can try to land."""
    rows = _ORIG_LOAD(path)
    if _ARM["on"] and threading.current_thread() is _MAIN:
        if _ARM["skip"] > 0:
            _ARM["skip"] -= 1
        else:
            _ARM["on"] = False
            _ARM["started"].set()
            _ARM["release"].wait(timeout=1.2)   # lock held -> worker is at the door and
    return rows                                  # this simply times out; lock lifted ->
                                                 # the worker lands inside the window


M.store._load = _sluggish_load


def race(op, concurrent_fact: str, skip: int = 0) -> None:
    """Run `op` (the RMW under test) on the main thread while a worker remember()s
    `concurrent_fact` the instant the RMW's armed read begins."""
    started, release = threading.Event(), threading.Event()
    _ARM.update(on=True, skip=skip, started=started, release=release)

    def _worker():
        started.wait(timeout=5.0)
        M.remember(concurrent_fact, source="user turn")
        release.set()                            # ends the park early under the mutant

    t = threading.Thread(target=_worker)
    t.start()
    op()
    t.join(timeout=10.0)
    _ARM["on"] = False


def texts():
    return [(r.get("text") or "") for r in _ORIG_LOAD()]


print("1. forget() — the whole match-and-tombstone is one locked RMW")
M.remember("Sam keeps a lantern in the attic.", source="user turn")
race(lambda: M.forget("the lantern in the attic"),
     "Sam keeps a canoe in the shed.")
check("forget: the concurrent fact survived (no lost write)",
      any("canoe" in t for t in texts()), texts())
check("forget: ...and the tombstone still landed",
      any("lantern" in (r.get("text") or "") and r.get("lifecycle")
          for r in _ORIG_LOAD()))

print("\n2. remember()'s reinforce branch — the hottest write path holds the lock")
M.remember("Sam keeps a trumpet in the hallway.", source="user turn")
race(lambda: M.remember("Sam keeps a trumpet in the hallway.", source="user turn"),
     "Sam keeps a compass in the drawer.")
check("reinforce: the concurrent fact survived (no lost write)",
      any("compass" in t for t in texts()), texts())
check("reinforce: ...and the repeat was counted as a second data point",
      any("trumpet" in (r.get("text") or "") and int(r.get("mentions", 1) or 1) >= 2
          for r in _ORIG_LOAD()))

print("\n3. recall()'s note_recalled pass — a READ path may not cost a fact")
M.remember("Sam keeps a telescope on the balcony.", source="user turn")
# recall()'s FIRST main-thread _load is the seam's (read-only, unlocked, safe);
# skip=1 parks the SECOND — the locked counting RMW this leg exists for.
race(lambda: M.recall("the telescope on the balcony"),
     "Sam keeps an anvil in the garage.", skip=1)
check("recall: the concurrent fact survived (no lost write)",
      any("anvil" in t for t in texts()), texts())
check("recall: ...and the lookup was still counted (into recalled, never mentions)",
      any("telescope" in (r.get("text") or "") and int(r.get("recalled", 0) or 0) >= 1
          for r in _ORIG_LOAD()))

M.store._load = _ORIG_LOAD
finish("G-REGISTRY-RMW")
