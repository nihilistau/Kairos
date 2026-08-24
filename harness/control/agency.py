"""The agency loop -- the model maintains its own memory autonomously.

Composes ephemeral tool calling (``harness.toolcore.tools``) + the memory tools
(``harness.skills.memory``) into a maintenance ROUND: the model is shown its
current memory and the curation tools and decides FOR ITSELF whether to forget
redundant/stale facts or consolidate them. Run between turns or on a schedule --
the "auto round" where the organism *does things* with its memory instead of only
stopping. This is the harness-side realization of the KAIROS agency tick; the Rust
heartbeat (engine ``kairos.rs``) can call ``agency_round`` on a tick to make it
fully autonomous.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Callable, List, Optional

from harness.inference.client import SPDaemonClient, get_client
from harness.inference.inference_config import InferenceConfig

logger = logging.getLogger(__name__)

# ── forget() IS OUT OF THIS VOCABULARY (2026-08-24 audit, B4) ──────────────────────────
# The whole agency-loop family (agency_round / run_agency_loop / run_agency_scheduler) is
# UNREACHABLE from any live path — app.py deliberately does not start the scheduler (its
# own comment: "it also fires agency_round(), an open-ended MODEL turn") — and this prompt
# told the model, four separate ways, to forget() rows on its own judgement. A model-driven
# forget loop must not sit fully built and green-gated, waiting for someone to wire it: the
# day a caller appears, the prompt is the policy. So the retiring verbs are gone from the
# vocabulary AND forget is stripped from the toolset the round is handed (below): a
# redundancy or a contradiction is REPORTED, and retiring is the operator's call. The
# store's own supersede machinery already tombstones a changed fact without being asked.
# The disconnected-surface row (with the arming condition) is docs/OFF-BY-DEFAULT.md §10.
AGENCY_PROMPT = (
    "You are reviewing your OWN long-term memory for upkeep. Your current memories:\n"
    "{mems}\n\n"
    "Maintain them with the tools:\n"
    "- If a single combined fact is clearer than several fragments, remember the combined "
    "fact — the store supersedes and tombstones on its own; you never delete anything.\n"
    "- If two memories contradict, or one looks stale or wrong, SAY WHICH and why in your "
    "reply. Retiring a memory is the operator's decision, not this round's.\n"
    "Make at most a few changes. If everything is consistent and current, do nothing "
    "and reply 'memory is healthy'."
)


def agency_round(
    *,
    client: Optional[SPDaemonClient] = None,
    config: Optional[InferenceConfig] = None,
    on_tool: Optional[Callable[[str, dict, str], None]] = None,
) -> str:
    """Run one model-driven memory-maintenance round; return the model's closing text."""
    from harness.toolcore.tools import ToolSpec, run_with_tools
    from harness.skills.memory import MEMORY_TOOLS, forget, list_memories

    prompt = AGENCY_PROMPT.format(mems=list_memories())
    # No forget in the round's hand — see the AGENCY_PROMPT note (2026-08-24, B4). The
    # prompt no longer asks for it, and a tool the prompt does not ask for but the hand
    # still holds is a leak waiting for a paraphrase.
    tools = [ToolSpec.from_callable(fn) for fn in MEMORY_TOOLS if fn is not forget]
    cfg = config or InferenceConfig(temperature=0.0, max_tokens=220, auto_recall=False)
    return run_with_tools(
        [{"role": "user", "content": prompt}],
        tools, client=client, config=cfg, on_tool=on_tool, max_rounds=5,
    )


def run_agency_loop(
    rounds: int = 1,
    *,
    client: Optional[SPDaemonClient] = None,
    config: Optional[InferenceConfig] = None,
    on_tool: Optional[Callable[[str, dict, str], None]] = None,
    on_round: Optional[Callable[[int, str], None]] = None,
) -> List[str]:
    """Run the agency round ``rounds`` times (the auto-rounds)."""
    out: List[str] = []
    for i in range(rounds):
        r = agency_round(client=client, config=config, on_tool=on_tool)
        out.append(r)
        if on_round:
            on_round(i, r)
    return out


