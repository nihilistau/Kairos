"""G-SHUTDOWN — there is a way to stop her, and it stops things in the right order.

Before this, `serve.py --stop` was three taskkill /F calls and no HTTP route could stop
anything: the room had no reach at all. A kill loses DELIVERY, not content — scheduler.py
calls _ON_SPOKE(text) before the outbox append, so her words are on disk the moment she
says them. What a kill costs is an unshown message, a generation in flight, and her turn
state. The graceful path exists for those.

Offline. No GPU, no daemon.

Run: python harness_tests/g_shutdown.py
"""
from __future__ import annotations

import io
import json
import os
import sys
import threading
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


from harness.control import shutdown as SD          # noqa: E402
from harness.kairos import scheduler as KS          # noqa: E402

print("1. QUIESCE STOPS NEW WORK AND SAYS SO")
SD._reset_for_test()
check("not shutting down at rest", not SD.is_shutting_down())
check("quiesce returns True the first time", SD.quiesce() is True)
check("...and the flag is set", SD.is_shutting_down())
check("...and it is idempotent", SD.quiesce() is False)

print("\n2. FLUSH WRITES WHAT WOULD OTHERWISE BE LOST")
SD._reset_for_test()
KS._OUTBOX["s1"].append({"text": "something she said", "kind": "solo"})
KS._OUTBOX["s1"].append({"text": "and another", "kind": "muse"})
p = os.path.join(ROOT, "var", "room", "undelivered.jsonl")
before = io.open(p, "rb").read() if os.path.exists(p) else b""
try:
    n = SD.flush()
    check("flush reports what it wrote", n == 2, n)
    rows = [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]
    check("...and the rows are on disk", len(rows) >= 2, len(rows))
    check("...carrying her text", any("something she said" == r.get("text") for r in rows))
    check("...and the session it was for", any(r.get("session") == "s1" for r in rows))
    check("...and the outbox is emptied so nothing is written twice",
          not KS._OUTBOX["s1"])
    check("flush on an empty outbox writes nothing", SD.flush() == 0)
finally:
    io.open(p, "wb").write(before)
    KS._OUTBOX.clear()

# ── FIX ROUND 1 — A RESTART DURING THE OLD TICKER'S SLEEP MUST NOT WAKE IT BACK UP ──────
# `stop_ticker()` used to SET a shared `threading.Event` and `start_ticker()` used to
# CLEAR it, on the guard "no `_TICKER` is alive". Those are two different generations of
# the ticker touching the SAME flag: a `stop` then an immediate `start`, both landing
# while the old `_loop` thread is still asleep in `time.sleep(_period())` (up to 600s),
# left the flag CLEARED by the restart before the old thread ever read SET — so the old
# thread woke up, saw "not stopping", and ticked anyway. Two threads, one GPU: the exact
# shape of the `_SEEDED` incident in scheduler.py (22 solo turns across two sessions,
# both generating from the same canon). `mode=her` stopping the ticker and the room's
# start button reviving her in the same process makes this the ORDINARY path, not an
# edge case.
#
# The fix replaced the shared Event with a generation counter (`_TICKER_GEN`): every
# start and every stop is a new generation, and `_loop` only ever compares the number it
# was born with against the CURRENT one — nothing for a later generation to clear out
# from under it. Proven two ways below: the counter itself never repeats a generation
# across a stop-then-restart (deterministic, no sleep), and a real old-generation thread,
# put to sleep and then superseded, is observed to never tick (bounded, well under 1s).
print("\n3. A RESTART DURING THE OLD TICKER'S SLEEP CANNOT REVIVE IT")
KS.stop_ticker()          # clean slate — nothing from an earlier section should be alive

KS.start_ticker(period_s=1000.0)             # generation A, asleep for the rest of this test
gen_a = KS._TICKER_GEN
was = KS.stop_ticker()                        # asks A to stop before it ever wakes
gen_after_stop = KS._TICKER_GEN
KS.start_ticker(period_s=1000.0)              # generation B — the restart that used to race A
gen_b = KS._TICKER_GEN
KS.stop_ticker()

check("stopping reported a ticker was actually running", was is True)
check("stopping is its own generation, not a flag A could still read as clear",
      gen_after_stop != gen_a, (gen_a, gen_after_stop))
check("the restart is a THIRD generation, not a revival of A's",
      gen_b != gen_a and gen_b != gen_after_stop, (gen_a, gen_after_stop, gen_b))

