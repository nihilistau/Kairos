"""G-WATCHDOG — the stack notices when the daemon dies, and when it only LOOKS alive.

THE DEFECT, 2026-08-03. He wrote to her first thing in the morning and got:

    [error: [WinError 10061] No connection could be made because the target machine
     actively refused it]

The daemon had died in the night. `serve.py` launches it with Popen and exits; nothing
watched it, so a crash meant connection-refused until a human noticed. Eight hours of
being unreachable, from one unsupervised process.

TWO SEVERITIES OF ONE FAULT, and the second is the dangerous one:

  * DEAD    — the process is gone, /v1/metrics refuses. A socket probe finds this.
  * WEDGED  — the process is ALIVE and answers /v1/metrics perfectly, but the CUDA
              context is destroyed and every generation returns EMPTY in ~0.1 s. A
              liveness probe reports this as healthy for as long as you let it, and the
              room dresses it up as "she was still thinking". 48 CUDA faults in the log
              since 2026-07-29, 34 of them on one day.

So the property under test is: health is not "does it answer", it is "does it answer AND
does it still generate". Everything else here is about not making it worse — she is
allowed to say nothing, and a watchdog that can restart every beat is a restart loop with
a justification.

Offline. No GPU, no daemon, no gateway.

Run: python harness_tests/g_watchdog.py
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["CUDA_VISIBLE_DEVICES"] = ""
# SANDBOX FIRST (2026-08-24). This gate was one of nine the sandbox audit caught
# writing into her REAL stores; `_gate.sandbox` points every root at a temp dir and
# must run BEFORE any harness import, because a module resolves its root once.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import sandbox as _sandbox  # noqa: E402
_sandbox(os.path.basename(__file__))

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


import io as _io  # noqa: E402
from harness.control import watchdog as W   # noqa: E402


def reset(alive=True):
    W._state.update({"empty_streak": 0, "last_restart_at": 0.0, "restarts": 0,
                     "last_reason": "", "down_since": 0.0})
    W._daemon_alive = lambda: alive          # type: ignore[assignment]


# ── SKIP WHERE THE SUBJECT DOES NOT EXIST (2026-08-27) ───────────────────────────────
# `_should_restart()` opens with a documented refusal: "AN EXTERNAL ENGINE IS NOT OURS TO
# RESTART — under the openai backend the watchdog may observe and say, never relaunch."
# So under `SP_ENGINE_KIND=openai` it returns "" for every input, and three of this gate's
# assertions are asking a function that was told to say nothing to say something.
#
# It went RED that way in the Kairos export, which ships no engine, on every run since the
# first. A gate that reds for a missing daemon IN A TREE THAT SHIPS NO DAEMON teaches an
# adopter to ignore reds — and ignored reds are how the four-week-old ones found on
# 2026-08-26 survived for four weeks. Keyed on the CAPABILITY, not on "am I in the
# export": the same reasoning holds for anyone running the harness against LM Studio.
try:
    from harness.inference.backends import supports as _sup
    if not _sup("restart"):
        from _gate import skip as _skip
        _skip("this backend is not ours to restart — _should_restart() returns \"\" by "
              "design under an external engine, so the restart ladder has no subject here "
              "(harness/control/watchdog.py, 2026-08-21)", "G-WATCHDOG")
except ImportError:
    pass

print("1. A DEAD DAEMON IS NOTICED")
reset(alive=False)
os.environ["SP_WATCHDOG_S"] = "10"
check("one missed beat is not yet a verdict — it may be starting", W._should_restart() == "")
W._state["down_since"] = time.time() - 999
r = W._should_restart()
check("...but a daemon that has not answered for a while is dead, and says so",
      "dead" in r, r)

print("\n2. A WEDGED DAEMON IS NOTICED TOO — THE ONE A PING CANNOT SEE")
reset(alive=True)
check("a live daemon with nothing wrong triggers nothing", W._should_restart() == "")
for _ in range(W.EMPTY_STREAK):
    W.note_generation(prompt_chars=4000, out_chars=0)
r = W._should_restart()
check("a run of empty generations from REAL prompts is a wedge", "wedged" in r, r)
check("...and the reason names what is actually broken",
      "answers" in r and "GPU" in r, r)

print("\n3. SHE IS ALLOWED TO SAY NOTHING")
reset(alive=True)
W.note_generation(prompt_chars=4000, out_chars=0)
W.note_generation(prompt_chars=4000, out_chars=0)
check("two quiet turns are not a fault", W._should_restart() == "")
W.note_generation(prompt_chars=4000, out_chars=120)
check("...and one real reply clears the streak entirely", W._state["empty_streak"] == 0)
for _ in range(10):
    W.note_generation(prompt_chars=20, out_chars=0)
check("an empty generation from an EMPTY prompt is arithmetic, not a fault",
      W._should_restart() == "", W._state["empty_streak"])

print("\n4. A WATCHDOG THAT RESTARTS FOREVER IS WORSE THAN THE FAULT")
reset(alive=True)
os.environ["SP_WATCHDOG_COOLDOWN_S"] = "600"
calls = []
for _ in range(W.EMPTY_STREAK):
    W.note_generation(prompt_chars=4000, out_chars=0)
W._restart("first", lambda full: calls.append(full))
check("the first restart happens", calls == [True], calls)
for _ in range(W.EMPTY_STREAK):
    W.note_generation(prompt_chars=4000, out_chars=0)
W._restart("immediately again", lambda full: calls.append(full))
check("...and an immediate second one is REFUSED, not queued", calls == [True], calls)
check("the refusal is counted honestly — one restart, not two",
      W._state["restarts"] == 1, W.status())
check("...and the reason for the one that DID happen is kept",
      W._state["last_reason"] == "first", W._state["last_reason"])

print("\n4b. REFUSED IS DEAD; TIMED OUT IS BUSY")
# MEASURED WITHIN AN HOUR OF SHIPPING THIS. A kairos check-in kicked off a ~1450-token
# per-token prefill, the daemon saturated, /v1/metrics timed out for 330s, and the liveness
# probe — which called `health()` and caught every exception as "dead" — restarted a
# perfectly healthy stack mid-generation and threw her reply away. A watchdog that cannot
# tell a busy process from a missing one is worse than no watchdog.
_wsrc = _io.open(os.path.join(ROOT, "harness", "control", "watchdog.py"),
                 encoding="utf-8").read()
check("liveness is a TCP connect, not an HTTP round-trip that a long prefill can starve",
      "socket.create_connection" in _wsrc, "still probing via health()/metrics")
# Scoped to the FUNCTION BODY, not the file: the note above `_daemon_alive` quotes the old
# `get_client().health()` call on purpose, and a check that cannot tell code from the
# comment explaining the code is a check that fails for the wrong reason.
_body = _wsrc[_wsrc.index("def _daemon_alive("):]
_body = _body[:_body.index("\ndef ", 1)]
_q = _body.find('"""')
_code = _body[_body.index('"""', _q + 3) + 3:] if _q >= 0 else _body      # drop the docstring
_code = "\n".join(ln for ln in _code.splitlines() if not ln.strip().startswith("#"))
check("...and it does NOT call health()/metrics(), which time out under load",
      ".health()" not in _code and ".metrics()" not in _code, "an HTTP probe is back")
