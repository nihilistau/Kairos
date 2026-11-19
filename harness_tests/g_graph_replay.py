"""G-GRAPH-REPLAY — the offline replay harness measures recall + graph links without touching a store
(memory-graph Task 7).

WHAT THIS HOLDS. `tools/graph_replay.py` copies `--store` (registry.jsonl + transcripts/) into a
sandbox, builds the graph there, and for each question runs her live recall decider with the graph
off (the baseline) and on (annotate), then up to `follow_hops` oracle-guided follows. The NUMBERS
it prints are measurements, not pass/fail; this gate holds the machinery:
  - the output parses, every declared field is on every question row, the summary echoes the
    config and carries the two honesty labels (tokens_est is chars/4, an estimate; the greedy
    follow is oracle-guided and overstates her);
  - `--store` is byte-identical afterwards (the harness must never write a store, and building the
    graph writes a directory beside the registry unless the roots are redirected first);
  - on the fixture, hand-computed: "what is my cat called" is a baseline hit; the second question
    needs the turn AFTER the minting turn, so it misses at baseline and at annotate, and is a graph
    hit only after exactly one follow; the third reaches nothing either way;
  - `tokens_est` is chars/4; no output carries the fixture's secret value.

  - a withheld secret as gold is never a hit, and a fact whose own text ends in "[x]" (added to the
    sandbox copy only) is recalled by its registry name, not by an id scraped out of its text.

MUTANTS (run 2026-11-03; each restored by text swap):
  (d) `served` counts the withheld note as shown -> "a withheld secret gold id is never a hit" goes red.
  (f) `served` put back on the baseline line -> "a secret the decider really injected is a baseline hit" goes red.
  (e) recalled ids scraped from the baseline text by a trailing-"[...]" regex -> "a fact ending in [x]
      is not mistaken for an id" goes red.
  (a) the tool points the registry at --store instead of the copy and drops SP_GRAPH_DIR
      -> "--store is byte-identical after the run" goes red.
  (b) tokens_est = chars/3 -> "tokens_est is chars/4" goes red.
  (c) follow_hops loop never runs -> "a question needing a follow is a graph hit after one hop" goes red.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
sandbox("g_graph_replay")
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

FX = os.path.join(HERE, "fixtures", "graph")
TOOL = os.path.join(ROOT, "tools", "graph_replay.py")
CAT = "ep_live_1767261600001"
CONFIG = {"rules": ["explicit", "sequence", "day", "minted_from"], "annotate_n": 2, "follow_hops": 2, "k": 3}
FIELDS = ("q", "baseline_hit", "graph_hit", "hops_used", "path", "chars_injected_baseline",
          "chars_injected_graph", "tokens_est")


def tree_hash(root):
    h = hashlib.sha256()
    for dp, dn, fn in os.walk(root):
        dn.sort()
        for n in sorted(fn):
            p = os.path.join(dp, n)
            h.update(os.path.relpath(p, root).encode())
            with open(p, "rb") as f:
                h.update(f.read())
    return h.hexdigest()


tmp = tempfile.mkdtemp(prefix="g_graph_replay_run_")
store = os.path.join(tmp, "store")
os.makedirs(store)
shutil.copyfile(os.path.join(FX, "registry.jsonl"), os.path.join(store, "registry.jsonl"))
shutil.copytree(os.path.join(FX, "transcripts"), os.path.join(store, "transcripts"))
# A fact whose own text ends in "[x]" exists only in this sandbox copy, never in the shared fixture.
TAG = "ep_live_1767261600099"
with open(os.path.join(store, "registry.jsonl"), "a", encoding="utf-8", newline="\n") as f:
    f.write(json.dumps({"name": TAG, "text": "Sam stamps his notebooks with a zebra label [x]", "speaker": "user",
                        "status": "live", "mem_class": "fact", "lifecycle": 0, "superseded_by": None,
                        "derived_from": [], "first_seen": "2026-01-02T09:30:00Z", "last_seen": "2026-01-02T09:30:00Z",
                        "ts": "2026-01-02T09:30:00Z", "kind": "fact", "src": "fixture"}) + "\n")
qfile = os.path.join(tmp, "questions.jsonl")
with open(os.path.join(FX, "questions.jsonl"), encoding="utf-8") as f:
    qtext = f.read()
with open(qfile, "w", encoding="utf-8", newline="\n") as f:
    f.write(qtext.rstrip("\n") + "\n" + json.dumps({"q": "which zebra label is on his notebooks", "gold": [TAG], "hops": 0}) + "\n")
cfg = os.path.join(tmp, "config.json")
with open(cfg, "w", encoding="utf-8") as f:
    json.dump(CONFIG, f)
out = os.path.join(tmp, "out.jsonl")
before = tree_hash(store)

env = {k: v for k, v in os.environ.items() if not k.startswith("SP_")}
r = subprocess.run([sys.executable, TOOL, "--store", store, "--questions", qfile,
                    "--config", cfg, "--out", out], capture_output=True, text=True, encoding="utf-8",
                   env=env, cwd=tmp, timeout=300)
check("the tool exits 0", r.returncode == 0, (r.returncode, r.stderr[-600:]))
check("--store is byte-identical after the run", tree_hash(store) == before)

rows = []
try:
    with open(out, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
except (OSError, ValueError) as e:
    check("the output parses as JSON lines", False, e)
qrows = [x for x in rows if x.get("kind") == "question"]
summ = [x for x in rows if x.get("kind") == "summary"]
check("one row per question and one summary row", len(qrows) == 5 and len(summ) == 1, len(rows))
check("every declared field is on every question row", qrows and all(k in x for x in qrows for k in FIELDS),
      [k for x in qrows for k in FIELDS if k not in x])
if len(qrows) == 5 and summ:
    s = summ[0]
    check("the summary echoes the config", s.get("config") == CONFIG, s.get("config"))
    check("the summary carries hit rates and mean chars and tokens both ways",
          all(k in s for k in ("hit_rate_baseline", "hit_rate_graph", "mean_chars_baseline", "mean_chars_graph",
                               "mean_tokens_est_baseline", "mean_tokens_est_graph")), sorted(s))
    check("tokens_est is labelled an estimate (chars/4)", "estimate" in s.get("tokens_est_note", "")
          and "chars/4" in s.get("tokens_est_note", ""), s.get("tokens_est_note"))
    check("the follow is labelled oracle-guided and as overstating her",
          "oracle-guided" in s.get("follow_note", "") and "overstates" in s.get("follow_note", ""), s.get("follow_note"))
    check("tokens_est is chars/4", all(x["tokens_est"] == {"baseline": x["chars_injected_baseline"] / 4,
                                                           "graph": x["chars_injected_graph"] / 4} for x in qrows),
          [x["tokens_est"] for x in qrows])
    q1, q2, q3, q4, q5 = qrows
    check("a plain fact question is a baseline hit", q1["baseline_hit"] is True and q1["graph_hit"] is True
          and q1["hops_used"] == 0, q1)
    check("a question needing a follow is a baseline miss", q2["baseline_hit"] is False, q2)
    check("a question needing a follow is a graph hit after one hop", q2["graph_hit"] is True
          and q2["hops_used"] == 1 and q2["path"][-1] == "t:2026-01-02:0", q2)
    check("the graph injects more than the baseline when it follows", q2["chars_injected_graph"] > q2["chars_injected_baseline"], q2)
    check("a question nothing answers is a miss both ways", q3["baseline_hit"] is False and q3["graph_hit"] is False, q3)
    # "what is the PIN" is a question the owner rule lets the decider answer, so the REAL baseline injects
    # the secret (a baseline hit: the baseline measures her recall as it is); the graph side counts only
    # what the view serves as itself, and for a secret that is the withheld note, so never a graph hit.
    check("a withheld secret gold id is never a hit", q4["graph_hit"] is False, q4)
    check("a secret the decider really injected is a baseline hit", q4["baseline_hit"] is True
          and q4["path"][:1] == ["ep_live_1767261600006"], q4)
    check("a fact ending in [x] is not mistaken for an id", q5["baseline_hit"] is True and q5["graph_hit"] is True
          and q5["path"][:1] == [TAG], q5)
blob = r.stdout + (open(out, encoding="utf-8").read() if os.path.exists(out) else "")
check("no output carries the fixture's secret value", "4417" not in blob)
check("stdout says what it measured", "oracle-guided" in r.stdout and "estimate" in r.stdout, r.stdout[-400:])

shutil.rmtree(tmp, ignore_errors=True)
finish("G-GRAPH-REPLAY")
