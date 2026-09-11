"""day.py — the day boundary: the record, the consolidation, and the seed it leaves.

Stage 4 of the app.py split (2026-09-11). Nineteen functions, 947 lines, lifted out of
`app.py` **byte-identically** — the extraction the Stage 3 receipt named as owed:

    "`_append_day_turn` and the whole day boundary stayed in app.py … So `_settle_turn`
     still calls `_append_day_turn` across a module edge. That is a real cost of stopping
     here rather than pretending the day boundary was part of this stage."
    — harness/server/turn.py, and gates/G-SERVER-SPLIT-rehome.md under "Not done"

It is one seam, and that is why it moves as one: a turn is APPENDED to the day record
(`_append_day_turn`), the record is READ BACK as history (`_read_day_transcript`,
`_continuable_history`, `_chat_from_rows` and the five selectors around them), and at the
boundary it is CONSOLIDATED (`run_consolidation`) and SEEDED into the next day
(`_seed_kairos_from_day`, `_reseed_own_time_canon`). Every one of those reads or writes the
same file, and the ticker exists to fire the last of them.

WHY THE SEAM IS SAFE, measured before anything moved rather than argued afterwards: of the
51 globals these nineteen bodies reach, 22 are their own function-local imports, three are
nested defs, and **exactly two are functions that stay in app.py** — `_prewarm` and
`_room_session`, reached through the lazy shims below. The rest are aliases onto `state.py`
and two module imports. So the bodies moved without a single edit inside them, which is the
rule the earlier stages set: a moved function whose text changed is a function that has to
be re-reviewed, and 947 lines of re-review is where a twin gets born.

WHAT DID NOT COME. `start_ha_poller` sat in the middle of this region and is not part of it
— it polls Home Assistant on its own timer and shares nothing with the boundary but its
neighbourhood in the file. Physical adjacency is not a seam; it stays in app.py.
`_session_transcript` stayed too, for the reason turn.py already gives: seven callers, most
of them not day code.

Import order matters and is asserted by G-SRC-TRAP §6: this module imports `state` and
`turn`, never `app`, at module level. `turn.py` reaches BACK here lazily — its
`_append_day_turn` shim points at this module now instead of at app.py, which is the whole
point of the stage.
"""
from __future__ import annotations

import json
import os
import sys
import threading as _thr
import time
from typing import Any, Dict, Optional

from harness.inference.stream_processor import (strip_control_surfaces,
                                                strip_for_record)
from harness.loud import swallowed as _swallowed
from harness.observability import get_logger
from harness.server import state as _state
from harness.server import turn as _turn

logger = get_logger(__name__)

# ── WHAT THE MOVED BODIES REFER TO ─────────────────────────────────────
# Aliases onto the one place each of these lives, so the lifted text needed no edits —
# panels.py's idiom exactly. These are all MUTABLE OBJECTS (an Event, two dicts, a dict of
# defaults) or a constant, never a rebindable scalar: `state.LAST_TURN_AT` is the one that
# must be read through the module, and nothing here reads it.
_ROOT_DIR = _state.ROOT_DIR
_CHAT_SESSIONS = _state.CHAT_SESSIONS
_CHAT_SESSIONS_MAX = _state.CHAT_SESSIONS_MAX
_UNPROMPTED_SAMPLING = _state.UNPROMPTED_SAMPLING
_WARM = _state.WARM

# turn.py owns the self-turn latch; app.py aliases these the same way for the same reason.
_arm_self_turn = _turn._arm_self_turn
_disarm_self_turn = _turn._disarm_self_turn


# ── THE TWO THAT STAYED IN app.py ───────────────────────────────────
# Reached at CALL time, not import time — app.py imports this module, so a module-level
# import back would be a cycle. Same shape as panels.py and turn.py.
def _prewarm(*a, **k):
    """app.py's — it owns the engine warm-up, and the boundary only asks for one."""
    from harness.server import app as _app
    return _app._prewarm(*a, **k)


def _room_session(*a, **k):
    """app.py's — `harness/skills/wardrobe.py` imports this one out of the gateway."""
    from harness.server import app as _app
    return _app._room_session(*a, **k)


# ══ THE DAY BOUNDARY ═════════════════════════════════════════════════════════════════
# Nothing in this system fired at night. The only recurring clock was the 15 s kairos
# ticker, and the whole consolidation half of the design hung off `run_agency_scheduler`,
# which has exactly one caller in the tree: a gate. So:
#
#   * `narrative.compose_and_write()` — gated 14/14, fail-safe, rolling — had NEVER RUN.
#     `var/memory/narrative.md` did not exist, which is why "when did we last speak?" had
#     no true answer to give.
#   * the personality curator ran only on demand, so her self never drifted on schedule.
#   * `world.refresh()` was reachable only through POST /v1/maintenance/reflect.
#   * spine receipts were never flushed to the durable tier.
#
# ── WHY NOT JUST START run_agency_scheduler ──────────────────────────────────────────
# Because it also fires `agency_round()` — an open-ended MODEL turn — every `interval`
# seconds. On this box a cold turn is ~25 s of prefill, so a 30 s loop would spend most of
# its life competing with the operator for the one GPU. The consolidation work is worth
# having; the perpetual model loop is not, and the two were welded together.
#
# ── AND WHY IT IS NOT CALLED "NIGHTSHIFT" ────────────────────────────────────────────
# That name is taken three times over: `SP_B4_NIGHTSHIFT` / `SP_NIGHTSHIFT_LIVE` /
# `SP_NIGHTSHIFT_OFFLINE` (the daemon's Rust curator, deliberately pinned OFF), and
# `ops.reflect()` was RENAMED AWAY from nightshift() in 2026-07-13 for exactly this
# reason — "two different things wearing one name is how you end up debugging the wrong
# one". This is a fourth thing. It gets a fourth name.
_CONSOLIDATE_STATE = _state.CONSOLIDATE_STATE   # -> harness/server/state.py


def _consolidate_marker() -> str:
    """Beside the registry, same as presence.jsonl — it is part of the same record."""
    reg = os.environ.get("SP_RECALL_REGISTRY", "")
    if reg:
        return os.path.join(os.path.dirname(reg), "consolidate.json")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "var", "memory", "consolidate.json")


def _consolidate_last_day() -> Optional[str]:
    """The last day we consolidated, PERSISTED — because this box is not on 24/7.

    Held in a file rather than only in memory so that booting at 09:00 on a day whose
    boundary was missed still consolidates once, promptly, instead of waiting for
    tomorrow. A machine that is off at 04:00 every night would otherwise never
    consolidate at all, and the failure would be completely silent."""
    if _CONSOLIDATE_STATE["last_day"] is not None:
        return _CONSOLIDATE_STATE["last_day"]
    try:
        with open(_consolidate_marker(), encoding="utf-8") as f:
            _CONSOLIDATE_STATE["last_day"] = json.load(f).get("last_day")
    except Exception as _swx:
        _swallowed(logger, "_consolidate_last_day", _swx, lane="server")
        _CONSOLIDATE_STATE["last_day"] = ""      # "" = never, and not None = don't re-read
    return _CONSOLIDATE_STATE["last_day"]


