"""The HARNESS SPINE — ADR-007: one decide → execute → verify pipeline for the agent.

The engine grew a Spine (ADR-002, engine spine.rs): an immutable LatentView folded through
priority-ordered Deciders into a discrete LatentDecision, applied by an Executor the deciders
can't touch. The harness had the same logic SCATTERED: persona tags parsed in one interceptor,
hygiene inline in the agency tick, recall ad-hoc. This module is the harness-side mirror —
typed, priority-folded, receipted — plus the ADR-006 stage the engine version doesn't have yet:
a VERIFIER that checks the executor's own claim of success (verify-before-accept as law).

Shape (deliberately tiny — a fold, not a framework):

    TurnView (immutable facts about the turn)
      → [Decider.decide(view) -> list[Decision]]   (pure; CANNOT touch the world)
      → Executor.execute(decision) -> result        (the only side-effecting stage)
      → Verifier.verify(decision, result) -> bool   (objective post-check; a failed verify
                                                     marks the receipt VERIFY_FAIL, never hides it)
      → SpineReceipt (auditable record of every decision/result/verdict)

Everything is additive: callers opt in per-seam. No existing path changes behavior unless it
routes through run_spine.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ADR-008: the RECEIPT RING — every spine decision this process makes, observable.
# run_spine appends automatically; /v1/spine (gateway) + the operator panel read it.
_RECEIPT_RING: deque = deque(maxlen=200)
_SEQ = 0                      # monotone id per ring entry (the persistence watermark rides it)
_PERSISTED_SEQ = 0            # highest seq already flushed to the telemetry-okf store


def get_recent_receipts(k: int = 50) -> List[Dict[str, Any]]:
    """The last k spine receipts as JSON-able dicts (newest last)."""
    items = list(_RECEIPT_RING)[-k:]
    return [{"ts": ts, "kind": r.kind, "decider": r.decider, "ok": r.ok,
             "verified": r.verified, "result": r.result, "ms": round(r.ms, 1)}
            for _seq, ts, r in items]


def persist_receipts(root: str = "") -> int:
    """ADR-005 flywheel: flush unpersisted ring receipts into the DURABLE telemetry-okf store
    (content-addressed + idempotent via the existing TelemetrySink — reused, not rebuilt).
    Each receipt becomes a `kind: "spine"` record beside the engine's turn/decision records,
    so the flywheel's training/audit corpus includes what the harness DECIDED and whether the
    verify held. Returns the number of NEW records sunk. Receipts survive restarts; re-flushes
    dedup by content hash. (Spine results carry operational text + registry-tier facts only —
    the private-secret lane never routes through spine payloads; the ADR-005 redaction law is
    upheld by construction, and the sink never un-redacts regardless.)"""
    global _PERSISTED_SEQ
    import json as _json
    import os as _os
    root = root or _os.environ.get("SP_TELEMETRY_OKF_ROOT") or _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))), "memory-okf-telemetry")
    try:
        from harness.telemetry.sink import TelemetrySink
        sink = TelemetrySink(root)
    except Exception as exc:
        logger.warning("[spine] telemetry sink unavailable: %s", exc)
        return 0
    new = 0
    hi = _PERSISTED_SEQ
    for seq, ts, r in list(_RECEIPT_RING):
        if seq <= _PERSISTED_SEQ:
            continue
        rec = _json.dumps({"kind": "spine", "ts": ts, "decider": r.decider, "decision": r.kind,
                           "ok": r.ok, "verified": r.verified, "result": r.result,
                           "ms": round(r.ms, 1)}, sort_keys=True)
        _, is_new = sink.sink(rec)
        if is_new:
            new += 1
        hi = max(hi, seq)
    _PERSISTED_SEQ = hi
    if new:
        logger.info("[spine] persisted %d receipt(s) -> %s", new, root)
    return new


# ──── the data ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class TurnView:
    """Immutable facts a Decider may read. Frozen: deciders CANNOT mutate the turn."""
    phase: str                      # "pre" | "post" | "tick"
    user_text: str = ""             # last user message (pre/post)
    reply: str = ""                 # the model's reply (post)
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Decision:
    """A discrete, symbolic decision (ADR-002: the boundary object). kind routes to an executor."""
    kind: str
    payload: Dict[str, Any] = field(default_factory=dict)
    decider: str = ""
    priority: int = 50


@dataclass
class SpineReceipt:
    """One decision's auditable outcome."""
    kind: str
    decider: str
    ok: bool
    verified: Optional[bool]        # None = no verifier registered for this kind
    result: str
    ms: float


