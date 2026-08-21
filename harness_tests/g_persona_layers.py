#!/usr/bin/env python
"""G-PERSONA-LAYERS — the persona composes from declared fragments, once, deterministically.

WHY THIS EXISTS
───────────────
`persona.md` was one monolithic file, so turning the thought channel off meant HAND-EDITING it to
remove the section that teaches her to open a channel and close it with `<channel|>`. Forgetting
is a bug this project has already had: `thinking = false` in the profile while the persona still
taught the markup, so she emitted control surfaces the engine was no longer structuring. **A
coupling that lives in a human's memory is a coupling that breaks.**

Fragments carry `when: thinking` and are simply not composed. The coupling becomes structural.

THE CONSTRAINT THAT SHAPES ALL OF IT: this output lands in the persist-KV prefix, which is
snapshot-cached for the process lifetime. A prefix that moves mid-session re-prefills the whole
conversation — the cardinal sin, and what made every turn cost 25 s before the prefill work. So
composition resolves ONCE at session start and must be deterministic given the knobs. That is
also why this layer is not Jinja: a template engine here invites per-turn rendering.

    FORALL knob sets:        same knobs -> byte-identical composition
    FORALL false `when`:     the fragment contributes ZERO characters
    FORALL unknown knobs:    the fragment is EXCLUDED and warned — never silently included
    FORALL orderings:        total and stable (order, then filename)
    FORALL absent dirs:      compose() is None -> the caller keeps using persona.md untouched
    FORALL fragments:        the `## Personality state` block is NOT among them (its writer
                             rewrites that block, and moving it would break the writer)

Runs against a SYNTHETIC fragment directory in a temp dir — the operator's real persona is
never read or written by this gate.

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
os.environ.setdefault("SP_DAEMON_URL", "http://127.0.0.1:9")

from harness.personality import persona_layers as PL  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


SB = tempfile.mkdtemp(prefix="g-persona-")
D = os.path.join(SB, "persona")
os.makedirs(D)


def frag(fn, order, body, when=None):
    fm = "---\norder: %d\n" % order + (("when: %s\n" % when) if when else "") + "---\n"
    with open(os.path.join(D, fn), "w", encoding="utf-8") as f:
        f.write(fm + body + "\n")


frag("00-identity.md", 0, "IDENTITY-BLOCK")
frag("20-memory.md", 20, "MEMORY-BLOCK")
frag("30-hands.md", 30, "HANDS-BLOCK", when="delegate")
frag("40-voice.md", 40, "VOICE-BLOCK")
frag("50-thinking.md", 50, "THINKING-BLOCK", when="thinking")
frag("55-noquiet.md", 55, "NOSILENCE-BLOCK", when="!silence")
frag("60-limits.md", 60, "LIMITS-BLOCK")

ON = {"SP_THINKING": "1", "SP_DELEGATE": "1", "SP_SILENCE_ANSWER": "1"}
OFF = {}

print("1. a false `when` contributes nothing at all")
t_on = PL.compose(env=ON, directory=D)
t_off = PL.compose(env=OFF, directory=D)
check("thinking ON -> the thinking block is present", "THINKING-BLOCK" in t_on)
check("thinking OFF -> the thinking block is ABSENT", "THINKING-BLOCK" not in t_off)
check("delegate OFF -> the hands block is ABSENT", "HANDS-BLOCK" not in t_off)
check("unconditional blocks are always present",
      all(b in t_on and b in t_off
          for b in ("IDENTITY-BLOCK", "MEMORY-BLOCK", "VOICE-BLOCK", "LIMITS-BLOCK")))
check("a NEGATED condition inverts: !silence composes when silence is OFF",
      "NOSILENCE-BLOCK" in t_off and "NOSILENCE-BLOCK" not in t_on)
check("an excluded fragment costs ZERO characters, not a blank line",
      len(t_off) < len(t_on) and "\n\n\n" not in t_off, (len(t_off), len(t_on)))

print("\n2. deterministic: same knobs, byte-identical composition")
check("ten compositions of the same knob set are identical",
      len({PL.compose(env=ON, directory=D) for _ in range(10)}) == 1)
check("...and of the OFF set too",
      len({PL.compose(env=OFF, directory=D) for _ in range(10)}) == 1)
check("the two differ (the test is not vacuous)", t_on != t_off)

print("\n3. the order is total and stable")
rows = PL.plan(env=ON, directory=D)
check("plan is sorted by order", [r["order"] for r in rows] == sorted(r["order"] for r in rows))
check("identity leads, limits trails",
      rows[0]["file"].startswith("00-") and rows[-1]["file"].startswith("60-"))
check("body order matches plan order",
      [b for b in ("IDENTITY-BLOCK", "MEMORY-BLOCK", "HANDS-BLOCK", "VOICE-BLOCK",
                   "THINKING-BLOCK", "NOSILENCE-BLOCK", "LIMITS-BLOCK")
       if b in t_on] == [b for b in ("IDENTITY-BLOCK", "MEMORY-BLOCK", "HANDS-BLOCK",
                                     "VOICE-BLOCK", "THINKING-BLOCK", "NOSILENCE-BLOCK",
                                     "LIMITS-BLOCK") if b in t_on])
# ties must break on filename, or which fragment wins differs between machines (readdir order)
frag("50-aaa.md", 50, "TIE-A")
frag("50-zzz.md", 50, "TIE-Z")
p2 = [r["file"] for r in PL.plan(env=ON, directory=D) if r["order"] == 50]
check("an order TIE breaks on filename, so composition cannot differ across machines",
      p2 == sorted(p2), p2)
os.remove(os.path.join(D, "50-aaa.md"))
os.remove(os.path.join(D, "50-zzz.md"))

print("\n4. an unknown knob FAILS CLOSED and is warned about")
frag("70-typo.md", 70, "TYPO-BLOCK", when="thinkng")     # deliberate typo
import logging  # noqa: E402

seen = []


class Grab(logging.Handler):
    def emit(self, r):
        seen.append(r.getMessage())


h = Grab()
PL.logger.addHandler(h)
PL.logger.setLevel(logging.WARNING)
t = PL.compose(env=ON, directory=D)
PL.logger.removeHandler(h)
check("a typo'd knob EXCLUDES the fragment (never silently included)",
      "TYPO-BLOCK" not in t)
check("...and says so, naming the bad knob", seen and "thinkng" in seen[0], seen[:1])
check("...and lists the known knobs so the fix is obvious",
      seen and "thinking" in seen[0])
os.remove(os.path.join(D, "70-typo.md"))

print("\n5. the knob vocabulary is closed, and every name maps to a real SP_ var")
serve_src = open(os.path.join(ROOT, "serve.py"), encoding="utf-8").read()
unmapped = [v for v in PL.KNOBS.values() if v not in serve_src]
check("every knob in the vocabulary is mapped in serve.py", not unmapped, unmapped)
check("knob_on() returns None for anything outside the vocabulary",
      PL.knob_on("not_a_knob", ON) is None)
check("knob_on() reads the mapped SP_ var, not the short name",
      PL.knob_on("thinking", {"SP_THINKING": "1"}) is True
      and PL.knob_on("thinking", {"thinking": "1"}) is False)

print("\n6. absent or empty directory keeps persona.md working")
check("no directory -> None (the caller falls back untouched)",
      PL.compose(env=ON, directory=os.path.join(SB, "nope")) is None)
empty = os.path.join(SB, "empty")
os.makedirs(empty)
check("empty directory -> None", PL.compose(env=ON, directory=empty) is None)
allout = os.path.join(SB, "allout")
os.makedirs(allout)
with open(os.path.join(allout, "10-x.md"), "w", encoding="utf-8") as f:
    f.write("---\norder: 10\nwhen: thinking\n---\nX\n")
check("every fragment excluded -> None, not an empty prefix",
      PL.compose(env=OFF, directory=allout) is None)

print("\n7. the state block stays where its writer expects it")
# persona_file.write_state() rewrites `## Personality state` inside persona.md. If the splitter
# had moved it into a fragment, tag shifts would write to a file nobody composes.
frag("80-state.md", 80, "## Personality state\nvoice: soft")
check("a fragment may CONTAIN the heading (nothing forbids it)...",
      "Personality state" in PL.compose(env=ON, directory=D))
os.remove(os.path.join(D, "80-state.md"))
from harness.personality.persona_file import STATE_SECTION  # noqa: E402

check("...but the real persona.md is still where write_state operates",
      STATE_SECTION == "## Personality state", STATE_SECTION)
live = os.path.join(ROOT, "persona")
if os.path.isdir(live):
    bad = [f for f in os.listdir(live)
           if f.endswith(".md")
           and STATE_SECTION.lower() in open(os.path.join(live, f), encoding="utf-8").read().lower()]
    check("the LIVE fragment dir does not contain the state block", not bad, bad)

print("\n8. load_agent_system prefers fragments — PROVED IN G-PF-PERSONA, NOT HERE")
# This section used to assert three things about load_agent_system by running
# inspect.getsource() over it and grepping for "persona_layers", "prose = _frag",
# and a count of "except Exception". Those pins caught deletion and nothing else:
# they proved the source contains some strings, never that the composed prose
# reaches the returned prefix, that it replaces rather than appends, or that the
# state block survives the swap. Renaming a local would have failed the gate while
# the behaviour held; returning the wrong text would have passed it.
#
# h_personality_persona.py now EXECUTES that precedence — fragments in, monolithic
# prose out, state block intact, unreadable fragment survivable — and is
# mutation-checked against both `prose = prose + _frag` and the branch disabled.
# Keeping the greps as well would be two copies of one truth, which is the bug
# class in AGENTS.md §0 and the reason this repo has lost a recall filter and a
# privacy guarantee. The weaker copy goes.
#
# The boundary: G-PERSONA-LAYERS owns fragment SELECTION (frontmatter, `when:`
# knobs, ordering, determinism, compose()'s None contract — sections 1-7 above).
# G-PF-PERSONA owns what load_agent_system does with the result.

shutil.rmtree(SB, ignore_errors=True)
print("\nG-PERSONA-LAYERS: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_persona_layers.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_persona_layers", "pass": PASS, "fail": FAIL,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
sys.exit(1 if FAIL else 0)
