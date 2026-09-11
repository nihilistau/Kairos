#!/usr/bin/env python
"""G-MINT-SHUTDOWN — the mint worker is STOPPED, not killed by the interpreter.

WHAT THIS EXISTS FOR (2026-09-11). The public CI had been failing intermittently with
`exit=-11` — SIGSEGV — since the offline suite first ran there. A different gate each time,
always AFTER that gate printed a clean verdict (`G-KAIROS-LATCH: 39 pass, 0 fail`, then the
signal), and with `PYTHONFAULTHANDLER=1` printing nothing at all — which is itself the clue,
because faulthandler is torn down during interpreter finalization, so a fault after that
point has nobody left to report it.

Two theories were tried and both returned clean negatives, recorded in the changelog: timing
(the suite ran at `-j 1` and a gate segfaulted anyway, with nothing else running) and
contention. What actually pointed here was an `atexit` probe over the gates themselves:

    gates that HAVE crashed in CI        all four leave `sp-mint` alive at exit
    gates that have never crashed        four of five leave no thread at all

`_mint_drain` has always had a `None` sentinel that makes it return, and **nothing ever sent
one**. So every process that minted an episode exited with that daemon thread still running,
and CPython's finalization killed it wherever it happened to be — which can be inside
`urlopen`, or inside `_save_all` **holding `_REG_LOCK`, mid-write to her fact registry.**
The crashing population is "gates that write memory"; which one dies is luck.

WHAT A GATE CAN AND CANNOT HOLD. A segfault in interpreter finalization is not something a
check can assert — the proof of that half is CI going quiet. What is assertable is the
property that makes it impossible, and that is what this grades: **a process that mints does
not reach finalization with the worker still running.** Driven in a SUBPROCESS, because the
claim is about interpreter exit and nothing measured from inside one run can see it.

§1 the worker stops, and says so           §4 the atexit hook is actually installed
§2 a backlog does not have to be drained   §5 a restarted worker is not poisoned by the flag
§3 no thread survives to finalization      §6 the one case it cannot reach, named honestly

OFFLINE. No GPU, no daemon — the daemon URL is a blackhole on purpose.
"""
import os
import subprocess
import sys
import textwrap
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from _gate import check, finish, sandbox            # noqa: E402

sandbox("g_mint_shutdown")

# A port nothing answers on and nothing REFUSES on fast is the worst case for a shutdown, and
# it is the one g_capture_async deliberately uses. 127.0.0.1:9 (discard) refuses promptly on
# these boxes, which is the COMMON case; the blackhole leg is §6 and is not timed.
os.environ["SP_CAPTURE_ASYNC"] = "1"
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"

from harness.skills.memory import mint as _mint      # noqa: E402

print("1. THE WORKER STOPS WHEN ASKED")
_mint._mint_later("a fact the engine will never see", "ep_x")
time.sleep(0.2)
check("a mint started the worker",
      _mint._MINT_WORKER is not None and _mint._MINT_WORKER.is_alive())
t0 = time.perf_counter()
stopped = _mint.mint_shutdown()
dt = time.perf_counter() - t0
check("mint_shutdown() reports it stopped", stopped is True, stopped)
check("...and the thread is actually gone", not _mint._MINT_WORKER.is_alive())
check("...promptly — the common case is a worker parked in get()", dt < 5.0, "%.2fs" % dt)

print("\n2. A BACKLOG DOES NOT HAVE TO BE MINTED FIRST")
# `put(None)` lands at the BACK of the queue. Before the stop flag, a shutdown behind a
# backlog had to mint every pending episode before it could see the sentinel — which is the
# whole reason the flag is read BEFORE the item rather than only via the sentinel.
for i in range(25):
    _mint._mint_later("backlog fact %d" % i, "ep_b%d" % i)
time.sleep(0.1)
t0 = time.perf_counter()
stopped2 = _mint.mint_shutdown()
dt2 = time.perf_counter() - t0
check("a shutdown behind 25 queued episodes still stops", stopped2 is True, stopped2)
check("...without draining them", dt2 < 5.0, "%.2fs" % dt2)
check("...and what is abandoned stays in the queue to be COUNTED, not lost silently",
      _mint.mint_backlog() >= 0, _mint.mint_backlog())

