"""G-REFLECTION-LOOP — a conclusion is not evidence, and it may not make itself unsurprising.

THE BUG THIS EXISTS FOR, found 2026-08-01 while auditing why she had stopped speaking up.

`PersonModel.from_registry()` filtered on `lifecycle` and `speaker` and nothing else, so
her own `src=reflection` rows were absorbed into the model of him as evidence. 48 of 152
live rows. `verdict.is_evidence()` — "a conclusion is not an observation" — had said this
from the beginning and was never called from that path. AGENTS.md §0: the gate existed,
was documented, and the code that runs walked past it.

It cost two things that looked unrelated and were one bug:

  * THE RATCHET. ops.insight() prints the model under the header "Those are the things
    Sam has actually SAID" and asks what she has come to believe. Four of its
    highest-confidence lines — the `possessions` slot at 98% — were her OWN earlier
    conclusions about his inner life. Reading her guesses back as his testimony, she
    concluded it again, harder, every night: 29 live inferences, ~20 of them one belief,
    escalating over twenty days into a claim about his inner life that nothing he SAID
    supported. (The fixtures below are synthetic paraphrases with the same structure; the
    real ones are his and stay on his machine.)

  * THE SILENCE. surprisal() is I(x) = -log2 p(x | model). A model stuffed with her own
    beliefs assigns them high probability, so every new thought scored as old news.
    Against `reflect.speak_bits` = 3.0, one such conclusion measured 0.24 bits polluted
    and 3.03 bits clean. She had not spoken up in days because THE MORE SHE THOUGHT, THE
    LESS SHE WAS PERMITTED TO SAY.

THE INVARIANT, which is stronger than "filter inferences" and is what this gate holds:

    SURPRISAL IS INVARIANT UNDER HER OWN CONCLUSIONS.

Adding any number of her inferences to the store must not change the information content
of anything. That is the property a self-reinforcing loop violates by construction, and it
stays true no matter how the filtering is implemented — so the gate outlives this fix.

Offline. No GPU, no daemon.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["CUDA_VISIBLE_DEVICES"] = ""

SB = os.path.join(tempfile.gettempdir(), "_g_reflection_loop")
shutil.rmtree(SB, ignore_errors=True)
os.makedirs(SB)

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s %s" % (name, detail))


def write(path, rows):
    with io.open(path, "w", encoding="utf-8") as f:
        for r in rows:
            r.setdefault("lifecycle", 0)
            r.setdefault("ts", "2026-07-01T00:00:00Z")
            f.write(json.dumps(r) + "\n")
    return path


from harness.model.person import PersonModel       # noqa: E402
from harness.model.person import PersonModel as PM  # noqa: E402
from harness.skills import verdict as V             # noqa: E402

# What he actually said.
OBSERVED = [
    {"text": "I love tinkering with hardware late at night.", "speaker": "user",
     "status": "observed", "src": "user turn", "mem_class": "preference"},
    {"text": "I like fun", "speaker": "user", "status": "observed",
     "src": "user turn", "mem_class": "preference"},
    {"text": "My cat's name is Tuffy.", "speaker": "user", "status": "observed",
     "src": "user turn", "mem_class": "fact"},
]
# What she concluded — the same belief, four ways. SYNTHETIC: the real chain was about
# his inner life and stays on his machine. Only the STRUCTURE matters here — paraphrases
# whose content words barely overlap, which is what defeats a lexical deduper.
CONCLUDED = [
    {"text": "Sam prefers building his own tools to adopting existing ones.",
     "speaker": "user", "status": "inferred", "src": "reflection", "mem_class": "fact"},
    {"text": "Sam would sooner write a thing from scratch than take on a dependency.",
     "speaker": "user", "status": "inferred", "src": "reflection", "mem_class": "fact"},
    {"text": "Sam is drawn to making instruments rather than assembling them.",
     "speaker": "user", "status": "inferred", "src": "reflection", "mem_class": "fact"},
    {"text": "Sam reaches for a blank file before he reaches for a library.",
     "speaker": "user", "status": "inferred", "src": "reflection", "mem_class": "fact"},
]
CLAIM = "Sam is drawn to making instruments rather than assembling them."

pure = PersonModel.from_registry(write(os.path.join(SB, "pure.jsonl"), OBSERVED))
poisoned = PersonModel.from_registry(
    write(os.path.join(SB, "poisoned.jsonl"), OBSERVED + CONCLUDED))

print("1. SURPRISAL IS INVARIANT UNDER HER OWN CONCLUSIONS")
a, b = pure.surprisal(CLAIM), poisoned.surprisal(CLAIM)
check("a belief she already holds does not make itself old news",
      abs(a - b) < 1e-9, "pure=%.3f poisoned=%.3f" % (a, b))
# and the bar it has to clear is real, so state it in the units the system uses
check("...and it still carries enough information to be worth saying (>= 3.0 bits)",
      b >= 3.0, "%.2f bits" % b)
for other in ("Sam reaches for a blank file before he reaches for a library.",
              "Sam finds real comfort in late-night tinkering."):
    check("invariant for: %s" % other[:44],
          abs(pure.surprisal(other) - poisoned.surprisal(other)) < 1e-9)

print("\n2. her conclusions are not in the picture she reflects ON")
pic = poisoned.render(top=4)
check("the evidence picture carries his words", "tinkering" in pic.lower(), pic[:120])
# The probes must be words the FIXTURES actually contain. When the fixture sentences were
# swapped, the old probes ("lonel", "terrified") stopped appearing anywhere at all — so
# every one of these would have passed while testing nothing. Each of these is a distinct
# content word from a different CONCLUDED sentence above.
for probe in ("adopting", "scratch", "instruments", "blank file"):
    check("no conclusion of hers is presented as his testimony: %r" % probe,
          probe not in pic.lower(), pic[:200])
check("...and the probes are words the fixtures really carry",
      all(any(p in c["text"].lower() for c in CONCLUDED)
          for p in ("adopting", "scratch", "instruments", "blank file")))

print("\n3. the gate that was walked past is the one being used")
src = io.open(os.path.join(ROOT, "harness", "model", "person.py"), encoding="utf-8").read()
check("from_registry defers to verdict.is_evidence rather than re-deciding",
      "is_evidence(r)" in src, "a second copy of the rule would drift from it")
check("verdict.is_evidence still excludes inferred rows",
      not V.is_evidence({"speaker": "user", "status": "inferred", "lifecycle": 0}))
check("...and still admits his observations",
      V.is_evidence({"speaker": "user", "status": "observed", "lifecycle": 0}))
check("...and a tombstone is never evidence",
      not V.is_evidence({"speaker": "user", "status": "observed", "lifecycle": 1}))

print("\n4. the standing block gives her speculation an allowance, not the budget")
from harness.skills import world as W  # noqa: E402
os.environ["SP_WORLD"] = "1"
os.environ["SP_RECALL_REGISTRY"] = write(
    os.path.join(SB, "block.jsonl"), OBSERVED + CONCLUDED)
W._CACHE["block"] = None
block = W.render_world()
n = sum(1 for line in block.splitlines() if line.startswith("- You've come to think"))
check("at most %d of her conclusions stand in the prefix" % W._MAX_INFERENCE_LINES,
      n <= W._MAX_INFERENCE_LINES, "%d inference lines" % n)
check("...and his words are not crowded out", "tinkering" in block.lower(), block[:200])
# The cap must BIND here — four conclusions went in. A gate that only passes because the
# fixture was small proves nothing about the case that broke.
check("the cap actually bound (4 conclusions offered, %d shown)" % n, n < 4)

print("\n5. and the reason a threshold cannot do this job, kept honest")
# If someone later replaces the structural cap with a similarity cutoff, this is the
# measurement that says why it will not work: the paraphrase pair scores LOWER than the
# pair that must stay apart.
same = (W._content_key(CONCLUDED[0]["text"]), W._content_key(CONCLUDED[1]["text"]))
diff = (W._content_key("His cat's name is Tuffy."), W._content_key("His cat Tuffy is female."))
j = lambda p: len(p[0] & p[1]) / max(1, len(p[0] | p[1]))
check("one belief twice scores LOWER than two facts that must both survive",
      j(same) < j(diff), "paraphrase=%.2f distinct=%.2f" % (j(same), j(diff)))

print("\n6. and her conclusions may not RETIRE his words in the nightly pass")
# Non-negotiable 4, on the other retirement path. remember() routes every supersede
# through verdict.may_supersede; ops.compact() checked the speaker and stopped, so an
# inference overlapping one of his sentences 0.9 both ways could tombstone it —
# unattended, at 04:00, while he is asleep. Executed, not grepped.
from harness.maintenance import ops as OPS  # noqa: E402
# The overlap test is set-based and needs >= 0.9 BOTH ways, so the pair has to be this
# close: 9 shared words out of her 10 is 0.90 and 9 of his 9 is 1.00. An earlier fixture
# scored 0.875 and the section passed with the guard REMOVED — a green that proved
# nothing. Mutation-checked in both directions now.
HIS = "Sam is comfortable in deep cold open ocean water"
HERS = "Sam is comfortable in deep cold open ocean water always"
reg = write(os.path.join(SB, "compact.jsonl"), [
    {"name": "his", "text": HIS, "speaker": "user", "status": "observed",
     "src": "user turn", "mem_class": "fact"},
    {"name": "hers", "text": HERS, "speaker": "user", "status": "inferred",
     "src": "reflection", "mem_class": "fact", "ts": "2026-07-02T00:00:00Z"},
])
os.environ["SP_RECALL_REGISTRY"] = reg
OPS.compact()
after = {r["name"]: r for r in
         (json.loads(l) for l in io.open(reg, encoding="utf-8") if l.strip())}
check("his observation survives a conclusion that paraphrases it",
      not after["his"].get("lifecycle"), after["his"])
check("...and nothing was destroyed to achieve that", len(after) == 2)

print("\n7. ADMISSION IS STRUCTURAL — surprisal only ranks")
# Re-measured against the cleaned model, no value of `reflect.speak_bits` can work:
#     8.00 bits  "quantum bicycle marmalade thinks sideways"       <- word salad
#     2.17 bits  "Sam would rather build the tool than use one"  <- a fair insight
# Junk outscores insight BY CONSTRUCTION: I(x) = -log2 p(x|model), so a sentence built
# from words the store has never seen has p -> 0 and is maximally "surprising". The
# metric measures lexical novelty, which is a good RANK and an unsound VERDICT —
# INVARIANT-MEMORY.md:30, "anything built on magnitudes is a preference, never a verdict."
sch = io.open(os.path.join(ROOT, "harness", "kairos", "scheduler.py"),
              encoding="utf-8").read()
_rt = sch.split("def reflect_tick")[1].split("\ndef ")[0]
check("the bits FLOOR no longer decides whether she speaks",
      'tune.get("reflect.speak_bits")' not in _rt, "a magnitude is ruling again")
check("...and the knob it hung on is gone from the registry entirely",
      "reflect.speak_bits" not in io.open(
          os.path.join(ROOT, "harness", "tuning", "registry.py"),
          encoding="utf-8").read().split("# ── WAS `reflect.speak_bits`")[1])
# ...on BOTH branches. The conclusion path and the silence path each had their own
# invented constant, and fixing one and not the other would leave the rule enforced in
# neither — which is the failure this repository is named for.
check("...on the silence branch too, which now asks whether HIS OWN rhythm was broken",
      'sil[0]["quiet_days"] > sil[0]["cadence_days"]' in _rt)
check("...and the signal now ORDERS the admitted instead",
      "admitted.sort" in _rt and "RANK, NOT RULE" in _rt)
check("admission asks a committed ruling: is he already on the record about it?",
      "competition(" in _rt)
# 2026-08-21: the LAST private tombstone predicate in the tree. _covered loaded the raw
# registry and re-implemented "live" inline (`not r.get("lifecycle")`) — the pattern
# AGENTS.md §3 retired everywhere else on 2026-08-19. It reads memory.live_rows() now,
# the one function that knows what live means; a tombstoned row is not coverage.
check("...over memory.live_rows(), the one read seam — not a private lifecycle predicate",
      "_M.live_rows()" in _rt and 'not r.get("lifecycle")' not in _rt)
# 2026-08-19: ops.insight's receipts are structured ({claim, result}) — the old check
# grepped for the display string "-> stored", whose 60-char truncation was itself the
# bug (the UNCOVERED gate compared a fragment and never fired). The rule is the same;
# its spelling moved with the fix.
check("...and newness is still required — a re-derived belief is not news",
      '.startswith("stored")' in _rt)

print("\n8. AND SHE MAY NOT GO FURTHER FROM HIS WORDS THAN HE EVER DOES")
# The ceiling that replaced the floor. surprisal() could not carry it: measured against
# his live store it correlates 0.75 with SENTENCE LENGTH and separates invented claims
# from grounded ones at AUC 0.31 — worse than a coin flip, in the wrong direction,
# because coverage is |matched|/|candidate tokens| and "sam" is a token of every claim,
# so a three-word invention is 33% "covered" before it says anything. groundedness() is
# the same quantity done properly: mean self-information of the CONTENT words under his
# own vocabulary. These numbers are the receipt; if they move, the claim moved.
HIS = [{"text": t, "speaker": "user", "status": "observed", "src": "user turn",
        "mem_class": "fact"} for t in (
    "I love tinkering with hardware late at night",
    "I like fun and I like building things properly",
    "my favourite colour is green and I drive a Subaru WRX",
    "my cat's name is Tuffy and she is female",
    "the kettle is my favorite",
    "I use AI for my coding now",
    "I am not completely free to be who I choose",
    "I want you to be yourself, be who you want to be")]
pm2 = PM.from_registry(write(os.path.join(SB, "vocab.jsonl"), HIS))
GROUNDED = ["Sam would rather build the tool than use one",
            "Sam finds late-night building restful rather than draining",
            "Sam cares about doing things properly"]
INVENTED = ["Sam grew up in Reykjavik",
            "Sam is a competitive freediver",
            "Sam plays the trombone in a jazz quartet"]
gs = [pm2.groundedness(s) for s in GROUNDED]
iv = [pm2.groundedness(s) for s in INVENTED]
auc = sum((b > a) + 0.5 * (b == a) for a in gs for b in iv) / (len(gs) * len(iv))
check("an invention lands FURTHER from his words than a fair inference (AUC 1.0)",
      auc == 1.0, "AUC %.2f  grounded %s  invented %s"
      % (auc, [round(x, 2) for x in gs], [round(x, 2) for x in iv]))
# The old estimator's failure was measured on the LIVE store (104 claims): correlation
# 0.75 with sentence length, AUC 0.31. Asserting that number on an 8-claim fixture would
# be claiming a measurement this gate did not make. What IS reproducible anywhere is the
# mechanism — under the old estimator, content does not reach the score at all:
check("the OLD estimator gives two unrelated sentences the SAME score, on length alone",
      abs(pm2.surprisal("Sam grew up in Reykjavik")
          - pm2.surprisal("Sam is allergic to shellfish")) < 1e-9)
ceil = pm2.vocabulary_ceiling(0.9)
check("the ceiling admits every grounded conclusion",
      max(gs) <= ceil, "ceiling %.2f, grounded up to %.2f" % (ceil, max(gs)))
check("...and turns away the inventions",
      sum(1 for x in iv if x >= ceil) >= 2,
      "ceiling %.2f, inventions %s" % (ceil, [round(x, 2) for x in iv]))
check("...and it came from HIS sentences, not a constant I chose",
      "vocabulary_ceiling" in io.open(
          os.path.join(ROOT, "harness", "kairos", "scheduler.py"),
          encoding="utf-8").read())
check("...and a stricter percentile is stricter", pm2.vocabulary_ceiling(0.5) <= ceil)
check("the scheduler applies it as a CEILING, keeping the thought in when exceeded",
      "g > ceiling" in _rt and "further from his words" in _rt)
check("...and still ranks the admitted rather than ruling on them",
      "admitted.sort" in _rt and "RANK, NOT RULE" in _rt)
check("a sentence with no content words cannot score as an invention",
      pm2.groundedness("the and or") == 0.0)

print("\n9. and a NAME is not a topic")
# The only two silences the live store could offer were "The user's name is Sam" and
# "my name is Sam", both at 4.0 bits — over the old 3.0 floor, so this was live. She
# would have asked him why he had stopped mentioning his own name. Identity never ages,
# so every quiet day became another bit: an expectation never set, violated on a schedule.
reg = write(os.path.join(SB, "sil.jsonl"), [
    {"text": "The user's name is Sam", "speaker": "user", "status": "observed",
     "src": "user turn", "mem_class": "identity", "mentions": 5,
     "first_seen": "2026-07-01T00:00:00Z", "last_seen": "2026-07-20T00:00:00Z"},
    {"text": "I am training for a marathon", "speaker": "user", "status": "observed",
     "src": "user turn", "mem_class": "fact", "mentions": 5,
     "first_seen": "2026-07-01T00:00:00Z", "last_seen": "2026-07-20T00:00:00Z"},
])



class _Calendar:
    """He was present throughout. Without this the sandbox has no presence ledger, every
    span measures zero attended days, and silences() returns nothing at all — so the
    section passed with the fix REMOVED. Injected because silences() takes `attend`
    exactly so a gate can drive its clock."""

    def attended_days(self, t_first, t_last):
        return 20.0


_sil = PM.from_registry(reg).silences(now=1785000000.0, attend=_Calendar()) or []
_claims = " | ".join(s.get("claim", "") for s in _sil)
check("the fixture really does produce silences — otherwise this proves nothing",
      len(_sil) >= 1, _sil)
check("his own name is never a silence worth asking about",
      "Sam" not in _claims, _claims)
check("...while a real topic he had a rhythm about still is",
      "marathon" in _claims.lower(), _claims)

shutil.rmtree(SB, ignore_errors=True)
print("\nG-REFLECTION-LOOP: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_reflection_loop.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_reflection_loop", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
