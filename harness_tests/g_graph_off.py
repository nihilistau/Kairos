"""G-GRAPH-OFF — with the graph's switches off, her per-turn recall is byte-identical to a tree
that has no graph (memory-graph Task 5).

WHAT THIS HOLDS. `recall_decider` is her live recall path. The graph may decorate what it injects
(`SP_GRAPH_ANNOTATE`), and when it does not, the `facts` payload must be exactly what it was
before the graph existed, and the off path executes no graph code. Two legs say it, and neither
claims more than it measures: the recall path does not IMPORT the package (the live process still
imports it at boot, `agent.all_tools` -> `recall_node`), and with the package imported no graph
FUNCTION runs on an off turn (`annotate.annotate_fact` is patched on its owner and counted). Also held:
  - ON adds only the node id and at most N neighbour lines; the fact's own text is untouched, and
    the decoration never carries a secret (it goes through `graph.view`);
  - no generation at all: today's facts, no exception, and the miss is counted;
  - the context `view` builds per call is cached on the registry stamp and generation, so a
    second annotate in the same turn does not re-read `live_rows` (and a changed registry does);
  - a stale graph with `build` on starts ONE daemon rebuild thread however many facts ask, the
    turn annotates from the generation it has, and a fresh graph starts none;
  - `serve.build_env` maps `[graph]` and leaves every key absent when the table (or a key) is
    absent; the shipped profile arms nothing.

MUTANTS (run 2026-11-03; each restored by text swap):
  (a) spine.recall_decider annotates whatever SP_GRAPH_ANNOTATE says (drop the `== "1"` test) ->
      "all switches off: facts byte-identical to a tree without the graph", "the off recall path does
      not import the graph package" and "an off turn calls no graph function (package imported)" go red.
  (b) annotate._kick skips the `if _running: return` guard -> "a stale graph starts exactly one
      rebuild thread" goes red.
  (c) view._ctx_for never reuses its cache -> "a second annotate in the same turn does not re-read
      live_rows" goes red.
  (d) build_env exports SP_GRAPH_ANNOTATE as "0" when the table is absent -> "an absent [graph]
      table leaves every SP_GRAPH_* key absent" goes red.
  (e) `[graph].rules` check: drop the unknown-name refusal in serve.build_env -> "build_env refuses
      an unknown [graph] rule name" goes red; drift GRAPH_RULE_NAMES -> "serve.GRAPH_RULE_NAMES
      equals graph rules.RULES" goes red.
"""
from __future__ import annotations

import copy
import os
import shutil
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
sb = sandbox("g_graph_off")
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import harness.skills.memory as memory  # noqa: E402
from harness.control.spine import recall_decider, TurnView  # noqa: E402
from harness.skills import graph  # noqa: E402
from harness.skills.graph import annotate, config, store  # noqa: E402
import serve  # noqa: E402

FX = os.path.join(HERE, "fixtures", "graph")
REG = os.environ["SP_RECALL_REGISTRY"]
TDIR = os.path.join(sb, "memory", "transcripts")
shutil.copyfile(os.path.join(FX, "registry.jsonl"), REG)
shutil.copytree(os.path.join(FX, "transcripts"), TDIR)
graph.build(REG)
GRAPH_ROOT = store.graph_root(REG)

CAT_FACT = "ep_live_1767261600001"
Q = "what is my cat called?"
SWITCHES = ("SP_GRAPH_BUILD", "SP_GRAPH_ANNOTATE", "SP_GRAPH_ANNOTATE_N", "SP_GRAPH_FOLLOW",
            "SP_GRAPH_FOLLOW_CAP", "SP_GRAPH_RULES")


# This gate drives the rebuild trigger several times in a row and expects each stale turn to be
# able to start one. The shipped floor (SP_GRAPH_REBUILD_MIN_S, default 600; held by
# G-GRAPH-FOLLOW) would make the second and later triggers no-ops, so the window is set to 0 here.
os.environ["SP_GRAPH_REBUILD_MIN_S"] = "0"


