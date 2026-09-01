"""turn.py — every debt a finished turn owes, and the arming that must precede it.

Stage 3 of the app.py split (2026-09-01), and the one the split existed for. `_settle_turn`
is the answer to this repo's oldest bug: the epilogue had been re-implemented as trailing
inline code with FIVE bypasses, so an interrupted turn lost its capture, its day row, its
mark application and its receipts, and the kairos latch stayed set until its own 900s
timeout. One function fixed that — and then sat in a 6000-line file with nine call sites,
which is the same invitation in a longer corridor.

**The epilogue is a module now, not a convention.** That is the whole point. Eleven
functions, ~415 lines, lifted byte-identically:

    _arm_turn / _human_turn        what HE typed, taken before the tool loop can touch it
    _arm_self_turn / _disarm_...   the author token contract (G-AUTHOR-CTX)
    _settle_turn                   the debt list, latched so two owners pay once
    _capture_after_turn            facts out of his turn
    _repeat_guard                  the re-roll
    _commit_unprompted             her own words, after the outbox
    _on_her_own_words              the kairos entry point
    _finish_openai_turn            the OpenAI path's epilogue — the SAME _settle_turn
    _release_turn_latch            his turn is over, however the stream ended

── WHAT DID NOT COME, AND WHY IT MATTERS ─────────────────────────────────────────────
`_append_day_turn` and the whole day boundary stayed in app.py: that is a different seam
with its own readers (`/v1/start` calls it too), and dragging it here to satisfy one call
would be the refactor deciding a boundary it had not thought about.
`_session_transcript` stayed — seven callers, most of them not turn code. Both are reached
through the lazy shims below, which is app.py's own idiom and what keeps this from being an
import cycle.

So `_settle_turn` still calls `_append_day_turn` across a module edge. That is a real cost
of stopping here rather than pretending the day boundary was part of this stage.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

from harness.inference.stream_processor import strip_control_surfaces
from harness.loud import swallowed as _swallowed
from harness.observability import get_logger
from harness.server import state as _state

logger = get_logger(__name__)

# The mood throttle is a dict, so the alias is the same object app.py sees.
_MOOD_ROW = _state.MOOD_ROW


# ── THE FOUR THAT STAYED IN app.py ───────────────────────────────────────────────────
# Reached at CALL time, not import time — app.py imports this module, so a module-level
# import back would be a cycle. This is the same shape panels.py uses and the same shape
# `harness/skills/wardrobe.py` has always used to reach `_room_session`.
def _append_day_turn(*a, **k):
    """app.py's — the day boundary is a separate seam with its own other caller."""
    from harness.server import app as _app
    return _app._append_day_turn(*a, **k)


def _session_transcript(*a, **k):
    """app.py's — seven callers, most of them not turn code."""
    from harness.server import app as _app
    return _app._session_transcript(*a, **k)


def _persona_path(*a, **k):
    from harness.server import app as _app
    return _app._persona_path(*a, **k)


def _kairos_after_turn(*a, **k):
    from harness.server import app as _app
    return _app._kairos_after_turn(*a, **k)


