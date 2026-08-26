"""G-CAPTURE-ASYNC — she does not wait on a GPU before she is allowed to answer him.

── THE BUG (measured, not theorised, 2026-07-14) ────────────────────────────────────────
remember() POSTed /v1/capture SYNCHRONOUSLY, timeout=120, on the write path of every fact. And
_capture_after_turn() calls remember() once per durable sentence, up to four, BEFORE the gateway
returns her reply (app.py:116, :128).

Timed against the live daemon, warm, nothing else running:

    527 ms  'My workshop bench is made of oak'
    403 ms  'Sam has an esp32 running the sensors'
    475 ms  'My NUC runs 24/7 in the cupboard'
    297 ms  'Sam is teaching himself the guitar'
    ------
   1702 ms  added to a ~4,400 ms turn, before he sees a single token of what she says.

That is the GOOD case. timeout=120 x 4 facts: THE WORST CASE IS EIGHT MINUTES OF SILENCE while she
waits for a GPU to finish building a cache. It is the judge-call bug again (#19-#22) — an aux model
call sitting inline on a path a human is waiting on — this time on the write path of every fact he
tells her.

── AND THE THING SHE WAS WAITING FOR IS NOT READ ON THIS PROFILE ────────────────────────
The mint builds ep.k/ep.v/ep.mf: KV blobs for the ENGINE's L5/replay recall. The live profile sets
authority='spine', and app.py:816 forces cfg.auto_recall=False on EVERY gateway turn — so the
engine recall, the only consumer of those episodes, never runs on a turn. In the harness, `npos` is
read by exactly two functions, memory_stats() and verify_registry(), and both are REPORTING.

She was being held silent to build an artifact the live recall path cannot read. The episodes still
matter for the daemon-direct fallback (gateway down), so they are not deleted — they are moved off
the path a human is waiting on, which is where they always belonged.

── WHAT THIS GATE ACTUALLY ASSERTS ──────────────────────────────────────────────────────
Not "the queue works". Two things that matter:
  1. THE ROW IS DURABLE THE INSTANT SHE IS TOLD. Deferring the mint must not defer the FACT.
     Every guard — admission, identity firewall, dedupe, supersede, secret classification — still
     runs synchronously, because those are what make it a memory rather than a log line.
  2. SHE IS NOT BLOCKED. A write completes in milliseconds even when the daemon is a black hole.

    python harness_tests/g_capture_async.py       (offline: no GPU, no daemon)
"""
import io
import os
import socket
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_fd, _reg = tempfile.mkstemp(suffix=".jsonl")
os.close(_fd)
os.environ["SP_RECALL_REGISTRY"] = _reg
os.environ["SP_CAPTURE_ASYNC"] = "1"

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


# ── A BLACK-HOLE DAEMON ──────────────────────────────────────────────────────────────
# NOT a closed port — a closed port refuses instantly and would prove nothing. This one ACCEPTS
# the connection and then never answers, which is exactly what a GPU busy with a small model generation
# looks like from the harness. Under the old synchronous code every remember() here would block
# for the full 120-second timeout.
_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
_srv.bind(("127.0.0.1", 0))
_srv.listen(8)
BLACKHOLE = "http://127.0.0.1:%d" % _srv.getsockname()[1]
_held = []


def _swallow():
    while True:
        try:
            c, _ = _srv.accept()
            _held.append(c)          # accept, hold, never reply
        except OSError:
            return


threading.Thread(target=_swallow, daemon=True).start()
os.environ["SP_DAEMON_URL"] = BLACKHOLE

from harness.skills import memory as M                   # noqa: E402
from harness.skills import lifecycle as lc               # noqa: E402

FACTS = [
    "My workshop bench is made of oak",
    "Sam has an esp32 running the sensors",
    "My NUC runs 24/7 in the cupboard",
    "Sam is teaching himself the guitar",
]

# ── 1. SHE ANSWERS HIM. SHE DOES NOT WAIT FOR THE CACHE. ─────────────────────────────
print("\n1. a turn's worth of facts, against a daemon that never answers")
t0 = time.perf_counter()
for f in FACTS:
    M.remember(f, source="user turn")
