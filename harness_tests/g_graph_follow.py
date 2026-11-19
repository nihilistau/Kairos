"""G-GRAPH-FOLLOW — `recall_node`, the follow tool, and the Task 5 review's hardening
(memory-graph Task 6).

WHAT THIS HOLDS.
  - `recall_node` is registered UNCONDITIONALLY, in the extra tier (never core), so her cached
    system prompt is byte-identical with `follow` on and off. The two bundles are built through
    the real `agent.system_bundle()` in this sandbox; `system_bundle` memoises in
    `agent._SYS["bundle"]`, so the gate sets that to None before each build (the same thing
    `invalidate_system_prefix` does) or the second build would only compare the cache to itself.
  - With `follow` off it answers "following is off"; over `follow_cap` successful follows in one
    question it answers "that's enough following for this turn" (the count resets when
    `memory.current_question()` changes; a miss costs nothing and does not count); an unknown,
    retired, or invisible id answers "nothing live under that id".
  - It never serves a secret: the secret's own id, the turn it was minted from, and its
    neighbours all come through `graph.view`, so "what's my PIN?" with follow on never yields 4417.
  - HARDENING carried from the Task 5 review:
    (a) the view's context cache honours `memory.invalidate_cache()`: an in-process write that
        leaves the registry's (path, mtime, size) stamp unchanged is still seen;
    (b) a background rebuild starts at most once per `SP_GRAPH_REBUILD_MIN_S` (default 600) once
        a generation exists (no generation at all is not churn and is built at once), and
        `graph.build` prunes to the newest `SP_GRAPH_KEEP` (default 3) generations, never the
        one CURRENT names;
    (c) staleness (a stat of every transcript day file) is computed at most once per window,
        not once per recalled fact;
    (d) `serve.build_env` rejects a `[graph].rules` that is not a list of strings, loudly.

MUTANTS (run 2026-11-03; each restored by text swap):
  (a) all_tools appends GRAPH_TOOLS only when SP_GRAPH_FOLLOW is "1" -> "registered whether or
      not follow is on" and "system prompt identical with follow on and off" go red.
  (b) view._ctx_for drops M.cache_epoch() from its key -> "an in-process write that leaves the
      stamp unchanged is seen" goes red (the cache is primed at a different stamp first, so the
      precondition cannot absorb the mutant).
  (c) annotate._refresh_if_stale ignores the window -> "one rebuild per window" and
      "staleness is computed once per window" go red.
  (d) store.prune deletes CURRENT's generation too -> "prune never deletes the generation CURRENT
      names" goes red.
  (f) store.prune orders by directory mtime only -> "an old generation with a bumped mtime is pruned first".
  (g) the tool's first docstring sentence is longer than 54 chars -> "the prompt lists the tool as one whole line".
  (h) the docstring's first line is cut mid-sentence again -> "the loaded description is a whole sentence about one hop".
  (e) recall_node renders node text itself, not via view.visible -> the secret checks go red.
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
sb = sandbox("g_graph_follow")
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import harness.skills.memory as memory  # noqa: E402
from harness import agent  # noqa: E402
from harness.skills import graph  # noqa: E402
from harness.skills.graph import annotate, config, store, view  # noqa: E402
from harness.skills.graph.tool import recall_node  # noqa: E402
import serve  # noqa: E402

FX = os.path.join(HERE, "fixtures", "graph")
REG = os.environ["SP_RECALL_REGISTRY"]
TDIR = os.path.join(sb, "memory", "transcripts")
shutil.copyfile(os.path.join(FX, "registry.jsonl"), REG)
shutil.copytree(os.path.join(FX, "transcripts"), TDIR)
graph.build(REG)
GROOT = store.graph_root(REG)

CAT_FACT = "ep_live_1767261600001"
RETIRED = "ep_live_1767261600002"
SECRET = "ep_live_1767261600006"
TUFFY_TURN = "t:2026-01-02:0"             # "my cat is called Tuffy", the turn CAT_FACT was minted from
MINTED = "t:2026-01-02:2"                 # the secret said in words
NOTE = memory.SECRET_WITHHELD_NOTE
SWITCHES = ("SP_GRAPH_BUILD", "SP_GRAPH_ANNOTATE", "SP_GRAPH_ANNOTATE_N", "SP_GRAPH_FOLLOW",
            "SP_GRAPH_FOLLOW_CAP", "SP_GRAPH_RULES", "SP_GRAPH_REBUILD_MIN_S", "SP_GRAPH_KEEP")
_asked = [0]


def clear():
    for k in SWITCHES:
        os.environ.pop(k, None)


def ask(q=None):
    """A new question: the follow cap counts per question."""
    _asked[0] += 1
    memory.set_question(q if q is not None else "question number %d" % _asked[0])


def names(specs):
    return [s.name for s in specs]


def join_rebuilds():
    for th in [th for th in threading.enumerate() if th.name == "graph-rebuild"]:
        th.join(30)


def backdate(seconds=100):
    t = time.time() - seconds
    for p in [REG] + [os.path.join(TDIR, n) for n in os.listdir(TDIR)]:
        os.utime(p, (t, t))


_last_sys = [""]


def bundle_text():
    agent._SYS["bundle"] = None                  # system_bundle memoises; build fresh each time
    sys_content, tool_index = agent.system_bundle()
    _last_sys[0] = sys_content
    # tool_index holds ToolSpecs whose repr carries the callable's address; compare what the model sees.
    return repr((sys_content, sorted((k, v.description, repr(v.parameters)) for k, v in tool_index.items())))


# ── registration: unconditional, extra tier ─────────────────────────────────────────────────
clear()
check("registered whether or not follow is on", "recall_node" in names(agent.all_tools()))
check("not in the core tier", "recall_node" not in names(agent.core_tools()))
check("in the extra tier", "recall_node" in names(agent.extra_tools()))
off_text = bundle_text()
off_sys = _last_sys[0]
os.environ["SP_GRAPH_FOLLOW"] = "1"
os.environ["SP_GRAPH_ANNOTATE"] = "1"
os.environ["SP_GRAPH_BUILD"] = "1"
on_text = bundle_text()
clear()
agent._SYS["bundle"] = None
GIST = "Open a memory by its [id]; shows what it links to"
lines = [l for l in off_sys.splitlines() if l.lstrip("- ").startswith("recall_node")]
check("the prompt lists the tool as one whole line, no ellipsis (the gist is all her prefix shows)",
      lines == ["- recall_node(node_id): " + GIST] and "…" not in lines[0], lines)
check("system prompt identical with follow on and off", off_text == on_text)
desc = {s.name: s.description for s in agent.all_tools()}["recall_node"]
check("the loaded description is a whole sentence about one hop (its docstring's first physical line)",
      desc.startswith(GIST) and desc.endswith(".") and "one hop" in desc, desc)

# ── behaviour ───────────────────────────────────────────────────────────────────────────────
ask()
check("off answers plainly", recall_node(CAT_FACT) == "following is off", recall_node(CAT_FACT))
os.environ["SP_GRAPH_FOLLOW"] = "1"
os.environ["SP_GRAPH_FOLLOW_CAP"] = "50"
got = recall_node(CAT_FACT)
check("follow returns the entry under its id", got.startswith("[%s] " % CAT_FACT) and "Tuffy" in got, got)
check("follows to the minting turn", "minted_from [%s] my cat is called Tuffy" % TUFFY_TURN in got, got)
check("neighbour lines use annotate's format",
      all(l.startswith("  ↳ ") for l in got.split("\n")[1:]) and len(got.split("\n")) > 1, got)
check("a turn id is followable one hop on", "Tuffy" in recall_node(TUFFY_TURN)
      and CAT_FACT in recall_node(TUFFY_TURN))
for bad in ["", "../registry.jsonl", "ep_nope", RETIRED, None, "  "]:
    check("garbage id %r answers plainly" % (bad,), recall_node(bad) == "nothing live under that id",
          recall_node(bad))
os.environ["SP_GRAPH_RULES"] = "day"
check("the configured rules limit the hop", "minted_from" not in recall_node(CAT_FACT))
os.environ.pop("SP_GRAPH_RULES")
d0 = graph.dropped()
shutil.move(GROOT, GROOT + ".away")
check("no generation answers plainly", recall_node(CAT_FACT) == "nothing live under that id")
shutil.move(GROOT + ".away", GROOT)

# the cap
os.environ["SP_GRAPH_FOLLOW_CAP"] = "3"
ask()
outs = [recall_node(CAT_FACT) for _ in range(4)]
check("cap holds", outs[-1] == "that's enough following for this turn" and "Tuffy" in outs[2], outs)
ask()
recall_node(CAT_FACT)
recall_node(CAT_FACT)
check("a miss does not spend the cap", recall_node("ep_nope") == "nothing live under that id"
      and recall_node(CAT_FACT).startswith("[") and recall_node(CAT_FACT).startswith("that's enough"))
ask()
check("a new question resets the cap", recall_node(CAT_FACT).startswith("[%s]" % CAT_FACT))
os.environ["SP_GRAPH_FOLLOW_CAP"] = "50"

# ── secrets ─────────────────────────────────────────────────────────────────────────────────
ask("what's my PIN?")
leaks = []
for nid in (SECRET, MINTED, "t:2026-01-02:3", "t:2026-01-02:4", "t:2026-01-02:5"):
    r = recall_node(nid)
    if "4417" in r or "four four one seven" in r:
        leaks.append((nid, r))
check("recall_node never serves a secret, even asked 'what's my PIN?'", leaks == [], leaks)
r = recall_node(SECRET)
check("a secret's id is the withheld note", r == "[%s] %s" % (SECRET, NOTE) or r.startswith("[%s] %s" % (SECRET, NOTE)), r)
check("a secret's minted turn is the withheld note", recall_node(MINTED).startswith("[%s] %s" % (MINTED, NOTE)))
check("no neighbour line of a secret carries it",
      "4417" not in recall_node("t:2026-01-02:1") and "4417" not in recall_node("t:2026-01-02:0"))

# ── (a) an in-process write is seen even when the stamp is not ───────────────────────────────
with open(REG, encoding="utf-8") as f:
    orig = f.read()
swapped = orig.replace('"mem_class": "private-secret"', '"mem_class": "private-secrex"')
assert len(swapped) == len(orig) and swapped != orig
st = os.stat(REG)
fixed_ns = st.st_mtime_ns


def write_reg(text):
    with open(REG, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.utime(REG, ns=(fixed_ns, fixed_ns))
    memory.invalidate_cache()                    # exactly what _save_all does after a write


nodes0 = store.load(GROOT)[0]
# Prime the cache on the swapped state at a DIFFERENT stamp (T1), so even a key without the epoch
# builds a context for it; then flip back at the SAME T1 and size: only the epoch tells them apart.
fixed_ns += 1_000_000_000
write_reg(swapped)
stamp_a = memory.registry_stamp()
check("(precondition) the secret is not a secret yet, so it is shown",
      view.visible(nodes0[SECRET], "") not in (None, NOTE), view.visible(nodes0[SECRET], ""))
write_reg(orig)
check("(precondition) the stamp is unchanged by the in-process write", memory.registry_stamp() == stamp_a)
check("an in-process write that leaves the stamp unchanged is seen", view.visible(nodes0[SECRET], "") == NOTE,
      view.visible(nodes0[SECRET], ""))
backdate()

# ── (b)(c) rebuild interval, staleness once per window ──────────────────────────────────────
clear()
os.environ["SP_GRAPH_BUILD"] = "1"
os.environ["SP_GRAPH_REBUILD_MIN_S"] = "600"
check("config: the default window is 600 s", (os.environ.pop("SP_GRAPH_REBUILD_MIN_S"), config.rebuild_min_s())[1] == 600)
check("config: the default keep is 3", config.keep() == 3)
os.environ["SP_GRAPH_KEEP"] = "0"
check("config: keep is never below 2", config.keep() == 2)
os.environ.pop("SP_GRAPH_KEEP")
os.environ["SP_GRAPH_REBUILD_MIN_S"] = "600"

started = []
real_run = annotate._run_build
real_now = annotate._now
real_newest = annotate._newest_source_mtime
stat_calls = []
annotate._run_build = lambda: started.append(1)
annotate._newest_source_mtime = lambda: (stat_calls.append(1), real_newest())[1]
try:
    graph.build(REG)                              # a fresh generation, newer than the backdated sources
    base = time.monotonic() + 10_000
    annotate._now = lambda: base
    for _ in range(5):
        annotate.annotate_fact("x", CAT_FACT, "q", 2)
    check("staleness is computed once per window, not once per fact", len(stat_calls) == 1, len(stat_calls))
    annotate._now = lambda: base + 601
    annotate.annotate_fact("x", CAT_FACT, "q", 2)
    check("...and again when the window has passed", len(stat_calls) == 2, len(stat_calls))

    t = time.time() + 50
    os.utime(REG, (t, t))                         # the registry is now newer than the graph
    s0 = annotate._started
    annotate._now = lambda: base + 5_000
    annotate.annotate_fact("x", CAT_FACT, "q", 2)
    join_rebuilds()
    annotate._now = lambda: base + 5_100
    annotate.annotate_fact("x", CAT_FACT, "q", 2)
    join_rebuilds()
    check("one rebuild per window", annotate._started == s0 + 1, (s0, annotate._started))
    annotate._now = lambda: base + 5_700
    annotate.annotate_fact("x", CAT_FACT, "q", 2)
    join_rebuilds()
    check("...and another once the window has passed", annotate._started == s0 + 2, (s0, annotate._started))
    shutil.rmtree(GROOT)
    s1 = annotate._started
    annotate._now = lambda: base + 5_701
    annotate.annotate_fact("x", CAT_FACT, "q", 2)
    join_rebuilds()
    check("no generation at all is built at once, window or not", annotate._started == s1 + 1,
          (s1, annotate._started))
finally:
    annotate._run_build = real_run
    annotate._now = real_now
    annotate._newest_source_mtime = real_newest
    backdate()
clear()

# ── prune ───────────────────────────────────────────────────────────────────────────────────
shutil.rmtree(GROOT, ignore_errors=True)
built = []
for _ in range(5):
    built.append(graph.build(REG)["generation"])
    time.sleep(0.01)
left = sorted(n for n in os.listdir(GROOT) if n.startswith("gen-"))
check("build prunes to the newest 3 generations by default", len(left) == 3 and set(left) <= set(built), left)
cur = open(os.path.join(GROOT, "CURRENT"), encoding="utf-8").read().strip()
check("...and CURRENT names a survivor", cur == built[-1] and cur in left, (cur, left))
os.environ["SP_GRAPH_KEEP"] = "2"
graph.build(REG)
left = [n for n in os.listdir(GROOT) if n.startswith("gen-")]
check("SP_GRAPH_KEEP is honoured", len(left) == 2, left)
os.environ.pop("SP_GRAPH_KEEP")
for _ in range(3):
    graph.build(REG)
check("config: keep is floored at 2", (os.environ.update(SP_GRAPH_KEEP="0"), config.keep())[1] == 2)
os.environ.pop("SP_GRAPH_KEEP")
gens = sorted(n for n in os.listdir(GROOT) if n.startswith("gen-"))
oldest = gens[0]
with open(os.path.join(GROOT, "CURRENT"), "w", encoding="utf-8") as f:
    f.write(oldest)
store.prune(GROOT, 1)
check("prune never deletes the generation CURRENT names", os.path.isdir(os.path.join(GROOT, oldest)),
      sorted(os.listdir(GROOT)))
check("prune ignores what is not a generation", store.prune(GROOT, 1) is None
      and os.path.exists(os.path.join(GROOT, "CURRENT")))
graph.build(REG)

# an old generation whose directory mtime is bumped newest (a half-failed rmtree) is still pruned first
for _ in range(2):
    time.sleep(1.1)                                # names carry whole seconds
    graph.build(REG)
gens = sorted(n for n in os.listdir(GROOT) if n.startswith("gen-"))
old = gens[0]
os.utime(os.path.join(GROOT, old), (time.time() + 500, time.time() + 500))
store.prune(GROOT, len(gens) - 1)
check("an old generation with a bumped mtime is pruned first", not os.path.isdir(os.path.join(GROOT, old))
      and len([n for n in os.listdir(GROOT) if n.startswith("gen-")]) == len(gens) - 1, sorted(os.listdir(GROOT)))

# ── (d) serve ───────────────────────────────────────────────────────────────────────────────
base_prof = copy.deepcopy(serve.load_profile("companion"))
for bad in ("explicit,day", "", ["explicit", 3], {"a": 1}):
    p = copy.deepcopy(base_prof)
    p["graph"] = {"rules": bad}
    try:
        serve.build_env(p)
        ok = False
    except SystemExit as e:
        ok = "graph" in str(e) and "rules" in str(e)
    check("a non-list [graph].rules %r is rejected loudly" % (bad,), ok)
p = copy.deepcopy(base_prof)
p["graph"] = {"rules": ["explicit", "day"], "rebuild_min_s": 120, "keep": 5}
env = serve.build_env(p)
check("serve maps rebuild_min_s and keep",
      env.get("SP_GRAPH_REBUILD_MIN_S") == "120" and env.get("SP_GRAPH_KEEP") == "5"
      and env.get("SP_GRAPH_RULES") == "explicit,day")
p = copy.deepcopy(base_prof)
p["graph"] = {"annotate": True}
env = serve.build_env(p)
check("keys the table leaves out stay absent", "SP_GRAPH_REBUILD_MIN_S" not in env and "SP_GRAPH_KEEP" not in env)

finish("G-GRAPH-FOLLOW")