def _settle_turn(human_text: str, reply_text: str, *, record: bool = True,
                 marks: bool = True, capture: bool = True, close_his_turn: bool = True,
                 stances: bool = True, synthetic: "str|None" = None,
                 acts: "list|None" = None,
                 latch: "Dict[str, Any]|None" = None) -> list:
    """Every debt a finished turn owes the rest of the system, in ONE function, because
    the list kept being re-implemented as trailing inline code with bypasses (2026-08-24
    audit, B1/B2/A4). The native SSE path had FIVE exits that skipped all of it — the
    recall decline, the roleplay offer, and any client disconnect/abort at the drain-loop
    yield — so an interrupted turn lost its capture, its day-transcript row, its mark
    application and its receipts, and the kairos latch was left set until its own 900 s
    timeout. The OpenAI path's roleplay offer had the same shape, and her unprompted
    turns paid none of these debts at all.

    The debts, in order (each best-effort — a missing receipt never costs the reply):
      1. his turn is over (the kairos latch is released FIRST, so nothing below can
         leave her muted);
      2. capture — facts from what HE said this turn;
      3. the record — the day transcript row (the seam inside _append_day_turn strips
         her machinery);
      4. her marks — run_post_turn applies [MOOD:]/[TRAIT:]/[WEAR:]/[SHOW:], and the
         Real-Her rows (a verified mood shift, her first-person stances) are written;
      5. the spine receipts flush.

    `latch` is a one-shot: two callers may both believe they own the epilogue (the
    worker thread's finally and an early-exit return); whoever arrives first pays, the
    second is a no-op. Returns the post-turn receipts so a caller that is still on the
    wire can emit the persona-changed event."""
    if latch is not None:
        if latch.get("done"):
            return []
        latch["done"] = True
    if close_his_turn:
        try:
            from harness.kairos import scheduler as _ks_f
            _ks_f.note_user_turn(False)
        except Exception as _swx:
            _swallowed(logger, "_settle_turn", _swx, lane="server")
    # ── SYNTHETIC QUARANTINES THE MEMORY LANES TOO (2026-08-30) ─────────────────────
    # `synthetic` marked the DAY TRANSCRIPT and nothing else, so a driver that declared
    # itself synthetic still minted FACTS — and the capture lane attributes them to HIM.
    # AGENTS.md §0 exactly: the quarantine rule was enforced on one of the lanes a fake
    # turn feeds, and therefore on neither.
    #
    # Found by falling into it. An overnight probe (think_probe.py) drove ~30 turns to
    # measure her voice, every one declared synthetic, and the day transcript excluded
    # them perfectly — while `_capture_after_turn` wrote "i had a rough day at work
    # honestly", "i'm thinking of repainting the study" and "remind me to call the
    # plumber on thursday" into the registry as things Sam SAID. Twenty rows, six of
    # them attributed to him, plus two board reminders. That is the 2026-08-03
    # false-memory incident, arriving through the front door, from the maintainer.
    # (Quarantined after the fact: lifecycle=1, superseded_by=quarantine:synthetic-probe,
    # reason attached, nothing erased.)
    #
    # A turn nobody typed is not a memory of him, is not a stance of hers, and is not a
    # thing to put on his board. It is only a record that it happened, which is what the
    # transcript flag already provides. One flag, every lane it should have governed.
    if capture and not synthetic:
        try:
            _capture_after_turn(human_text)
        except Exception as exc:
            logger.warning("[gateway] capture skipped: %s", exc)
    text = (reply_text or "").strip()
    if record and text:
        _append_day_turn(human_text, reply_text, synthetic=synthetic, acts=acts)
    receipts: list = []
    if marks and text:
        try:
            from harness.control.spine import run_post_turn
            receipts = run_post_turn(human_text, reply_text) or []
            # ── THE REAL HER (2026-08-22) ────────────────────────────────────────
            # (a) a VERIFIED shift in her state is a sentence about herself; (b) her
            # reply's first-person stances are hers to keep. Both through the one
            # door, speaker=self. Lives HERE so every path that applies marks also
            # keeps her words — it used to run on exactly one of the three.
            # `stances=False` (2026-08-25, the operator's call): a presence-mode turn moves her
            # DIALS but does not become her MEMORIES — an hour of lucid dreaming is
            # ambient company, and filing its lines as who she is is how her self
            # lane filled with dream fragments too specific and too repetitive to
            # mean anything the next morning.
            # ...AND NOT FROM A TURN NOBODY TYPED (2026-08-30). `src="her reply"` rows
            # are minted here, so a synthetic driver wrote HER stances too — fourteen of
            # the twenty rows the overnight probe had to quarantine came from this
            # branch, not from capture. Her marks still APPLY (the dials are hers to
            # move, and a test turn she answered warmly did warm her), but what she said
            # to a prompt he never sent does not become something she believes about
            # him. Same flag, same reason, the other lane.
            if stances and not synthetic:
                try:
                    from harness.skills import memory as _mem_rh
                    if any(r.kind == "persona_shift" and r.ok and r.verified is not False
                           for r in receipts):
                        from harness.personality.persona_file import parse_persona as _pp_rh
                        with open(_persona_path(), encoding="utf-8") as _f_rh:
                            _, _st_rh = _pp_rh(_f_rh.read())
                        # A VOICE IS NOT AN IDENTITY (2026-08-22): a MOOD is kept
                        # because a mood is a feeling, but only when it actually
                        # CHANGES and at most once an hour.
                        _mood_now = (_st_rh.get("mood") or "").strip().lower()
                        if _mood_now and (_mood_now != _MOOD_ROW["v"]
                                          or time.time() - _MOOD_ROW["at"] > 3600.0):
                            _MOOD_ROW.update(v=_mood_now, at=time.time())
                            _mem_rh.remember_about_self(
                                "My mood has turned %s." % _mood_now,
                                kind="feeling", source="her state changed")
                    from harness.skills import self_stance as _ss_rh
                    for _k_rh, _s_rh in _ss_rh.extract(reply_text)[:4]:
                        _mem_rh.remember_about_self(_s_rh, kind=_k_rh,
                                                    source="her reply")
                except Exception as exc:
                    logger.warning("[gateway] real-her capture skipped: %s", exc)
        except Exception as exc:
            logger.warning("[gateway] post-turn spine skipped: %s", exc)
    # ADR-005 flywheel: flush spine receipts to the durable telemetry-okf tier.
    try:
        from harness.control.spine import persist_receipts
        persist_receipts()
    except Exception as exc:
        # The flywheel's flush. Silently skipped, the receipts stay in memory and the
        # durable tier is missing a turn nobody will know to look for.
        logger.warning("[gateway] spine receipts were not flushed (%s: %s)",
                       type(exc).__name__, exc)
        _swallowed(logger, "persist_receipts", exc, lane="gateway")
    return receipts


