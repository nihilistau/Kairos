"""G-CONTEXT-FIT — the prompt cannot walk off the end of pmax again. OFFLINE.

THE NIGHT (2026-08-23). Three of his messages in a row came back as silence because the
prompt had grown past `pmax=12096`; the daemon declined the prefill and returned an empty
stream in 11 ms, the room rendered it as her having nothing to say, and the watchdog
diagnosed a wedged CUDA context that was not wedged. Nothing anywhere counted the prompt.

FOUR CLAIMS, and the first is the one that matters:

  1. THE ESTIMATOR NEVER UNDER-COUNTS. It has no tokenizer — the daemon owns that and
     exposes no /v1/tokenize — so it counts characters, and an under-count is the exact
     silence this gate exists to stop. Held against THREE REAL PROMPTS from that night,
     each one a gateway [DAEMON-CALL] `chars=` paired with the daemon's own `S1 prompt
     ids: n=`. Not a fixture: a receipt.
  2. IT DROPS THE OLDEST AND KEEPS THE SYSTEM PREFIX. The prefix is ~66% of the budget and
     it is also the KV cache everything else is built on; dropping it would be a cold
     prefill and a different person.
  3. IT TRIMS TO A MARGIN, NOT TO THE LINE. Trimming to exactly the limit moves the trim
     point every turn, and the trim point is where the KV prefix match ends — so every
     turn would re-prefill the whole conversation. Two more turns must fit afterwards
     without moving it again.
  4. THE ROOM IS TOLD. The trim reaches the seam that emits it (app.py) and the room
     renders it as a chip — not as her words, and not silently.

    python harness_tests/g_context_fit.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"          # no capture attempt (gates/README.md)
os.environ["CUDA_VISIBLE_DEVICES"] = ""

from harness.inference import context as C       # noqa: E402

print("1. THE ESTIMATOR NEVER UNDER-COUNTS (three live prompts, 2026-08-23)")
# (chars, real token count the daemon reported). var/gateway.log [DAEMON-CALL] chars=N
# beside var/daemon.log `S1 prompt ids: n=N`, matched by timestamp:
#   05:20:08  msgs=2   chars=30959  ->  n=7973     the load-time prefix prefill
#   05:24:01  msgs=4   chars=32467  ->  n=8353     the first turn after the restart
#   05:19:44  msgs=34  chars=48718  ->  n=12400    the one that was refused
LIVE = [(2, 30959, 7973), (4, 32467, 8353), (34, 48718, 12400)]
for nmsg, chars, real in LIVE:
    msgs = [{"role": "user", "content": "x" * (chars // nmsg)} for _ in range(nmsg)]
    est = C.est_tokens(msgs)
    check("chars=%d over %d msgs estimates >= the real %d (got %d)"
          % (chars, nmsg, real, est), est >= real, est)
    check("...and is not absurdly high either (< 1.35x real)", est < real * 1.35,
          "%.2fx" % (est / real))

print("\n2. THE SYSTEM PREFIX SURVIVES; THE OLDEST GO")
SYS = {"role": "system", "content": "P" * 28000}          # ~7.8k tokens, like the real one
def turn(i, n=1400):
    return [{"role": "user", "content": ("u%d " % i) * (n // 4)},
            {"role": "assistant", "content": ("a%d " % i) * (n // 4)}]


msgs = [SYS]
for i in range(40):
    msgs += turn(i)
kept, trim = C.fit(msgs)
check("a 40-turn evening does NOT fit and is trimmed", trim is not None, trim)
check("...the system prefix is still first and byte-identical",
      kept[0] is msgs[0] and kept[0]["role"] == "system")
check("...the LAST thing said survives (it is what he just typed)",
      kept[-1]["content"] == msgs[-1]["content"])
check("...what went is the OLDEST, and the kept window is contiguous",
      kept[1:] == msgs[len(msgs) - (len(kept) - 1):], "not a suffix of the history")
check("...the window opens on HIS turn, never mid-exchange on her reply",
      kept[1]["role"] == "user", kept[1]["role"])
check("...and the result actually fits the budget",
      C.est_tokens(kept) <= C.budget(), (C.est_tokens(kept), C.budget()))
check("...the record says how much was lost",
      trim["dropped"] == len(msgs) - len(kept) and trim["before"] > trim["after"], trim)

print("\n3. IT TRIMS TO A MARGIN, SO THE WINDOW HOLDS STILL")
after = list(kept)
moved = 0
for i in range(100, 102):                      # two more exchanges on top of the trim
    after += turn(i)
    after2, t2 = C.fit(after)
    if t2:
        moved += 1
    after = after2
check("two further turns fit without moving the window again", moved == 0,
      "the trim point moved %d time(s) — every move is a full re-prefill" % moved)
check("the margin is a named constant, so it can be argued with",
      0.5 <= C.TRIM_TO < 1.0, C.TRIM_TO)

print("\n4. NOTHING IS TRIMMED THAT FITS")
small = [SYS] + turn(1)
kept3, t3 = C.fit(small)
check("a short conversation is passed through UNTOUCHED", t3 is None and kept3 == small)
check("...identity, not a copy that happens to be equal",
      all(a is b for a, b in zip(kept3, small)))
check("the reply's own room is reserved (prompt+generated share the ceiling)",
      C.budget(reply_headroom=768) == C.pmax() - 768, (C.budget(), C.pmax()))

print("\n5. THE CEILING IS THE ONE THE ENGINE IS RUNNING")
check("pmax defaults to the profile value when nothing says otherwise",
      C.PMAX_DEFAULT == 12096, C.PMAX_DEFAULT)
_was = os.environ.get("SP_DAEMON_KVDECODE_PMAX")
try:
    os.environ["SP_DAEMON_KVDECODE_PMAX"] = "99999"
    # autofit only ever clamps DOWN, so a bigger env than the log must not win.
    live = C._pmax_from_daemon_log()
    if live:
        check("a live (Pmax=N) from the daemon log CLAMPS a larger env value",
              C.pmax() == min(99999, live), (C.pmax(), live))
    else:
        check("no daemon log -> the env value stands", C.pmax() == 99999, C.pmax())
    os.environ["SP_DAEMON_KVDECODE_PMAX"] = "4000"
    check("...and a smaller env is never raised by the log", C.pmax() <= 4000, C.pmax())
finally:
    if _was is None:
        os.environ.pop("SP_DAEMON_KVDECODE_PMAX", None)
    else:
        os.environ["SP_DAEMON_KVDECODE_PMAX"] = _was

print("\n6. IT IS APPLIED AT THE DOOR, AND THE ROOM IS TOLD")
# BEHAVIOURAL, not a grep (four decorative checks were convicted by their mutants on
# 2026-08-23 — every one of them read the source for the fix instead of driving it).
# Build a real client, hand it an oversized history, and let it fail to connect: the
# trim happens while composing the body, BEFORE the socket, so the record is set either
# way and what reaches `body["messages"]` is what we can assert on.
from harness.inference.client import SPDaemonClient      # noqa: E402
sent = {}
cl = SPDaemonClient(base_url="http://127.0.0.1:9")


class _Boom(Exception):
    pass


class _FakeHTTP:
    def stream(self, method, url, json=None, **kw):
        sent["messages"] = list((json or {}).get("messages") or [])
        raise _Boom()


cl._client = _FakeHTTP()
try:
    list(cl.chat_stream(messages=msgs))
except _Boom:
    pass
except Exception as exc:                                  # pragma: no cover
    check("the fake transport was reached", False, repr(exc))
check("the client TRIMMED before sending — the daemon never sees the overrun",
      sent.get("messages") and len(sent["messages"]) < len(msgs),
      (len(sent.get("messages") or []), len(msgs)))
check("...to something under the ceiling",
      C.est_tokens(sent["messages"]) <= C.budget(), C.est_tokens(sent["messages"]))
check("...and the client REPORTS it, the way it reports kairos",
      cl.last_trim and cl.last_trim["dropped"] > 0, cl.last_trim)
check("the system prefix went through untouched", sent["messages"][0]["role"] == "system")

cl2 = SPDaemonClient(base_url="http://127.0.0.1:9")
cl2._client = _FakeHTTP()
try:
    list(cl2.chat_stream(messages=small))
except _Boom:
    pass
check("a conversation that fits is sent whole and reports NO trim",
      cl2.last_trim is None and len(sent["messages"]) == len(small), cl2.last_trim)

line = C.notice({"dropped": 6, "kept": 9, "before": 13000, "after": 8000, "budget": 11328})
check("the notice says what was lost, in his terms", "6 older turns" in line, line)
check("...and that she still has the recent turns and her memory",
      "memory" in line and "recent" in line, line)
app = open(os.path.join(ROOT, "harness", "server", "app.py"),
           encoding="utf-8", errors="replace").read()
check("the gateway emits it on the turn it happened",
      'evq.put({"notice": _ctx.notice(_trim)})' in app)
check("...read off the client the same way last_kairos is",
      'getattr(get_client(), "last_trim", None)' in app)
chat = open(os.path.join(ROOT, "ui", "src", "Chat.jsx"),
            encoding="utf-8", errors="replace").read()
# AMENDED 2026-08-24: this read `"ev.notice) last.events"`, which asserted that
# `notice` was the LAST name in the event-routing condition. A wear event joined the
# list beside it and the check went red on a line that still does exactly what it
# claims. The claim is that a notice is routed to `events` and rendered as a chip -
# assert that, not which siblings it happens to stand next to.
check("the room keeps a notice as an ACT, not as her words",
      "ev.notice" in chat and "last.events = [...last.events, ev]" in chat
      and "act-notice" in chat)
css = open(os.path.join(ROOT, "ui", "src", "room.css"),
           encoding="utf-8", errors="replace").read()
check("...and the chip has a style, so it is not an invisible div",
      ".act-notice" in css)

print("\n7. THE FOREIGN BACKEND ANSWERS HONESTLY RATHER THAN NOT AT ALL")
from harness.inference.backends.openai import OpenAIClient  # noqa: E402
check("openai carries last_trim as None (no pmax, so nothing to report)",
      OpenAIClient(base_url="http://127.0.0.1:9").last_trim is None)

print("\n8. THE CUT IS STICKY, OR EVERY TURN PAYS FOR IT (2026-08-28, live)")
# The evening his conversation first crossed pmax, fit() re-cut newest-first on every
# call, so each turn kept a slightly different window (23 dropped, 23, then 26...). The
# window's FRONT is where the daemon's committed KV must match, so every turn found no
# seam (PERSIST-KV RESEAM drop 437), fell to the full-prefill floor, and re-prefilled
# ~10,300 tokens at 20 ms/tok. MEASURED: 235.4 s, 222.5 s, 207.4 s per ordinary turn —
# reported as "the gateway is frozen", because a four-minute reply and a hang look the
# same from the room. Point 3 of this file's own header claimed the kept window was
# stable; it never was, because the trimmed list is not what the room sends next turn.
from harness.inference import context as C  # noqa: E402
C._STICKY_CUT = None
_m = [{"role": "system", "content": "S" * 400}]
for _i in range(30):
    _m += [{"role": "user", "content": "u%d " % _i + "x" * 380},
           {"role": "assistant", "content": "a%d " % _i + "y" * 380}]
_f1, _t1 = C.fit(list(_m), reply_headroom=0, limit=3000)
check("a fresh overflow cuts (the pre-existing behaviour)",
      _t1 is not None and _t1["dropped"] > 0, _t1)
_m2 = list(_m) + [{"role": "user", "content": "u30 " + "x" * 60},
                  {"role": "assistant", "content": "a30 " + "y" * 60}]
_f2, _t2 = C.fit(_m2, reply_headroom=0, limit=3000)
check("one new exchange later, the cut does NOT move — same first kept message",
      _f2[1]["content"] == _f1[1]["content"] and _t2 and _t2.get("sticky") is True,
      (_f1[1]["content"][:10], _f2[1]["content"][:10], _t2))
_m3 = list(_m2)
for _i in range(31, 45):
    _m3 += [{"role": "user", "content": "u%d " % _i + "x" * 380},
            {"role": "assistant", "content": "a%d " % _i + "y" * 380}]
_f3, _t3 = C.fit(_m3, reply_headroom=0, limit=3000)
check("...and a genuine overflow re-cuts fresh, once, with the slack that buys quiet turns",
      _t3 is not None and not _t3.get("sticky") and _f3[1]["content"] != _f1[1]["content"],
      _t3)
check("...never returning something over the budget",
      C.est_tokens(_f2) <= _t2["budget"] and C.est_tokens(_f3) <= _t3["budget"])
_f4, _t4 = C.fit(list(_m[:5]), reply_headroom=0, limit=3000)
check("a short prompt is untouched even while a sticky cut exists", _t4 is None)
C._STICKY_CUT = None

finish("G-CONTEXT-FIT")