ticks: list = []
_real_tick_once = KS.tick_once
KS.tick_once = lambda now=None: ticks.append(threading.current_thread().ident)
try:
    KS.start_ticker(period_s=0.4)             # generation A: wakes once, ~0.4s in
    thread_a = KS._TICKER
    KS.stop_ticker()                          # superseded before it ever wakes
    KS.start_ticker(period_s=0.05)            # generation B: several quick beats
    thread_b = KS._TICKER
    time.sleep(0.65)                          # covers A's one wake and ~12 of B's
    check("the current generation actually ticked", thread_b.ident in ticks)
    check("the superseded generation never ticked once it woke",
          thread_a.ident not in ticks, ticks)
finally:
    KS.stop_ticker()
    KS.tick_once = _real_tick_once

print("\n4. A TURN IN FLIGHT IS WAITED FOR — BUT NOT FOREVER")
SD._reset_for_test()
check("nothing in flight finishes at once", SD.finish_or_abandon(1.0) is True)
SD.note_turn_start()
t0 = time.time()
check("a turn in flight times out rather than blocking",
      SD.finish_or_abandon(0.4) is False)
check("...and it respected the cap", time.time() - t0 < 3.0, time.time() - t0)
SD.note_turn_end()
check("...and finishes once the turn ends", SD.finish_or_abandon(1.0) is True)

print("\n5. HER LAST WORD IS OPTIONAL, BOUNDED, AND NEVER FATAL")
SD._reset_for_test()
check("she gets a last word", SD.goodnight(lambda: "goodnight, love", 2.0) is True)
check("an empty reply is not a goodnight", SD.goodnight(lambda: "   ", 2.0) is False)


def _boom():
    raise RuntimeError("daemon is gone")


check("a failing generation does not fail the shutdown",
      SD.goodnight(_boom, 2.0) is False)


def _hang():
    time.sleep(30)
    return "too late"


t0 = time.time()
check("a hung generation cannot block the shutdown",
      SD.goodnight(_hang, 0.4) is False)
check("...and it returned within the cap", time.time() - t0 < 3.0, time.time() - t0)

print("\n6. A MODE IS THE RUNG THE LADDER STOPS AT")
CALLS = []


def _spy(name, ret=True):
    def _f(*a, **k):
        CALLS.append(name)
        return ret
    return _f


def _fake_steps():
    return {"quiesce": _spy("quiesce"), "finish_or_abandon": _spy("finish"),
            "flush": _spy("flush", 0), "stop_voice": _spy("voice"),
            "stop_daemon": _spy("daemon"), "stop_gateway": _spy("gateway", None)}


SD._reset_for_test(); CALLS.clear()
r = SD.shutdown("her", _steps=_fake_steps())
check("`her` runs the ladder in order",
      CALLS == ["quiesce", "finish", "flush", "voice", "daemon"], CALLS)
check("...and does NOT stop the gateway", "gateway" not in CALLS, CALLS)
# ── THE GOODNIGHT'S POSITION, finally on the record (2026-08-19) ──────────────────
# _run_ladder called the module-level goodnight() directly and ignored _steps, so the
# spy never saw this rung: the CALLS assertions above have a goodnight-shaped hole,
# and moving it AFTER stop_daemon — asking her for a last word from a dead daemon,
# the exact failure ladder_running() was invented for — would have stayed green.
SD._reset_for_test(); CALLS.clear()
steps_g = _fake_steps()
steps_g["goodnight"] = lambda fn, t: (CALLS.append("goodnight"), True)[1]
r = SD.shutdown("her", goodnight_fn=lambda: "goodnight, love", _steps=steps_g)
check("with a goodnight requested, she speaks BEFORE anything stops",
      CALLS == ["quiesce", "finish", "goodnight", "flush", "voice", "daemon"], CALLS)
check("...and the ladder records that she said it", r["goodnight_said"] is True, r)
check("...and reports the mode back", r["mode"] == "her", r)
check("...and what it stopped", r["stopped"] == ["voice", "daemon"], r)

SD._reset_for_test(); CALLS.clear()
SD.shutdown("all", _steps=_fake_steps())
check("`all` is the same ladder plus the gateway, LAST",
      CALLS == ["quiesce", "finish", "flush", "voice", "daemon", "gateway"], CALLS)

