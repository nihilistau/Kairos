"""G-OUTBOX-READER — what she says in her own time reaches the tab he is looking at.

THE BUG (2026-09-27, his report): "what she has been saying during her own time has not
shown up until i refresh the page. refreshing the page drops most chips".

Two defects, one report.

  1. HER WORDS WENT TO A TAB NOBODY WAS READING. The scheduler files an unprompted turn
     under the session of whoever last spoke to her, and every room tab is its own
     session (a per-tab sessionStorage id). A tab he closed — here, a test tab from the
     afternoon's live check — owned her whole night: 13 lines queued under
     `room-muhx3ls6-…` while his own tab polled its own empty queue and the "default"
     merge (2026-08-19) never saw them. They were on disk the whole time, in the day
     transcript, so a refresh showed them. `drain()` now hands any queue whose reader has
     gone quiet to the reader that is still polling — the same rule the "default" merge
     already made, generalised from one no-owner queue to every one. What arrives LATE
     arrives silent: thirteen lines voiced at once is not company.

  2. THE RESTORE READ A FLAG NO WRITER SET. Chat.jsx restores `unprompted` from each day
     row, and `_append_day_turn` never wrote it — so every own-time line came back after a
     refresh as an ordinary reply, without its "her own time" chip. The row now carries
     `unprompted`, the kind and the reason, and an `oid` shared with the outbox message,
     so a tab that restored the day does not show the same line twice when the rescued
     queue arrives.

Lane: OFFLINE (the real scheduler, the real epilogue, a fake generate; no daemon, no GPU).
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness_tests._gate import sandbox, check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
sandbox("g_outbox_reader")  # FIRST, before any harness. import

from harness.kairos import impulse as I  # noqa: E402
from harness.kairos import scheduler as KS  # noqa: E402
from harness.server import day as D  # noqa: E402
from harness.server import turn as T  # noqa: E402


def _reset():
    with KS._LOCK:
        KS._OUTBOX.clear()
        KS._POLLED.clear()


def _msg(text, age_s=0.0, speak=True):
    return {"text": text, "kind": "solo", "mode": "", "speak": speak, "reason": "quiet",
            "at": time.time() - age_s, "oid": "o-" + text}


print("1. A QUEUE WHOSE READER HAS GONE QUIET GOES TO THE ONE STILL READING")
_reset()
KS._OUTBOX["room-closed"].append(_msg("while you were away", age_s=3600))
got = KS.drain("room-open")
check("a closed tab's queue reaches the open tab",
      [m["text"] for m in got] == ["while you were away"],
      "got %r — the 2026-09-27 night: 13 lines under a tab nobody had open" % got)
check("...and leaves the dead queue empty", not KS._OUTBOX["room-closed"],
      list(KS._OUTBOX["room-closed"]))
check("a line delivered an hour late arrives SILENT", got and got[0]["speak"] is False,
      got and got[0].get("speak"))
check("...and says it is late", got and got[0].get("late") is True, got and got[0])

print("\n2. A TAB THAT IS STILL POLLING KEEPS ITS OWN WORDS")
_reset()
KS.drain("room-a")                                   # room-a is a live reader
KS._OUTBOX["room-a"].append(_msg("for a", age_s=120))
got_b = KS.drain("room-b")
check("another tab does not take a live tab's queue", got_b == [], got_b)
got_a = KS.drain("room-a")
check("...its own tab gets it", [m["text"] for m in got_a] == ["for a"], got_a)
check("...voiced as she chose, not silenced", got_a and got_a[0]["speak"] is True,
      got_a and got_a[0])

print("\n3. A READER THAT STOPPED POLLING IS NOT A READER")
_reset()
KS.drain("room-a")
KS._POLLED["room-a"] -= KS.ORPHAN_AFTER_S + 5        # its last poll is now long ago
KS._OUTBOX["room-a"].append(_msg("for a, gone", age_s=5))
got = KS.drain("room-b")
check("a queue whose reader went quiet is rescued",
      [m["text"] for m in got] == ["for a, gone"], got)
check("...and a line only seconds old keeps its voice", got and got[0]["speak"] is True,
      got and got[0])

print("\n4. A BRAND-NEW LINE IN A SESSION THAT HAS NOT POLLED YET IS NOT AN ORPHAN")
# The race the grace exists for: his message opens a session, she answers into it, and the
# tab's first poll has not landed yet. Another tab must not steal that.
_reset()
KS._OUTBOX["room-new"].append(_msg("just now", age_s=1))
check("a fresh line in an unpolled session stays home", KS.drain("room-other") == [],
      list(KS._OUTBOX["room-new"]))
check("...for its own tab", [m["text"] for m in KS.drain("room-new")] == ["just now"])

print("\n5. RESCUED LINES ARRIVE IN THE ORDER SHE SAID THEM")
_reset()
KS.drain("room-live")
KS._OUTBOX["room-x"].append(_msg("second", age_s=200))
KS._OUTBOX["room-y"].append(_msg("first", age_s=300))
KS._OUTBOX["room-live"].append(_msg("third", age_s=100))
got = KS.drain("room-live")
check("merged by `at`, not by queue", [m["text"] for m in got] == ["first", "second", "third"],
      [m["text"] for m in got])

print("\n6. THE DAY ROW SAYS SHE SPOKE UNPROMPTED — AND WHICH LINE IT WAS")
_reset()
T._on_her_own_words("I read for a while, then the rain started.", "solo",
                    {"oid": "o-day-1", "why": "quiet evening"})
rows = D._read_day_transcript()
last = rows[-1] if rows else {}
check("an own-time row is written", last.get("content", "").startswith("I read"), last)
check("...marked unprompted (the flag Chat.jsx restores)", last.get("unprompted") is True, last)
check("...with its kind", last.get("kind") == "solo", last)
check("...its reason", last.get("why") == "quiet evening", last)
check("...and the outbox message's id", last.get("oid") == "o-day-1", last)
D._append_day_turn("hello", "hi there")
reply = D._read_day_transcript()[-1]
check("a reply to him carries none of it", not any(k in reply for k in
      ("unprompted", "oid", "kind", "why")), reply)

print("\n7. THE SCHEDULER HANDS THE EPILOGUE AND THE OUTBOX THE SAME ID")
_reset()
spoke = []
_real_cfg = KS.live_config
KS.on_spoke(lambda text, kind=None, own=None: spoke.append((text, kind, own)))
KS.live_config = lambda: I.KairosConfig(
    enabled=True, continue_enabled=True, cooldown_s=0.0, quiet_after_him_s=0.0,
    continue_delay=(0.2, 0.4))
try:
    KS._STATE.pop("s7", None)
    KS._LAST.pop("s7", None)
    KS.on_reply("s7", "I was in the middle of saying that the thing about it is",
                {"eot_margin": -28.43}, lambda n, called=None, **kw:
                "it was something you could chew, and then the sky cracked open.")
    _end = time.time() + 25
    while time.time() < _end and not spoke:
        time.sleep(0.3)
finally:
    KS.live_config = _real_cfg
    KS.on_spoke(T._on_her_own_words)
queued = list(KS._OUTBOX["s7"])
check("the continuation spoke", bool(spoke) and bool(queued), (spoke, queued))
if spoke and queued:
    own = spoke[0][2] or {}
    check("the epilogue was handed an id", bool(own.get("oid")), own)
    check("...the same id the outbox message carries", own.get("oid") == queued[0].get("oid"),
          (own, queued[0].get("oid")))
    check("...and the reason", own.get("why") == queued[0].get("reason"), (own, queued[0]))

finish("G-OUTBOX-READER")