class Decider:
    """Pure decision stage. Subclass or wrap a function; MUST NOT side-effect."""
    name = "decider"
    priority = 50

    def decide(self, view: TurnView) -> List[Decision]:  # pragma: no cover - interface
        return []


class FnDecider(Decider):
    def __init__(self, name: str, fn: Callable[[TurnView], List[Decision]], priority: int = 50):
        self.name, self._fn, self.priority = name, fn, priority

    def decide(self, view: TurnView) -> List[Decision]:
        return self._fn(view) or []


# ──── the fold ────────────────────────────────────────────────────────────────
def run_spine(
    view: TurnView,
    deciders: List[Decider],
    executors: Dict[str, Callable[[Decision], str]],
    verifiers: Optional[Dict[str, Callable[[Decision, str], bool]]] = None,
    decided: Optional[List[Decision]] = None,
) -> List[SpineReceipt]:
    """Fold the view through the deciders (priority order), execute each decision, verify each
    result. Never raises — a failing stage becomes an honest receipt, not a crash.

    `decided`: decisions the caller already collected — executed and receipted WITHOUT
    re-folding. run_pre_turn used to fold its deciders itself for the return value and
    then call here, which folded THE SAME deciders AGAIN: two full ranked registry scans
    per armed-recall turn (measured 2× 3.8 ms and growing with the store), and — the
    correctness half — the decisions the caller ACTED ON came from the first fold while
    the receipts described the second. One evaluation; the receipt describes the
    decision that ran."""
    verifiers = verifiers or {}
    receipts: List[SpineReceipt] = []
    decisions: List[Decision] = list(decided) if decided is not None else []
    for d in sorted(deciders, key=lambda d: d.priority) if decided is None else []:
        try:
            for dec in d.decide(view):
                dec.decider = dec.decider or d.name
                dec.priority = d.priority
                decisions.append(dec)
        except Exception as exc:
            logger.warning("[spine] decider %s raised: %s", d.name, exc)
            receipts.append(SpineReceipt(kind="(decide)", decider=d.name, ok=False,
                                         verified=None, result=f"decider error: {exc}", ms=0.0))
    for dec in decisions:
        t0 = time.time()
        ex = executors.get(dec.kind)
        if ex is None:
            receipts.append(SpineReceipt(kind=dec.kind, decider=dec.decider, ok=False,
                                         verified=None, result="no executor", ms=0.0))
            continue
        try:
            result = str(ex(dec))
            ok = True
        except Exception as exc:
            result, ok = f"executor error: {exc}", False
        verified: Optional[bool] = None
        vf = verifiers.get(dec.kind)
        if vf is not None and ok:
            try:
                verified = bool(vf(dec, result))
            except Exception as exc:
                verified = False
                result += f" [verifier error: {exc}]"
            if verified is False:
                logger.warning("[spine] VERIFY_FAIL %s/%s: %s", dec.decider, dec.kind, result[:120])
        receipts.append(SpineReceipt(kind=dec.kind, decider=dec.decider, ok=ok,
                                     verified=verified, result=result[:400],
                                     ms=(time.time() - t0) * 1000.0))
    global _SEQ
    now = time.time()
    for r in receipts:
        _SEQ += 1
        _RECEIPT_RING.append((_SEQ, now, r))
    return receipts


# ──── the stock deciders / executors / verifiers (the seams we already own) ────
# THE DECIDER ORDER IS POLICY, COMMITTED AS DATA (Tier 2, INVARIANT-ROADMAP.md).
# Lower runs first. toolset before recall — pick the tier, then decide the injection —
# is a decision, not an accident of integers scattered over four constructors.
# G-LANE-TABLE pins this dict and asserts every constructor consumes it.
PRIORITIES = {"toolset": 10, "recall": 20, "persona_tags": 30, "hygiene": 40}


