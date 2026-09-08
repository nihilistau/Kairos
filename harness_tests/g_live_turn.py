"""G-LIVE-TURN — "check for a live turn before bouncing" is a step of the bounce now.

THE RULE, AND WHY IT KEPT FAILING (2026-09-09). This tree's standing rule is to check for a
live turn as its own step before every bounce, because a stop mid-generation loses the turn.
The rule was real; the CHECK was a snippet retyped by hand each time, scraping the gateway
log — find the last `DAEMON-CALL`, call it in-flight if no `round=` / `SPOKE` / `dropped` /
`REFUSED` line follows.

It false-positives on the most common call there is. A LOAD-TIME PREFILL logs
`DAEMON-CALL app.py:_go` and finishes with `base snapshot ready … prefix is HOT` — none of
the four tokens it looked for. So every freshly-warmed idle stack read "A TURN MAY BE IN
FLIGHT". Measured side by side on one warm idle gateway: old heuristic `IN FLIGHT?`, new
check `idle`.

That is worse than no check. Twice in one session the author of the rule read the warning,
judged it noise, and stopped the stack anyway — both times by chaining the check into the
same command as the stop, so the verdict was printed and stepped over in one breath.

So two things changed and this gate holds both:

  1. THE ANSWER IS AUTHORITATIVE, not inferred. `scheduler.in_flight()` is the union of the
     gateway's own turn latch (self-healing after 900 s, so it cannot wedge a bounce) and
     any live unprompted-turn thread (which covers a solo's delay AND its generation, since
     `_arm` sleeps and generates on one thread). Surfaced on /v1/kairos/state.
  2. THE CHECK IS A STEP OF THE STOP, not something the operator remembers — on `--stop`,
     on `--gateway-only` and on the full launch, all three of which stop a running gateway.
     `--force` overrides; no gateway fails OPEN, because a stop must not be blocked by the
     absence of the thing it is stopping.

Lane: OFFLINE (drives the scheduler directly; no daemon, no GPU).
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness_tests._gate import sandbox, check, finish  # noqa: E402

sandbox()

from harness.kairos import scheduler as KS  # noqa: E402
from harness_tests import _src as _srcmod  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

print("0. THE VERDICT IS DRIVEN, BOTH WAYS")
KS.note_user_turn(False)
for s in list(KS._TIMERS):
    KS._TIMERS.pop(s, None)
busy, why = KS.in_flight()
check("an idle scheduler reports NOT in flight", busy is False, why)
check("...and says why, so the verdict is readable",
      isinstance(why, str) and len(why) > 8 and "idle" in why.lower(), why)

KS.note_user_turn(True)
busy, why = KS.in_flight()
check("his turn armed -> IN FLIGHT", busy is True, why)
check("...naming the latch", "his turn" in why.lower(), why)

KS.note_user_turn(False)
busy, _ = KS.in_flight()
check("released -> idle again", busy is False)

print("\n1. THE LATCH SELF-HEALS, SO IT CANNOT WEDGE A BOUNCE FOREVER")
# `note_user_turn` is documented "safe to miss the closing edge — it times out". A guard
# built on a latch that could stick would eventually make her unstoppable, which is a worse
# failure than the one being fixed.
KS.note_user_turn(True)
with KS._LOCK:
    KS._USER_TURN_UNTIL = time.time() - 1.0        # as if the closing edge was missed long ago
busy, why = KS.in_flight()
check("a stale latch does NOT report in flight", busy is False, why)
check("...and the timeout is bounded and known", 0 < KS._USER_TURN_MAX_S <= 3600.0,
      "%.0fs" % KS._USER_TURN_MAX_S)

print("\n2. AN UNPROMPTED TURN COUNTS TOO")
# The whole point of including the timers: a solo/check-in is a turn, and it is exactly the
# kind that happens while nobody is watching the room.
KS.note_user_turn(False)
ev = threading.Event()
t = threading.Timer(30.0, lambda: ev.set())
t.daemon = True
t.start()
KS._TIMERS["g-live-turn"] = t
try:
    busy, why = KS.in_flight()
    check("a live unprompted timer -> IN FLIGHT", busy is True, why)
    check("...naming the session", "g-live-turn" in why, why)
finally:
    t.cancel()
    KS._TIMERS.pop("g-live-turn", None)
busy, _ = KS.in_flight()
check("cancelled -> idle again", busy is False)

print("\n3. IT IS ON THE ROUTE, SO TOOLING CAN ASK INSTEAD OF GUESSING")
st = KS.peek_state("g-live-turn-probe")
check("peek_state reports turn_in_flight", "turn_in_flight" in st, sorted(st)[:6])
check("...and the reason with it", "in_flight_why" in st)
check("...as a real bool", isinstance(st["turn_in_flight"], bool), type(st["turn_in_flight"]))

print("\n4. THE CHECK IS A STEP OF EVERY STOP, NOT A HABIT")
sv = _srcmod.text("serve.py") if hasattr(_srcmod, "text") else open(
    os.path.join(ROOT, "serve.py"), encoding="utf-8").read()
import re  # noqa: E402

# COMMENTS **AND DOCSTRINGS**. §5 below forbids the old log-scraping tokens, and
# `turn_in_flight`'s own docstring quotes them to explain what it replaced — so the first
# cut of that section failed on a correct fix, for the third time this session in this
# exact shape. Both are blanked to spaces so offsets still mean what they say.
def _strip(t: str) -> str:
    t = re.sub(r'"""(?:.|\n)*?"""', lambda m: " " * len(m.group(0)), t)
    t = re.sub(r"'''(?:.|\n)*?'''", lambda m: " " * len(m.group(0)), t)
    return re.sub(r"#[^\n]*", lambda m: " " * len(m.group(0)), t)


code = _strip(sv)
n = code.count("guard_live_turn(")
check("serve.py defines the guard once", code.count("def guard_live_turn(") == 1)
check("...and calls it on all three stopping paths", n - 1 >= 3,
      "%d call site(s) — --stop, --gateway-only and the full launch each stop a gateway" % (n - 1))
check("--force is a known flag", '"--force"' in code)
check("...and the guard honours it", "if force:" in code)

print("\n5. AND IT ASKS THE GATEWAY, IT DOES NOT READ THE LOG")
# THE ANTI-REGRESSION. The failure was not a bad threshold, it was the METHOD: inferring a
# turn from log lines that a load prefill does not emit. A guard that goes back to the log
# is the same bug with a new regex.
i = code.find("def turn_in_flight(")
j = code.find("def guard_live_turn(")
fn = code[i:j] if 0 <= i < j else ""
check("turn_in_flight exists", bool(fn))
check("...asks /v1/kairos/state", "/v1/kairos/state" in fn)
for banned in ("gateway.log", "DAEMON-CALL", "round=", "SPOKE"):
    check("...and never scrapes %r" % banned, banned not in fn,
          "inferring a turn from the log is the bug this replaces")
check("...fails OPEN when no gateway answers", "URLError" in fn and "return False" in fn,
      "a stop must not be blocked because the thing it stops is already gone")

finish("G-LIVE-TURN")
