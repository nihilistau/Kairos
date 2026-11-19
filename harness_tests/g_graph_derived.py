"""G-GRAPH-DERIVED — the graph is derived data: built, replaced atomically, rebuilt from nothing
(memory-graph Task 3).

WHAT THIS HOLDS. `graph.build` reads the registry and day transcripts and writes ONLY under
the graph root, as a generation directory published by an atomic `CURRENT` pointer. So:
  - building never touches `registry.jsonl` or `transcripts/*` (byte-identical before/after);
  - deleting the whole graph root and rebuilding gives the same nodes and edges;
  - a build that dies half way leaves `CURRENT` on the previous generation, because the
    pointer is the LAST thing written, after nodes, edges and summary are all on disk;
  - the summary says whether the transcripts were read at all ("ok" / "absent" / "unreadable"),
    so a missing or unreadable directory is a field in the summary and not a graph that
    quietly has no turns;
  - an unknown rule name is a ValueError naming it (a CLI/build error; turn paths never call
    build).

MUTANT (run 2026-11-03): `write_generation` publishes `CURRENT` before the edges file ->
"a failed build leaves CURRENT on the previous generation" goes red.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
sb = sandbox("g_graph_derived")
os.environ.pop("SP_GRAPH_DIR", None)
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from harness.skills import graph  # noqa: E402
from harness.skills.graph import store  # noqa: E402
from harness.model import transcript  # noqa: E402

FX = os.path.join(HERE, "fixtures", "graph")
REG = os.path.join(sb, "memory", "registry.jsonl")
TDIR = os.path.join(sb, "memory", "transcripts")
shutil.copyfile(os.path.join(FX, "registry.jsonl"), REG)
shutil.copytree(os.path.join(FX, "transcripts"), TDIR)
# The app-event fixture too, so every rule has an edge to count (2026-11-08; the activity files
# staying byte-identical is G-GRAPH-ACTIVITY §5).
shutil.copytree(os.path.join(FX, "activity"), os.path.join(sb, "memory", "activity"))
GROOT = store.graph_root(REG)


def digest() -> dict:
    out = {}
    for base in (REG, TDIR):
        paths = [base] if os.path.isfile(base) else [os.path.join(base, n) for n in sorted(os.listdir(base))]
        for p in paths:
            with open(p, "rb") as f:
                out[p] = hashlib.sha256(f.read()).hexdigest()
    return out


def sets(root: str):
    nodes, edges, _ = store.load(root)
    return (sorted(nodes), sorted((e["from"], e["to"], e["type"], e["rule"]) for e in edges))


check("graph_root sits beside the registry", GROOT == os.path.join(os.path.dirname(REG), "graph"), GROOT)
os.environ["SP_GRAPH_DIR"] = os.path.join(sb, "elsewhere")
check("SP_GRAPH_DIR overrides the graph root", store.graph_root(REG) == os.environ["SP_GRAPH_DIR"])
os.environ.pop("SP_GRAPH_DIR")
check("load is None before any build", store.load(GROOT) is None)
_cwd = os.getcwd()
os.chdir(sb)
try:
    os.makedirs(os.path.join(sb, "gen-x"), exist_ok=True)
    with open(os.path.join(sb, "CURRENT"), "w", encoding="utf-8") as _f:
        _f.write("gen-x")
    _empty = store.load("")
finally:
    os.chdir(_cwd)
    os.remove(os.path.join(sb, "CURRENT"))
    shutil.rmtree(os.path.join(sb, "gen-x"), ignore_errors=True)
check("an empty root loads nothing (CURRENT is not resolved against the cwd)", _empty is None, _empty)

before = digest()
s1 = graph.build(REG)
check("registry and transcripts byte-identical after build", before == digest())
check("summary counts dropped edges", s1["dropped_by_rule"]["explicit"] == 1, s1["dropped_by_rule"])
check("summary names the generation, rule versions and a build time",
      bool(s1["generation"]) and s1["rules"] == {k: 1 for k in graph.RULES} and bool(s1["built_at"]))
check("summary counts nodes and edges per rule",
      s1["nodes"] > 0 and set(s1["edges_by_rule"]) == set(graph.RULES)
      and all(v > 0 for v in s1["edges_by_rule"].values()), s1["edges_by_rule"])
check("transcripts were read", s1["transcripts"] == "ok", s1.get("transcripts"))
loaded = store.load(GROOT)
check("load returns what build wrote", loaded[2]["generation"] == s1["generation"]
      and len(loaded[0]) == s1["nodes"] and len(loaded[1]) == sum(s1["edges_by_rule"].values()))
check("load is cached on CURRENT", store.load(GROOT) is loaded)
a = sets(GROOT)

shutil.rmtree(GROOT)
check("load is None once the graph is deleted", store.load(GROOT) is None)
s2 = graph.build(REG)
check("delete and rebuild gives the same graph", a == sets(GROOT))

s3 = graph.build(REG)
gens = [n for n in os.listdir(GROOT) if n.startswith("gen-")]
check("old generations are kept", len(gens) == 2 and s2["generation"] in gens and s3["generation"] in gens, gens)

# A crash after nodes.jsonl is written: patch the OWNER of the file writes.
_real = store._write_jsonl


def _boom(path, rows):
    if os.path.basename(path) == "edges.jsonl":
        raise OSError("disk full (gate)")
    return _real(path, rows)


store._write_jsonl = _boom
try:
    graph.build(REG)
    check("a failing build raises to its caller", False)
except OSError:
    check("a failing build raises to its caller", True)
finally:
    store._write_jsonl = _real
_cur = store.load(GROOT)
check("a failed build leaves CURRENT on the previous generation",
      _cur is not None and _cur[2]["generation"] == s3["generation"], "CURRENT unreadable" if _cur is None else "")
check("a failed build leaves no half-written generation behind",
      sorted(n for n in os.listdir(GROOT) if n.startswith("gen-")) == sorted(gens))

try:
    graph.build(REG, rules=["explicit", "nope"])
    check("an unknown rule is a ValueError naming it", False)
except ValueError as e:
    check("an unknown rule is a ValueError naming it", "nope" in str(e), str(e))
only = graph.build(REG, rules=["sequence"])
check("build honours a rule subset", list(only["edges_by_rule"]) == ["sequence"] and only["rules"] == {"sequence": 1})

check("dropped() is a count", isinstance(graph.dropped(), int))

# Transcripts: absent vs unreadable are distinct summary values, never a silent empty graph.
real_all_rows = transcript.all_rows
transcript.all_rows = lambda registry="", days=None: None
try:
    unreadable = graph.build(REG)
finally:
    transcript.all_rows = real_all_rows
check("an unreadable transcripts dir is reported", unreadable["transcripts"] == "unreadable",
      unreadable.get("transcripts"))

sb2 = os.path.join(sb, "bare")
os.makedirs(os.path.join(sb2, "memory"))
REG2 = os.path.join(sb2, "memory", "registry.jsonl")
shutil.copyfile(os.path.join(FX, "registry.jsonl"), REG2)
bare = graph.build(REG2)
check("a sandbox with no transcripts dir builds with transcripts == 'absent'",
      bare["transcripts"] == "absent" and bare["nodes"] > 0, bare.get("transcripts"))

env = dict(os.environ, SP_GRAPH_DIR=os.path.join(sb, "cli-graph"), SP_RECALL_REGISTRY=REG)
r = subprocess.run([sys.executable, "-m", "harness.skills.graph", "build"], cwd=ROOT, env=env,
                   capture_output=True, text=True, encoding="utf-8")
check("CLI prints the summary", r.returncode == 0 and '"generation"' in r.stdout, r.stderr[-300:])
try:
    cli = json.loads(r.stdout)
    check("CLI output is JSON and agrees with the store",
          store.load(env["SP_GRAPH_DIR"])[2]["generation"] == cli["generation"])
except ValueError:
    check("CLI output is JSON and agrees with the store", False, r.stdout[:200])

# A readable line that is JSON but not an object ([1,2]) raises TypeError/AttributeError, not
# ValueError; readers sit on turn paths and must return None and count it.
bad = os.path.join(sb, "bad-graph")
os.makedirs(os.path.join(bad, "gen-bad"))
for fn, body in (("nodes.jsonl", "[1,2]\n"), ("edges.jsonl", ""), ("summary.json", "{}")):
    with open(os.path.join(bad, "gen-bad", fn), "w", encoding="utf-8") as f:
        f.write(body)
with open(os.path.join(bad, "CURRENT"), "w", encoding="utf-8") as f:
    f.write("gen-bad")
d0 = graph.dropped()
try:
    got = store.load(bad)
    check("load returns None for a nodes line that is not an object, without raising", got is None, got)
except Exception as e:  # noqa: BLE001
    check("load returns None for a nodes line that is not an object, without raising", False, repr(e))
check("that unreadable generation is counted", graph.dropped() == d0 + 1, (d0, graph.dropped()))

# The pointer's temp name is unique per build: two builds sharing a fixed `CURRENT.tmp` could
# publish each other's generation. Record os.replace's source across two builds (patched on the
# module the store calls it through) and require distinct names, neither the fixed one.
_real_replace = os.replace
_srcs: list = []


def _rec_replace(src, dst, *a, **k):
    _srcs.append(os.path.basename(src))
    return _real_replace(src, dst, *a, **k)


os.replace = _rec_replace
try:
    graph.build(REG)
    graph.build(REG)
finally:
    os.replace = _real_replace
ptr = [n for n in _srcs if n.startswith("CURRENT")]
check("each build publishes CURRENT from its own temp name",
      len(ptr) == 2 and ptr[0] != ptr[1] and "CURRENT.tmp" not in ptr, ptr)
check("no pointer temp file is left behind", not [n for n in os.listdir(GROOT) if n.endswith(".tmp")])

finish("G-GRAPH-DERIVED")
