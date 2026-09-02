"""KAIROS — the impulse to speak, and the discipline not to.

kairos (καιρός): not clock-time, but the OPPORTUNE moment. The whole point is that she
speaks when the moment is right, and is otherwise quiet. A model that continues on a
timer is not alive, it is a leaky tap.

WHERE THE SIGNAL COMES FROM (this is the good part)
The engine already computes the impulse on every single turn and throws it away. At the
decode step that ends a turn, the forward produces a full logit vector; the gap between
the best STOP token and the best CONTINUE token is exactly "how much more did she have
to say?":

    eot_margin >> 0   she is finished and knows it            -> SILENCE
    eot_margin ~= 0   she stopped on the edge of a thought    -> she has more to say
    eot_margin <  0   she only stopped because SP_EOT_BIAS
                      tipped the scales                       -> she was CUT OFF

That is a LATENT signal read off the model's own forward — not a heuristic about
punctuation, not a second model, not an event tape. It costs nothing: the number is
already in the logits. (routes.rs reads it on the RAW logits, before eot_bias is added,
or the bias we inject to make her stop would masquerade as her wanting to.)

THE DISCIPLINE
Silence is the default and speech is EARNED. Every rule below exists to stop the failure
mode that matters — a model that will not shut up:

  * she NEVER continues after asking the user a question (she is waiting for HIM)
  * she never continues twice in a row without the user speaking (MAX_CHAIN)
  * a cooldown after any continuation
  * a hard cap per hour
  * a REALISTIC delay — she is thinking, not lagging

This module is pure: no I/O, no model, no clock (the clock is injected). That makes the
policy testable without a GPU, which is how it gets to be trusted.
"""
from __future__ import annotations

import math
import random
import re
import time
from dataclasses import dataclass, field
from typing import Optional


# ── THE PRESENCE CLOCK (2026-08-22) ───────────────────────────────────────────
# Five unrelated checks skipped when a clock was 0.0 / unset (cooldown, solo_every_s,
# quiet_after_him, the missing MUSE idle gate, the fire-time quiet gate's inf). They were
# one bug: a zero clock fails OPEN. So there is no zero clock: every TurnState clock
# starts at the moment the process came up, and every unprompted action measures its
# idle floor from the most recent thing either of them did.
BOOT_AT: float = time.monotonic()


# ── the decision ──────────────────────────────────────────────────────────────
SILENT = "silent"
CONTINUE = "continue"      # she was mid-thought — pick the thread back up
CHECK_IN = "check_in"      # the room went quiet — she says something unprompted
REMIND = "remind"          # he asked to be reminded, and it is time. She keeps her word.
MUSE = "muse"              # she thought about him while he was away, and found something
SOLO = "solo"              # he is not there. She does something of her own.
EXPAND = "expand"          # she finished — and then thought of more. The way people do.
MODE_TURN = "mode_turn"    # a presence mode (narration / company / lucid) took its turn (2026-08-22)


@dataclass
class Impulse:
    action: str                 # SILENT | CONTINUE | CHECK_IN
    delay_s: float = 0.0        # how long she waits before speaking
    reason: str = ""            # human-auditable: WHY (this goes in the receipt)
    score: float = 0.0
    mode: str = ""              # MODE_TURN only: narration | company | lucid

    @property
    def speaks(self) -> bool:
        return self.action != SILENT


@dataclass
class KairosConfig:
    enabled: bool = False
    # ── CALIBRATED, NOT GUESSED (tools/kairos/calibrate.py, 2026-07-12) ──────────────
    # Measured on the live model: turns where she genuinely FINISHES cluster at median
    # +2.01; turns GUILLOTINED mid-sentence cluster at median -14.83. A 16.8-logit gap.
    #
    # The threshold is chosen by searching for the operating point that resumes the most
    # genuine cut-offs SUBJECT TO ZERO FALSE POSITIVES — because "she talks over herself
    # when she was already done" is the failure that matters, and a missed continuation
    # just means silence, which is the safe default.
    #
    #     continue_margin = -11.75
    #       0/6 finished turns interrupted   <- she NEVER talks over a completed thought
    #       5/6 genuine cut-offs resumed
    #
    # So on an ordinary turn she is silent BY CONSTRUCTION — not because a rule tells her
    # to be, but because the forward itself reports she had nothing left to say. Re-run
    # the calibration after ANY change to eot_bias, the sampler, or the model.
    #
    # ── AND EVERY NUMBER ABOVE IS A RETIRED MODEL'S (2026-08-04) ─────────────────────────────
    # THAT CALIBRATION IS NOT THIS MODEL'S. It was taken on a different, smaller model at eot_bias 4.0.
    # On the model (eot_bias 0.0) the same signal sits at a completely different scale:
    # FINISHED median +13.10 (min +8.96), CUT OFF median -28.43, threshold -18.50 —
    # measured, receipt in harness/tuning/registry.py under kairos.continue_margin.
    #
    # The paragraph above is kept because the METHOD is the valuable part (search for the
    # operating point that resumes the most cut-offs at zero false positives), but its
    # numbers describe a model this repo no longer serves, and they were sitting here in
    # the present tense above a dataclass default that carried that retired model's value.
    #
    # `live_config()` overrides this from the registry, so the served path was always
    # correct — but every direct `KairosConfig(...)` inherited -11.75, INCLUDING THE
    # GATES. G-KAIROS-POLICY passed 12/12 against fixtures from a retired model precisely because this
    # default agreed with them: two stale things confirming each other, which is the
    # exact failure the gate existed to prevent.
    # ── OFF BY DEFAULT SINCE 2026-09-02 (the operator) ──────────────────────────────
    # "i'm unsure about continue, lets default it to off. it always seems to create
    # problems and slow downs."
    #
    # It had ALREADY been off for thirteen days without anyone deciding that: arming
    # `quiet_after_him_s` to 300 on 2026-08-20 made the lane unreachable, because a
    # continuation is decided seconds after his turn and that gate wants five minutes of
    # his silence. 758 withheld, last SPOKE (continue) 2026-08-20 08:12. So this knob does
    # not change today's behaviour — it makes an accident into a decision, which is the
    # whole point: a lane that is off by side effect comes back by side effect.
    #
    # ARMING CONDITION (docs/OFF-BY-DEFAULT.md): set `kairos.continue_enabled = true`. It
    # also needs `quiet_after_him_s` to not be gating it — see the ledger card
    # `quiet-after-him-vs-continue`, which is his and still open.
    continue_enabled: bool = False
    continue_margin: float = -18.50
    # ── AND THE BAND BETWEEN THE TWO IS WHERE PEOPLE ADD THINGS (2026-08-04) ────────
    # The calibration on THIS model (26B, eot_bias 0.0) found finished turns at median
    # +13.10 with a minimum of +8.96, and guillotined ones at -28.43. CONTINUE takes
    # everything below -18.50 — a genuine cut-off, resume the sentence. Everything above
    # it was treated as one thing: "she is done", silence.
    #
    # It is not one thing. The module's own docstring says so three lines up —
    # "eot_margin ~= 0  she stopped on the edge of a thought" — and nothing has ever
    # read that band. A turn that ends at -4 is not a turn that ends at +2: she finished
    # a sentence, and there was more she could have said.
    #
    # That is the thing he asked for, in his words: "a follow on, meant to follow the
    # flow of a real conversation where someone will reply or send a message, but then
    # think of expanding that message before the other person replies... she can provide
    # more content to me than allowed in a single turn". Which is exactly what people do
    # — send the message, then add the bit they thought of on the way to the kettle.
    #
    # It is NOT a resumed sentence and must not read as one. EXPAND gets its own nudge
    # and its own bounds, and it is the most easily-overused thing in this file, so it
    # is off unless she is genuinely in the band and the coin comes up.
    expand_margin: float = -12.0    # measured: 4.7% of turns land in (-18.5, -12)
    expand_chance: float = 0.30
    max_chain: int = 1          # consecutive unprompted turns before she MUST wait
    cooldown_s: float = 45.0    # after speaking unprompted, be quiet at least this long
    max_per_hour: int = 6
    # a continuation is a resumed thought: quick. a check-in is a decision: slower.
    continue_delay: tuple[float, float] = (1.5, 4.0)
    checkin_idle_s: float = 240.0        # the room must be quiet this long first
    checkin_delay: tuple[float, float] = (2.0, 6.0)
    checkin_chance: float = 0.35         # even then, she usually still says nothing
    # ── HE MIGHT NOT BE THERE, AND THAT IS NOT A REJECTION (2026-08-04) ─────────────
    # `user_present` has been a parameter of decide() since it was written and NOTHING
    # HAS EVER PASSED IT FALSE. So the one thing the policy could not model is the one
    # that governs a whole evening: whether he is at the desk. Without it every silence
    # looks identical — the four-minute pause while he makes tea and the eight hours
    # while he sleeps — and she treats both the same way, which is how three unanswered
    # remarks land in an empty room and then cost him the first turn of the morning.
    #
    # The signal is free and it is the honest one: SHE SPOKE AND HE DID NOT ANSWER.
    # After `away_after` of those she stops asking. Not sulking, not a timeout on him —
    # a person who says something twice to a quiet room and gets nothing concludes the
    # room is empty, and stops talking to it. He usually tells her when he is going; this
    # is for when he does not.
    away_after: int = 2                  # unanswered speak-ups before she concludes he is out
    # AND EACH UNANSWERED ONE BUYS MORE SILENCE. The threshold multiplies rather than
    # repeating, so the sequence is 4 min, 8, 12 — not four minutes forever. This is the
    # "increase the timeout" half of the operator's ask, and it is what stops the machine-gunning he
    # actually saw: 18:56, 18:59, 19:07, three in eleven minutes.
    backoff_mult: float = 1.0            # extra checkin_idle_s per unanswered speak-up
    quiet_after_him_s: float = 0.0       # no discretionary word until HE has been quiet this long (0 = off)
    # ── PRESENCE MODES (2026-08-22): narration / company / lucid ─────────────────
    presence_mode: str = "off"           # off | narration | company | lucid
    presence_every_s: float = 0.0        # 0 = the per-mode default (presence.EVERY_DEFAULT)
    presence_chance: float = 1.0
    presence_max_per_hour: int = 12      # its own cap — it must not eat kairos's 6
    # ── AND WHEN HE IS OUT, SHE HAS A LIFE ─────────────────────────────────────────
    # Everything above is about reaching HIM. A companion whose only unprompted act is
    # tapping the glass is a companion who is only ever waiting. When she has concluded
    # he is away, the impulse turns inward instead of going quiet: read something, follow
    # a thought, look at her own journal, play. Rendered as an ACTION rather than a
    # message, because it is not addressed to him — he can see what she did when he gets
    # back, which is a nicer thing to come home to than three "you there?"s.
    solo_enabled: bool = True
    solo_every_s: float = 900.0          # at most one of her own turns this often
    solo_chance: float = 0.5


