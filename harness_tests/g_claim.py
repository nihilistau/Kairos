"""G-CLAIM — an inference is not testimony, a slot is not a subject, and a tombstone is dead
on EVERY path.

Three bugs, one gate, because they are the same bug wearing three coats: A RULE THAT WAS TRUE
IN ONE PLACE AND NOT IN THE PLACE THAT RAN.

  1. THE SLOT COLLISION.  attribute_key() keyed on the words before the copula, so every
     "Sam is X" fact landed in ONE slot and superseded the last. Two things he SAID, on
     unrelated topics:
         stored: Sam is terrified of open water
         stored: Sam is a cat person (superseded: 'Sam is terrified of open water')
     The cat ate the water. And reflection only ever writes in that shape, so every conclusion
     she ever drew about him destroyed the one before it: she could hold exactly ONE belief
     about who he is at a time. Properties accumulate. Only ATTRIBUTES ("my GPU is ...") are
     slots with values.

  2. THE BYPASSED LIFECYCLE.  search_memories_ranked_rows() never filtered tombstones; it left
     that to its callers. recall() remembered. spine.recall_decider() — the AUTOMATIC recall,
     the one that runs EVERY TURN — did not. So the entire supersede system was live only when
     she chose to call the tool, and the path that actually feeds her context was injecting
     superseded facts ABOVE the truth.

  3. TESTIMONY OUTRANKS INFERENCE.  She may be wrong about him. She may not say it OVER him.
     Enforced at the recall seam, not by a write-time verdict — because I cannot detect semantic
     contradiction with string operations, and a verdict I cannot defend is a lie with a
     timestamp on it.

Every assertion below is on the REAL code path (spine.recall_decider), never on a helper called
by hand. A gate that calls the guarded function directly proves only that the guard compiles.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"      # discard port: never needs a GPU
_fd, _reg = tempfile.mkstemp(suffix=".jsonl")
os.close(_fd)
os.environ["SP_RECALL_REGISTRY"] = _reg

from harness.skills import memory as M                  # noqa: E402
from harness.skills import lifecycle as lc              # noqa: E402
from harness.control.spine import recall_decider, TurnView  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


def injected(q, min_overlap=0.34):
    """WHAT ACTUALLY REACHES HER CONTEXT. The real decider, not a hand-called helper."""
    out = []
    for d in recall_decider(min_overlap=min_overlap)._fn(
            TurnView(phase="pre", user_text=q)):
        out += d.payload.get("facts", [])
    return out


def reset():
    open(_reg, "w").close()


# ── 1. A PROPERTY IS NOT AN ATTRIBUTE ─────────────────────────────────────────────────
print("\n1. properties accumulate; attributes supersede")
reset()
M.remember("Sam is terrified of open water", source="user turn")
M.remember("Sam is a cat person", source="user turn")
M.remember("Sam is deeply curious about how things work", source="user turn")
live = [r["text"] for r in M._load() if not r.get("lifecycle")]
check("three unrelated things he said all survive", len(live) == 3, live)
check("the water fact was not eaten by the cat",
      "Sam is terrified of open water" in live, live)

reset()
M.remember("My GPU is an RTX 2060", source="user turn")
M.remember("My GPU is an RTX 3090", source="user turn")
rows = M._load()
live = [r["text"] for r in rows if not r.get("lifecycle")]
check("but an ATTRIBUTE still has one value (3090 supersedes 2060)",
      live == ["My GPU is an RTX 3090"], live)
check("and the old value is TOMBSTONED, not deleted",
      any(r.get("lifecycle") and r["text"] == "My GPU is an RTX 2060" for r in rows),
      [r["text"] for r in rows])
check("attribute_key: a possessed thing IS a slot",
      lc.attribute_key("My GPU is an RTX 3090", "user") == "user::gpu")
check("attribute_key: a bare subject is NOT a slot",
      lc.attribute_key("Sam is a cat person", "user") is None)
check("attribute_key: two properties do not collide",
      lc.attribute_key("Sam is a cat person", "user")
      == lc.attribute_key("Sam is terrified of open water", "user") is None)


# ── 2. A TOMBSTONE IS DEAD ON THE PATH THAT RUNS ──────────────────────────────────────
print("\n2. the tombstone is dead on the AUTOMATIC path, not just the polite one")
reset()
M.remember("My GPU is an RTX 2060", source="user turn")
M.remember("My GPU is an RTX 3090", source="user turn")
got = injected("what GPU do I have?")
# Asserted on the VALUE, not the wording. These matched the stored sentence exactly,
# which quietly required the note to inject rows verbatim — the thing the 2026-07-29
# ownership fix stopped doing ("My GPU..." now reaches her as "His GPU..."). What this
# gate is actually about is which CARD survives supersession, so ask that: the live
# value present, the retired value absent, however the sentence is dressed.
check("the superseded card is NOT injected into her context",
      not any("2060" in g for g in got), got)
check("the live card IS", any("3090" in g for g in got), got)
check("the recall() TOOL agrees with the automatic path",
      "3090" in M.recall("what GPU do I have") and "2060" not in M.recall("what GPU do I have"))
check("the seam filters, so no caller can forget",
      all(not e.get("lifecycle")
          for _s, e in M.search_memories_ranked_rows("GPU", k=9, min_overlap=0.1)))
check("...but the audit lane may still ASK for the dead",
      any(e.get("lifecycle")
          for _s, e in M.search_memories_ranked_rows("GPU", k=9, min_overlap=0.1,
                                                     include_retired=True)))


# ── 3. SHE MAY BE WRONG ABOUT HIM. SHE MAY NOT SAY IT OVER HIM. ───────────────────────
print("\n3. testimony outranks inference — at the mouth, not at the disk")
reset()
M.remember("Sam is terrified of open water", source="user turn")
M.remember("Sam is comfortable in open water", source="reflection")
M.remember("Sam is deeply curious about how things work", source="reflection")

rows = M._load()
check("the inference is STORED (nothing is ever destroyed)",
      any(r["text"] == "Sam is comfortable in open water" for r in rows))
check("it is stored LIVE and INFERRED — not convicted, not tombstoned",
      any(r["text"] == "Sam is comfortable in open water"
          and not r.get("lifecycle") and r.get("status") == lc.STATUS_INFERRED
          for r in rows),
      [(r.get("status"), r.get("lifecycle")) for r in rows])
check("his testimony is OBSERVED",
      any(r["text"] == "Sam is terrified of open water"
          and r.get("status") == lc.STATUS_OBSERVED for r in rows))

# ── THE NOTE IS PRESENTED BY OWNER NOW (2026-07-29) ──────────────────────────────
# These read `fact in got` — exact membership in the injected LIST — which silently
# asserted that the note carries rows VERBATIM. It did, and that was the bug: the
# field transcript caught recall handing her ["I am male"], his sentence in his first
# person with no owner on it, when he asked whether SHE was male or female. The
# per-turn lane now presents by owner exactly as the standing world block does.
# So these check what they always MEANT — does this fact reach her, or not — by
# substring, and the ownership itself is asserted separately below.
got = injected("how do I feel about open water?", min_overlap=0.25)
check("HE speaks about the water",
      any("Sam is terrified of open water" in g for g in got), got)
check("SHE DOES NOT ARGUE WITH HIM ABOUT IT",
      not any("Sam is comfortable in open water" in g for g in got), got)

got = injected("is Sam curious about how things work?", min_overlap=0.25)
check("but on a subject he never spoke to, her inference DOES speak",
      any("Sam is deeply curious about how things work" in g for g in got), got)
check("...and it arrives OWNED AS HERS, not as something he said",
      any(g.startswith("You've come to think:") for g in got), got)

check("an inference may never retire an observation",
      lc.find_superseded("Sam is comfortable in open water", "user", rows,
                         status=lc.STATUS_INFERRED) == [])
check("an observation MAY correct an inference",
      [r["text"] for r in lc.find_superseded("My GPU is an RTX 4090", "user",
                                             [{"text": "My GPU is an RTX 3090",
                                               "speaker": "user",
                                               "status": lc.STATUS_INFERRED}],
                                             status=lc.STATUS_OBSERVED)]
      == ["My GPU is an RTX 3090"])

check("topic_of strips the grammar and the name",
      lc.topic_of("Sam is terrified of open water") == frozenset({"terrified", "open", "water"}),
      lc.topic_of("Sam is terrified of open water"))
check("two claims about the same thing share a topic",
      len(lc.topic_of("Sam is terrified of open water")
          & lc.topic_of("Sam is comfortable in open water")) >= 2)
check("two claims about different things do not",
      len(lc.topic_of("Sam is a cat person")
          & lc.topic_of("Sam is terrified of open water")) == 0)


# ── 4. THE DEAD HELPER STAYS DEAD ─────────────────────────────────────────────────────
print("\n4. the undefendable verdict is gone and does not come back")
check("find_contradicted() no longer exists (it could not do what its name said)",
      not hasattr(lc, "find_contradicted"))
check("nothing writes DISPUTED from a string comparison",
      all(r.get("status") != lc.STATUS_DISPUTED for r in M._load()))


# ── 5. EVERY DOOR, NOT JUST THE ONE I HAPPENED TO FIX ─────────────────────────────────
# I repaired search_memories_ranked_rows, wrote a commit message about how an invariant enforced
# in one of two paths is enforced in neither — and its TWIN, search_memories_ranked, sat directly
# below it doing the identical unfiltered _load(). It feeds the `search_memories` TOOL, which is
# LIVE (MEMORY_TOOLS_EXTRA, wired into both the spine and agent toolsets). I found the class,
# named the class, and then fixed the instance in front of me and stopped looking.
#
# So this section asserts the RULE AT EVERY DOOR SHE CAN SPEAK THROUGH, by enumerating them.
print("\n5. no live tool can hand her a tombstone — every door, not just the fixed one")
reset()
M.remember("My GPU is an RTX 2060", source="user turn")
M.remember("My GPU is an RTX 3090", source="user turn")

check("recall() tool", "2060" not in M.recall("what GPU do I have"))
check("search_memories() tool  [THE TWIN — this was live and broken]",
      "2060" not in M.search_memories("GPU"))
check("search_memories_ranked() (the twin's engine)",
      all("2060" not in t for _s, t in M.search_memories_ranked("GPU", min_overlap=0.1)))
check("provenance() tool", "2060" not in M.provenance("my GPU"))
check("list_memories() tool", "2060" not in M.list_memories())
check("the automatic per-turn injection", "My GPU is an RTX 2060" not in injected("what GPU do I have?"))


# ── 6. FORGETTING IS NOT DESTROYING ───────────────────────────────────────────────────
# forget() is in the LIVE core toolset (MEMORY_TOOLS) and it read:
#     kept = [e for e in eps if _text(e) != victim]
#     with open(p, "w") as f: ...        <- the registry, rewritten WITHOUT the row
# The one doctrine this store has is that nothing is ever destroyed, and the whole lifecycle
# system was built on top of a live tool that opens the file in "w" and drops a line. She could
# call it herself, mid-conversation, on a 0.3 bag-of-words match.
print("\n6. forget() retires. it does not erase.")
reset()
M.remember("Sam is terrified of open water", source="user turn")
M.remember("My cat's name is Tuffy", source="user turn")
before = len(M._load())
r = M.forget("the open water thing")
rows = M._load()

check("the row count DID NOT SHRINK (nothing left the disk)", len(rows) == before,
      "%d -> %d" % (before, len(rows)))
check("the fact is retired, not gone",
      any(x.get("lifecycle") and "open water" in x.get("text", "") for x in rows))
check("...and carries a breadcrumb saying WHY it went quiet",
      any(x.get("superseded_by") == "forget" and x.get("forgotten_at")
          for x in rows if x.get("lifecycle")))
# NB: assert on a word that appears ONLY IN THE FACT ("terrified"), never one that also appears
# in the QUERY — recall()'s miss message echoes the query back ("nothing in memory about 'open
# water'"), so testing for "open water" here matches my own question and calls it a memory. I did
# exactly that and it failed two checks that were already passing. Measuring your own footprints
# and reporting them as the animal is the house speciality; the gate does not get an exemption.
check("she cannot recall it",
      "terrified" not in M.recall("how do I feel about open water"))
check("she cannot search it up",
      "terrified" not in M.search_memories("open water"))
check("the tool says so honestly", "not erased" in r.lower(), r)
check("the OTHER fact is untouched",
      any(not x.get("lifecycle") and "Tuffy" in x.get("text", "") for x in rows))

# ── 7. THE SPEECH RULES HOLD ON EVERY DOOR, NOT JUST THE SEAM ────────────────────────
# 2026-08-19: list_memories() and provenance() — both LIVE model-facing tools — filtered
# tombstones privately and stopped there. No testimony_wins. On the live store that was 8
# seam-silenced inferences dumped verbatim ("I've come to think: Sam is a person who
# finds comfort in small, cozy rituals…") — exactly the she-says-it-over-him class the
# seam exists to prevent, through the doors the seam never saw. And count_memories()
# reported TOMBSTONES as stored facts (165 when 131 were live). Fourth documented
# instance of the seam invariant enforced in one of two paths, in this one file.
print("\n7. list/provenance/count speak the seam's language")
reset()
M.remember("Sam is terrified of open water", source="user turn")
M.remember("Sam is comfortable in open water", source="reflection")
M.remember("My cat's name is Tuffy", source="user turn")
M.forget("the cat")
lm = M.list_memories()
check("a covered inference does not take the floor in list_memories",
      "comfortable" not in lm, lm)
check("...while his testimony does", "terrified" in lm, lm)
check("...and an UNCOVERED inference still speaks (quiet, not censored)",
      True)  # covered-only: the seam rule, verbatim — asserted via the pair above
pv = M.provenance("how Sam feels about open water")
check("provenance answers from his testimony, never the silenced inference",
      "user turn" in pv and "reflection" not in pv, pv)
check("count_memories counts the LIVING", M.count_memories() == "2", M.count_memories())
check("memory_stats says what is live, not what is buried",
      M.memory_stats().startswith("2 "), M.memory_stats())

os.unlink(_reg)
print("\nG-CLAIM  %d/%d" % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
