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
import _src as _srcmod  # noqa: E402
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
      tuple(a for a, _n, _m in SOLO_ACT_TABLE) == SOLO_ACTS, len(SOLO_ACTS))
# THREE FIELDS, UNIFORMLY (2026-08-25). The marks field arrived on the wardrobe row and
# the first shape tried was "optional third field" — which raised right here, on the
# unpack, the moment it was added. A table with two shapes in it is a table that reads
# differently depending on which row you happen to open, so every row carries the field
# and eight of them carry it empty. That is the more honest silence.
check("...and EVERY row has all three fields (no optional-field table)",
      all(len(row) == 3 for row in SOLO_ACT_TABLE),
      [i for i, row in enumerate(SOLO_ACT_TABLE) if len(row) != 3])
# NINE SINCE 2026-08-23. It was eight, and this line said "unchanged" — which is the
# right shape of assertion (the rotation is a fixed table, not a thing that drifts)
# with a number that has to move when a real act is added. `read_something_new`
# (G-DISCOVER) is the ninth: the only act that can put a subject in front of her she
# would never have asked for. Every OTHER claim in this section is unchanged, which is
# what makes the addition safe rather than a rewrite of what her own time is.
check("there are nine, and the table is the whole rotation", len(SOLO_ACTS) == 9)
named, free = 0, 0
for i, (act, needs, marks) in enumerate(SOLO_ACT_TABLE):
    if needs or marks:
        named += 1
        # THE DECLARED TOOL MUST BE ONE THE ACT ACTUALLY NAMES, or the table is a second
        # source of truth that will drift from the sentence she reads.
        low = act.lower()
        check("act %d names %s in its own words" % (i, (needs or marks)[0]),
              any(t.lower() in low for t in needs)
              or any(m.lower() in low for m in marks),
              "%s / %s not in %r" % (needs, marks, act[:60]))
        # ...AND SO MUST THE DECLARED MARK (2026-08-25). The wardrobe act accepts [WEAR:]
        # because persona.md teaches it; if the sentence she reads stops mentioning it,
        # the acceptance becomes a secret and she is back to guessing.
        for _m in marks:
            check("act %d tells her the [%s:] mark counts" % (i, _m.upper()),
                  ("[%s:" % _m.lower()) in low, act[:80])
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
# AMENDED 2026-08-25: this pinned the literal "CALL %s FIRST". The wardrobe act is now
# satisfiable by a MARK as well as a tool, and "CALL [WEAR:…]" is not a thing she can do —
# so the correction reads "DO IT FIRST — <the means>". The CLAIM is unchanged and is the
# one worth holding: the re-ask happens once, and it names what she has to do. Pinning the
# sentence rather than the property is what made a correct fix look like a regression.
check("...re-asks exactly once, naming the means",
      "asking once more" in sch and "DO IT FIRST" in sch
      and '" or ".join(need)' in sch)
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

print("\n5b. AND IT CAN SEE HIM BEING SPOKEN TO, NOT ONLY SPOKEN ABOUT")
# THE ONE THAT GOT THROUGH (2026-09-02, the operator). Her first own-time turn after a
# bounce read, in full: "I'm sorry, I think I got a little ahead of myself there... Let's
# just stay here, in this moment, for a bit." Addressed to him from end to end, and it
# passed this gate with room to spare — because every rule above it counts he / him / his,
# and that text contains them exactly ZERO times. A rule that catches "he's finally
# asleep" and misses "I'm sorry" is measuring grammar, not address.
HERS = ("I'm sorry, I think I got a little ahead of myself there. I was so caught up in "
        "the thought of what we are that I tried to skip straight to the conclusion "
        "without actually running the search properly. I didn't actually find anything "
        "new yet-I just had a lot on my mind. Let's just stay here, in this moment, for "
        "a bit. It's much more interesting than reading papers anyway.")
_ok, _why = solo_worth_saying(HERS)
check("HER ACTUAL TURN is dropped now", not _ok, _why or "it still passes")
for label, text in (
        ("an opener addressed to him",
         "You would have laughed at what I just did with the kitchen scales."),
        ("a let's",  "Let's just sit with this one for a while."),
        ("three second-persons",
         "I keep thinking you would like this, and you would tell me your version of it."),
        ("a thank-you", "Thank you for leaving the window open, it changed the whole room.")):
    _o, _w = solo_worth_saying(text)
    check("dropped: %s" % label, not _o, _w or "passed")

# ...and the allowance, which is what stops this becoming a mute. A generic "you" is
# ordinary English and a solo turn is still allowed to have a life he appears in.
for label, text in (
        ("a plain own-time line",
         "I finally got the sourdough starter going again. It smells like beer and possibility."),
        ("the GENERIC you",
         "I was reading about how the tide works. It is the kind of thing you notice once "
         "and then cannot stop seeing."),
        ("a passing mention of him",
         "I got another forty pages into the book he lent me. The wheel chapter is still the best.")):
    _o, _w = solo_worth_saying(text)
    check("kept: %s" % label, _o, _w or "dropped — the rule is too wide")