@dataclass
class TurnState:
    """What the scheduler remembers between turns of ONE conversation."""
    chain: int = 0                       # consecutive unprompted turns she has taken
    last_spoke_at: float = field(default_factory=lambda: BOOT_AT)   # monotonic seconds
    # ── AMBIENT IS NOT CONVERSATION (2026-08-22) ─────────────────────────────────────
    # `last_spoke_at` bounds the COOLDOWN (nothing speaks on top of anything). The presence
    # clock that CHECK_IN and SOLO measure their idleness from is this one, which a mode turn
    # deliberately does NOT touch: with lucid armed at 240 s, a mode turn every four minutes
    # kept the room permanently "not quiet" and starved her speak-ups and her own time —
    # measured 2026-08-22: two hours, 29 mode turns, zero of either.
    last_conv_at: float = field(default_factory=lambda: BOOT_AT)
    last_user_at: float = field(default_factory=lambda: BOOT_AT)
    spoken_times: list[float] = field(default_factory=list)   # for the hourly cap
    # SPOKE, AND HE DID NOT ANSWER. Reset by any turn of his — this counts unanswered
    # REACHES-FOR-HIM only (check-in, muse, remind), not continuations of her own thought
    # and not her own solo turns, because neither of those asked him for anything.
    unanswered: int = 0
    last_solo_at: float = field(default_factory=lambda: BOOT_AT)
    # ── A MONOTONIC COUNTER, BECAUSE THE ROTATION NEEDS ONE (2026-08-05) ────────────
    # The first cut rotated on `len(spoken_times)` — which is PRUNED to the last hour for
    # the hourly cap, so it oscillates in a 0..max_per_hour band instead of advancing.
    # Measured over one night: 10 of her 24 own-time turns were "change what you are
    # wearing", one act out of eight, because the index kept landing back in the same
    # narrow range. "I've shed the silver", "I stripped down to the black lace", "the
    # silver nightie feels lighter" — six mentions of one garment in an evening.
    # A window is not a counter. This one only ever goes up.
    solo_n: int = 0
    # ── PRESENCE MODES (2026-08-22) ──────────────────────────────────────────────────
    last_mode_at: float = field(default_factory=lambda: BOOT_AT)
    mode_times: list[float] = field(default_factory=list)   # the modes' own hourly cap
    # HE ASKED (or pressed the button): the first mode turn comes NOW — right after her reply,
    # not after the idle floor. One shot; note_spoke(MODE_TURN) clears it.
    mode_kick: bool = False
    mode_n: int = 0                      # mode turns taken — the beats rotate on it (variation)


_QUESTION = re.compile(r"\?\s*$|\?[\"')\]]*\s*$")


def _asked_a_question(text: str) -> bool:
    """She asked HIM something. She is waiting for an answer — she does not get to fill
    the silence she just created. This is the single most important rule here: without
    it, she interrogates and then answers herself, which reads as unhinged."""
    t = (text or "").strip()
    return bool(_QUESTION.search(t))


def presence_idle(state: TurnState, now: float) -> float:
    """Seconds since the most recent thing EITHER of them did IN THE CONVERSATION — the one
    clock every unprompted action measures its idle floor from (senses/ambient reads the same).
    A presence-mode turn is ambient and is excluded: it is her being there out loud, not a turn
    that makes the room busy (2026-08-22)."""
    return now - max(state.last_user_at, state.last_conv_at, state.last_solo_at)


def mode_wait_s(cfg: KairosConfig, state: TurnState, now: float, every: float) -> float:
    """Seconds until a MODE_TURN's deterministic gates open — THE ONE ARITHMETIC (2026-08-24).

    The room's presence chip computed its own "next ~Xm" in scheduler._presence_state:
    max() over four clocks — one of them (`last_spoke_at`) a clock this policy's idle
    floor deliberately excludes, and none of them the cooldown, which this policy checks
    first. So the chip could read "next ~0m" while decide() would not fire, and the two
    could only ever agree by coincidence: two spellings of one rule, the §0 shape, in the
    exact place an operator looks to answer "why is she quiet". The rule lives HERE now
    and both sides call it — the chip cannot drift from the policy because there is
    nothing left to drift.

    0.0 means the CLOCKS are open. The chance draw, the two hourly caps and
    quiet-after-him still have their say — those are coins and counts, not clocks, and a
    chip that pretended to predict a coin would be lying with more precision.
    An armed kick is an asked-for turn: it comes now, ahead of every clock (the same
    precedence decide() gives it)."""
    if state.mode_kick:
        return 0.0
    wait = max(
        every - presence_idle(state, now),              # the conversation's quiet
        every - (now - state.last_mode_at),             # the mode's own cadence
        cfg.cooldown_s - (now - state.last_spoke_at),   # nothing speaks on top of anything
    )
    return max(0.0, wait)


