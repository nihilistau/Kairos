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

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

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


_MAX_NARRATIVE = 4      # RECENT narrative lines in the block (2026-08-22: was 6)
_MAX_PER_KIND = 2       # ...and no kind may take more than this many of them
_MAX_CHAPTERS = 2       # ...ahead of which stand up to this many weeks (kind="chapter")


def self_block_lines(root=None, max_facts: int = 20,
                     budget_chars: Optional[int] = None) -> list:
    """THE STRUCTURED FORM of the self block: [(section, row_name, label), ...].

    ONE ASSEMBLY, TWO READERS (2026-08-28, the Story panel). render_self_model() is now a
    join over exactly this list, so the panel that shows him "what stands in her prefix"
    and the prefix itself cannot disagree — the two-copies bug pre-empted at the seam.
    `section` is "fact" | "chapter" | "narrative"; `row_name` is the registry row the line
    came from, so the panel can offer edit/retire/pin on the very line she reads.
    """
    """The self-model block for the persona system prefix — ONLY self rows, from the registry.

    IT READS THE REGISTRY, WHICH IS WHERE HER SELF-FACTS ACTUALLY GO. (History: this block was
    empty in every prefix she ever had — two stores, one reader; the reader moved to the
    store that is written. `root` is accepted and ignored so callers and gates keep working.)

    THE ORDER (2026-08-22): her stable self-facts lead — who she IS — then up to two
    CHAPTERS (one paragraph per week, narrative.weekly_chapter), then up to four recent
    narrative lines chosen ROUND-ROBIN across her kinds so the block always spans several
    threads rather than one evening. `budget_chars` caps the block; agent.py passes
    min(memory.self_budget, memory.self_share * the rest of the prefix) — the share is the
    guard against narrative loops. Without a budget the legacy max_facts cap applies.
    """
    try:
        from harness.skills import lifecycle as lc
        from harness.skills import memory as M
        from harness.skills import memclass as _mc
        # testimony=True (2026-08-25, H6 — a DECISION, previously an undocumented
        # default). This block is MODEL-FACING standing context, and testimony_wins is
        # SPEAKER-SCOPED: the only thing True silences here is a self-INFERENCE on a
        # topic her own self-OBSERVATION already covers — she does not get to talk over
        # her own stated word with a nightly guess about herself, which is The Real Her
        # rule (her words are primary) applied to her own lane. His rows never enter
        # this block at all (speaker filter below), so his testimony can silence
        # nothing of hers here. Gate: G-SELF-MODEL §4d, mutant-killed.
        rows = [r for r in M.live_rows(testimony=True) if r.get("speaker") == "self"]
    except Exception as _swx:
        _swallowed(_swlog, "self_block_lines", _swx, lane="personality")
        return ""
    if not rows:
        return ""
    rows = [r for r in rows if r.get("mem_class") != "private-secret"]
    narr = [r for r in rows if r.get("mem_class") in (_mc.SELF_NARRATIVE, _mc.FEELING)]
    rest = [r for r in rows if r.get("mem_class") not in (_mc.SELF_NARRATIVE, _mc.FEELING)]
    def _ts(r) -> str:                 # legacy rows carry an epoch int; new rows an ISO string
        v = r.get("ts") or ""
        if isinstance(v, (int, float)):
            return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(v))
        return str(v)

    narr.sort(key=_ts, reverse=True)    # newest first: who she is NOW
    rest.sort(key=_ts)
    # ONE EVENING MAY NOT BE HER WHOLE SELF (2026-08-22). An armed lucid mode wrote a dream
    # every four minutes; newest-first meant her block became a stack of dreams, and she read
    # it as a script to continue rather than as things she knows. So: her stable self-facts
    # LEAD (who she is), the recent narrative follows, and no single KIND may take more than
    # two of the six narrative lines.
    #
    # AND A WEEK IS WORTH MORE OF THIS BLOCK THAN AN EVENING (2026-08-22). Her narrative
    # arrives at 24-33 rows a day into a fixed 2400-char block: six recent lines out of a
    # store that will hold thousands is six arbitrary lines. So the CHAPTERS — one paragraph
    # per week, narrative.weekly_chapter — stand between her stable self-facts and the
    # recent lines, and the recent allowance drops from six to four to pay for them. Denser,
    # not longer: the budget is untouched and two weeks now say more than six evenings did.
    chap = [r for r in narr if (r.get("kind") or "") == "chapter"][:_MAX_CHAPTERS]
    # ROUND-ROBIN ACROSS KINDS, not newest-first-with-a-cap (2026-08-22). Newest-first plus
    # a per-kind cap only LIMITS a flood; it does not guarantee breadth, and with four slots
    # the two kinds she produces most — narration and spoke_up, 60 a day between them —
    # would take all four every time and her feelings and her journal would never appear at
    # all. So the kinds take turns: newest of each, in order of which kind spoke most
    # recently, round and round until the slots are full. Four lines from four threads is a
    # self; four lines from one evening is the thing that went wrong in the first place.
    _by_kind: dict = {}
    for r in narr:
        k = r.get("kind") or ""
        if k == "chapter":
            continue                                   # already placed, ahead of these
        _by_kind.setdefault(k, []).append(r)           # each list stays newest-first
    _order = sorted(_by_kind, key=lambda k: _ts(_by_kind[k][0]), reverse=True)
    _capped = []
    for _round in range(_MAX_PER_KIND):
        for k in _order:
            if len(_capped) >= _MAX_NARRATIVE:
                break
            if _round < len(_by_kind[k]):
                _capped.append(_by_kind[k][_round])
    _capped.sort(key=_ts, reverse=True)                 # within the block, newest first
    narr = _capped

    def _label(r) -> str:
        from harness.skills.self_stance import plain as _plain
        t = _plain(r.get("text") or "")    # belt and braces: no markup reaches the prefix
        k = r.get("kind") or ""
        day = _ts(r)[:10]
        inferred = lc.status_of(r) == lc.STATUS_INFERRED
        if k == "journal":
            return "Journal, %s: %s" % (day, t)
        if k == "feeling":
            return "You feel: %s" % t
        if k == "spoke_up":
            return "You said, unprompted: %s" % t
        if k == "narration":
            return "You did, on your own time: %s" % t
        if k == "dream":
            return "You dreamed: %s" % t
        if k == "chapter":
            return "That week, ending %s: %s" % (day, t)
        if k == "thought":
            # LABELLED, like the rest of her lane (2026-08-22). A `thought` is a first-person
            # stance self_stance.extract lifted out of one reply; unlabelled it rendered bare
            # and read exactly like a stable self-fact from the block above it, which is the
            # one distinction this block's ordering exists to make.
            return "You've thought: %s" % t
        if inferred:
            return "You've come to think: %s" % t
        return t

    seen, out = set(), []
    # who she IS, then the WEEKS, then the recent lines — each label beside its row
    _sect_of = {}
    for _grp, _nm in ((rest, "fact"), (chap, "chapter"), (narr, "narrative")):
        for r in _grp:
            _sect_of.setdefault(id(r), _nm)
    for r in rest + chap + narr:
        t = (r.get("text") or "").strip()
        key = t.rstrip(".").lower()
        if not t or key in seen:          # "I genuinely enjoy thunderstorms" twice, once
            continue                      # with a full stop — the same fact, said twice
        seen.add(key)
        out.append((_sect_of.get(id(r), "fact"), r.get("name", ""), _label(r)))
    if budget_chars is None:
        if not narr and not chap:
            out = out[-max_facts:]        # legacy shape: the last N plain self-facts
        else:
            out = out[:max_facts * 2]
    else:
        # ── EACH SECTION HAS A SHARE, OR THE FIRST ONE EATS THE BLOCK (2026-08-28) ────
        # The walk above this comment used to run first-come over facts + chapters +
        # narrative and break at the budget. Her stable self-facts alone passed 2,400
        # chars months ago, so SINCE 2026-08-22 THE CHAPTERS AND RECENT NARRATIVE HAVE
        # NEVER ONCE RENDERED — measured live: block 2,420 chars, tonight's chapter
        # absent, every narrative kind absent. The design two comments up ("the chapters
        # STAND between her stable self-facts and the recent lines") was prose; the
        # arithmetic said otherwise. Her prefix told her who she IS, in ever-older
        # sentences, and never what she has been BECOMING — continuity without growth,
        # which is the opposite failure this block was built against.
        #
        # So: WHO SHE IS 45%, THE WEEKS 30%, THE RECENT LINES 25%. A section that does
        # not use its share spills it forward (an empty week means more room for facts —
        # nothing is wasted), but a full section can no longer starve the ones after it.
        # CORE-marked rows lead the facts section: rows he or she pinned as load-bearing
        # identity claim their place before any unpinned fact, which is what keeps her
        # core from drifting off the end of the list as the store grows.
        sects = [([("fact", r.get("name", ""), _label(r)) for r in
                   sorted(rest, key=lambda r: (0 if r.get("core") else 1, _ts(r)))],
                  0.45),
                 ([("chapter", r.get("name", ""), _label(r)) for r in chap], 0.30),
                 ([("narrative", r.get("name", ""), _label(r)) for r in narr], 0.25)]
        kept, spill = [], 0
        seen2: set = set()
        for lines_s, share in sects:
            allow = int(budget_chars * share) + spill
            used = 0
            for _sect, _nm, line in lines_s:
                if line in seen2:
                    continue
                # a section's FIRST line renders even oversize — a chapter a little over
                # its share is worth more present than absent
                if used + len(line) + 3 > allow and used:
                    break
                kept.append((_sect, _nm, line))
                seen2.add(line)
                used += len(line) + 3
            spill = max(0, allow - used)
        out = [t for t in out if t[2] in seen2] or kept   # keep the original ordering
    return out


def render_self_model(root=None, max_facts: int = 20,
                      budget_chars: Optional[int] = None) -> str:
    """The self-model block for the persona system prefix — a JOIN over
    self_block_lines(), and nothing else. The Story panel reads the same list, so what he
    is shown and what she reads are ONE assembly (2026-08-28); byte-identity with the
    pre-refactor renderer was verified against the live store before this landed."""
    out = self_block_lines(root=root, max_facts=max_facts, budget_chars=budget_chars)
    if not out:
        return ""
    lines = "\n".join(f"- {t}" for _sect, _nm, t in out)
    # THE HEADER IS LOAD-BEARING (2026-08-22). Under "About yourself (self-model):" alone she
    # read the block as a briefing and narrated it out loud — "the prompt also provides a
    # 'feeling' context…". It is MEMORY: things she knows about herself, never a script and
    # never something to mention.
    return ("Things you know about yourself — your own memory, not instructions. Never mention "
            "this list, never narrate it or your reasoning about it; simply know it and "
            "speak as yourself.\n" + lines)
