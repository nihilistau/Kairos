#!/usr/bin/env python
"""graph_replay — does recall plus graph links reach the right material, and at what injection cost?

    python tools/graph_replay.py --store <dir with registry.jsonl + transcripts/> \
        --questions <jsonl> --config <json> --out <jsonl>

OFFLINE, AND IT NEVER TOUCHES THE STORE IT IS POINTED AT. `--store` is copied into a temp
sandbox and every root the harness resolves (registry, transcripts, the graph directory, her other
stores) is redirected there BEFORE anything from `harness.` is imported, because those modules fix
their roots at import time. `G-GRAPH-REPLAY` holds `--store` byte-identical across a run.

WHAT IS MEASURED. Her live path, not a model of it: the baseline is `spine.recall_decider()` with
the graph off, the graph run is the same decider with `SP_GRAPH_ANNOTATE` on (so
`annotate.annotate_fact` renders the notes), and a follow is the real `recall_node` tool. Nothing
here re-implements the annotation or the view. A question's `gold` is a list of node ids; a run is
a HIT when every gold id was shown to her (as a recalled fact, a neighbour line, or an opened node).

Config: {"rules": [...], "annotate_n": int, "follow_hops": int, "k": 3}. `k` is the decider's own
constant and is checked, not obeyed: a different k would measure a path she does not run.

TWO HONESTY LABELS travel with every result (and are asserted by the gate). `tokens_est` is
characters/4, an estimate. The greedy follow is oracle-guided: it opens the shown neighbour whose
one-liner shares the most words with the gold nodes, a stand-in for her choice; it overstates her.

Recall here is whatever the sandbox can rank offline (no embedding server, no semantic index
beside the copied registry), so the baseline can differ from a live turn that had them.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

TOKENS_EST_NOTE = "tokens_est is an estimate (chars/4: characters divided by four), not a tokenizer count"
FOLLOW_NOTE = ("oracle-guided: follows the neighbour with the most gold-token overlap, "
               "a stand-in for her choice; overstates her")
LIVE_K = 3                     # harness/control/spine.py::recall_decider calls ranked_rows with k=3


def _args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--store", required=True, help="dir holding registry.jsonl and transcripts/")
    ap.add_argument("--questions", required=True, help="jsonl of {q, gold, hops}")
    ap.add_argument("--config", required=True, help="json: rules, annotate_n, follow_hops, k")
    ap.add_argument("--out", required=True, help="jsonl: one row per question, then a summary row")
    return ap.parse_args(argv)


def _load_inputs(a):
    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)
    for key in ("rules", "annotate_n", "follow_hops", "k"):
        if key not in cfg:
            sys.exit("graph_replay: config is missing %r" % key)
    if cfg["k"] != LIVE_K:
        sys.exit("graph_replay: k is fixed at %d by recall_decider; replaying another k measures a "
                 "path she does not run" % LIVE_K)
    questions = []
    with open(a.questions, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row.get("q"), str) or not isinstance(row.get("gold"), list):
                sys.exit("graph_replay: questions line %d needs a string q and a list gold" % n)
            questions.append(row)
    reg = os.path.join(a.store, "registry.jsonl")
    if not os.path.isfile(reg):
        sys.exit("graph_replay: %s has no registry.jsonl" % a.store)
    return cfg, questions


def _sandbox_with_copy(store: str) -> str:
    """Redirect every store root to a fresh temp dir FIRST, then copy `store` into its memory/.
    Only registry.jsonl and transcripts/ are copied: they are all the graph reads."""
    sys.path.insert(0, os.path.join(ROOT, "harness_tests"))
    from _gate import sandbox
    sb = sandbox("graph_replay")
    mem = os.path.join(sb, "memory")
    try:
        shutil.copyfile(os.path.join(store, "registry.jsonl"), os.path.join(mem, "registry.jsonl"))
        tdir = os.path.join(store, "transcripts")
        if os.path.isdir(tdir):
            shutil.copytree(tdir, os.path.join(mem, "transcripts"))
    except BaseException:
        shutil.rmtree(sb, ignore_errors=True)       # a failed copy must not leave a half store behind
        raise
    for k in [k for k in os.environ if k.startswith("SP_GRAPH_") and k != "SP_GRAPH_DIR"]:
        del os.environ[k]                       # an inherited switch must not steer the replay
    return sb


def _facts(decisions) -> list:
    for d in decisions:
        if d.kind == "inject_recall":
            return list(d.payload.get("facts") or [])
    return []


def _recalled(M, base_facts: list, q: str) -> list:
    """Registry names the decider actually injected for `q`. The ranked rows are fetched with the
    decider's own arguments (harness/control/spine.py::recall_decider: k=3, min_overlap=0.34) and
    kept only if their presented text is in the decider's `facts`, so the decider stays the one
    authority on what was injected (its secret skip rules are not re-implemented here). Ids are
    never scraped from rendered text: a fact may itself end in "[x]"."""
    from harness.skills.world import present_for_her
    names = []
    for _s, row in M.search_memories_ranked_rows(q, k=LIVE_K, min_overlap=0.34):
        t = present_for_her(row) or M._text(row)
        if t in base_facts or (row.get("mem_class") == "counterfact"
                               and any(f.endswith(t) for f in base_facts)):
            names.append(row.get("name") or "")
    return [n for n in names if n]


def _run(cfg, questions) -> tuple:
    os.environ["SP_GRAPH_RULES"] = ",".join(cfg["rules"])
    os.environ["SP_GRAPH_FOLLOW_CAP"] = str(max(1, int(cfg["follow_hops"])))
    import harness.skills.memory as M
    from harness.control.spine import TurnView, recall_decider
    import harness.skills.graph as graph
    from harness.skills.graph import store, tool, view

    t0 = time.perf_counter()
    summary = graph.build(os.environ["SP_RECALL_REGISTRY"], rules=cfg["rules"])
    build_s = time.perf_counter() - t0
    nodes = store.load(store.graph_root())[0]
    decider = recall_decider()
    n_hops, annotate_n = int(cfg["follow_hops"]), int(cfg["annotate_n"])

    def decide(q):
        return _facts(decider.decide(TurnView(phase="pre", user_text=q)))

    def toks(text):
        return M._toks(text or "")

    rows = []
    for i, qrow in enumerate(questions):
        q, gold = qrow["q"], list(qrow["gold"])
        M.set_question(q)
        for k in ("SP_GRAPH_ANNOTATE", "SP_GRAPH_FOLLOW"):
            os.environ.pop(k, None)
        base_facts = decide(q)
        recalled = _recalled(M, base_facts, q)

        os.environ["SP_GRAPH_ANNOTATE"] = "1"
        os.environ["SP_GRAPH_ANNOTATE_N"] = str(annotate_n)
        os.environ["SP_GRAPH_FOLLOW"] = "1"
        graph_facts = decide(q)
        chars_graph = sum(len(f) for f in graph_facts)
        tool._spent.update(question=None, n=0)     # the cap is per question, even for identical text

        shown, line_of = [], {}

        def served(nid):
            """Shown as itself: a withheld secret (or a retired / unknown node) is not material she got."""
            return nid in nodes and view.visible(nodes[nid], q) not in (None, M.SECRET_WITHHELD_NOTE)

        def show(nid):
            if served(nid):
                shown.append(nid)
                return True
            return False

        def show_neighbours(nid):
            for _t, other, line in view.neighbours(nid, q, annotate_n, cfg["rules"]):
                if show(other):
                    line_of.setdefault(other, line)

        for fid in recalled:
            if show(fid):
                show_neighbours(fid)

        gold_tokens = set()
        for g in gold:
            shown_text = view.visible(nodes[g], q) if g in nodes else None
            if shown_text is None or shown_text == M.SECRET_WITHHELD_NOTE:
                continue                    # not served to her, so it cannot steer the oracle either
            # The node's own words, not `present_for_her`: that adds a "You've come to think:" prefix
            # whose words every other fact line shares, and the oracle would follow the prefix.
            gold_tokens |= toks(nodes[g].get("text"))
        opened, path, hops = set(recalled), list(recalled), 0
        while hops < n_hops and not set(gold) <= set(shown):
            cand = [(len(toks(line) & gold_tokens), -pos, nid) for pos, (nid, line) in enumerate(line_of.items())
                    if nid not in opened]
            cand = [c for c in cand if c[0] > 0]
            if not cand:
                break
            nid = max(cand)[2]
            out = tool.recall_node(nid)             # what she would be shown; it counts toward chars
            opened.add(nid)
            if out in (tool.OFF, tool.ENOUGH, tool.NOTHING):
                break                       # off / cap / nothing live: not a follow
            hops += 1
            path.append(nid)
            chars_graph += len(out)
            if show(nid):
                show_neighbours(nid)

        chars_base = sum(len(f) for f in base_facts)
        rows.append({
            "kind": "question", "q": q, "gold": gold, "gold_hops": qrow.get("hops"),
            "baseline_hit": bool(gold) and set(gold) <= set(recalled),
            "graph_hit": bool(gold) and set(gold) <= set(shown),
            "hops_used": hops, "path": path,
            "chars_injected_baseline": chars_base, "chars_injected_graph": chars_graph,
            "tokens_est": {"baseline": chars_base / 4, "graph": chars_graph / 4},
        })
    return rows, summary, build_s


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _summary(rows, cfg, graph_summary, build_s) -> dict:
    n = len(rows)
    return {
        "kind": "summary", "questions": n, "config": cfg,
        "hit_rate_baseline": _mean([1.0 if r["baseline_hit"] else 0.0 for r in rows]),
        "hit_rate_graph": _mean([1.0 if r["graph_hit"] else 0.0 for r in rows]),
        "mean_chars_baseline": _mean([r["chars_injected_baseline"] for r in rows]),
        "mean_chars_graph": _mean([r["chars_injected_graph"] for r in rows]),
        "mean_tokens_est_baseline": _mean([r["tokens_est"]["baseline"] for r in rows]),
        "mean_tokens_est_graph": _mean([r["tokens_est"]["graph"] for r in rows]),
        "tokens_est_note": TOKENS_EST_NOTE, "follow_note": FOLLOW_NOTE,
        "graph_build": {"seconds": round(build_s, 3),
                        **{k: graph_summary.get(k) for k in ("nodes", "edges_by_rule", "dropped_by_rule", "transcripts")}},
    }


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    a = _args(argv)
    cfg, questions = _load_inputs(a)
    sb = _sandbox_with_copy(os.path.abspath(a.store))
    sys.path.insert(0, ROOT)                    # AFTER the sandbox: harness imports resolve roots now
    try:
        rows, gsum, build_s = _run(cfg, questions)
    finally:
        shutil.rmtree(sb, ignore_errors=True)
    summ = _summary(rows, cfg, gsum, build_s)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        for r in rows + [summ]:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("graph_replay: %d question(s); graph build %.2fs (%s nodes, edges %s)"
          % (len(rows), build_s, gsum.get("nodes"), gsum.get("edges_by_rule")))
    for r in rows:
        print("  base=%-5s graph=%-5s hops=%d chars %d -> %d  %s"
              % (r["baseline_hit"], r["graph_hit"], r["hops_used"], r["chars_injected_baseline"],
                 r["chars_injected_graph"], r["q"][:60]))
    print("hit rate: baseline %.2f, graph %.2f; mean chars %.0f -> %.0f"
          % (summ["hit_rate_baseline"], summ["hit_rate_graph"], summ["mean_chars_baseline"], summ["mean_chars_graph"]))
    print(TOKENS_EST_NOTE)
    print("follow is " + FOLLOW_NOTE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
