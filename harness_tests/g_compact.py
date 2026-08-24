#!/usr/bin/env python
"""G-COMPACT — automatic hygiene may tidy the store; it may never destroy it.

WHY THIS GATE EXISTS (2026-08-19 audit)
───────────────────────────────────────
`memory.compact_registry()` — the function the KAIROS tick's hygiene decider executes,
AND a model-callable HYGIENE_TOOL — hard-deleted rows with a raw unlocked `open(p, "w")`:
the exact shape `forget()` was convicted of (memory.py's own docstring calls that one
"the single doctrine defeated by one tool call"). Worse, its dedupe keyed on text across
ALL rows and kept the FIRST occurrence — and tombstones sort first, so a fact that was
forgotten and then honestly re-stated was resolved by DELETING THE LIVE ROW AND KEEPING
THE CORPSE. `ops.compact()` did the same job correctly, three doors down: twin functions,
and the automatic path ran the unguarded one (AGENTS.md §0, verbatim).

This gate drives THE REAL PATH — `spine.run_tick()` (hygiene decider → executor →
verifier) — over a store built through the real writers where the history can only arise
through them (remember → forget → remember is how a corpse and a live twin coexist).

OFFLINE. No GPU, no daemon (SP_DAEMON_URL at a discard port).

    python harness_tests/g_compact.py
"""
import json
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_TMP = tempfile.mkdtemp(prefix="sp_g_compact_")
REG = os.path.join(_TMP, "registry.jsonl")
open(REG, "w").close()
os.environ["SP_RECALL_REGISTRY"] = REG
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:59999"
os.environ["SP_CAPTURE_ASYNC"] = "0"

from harness.skills import memory as M          # noqa: E402
from harness.control import spine               # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


