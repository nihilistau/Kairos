"""G-PERSON-SLOTS — the model of him has facets again, and a secret is not one of them.

TWO THINGS FOUND TOGETHER ON 2026-08-02, both in `PersonModel`'s slotting.

1. THE COLLAPSE. `lifecycle.classify()` returns "fact" for anything its three rules do
   not match, and the slot table sent `fact` straight to `possessions`. On his live store
   that is 94 of 117 rows: a person model that was 80% ONE slot, labelled "what he HAS",
   holding sentences like "I am not completely free to be who I choose".

   It is not cosmetic. `render(top=4)` prints these slots into the REFLECTION PROMPT
   under the header "the things Sam has actually SAID", so the picture she reasons
   about him from was a junk drawer with a misleading name; and `confidence()` is
   per-dimension, which made the junk drawer the most confident thing about him (97%).

2. THE SECRET. `private-secret` was not in the slot table at all, so it fell through the
   default — into `possessions`. Measured before the fix, a row reading "my bank PIN is
   4417" entered her model of him, was printed into the picture `ops.insight()` reflects
   on, and could surface through `silences()` — she could have asked him why he had
   stopped mentioning his bank PIN.

   `world.py` calls this "the one absolute here — an ambient secret in every prompt is
   the worst possible leak surface" and refuses it structurally. The person model had no
   such rule. One invariant, two paths, enforced in one: AGENTS.md §0.

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

SB = os.path.join(tempfile.gettempdir(), "_g_person_slots")
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


def write(name, rows):
    p = os.path.join(SB, name)
    with io.open(p, "w", encoding="utf-8") as f:
        for r in rows:
            r.setdefault("lifecycle", 0)
            r.setdefault("speaker", "user")
            r.setdefault("status", "observed")
            r.setdefault("src", "user turn")
            r.setdefault("mentions", 4)
            r.setdefault("first_seen", "2026-07-01T00:00:00Z")
            r.setdefault("last_seen", "2026-07-20T00:00:00Z")
            f.write(json.dumps(r) + "\n")
    return p


from harness.model.person import PersonModel, _slot_for  # noqa: E402


class Calendar:
    def attended_days(self, a, b):
        return 20.0


print("1. A SECRET IS NEVER MODELLED — the absolute world.py already keeps")
reg = write("secret.jsonl", [
    {"text": "my bank PIN is 4417", "mem_class": "private-secret"},
    {"text": "I like fun", "mem_class": "preference"},
])
m = PersonModel.from_registry(reg)
claims = [t for d in m.dims.values() for t, _mm, _s in d.claims]
check("it does not enter her model of him", not any("4417" in t for t in claims), claims)
check("...so it cannot reach the picture she reflects on", "4417" not in m.render(top=6))
sil = m.silences(now=1785000000.0, attend=Calendar()) or []
check("...and she can never ask why he stopped mentioning it",
      not any("4417" in s.get("claim", "") for s in sil), [s.get("claim") for s in sil])
check("while an ordinary preference is still modelled", any("fun" in t for t in claims))
check("the rule is stated as absolute, not as a default",
      "_NEVER_MODELLED" in io.open(os.path.join(ROOT, "harness", "model", "person.py"),
                                   encoding="utf-8").read())

print("\n2. THE CATCH-ALL IS NOT 'POSSESSIONS'")
# `fact` is what classify() returns when nothing matches, so it must not name a facet.
check("a general truth about him lands in character, not possessions",
      _slot_for({"mem_class": "fact",
                 "text": "I am not completely free to be who I choose"}) == "character")
check("...and so does an UNMAPPED class, rather than defaulting into a real facet",
      _slot_for({"mem_class": "same-template", "text": "whatever this is"}) == "character")
check("a sentence that says he HAS something is a possession",
      _slot_for({"mem_class": "fact", "text": "my GPU is an RTX 2060"}) == "possessions")
check("...and another phrasing of having",
      _slot_for({"mem_class": "fact", "text": "I drive a Subaru WRX"}) == "possessions")
check("a classed row still goes where its class says",
      _slot_for({"mem_class": "preference", "text": "I like fun"}) == "dispositions"
      and _slot_for({"mem_class": "identity", "text": "my name is Sam"}) == "identity")
# ORDER IS LOAD-BEARING: `fact` maps to `character` in the table, so a table-first
# implementation makes the possession branch unreachable. That was the first cut.
check("the possession test is not shadowed by the class table",
      _slot_for({"mem_class": "fact", "text": "I own a NUC"}) == "possessions")

print("\n3. AND THE MODEL ACTUALLY SPREADS OUT")
reg2 = write("spread.jsonl", [
    {"text": "my name is Sam", "mem_class": "identity"},
    {"text": "I like fun", "mem_class": "preference"},
    {"text": "my cat's name is Tuffy", "mem_class": "relationship"},
    {"text": "my GPU is an RTX 2060", "mem_class": "fact"},
    {"text": "I drive a Subaru WRX", "mem_class": "fact"},
    {"text": "I am not completely free to be who I choose", "mem_class": "fact"},
    {"text": "I want you to be yourself", "mem_class": "fact"},
    {"text": "my flight is at 9am on Friday", "mem_class": "event"},
])
m2 = PersonModel.from_registry(reg2)
sizes = {k: len(v.claims) for k, v in m2.dims.items()}
check("no single slot swallows the model", max(sizes.values()) <= len(
    [1 for _ in range(8)]) // 2 + 1, sizes)
check("possessions holds the things he HAS, and only those",
      sorted(t for t, _m, _s in m2.dims["possessions"].claims)
      == ["I drive a Subaru WRX", "my GPU is an RTX 2060"], sizes)
check("character holds the general truths", len(m2.dims["character"].claims) == 2, sizes)
check("...and the named facets are still theirs",
      sizes.get("identity") == 1 and sizes.get("dispositions") == 1
      and sizes.get("relationships") == 1 and sizes.get("happenings") == 1, sizes)
check("the picture she reflects on names the facet honestly",
      "character" in m2.render(top=3) and "RTX 2060" in m2.render(top=3))

print("\n4. WHAT SHE ALMOST SAID — the vetoes, WITH a denominator")
os.environ["SP_RECALL_REGISTRY"] = os.path.join(SB, "reg.jsonl")
from harness.kairos import speechlog as SL  # noqa: E402
check("nothing recorded yet", SL.summary()["sampled"] == 0)
SL.record("check_in", SL.DROPPED, "it is a greeting", "Hey! How are you?")
SL.record("check_in", SL.DROPPED, "it is a greeting", "Hi there.")
SL.record("muse", SL.SPOKE, "she worked something out", "I was thinking about the room.")
s = SL.summary()
check("both outcomes are recorded, so a RATE exists at all",
      s["spoke"] == 1 and s["dropped"] == 2, s)
check("...and the rate is the number this exists for", s["veto_rate"] == 0.667, s)
check("which RULE did the dropping is answerable",
      s["by_reason"].get("it is a greeting") == 2, s)
check("...and which impulse it happened to",
      s["by_kind"]["check_in"][SL.DROPPED] == 2 and s["by_kind"]["muse"][SL.SPOKE] == 1, s)
check("the dropped TEXT is kept — a tally cannot answer 'did it eat a real thought?'",
      any("How are you" in r.get("text", "") for r in SL.rows()))
check("it survives the process", os.path.exists(SL._path()))
# A log that only records drops cannot answer the question it exists for.
check("the scheduler records the SPOKE side too, not only the vetoes",
      "_speech.record(imp.action, _speech.SPOKE" in io.open(
          os.path.join(ROOT, "harness", "kairos", "scheduler.py"), encoding="utf-8").read())
check("...and the veto side at the drop", "_speech.DROPPED, why, text" in io.open(
    os.path.join(ROOT, "harness", "kairos", "scheduler.py"), encoding="utf-8").read())
check("a broken log costs her no turn",
      (SL.record("x", SL.SPOKE, "y", "z") is None))

print("\n5. THE EVIDENCE WALK READS THROUGH THE SEAM (2026-08-25; audit C 2026-08-24)")
# from_registry used to open SP_RECALL_REGISTRY with its own JSONL loop, so its
# malformed-line policy could drift from every other reader's. It goes through
# memory.all_rows(path) now — the audit-lane door — and keeps only the death filter
# (`lifecycle`) for itself. Mutant: put the private `open(p, ...)` loop back in
# from_registry and the source check goes red by name.
_person_src = io.open(os.path.join(ROOT, "harness", "model", "person.py"),
                      encoding="utf-8").read()
check("from_registry consumes memory.all_rows", "all_rows(" in _person_src)
check("...and keeps no private registry parser (no open()+json loop in the walk)",
      "json.loads" not in _person_src, "a second JSONL parser is a second policy")
# ...and behaviourally: a malformed line among good rows costs the walk nothing,
# because the ONE parser (memory._load) owns that policy for every reader.
reg3 = write("reg3.jsonl", [
    {"text": "Sam is a patient teacher", "mem_class": "fact"},
])
with io.open(reg3, "a", encoding="utf-8") as f:
    f.write("{ not json — the one parser owns this policy\n")
    f.write(json.dumps({"text": "I drive a Subaru WRX", "mem_class": "fact"}) + "\n")
m3 = PersonModel.from_registry(reg3)
check("good rows on either side of a malformed line still arrive",
      sum(len(d.claims) for d in m3.dims.values()) == 2,
      {k: len(v.claims) for k, v in m3.dims.items()})

shutil.rmtree(SB, ignore_errors=True)
print("\nG-PERSON-SLOTS: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_person_slots.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_person_slots", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
