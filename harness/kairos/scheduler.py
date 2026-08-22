"""KAIROS SCHEDULER — the thing that actually lets her speak, and mostly stops her.

Sits on the gateway's turn boundary. After every reply:

    1. read the turn's continuation impulse (eot_margin, straight from the forward)
    2. ask the policy (harness/kairos/impulse.py) — which says SILENT almost always
    3. if it says otherwise, WAIT the realistic delay, then generate the continuation
    4. run the last gate: worth_saying(). A continuation that is a greeting, a
       re-introduction, or a restatement is DROPPED and never reaches the operator.
    5. only what survives all four goes in the session's OUTBOX, which the console polls

Steps 4 and 5 matter as much as 1-3. An unprompted message that adds nothing is worse
than silence: it teaches the operator to ignore her. She is allowed to think, and then
decide she had nothing after all.

All knobs are read LIVE from the tuning registry on every turn, so the operator can move
kairos.max_chain or kairos.continue_margin in the UI and the next turn obeys it — no
restart. Config that requires a restart is config nobody tunes.
"""
from __future__ import annotations

import calendar
import json
import logging
import os
import threading
import random
import time
from collections import defaultdict, deque
from typing import Any, Callable, Optional

from harness.kairos.impulse import (
    CHECK_IN, CONTINUE, REMIND, MUSE, CHECK_IN_NUDGE, continue_nudge, remind_nudge,
    muse_nudge,
    Impulse, KairosConfig, TurnState, SOLO, SOLO_NUDGE, solo_nudge, solo_worth_saying,
    solo_did_the_thing, solo_needs,
    EXPAND, expand_nudge, MODE_TURN,
    decide, note_spoke, note_user, worth_saying,
)
from harness.kairos import speechlog as _speech
from harness.tuning import registry as tune

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()

# ── HIS TURN IS NOT A THING SHE TALKS OVER (2026-08-04) ──────────────────────────────
# MEASURED from the caller log, seventeen minutes of his evening:
#     18:56  _generate <- scheduler     19:07  _generate <- scheduler
#     18:59  _generate <- scheduler     19:10  _run  <- HIS MESSAGE
#                                       19:13  _generate <- scheduler
# Four unprompted turns around one of his. Individual turns were 14-60 s; he experienced
# ten minutes, because every speak-up holds the one resident cache and his message waits
# behind whatever she started before he pressed send.
#
# The engine's priority gate does not help here: it guards /v1/oneshot, and a speak-up is
# a /v1/chat call like his. `agency.py` has had the right rule the whole time — an
# `idle_gate` that skips a tick "so the maintenance never starves a live /v1/chat turn" —
# applied to the maintenance loop and not to the one thing that actually speaks. Third
# surface, same §0 shape.
#
# So: while he is mid-turn, she does not start one. Not a queue and not a cancellation —
# the impulse is simply dropped, which is the honest outcome, because an unprompted remark
# that arrives four minutes late is answering a moment that has gone. She gets another
# impulse in seven seconds; he only gets one evening.
# A DEADLINE, NOT A COUNTER, and the difference matters more than it looks. The first cut
# incremented on the way in and decremented on the way out — and the turn generator has
# three early-return paths between those two points. Any one of them would have left the
# counter high forever and SHE WOULD NEVER SPEAK AGAIN, silently, with no error anywhere.
# That is a far worse failure than the one this guard exists to fix, and it is exactly the
# kind of latch this repo has been bitten by before (the wedged daemon, the accumulating
# recall note).
#
# So the marker expires by itself. A released turn clears it immediately; a turn that dies
# on some path nobody thought about costs her one window of quiet and then she is free.
_USER_TURN_UNTIL: float = 0.0
_USER_TURN_MAX_S: float = 900.0


def note_user_turn(active: bool) -> None:
    """The gateway marks his turns. Safe to miss the closing edge — it times out."""
    global _USER_TURN_UNTIL
    with _LOCK:
        _USER_TURN_UNTIL = (time.time() + _USER_TURN_MAX_S) if active else 0.0


def user_turn_active() -> bool:
    with _LOCK:
        return time.time() < _USER_TURN_UNTIL
_STATE: dict[str, TurnState] = defaultdict(TurnState)
_OUTBOX: dict[str, deque] = defaultdict(deque)
_TIMERS: dict[str, threading.Timer] = {}

# THE LAST TURN, PER SESSION — her reply, and the closure that can run one more turn on
# that conversation. The idle ticker needs both: to check in, she has to be able to SPEAK,
# and speaking means generating against the history she was last in.
_LAST: dict[str, tuple] = {}
# WHICH SESSIONS ARE ONLY A SEED. A seeded session is a placeholder for a conversation
# that has not happened yet — it exists so she can speak first after a restart. The moment
# a REAL one starts it is redundant, and leaving it costs double: measured 2026-08-05, 22
# solo turns across `default` (14, seeded) and `room-msdtx7kx-ak8ex0` (8, real), both
# generating from the SAME canon, both holding the one GPU.
#
# This became possible the same night the room started sending a session_id — before that
# the room WAS "default" and the seed was the same key, which is exactly what
# `_room_session`'s docstring assumed in writing. One fix, one assumption quietly broken
# three hours later, and nothing connected the two until the log was read.
_SEEDED: set = set()
_TICKER: Optional[threading.Thread] = None
# A GENERATION COUNTER, NOT A SHARED STOP EVENT (2026-08-08) — round 1 of this task's own
# review caught the race a single `threading.Event` opens up. `stop_ticker()` used to set
# the event and drop `_TICKER` to None while the old `_loop` thread could still be asleep
# in `time.sleep(_period())` for up to 600s. If `start_ticker()` ran again in that window,
# its "one already alive?" guard read `_TICKER` — now None — and proceeded, and
# `_TICKER_STOP.clear()` wiped the flag out from under the thread that had not woken up
# yet. That thread then woke, saw CLEAR, and ticked again: two threads calling
# `tick_once()` against the one GPU, the exact shape of the incident the `_SEEDED` comment
# above measures — two generators on the same canon, both holding the one resident cache.
# And this is not a rare interleaving to shrug off: `mode=her` stops the ticker and the
# room's start button brings her back in the SAME gateway process, so stop-then-restart is
# the ordinary path for this feature, not an edge case.
#
# A generation counter closes it without a flag for a later generation to race: every
# start and every stop is a new generation, `_loop` captures the generation it was born
# into, and it only ever compares its own number against the CURRENT one — there is
# nothing shared to clear out from under it.
_TICKER_GEN: int = 0

# WHERE HER UNPROMPTED TURNS GO. The scheduler must not know what a day transcript is —
# the gateway owns that file — so the gateway hands it a writer at startup. None means
# nobody is listening, which is a legitimate state (tests, the CLI) and not an error.
_ON_SPOKE = None


def on_spoke(fn) -> None:
    """Register the one writer for what she says unprompted. See the call site in tick()."""
    global _ON_SPOKE
    _ON_SPOKE = fn


_SEEDER = None          # app.py's day-seeder (rebuilds a closure from the day's transcript)
_WARM_OK = None         # app.py's "the prefix is hot" (she never starts a mode into a cold prefill)
_PENDING_KICK = [False] # a kick asked for while there was no session yet
_LAST_MODE_TEXT: dict = {}


def set_seeder(fn) -> None:
    global _SEEDER
    _SEEDER = fn


def set_warm_ok(fn) -> None:
    global _WARM_OK
    _WARM_OK = fn


def _warm_ok() -> bool:
    try:
        return bool(_WARM_OK()) if _WARM_OK is not None else True
    except Exception:
        return True


def _seed_for_presence() -> bool:
    """A MODE STARTS ON A BOUNCE, before he has spoken — but only once the prefix is hot
    (his ask, 2026-08-22). seed_on_boot is about her speaking FIRST on her own; an armed
    mode is his standing order, so the seed is forced."""
    if _SEEDER is None or not _warm_ok():
        return False
    try:
        ok = bool(_SEEDER(force=True))
    except TypeError:
        ok = bool(_SEEDER())
    except Exception as exc:
        logger.warning("[kairos] presence seed failed: %s", exc)
        return False
    if ok and _PENDING_KICK[0]:
        with _LOCK:
            for st in _STATE.values():
                st.mode_kick = True
            _PENDING_KICK[0] = False
    return ok