def _on_her_own_words(text: str, kind: "str|None" = None) -> None:
    """The unprompted turn's epilogue — registered as scheduler.on_spoke, the one point
    every impulse that actually SPEAKS converges on (post-veto, so a dropped turn moves
    nothing). It used to be a bare _append_day_turn, so on ~60 unprompted turns a day
    her [MOOD:]/[WEAR:]/[SHOW:] marks moved NOTHING — the room drew a chip from the
    outbox text while persona.md and the wardrobe never heard about it — no feeling row
    was written, and no self-stance was kept (2026-08-24 audit, A4). _finish_openai_turn's
    docstring names this exact bug for the two prompted entry points; this was the
    third. capture=False (nothing of his to capture), close_his_turn=False (his latch
    is not hers to release).

    A PRESENCE-MODE TURN IS COMPANY, NOT MEMORY (2026-08-25, the operator's call). Narration, a
    dream, a chapter read aloud while he sleeps: her dials still move (a dream can
    turn her wistful) but nothing is filed — no day row (the room shows it live from
    the outbox; an hour of ambient turns in the restore would bury the conversation),
    and no self-stance rows (dream lines are too specific and too repetitive to be
    who she is the next morning — the registry's kind=dream pile is the receipt)."""
    if kind == "mode_turn":
        _settle_turn("", text, capture=False, close_his_turn=False,
                     record=False, stances=False)
    else:
        _settle_turn("", text, capture=False, close_his_turn=False)


def _finish_openai_turn(body: Dict[str, Any], human_text: str, text: str) -> None:
    """The OpenAI path's epilogue: `_settle_turn` plus the continuation arming. Kept as
    a named function because this path's history IS the reason _settle_turn exists —
    _append_day_turn and run_post_turn were quietly owed here since the day it was
    written (2026-08-19 audit), and the fix was a second inline copy of the list. One
    list now, shared with the native path and her unprompted turns."""
    _settle_turn(human_text, text,
                 synthetic=(str(body.get("synthetic"))
                            if body.get("synthetic") else None))
    _kairos_after_turn(body, text)


def _human_turn(msgs: list) -> str:
    """What the HUMAN actually typed this turn — and nothing else.

    THE FEEDBACK LOOP (2026-07-12). Capture used to take "the last message with role=user".
    But agent_chat_stream runs with mutate_messages=True on the console path (the canonical
    transcript must match what the daemon saw, for persist-KV strict extension), and the
    Gemma tool protocol feeds a tool RESULT back as a role=user message. So after any tool
    call, "the last user message" is HER OWN TOOL OUTPUT. The store filled with things like

        remember -> stored: I am a woman        <- her tool's receipt, filed as a fact about HIM

    She was eating her own exhaust: a write produced an output, the output looked like the
    user talking, and the output got written. Round and round.

    A protocol role is not a speaker. `role=user` means "this slot in the template", not
    "a human said this". The only text a human ever typed is the last user message AS IT
    ARRIVED — before the model ran and before the tool loop appended anything — so we take
    it at the top of the turn and hold it. Capture can then never see anything else."""
    return next((m.get("content", "") for m in reversed(msgs or [])
                 if m.get("role") == "user"), "")