# THE ESCAPE HATCH. The operator's words: "This is my machine and a lot happens on it. A simple kill
# will sometimes be required." It must not quiesce, wait, or flush — if it did any of
# those it would not be a kill, and the one thing it promises is that it returns now.
SD._reset_for_test(); CALLS.clear()
SD.shutdown("kill", _steps=_fake_steps())
# quiesce IS on the kill ladder now (2026-08-19): it is instant (a flag, a ticker stop,
# timer cancels — no waits), and without it the gateway kept ACCEPTING turns and the
# kairos ticker kept beating between stop_daemon and stop_gateway, both against a dead
# socket. What kill still skips is everything that WAITS: finish_or_abandon, goodnight,
# flush. "It returns now" holds.
check("`kill` quiesces (instant) but skips the waiting rungs and flush",
      CALLS == ["quiesce", "voice", "daemon", "gateway"], CALLS)
check("...and says so, so the room can warn honestly",
      SD.shutdown("kill", _steps=_fake_steps())["flushed"] == 0)

SD._reset_for_test()
bad = SD.shutdown("nonsense", _steps=_fake_steps())
check("an unknown mode is refused rather than guessed",
      bad["ok"] is False and "mode" in bad.get("error", ""), bad)

print("\n7. THE GOODNIGHT RUNG ONLY RUNS WHEN ASKED")
SD._reset_for_test(); CALLS.clear()
r = SD.shutdown("her", goodnight_fn=lambda: "night", _steps=_fake_steps())
check("she is asked when a goodnight is requested", r["goodnight_said"] is True, r)
SD._reset_for_test(); CALLS.clear()
r = SD.shutdown("her", _steps=_fake_steps())
check("...and not otherwise", r["goodnight_said"] is False, r)

print("\n8. SHE CAN BE STARTED AGAIN WITHOUT KILLING THE THING THAT ASKED")
srv = io.open(os.path.join(ROOT, "serve.py"), encoding="utf-8", errors="replace").read()
check("--daemon-only exists", '"--daemon-only"' in srv)
check("...and is a KNOWN flag, or serve.py refuses it",
      "--daemon-only" in srv[srv.index("KNOWN_FLAGS"):srv.index("KNOWN_FLAGS") + 200])
# THE TRAP THIS AVOIDS. `main()` calls stop() before every launch and stop() kills the
# gateway — so a start button that spawned `serve.py <profile>` would kill the thing that
# pressed it. The daemon-only path must return before that line is ever reached.
check("...and the daemon-only branch returns before stop() is reached",
      "daemon_only" in srv and srv.index("if daemon_only") < srv.index("\n    stop(c)"),
      "daemon-only branch must precede the full launch's stop(c) in main()")
# ...but it may still replace a WRONG-MODEL daemon by image name — killing the daemon
# is safe (the caller is the gateway, a python process); what it must never call is
# the full stop(), which kills every harness.server.app python.
check("...and the daemon-only branch never calls the full stop()",
      "stop(c)" not in srv[srv.index("if daemon_only"):srv.index("\n    stop(c)")],
      "the daemon-only branch reached for the gateway-killing stop()")
check("...and it is documented in the usage line", "--daemon-only" in srv[
      srv.index("usage: python serve.py"):srv.index("usage: python serve.py") + 120])
# ONE COPY OF THE LAUNCH, NOT TWO. The first cut of this task pasted the daemon Popen a
# second time into the daemon-only branch. Two copies of one truth is the bug this repo
# keeps getting hit by: the day the engine gains an argument, the path nobody reads is
# the one that comes up wrong.
check("both launch paths call ONE daemon launcher",
      srv.count("def launch_daemon(") == 1 and srv.count("launch_daemon(c, env)") == 2,
      srv.count("launch_daemon(c, env)"))
# 2026-08-21: the spawn moved to engine/launch.py (the sp-specific half, imported lazily so
# the launcher runs without engine/). ONE copy across both files is the rule.
_launch_src = io.open(os.path.join(ROOT, "engine", "launch.py"), encoding="utf-8").read() \
    if os.path.exists(os.path.join(ROOT, "engine", "launch.py")) else ""
# In a tree without engine/ (the Kairos export) there is no daemon to spawn at all, and
# serve.py itself must still carry NO raw Popen of one — the count is then exactly zero.
_want = 1 if _launch_src else 0
check("...and the raw daemon Popen appears exactly %d time(s) (serve.py + engine/launch.py)" % _want,
      (srv + _launch_src).count('"start",\n') == _want, (srv + _launch_src).count('"start",\n'))

print("\n9. THE ROUTES EXIST AND REPLY BEFORE THEY EXIT")
app = io.open(os.path.join(ROOT, "harness", "server", "app.py"),
              encoding="utf-8", errors="replace").read()