def authority_lane(authority_pref: str, auto_recall: bool, want_recall: bool,
                   looks_q: bool):
    """WHICH RECALL AUTHORITY RUNS THIS TURN — the gateway's lane policy as a pure
    function (Tier 2; it lived inline in app.py's stream generator). Returns
    (auto_recall, want_recall, event) with event in {None, 'spine', 'L5'}.

    The rules, in committed order (each bought with a live incident):
      1. QONLY: spine recall only on turns that ASK something — greetings/acks were
         surfacing junk episodes ("hi there!" x3).
      2. SPINE AUTHORITY: profile-selected; refuses the client's auto_recall
         passthrough (the daemon-L5 delivery re-prefills + clears the committed
         cache — the live "minutes then [aborted]" pattern).
      3. ONE AUTHORITY: free composition of both is REFUTED on the metal
         ("favorite color?" -> "Human blood is green"). If the daemon's recall is
         armed, spine auto-disarms.
    THEOREM the gate holds over all 16 cells: never both authorities on one turn."""
    event = None
    if want_recall and not looks_q:
        want_recall = False
    if authority_pref == "spine" and auto_recall:
        auto_recall = False
        event = "spine"
    if auto_recall and want_recall:
        want_recall = False
        event = "L5"
    return auto_recall, want_recall, event


def persona_tag_decider() -> Decider:
    """POST-turn: if the reply carries a personality/wardrobe mark, decide a persona_shift.

    THE TEST IS THE INTERCEPTOR'S OWN, not a copy of it. This held a private regex over
    `MOOD|VOICE|TRAIT` while the executor also acts on `[WEAR:]` and `[SHOW:]`, so a reply
    that only changed her clothes decided nothing and reached no executor — she changed and
    the room did not. Whoever owns the recognisers owns the question."""
    def fn(view: TurnView) -> List[Decision]:
        from harness.personality.interceptor import carries_marks
        if view.phase != "post" or not carries_marks(view.reply or ""):
            return []
        return [Decision(kind="persona_shift", payload={"reply": view.reply})]
    return FnDecider("persona_tags", fn, priority=PRIORITIES["persona_tags"])


def hygiene_decider() -> Decider:
    """TICK: if the registry's health VERDICT says so, decide a compaction.
    Tier 2 conversion: this used to sniff 'NEEDS COMPACTION' out of the human-readable
    report string — branching on a paragraph, the src-trap in a lab coat. It consumes
    the enum now (memory.registry_status); the report rides along for the receipt."""
    def fn(view: TurnView) -> List[Decision]:
        if view.phase != "tick":
            return []
        from harness.skills.memory import registry_status, verify_registry
        if registry_status() == "needs-compaction":
            return [Decision(kind="compact_registry", payload={"report": verify_registry()})]
        return []
    return FnDecider("hygiene", fn, priority=PRIORITIES["hygiene"])


def recall_decider(min_overlap: float = 0.34) -> Decider:
    """PRE-turn: if stored facts strongly match the user's message, decide a context injection
    (the harness-side text-in-context recall; the engine's L5 path stays authoritative when on)."""
    def fn(view: TurnView) -> List[Decision]:
        if view.phase != "pre" or not view.user_text:
            return []
        from harness.skills.memory import (search_memories_ranked_rows, attr_absent,
                                           DECLINE_MSG, _text)
        hits = search_memories_ranked_rows(view.user_text, k=3, min_overlap=min_overlap)
        if not hits:
            return []
        # ── MEM-OKF per-entry policy dispatch (P1b-2b; G-MEMPOLICY-V3 doctrine).
        # REGISTERED DIVERGENCE (2026-08-19): harness/skills/memclass.py declares
        # itself THE class→delivery registry ("one registry, everyone consumes") and
        # this decider — the one recall authority that actually runs — branches
        # inline instead: `self-fact` (declared recite) and `same-template` (declared
        # systemecho) get plain-note delivery here. Converting this branch to consume
        # the registry would CHANGE live recall delivery unmeasured, so it is written
        # down instead. ARMING CONDITION: a paired live run comparing the declared
        # deliveries against today's plain-note behaviour, then one consumer.
        # The harness is the ONE recall authority post-rehoming, so it must honor
        # the per-entry classes the engine dispatch honored:
        #   private-secret + absent attr  -> ZERO-INFERENCE fixed decline (the
        #       turn never reaches the model; confab/leak impossible)
        #   private-secret + present attr -> recite (fact enters the note)
        #   counterfact                   -> authoritative override framing
        #   persona / untagged            -> plain note (today's behavior)
        _top_score, top = hits[0]
        if top.get("mem_class") == "private-secret" and attr_absent(view.user_text, _text(top)):
            return [Decision(kind="decline_recall", payload={"message": DECLINE_MSG})]
        facts = []
        for _s, row in hits:
            t = _text(row)
            mc = row.get("mem_class", "")
            if mc == "private-secret" and attr_absent(view.user_text, t):
                continue  # never surface a secret's text for an attribute it lacks
            # ── THE OWNERSHIP TANGLE, PER-TURN LANE (field transcript 2026-07-29) ────
            # This appended the RAW fact text. The row — which knows whose sentence it
            # is — was right here and thrown away. Receipt: he asked "are you male or
            # female?" and recall handed her ["I am male"], HIS sentence in HIS first
            # person with no owner on it, and the turn came back confused. The standing
            # world block was taught this grammar in 3eaae5a; this lane was not, so the
            # invariant held in one of two paths and therefore in neither.
            #
            # Present by OWNER, through the SAME function the world block uses:
            # his facts read as his, her conclusions read as hers. The secret filter and
            # the counterfact framing above/below are unchanged and still run on the
            # stored text — presentation is the last step, never the gate.
            from harness.skills.world import present_for_her
            t = present_for_her(row) or t
            if mc == "counterfact":
                t = ("Fact on record (authoritative for this conversation, "
                     "overrides prior knowledge): " + t)
            facts.append(t)
        if not facts:
            return []
        return [Decision(kind="inject_recall", payload={"facts": facts})]
    return FnDecider("recall", fn, priority=PRIORITIES["recall"])


