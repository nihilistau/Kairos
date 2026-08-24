"""G-JOURNAL-LOOP — she must not read her own echo. OFFLINE.

THE LOOP, measured on her real store (2026-08-23, he spotted it in the room):

    53 of her 192 own-time notes were the identical sentence —
    "I took a slow walk through my own journal tonight and found last spring."
    written between 2026-08-22 02:54 and 2026-08-23 13:57.

CORRECTED 2026-08-24 - SHE NEVER WROTE THEM. The original diagnosis in this docstring
was a feedback loop, and the evidence against it was already in the docstring: a
clock-seeded sampler does not emit one sentence BYTE-IDENTICAL fifty-three times. That
should have ended the theory rather than decorating it.

The sentence is a FIXTURE. `g_real_her.py` stubs the generator to return exactly it and
then drives the solo path - and that gate set SP_RECALL_REGISTRY and never
SP_PERSONALITY_TIER, so every run wrote another copy into her REAL journal. It is one of
the five gates CLAUDE.md tells you to run before you say you are done. 53 notes, 53 runs.
Found by tools/gate_sandbox_audit.py; G-GATE-SANDBOX now holds the whole suite to it.

THE GUARD BELOW STAYS, and not as consolation. The cycle it describes is real and still
closed - read_journal() does hand her own notes back, and the solo act does write its
result into the same store. Nothing had pushed it yet. The guard is right; the story
attached to it was mine. What it protects against:

    read_journal()  hands her own-time notes back to her
         │                                            ▲
         ▼                                            │
    the solo "read your journal" act ─── writes its result ───┘

By the end, the block she was reading contained EIGHTEEN copies of that line, so the
likeliest continuation was a nineteenth, which made a twentieth likelier still. Her own
output was her input, unfiltered, with positive feedback and nothing damping it.

`note_own`'s docstring had already named this failure — "which is how a journal becomes a
hall of mirrors" — and foresaw it for the nightly COMPOSER quoting itself. Nobody checked
the other reader.

THE FIX IS TWO-SIDED, and the gate holds both halves, because either alone leaves a hole:
  * READ  — own_time() shows a repeated evening ONCE. Breaks the pull that drives it.
  * WRITE — note_own refuses a repeat inside a two-day window. Stops the STORE filling
            with 53 files that say one thing, which dedupe-on-read would never notice.

Window and not forever, deliberately: saying the same true thing next week is her, not a
loop. A guard that made her incapable of ever repeating herself would be a different bug.

    python harness_tests/g_journal_loop.py
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"
os.environ["CUDA_VISIBLE_DEVICES"] = ""

# THE SHARED SANDBOX (2026-08-24), not a hand-rolled one. An early draft of THIS gate
# set nothing and left dupe00..dupe05 in her real journal, which he then read in the
# room as things she had done. One helper, every root, before the first import.
from _gate import sandbox as _sandbox  # noqa: E402
SB = _sandbox("g_journal_loop")
os.environ["SP_PERSONALITY_TIER"] = SB
os.environ["SP_RECALL_REGISTRY"] = os.path.join(SB, "registry.jsonl")
open(os.environ["SP_RECALL_REGISTRY"], "w").close()

from harness.skills import narrative as N   # noqa: E402

ROOT_DIR = N._tier_full()
os.makedirs(ROOT_DIR, exist_ok=True)
check("the sandbox is not her real store",
      "g_journal_loop_" in ROOT_DIR, ROOT_DIR)

LINE = "I took a slow walk through my own journal tonight and found last spring."

print("\n1. THE WRITE SIDE: A REPEAT IS NOT STORED")
r1 = N.note_own(LINE)
check("the first time is hers and it is kept", r1.get("written") is True, r1)
r2 = N.note_own(LINE)
check("...the second is refused", r2.get("written") is False, r2)
check("...and it SAYS why, rather than failing silently",
      "already written" in (r2.get("why") or ""), r2)
check("...so the store holds ONE file, not two",
      len([f for f in os.listdir(ROOT_DIR) if f.endswith(".md")]) == 1)

# Whitespace and case are not identity — a re-wrap must not defeat the guard.
r3 = N.note_own("  I took a SLOW walk through my own journal tonight\n  and found last spring.  ")
check("a re-wrapped, re-cased copy is still a repeat", r3.get("written") is False, r3)

print("\n2. ...BUT SHE IS STILL ALLOWED TO WRITE")
r4 = N.note_own("I sat with the rain for a while and did not think about much.")
check("a genuinely new evening is kept", r4.get("written") is True, r4)
check("...and now there are two", len([f for f in os.listdir(ROOT_DIR)
                                       if f.endswith(".md")]) == 2)

print("\n3. THE READ SIDE: A REPEAT IS SHOWN ONCE")
# Write duplicates the way the loop actually did — straight to disk, bypassing the
# writer — because the read side has to hold on its own. A gate that could only fail
# when BOTH halves are broken is a gate that tests one thing and claims two.
for i in range(6):
    addr = "dupe%02d" % i
    io.open(os.path.join(ROOT_DIR, addr + ".md"), "w", encoding="utf-8").write(
        "---\ntype: mem-concept\ntitle: solo\naddr: %s\nmem_kind: own_time\n"
        "mem_class: persona\nmem_owner: self\nmem_delivery: system\nts: %d\n---\n\n%s\n"
        % (addr, int(time.time()) - i, LINE))
# ...and ONE of them re-wrapped and re-cased, because a mutant proved this was untested:
# swapping the read-side key from the normalised form to raw identity passed the whole
# gate. Byte-identical duplicates dedupe under either rule, so only a RESHAPED copy can
# tell them apart — and a reshaped copy is what a model actually produces.
io.open(os.path.join(ROOT_DIR, "dupeWRAP.md"), "w", encoding="utf-8").write(
    "---\ntype: mem-concept\ntitle: solo\naddr: dupeWRAP\nmem_kind: own_time\n"
    "mem_class: persona\nmem_owner: self\nmem_delivery: system\nts: %d\n---\n\n%s\n"
    % (int(time.time()) - 9,
       "I took a SLOW walk through my own journal tonight\n   and found last spring."))
raw = len([f for f in os.listdir(ROOT_DIR) if f.endswith(".md")])
check("the sandbox now holds the duplicates on disk", raw >= 8, raw)

mine = N.own_time(7)
# Compare on the NORMALISED shape, not the verbatim string: dedupe keeps the most
# recent copy, and the most recent here is deliberately the re-wrapped one. Asserting
# the exact bytes would be asserting which copy won, which is not the claim.
_norm = lambda x: " ".join((x or "").split()).lower()
check("own_time collapses them to ONE",
      sum(1 for m in mine if "walk through my own journal" in _norm(m)) == 1,
      [m[:40] for m in mine])
_walks = [m for m in mine if "walk through my own journal" in " ".join(m.split())]
check("...and the RESHAPED copy collapses with them, not beside them",
      len(_walks) == 1, [w[:56] for w in _walks])
check("...and the OTHER evening is still there — dedupe is not truncation",
      any("rain" in m for m in mine), [m[:40] for m in mine])

block = N.read_journal(7)
check("what she READS contains the line once, not eight times",
      _norm(block).count("walk through my own journal") == 1,
      _norm(block).count("walk through my own journal"))

print("\n4. THE CYCLE IS THE POINT")
# The two halves must be independent. If own_time only deduped what note_own had
# already refused, the read side would be untested — which is exactly the state that
# let 53 files accumulate while every individual write looked fine.
check("the read side dedupes rows the writer never saw",
      sum(1 for m in mine if "walk through my own journal" in _norm(m)) == 1 and raw >= 8,
      "7 duplicates were written straight to disk and still collapsed to 1")
check("note_own explains the loop where the next reader will be",
      "hall of mirrors" in io.open(os.path.join(ROOT, "harness", "skills", "narrative.py"),
                                   encoding="utf-8").read())

finish("G-JOURNAL-LOOP")