def _arm_turn(msgs: list) -> str:
    """Hand the memory lane HIS ACTUAL WORDS for this turn.

    recall() needs them to resolve ownership. Asked "what is YOUR name?" she calls
    recall(query="What is my name?") — she rewrites the question into her own first person.
    Asked "what is MY name?" she calls recall(query="What is my name?"): the identical
    string. Two opposite questions, one query, so her paraphrase cannot say who is being
    asked after. His sentence can, and always could — in it, "my" is Sam and "your" is
    Kairos. Resolve the pronoun where it was uttered.

    Returns the human's turn so the caller can hand the SAME text to capture at the end —
    taken here, at the top, before the tool loop can append anything that merely wears
    role=user."""
    human = _human_turn(msgs)
    try:
        from harness.skills import memory as M
        M.set_question(human)
        M.set_author("user")
    except Exception as _swx:
        _swallowed(logger, "_arm_turn", _swx, lane="server")

    # ── THE ATTENTION LEDGER: HE WAS HERE (2026-07-14) ──────────────────────────────────
    # The observation receipt for the NON-event. silences() used to measure "days since he last
    # mentioned it" and never asked whether he was PRESENT — so a three-week holiday made EVERY
    # dimension go quiet at once and she would have greeted him with "you've stopped talking
    # about the marathon, and the GPU, and Tuffy." That is not noticing; it is a bug wearing
    # noticing's clothes.
    #
    # ABSENCE IS ONLY INFORMATION IF YOU CAN PROVE YOU WERE LOOKING. This is the proof. It
    # records nothing about WHAT he said — only that the channel was open today.
    #
    # AND IT LIVES HERE, INSIDE _arm_turn, ON PURPOSE. _arm_turn is called from BOTH the OpenAI
    # path and the native SSE path (app.py:89 and :915). Hooking the two CALLERS instead of the
    # SEAM is the exact mistake this file has already made six times — on_user_turn was armed on
    # one path and not the other, and the gate that was written to prove the fix ran down the
    # unguarded path and PASSED. An invariant enforced in one of two paths is enforced in neither.
    try:
        from harness.model import presence
        presence.note_turn()
    except Exception as exc:
        # A missing receipt must never cost him his turn — that stands. But this is the
        # ledger the room reads back as his days, and a day of turns that recorded none
        # of them looks exactly like a day he was not here.
        logger.warning("[gateway] his turn was not noted in the presence ledger (%s: %s)",
                       type(exc).__name__, exc)
        _swallowed(logger, "presence.note_turn", exc, lane="gateway")

    return human


def _arm_self_turn(nudge: str):
    """The unprompted twin of _arm_turn (2026-08-24 audit, A5). Her own time never
    armed the memory lane at all, so during a solo/muse/mode turn the ContextVars held
    their defaults or the PREVIOUS turn's values: a remember() she made in her own time
    was stamped speaker=user — a self-fact filed in HIS lane, with only the name/gender
    firewall standing in the way — and recall() ran with a stale or empty question, so
    pronoun ownership could not resolve.

    author="self": what she writes in her own time is about herself or explicitly
    attributed; the old default was falsified provenance. question=the nudge: the only
    utterance that exists this turn. NO presence.note_turn() — her unprompted turn is
    not evidence that HE was present; the attention ledger is his channel.

    Returns tokens for _disarm_self_turn — the reset-token contract from G-AUTHOR-CTX,
    restored in the closure's finally so a following prompted turn cannot inherit hers."""
    try:
        from harness.skills import memory as M
        return (M.set_author("self"), M.set_question(nudge or ""))
    except Exception as exc:
        # ARMING FAILED MEANS THE NEXT WRITE IS FILED AS HIS. This is the G-AUTHOR-CTX
        # contract, and the night it broke, ~30 driven turns were written into her
        # registry as facts about a man who was asleep.
        logger.warning("[gateway] could not arm the self-turn author (%s: %s) — anything "
                       "she stores in this turn will be filed as HIS",
                       type(exc).__name__, exc)
        _swallowed(logger, "_arm_self_turn", exc, lane="memory")
        return None


