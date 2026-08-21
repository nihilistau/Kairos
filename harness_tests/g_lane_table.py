#!/usr/bin/env python
"""G-LANE-TABLE — the gateway's recall-lane policy, the hygiene verdict, and the decider
order: three small Tier 2 conversions, pinned (INVARIANT-ROADMAP.md).

  1. AUTHORITY LANE. spine.authority_lane() — QONLY, the profile-selected spine
     authority, and the one-authority guard, extracted from app.py's stream generator
     into a pure function and enumerated EXHAUSTIVELY (16 cells). The theorem that has a
     body count ("favorite color?" -> "Human blood is green"): NEVER BOTH AUTHORITIES ON
     ONE TURN, held over every cell.
  2. HYGIENE VERDICT. memory.registry_status() is an enum and the REAL hygiene_decider
     consumes it — it used to sniff 'NEEDS COMPACTION' out of the report STRING
     (branching on a paragraph, the src-trap in a lab coat). Worlds through the real
     writer: clean -> no decision; a duplicated row -> compaction decided.
  3. THE DECIDER ORDER IS DATA. spine.PRIORITIES is the committed ordering; every stock
     decider constructor provably consumes it (toolset before recall: pick the tier,
     then decide the injection).

OFFLINE. No GPU, no daemon.
"""
import itertools
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_CAPTURE_ASYNC"] = "0"
_tmp = tempfile.mkdtemp(prefix="g_lane_")
REG = os.path.join(_tmp, "reg.jsonl")
open(REG, "w").close()
os.environ["SP_RECALL_REGISTRY"] = REG
for _k in [k for k in os.environ if k.startswith("SP_SEM_")]:
    del os.environ[_k]

from harness.control import spine as S                   # noqa: E402
from harness.skills import memory as M                   # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, str(detail)[:200]))


# -- 1. AUTHORITY LANE, EXHAUSTIVE ------------------------------------------------------------
print("\n1. authority_lane: all 16 cells")
cells = {}
for pref, auto, want, q in itertools.product(("spine", "l5"), (0, 1), (0, 1), (0, 1)):
    cells[(pref, auto, want, q)] = S.authority_lane(pref, bool(auto), bool(want), bool(q))
check("FORALL cells: never both authorities on one turn",
      all(not (a and w) for a, w, _ in cells.values()), cells)
check("FORALL cells: spine preference always disarms the daemon",
      all(not a for (p, _, _, _), (a, _, _) in cells.items() if p == "spine"))
check("FORALL cells: no question, no spine recall (QONLY)",
      all(not w for (_, _, _, q), (_, w, _) in cells.items() if q == 0))
check("l5 armed + spine wanted -> L5 wins with the receipt event",
      cells[("l5", 1, 1, 1)] == (True, False, "L5"))
check("spine pref + client passthrough -> spine wins with the receipt event",
      cells[("spine", 1, 1, 1)] == (False, True, "spine"))
check("plain spine question turn -> spine recall, no event",
      cells[("spine", 0, 1, 1)] == (False, True, None))
check("FORALL cells: the lane never ARMS what the caller did not ask for",
      all((a <= auto) and (w <= want)
          for (p, auto, want, q), (a, w, _) in cells.items()))

# -- 2. HYGIENE: THE ENUM, THROUGH THE REAL DECIDER -------------------------------------------
print("\n2. hygiene verdict (enum, not prose sniff)")
M.remember("Sam's rake handle is oak", source="user turn")
check("clean registry -> status ok", M.registry_status() == "ok", M.registry_status())
dec = S.hygiene_decider()._fn(S.TurnView(phase="tick"))
check("clean registry -> the real decider decides nothing", dec == [], dec)
with open(REG, encoding="utf-8") as f:
    line = f.readline()
with open(REG, "a", encoding="utf-8") as f:
    f.write(line)                                        # an exact duplicate row
check("duplicated row -> needs-compaction", M.registry_status() == "needs-compaction")
dec = S.hygiene_decider()._fn(S.TurnView(phase="tick"))
check("the real decider decides compaction, with the report as receipt",
      len(dec) == 1 and dec[0].kind == "compact_registry"
      and "NEEDS COMPACTION" in dec[0].payload.get("report", ""), dec)
os.environ["SP_RECALL_REGISTRY"] = os.path.join(_tmp, "nowhere.jsonl")
check("no registry -> unconfigured (a third verdict, not a crash)",
      M.registry_status() == "unconfigured")
os.environ["SP_RECALL_REGISTRY"] = REG

# -- 3. THE DECIDER ORDER IS DATA -------------------------------------------------------------
print("\n3. priorities: committed, consumed")
check("the committed ordering is what the doctrine says",
      S.PRIORITIES == {"toolset": 10, "recall": 20, "persona_tags": 30, "hygiene": 40})
built = {d.name: d.priority for d in (S.toolset_decider(), S.recall_decider(),
                                      S.persona_tag_decider(), S.hygiene_decider())}
check("every stock decider consumes the committed dict", built == S.PRIORITIES, built)
check("toolset runs before recall (pick the tier, then decide the injection)",
      S.PRIORITIES["toolset"] < S.PRIORITIES["recall"])

print("\nG-LANE-TABLE: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_lane_table.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_lane_table", "pass": PASS, "fail": FAIL,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
sys.exit(1 if FAIL else 0)
