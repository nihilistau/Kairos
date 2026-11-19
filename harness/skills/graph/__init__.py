"""The memory graph's door — a derived view over her fact registry and day transcripts.

The graph never writes `registry.jsonl`, `transcripts/*.jsonl`, `activity/**` or `speech.jsonl`; everything
here is recomputable from them, and `build` writes only under the graph root (see `store`).
Reader paths must never raise into a turn: a failure they swallow is counted with
`note_dropped()` and surfaces as `dropped()`.
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

from harness.skills.graph import config, nodes, rules, store          # noqa: F401
from harness.skills.graph.nodes import collect               # noqa: F401
from harness.skills.graph.rules import RULES, apply          # noqa: F401

DEFAULT_RULES = ["explicit", "sequence", "day", "minted_from", "activity"]

_DROPPED = 0
_DROPPED_LOCK = threading.Lock()


def note_dropped(n: int = 1) -> None:
    global _DROPPED
    with _DROPPED_LOCK:
        _DROPPED += n


def dropped() -> int:
    """Failures swallowed by reader paths since the process started."""
    return _DROPPED


def build(registry: str = "", rules: list | None = None) -> dict:
    """Collect nodes, apply the rules, publish a new generation, return its summary.

    Raises ValueError for an unknown rule name and lets disk errors through: building is a CLI
    / scheduled act, never a turn path, and a build that fails must say so. The previous
    generation stays current either way.
    """
    names = list(DEFAULT_RULES if rules is None else rules)
    unknown = [n for n in names if n not in RULES]
    if unknown:
        raise ValueError("unknown graph rule(s): %s (known: %s)" % (", ".join(unknown), ", ".join(RULES)))
    state = nodes.transcripts_state(registry)
    ns = nodes.collect(registry)
    es, dropped_by_rule = apply(ns, names)
    by_rule = {n: 0 for n in names}
    for e in es:
        by_rule[e["rule"]] += 1
    from harness.model import activity as _activity
    summary = {"nodes": len(ns), "edges_by_rule": by_rule, "dropped_by_rule": dropped_by_rule,
               "rules": {n: RULES[n].version for n in names}, "transcripts": state,
               "app_events": sum(1 for n in ns if n["kind"] == "app_event"),
               "app_events_private_skipped": _activity.private_count(registry),
               "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    root = store.graph_root(registry)
    if not root:
        raise ValueError("no graph root: pass a registry path or set SP_GRAPH_DIR / SP_RECALL_REGISTRY")
    os.makedirs(root, exist_ok=True)
    store.write_generation(root, ns, es, summary)
    store.prune(root, config.keep())
    return summary


def neighbours(node_id: str, query: str, n: int, rules: list | None = None) -> list:
    """(edge_type, id, one_liner) of up to `n` neighbours she may see; see `view`."""
    from harness.skills.graph import view
    return view.neighbours(node_id, query, n, rules)
