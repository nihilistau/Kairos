#!/usr/bin/env python
"""G-SILENCE-ANSWER — a silence may inform a REPLY, and only when it has earned the right.

G-SILENCE established the first half of the doctrine:

    "Absence is only information if you can prove you were looking."

This gate holds the two halves that were still missing, both found by MEASURING the live store
rather than by reasoning about it.

1. YOU MUST HAVE BEEN LOOKING LONG ENOUGH. With four days in the attention ledger,
   `PersonModel.silences()` returned five silences on his real registry, led by

       8.00 bits  quiet=4.0  cadence=0.5   "the kettle is my favorite!"

   A cadence of half a day is a burst inside ONE conversation, and the arithmetic was calling a
   single quiet day a two-bit surprise. So: a topic must have been raised across at least two
   SEPARATE attended days before its quiet means anything (`_MIN_SPAN_DAYS`), no cadence under a
   day may be believed (`_MIN_CADENCE_DAYS`), and the ledger itself must be deep enough
   (`silence.MIN_LEDGER_DAYS`) — enforced in code, not left as advice. Those floors cut the five
   to one on the same store.

2. A SILENCE MAY NOT COLOUR AN ANSWER IT HAS NOTHING TO DO WITH. The answer-time note is topic
   -gated: it rides the turn only when the quiet claim overlaps what he JUST ASKED. Ambient
   "you've stopped talking about X" is the sentence G-SILENCE exists to prevent; "he raised the
   GPU and she knows he has not raised it in a while" is context for an answer.

    FORALL bursts:            a rhythm seen inside one sitting proposes NOTHING
    FORALL shallow ledgers:   below MIN_LEDGER_DAYS, nothing is surfaced at any bits
    FORALL unrelated asks:    no topic overlap, no note
    FORALL notes:             framed as noticing, declared unspeakable, never an instruction
    FORALL standing renders:  AT MOST ONE — never a list, which is an ambient accusation
    FORALL knob-off:          both surfaces are silent

FULLY SANDBOXED — it drives a fake registry and a fake attention ledger, and refuses to run if
either resolved outside the temp dir.

OFFLINE. No GPU, no daemon.
"""
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

SB = tempfile.mkdtemp(prefix="g-silence-answer-")
os.environ["SP_RECALL_REGISTRY"] = os.path.join(SB, "registry.jsonl")
import json as _json
import time as _time

# ── A TRANSCRIPT STORE, because a silence is now CORROBORATED against his own turns ──
# `person.silences()` refutes any claim he has spoken to since its row was minted, and it
# FAILS CLOSED when there is no record to check ("absence is only information if you can
# prove you were looking" — its own thesis). This fixture therefore has to say what he
# actually said, and what he said is: nothing about any of these claims. That makes the
# assertions below stronger than they were, not weaker. See G-SILENCE-CORROBORATE.
_TDIR = os.path.join(os.path.dirname(os.environ["SP_RECALL_REGISTRY"]), "transcripts")
os.makedirs(_TDIR, exist_ok=True)
with open(os.path.join(_TDIR, "%s.jsonl" % _time.strftime(
        "%Y-%m-%d", _time.gmtime(_time.time() - 86400.0)), ), "w", encoding="utf-8") as _f:
    _f.write(_json.dumps({"role": "user", "at": (_time.time() - 86400.0) * 1000.0,
                          "content": "nothing here bears on the fixtures"}) + chr(10))

os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_SILENCE_ANSWER"] = "1"

from harness.model import presence  # noqa: E402
from harness.model.person import PersonModel  # noqa: E402
from harness.skills import silence as S  # noqa: E402

if SB not in os.environ["SP_RECALL_REGISTRY"] or SB not in presence._path():
    print("REFUSING TO RUN: stores not sandboxed\n  reg: %s\n  ledger: %s"
          % (os.environ["SP_RECALL_REGISTRY"], presence._path()))
    shutil.rmtree(SB, ignore_errors=True)
    sys.exit(2)

PASS = FAIL = 0
DAY = 86400.0
NOW = 1800000000.0            # a fixed clock: a gate that drifts with the wall is not a gate


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


def write_ledger(n_days, upto=NOW):
    """He talked to her on each of the last n_days days."""
    days = {}
    for i in range(n_days):
        days[presence._day_key(upto - i * DAY)] = 3
    presence._save(days)
    presence._load.cache_clear() if hasattr(presence._load, "cache_clear") else None