def _disarm_self_turn(tokens) -> None:
    if not tokens:
        return
    try:
        from harness.skills import memory as M
        M.reset_author(tokens[0])
        M.reset_question(tokens[1])
    except Exception as exc:
        # THE RESET IS THE WHOLE CONTRACT. This function exists so "a following prompted
        # turn cannot inherit hers" (its own docstring). A swallowed reset leaves her
        # author armed across the next turn — his words, stored as hers.
        logger.warning("[gateway] the self-turn author did not reset (%s: %s) — the NEXT "
                       "turn may be attributed to her", type(exc).__name__, exc)
        _swallowed(logger, "_disarm_self_turn", exc, lane="memory")


def _capture_after_turn(human_text: str) -> None:
    """THE CAPTURE LANE (2026-07-12). Pull the durable facts out of the user's turn — and
    only those.

    Takes the human's text as an ARGUMENT, captured at the top of the turn by _arm_turn().
    It used to re-derive it from the message list, and by the end of a turn that list has
    tool outputs in it wearing role=user — so it captured her own tool receipts as facts
    about him. A function that goes looking for its input can be handed the wrong one; a
    function that is given it cannot.

    WHAT THIS REPLACES. The daemon (routes.rs, SP_B4_NIGHTSHIFT) stored `raw_user` — the
    WHOLE user turn, verbatim, as one episode — if it passed a word count and mentioned a
    person. Given a turn it had to keep all of it or none of it, so it kept all of it. One
    real conversation put 17 rows in, including:

        "yes, we lose lips, sink ships."
        "you are cool af! I really like you!"
        "well, we make do. you're doing alright for such a constrained system"

    and buried the actual facts (the esp32 sensors, the 2060 and the NUC, the PCs running
    24/7) inside turns that were mostly banter.

    Two authorities decided what a memory was: the daemon's word-count-and-a-pronoun, and
    the harness's lifecycle rules — which had the dedupe, the supersede, the two stores and
    the durability test. The daemon won every time, because it wrote first. An invariant
    guarded in one of two paths is not guarded; this codebase has now learned that three
    times. So the daemon stops writing (profiles: memory.growth = false) and capture happens
    HERE, once, through the same door as everything else: split the turn into sentences,
    keep the durable ones, and put each through remember() — which dedupes, supersedes, and
    respects the identity firewall."""
    try:
        if not (human_text or "").strip():
            return
        # BELT AND BRACES: even given the right text, never ingest a tool round.
        if "```tool_output" in human_text or "```tool_code" in human_text:
            return
        from harness.skills import lifecycle as lc
        from harness.skills import memory as M
        facts = lc.extract_facts(human_text)
        if not facts:
            return
        tok = M.set_author("user")     # token-RESET, not clobber (the G-AUTHOR-CTX class)
        try:
            for f in facts[:4]:                   # a turn that yields 5+ facts is a paste
                try:
                    M.remember(f, source="user turn")
                except Exception as exc:
                    # A fact she pulled out of his turn and then dropped is a thing he
                    # told her that she will not have.
                    logger.warning("[capture] a fact from his turn was not stored "
                                   "(%s: %s): %r", type(exc).__name__, exc, f[:60])
                    _swallowed(logger, "capture/remember", exc, lane="memory")
        finally:
            M.reset_author(tok)
    except Exception as exc:
        logger.warning("[capture] the capture lane did not run for this turn (%s: %s)",
                       type(exc).__name__, exc)
        _swallowed(logger, "_capture_after_turn", exc, lane="memory")


