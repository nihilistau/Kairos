"""G-CURATE — he can re-file a row without losing it, and settle a question without losing that
either. OFFLINE.

TWO SURFACES, ONE RULE: his judgement is recorded, never silent, and nothing is destroyed.

  ops.relabel     the classifier is a heuristic and the author lane is set by whichever door
                  a producer used. Both are wrong sometimes, and until now the only remedy
                  was to retire a true row and re-add it - which loses its mentions, its
                  first_seen and its provenance. This moves the LABELS and keeps the row.
  decisions       the queue of things only he can settle. NOT her memory (nothing here
                  reaches her prefix or her recall) and NOT the ledger (that records what is
                  OFF and why, permanently, for a reader; this records what is UNDECIDED,
                  for a decider).

The vocabulary check is the load-bearing part of the relabel: a panel that could invent a
mem_class would put rows in signature cells the verdict table has never seen AND outside the
producer closure G-MEMCLASS holds. It cannot, and section 2 is why.

    python harness_tests/g_curate.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _src as _srcmod  # noqa: E402
from _gate import check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"          # no capture attempt (gates/README.md)
os.environ["SP_CAPTURE_ASYNC"] = "0"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["SP_SEM_MINT"] = "0"
_D = tempfile.mkdtemp(prefix="g_curate_")
os.environ["SP_RECALL_REGISTRY"] = os.path.join(_D, "registry.jsonl")
open(os.environ["SP_RECALL_REGISTRY"], "w").close()

from harness.skills import memory as M            # noqa: E402
from harness.skills import memclass as MC         # noqa: E402
from harness.skills import decisions as DEC       # noqa: E402
from harness.maintenance import ops               # noqa: E402


def row_of(name):
    return next((r for r in M._load() if r.get("name") == name), {})


print("1. A RELABEL MOVES THE LABELS AND KEEPS THE ROW")
M.remember("Sam's brother is a diver who lives in Broome", source="user turn")
M.remember("Sam's brother is a diver who lives in Broome", source="user turn")   # mentions 2
name = M._load()[-1]["name"]
before = dict(row_of(name))
check("the row starts as his, class relationship, mentions 2",
      before.get("speaker") == "user" and before.get("mem_class") == "relationship"
      and before.get("mentions") == 2, before.get("mem_class"))

res = ops.relabel(name, mem_class="fact")
after = row_of(name)
check("relabel reports what moved", res.get("ok") and res["changed"] == {"mem_class": "fact"}
      and res["was"] == {"mem_class": "relationship"}, res)
check("...the class really moved", after.get("mem_class") == "fact")
for f in ("text", "name", "ts", "first_seen", "mentions", "recalled", "dir", "npos"):
    check("...and %s is untouched" % f, after.get(f) == before.get(f),
          (f, before.get(f), after.get(f)))
check("...and it SAYS SO on the row, dated",
      "operator relabel" in (after.get("src") or "")
      and "mem_class relationship->fact" in (after.get("src") or ""), after.get("src"))
check("...appended to src, not replacing it (provenance reads the history)",
      (after.get("src") or "").startswith(before.get("src") or ""), after.get("src"))

res2 = ops.relabel(name, speaker="self", kind="thought", mem_class=MC.SELF_NARRATIVE)
after2 = row_of(name)
check("three labels move at once, and all three land",
      res2.get("ok") and after2.get("speaker") == "self"
      and after2.get("kind") == "thought"
      and after2.get("mem_class") == MC.SELF_NARRATIVE, res2.get("changed"))
check("a no-op relabel changes nothing and says so",
      ops.relabel(name, speaker="self")["changed"] == {})
check("clearing the kind is allowed (empty is a value)",
      ops.relabel(name, kind="")["changed"] == {"kind": ""} and not row_of(name).get("kind"))

print("\n2. THE VOCABULARY IS THE LAW, AND THE PANEL IS NOT")
check("an invented mem_class is refused",
      ops.relabel(name, mem_class="vibes")["ok"] is False)
check("an invented kind is refused", ops.relabel(name, kind="mood")["ok"] is False)
check("an invented speaker is refused", ops.relabel(name, speaker="nobody")["ok"] is False)
check("a name that is not in the store is refused",
      ops.relabel("ep_tool_nope", mem_class="fact")["ok"] is False)
check("a relabel with no fields is refused", ops.relabel(name)["ok"] is False)
check("...and none of those refusals touched the row",
      row_of(name).get("mem_class") == MC.SELF_NARRATIVE)
check("every offered class is one memclass actually holds",
      all(c in MC.CLASSES for c in
          ("fact", "preference", "relationship", "identity", "event",
           "self-narrative", "feeling", "private-secret")))
check("every offered kind is one the narrative vocabulary holds",
      all(k in MC.NARRATIVE_KINDS for k in
          ("journal", "thought", "narration", "dream", "self_description",
           "spoke_up", "feeling", "chapter")))

print("\n3. NOTHING IS DESTROYED, HERE EITHER")
n_before = len(M._load())
ops.relabel(name, mem_class="fact")
check("a relabel adds no rows and removes none", len(M._load()) == n_before)
check("...and the row is still LIVE (relabel is not retirement)",
      not row_of(name).get("lifecycle"))

print("\n4. THE QUEUE: ASKED, DECIDED, AND KEPT")
os.environ["SP_DECISIONS"] = os.path.join(_D, "decisions.jsonl")
a = DEC.ask("Arm the thing?", body="because reasons", options=["yes", "no"],
            kind="route", area="test", id="q1")
check("a question lands", a.get("ok") and a.get("id") == "q1", a)
check("...and is OPEN", [r["id"] for r in DEC.open_items()] == ["q1"])
check("re-asking the same id does not duplicate it",
      DEC.ask("Arm the thing?", id="q1").get("already") is True and len(DEC.items()) == 1)
check("a choice outside the options is refused",
      DEC.decide("q1", "maybe")["ok"] is False)
check("deciding a question that does not exist is refused",
      DEC.decide("nope", "yes")["ok"] is False)
check("...and it is still open after both refusals", len(DEC.open_items()) == 1)
d = DEC.decide("q1", "yes", note="because he said so")
check("a decision lands and carries the kind back (so a route knows to run)",
      d.get("ok") and d.get("choice") == "yes" and d.get("kind") == "route", d)
check("...it leaves the OPEN queue", DEC.open_items() == [])
it = DEC.items()[0]
check("...and the ASK is still there with its answer beside it",
      it["title"] == "Arm the thing?" and it["choice"] == "yes"
      and it["note"] == "because he said so" and it["status"] == "decided", it)
DEC.decide("q1", "no", note="changed my mind")
it2 = DEC.items()[0]
check("CHANGING HIS MIND IS HISTORY, NOT A REWRITE: last verdict wins",
      it2["choice"] == "no" and it2["note"] == "changed my mind")
raw = [json.loads(x) for x in open(os.environ["SP_DECISIONS"], encoding="utf-8") if x.strip()]
check("...and BOTH verdicts are still on disk, append-only",
      [r.get("choice") for r in raw if r.get("op") == "decide"] == ["yes", "no"], raw)

print("\n5. THE QUEUE IS NOT HER MEMORY")
check("nothing the queue wrote reached the registry",
      not any("Arm the thing" in (r.get("text") or "") for r in M._load()))
src = open(os.path.join(ROOT, "harness", "skills", "decisions.py"),
           encoding="utf-8", errors="replace").read()
check("decisions.py never imports the memory package",
      "harness.skills.memory" not in src and "harness.maintenance.ops" not in src)
# THE BAN IS ON CODE, NOT ON THE WORD. decisions.py's own docstring says "remember()
# never sees it" — which is the promise, not a violation of it. h_aux §4 records the same
# distinction; a gate that greps prose convicts the comment that explains the rule.
_code = chr(10).join(l for l in src.splitlines()
                     if not l.lstrip().startswith("#"))
_code = _code.split('"""')[2] if _code.count('"""') >= 2 else _code   # drop the docstring
check("...and never touches a writer seam, in CODE",
      all(w not in _code for w in ("remember(", "_save_all", "compact_registry",
                                   "forget(", "ops.add", "ops.relabel")),
      [w for w in ("remember(", "_save_all", "compact_registry", "forget(") if w in _code])
check("its store is its own file, not the registry",
      "decisions.jsonl" in DEC.path() and "registry.jsonl" not in DEC.path())

print("\n6. THE PANEL CAN ONLY ASK FOR WHAT THE SERVER ALLOWS")
app = _srcmod.pkg("harness", "server")
check("the relabel route exists and goes through ops.relabel",
      '"/v1/memory/relabel"' in app and "ops.relabel(" in app)
check("the decide route exists and goes through decisions.decide",
      '"/v1/decisions/decide"' in app and "_dec.decide(" in app)
check("the memory payload carries `kind`, or the panel cannot show what it edits",
      '"kind": e.get("kind", "")' in app)
ui = open(os.path.join(ROOT, "ui", "src", "apps", "Memory.jsx"),
          encoding="utf-8", errors="replace").read()
check("the panel offers only vocabulary the server will accept",
      all(("'%s'" % c) in ui for c in ("fact", "self-narrative", "feeling"))
      and "memclass.CLASSES" in ui, "the comment must name where the law lives")

finish("G-CURATE")