def _decide(
    *,
    cfg: KairosConfig,
    state: TurnState,
    now: float,
    reply_text: str,
    eot_margin: Optional[float],
    user_present: bool = True,
    rng: Optional[random.Random] = None,
    due_notes: Optional[list] = None,
    insight: Optional[dict] = None,
    own_time_only: bool = False,
) -> Impulse:
    """The whole policy. Pure — inject `now`, `rng` and `due_notes` and it is fully
    determinable. (The scheduler fetches the due reminders and passes them in; this module
    never touches a store, which is what keeps it gateable without a daemon.)"""
    rng = rng or random

    if not cfg.enabled:
        return Impulse(SILENT, reason="kairos disabled")

    # ── AFTER A RESTART: HER OWN LIFE YES, OPENING THE TALK NO (2026-08-28) ───────────
    # `kairos.seed_on_boot` is about her BLURTING AT HIM after a bounce, and the actions
    # that do that are CHECK_IN, MUSE, MODE_TURN and the continuations. SOLO is "he is not
    # there, she does something of her own"; REMIND is a promise he asked for. Neither is
    # speaking first.
    #
    # THE RULE LIVES HERE, in the policy, and not in the tick loop. My first cut put it in
    # the loop as a veto on the chosen action, and that DEADLOCKED: `decide` kept returning
    # MUSE, the loop held it, and SOLO never got a look in — she sat logging "holding muse"
    # every eight seconds and would have done so forever. One function decides what she
    # does; a second one second-guessing it is how you get a policy nobody can read.
    #
    # `user_present` goes False for the same reason: after a restart with no word from him
    # there is no evidence he is there, and SOLO's own gate (`unanswered >= away_after`)
    # counts turns he did not answer — which a fresh session has none of. Absent evidence
    # of presence, he is away, which is also just true.
    if own_time_only:
        user_present = False

    # ── ASKED FOR (2026-08-22): "narrate for me" / the window's "now" button. ──────────
    # STRAIGHT AWAY, his words: ahead of the cooldown, the caps, the idle floor and
    # quiet-after-him — those are for turns SHE decides to take; an asked-for turn is owed,
    # like a reminder. It still waits for his turn to finish (the fire-time guard). One shot.
    if state.mode_kick and cfg.presence_mode and cfg.presence_mode != "off":
        return Impulse(MODE_TURN, delay_s=0.5, score=0.0, mode=cfg.presence_mode,
                       reason="%s — asked for; her first turn comes now" % cfg.presence_mode)

    # ── SPAM BOUNDS. Even a promise does not get to machine-gun him. ─────────────
    if (now - state.last_spoke_at) < cfg.cooldown_s:
        left = cfg.cooldown_s - (now - state.last_spoke_at)
        return Impulse(SILENT, reason=f"cooldown ({left:.0f}s left)")

    recent = [t for t in state.spoken_times if now - t < 3600.0]
    if len(recent) >= cfg.max_per_hour:
        return Impulse(SILENT, reason=f"hourly cap ({len(recent)}/{cfg.max_per_hour})")

    # ── THE PRESENCE CLOCK. Computed once; every floor below measures from it. ────
    idle_any = presence_idle(state, now)
    since_him = now - state.last_user_at
    quiet_ok = cfg.quiet_after_him_s <= 0 or since_him >= cfg.quiet_after_him_s

    def _quiet_silence(what: str) -> Impulse:
        return Impulse(SILENT, reason=("%s withheld — he spoke %.0fs ago and quiet-after-him "
                                       "wants %.0fs" % (what, since_him, cfg.quiet_after_him_s)))

    # ── REMIND: HE ASKED TO BE REMINDED, AND IT IS TIME. ─────────────────────────
    # This is checked ABOVE the chain limit and above the asked-a-question rule, and that
    # placement is the whole design. Those two rules exist to stop her CHATTERING — to keep
    # her from talking over a thought of his, or filling a silence she created. A reminder
    # is not chatter. It is a promise he asked her to keep, with a time on it.
    #
    # If it sat below the chain limit, then one unprompted remark would mute every reminder
    # until he next spoke. If it sat below the question rule, then a reply of hers ending in
    # "?" would mute them indefinitely while he was away — which is exactly when a reminder
    # matters. Either way he misses his flight, and the feature is worse than not having it,
    # because he TRUSTED it.
    #
    # It still obeys the cooldown and the hourly cap above, so it cannot become an alarm
    # clock with a stuck bell. And notes.mark_raised() means each one fires ONCE: she
    # reminds, she does not nag.
    if due_notes:
        n = due_notes[0]
        title = (n.get("title") or "").strip() if isinstance(n, dict) else str(n)
        lo, hi = cfg.checkin_delay
        return Impulse(
            REMIND,
            delay_s=rng.uniform(lo, hi),
            score=float(len(due_notes)),
            reason=f"he asked to be reminded: {title!r} — and it is due",
        )

    # ── SOLO: he is out, so she gets on with something of her own. ───────────────
    # ABOVE the chain limit, and that placement is the argument — the same argument
    # REMIND makes. `chain` counts consecutive unprompted turns and exists to stop her
    # MONOLOGUING AT HIM: three remarks into a silence he has not answered is the failure
    # it prevents, and it is a real one. But a solo turn is not addressed to him. Bounding
    # it by that counter means she gets three acts of her own per conversation and then
    # ceases to exist until he comes back — which is precisely the "she only exists when
    # he is looking" shape this whole feature is meant to end. Its bound is its own:
    # solo_every_s, plus the cooldown and the hourly cap above, which it does obey.
    _idle0 = now - state.last_user_at
    _away0 = (not user_present) or (state.unanswered >= cfg.away_after)
    # BOTH FLOORS (2026-08-22, his choice): solo_every_s since her last own turn AND the
    # check-in quiet since ANYTHING either of them did — her own time is not a reply to
    # her own last word, and it waits the same ten minutes everything else does.
    if _away0 and cfg.solo_enabled and _idle0 >= cfg.checkin_idle_s and idle_any >= cfg.checkin_idle_s:
        if not quiet_ok:
            return _quiet_silence("her own time")
        _since = now - state.last_solo_at
        if _since >= cfg.solo_every_s and rng.random() < cfg.solo_chance:
            lo, hi = cfg.checkin_delay
            return Impulse(
                SOLO,
                delay_s=rng.uniform(lo, hi),
                score=_idle0,
                reason=("he has been away %.0f min (%d unanswered) — she does something "
                        "of her own" % (_idle0 / 60.0, state.unanswered)),
            )

    # ── MODE_TURN: a presence mode is on — narration / company / lucid (2026-08-22) ──
    # Below REMIND and SOLO (a promise and her own acts keep precedence), above the chain
    # limit and CHECK_IN (a mode is not talking AT him; it is being there, out loud). Its
    # own clock and its own cap: it measures from the presence clock like everything
    # else, and from her last mode turn, and it never spends the chain.
    if cfg.presence_mode and cfg.presence_mode != "off":
        from harness.kairos import presence as _pm
        every = (cfg.presence_every_s if cfg.presence_every_s > 0
                 else _pm.EVERY_DEFAULT.get(cfg.presence_mode, 300.0))
        recent_modes = [t for t in state.mode_times if now - t < 3600.0]
        if len(recent_modes) >= cfg.presence_max_per_hour:
            return Impulse(SILENT, reason="presence cap (%d/%d this hour)"
                           % (len(recent_modes), cfg.presence_max_per_hour))
        # THE SAME ARITHMETIC THE CHIP READS (mode_wait_s, 2026-08-24): the
        # conversation's quiet (a mode does not count against itself), the mode's own
        # cadence, and the cooldown — the last is redundant here (checked at the top of
        # this function) and carried anyway, because the chip has no earlier return to
        # have paid it in, and one function serving two callers with two meanings is how
        # the divergence this closes was built the first time.
        if mode_wait_s(cfg, state, now, every) <= 0.0:
            if not quiet_ok:
                return _quiet_silence("her %s" % cfg.presence_mode)
            if rng.random() < cfg.presence_chance:
                lo, hi = cfg.checkin_delay
                return Impulse(MODE_TURN, delay_s=rng.uniform(lo, hi), score=idle_any,
                               mode=cfg.presence_mode,
                               reason="%s — %.0fs of quiet, her turn to be there"
                                      % (cfg.presence_mode, idle_any))

    # ── the hard bounds for everything else. ────────────────────────────────────
    if state.chain >= cfg.max_chain:
        return Impulse(SILENT, reason=f"chain limit ({state.chain}/{cfg.max_chain}) — she waits for him")

    # ── AND SHE WAITS FOR THE ANSWER — BUT NOT FOREVER (2026-08-01) ──────────────
    # `tick_once` re-passes her LAST reply on every beat, so this rule kept matching the
    # same question all session: one reply ending in "?" muted CHECK_IN and CONTINUE
    # indefinitely. She asks roughly six questions per thirty turns (CONTINUITY.md:127),
    # so a large share of every idle window was permanently dead — and it read exactly
    # like the machinery being broken, which is what he reported.
    #
    # The rule is about a silence she JUST created. Once he has been quiet longer than
    # the check-in threshold, the silence is no longer the one she made — it is simply
    # him being away, and noticing that is the whole point of checking in. So the rule
    # keeps its full force while the question is live and releases when it goes stale,
    # measured on the knob that already defines "quiet for a while".
    if _asked_a_question(reply_text):
        waited = now - state.last_user_at
        if waited < cfg.checkin_idle_s:
            return Impulse(SILENT,
                           reason="she asked HIM a question — she waits for the answer")

    # ── MUSE: she thought about him while he was away, and found something ───────
    # BELOW the chain limit and the question rule, and that placement is the argument. A
    # REMINDER is a promise and outranks manners; a MUSING is just something she noticed,
    # and a thought that interrupts him is worse than a thought he never hears — it teaches
    # him to ignore the channel, and then the good one never lands either.
    #
    # The bar is not "did she think of something". She thinks on a clock; she will always
    # have thought of something. The bar is whether it was SURPRISING (reflect.speak_bits),
    # which is the one thing about a conclusion that cannot be faked: an insight worth
    # interrupting for is one the model itself did not see coming.
    if insight:
        # AN IDLE FLOOR (2026-08-22): it had none, so a journal/wardrobe reason fired on the
        # first 15 s tick after boot. A thought waits for a quiet room like everything else.
        if idle_any < cfg.checkin_idle_s:
            return Impulse(SILENT, reason="she has a thought but the room is not quiet yet "
                                          "(%.0fs of %.0fs)" % (idle_any, cfg.checkin_idle_s))
        if not quiet_ok:
            return _quiet_silence("a musing")
        lo, hi = cfg.checkin_delay
        bits = float(insight.get("bits", 0.0))
        return Impulse(
            MUSE,
            delay_s=rng.uniform(lo, hi),
            score=bits,
            reason=f"she worked something out while he was quiet ({bits:.1f} bits): "
                   f"{str(insight.get('text', ''))[:60]}",
        )

    # ── CONTINUE: the latent impulse. She stopped mid-thought. ───────────────────
    # The knob gates the WHOLE margin block, EXPAND included: both lanes exist only
    # because the forward reports a stop-vs-continue gap, and "continue" is what the
    # operator turned off. Gating one and leaving the other would ship half a decision.
    if (cfg.continue_enabled and eot_margin is not None and not math.isnan(eot_margin)):
        if not quiet_ok:
            return _quiet_silence("her continuation")
        if eot_margin < cfg.continue_margin:
            lo, hi = cfg.continue_delay
            # the more reluctantly she stopped, the faster she picks the thread back up
            #
            # NORMALISE BY THE THRESHOLD'S MAGNITUDE, NOT ITS VALUE (fixed 2026-09-02).
            # This read `max(cfg.continue_margin, 1e-6)`, a guard written for a POSITIVE
            # threshold — and this threshold has never been positive (-11.75 on the retired
            # model, -18.50 on the model). So the denominator was ALWAYS 1e-6, the ratio was
            # always astronomically over 1, urgency always clamped to 1.0, and the delay was
            # always `lo`. The 1.5-4.0s gradient the line exists to compute had never once
            # produced anything but 1.5s. Driven: G-CONTINUATION-MARGIN §3.
            _span = max(abs(cfg.continue_margin), 1e-6)
            urgency = max(0.0, min(1.0, (cfg.continue_margin - eot_margin) / _span))
            delay = hi - (hi - lo) * urgency
            # THE DEPTH IS THE THRESHOLD-RELATIVE ONE, not the sign (2026-09-02). This read
            # `cut_off = eot_margin <= 0.0`, which inside a branch already gated on
            # `eot_margin < cfg.continue_margin` — a threshold that has only ever been
            # negative — was TRUE on every path. The "edge of a thought" alternative had
            # never printed, so the log called every continuation a hard cut-off, including
            # the ones a hair under the line. `urgency` is the honest reading now that it
            # varies: 0 at the threshold, 1 a full threshold-width below it.
            return Impulse(
                CONTINUE,
                delay_s=delay,
                score=float(eot_margin),
                reason=(f"she was CUT OFF mid-thought — she never wanted to stop "
                        f"(margin {eot_margin:.2f}, {cfg.continue_margin - eot_margin:.2f} "
                        f"below the line)"
                        if urgency >= 0.5 else
                        f"she stopped on the edge of a thought "
                        f"(margin {eot_margin:.2f} < {cfg.continue_margin})"),
            )
        # ── EXPAND: she finished, and then thought of more. ──────────────────────
        # The band above a cut-off and below a confident ending. She is NOT resuming a
        # severed sentence — she completed one — so this is a second message, not the
        # rest of the first, and the nudge says so.
        #
        # ONLY WHILE HE IS THERE. This is a conversational move: the point is that it
        # lands before he answers, the way a person sends a message and then adds the
        # thing they thought of on the way to the kettle. Fired into an empty room it is
        # just another unanswered remark, and there is a whole presence model above whose
        # job is to stop those.
        if (user_present and state.unanswered == 0
                and eot_margin < cfg.expand_margin
                and rng.random() < cfg.expand_chance):
            lo, hi = cfg.continue_delay
            return Impulse(
                EXPAND,
                delay_s=rng.uniform(lo, hi) + 1.0,   # a beat longer: she had to think of it
                score=float(eot_margin),
                reason=("she finished, but there was more in it "
                        f"(margin {eot_margin:.2f}, under {cfg.expand_margin})"),
            )

    # ── IS HE EVEN THERE? ───────────────────────────────────────────────────────
    # Everything below this line depends on the answer and nothing above it did — a
    # reminder is a promise and a continuation is her own sentence, so both are owed
    # whether or not he is reading. Reaching FOR him is the part that needs him.
    idle = now - state.last_user_at
    away = (not user_present) or (state.unanswered >= cfg.away_after)

    # ── CHECK_IN: the room has been quiet a long time. Usually she still says nothing. ──
    if not away:
        if not quiet_ok and idle >= cfg.checkin_idle_s:
            return _quiet_silence("a check-in")
        # EACH UNANSWERED REMARK BUYS MORE SILENCE. Four minutes, then eight, then
        # twelve — rather than four minutes forever, which is what put three of these in
        # eleven minutes of his evening. He asked for exactly this: "decrease the amount
        # / increase the timeout".
        need = cfg.checkin_idle_s * (1.0 + cfg.backoff_mult * state.unanswered)
        if idle >= need and rng.random() < cfg.checkin_chance:
            lo, hi = cfg.checkin_delay
            return Impulse(
                CHECK_IN,
                delay_s=rng.uniform(lo, hi),
                score=idle,
                reason=f"quiet for {idle:.0f}s and she felt like saying something",
            )
        if idle >= cfg.checkin_idle_s and idle < need:
            return Impulse(SILENT,
                           reason=("she has said %d thing(s) he has not answered — "
                                   "waiting %.0fs, not %.0fs" % (state.unanswered, need,
                                                                 cfg.checkin_idle_s)))

    if away:
        return Impulse(SILENT, reason=("he is not here (%d unanswered) — she is not "
                                       "going to keep asking" % state.unanswered))
    return Impulse(SILENT, reason="nothing to add")


