"""The live-only view: the ONLY way graph content reaches her.

The graph keeps retired facts and secrets, because it is derived data and "what did she
believe, and what replaced it" is the point of keeping them. Nothing it stores may be handed to
her as it stands. Every node she is shown goes through here, and this module gets its answers
from the memory package's own doors, never from the node:

  - LIVENESS AND TESTIMONY come from `M.live_rows(testimony=True)`, keyed by registry `name`. A
    fact whose name is not in that set (retired, tombstoned, or a covered inference that does
    not take the floor) is invisible. The node's own `retired` flag is not consulted: it is a
    snapshot from build time, and the registry has moved since.
  - SECRETS ARE NEVER SERVED. A live private-secret fact is `M.SECRET_WITHHELD_NOTE` whatever
    the question, and so is a turn that carries one: (a) the `minted_from` source of a live
    secret; (b) a turn holding >= 60% of its words; (c) a turn holding any KEY token of it, a
    salient token that contains a digit or appears in <= 2 live registry rows. (c) exists
    because the value alone is the secret: her reply "It is 4417, as you told me." after
    recall() served the PIN holds 1 of {sam, pin, 4417} and no minted_from edge reaches it,
    and on a 15-19 token secret quoting only the sensitive span is far under 60%. Withholding
    an innocent turn that shares a rare word costs a line; leaking costs the secret.
    Secrets reach her only through `recall()`, whose
    rule (`present.secret_withheld`) assumes the question already matched the record by ranked
    overlap; the graph reaches a node by adjacency, which never satisfies that, and every
    overlap test tried here leaked on some everyday question. `query` stays in the signatures
    for callers, but nothing secret-related reads it.
  - PRESENTATION is `world.present_for_her(row)`, the same grammar the standing block uses.
  - APP EVENTS (2026-11-08) are what he did in another app, never a claim he made, so they
    are labelled as such ("(in primer, open_page) Kookaburra") and pass the SAME secret test
    as a turn: a title holding a secret's key token or most of its words is the withheld
    note. Private events never become nodes (the activity reader drops them).

A reader on a turn path never raises: a failure is counted in `graph.dropped()` and the answer
is empty, so the turn proceeds without annotation.
"""
from __future__ import annotations

import re
import threading
from typing import Optional

import harness.skills.memory as M
from harness.skills import world
from harness.skills.graph import store
from harness.user import say as _say

ONE_LINER_MAX = 80
SYNTHETIC_LABEL = _say("(from a turn {he} never typed) ")

# Order neighbours are offered in; anything not named sorts last.
_RULE_ORDER = {"explicit": 0, "minted_from": 1, "sequence": 2, "day": 3, "activity": 4}
_SENTENCE_END = re.compile(r"(?<=[.!?])\s")


