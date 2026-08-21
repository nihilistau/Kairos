"""G-SILENCE — she may only be surprised by an absence she was present for.

    "Absence is only information if you can prove you were looking."

THE BUG THIS GATE EXISTS TO KILL
────────────────────────────────
PersonModel.silences() measured `quiet = CALENDAR days since he last mentioned it`. It never
asked whether he was THERE.

Go away for three weeks — a holiday, a deadline, a hospital — and EVERY dimension with three or
more mentions goes silent SIMULTANEOUSLY, at high bits. She greets him with:

    "You've stopped talking about the marathon. And the GPU. And Tuffy. And your flight."

That is not noticing. IT IS A BUG WEARING NOTICING'S CLOTHES — and it is worse than saying
nothing, because the ONE signal in this system that makes a person feel known would be firing on
the fact that they were busy. He would learn to ignore the channel, and then the good one never
gets heard.

THE FIX, AND WHY IT IS A FIX AND NOT A PATCH
────────────────────────────────────────────
Every clock in silences() is now an ATTENTION clock: time is measured in DAYS HE ACTUALLY TALKED
TO HER. If he said nothing at all, attended == 0, p == 1, bits == 0 — nothing is surprising, and
that falls out of the ARITHMETIC rather than a special case. That is the test of a real fix: the
degenerate case is not handled, it simply cannot arise.

The two scenarios below are the whole gate. Everything else is detail.

    python harness_tests/g_silence.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP = tempfile.mkdtemp()
os.environ["SP_RECALL_REGISTRY"] = os.path.join(_TMP, "registry.jsonl")
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"   # a gate must never need a GPU

from harness.model import presence                      # noqa: E402
from harness.model.person import Dimension, PersonModel  # noqa: E402

PASS, FAIL = [], []
DAY = 86400.0


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""), flush=True)


class FakeAttention:
    """A calendar we control: which days did he actually speak to her?"""

    def __init__(self, present_days: set):
        self.present = present_days           # {days-ago: he spoke}

    def attended_days(self, t0: float, t1: float) -> float:
        if t1 <= t0:
            return 0.0
        n = 0
        t = t0
        while t <= t1 + 1.0:
            days_ago = round((NOW - t) / DAY)
            if days_ago in self.present:
                n += 1
            t += DAY
        return float(n)


NOW = time.time()


def _model_with(claim: str, mentions: int, first_days_ago: float, last_days_ago: float):
    """A person who mentioned ONE thing, on a rhythm, and then stopped."""
    m = PersonModel()
    d = Dimension("dispositions")
    iso = "%Y-%m-%dT%H:%M:%SZ"
    first = time.strftime(iso, time.gmtime(NOW - first_days_ago * DAY))
    last = time.strftime(iso, time.gmtime(NOW - last_days_ago * DAY))
    d.timed.append((claim, mentions, 1.0, first, last))
    d.claims.append((claim, mentions, 1.0))
    m.dims["dispositions"] = d
    return m


def main() -> int:
    print("G-SILENCE - she may only be surprised by an absence she was PRESENT for.\n", flush=True)

    # He mentioned the marathon 5 times over 10 days, and last said it 21 days ago.
    # Cadence ~2 days. He has now been quiet about it for three weeks.
    model = _model_with("Sam is training for a marathon", mentions=5,
                        first_days_ago=31, last_days_ago=21)

    # ── SCENARIO 1: HE WAS THERE THE WHOLE TIME AND STOPPED MENTIONING IT ───────────────
    # This is a REAL silence. He was talking to her every single day and never once brought up
    # the thing he used to bring up every other day. THAT is the dog that did not bark.
    present_throughout = FakeAttention(set(range(0, 40)))
    sil = model.silences(now=NOW, attend=present_throughout)
    check("HE WAS HERE AND WENT QUIET -> she notices",
          len(sil) == 1 and sil[0]["bits"] > 3.0,
          f"{len(sil)} silence(s), {sil[0]['bits'] if sil else 0} bits "
          f"(quiet {sil[0]['quiet_days'] if sil else 0}d on a {sil[0]['cadence_days'] if sil else 0}d rhythm)")

    # ── SCENARIO 2: HE WENT AWAY. THE CRUX. ────────────────────────────────────────────
    # Same facts, same 21 days of not mentioning the marathon — but he was not THERE. He spoke
    # to her up until 21 days ago and then vanished (holiday / deadline / hospital).
    #
    # THE OLD CODE FIRED HERE, AT FULL VOLUME, ON EVERY DIMENSION AT ONCE.
    #
    # The empty driveway tells you nothing if you slept in.
    went_away = FakeAttention(set(range(21, 40)))     # present BEFORE, absent SINCE
    sil = model.silences(now=NOW, attend=went_away)
    check("HE WENT AWAY -> she notices NOTHING (the empty driveway, and she slept in)",
          len(sil) == 0,
          "silent" if not sil else
          f"FIRED ANYWAY: {sil[0]['bits']} bits — she would tell a man back from hospital "
          f"that he has gone quiet about his marathon")

    # ── SCENARIO 3: HE CAME BACK AND STILL HAS NOT MENTIONED IT ────────────────────────
    # THIS SCENARIO CAUGHT ME, NOT THE CODE. My first version had him back for THREE days and
    # asserted she should be mildly surprised. She was not — 4 attended days against a 4.125
    # threshold on a 2.8-day rhythm. The code said "not yet", AND THE CODE WAS RIGHT. Three days
    # back from holiday is not yet a meaningful silence. I had written the assertion I wanted
    # rather than the one that was true, which is the whole failure mode of a gate.
    #
    # So: he has been back a WEEK and still has not said it. NOW it is surprising — and here is
    # the thing that makes attended time the right clock rather than a safety hack:
    #
    #     calendar clock : 22 quiet days on a 2.8-day rhythm  -> 8.0 bits. MAXED. A scream.
    #     attention clock:  8 attended days                   -> ~2.9 bits. Proportionate.
    #
    # The old code could only shout. It could not say "hm, you haven't mentioned the marathon
    # since you got back" — it could only say "YOU HAVE ABANDONED THE MARATHON". Attended time
    # does not just suppress the false positives; it gives the TRUE ones their right volume.
    back_for_7 = FakeAttention(set(range(0, 7)) | set(range(21, 40)))
    sil = model.silences(now=NOW, attend=back_for_7)
    check("HE CAME BACK and STILL has not said it -> proportionate, not a scream",
          len(sil) == 1 and 1.0 < sil[0]["bits"] < 6.0,
          f"{sil[0]['bits'] if sil else 0} bits over {sil[0]['quiet_days'] if sil else 0} ATTENDED days "
          f"(the calendar clock would have maxed at 8.0 and shouted)")

    # ── SCENARIO 4: A THING STILL ON ITS RHYTHM IS NOT NEWS ────────────────────────────
    fresh = _model_with("Sam drinks Oolong", mentions=5, first_days_ago=10, last_days_ago=1)
    sil = fresh.silences(now=NOW, attend=FakeAttention(set(range(0, 40))))
    check("a neighbour who waved on time is not news",
          len(sil) == 0, "still within its cadence" if not sil else f"FIRED: {sil[0]['bits']} bits")

    # ── SCENARIO 5: NO LEDGER AT ALL -> NOTHING IS SURPRISING ──────────────────────────
    # A fresh install has never recorded a single turn. That is NOT "he was never here" — it is
    # "I HAVE NO IDEA whether he was here." A system with no memory of looking must not claim to
    # have seen nothing. It must say nothing.
    never_seen = FakeAttention(set())
    sil = model.silences(now=NOW, attend=never_seen)
    check("NO ATTENTION LEDGER -> she claims nothing (absence of data is not data)",
          len(sil) == 0,
          "silent" if not sil else "invented a silence out of having never watched")

    # ── SCENARIO 6: THE REAL LEDGER WORKS (not just the fake one) ──────────────────────
    presence.note_turn(NOW - 2 * DAY)
    presence.note_turn(NOW - 1 * DAY)
    presence.note_turn(NOW)
    got = presence.attended_days(NOW - 5 * DAY, NOW)
    check("the real ledger counts the days he actually spoke",
          got == 3.0, f"{got} days of proven attention out of a 5-day window")

    total = len(PASS) + len(FAIL)
    print(f"\nG-SILENCE: {'PASS' if not FAIL else 'FAIL'} ({len(PASS)}/{total})", flush=True)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
