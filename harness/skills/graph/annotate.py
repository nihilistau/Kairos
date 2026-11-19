"""annotate: a recalled fact, decorated with its graph id and a few neighbours.

`harness/control/spine.py::recall_decider` calls `annotate_fact` per recalled fact when
`SP_GRAPH_ANNOTATE` is on, and the memory-graph replay (Task 7) calls the SAME function, so what
the replay measures is what the turn does. Format: `"<text> [<id>]"`, then one line per
neighbour, `"\n  ↳ <edge_type> [<id>] <one_liner>"`. Every neighbour comes through
`graph.view`, which withholds retired facts and never serves a secret; nothing here filters.

NEVER BLOCKS, NEVER RAISES. With no generation the text comes back unchanged and the miss is
counted (`graph.dropped()`). With `build` on and the current generation older than the registry
or the newest transcript, ONE daemon thread rebuilds (a module flag under a lock stops a second)
and this turn annotates from the generation it already has. Two floors keep a busy day from
rebuilding on every turn (each transcript append makes the graph stale): the staleness check
itself runs at most once per `SP_GRAPH_REBUILD_MIN_S` window per generation, and a rebuild
starts at most once per window once a generation exists (none at all is built at once).
"""
from __future__ import annotations

import calendar
import os
import threading
import time

import harness.skills.memory as M
from harness.model import transcript
from harness.skills.graph import config, store, view

_LOCK = threading.Lock()
_running = False              # a rebuild thread is alive; guarded by _LOCK
_started = 0                  # rebuild threads ever started (the gate reads it)
_last_kick = None             # `_now()` when the last rebuild thread started; guarded by _LOCK
_STALE: dict = {"gen": None, "at": 0.0, "stale": False}   # the last staleness answer; guarded by _LOCK
_now = time.monotonic         # the clock the windows use; a gate swaps it here, in the owner


def _run_build() -> None:
    """The rebuild itself. Module-level so a gate can stub it and count starts instead of
    racing a real build."""
    import harness.skills.graph as graph
    graph.build(rules=config.switches()["rules"])


def _worker() -> None:
    global _running
    try:
        _run_build()
    except Exception:  # noqa: BLE001 - a background rebuild never raises into anything
        import harness.skills.graph as graph
        graph.note_dropped()
    finally:
        with _LOCK:
            _running = False


def _kick() -> None:
    global _running, _started, _last_kick
    with _LOCK:
        if _running:
            return
        _running = True
        _started += 1
        _last_kick = _now()
    try:
        threading.Thread(target=_worker, name="graph-rebuild", daemon=True).start()
    except Exception:  # noqa: BLE001
        with _LOCK:
            _running = False
        raise


def _newest_source_mtime() -> float:
    """Latest mtime of the registry and the transcript day files; 0.0 when unreadable."""
    newest = 0.0
    reg = M.registry_stamp()[0]
    paths = [reg] if reg else []
    d = transcript._dir()
    if d and os.path.isdir(d):
        paths += [os.path.join(d, n) for n in os.listdir(d) if n.endswith(".jsonl")]
    for p in paths:
        try:
            newest = max(newest, os.path.getmtime(p))
        except OSError:
            pass
    return newest


def _stale(summary: dict | None) -> bool:
    if summary is None:
        return True
    try:
        built = calendar.timegm(time.strptime(summary["built_at"], "%Y-%m-%dT%H:%M:%SZ"))
    except (KeyError, ValueError, TypeError):
        return True
    return _newest_source_mtime() > built


def _refresh_if_stale(got) -> None:
    summary = got[2] if got else None
    if summary is None:
        _kick()                                  # nothing to serve: not churn, build it now
        return
    window, now, gen = config.rebuild_min_s(), _now(), summary.get("generation")
    with _LOCK:
        cached = (window > 0 and _STALE["gen"] == gen and now - _STALE["at"] < window)
        stale = _STALE["stale"] if cached else None
    if stale is None:                            # the stat of every day file: once per window
        stale = _stale(summary)
        with _LOCK:
            _STALE.update(gen=gen, at=now, stale=stale)
    if not stale:
        return
    with _LOCK:
        recent = _last_kick is not None and now - _last_kick < window
    if not recent:
        _kick()


def neighbour_line(etype: str, node_id: str, line: str) -> str:
    """One neighbour as annotate and `recall_node` both print it. The single copy of the format."""
    return "\n  ↳ %s [%s] %s" % (etype, node_id, line)


def neighbour_block(node_id: str, query: str, n: int, rules: list | None = None) -> str:
    """Up to `n` visible neighbours of `node_id`, each as `neighbour_line`; "" if none."""
    return "".join(neighbour_line(*nb) for nb in view.neighbours(node_id, query, n, rules))


def annotate_fact(text: str, row_name: str, query: str, n: int) -> str:
    """`text` with its node id and up to `n` neighbours, or `text` unchanged."""
    try:
        got = store.load(store.graph_root())
        if config.switches()["build"]:
            _refresh_if_stale(got)
        if got is None:
            import harness.skills.graph as graph
            graph.note_dropped()
            return text
        if not row_name or row_name not in got[0]:
            return text                        # newer than the generation: nothing to say yet
        return "%s [%s]%s" % (text, row_name, neighbour_block(row_name, query, n, config.switches()["rules"]))
    except Exception:  # noqa: BLE001 - annotation is decoration; the turn proceeds without it
        import harness.skills.graph as graph
        graph.note_dropped()
        return text