def write_registry(rows):
    with open(os.environ["SP_RECALL_REGISTRY"], "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def fact(text, mentions, first_days_ago, last_days_ago, mem_class="possessions"):
    return {"text": text, "speaker": "user", "status": "observed", "mem_class": mem_class,
            "mentions": mentions, "lifecycle": 0,
            "first_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                        time.gmtime(NOW - first_days_ago * DAY)),
            "last_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                       time.gmtime(NOW - last_days_ago * DAY)),
            "ts": NOW - last_days_ago * DAY}


# A genuine rhythm, and a STRONG silence: 6 mentions across 18 attended days (cadence 3.6)
# then 20 attended days of nothing -> p = 0.5^5.6, about 5.6 bits. Chosen to clear the
# MIN_BITS_ANSWER bar with room, because the bar is a statement about how surprised she has to
# be before a silence may colour an answer he asked for (3 bits ~ "I would have given this
# about one chance in eight") and a fixture must not be the thing that sets it.
GPU = fact("My GPU is an RTX 2060", 6, 38, 20)
# A burst: 4 mentions inside ONE sitting 20 days ago. Same quiet period, no rhythm behind it.
BURST = fact("the kettle is my favorite!", 4, 20, 20)

print("1. a burst is not a rhythm")
write_ledger(60)
write_registry([GPU, BURST])
sil = PersonModel.from_registry().silences(now=NOW)
claims = [r["claim"] for r in sil]
check("the real rhythm is seen", "My GPU is an RTX 2060" in claims, claims)
check("THE BURST IS NOT — four mentions in one sitting propose nothing",
      "the kettle is my favorite!" not in claims, claims)
check("no surviving silence claims a sub-day cadence",
      all(r["cadence_days"] >= 1.0 for r in sil), [r["cadence_days"] for r in sil])

print("\n2. you must have been looking LONG ENOUGH")
for depth in (0, 1, 4, S.MIN_LEDGER_DAYS - 1):
    write_ledger(depth) if depth else presence._save({})
    check("ledger %2d day(s): nothing is surfaced, at any bits" % depth,
          S.for_question("how is the GPU going?", now=NOW) == [] and S.standing(now=NOW) == "",
          (S.ledger_days(), S.why_quiet()))
write_ledger(60)
check("a deep ledger DOES let it speak",
      S.for_question("how is the GPU going?", now=NOW) != [], S.why_quiet())
check("why_quiet() explains itself for the operator",
      "armed" in S.why_quiet(), S.why_quiet())

print("\n3. a silence may not colour an unrelated answer")
check("he asks about the GPU -> the GPU silence is offered",
      [h["claim"] for h in S.for_question("how is the GPU going?", now=NOW)]
      == ["My GPU is an RTX 2060"])
check("he asks about the cat -> NOTHING (no topic overlap)",
      S.for_question("what is my cat's name?", now=NOW) == [],
      S.for_question("what is my cat's name?", now=NOW))
check("he says hello -> nothing (no topic at all)", S.for_question("hey", now=NOW) == [])
check("an empty turn -> nothing", S.for_question("", now=NOW) == [])
check("at most `top` are ever returned",
      len(S.for_question("how is the GPU going?", top=1)) <= 1)

print("\n4. the note is noticing, not an instruction")
note = S.note_for_question("how is the GPU going?", now=NOW)
check("a note is produced", bool(note))
check("it declares itself UNSPEAKABLE — she once imitated the recall note's register aloud",
      "never mention this note" in note, note[:120])
check("it says context, not instruction", "not an instruction" in note)
check("it does NOT tell her to raise it",
      "you should" not in note.lower() and "must" not in note.lower(), note[:160])
# Derived from the hit, not written as a literal: the first cut hardcoded the quiet-day count
# from an earlier fixture and failed the moment the fixture was strengthened, which tests the
# fixture rather than the note.
_h = S.for_question("how is the GPU going?", now=NOW)[0]
check("it carries the numbers so she can judge for herself",
      "day(s)" in note and ("%.0f" % _h["quiet_days"]) in note
      and ("%.0f" % _h["cadence_days"]) in note, note[:200])
check("...and the claim itself, so she knows WHAT went quiet", _h["claim"] in note)
check("an unrelated question yields no note", S.note_for_question("hey there", now=NOW) == "")

print("\n5. the standing render is ONE, never a list")
# Three genuine rhythms all gone quiet — exactly the "marathon, and the GPU, and Tuffy" shape.
write_registry([GPU,
                fact("My cat's name is Tuffy", 6, 36, 18, "relationships"),
                fact("I run every morning", 7, 40, 22, "happenings")])
many = S._ranked(S.MIN_BITS_STANDING, now=NOW)
check("several silences are genuinely above the bar (the test is not vacuous)",
      len(many) >= 2, len(many))
st = S.standing(now=NOW)
check("the standing world renders exactly one of them",
      sum(1 for m in many if m["claim"] in st) == 1,
      [m["claim"] for m in many if m["claim"] in st])
check("it is the STRONGEST one", many[0]["claim"] in st, st[:120])
check("and it says she has not raised it", "not raised it" in st, st[:160])

print("\n6. the knob")
os.environ["SP_SILENCE_ANSWER"] = "0"
check("off: no answer-time note", S.for_question("how is the GPU going?", now=NOW) == [])
check("off: no note text", S.note_for_question("how is the GPU going?", now=NOW) == "")
check("off: nothing in the standing world", S.standing(now=NOW) == "")
check("off: why_quiet() says so", "off" in S.why_quiet(), S.why_quiet())
os.environ["SP_SILENCE_ANSWER"] = "1"

print("\n7. it reads; it never writes")
import inspect  # noqa: E402

src = inspect.getsource(S)
check("no write-mode open() anywhere in the module",
      '"w"' not in src and "'w'" not in src)
check("no remember / update / save call",
      not any(k in src for k in ("remember(", ".save(", "N.update(", "_write_all(")))
before = open(os.environ["SP_RECALL_REGISTRY"], "rb").read()
S.for_question("how is the GPU going?", now=NOW)
S.standing(now=NOW)
S.note_for_question("how is the GPU going?", now=NOW)
check("the registry is byte-identical after every surface has run",
      open(os.environ["SP_RECALL_REGISTRY"], "rb").read() == before)

print("\nG-SILENCE-ANSWER: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_silence_answer.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_silence_answer", "pass": PASS, "fail": FAIL,
               "min_ledger_days": S.MIN_LEDGER_DAYS,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
shutil.rmtree(SB, ignore_errors=True)
sys.exit(1 if FAIL else 0)