# ── THE RAN-TODAY LEDGER (2026-08-24 audit, H8) ────────────────────────────────────────
# The nightly job (app.py's day-boundary pass) runs consolidate_current() and THEN
# ops.reflect(), in one process — and both ran the personality curator and world.refresh,
# so each fired TWICE per night on the same day's evidence. The dedupe lives here, beside
# the first runner: consolidate_current marks what it ran, reflect() asks before repeating
# it. In-process on purpose — the two calls share the night job's process, and a marker
# that survived restarts would wrongly suppress a legitimately re-run pass tomorrow-shaped
# edge cases aside (a UTC date is the grain the night job already thinks in). Deliberately
# ONE-directional: reflect() defers to consolidate_current, never the reverse, so the
# operator's reflect button always does what it says when pressed first.
_NIGHTLY_RAN: dict = {"personality": "", "world": ""}


def _mark_ran(step: str) -> None:
    _NIGHTLY_RAN[step] = time.strftime("%Y-%m-%d", time.gmtime())


def ran_today(step: str) -> bool:
    """Did consolidate_current already run this shared nightly step today (UTC)?"""
    return _NIGHTLY_RAN.get(step, "") == time.strftime("%Y-%m-%d", time.gmtime())


def _daemon_busy(client: SPDaemonClient) -> bool:
    """Best-effort: is a generation actively streaming? (a courtesy idle gate -- the
    daemon serializes on its resident-cache mutex so this is safety-optional)."""
    try:
        return float(client.metrics().get("tokens_per_sec", 0.0)) > 1.0
    except Exception:
        return False


def consolidate_current(convo, client: Optional[SPDaemonClient] = None) -> Optional[dict]:
    """Consolidate a conversation into the tiered store: extract durable facts -> mid-term
    registry, store the transcript full + summary -> long-term MEM-OKF. Returns the
    consolidation result, or None if nothing to do.

    `convo` is EITHER a path to a JSON message list OR the message list itself.

    ── WHY IT TAKES BOTH NOW (2026-07-30) ────────────────────────────────────────────
    It required a PATH, which is an accident of its only caller (`run_agency_scheduler`,
    driven by a CLI that had a file). The gateway holds live transcripts in memory
    (`_CHAT_SESSIONS`) and has no file to offer — so when the day-boundary job tried to
    call this, it got `stat: path should be string... not list` and the NARRATIVE WAS
    SKIPPED. That is the whole reason `var/memory/narrative.md` still did not exist after
    the clock was wired: the last link wanted a filename.

    A function whose job is "consolidate this conversation" should not care whether the
    conversation is on disk. Accepting the list removes the only thing standing between a
    live session and its own record."""
    import json
    import os
    if isinstance(convo, (list, tuple)):
        msgs = list(convo)
    else:
        if not convo or not os.path.exists(convo):
            return None
        try:
            with open(convo, encoding="utf-8") as f:
                msgs = json.load(f)
        except Exception as exc:
            logger.error("[agency] bad current-conversation file: %s", exc)
            return None
    if not msgs:
        return None
    from harness.skills.conversation_memory import consolidate_conversation
    result = consolidate_conversation(msgs, client=client)
    # PF-B5: NIGHTSHIFT also curates the PERSONALITY from the same transcript — extract the shifts
    # the model expressed, prune stale traits, snapshot to the memory-okf-personality tier. Gated
    # SP_PERSONALITY=1 (it writes persona.md); best-effort (never breaks memory consolidation).
    if os.environ.get("SP_PERSONALITY", "0") == "1":
        try:
            from harness.personality.curator import consolidate_personality
            pr = consolidate_personality(msgs)
            _mark_ran("personality")       # so ops.reflect does not run it again tonight (H8)
            if isinstance(result, dict):
                result["personality"] = pr
        except Exception as exc:
            logger.warning("[agency] personality curation skipped: %s", exc)
    # ── N2 (CONTINUITY.md): NIGHTSHIFT writes the days down ──────────────────────────
    # She composes one dated paragraph — what has been happening between them — and the
    # standing world folds it in on refresh. Best-effort: an unreachable model leaves
    # yesterday's paragraph standing (a stale true record beats a fresh empty one).
    if os.environ.get("SP_WORLD", "0") == "1":
        try:
            from harness.skills.narrative import compose_and_write
            from harness.skills.world import refresh
            nr = compose_and_write(msgs)
            refresh()          # the deliberate prefix re-cost, at the night boundary
            _mark_ran("world")             # so ops.reflect does not refresh again tonight (H8)
            if isinstance(result, dict):
                result["narrative"] = nr
            logger.info("[agency] narrative: %s", nr)
        except Exception as exc:
            logger.warning("[agency] narrative skipped: %s", exc)
    return result