def clear():
    for k in SWITCHES:
        os.environ.pop(k, None)


def decider_facts(q=Q):
    out = []
    for d in recall_decider()._fn(TurnView(phase="pre", user_text=q)):
        out += d.payload.get("facts", [])
    return out


def backdate(seconds=100):
    """Make the registry and transcripts older than any graph built from now on."""
    t = time.time() - seconds
    for p in [REG] + [os.path.join(TDIR, n) for n in os.listdir(TDIR)]:
        os.utime(p, (t, t))


def join_rebuilds():
    for th in [th for th in threading.enumerate() if th.name == "graph-rebuild"]:
        th.join(30)


clear()
backdate()

# ── all off: byte-identical, and no graph code runs ────────────────────────────
GRAPH_MODS = [k for k in sys.modules if k == "harness.skills.graph" or k.startswith("harness.skills.graph.")]
saved = {k: sys.modules.pop(k) for k in GRAPH_MODS}
d0 = saved["harness.skills.graph"].dropped()
facts_off = decider_facts()
imported = [k for k in sys.modules if k == "harness.skills.graph" or k.startswith("harness.skills.graph.")]
for k in GRAPH_MODS:
    sys.modules[k] = None                        # unimportable: the tree as it was before the graph
facts_ref = decider_facts()
for k in GRAPH_MODS:
    del sys.modules[k]
sys.modules.update(saved)
check("the recall path returns the cat fact", len(facts_off) >= 1 and "Tuffy" in facts_off[0], facts_off)
check("all switches off: facts byte-identical to a tree without the graph", facts_off == facts_ref,
      (facts_off, facts_ref))
check("the off recall path does not import the graph package", imported == [], imported)
check("an off turn counts no graph drop", graph.dropped() == d0)
os.environ["SP_GRAPH_ANNOTATE"] = "0"
check("SP_GRAPH_ANNOTATE=0 is off", decider_facts() == facts_off)
clear()

# The package IS imported in the live process (agent.all_tools -> recall_node), so "not imported"
# is not the claim that matters. With it imported, no graph function may run on an off turn.
_calls = []
_real_annotate = annotate.annotate_fact
annotate.annotate_fact = lambda *a, **k: (_calls.append(a), _real_annotate(*a, **k))[1]   # the OWNER
try:
    facts_off2 = decider_facts()
finally:
    annotate.annotate_fact = _real_annotate
check("an off turn calls no graph function (package imported)", _calls == [] and facts_off2 == facts_off, _calls)

# ── annotate on ────────────────────────────────────────────────────────────────────────────
os.environ["SP_GRAPH_ANNOTATE"] = "1"
facts_on = decider_facts()
check("annotate on: the recalled fact carries its id", f"[{CAT_FACT}]" in facts_on[0], facts_on)
check("annotate on: the fact's own text is untouched", facts_on[0].startswith(facts_off[0] + " [" + CAT_FACT + "]"))
check("annotate on: at most N (default 2) neighbour lines", 0 < facts_on[0].count("↳") <= 2, facts_on[0])
os.environ["SP_GRAPH_ANNOTATE_N"] = "1"
check("annotate on: SP_GRAPH_ANNOTATE_N is honoured", decider_facts()[0].count("↳") == 1)
os.environ["SP_GRAPH_ANNOTATE_N"] = "0"
check("annotate on: N=0 is the id alone", "↳" not in decider_facts()[0])
os.environ.pop("SP_GRAPH_ANNOTATE_N")

leaks = []
for q in (Q, "what's my PIN?", "what is my bank card PIN?", "tell me about Sam", "what did I say about the cat?"):
    clear()
    off = decider_facts(q)
    os.environ["SP_GRAPH_ANNOTATE"] = "1"
    on = decider_facts(q)
    if len(off) != len(on):
        leaks.append((q, "count differs"))
    for o, a in zip(off, on):
        if "4417" in a[len(o):]:
            leaks.append((q, a))