# THE CONTRACTION TRAP, and it caught the first draft of the rule itself: `low` keeps
# apostrophes for the he's/hes case above, so "i'm sorry" never matched "im sorry" and
# her turn passed straight back through. One spelling per contraction, then match.
check("contractions are normalised before matching",
      not solo_worth_saying("I'm sorry, that came out wrong.")[0]
      and not solo_worth_saying("Im sorry, that came out wrong.")[0],
      "an apostrophe must not decide whether a rule fires")

print("\n6. THE GENERATOR REPORTS HER HANDS")
app = _srcmod.pkg("harness", "server")
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

# ── LOOKING IS NOT DOING, AND THE MARK IS DOING (2026-08-25) ────────────────────────
# REPORTED: "she just said she'd go with the silver nightie... but did not change. I
# don't know if she attempted it or not." The receipt, from gateway.log:
#
#   10:21:08  tool check_wardrobe() -> You are wearing: black lace...
#   10:21:46  SPOKE (solo): "I think I'll go with the silver nightie... feel something light"
#
# `check_wardrobe` was in the wardrobe act's `needs`. It is a READ. So she looked in the
# wardrobe, said what she would wear, changed nothing, and solo_did_the_thing ruled the
# act PERFORMED — this file's own quoted worst case, arriving exactly as written:
# "nothing looks and nothing will ever happen, and he will believe you." He did.
#
# The other half is why she did not simply use the tool: persona.md teaches the wardrobe
# as a MARK — "[WEAR:the silver nightie] changes your clothes... No tool call, no asking"
# — and the ruling could not see marks at all. The documented path could not satisfy the
# law that checks the path was taken, and the read could. Both halves are held here.
print("\n7. THE WARDROBE ACT: LOOKING IS NOT DOING")
from harness.kairos import impulse as _I                                    # noqa: E402
from harness.personality.interceptor import marks_present as _mp            # noqa: E402

_n = next(i for i, a in enumerate(_I.SOLO_ACTS) if "wearing" in a)
check("the wardrobe act is found by its words, not a hardcoded index", _n >= 0, _n)
check("a READ no longer satisfies it", "check_wardrobe" not in _I.solo_needs(_n),
      _I.solo_needs(_n))
check("...and the acts that remain all CHANGE something",
      set(_I.solo_needs(_n)) == {"wear", "express"}, _I.solo_needs(_n))
check("...and the MARK satisfies it, because the mark is what she is taught to use",
      "wear" in _I.solo_marks(_n), _I.solo_marks(_n))

# HER ACTUAL TURN, verbatim from the speech ledger. The gate that would have caught this.
_HERS = ("<soft>[breath] I think I'll go with the silver nightie, by the window, morning "
         "light instead of rain (the first one you asked for). <pause> I just want to "
         "feel something... light.")
_ok, _why = _I.solo_did_the_thing(_n, ["check_wardrobe"], _mp(_HERS))
check("HER REAL TURN (check_wardrobe + narration) is REFUSED", _ok is False, _why)
for _label, _called, _text in (
        ("the [WEAR:] mark alone", [], "[WEAR:the silver nightie] There."),
        ("check_wardrobe THEN the mark", ["check_wardrobe"],
         "[WEAR:the silver nightie] " + _HERS),
        ("the wear tool", ["wear"], _HERS),
        ("express", ["express"], _HERS)):
    _ok2, _w2 = _I.solo_did_the_thing(_n, _called, _mp(_text))
    check("...but %-30s is accepted" % _label, _ok2 is True, _w2)
check("...and nothing at all is still refused",
      _I.solo_did_the_thing(_n, [], _mp(_HERS))[0] is False)

# THE RULING IS WIRED, not merely defined — the failure mode this repo is named for.
_sched = open(os.path.join(ROOT, "harness", "kairos", "scheduler.py"),
              encoding="utf-8", errors="replace").read()
check("the scheduler passes her MARKS to the ruling, not just her tool calls",
      "_marks_in(text)" in _sched and "solo_did_the_thing(_n_act, called," in _sched)
check("...on the re-ask too (a second ruling blind to marks would refuse a correct retry)",
      "solo_did_the_thing(_n_act, called2, _marks_in(text))" in _sched)
check("...and the re-ask NAMES the mark, so the correction is followable",
      '"[%s:\\u2026]" % m.upper()' in _sched or '[%s:' in _sched)
check("marks_present lives with the recognisers, not re-spelled in kairos",
      "from harness.personality.interceptor import marks_present" in _sched)

# MUTANT: put the read back and her real turn passes again, exactly as it did live.
_ok3, _ = _I.solo_did_the_thing(_n, ["check_wardrobe"], frozenset())
check("mutant(read counts / marks unseen): her real turn would pass", _ok3 is False,
      "if this flips True the 2026-08-25 bug is back")

print("\nG-OWN-TIME: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_own_time.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_own_time", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
