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

print("\nG-WATCHDOG: %d pass, %d fail" % (PASS, FAIL))
import io  # noqa: E402
import json  # noqa: E402
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_watchdog.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_watchdog", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