check("POST /v1/shutdown exists", '"/v1/shutdown"' in app)
check("POST /v1/start exists", '"/v1/start"' in app)
check("...and shutdown goes through the ladder, not its own teardown",
      "_sd.shutdown(" in app and "taskkill" not in app)
# THE FIDDLY BIT. For mode=all the gateway kills ITSELF. If it exits before the socket is
# flushed the room sees a dead connection and reports a failure on a success.
blk = app[app.index('"/v1/shutdown"'):]
blk = blk[:blk.index('elif self.path == "/v1/start"')]
# ANCHORED ON THE FLUSH, NOT ON ANY write(). The first `self.wfile.write` in this block
# belongs to the 400 unknown-mode reply, which returns immediately — so it precedes the
# ladder no matter how badly the SUCCESS path is reordered, and a check on it would pass
# on exactly the bug it exists to catch. `self.wfile.flush()` appears once, on the accepted
# path, and it is the last thing that happens before the ladder runs.
check("...and the socket is explicitly flushed", blk.count("self.wfile.flush()") == 1,
      blk.count("self.wfile.flush()"))
check("...and the response is written AND flushed before the gateway stops",
      blk.index("self.wfile.write") < blk.index("self.wfile.flush()") < blk.index("_sd.shutdown("))
check("start carries the profile forward rather than hardcoding one",
      "SP_PROFILE" in app[app.index('"/v1/start"'):app.index('"/v1/start"') + 1200])
check("...and never hardcodes a model", "companion" not in app[
      app.index('"/v1/start"'):app.index('"/v1/start"') + 1200])
# AND IT STARTS THE DOOR THAT CANNOT KILL ITS OWN CALLER.
check("...and starts her with --daemon-only, never a full launch",
      '"--daemon-only"' in app[app.index('"/v1/start"'):app.index('"/v1/start"') + 2400])

print("\n10. THE ROOM CAN REACH IT, AND CANNOT DO IT BY ACCIDENT")
api = io.open(os.path.join(ROOT, "ui", "src", "api.js"),
              encoding="utf-8", errors="replace").read()
main = io.open(os.path.join(ROOT, "ui", "src", "main.jsx"),
               encoding="utf-8", errors="replace").read()
check("api exposes shutdown", "export const shutdown" in api)
check("...and start", "export const startHer" in api)
check("the dock carries the button", "sd-btn" in main)
# TWO STEPS, AND THE MODE IS THE CONFIRM. One click must never stop anything.
check("...behind a two-step confirm", "armed" in main and "sd-confirm" in main)
check("...where the FIRST click only arms it",
      "setArmed(true)" in main and "api.shutdown" not in
      main[main.index("setArmed(true)") - 200:main.index("setArmed(true)")],
      "the un-armed button must not call the route")
check("...offering all three modes",
      all(m in main for m in ("'her'", "'all'", "'kill'")), "her/all/kill")
check("...and kill says what it discards",
      "discard" in main.lower() or "loses" in main.lower(),
      "the destructive option must name its cost")
down = io.open(os.path.join(ROOT, "ui", "src", "room", "Down.jsx"),
               encoding="utf-8", errors="replace").read()
check("a shutdown does not look like a crash", "shut down" in down.lower())
check("...and offers a way back when the gateway survived", "startHer" in down)
# AND THE BUNDLE THE BROWSER ACTUALLY LOADS CARRIES IT. A source file that never
# reached console/room/ is the shape of last night's blank room: every server-side
# check green, nothing on screen.
_built = os.path.join(ROOT, "console", "room", "assets")
_js = [f for f in os.listdir(_built) if f.endswith(".js")] if os.path.isdir(_built) else []
_bundle = "".join(io.open(os.path.join(_built, f), encoding="utf-8", errors="replace").read()
                  for f in _js)
check("the built bundle carries the button", "sd-btn" in _bundle, _js)
check("...and the down state", "sd-down" in _bundle, _js)

print("\n11. THE COUNTER IS WIRED INTO BOTH CHAT PATHS, AND ALWAYS PAIRED")
# BOTH, NOT ONE. app.py's own comments record five hooks — kairos, the repeat-guard,
# roleplay, capture, on_user_turn — each wired into `/v1/chat` OR `/v1/chat/completions`
# and therefore into neither. The ladder's wait is the sixth candidate.
check("both chat paths open a turn", app.count("_sd_turn_start()") == 3,
      app.count("_sd_turn_start()"))