def seed(session: str, reply_text: str, generate, force: bool = False) -> bool:
    """Give her a conversation to speak into after a restart. Returns True if seeded.

    SHE COULD NOT SPEAK FIRST. EVER. `_LAST` is populated only by `on_reply`, so until HE
    said something, a fresh gateway had nothing to speak against and `tick_once` iterated
    an empty dict. Every continuity phase that spanned a restart was silent by
    construction — and a continuity phase is exactly the window (he is asleep, or away)
    where initiative is the entire point.

    `last_user_at` is seeded to NOW rather than to his real last turn, deliberately. It is
    the clock CHECK_IN measures idleness against, and it starts at 0.0, which reads as
    "never" and disables check-in outright. Setting it to boot time means she waits a full
    `checkin_idle_s` before she may say anything — she does not blurt the moment the
    process comes up, which is the right manners and also the safe direction if he has
    been gone for hours.

    Never clobbers a live session: if `on_reply` has already run, that closure is bound to
    the real conversation and is strictly better than anything rebuilt from disk.
    """
    if not (reply_text or "").strip() or generate is None:
        return False
    # ── SPEAKING FIRST IS A CHOICE NOW (2026-08-20, operator) ────────────────────
    # "she shouldn't act first at bounce/restart like before." The seeded session is
    # the mechanism behind acting first; the knob makes it opt-in. Off (the default)
    # means a fresh boot waits for him — the safe direction, and after a morning of
    # restart-blurt-restart-blurt, also the polite one.
    try:
        if not force and not bool(tune.get("kairos.seed_on_boot")):
            logger.info("[kairos] not seeding — kairos.seed_on_boot is off; "
                        "she waits for him after a restart")
            return False
    except Exception:
        return False        # an unreadable knob keeps the quiet default
    with _LOCK:
        if session in _LAST:
            return False
        _LAST[session] = (reply_text, generate)
        _SEEDED.add(session)
        _STATE[session].last_user_at = time.monotonic()
    logger.info("[kairos] seeded session=%s from the day's transcript — "
                "she can speak first without waiting for him", session)
    return True


def live_config() -> KairosConfig:
    """Read the knobs fresh, every turn. The UI is the source of truth."""
    return KairosConfig(
        enabled=bool(tune.get("kairos.enabled")),
        continue_margin=float(tune.get("kairos.continue_margin")),
        max_chain=int(tune.get("kairos.max_chain")),
        cooldown_s=float(tune.get("kairos.cooldown_s")),
        max_per_hour=int(tune.get("kairos.max_per_hour")),
        checkin_idle_s=float(tune.get("kairos.checkin_idle_s")),
        checkin_chance=float(tune.get("kairos.checkin_chance")),
        expand_margin=float(tune.get("kairos.expand_margin")),
        expand_chance=float(tune.get("kairos.expand_chance")),
        # PRESENCE AND HER OWN TIME. Read live like everything else here — these are the
        # knobs most likely to want moving after an evening of actually living with it,
        # and a knob that needs a restart is a knob nobody touches.
        away_after=int(tune.get("kairos.away_after")),
        backoff_mult=float(tune.get("kairos.backoff_mult")),
        solo_enabled=bool(tune.get("kairos.solo_enabled")),
        solo_every_s=float(tune.get("kairos.solo_every_s")),
        solo_chance=float(tune.get("kairos.solo_chance")),
        quiet_after_him_s=_quiet_after_him(),
        presence_mode=_presence("presence.mode", "off", str),
        presence_every_s=_presence_every(),
        presence_chance=_presence("presence.chance", 1.0, float),
        presence_max_per_hour=_presence("presence.max_per_hour", 12, int),
    )


def _presence_every() -> float:
    """The CURRENT mode's own cadence knob (three knobs, not one — 2026-08-22); 0 when no mode."""
    m = _presence("presence.mode", "off", str)
    if m not in ("narration", "company", "lucid"):
        return 0.0
    return _presence("presence.every_%s_s" % m, 0.0, float)


def _presence(key: str, default, cast):
    """The presence-mode knobs (2026-08-22); an unreadable knob keeps the quiet default."""
    try:
        v = tune.get(key)
        return cast(v) if v is not None and v != "" else default
    except Exception:
        return default


def _quiet_after_him() -> float:
    """The policy's quiet-after-him floor (2026-08-22 — it lived here as a fire-time drop)."""
    try:
        return float(tune.get("kairos.quiet_after_him_s"))
    except Exception:
        return 0.0


def on_user_turn(session: str) -> None:
    """He spoke. Her chain resets — that is what makes this a conversation."""
    with _LOCK:
        # A REAL CONVERSATION RETIRES THE PLACEHOLDER. See _SEEDED: the seeded session
        # exists only so she can speak first after a restart, and once he has actually
        # said something it is a second mouth on the same history.
        if session not in _SEEDED:
            for stale in [k for k in _SEEDED if k != session]:
                _SEEDED.discard(stale)
                _LAST.pop(stale, None)
                _STATE.pop(stale, None)
                t = _TIMERS.pop(stale, None)
                if t:
                    t.cancel()
                logger.info("[kairos] retired the seeded session %r — %r is live now",
                            stale, session)
        note_user(_STATE[session], time.monotonic())
        t = _TIMERS.pop(session, None)
    if t:
        t.cancel()          # he spoke while she was waiting to continue — she yields to him


def on_reply(
    session: str,
    reply_text: str,
    kairos_payload: Optional[dict],
    generate: Callable[[str], str],
) -> Optional[Impulse]:
    """Called after each assistant reply. `generate(nudge)` runs one more turn with the
    nudge appended and returns her text. Returns the Impulse (for the receipt/telemetry)."""
    cfg = live_config()

    # REMEMBER THE TURN EVEN WHEN SHE IS SILENT — and even when kairos is off. The idle
    # ticker speaks against the last conversation, so it needs the closure regardless of
    # what this turn decided. Storing it only on the speaking path would mean she could
    # only ever check in after a turn she had already interrupted.
    with _LOCK:
        _LAST[session] = (reply_text, generate)

    if not cfg.enabled:
        return None

    margin = None
    if kairos_payload:
        margin = kairos_payload.get("eot_margin")

    now = time.monotonic()
    due = _due_notes()
    with _LOCK:
        st = _STATE[session]
        imp = decide(cfg=cfg, state=st, now=now, reply_text=reply_text,
                     eot_margin=margin, due_notes=due)

    logger.info("[kairos] session=%s margin=%s -> %s (%s)",
                session, f"{margin:.2f}" if isinstance(margin, float) else margin,
                imp.action, imp.reason)
    if not imp.speaks:
        return imp

    _arm(session, imp, reply_text, generate, margin, notes=due if imp.action == REMIND else None)
    return imp


# ── REFLECTION ON THE CLOCK (2026-07-13) ─────────────────────────────────────
#
# THINKING IS NOT SPEAKING, and keeping them apart is the whole design.
#
# She reflects SILENTLY whenever the room has been still long enough: she reads what she
# knows about him and writes down what she has come to believe. That happens whether or not
# he ever hears about it — it is how the model of him gets built, and most of what she
# concludes should simply become part of what she knows, unremarked. A person who told you
# every single thing they had ever noticed about you would be unbearable.
#
# Only a genuinely SURPRISING conclusion earns an interruption (reflect.speak_bits). The bar
# is not "did she think of something" — she thinks on a clock, she will always have thought
# of something. The bar is whether the model itself did not see it coming, which is the one
# property of a conclusion that cannot be faked.
#
# NO NEW EVIDENCE, NO NEW THINKING. If nothing has been added to the store since the last
# reflection, she does not run: re-reading the same facts just re-derives the same
# conclusion and presents it as a discovery. (Reinforcement makes that harmless in the
# STORE — a re-derived belief strengthens rather than duplicating — but it would be deadly
# in the CHANNEL, where the same thought arriving twice is how a companion becomes a bore.)
_LAST_REFLECT_AT: float = 0.0
_LAST_EVIDENCE: int = -1
_PENDING_INSIGHT: dict = {}


def _evidence_count() -> int:
    """How much she has been TOLD — not how much she has CONCLUDED.

    ── A REFLECTION IS A CONCLUSION, NOT AN OBSERVATION (2026-07-14) ────────────────────
    This used to be `len(_load())`: every row in the store, including her own reflections.

    And `insight()` WRITES ROWS. So the sequence was:

        ev = evidence_count()          # 46
        if ev == last_evidence: return # "nothing new to think about"
        last_evidence = ev             # 46
        insight()                      # <-- writes 2 rows. The store is now 48.

    ...and on the next tick the count is 48, which is "new evidence", so she reflects again —
    ON HER OWN REFLECTIONS. The gate that was supposed to mean "has he told me anything?"
    actually meant "has the store changed?", and she is part of the store.

    It never spun (the 30-minute cooldown bounded it). IT JUST DRIFTED. Each pass took her
    conclusions as fresh input and concluded something about them, and from the outside that
    reads as "the model has got a bit weird lately" — which is unfalsifiable, gets blamed on
    the weights, and is nearly impossible to see from a transcript.

    DERIVING A BELIEF FROM EVIDENCE MUST NOT CREATE EVIDENCE.

    Evidence is what HE said and what the WORLD did. Never what SHE concluded. A system whose
    inferences re-enter its own input is not learning, it is compounding — and the only thing
    that compounds is its own certainty.

    (The same shape as `_capture_after_turn` storing tool RESULTS as facts about him — she ate
    her own exhaust. It is the third time this exact loop has appeared in this codebase, which
    is why it gets a named rule rather than a fix.)
    """
    try:
        from harness.skills.memory import _load
        return sum(1 for r in _load() if _is_evidence(r))
    except Exception:
        return -1


