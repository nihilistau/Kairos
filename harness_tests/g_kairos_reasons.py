"""G-KAIROS-REASONS — the half that was computed and thrown away.

Everything she could say came from a latent signal (CONTINUE) or a clock plus a coin flip
(CHECK_IN), and the coin flip was the one that reached him. "Just a timer" was an accurate
description, and not for want of signal: three of the richest things this system knows
were computed daily and consulted by nobody —

  * her own journal paragraph, written nightly and read only into her prefix;
  * `task_bridge.summary()`, THE definition of an open commitment, rendered as context and
    never as "I said I'd do that";
  * `presence.jsonl` turns-per-day — only `> 0` was ever read, so the shape of his week
    was written down and discarded.

WHAT THIS GATE HOLDS:

  * A REASON DOES NOT DECIDE ANYTHING. It travels the existing MUSE channel in the shape
    reflection already uses, so `impulse.decide()` — a committed 512-cell table — is
    untouched and every bound it enforces still binds.
  * SHE RAISES A THING ONCE. A raised key is durable, and the same reason never returns.
  * A CONCLUSION OUTRANKS A REASON, and a HELD conclusion outranks one too. A thought she
    reached tonight must not be displaced by something she has been carrying for a week.
  * THE DATE GUARD. narrative.py writes "Saturday 01 August 2026"; everything else speaks
    ISO. The first version compared them directly, never matched, and offered her TODAY's
    journal entry back to him — the very conversation he had just had.
  * RHYTHM IS INERT AND SAYS SO, and the RULE is what protects him rather than the wait.
    Backtested on his real ledger — seven present days spanning a nine-fold range of
    turns-per-day — "below half the median" fired on a day whose count had already
    occurred earlier that same week, an ordinary day for him, purely because two heavy
    days had dragged the median far above typical. "Quieter than the quietest day he has
    ever had" fired zero times, needs no tuned constant, and gets rarer as it learns
    him. (His actual counts are his; every fixture below is synthetic and carries the
    same skew.) So the ledger depth is 7 rather than silence.py's 14, deliberately:
    silence.py needs a per-topic CADENCE, this needs a FLOOR.

Offline. Every source is pure — data in, proposal out.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["CUDA_VISIBLE_DEVICES"] = ""

SB = os.path.join(tempfile.gettempdir(), "_g_kairos_reasons")
shutil.rmtree(SB, ignore_errors=True)
os.makedirs(SB)
os.environ["SP_RECALL_REGISTRY"] = os.path.join(SB, "registry.jsonl")

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s %s" % (name, detail))


from harness.kairos import reasons as R                                    # noqa: E402
# SYNTHETIC CLOCKS (2026-08-22): a fresh TurnState's clocks default to impulse.BOOT_AT, the
# real monotonic boot time, which would sit in this gate's small fixture times' FUTURE.
# Pin the boot to t=1.0 here — non-zero, before every `now` below.
import harness.kairos.impulse as _imp_pin  # noqa: E402
_imp_pin.BOOT_AT = 1.0
from harness.kairos.impulse import MUSE, SILENT, KairosConfig, TurnState   # noqa: E402
from harness.kairos.impulse import decide, muse_nudge, note_user           # noqa: E402

TODAY = "2026-08-01"
NOTES = [{"id": "n2", "title": "wire the favicon", "ts": "2026-07-30"},
         {"id": "n1", "title": "finish the seam measurement", "ts": "2026-07-28",
          "task_status": "running"}]
JOURNAL_OLD = ("As of Friday 31 July 2026: We got the model running properly and he "
               "stayed up far too late with it.")
JOURNAL_TODAY = "As of Saturday 01 August 2026: Today we talked about my sense of self."

print("1. WHAT IS STILL OPEN becomes something she can say")
r = R.from_commitment(NOTES, set())
check("the OLDEST commitment is the one she raises", r and r["text"] == "finish the seam measurement", r)
check("...carrying the fact that she already started it", r.get("running") is True)
check("...and a key so it can be raised exactly once", r["raise_key"] == "commitment:n1")
check("once raised, she moves to the next one",
      R.from_commitment(NOTES, {"commitment:n1"})["text"] == "wire the favicon")
check("with all of them raised she says nothing rather than repeating",
      R.from_commitment(NOTES, {"commitment:n1", "commitment:n2"}) is None)
check("an empty board is silence, not an error", R.from_commitment([], set()) is None)

print("\n2. HER JOURNAL — and the date guard the first version got wrong")
check("an entry from a previous day is something she has been carrying",
      (R.from_journal(JOURNAL_OLD, TODAY, set()) or {}).get("raise_key") == "journal:2026-07-31")
check("TODAY's entry is NOT offered back to him — he was in that conversation",
      R.from_journal(JOURNAL_TODAY, TODAY, set()) is None)
check("...and that is decided on a real date, not a string compare",
      "strptime" in io.open(os.path.join(ROOT, "harness", "kairos", "reasons.py"),
                            encoding="utf-8").read())
check("each entry is raised once", R.from_journal(JOURNAL_OLD, TODAY,
                                                  {"journal:2026-07-31"}) is None)
check("an unparseable date is not treated as a day that has passed",
      R.from_journal("As of some time ago: things happened.", TODAY, set()) is None)
check("no journal, no reason", R.from_journal("", TODAY, set()) is None)

print("\n3. HIS RHYTHM is inert, and says why")
thin = {"2026-07-%02d" % d: 40 for d in range(28, 32)}          # 4 present days
thin[TODAY] = 2
check("a ledger too thin to have a floor proposes nothing",
      R.from_rhythm(thin, TODAY, set()) is None)
deep = {"2026-07-%02d" % d: 40 for d in range(25, 32)}          # 7 present days
deep[TODAY] = 2
check("...but a deep enough one notices a day quieter than any he has had",
      (R.from_rhythm(deep, TODAY, set()) or {}).get("kind") == "rhythm")
check("an ordinary day is not a remark", R.from_rhythm(dict(deep, **{TODAY: 40}),
                                                       TODAY, set()) is None)
# THE SHAPE OF THE FALSE POSITIVE THAT CHOSE THIS RULE. On his real ledger the median
# rule fired on a day whose turn count had already occurred earlier that week — a
# perfectly ordinary day — because two heavy days had dragged the median far above
# typical. A rank cannot be dragged. SYNTHETIC numbers with that same skew; his are his.
real = {"2026-07-13": 40, "2026-07-14": 240, "2026-07-15": 25, "2026-07-29": 160,
        "2026-07-30": 25, "2026-07-31": 60, TODAY: 40}
# The distortion case, sized so it actually REACHES the rule. Slicing his real ledger at
# 30 July left only four present days, so the depth guard returned None first and this
# check passed without ever exercising the comparison — the third green today that proved
# nothing. Seven prior days, median dragged far above typical by the heavy ones, today
# an ordinary count that has already occurred twice: the median rule fires, a rank cannot.
skewed = {"2026-07-%02d" % d: v for d, v in
          zip(range(20, 27), (25, 40, 25, 160, 240, 200, 180))}
skewed[TODAY] = 25
check("an ordinary day is not a remark just because heavy days preceded it",
      R.from_rhythm(skewed, TODAY, set()) is None,
      "median of prior = %d, today = 25" % sorted(v for k, v in skewed.items()
                                                  if k != TODAY)[3])
check("...and it stays silent on an ordinary day with that same skew",
      R.from_rhythm(real, TODAY, set()) is None)
check("a genuinely unprecedented quiet day IS noticed",
      (R.from_rhythm(dict(real, **{TODAY: 3}), TODAY, set()) or {}).get("kind") == "rhythm")
check("the rule needs no tuned fraction at all",
      "0.5" not in io.open(os.path.join(ROOT, "harness", "kairos", "reasons.py"),
                           encoding="utf-8").read().split("def from_rhythm")[1].split("def ")[0])
check("the arming condition is stated where he will find it",
      "present days" in R.why_quiet(), R.why_quiet())
check("...and it differs from silence.py's on purpose, with the reason written down",
      R.MIN_LEDGER_DAYS != __import__("harness.skills.silence", fromlist=["x"]).MIN_LEDGER_DAYS
      and "PER-TOPIC CADENCE" in io.open(
          os.path.join(ROOT, "harness", "kairos", "reasons.py"), encoding="utf-8").read())

print("\n4. SHE RAISES A THING ONCE — durably")
check("nothing is raised yet", not R.raised_keys())
R.mark_raised("commitment:n1")
check("a raised key persists", "commitment:n1" in R.raised_keys())
check("...and it is a file, so a restart does not make her repeat herself",
      os.path.exists(R._raised_path()))
R.mark_raised("commitment:n1")
check("marking twice does not corrupt the ledger", R.raised_keys() == {"commitment:n1"})

print("\n5. A REASON OBEYS THE POLICY — it does not become a new authority")
CFG = KairosConfig(enabled=True, max_chain=2, cooldown_s=45.0, max_per_hour=6)
st = TurnState()
note_user(st, 1000.0)
reason = R.from_commitment(NOTES, set())
# (2026-08-22: a musing waits for the room to be quiet — checkin_idle_s — like any other
#  unprompted word, so the reason is offered after that floor, not 10 s after his turn)
imp = decide(cfg=CFG, state=st, now=1000.0 + CFG.checkin_idle_s + 1.0, reply_text="ok.",
             eot_margin=None, insight=reason)
check("a reason speaks through MUSE, the channel that already existed",
      imp.action == MUSE, imp)
st2 = TurnState(chain=2, last_user_at=1000.0)
check("...and the chain limit still rules it",
      decide(cfg=CFG, state=st2, now=1010.0, reply_text="ok.", eot_margin=None,
             insight=reason).action == SILENT)
st3 = TurnState(last_spoke_at=1000.0, last_user_at=900.0)
check("...and so does the cooldown",
      decide(cfg=CFG, state=st3, now=1010.0, reply_text="ok.", eot_margin=None,
             insight=reason).action == SILENT)
sched = io.open(os.path.join(ROOT, "harness", "kairos", "scheduler.py"),
                encoding="utf-8").read()
check("a reason is consulted only when she has concluded nothing",
      "if not insight:" in sched and
      sched.index("_PENDING_INSIGHT.items()") < sched.index("_R.propose()"))

print("\n6. AND SHE IS TOLD THE RIGHT THING TO SAY")
# One channel, three quite different things to say. Handing a commitment to the
# conclusion nudge would have her announce that she has come to BELIEVE she owes him a
# favicon — the sort of wrong that costs a channel its credibility.
n_com = muse_nudge(reason)
n_jou = muse_nudge(R.from_journal(JOURNAL_OLD, TODAY, set()))
n_rhy = muse_nudge(R.from_rhythm(deep, TODAY, set()))
check("a commitment is framed as something still open",
      "still open between you" in n_com and "seam measurement" in n_com)
check("...and never as a conclusion she has drawn about him",
      "came to a conclusion" not in n_com)
check("a journal line is framed as hers, and she is told not to read it out",
      "your journal" in n_jou and "Do NOT read the entry out" in n_jou)
check("a rhythm remark is told to carry no numbers and no diagnosis",
      "no numbers" in n_rhy and "keeping score" in n_rhy)
check("every reason still has permission to say nothing",
      all("say nothing at all" in n for n in (n_com, n_jou, n_rhy)))

shutil.rmtree(SB, ignore_errors=True)
print("\nG-KAIROS-REASONS: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_kairos_reasons.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_kairos_reasons", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
