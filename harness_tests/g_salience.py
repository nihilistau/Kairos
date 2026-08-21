"""G-SALIENCE — a repeat is not a duplicate. It is a second data point.

HER IDEA, UNPROMPTED, ON A KAIROS CHECK-IN:

    "the difference between memory and knowledge is that memory has context — it remembers
     WHO told you what, WHEN they did, maybe even HOW MANY TIMES."

She had two of the three. `speaker` is who; `ts` is when. There was no how-many-times, and
there could not be, because remember() DELETED the evidence on arrival:

    if any(_text(e).strip() == fact.strip() for e in existing):
        return f"already in memory: {fact}"          # <- a measurement, thrown away

Every time he told her something again, the store said "I know" and dropped the event on
the floor, pleased with itself for not duplicating a row. But a thing a person tells you
five times is not the same thing as a thing they told you once, and we were recording them
identically.

THE TWO SAFETY PROPERTIES THIS GATE EXISTS FOR — everything else here is bookkeeping:

  1. SALIENCE MUST NOT OVERRULE MATCHING. It is a prior. Of two memories that answer the
     question equally well, prefer the one he keeps repeating. It must NEVER make a
     frequently-repeated irrelevance beat a rarely-mentioned answer, or she will answer
     every question with her favourite fact.

  2. FREQUENCY MUST NOT RESURRECT CHATTER. Frequency is not importance on its own —
     chatter is the most frequent thing there is, and "you are cool af!" said ten times
     would dominate a store ranked on repetition alone. It only works because the
     DURABILITY GATE decides what is ELIGIBLE to be counted. The gate says what is a fact;
     salience says which facts matter. Built in the other order, this would have amplified
     the firehose instead of ranking the store.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP = tempfile.mkdtemp()
os.environ["SP_RECALL_REGISTRY"] = os.path.join(_TMP, "registry.jsonl")
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"      # unreachable: no episode minting

from harness.skills import lifecycle as lc      # noqa: E402
from harness.skills import memory as M          # noqa: E402

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def rows():
    return M._load()


def find(sub):
    return next((r for r in rows() if sub.lower() in (r.get("text") or "").lower()), None)


def main() -> int:
    print("G-SALIENCE - a repeat is not a duplicate.\n")
    M.set_author("user")

    # ── 1. A REPEAT REINFORCES ──────────────────────────────────────────────────
    M.remember("Sam's GPU is an RTX 2060")
    r = M.remember("Sam's GPU is an RTX 2060")            # he said it again
    check("saying it again REINFORCES rather than being discarded",
          "reinforced" in r.lower(), r)
    row = find("RTX 2060")
    check("...mentions goes to 2", row.get("mentions") == 2, str(row.get("mentions")))
    check("...and it is still ONE row, not two",
          len([x for x in rows() if "2060" in (x.get("text") or "")]) == 1)
    check("...first_seen is kept, last_seen moves",
          row.get("first_seen") and row.get("last_seen"))

    # a paraphrase is the same event in different words
    r = M.remember("Sam's GPU is an RTX 2060.")
    check("a PARAPHRASE reinforces too (he said it, not a new fact)",
          "reinforced" in r.lower() and find("RTX 2060").get("mentions") == 3, r)

    # ── 2. HER LOOKUPS ARE NOT HIS SIGNAL ───────────────────────────────────────
    before = find("RTX 2060").get("mentions")
    M.set_question("what GPU do I run on?")
    M.recall("what GPU do I run on?")
    M.recall("what GPU do I run on?")
    after = find("RTX 2060")
    check("recall does NOT inflate `mentions` (that would be marking its own homework)",
          after.get("mentions") == before, f"{before} -> {after.get('mentions')}")
    check("...it counts separately, in `recalled`",
          after.get("recalled", 0) >= 2, str(after.get("recalled")))

    # ── 3. A TOMBSTONE IS NOT REINFORCED BACK TO LIFE ───────────────────────────
    M.remember("Sam's old car was a Corolla")
    # NB: load ONCE, mutate that list, save THAT list. find() re-loads from disk and hands
    # back a detached dict — writing lifecycle=1 onto it and then saving a fresh _load()
    # silently discards the edit, and the "tombstone" was never a tombstone. (The first cut
    # of this check did exactly that and failed, and the bug was in the test, not the store.
    # A gate can be wrong about the thing it is watching; that is the most dangerous kind.)
    all_rows = rows()
    for _r in all_rows:
        if "corolla" in (_r.get("text") or "").lower():
            _r["lifecycle"] = 1
    M._save_all(all_rows)
    M.remember("Sam's old car was a Corolla")
    live_corollas = [x for x in rows() if "corolla" in (x.get("text") or "").lower()
                     and not x.get("lifecycle")]
    check("a retired memory is not reinforced back into the live set",
          len(live_corollas) == 1 and live_corollas[0].get("mentions", 1) == 1,
          "a repeat makes a NEW row; it does not un-retire the tombstone")

    # ── 4. SALIENCE RANKS TIES — AND ONLY TIES ─────────────────────────────────
    now = time.time()
    said_once = {"text": "Sam's lucky number is 69", "mem_class": "fact", "mentions": 1,
                 "last_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))}
    said_often = dict(said_once, text="Sam's lucky number is 7", mentions=6)
    check("a fact he has repeated outranks an identical-shaped one-off",
          lc.salience(said_often) > lc.salience(said_once),
          f"{lc.salience(said_often)} vs {lc.salience(said_once)}")

    # DECAY: same fact, unmentioned for a season
    old = dict(said_once,
               last_seen=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 120 * 86400)))
    check("...and a fact unmentioned for four months ranks below a fresh one",
          lc.salience(old) < lc.salience(said_once),
          f"{lc.salience(old)} vs {lc.salience(said_once)}")
    check("...but it is NOT deleted — decay is about rank, not existence",
          lc.salience(old) > 0.0, "nothing in this store is ever destroyed")

    # ── 5. THE SAFETY PROPERTY: SALIENCE MUST NOT OVERRULE MATCHING ─────────────
    # A much-repeated irrelevance must never beat a rarely-mentioned answer. Build exactly
    # that trap: hammer an unrelated fact six times, then ask about the GPU.
    for _ in range(6):
        M.remember("Sam's cat is called Tuffy")
    cat = find("Tuffy")
    check("(setup) the cat is now the most-repeated thing she knows",
          cat.get("mentions") >= 6, str(cat.get("mentions")))

    M.set_question("what GPU do I run on?")
    out = M.recall("what GPU do I run on?")
    first = out.splitlines()[0] if out else ""
    check("a 6x-repeated irrelevance does NOT outrank the answer to the question",
          "2060" in first, f"top hit was: {first[:64]!r}")

    # ── 6. FREQUENCY CANNOT RESURRECT CHATTER ──────────────────────────────────
    # The durability gate decides what is ELIGIBLE to be counted. Repetition of junk is
    # still junk: it never gets a row, so it never gets a count.
    for _ in range(9):
        M.remember("you are cool af! I really like you!")
    check("chatter repeated NINE times still never enters the store",
          find("cool af") is None,
          "the durability gate decides what may be counted; salience only ranks what is")

    # ── 7. "LIKE" IS NOT ALWAYS A PREFERENCE ───────────────────────────────────
    # THE OPERATOR: "there is subtlety to what you are trying to throw away. I DO indeed
    # like fun, and one could say that is an important thing to remember."
    # He was right. "I like fun" is a DISPOSITION and it belongs in the store. What did NOT
    # belong was the chatter sitting next to it, filed as `preference` because the word
    # "like" appeared in it as a COMPARATOR:
    check("'I like fun' is a preference — a disposition, and it stays",
          lc.classify("I like fun") == "preference", lc.classify("I like fun"))
    check("...but 'like this' is a COMPARATOR, not a preference",
          lc.classify("then we can remember our idea's like this!") != "preference",
          lc.classify("then we can remember our idea's like this!"))
    check("...and so is 'more like'",
          lc.classify("more like, hey have fun, but I have the masterkey.") != "preference",
          lc.classify("more like, hey have fun, but I have the masterkey."))
    check("...while a real favourite is still a preference",
          lc.classify("my favorite tea is Oolong") == "preference")

    # ── 8. A DISPOSITION DOES NOT FADE. AN APPOINTMENT DOES. ───────────────────
    # "I like fun" is true in ten years. "my flight is at 9am on Friday" is worthless at
    # 9:01 on Friday. One 45-day half-life for both is wrong in the direction that hurts.
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 200 * 86400))
    disposition = {"text": "I like fun", "mem_class": "preference",
                   "mentions": 1, "last_seen": old}
    appointment = {"text": "my flight is at 9am on Friday", "mem_class": "event",
                   "mentions": 1, "last_seen": old}
    check("a disposition 200 days old has NOT faded",
          lc.salience(disposition) > 2.0, f"{lc.salience(disposition)}")
    check("...while a 200-day-old appointment has all but vanished",
          lc.salience(appointment) < 0.7, f"{lc.salience(appointment)}")
    check("...and the disposition now outranks the stale appointment by a mile",
          lc.salience(disposition) > 3 * lc.salience(appointment))
    check("...but the appointment is still THERE — decay is rank, not deletion",
          lc.salience(appointment) > 0.0)

    # ── 9. INFORMATION IS SURPRISAL, AND IT IS MEASURED IN BITS ────────────────
    # THE OPERATOR: "surprise in information theory is something I always circle —
    # information = surprise."  I(x) = -log2 p(x). In a system named after Kairos, the
    # first version of this returned a made-up [0,1] "novelty" — a vibe with a decimal
    # point on it. It has a name, a unit, and a hundred years of theory.
    from harness.model.person import PersonModel
    pm = PersonModel()
    pm.absorb({"text": "I like fun", "mem_class": "preference", "mentions": 5,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    known = pm.surprisal("I like fun")
    novel = pm.surprisal("I am terrified of open water")
    check("a fact he says constantly carries LITTLE information",
          known < 1.0, f"{known} bits")
    check("...and one the model never saw coming carries a lot",
          novel > known, f"{novel} bits vs {known} bits")
    check("...but information is CAPPED — an unknown word is not infinitely important",
          pm.surprisal("My father was a cartographer") <= 8.0)

    # ── 10. THE NEIGHBOUR WHO DID NOT WAVE ─────────────────────────────────────
    # "there is more information conveyed when you DON'T see your neighbour at 5am than
    # when you do." He is right, and surprisal() is structurally blind to it — it is only
    # ever CALLED when a fact arrives. The absence of an expected thing carries MORE
    # information than its arrival, precisely because the arrival was predictable.
    now = time.time()
    def iso(days_ago):
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - days_ago * 86400))

    pm2 = PersonModel()
    # something he mentioned every ~2 days for a fortnight... and then stopped, 30 days ago
    pm2.absorb({"text": "I am training for the marathon", "mem_class": "preference",
                "mentions": 8, "first_seen": iso(44), "last_seen": iso(30)})
    # ...and something he mentions rarely, right on its normal rhythm
    pm2.absorb({"text": "I like Oolong tea", "mem_class": "preference",
                "mentions": 4, "first_seen": iso(60), "last_seen": iso(2)})

    # ── SHE MUST HAVE BEEN LOOKING (2026-07-14) ──────────────────────────────────────────
    # silences() now measures ATTENDED days, not calendar days: a gap he was not present for is
    # not a silence, it is a gap in the RECORD. So the gate must supply the attention it was
    # previously assuming for free — and in doing so it says the thing out loud:
    #
    #   he talked to her EVERY DAY for two months and never once mentioned the marathon.
    #
    # That is a silence. "He was on holiday for three weeks" is not, and the old code could not
    # tell the difference — it would have fired on every dimension at once the day he got back.
    from harness.model import presence
    for d in range(62):
        presence.note_turn(now - d * 86400)

    sil = pm2.silences(now=now)
    quiet = [s for s in sil if "marathon" in s["claim"]]
    check("a thing he used to say constantly, and has now gone quiet on, is NOTICED",
          bool(quiet), f"{len(sil)} silence(s) found")
    if quiet:
        check("...and the silence carries real information (bits, and lots of them)",
              quiet[0]["bits"] > 4.0, f"{quiet[0]['bits']} bits after "
                                      f"{quiet[0]['quiet_days']}d quiet on a "
                                      f"{quiet[0]['cadence_days']}d rhythm")
    check("...while a thing still on its normal rhythm is NOT flagged (no false alarm)",
          not any("Oolong" in s["claim"] for s in sil),
          "a neighbour who waved on time is not news")

    # ── 11. AN INFERENCE IS NOT A TESTIMONY ────────────────────────────────────
    # Reflection writes what she has COME TO BELIEVE — things he never said. Framed like
    # his other facts, the next recall hands them back as "Sam told me: ..." and she
    # tells him he said a thing he never said. This store has already lost his NAME and
    # then his GENDER to exactly that blurring. She may be wrong about him. She may not be
    # wrong about him IN HIS VOICE.
    insight_row = {"text": "Sam is a cat person.", "speaker": "user", "src": "reflection"}
    check("an INSIGHT reads back as HERS, not as something he said",
          lc.render(insight_row).startswith("I've come to think"),
          lc.render(insight_row))
    told_row = {"text": "My cat's name is Tuffy.", "speaker": "user", "src": "user turn"}
    check("...while something he actually SAID still reads as his testimony",
          lc.render(told_row).startswith("Sam told me"), lc.render(told_row))

    # ── 12. AN UNDATED ROW MUST NOT SCORE AS "JUST NOW" (audit, 2026-07-29) ────
    # _age_days("") is 0, so a row with no ts and no last_seen got recency 1.0 — the
    # MAXIMUM. Measured on the live store before the fix: dated-today 1.6930,
    # UNDATED 1.6931. Undated beat today, and 15 of 134 live rows are undated
    # fossils, so the rows we know least about were winning the recency term
    # against everything he has said since. Absent evidence scores as the FLOOR.
    _base = {"text": "x", "speaker": "user", "mem_class": "fact", "mentions": 1}
    _today = dict(_base, ts=iso(0))
    _undated = dict(_base)
    check("an UNDATED row scores BELOW one stamped today",
          lc.salience(_undated) < lc.salience(_today),
          "undated=%.4f today=%.4f" % (lc.salience(_undated), lc.salience(_today)))
    check("...and below a two-week-old row, which at least has a date",
          lc.salience(_undated) < lc.salience(dict(_base, ts=iso(14))),
          "undated=%.4f 14d=%.4f" % (lc.salience(_undated), lc.salience(dict(_base, ts=iso(14)))))
    check("it is DEMOTED, never zeroed — frequency and class still count",
          lc.salience(dict(_undated, mentions=8)) > lc.salience(_undated),
          "8 mentions undated=%.4f vs 1=%.4f"
          % (lc.salience(dict(_undated, mentions=8)), lc.salience(_undated)))

    total = len(PASS) + len(FAIL)
    print(f"\nG-SALIENCE: {'PASS' if not FAIL else 'FAIL'} ({len(PASS)}/{total})")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