check("annotate adds no secret text beyond the fact itself, whatever the question", leaks == [], leaks)

# ── perf: one registry read per turn, not per fact ─────────────────────────────────────────
clear()
_real_live = memory.live_rows
reads = []
memory.live_rows = lambda testimony=False: (reads.append(testimony), _real_live(testimony=testimony))[1]
try:
    a1 = annotate.annotate_fact("x", CAT_FACT, Q, 2)
    a2 = annotate.annotate_fact("y", "t:2026-01-01:0", Q, 2)
    after_two = list(reads)
    t = time.time() + 5
    os.utime(REG, (t, t))                        # the stamp moves: the context must be rebuilt
    annotate.annotate_fact("x", CAT_FACT, Q, 2)
    after_touch = list(reads)
finally:
    memory.live_rows = _real_live
    backdate()
check("annotate returned decorated text for both facts", "[" + CAT_FACT + "]" in a1 and "[t:2026-01-01:0]" in a2)
check("a second annotate in the same turn does not re-read live_rows", after_two == [True], after_two)
check("a changed registry stamp rebuilds the context", after_touch == [True, True], after_touch)

# ── no generation: today's facts, no exception, counted ────────────────────────────────────
clear()
facts_plain = decider_facts()
os.environ["SP_GRAPH_ANNOTATE"] = "1"
shutil.rmtree(GRAPH_ROOT)
d1 = graph.dropped()
try:
    facts_none = decider_facts()
    err = None
except Exception as e:  # noqa: BLE001
    facts_none, err = None, repr(e)
check("annotate on with no graph: today's facts, no exception", facts_none == facts_plain, err or facts_none)
check("...and it is counted", graph.dropped() >= d1 + 1, (d1, graph.dropped()))

# ── background rebuild: one thread, never blocks the turn ──────────────────────────────────
clear()
graph.build(REG)                                 # current generation, newer than the backdated sources
os.environ["SP_GRAPH_ANNOTATE"] = "1"
os.environ["SP_GRAPH_BUILD"] = "1"
s0 = annotate._started
annotate.annotate_fact("x", CAT_FACT, Q, 2)
check("a fresh graph starts no rebuild", annotate._started == s0, (s0, annotate._started))

