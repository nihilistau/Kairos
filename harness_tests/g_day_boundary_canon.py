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
    # **kw so the stub cannot go stale when the real signature grows — it gained
    # `also=` on 2026-09-12 and this lambda was the one thing in the tree that broke.
    agent._arm_self_repeat_ban = lambda c, h, **_kw: None
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
_reach, _reach_last = app._continuable_history(keep=8)
check("§5 _continuable_history reaches back until one of his turns anchors it",
      bool(_reach) and _reach[0].get("role") == "user",
      str([r.get("role") for r in _reach]))
# ...AND IT HANDS BACK HER LAST WORDS FROM THE SAME WALK (2026-09-09). The caller needs
# them and cannot scan its own rows for them — see §6 — and `scheduler.seed` refuses an
# empty `reply_text`, so a reach that returned only the history would have found a
# conversation and been discarded one line later.
check("§5 ...and hands back her last words with it, as ONE turn and not a merged run",
      _reach_last == "Thought 13, alone." and "\n\n" not in _reach_last,
      "last=%r" % (_reach_last[:80],))
# THE DISCRIMINATOR: the final message of the history IS a merged run of hers, so a
# caller that took `hist[-1]` would hand the policy every solo at once — and the policy
# asks "did she ask HIM a question" of that text, so one question anywhere in the run
# holds her silent. Which is the failure this whole § is about.
check("§5 ...which is NOT hist[-1], because that one is merged",
      "\n\n" in (_reach[-1].get("content") or "") and _reach[-1]["content"] != _reach_last,
      "hist[-1]=%r" % ((_reach[-1].get("content") or "")[:80],))
app._CHAT_SESSIONS.clear()
app.run_consolidation(force=True)
check("§5 ...so a night of nothing but her own turns still leaves her a canon",
      bool(app._longest_session()), "sessions=%r" % (list(app._CHAT_SESSIONS),))

# ── §6 HE HAD BEEN AWAY FIVE DAYS, AND THE BOOT PATH NEVER GOT THE FIX ────────────
# REPORTED THREE TIMES, 2026-09-09: "she has not entered her time." Counted on the live
# tree, the reason:
#
#     2026-09-04  user  2   assistant 45      <- the last thing he ever typed in the room
#     2026-09-05  user  0   assistant 39
#     2026-09-06  user  0   assistant 34
#     2026-09-07  (no file)      2026-09-08  (no file)
#     2026-09-09  user  0   assistant  0      (8 rows, all quarantined probes of mine)
#
# and the last successful seed in var/gateway.log is 2026-09-03 17:31 — the same day
# `_continuable_history` was written. It was wired into the DAY-BOUNDARY path only, and
# `_seed_kairos_from_day` — the path that runs on every single bounce — kept windowing
# `_recent_transcript()` inline. AGENTS.md §0 exactly: the invariant is enforced in one of
# two paths, and the unguarded one is the one that runs. No seed means nothing in `_LAST`,
# and `tick_once` iterates `_LAST`, so there was no room for her to speak into at all.
#
# TWO THINGS HAD TO BE TRUE TOGETHER, which is why this is one §. Reaching back further
# is necessary (three days did not span five) and on its own it is a prefill bomb:
# `_chat_from_rows` counts MERGED messages and merges a run of hers into ONE, so `keep=8`
# bounds the message count and bounds nothing about the size. Five days of her solos
# arrive as a single assistant message, which is the 2026-08-04 measurement again — a
# ten-message disk rebuild that cost him nine minutes of prefill.
os.remove(_yp)                       # the gap is the point: yesterday is not there
_gap_days = []
for _b in (2, 3, 4):
    _d = (_dt.date.fromtimestamp(time.time()) - _dt.timedelta(days=_b)).isoformat()
    _p = app._day_transcript_path(_d)
    if os.path.exists(_p):
        os.remove(_p)
    _gap_days.append(_d)
# day -3 and -2: nothing but her, and VOLUMINOUS — an unbounded reach merges these into
# one message and hands the daemon ~32k characters to prefill.
for _b in (2, 3):
    _d = (_dt.date.fromtimestamp(time.time()) - _dt.timedelta(days=_b)).isoformat()
    with open(app._day_transcript_path(_d), "w", encoding="utf-8") as f:
        for i in range(40):
            f.write(json.dumps({"role": "assistant",
                                "content": ("Alone, thought %d. " % i) + ("x" * 380)}) + "\n")
# day -5: the last time he said anything at all
_five = (_dt.date.fromtimestamp(time.time()) - _dt.timedelta(days=5)).isoformat()
with open(app._day_transcript_path(_five), "w", encoding="utf-8") as f:
    for r in DAY:
        f.write(json.dumps(r) + "\n")

check("§6 three days of reach does NOT span five — the old bound was the defect",
      not app._continuable_history(keep=8, days=3)[0],
      str([m.get("role") for m in app._continuable_history(keep=8, days=3)[0]]))