def _is_evidence(row: dict) -> bool:
    """Is this row something the WORLD told her, or something SHE decided?

    ── src IS AN AUDIT TRAIL, NOT A CLAIM STATUS, AND I NEARLY SHIPPED A GATE THAT TRUSTED IT ──
    My first cut tested `src not in ("reflection", "insight")`. It passed — because exactly ONE
    row in the live store happens to have src EXACTLY "reflection". Here is what src actually
    holds:

        'user turn'                                     30
        'rescued from ep_live_m1783826444872'            1
        'user turn | repair: un-retired (2026-07-12)'    1
        ' | cleanup: stamped speaker=user'               9
        'reflection'                                     1

    It is FREE-TEXT PROVENANCE PROSE that gets appended to over time. The moment a reflection row
    is touched by a cleanup pass it becomes "reflection | cleanup: ...", the exact-match fails,
    and the row silently becomes EVIDENCE again — reopening the self-feeding loop this function
    exists to close. The gate would not error. It would just quietly stop working, months later,
    because of a maintenance script.

    So: check the STRUCTURED field (speaker) first, and treat src as a fuzzy hint, not a key.
    A field that is a paragraph is not a field you can branch on.

    (This is why the store needs a real claim status — candidate/observed/inferred/confirmed —
    as a first-class enum, instead of inferring epistemics from prose. Filed as its own task;
    this is the hardening that makes today's fix survive until then.)

    ── THAT TASK IS DONE, SO THE PROSE-SNIFF IS NOW THE FALLBACK, NOT THE TEST (2026-07-14) ──
    `status` exists. It is written at stamp() time from the authoring path, it cannot be mangled
    by a maintenance script appending to a provenance string, and it is what this function should
    always have been reading. The src sniff stays ONLY to classify legacy rows written before the
    field existed — it is now a migration shim with an expiry date, not the mechanism.

    AND A TOMBSTONE IS NOT NEWS. This is what the sweep for the recall-seam bug turned up here:
    the evidence count included RETIRED rows, so a fact he corrected still counted as a fresh
    reason to go and think about him. Superseded is superseded — on this path too.
    """
    # ── Tier 1.3: this is a σ PROJECTION now (verdict.is_evidence) ──────────────────────
    # Everything the history above argues — the structured field wins, the src sniff is a
    # migration shim for pre-status rows only, a tombstone is not news — lives in ONE
    # place: lifecycle.status_of (the one normalization) + verdict.sigma. This function
    # had its own copy of the shim, and the seam had NONE — a legacy reflection row was
    # a conclusion here and testimony at the seam. One law now; G-SEM-PROJ holds it.
    from harness.skills import verdict as _v
    return _v.is_evidence(row)


def reflect_tick(now: Optional[float] = None) -> Optional[dict]:
    """Think about him, quietly. Returns an insight worth SAYING, or None (usually None)."""
    global _LAST_REFLECT_AT, _LAST_EVIDENCE
    from harness.tuning import registry as tune
    if not bool(tune.get("reflect.enabled")):
        return None

    now = now if now is not None else time.monotonic()
    idle_s = float(tune.get("reflect.idle_s"))
    cool_s = float(tune.get("reflect.cooldown_s"))

    with _LOCK:
        # the room must be still — reflection is a whole model turn and must never race him
        # for the GPU while he is mid-sentence
        last_user = max((st.last_user_at for st in _STATE.values()), default=0.0)
        if not last_user or (now - last_user) < idle_s:
            return None
        if _LAST_REFLECT_AT and (now - _LAST_REFLECT_AT) < cool_s:
            return None
        ev = _evidence_count()
        if ev == _LAST_EVIDENCE:
            return None                       # nothing new to think ABOUT
        _LAST_REFLECT_AT, _LAST_EVIDENCE = now, ev

    try:
        from harness.maintenance import ops
        from harness.model.person import PersonModel
        res = ops.insight()
    except Exception as exc:
        logger.warning("[kairos] reflection failed: %s", exc)
        return None

    # 1. HAS SOMETHING GONE QUIET? The neighbour who did not wave carries more information
    #    than the one who did, and noticing it is not retrieval — nobody asked a question.
    try:
        pm = PersonModel.from_registry()
        sil = pm.silences()
        # STRUCTURAL HERE TOO. This was `bits >= reflect.speak_bits`, an invented constant
        # deciding whether an absence was worth a question. The structural admission was
        # already sitting in silences() and doing the real work — at least three mentions,
        # seen across at least two attended days, cadence floored at a day, and (since
        # 2026-08-01) never an identity fact. What remains to ask is simply whether the
        # expectation those conditions established has actually been VIOLATED: has he been
        # quiet for longer than his own rhythm on this topic? That is a comparison between
        # two measured quantities rather than a threshold over one, so it needs no number
        # of mine, and it means what it says. bits still ORDERS them — silences() returns
        # them strongest-first — so she raises the loudest absence, or none.
        if sil and sil[0]["quiet_days"] > sil[0]["cadence_days"]:
            logger.info("[kairos] reflection: a silence worth asking about "
                        "(quiet %.1fd vs his own cadence %.1fd, %.1f bits)",
                        sil[0]["quiet_days"], sil[0]["cadence_days"], sil[0]["bits"])
            return {"text": sil[0]["claim"], "bits": sil[0]["bits"], "silence": sil[0]}
    except Exception:
        pass

    # 2. Otherwise: did she CONCLUDE anything, and was it surprising enough to interrupt for?
    # ops.insight() returns structured receipts ({"claim", "result"}) as of 2026-08-19.
    # The old receipt was the display string `f"{line[:60]} -> {res[:38]}"`, and this
    # function recovered the claim with split(" -> ")[0] — i.e. THE FIRST 60 CHARACTERS.
    # Insights are full sentences starting "Sam " and routinely longer, so _covered()
    # compared a truncated fragment against full stored rows, matched nothing, and the
    # structural admission gate below NEVER FIRED for exactly the insights long enough
    # to need it. The claim rides whole now; truncation is for logs only.
    wrote = res.get("wrote") or []
    if not wrote:
        logger.info("[kairos] reflected — nothing new concluded")
        return None
    # a REINFORCED belief is one she already held; it is stronger now, but it is not NEWS
    fresh = [w["claim"] for w in wrote
             if isinstance(w, dict) and w.get("result", "").startswith("stored")]
    if not fresh:
        logger.info("[kairos] reflected — only re-derived what she already believed")
        return None

    # ── ADMISSION IS STRUCTURAL. SURPRISAL ONLY RANKS. (2026-08-01) ──────────────────
    # This was `if surprisal(text) < reflect.speak_bits: stay quiet`, and re-measuring it
    # against the cleaned model showed no value of that floor can work:
    #
    #     8.00 bits  "quantum bicycle marmalade thinks sideways"      <- word salad
    #     2.17 bits  "Sam would rather build the tool than use one" <- a fair insight
    #
    # Junk outscores insight BY CONSTRUCTION: I(x) = -log2 p(x|model), so a sentence built
    # from words the store has never seen has p -> 0 and is maximally "surprising". The
    # metric measures lexical novelty, which is a perfectly good RANK and an unsound
    # VERDICT — and INVARIANT-MEMORY.md:30 already said so: "anything built on magnitudes
    # is a preference, never a verdict."
    #
    # So the gate becomes structure, out of the vocabulary this store already rules with:
    #
    #   NEW      — `fresh` above: `remember()` said "stored", not "reinforced". A belief
    #              she already held is stronger tonight, but it is not news.
    #   UNCOVERED — verdict.competition(): the same committed ruling the recall seam uses
    #              to keep a covered inference home. If HIS OWN WORDS already speak to it,
    #              she is not telling him anything; she is repeating him back to himself
    #              with "I've come to think" on the front.
    #
    # Surprisal keeps its job, which is to ORDER the admitted: when reflection produced
    # more than one new conclusion, the more novel of them is the one worth the turn.
    from harness.skills import memory as _M
    from harness.skills import verdict as _V

    # THE ONE READ SEAM (2026-08-21, the last holdout). This loaded the raw registry
    # and re-implemented the tombstone predicate inline (a bare lifecycle test) —
    # the private-predicate pattern AGENTS.md §3 retired everywhere else on 2026-08-19.
    # memory.live_rows() is the one place that knows what "live" means; a third
    # spelling of it here would be the next row to drift.
    try:
        rows = _M.live_rows()
    except Exception:
        rows = []

    def _covered(t: str) -> bool:
        # The stored row holds lc.normalize_fact(claim), so the lookup must compare the
        # same normalization — a raw==stored comparison silently never matches a claim
        # the normalizer touched, and this gate then never fires (the 60-char truncation
        # fixed above was the bigger half of the same silent-miss).
        from harness.skills import lifecycle as _lc
        tn = _lc.normalize_fact(t).strip()
        row = next((r for r in rows
                    if (r.get("text") or "").strip() in (t, tn)), None)
        if row is None:
            return False
        try:
            return _V.competition(row, rows) == "1"
        except Exception:
            return False

    pm = PersonModel.from_registry()
    # THE CEILING IS HIS OWN VOCABULARY. A conclusion about him may be no more exotic than
    # the way he talks — beyond that it has stopped being an inference and become an
    # invention, which is the failure this system actually had ("Sam is terrified of
    # being truly known and left alone", from nothing he ever said). Self-calibrating, so
    # there is no constant of mine sitting under a measurement.
    try:
        ceiling = pm.vocabulary_ceiling(float(tune.get("reflect.speak_pct")))
    except Exception:
        ceiling = 8.0

    admitted = []
    for t in fresh:
        t = t.strip()
        if not t:
            continue
        if _covered(t):
            logger.info("[kairos] kept it to herself — his own words already speak to it: %r",
                        t[:60])
            continue
        try:
            g = pm.groundedness(t)
        except Exception:
            g = 0.0
        if g > ceiling:
            logger.info("[kairos] kept it to herself — further from his words than he "
                        "ever gets (%.2f > %.2f): %r", g, ceiling, t[:60])
            continue
        admitted.append((g, t))
    if not admitted:
        return None
    # RANK, NOT RULE: among conclusions that are all grounded enough to say, the one that
    # travels furthest from what he has already said is the one worth the turn.
    admitted.sort(key=lambda x: -x[0])
    bits, text = admitted[0]
    logger.info("[kairos] reflection worth saying (%.2f bits, ceiling %.2f, best of %d): %r",
                bits, ceiling, len(admitted), text[:60])
    return {"text": text, "bits": bits}