t = time.time() + 5
os.utime(REG, (t, t))                            # the registry is now newer than the graph
gate_open = threading.Event()
real_run = annotate._run_build
annotate._run_build = lambda: gate_open.wait(10)  # the trigger, stubbed: the thread parks here
try:
    outs = []
    workers = [threading.Thread(target=lambda: outs.append(annotate.annotate_fact("x", CAT_FACT, Q, 2)))
               for _ in range(6)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(5)
    for _ in range(3):
        outs.append(annotate.annotate_fact("x", CAT_FACT, Q, 2))
    check("a stale graph starts exactly one rebuild thread", annotate._started == s0 + 1 and annotate._running,
          (s0, annotate._started, annotate._running))
    check("the turn annotates from the current generation while that thread runs",
          len(outs) == 9 and all(o.startswith("x [" + CAT_FACT + "]") for o in outs), outs[:2])
finally:
    gate_open.set()
    join_rebuilds()
    annotate._run_build = real_run
check("the flag clears when the thread ends", not annotate._running)
annotate._run_build = lambda: None
try:
    annotate.annotate_fact("x", CAT_FACT, Q, 2)
    join_rebuilds()
finally:
    annotate._run_build = real_run
check("...so the next stale turn may start another", annotate._started == s0 + 2, annotate._started)

# The real build, no stub: no generation + build on -> text unchanged + counted + a thread builds it.
shutil.rmtree(GRAPH_ROOT)
d2 = graph.dropped()
out = annotate.annotate_fact("x", CAT_FACT, Q, 2)
join_rebuilds()
check("no generation, build on: the text comes back unchanged and the miss is counted",
      out == "x" and graph.dropped() >= d2 + 1, (out, d2, graph.dropped()))
check("...and the background thread built a generation", store.load(GRAPH_ROOT) is not None)
check("...which the next turn annotates from",
      annotate.annotate_fact("x", CAT_FACT, Q, 2).startswith("x [" + CAT_FACT + "]"))
clear()

# ── config and serve ───────────────────────────────────────────────────────────────────────
check("config: unset is every switch off, with the documented defaults",
      config.switches() == {"build": False, "annotate": False, "annotate_n": 2, "follow": False,
                            "follow_cap": 3, "rules": ["explicit", "sequence", "day", "minted_from", "activity"],
                            "dir": os.environ.get("SP_GRAPH_DIR", "")})
base = copy.deepcopy(serve.load_profile("companion"))
base.pop("graph", None)
env0 = serve.build_env(copy.deepcopy(base))
# SP_GRAPH_DIR is a LOCATION, not a switch: since 2026-11-26 her home names it (the same
# folder the reader derived beside the registry), so it is present without any [graph].
# Every SWITCH stays absent, and the location is the home's, not an invention.
_sw0 = [k for k in env0 if k.startswith("SP_GRAPH_") and k != "SP_GRAPH_DIR"]
check("an absent [graph] table leaves every SP_GRAPH_* switch absent", not _sw0, _sw0)
from harness import home as _home  # noqa: E402
check("...and SP_GRAPH_DIR, when present, is the home's graph folder",
      "SP_GRAPH_DIR" not in env0 or env0["SP_GRAPH_DIR"] == _home.env_for(
          serve.home_path(base))["SP_GRAPH_DIR"], env0.get("SP_GRAPH_DIR"))
on_prof = copy.deepcopy(base)
on_prof["graph"] = {"annotate": True, "annotate_neighbours": 3, "rules": ["explicit", "day"]}
env1 = serve.build_env(on_prof)
check("serve maps [graph] keys", env1.get("SP_GRAPH_ANNOTATE") == "1" and env1.get("SP_GRAPH_ANNOTATE_N") == "3"
      and env1.get("SP_GRAPH_RULES") == "explicit,day", {k: v for k, v in env1.items() if k.startswith("SP_GRAPH_")})
check("a key the table leaves out stays absent",
      not any(k in env1 for k in ("SP_GRAPH_BUILD", "SP_GRAPH_FOLLOW", "SP_GRAPH_FOLLOW_CAP")))
for _bad_rules in (["explicit", "dya"], ["nope"]):
    _bad_prof = copy.deepcopy(base)
    _bad_prof["graph"] = {"rules": _bad_rules}
    try:
        serve.build_env(_bad_prof)
        _refused = False
    except SystemExit:
        _refused = True
    check("build_env refuses an unknown [graph] rule name %r" % (_bad_rules,), _refused)
from harness.skills.graph import rules as _graph_rules  # noqa: E402
check("serve.GRAPH_RULE_NAMES equals graph rules.RULES", set(serve.GRAPH_RULE_NAMES) == set(_graph_rules.RULES.keys()),
      (sorted(serve.GRAPH_RULE_NAMES), sorted(_graph_rules.RULES)))
off_prof = copy.deepcopy(base)
off_prof["graph"] = {"build": False, "annotate": False, "follow": False}
env2 = serve.build_env(off_prof)
check("an all-false [graph] table exports off",
      [env2.get(k) for k in ("SP_GRAPH_BUILD", "SP_GRAPH_ANNOTATE", "SP_GRAPH_FOLLOW")] == ["0", "0", "0"])
prof = os.path.join(ROOT, "profiles", "companion.toml")
if os.path.exists(prof):
    import tomllib
    with open(prof, "rb") as f:
        g = tomllib.load(f).get("graph", {})
    check("the shipped profile has a [graph] table and arms nothing",
          bool(g) and not any(v is True for v in g.values()), g)

finish("G-GRAPH-OFF")