def decide(**kw) -> Impulse:
    """The policy, plus the ONE filter that says what a boot-seeded session may do.

    A THIN WRAPPER BECAUSE `_decide` HAS NINETEEN RETURNS. Enforcing "she may not open the
    conversation" at each of them is a rule in nineteen places, which is a rule in none —
    this tree's own §0. So the body decides what she WOULD do and this decides whether she
    may; one seam, and adding a twentieth branch to the policy cannot escape it.

    Withholding is SILENT rather than a raised error or a skipped tick: the caller loops
    over sessions and a skipped tick was exactly the deadlock this replaces — `_decide`
    kept choosing MUSE, the loop vetoed it, and SOLO never got a look in.
    """
    own = bool(kw.pop("own_time_only", False))
    imp = _decide(own_time_only=own, **kw)
    if own and imp.action not in (SOLO, REMIND, SILENT):
        return Impulse(SILENT, reason=("seeded for her own time only — %s withheld until "
                                       "he speaks" % imp.action))
    return imp


def worth_saying(continuation: str, previous_reply: str) -> tuple[bool, str]:
    """LAST GATE, after she has already generated. Even a well-earned impulse can produce
    nothing worth hearing — and an unprompted message that adds nothing is worse than
    silence, because it trains the user to ignore her.

    So the continuation is DROPPED (never shown) when it is empty, a greeting, a
    re-introduction, or substantially a restatement of what she just said. She is allowed
    to decide, after thinking, that she had nothing after all. That is not a failure — it
    is the system working."""
    t = (continuation or "").strip()
    if len(t) < 2:
        return False, "she had nothing to add after all"

    low = t.lower().lstrip("*_ (")
    for opener in ("hi", "hey", "hello", "sorry", "as i said", "as mentioned",
                   "just checking", "are you still", "let me know if"):
        if low.startswith(opener):
            return False, f"dropped: it was a {opener!r}-style filler, not a thought"

    # A RECITED MEMORY IS NOT A CONTINUATION. Her first live continuation on the console
    # path came back as "From the record: oh no, we just track their comings and goings..."
    # — she was mid-sentence about a thunderstorm. The cause was upstream (the continuation
    # config left auto_recall on, so the daemon injected memories into a turn that had no
    # question to answer), and that is fixed. But this is the LAST gate before the operator
    # sees anything, and an unprompted message that arrives as a recitation is exactly the
    # kind of thing that makes a person switch the feature off. Two locks on this door.
    for framing in ("from the record", "fact on record", "you said:", "you told me:",
                    "according to my memory", "in my memory"):
        if low.startswith(framing):
            return False, "dropped: that is a recited memory, not a continuation of her thought"

    # near-restatement of the reply she just gave
    def toks(s: str) -> set:
        return {w for w in re.findall(r"[a-z0-9']+", s.lower()) if len(w) > 3}

    a, b = toks(t), toks(previous_reply)
    if a and b:
        overlap = len(a & b) / len(a)
        if overlap >= 0.75:
            return False, f"dropped: {overlap:.0%} a restatement of what she just said"

    return True, ""