def _watch_tick() -> None:
    """SHE ACTUALLY LOOKS. On the same clock she thinks on.

    "I will look out for a 3090 GPU to be available."  — and then nothing looked.

    This is what makes that sentence true. A watch that fires becomes an ordinary due
    reminder, so it arrives through the path that is already gated and already bounded: she
    tells him once, with the evidence, and does not nag. The promise and the keeping of it
    now run on the same rails as every other promise she makes."""
    try:
        from harness.skills import watch as W
        due = W.due_checks()
        if not due:
            return
        note = due[0]                       # one per tick: this costs a search and a turn
        res = W.check(note)
        if res.get("fired"):
            # A FIRED WATCH IS A DUE REMINDER. Give it a due date of NOW and the existing
            # REMIND path — bounded, once, with a reason — carries it the rest of the way.
            from harness.skills import notes as N
            N.update(note["id"], due_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                     raised=False)
            logger.info("[watch] %r fired — it is now a due reminder", note.get("title"))
    except Exception as exc:
        logger.warning("[watch] tick failed: %s", exc)


def _due_notes() -> list:
    """Reminders that have come due and have not been raised yet. Kept out of impulse.py so
    the policy stays pure and gateable without a store."""
    try:
        from harness.skills import notes as N
        return N.due()
    except Exception:
        return []