def toolset_decider() -> Decider:
    """PRE-turn (ADR-008): pick WHICH tool tier the turn advertises. The banked rule is a 12B
    picks reliably from ≤6 tools — this decider makes those six the RIGHT six for the turn:
    coding words → the coding set; memory words → the memory set (+extras); else → core.
    Deterministic keyword routing (no model call, no latency): the tiers are coarse on purpose —
    a wrong pick degrades to load_tools discovery, never to a hard failure."""
    coding_kw = ("code", "file", "edit", "fix", "bug", "test", "pytest", "function", "script",
                 "refactor", "compile", "build", "implement", "write a", "debug", "error", "diff")
    memory_kw = ("remember", "forget", "memory", "memories", "recall", "know about me",
                 "what do you know", "where did you learn", "provenance", "stored")

    def fn(view: TurnView) -> List[Decision]:
        if view.phase != "pre" or not view.user_text:
            return []
        low = view.user_text.lower()
        tier = "core"
        if any(k in low for k in coding_kw):
            tier = "coding"
        elif any(k in low for k in memory_kw):
            tier = "memory"
        if tier == "core":
            return []                      # default set — no decision needed (null floor)
        return [Decision(kind="select_toolset", payload={"tier": tier})]
    return FnDecider("toolset", fn, priority=PRIORITIES["toolset"])


def toolset_for(tier: str):
    """Resolve a toolset tier to (core_specs, extra_specs) for run_with_tools/agent streams."""
    from harness.toolcore.tools import ToolSpec
    if tier == "coding":
        from harness.skills.builtin.coding import (read_file, write_file, edit_file,
                                                   search, run_tests, run_command)
        core = [ToolSpec.from_callable(f) for f in
                (read_file, write_file, edit_file, search, run_tests, run_command)]
    elif tier == "memory":
        from harness.skills.memory import MEMORY_TOOLS, MEMORY_TOOLS_EXTRA
        core = [ToolSpec.from_callable(f) for f in (MEMORY_TOOLS + MEMORY_TOOLS_EXTRA[:2])]
    else:
        return None, None                  # caller keeps its defaults
    from harness.agent import all_tools
    core_names = {t.name for t in core}
    extra = [t for t in all_tools() if t.name not in core_names]
    return core, extra


def stock_executors() -> Dict[str, Callable[[Decision], str]]:
    def ex_persona(dec: Decision) -> str:
        from harness.personality.interceptor import apply_personality_tags
        # THE LIVE POST-TURN PATH. act=True — this is the reply she just said, so the
        # wardrobe marks in it are performed here. The curator replays history through the
        # same function with act off; see interceptor.apply_personality_tags.
        _, state = apply_personality_tags(dec.payload.get("reply", ""), act=True)
        return "persona state now: " + "; ".join(f"{k}={v}" for k, v in state.items() if v)

    def ex_compact(dec: Decision) -> str:
        from harness.skills.memory import compact_registry
        return compact_registry()

    def ex_inject(dec: Decision) -> str:
        # The caller reads the decision's payload to build the turn; executing it is a no-op
        # marker (the injection happens in the prompt assembly, which the caller owns).
        return f"recall context ready: {len(dec.payload.get('facts', []))} fact(s)"

    def ex_toolset(dec: Decision) -> str:
        return f"toolset tier: {dec.payload.get('tier', 'core')}"

    return {"persona_shift": ex_persona, "compact_registry": ex_compact,
            "inject_recall": ex_inject, "select_toolset": ex_toolset}