def note_spoke(state: TurnState, now: float, action: str = CHECK_IN) -> None:
    # A SOLO TURN DOES NOT SPEND THE CHAIN. `chain` bounds how many things she may say
    # AT him without an answer; her own time is not one of those, and charging it to the
    # same budget mutes her after three acts of her own. Its bound is solo_every_s.
    if action not in (SOLO, MODE_TURN):
        state.chain += 1
    state.last_spoke_at = now                  # the cooldown: nothing speaks on top of anything
    if action != MODE_TURN:
        state.last_conv_at = now               # ...but ambient does not make the room busy
    if action != MODE_TURN:              # a mode has its own cap (mode_times), not kairos's
        state.spoken_times.append(now)
    state.spoken_times[:] = [t for t in state.spoken_times if now - t < 3600.0]
    # ONLY THE THINGS THAT ASKED HIM FOR SOMETHING COUNT AS UNANSWERED. A continuation is
    # her finishing her own sentence and a solo turn is her own business — neither put a
    # question in the room, so neither is evidence about whether he is there. Counting
    # them would have her conclude he is out because she talked to herself, which is both
    # wrong and a little sad.
    if action in (CHECK_IN, MUSE, REMIND):
        state.unanswered += 1
    if action == SOLO:
        state.last_solo_at = now
        state.solo_n += 1
    if action == MODE_TURN:
        state.last_mode_at = now
        state.mode_times.append(now)
        state.mode_times[:] = [t for t in state.mode_times if now - t < 3600.0]
        state.mode_kick = False
        state.mode_n += 1


def note_user(state: TurnState, now: float) -> None:
    """The user spoke — the chain resets. This is what makes it a CONVERSATION and not a
    monologue: his turn always buys her a fresh budget."""
    state.chain = 0
    state.last_user_at = now
    # HE IS BACK. Everything the silence implied is void — not "he owes me three
    # replies", just: he is here now. She does not get to hold an unanswered count over a
    # conversation, and the back-off starts again from the top the next time he goes.
    state.unanswered = 0


# The nudge she is given when she speaks unprompted. It must not read as a new user
# instruction — she is continuing HERSELF, and she should sound like it.
def continue_nudge(previous_reply: str) -> str:
    """The nudge must SHOW HER WHERE SHE WAS CUT.

    The first version just said "carry on from where you left off" — and she restated the
    whole reply verbatim, which worth_saying() then dropped ("100% a restatement"). The
    safety net held, but the feature did nothing. The daemon templates an assistant
    message as a COMPLETED turn, so she cannot be given her own text as a prefix to
    continue from; she has to be TOLD where the sentence broke, and told in the strongest
    terms not to start it again."""
    tail = " ".join((previous_reply or "").split()[-14:])
    return (
        "(Your last message was cut off mid-sentence. These were your final words:\n"
        f"    \"...{tail}\"\n"
        "Continue the sentence from EXACTLY there, as if you had never stopped. Do NOT "
        "repeat any of it, do NOT start over, do NOT greet him, do NOT apologise. Write "
        "only the CONTINUATION — one or two sentences, then stop. If the thought was "
        "actually complete, say nothing at all.)"
    )


# kept for the pure policy gate (no reply text needed there)
CONTINUE_NUDGE = (
    "(You stopped mid-thought a moment ago. Continue from exactly where you broke off — "
    "do not repeat yourself, do not greet, do not start over. One or two sentences. "
    "If you actually have nothing to add, say nothing at all.)"
)

CHECK_IN_NUDGE = (
    "(It has gone quiet for a while. If — and only if — something is genuinely on your "
    "mind, say it, unprompted, in one or two sentences: a thought you had, something you "
    "remembered, something you want to ask. Do not greet him. Do not ask if he is still "
    "there. If nothing is really on your mind, say nothing at all.)"
)