elapsed = (time.perf_counter() - t0) * 1000.0

print("     %d facts written in %.0f ms (the old path: 1,702 ms warm, up to 480,000 ms hung)"
      % (len(FACTS), elapsed))
check("a turn's memory writes cost her under 250 ms, not 1.7 s and not 8 minutes",
      elapsed < 250, "%.0f ms" % elapsed)
check("...and that holds even though the daemon NEVER responds",
      elapsed < 250, "%.0f ms — she is still waiting on the GPU" % elapsed)


# ── 2. THE FACT IS DURABLE THE INSTANT SHE IS TOLD ───────────────────────────────────
# Deferring the MINT must never defer the MEMORY. This is the assertion that makes the
# optimisation safe: the row and every guard are synchronous; only the KV blob is late.
print("\n2. deferring the mint does not defer the fact")
rows = M._load()
check("all %d facts are ON DISK already" % len(FACTS), len(rows) == len(FACTS), len(rows))
check("each row is live", all(not r.get("lifecycle") for r in rows))
check("each row has its speaker (the guards ran)",
      all(r.get("speaker") == "user" for r in rows),
      [r.get("speaker") for r in rows])
check("each row has its status (the guards ran)",
      all(r.get("status") == lc.STATUS_OBSERVED for r in rows))
check("each row is classified (the guards ran)",
      all(r.get("mem_class") for r in rows))
check("she can recall a fact whose episode has NOT been minted",
      "oak" in M.recall("what is my workshop bench made of"),
      M.recall("what is my workshop bench made of"))

# The npos is what is late — and it is not on the recall path. That is the whole point.
check("npos is 0 (the KV mint is still queued — it is late, and nothing reads it)",
      all(int(r.get("npos", 0) or 0) == 0 for r in rows))
check("the mint is QUEUED, not dropped", M.mint_backlog() > 0, M.mint_backlog())


# ── 3. THE GUARDS STILL RUN, SYNCHRONOUSLY, ON THE SAME PATH ─────────────────────────
# If deferring the mint had quietly moved the write off the guarded path, this is where it shows.
print("\n3. every guard still runs on the write, not on the worker")
M.remember("My PIN is 4471", source="user turn")
sec = next((r for r in M._load() if "4471" in (r.get("text") or "")), {})
check("a secret is still classified private-secret at write time",
      sec.get("mem_class") == "private-secret", sec.get("mem_class"))

before = len(M._load())
M.remember("My workshop bench is made of oak", source="user turn")   # exact repeat
after = M._load()
check("a repeat still REINFORCES rather than duplicating",
      len(after) == before, "%d -> %d" % (before, len(after)))
bench = next(r for r in after if "oak" in (r.get("text") or ""))
check("...and mentions went up", int(bench.get("mentions", 1)) >= 2, bench.get("mentions"))


# ── 4. SYNC MODE IS STILL THERE, AND IT IS THE OLD BEHAVIOUR ─────────────────────────
# mint_async=false must give back exactly what we had. A lever with no null floor is not a lever.
print("\n4. mint_async=false restores the old synchronous path (the null floor)")
os.environ["SP_CAPTURE_ASYNC"] = "0"
check("the async switch is read from the env, not hardcoded", not M._mint_is_async())
os.environ["SP_CAPTURE_ASYNC"] = "1"
check("...and back on", M._mint_is_async())

