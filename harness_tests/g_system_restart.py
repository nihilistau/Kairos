"""G-SYSTEM-RESTART — the room may restart the stack, through the one door, answering first.

WHY IT EXISTS. On 2026-08-01 a twelve-hour-old daemon degenerated into token soup and the
only cure was a terminal. The operator was asleep-adjacent and the room could not fix
itself. So: two controls, deliberately separate and labelled with what they cost — a
gateway bounce (seconds, keeps the warm prefix) and a full restart (minutes, reloads the
model). One button for both would make the cheap fix feel as expensive as the dear one.

WHAT IS ASSERTED, and each was a real mistake first or a real hazard:

  * IT GOES THROUGH serve.py. Not a hand-rolled kill-and-respawn. serve.py owns the env
    table, the schema check, and the profile/daemon agreement guard — a hand-rolled
    restart is precisely how the wrong-profile silence happened.

  * THE ANSWER IS WRITTEN BEFORE ANYTHING IS STOPPED. The first cut spawned the restart
    and THEN tried to reply; the comment above it claimed the opposite. Measured, `curl`
    got an empty body every time, because serve.py had already killed the gateway
    mid-write — and the UI's error handling hid it. A comment disagreeing with its code
    is worse than no comment, because it is believed.

  * THE SPAWN IS DETACHED. A full restart stops the process that is serving the request.
    A child inheriting its handles dies with it, so the restart would kill the gateway
    and then die before starting the replacement — stack down, room polling nothing.

  * THE OP IS A FINITE SET. Two values. Not a command string.

  * IT REFUSES RATHER THAN GUESSES. No known profile -> restartable is false and the
    route declines, because restarting with the wrong profile is the outage this whole
    area already produced once.

Offline. Reads sources and calls the resolver; starts nothing.
"""
from __future__ import annotations

import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s %s" % (name, detail))


APP = io.open(os.path.join(ROOT, "harness", "server", "app.py"), encoding="utf-8").read()
SRV = io.open(os.path.join(ROOT, "serve.py"), encoding="utf-8").read()

print("1. the profile is known, not guessed")
check("serve.py stamps SP_PROFILE into the env", '"SP_PROFILE"' in SRV)
check("...and load_profile carries the name so it can", '_profile_name' in SRV)
check("the gateway prefers the stamp", 'environ.get("SP_PROFILE")' in APP)
check("...with a derivation fallback for a stack started before it",
      "_running_daemon_model()" in APP)
check("an unknown profile is REFUSED, not guessed at",
      "cannot tell which profile this stack uses" in APP)
check("...and the read route says so up front", '"restartable"' in APP)

print("\n2. it goes through serve.py — the one door")
i = APP.index("def _do_restart")
# To the function's END, not a hand-counted 1400 chars: the 2026-08-19 shutdown guard
# added ~500 chars at the top of _do_restart and pushed the Popen flags out of the
# window — three FAILs about code that had not changed. A fixed-width span is a line
# number wearing a trenchcoat.
_j = APP.find("\ndef ", i + 1)
win = APP[i:_j if _j > 0 else i + 2400]
check("the relaunch invokes serve.py", '"serve.py"' in win)
check("...and passes the profile", "prof]" in win or "prof)" in win or ", prof" in win)
check("a gateway-only bounce passes --gateway-only", '"--gateway-only"' in win)
check("nothing kills a process by hand here",
      "taskkill" not in win and ".terminate()" not in win and ".kill()" not in win)

print("\n3. THE ANSWER GOES OUT BEFORE ANYTHING STOPS")
h = APP.index('elif self.path == "/v1/system":')
handler = APP[h:h + 1600]
i_write = handler.index("self.wfile.write(payload)")
i_spawn = handler.index("_do_restart(")
check("the payload is written before the restart is triggered", i_write < i_spawn,
      "write@%d spawn@%d" % (i_write, i_spawn))
check("...and flushed before it too", handler.index("flush()") < i_spawn)
check("the comment no longer contradicts the code",
      "ONLY NOW" in handler)
# The validation half must not stop anything either.
j = APP.index("def _spawn_restart")
val = APP[j:j + 900]
check("the validating half starts no process", "Popen" not in val)

print("\n4. the spawn is DETACHED, or a full restart kills its own replacement")
check("detached on Windows", "DETACHED_PROCESS" in win)
check("...and a new session elsewhere", "start_new_session" in win)
check("stdio is not inherited", "DEVNULL" in win)

print("\n5. the op is a finite set")
check("only restart and restart_gateway are accepted",
      'op in ("restart", "restart_gateway")' in APP)
check("anything else is refused with the valid set named",
      "op must be restart or restart_gateway" in APP)
check("no command string is ever taken from the body",
      "body.get(\"cmd\"" not in APP and "body.get('cmd'" not in APP)

print("\n6. the two costs are shown as different")
UI = io.open(os.path.join(ROOT, "ui", "src", "main.jsx"), encoding="utf-8").read()
check("the room offers both, separately", "restart_gateway" in UI and "'restart'" in UI)
check("the expensive one asks first", "yes, restart" in UI)
check("...and says what it costs", "2 min" in UI or "~2" in UI)
check("the cheap one advertises that it keeps the model warm",
      "keeps the model warm" in UI)
check("the room polls /health back rather than guessing a duration",
      "/health" in UI and "setTimeout(wait" in UI)

print("\n7. the resolver actually answers on this machine")
sys.path.insert(0, ROOT)
from harness.server import app as _app  # noqa: E402
# CONDITIONAL ON PURPOSE. Whether a daemon is running is not a property of the code,
# and a gate whose verdict depends on that is the G-PF-PERSONA mistake again. The
# invariant is: resolve to a REAL profile, or refuse. Never guess.
prof = _app._system_profile()
if prof:
    check("the resolved profile names a real profile file",
          os.path.exists(os.path.join(ROOT, "profiles", prof + ".toml")), prof)
else:
    check("no profile resolved -> the route declines rather than guessing",
          "cannot tell which profile this stack uses" in APP)
check("the root is resolved from __file__, not from cwd",
      "_ROOT_DIR = os.path.dirname" in APP)
check("a failed derivation is LOGGED, not swallowed",
      "could not derive the profile" in APP)

print("\nG-SYSTEM-RESTART: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_system_restart.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_system_restart", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