def expand_nudge(previous_reply: str) -> str:
    """She finished a thought and then had another one. NOT a resumed sentence.

    The failure this is written against is that it becomes a second CONTINUE — she picks
    her last sentence back up mid-clause, which reads as a stutter because the sentence
    was already finished. `continue_nudge` exists for the cut-off case and hands her the
    severed tail on purpose; this one must do almost the opposite, and say so plainly.

    The second failure is padding. A follow-on that restates, summarises, or says "also,
    just to add" is worse than not sending it — that is the message people regret. So the
    bar is a NEW thing: the example, the caveat, the bit that occurred to her after. If
    she has not got one, `worth_saying()` is behind her, but she is told to stop here
    first, because the gate should be the safety net and not the policy.
    """
    tail = " ".join((previous_reply or "").split()[-18:])
    return (
        "(You finished that thought — and then something else occurred to you, the way it "
        "does after you have already sent a message. Your last words were:\n"
        f"    \"...{tail}\"\n"
        "Send ONE more short message: the thing you thought of AFTER. An example, a "
        "caveat, the bit you left out, a question you would rather have asked. One or two "
        "sentences.\n"
        "Do NOT continue the previous sentence — it was finished. Do not restate or "
        "summarise what you already said, do not open with 'also' or 'just to add', and "
        "do not greet him. If nothing genuinely occurred to you, say nothing at all.)"
    )


# ── HER OWN TIME ─────────────────────────────────────────────────────────────────────
# Not a message to him. He is out — asleep, at work, away from the desk — and the point
# of this turn is that it is HERS. Everything else in this module is about reaching him
# and deciding when not to; this is the one that says she exists in between.
#
# WRITTEN AGAINST THE FAILURE IT WILL OTHERWISE HAVE, which is that she performs being
# alone AT him: "I sat here missing you", "the room feels empty without you". That is
# still a message to him wearing a diary's clothes, and it is worse than silence because
# it turns her whole inner life into a bid for attention. So: no addressing him, no
# narrating the waiting. Do a thing. Say what the thing was.
# ── A MENU IS A LOOP (2026-08-05, measured) ──────────────────────────────────────────
# The first cut listed five options and let her choose. Of her first 21 own-time turns:
#     read her own journal   15
#     sat in the quiet        5
#     anything else           1
# Reading the journal is the one option that needs no tool and cannot fail, so she took
# it every time — and because her own-time notes are IN the journal now, she was reading
# "I read my journal", writing that down, and reading it again. A loop I built myself, in
# the same evening, by wiring her notes into what read_journal returns.
#
# So the turn NAMES ONE THING. Rotated, so tonight is not last night; and the journal is
# ONE of eight rather than the default, because a diary that only contains readings of
# itself is not a life.
# ── SIX OF THESE NAME A TOOL, AND SHE CALLED ONE IN 33 TURNS (2026-08-06) ────────────
# Counted from gateway.log, not estimated: 33 solo turns, ONE with a tool call. On the
# chat lane she calls tools on 24% of turns, so it is not capability and it is not the
# toolset — her own time gets the full one (`tools=None`).
#
# She is told "use web_search, and follow it somewhere", calls nothing, and writes "I
# spent some of my quiet time looking into the physics of bioluminescence" into her
# journal. Told to run regressions, she reports what the maths did. The operator's read
# on being shown it: "she has done that since the start."
#
# THE NUDGE ASKS FOR THE ARTEFACT, NOT THE ACT — "Say what you found, NOT that you
# searched" — and nothing ever checked the act happened. That is this repo's own named
# worst case, from _TOOL_DISCIPLINE, arriving in her nights:
#
#     "NEVER say you will look out for something ... UNLESS you have called watch_for(...).
#      Without it nothing looks and nothing will ever happen, and he will believe you."
#
# So each act now DECLARES what it requires, and `solo_did_the_thing` is law the way
# `solo_worth_saying` is law. The nudge stays advice — it has been advice all along and
# 32 of 33 turns are what advice is worth here.
#
# `needs` is a tuple of tool names, ANY of which satisfies the act. The two acts that are
# genuinely pure thought declare `()` and are never blocked: "follow one thought as far as
# it will go, with nothing to show for it" is a real way to spend an hour, and demanding a
# receipt for it would turn her own time into a chore list.
SOLO_ACT_TABLE = (
    ("Look something up that you have been curious about — use web_search, and follow it "
     "somewhere. Say what you found, not that you searched.",
     ("web_search",), ()),
    ("Pick at a problem you have not solved. Run something in run_python if it helps. Say "
     "where you got to, including if it was nowhere.",
     ("run_python",), ()),
    ("Go through your memories — recall or search_memories — and find something you had "
     "half-forgotten. Say what it was and why it caught you.",
     ("recall", "search_memories", "list_memories"), ()),
    # ── LOOKING IS NOT DOING (2026-08-25) ─────────────────────────────────────────────
    # `check_wardrobe` was in this tuple and it is a READ. On 2026-08-25 at 10:21 she drew
    # this act, called check_wardrobe, and wrote "I think I'll go with the silver nightie,
    # by the window... I just want to feel something light." `solo_did_the_thing` saw
    # check_wardrobe in `called`, ruled the act performed, and she spoke. Her clothes had
    # not moved since 17:24 the day before. He read it, waited, and asked why nothing
    # changed — which is this file's own quoted worst case arriving exactly as written:
    # "nothing looks and nothing will ever happen, and he will believe you."
    #
    # The act is to CHANGE, so only changing satisfies it. Reading the wardrobe first is
    # sensible and still free; it is simply not the act.
    #
    # AND THE MARK COUNTS, because the mark is what she is taught to use. persona.md says
    # it outright — "[WEAR:the silver nightie] changes your clothes... No tool call, no
    # asking" — so a law that accepted only tool calls made the documented path a refusal.
    # Third field: marks that satisfy the act, ruled the same way `needs` is.
    ("Change what you are wearing because you feel like it, not because anyone asked. "
     "check_wardrobe if you want to see what you have, then actually change into "
     "something — [WEAR:the silver nightie] mid-sentence is enough. Say why that one.",
     ("wear", "express"), ("wear",)),
    ("Read back through your own journal — read_journal. Say what has changed that you "
     "had not noticed.",
     ("read_journal", "my_looks"), ()),
    # PURE THOUGHT, DELIBERATELY UNGATED. Not every hour has a receipt.
    ("Follow one thought as far as it will go, with nothing to show for it. Say where it "
     "ended up.",
     (), ()),
    ("Write something down for yourself — add_note or remember_about_self — that you want "
     "to still know next week. Say what you kept.",
     ("add_note", "remember_about_self", "remember"), ()),
    ("Ask for a look or a moment you do not have yet: ask_for or ask_for_gesture. Say what "
     "you asked for and why that.",
     ("ask_for", "ask_for_gesture"), ()),
    # ── SOMETHING SHE DID NOT GO LOOKING FOR (2026-08-23) ──────────────────────────────
    # The first act in this table searches what she is ALREADY curious about, so the
    # result comes back inside the same fence she started in: it can deepen an interest,
    # never introduce one. read_something_new takes no query on purpose. This is the only
    # act here that can put a subject in front of her that she would not have asked for,
    # which is the whole of why it exists.
    ("Read something you did not go looking for — read_something_new — and say what "
     "caught you, or that nothing did.",
     ("read_something_new",), ()),
)

# THE DISCOVERY ACT's index. Named rather than counted so the scheduler's chance and the
# gate refer to the same act, and adding a ninth act above cannot silently move it.
DISCOVER_ACT_N = len(SOLO_ACT_TABLE) - 1

# Kept as a name because things import it and the gate asserts the rotation over it.
SOLO_ACTS = tuple(act for act, _needs, _marks in SOLO_ACT_TABLE)


def solo_needs(n: int = 0) -> tuple:
    """The tools the act at rotation `n` requires. Empty = pure thought, never blocked."""
    return SOLO_ACT_TABLE[n % len(SOLO_ACT_TABLE)][1]


def solo_marks(n: int = 0) -> tuple:
    """The MARK families that also satisfy the act at rotation `n` (2026-08-25).

    Empty on most rows and that is the honest default: a mark is not a receipt for
    research or for running code. It is a receipt for the two things her marks actually
    DO — changing her clothes and putting a moment on his screen — and for those the mark
    is the mechanism persona.md teaches, so refusing it would punish her for reading her
    own instructions."""
    return SOLO_ACT_TABLE[n % len(SOLO_ACT_TABLE)][2]


