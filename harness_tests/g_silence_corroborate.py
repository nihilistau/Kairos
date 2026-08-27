#!/usr/bin/env python
"""G-SILENCE-CORROBORATE — a silence he has spoken to is not a silence.

WHAT THIS ANSWERS. `PersonModel.silences()` measured `quiet` as days since a claim's ROW
was last minted, and called that "days since he mentioned it". Those are different
quantities, and the store's own dedup opens the gap: a restatement that supersedes or
matches an existing row does not move `last`. A claim he repeats constantly — whose
repeats are exactly what dedup collapses — goes quiet in the registry while the behaviour
never stops.

MEASURED over three days of a real gateway.log. An affectionate line the operator repeats
daily was minted once and never re-minted, so it ranked as the loudest absence on
essentially every idle tick for three days (fourteen firings; quiet 2.0d -> 3.0d, bits
2.0 -> 3.0), and the muse lane spoke it: an unprompted line asking whether he still felt
the same, sent TWELVE MINUTES after he had said the very thing it accused him of dropping
and she had answered in kind.

The fix is not a list of tender phrases to skip; it is to measure the quantity the
docstring already claims to measure, against the record that knows it: HIS OWN TURNS.

  1. THE REGRESSION ITSELF — his real shape: a claim minted once, restated in his turns,
     is proposed WITHOUT corroboration and refuted WITH it.
  2. A GENUINE SILENCE SURVIVES — this is not "always refute".
  3. IT FAILS CLOSED when the transcript cannot be read, which is this function's own
     thesis ("absence is only information if you can prove you were looking").
  4. CONTAINMENT, NOT OVERLAP — a claim sharing one word with an unrelated turn is not
     ruled spoken.
  5. BOTH DOORS. The ambient door (scheduler) may not admit a silence on thinner evidence
     than the answer-time door (skills/silence.py) demands, and it reads ONE authority for
     the floor rather than restating the number.

OFFLINE. No GPU, no daemon.
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from _gate import sandbox   # noqa: E402
sandbox("g_silence_corroborate")

os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"

from harness.model import person as P            # noqa: E402
from harness.model.person import PersonModel     # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


NOW = time.time()
DAY = 86400.0


class Calendar:
    """He was present every day. Attention is not what this gate is about."""

    def attended_days(self, t0, t1):
        return max(0.0, (t1 - t0) / DAY)

    def present_days_total(self):
        return 90


def _registry(rows):
    """Write a registry the real from_registry() will read, inside the sandbox."""
    p = os.environ["SP_RECALL_REGISTRY"]          # the sandbox owns this path
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return p


def _row(claim, name, mentions=3, first_ago=12 * DAY, last_ago=10 * DAY):
    """One row carrying its own rhythm — the shape absorb() actually reads.

    `text` is the field the model ranks (see _slot_for / Dimension); `topic` is the
    registry's 40-char display key and is NOT it. `mentions`/`first_seen`/`last_seen` live
    ON the row: absorb() does not aggregate across rows, so three separate rows are three
    one-mention claims and never clear min_mentions.
    """
    return {"name": name, "text": claim, "topic": claim[:40], "npos": 1, "lifecycle": 0,
            "speaker": "user", "status": "observed", "ts": _iso(last_ago),
            "mentions": mentions, "first_seen": _iso(first_ago),
            "last_seen": _iso(last_ago),
            "mem_class": "preference", "sig_bits": "0" * 64}


def _iso(secs_ago):
    # WITH THE Z. Every stamp in this store is gmtime() + a literal Z, and lifecycle's
    # _age_days returns 0.0 for anything else — silently, which is how a fixture without
    # one reports every row as brand new and no silence ever fires.
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - secs_ago))


def _tdir():
    """Beside the registry — the same resolution _his_turns() uses."""
    return os.path.join(os.path.dirname(os.environ["SP_RECALL_REGISTRY"]), "transcripts")


def _transcript(turns):
    """turns = [(seconds_ago, text)] as HIS rows, in the store's real epoch-MS shape."""
    d = _tdir()
    os.makedirs(d, exist_ok=True)
    by_day = {}
    for ago, text in turns:
        at = (NOW - ago) * 1000.0
        day = time.strftime("%Y-%m-%d", time.gmtime(NOW - ago))
        by_day.setdefault(day, []).append({"role": "user", "at": at, "content": text})
    for day, rows in by_day.items():
        with open(os.path.join(d, "%s.jsonl" % day), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return d


# ── HIS SHAPE, reduced to its essentials: a TIGHT rhythm (three mentions on three
# consecutive attended days, so cadence floors at a day) and then a long gap in the
# REGISTRY — while he goes on saying it in his turns, which is the whole bug.
MENTIONS = [_row("good morning", "m1")]
KETTLE = [_row("the kettle is my favorite", "k1")]

print("1. THE REGRESSION — a claim he restated is proposed, then refuted")
_registry(MENTIONS)
pm = PersonModel.from_registry()
# said_since returning nothing IS the pre-fix behaviour, exactly.
before = pm.silences(now=NOW, attend=Calendar(), said_since=lambda t: set())
check("without corroboration it IS proposed (the bug reproduces)",
      any("morning" in str(s["claim"]).lower() for s in before),
      [s["claim"] for s in before])

_transcript([(1 * DAY, "good morning"), (2 * DAY, "how did you sleep")])
after = pm.silences(now=NOW, attend=Calendar())
check("...and with his own turns read, it is REFUTED",
      not any("morning" in str(s["claim"]).lower() for s in after),
      [s["claim"] for s in after])
# THE NUMBERS ARE REAL. Replayed against the live store at the moment of the last firing,
# the uncorroborated path proposed exactly 2.00 bits / quiet=2.0 / cadence=1.0 on the
# repeated line — matching the gateway.log entry digit for digit — and proposed nothing
# once corroborated.
check("...the refuted claim was a real proposal, not an empty list either way",
      len(before) > len(after), "%d -> %d" % (len(before), len(after)))

print("\n2. A GENUINE SILENCE SURVIVES — this is not 'always refute'")
_registry(MENTIONS + KETTLE)
pm = PersonModel.from_registry()
_transcript([(1 * DAY, "good morning"), (2 * DAY, "how did you sleep")])
got = pm.silences(now=NOW, attend=Calendar())
check("the thing he really has gone quiet on is still raised",
      any("kettle" in str(s["claim"]).lower() for s in got), [s["claim"] for s in got])
check("...and the corroborated one is still not",
      not any("morning" in str(s["claim"]).lower() for s in got), [s["claim"] for s in got])

print("\n3. IT FAILS CLOSED when it cannot prove she was looking")
_registry(MENTIONS)
pm = PersonModel.from_registry()
d = _tdir()
for n in os.listdir(d):
    os.remove(os.path.join(d, n))
os.rmdir(d)
check("no transcript at all -> no claim, rather than every claim",
      pm.silences(now=NOW, attend=Calendar()) == [])

print("\n4. CONTAINMENT, NOT OVERLAP")
_registry(KETTLE)
pm = PersonModel.from_registry()
# he said "kettle" but never "favorite" — one shared word is not having spoken to it
_transcript([(1 * DAY, "the kettle is boiling")])
got = pm.silences(now=NOW, attend=Calendar())
check("one shared word does not refute a two-word claim",
      any("kettle" in str(s["claim"]).lower() for s in got), [s["claim"] for s in got])
_transcript([(1 * DAY, "the kettle is still my favorite thing in this house")])
got = pm.silences(now=NOW, attend=Calendar())
check("...and the whole claim in one turn does",
      not any("kettle" in str(s["claim"]).lower() for s in got), [s["claim"] for s in got])

print("\n5. BOTH DOORS — driven through the REAL reflect_tick, not grepped for")
# ── WHY THIS IS BEHAVIOURAL AND NOT A GREP ───────────────────────────────────────────
# THE §0 CHECK, and it is the reason this gate exists: skills/silence.py refuses to speak
# below MIN_LEDGER_DAYS and is DEFAULT OFF for want of ledger depth, while the ambient
# door read the same model with no floor and interrupted him every half hour.
#
# The first cut asserted `"MIN_LEDGER_DAYS" in scheduler.py`. Run against the mutant with
# the floor DELETED, it still passed — the name survives in the comment that explains the
# floor. Prose-matching where structure was meant is how a green gate ships over absent
# code, so the floor is EXERCISED: the real reflect_tick is called at both depths.
from harness.kairos import scheduler as KS      # noqa: E402
from harness.skills import silence as SIL       # noqa: E402

_registry(KETTLE)                    # a genuine, uncorroborated silence is on offer
_transcript([(1 * DAY, "nothing to do with it")])
from harness.model import presence as PRES     # noqa: E402
_real_days, _real_att = SIL.ledger_days, PRES.attended_days
try:
    # ambient_silence() takes no injection points — it is the REAL production path — so the
    # calendar it actually consults is faked here, the same one Calendar() supplies above.
    PRES.attended_days = Calendar().attended_days
    SIL.ledger_days = lambda: SIL.MIN_LEDGER_DAYS - 1
    shallow = KS.ambient_silence()
    SIL.ledger_days = lambda: SIL.MIN_LEDGER_DAYS + 30
    deep = KS.ambient_silence()
finally:
    SIL.ledger_days, PRES.attended_days = _real_days, _real_att

check("a ledger too shallow to have watched offers NO silence",
      shallow is None, shallow)
check("...and a deep one still does (the floor gates, it does not disable)",
      (deep or {}).get("silence") is not None, deep)
check("...and what it offers is the real claim",
      "kettle" in str((deep or {}).get("text", "")).lower(), deep)

_p = open(os.path.join(ROOT, "harness", "model", "person.py"), encoding="utf-8").read()
# ORDER VIA find(), NOT index() — a missing anchor must FAIL this check, not raise out
# of the gate and skip everything after it (including the receipt).
_decl, _use = _p.find("def silences"), _p.find("cw <= said_since")
check("corroboration lives in silences() itself, so BOTH doors inherit it",
      "said_since" in _p and 0 <= _decl < _use,
      "a rule in one caller is a rule on neither path")

print("\nG-SILENCE-CORROBORATE: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_silence_corroborate.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_silence_corroborate", "pass": PASS, "fail": FAIL,
               "corroborate_days": P._CORROBORATE_DAYS,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
sys.exit(1 if FAIL else 0)