def _arm(session, imp, reply_text, generate, margin, notes=None, insight=None) -> None:
    """Wait the delay, generate, and let worth_saying() have the last word."""
    def _fire():
        # "NOTHING NEW STARTS" IS ENFORCED HERE TOO (2026-08-19). app.py's _sd_turn_start
        # docstring claims to be where that rule lives — and it guarded the two HTTP
        # paths while THIS, the third path that reaches the model, checked only
        # user_turn_active(): a timer armed before quiesce() could fire a full
        # generation INTO stop_daemon, uncounted by _IN_FLIGHT so finish_or_abandon
        # returned immediately. The same guard, and the same counter, or the ladder
        # waits on two of three mouths.
        from harness.control import shutdown as _sd
        if _sd.is_shutting_down():
            logger.info("[kairos] impulse dropped — the stack is shutting down")
            return
        _sd.note_turn_start()
        try:
            _fire_inner()
        finally:
            _sd.note_turn_end()

    def _fire_inner():
        _mode_meta = None                      # set only on a MODE_TURN (presence modes)
        _mode_sampling, _mode_max = None, None
        # the CONTINUE nudge is built from the reply so she can see WHERE she was cut —
        # without the tail she just restates the whole thing and worth_saying() drops it.
        if imp.action == CONTINUE:
            # 16:56 and 17:09: she streamed a planning scratchpad, kairos read
            # margin < 0 ("cut off mid-thought") and kept the GPU at 98% finishing
            # a thought that was never speech. A scratchpad is not a cut-off reply.
            try:
                from harness.agent import _looks_like_scratchpad
                if _looks_like_scratchpad(reply_text or ""):
                    logger.info("[kairos] continue dropped — that was planning, not a cut-off thought")
                    return
            except Exception:
                pass
            nudge = continue_nudge(reply_text)
        elif imp.action == EXPAND:
            # NOT continue_nudge: that hands her a severed tail to resume, and this
            # sentence was finished. See expand_nudge.
            nudge = expand_nudge(reply_text)
        elif imp.action == REMIND:
            nudge = remind_nudge(notes or [])
        elif imp.action == MUSE:
            nudge = muse_nudge(insight or {})
        elif imp.action == SOLO:
            # ROTATED. A menu became a loop: 15 of her first 21 own-time turns were
            # 'I read my journal', because that option needed no tool and could not
            # fail. The counter is the state's own solo count, so the rotation is
            # deterministic and testable rather than a random draw.
            nudge = solo_nudge(_STATE[session].solo_n)
        elif imp.action == MODE_TURN:
            # ── A PRESENCE MODE'S TURN (2026-08-22): narration / company / lucid ───────
            if str(tune.get("presence.mode") or "off") == "off":
                logger.info("[kairos] mode turn dropped — the mode was switched off while it waited")
                return
            # The register is his prompt block; the cue is his hint or an assembled one
            # (hour, mood, her own time, the book in hand); a reading turn hands her the
            # next passage of the book she has picked up. Aux models never speak here.
            from harness.kairos import presence as _pm
            from harness.skills import library as _lib
            _mode = imp.mode or str(tune.get("presence.mode") or "narration")
            _intimate = bool(tune.get("presence.intimate"))
            _cue = str(tune.get("presence.cue") or "").strip()
            try:
                _book = _lib.in_hand()
            except Exception:
                _book = None
            _passage, _title = None, ""
            if _mode in ("narration", "lucid") and _book and not _book.get("done"):
                try:
                    _rc = float(tune.get("presence.read_chance"))
                except Exception:
                    _rc = 0.35
                if random.random() < _rc:
                    try:
                        _passage = _lib.next_passage(int(tune.get("presence.read_chunk_chars") or 700)) or None
                    except Exception:
                        _passage = None
                    _title = _book["title"]
            if not _cue:
                _mood = ""
                try:
                    from harness.personality.persona_file import parse_persona as _pp
                    from harness.personality.interceptor import _persona_path as _ppath
                    with open(_ppath(), encoding="utf-8") as _f:
                        _, _pstate = _pp(_f.read())
                    _mood = (_pstate.get("mood") or "").strip()
                except Exception:
                    pass
                try:
                    from harness.skills import narrative as _nar
                    _own = _nar.own_time(1)
                except Exception:
                    _own = []
                _about = ""
                if _book:
                    try:
                        _about = _lib.about_so_far()
                    except Exception:
                        _about = ""
                _cue = _pm.assemble_cue(mood=_mood, own_time=_own,
                                        book=({"title": _book["title"], "about": _about} if _book else None))
            try:
                _len = int(tune.get("presence.len_%s" % _mode) or 0)
            except Exception:
                _len = 0
            _mode_sampling = dict(_pm.SAMPLING[_mode])
            _mode_max = (_len or int(_mode_sampling.pop("max_tokens", 140))) + (60 if _passage else 0)
            _mode_sampling.pop("max_tokens", None)
            _mode_sampling["seed"] = random.randrange(1, 2 ** 31)        # a fresh sampler state per turn
            with _LOCK:
                _n = _STATE[session].mode_n
            _last_text = _LAST_MODE_TEXT.get(session, "")
            nudge = _pm.mode_nudge(_mode, cue=_cue, intimate=_intimate, passage=_passage, title=_title,
                                   beat=_pm.beat_for(_mode, _n), last=_last_text,
                                   words=int(_mode_max * 0.7))
            _mode_meta = {"mode": _mode, "reading": bool(_passage), "title": _title}
        else:
            nudge = CHECK_IN_NUDGE
        # HE IS TALKING. Checked HERE rather than at arm time because the wait is the
        # whole point of the delay — he may well have started typing during it, and the
        # impulse that made sense when it was armed is the one most likely to land on top
        # of him. Dropped, not deferred: see the note at _USER_TURN_DEPTH.
        if user_turn_active():
            logger.info("[kairos] impulse dropped — his turn is in flight")
            return
        # ── HIS QUIET IS THE CLOCK (2026-08-20, operator's rule) ─────────────────────
        # checkin_idle_s measures the SESSION's quiet, which includes her own speech —
        # so she could ping, wait out her cooldown, and ping again with him gone the
        # whole time (measured this morning: check_in 10:11:07, muse 10:11:55). This
        # gate measures HIM: no discretionary speak-up until at least
        # kairos.quiet_after_him_s since HE last said anything, in ANY session.
        # 0 = off. Reminders and her own time are deliberately not gated.
        # quiet-after-him is decided in the POLICY now (impulse.decide, 2026-08-22) —
        # peek_state, the log line and what fires all agree; nothing is dropped here.
        if imp.action != REMIND:
            try:
                from harness.kairos import offload as _offload
                if _offload.pregate(imp.action, imp.reason, reply_text or "") is False:
                    try:
                        _speech.record(imp.action, _speech.DROPPED,
                                       "sidecar pre-judge: nothing new to add", "")
                    except Exception:
                        pass
                    return
            except Exception:
                pass                       # the gate must never break her own time
        # ── DID SHE ACTUALLY DO IT (2026-08-06) ──────────────────────────────────────
        # 33 solo turns in the log; ONE called a tool. Six of the eight acts name the tool
        # they need, and the nudge asks for the artefact rather than the act — "say what
        # you found, NOT that you searched" — so she wrote up research she had not done,
        # into her own journal, for weeks. `called` is her hands, reported back by
        # _generate; `solo_did_the_thing` is the ruling.
        called: list = []
        try:
            if imp.action == MODE_TURN:
                try:
                    text = generate(nudge, None, sampling=_mode_sampling, max_tokens=_mode_max) or ""
                except TypeError:           # a closure that predates the sampling kwargs
                    text = generate(nudge) or ""
            else:
                text = (generate(nudge, called) if imp.action == SOLO
                        else generate(nudge)) or ""
            text = text.strip()
        except TypeError:
            # A caller that predates the `called` parameter. Her own time then has no
            # evidence to rule on, and the gate below fails OPEN rather than silencing
            # her — an unproven turn is a worse outcome than an ungated one.
            called = None
            try:
                text = (generate(nudge) or "").strip()
            except Exception as exc:
                logger.warning("[kairos] continuation failed: %s", exc)
                return
        except Exception as exc:                      # never let a continuation break the app
            logger.warning("[kairos] continuation failed: %s", exc)
            return
        # ── AN ATTEMPT CONSUMES THE CLOCK, SPOKEN OR NOT (2026-08-20 12:56) ──────────
        # Live loop, caught by the A/B monitor: solo generated ~2.5 min of 26B, dropped
        # ("she did not feel like anything after all"), and the tick re-proposed solo
        # FIVE SECONDS later — because last_solo_at moves only in note_spoke, and a
        # dropped turn never gets there. Same shape as the 10:34-10:40 check-in loop
        # (cooldown_s reads last_spoke_at, same gap). The GPU cost is paid at
        # generate(), so the pacing clocks advance at generate() — attempts are what
        # the budget must meter. ONLY the clocks: chain / unanswered / spoken_times /
        # solo_n are speech facts and still move in note_spoke, on speech alone.
        with _LOCK:
            _st_now = _STATE[session]
            _st_now.last_spoke_at = time.monotonic()
            if imp.action == SOLO:
                _st_now.last_solo_at = time.monotonic()

        # ONE RE-ASK, THEN REFUSED. The correction is specific — it names the tool and
        # says the writing-up is the second half — because "try again" taught her nothing
        # the last nine times this repo said it. If she still will not reach for it, the
        # turn does not happen: it is not spoken and it is not written to her journal,
        # which is the whole point. A journal that records things she did not do is worse
        # than no journal, and this one has been doing it since the day it was written.
        if imp.action == SOLO and called is not None:
            ok_did, why_did = solo_did_the_thing(_STATE[session].solo_n, called)
            if not ok_did:
                need = solo_needs(_STATE[session].solo_n)
                logger.info("[kairos] solo: %s — asking once more", why_did)
                retry = (nudge + "\n\n(You wrote that up without doing it. CALL %s FIRST — "
                         "one fenced tool_code block, nothing else — and then say what came "
                         "of it in your own words. If you do not want to do this one, say "
                         "nothing at all; that is allowed and inventing it is not.)"
                         % " or ".join(need))
                called2: list = []
                try:
                    text = (generate(retry, called2) or "").strip()
                except Exception as exc:
                    logger.warning("[kairos] solo retry failed: %s", exc)
                    return
                ok_did, why_did = solo_did_the_thing(_STATE[session].solo_n, called2)
                if not ok_did:
                    logger.info("[kairos] solo REFUSED — %s (asked twice)", why_did)
                    try:
                        _speech.record(imp.action, _speech.DROPPED,
                                       "claimed an act it never performed", text)
                    except Exception:
                        pass
                    return

        # A REMINDER IS NOT SUBJECT TO worth_saying(). That gate exists to let her decide,
        # after thinking, that she had nothing worth saying — and that freedom is right for
        # a continuation or a check-in. It is WRONG here: he asked to be reminded, and a
        # reminder she talked herself out of is a broken promise that looks exactly like a
        # bug. She still chooses the words; she does not get to choose silence.
        # HER OWN TIME HAS ITS OWN LAST GATE. worth_saying() judges whether a
        # continuation ADDS anything; this judges whether a solo turn is actually
        # hers, which is a different question and the one the nudge kept losing.
        if imp.action == SOLO:
            ok_solo, why_solo = solo_worth_saying(text)
            if not ok_solo:
                logger.info('[kairos] solo dropped — %s', why_solo)
                return
        if imp.action == MODE_TURN:
            from harness.kairos import presence as _pm2
            text = _pm2.finish(_pm2.trim_question(text))   # never mid-line; never a question
        if imp.action == MODE_TURN and not (_mode_meta and _mode_meta["reading"]):
            # a mode turn is judged against her LAST MODE TURN, not his reply — the 05:15 dream
            # repeated the 05:02 one word for word; that is the restatement this rule exists for
            ok, why = worth_saying(text, _LAST_MODE_TEXT.get(session, "") or reply_text)
            if not ok:
                _speech.record(imp.action, _speech.DROPPED, why, text)
                logger.info("[kairos] mode turn DROPPED: %s :: %r", why, text[:60])
                return
        elif imp.action != REMIND and not (imp.action == MODE_TURN and _mode_meta and _mode_meta["reading"]):
            ok, why = worth_saying(text, reply_text)
            if not ok:
                # RECORDED, not just logged. This drop is her voice going somewhere, and
                # until now it went into an INFO line and was forgotten — so nobody could
                # answer whether these rules are a backstop or a crutch, which
                # CONTINUITY.md §7 raises and cannot test. speechlog keeps the reason AND
                # the text, because "did that rule eat a real thought?" is not a question
                # a tally can answer.
                _speech.record(imp.action, _speech.DROPPED, why, text)
                logger.info("[kairos] DROPPED: %s :: %r", why, text[:60])
                return
        elif not text:
            # she produced nothing at all — say it plainly rather than drop the promise
            titles = ", ".join((n.get("title") or "") for n in (notes or [])[:3])
            text = f"Reminder: {titles}."

        # AND THE DENOMINATOR. A veto count with nothing to divide by is a number that
        # will be misread: twelve drops is excellent out of two hundred and catastrophic
        # out of thirteen. Both outcomes, one shape, so the ratio is computable.
        _speech.record(imp.action, _speech.SPOKE, imp.reason, text)

        with _LOCK:
            # THE ACTION MATTERS: only the things that asked him for something count
            # toward `unanswered`. See note_spoke.
            note_spoke(_STATE[session], time.monotonic(), imp.action)
            # ── SHE MUST KNOW SHE ALREADY SAID IT (2026-08-03) ────────────────────────
            # `_LAST` was written only by on_reply and seed — HIS turns. An unprompted
            # message never updated it, so the next impulse generated against the same
            # stale context and produced the same words. Measured in speech.jsonl: the
            # same check-in SPOKEN twice 3m44s apart, and one line spoken FOUR times
            # across two hours — worth_saying compares against the previous reply, and
            # the previous reply it was shown never moved. Not the poller, not
            # StrictMode: she genuinely did not know she had spoken.
            #
            # The closure is reused as-is; only the text it is compared against and
            # continued from advances.
            _old = _LAST.get(session)
            if _old is not None:
                _LAST[session] = (text, _old[1])
            # ── AND IT HAS TO BE WRITTEN DOWN (2026-08-03) ────────────────────────────
            # Advancing `_LAST` fixed what she is COMPARED against and not what she is
            # GENERATED from: the closure holds the history it was seeded with, frozen, so
            # every impulse ran against the same context — and both speak-up paths generate
            # at temperature 0.0. Greedy decoding on identical context returns identical
            # text, which is exactly what his transcript shows: "I watch you for a moment,
            # my expression unreadable, just letting the silence settle between us like
            # it's something..." twice, diverging only at word sixteen — far enough apart
            # for worth_saying to wave it through, close enough that he read it as a stuck
            # record.
            #
            # Nothing was recording her unprompted turns at all. Eighteen rows in today's
            # transcript, every one of them a reply to something he typed; the four times
            # she spoke first exist nowhere. So she could not remember having spoken, the
            # anti-repeat ban had nothing to ban, and tonight's journal would be written
            # from a day with her side of it missing.
            #
            # The gateway owns the transcript, not the scheduler — so it registers a
            # writer here. One hook, called at the one point every impulse converges on.
            if _ON_SPOKE is not None:
                try:
                    _ON_SPOKE(text)
                except Exception as exc:
                    logger.warning("[kairos] could not record what she said: %s", exc)
            if imp.action == MODE_TURN and _mode_meta:
                from harness.kairos import presence as _pm3
                _LAST_MODE_TEXT[session] = text            # what she said this time (anti-repeat)
                text = _pm3.wrap_for_voice(_mode_meta["mode"], text)
            _OUTBOX[session].append({
                "text": text,
                "kind": ("mode" if imp.action == MODE_TURN else imp.action),
                "mode": (_mode_meta or {}).get("mode", "") if imp.action == MODE_TURN else "",
                "speak": (bool(tune.get("presence.voice")) if imp.action == MODE_TURN else True),
                "reason": imp.reason,
                "margin": margin,
                "notes": [n.get("id") for n in (notes or [])],
                "at": time.time(),
            })

        # HER OWN TIME GOES IN HER OWN JOURNAL. Written only AFTER it survived
        # worth_saying and reached the outbox, for the same reason the reminder below is
        # marked here: a turn that was dropped for being empty or a restatement did not
        # happen, and a journal that records things she did not do is worse than no
        # journal. The chat log keeps it too — but he has to scroll for that, and SHE
        # cannot read a chat log back at all. This is the copy that is hers.
        # ── THE REAL HER (2026-08-22): what she actually said, unprompted, is memory. ──
        # After the outbox append, never before: only a DELIVERED utterance is hers to
        # keep (worth_saying / solo_worth_saying / the pregate drop above all returned
        # already). producer "kairos.speak" (memclass REGISTRY).
        if imp.action == MODE_TURN and _mode_meta:
            # a mode turn is her narrative by its KIND (presence.memory_kind); a reading turn
            # keeps the ACT, never the passage — the line she added after it, or a plain one
            try:
                from harness.skills import memory as _mem
                from harness.kairos import presence as _pm4
                from harness.skills.self_stance import plain as _plain_words
                _plain = _plain_words(text)
                if _mode_meta["reading"]:
                    _keep = "I read him the next pages of %s." % (_mode_meta.get("title") or "the book")
                else:
                    _keep = _plain
                _mem.remember_about_self(_keep, kind=_pm4.memory_kind(_mode_meta["mode"], reading=_mode_meta["reading"]),
                                         source="she was %s" % _mode_meta["mode"])
            except Exception as exc:
                logger.warning("[kairos] could not keep her mode turn: %s", exc)
        elif imp.action != REMIND:
            try:
                from harness.skills import memory as _mem
                from harness.skills.self_stance import plain as _plain_words2
                _mem.remember_about_self(
                    _plain_words2(text), kind=("narration" if imp.action == SOLO else "spoke_up"),
                    source="she spoke unprompted (%s)" % imp.action)
            except Exception as exc:
                logger.warning("[kairos] could not keep what she said: %s", exc)
        if imp.action == SOLO:
            try:
                from harness.skills import narrative as _nar
                from harness.skills.self_stance import plain as _plain_j
                _nar.note_own(_plain_j(text), kind="solo")   # her journal reads her WORDS
            except Exception as exc:
                logger.warning("[kairos] could not write her own-time note: %s", exc)

        # SHE REMINDS; SHE DOES NOT NAG. Marked only AFTER it actually reached the outbox,
        # so a reminder that failed to generate is still owed and will fire on a later tick.
        if imp.action == REMIND:
            try:
                from harness.skills import notes as N
                for n in (notes or []):
                    N.mark_raised(n.get("id"))
            except Exception as exc:
                logger.warning("[kairos] could not mark reminder raised: %s", exc)

        logger.info("[kairos] SPOKE (%s): %r", imp.action, text[:70])

    with _LOCK:
        # CANCEL WHAT WE OVERWRITE. tick_once guards this slot; on_reply's path did not,
        # so a second _arm inside the delay window orphaned the first Timer — which
        # still fired, off the books, no longer reachable by cancel.
        old = _TIMERS.pop(session, None)
        if old:
            old.cancel()
        t = threading.Timer(imp.delay_s, _fire)
        t.daemon = True
        _TIMERS[session] = t
        t.start()