with KS._LOCK:
    KS._LAST.clear(); KS._SEEDED.clear(); KS._OWN_TIME_ONLY.clear()
    KS._STATE.clear(); KS._TIMERS.clear()
app._CHAT_SESSIONS.clear()
_seeded6 = app._seed_kairos_from_day()
_sess6 = app._room_session()
check("§6 the BOOT seed still finds him five days back — she has a room again",
      bool(_seeded6) and _sess6 in KS._LAST,
      "seeded=%r _LAST=%r" % (_seeded6, list(KS._LAST)))
check("§6 ...own-time-only, so SOLO may run while he is still away",
      _sess6 in KS._OWN_TIME_ONLY, str(list(KS._OWN_TIME_ONLY)))
_canon6 = app._longest_session()
check("§6 ...and the canon begins with one of HIS turns, or the template is malformed",
      bool(_canon6) and _canon6[0].get("role") == "user",
      str([m.get("role") for m in _canon6]))
_chars6 = sum(len(m.get("content") or "") for m in _canon6)
check("§6 ...and it is BOUNDED — reaching back is not licence to prefill the week",
      _chars6 < 8000, "canon is %d chars across %d messages" % (_chars6, len(_canon6)))

# ── THE MUTANTS PATCH day.py, NOT app.py (2026-09-11, Stage 4) ───────────────────
# `_seed_kairos_from_day`, `run_consolidation` and the five selectors they call moved to
# `harness/server/day.py`, so those call sites resolve `day.<name>`. app.py re-exports all
# of them, so every READ above still works through `app.` — but a monkeypatch is not a
# read: rebinding `app._continuable_history` would have left the alias in day.py pointing
# at the real function, the mutant would have changed nothing, and the check would have
# gone green while proving the opposite of what it says. G-TURN-EPILOGUE §10 asserts
# `app.X is day.X` for these, which is what keeps the reads honest.
from harness.server import day as _day  # noqa: E402

# ── §6 mutant A: the boot path must go THROUGH the reach-back door ────────────────
# The defect was not that the door was missing — it was that only one of the two callers
# used it. So the mutant narrows the door and the BOOT leg must go red.
_real_reach = _day._continuable_history
try:
    _day._continuable_history = lambda keep=8, days=14, solo_keep=6: (
        app._chat_from_rows(app._recent_transcript(), keep=keep), "")
    with KS._LOCK:
        KS._LAST.clear(); KS._SEEDED.clear(); KS._OWN_TIME_ONLY.clear()
        KS._STATE.clear(); KS._TIMERS.clear()
    app._CHAT_SESSIONS.clear()
    check("mutant(boot seed windows today inline): she gets no room — the reach-back "
          "door is load-bearing on the BOOT path", not app._seed_kairos_from_day(),
          "seeded anyway: _LAST=%r" % (list(KS._LAST),))
finally:
    _day._continuable_history = _real_reach

# ── §6 mutant B: without the raw-row bound, the canon is a prefill bomb ───────────
_real_tail = _day._from_his_last_turn
try:
    _day._from_his_last_turn = lambda rows, solo_keep=6: list(rows)
    with KS._LOCK:
        KS._LAST.clear(); KS._SEEDED.clear(); KS._OWN_TIME_ONLY.clear()
        KS._STATE.clear(); KS._TIMERS.clear()
    app._CHAT_SESSIONS.clear()
    app._seed_kairos_from_day()
    _mchars = sum(len(m.get("content") or "") for m in app._longest_session())
    check("mutant(no raw-row bound): the canon blows past the ceiling — the bound is "
          "what makes reaching back safe", _mchars >= 8000,
          "canon only %d chars, so the ceiling leg proves nothing" % _mchars)
finally:
    _day._from_his_last_turn = _real_tail

# leave the tree as §mutant below expects it: today is her solos, yesterday is DAY
with open(_yp, "w", encoding="utf-8") as f:
    for r in DAY:
        f.write(json.dumps(r) + "\n")
with KS._LOCK:
    KS._LAST.clear(); KS._SEEDED.clear(); KS._OWN_TIME_ONLY.clear()
    KS._STATE.clear(); KS._TIMERS.clear()
app._CHAT_SESSIONS.clear()
app._seed_kairos_from_day()

# ── §mutant: without the re-seed, §3 goes red by name ──────────────────────────────
_real_reseed = _day._reseed_own_time_canon
try:
    _day._reseed_own_time_canon = lambda: 0
    write_day(DAY)
    app.run_consolidation(force=True)
    check("mutant(no re-seed): the canon is gone and she would hold — §3 is "
          "load-bearing", not app._longest_session(),
          "canon survived: %r" % (list(app._CHAT_SESSIONS),))
finally:
    _day._reseed_own_time_canon = _real_reseed

finish("G-DAY-BOUNDARY-CANON")