def _cut(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= ONE_LINER_MAX else text[:ONE_LINER_MAX - 1].rstrip() + "…"


def _line(node: dict, text: str) -> str:
    if node.get("kind") == "fact":
        return _cut(text)                       # a fact is already one statement
    if node.get("kind") == EVENT_KIND:
        return _cut(text)                       # a label and a title, one line already
    head = text[:len(SYNTHETIC_LABEL)] if text.startswith(SYNTHETIC_LABEL) else ""
    body = _SENTENCE_END.split(text[len(head):].strip(), 1)[0]
    return _cut(head + body)


TURN_KINDS = ("turn_user", "turn_her")
EVENT_KIND = "app_event"


def event_label(node: dict) -> str:
    """"(in <app>, <event>) " — what an app event is, before its title."""
    return "(in %s, %s) " % (node.get("app") or "an app", node.get("event") or "event")
SECRET_TURN_SHARE = 0.6          # a turn holding this share of a secret's words is carrying it
SECRET_KEY_MAX_DF = 2            # a secret's token in at most this many live rows is a key token


def _row_text(row: dict) -> str:
    return row.get("text") or row.get("topic") or ""


class _Ctx:
    """What one call needs from the registry, read ONCE: the live+testimony rows by name, the
    live private-secret rows among them, each secret's key tokens (digit-bearing, or in <= 2
    live rows), and the turns the graph says a secret was minted from."""

    def __init__(self, edges: list):
        rows = M.live_rows(testimony=True)
        self.live = {r.get("name"): r for r in rows if r.get("name")}
        self.secrets = {n: r for n, r in self.live.items() if (r.get("mem_class") or "") == "private-secret"}
        self.toks = {n: M._toks(_row_text(r)) for n, r in self.secrets.items()}
        self.keys: dict = {}
        if self.toks:
            df: dict = {}
            for r in rows:                      # every live row counts, nameless ones included
                for t in M._toks(_row_text(r)):
                    df[t] = df.get(t, 0) + 1
            self.keys = {n: {t for t in ts if any(c.isdigit() for c in t) or df.get(t, 0) <= SECRET_KEY_MAX_DF}
                         for n, ts in self.toks.items()}
        self.minted: dict = {}
        for e in edges:
            if e.get("type") == "minted_from" and e.get("from") in self.secrets:
                self.minted.setdefault(e["to"], []).append(e["from"])


# THE CONTEXT IS CACHED (Task 4 review). Building a `_Ctx` re-tokenises every live registry row
# (31 ms on her live store), and annotate asks once per recalled fact per turn. The key is the
# registry's stamp (the recall seam's own cache key since 2026-09-11, `rank.py::_idf_table`), the
# graph generation (the `minted` leg comes from its edges), and the `live_rows` door itself: a
# caller that swaps the door (a gate lending it a different registry) must not be served the
# context built through the real one. The memory package's `cache_epoch()` is in it too: every
# in-process registry write calls `invalidate_cache()`, which is the PRIMARY signal; the stamp is
# the fallback for a writer that is not this process (an equal-size rewrite inside one mtime tick
# defeats the stamp, and here that would keep a stale SECRET SET).
_CTX_CACHE: dict = {"key": None, "ctx": None}
_CTX_LOCK = threading.Lock()


def _ctx_for(edges: list, generation) -> "_Ctx":
    key = (M.registry_stamp(), M.cache_epoch(), generation, M.live_rows)
    with _CTX_LOCK:
        if _CTX_CACHE["key"] == key:
            return _CTX_CACHE["ctx"]
    ctx = _Ctx(edges)
    with _CTX_LOCK:
        _CTX_CACHE["key"], _CTX_CACHE["ctx"] = key, ctx
    return ctx


def _visible(node: dict, query: str, ctx: "_Ctx") -> Optional[str]:
    kind = node.get("kind")
    if kind == "fact":
        row = ctx.live.get(node.get("id"))
        if row is None:
            return None
        if (row.get("mem_class") or "") == "private-secret":
            return M.SECRET_WITHHELD_NOTE
        return world.present_for_her(row)
    if kind not in TURN_KINDS and kind != EVENT_KIND:
        return None                              # fail closed on a kind this door does not know
    text = node.get("text") or ""
    carried = set(ctx.minted.get(node.get("id"), ()))
    if ctx.toks:
        tt = M._toks(text)
        carried |= {n for n, t in ctx.toks.items() if t and len(t & tt) / len(t) >= SECRET_TURN_SHARE}
        carried |= {n for n, k in ctx.keys.items() if k & tt}
    if carried:
        return M.SECRET_WITHHELD_NOTE
    if kind == EVENT_KIND:
        return event_label(node) + text
    return SYNTHETIC_LABEL + text if node.get("synthetic") else text


def _edges() -> tuple:
    got = store.load(store.graph_root())
    return (got[1], got[2].get("generation")) if got else ([], None)


def visible(node: dict, query: str) -> Optional[str]:
    """The text she may see for this node, or None. Facts: None unless live (with testimony),
    the withheld note for a secret (always), else `present_for_her`.
    Turns: their text, a synthetic one labelled; a turn that carries a live secret (minted a
    secret, holds most of its words, or holds any key token of it) is the withheld note, as
    the secret is.
    Never raises: a failure is counted and the node is not shown."""
    try:
        return _visible(node, query, _ctx_for(*_edges()))
    except Exception:  # noqa: BLE001 - a reader on a turn path never raises
        _dropped()
        return None


def one_liner(node: dict) -> str:
    """The node in <= 80 chars, as she would be shown it (so a withheld secret is its note,
    a retired fact is empty). The query is empty: a secret is always the note."""
    text = visible(node, "")
    return "" if text is None else _line(node, text)


def _dropped() -> None:
    import harness.skills.graph as graph
    graph.note_dropped()


def neighbours(node_id: str, query: str, n: int, rules: Optional[list] = None) -> list:
    """Up to `n` visible neighbours as (edge_type, id, one_liner), over edges in either
    direction. Explicit edges first, then minted_from by weight, then sequence, then day."""
    try:
        if n <= 0:
            return []
        got = store.load(store.graph_root())
        if got is None:
            return []
        nodes, edges, summary = got
        if node_id not in nodes:
            return []
        cand = []
        for i, e in enumerate(edges):
            if rules is not None and e["rule"] not in rules:
                continue
            other = e["to"] if e["from"] == node_id else e["from"] if e["to"] == node_id else None
            if other is None or other == node_id:
                continue
            cand.append((_RULE_ORDER.get(e["rule"], 9), -float(e.get("weight") or 0.0), i, e["type"], other))
        cand.sort()
        ctx: Optional[_Ctx] = None           # one registry read per call, and only if a candidate turns up
        out, seen = [], set()
        for _r, _w, _i, etype, other in cand:
            if other in seen or other not in nodes:
                continue
            node = nodes[other]
            if ctx is None:
                ctx = _ctx_for(edges, summary.get("generation"))
            text = _visible(node, query, ctx)
            if text is None:
                continue
            seen.add(other)
            out.append((etype, other, _line(node, text)))
            if len(out) >= n:
                break
        return out
    except Exception:  # noqa: BLE001 - a reader on a turn path never raises
        _dropped()
        return []