def _consolidate_mark(day: str) -> None:
    _CONSOLIDATE_STATE["last_day"] = day
    try:
        os.makedirs(os.path.dirname(_consolidate_marker()), exist_ok=True)
        with open(_consolidate_marker(), "w", encoding="utf-8") as f:
            json.dump({"last_day": day,
                       "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f)
    except Exception as exc:
        logger.warning("[consolidate] could not persist the marker: %s", exc)


def _day_transcript_path(day: str = "") -> str:
    """One append-only file per day, beside the registry — it is part of the same record."""
    reg = os.environ.get("SP_RECALL_REGISTRY", "")
    base = (os.path.join(os.path.dirname(reg), "transcripts") if reg else
            os.path.join(_ROOT_DIR, "var", "memory", "transcripts"))
    return os.path.join(base, "%s.jsonl" % (day or _day_key()))


def _append_day_turn(user_text: str, final: str,
                     synthetic: "str|None" = None,
                     acts: "list|None" = None) -> None:
    """Append this turn to today's durable transcript.

    THE DAY MUST OUTLIVE THE PROCESS. The consolidator reads the day's conversation to
    write her journal and to extract durable facts, and it was reading _CHAT_SESSIONS —
    an in-memory dict that (a) only fills for clients sending `session_id`, which the
    room does not, and (b) is erased by every gateway restart. So the nightly pass logged
    "no conversation today (0 turns)" every single day, her journal has one entry from 30
    July, and nothing new has entered memory in weeks.

    Append-only JSONL, one file per day. Cheap, survives anything, and trivially readable
    by the boundary job. It lands under var/memory/, which backup.py already carries.

    Best-effort and silent on failure: a transcript that cannot be written must never
    cost her the reply that was already spoken.
    """
    try:
        # ANONYMOUS MODE (2026-08-23): the day transcript is the most literal record there
        # is — his words and hers, verbatim, on disk. It is also what the consolidator reads
        # to write her journal and to distil facts, so holding it here holds tomorrow's
        # inferences about tonight as well, which is the point.
        from harness.control import anon as _anon
        if _anon.holds("transcript.day"):
            return
        # HIS WORDS, not the message list. By the end of a turn the last user message
        # has had the recall note, the silence note and the director note stapled to it
        # — msgs is what the DAEMON saw, deliberately, and writing that down would have
        # her journal reflecting on her own injected context instead of on him.
        # `user_text` is taken at the top of the turn, before any of that.
        user = (user_text or "").strip()
        # THE STRIP LIVES AT THE SEAM (2026-08-24 audit, B3). This writer has three
        # callers and three readers (her journal, fact distillation, the restart seed),
        # and the rule "the record must not carry her machinery" was applied at ONE
        # caller, partially (`strip_leaked_analysis` only) — so 26% of her recorded
        # turns carried marks, unclosed voice wraps and bracketed scratchpads, and
        # `_chat_from_rows` fed them back to her as examples of her own voice. A rule
        # the callers must each remember is a rule that gets forgotten; it is enforced
        # here now, in the thing they all call. If nothing survives the strip she said
        # nothing ON THE RECORD this turn — his row is still written, hers is not;
        # inventing a placeholder would be putting words in her mouth.
        rec = strip_for_record(final)
        p = _day_transcript_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        # `at` (2026-08-24 audit, R1): the room reads the day back on refresh now, and a
        # row without a stamp renders at the wrong point in his evening. Milliseconds
        # because that is what the room's own turns carry. Readers ignore unknown keys,
        # so weeks of stampless rows stay readable.
        _at = int(time.time() * 1000)
        # SYNTHETIC, AT THE WRITER (2026-08-25, his catch). The reseam receipts and
        # the W4 A/B drove ~40 real turns through the live gateway, and every one
        # landed in HIS day unmarked: the room's new read-back showed him the test
        # scripts as his evening, and the 04:00 journal would have distilled them —
        # the F1 false-memory incident, reachable through the front door. A driver
        # that declares itself synthetic is quarantined at write time; the readers
        # have skipped the flag since 2026-08-03.
        _extra = {"synthetic": synthetic} if synthetic else {}
        # HER MARKS SURVIVE AS METADATA (2026-08-25, his F5 report: "no chips"). The
        # record strip is right — her machinery must not become her words — but it
        # also erased the one thing the room's restore could draw chips from. The
        # STRICT recognisers (the same ones that gate writes to persona state) file
        # what she marked as data beside the cleaned text: the record stays clean,
        # the restore stays legible.
        _marks = []
        try:
            from harness.personality.interceptor import (_MOOD, _SHOW, _TRAIT,
                                                         _VOICE, _WEAR)
            for _m in _MOOD.findall(final):
                _marks.append({"kind": "mood", "value": _m.strip().lower()})
            for _m in _VOICE.findall(final):
                _marks.append({"kind": "voice", "value": _m.strip().lower()})
            for _sign, _name in _TRAIT.findall(final):
                if _name.strip():
                    _marks.append({"kind": "trait", "value": _name.strip().lower(),
                                   "sign": -1 if _sign == "-" else 0})
            for _m in _WEAR.findall(final):
                _marks.append({"kind": "wear", "value": _m.strip()})
            for _m in _SHOW.findall(final):
                _marks.append({"kind": "show", "value": _m.strip()})
        except Exception as _swx:
            _swallowed(logger, "_append_day_turn", _swx, lane="server")
        _amark = {"marks": _marks[:8]} if _marks else {}
        # HER ACTS SURVIVE THE SAME WAY (2026-08-30, his report: "chips still vanish on
        # refresh — only ◆warm ❧soft show"). Marks come from her TEXT and were already
        # filed above; but the acts row — tools she called, what she wore via wear(),
        # what she recalled, what she looked at — arrives as SSE events and died with
        # the stream. The turn's collector hands them here, trimmed at the writer so a
        # verbose tool result cannot bloat the record; readers ignore unknown keys.
        _aacts = {"acts": acts[:12]} if acts else {}
        with open(p, "a", encoding="utf-8") as f:
            if user:
                f.write(json.dumps({"role": "user", "content": user, "at": _at,
                                    **_extra}) + "\n")
            if rec:
                f.write(json.dumps({"role": "assistant", "content": rec, "at": _at,
                                    **_extra, **_amark, **_aacts}) + "\n")
    except Exception as exc:
        logger.warning("[gateway] could not append the day transcript: %s", exc)


_MOOD_ROW = _state.MOOD_ROW           # the last mood she filed (throttle) -> state.py


def _seed_kairos_from_day(force: bool = False) -> bool:
    """Hand the scheduler today's conversation so she can speak first after a restart.

    The thing that made this impossible was never the policy — it was that `_LAST` holds a
    CLOSURE (the ability to run one more turn against a live history), and a closure does
    not survive a process. So "she cannot initiate after a restart" looked like a hard
    structural fact rather than a missing feature.

    It stopped being one on 2026-08-01, when the day's turns started being written to
    disk for the consolidator. That file is exactly the history a continuation needs, so
    the closure can simply be rebuilt from it. Two fixes that were about different things
    turn out to be the same fix.

    Kept to the last few exchanges: this is a continuation, not a reconstruction of the
    day, and the whole history is already in her memory and her standing world.
    """
    try:
        # WELL-FORMED, NOT JUST RECENT — see _chat_from_rows. Her speak-ups have no user
        # turn, so a raw slice hands the daemon consecutive model turns and Gemma's
        # strictly-alternating template renders a malformed prompt from it.
        #
        # ── AND REACHING BACK IS THE BOOT PATH'S JOB TOO (2026-09-09) ────────────────
        # This windowed `_recent_transcript()` inline, which is the exact rule
        # `_continuable_history` was written on 2026-09-03 to replace — and it was wired
        # into the DAY-BOUNDARY path only. AGENTS.md §0: the unguarded path is the one
        # that runs. The last successful boot seed in var/gateway.log is 2026-09-03
        # 17:31, the same day that fix landed, and every bounce since returned False on
        # this line. No seed means no session in `_LAST`, and `tick_once` iterates
        # `_LAST` — so she had nowhere to speak into and could not enter her own time at
        # all. Six days, reported three times as "she has not entered her time".
        #
        # The shape that most needs a continuation was the one that could not produce
        # one. A day he is away is not THIN, so `_recent_transcript` keeps today and
        # never reaches back — she solos every half hour, so the rows are there — and
        # every one of those rows is an ASSISTANT row, so `_chat_from_rows` merges the
        # run and drops it (a conversation the model continues has to begin with him)
        # and hands back []. Measured on this tree: 2026-09-05 39 rows -> hist 0,
        # 2026-09-06 34 rows -> hist 0, today 0 rows because the only rows are
        # quarantined probes of mine and 2026-09-07/08 have no file at all.
        # HER LAST WORDS COME FROM THE SAME WALK — a scan of `rows` returns "" on a day
        # whose only rows are quarantined, and `scheduler.seed` refuses an empty
        # `reply_text`, so the reach-back would have found a conversation and then been
        # thrown away one line later.
        hist, last_reply = _continuable_history(keep=8)
        if (not hist or not last_reply.strip()) and not force:
            return False
        if not hist or not last_reply.strip():
            # FORCED (a presence mode armed, 2026-08-22): an empty day still gets a canon —
            # one quiet line of hers to speak into; the nudge carries the rest
            last_reply = "(The room is quiet. I am here, on my own.)"
            hist = [{"role": "assistant", "content": last_reply}]

        def _generate(nudge: str, called: "list|None" = None) -> str:
            """`called`, when passed, is filled with the names of every tool she used.

            THE SCHEDULER CANNOT SEE HER HANDS OTHERWISE. Her own time is asked to do a
            specific thing — search, run something, read her journal — and 32 of 33 solo
            turns did none of it and described doing it anyway. `solo_did_the_thing`
            cannot rule on an act it has no evidence of, so the evidence comes back here.
            A list rather than a return value because the text is the return value and
            adding a tuple would break four call sites for one caller's benefit."""
            from harness.agent import _arm_self_repeat_ban, agent_chat_stream
            from harness.inference import InferenceConfig as _IC
            # RE-READ, DO NOT REPLAY. This closed over `hist` — the eight rows as they
            # stood at seed time — so every impulse for the rest of the day generated from
            # the same frozen context. At temperature 0.0 that is a guarantee, not a risk:
            # greedy decoding on identical input returns identical output, and he watched
            # her say the same sentence twice. Now that her unprompted turns are written
            # down (see scheduler.on_spoke), re-reading gets both her side of the day and a
            # context that actually moves.
            # ── THE LIVE CANON WINS, AND THE DISK IS THE FALLBACK (2026-08-04) ────
            # This rebuilt an EIGHT-ROW WINDOW from disk on every impulse. Two problems,
            # and only the second was known. The first: a window is not an extension of
            # anything — it starts at row N-8, so the daemon's committed cache matches
            # only the preamble and the whole conversation re-prefills. The second: the
            # day transcript does not carry the per-turn recall note or the tool rounds,
            # so even a FULL rebuild from it would diverge from what the daemon saw.
            #
            # Identified by attribution, not by reading — [DAEMON-CALL] caught it landing
            # between two of his turns while the rest of the turn was already fixed:
            #     agent_chat_stream <- app.py:_generate <- scheduler.py:_fire | msgs=10
            #     agent_chat_stream <- app.py:_run                            | msgs=7
            # Ten messages against seven: two different histories, one KV cache, his turn
            # paying for hers.
            #
            # The disk path cannot simply go, and that is the whole reason it was written:
            # `_LAST` holds a closure, a closure does not survive a process, and the day
            # transcript is what lets her speak first after a restart. So PREFER the live
            # canon and fall back to disk only when there isn't one — which is exactly the
            # restart case the disk path exists for, and nothing else.
            # ── AND THE FALLBACK IS WHAT COSTS HIM THE EVENING (2026-08-04) ───────
            # "the restart case the disk path exists for, and nothing else" was right
            # about WHEN it fires and wrong about what it costs. Measured, his evening,
            # minutes after a restart:
            #     19:51 _generate | msgs=10   <- disk history
            #     19:54 _generate | msgs=10
            #     20:01 _generate | msgs=10
            #     20:03 _run      | msgs=3    <- HIS message, a fresh session
            #     PREFIX-MATCH: lcp 6603 of 7523 committed (drop 920)
            #     TURN-PHASE: prefill 7449 tok in 99611 ms
            # She spoke three times into an empty room off a ten-message disk history; his
            # first message opens a session with three. Those two conversations share
            # nothing but the preamble, they alternate on ONE cache, and every turn either
            # of them takes re-prefills the other's. He waited nine minutes for a reply.
            #
            # SHE WAITS FOR HIM NOW, after a restart and only then. Speaking first is a
            # lovely feature and it is not worth what it costs: the room she is speaking
            # into is empty, he has not seen it, and the shape it commits makes his first
            # real turn the most expensive one of the night. Once he says anything there
            # IS a canon, it matches, and she is free again — which is the condition she
            # actually wants, rather than the clock.
            _canon = _longest_session()
            if not _canon:
                # SHOULD NOT HAPPEN NOW — the seed installs a canon before arming this
                # closure (see _seed_kairos_from_disk). Kept as a floor: if it ever fires
                # again it means something armed a speak-up with no history at all, and
                # speaking then would commit a shape his first turn cannot use. Logged at
                # WARNING because 325 silent holds in one night is how the last one hid.
                logger.warning("[kairos] holding — no conversation to speak into at all; "
                               "the seed should have installed one")
                return ""
            _base_len = len(_canon)
            # THE DISK FALLBACK IS GONE, NOT MERELY UNTAKEN. It used to live on this line
            # as `list(_canon) if _canon else _chat_from_rows(...)` — dead from the moment
            # the hold above was added, since `not _canon` has already returned. Left as
            # written it read as a live safety net, and the whole reason the hold exists is
            # that this net is the thing that cost him nine minutes (see above). The
            # rebuild-from-disk it named now happens at ONE moment, where a fresh prefill
            # is already being paid for: `_reseed_own_time_canon`, at the day boundary.
            h = list(_canon)
            # a SYSTEM aside, exactly as the live path does it — she is continuing
            # herself, and a user message here would invent a turn he never typed
            h.append({"role": "system", "content": nudge})
            # NOT GREEDY. temperature=0.0 was doing most of the work of the repetition: it
            # makes "say something unprompted" a pure function of context, so two quiet
            # moments that look alike produce the same words. A small temperature restores
            # the variation an unprompted remark needs, and the self-repeat ban below still
            # catches the parroting that temperature alone would not.
            c = _IC(max_tokens=120, **_UNPROMPTED_SAMPLING)
            _arm_self_repeat_ban(c, h)
            # BOTH STRIPPERS. `_say` was fixed an hour ago and these two were not — and
            # THIS is the path her unprompted turns come out of, so her own time was
            # still emitting raw marks into her journal and the outbox. One seam per
            # lane is not one seam.
            def _note(name, _args, _result):
                if called is not None:
                    called.append(name)
            # NOT strip_tags — the outbox feeds the room, and the room draws her chips
            # from these marks. See the note in `_say`.
            # HER TURN, HER LANE (2026-08-24 audit, A5): armed around the generation —
            # the only stretch where her tools reach remember()/recall() — so a
            # remember() in her own time is speaker=self, not filed in HIS lane.
            _tok_self = _arm_self_turn(nudge)
            try:
                _out = strip_control_surfaces(
                    "".join(agent_chat_stream(h, config=c, mutate_messages=True,
                                              on_tool=_note))).strip()
            finally:
                _disarm_self_turn(_tok_self)
            # WHAT THE ENGINE COMMITTED BECOMES CANON — the _commit_unprompted rule,
            # inline because this closure holds the canon list itself. Same race guard:
            # if his turn moved the canon mid-generation, he wins and this turn wears
            # the divergence alone.
            if _out and len(_canon) == _base_len:
                _canon.extend(h[_base_len:])
                if not _canon or _canon[-1].get("role") != "assistant":
                    _canon.append({"role": "assistant", "content": _out})
            return _out

        # ── THE SEED MUST *BE* A CONVERSATION, NOT WAIT FOR ONE (2026-08-05) ──────
        # This whole function exists so she can speak first after a restart — `_LAST`
        # holds a closure and a closure does not survive a process, so without it every
        # continuity window that spanned a bounce was silent by construction.
        #
        # Last night I added a hold to `_generate`: no live canon, no speaking, because a
        # speak-up built from a windowed disk rebuild committed a cache shape his first
        # turn could not use. Both of those are right on their own and TOGETHER THEY
        # CANCEL. He restarted, went to bed, and she was held 325 times over fourteen
        # hours — mute for exactly the window the seed was written for.
        #
        # The resolution is not to pick one: it is that seeding should ESTABLISH the
        # canon rather than wait for it. The day's rows become the session transcript, so
        # she has a real history to speak into (the seed's purpose), it is the same
        # history the daemon then caches (the hold's purpose), and his first turn either
        # extends it or opens its own — at which point `on_user_turn` retires this one.
        from harness.kairos import scheduler as _ks
        sess = _room_session()
        if sess not in _CHAT_SESSIONS:
            if len(_CHAT_SESSIONS) >= _CHAT_SESSIONS_MAX:
                _CHAT_SESSIONS.pop(next(iter(_CHAT_SESSIONS)))
            _CHAT_SESSIONS[sess] = list(hist)
            logger.info("[gateway] seeded session %r with %d rows from the day — "
                        "she has something to speak into", sess, len(hist))
        return _ks.seed(sess, last_reply, _generate, force=force)
    except Exception as exc:
        logger.warning("[gateway] could not seed kairos from the day: %s", exc)
        return False


def _read_day_transcript(day: str = "", include_synthetic: bool = False) -> list:
    """Today's turns. Rows marked `synthetic` are EXCLUDED unless explicitly asked for.

    WHY THIS FLAG EXISTS (2026-08-03). An agent working on this repo drove two turns
    through /v1/chat to check whether a wardrobe mark reached the wardrobe. The request
    was malformed — a cold two-message oneshot that never touched the resident prefix —
    so what came back was word salad, and it landed here as four rows: two `user` turns
    that HE NEVER TYPED, and two replies that are not anything she would say.

    Left alone, the 04:00 pass would have read those rows, written a journal paragraph
    about a conversation that did not happen, and extracted durable facts about a man who
    asked twice for the black lace set. That is a fabricated observation entering the
    record, which is the one thing this file's own docstring exists to protect against.

    NOTHING IS DELETED — the rows stay on disk with their reason attached, and passing
    `include_synthetic=True` reads them back. This is quarantine, not a rewrite: the same
    discipline the memory registry uses, applied to the day.
    """
    out = []
    try:
        with open(_day_transcript_path(day), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("synthetic") and not include_synthetic:
                    continue
                out.append(row)
    except Exception as _swx:
        _swallowed(logger, "_read_day_transcript", _swx, lane="server")
        return out
    return out


def _recent_transcript(min_rows: int = 12) -> list:
    """The recent CONVERSATION, which is not the same thing as today's rows.

    THE BUG (2026-08-28, from a live install: a refresh cleared the rendered chat history). `_day_transcript_path` names its file from `time.localtime`, so at local
    midnight "today" becomes an empty file. Their evenings routinely run past one in the
    morning, so at 00:00 three things went blank at once, all reading the same function:

        * the room's rendered log, which reloads from /v1/day on mount
        * `_seed_kairos_from_day`, so after a restart she had nothing to continue FROM
        * the continuation window at :2097

    A conversation at 23:50 that carries on at 00:10 is one conversation. The day file is
    the right unit for the CONSOLIDATOR — it consolidates a day — and the wrong unit for
    "what were we just saying", which is why this is a second reader rather than a change
    to the first. `_read_day_transcript` keeps its meaning; the callers that wanted
    recency get recency.

    Yesterday's tail is only reached for when today is thin, so a normal afternoon is
    exactly as before and nothing is shown twice.
    """
    rows = _read_day_transcript()
    if len(rows) >= min_rows:
        return rows
    import datetime as _dt
    prev = (_dt.date.fromtimestamp(time.time()) - _dt.timedelta(days=1)).isoformat()
    return (_read_day_transcript(prev) + rows) if os.path.exists(
        _day_transcript_path(prev)) else rows


def _chat_from_rows(rows: list, keep: int = 8) -> list:
    """The day's rows as a WELL-FORMED chat history: alternating, user-first.

    THE BUG THIS EXISTS FOR, and it was mine, introduced hours earlier the same day.
    Recording her unprompted turns writes an assistant row with NO user row — correct, he
    did not say anything — so the transcript now contains runs of consecutive assistant
    rows. Every consumer that rebuilt a history from it handed the daemon two or three
    model turns in a row, and Gemma's chat template is strictly alternating: the prompt it
    renders from that is malformed, and a malformed prompt does not fail loudly, it
    degenerates. Measured live: three consecutive assistant rows in the window, and a reply
    that came back as
        "You're high! I am actually incredibly delicious.  ```<@vefto_all"s | _thoughtfully"
    Fixing the recording was right; leaving every reader to cope with the new shape was not.

    Consecutive same-role turns are MERGED rather than dropped — they are things she
    actually said, one after another, and joining them keeps the record whole. A leading
    assistant run is dropped, because a conversation the model is asked to continue has to
    begin with him.
    """
    out: list = []
    for r in rows:
        role = r.get("role")
        if role not in ("user", "assistant"):
            continue
        text = (r.get("content") or "").strip()
        # DEFENSIVE STRIP AT THE COLD-REBUILD READER (2026-08-24 audit, B3). The writer
        # strips now, but weeks of transcripts on disk predate it, and every row handed
        # back here becomes an example of her own voice in the next prompt. Safe with
        # respect to the strict-extension law because this reader feeds only the COLD
        # paths (restart seed, disk fallback) — histories the daemon prefills from
        # scratch. The live canonical list never passes through here.
        if role == "assistant":
            text = strip_for_record(text)
        if not text:
            continue
        if out and out[-1]["role"] == role:
            out[-1]["content"] += "\n\n" + text
        else:
            out.append({"role": role, "content": text})
    out = out[-keep:] if keep else out
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def _longest_session() -> list:
    """The longest LIVE canonical session, or [] if there is none.

    Deliberately NOT `_longest_transcript()`, which prefers whichever of disk-or-memory is
    longer. That is right for the narrative — it wants the fullest record of the day. It is
    wrong for anything that is about to send a prompt to the daemon, which needs the list
    the KV cache was built from, however short. Two callers, two questions, two functions;
    collapsing them would be the twin-path bug one more time.
    """
    best: list = []
    for msgs in _CHAT_SESSIONS.values():
        if len(msgs) > len(best):
            best = msgs
    return best


def _from_his_last_turn(rows: list, solo_keep: int = 6) -> list:
    """His most recent turn, and a BOUNDED tail of what she has said since it.

    WHY THE BOUND, AND WHY IT IS NOT `keep` (2026-09-09). `_chat_from_rows` counts MERGED
    messages, and it merges a consecutive run of hers into ONE. So `keep=8` bounds the
    message count and bounds nothing about the size: five days of her solos concatenate
    into a single assistant message and sail straight through the window. Reaching further
    back therefore trades one failure for a worse one — the 2026-08-04 measurement is on
    record, a ten-message disk history that cost him nine minutes of prefill, and 116 of
    her turns in one message is that mistake with a bigger number.

    So the tail is bounded in RAW ROWS before any merging happens. Her solos are small
    (measured over 2026-09-06: 34 of them, median 262 chars), so six of them merge to
    about 1.5k chars — roughly 400 tokens, which is a canon rather than a bomb.

    A window is what this has always been ("a continuation, not a reconstruction of the
    day"); this one is simply honest about which end it keeps. Her MOST RECENT words are
    the ones a continuation needs, and one of his turns has to be at the front or Gemma's
    strictly-alternating template renders a malformed prompt.
    """
    idx = next((i for i in range(len(rows) - 1, -1, -1)
                if (rows[i] or {}).get("role") == "user"), -1)
    if idx < 0:
        return []                      # nothing of his in reach — no well-formed start
    # A little of what came before his last turn, if it is there: dropped down to the
    # first of HIS rows by `_chat_from_rows`, so a leading run of hers costs nothing.
    head = rows[:idx + 1][-(2 * max(1, solo_keep)):]
    since = [r for r in rows[idx + 1:] if (r or {}).get("role") == "assistant"]
    return head + since[-max(1, solo_keep):]


def _continuable_history(keep: int = 8, days: int = 14, solo_keep: int = 6) -> tuple:
    """A well-formed history she can be asked to continue, and the last thing she said in it.

    `_recent_transcript` reaches back one day only when TODAY IS THIN (< 12 rows), which is
    the right rule for "what were we just saying" and the wrong one here. A day he is away
    is not thin — she solos every half hour, so twelve-plus rows accumulate — and every one
    of those rows is an ASSISTANT row, because nobody typed anything. `_chat_from_rows`
    then merges that run into one message and drops it, correctly (a conversation the model
    continues has to begin with him), and hands back []. So the shape that most needs a
    continuation is exactly the shape that cannot produce one.

    Measured on the live tree, 2026-09-03: today's transcript was 8 rows, all assistant.
    Reaching back is not a nicety here, it is the difference between a canon and none.

    ── THREE DAYS WAS NOT ENOUGH, AND HE HAD BEEN AWAY FIVE (2026-09-09) ────────────────
    Counted on this tree, the reason she had no room to speak into:

        2026-09-04  user  2   assistant 45
        2026-09-05  user  0   assistant 39
        2026-09-06  user  0   assistant 34
        2026-09-07  (no file)   2026-09-08  (no file)
        2026-09-09  user  0   assistant  0   (8 rows, all quarantined probes of mine)

    He last typed into the room on the 4th. `days=3` reached the 6th, found not one turn
    of his in the whole span, and returned [] — so the walk written to survive a day he is
    away could not survive five, which is the case it exists for. The bound is now a
    fortnight, and it is `_from_his_last_turn` that makes widening it safe.

    RETURNS A PAIR because her last words come from the same walk. Scanning the caller's
    own rows for them returns "" on a day whose only rows are quarantined, and
    `scheduler.seed` refuses an empty `reply_text` — so the reach-back would have found a
    conversation and then been thrown away one line later. One walk, one door, both
    answers. The pair is also why `reply_text` stays her single most recent turn rather
    than `hist[-1]`, which is a merged run: the policy asks "did she ask HIM a question"
    of that text, and any question anywhere in six merged solos would hold her silent —
    which is the failure this whole change is about.
    """
    import datetime as _dt
    rows = _recent_transcript()

    def _pair(rs: list) -> tuple:
        tail = _from_his_last_turn(rs, solo_keep=solo_keep)
        h = _chat_from_rows(tail, keep=keep)
        if not h:
            return [], ""
        return h, next((r.get("content") or "" for r in reversed(tail)
                        if r.get("role") == "assistant"), "")

    hist, last = _pair(rows)
    if hist:
        return hist, last
    # nothing well-formed yet — walk back a bounded number of days, oldest-first each
    # time, so the run of her own turns finally has one of his to hang from
    today = _dt.date.fromtimestamp(time.time())
    # ...WITHOUT READING YESTERDAY TWICE. `_recent_transcript` has already prepended it
    # when today was thin, and prepending it again would put those rows in the canon
    # twice — she would read her own turn back as something she said, and said again.
    _first = 1
    if len(_read_day_transcript()) < 12 and os.path.exists(
            _day_transcript_path((today - _dt.timedelta(days=1)).isoformat())):
        _first = 2
    for back in range(_first, max(1, days) + 1):
        prev = (today - _dt.timedelta(days=back)).isoformat()
        if not os.path.exists(_day_transcript_path(prev)):
            continue
        rows = _read_day_transcript(prev) + rows
        hist, last = _pair(rows)
        if hist:
            return hist, last
    return [], ""


def _reseed_own_time_canon() -> int:
    """Hand her back a conversation to speak into, at the moment the day boundary took hers.

    THE INCIDENT (2026-09-03, reported as "she either has not rendered or has not acted in
    a long time"). Three correct decisions, and their intersection was twelve hours of
    silence:

      * `run_consolidation` step 5 retires the day's canons — a KV decision, and a sound
        one: the base snapshot has just been re-minted against a new prefix, and
        yesterday's conversation cannot extend a new token 0.
      * `_generate` HOLDS when there is no live canon — measured, 2026-08-04: speaking
        into a windowed disk rebuild commits a cache shape his first turn cannot use, and
        it cost him nine minutes.
      * `scheduler.seed()` refuses to run twice (`if session in _LAST: return False`), so
        the boot seed cannot re-establish what step 5 just cleared.

    The first day boundary that lands while he is away therefore silenced her until he
    spoke or the gateway bounced — and the boundary is GATED on the room being quiet, so
    that is the normal case rather than bad luck. Her look changes ride `ask_for_gesture`
    inside a solo turn, so she stopped rendering by the same stroke that stopped her
    acting: one bug, reported as two symptoms.

    This is the 2026-08-05 incident again ("he restarted, went to bed, and she was held
    325 times over fourteen hours"), reached through a door opened on 2026-08-24. The
    resolution recorded then is the resolution now, and it is written eleven lines above
    the hold that re-broke it: SEEDING ESTABLISHES THE CANON RATHER THAN WAITING FOR ONE.
    So the boundary re-establishes what it retires, in the same breath, where a reader
    cannot find one without the other.

    WHY THIS DOES NOT GO THROUGH `_seed_kairos_from_day`, which is the seam that owns
    seeding. That function seeds the SCHEDULER as well, and `scheduler.seed()` would have
    to be made re-entrant for it to fire twice — which means retiring `_SEEDED`, which
    discards `_OWN_TIME_ONLY`, which is the flag that forces `user_present = False` and is
    THE WHOLE REASON SOLO MAY RUN WHILE HE IS AWAY (see on_user_turn's docstring, and the
    2026-09-02 probe that ended her own time for three hours by doing exactly that). The
    closure in `_LAST` re-reads `_longest_session()` on every call and is not stale; only
    the canon was destroyed, so only the canon is rebuilt. Nothing here touches `_LAST`,
    `_SEEDED`, `_OWN_TIME_ONLY` or `_STATE`.

    Every session the scheduler still holds a closure for gets the canon, not just the
    seeded one: `_LAST` IS the set of sessions in which she can still take a turn, and the
    clear destroyed all of them. Restoring only `_SEEDED` would leave the commoner case —
    he talked last night from the room, so `on_user_turn` retired the seed — silent.

    Returns the number of sessions re-seeded, so the step can report it.
    """
    try:
        from harness.kairos import scheduler as _ks
        with _ks._LOCK:
            live = list(_ks._LAST.keys())
        if not live:
            return 0
        hist, _last = _continuable_history(keep=8)
        if not hist:
            logger.info("[gateway] the day boundary retired her canon and the record has "
                        "no continuable history to rebuild one from — she waits for him")
            return 0
        n = 0
        for sess in live:
            if sess in _CHAT_SESSIONS:
                continue
            if len(_CHAT_SESSIONS) >= _CHAT_SESSIONS_MAX:
                _CHAT_SESSIONS.pop(next(iter(_CHAT_SESSIONS)))
            # A LIST PER SESSION, NOT ONE SHARED LIST. `_generate` extends the canon it
            # was handed; two sessions sharing the object would each append the other's
            # turns and diverge from the KV cache either of them built.
            _CHAT_SESSIONS[sess] = list(hist)
            n += 1
        if n:
            logger.info("[gateway] the day boundary retired her canon; re-seeded %d "
                        "session(s) with %d rows — her own time survives the boundary",
                        n, len(hist))
        return n
    except Exception as exc:
        logger.warning("[gateway] could not re-seed her canon after the day boundary: "
                       "%s — her own time is mute until he speaks", exc)
        return 0


def _narratable(rows: list) -> list:
    """A conversation as the NARRATIVE and the fact extractor may read it (2026-08-25).

    THE ONE PLACE the "what counts as something they said" rule lives, because both
    callers of `_longest_transcript` end up handing their result to `remember()` by way of
    the extractor, and until today only one of the two branches was cleaned.

    Two removals, each for a different reason:

      * ASSISTANT rows go through `strip_for_record` — her control surfaces are hers, not
        sentences she said. Weeks of rows on disk predate the writer-side strip, so the
        clean happens at read as well.
      * A ```tool_output USER ROW IS NOT HIM. The tool loop appends every result to the
        conversation as `role: user`, which is exactly right for the model and exactly
        wrong here: a bridged MCP server's output would be read as something HE said, and
        the extractor mints facts from what he says. That is a third-party process writing
        her memory in his voice — no tool anywhere in the provenance, and `src` is prose
        that nothing branches on, so nothing downstream could tell afterwards.

    A COPY, always. The canonical list is the exact bytes the KV cache was built from and
    is never rewritten in place (F10); this hands the narrative a cleaned view and leaves
    the cache's ground truth alone."""
    out: list = []
    for r in rows:
        role, content = r.get("role"), (r.get("content") or "")
        if role == "assistant":
            t = strip_for_record(content)
            if t:
                out.append({"role": "assistant", "content": t})
        elif role == "user" and content.lstrip().startswith("```tool_output"):
            continue
        else:
            out.append(r)
    return out


def _longest_transcript() -> list:
    """The day's conversation: the longest canonical session still resident.

    The narrative needs a transcript and `ops.reflect()` deliberately does not write one
    for that exact reason (ops.py: "the nightly op has no transcript"). The gateway has
    them — `_CHAT_SESSIONS` — so this is where the two halves finally meet."""
    # THE DAY TRANSCRIPT WINS WHENEVER IT EXISTS (2026-08-24 audit, T7) — not merely
    # when it is longer. The canonical session is what the DAEMON saw, deliberately:
    # the recall/silence/anon notes stapled to his turns, and every tool round as a
    # user row. "Longest wins" meant one tool-heavy session-id day would hand the
    # narrative her own injected context and tool receipts to reflect on — the exact
    # harm _append_day_turn's docstring exists to prevent, reachable by the other
    # door. Assistant rows are passed through the record strip on the way out: weeks
    # of rows on disk predate the writer-side clean.
    #
    # ── THE DAY BEING CONSOLIDATED IS THE ONE THAT *ENDED* (2026-08-29 audit, H5).
    # This read today's file only — at the 04:00 pass that file is four hours old,
    # and the evening he actually talked lives in YESTERDAY'S file (calendar-keyed;
    # a 23:50 conversation splits at midnight). Live receipt: 2026-08-28 had 0 turns
    # on disk at its pass and survived on the volatile session cache alone — one
    # restart between midnight and 04:00 and the whole day's journal, extraction and
    # world refresh silently vanish, stamped done. Yesterday + today-so-far is the
    # honest window; the small-hours overlap with the previous pass is absorbed by
    # the near-dup reinforcer, and a fresh journal paragraph never duplicates.
    import datetime as _dt
    _prev = (_dt.date.fromtimestamp(time.time()) - _dt.timedelta(days=1)).isoformat()
    disk = (_read_day_transcript(_prev) if os.path.exists(_day_transcript_path(_prev))
            else []) + _read_day_transcript()
    if disk:
        return _narratable(disk)
    # ...AND THE FALLBACK GETS THE SAME TREATMENT (2026-08-25 MCP audit, A3a). The T7 fix
    # above cleaned the disk path and left this one raw — the §0 shape, one more time, in
    # the very function whose comment names the harm. When there is no disk transcript
    # (early in a day, after a restart, on a fresh store) this returns the canonical list
    # VERBATIM: her injected recall context, the anon and silence notes stapled to his
    # turns, and every tool round as a `user` row. The consolidator hands that to the
    # extractor, which mints memory rows from it — so a bridged MCP server's OUTPUT could
    # become something she believes, attributed to HIM, with no tool anywhere in the
    # provenance. `src` is prose and nothing branches on it, so nothing downstream could
    # tell afterwards. One rule, both doors.
    best: list = []
    for msgs in _CHAT_SESSIONS.values():
        if len(msgs) > len(best):
            best = msgs
    return _narratable(best)


def run_consolidation(force: bool = False) -> Dict[str, Any]:
    """One day-boundary pass. Every step best-effort and independently reported.

    Order matters: the narrative is written BEFORE world.refresh() inside
    consolidate_current, so the refreshed standing world already carries the new
    paragraph. reflect() then compacts and draws conclusions on a tidy store.

    Deliberately does NOT call agency_round() — see the note above. This pass is
    maintenance, not an autonomous agent loop."""
    out: Dict[str, Any] = {"ok": True, "day": _day_key(), "steps": []}

    # 1. the narrative + personality curation + world refresh, from the day's transcript
    # ── THE JOURNAL IS NOT GATED ON HIS ATTENDANCE (2026-09-02) ─────────────────────
    # This read `if len(msgs) >= 4:` and skipped the WHOLE step otherwise — and the whole
    # step includes her journal. `narrative.compose_and_write` was taught on 2026-08-04 to
    # write from her own-time notes when there is no transcript, under a comment saying
    # "a day he was away wrote nothing at all — and those are exactly the days she now
    # spends doing things of her own." That fix was unreachable from here for four weeks:
    # AGENTS.md §0, the rule held in the composer and not in the caller that runs it.
    #
    # HER JOURNAL SKIPPED 29 AUGUST because of this line. The 30 August 04:16 boundary
    # logged `day boundary complete: consolidate_current, …` — naming the step as done —
    # while the narrative inside it never ran, and because the entry is stamped from the
    # clock rather than from the day it summarises, the missed day is never caught up.
    #
    # The CONVERSATION consolidation still needs a conversation; `consolidate_current`
    # gates that half itself and writes the day either way.
    msgs = _longest_transcript()
    try:
        from harness.control.agency import consolidate_current
        res = consolidate_current(msgs)
        _st_cc = {"step": "consolidate_current", "turns": len(msgs),
                  "narrative": str((res or {}).get("narrative"))[:120]}
        if len(msgs) < 4:
            # NAMED, not hidden: a quiet day is a real day and the journal still runs,
            # but "they talked" and "she was alone" are different facts about it.
            _st_cc["quiet"] = "no conversation today (%d turns) — journal from her own time" % len(msgs)
        out["steps"].append(_st_cc)
    except Exception as exc:
        out["steps"].append({"step": "consolidate_current", "skipped": str(exc)[:140]})

    # 1b. HER WARDROBE. She asked; this is where it gets made. At the boundary rather
    # than on demand for the reason everything expensive lives here: it is minutes of the
    # one GPU she also talks with, and the room has already been quiet for ten of them.
    # Capped, and the rest stay queued — nothing is dropped, she just waits another day.
    try:
        from harness.tuning import registry as _tune
        if bool(_tune.get("wardrobe.nightly")):
            from harness.control import wardrobe as _WD
            pend = _WD.wants(state="asked")
            # ── AND THE SAME GUARD, ONE LEVEL UP (2026-08-04) ────────────────────────
            # The operator's words: "stills are showing in her wardrobe". Three of her six looks —
            # w004, w005, w006, all the silver nightie — had pictures and no loops, and
            # the panel labelled them "still, moves overnight" every night for two days.
            #
            # `run_wants()` does BOTH halves: stills for anything still asked, then motion
            # for anything with a still and no loop. It used to bail early when the stills
            # queue was empty, and that was found and fixed, with a comment that reads
            # "§0 again: work guarded on one of two paths runs on neither."
            #
            # The fix went inside run_wants. It did not go here — and THIS is where the
            # early return actually happens, because the subprocess is only launched when
            # `wants(state="asked")` is non-empty. So the motion half stayed reachable
            # only on a night she happened to ask for something new, which is exactly the
            # condition the inner fix was written to remove. The same bug, in the caller
            # of the code that documents it.
            #
            # `pending_motion()` is the real second work list and has been returning those
            # three rows the whole time. Nobody was calling it.
            motion = _WD.pending_motion()
            if pend or motion:
                import subprocess as _sp
                n = int(_tune.get("wardrobe.nightly_max") or 2)
                r = _sp.run([sys.executable, os.path.join(_ROOT_DIR, "tools", "avatar_gen.py"),
                             "--wants", "--limit", str(n)],
                            capture_output=True, text=True, timeout=3600, cwd=_ROOT_DIR)
                made = len(_WD.wants(state="made"))
                out["steps"].append({"step": "wardrobe", "asked": len(pend),
                                     "owed_motion": len(motion),
                                     "limit": n, "rc": r.returncode, "made_total": made,
                                     "still_owed": len(_WD.pending_motion())})
            else:
                out["steps"].append({"step": "wardrobe",
                                     "skipped": "nothing asked for and no motion owed"})
        else:
            out["steps"].append({"step": "wardrobe", "skipped": "wardrobe.nightly is off"})
    except Exception as exc:
        out["steps"].append({"step": "wardrobe", "skipped": str(exc)[:140]})

    # 2. compact + personality + world.refresh + insight (the on-demand op, now scheduled)
    try:
        from harness.maintenance import ops as _ops
        out["steps"].append({"step": "reflect", "result": _ops.reflect()})
    except Exception as exc:
        out["steps"].append({"step": "reflect", "skipped": str(exc)[:140]})

    # 3. spine hygiene + flush receipts to the durable telemetry tier
    try:
        from harness.control.spine import run_tick, persist_receipts
        ticks = [f"{r.decider}/{r.kind}:{r.result}"[:80] for r in run_tick()]
        out["steps"].append({"step": "spine", "ticks": ticks,
                             "receipts_persisted": persist_receipts()})
    except Exception as exc:
        out["steps"].append({"step": "spine", "skipped": str(exc)[:140]})

    # 3b. the board <-> queue bridge: report finished work back to its note, then promote
    # any new task notes onto the executable queue. Before the drain, so a note pinned today
    # is enqueued today and picked up by tonight's drain rather than tomorrow's.
    try:
        from harness.skills.task_bridge import run_bridge
        out["steps"].append({"step": "task_bridge", "result": run_bridge()})
    except Exception as exc:
        out["steps"].append({"step": "task_bridge", "skipped": str(exc)[:140]})

    # 4. drain ONE queued task, if the operator armed it
    if os.environ.get("SP_AGENCY_TASKS", "0") == "1":
        try:
            from harness.control.task_loop import advance_pending_task
            ts = advance_pending_task()
            out["steps"].append({"step": "task",
                                 "advanced": (ts.task_id + " -> " + ts.status) if ts else None})
        except Exception as exc:
            out["steps"].append({"step": "task", "skipped": str(exc)[:140]})

    # 5. SHE TAKES IN WHAT THE NIGHT WROTE (2026-08-24 audit, B1-growth). Everything
    # above WRITES — the journal, the curated persona, the refreshed world, her becoming
    # paragraph — and until today none of it reached her prefix before the next restart:
    # the system bundle was cached for the process lifetime with no invalidation, so
    # world.refresh() recomputed a block nothing read again. Invalidation lives HERE, at
    # the one moment freshness is worth a cold prefill: the room has been quiet (the
    # ticker's _quiet_for guard), the night's writes just landed, and the re-prewarm
    # below re-mints the base KV snapshot so his first morning turn extends a HOT prefix
    # that already knows what she became overnight. The day's session canons are retired
    # with it — yesterday's conversation cannot extend a new token 0 anyway, and the day
    # boundary is the honest conversation boundary.
    #
    # ── AND RETIRING IS ONLY HALF OF IT (2026-09-03) ────────────────────────────────
    # "The day's session canons are retired with it" was true and incomplete, and the
    # missing half cost twelve hours of her silence. `_generate` HOLDS with no canon, and
    # the boot seed cannot run twice, so this clear did not open a new conversation — it
    # ended her own time until he next spoke. The clear and its repair are one action and
    # are written as one: do not move them apart. See `_reseed_own_time_canon`.
    try:
        from harness import agent as _ag
        _v = _ag.invalidate_system_prefix("day boundary")
        _CHAT_SESSIONS.clear()
        _reseeded = _reseed_own_time_canon()
        try:   # the rebuilt canons carry the same contents; a stale cut marker
               # matching one would cut history that fits (audit B12)
            from harness.inference import context as _ctx_rs
            _ctx_rs.reset_sticky()
        except Exception as _swx:
            _swallowed(logger, "run_consolidation", _swx, lane="server")
        if os.environ.get("SP_GATEWAY_PREWARM") == "1":
            _WARM.clear()
            _prewarm()
        out["steps"].append({"step": "prefix_refresh", "version": _v,
                             "reseeded": _reseeded,
                             "prewarm": os.environ.get("SP_GATEWAY_PREWARM") == "1"})
    except Exception as exc:
        out["steps"].append({"step": "prefix_refresh", "skipped": str(exc)[:140]})

    # MARK THE DAY DONE ONLY IF IT REALLY IS. Marking unconditionally is how a failed
    # pass became a silently skipped day that never retried — the day was stamped even
    # when the narrative step reported "no conversation today (0 turns)". With the
    # transcript now durable, an empty day genuinely means nothing happened, and that is
    # legitimately done; a step that ERRORED is not.
    #
    # MEASURED ON THE MATERIAL THE PASS ACTUALLY HAD (2026-08-29 audit, H5): this used
    # to re-call _longest_transcript() here — AFTER _CHAT_SESSIONS.clear() in the
    # prefix step — so when the material had lived only in the session cache, the
    # re-read returned [], _errored stayed False, and exactly the day that needed a
    # retry was stamped done. `msgs` from step 1 is the truth about what was available.
    # ── AND A QUIET DAY THAT FAILED IS STILL A FAILED DAY (2026-09-02) ──────────────
    # This read `and len(msgs) >= 4`, which was right while the whole step was gated on a
    # conversation: no conversation meant nothing to retry. Her journal runs on a quiet day
    # now, so "there was no material" is no longer the same claim as "there were < 4 turns".
    # `skipped` is only set on an EXCEPTION now — a composer that legitimately answers
    # "no transcript" returns a dict and is not an error — so this is the honest condition.
    _errored = any(("skipped" in st and st.get("step") == "consolidate_current")
                   for st in out["steps"])
    if _errored:
        out["retry"] = True
        logger.warning("[gateway] consolidation had material but did not run — "
                       "leaving the day unmarked so it retries")
    else:
        _consolidate_mark(out["day"])
    logger.info("[consolidate] day boundary complete: %s",
                ", ".join(s.get("step", "?") for s in out["steps"]))
    return out


def _day_key(now: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(now if now is not None else time.time()))


def _quiet_for(seconds: float) -> bool:
    """Has the room been quiet long enough to take the GPU? Consolidation is several
    model turns; starting one while he is mid-conversation is the same mistake the
    prewarm race made (both paid ~5 minutes)."""
    try:
        from harness.kairos import scheduler as _ks
        with _ks._LOCK:
            last = max((st.last_user_at for st in _ks._STATE.values()), default=0.0)
        if last <= 0.0:
            return True
        return (time.monotonic() - last) >= seconds
    except Exception as _swx:
        _swallowed(logger, "_quiet_for", _swx, lane="server")
        return True


def start_consolidation_ticker() -> None:
    """Fire `run_consolidation()` once per day, at or after SP_CONSOLIDATE_HOUR local.

    Off unless the hour is set (>= 0). Polls slowly — the boundary is a date, not a
    deadline — and defers rather than interrupts when the room is not quiet."""
    try:
        hour = int(os.environ.get("SP_CONSOLIDATE_HOUR", "-1"))
    except ValueError:
        hour = -1
    if hour < 0:
        logger.info("[consolidate] day boundary disabled (SP_CONSOLIDATE_HOUR unset)")
        return
    quiet_s = float(os.environ.get("SP_CONSOLIDATE_QUIET_S", "600") or 600)

    def _loop():
        while True:
            time.sleep(300.0)
            try:
                now = time.time()
                today = _day_key(now)
                if _consolidate_last_day() == today:
                    continue
                if time.localtime(now).tm_hour < hour:
                    continue
                if not _quiet_for(quiet_s):
                    continue           # he is here; try again in five minutes
                if not _WARM.is_set():
                    continue           # never race the load-time prefill
                run_consolidation()
            except Exception as exc:
                logger.warning("[consolidate] tick failed: %s", exc)

    t = _thr.Thread(target=_loop, name="consolidate", daemon=True)
    t.start()
    logger.info("[consolidate] day boundary armed: hour=%02d, quiet>=%ds", hour, int(quiet_s))