def stock_verifiers() -> Dict[str, Callable[[Decision, str], bool]]:
    """ADR-006 law: the executor's claim is CHECKED, not trusted."""
    def vf_persona(dec: Decision, result: str) -> bool:
        # Re-read persona.md and confirm the tagged mood/voice actually landed.
        #
        # AGAINST THE EXECUTOR'S OWN DERIVATION (2026-08-19). This compared the RAW
        # capture (moods[-1]) to the CLEANED write, so every spelling the interceptor
        # deliberately repairs — [MOOD::tender] (x8 in one day), [MOOD:wistful;
        # naughty] (x7), [MOOD-wistful] — wrote correctly and then FAILED verification,
        # and the failed verify suppressed the live persona chip event. The consumer
        # branched on a value the producer cannot produce (TRAPS §1), inside the layer
        # whose whole doctrine is verify-before-accept. expected_mood/expected_voice
        # ARE the executor's derivation; there is nothing left to disagree about.
        import re
        from harness.personality.persona_file import parse_persona
        from harness.personality.interceptor import (_persona_path, _MOOD, _VOICE,
                                                     _split_crammed, expected_mood,
                                                     expected_voice)
        try:
            from pathlib import Path
            _, state = parse_persona(Path(_persona_path()).read_text(encoding="utf-8"))
        except Exception:
            return False
        reply = _split_crammed(dec.payload.get("reply", ""))
        moods = _MOOD.findall(reply)
        if moods:
            want = expected_mood(moods[-1])
            if want and state.get("mood", "").strip() != want:
                return False
        voices = _VOICE.findall(reply)
        if voices and state.get("voice", "").strip() != expected_voice(voices[-1]):
            return False
        return True

    def vf_compact(dec: Decision, result: str) -> bool:
        # The ENUM, not the paragraph. hygiene_decider's docstring records converting the
        # DECIDER away from sniffing 'NEEDS COMPACTION' out of the report string — and the
        # verifier six lines down kept doing exactly that. Same law, second consumer.
        from harness.skills.memory import registry_status
        return registry_status() != "needs-compaction"

    return {"persona_shift": vf_persona, "compact_registry": vf_compact}


def run_pre_turn(user_text: str, *, recall: bool = False, toolset: bool = False):
    """The gateway's pre-turn spine (ADR-008). Returns (receipts, decisions) — the caller reads
    the decisions' payloads (recall facts / toolset tier) to assemble the turn; the spine only
    DECIDES + receipts. Flags select which deciders arm (both default-off at the call site)."""
    deciders: List[Decider] = []
    if toolset:
        deciders.append(toolset_decider())
    if recall:
        deciders.append(recall_decider())
    view = TurnView(phase="pre", user_text=user_text)
    decisions: List[Decision] = []
    for d in sorted(deciders, key=lambda d: d.priority):
        try:
            for dec in d.decide(view):
                dec.decider = dec.decider or d.name
                dec.priority = d.priority
                decisions.append(dec)
        except Exception as exc:
            logger.warning("[spine] pre-turn decider %s raised: %s", d.name, exc)
    # ONE fold. run_spine used to re-fold the same deciders (2× the ranked registry
    # scan per armed turn), and its receipts described a DIFFERENT evaluation from the
    # decisions returned to the caller — see run_spine's `decided` docstring.
    receipts = run_spine(view, deciders, stock_executors(), stock_verifiers(),
                         decided=decisions)
    return receipts, decisions


def run_post_turn(user_text: str, reply: str) -> List[SpineReceipt]:
    """The gateway's post-turn spine: persona tags (extensible)."""
    view = TurnView(phase="post", user_text=user_text, reply=reply)
    return run_spine(view, [persona_tag_decider()], stock_executors(), stock_verifiers())


def run_tick() -> List[SpineReceipt]:
    """The KAIROS tick spine: hygiene (extensible)."""
    view = TurnView(phase="tick")
    return run_spine(view, [hygiene_decider()], stock_executors(), stock_verifiers())