def rows():
    out = []
    with open(REG, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    out.append({"_malformed": ln})
    return out


print("1. THE HISTORY ONLY THE REAL WRITERS CAN PRODUCE")
# A corpse and its living twin: he said it, she forgot it, he said it again.
M.remember("Sam's workshop door is painted green.", source="user turn")
M.forget("workshop door painted")
M.remember("Sam's workshop door is painted green.", source="user turn")
# An honest unique fact, as a control.
M.remember("Sam keeps a spare key under the third flowerpot.", source="user turn")
r0 = rows()
corpse = [r for r in r0 if r.get("lifecycle") and "door" in (r.get("text") or "")]
live_door = [r for r in r0 if not r.get("lifecycle") and "door" in (r.get("text") or "")]
check("the corpse+live pair exists through the real writers",
      len(corpse) == 1 and len(live_door) == 1, (len(corpse), len(live_door)))

# An exact live duplicate cannot arise through remember() (it reinforces); it arises from
# the daemon era, rescues, and crashes. Plant one shaped like a real row.
dup = dict(live_door[0])
dup["name"] = "ep_tool_dupe_test"
with open(REG, "a", encoding="utf-8") as f:
    f.write(json.dumps(dup, ensure_ascii=False) + "\n")
    f.write("{ this line is not json and must be quarantined, not vaporised\n")

before = rows()
n_before_parsed = sum(1 for r in before if "_malformed" not in r)

print("\n2. THE TICK RUNS — THE REAL AUTOMATIC PATH, DECIDER TO VERIFIER")
check("the health verdict demands compaction first", M.registry_status() == "needs-compaction")
receipts = spine.run_tick()
compacts = [r for r in receipts if getattr(r, "decision", None) is not None
            and getattr(r.decision, "kind", "") == "compact_registry"] or receipts
check("the tick produced a compact receipt", len(receipts) >= 1, receipts)

print("\n3. NOTHING IS DESTROYED")
after = rows()
mal_after = [r for r in after if "_malformed" in r]
n_after_parsed = len(after) - len(mal_after)
check("no parsed row left the registry", n_after_parsed >= n_before_parsed,
      (n_before_parsed, n_after_parsed))
check("the malformed line is out of the registry", not mal_after, mal_after)
qp = os.path.join(_TMP, "quarantine.jsonl")
q = open(qp, encoding="utf-8").read() if os.path.exists(qp) else ""
check("...and into quarantine, with the raw line kept", "not json" in q, q[:120])

print("\n4. THE LIVING ARE NOT RESOLVED IN FAVOUR OF THE DEAD")
live_door2 = [r for r in after if not r.get("lifecycle") and "door" in (r.get("text") or "")]
dead_door2 = [r for r in after if r.get("lifecycle") and "door" in (r.get("text") or "")]
check("exactly one door row is still LIVE", len(live_door2) == 1, len(live_door2))
check("...and it is a REAL one, not the planted dup surviving alone",
      live_door2 and live_door2[0]["name"] != "ep_tool_dupe_test", live_door2)
check("the planted dup was TOMBSTONED, not deleted",
      any(r.get("name") == "ep_tool_dupe_test" and r.get("lifecycle") for r in after),
      [r.get("name") for r in after])
check("...with a superseded_by breadcrumb",
      any(r.get("name") == "ep_tool_dupe_test" and r.get("superseded_by") for r in after))
check("the original corpse is untouched history",
      any(r.get("name") == corpse[0]["name"] and r.get("lifecycle") for r in after))
check("the control fact is untouched",
      any("flowerpot" in (r.get("text") or "") and not r.get("lifecycle") for r in after))

print("\n5. THE TICK CONVERGES — a tombstone is history, not a pending chore")
check("after compaction the verdict is ok (or the tick loops forever)",
      M.registry_status() == "ok", M.registry_status())
receipts2 = spine.run_tick()
kinds2 = [getattr(getattr(r, "decision", None), "kind", "") for r in receipts2]
check("a second tick decides NO compaction", "compact_registry" not in kinds2, kinds2)

print("\n6. A WRITE DURING COMPACTION IS NOT A LOST WRITE")
# The hammer: remember() on one thread, compact on another, both holding the same lock —
# without it, load/rewrite interleaving silently drops rows (memory.py:86-97's scenario).
# The facts must be DISTINCT after _toks() (digits are dropped: "shelf 3" == "shelf 4",
# which reinforces instead of storing — the first cut of this hammer hit exactly that),
# and must not share an attribute slot (or compact's conflict pass retires them, which
# is compaction working, not a lost write).
_NOUNS = ("bicycle kettle ladder hammock trumpet compass anvil lantern snorkel telescope "
          "wheelbarrow accordion typewriter canoe chisel dartboard easel flask grindstone "
          "harmonica icebox jukebox kayak loom").split()
facts = ["Sam keeps a %s in the attic." % n for n in _NOUNS]
errs = []


def _writer():
    try:
        for f in facts:
            M.remember(f, source="user turn")
    except Exception as exc:                        # pragma: no cover
        errs.append(repr(exc))


t = threading.Thread(target=_writer)
t.start()
from harness.maintenance import ops                 # noqa: E402
for _ in range(6):
    ops.compact()
t.join()
check("the writer thread survived", not errs, errs)
after3 = [r for r in rows() if "_malformed" not in r]
missing = [f for f in facts
           if not any((r.get("text") or "") == f for r in after3)]
check("every concurrent fact is on disk (no lost writes)", not missing,
      ("%d missing" % len(missing), missing[:2]))

print("\n7. CLEANUP QUARANTINES WHAT IT CANNOT PARSE — the doctrine in BOTH passes")
# _cleanup_locked read _rows() — which silently drops what does not parse — and then
# _write(keep): a malformed line was VAPORISED by the one maintenance pass whose
# docstring says "REVERSIBLE: everything lands in quarantine.jsonl". _compact_locked
# (§3 above) had learned to quarantine them on 2026-08-19; this pass had not — same
# file, one doctrine, held in one of two passes, AGENTS.md §0 verbatim. Fixed
# 2026-08-24 (_rows_and_malformed); this section is the receipt the fix's own comment
# promised. Mutant: put `rows, malformed = _rows(), []` back and both checks go red.
with open(REG, "a", encoding="utf-8") as f:
    f.write("{ cleanup must quarantine me, not vaporise me\n")
n_parsed_before = sum(1 for r in rows() if "_malformed" not in r)
res7 = ops.cleanup()
check("cleanup reports the malformed line", res7.get("malformed_quarantined") == 1, res7)
check("the malformed line is OUT of the registry",
      not [r for r in rows() if "_malformed" in r])
q7 = open(qp, encoding="utf-8").read() if os.path.exists(qp) else ""
check("...and IN quarantine, raw, with the cleanup reason",
      "cleanup must quarantine me" in q7 and "malformed line (cleanup)" in q7, q7[-160:])
check("no parsed row was lost in the pass",
      sum(1 for r in rows() if "_malformed" not in r) >= n_parsed_before)

print("\nG-COMPACT: %d pass, %d fail" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