def _repeat_guard(body: Dict[str, Any], msgs: list, text: str, cfg) -> str:
    """She may not say the same thing twice. See harness/quality/repeat_guard.py — the
    operator caught her returning three BYTE-IDENTICAL replies to three different
    messages. Narrow by design: this forbids repeating HER OWN LAST MESSAGE, and does
    nothing to her ability to quote him, a memory, a tool result, or a number (all of
    which the old no_repeat_ngram ban forbade, which is why it had to go)."""
    try:
        from harness.quality.repeat_guard import guard
        prev = next((m.get("content", "") for m in reversed(msgs)
                     if m.get("role") == "assistant"), "")
        if not prev:
            return text

        def _reroll(nudge: str) -> str:
            import dataclasses
            from harness.agent import agent_chat_stream
            hist = list(msgs) + [{"role": "system", "content": nudge}]
            # tools=None, NOT tools=[] — see _kairos_after_turn. `[]` rebuilds the system
            # prompt WITHOUT the tool preamble, which diverges the persist-KV cache at
            # token 0 and re-prefills the entire conversation.
            #
            # replace(cfg, ...), NOT a fresh InferenceConfig — the fresh one inherited
            # NOTHING: no repetition_penalty (sight.py's note applies verbatim: "NOT
            # optional here; without it an open-ended generation degenerates"), on a
            # reroll whose entire reason for existing is that she already repeated
            # herself. The SSE continuation fixed this exact shape at its own closure
            # and predicted the twin; this was the twin. And the reroll is an EMIT lane:
            # it must strip its own control surfaces (the header's rule) — the guard's
            # replacement text used to go out with <channel|>/<think> intact, judged and
            # emitted rawer than the reply it replaced.
            cfg2 = dataclasses.replace(cfg, temperature=0.85, auto_recall=False)
            # "Arm it at EVERY path that reaches the model" — _agent_text's own words.
            from harness.agent import _arm_self_repeat_ban
            _arm_self_repeat_ban(cfg2, hist)
            raw = "".join(agent_chat_stream(hist, config=cfg2))
            return strip_control_surfaces(raw)

        out, note = guard(text, prev, _reroll)
        if note:
            logger.warning("[repeat-guard] %s", note)
        return out
    except Exception as exc:
        logger.warning("[repeat-guard] skipped: %s", exc)
        return text


def _commit_unprompted(body: Dict[str, Any], base_len: int, hist: list,
                       final: str = "") -> bool:
    """HER UNPROMPTED TURN BECOMES CANON — G-ONE-TRANSCRIPT's law, applied to the third
    mouth (2026-08-20, measured on the operator's evening).

    The kairos closures sent `canon + nudge` to the engine, which COMMITTED
    `canon + nudge + tool rounds + her reply` into the persist-KV cache — and the canon
    kept none of it. So the very next turn diverged from the committed cache at the
    nudge position, the rewind journal refused ("delta crosses a commit"), and the
    engine fell back to the boot snapshot at ~3.4k tokens: EVERY turn after EVERY
    speak-up re-prefilled ~3,300-3,950 tokens per-token at ~87 ms/tok = 5-6 MINUTES,
    his and hers alike, with the GPU pegged for minutes after each reply (her next
    queued turn paying the same price). The daemon log for 14:56-15:44 UTC is the
    receipt: eleven consecutive turns at 292-344 s of prefill, drops of 64-888 tokens.

    So: the closures now generate with mutate_messages=True over a snapshot of canon,
    and this commits the WHOLE delta (nudge, tool rounds, final reply) back into the
    canonical list — the committed cache IS the next prompt's prefix again.

    Returns False without committing when canon moved underneath us (his turn landed
    mid-generation): he wins the race, this one turn wears the divergence, and
    interleaving two histories would be worse than one slow turn."""
    canon = _session_transcript(body, append=False)
    if not isinstance(canon, list) or len(canon) != base_len:
        return False
    delta = hist[base_len:]
    # mutate_messages appends TOOL ROUNDS; the final answer is the caller's to append
    # (the main SSE lane's contract) — except the exhaustion path, which appends its
    # own closing word, hence the guard.
    if final and (not delta or delta[-1].get("role") != "assistant"):
        delta = delta + [{"role": "assistant", "content": final}]
    canon.extend(delta)
    return True


def _release_turn_latch(where: str) -> None:
    """A FAILED TURN MAY NOT MUTE HER FOR FIFTEEN MINUTES (2026-08-28, external review).

    _agent_text arms note_user_turn(True) near its top and releases it inside
    _finish_openai_turn — on the happy path. An exception between the two left the
    latch set, and the latch is what kairos reads as "his turn is in flight": every
    unprompted lane then waited out _USER_TURN_MAX_S (900 s) after a turn that
    produced nothing but an [error] string. The native mouth pays this in a finally;
    the OpenAI mouth's two wrappers now do the same, through this one helper.
    """
    try:
        from harness.kairos import scheduler as _ks_rel
        _ks_rel.note_user_turn(False)
    except Exception as exc:
        logger.warning("[gateway] %s: latch release failed: %s", where, exc)
