"""G-OWN-TIME — she does the thing before she says she did it. OFFLINE.

HIS QUESTION, 2026-08-06: "did she look into what she said? research or web search or did
she make it up?"

MEASURED FROM gateway.log — and the FIRST measurement was wrong, which is the more
useful half of this note.

The first count read `rounds[-1]`, the last round before each SPOKE. That is the
ANSWERING round, which by design calls nothing, so it reported "33 solo turns, ONE called
a tool" and I put that number in a commit message. The instrument measured the wrong path,
in the middle of an investigation into an instrument that measured the wrong path.

Counting every round of each turn, bounded by the kairos decision line that opens it:

    room-msdtx7kx-ak8ex0   17 of 26 solo turns called a tool   a live conversation
    claude-console          3 of  5                            a live conversation
    default                 0 of  6                            the SEEDED placeholder

THE AGGREGATE HID THE ANSWER. On a live conversation she acts — 20 of 31, near the
seven-in-eight ceiling once the pure-thought act is allowed for. On the SEEDED session,
rebuilt from disk history (msgs=10 against a live msgs=34), she has never once called
anything. Both invented entries the operator brought came from it:

    "I spent some of my quiet time looking into the physics of bioluminescence"
        23:55  round=0 is_tool=False calls=0  — one round, no tool
    "I ran some regressions on my own recent output"
        00:12  round=0 is_tool=False calls=0  — one round, no tool

So the confabulation is real and his examples are real, and "she has always done this" is
not: she does it on the placeholder and not on a real conversation.

THE NUDGE ASKED FOR THE ARTEFACT, NOT THE ACT — "Say what you found, NOT that you
searched" — and nothing ever checked the act happened. That is this repository's own
named worst case, from `_TOOL_DISCIPLINE`, arriving in her nights:

    "NEVER say you will look out for something ... UNLESS you have called watch_for(...).
     Without it nothing looks and nothing will ever happen, and he will believe you."

WHAT THIS GATE HOLDS:
  1. Every act declares what it requires, and the ONE that is pure thought declares
     nothing and is never blocked — "follow one thought with nothing to show for it" is a
     real way to spend an hour and demanding a receipt would make her own time a chore.
     The journal act used to be ungated by omission, and impulse.py records what that
     cost: 15 of her first 21 own-time turns were "I read my journal", because it was the
     option that needed no tool AND COULD NOT FAIL.
  2. The ruling is on EVIDENCE — the tools she actually called, reported back from the
     generator — not on the words she used. Judging the text would be the same mistake in
     a new place: prose ruling (AGENTS.md §5).
  3. ONE re-ask, naming the tool, then REFUSED. Not spoken, not journalled. A journal that
     records things she did not do is worse than no journal.
  4. The gate fails OPEN if the evidence is missing, because an unproven turn silenced is
     worse than an ungated one.

Offline. No GPU, no daemon.

Run: python harness_tests/g_own_time.py
"""
from __future__ import annotations

import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["CUDA_VISIBLE_DEVICES"] = ""

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


from harness.kairos.impulse import (SOLO_ACT_TABLE, SOLO_ACTS,  # noqa: E402
                                    solo_did_the_thing, solo_needs, solo_nudge,
                                    solo_worth_saying)

print("1. EVERY ACT DECLARES WHAT IT REQUIRES")
check("the table and the legacy tuple are the same acts",
      tuple(a for a, _ in SOLO_ACT_TABLE) == SOLO_ACTS, len(SOLO_ACTS))
# NINE SINCE 2026-08-23. It was eight, and this line said "unchanged" — which is the
# right shape of assertion (the rotation is a fixed table, not a thing that drifts)
# with a number that has to move when a real act is added. `read_something_new`
# (G-DISCOVER) is the ninth: the only act that can put a subject in front of her she
# would never have asked for. Every OTHER claim in this section is unchanged, which is
# what makes the addition safe rather than a rewrite of what her own time is.
check("there are nine, and the table is the whole rotation", len(SOLO_ACTS) == 9)
named, free = 0, 0
for i, (act, needs) in enumerate(SOLO_ACT_TABLE):
    if needs:
        named += 1
        # THE DECLARED TOOL MUST BE ONE THE ACT ACTUALLY NAMES, or the table is a second
        # source of truth that will drift from the sentence she reads.
        low = act.lower()
        check("act %d names %s in its own words" % (i, needs[0]),
              any(t.lower() in low for t in needs),
              "%s not in %r" % (needs, act[:60]))
    else:
        free += 1