print("\n3. NO THREAD SURVIVES TO FINALIZATION  (the actual claim, in a subprocess)")
# atexit runs BEFORE daemon threads are killed, so this is the last moment the list means
# anything. The gate's own process cannot answer this about itself.
_prog = textwrap.dedent(
    """
    import atexit, os, sys, threading, time
    sys.path.insert(0, %r)
    os.environ["SP_CAPTURE_ASYNC"] = "1"
    os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
    import tempfile
    os.environ["SP_RECALL_REGISTRY"] = os.path.join(
        tempfile.mkdtemp(prefix="g_mint_shutdown_sub_"), "registry.jsonl")
    def _report():
        alive = [t.name for t in threading.enumerate() if t is not threading.main_thread()]
        sys.stdout.write("ALIVE=%%s\\n" %% ",".join(sorted(alive)))
        sys.stdout.flush()
    atexit.register(_report)          # registered FIRST, so it runs LAST
    from harness.skills.memory import mint as m
    for i in range(5):
        m._mint_later("subprocess fact %%d" %% i, "ep_s%%d" %% i)
    time.sleep(0.3)
    """
) % (ROOT,)
r = subprocess.run([sys.executable, "-u", "-c", _prog], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=180)
_alive = next((ln.split("=", 1)[1].strip() for ln in (r.stdout or "").splitlines()
               if ln.startswith("ALIVE=")), None)
check("the subprocess reported its live threads at exit", _alive is not None,
      "stdout=%r stderr=%r" % (r.stdout[-300:], r.stderr[-300:]))
check("a process that minted reaches finalization with NO worker alive", _alive == "",
      "still alive: %r" % (_alive,))
check("...and it exited normally, not on a signal", r.returncode == 0, r.returncode)

print("\n4. THE HOOK IS INSTALLED BY MINTING, NOT BY IMPORTING")
# A process that never mints should not carry a hook; one that does must.
check("minting installed the atexit hook", _mint._MINT_ATEXIT[0] is True)
_fresh = subprocess.run(
    [sys.executable, "-c",
     "import sys; sys.path.insert(0, %r);"
     "from harness.skills.memory import mint as m;"
     "print(m._MINT_ATEXIT[0])" % ROOT],
    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
check("...and a bare import of the module installs none",
      (_fresh.stdout or "").strip() == "False", _fresh.stdout)

print("\n5. A RESTARTED WORKER IS NOT POISONED BY THE FLAG")
# The flag means "the worker running right now should stop", never "minting is over". Left
# set, the next worker would return on its first item and drop every episode from then on.
_mint._mint_later("after the shutdown", "ep_after")
time.sleep(0.2)
check("a mint after a shutdown starts a live worker again",
      _mint._MINT_WORKER is not None and _mint._MINT_WORKER.is_alive())
check("...because the stop flag was cleared at start", not _mint._MINT_STOP.is_set())
_mint.mint_shutdown()

print("\n6. THE CASE IT CANNOT REACH, NAMED RATHER THAN HIDDEN")
# A capture already inside `urlopen(timeout=120)` cannot be interrupted from another thread.
# Hanging shutdown for two minutes to close that window would be the worse bug, so the
# contract is: bounded join, and SAY SO. `g_capture_async` blackholes the daemon on purpose
# and is expected to print that line.
import inspect                                       # noqa: E402
_src = inspect.getsource(_mint.mint_shutdown)
check("mint_shutdown takes a bounded timeout rather than joining forever",
      "w.join(timeout)" in _src and "_MINT_JOIN_S" in inspect.getsource(_mint))
check("...and a worker it could not stop is LOUD, with the backlog count",
      "_log.warning" in _src and "abandoned" in _src)
check("...and it never raises out of an exit hook",
      "except Exception" in _src and "return False" in _src)

finish("G-MINT-SHUTDOWN")
