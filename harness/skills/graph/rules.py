"""Edge rules: small, versioned functions from nodes to candidate edges.

A rule EMITS candidates and does not check that both ends exist; `apply` is the one place
that drops an edge whose endpoint is not a node, and counts it per rule. That split is the
invariant ("an edge is written only when both ends are nodes") and it is why a dangling
`superseded_by` shows up as `dropped["explicit"] == 1` instead of vanishing. A rule signals
"I know there is nothing to point at" by emitting `to=None`.

Each edge is `{"from", "to", "type", "rule", "rule_version", "weight"}`. Bump a rule's
`version` when its semantics change, so stored edges say which reading produced them.

  explicit     supersedes (new -> old) from `superseded_by`; derived_from (distillate -> support)
  sequence     next between consecutive turns of a day file; answer_to (her turn -> nearest
               earlier user turn of that file)
  day          next_day (first turn -> next existing day's first turn); same_day (fact ->
               first turn of its first_seen day). Linear on purpose: all-pairs same_day is O(n^2).
  minted_from  fact -> the timed user turn in the 10 minutes before first_seen sharing the most
               words with it; weight = overlap / len(fact tokens), kept only at >= 0.3. Untimed
               and synthetic (injected, not his) turns are never candidates.
               Measured hits on the real store: 67 of 2339 facts (2026-11-03; 7252 nodes).
  activity     (2026-11-08) app events from `harness/model/activity.py`: `next` between consecutive
               events of one app-day file; `during` from an event to the nearest timed turn (his
               or hers) within ACTIVITY_WINDOW_S either side, weight = 1 - |dt| / window; and
               `same_day` from every event to the first turn of its day. Untimed events get
               `next` and `same_day` only. The other rules see TURNS only: `sequence` and `day`
               were written when every non-fact node was a turn, so they filter on TURN_KINDS
               and an app event can never become her `answer_to` or his `next`.
"""
from __future__ import annotations

from typing import Callable, Iterable, NamedTuple

import harness.skills.memory as M

MINT_WINDOW_S = 10 * 60
MINT_MIN_WEIGHT = 0.3
ACTIVITY_WINDOW_S = 10 * 60
TURN_KINDS = ("turn_user", "turn_her")


class Rule(NamedTuple):
    name: str
    version: int
    fn: Callable[[list, dict], Iterable[dict]]


def _edge(rule: str, version: int, frm, to, typ: str, weight: float = 1.0) -> dict:
    return {"from": frm, "to": to, "type": typ, "rule": rule,
            "rule_version": version, "weight": weight}


def _turns_by_day(nodes: list) -> dict:
    days: dict = {}
    for n in nodes:
        if n["kind"] in TURN_KINDS:
            days.setdefault(n["day"], []).append(n)
    return days


def _explicit(nodes, by_id):
    for n in nodes:
        if n["kind"] != "fact":
            continue
        if n.get("superseded_by"):
            yield _edge("explicit", 1, n["superseded_by"], n["id"], "supersedes")
        for src in n.get("derived_from") or []:
            yield _edge("explicit", 1, n["id"], src, "derived_from")


def _sequence(nodes, by_id):
    for turns in _turns_by_day(nodes).values():
        last_user = None
        for prev, cur in zip([None] + turns, turns):
            if prev is not None:
                yield _edge("sequence", 1, prev["id"], cur["id"], "next")
            if cur["kind"] == "turn_user":
                last_user = cur
            elif last_user is not None:
                yield _edge("sequence", 1, cur["id"], last_user["id"], "answer_to")


def _day(nodes, by_id):
    days = _turns_by_day(nodes)
    firsts = {d: t[0]["id"] for d, t in days.items()}
    order = sorted(firsts)
    for a, b in zip(order, order[1:]):
        yield _edge("day", 1, firsts[a], firsts[b], "next_day")
    for n in nodes:
        if n["kind"] == "fact":
            yield _edge("day", 1, n["id"], firsts.get(n["day"]), "same_day")


def _minted_from(nodes, by_id):
    users = [n for n in nodes if n["kind"] == "turn_user"
             and n["at"] is not None and not n.get("synthetic")]
    toks = {n["id"]: M._toks(n["text"]) for n in users}
    for f in nodes:
        if f["kind"] != "fact" or f["at"] is None:
            continue
        ft = M._toks(f["text"])
        if not ft:
            continue
        best, best_w = None, 0.0
        for t in users:
            if not 0 <= f["at"] - t["at"] <= MINT_WINDOW_S:
                continue
            w = len(ft & toks[t["id"]]) / len(ft)
            if w > best_w or (w == best_w and best is not None and t["at"] > best["at"]):
                best, best_w = t, w
        if best is not None and best_w >= MINT_MIN_WEIGHT:
            yield _edge("minted_from", 1, f["id"], best["id"], "minted_from", best_w)


def _activity(nodes, by_id):
    events = [n for n in nodes if n["kind"] == "app_event"]
    if not events:
        return
    days = _turns_by_day(nodes)
    firsts = {d: t[0]["id"] for d, t in days.items()}
    timed = sorted((t["at"], t["id"]) for ts in days.values() for t in ts if t["at"] is not None)
    by_file: dict = {}
    for ev in events:
        by_file.setdefault((ev["app"], ev["day"]), []).append(ev)
    for evs in by_file.values():
        for a, b in zip(evs, evs[1:]):
            yield _edge("activity", 1, a["id"], b["id"], "next")
    for ev in events:
        yield _edge("activity", 1, ev["id"], firsts.get(ev["day"]), "same_day")
        if ev["at"] is None:
            continue
        best, best_dt = None, None
        for at, tid in timed:
            dt = abs(at - ev["at"])
            if dt <= ACTIVITY_WINDOW_S and (best_dt is None or dt < best_dt):
                best, best_dt = tid, dt
        if best is not None:
            yield _edge("activity", 1, ev["id"], best, "during", round(1.0 - best_dt / ACTIVITY_WINDOW_S, 4))


RULES = {r.name: r for r in (
    Rule("explicit", 1, _explicit),
    Rule("sequence", 1, _sequence),
    Rule("day", 1, _day),
    Rule("minted_from", 1, _minted_from),
    Rule("activity", 1, _activity),
)}


def apply(nodes: list, names: list) -> tuple:
    """(edges, dropped_by_rule). Unknown rule names raise KeyError: a typo in the config
    must not quietly build a graph without that rule."""
    by_id = {n["id"]: n for n in nodes}
    edges, dropped, seen = [], {}, set()
    for name in names:
        rule = RULES[name]
        dropped.setdefault(name, 0)
        for e in rule.fn(nodes, by_id):
            if e["from"] not in by_id or e["to"] not in by_id:
                dropped[name] += 1
                continue
            key = (e["from"], e["to"], e["type"], e["rule"])
            if key not in seen:
                seen.add(key)
                edges.append(e)
    return edges, dropped