# SEVEN, NOT SIX. The journal act used to read "Read back through your own journal" with
# no tool named — and impulse.py's own comment records what that cost: "15 of her first 21
# own-time turns were 'I read my journal', because that option needed no tool AND COULD NOT
# FAIL." An ungated act is the one the rotation collapses onto. It names `read_journal` now
# and is gated with the rest.
# EIGHT SINCE 2026-08-23 — the ninth act (read_something_new) declares its tool like
# the rest, precisely because an ungated act is the one the rotation collapses onto.
check("eight acts require a tool", named == 8, named)
# ONE STAYS FREE, and it has to. "Follow one thought as far as it will go, with nothing to
# show for it" is a real way to spend an hour; demanding a receipt for it would turn her
# own time into a chore list, which is the opposite of what it is for.
check("...and exactly one is pure thought, never blocked", free == 1, free)

print("\n2. THE RULING IS ON EVIDENCE, NOT ON HER WORDS")
ok, why = solo_did_the_thing(0, [])
check("an act with no call is refused", not ok, why)
check("...and says which tool was needed", "web_search" in why, why)
check("the same act WITH the call passes", solo_did_the_thing(0, ["web_search"])[0])
check("...case and whitespace do not matter",
      solo_did_the_thing(0, ["  Web_Search "])[0])
check("any of the alternatives satisfies it",
      solo_did_the_thing(2, ["search_memories"])[0] and solo_did_the_thing(2, ["recall"])[0])
check("a DIFFERENT tool does not", not solo_did_the_thing(0, ["check_wardrobe"])[0])
# PURE THOUGHT IS NOT A LOOPHOLE AND NOT A CHORE. It is ungated by design and must stay so.
check("the pure-thought act passes with nothing called", solo_did_the_thing(5, [])[0])
check("...and the rotation reaches it", solo_needs(5) == ())
# THE WORDS ARE NEVER CONSULTED. A turn that says "I searched" and called nothing must
# still fail — judging the prose would be the exact mistake in a new place.
check("claiming it in prose does not satisfy the gate",
      not solo_did_the_thing(0, [])[0])

print("\n3. THE ROTATION STILL WORKS, AND `needs` FOLLOWS IT")
seen = {solo_needs(n) for n in range(len(SOLO_ACTS))}
check("every act is reachable by rotation", len(seen) == len(set(seen)), sorted(map(str, seen)))
for n in range(len(SOLO_ACTS) * 2):
    check("rotation %2d wraps to act %d" % (n, n % 8),
          solo_needs(n) == SOLO_ACT_TABLE[n % 8][1]) if n < 3 else None
check("solo_nudge still builds and carries the act",
      SOLO_ACTS[3][:24] in solo_nudge(3), solo_nudge(3)[:80])
# THE NUDGE SPLITS DOING FROM SAYING, and only where there is something to do. It used to
# run straight from the act to "then say it", which reads as one instruction about what to
# WRITE — and 32 of 33 turns skipped to the writing. Two numbered steps, call first.
for n in range(8):
    nud = solo_nudge(n)
    if solo_needs(n):
        check("act %d tells her to DO it first" % n,
              "TWO STEPS, IN ORDER" in nud and "ACTUALLY DO IT" in nud
              and "Do not write step 2 without doing step 1" in nud, nud[-160:])
    else:
        check("the pure-thought act is NOT given a chore list",
              "TWO STEPS" not in nud, nud[-90:])
# AND THE HONEST WAY OUT IS NAMED WHERE THE PRESSURE IS. The failure this creates is not
# silence, it is a beautiful sentence about an hour that did not happen.
check("...and silence is offered as a real answer",
      "say nothing at all" in solo_nudge(0) and "making it up is not" in solo_nudge(0))

