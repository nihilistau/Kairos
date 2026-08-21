"""PF-B1 — fact ownership + the agent self-model, stored as OKF concepts.

`mem_owner` is an axis ORTHOGONAL to `mem_class` (ADR-004): who the fact is ABOUT.
  - self  : a fact about the AGENT (its capabilities/identity) — the self-model.
  - user  : a fact about the OPERATOR.
The owner is set at CAPTURE by the SOURCE (the agent asserting a self-fact vs the user stating a
user-fact), NOT inferred from text — so it needs no classifier. Facts are written as content-
addressed OKF concepts with `mem_owner` frontmatter, so the same store-merge (engine) + curator
(DF-B6) machinery serves/curates them. `render_self_model()` produces the self-model block for the
persona system prefix (PF-B2 will fold it into load_agent_system).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

HARNESS_ROOT = Path(__file__).resolve().parents[2]
SELF_TIER = HARNESS_ROOT / "memory-okf-self"   # the self-model + user-facts store (owner-tagged)


def _resolve_root(root=None) -> Path:
    """Root precedence: explicit arg > SP_SELF_MODEL_ROOT env > default SELF_TIER."""
    return Path(root) if root else Path(os.environ.get("SP_SELF_MODEL_ROOT") or SELF_TIER)

# CONSUMED from THE class registry (2026-07-14, INVARIANT-ROADMAP.md Tier 1.2). The
# local copy had drifted from the 2026-07-12 engine fix (fact/episodic-event -> system,
# not recite: a remembered thing is CONTEXT, not a command). self-fact stays recite by
# doctrine — she does not paraphrase who she is. G-MEMCLASS convicts any new copy.
from harness.skills import memclass as _mc

_CLASS_DELIVERY = _mc.delivery_map()


def _addr(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class SelfModelStore:
    """OKF-concept store for owner-tagged facts (self-model + user-facts)."""

    def __init__(self, root=None):
        self.full = _resolve_root(root) / "full"
        self.full.mkdir(parents=True, exist_ok=True)

    def _write(self, statement: str, owner: str, mem_class: str) -> str:
        addr = _addr(statement)
        deliv = _CLASS_DELIVERY.get(mem_class, "recite")
        fm = ["---", "type: mem-concept", f"title: {owner}-fact", f"addr: {addr}",
              f"mem_class: {mem_class}", f"mem_owner: {owner}", f"mem_delivery: {deliv}",
              f"ts: {int(time.time())}", "---", "", statement, ""]
        (self.full / f"{addr}.md").write_text("\n".join(fm), encoding="utf-8")
        return addr

    def remember_self(self, statement: str, mem_class: str = "self-fact") -> str:
        """Record a fact ABOUT THE AGENT (the self-model)."""
        return self._write(statement, "self", mem_class)

    def remember_user(self, statement: str, mem_class: str = "fact") -> str:
        """Record a fact ABOUT THE USER."""
        return self._write(statement, "user", mem_class)

    def _iter(self):
        for p in sorted(self.full.glob("*.md")):
            raw = p.read_text(encoding="utf-8")
            owner = mem_class = None
            body = []
            fences = 0
            for line in raw.splitlines():
                if line.strip() == "---":
                    fences += 1; continue
                if fences >= 2:
                    body.append(line)
                elif line.strip().startswith("mem_owner:"):
                    owner = line.split(":", 1)[1].strip()
                elif line.strip().startswith("mem_class:"):
                    mem_class = line.split(":", 1)[1].strip()
            yield {"addr": p.stem, "owner": owner, "class": mem_class,
                   "text": "\n".join(body).strip()}

    def facts(self, owner: Optional[str] = None) -> List[Dict]:
        return [f for f in self._iter() if owner is None or f["owner"] == owner]

    def self_facts(self) -> List[Dict]:
        return self.facts("self")

    def user_facts(self) -> List[Dict]:
        return self.facts("user")


def remember_self(statement: str, mem_class: str = "self-fact", root=None) -> str:
    """Store a fact about her. ONE DOOR — this writes to the registry, same as the
    `remember_about_self` tool.

    Both were exposed to her as tools, writing to two different stores, and only the
    store nobody read was reachable from here. Whichever she reached for, the fact had to
    land in the same place, or the tool she happened to pick decided whether the memory
    survived. Delegating rather than deleting keeps every existing caller
    (harness/personality/tools.py, the PERSONALITY_TOOLS pack) working unchanged.

    `root` is honoured only when a caller explicitly passes one — the gates that point
    this at a temp directory still get the old isolated behaviour.
    """
    if root is not None:
        return SelfModelStore(root).remember_self(statement, mem_class)
    try:
        from harness.skills.memory import remember_about_self
        return remember_about_self(statement)
    except Exception:
        return SelfModelStore(root).remember_self(statement, mem_class)


def remember_user(statement: str, mem_class: str = "fact", root=None) -> str:
    return SelfModelStore(root).remember_user(statement, mem_class)


def render_self_model(root=None, max_facts: int = 20) -> str:
    """The self-model block for the persona system prefix — ONLY self-facts.

    IT READS THE REGISTRY, WHICH IS WHERE HER SELF-FACTS ACTUALLY GO.

    This block was EMPTY IN EVERY PREFIX SHE HAS EVER HAD, and the reason is the bug this
    repository is named after. There were two stores and one reader:

        remember_about_self()  (harness/skills/memory.py — THE TOOL SHE IS OFFERED)
            -> set_author("self") -> remember(...) -> var/memory/registry.jsonl
        render_self_model()    (here, THE ONLY CONSUMER)
            -> SelfModelStore -> memory-okf-self/

    `memory-okf-self/full/` has been an empty directory since 10 July. Meanwhile twelve
    rows in the registry carry `speaker == "self"` — she HAS been remembering things about
    herself for three weeks, into a store nothing reads. The operator's report was "nothing
    is really sticking except what we put in her .md files", and he was exactly right.

    So the reader moves to the store that is written, rather than the writer moving to the
    store that is read. The registry is the right authority: it is the recall store, it
    carries lifecycle (a retired self-fact must not be recited), it is backed up, and it is
    the one both halves of the memory system already agree on. `memory-okf-self` becomes
    vestigial rather than a second copy of the truth.

    `root` is accepted and ignored, so existing callers and gates keep working.
    """
    try:
        from harness.skills import lifecycle as lc
        from harness.skills import memory as M
        rows = [r for r in M.live_rows() if r.get("speaker") == "self"]
    except Exception:
        return ""
    if not rows:
        return ""
    # newest last — the same order a person tells you about themselves
    rows.sort(key=lambda r: r.get("ts") or 0)
    seen, facts = set(), []
    for r in rows:
        # NEVER AMBIENT: this block rides the persist-KV prefix — the same surface
        # world._compose guards with "the one absolute here". It had no filter, so a
        # self-lane credential (classify() runs on remember_about_self writes too)
        # would have rendered into every prompt she was ever sent.
        if r.get("mem_class") == "private-secret":
            continue
        t = (r.get("text") or "").strip()
        k = t.rstrip(".").lower()
        if not t or k in seen:          # "I genuinely enjoy thunderstorms" twice, once
            continue                    # with a full stop — the same fact, said twice
        seen.add(k)
        # Her conclusion about herself is not a bare assertion — status exists so a
        # guess never reads as ground truth, and this renderer ignored it.
        if lc.status_of(r) == lc.STATUS_INFERRED:
            t = f"I've come to think: {t}"
        facts.append(t)
    facts = facts[-max_facts:]
    if not facts:
        return ""
    lines = "\n".join(f"- {t}" for t in facts)
    return f"About yourself (self-model):\n{lines}"