# ── THE IDLE TICK (2026-07-12) ────────────────────────────────────────────────
# CHECK_IN was unreachable code. decide() has a whole branch for it — "the room has been
# quiet a long time" — and the only caller of decide() was on_reply(), which fires the
# instant a reply is produced, i.e. moments after HE spoke. So `idle = now - last_user_at`
# was always ~0, and `idle >= checkin_idle_s` (240s) could never be true. The knobs were on
# the operator panel; the policy was gated pure and correct; the branch could not run.
#
# That is the "she ticks turns noop" the operator named at the outset: the system had a
# heartbeat everywhere except where it needed one. Silence is not an event, so nothing
# generated it — and a thing that can only act when spoken to cannot notice a quiet room.
# It needs a clock of its own.
#
# The tick is cheap: it asks the POLICY, not the model. It reaches the model only if the
# policy says speak — and the policy says SILENT almost always (240s of quiet, then a 35%
# roll, then the cooldown, the hourly cap and the chain limit all still apply).
def tick_once(now: Optional[float] = None) -> None:
    cfg = live_config()
    if not cfg.enabled:
        return
    now = now if now is not None else time.monotonic()

    # SHE LOOKS AT THE WORLD FOR HIM. due_checks() is cheap and network-free; it only
    # reaches the web when a watch is actually stale (every 6h by default), so this costs
    # nothing on the overwhelming majority of ticks.
    _watch_tick()

    due = _due_notes()          # THE CLOCK IS WHAT MAKES A REMINDER POSSIBLE AT ALL.

    # SHE THINKS ON THE SAME CLOCK SHE SPEAKS ON, but they are not the same act. reflect_tick
    # writes what she concludes into the store REGARDLESS; it returns something here only on
    # the rare occasion the conclusion was surprising enough to be worth interrupting him
    # for. Most reflections end in her simply knowing something new and saying nothing.
    insight = None
    try:
        insight = reflect_tick(now)
    except Exception as exc:
        logger.warning("[kairos] reflect_tick: %s", exc)

    # ── A THOUGHT SHE HAD IS NOT THROWN AWAY BECAUSE THE TIMING WAS WRONG ────────────
    # reflect_tick() latches _LAST_REFLECT_AT and _LAST_EVIDENCE the moment it runs, so a
    # conclusion that arrived while decide() happened to say SILENT — cooldown, chain
    # limit, a stale question — was destroyed, and the 1800 s cooldown guaranteed it would
    # never be recomputed. Measured on 2026-08-01: she spoke at 20:41:52, a 4.0-bit
    # reflection landed twelve seconds later, and it went in the bin.
    #
    # _PENDING_INSIGHT was declared for exactly this and referenced nowhere in the tree.
    # Wiring it: a thought waits for its moment instead of dying at it.
    #
    # It does not wait indefinitely — an observation about him from two hours ago,
    # delivered cold, is worse than silence. One reflect cooldown is its shelf life,
    # which is the same clock that decides how often she is allowed to think at all.
    if insight:
        _PENDING_INSIGHT.clear()
        _PENDING_INSIGHT.update(insight, _at=now)
    elif _PENDING_INSIGHT:
        age = now - float(_PENDING_INSIGHT.get("_at") or 0.0)
        try:
            shelf = float(tune.get("reflect.cooldown_s"))
        except Exception:
            shelf = 1800.0
        if age > shelf:
            logger.info("[kairos] a held thought went stale unspoken (%.0fs): %r",
                        age, str(_PENDING_INSIGHT.get("text", ""))[:60])
            _PENDING_INSIGHT.clear()
        else:
            insight = {k: v for k, v in _PENDING_INSIGHT.items() if k != "_at"}

    # ── AND IF SHE HAS NOT CONCLUDED ANYTHING, SHE MAY STILL HAVE A REASON ───────────
    # Reflection is one source of something-worth-saying and it is the rarest: it needs
    # new evidence, an idle room, a 1800 s cooldown and 3.0 bits. Everything else she
    # knows — what is still open between them, what she wrote in her journal last night,
    # how his week is going — was computed daily and consulted by nobody, which is why
    # the only impulse that ever reached him was a coin flip on a timer.
    #
    # LAST, deliberately. A conclusion she reached tonight outranks a thing she has been
    # carrying for a week; and a reason must never displace a held insight that is still
    # waiting for its moment.
    if not insight:
        try:
            from harness.kairos import reasons as _R
            insight = _R.propose()
            if insight:
                logger.info("[kairos] a reason to speak: %s — %r",
                            insight.get("kind"), str(insight.get("text", ""))[:70])
        except Exception as exc:
            logger.warning("[kairos] reasons: %s", exc)

    with _LOCK:
        sessions = list(_LAST.items())
    if not sessions and cfg.presence_mode and cfg.presence_mode != "off":
        if _seed_for_presence():
            with _LOCK:
                sessions = list(_LAST.items())
    for session, (reply_text, generate) in sessions:
        with _LOCK:
            st = _STATE[session]
            if _TIMERS.get(session) and _TIMERS[session].is_alive():
                continue                       # she is already about to say something
            imp = decide(cfg=cfg, state=st, now=now,
                         reply_text=reply_text, eot_margin=None, due_notes=due,
                         insight=insight)
        if not imp.speaks:
            continue
        logger.info("[kairos] session=%s idle tick -> %s (%s)", session, imp.action, imp.reason)
        _arm(session, imp, reply_text, generate, None,
             notes=due if imp.action == REMIND else None,
             insight=insight if imp.action == MUSE else None)
        if imp.action == MUSE:
            _PENDING_INSIGHT.clear()       # spoken — it is no longer waiting for a moment
            if (insight or {}).get("raise_key"):
                # She raises a thing ONCE. Marked here rather than after she speaks: the
                # cost of marking early is a reason occasionally lost when she decides she
                # had nothing to say, and the cost of marking late is saying it twice.
                try:
                    from harness.kairos import reasons as _R
                    _R.mark_raised(insight["raise_key"])
                except Exception as exc:
                    logger.warning("[kairos] could not mark a reason raised: %s", exc)
                # ── AND THE WARDROBE'S OWN "SHE HAS BEEN TOLD" (2026-08-05) ──────────
                # `raised` is the kairos guard and it is enough to stop her saying it
                # twice. But the wardrobe keeps the same fact for its own surfaces —
                # the panel says "she has not been told yet" beside a new arrival — and
                # only my_looks() was ever setting it. So an item she had just been
                # ANNOUNCED still read as un-announced until she happened to list her
                # looks. One event, two records, and the second was never written.
                if (insight or {}).get("kind") == "arrival" and insight.get("id"):
                    try:
                        from harness.control import wardrobe as _WDm
                        _WDm.mark_seen(insight["id"])
                    except Exception as exc:
                        logger.warning("[kairos] could not mark an arrival told: %s", exc)
        if imp.action in (REMIND, MUSE):
            break              # one session hears it, not every open tab