check("...and every one of them closes it", app.count("_sd_turn_end()") == 3,
      app.count("_sd_turn_end()"))
# PAIRED IN A `finally`, NOT BESIDE A RETURN. An unbalanced counter breaks nothing
# today and makes every shutdown months from now wait the full timeout and abandon.
# ANCHORED ON THE ROUTE, NOT ON THE STREAM TEST. `if body.get("stream"):` appears twice
# — once in the Flask surface at the top of the file, once in the stdlib dispatch — and
# str.index finds the FIRST, which is not the one this task wired. The gate went green on
# the wrong block for exactly as long as it took to read the failure detail.
for _p in ('for chunk in _native_chat_sse(body)',
           'elif self.path == "/v1/chat/completions"'):
    _blk = app[app.index(_p) - 400:app.index(_p) + 2400]
    check("...in a finally around %s" % _p[:22],
          "_sd_turn_start()" in _blk and "finally:" in _blk
          and _blk.index("finally:") < _blk.index("_sd_turn_end()")
          and _blk.index("_sd_turn_start()") < _blk.index("finally:"), _p)
check("the counter can never fail a turn",
      app.count("in-flight counter") == 2, app.count("in-flight counter"))
idx = io.open(os.path.join(ROOT, "gates", "GATE-INDEX.md"),
              encoding="utf-8", errors="replace").read()
check("the gate is registered", "G-SHUTDOWN" in idx and "g_shutdown.py" in idx)

print("\n12. THE FLAG HAS A READER AND A CLEARER — FOUND BY DRIVING IT, NOT BY READING")
# THE SPEC SAID quiesce SETS "a flag the turn paths check". NOTHING CHECKED IT. Written
# 2026-08-06, measured the same evening: `is_shutting_down` had no caller anywhere outside
# its own gate, and no clearer at all — so a `her` shutdown latched the gateway into a
# state it could never leave, and a turn arriving after the daemon died went at a dead
# socket. A flag with no reader is not an invariant, it is a comment with state attached.
SD._reset_for_test()
check("a flag nobody reads is not a rule — both chat paths read it now",
      app.count("if not _sd_turn_start():") == 2, app.count("if not _sd_turn_start():"))
check("...and refuse with one spelling, not two",
      app.count("self._refuse_shutting_down()") == 2
      and app.count("def _refuse_shutting_down(") == 1,
      app.count("self._refuse_shutting_down()"))
check("...with 503, so the caller knows to retry rather than to file a bug",
      "self.send_response(503)" in app)
check("nothing is shutting down to begin with", SD.is_shutting_down() is False)
SD.quiesce()
check("quiesce sets it", SD.is_shutting_down() is True)
check("...and the ladder is NOT running just because the flag is set",
      SD.ladder_running() is False)
check("resume clears it, and says it did", SD.resume() is True)
check("...so she can be spoken to again", SD.is_shutting_down() is False)
check("...and clearing twice is not an error", SD.resume() is False)
check("/v1/start clears the flag, or she comes back mute",
      "_sd.resume()" in app)
# THE RACE THAT COST A DAEMON. `her` with a goodnight holds the ladder ~100 s while the
# room already shows `start her`, because the route replies on ACCEPTANCE. Pressing it
# launched a daemon that the still-running ladder killed on its way past stop_daemon.
SD._reset_for_test()
_seen_mid = {}


def _slow_voice(*a, **k):
    _seen_mid["running"] = SD.ladder_running()
    return True


SD.shutdown("her", _steps={"quiesce": lambda *a, **k: True,
                           "finish_or_abandon": lambda *a, **k: True,
                           "flush": lambda *a, **k: 0,
                           "stop_voice": _slow_voice,
                           "stop_daemon": lambda *a, **k: True})
check("the ladder says so WHILE it runs", _seen_mid.get("running") is True)
check("...and stops saying so when it is done", SD.ladder_running() is False)
check("/v1/start refuses while the ladder is still coming down",
      "_sd.ladder_running()" in app and "409" in app[app.index('"/v1/start"'):
                                                     app.index('"/v1/start"') + 2400])