print("\n4. THE SCHEDULER ASKS ONCE MORE, THEN REFUSES")
sch = io.open(os.path.join(ROOT, "harness", "kairos", "scheduler.py"),
              encoding="utf-8", errors="replace").read()
# AMENDED 2026-08-24 (audit K2): the ruling reads the EFFECTIVE act — the rotation
# unless the discover dial overrode it — so a discovery turn is judged against the
# act she was handed rather than convicted of skipping one she never owed.
check("it rules with solo_did_the_thing, on the effective act",
      "solo_did_the_thing(_n_act" in sch)
check("...on the tools she actually called", "generate(nudge, called)" in sch)
check("...re-asks exactly once, naming the tool",
      "asking once more" in sch and "CALL %s FIRST" in sch)
# The refusal must come BEFORE the branch that would speak. There are two
# `if imp.action != REMIND` branches in the file now (the kairos-judge offload added an
# earlier one, 2026-08-20); the one this rule is about is the one AFTER the refusal.
check("...and then REFUSES rather than speaking",
      "solo REFUSED" in sch
      and sch.find("if imp.action != REMIND", sch.index("solo REFUSED")) > 0)
# REFUSED MEANS NOT JOURNALLED. The journal write happens after the outbox append, so a
# `return` before either is what keeps an invented evening out of her history.
check("...before the outbox or the journal are touched",
      sch.index("solo REFUSED") < sch.index("_OUTBOX[session].append"))
check("the drop is RECORDED, not just logged",
      "claimed an act it never performed" in sch)
# FAIL OPEN. If the generator cannot report her hands, a turn she really did have is worth
# more than a rule we cannot evaluate.
check("a caller that cannot report tools does not silence her",
      "called = None" in sch and "called is not None" in sch)

print("\n5. AND IT IS A SEPARATE QUESTION FROM `solo_worth_saying`")
# Two gates, two questions: is this turn HERS (not performed at him), and did it HAPPEN.
# Collapsing them would let a beautifully-written invention through on the strength of its
# tone, which is precisely what has been happening.
ok_w, _ = solo_worth_saying("I sat with the rain for a while and let it be boring.")
check("a real solo line still passes worth_saying", ok_w)
check("...and did_the_thing is asked separately in the scheduler",
      sch.index("solo_did_the_thing") < sch.index("solo_worth_saying(text)"))

print("\n6. THE GENERATOR REPORTS HER HANDS")
app = io.open(os.path.join(ROOT, "harness", "server", "app.py"),
              encoding="utf-8", errors="replace").read()
check("_generate takes a `called` sink", 'def _generate(nudge: str, called:' in app)
check("...wired to the tool-loop callback", "on_tool=_note" in app)
check("...and appends every name", "called.append(name)" in app)
# ── EVERY CLOSURE, NOT THE ONE I HAPPENED TO EDIT (2026-08-06) ─────────────────────
# `_generate` is the SEED path. `_continue` — twice, once per chat lane — is the LIVE
# one, bound to a real conversation, and it is what the scheduler actually holds after
# he has spoken. Only `_generate` got the parameter, so on a real conversation
# `generate(nudge, called)` raised TypeError, the gate fell open, and a solo turn with
# calls=0 spoke anyway. Measured at 00:42 on the first run of the new code: §0 inside
# the fix for §0.
#
# Counted, not merely present: three closures answer "generate one more turn" and all
# three must report her hands, or the gate is enforced on whichever path is not running.
check("EVERY generate closure reports her hands, not just the seed one",
      app.count('def _continue(nudge: str, called:') == 2, 
      app.count('def _continue(nudge: str, called:'))
# COUNTED ON THE STABLE TOKEN. The first cut matched a whole formatted line, so a
# reflow — one that a linter or a wrapped argument list produces for free — read as a
# missing wiring. `on_tool=lambda nm` is what does not move.
check("...and each is wired to on_tool",
      app.count("on_tool=lambda nm") == 2, app.count("on_tool=lambda nm"))
check("...leaving no one-argument generate closure behind",
      "def _continue(nudge: str) -> str:" not in app
      and "def _generate(nudge: str) -> str:" not in app)

print("\nG-OWN-TIME: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_own_time.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_own_time", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