def start_ticker(period_s: Optional[float] = None) -> None:
    """One clock for the whole gateway. Idempotent.

    ── THE HEARTBEAT IS A KNOB NOW (2026-07-31) ──────────────────────────────────────
    It was a hardcoded 15.0 s default that the one call site (`app.py: _ks.start_ticker()`)
    never overrode, so the number could not be changed without an edit — the same shape as
    every other dial this week that turned out to be unreachable.

    THE PERIOD IS RE-READ EVERY ITERATION, not captured in the closure. Reading it once
    would have made this a restart-scoped knob wearing a live knob's clothes, and
    `G-KNOBS` §2 exists precisely to reject that pattern. Now moving the slider takes
    effect on the next beat.

    WHAT THE PERIOD ACTUALLY BOUNDS: this is the RESOLUTION of every kairos decision, not
    a rate limit — the limits are cooldown_s, checkin_idle_s and max_per_hour, and they are
    checked on the beat. So the two cases it affects differ:

      CONTINUE (she was cut off mid-thought)  latency-sensitive. At 15 s she picks the
                                              thread back up within 15 s; at 60 s it can
                                              take a minute, which reads as her having
                                              let it go.
      CHECK-IN (the room went quiet)          not sensitive at all. The gate is 240 s of
                                              idle, so a 60 s beat costs nothing.

    An explicit `period_s` still wins, for tests that want a fast deterministic clock.
    """
    global _TICKER, _TICKER_GEN
    with _LOCK:
        if _TICKER and _TICKER.is_alive():
            return

        # THIS THREAD'S OWN GENERATION, captured once and compared on every beat — never
        # a shared flag a later start/stop could rewrite underneath it. See the note by
        # `_TICKER_GEN`.
        _TICKER_GEN += 1
        my_gen = _TICKER_GEN

        def _period() -> float:
            if period_s is not None:
                return max(0.05, float(period_s))
            try:
                from harness.tuning import registry as tune
                v = float(tune.get("kairos.tick_s"))
            except Exception:
                v = 15.0
            # A floor, because a zero or negative period is a busy-loop that starves the
            # GPU thread this scheduler exists to stay out of the way of.
            return min(600.0, max(1.0, v))

        def _loop():
            while True:
                time.sleep(_period())
                with _LOCK:
                    # NOT THE CURRENT GENERATION: either `stop_ticker()` asked to stop, or
                    # a restart while this thread slept already started a newer one. Either
                    # way this thread's only correct move is to end without ticking — a
                    # stale thread that ticks anyway is the double-ticker this counter
                    # exists to rule out.
                    if _TICKER_GEN != my_gen:
                        logger.info("[kairos] ticker stopping — shutdown requested "
                                    "or superseded by a restart")
                        return
                try:
                    tick_once()
                except Exception as exc:
                    logger.warning("[kairos] tick failed: %s", exc)

        _TICKER = threading.Thread(target=_loop, name="kairos-tick", daemon=True)
        _TICKER.start()
        # _period(), not period_s: the one call site passes nothing, so this line has
        # raised a formatting error on EVERY boot since the heartbeat became a knob —
        # the log line telling you the ticker started has never once printed.
        logger.info("[kairos] idle ticker started (every %.0fs)", _period())


def stop_ticker() -> bool:
    """Ask the idle loop to stop. Returns whether one was running.

    The thread is a daemon and checks its own captured generation against `_TICKER_GEN`
    on each beat, so this is a REQUEST rather than a kill: a beat already generating
    finishes its own turn. Idempotent, and safe to call when nothing is running — a
    shutdown must never fail because the thing it is stopping had not started.

    BUMPS THE GENERATION rather than setting a flag, because a flag is exactly what a
    `start_ticker()` racing this call could clear out from under a thread that has not
    woken up yet — see the note by `_TICKER_GEN` for the incident that shape produced.
    """
    global _TICKER, _TICKER_GEN
    with _LOCK:
        was = bool(_TICKER and _TICKER.is_alive())
        _TICKER_GEN += 1
        _TICKER = None
    return was