# ── 5. THE DISK FLOOR — the mint yields before the registry write does ───────────────
# Added 2026-08-23, the day /v1/capture came back on the model (G-MOE-SEAM). An episode is
# ep.k + ep.v at full depth per position: MEASURED over her 51 real ones, mean 11.1 MB and
# max 79.1 MB. The drive was already at 930 of 932 GB, so turning the mint back on without
# a floor spends the last 2.5 GB in about 231 memories.
#
# A FULL DISK IS NOT A MEMORY PROBLEM, it is an everything problem — and the registry write
# is the one that would actually lose something of hers. So the mint yields first: the row
# still lands, with npos=0, and recall is text + semantic. Same degradation as "no engine,
# no mint", reached by a different road.
print("\n5. the disk floor stops the mint before it stops the registry")
M._CAPTURE_REFUSED.update(why="", at=0.0, n=0)
_was = os.environ.get("SP_CAPTURE_MIN_FREE_GB")
try:
    # BEHAVIOURAL, both directions. The first cut of this guard called a `logger` this
    # module does not have; the NameError was swallowed by its own except, execution fell
    # through and the mint ran anyway — measured npos=12 with the floor set to 9000 GB. A
    # guard whose failure mode is "no guard" reads like protection and is not. So the test
    # is that an impossible floor REFUSES, not that the code contains a floor.
    os.environ["SP_CAPTURE_MIN_FREE_GB"] = "9000000"
    npos, ok = M._mint_now("http://127.0.0.1:9", "a fact nobody should mint",
                           os.path.join(os.path.dirname(_reg), "eps", "ep_floor_probe"))
    check("an impossible floor REFUSES the mint", (npos, ok) == (0, False), (npos, ok))
    why = M.capture_status().get("why", "")
    check("...and says which floor, with the free space, in its own words",
          "disk floor" in why and "GB free" in why, why[:70])
    # >= 1, not == 1: the async worker from section 3 may still be draining and each of
    # its facts hits the now-armed breaker and counts. The CLAIM is that the refusal was
    # recorded on the same counter a structural refusal uses, not that nothing else ran.
    check("...and it is the SAME breaker a structural refusal uses (recorded, not retried)",
          M.capture_status().get("n", 0) >= 1, M.capture_status().get("n"))
    check("...and no episode directory was created for a mint that never ran",
          not os.path.isdir(os.path.join(os.path.dirname(_reg), "eps", "ep_floor_probe")))
finally:
    M._CAPTURE_REFUSED.update(why="", at=0.0, n=0)
    if _was is None:
        os.environ.pop("SP_CAPTURE_MIN_FREE_GB", None)
    else:
        os.environ["SP_CAPTURE_MIN_FREE_GB"] = _was
# ── 6. WHERE EPISODES LIVE IS A KNOB, AND MOVING IT ORPHANS NOTHING ──────────────────
# Added 2026-08-23 with the backfill. An episode is 11.1 MB, write-once, read only on a
# deep recall — so it belongs off the working drive, and this box had 32 GB of Optane
# sitting empty. The row carries its own ABSOLUTE `dir`, which is what makes the root
# safe to move: everything already written stays exactly where it is and is still found.
print("\n6. the episode root is a knob, and old rows keep their own dir")
_wasd = os.environ.get("SP_EPS_DIR")
try:
    os.environ.pop("SP_EPS_DIR", None)
    default_root = M.eps_root()
    check("with nothing set, episodes live beside the registry",
          default_root.endswith("/eps") and os.path.dirname(_reg).replace(chr(92), "/") in default_root,
          default_root)
    os.environ["SP_EPS_DIR"] = "F:/somewhere-else"
    check("the override is taken, and normalised to forward slashes",
          M.eps_root() == "F:/somewhere-else", M.eps_root())
    os.environ["SP_EPS_DIR"] = "F:/trailing/"
    check("...a trailing separator does not become a double slash later",
          M.eps_root() == "F:/trailing", M.eps_root())
    os.environ["SP_EPS_DIR"] = "   "
    check("blank is not a path — it means 'beside the registry'",
          M.eps_root() == default_root, M.eps_root())
finally:
    if _wasd is None:
        os.environ.pop("SP_EPS_DIR", None)
    else:
        os.environ["SP_EPS_DIR"] = _wasd
check("the episode root is mapped through the one door too",
      "SP_EPS_DIR" in io.open(
          os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "serve.py"), encoding="utf-8", errors="replace").read())

check("the floor is mapped through the one door (a knob not in serve.py does not exist)",
      "SP_CAPTURE_MIN_FREE_GB" in io.open(
          os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "serve.py"), encoding="utf-8", errors="replace").read())

for c in _held:
    try:
        c.close()
    except OSError:
        pass
_srv.close()
os.unlink(_reg)
print("\nG-CAPTURE-ASYNC  %d/%d" % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
