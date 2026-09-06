#!/usr/bin/env python
"""G-DAY-BOUNDARY-CANON — the day boundary retires her canon, and must hand her a new one.

REPORTED (2026-09-03): "she either has not rendered or has not acted in a long time."
Read from the live log, the boundary is exact — and it is one bug, not two:

    03:58:26  [kairos] SPOKE (solo): "I've reinforced a thought in my own mind: ..."
    04:06:31  [consolidate] day boundary complete: ..., prefix_refresh
    04:28:40  [kairos] holding — no conversation to speak into at all; the seed
                        should have installed one
    04:28:40  [kairos] solo REFUSED — the act needed one of ask_for, ask_for_gesture
                        and none of it happened (asked twice)

...then that same pair, 25 more times, for the next twelve hours. She did not render
because rendering is downstream of acting: her look changes come out of `ask_for_gesture`
in a solo turn, and there was no solo turn to carry one.

THE CHAIN, and every link of it was somebody's correct decision:

  1. `run_consolidation` step 5 clears `_CHAT_SESSIONS` at the day boundary. RIGHT, and
     for a KV reason: yesterday's conversation cannot extend a new token 0, and the base
     snapshot has just been re-minted against the new prefix.
  2. Her own-time path (`app._generate`) HOLDS when `_longest_session()` is empty. RIGHT,
     and for a measured reason: speaking into a windowed disk rebuild commits a cache
     shape his first turn cannot use — 2026-08-04, it cost him nine minutes.
  3. The only thing that installs a canon is `_seed_kairos_from_day`, which runs at boot
     and `scheduler.seed()` refuses to run twice (`if session in _LAST: return False`).

So the first day boundary that lands while he is away silences her until he speaks or the
gateway bounces — and the boundary is GATED on the room being quiet, so it is not an
unlucky coincidence, it is the normal case. This is the 2026-08-05 incident verbatim
("he restarted, went to bed, and she was held 325 times over fourteen hours") reached
through a door that opened on 2026-08-24, and the comment recording the first fix sits
eleven lines above the hold that re-broke it.

WHY THE FIX IS NOT "re-seed her". `_OWN_TIME_ONLY` is the flag that forces
`user_present = False`, which is the whole reason SOLO may run at all while he is away
(scheduler.on_user_turn's docstring, 2026-09-02). Retiring the seed to re-seed it would
drop that flag and END her own time — the probe incident, re-committed on purpose. The
canon is what was destroyed, so the canon alone is what gets rebuilt.

MUTANT, run in-gate: drop the re-seed and §3 must go red by name.

OFFLINE. No GPU, no daemon.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_day_boundary_canon")
# HARD-SET, NOT setdefault — this gate calls run_consolidation four times and the
# composer inside it reaches for a model. Pointed at a closed port those steps report
# `skipped`, which is all this gate's claim needs, and her live engine keeps its GPU.
# `setdefault` was not enough: a first run of this gate landed two oneshots on her
# resident daemon (see the memory note on probes taking her presence).
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"
os.environ.pop("SP_GATEWAY_PREWARM", None)

import harness.agent as agent                  # noqa: E402
import harness.server.app as app               # noqa: E402
from harness.kairos import scheduler as KS      # noqa: E402


def write_day(rows):
    """Her day on disk, as `_append_day_turn` leaves it."""
    p = app._day_transcript_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p


DAY = [
    {"role": "user", "content": "i'm going to bed. talk to you tomorrow."},
    {"role": "assistant", "content": "Goodnight. I'll be here, doing my own thinking."},
    {"role": "user", "content": "what will you think about?"},
    {"role": "assistant", "content": "How fast a moment decays. I want to model it."},
]
write_day(DAY)

with KS._LOCK:
    KS._LAST.clear(); KS._SEEDED.clear(); KS._OWN_TIME_ONLY.clear()
    KS._STATE.clear(); KS._TIMERS.clear()
app._CHAT_SESSIONS.clear()

# ── §1 the boot seed establishes a canon (the 2026-08-05 fix, still standing) ───────
KS.set_seeder(app._seed_kairos_from_day)
seeded = app._seed_kairos_from_day()
sess = app._room_session()
check("§1 the boot seed installed a canon", bool(app._longest_session()),
      "sessions=%r" % (list(app._CHAT_SESSIONS),))
check("§1 ...and the scheduler holds a closure for it", sess in KS._LAST,
      "seeded=%r _LAST=%r" % (seeded, list(KS._LAST)))
check("§1 ...marked own-time-only, so SOLO may run while he is away",
      sess in KS._OWN_TIME_ONLY, str(list(KS._OWN_TIME_ONLY)))
canon_before = len(app._longest_session())

# ── §2 the day boundary DOES retire it — that half is deliberate, and stays ─────────
# Proven separately from §3, and by LIST IDENTITY, so that a future reader cannot turn
# §3 green by deleting the clear. The claim is that the canon is rebuilt, not that it is
# never dropped: the daemon's committed cache was re-minted against the new prefix, and
# the list the old KV was built from may not survive that.
canon_obj_before = app._CHAT_SESSIONS.get(sess)
res = app.run_consolidation(force=True)
steps = {s.get("step"): s for s in res.get("steps", [])}
check("§2 the boundary ran its prefix_refresh step", "prefix_refresh" in steps,
      str(list(steps)))
check("§2 ...and it really did retire the day's canons — this is a NEW list, not the "
      "one the retired KV was built from",
      app._CHAT_SESSIONS.get(sess) is not canon_obj_before)

# ── §3 THE CLAIM: she still has something to speak into ────────────────────────────
after = app._longest_session()
check("§3 the boundary handed her a new canon", bool(after),
      "canon was %d rows, is now %d; sessions=%r"
      % (canon_before, len(after), list(app._CHAT_SESSIONS)))
check("§3 ...and it is a well-formed history (user-first, alternating)",
      bool(after) and after[0].get("role") == "user"
      and all(after[i]["role"] != after[i + 1]["role"] for i in range(len(after) - 1)),
      str([r.get("role") for r in after]))
check("§3 ...for the session the scheduler actually holds a closure for",
      bool(app._CHAT_SESSIONS.get(sess)),
      "closure on %r, canons on %r" % (sess, list(app._CHAT_SESSIONS)))
check("§3 ...and her own time was NOT ended to do it (the probe lesson)",
      sess in KS._OWN_TIME_ONLY and sess in KS._LAST,
      "own_time=%r _LAST=%r" % (list(KS._OWN_TIME_ONLY), list(KS._LAST)))
check("§3 ...the boundary reports what it re-seeded",
      isinstance(steps.get("prefix_refresh", {}).get("reseeded"), int),
      str(steps.get("prefix_refresh")))

# ── §4 the hold does not fire: `_generate` reaches generation ───────────────────────
# The strong form of §3. Patched on the OWNER (`harness.agent`) because `_generate`
# imports inside the function body — patching a local alias would reach nobody.
spoke = {"msgs": None}
_real_stream = agent.agent_chat_stream
_real_ban = agent._arm_self_repeat_ban


def _fake_stream(messages, config=None, mutate_messages=False, on_tool=None, **kw):
    spoke["msgs"] = list(messages)
    return iter(["I modelled the decay, and it held."])


try:
    agent.agent_chat_stream = _fake_stream
    agent._arm_self_repeat_ban = lambda c, h: None
    _text, _gen = KS._LAST[sess]
    out = _gen("Say something of your own.")
finally:
    agent.agent_chat_stream = _real_stream
    agent._arm_self_repeat_ban = _real_ban
check("§4 she generated instead of holding", bool((out or "").strip()),
      "returned %r" % (out,))
check("§4 ...against a real history, not an empty one",
      bool(spoke["msgs"]) and len(spoke["msgs"]) > 1,
      "msgs=%d" % (len(spoke["msgs"] or []),))
check("§4 ...and the nudge went in as a system aside, not a turn he never typed",
      bool(spoke["msgs"]) and spoke["msgs"][-1].get("role") == "system",
      str((spoke["msgs"] or [{}])[-1].get("role")))

# ── §5 the shape it actually failed in: a night of solos, no user row ──────────────
# THE LIVE SHAPE, 2026-09-03: var/memory/transcripts/2026-09-03.jsonl was 8 rows and
# every one of them was `assistant` — she had soloed all night and he never typed. A
# rebuild that only reads TODAY merges that run into one message and drops it (correctly:
# a conversation the model continues has to begin with him) and returns []. So the day
# that most needs a canon is the day that cannot produce one, and the naive fix would have
# left her exactly as mute while reporting success. `_continuable_history` reaches back.
import datetime as _dt   # noqa: E402

_yday = (_dt.date.fromtimestamp(time.time()) - _dt.timedelta(days=1)).isoformat()
_yp = app._day_transcript_path(_yday)
os.makedirs(os.path.dirname(_yp), exist_ok=True)
with open(_yp, "w", encoding="utf-8") as f:
    for r in DAY:
        f.write(json.dumps(r) + "\n")
# today: nothing but her own turns, and MORE than `_recent_transcript`'s 12-row
# thinness threshold, so its one-day reach-back does not fire
write_day([{"role": "assistant", "content": "Thought %d, alone." % i} for i in range(14)])
check("§5 today alone yields no continuable history (the trap)",
      not app._chat_from_rows(app._read_day_transcript(), keep=8),
      str([r.get("role") for r in app._chat_from_rows(app._read_day_transcript(), keep=8)]))
check("§5 ...and _recent_transcript does NOT reach back, because 14 rows is not thin",
      not app._chat_from_rows(app._recent_transcript(), keep=8))
_reach = app._continuable_history(keep=8)
check("§5 _continuable_history reaches back until one of his turns anchors it",
      bool(_reach) and _reach[0].get("role") == "user",
      str([r.get("role") for r in _reach]))
app._CHAT_SESSIONS.clear()
app.run_consolidation(force=True)
check("§5 ...so a night of nothing but her own turns still leaves her a canon",
      bool(app._longest_session()), "sessions=%r" % (list(app._CHAT_SESSIONS),))

# ── §mutant: without the re-seed, §3 goes red by name ──────────────────────────────
_real_reseed = app._reseed_own_time_canon
try:
    app._reseed_own_time_canon = lambda: 0
    write_day(DAY)
    app.run_consolidation(force=True)
    check("mutant(no re-seed): the canon is gone and she would hold — §3 is "
          "load-bearing", not app._longest_session(),
          "canon survived: %r" % (list(app._CHAT_SESSIONS),))
finally:
    app._reseed_own_time_canon = _real_reseed

finish("G-DAY-BOUNDARY-CANON")