def cancel_timers() -> int:
    """Cancel every pending per-session Timer. shutdown.quiesce() calls this: stopping
    the ticker stops the BEAT, but a Timer already armed is a generation already
    scheduled, and quiesce used to leave them all live — the _fire guard would drop
    them at fire time, but a cancelled timer is better than a dropped impulse plus a
    log line during teardown."""
    with _LOCK:
        ts = list(_TIMERS.values())
        _TIMERS.clear()
    for t in ts:
        t.cancel()
    return len(ts)


# A flushed message may come back while it is still warm; past this it is a record.
# Judgment call, written down: a shutdown-and-restart cycle on this box can cost 15+
# minutes cold, so the reflect cooldown (1800 s) is too tight — but a cut-off fragment
# from yesterday delivered cold is worse than silence (the pending-insight rule). Four
# hours covers an evening's bounce and not a night's absence.
UNDELIVERED_SHELF_S = 4 * 3600.0


def reload_undelivered() -> dict:
    """Bring what flush() preserved back to the queue that is read. The missing half of
    the shutdown ladder (2026-08-19): flush wrote her undelivered words to disk — "a
    kill loses DELIVERY, not content" — and nothing ever read them back, so the loss it
    scoped away was simply made tidy. Called from BOTH re-entry points: gateway boot
    (mode=all/kill killed the process) and shutdown.resume() (mode=her kept it).

    THE FILE ONLY GROWS. The cursor is a `redelivered` marker row carrying `upto` (the
    line count consumed) — never a rewrite, so two shutdowns in one day still read as
    two shutdowns and a re-run delivers nothing twice. Rows older than
    UNDELIVERED_SHELF_S stay home as record, counted in the receipt. `pending_insight`
    rows are NOT restored: their shelf logic runs on monotonic time, which does not
    survive a process, and a held thought is re-derivable — her said words are not."""
    from harness.control import shutdown as sd
    p = sd.undelivered_path()
    if not p or not os.path.exists(p):
        return {"restored": 0, "stale": 0}
    restored = stale = 0
    with _LOCK:
        rows = []
        with open(p, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rows.append(json.loads(ln))
                except Exception:
                    rows.append({"why": "malformed"})   # counted lines; never a crash
        start = 0
        for r in rows:
            if r.get("why") == "redelivered":
                start = max(start, int(r.get("upto") or 0))
        now = time.time()
        for r in rows[start:]:
            if r.get("why") != "undelivered":
                continue
            # `at` wears TWO shapes and both are real: the scheduler stamps outbox rows
            # with time.time() (an epoch float — what the room's timeline reads), and
            # flush() setdefaults an ISO string only for rows that had none. The first
            # cut parsed ISO only, so EVERY real row aged out as unparseable and the
            # first live reload marked tonight's 28-minute-old messages stale — while
            # the gate stayed green on hand-built ISO fixtures: the fixture had the
            # wrong shape, which is supplying your own precondition in miniature.
            at = r.get("at")
            if isinstance(at, (int, float)):
                age = now - float(at)
            else:
                try:
                    # timegm + the gmtime-written stamp — the G-CLOCK pairing.
                    age = now - calendar.timegm(
                        time.strptime(at or "", "%Y-%m-%dT%H:%M:%SZ"))
                except (ValueError, TypeError):
                    age = None
            if age is None or age > UNDELIVERED_SHELF_S:
                stale += 1
                continue
            msg = {k: v for k, v in r.items() if k not in ("session", "why")}
            msg["redelivered"] = True
            _OUTBOX[r.get("session") or "default"].append(msg)
            restored += 1
        if restored or stale:
            try:
                with open(p, "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "why": "redelivered", "upto": len(rows),
                        "restored": restored, "stale": stale,
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }) + "\n")
            except Exception as exc:
                logger.warning("[kairos] could not write the redelivered marker: %s", exc)
    if restored or stale:
        logger.info("[kairos] redelivered %d flushed message(s); %d stale stayed home",
                    restored, stale)
    return {"restored": restored, "stale": stale}


def drain(session: str) -> list[dict]:
    """The console polls this. Returns and clears anything she has decided to say.

    THE NO-OWNER QUEUE IS DELIVERED TO WHOEVER IS ACTUALLY LISTENING (2026-08-19).
    Boot-time seeds and own-time speech land under "default" (there is no client session
    yet when they are written), and on_user_turn RETIRES the seeded session the moment a
    real one exists — so anything still queued there had NO READER: the room polls its
    own room-<uuid>, the console polls its SESSION_ID, and her "what I did while you
    were away" sat in a queue nobody would ever drain. This is the incident
    _session_of's docstring records ("she spoke, correctly, into a session nobody was
    listening to"), reintroduced by the session_id fix. The merge lives HERE, in the
    seam both clients share, so neither client has to know the seed queue exists."""
    with _LOCK:
        out = list(_OUTBOX[session])
        _OUTBOX[session].clear()
        if session != "default" and _OUTBOX["default"]:
            out = list(_OUTBOX["default"]) + out
            _OUTBOX["default"].clear()
    return out


def enter_mode(mode: str, session: Optional[str] = None, kick: bool = True) -> dict:
    """Set presence.mode and (kick) arm the one-shot so her first turn comes right after her
    reply. Her tool (presence.enter_mode) and the window's 'now' buttons both land here."""
    from harness.kairos import presence as _pm
    m = (mode or "").strip().lower()
    if m in ("dream", "lucid dream", "lucid_dream"):
        m = "lucid"
    if m == "narrate":
        m = "narration"
    if m not in _pm.MODES or m == "off":
        return {"ok": False, "error": "no such mode: %r (narration | company | lucid)" % mode}
    tune.set_many({"presence.mode": m})
    with _LOCK:
        live = list(_LAST.keys())
    if not live and kick:
        _PENDING_KICK[0] = True              # consumed by the seed (now if warm, else the next tick)
        _seed_for_presence()
    with _LOCK:
        sessions = [session] if session else (list(_LAST.keys()) or ["default"])
        for s in sessions:
            _STATE[s].mode_kick = bool(kick)
    if kick:
        # STRAIGHT AWAY (his words): do not wait for the next heartbeat — one tick now, on a
        # thread so the caller (her tool mid-reply, or the window) is not held.
        try:
            threading.Thread(target=tick_once, name="kairos-kick", daemon=True).start()
        except Exception:
            pass
    return {"ok": True, "mode": m, "kicked": bool(kick), "sessions": sessions}


def leave_mode() -> dict:
    """presence.mode -> off; any armed kick is cleared; a pending mode turn is dropped at
    fire time (the re-check in _fire_inner)."""
    tune.set_many({"presence.mode": "off"})
    with _LOCK:
        for st in _STATE.values():
            st.mode_kick = False
    return {"ok": True, "mode": "off"}


def peek_state(session: str) -> dict:
    """For the operator panel: why is she quiet right now?"""
    cfg = live_config()
    now = time.monotonic()
    with _LOCK:
        st = _STATE[session]
        recent = len([t for t in st.spoken_times if now - t < 3600.0])
        cooling = max(0.0, cfg.cooldown_s - (now - st.last_spoke_at)) if st.last_spoke_at else 0.0
        return {
            "enabled": cfg.enabled,
            "chain": st.chain,
            "max_chain": cfg.max_chain,
            "cooldown_left_s": round(cooling, 1),
            "spoken_last_hour": recent,
            "max_per_hour": cfg.max_per_hour,
            "pending": len(_OUTBOX[session]),
            # WHAT SHE ALMOST SAID. The panel already answered "why is she quiet right
            # now"; this answers the slower and more useful question — how much of what
            # she produced never reached him, and which rule took it.
            "speech": _speech.summary(),
            "presence": _presence_state(cfg, st, now),
        }


def _presence_state(cfg, st, now: float) -> dict:
    """For the chip: which mode, when the next turn may come, what she is reading."""
    out = {"mode": cfg.presence_mode, "next_in_s": None, "reading": None}
    try:
        if cfg.presence_mode and cfg.presence_mode != "off":
            from harness.kairos import presence as _pm
            every = (cfg.presence_every_s if cfg.presence_every_s > 0
                     else _pm.EVERY_DEFAULT.get(cfg.presence_mode, 300.0))
            last = max(st.last_user_at, st.last_spoke_at, st.last_solo_at, st.last_mode_at)
            out["next_in_s"] = round(max(0.0, every - (now - last)), 1)
        from harness.skills import library as _lib
        b = _lib.in_hand()
        if b:
            out["reading"] = {"title": b["title"], "pos": b["pos"], "chars": b["chars"], "done": b["done"]}
    except Exception:
        pass
    return out

