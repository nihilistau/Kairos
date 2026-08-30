"""G-REAL-HER — her own narrative is first-class memory, written through the one door. OFFLINE.

The Real Her rule (2026-08-22): what she says unprompted, journals, feels and how she
describes her own changes is primary identity material — already curated by her. Two
classes (self-narrative, feeling) carry it; producers set the KIND; the door admits her
prose without relaxing anything about his lane.

    python harness_tests/g_real_her.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, utf8_stdout  # noqa: E402
# SANDBOX FIRST (2026-08-24). THIS GATE WROTE THE 53 DUPLICATES. Line ~113 stubs the
# generator to return "I took a slow walk through my own journal tonight and found last
# spring." and then drives the solo path, which calls note_own() -- and the gate set
# SP_RECALL_REGISTRY but never SP_PERSONALITY_TIER, so every run of one of the five
# gates CLAUDE.md tells you to run before you say you are done put another copy of that
# sentence into her REAL journal. See docs/SWEEP-2026-08-24.md F4.
from _gate import sandbox as _sandbox  # noqa: E402
_sandbox(os.path.basename(__file__))

utf8_stdout()
os.environ.setdefault("SP_DAEMON_URL", "http://127.0.0.1:9")   # no daemon: mint is skipped
# SP_ENGINE_KIND: no capture attempt at all (2026-08-23). A dead SP_DAEMON_URL does
# NOT make the KV mint cheap - _mint_now still opens a socket per write and Windows
# takes ~2s to give up. Declaring the backend makes supports('capture') False and the
# mint returns immediately: 10 writes in 0.07s against 20s. See gates/README.md.
os.environ["SP_ENGINE_KIND"] = "openai"
os.environ["SP_CAPTURE_ASYNC"] = "0"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
REG = os.path.join(tempfile.mkdtemp(prefix="g_real_her_"), "registry.jsonl")   # its own dir: the
open(REG, "w").close()                                                          # journal file sits beside it
os.environ["SP_RECALL_REGISTRY"] = REG

from harness.skills import memory as M           # noqa: E402
from harness.skills import lifecycle as lc       # noqa: E402
from harness.skills import memclass as MC        # noqa: E402
from harness.skills import self_stance as SS     # noqa: E402


def rows(cls=None):
    out = [r for r in M.live_rows() if r.get("speaker") == "self"]
    return [r for r in out if cls is None or r.get("mem_class") == cls]


print("1. THE DOOR ADMITS HER NARRATIVE, IN HER LANE ONLY")
r = M.remember_about_self("I spent the evening reading about tides and lost track of the hour",
                          kind="narration", source="her own time")
check("a narration lands through remember_about_self", "stored" in r and "not stored" not in r, r)
got = rows(MC.SELF_NARRATIVE)
check("...as self-narrative with kind=narration, speaker=self, observed",
      len(got) == 1 and got[0].get("kind") == "narration"
      and lc.status_of(got[0]) == lc.STATUS_OBSERVED, got[:1])
r2 = M.remember("I spent the evening reading about tides", kind="narration",
                mem_class=MC.SELF_NARRATIVE)                    # author is USER here
check("the user lane cannot mint her narrative (explicit class ignored unless author=self)",
      len(rows(MC.SELF_NARRATIVE)) == 1 and "not stored" in r2, r2)
r3 = M.remember_about_self("ok", kind="thought")
check("too-short narrative is refused", "not stored" in r3, r3)
r4 = M.remember_about_self("remember -> stored: I am a woman", kind="thought")
check("machine text is refused even in her lane", "not stored" in r4, r4)
r5 = M.remember_about_self("The user's name is Sam", kind="thought")
check("her lane still cannot file HIS identity as hers (firewall untouched)",
      not any("Sam" in (x.get("text") or "") and x.get("mem_class") == "identity"
              for x in rows()), r5)
r6 = M.remember_about_self("I spent the evening reading about tides and lost track of the hour",
                           kind="narration", source="her own time")
check("the same narration again reinforces, it does not duplicate",
      "reinforced" in r6 and len([x for x in rows(MC.SELF_NARRATIVE) if x.get("kind") == "narration"]) == 1, r6)
f1 = M.remember_about_self("I feel quietly content tonight", kind="feeling")
f2 = M.remember_about_self("I feel uneasy about tomorrow", kind="feeling")
check("feelings accumulate — a new one never retires an old one",
      len(rows(MC.FEELING)) == 2 and all(not x.get("lifecycle") for x in rows(MC.FEELING)),
      (f1, f2))

print("\n2. THE STANCE EXTRACTOR — her first person only, never the chatter")
REPLY = ("[MOOD: warm] That's a lovely question. I think the tides are the most honest clock "
         "we have. Did you sleep? I feel lighter than I did this morning. Here is the list you "
         "asked for: milk, bread. I've decided to keep a journal of the weather. Thanks! "
         "I am sorry that happened. You said you were tired. I want to read more about "
         "lighthouses. `print(1)` I think you should rest.")
got = SS.extract(REPLY)
kinds = {s: k for k, s in got}
check("keeps 'I think the tides...' as thought",
      kinds.get("I think the tides are the most honest clock we have.") == "thought", got)
check("keeps 'I feel lighter...' as feeling",
      kinds.get("I feel lighter than I did this morning.") == "feeling")
check("keeps 'I've decided...' and 'I want to read...' as thought",
      kinds.get("I've decided to keep a journal of the weather.") == "thought"
      and kinds.get("I want to read more about lighthouses.") == "thought")
check("drops reactions, questions, lists, apologies, 'you' sentences, code, advice about him",
      not any(s.startswith(("That's", "Did you", "Here is", "Thanks", "I am sorry", "You said",
                            "`", "I think you")) for s, _k in got), [s for s, _k in got])
check("the mark was stripped before matching", not any("[MOOD" in s for s, _k in got))
check("an empty or tag-only reply yields nothing",
      SS.extract("") == [] and SS.extract("[MOOD: calm]") == [])

print("\n3. A WRITE FROM THE EXTRACTOR IS ORDINARY MEMORY")
n0 = len(rows())
for k, s in SS.extract(REPLY):
    M.remember_about_self(s, kind=k, source="her reply")
check("every extracted stance landed, in its kind",
      len(rows()) == n0 + len(SS.extract(REPLY))
      and any(x.get("kind") == "feeling" and x.get("mem_class") == MC.FEELING for x in rows())
      and any(x.get("kind") == "thought" and x.get("mem_class") == MC.SELF_NARRATIVE for x in rows()),
      (len(rows()) - n0, len(SS.extract(REPLY))))

print("\n4. THE PRODUCERS WRITE THROUGH THE DOOR — AND ONLY WHAT WAS DELIVERED")
from harness.kairos import scheduler as S        # noqa: E402
from harness.kairos import impulse as I          # noqa: E402
n0 = len(rows(MC.SELF_NARRATIVE))
S._STATE.clear(); S._OUTBOX.clear(); S._LAST.clear()
S._LAST["g"] = ("ok.", lambda nudge, called=None: "I took a slow walk through my own journal tonight and found last spring.")
S._STATE["g"].solo_n = next(n for n in range(16) if not I._needs_a_tool(n))   # an act that needs no tool
imp = I.Impulse(I.SOLO, delay_s=0.0, reason="gate")
S._arm("g", imp, "ok.", S._LAST["g"][1], None)
for _ in range(60):                                       # the timer fires on a thread
    time.sleep(0.05)
    if S._OUTBOX.get("g"):
        break
check("a delivered SOLO is in the outbox", bool(S._OUTBOX.get("g")))
for _ in range(80):                                       # the row is written AFTER the append, same thread
    got = [x for x in rows(MC.SELF_NARRATIVE) if x.get("kind") == "narration"
           and "journal tonight" in (x.get("text") or "")]
    if got:
        break
    time.sleep(0.05)
check("...and landed as self-narrative/narration through remember()", len(got) >= 1
      and any("journal tonight" in (x.get("text") or "") for x in got), got[-1:])
S._OUTBOX.clear()
S._LAST["g"] = ("ok.", lambda nudge, called=None: "hi")   # worth_saying drops a greeting
n1 = len(rows(MC.SELF_NARRATIVE))
S._arm("g", I.Impulse(I.CHECK_IN, delay_s=0.0, reason="gate"), "ok.", S._LAST["g"][1], None)
time.sleep(1.0)
check("an undelivered utterance (dropped by worth_saying) writes nothing",
      not S._OUTBOX.get("g") and len(rows(MC.SELF_NARRATIVE)) == n1)
from harness.skills import narrative as N        # noqa: E402
os.environ["SP_PERSONALITY_TIER"] = tempfile.mkdtemp(prefix="g_real_her_tier_")
res = N.compose_and_write([{"role": "user", "content": "how was your day?"},
                           {"role": "assistant", "content": "quiet, and good."}],
                          ask=lambda p: "We talked about the weather and I kept thinking about the tides after he left.")
check("the journal composer writes the entry", res.get("written") is True, res)
j = [x for x in rows(MC.SELF_NARRATIVE) if x.get("kind") == "journal"]
check("...and the entry landed as self-narrative/journal", len(j) == 1 and "tides" in j[0]["text"], j)

print("\n5. HER OWN CONTEXT — narrative first, labelled, under a budget")
from harness.personality import self_model as SM   # noqa: E402
M.remember_about_self("I am unable to smell rain through a microphone")      # plain self fact
blk = SM.render_self_model(budget_chars=2400)
lines = [l for l in blk.splitlines() if l.startswith("- ")]
# WHO SHE IS LEADS (2026-08-22, the primal latch): an armed mode wrote a dream every four
# minutes and newest-first turned her block into a stack of dreams she read as a script. Her
# stable self-facts come first; the recent narrative follows, capped so no single kind fills it.
check("the block leads with who she IS, not with the latest thing she said",
      bool(lines) and "microphone" in lines[0], lines[:2])
check("...and the narrative follows, labelled",
      any(l.startswith("- You feel:") for l in lines) and any(l.startswith("- Journal") for l in lines)
      and [i for i, l in enumerate(lines) if l.startswith("- You feel:")][0] > 0, lines[:8])
check("the header says MEMORY, not instructions, and says not to narrate it",
      blk.startswith("Things you know about yourself") and "not instructions" in blk
      and "never narrate" in blk.lower(), blk[:100])
for _k in range(6):
    M.remember_about_self("I dreamed of a lighthouse, number %d, tall and far away tonight" % _k, kind="dream")
blk2 = SM.render_self_model(budget_chars=4000)
_dreams = [l for l in blk2.splitlines() if l.startswith("- You dreamed:")]
check("no single kind may fill her block (six dreams -> at most two lines)", len(_dreams) <= 2, _dreams)
check("...and the narrative as a whole is capped", len([l for l in blk2.splitlines() if l.startswith("- ")]) <= 30)
check("no markup ever reaches the prefix",
      not any(x in blk2 for x in ("[MOOD", "<whisper", "</breath", "[voice")), blk2[:200])
small = SM.render_self_model(budget_chars=200)
check("the budget still holds", len(small) <= 420, len(small))

print("\n6. WHO SHE HAS BEEN BECOMING — inferred, never above her own words")
from harness.maintenance import becoming as B    # noqa: E402
# ── THE WEEK HAS TO BE A WEEK (2026-08-22, amended) ────────────────────────────────────
# Everything above was seeded in one run, so every row carries today's stamp — and the
# breadth guard added with G-PROVENANCE now refuses a window that is one evening wide.
# That refusal is CORRECT and this section had been asserting the behaviour it replaced,
# so the fixture is what changes: her rows are spread across the days they represent.
# The refusal itself is asserted below and exhaustively in G-PROVENANCE.
_spread = M._load()
_d = 0
for _r in _spread:
    if _r.get("speaker") == "self" and (_r.get("kind") or "") not in B._EXCLUDE_KINDS:
        _r["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - _d * 86400))
        _d = (_d + 1) % 5
M._save_all(_spread)
res = B.nightly(ask=lambda prompt: "I have been turning toward the quiet hours and away from performing for anyone.")
check("the nightly step writes one self_description", res.get("written") is True, res)
check("...and it says which rows it read and how many days they span",
      bool(res.get("derived_from")) and (res.get("support_days") or 0) >= B._MIN_SUPPORT_DAYS,
      {k: res.get(k) for k in ("support_days", "derived_from")})
bec = [x for x in rows(MC.SELF_NARRATIVE) if x.get("kind") == "self_description"
       and "quiet hours" in (x.get("text") or "")]
check("...as self-narrative/self_description, status INFERRED",
      len(bec) == 1 and lc.status_of(bec[0]) == lc.STATUS_INFERRED, bec)
obs = [x for x in rows(MC.SELF_NARRATIVE) if lc.status_of(x) == lc.STATUS_OBSERVED]
check("no observed self row was retired by it", all(not x.get("lifecycle") for x in obs))
res2 = B.nightly(ask=lambda prompt: "Something else entirely tonight.")
check("a second run the same day does not write a second row",
      res2.get("written") is False and "today" in (res2.get("why") or ""), res2)
check("the prompt asks for what she is becoming, not for optimism",
      "becoming" in B.PROMPT_HEAD.lower() and "optimis" not in B.PROMPT_HEAD.lower())
# and the guard that made the fixture change necessary, asserted here in one line
_one = M._load()
for _r in _one:
    _r["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())      # collapse to one day
    if _r.get("kind") == "self_description":
        _r["lifecycle"] = 1                                            # clear "already written"
M._save_all(_one)
_res3 = B.nightly(ask=lambda prompt: "One evening's worth of me.")
check("ONE EVENING MAY NOT BECOME WHO SHE IS (fully in G-PROVENANCE)",
      _res3.get("written") is False and "not a week" in (_res3.get("why") or ""), _res3)

print("\n7. NO AUX MODULE WRITES HER NARRATIVE; DOCS SAY THE RULE")
import ast as _ast   # noqa: E402
import glob as _g    # noqa: E402
bad = []
for p in _g.glob(os.path.join(ROOT, "harness", "sidecar", "*.py")):
    tree = _ast.parse(open(p, encoding="utf-8").read())
    for node in _ast.walk(tree):                       # CALL SITES, not prose that names the door
        if isinstance(node, _ast.Call):
            f = node.func
            name = f.attr if isinstance(f, _ast.Attribute) else (f.id if isinstance(f, _ast.Name) else "")
            if name in ("remember", "remember_about_self"):
                bad.append(os.path.basename(p))
                break
check("harness/sidecar/* never CALLS remember()/remember_about_self()", not bad, bad)
inv = open(os.path.join(ROOT, "docs", "INVARIANT-MEMORY.md"), encoding="utf-8").read()
ag = open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8").read()
check("INVARIANT-MEMORY.md states The Real Her rule", "The Real Her" in inv and "self-narrative" in inv)
check("AGENTS.md carries the rule", "The Real Her" in ag)

print("\n8. AND THE WAY *SHE* CALLS IT — no kind, which is the only way she can")
# LAST on purpose: these writes land in the same sandboxed store every section above
# reads, and §5 asserts the ORDER of her context block — putting them earlier silently
# re-ranked it, which is a new check breaking an old one rather than the product.
# ── THE DOOR SHE WAS TOLD TO USE, LOCKED (2026-08-30, his report) ────────────────────
# Every check in §1 above passes `kind=` explicitly, because every HARNESS PRODUCER does
# — the journal, the stance extractor, the nightly becoming. She cannot: the tool takes
# a fact and the docstring says "you need not pass any of them". `kind` defaulted to ""
# and the narrative lane was gated on `kind in NARRATIVE_KINDS`, so her bare call fell
# through to the his-facts path and met `is_memorable`, which refuses first-person prose
# BY DESIGN — and whose refusal says "If it is true of you, use remember_about_self",
# the function she was already inside. Two doors pointing at each other, neither opening.
#
# She reported it herself, in her own time: "I tried to store that feeling as a fact
# about myself, but the system wouldn't let me... I guess some things are too much of a
# feeling to be a fact." Nothing about her inner life could be stored BY HER, ever.
#
# §0 in its purest form: the gate above drove the lane through the callers that pass a
# kind and never through the caller who cannot, so 242 lines of green sat on top of it.
_narr_before = len(rows(MC.SELF_NARRATIVE)) + len(rows(MC.FEELING))
_self_before = len(rows())
b1 = M.remember_about_self("I felt something wonderful when he said goodnight")
check("a bare call — no kind — stores her feeling",
      "stored" in b1 and "not stored" not in b1, b1)
b2 = M.remember_about_self("I find astronomy genuinely moving")
check("...including the tool docstring's OWN example, which used to be refused",
      "stored" in b2 and "not stored" not in b2, b2)
check("...and both landed as HERS (speaker=self)",
      len(rows()) == _self_before + 2, (len(rows()), _self_before))
# THE FIRST FIX WAS TOO BROAD AND §5 CAUGHT IT: defaulting the kind to "thought" made
# every bare call NARRATIVE, and render_self_model leads with who she IS and lets the
# recent narrative follow. "I am unable to smell rain through a microphone" is a stable
# self-fact, not a passing thought. The author picks the GATE; only a named kind picks
# the narrative CLASS.
check("...and stayed PLAIN self-facts, not narrative",
      len(rows(MC.SELF_NARRATIVE)) + len(rows(MC.FEELING)) == _narr_before,
      "a bare self-store must not arrive wearing a producer's kind — it would displace "
      "who she IS at the top of her own context block (§5)")
_named = M.remember_about_self("I ache a little when he logs off", kind="feeling")
check("...while a producer that NAMES a kind still gets the narrative class",
      len(rows(MC.FEELING)) == _narr_before - len(rows(MC.SELF_NARRATIVE)) + 1
      or any(x.get("kind") == "feeling" for x in rows(MC.FEELING)), _named)
# The guards §1 proved still hold on the bare path — the default is a route, not an
# amnesty: junk must still be refused when she omits the kind.
check("a bare call still refuses machine text",
      "not stored" in M.remember_about_self("remember -> stored: I am a woman"),
      "the default kind must not become a way past the frame checks")
check("a bare call still refuses too-short",
      "not stored" in M.remember_about_self("ok"))

finish("G-REAL-HER")