def run_agency_scheduler(
    *,
    interval: float = 30.0,
    rounds: Optional[int] = None,
    client: Optional[SPDaemonClient] = None,
    config: Optional[InferenceConfig] = None,
    idle_gate: bool = True,
    convo_path: Optional[str] = None,
    on_round: Optional[Callable[[int, str], None]] = None,
    on_tool: Optional[Callable[[str, dict, str], None]] = None,
) -> int:
    """The KAIROS agency tick: fire ``agency_round`` on a heartbeat.

    Runs forever (``rounds=None``) or for ``rounds`` ticks. ``idle_gate`` skips a tick
    while the daemon is generating (mirrors the engine kairos.rs ``inference_active``
    backoff) so the maintenance never starves a live ``/v1/chat`` turn. Returns the
    number of rounds actually executed. The engine's Rust heartbeat can drive this by
    spawning the harness scheduler; the model-driven substance lives here.
    """
    client = client or get_client()
    done = 0
    while rounds is None or done < rounds:
        time.sleep(max(0.0, interval))
        if idle_gate and _daemon_busy(client):
            if on_round:
                on_round(-1, "(skipped: daemon busy)")
            continue
        # consolidate the current conversation (short -> mid + long) before maintenance
        if convo_path:
            try:
                cres = consolidate_current(convo_path, client=client)
                if cres and on_round:
                    on_round(-3, f"consolidated current conversation -> {len(cres['facts'])} fact(s), addr {cres['conversation_addr']}")
            except Exception as exc:
                logger.error("[agency] consolidate failed (operation=tick): %s", exc)
        # PK2 §T2-E4: drain ONE pending work-queue task per idle tick (SP_AGENCY_TASKS=1).
        # The organism advances operator-posted goals between chats, receipted, resumable.
        if os.environ.get("SP_AGENCY_TASKS", "0") == "1":
            try:
                from harness.control.task_loop import advance_pending_task
                ts = advance_pending_task(client=client)
                if ts and on_round:
                    on_round(-4, f"advanced task {ts.task_id} -> {ts.status}: {ts.result[:120]}")
            except Exception as exc:
                logger.error("[agency] task advance failed (operation=tick): %s", exc)
        # ADR-006 §D4 / ADR-007: registry HYGIENE on the tick, routed through the HARNESS SPINE
        # (decide → execute → VERIFY): the compaction's success is re-checked, not trusted, and
        # every decision leaves a receipt. Deterministic, no model call, default-on (compaction
        # only drops malformed lines + exact dups, never a real fact).
        try:
            from harness.control.spine import run_tick, persist_receipts
            for r in run_tick():
                if on_round:
                    v = "verified" if r.verified else ("VERIFY_FAIL" if r.verified is False else "unverified")
                    on_round(-5, f"spine tick {r.decider}/{r.kind}: {r.result} [{v}]")
            # ADR-005 flywheel: flush this process's spine receipts to the durable
            # telemetry-okf tier each tick (content-addressed, idempotent).
            n = persist_receipts()
            if n and on_round:
                on_round(-6, f"persisted {n} spine receipt(s) to telemetry-okf")
        except Exception as exc:
            logger.error("[agency] hygiene failed (operation=tick): %s", exc)
        try:
            r = agency_round(client=client, config=config, on_tool=on_tool)
        except Exception as exc:  # surface, never crash the heartbeat
            logger.error("[agency] round failed (operation=tick): %s", exc)
            r = f"(agency round error: {exc})"
        done += 1
        if on_round:
            on_round(done, r)
    return done