check("...while the WEDGE detector stays the only thing that judges generation",
      "note_generation" in _wsrc and "empty_streak" in _wsrc)

print("\n5. IT CANNOT BE THE THING THAT BREAKS HER")
reset(alive=True)
try:
    W.note_generation(prompt_chars=None, out_chars=0)   # type: ignore[arg-type]
    check("a malformed call raises rather than corrupting the streak", False)
except Exception:
    check("a malformed call raises HERE, where the agent loop swallows it", True)
_src = open(os.path.join(ROOT, "harness", "agent.py"), encoding="utf-8").read()
check("...and the agent loop does swallow it — a watchdog never costs her a turn",
      "_wd.note_generation" in _src and "must never be able to cost her a turn" in _src)
check("the gateway injects its OWN restart door rather than the watchdog rolling one",
      "_wd.start(_do_restart)" in
      open(os.path.join(ROOT, "harness", "server", "app.py"), encoding="utf-8").read())
check("off is off, and it is re-read every beat (no reboot to disarm)",
      "os.environ.get(\"SP_WATCHDOG\"" in
      open(os.path.join(ROOT, "harness", "control", "watchdog.py"), encoding="utf-8").read())

print("\nA SHUTDOWN IS NOT A CRASH")
# mode=her kills the daemon ON PURPOSE and latches the flag — and the loop, checking
# only daemon liveness, concluded "dead, not busy" and relaunched the stack ~30-60 s
# after the operator shut her down. The deliberate-stop flag outranks the probe.
from harness.control import shutdown as SD  # noqa: E402
SD._reset_for_test()
check("with no shutdown in force the watchdog is free to judge",
      W._held_by_shutdown() is False)