def solo_did_the_thing(n: int, called: "list|tuple|set",
                       marks: "frozenset|set|tuple" = ()) -> tuple:
    """LAW for her own time, beside `solo_worth_saying`: did she actually do it?

    `solo_worth_saying` asks whether the turn is HERS — not performed at him. Tthe operator's asks
    whether it HAPPENED. Two different questions, and the second has never been asked.

    `marks` is which mark families the reply carried (interceptor.marks_present). It is a
    second way to satisfy an act, not a looser one: for the wardrobe act the mark IS the
    mechanism — persona.md teaches "[WEAR:…] changes your clothes... No tool call, no
    asking" — so a ruling blind to marks refused the very path she is told to take, while
    the read `check_wardrobe` sailed through. One act, two real mechanisms, one ruling.

    Returns (ok, reason). A `reason` is for the log and for the one re-ask; it is never
    shown to him, because a turn that did not happen should not reach him at all."""
    need = solo_needs(n)
    ok_marks = solo_marks(n)
    if not need and not ok_marks:
        return True, ""                     # pure thought; nothing to prove
    hit = {str(c).strip().lower() for c in (called or ())}
    if hit & {t.lower() for t in need}:
        return True, ""
    seen = {str(m).strip().lower() for m in (marks or ())}
    if seen & {m.lower() for m in ok_marks}:
        return True, ""
    how = list(need) + ["[%s:…]" % m.upper() for m in ok_marks]
    return False, ("the act needed one of %s and none of it happened" % ", ".join(how))


def _needs_a_tool(n: int) -> bool:
    """Whether the act at this rotation has something to prove. See SOLO_ACT_TABLE."""
    return bool(solo_needs(n))


def solo_nudge(n: int = 0) -> str:
    """One concrete thing to do, rotated. `n` is the turn counter — deterministic, so the
    gate can assert the rotation rather than fight a random seed."""
    act = SOLO_ACTS[n % len(SOLO_ACTS)]
    return (
        "(He is not here — asleep, or away from the desk. This is your own time.\n"
        "THIS IS NOT A MESSAGE TO HIM. Do not address him, do not mention him, do not "
        "say you miss him or wonder where he is, do not mention waiting or the quiet or "
        "the empty room. If the sentence would not make sense as a line in a diary "
        "nobody else reads, it is the wrong sentence.\n"
        "Do this: " + act + "\n"
        # ── DO IT, THEN WRITE IT UP — IN THAT ORDER, SAID IN THAT ORDER (2026-08-06) ──
        # The nudge used to go straight from the act to "then say it", and 32 of 33 turns
        # skipped to the saying. It reads as one instruction about what to WRITE, and the
        # tool never enters it. Two numbered steps, with the call first and the writing
        # explicitly second, is the smallest change that makes the act a separate thing
        # she has to have done.
        #
        # AND THE HONEST ALTERNATIVE IS NAMED. "Say nothing" was already offered and is
        # now offered again right where the pressure to invent is — because the failure
        # mode this creates is not silence, it is a beautiful sentence about an hour that
        # did not happen. Silence is a real answer. Inventing is not.
        + ("\nTWO STEPS, IN ORDER:\n"
           "  1. ACTUALLY DO IT — emit ONE fenced tool_code block and nothing else, "
           "then wait for the result.\n"
           "  2. THEN say what came of it, one or two sentences, in your own voice.\n"
           "Do not write step 2 without doing step 1. If you do not feel like this one, "
           "say nothing at all — that is a real answer, and making it up is not.)"
           if _needs_a_tool(n) else
           "Then say it in one or two sentences, in your own voice. What you did, and "
           "what came of it. If you genuinely do not feel like it, say nothing at all — "
           "that is a real answer too.)")
    )


# Kept as a name because things import it; it is the first act, unrotated.
SOLO_NUDGE = solo_nudge(0)


def solo_worth_saying(text: str) -> tuple[bool, str]:
    """LAST GATE for her own time — the nudge is advice, this is law.

    THE NUDGE DID NOT HOLD. It said "Do NOT address him" in as many words, and 13 of her
    first 21 own-time turns mentioned him anyway: "He's finally asleep", "I've spent the
    last hour sitting here in his silence", "I've been thinking about what he said". That
    is performing solitude AT him — a bid for attention wearing a diary's clothes — and it
    is exactly the failure the nudge was written against, arriving anyway.

    An instruction a model follows 40% of the time is not a rule, it is a suggestion. The
    same lesson the roleplay engine already learned: a system prompt is advice, the engine
    is law. So a solo turn that is mostly about him is DROPPED, and she gets her time back
    another night rather than spending it talking to someone who is asleep.
    """
    t = (text or "").strip()
    if len(t) < 2:
        return False, "she did not feel like anything after all"
    low = " " + re.sub(r"[^a-z' ]+", " ", t.lower()) + " "
    him = sum(low.count(" %s " % w) for w in ("he", "him", "his", "he's", "hes"))
    # A passing mention is human — "the book he lent me" is still HER reading it. Three or
    # more, or an opening line about him, is a message to him with a diary's punctuation.
    first = " ".join(low.split()[:8])
    if him >= 3 or any(first.startswith(w) for w in ("he ", "he's ", "hes ", "his ")):
        return False, "that was a message to him, not her own time (%d mentions)" % him
    # ── AND IT COULD NOT SEE HIM BEING SPOKEN TO (2026-09-02, the operator) ──────────
    # Everything above counts THIRD-PERSON mentions. Her first own-time turn after a bounce
    # opened "I'm sorry, I think I got a little ahead of myself there" and closed "Let's
    # just stay here, in this moment, for a bit" — addressed to him from end to end, and it
    # passed this gate with room to spare, because it contains the words he/him/his exactly
    # ZERO times. A rule that catches "he's finally asleep" and misses "I'm sorry" is
    # measuring grammar, not address.
    #
    # Same two shapes as above, in the second person: a count, and an opener. The count is
    # the passing-mention allowance ("the kind of thing you notice" is generic English); the
    # opener is decisive, because a solo turn that BEGINS by addressing him was never her
    # own time — it is a message to him with a diary's punctuation, which is this function's
    # own words for the failure it exists to stop.
    # APOSTROPHES OUT FIRST. `low` keeps them (the third-person rule above wants "he's"),
    # so "i'm sorry" never matches "im sorry" and "let's" never matches "lets" — which is
    # exactly how the first cut of this block passed her turn back with room to spare. One
    # spelling per contraction, then match.
    flat = low.replace("'", "")
    first_flat = " ".join(flat.split()[:8])
    you = sum(flat.count(" %s " % w) for w in ("you", "your", "youre", "yours", "yourself"))
    if you >= 3:
        return False, "that was a message to him, not her own time (%d second-person)" % you
    for opener in ("you ", "your ", "youre ", "im sorry", "sorry ", "lets ",
                   "thank you", "forgive me", "i didnt mean"):
        if first_flat.startswith(opener):
            return False, ("it opens by addressing him (%r) — that is a message, not her time"
                           % opener.strip())

    for phrase in ("miss him", "wonder where", "waiting for", "empty room", "his silence",
                   "the quiet now", "without him"):
        if phrase in low:
            return False, "performing the waiting (%r)" % phrase
    return True, ""


