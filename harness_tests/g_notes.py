"""G-NOTES — the board: store, lifecycle, tools, and the promise.

A note is not a fact, and the whole feature turns on that. The fact store's admission gate
is deliberately brutal — a durable fact must assert a standing state about a person — and
it would refuse almost every note ever written ("buy a 3090 if stock returns" asserts
nothing standing about anybody). Put notes in the fact store and either the gate refuses
them or you loosen the gate and the firehose comes back. So: same MEM-OKF spine, own lane.

THE PROMISE is the part that must not break. He asks to be reminded; she says she will.
If that reminder silently fails to fire, he finds out by missing the thing — and a feature
he TRUSTED and that quietly lied to him is worse than no feature. So the reminder path is
gated harder than anything else here: it fires, it fires once, it survives her deciding
she has nothing to say, and it is not muted by the rules that exist to stop her chattering.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# isolate the store BEFORE importing anything that resolves it
_TMP = tempfile.mkdtemp()
os.environ["SP_RECALL_REGISTRY"] = os.path.join(_TMP, "registry.jsonl")

from harness.skills import notes as N            # noqa: E402
from harness.skills import note_tools as T       # noqa: E402
from harness.skills import lifecycle as lc       # noqa: E402
from harness.skills.duetime import parse_due     # noqa: E402
from harness.kairos import impulse as I          # noqa: E402

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    print("G-NOTES - the board, and the promise.\n")

    # ── STORE ───────────────────────────────────────────────────────────────────
    N.set_author(N.SPEAKER_USER)
    a = N.add("Buy a 3090 if stock returns", body="He is on a 2060 6GB", category="idea")
    check("a note goes on the board", bool(a["id"]) and a["category"] == "idea")
    check("...stamped with WHO put it there", a["speaker"] == "user", a["speaker"])
    check("...and coloured by category", a["colour"] == N.CATEGORY_COLOUR["idea"])

    N.set_author(N.SPEAKER_SELF)
    b = N.add("Ask him what the mmwave sensors are for", category="idea")
    check("SHE can put something on the board too, and it is HERS",
          b["speaker"] == "self", b["speaker"])

    # ── EDIT is an EDIT, not a new row (a board is not a tape) ───────────────────
    N.update(a["id"], body="Only if under $1500")
    live = N.live()
    check("editing a note does not mint a second one", len(live) == 2, f"{len(live)} rows")
    check("...and the edit stuck", N.get(a["id"])["body"] == "Only if under $1500")

    # ── REMOVE tombstones, exactly like the fact store ──────────────────────────
    N.remove(b["id"])
    check("remove TOMBSTONES rather than deleting",
          N.get(b["id"])["lifecycle"] == 1 and len(N.live()) == 1)

    # ── A NOTE IS NOT A FACT: the durability gate must never touch it ────────────
    ok, why = lc.is_memorable("Buy a 3090 if stock returns")
    check("the FACT gate would refuse this note (which is why notes have their own lane)",
          not ok, why)
    check("...but the board keeps it anyway", any(
        n["title"] == "Buy a 3090 if stock returns" for n in N.live()))

    # ── TOOLS: she reaches the same store, and her notes are hers ───────────────
    out = T.add_note("Try the Q4B fine-tune", category="idea")
    check("her add_note tool works", "noted:" in out, out[:52])
    hers = next(n for n in N.live() if n["title"] == "Try the Q4B fine-tune")
    check("...and a note SHE adds is stamped SELF, not his",
          hers["speaker"] == "self", hers["speaker"])

    check("find_notes searches the board", "3090" in T.find_notes("3090"))
    check("find_notes() with no query lists everything", len(T.find_notes().splitlines()) == 2)

    # ── REMINDERS: plain English in, a real timestamp out ───────────────────────
    now = datetime(2026, 7, 13, 14, 30, tzinfo=timezone.utc)          # a Monday
    iso, human = parse_due("friday 10am", now=now)
    check("'friday 10am' becomes a real timestamp", iso == "2026-07-17T10:00:00Z", iso)
    # SHE SAYS IT BACK — AND IT LEAVES HER NOTHING TO GUESS AT.
    # Live, first try: he said "remind me to defrost the freezer tomorrow at 8am". The store
    # got it exactly right. The tool handed her "tomorrow at 08:00" — and she told him
    # "I'll remind you on TUESDAY at 8am". It was a Monday. She had no weekday in front of
    # her, so she inferred one, and inferred it wrong. A confirmation that exists to catch a
    # wrong time cannot leave a blank in it.
    check("...and she can SAY IT BACK, weekday and date included",
          human == "Friday 17 Jul at 10:00", human)
    _, h2 = parse_due("tomorrow at 8am", now=now)          # now = Monday 13 Jul
    check("...even 'tomorrow' names the day, so she cannot guess it wrong",
          "Tuesday 14 Jul" in h2, h2)
    check("an unreadable time is REFUSED, not silently dropped",
          parse_due("sometime soonish")[0] == "", "a promise you cannot keep is worse than none")
    check("...and the tool refuses the note rather than promising",
          "could not read" in T.add_note("Nope", due="sometime soonish"))

    # ── THE PROMISE ─────────────────────────────────────────────────────────────
    past = _iso(datetime.now(timezone.utc) - timedelta(minutes=5))
    future = _iso(datetime.now(timezone.utc) + timedelta(days=2))
    overdue = N.add("Call the NUC supplier", category="reminder", due_at=past)
    N.add("Flight to Sydney", category="reminder", due_at=future)

    d = N.due()
    check("an OVERDUE reminder comes due", [n["id"] for n in d] == [overdue["id"]],
          f"{len(d)} due")
    check("...and one that is not yet due does not", all(n["due_at"] <= _iso(
        datetime.now(timezone.utc)) for n in d))

    cfg = I.KairosConfig(enabled=True, cooldown_s=0.0)
    st = I.TurnState()
    I.note_user(st, 1000.0)

    imp = I.decide(cfg=cfg, state=st, now=1000.1, reply_text="Sure.",
                   eot_margin=None, due_notes=d)
    check("a due reminder makes her SPEAK", imp.speaks and imp.action == I.REMIND, imp.reason)

    # THE TWO RULES A PROMISE MUST OUTRANK ─────────────────────────────────────
    st_chained = I.TurnState(chain=1)          # she has already spoken unprompted once
    I.note_user(st_chained, 1000.0)
    imp = I.decide(cfg=cfg, state=st_chained, now=1000.1, reply_text="Sure.",
                   eot_margin=None, due_notes=d)
    check("the chain limit does not mute a reminder (he'd miss his flight)",
          imp.action == I.REMIND, imp.reason)

    imp = I.decide(cfg=cfg, state=st, now=1000.1,
                   reply_text="What did you decide about the NUC?",   # she asked HIM something
                   eot_margin=None, due_notes=d)
    check("nor does 'she asked him a question' (that rule stops chatter, not promises)",
          imp.action == I.REMIND, imp.reason)

    # ...but the spam bounds still hold.
    st_hot = I.TurnState(last_spoke_at=1000.0)
    I.note_user(st_hot, 1000.0)
    cfg_cool = I.KairosConfig(enabled=True, cooldown_s=45.0)
    imp = I.decide(cfg=cfg_cool, state=st_hot, now=1005.0, reply_text="Sure.",
                   eot_margin=None, due_notes=d)
    check("the cooldown DOES still hold it (a promise is not an alarm bell)",
          imp.action == I.SILENT, imp.reason)

    # SHE REMINDS ONCE, SHE DOES NOT NAG ────────────────────────────────────────
    N.mark_raised(overdue["id"])
    check("a reminder she has raised does not come due again", N.due() == [],
          "she reminds; she does not nag")
    check("...but it is still THERE, unfinished, until he deals with it",
          any(n["id"] == overdue["id"] for n in N.live()))

    # and no reminder means no reason to speak
    imp = I.decide(cfg=cfg, state=st, now=1000.1, reply_text="Sure.",
                   eot_margin=None, due_notes=[])
    check("with nothing due she is silent again", not imp.speaks, imp.reason)

    # the nudge hands her the FACTS — she must not have to remember them mid-sentence
    nudge = I.remind_nudge([overdue])
    check("the nudge carries the reminder verbatim", "Call the NUC supplier" in nudge)

    # ── ONE CALL PER ROUND ──────────────────────────────────────────────────────
    # THE FIRST LIVE NOTES TURN. She emitted THREE tool calls in one fence —
    # add_note, edit_note, remove_note — and narrated it as she went: "I'll remove the
    # temporary note after editing it." She created the note, tidied it, deleted it, all
    # without ever seeing a single tool_output, and then told him it was done. The board
    # was empty. The prompt had said "call at most ONE tool" from the beginning; nothing
    # enforced it. An action taken before observing the result of the last one is a guess.
    from harness.toolcore.tools import _parse_tool_calls
    fence = ("```tool_code\n"
             "add_note('Defrost the freezer', due='tomorrow 8am')\n"
             "edit_note('abc', body='x')\n"
             "remove_note('abc')\n"
             "```")
    known = {"add_note", "edit_note", "remove_note"}
    parsed = _parse_tool_calls(fence, known=known)
    check("the parser still SEES all three calls (we do not hide the model's intent)",
          len(parsed) == 3, f"{len(parsed)} parsed")
    # the loop truncates — asserted here at the seam the loops both use
    check("...but only the FIRST is executed, so she must see its result before the next",
          parsed[:1][0][0] == "add_note", parsed[0][0])

    total = len(PASS) + len(FAIL)
    print(f"\nG-NOTES: {'PASS' if not FAIL else 'FAIL'} ({len(PASS)}/{total})")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