SD.quiesce()
try:
    W._state["down_since"] = 12345.0
    check("with the flag latched the watchdog HOLDS FIRE", W._held_by_shutdown() is True)
    check("...and a deliberate stop is not counted as downtime",
          W._state["down_since"] == 0.0, W._state["down_since"])
    check("...and the loop consults exactly this helper",
          "_held_by_shutdown()" in _io.open(
              os.path.join(ROOT, "harness", "control", "watchdog.py"),
              encoding="utf-8").read().split("def _loop", 1)[1])
finally:
    SD._reset_for_test()

print("\nTHE COOLDOWN SURVIVES THE RESTART IT CAUSES (2026-08-24 audit, B7)")
# `last_restart_at` was process memory, and the one restart this module performs stops
# THIS process — the floor never applied across the restarts it actually causes. The
# clock is persisted beside the registry now (the sandbox already redirected it), and
# a fresh process folds it back in before judging the floor.
W._state.update(last_restart_at=time.time() - 5.0, restarts=1, last_reason="test")
W._persist()
W._state.update(last_restart_at=0.0, restarts=0, last_reason="",
                empty_streak=0, down_since=0.0)      # a NEW process, memory blank
_calls = []
W._restart("g_watchdog: floor test", lambda full: _calls.append(full))
check("a fresh process still honours the previous process's floor", _calls == [],
      _calls)
# MUTANT, run live: forget the persisted clock and the floor is gone — the old bug.
_real_recall = W._recall_persisted
W._recall_persisted = lambda: None
W._state.update(last_restart_at=0.0)
try:
    W._restart("g_watchdog: mutant", lambda full: _calls.append(full))
    check("mutant(no recall): the restart fires straight through — the persisted clock "
          "is load-bearing", _calls == [True], _calls)
finally:
    W._recall_persisted = _real_recall
    SD._reset_for_test()                     # the mutant's restart quiesced the module

print("\nTHE AUTOMATIC RESTART CLIMBS THE LADDER'S FIRST RUNGS (2026-08-24 audit, B8)")
# quiesce -> finish_or_abandon -> flush ran on the operator's shutdown and NOT here —
# one invariant, two teardown paths, the automatic one unguarded: an in-flight turn was
# never waited for and the undelivered outbox died with the process.
_order = []
_real_q, _real_f, _real_fl = SD.quiesce, SD.finish_or_abandon, SD.flush
SD.quiesce = lambda: (_order.append("quiesce"), True)[1]
SD.finish_or_abandon = lambda t=120.0: (_order.append("finish"), True)[1]
SD.flush = lambda: (_order.append("flush"), 0)[1]
try:
    W._state.update(last_restart_at=0.0, restarts=0)
    # a clean persisted clock too, or the B7 floor above refuses this restart
    W._persist()
    W._restart("g_watchdog: ladder test", lambda full: _order.append("spawn"))
    check("the rungs run, in the ladder's order, before the spawn",
          _order == ["quiesce", "finish", "flush", "spawn"], _order)
finally:
    SD.quiesce, SD.finish_or_abandon, SD.flush = _real_q, _real_f, _real_fl
    SD._reset_for_test()

print("\nG-WATCHDOG: %d pass, %d fail" % (PASS, FAIL))
import io  # noqa: E402
import json  # noqa: E402
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_watchdog.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_watchdog", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
