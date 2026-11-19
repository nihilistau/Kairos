"""The graph's generation store: derived data, replaced whole, published by one atomic pointer.

LAYOUT. `<root>/gen-<YYYYmmddTHHMMSS>-<4 hex>/{nodes.jsonl, edges.jsonl, summary.json}` and
`<root>/CURRENT`, a one-line file holding the live generation's directory name. A build writes
the whole generation first and only then swaps the pointer (`CURRENT.<uuid>.tmp` + `os.replace`), so
a reader sees the old graph or the new one, never half of either, and a build that dies
leaves `CURRENT` where it was. `prune` (called by `graph.build` after a successful publish) keeps the newest few and always
the one CURRENT names; a build that fails prunes nothing.

`graph_root` is `SP_GRAPH_DIR` if set, else `graph/` beside the registry, the same "beside
the registry" resolution the transcripts use, so a gate's sandbox carries its own graph.

`load` caches on the CURRENT content (plus the root): the 2026-09-11 recall-seam lesson is that
a stamp is the cache key, not a re-read of every row per call. It returns None rather than
raising, because readers sit on turn paths.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from datetime import datetime
from typing import Optional

from harness.store_io import replace_atomic

_CACHE: dict = {}
_LOCK = threading.Lock()


def graph_root(registry: str = "") -> str:
    env = os.environ.get("SP_GRAPH_DIR", "")
    if env:
        return env
    reg = registry or os.environ.get("SP_RECALL_REGISTRY", "")
    return os.path.join(os.path.dirname(reg), "graph") if reg else ""


def _write_jsonl(path: str, rows: list) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def write_generation(root: str, nodes: list, edges: list, summary: dict) -> str:
    name = "gen-%s-%s" % (datetime.now().strftime("%Y%m%dT%H%M%S"), uuid.uuid4().hex[:4])
    gdir = os.path.join(root, name)
    summary["generation"] = name
    os.makedirs(gdir)
    try:
        _write_jsonl(os.path.join(gdir, "nodes.jsonl"), nodes)
        _write_jsonl(os.path.join(gdir, "edges.jsonl"), edges)
        with open(os.path.join(gdir, "summary.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(summary, f, ensure_ascii=False, sort_keys=True, indent=1)
        # A pointer temp name of its own: two builds sharing `CURRENT.tmp` could publish each
        # other's generation name, and the loser's cleanup then rmtree'd a published directory.
        tmp = os.path.join(root, "CURRENT.%s.tmp" % uuid.uuid4().hex)
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(name)
            replace_atomic(tmp, os.path.join(root, "CURRENT"))
        except BaseException as _e:     # cleans up, then re-raises: nothing is swallowed
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
    except BaseException as _e:         # same: the half-built generation goes, the error stays
        shutil.rmtree(gdir, ignore_errors=True)
        raise
    return name


def prune(root: str, keep: int) -> None:
    """Delete all but the newest `keep` generations, and never the one CURRENT names. Best
    effort: a directory that will not go is left for the next build. "Newest" is the timestamp in
    the NAME (a half-failed rmtree on Windows bumps an old directory's mtime, which must not
    make it look new), then directory mtime within the same second (the name's suffix is
    random), then the name.""" 
    try:
        with open(os.path.join(root, "CURRENT"), encoding="utf-8") as f:
            cur = f.read().strip()
        gens = sorted((n for n in os.listdir(root)
                       if n.startswith("gen-") and os.path.isdir(os.path.join(root, n))),
                      key=lambda n: (n[:19], os.stat(os.path.join(root, n)).st_mtime_ns, n))
    except OSError:
        return
    for name in gens[:max(0, len(gens) - max(1, keep))]:
        if name != cur:
            shutil.rmtree(os.path.join(root, name), ignore_errors=True)


def _read_jsonl(path: str) -> list:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def load(root: str) -> Optional[tuple]:
    """(nodes_by_id, edges, summary) of the current generation, or None when there is none
    (or it cannot be read; the failure is counted via `graph.dropped()`)."""
    if not root:
        # An empty root would resolve CURRENT against the cwd and load whatever graph lives there.
        from harness.skills.graph import note_dropped
        note_dropped()
        return None
    try:
        with open(os.path.join(root, "CURRENT"), encoding="utf-8") as f:
            cur = f.read().strip()
    except OSError:
        return None
    if not cur:
        return None
    key = (os.path.abspath(root), cur)
    with _LOCK:
        hit = _CACHE.get(key)
    if hit is not None:
        return hit
    gdir = os.path.join(root, cur)
    try:
        nodes = {n["id"]: n for n in _read_jsonl(os.path.join(gdir, "nodes.jsonl"))}
        edges = _read_jsonl(os.path.join(gdir, "edges.jsonl"))
        with open(os.path.join(gdir, "summary.json"), encoding="utf-8") as f:
            summary = json.load(f)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):   # TypeError/AttributeError: a line that is JSON but not an object
        from harness.skills.graph import note_dropped
        note_dropped()
        return None
    out = (nodes, edges, summary)
    with _LOCK:
        for k in [k for k in _CACHE if k[0] == key[0]]:
            del _CACHE[k]            # one live generation per root
        _CACHE[key] = out
    return out