# ── 13. WHAT WAS FLUSHED IS DELIVERED — once, warm, and the record only grows ─────────
# flush() preserved her undelivered words at shutdown and NOTHING EVER READ THEM BACK:
# a message she said that the room never showed stayed lost, just lost tidily. The
# reader is scheduler.reload_undelivered(), called from the two re-entry points
# (gateway boot and resume()). The file stays APPEND-ONLY — the cursor is a
# `redelivered` marker row, never a rewrite — and redelivery has a shelf: a day-old
# cut-off fragment delivered cold is worse than silence (the pending-insight rule).
print("\n13. WHAT WAS FLUSHED IS DELIVERED — once, warm, append-only")
import tempfile  # noqa: E402
_UP = os.path.join(tempfile.gettempdir(), "g_shutdown_undelivered.jsonl")
if os.path.exists(_UP):
    os.remove(_UP)
_orig_up, SD.undelivered_path = SD.undelivered_path, lambda: _UP
_orig_st, KS.start_ticker = KS.start_ticker, lambda *a, **k: None
try:
    SD._reset_for_test(); KS._OUTBOX.clear()
    # REAL-shaped rows: the scheduler stamps `at` with time.time() — an EPOCH FLOAT.
    # The first cut of this fixture hand-built ISO stamps, and the gate stayed green
    # while the first live reload marked every real row stale (the parser knew only
    # ISO). A fixture with the wrong shape supplies its own precondition.
    KS._OUTBOX["room-x"].append({"text": "I kept thinking about the storm.", "kind": "muse",
                                 "reason": "a held thought", "at": 1787061600.0})
    KS._OUTBOX["room-x"].append({"text": "…and the way it broke.", "kind": "continue",
                                 "reason": "she was CUT OFF", "at": 1787061605.0})
    n = SD.flush()
    check("the real flush wrote the rows", n == 2, n)
    # a STALE row, flushed by some earlier shutdown, sits in the same file
    with io.open(_UP, "a", encoding="utf-8") as f:
        f.write(json.dumps({"session": "room-x", "why": "undelivered",
                            "text": "ancient fragment", "kind": "continue",
                            "at": "2026-08-01T00:00:00Z"}) + "\n")
    before_bytes = io.open(_UP, "rb").read()

    import unittest.mock as _um
    with _um.patch("time.time", return_value=1787061605.0):  # 2026-08-19T14:00:05Z
        r = KS.reload_undelivered()
    got = list(KS._OUTBOX["room-x"])
    check("the warm rows are back in HER outbox, in order",
          [m.get("text") for m in got] == ["I kept thinking about the storm.",
                                           "…and the way it broke."],
          [m.get("text") for m in got])
    check("...carrying what the room reads (kind/reason/at) plus the redelivered flag",
          got and got[0].get("kind") == "muse" and got[0].get("reason")
          and got[0].get("at") and got[0].get("redelivered") is True, got[:1])
    check("the stale fragment stayed home, and the receipt says so",
          r.get("restored") == 2 and r.get("stale") == 1
          and not any("ancient" in (m.get("text") or "") for m in got), r)
    after_bytes = io.open(_UP, "rb").read()
    check("the file only GREW (append-only: the cursor is a marker row, not a rewrite)",
          after_bytes.startswith(before_bytes) and len(after_bytes) > len(before_bytes))
    check("...and the marker names what happened",
          any(json.loads(l).get("why") == "redelivered"
              for l in after_bytes.decode("utf-8").splitlines() if l.strip()))
    KS._OUTBOX.clear()
    r2 = KS.reload_undelivered()
    check("a second reload delivers NOTHING (once means once)",
          r2.get("restored") == 0 and not KS._OUTBOX["room-x"], r2)

    # resume() is a re-entry point: it must reload — behaviourally, not by grep
    KS._OUTBOX.clear()
    with io.open(_UP, "a", encoding="utf-8") as f:
        f.write(json.dumps({"session": "room-y", "why": "undelivered",
                            "text": "resumed hello", "kind": "muse",
                            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n")
    SD.quiesce(); SD.resume()
    check("resume() reloads what the shutdown before it flushed",
          any(m.get("text") == "resumed hello" for m in KS._OUTBOX["room-y"]),
          list(KS._OUTBOX["room-y"]))
    # ...and the gateway BOOT is the other re-entry point (mode=all/kill killed the
    # process, so resume() never runs) — held statically, like the other run() wiring.
    check("gateway boot wires the reload too", "reload_undelivered" in app)
finally:
    SD.undelivered_path = _orig_up
    KS.start_ticker = _orig_st
    KS._OUTBOX.clear()
    SD._reset_for_test()
    if os.path.exists(_UP):
        os.remove(_UP)

print("\nG-SHUTDOWN: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_shutdown.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_shutdown", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
