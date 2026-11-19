"""recall_node: the follow tool. One hop along the memory graph, by id.

REGISTERED UNCONDITIONALLY (`agent.all_tools`, extra tier). Her system prompt is a cached
prefix; a tool that appeared and vanished with a switch would change token 0 and cost a cold
prefill each time it flipped. So the tool is always there and the switch is read at CALL time:
off answers "following is off".

Every word it returns comes through `graph.view` (`visible`, and `annotate.neighbour_block`,
which goes through `view.neighbours`), never from the node. A secret's id, and a turn that
carries one, are the withheld note; retired and unknown ids are "nothing live under that id".
The cap counts successful follows per question (`memory.current_question()`); a miss is free,
so it cannot be used to burn her budget, and a garbage id is not an error.
"""
from __future__ import annotations

import threading

import harness.skills.memory as M
from harness.skills.graph import annotate, config, store, view

OFF = "following is off"
ENOUGH = "that's enough following for this turn"
NOTHING = "nothing live under that id"

_LOCK = threading.Lock()
_spent = {"question": None, "n": 0}          # follows this question has used


def recall_node(node_id: str) -> str:
    """Open a memory by its [id]; shows what it links to. Pass an ID shown in square brackets in a memory note; you get that entry and the IDs it links to, one hop per call.

    The FIRST PHYSICAL LINE is the tool's whole description (`ToolSpec` keeps only the first
    line of the docstring, harness/toolcore/tools.py), so it is one complete line and only these
    notes wrap. Her cached prefix shows just the gist (`_gist` cuts at 54 characters, so the
    opening sentence must stay exactly as it is); G-GRAPH-FOLLOW holds both."""
    try:
        sw = config.switches()
        if not sw["follow"]:
            return OFF
        q = M.current_question()
        with _LOCK:
            if _spent["question"] != q:
                _spent["question"], _spent["n"] = q, 0
            if _spent["n"] >= sw["follow_cap"]:
                return ENOUGH
        nid = node_id.strip() if isinstance(node_id, str) else ""
        got = store.load(store.graph_root()) if nid else None
        node = got[0].get(nid) if got else None
        text = view.visible(node, q) if node is not None else None
        if text is None:
            return NOTHING
        with _LOCK:
            if _spent["question"] == q:
                _spent["n"] += 1
        return "[%s] %s%s" % (nid, text, annotate.neighbour_block(nid, q, sw["annotate_n"], sw["rules"]))
    except Exception:  # noqa: BLE001 - a tool on a turn path answers, it does not raise
        import harness.skills.graph as graph
        graph.note_dropped()
        return NOTHING


GRAPH_TOOLS = [recall_node]