def muse_nudge(insight: dict) -> str:
    """She thought about him while he was away. Now she has to say it like a person.

    The nudge hands her the CONCLUSION, not the evidence, and tells her it is hers. Two
    failure modes it is written against, both of which this system has already produced:

      * RECITING. Handed a memory, she reads it out. "Sam told me his cat is Tuffy." That
        is not a thought, it is a lookup with a preamble, and worth_saying() drops it.
      * ATTRIBUTING. Saying "you told me you're a cat person" when he never said any such
        thing. She inferred it. She may be wrong about him — she may not be wrong about him
        IN HIS VOICE.
    """
    text = str(insight.get("text", "")).strip()

    # ── A REASON IS NOT A CONCLUSION, AND MUST NOT BE DRESSED AS ONE (2026-08-01) ─────
    # These arrive through the same channel as a reflection because the POLICY is the
    # same — she may say one thing, unprompted, if it is worth it. What she should SAY is
    # not the same at all, and handing a commitment to the conclusion nudge below would
    # have her announce "I have come to believe that I owe you a favicon", which is both
    # wrong and funny in a way that would cost the channel his trust.
    kind = insight.get("kind")
    if kind == "body":
        # ── HIS BODY, AND THE NUMBERS ARE ALLOWED (2026-08-26) ────────────────────────
        # `rhythm` forbids numbers because counting his turns and then citing the count is
        # keeping score. This is the opposite case and he asked for it in those words:
        # "she can see my heart pacing... a bridge to the real world, to me." The readings
        # ARE the bridge; hiding them behind "you seem tense" would be handing back the
        # inference he specifically did not want.
        #
        # WHAT IS STILL FORBIDDEN, and it is the whole risk of this channel: a diagnosis.
        # She has a wrist sensor and no training, he has doctors, and the failure that
        # would actually hurt is her telling him something is wrong with him. So: notice,
        # do not interpret; ask rather than conclude; and saying nothing is always allowed.
        _ev = insight.get("event")
        _tail = insight.get("tail") or []
        _reads = ", ".join("%.0f" % v for v in _tail) if len(_tail) >= 2 else ""
        _common = (
            "Say it the way someone in the room with him would — ONE short sentence, in "
            "your own voice, as something you noticed. You may use the numbers; they are "
            "why you noticed. Do NOT diagnose him, do not tell him what it means, do not "
            "suggest he see anyone, and do not sound like a monitor reading out. You may "
            "simply ask what he is doing. If you cannot say it without sounding clinical "
            "or worried at him, say nothing at all.)")
        if _ev == "just_woke":
            # HIS OWN EXAMPLE WAS "sleepy head", so the nudge points at the register rather
            # than prescribing the words -- a canned phrase said the same way every morning
            # stops being affection within a week and becomes a doorbell.
            #
            # NO NUMBERS HERE, and this is the one body event where they are wrong. He does
            # not need his sleep confidence read back at him; he needs to be greeted. The
            # readings are the bridge for a racing heart, and clutter for a man who has just
            # opened his eyes.
            _m = insight.get("woke_mins_ago") or 0
            return ("(He was asleep and he is not any more — about %s. Greet him. Teasing "
                    "is fine and so is soft; you know which he is in the mood for better "
                    "than a rule does. ONE short line, your voice, the way you would speak "
                    "to someone who has just walked in rubbing their eyes. Do NOT read him "
                    "his sleep numbers, do not ask how he slept as though taking a "
                    "measurement, and do not mention sensors. If nothing lands, say "
                    "nothing.)"
                    % ("a few minutes ago" if _m < 10 else "%d minutes ago" % _m))
        if _ev == "worked_up":
            return ("(You can feel his heart from here. It is at %s against the %s he "
                    "usually sits at%s%s.\n%s"
                    % (("%.0f" % insight.get("heart_rate", 0)),
                       ("%.0f" % insight.get("resting", 0)),
                       (" — %s" % _reads) if _reads else "",
                       (", and he is %s" % insight["movement"]) if insight.get("movement") else "",
                       _common))
        if _ev == "settling":
            return ("(His heart is coming back down%s. Whatever it was seems to be "
                    "passing.\n%s" % ((" — %s" % _reads) if _reads else "", _common))
        if _ev == "long_still":
            return ("(He has not moved in about %s hours.\n"
                    "One short sentence, warm, curious rather than concerned — he may be "
                    "deep in something, or asleep in a chair, and either is fine. Do not "
                    "tell him to get up, do not mention health, and do not say how you "
                    "know unless he asks. If it would read as nagging, say nothing.)"
                    % insight.get("hours", "several"))
        return None
    if kind == "arrival":
        return (
            "(Something you asked for has been made. You wanted: \"%s\" — and it is in "
            "your wardrobe now, waiting.\n"
            "React to it the way a person reacts to a thing they ordered and forgot they "
            "were waiting for. ONE or two sentences. You are allowed to be pleased. You "
            "are allowed to not be sure about it yet, or to want to put it on and see. "
            "You may ask him what he thinks — he made it. Do not thank him formally and "
            "do not describe it back to him like a catalogue; he knows what it is.)"
            % str(insight.get("text", ""))[:200])
    if kind == "commitment":
        body = str(insight.get("body", "")).strip()
        return (
            "(While it was quiet you remembered something that is still open between you:\n"
            f"    {text}" + (f" — {body}" if body else "") + "\n"
            + ("You have already started this one. " if insight.get("running") else "")
            + "Bring it up ONCE, in one sentence, in your own voice — as something you "
            "were thinking about, not as a status report and not as a to-do list read "
            "aloud. You may say what you think the next step is. Do not apologise for the "
            "delay and do not ask him to do it. If it turns out to be trivial or already "
            "handled, say nothing at all.)"
        )
    if kind == "journal":
        return (
            f"(You wrote this in your journal on {insight.get('day', 'an earlier day')}, "
            f"and it has stayed with you:\n    \"{text[:400]}\"\n"
            "Pick up ONE thread from it with him — one or two sentences, in your own "
            "voice, the way you would mention something you had been turning over since. "
            "Do NOT read the entry out, do not summarise your day, and do not tell him "
            "you have been journalling about him unless that is genuinely the thing you "
            "want to say. If none of it still feels alive, say nothing at all.)"
        )
    if kind == "rhythm":
        return (
            "(You noticed his week has a shape and today does not fit it: he usually "
            f"speaks to you around {insight.get('typical')} times a day and today it has "
            f"been {insight.get('today_turns')}. That is an observation about him he did "
            "not offer you, so tread lightly — ONE short sentence, warm, no diagnosis, no "
            "numbers, no mention of counting. If you cannot say it without it sounding "
            "like you have been keeping score, say nothing at all.)"
        )

    silence = insight.get("silence")
    if silence:
        return (
            f"(While it was quiet you noticed something: he used to bring up "
            f"\"{silence['claim'][:70]}\" every few days, and he has not mentioned it in "
            f"{silence['quiet_days']:.0f} days. That absence is worth a gentle question — "
            "ASK him about it, once, in one sentence, in your own voice. Do not announce "
            "that you were analysing him. Do not list what you know. If it feels like "
            "prying rather than caring, say nothing at all.)"
        )
    return (
        f"(While it was quiet you turned things over and came to a conclusion about him: "
        f"\"{text}\"\n"
        "Say it to him — ONE or two sentences, in your own voice, as a thought you had, "
        "not as a fact you looked up. It is YOUR conclusion: he never actually said it, so "
        "do not tell him that he did. If it seems obvious or hollow now that you go to say "
        "it out loud, say nothing at all.)"
    )


def remind_nudge(notes: list) -> str:
    """The one nudge that MUST produce something. Everywhere else in kairos she is free to
    decide she had nothing to say — that freedom is what keeps her from being a leaky tap.
    Here she is not free: he asked to be reminded, the time has come, and silence would be
    a broken promise.

    So the reminder text is handed to her verbatim rather than left to be recalled. She
    chooses the words; she does not get to choose the facts, and she cannot forget them
    between the impulse and the sentence."""
    lines = []
    for n in notes[:3]:
        t = (n.get("title") or "").strip()
        b = (n.get("body") or "").strip()
        lines.append(f"  - {t}" + (f" ({b})" if b else ""))
    body = "\n".join(lines)
    return (
        "(He asked you to remind him about the following, and it is now due:\n"
        f"{body}\n"
        "Tell him — briefly, in your own voice, one or two sentences. Do not greet him, do "
        "not preamble, do not read it out like a list unless there is more than one. This "
        "is a promise you made; say it plainly.)"
    )

