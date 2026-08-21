"""
SSE Gateway
==========

The harness's server side: an OpenAI-compatible HTTP gateway that wraps the
Kairos native daemon. External callers get the familiar
``POST /v1/chat/completions`` (streaming SSE or blocking); internally each
request is governed by the interceptor pipeline and forwarded to ``sp-daemon``.

This is the "custom server" half of replacing LMStudio: the daemon speaks
Kairos native ``/v1/chat``; this gateway speaks OpenAI so existing tools
(and the harness CLI) can talk to it unchanged.

Uses Flask if installed; otherwise a stdlib ``http.server`` fallback so the
gateway runs with zero third-party deps.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import logging
import os
import os as _o_sys
import sys

# The repo root, resolved from THIS file rather than from cwd. The first cut left it
# undefined; _system_profile() raised NameError and a bare `except Exception: pass`
# swallowed it, so the restart route reported 'restartable: false' with no reason
# anywhere. A relative glob had also been silently working only because the gateway
# happens to be launched from the repo root.
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import re
import threading
import time

from typing import Any, Dict, Iterator, Optional

# ── WHAT IS NEVER SPEECH ────────────────────────────────────────────────────────────
# The vocabulary and the discriminator now live at ONE place — stream_processor — and are
# applied inside the client, where daemon text enters the harness. See the long comment
# at `SPDaemonClient.chat_stream`: a private regex HERE was how the night narrative got
# "<channel|>" written into her permanent journal, because that lane never came through
# this file at all.
#
# The calls that remain below are not redundant copies of the rule; they are the lanes the
# client seam cannot reach, because those lanes consume RAW STREAM DELTAS (`chat_stream`
# yields each token unstripped and only strips the aggregate it returns). `_say` and the
# kairos continuation join deltas themselves, so they must strip themselves. The two
# blocking lanes strip idempotently over the client's own pass — cheap, and belt-and-braces
# on the thing that has now escaped five times.
from harness.inference.stream_processor import (hold_partial_marker,
                                                strip_control_surfaces, strip_tags)

from harness.inference import InferenceConfig, get_client
from harness.observability import get_logger

logger = get_logger(__name__)


# ──── THE SAMPLER-DEFAULT SEAM (ADR-013) ─────────────────────────────────
# byteexact and eot_bias were each resolved in ONE of FOUR InferenceConfig
# builders here. /v1/chat honoured SP_GATEWAY_BYTEEXACT; _to_config and the
# OpenAI-compat agent path did not, so they left byteexact=None and the DAEMON's
# own default (ON, "exact for gates") won.
#
# On gemma4-MoE that is fatal and silent: the MoE FFN seam REFUSES byteexact (the
# integer islands cover the DENSE FFN only), so the daemon returned 200 with an
# empty stream in SIX MILLISECONDS and the console showed a blank reply. The model
# was fine — the same prompt sent daemon-direct with byteexact:false answers
# normally. Same shape for eot_bias: two builders defaulted it to 4.0, which on
# this model makes the FIRST sampled token a stop.
#
# One resolver, used by every builder. Explicit client value always wins.
def _bx_default(explicit):
    """byteexact: explicit > SP_GATEWAY_BYTEEXACT > daemon default (None)."""
    if explicit is not None:
        return explicit
    import os as _o
    v = _o.environ.get("SP_GATEWAY_BYTEEXACT")
    if v == "0":
        return False
    if v == "1":
        return True
    return None


def _knob_set(name: str):
    """The operator's OVERRIDE for a knob, or None if he has never touched it.

    Distinct from `_knob` on purpose. `_knob` answers "what is this dial reading",
    which includes the declared default; this answers "did he actually set it", and
    only that may be pushed onto a decode path that has been running on the daemon's
    own values. A declared default is a suggestion in a registry, not a measurement on
    this model."""
    try:
        from harness.tuning import registry as _tune
        return _tune._load().get(name)
    except Exception:
        return None


def _knob(name: str, fallback):
    """A tuning value, or the fallback if the registry cannot answer.

    Never raises and never blocks a turn: a knob that fails to resolve must cost her the
    setting, not the reply. Read per-turn on purpose — the whole point of the registry is
    that the next turn obeys a change with no restart.
    """
    try:
        from harness.tuning import registry as _tune
        v = _tune.get(name)
        return fallback if v is None else v
    except Exception:
        return fallback


def _eot_default(explicit):
    """eot_bias: explicit > SP_EOT_BIAS (the profile, via serve.py) > 0.0.

    THE FALLBACK WAS 4.0, WHICH IS THE 12B's (2026-08-04). serve.py always exports
    SP_EOT_BIAS from the profile, so the served path was never wrong — but anything that
    reaches this module WITHOUT that env (a gate hitting the gateway directly, the CLI, a
    bare import) got the retired model's bias on the MoE, where 4.0 makes the first
    sampled token a stop and the turn comes back EMPTY. The registry moved its declared
    default to 0.0 for exactly this reason and this resolver did not follow.
    """
    if explicit is not None:
        return explicit
    import os as _o
    raw = _o.environ.get("SP_EOT_BIAS")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return 0.0


# ──── Request handling (framework-agnostic core) ─────────────────────────
def _to_config(body: Dict[str, Any]) -> InferenceConfig:
    return InferenceConfig(
        temperature=body.get("temperature"),
        top_p=body.get("top_p"),
        max_tokens=body.get("max_tokens", 512),
        stop=body.get("stop"),
        seed=body.get("seed"),
        model=body.get("model"),
        # Kairos extensions, passed through if present
        byteexact=_bx_default(body.get("byteexact")),
        auto_recall=body.get("auto_recall"),
    )


def _chunk(delta: str, model: str, finish: str | None = None) -> str:
    obj = {
        "id": f"chatcmpl-{int(time.time()*1000)}",
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {"content": delta} if delta else {},
            "finish_reason": finish,
        }],
    }
    return f"data: {json.dumps(obj)}\n\n"


def _session_of(body: Dict[str, Any]) -> str:
    """THE session key. One function, because there were four sites and two rules:

        _agent_text / _kairos_after_turn :  session | session_id | default
        _native_chat_sse                 :  session | chat_id    | default

    ...and console.html sends `session_id`. So on the console path — the one a human
    actually uses — kairos filed her unprompted message under "default" while the console
    would have polled the outbox for its own uuid. She would have spoken, correctly, into a
    session nobody was listening to, and every symptom would have said "she never spoke".

    A key derived in more than one place is a key that disagrees with itself."""
    for k in ("session", "session_id", "chat_id"):
        v = body.get(k)
        if v:
            # The panels' idea of "the" session follows the conversation that is
            # actually happening — see _room_session().
            _LAST_SESSION["id"] = str(v)
            return str(v)
    return "default"


# The most recent REAL session a chat body named. "default" only until the first turn.
_LAST_SESSION: Dict[str, str] = {"id": "default"}


def _agent_text(body: Dict[str, Any]) -> str:
    """Run the request through the AGENT loop (Gemma tool calling) unless tools are disabled.
    This is the unification: the model CALLS its tools (memory/system/web) in the chat, instead
    of a passthrough with no tool calling. Set body['tools']=false (or 'use_tools':false) to skip."""
    msgs = body.get("messages", [])
    # THE WARM GATE, ON THIS PATH TOO (2026-08-19). _await_warm was written for exactly
    # this ("chat turns call this BEFORE touching the daemon") and had ZERO callers —
    # the SSE path inlined its own copy and this one raced the load-time prefill, the
    # both-pay-a-5-minute-cold-prefill incident the warm gate exists for. Here, at the
    # point both OpenAI endpoints converge, same as every other per-turn hook.
    _await_warm()
    # ROLEPLAY: may inject the scene's system prompt + this turn's director note, or return
    # the scenario OFFER outright. Wired at BOTH entry points (here and _native_chat_sse) —
    # a hook wired into one of two paths has been the single most reliable bug in this
    # system, four times over in one day.
    _human = _arm_turn(msgs)     # what he TYPED — taken before the tool loop touches msgs
    # HE SPOKE. TELL THE SCHEDULER — on THIS path too.
    # on_user_turn() was called only in _native_chat_sse, so on the OpenAI path the
    # scheduler never learned that a human had said anything. Two consequences, both silent:
    # her CHAIN never reset (so after one unprompted message she was muted for good), and
    # last_user_at stayed 0, so the room NEVER counted as quiet and reflect_tick could not
    # fire at all. It is the same bug as kairos, the repeat-guard, roleplay, capture and the
    # console fork: an event wired into one of two entry points is wired into neither.
    try:
        from harness.kairos import scheduler as _ks_u
        _ks_u.on_user_turn(_session_of(body))
    except Exception:
        pass
    _offer = _roleplay_pre_turn(body, msgs)
    if _offer:
        return _offer
    # READ THE FLAG AFTER THE ROLEPLAY HOOK. _roleplay_pre_turn sets body["tools"]=False
    # inside a scene ("a character does not call web_search mid-kiss", and the first
    # scene turn HUNG on empty tool rounds) — but this flag used to be read at the top
    # of the function, so the branch below always saw the stale pre-scene value and the
    # scene ran with tools anyway. Enforced in neither path, the fourth time for this
    # exact hook (see the comment at the top of this function).
    use_tools = body.get("tools", body.get("use_tools", True)) is not False
    if not use_tools:
        # ARM THE SELF-REPEAT BAN HERE TOO. It was armed only inside agent_chat_stream —
        # so this tools=False branch (which goes straight to the client) had no guard, and
        # the very gate written to prove the fix ran down the unguarded path and "passed"
        # on temperature luck. Same hole, third variant, one day. Arm it at EVERY path that
        # reaches the model, not at the one you happened to be looking at.
        from harness.agent import _arm_self_repeat_ban
        _cfg = _to_config(body)
        _arm_self_repeat_ban(_cfg, msgs)
        text = strip_control_surfaces(get_client().chat(messages=msgs, config=_cfg).text)
        text = _repeat_guard(body, msgs, text, _cfg)
        _finish_openai_turn(body, _human, text)
        return text
    from harness.agent import agent_chat
    from harness.inference import InferenceConfig
    cfg = InferenceConfig(
        temperature=body.get("temperature", 0.0),
        max_tokens=body.get("max_tokens", 256),
        eot_bias=_eot_default(body.get("eot_bias")),
        byteexact=_bx_default(body.get("byteexact")),
        auto_recall=False,  # the model uses tools, not the daemon's heuristic recall
    )
    # STRIP AT GENERATION, NOT AT THE EXIT. The OpenAI path never had this at all — it
    # returned "<channel|><channel|> I can do that…" verbatim (measured 2026-07-30), while
    # the native SSE path was clean. Doing it here rather than at `return` means the repeat
    # guard, capture and kairos all judge the words she actually said, instead of judging
    # control markup that happens to lead them.
    text = strip_control_surfaces(agent_chat(msgs, config=cfg))
    text = _repeat_guard(body, msgs, text, cfg)
    _finish_openai_turn(body, _human, text)
    return text


def _finish_openai_turn(body: Dict[str, Any], human_text: str, text: str) -> None:
    """Everything a completed turn owes the rest of the system — ONE list, because the
    OpenAI path had been quietly owing two of them since the day it was written
    (2026-08-19 audit): _append_day_turn never ran here, so an OpenAI-path turn never
    entered the day transcript — invisible to consolidation, to her journal, and to
    _seed_kairos_from_day; and run_post_turn never ran, so a [MOOD:]/[TRAIT:]/[WEAR:]
    mark she emitted on this path moved NOTHING — her clothes and mood only changed on
    /v1/chat. Same story as on_user_turn and the repeat-guard before it: an event wired
    into one of two entry points is wired into neither."""
    _capture_after_turn(human_text)
    if (text or "").strip():
        _append_day_turn(human_text, text)
        try:
            from harness.control.spine import run_post_turn
            run_post_turn(human_text, text)
        except Exception as exc:
            logger.warning("[gateway] post-turn spine skipped: %s", exc)
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
    except Exception:
        pass

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
    except Exception:
        pass                                  # a missing receipt must never cost him his turn

    return human


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
                except Exception:
                    pass
        finally:
            M.reset_author(tok)
    except Exception:
        pass


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


def _system_profile() -> str:
    """Which profile this stack was launched with.

    SP_PROFILE is stamped by serve.py's build_env and is the authority. The fallback
    derives it by matching the running daemon's model against the profiles — which works
    only while no two profiles share a model, so it is a fallback and not the rule. It
    exists because a stack started before the stamp landed still needs to be restartable.
    """
    p = (_o_sys.environ.get("SP_PROFILE") or "").strip()
    if p:
        return p
    try:
        if _ROOT_DIR not in sys.path:
            sys.path.insert(0, _ROOT_DIR)
        import serve as _serve
        running = _serve._running_daemon_model()
        if running:
            import glob
            for f in sorted(glob.glob(os.path.join(_ROOT_DIR, "profiles", "*.toml"))):
                name = os.path.basename(f)[:-5]
                try:
                    c = _serve.load_profile(name)
                except Exception:
                    continue
                if os.path.normcase(c["paths"]["model"]) == os.path.normcase(running):
                    return name
    except Exception as exc:
        # SAY WHY. This swallowed a NameError for its whole first life and the only
        # symptom was a restart button that quietly refused to exist.
        logger.warning("[system] could not derive the profile: %s: %s",
                       type(exc).__name__, exc)
    return ""


def _engine_info() -> Dict[str, Any]:
    """Which backend this gateway talks to, and what it can do — for the room's chips
    and the restart controls (2026-08-21, the engine-agnostic seam)."""
    try:
        from harness.inference.client import get_client
        c = get_client()
        return {"kind": getattr(c, "kind", "sp"), "base_url": getattr(c, "base_url", ""),
                "supports": sorted(getattr(c, "supports", ())),
                "model": getattr(c, "default_model", "") or os.environ.get("SP_ENGINE_MODEL", "")}
    except Exception as exc:
        return {"kind": "?", "error": str(exc)[:120]}


def _system_json() -> Dict[str, Any]:
    prof = _system_profile()
    eng = _engine_info()
    # AN EXTERNAL ENGINE IS NOT THE HARNESS'S TO RESTART (2026-08-21): under the openai
    # backend the model lives in LM Studio / llama-server / a cloud; the room may only
    # bounce the GATEWAY. `restartable` says so rather than offering a button that lies.
    ext = "restart" not in (eng.get("supports") or [])
    return {"ok": True, "profile": prof or None, "engine": eng,
            "restartable": bool(prof) and not ext,
            "gateway_bounce": bool(prof),
            "note": ("this engine is external (%s) — start and stop it yourself; the "
                     "gateway can still be bounced" % eng.get("base_url", "")) if ext else
                    ("a full restart reloads the model and takes a couple of minutes; "
                     "the gateway bounce is seconds and leaves the daemon alone")}


def _spawn_restart(full: bool) -> Dict[str, Any]:
    """Relaunch through serve.py — the one door — and DETACHED.

    Detached matters more than it looks: a full restart STOPS THE GATEWAY THAT IS SERVING
    THIS REQUEST. A child inheriting this process's handles dies with it, so the restart
    would kill the gateway and then die before starting the replacement, leaving the
    stack down and the room with nothing to poll. The caller therefore gets its answer
    BEFORE anything is stopped, and the relaunch outlives its parent.

    It goes through serve.py rather than killing and respawning by hand because serve.py
    owns the env, the schema check and the profile/daemon agreement guard. A hand-rolled
    restart is how the wrong-profile outage happened in the first place.
    """
    prof = _system_profile()
    if not prof:
        return {"ok": False, "error": "cannot tell which profile this stack uses; "
                                      "restart it from a terminal"}
    if full and "restart" not in (_engine_info().get("supports") or []):
        return {"ok": False, "error": "the engine is external — the harness does not "
                                      "start or stop it; bounce the gateway instead"}
    return {"ok": True, "profile": prof, "full": full, "eta_s": 180 if full else 20}


def _do_restart(full: bool) -> None:
    """Actually relaunch. Called AFTER the response has been written and flushed, because
    a full restart stops this very process and a reply from a dead socket is no reply.

    The first cut called this before responding and the comment above it claimed
    otherwise — the code and the sentence disagreed, and the sentence was the wrong one.
    Measured: `curl` got an empty body every time, because serve.py had already killed
    the gateway mid-write. The UI tolerated it by catching the failure, which is exactly
    how a lie like that survives.
    """
    # EVERY DAEMON-SPAWN DOOR GETS THE GUARD, not just /v1/start (the class, not the
    # instance): a restart spawned mid-teardown is the watchdog bug by another door —
    # the ladder kills what this just launched, or worse, this un-shuts a deliberate
    # stop.
    try:
        from harness.control import shutdown as _sd
        if _sd.is_shutting_down() or _sd.ladder_running():
            logger.warning("[system] restart refused — a shutdown is in force")
            return
    except Exception:
        pass
    prof = _system_profile()
    if not prof:
        return
    argv = [sys.executable, os.path.join(_ROOT_DIR, "serve.py"), prof]
    if not full:
        argv.append("--gateway-only")
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) |                 getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        subprocess.Popen(argv, cwd=_ROOT_DIR, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                         creationflags=flags, close_fds=True,
                         start_new_session=(os.name != "nt"))
    except Exception as exc:
        logger.warning("[system] restart spawn failed: %s", exc)


def _avatar_rung_and_ceiling():
    """The live heat rung and the operator's ceiling, both from the systems that already
    own them — the roleplay scene if one is running, and the tuning registry. The avatar
    does not get its own idea of either."""
    rung, ceiling = 0, 7
    try:
        from harness.tuning import registry as tune
        ceiling = int(tune.get("roleplay.max_heat"))
    except Exception:
        pass
    try:
        from harness.roleplay import engine as rp
        # OFF MEANS OFF DOWNSTREAM TOO (2026-08-03). `roleplay.enabled` gated the
        # PRE-TURN — the place a scene is entered and its prompt injected — and nothing
        # else. A scene that was already running kept driving her AVATAR RUNG after the
        # feature was switched off, because this reader asked the engine "is a scene
        # active" without ever asking "is the feature on". Half a switch is not a switch.
        if _roleplay_on():
            sc = rp.active(_room_session())
            if sc is not None:
                rung = int(sc.heat.level)
    except Exception:
        pass
    return rung, ceiling


# ── GENERATE-NOW (2026-08-21): one background job at a time, status readable ────────
_GEN_JOB: Dict[str, Any] = {"running": False, "what": "", "started": 0.0,
                            "done": 0, "last": ""}


def _gen_now_start(body: Dict[str, Any]) -> Dict[str, Any]:
    if _GEN_JOB["running"]:
        return {"ok": False, "error": "a generation is already running",
                "job": dict(_GEN_JOB)}
    want_id = (body.get("id") or "").strip()
    _GEN_JOB.update(running=True, what=(want_id or "all"), started=time.time(),
                    done=0, last="starting")
    # THE FLAG FOLLOWS THE THREAD, not the intention (2026-08-21 01:13): the first
    # live click set running=True and then Thread() raised (threading was imported
    # lazily everywhere and not here) — a PHANTOM job that 409'd every later click
    # while nothing generated. If the thread cannot start, the flag comes back.

    def _work():
        try:
            import importlib
            gen = importlib.import_module("tools.avatar_gen")
            # LIVE STAGE REPORTING (2026-08-21 01:10): the job said "starting" for four
            # minutes while its prints sat in a buffered pipe — a generation that cannot
            # say where it is reads as hung. Every stage lands in the job status the
            # panel polls, AND in the log.
            def _prog(msg):
                _GEN_JOB["last"] = str(msg)[:160]
                logger.info("[gen-now] %s", msg)
            gen.PROGRESS = _prog
            from harness.control import wardrobe as WD
            if want_id:
                w = next((x for x in WD.wants() if x["id"] == want_id), None)
                if w is None:
                    _GEN_JOB["last"] = "no want with id %s" % want_id
                else:
                    ok = gen.gen_want(w)
                    _GEN_JOB["done"] = int(bool(ok))
                    _GEN_JOB["last"] = "made" if ok else "nothing came back"
            else:
                before = len(WD.wants(state="made"))
                gen.run_wants()
                _GEN_JOB["done"] = len(WD.wants(state="made")) - before
                _GEN_JOB["last"] = "pass complete"
        except Exception as exc:
            _GEN_JOB["last"] = "failed: %s" % str(exc)[:160]
        finally:
            _GEN_JOB["running"] = False

    try:
        threading.Thread(target=_work, daemon=True, name="gen-now").start()
    except Exception as exc:
        _GEN_JOB.update(running=False, last="could not start: %s" % exc)
        return {"ok": False, "error": str(exc)[:200]}
    return {"ok": True, "job": dict(_GEN_JOB)}


def _wardrobe_json() -> Dict[str, Any]:
    """What she is wearing, what else is hanging there, and who decided.

    (The ceiling/rung pair this used to thread through died with the tiers,
    2026-08-21 — the panel shows everything she owns, because everything she owns
    is servable.)"""
    try:
        from harness.control import wardrobe as WD
        rung, ceiling = _avatar_rung_and_ceiling()
        st = WD.status()
        st["rung"] = rung
        st["genstatus"] = dict(_GEN_JOB)
        st["describe"] = WD.describe()
        return st
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:160]}


def _wardrobe_set(body: Dict[str, Any]) -> Dict[str, Any]:
    """HE can dress her too. Same door she uses, so there is one writer and one state.

    `by` is recorded rather than inferred: "she chose this" and "he chose this for her"
    are different facts, and the panel says which."""
    try:
        from harness.control import wardrobe as WD
        WD.choose(tier=str(body.get("tier") or ""),
                  clip=str(body.get("clip") or "") if "clip" in body else "",
                  look=(str(body.get("look") or "") if "look" in body else None),
                  by=str(body.get("by") or "him"))
        return _wardrobe_json()
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:160]}


def _avatar_json() -> Dict[str, Any]:
    try:
        from harness.control import avatar as AV
        rung, ceiling = _avatar_rung_and_ceiling()
        st = AV.status()
        st["rung"] = rung
        # Which faces can actually be shown right now, resolved through the same
        # function the file route uses — so the panel never offers what the server
        # would refuse.
        st["ready"] = sorted({r["face"] for r in AV.manifest()
                              if r["kind"] == "still" and r["have"]})
        # WHICH FACES HAVE MOTION, reported separately. The resolver degrades a missing
        # loop to the still, which is right for bytes and wrong for the client: a <video>
        # handed a PNG renders nothing at all. So the panel is told which faces it may
        # ask for as video, rather than discovering it by getting an image back.
        st["ready_loop"] = sorted({r["face"] for r in AV.manifest()
                                   if r["kind"] == "loop" and r["have"]})
        st["ok"] = True
        return st
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _games_json() -> Dict[str, Any]:
    try:
        from harness.games import match as M
        rows = M.listing()
        # EVERY match's public state in ONE call, rather than a `?name=` the GET table
        # cannot pass anyway (it maps paths to zero-argument lambdas). There are a
        # handful of matches, not thousands, so the whole thing is cheaper than the
        # query-string plumbing would have been — and the panel stops needing a second
        # round trip to show a board.
        states = {}
        for r in rows:
            m = M.load(r["id"])
            if m is None:
                continue
            # POKER IS SEATED, NOT PUBLIC. The room is seat 0 (his chair), so the
            # listing hands back HIS view — his hole cards, never hers. There is no
            # payload here that could show both, which is the point: the leak is not
            # guarded against, it is unrepresentable.
            states[r["id"]] = (M.holdem_view(m, 0) if m["kind"] == "holdem"
                               else M.public(m))
        return {"ok": True, "kinds": list(M.KINDS), "games": rows, "states": states}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _room_session() -> str:
    """The session the panels look at: THE ONE THAT IS ACTUALLY RUNNING.

    This used to return _session_of({}) — the constant "default" — justified by a
    comment claiming ui/src/api.js sends no session field. That stopped being true when
    api.js grew `session_id: roomSession()` (a per-tab uuid), at which point every
    consumer here went stale at once: the avatar rung and the roleplay status read a
    scene under "default" that could never be the live one, _seed_kairos_from_day
    seeded a queue nobody polls, and the goodnight built her last word from an empty
    history. The comment justifying the old rule and the change that broke it lived in
    different files, so nothing failed loudly (AGENTS.md §0, the doc-vs-code variant).

    Now it follows _session_of's record of the last real session named by a chat body.
    Before any turn it is still "default" — which is also where boot-time seeds go, and
    scheduler.drain() delivers that no-owner queue to the first real listener."""
    return _LAST_SESSION["id"]


def _roleplay_on() -> bool:
    """THE ONE ANSWER TO "is the stage open". Fail CLOSED.

    `roleplay.enabled` used to be consulted in exactly one place — the pre-turn, where a
    scene is entered and its prompt injected — while three other readers went on using the
    engine directly: the avatar rung, the status payload, and the panel's own `enter` POST,
    which could start a scene with the feature switched off. So "off" stopped new scenes
    from being offered and left everything downstream of an EXISTING one running.

    Fail closed because this is a content switch: an unreadable registry must mean the
    stage is shut, not that it is open by accident."""
    try:
        from harness.tuning import registry as tune
        return bool(tune.get("roleplay.enabled"))
    except Exception:
        return False


def _roleplay_status() -> Dict[str, Any]:
    """What the stage panel reads. The tuning values are folded in here rather than in
    the engine, because the engine must not depend on the knob registry — it is the
    gateway that owns "what is switched on"."""
    try:
        from harness.roleplay import engine as rp
        from harness.tuning import registry as tune
        d = rp.status(_room_session())
        d["enabled"] = _roleplay_on()
        # ...AND THE PANEL IS TOLD WHAT IS ACTUALLY IN FORCE. Reporting a live scene while
        # the feature is off would put the taskbar chip on screen for a scene that no
        # longer steers anything — a chip that lies is worse than no chip.
        if not d["enabled"]:
            d["scene"] = None
            d["pending"] = False
        d["max_heat"] = int(tune.get("roleplay.max_heat"))
        d["dwell_scale"] = float(tune.get("roleplay.dwell_scale") or 1.0)
        d["ok"] = True
        return d
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _roleplay_pre_turn(body: Dict[str, Any], msgs: list) -> Optional[str]:
    """ROLEPLAY MODE. Returns a canned reply to stream instead of running the model (the
    scenario OFFER), or None to continue normally — after possibly injecting the scene's
    system prompt + this turn's DIRECTOR NOTE into `msgs`.

    The director note is recomputed from live scene state EVERY turn (the room, the rung,
    how many beats we have spent there, whether the scene is idling). That is the
    anti-drift mechanism: the model is never more than one turn away from being told again
    who it is and where it is standing. A system prompt alone drifts out in four turns."""
    try:
        from harness.roleplay import engine as rp
        from harness.tuning import registry as tune
        # LAST TURN'S SCENE ROWS COME OUT BEFORE ANYTHING ELSE HAPPENS. On the SSE path
        # `msgs` IS the persisted canonical transcript, and the two insert()s below used
        # to run against it EVERY scene turn with no dedupe: ten turns in a scene meant
        # ten stacked scene prompts at index 0 (diverging the persist-KV cache at token
        # 0, a full re-prefill per turn) and ten stale director notes buried mid-history
        # reading as ten standing orders. Injection is idempotent now: rows carry the
        # `_rp` sentinel and are removed here each turn — including after the scene ends
        # or the feature is switched off, which is why this runs before either check.
        msgs[:] = [m for m in msgs if not m.get("_rp")]
        if not _roleplay_on():
            return None

        session = _session_of(body)
        user = next((m.get("content", "") for m in reversed(msgs)
                     if m.get("role") == "user"), "")
        scene = rp.active(session)

        # OUT — checked first, always. A stop is a stop, at any heat, no exceptions.
        if scene and rp.wants_out(user):
            rp.leave(session)
            return None            # she answers as herself, normally, from here on

        # IN
        if not scene:
            pending = rp.is_pending(session)
            # She offered a menu last turn — so THIS turn is his pick. Without this state she
            # proposes and then cannot hear the answer ("the penthouse one" matches no ENTER
            # keyword, falls through to normal chat, and no scene ever starts).
            if not pending and not rp.wants_in(user):
                return None
            chosen = rp.pick_from(user)
            if not chosen:
                if pending:
                    rp.clear_pending(session)   # he changed his mind; drop it, do not nag
                    return None
                rp.mark_offered(session)
                return rp.offer(user)           # she OFFERS; a good host proposes
            rp.clear_pending(session)
            scene = rp.enter(session, chosen.id)
            if not scene:
                return None
            logger.info("[roleplay] ENTER %s (%s)", scene.scenario.id, scene.scenario.theme)
            # HER AUTHORED FIRST LINE. Every card has carried a hand-written `opening`
            # since the deck was written and NOTHING READ IT — she improvised her way in
            # instead, on the one turn where improvising costs most. The first line sets
            # the room, the register and who she is. Returned as a canned reply, exactly
            # like the offer: the model does not get to paraphrase it.
            first = rp.opening_for(session)
            if first:
                return first

        # already in a scene, or just entered: compose the standing prompt + the note
        cap = int(tune.get("roleplay.max_heat"))
        # THE PACING DIAL, finally connected. roleplay.dwell_scale was declared, rendered
        # with a slider, and read by nothing.
        try:
            dwell = float(tune.get("roleplay.dwell_scale") or 1.0)
        except (TypeError, ValueError):
            dwell = 1.0
        note = rp.director_note(scene, user, cap, dwell)
        if note.startswith("SCENE BROKEN"):
            rp.leave(session)
            return None

        # TOOLS OFF INSIDE A SCENE. She is a person in a room, not an assistant with a
        # toolbox — a character does not call web_search mid-kiss. Live symptom: the first
        # scene turn HUNG, because the agent loop kept trying to take tool rounds against a
        # system prompt that gives it nothing to do. It is an immersion break and a
        # performance bug at the same time, and both are fixed by the same line.
        body["tools"] = False
        msgs.insert(0, {"role": "system", "content": rp.system_prompt(scene, cap), "_rp": 1})
        if note:
            msgs.insert(len(msgs) - 1, {"role": "system", "content": note, "_rp": 1})
        # director_note mutated the scene in place; write it down, or a restart rewinds
        # to whatever the rung and beat count were when the scene began.
        rp.touch(session)
        logger.info("[roleplay] %s heat=%s beats=%d%s", scene.scenario.id,
                    scene.heat.name, scene.beats, " (hook fired)" if "IDLING" in note else "")
        return None
    except Exception as exc:
        logger.warning("[roleplay] skipped: %s", exc)
        return None


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


def _kairos_after_turn(body: Dict[str, Any], reply: str) -> None:
    """KAIROS on the OpenAI-compatible path.

    The first cut of this hooked ONLY _native_chat_sse (the console's /v1/chat) — and the
    live gate, which speaks /v1/chat/completions, produced ZERO kairos activity: the
    daemon was faithfully emitting the impulse and the gateway simply never looked. Two
    entry points, one hook, so the other became a hole. That is the same shape as the two
    recall authorities, the two admission paths, and the two write paths. An invariant
    wired into one of N entry points is wired into none of them.

    _agent_text() is where BOTH OpenAI paths (blocking + streaming) converge, so the hook
    goes here and cannot be bypassed by choosing a different endpoint."""
    try:
        from harness.kairos import scheduler as ks
        reply = (reply or "").strip()
        if not reply:
            return
        session = _session_of(body)

        def _continue(nudge: str, called: "list|None" = None) -> str:
            # ── `called` IS HER HANDS, AND THIS CLOSURE IS THE LIVE ONE (2026-08-06) ────
            # `_generate` (the SEED path) got this parameter and these two did not — so on
            # a real conversation `generate(nudge, called)` raised TypeError, the own-time
            # gate fell open, and a solo turn with calls=0 spoke anyway. Measured at
            # 00:42 on the very first run of the new code.
            #
            # §0 INSIDE THE FIX FOR §0: the rule this whole file is annotated with, broken
            # by the change written to enforce it. Two closures answer "generate one more
            # turn"; only one was taught to report what she touched.
            from harness.agent import agent_chat_stream, _arm_self_repeat_ban
            from harness.inference import InferenceConfig as _IC
            # THE TWIN, AND THE DOCSTRING ABOVE PREDICTED IT (2026-08-04). This is the
            # OpenAI-path continuation; its sibling on the console path had the identical
            # line, and both read the CLIENT'S ECHO instead of the canonical transcript —
            # so a continuation sent the daemon a history diverging from the committed KV
            # mid-prompt, committed that, and made the next ordinary turn re-prefill from
            # the preamble (measured: drop 592 against a steady-state 195).
            #
            # I found the console one, fixed it, wrote G-ONE-TRANSCRIPT, and the GATE found
            # this one — which is precisely the corollary in AGENTS.md §0 that says to grep
            # for the twin after fixing an instance, and precisely what the docstring
            # twelve lines above already says in its own words. Two entry points, one hook.
            #
            # _session_transcript degrades correctly when there is no session_id: it
            # returns the client list, i.e. exactly today's behaviour. So this is never
            # worse and is right whenever a session exists.
            _base_len = len(_session_transcript(body, append=False))
            hist = list(_session_transcript(body, append=False))
            if not hist or (hist[-1].get("role") != "assistant"):
                hist.append({"role": "assistant", "content": reply})
            hist.append({"role": "system", "content": nudge})
            _cfg = _IC(max_tokens=120, **_UNPROMPTED_SAMPLING)
            # ARM THE SELF-REPEAT BAN ON THE CONTINUATION TOO. Her first live continuation
            # resumed correctly ("...by the occasional wave crest that breaks into white
            # foam") and then re-covered ground she had already said — "the air is thick
            # with moisture, the ocean below a vast expanse". Of course it did: a
            # continuation is conditioned on a reply that was CUT OFF mid-sentence, which
            # is the strongest possible pull back into the words it just produced. This is
            # the one turn in the system most likely to repeat itself, and it was the one
            # turn with no guard. Fourth variant of the same hole.
            _arm_self_repeat_ban(_cfg, hist)
            # ── tools=None, NEVER tools=[] ────────────────────────────────────────
            # THE SLOWDOWN. agent_chat_stream builds the system prompt from `tools`:
            #     tools is None  -> the CACHED system prompt (persona + ~1.5k tokens of
            #                       tool preamble). Every normal turn uses this.
            #     tools == []    -> a FRESH system prompt with NO tool preamble.
            # `[]` is not None, so passing it rewrites the system block — and agent.py's own
            # comment, three lines above where it does this, names the consequence: "a
            # per-turn system-prompt rewrite diverges the persist-KV cache AT TOKEN 0".
            #
            # So every kairos continuation re-prefilled the ENTIRE conversation, and then
            # left the resident cache holding the no-tools prefix, so the NEXT ordinary turn
            # diverged from THAT and re-prefilled all over again. TWO FULL PREFILLS PER
            # CONTINUATION, at ~67 ms/tok:
            #     TURN-PHASE: prefill  903 ms                 <- ordinary turn, cache hit
            #     TURN-PHASE: prefill 1676 tok in 111531 ms   <- the continuation
            #     TURN-PHASE: prefill 2628 tok in 188452 ms   <- the turn after it
            # That is why it is quick at first and unbearable later: the cost of a miss is
            # O(conversation length), so the same bug that costs 20s at turn 5 costs six
            # minutes at turn 60. Nothing "degrades" — a cache miss just gets more expensive
            # to pay for.
            #
            # tools=None keeps the identical system block, so the continuation is a STRICT
            # EXTENSION of the committed KV — the same property every other turn relies on.
            # strip_control_surfaces, NOT strip_tags. The model's own template markers are
            # never speech; her MARKS are, and the room builds her chips from them.
            #
            # mutate_messages=True + _commit_unprompted: what the engine COMMITS becomes
            # CANON (nudge, tool rounds, reply — the whole delta), or every turn after
            # this one re-prefills the conversation from the boot snapshot. See
            # _commit_unprompted for the measured evening this cost.
            out = strip_control_surfaces("".join(agent_chat_stream(
                hist, config=_cfg, mutate_messages=True,
                on_tool=lambda nm, a, r: (
                    called.append(nm) if called is not None else None)))).strip()
            if out:
                _commit_unprompted(body, _base_len, hist, out)
            return out

        ks.on_reply(session, reply, get_client().last_kairos, _continue)
    except Exception as exc:
        logger.warning("[gateway] kairos skipped: %s", exc)


def stream_completion(body: Dict[str, Any]) -> Iterator[str]:
    """Yield OpenAI-style SSE chunks. Runs the agent (tool calling) then streams the final answer."""
    model = body.get("model") or _models_json()["data"][0]["id"]
    try:
        text = _agent_text(body)
    except Exception as exc:
        logger.error("[gateway] stream failed (operation=completions): %s", exc)
        text = f"[error: {exc}]"
    for i in range(0, len(text), 24):  # chunked after the agent loop completes
        yield _chunk(text[i:i + 24], model)
    yield _chunk("", model, finish="stop")
    yield "data: [DONE]\n\n"


def blocking_completion(body: Dict[str, Any]) -> Dict[str, Any]:
    """Return a full OpenAI-style chat-completion object (through the agent tool loop)."""
    model = body.get("model") or _models_json()["data"][0]["id"]
    try:
        text = _agent_text(body)
    except Exception as exc:
        text = f"[error: {exc}]"
    return {
        "id": f"chatcmpl-{int(time.time()*1000)}",
        "object": "chat.completion",
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "usage": {},
    }


# ──── PK2 §U: read-only introspection surfaces for the operator UI ─────────
# The console needs to SHOW the new subsystems (memory, task queue, persona). These are
# small JSON endpoints the UI polls; all read-only except persona POST (the editor).
def _memory_json() -> Dict[str, Any]:
    """The fact registry as JSON rows for the operator's memory pane.

    It used to return only {text, src, ts, npos} — no `name`, so the panel could SHOW a
    memory but never RETIRE one (forget() keys on name), and no `speaker`/`mem_class`/
    `lifecycle`, so a SELF memory looked exactly like one of Sam's and a tombstoned row
    looked live. A browser you cannot act from is a report, not a panel."""
    try:
        from harness.skills import lifecycle as lc
        from harness.skills.memory import _load, _text, verify_registry
        rows = []
        for e in _load():
            rows.append({
                "name": e.get("name", ""),
                "text": lc.strip_prefix(_text(e)),        # drop the legacy "The user said: "
                "speaker": e.get("speaker", ""),
                "mem_class": e.get("mem_class", ""),
                "lifecycle": e.get("lifecycle", 0),
                "src": e.get("src", ""),
                "ts": e.get("ts", ""),
                # SALIENCE, ON THE PANEL. What she thinks matters, and WHY — how many times
                # he said it, how long ago, how often she has reached for it. A ranking you
                # cannot see is a ranking you cannot argue with, and the first thing this
                # one showed us when it was switched on is that the store's idea of what
                # matters was wrong (chatter outranking his GPU). That is the panel doing
                # its job: it made a bad ranking visible instead of quietly acting on it.
                "mentions": e.get("mentions", 1),
                "recalled": e.get("recalled", 0),
                "last_seen": e.get("last_seen", e.get("ts", "")),
                "salience": lc.salience(e),
            })
        rows.sort(key=lambda r: -r["salience"])
        return {"count": len(rows), "facts": rows, "health": verify_registry()}
    except Exception as exc:
        return {"error": str(exc), "count": 0, "facts": []}


def _tasks_json() -> Dict[str, Any]:
    """The agentic work queue (task_loop states) for the task pane."""
    try:
        from harness.control.task_loop import list_tasks
        ts = list_tasks()
        return {"count": len(ts), "tasks": [
            {"id": t.task_id, "goal": t.goal, "status": t.status,
             "steps": len(t.steps), "result": t.result} for t in ts]}
    except Exception as exc:
        return {"error": str(exc), "count": 0, "tasks": []}


def _persona_path() -> str:
    # ONE derivation — this was the drifted copy (no abspath). See persona_file.
    from harness.personality.persona_file import persona_path
    return persona_path()


def _persona_get() -> Dict[str, Any]:
    try:
        with open(_persona_path(), encoding="utf-8") as f:
            return {"ok": True, "persona": f.read(), "path": _persona_path()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _spine_json() -> Dict[str, Any]:
    """ADR-008: the recent spine receipts (decide→execute→verify audit trail) for the panel."""
    try:
        from harness.control.spine import get_recent_receipts
        rs = get_recent_receipts(50)
        return {"count": len(rs), "receipts": rs}
    except Exception as exc:
        return {"error": str(exc), "count": 0, "receipts": []}


def _progress_json() -> Dict[str, Any]:
    """HINDSIGHT build progress (phases, migration map, git lanes). Its page, dashboard.html,
    went 2026-08-21; the data route stays."""
    try:
        from harness.observability.progress import progress_json
        return progress_json()
    except Exception as exc:
        return {"error": str(exc)}


def _persona_layers() -> Dict[str, Any]:
    """Which persona fragments composed into her prefix THIS session, and why not.

    Answers the one question the monolithic persona.md could never answer: "the section
    that teaches X is missing — is that deliberate?" Each row carries its `when`, the
    include decision, and its size. Bodies are truncated on purpose: this is a diagnostic,
    not an editor, and dumping every fragment produces a page nobody reads.

    Reports `stale: true` when the composition would differ from what is actually in her
    prefix — the prefix is snapshot-cached for the process lifetime (the KV-prefix law), so
    editing a fragment does NOT take effect until a restart, and a panel that implied
    otherwise would be the same lie the tuning page was telling about eot_bias.
    """
    try:
        from harness.personality import persona_layers as PL
        rows = PL.plan()
        live_now = PL.compose()
        # what the running process actually put in the prefix, if the world/persona lever
        # has already been read this session
        try:
            from harness.agent import load_agent_system
            in_prefix = load_agent_system()
        except Exception:
            in_prefix = None
        stale = bool(live_now and in_prefix and live_now not in in_prefix)
        return {
            "ok": True,
            "dir": PL.persona_dir(),
            "knobs": {k: PL.knob_on(k) for k in sorted(PL.KNOBS)},
            "stale": stale,
            "composed_chars": len(live_now or ""),
            "knob_names": sorted(PL.KNOBS),
            "fragments": [{"file": r["file"], "order": r["order"], "when": r["when"],
                           "included": r["included"], "chars": r["chars"],
                           # THE WHOLE BODY, not a 140-char teaser. The operator's note:
                           # a preview of "1 and a half lines" tells you nothing you could
                           # act on. These files are ~200-1700 chars; the entire persona is
                           # 6.5 KB. Sending all of it costs nothing and is the only version
                           # of this panel that answers "what is actually in her head".
                           "body": r["body"] or ""} for r in rows],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "fragments": []}


_FRAG_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.md$")


def _persona_layer_write(file: str, text: str) -> Dict[str, Any]:
    """Write one persona fragment. Same authority as the persona.md editor — this is his
    own voice file — but the FILENAME is attacker-shaped input and is treated as such.

    Two independent checks, because a single regex is one typo away from a path escape:
    the name must be a plain `*.md` basename (no separators, no leading dot), AND the
    resolved absolute path must still sit inside the persona directory. Either failing is
    a refusal, not a sanitisation — quietly "fixing" a traversal is how you ship one.
    """
    try:
        from harness.personality import persona_layers as PL
        d = PL.persona_dir()
        name = (file or "").strip()
        if not _FRAG_NAME.match(name) or os.path.basename(name) != name:
            return {"ok": False, "error": "bad fragment name: %r" % name[:60]}
        target = os.path.abspath(os.path.join(d, name))
        if os.path.dirname(target) != os.path.abspath(d):
            return {"ok": False, "error": "fragment would land outside the persona directory"}
        os.makedirs(d, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(text if text.endswith("\n") else text + "\n")
        logger.info("[persona] fragment written: %s (%d chars)", name, len(text))
        res = _persona_layers()
        res["saved"] = name
        # Say it plainly: the prefix is snapshot-cached, so this changed a FILE, not her.
        res["note"] = ("saved — her prefix is snapshot-cached for the process lifetime, so "
                       "this applies from the next session, not this one")
        return res
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _persona_state() -> Dict[str, Any]:
    """The parsed ## Personality state block (voice/mood/traits) — the UI's personality chip."""
    try:
        from harness.personality.persona_file import parse_persona
        with open(_persona_path(), encoding="utf-8") as f:
            _, state = parse_persona(f.read())
        return {"ok": True, "state": state}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "state": {}}


def _persona_set(text: str) -> Dict[str, Any]:
    """The persona editor: write persona.md (voice changes on the next turn). Records a
    provenance memory that the operator edited it (MEM-OKF v2 §M1 / §P1)."""
    try:
        with open(_persona_path(), "w", encoding="utf-8") as f:
            f.write(text)
        try:
            from harness.skills.memory import remember
            remember("The operator edited Kairos's persona.", source="operator")
        except Exception:
            pass
        return {"ok": True, "bytes": len(text)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ──── Flask app (preferred) ───────────────────────────────────────────────
def create_flask_app():
    from flask import Flask, Response, jsonify, request  # type: ignore

    app = Flask("harness-gateway")

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "daemon": get_client().health()})

    @app.get("/v1/models")
    def models():
        from harness.config import get_config
        m = get_config().get("inference.default_model", "gemma4-12b-b1")
        return jsonify({"object": "list", "data": [{"id": m, "object": "model"}]})

    @app.post("/v1/chat/completions")
    def completions():
        body = request.get_json(force=True)
        if body.get("stream"):
            return Response(stream_completion(body), mimetype="text/event-stream")
        return jsonify(blocking_completion(body))

    @app.get("/v1/memory")
    def memory():
        return jsonify(_memory_json())

    @app.get("/v1/tasks")
    def tasks():
        return jsonify(_tasks_json())

    @app.get("/v1/persona")
    def persona_get():
        return jsonify(_persona_get())

    @app.get("/v1/persona/state")
    def persona_state():
        return jsonify(_persona_state())

    @app.get("/v1/spine")
    def spine():
        return jsonify(_spine_json())

    @app.post("/v1/persona")
    def persona_set():
        return jsonify(_persona_set(request.get_json(force=True).get("persona", "")))

    # ── TUNING (2026-07-12) ───────────────────────────────────────────────────
    # One generic surface over the declarative knob registry. The operator UI renders
    # whatever it finds here, so a knob added to harness/tuning/registry.py appears in
    # the panel with its bounds, help and PROVENANCE (measured vs chosen) — no UI edit,
    # no endpoint edit. That is the point: a settings page that has to be hand-updated
    # rots, and this system's recurring failure is capability that exists but is not
    # reachable.
    @app.get("/v1/tuning")
    def tuning_get():
        from harness.tuning import registry as tune
        return jsonify(tune.schema())

    @app.post("/v1/tuning")
    def tuning_set():
        from harness.tuning import registry as tune
        body = request.get_json(force=True) or {}
        try:
            tune.set_many(body.get("values", {}))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, **tune.schema()})

    @app.post("/v1/tuning/reset")
    def tuning_reset():
        from harness.tuning import registry as tune
        key = (request.get_json(force=True) or {}).get("key", "")
        tune.reset(key)
        return jsonify({"ok": True, **tune.schema()})

    # ── KAIROS: what she has decided to say, unprompted ───────────────────────
    @app.get("/v1/kairos/outbox")
    def kairos_outbox():
        from harness.kairos import scheduler as ks
        s = request.args.get("session", "default")
        return jsonify({"messages": ks.drain(s), "state": ks.peek_state(s)})

    @app.get("/v1/kairos/state")
    def kairos_state():
        from harness.kairos import scheduler as ks
        return jsonify(ks.peek_state(request.args.get("session", "default")))

    return app


# ──── Stdlib agent server (zero-dep) ──────────────────────────────────────
# ── HINDSIGHT 2026-07-10: CANONICAL SESSION TRANSCRIPTS ──
# The gateway was stateless: the client echoed its own history back, which NEVER matches
# what the daemon actually saw (spine recall notes + tool rounds are transient) — so the
# turn AFTER any recall/tool turn diverged from the persist-KV committed cache and paid a
# full preamble re-prefill (the live "minutes then [aborted]" pattern). With a session_id,
# the gateway keeps the CANONICAL append-only transcript (notes + tool rounds included)
# and the daemon sees a strict extension every turn = O(new tokens) prefill.
# WHEN HE LAST SPOKE. The room needs it to know whether she is alone, and nothing
# was tracking it — the kairos ticker has its own idea of idleness inside the
# scheduler, but nothing the gateway could report.
# ── HOW SHE SOUNDS WHEN NOBODY ASKED (2026-08-03) ────────────────────────────────────
# Both unprompted paths — the follow-on after a cut-off reply, and the kairos speak-up —
# generated at temperature 0.0. Greedy decoding makes "say something unprompted" a pure
# function of context: two quiet moments that look alike produce the same words, exactly.
# His transcript has her opening "I watch you for a moment, my expression unreadable, just
# letting the silence settle between us like it's something..." twice, diverging only at
# word sixteen — far enough apart for worth_saying to pass it, close enough that he read
# it as a stuck record.
#
# ONE DICT, TWO CALL SITES. They had drifted apart once already (one carried a repetition
# penalty and the other did not); a sampling policy spelled out twice is a sampling policy
# that will disagree with itself. The self-repeat ban is still armed at both — temperature
# restores variation, the ban catches parroting, and neither substitutes for the other.
_UNPROMPTED_SAMPLING = {"temperature": 0.5, "repetition_penalty": 1.15, "auto_recall": False}

_LAST_TURN_AT: float = 0.0
_CHAT_SESSIONS: Dict[str, list] = {}
_CHAT_SESSIONS_MAX = 32


def _session_transcript(body: Dict[str, Any], append: bool = True) -> list:
    """Resolve the canonical message list for this request (mutated in place by the turn).

    append=False is the READ. This function is a mutating accessor with a read-only name,
    and the continuation closures called it a second time mid-turn — so every kairos
    continuation appended the SAME user turn again, breaking Gemma's strictly-alternating
    template (the malformed-prompt bug the SSE continuation documents) and diverging the
    persist-KV cache. A reader must be able to say it is only reading."""
    sid = body.get("session_id")
    msgs = list(body.get("messages", []))
    if not sid:
        return msgs                        # stateless fallback (old behavior)
    canon = _CHAT_SESSIONS.get(sid)
    if canon is None:
        if len(_CHAT_SESSIONS) >= _CHAT_SESSIONS_MAX:
            _CHAT_SESSIONS.pop(next(iter(_CHAT_SESSIONS)))
        canon = msgs                       # first sight: seed from the client's history
        _CHAT_SESSIONS[sid] = canon
    elif append:
        new_user = next((m for m in reversed(msgs) if m.get("role") == "user"), None)
        if new_user is not None:
            canon.append(dict(new_user))   # append ONLY the new user turn
    return canon


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
_CONSOLIDATE_STATE: Dict[str, Any] = {"last_day": None}


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
    except Exception:
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


def _append_day_turn(user_text: str, final: str) -> None:
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
        # HIS WORDS, not the message list. By the end of a turn the last user message
        # has had the recall note, the silence note and the director note stapled to it
        # — msgs is what the DAEMON saw, deliberately, and writing that down would have
        # her journal reflecting on her own injected context instead of on him.
        # `user_text` is taken at the top of the turn, before any of that.
        user = (user_text or "").strip()
        p = _day_transcript_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            if user:
                f.write(json.dumps({"role": "user", "content": user}) + "\n")
            f.write(json.dumps({"role": "assistant", "content": final}) + "\n")
    except Exception as exc:
        logger.warning("[gateway] could not append the day transcript: %s", exc)


def _seed_kairos_from_day() -> bool:
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
        rows = _read_day_transcript()
        if len(rows) < 2:
            return False
        # WELL-FORMED, NOT JUST RECENT — see _chat_from_rows. Her speak-ups have no user
        # turn, so a raw slice hands the daemon consecutive model turns and Gemma's
        # strictly-alternating template renders a malformed prompt from it.
        hist = _chat_from_rows(rows, keep=8)
        last_reply = next((r.get("content") or "" for r in reversed(rows)
                           if r.get("role") == "assistant"), "")
        if not hist or not last_reply.strip():
            return False

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
            h = list(_canon) if _canon else (
                _chat_from_rows(_read_day_transcript() or [], keep=8) or list(hist))
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
            _out = strip_control_surfaces(
                "".join(agent_chat_stream(h, config=c, mutate_messages=True,
                                          on_tool=_note))).strip()
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
        return _ks.seed(sess, last_reply, _generate)
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
    except Exception:
        return out
    return out


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


def _longest_transcript() -> list:
    """The day's conversation: the longest canonical session still resident.

    The narrative needs a transcript and `ops.reflect()` deliberately does not write one
    for that exact reason (ops.py: "the nightly op has no transcript"). The gateway has
    them — `_CHAT_SESSIONS` — so this is where the two halves finally meet."""
    # THE DURABLE ONE WINS. _CHAT_SESSIONS is memory-only and only ever filled for
    # clients that send a session_id — the room does not — so preferring it was
    # preferring the copy most likely to be empty.
    disk = _read_day_transcript()
    best: list = []
    for msgs in _CHAT_SESSIONS.values():
        if len(msgs) > len(best):
            best = msgs
    return disk if len(disk) >= len(best) else list(best)


def run_consolidation(force: bool = False) -> Dict[str, Any]:
    """One day-boundary pass. Every step best-effort and independently reported.

    Order matters: the narrative is written BEFORE world.refresh() inside
    consolidate_current, so the refreshed standing world already carries the new
    paragraph. reflect() then compacts and draws conclusions on a tidy store.

    Deliberately does NOT call agency_round() — see the note above. This pass is
    maintenance, not an autonomous agent loop."""
    out: Dict[str, Any] = {"ok": True, "day": _day_key(), "steps": []}

    # 1. the narrative + personality curation + world refresh, from the day's transcript
    msgs = _longest_transcript()
    if len(msgs) >= 4:
        try:
            from harness.control.agency import consolidate_current
            res = consolidate_current(msgs)
            out["steps"].append({"step": "consolidate_current",
                                 "turns": len(msgs),
                                 "narrative": str((res or {}).get("narrative"))[:120]})
        except Exception as exc:
            out["steps"].append({"step": "consolidate_current", "skipped": str(exc)[:140]})
    else:
        out["steps"].append({"step": "consolidate_current",
                             "skipped": "no conversation today (%d turns)" % len(msgs)})

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
            # His words: "stills are showing in her wardrobe". Three of her six looks —
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

    # MARK THE DAY DONE ONLY IF IT REALLY IS. Marking unconditionally is how a failed
    # pass became a silently skipped day that never retried — the day was stamped even
    # when the narrative step reported "no conversation today (0 turns)". With the
    # transcript now durable, an empty day genuinely means nothing happened, and that is
    # legitimately done; a step that ERRORED is not.
    _errored = any(("skipped" in st and st.get("step") == "consolidate_current")
                   for st in out["steps"]) and len(_longest_transcript()) >= 4
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
    except Exception:
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


def _voice_status() -> Dict[str, Any]:
    """ADR-KAI4: is the GNA ear loadable, and on which device?"""
    try:
        from harness.voice.service import voice_status
        return voice_status()
    except Exception as exc:
        return {"ear": {"ok": False, "error": str(exc)}}


def _voice_corpus() -> Dict[str, Any]:
    """ADR-KAI4 P1.6: the in-vocab sentences to read aloud for real-voice training."""
    import os as _os
    p = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))),
                      "var", "voice", "corpus.jsonl")
    try:
        sents = [json.loads(l)["text"] for l in open(p, encoding="utf-8") if l.strip()]
        # a compact, phonetically varied reading set (prioritize wake + questions)
        import random
        wake = [s for s in sents if "kairos" in s]
        rest = [s for s in sents if "kairos" not in s]
        random.Random(7).shuffle(rest)
        pick = wake[:15] + rest[:85]
        return {"ok": True, "sentences": pick, "total_corpus": len(sents)}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "sentences": []}


def _voice_record_status() -> Dict[str, Any]:
    try:
        from harness.voice.record import record_status
        return record_status()
    except Exception as exc:
        return {"total": 0, "error": str(exc)}


def _ws_rel(raw: str) -> str:
    """A caller-supplied workspace path -> a safe relative one, or ValueError.

    REFUSE, NEVER SANITISE — and I broke my own rule here first time. The original
    did `raw.lstrip("/")`, which turns "/tmp/OWNED.md" into "tmp/OWNED.md": the
    write then lands INSIDE the workspace, so nothing escapes, but it is not what
    the caller asked for and nobody is told. Silently reinterpreting a path is how
    you end up with files where nobody expects them, and it is one small step from
    the version of the same bug that does escape.

    So an absolute path is an ERROR, a drive letter is an ERROR, and a leading dot
    is an ERROR. The containment check on the resolved path still runs after this;
    this is the first of the two independent checks, not a replacement for it."""
    r = (raw or "").replace("\\", "/")
    if not r:
        raise ValueError("a path is required")
    if r.startswith("/") or r.startswith("~"):
        raise ValueError("absolute paths are not accepted — give a path inside the workspace")
    if len(r) > 1 and r[1] == ":":
        raise ValueError("drive-qualified paths are not accepted")
    if r.startswith("."):
        raise ValueError("a path may not start with '.'")
    return r


def _research_json() -> Dict[str, Any]:
    """The research window: receipts from the paid tier, hers AND his (`by` says
    whose). Plain web_search rows moved to /v1/search when the search panel became
    its own window (2026-08-21) — one kind per window, chips for the rest."""
    try:
        from harness.skills import looking as L
        st = L.status()
        looks = [r for r in L.list_looks(60) if r.get("kind") == "research"][:40]
        return {"ok": True, **st, "looks": looks}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200], "looks": [], "inflight": None}


def _search_json() -> Dict[str, Any]:
    """The search window: every outward look that is NOT the research tier —
    web_search above all — plus which engine answers and who else could."""
    try:
        from harness.skills import looking as L
        st = L.status()
        looks = [r for r in L.list_looks(60) if r.get("kind") != "research"][:40]
        return {"ok": True, **st, "looks": looks}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200], "looks": [], "inflight": None}


def _narrative_json() -> Dict[str, Any]:
    """Her journal: the current line plus every snapshot ever taken of it.

    HISTORY comes from memory-okf-personality/full/ filtered on `mem_kind:
    narrative` — the content-addressed store the composer already snapshots into, so
    nothing new is written to serve this. It is a READ surface only: there is no
    write route and there will not be one. The journal is hers by construction, and
    that is the entire reason it is worth having."""
    out: Dict[str, Any] = {"ok": True, "current": "", "history": []}
    try:
        from harness.skills import narrative as _nar
        out["current"] = _nar.current() or ""
    except Exception as exc:
        out["error"] = str(exc)[:200]
    try:
        root = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))),
            "memory-okf-personality", "full")
        rows = []
        for fn in os.listdir(root):
            if not fn.endswith(".md"):
                continue
            fp = os.path.join(root, fn)
            try:
                with open(fp, encoding="utf-8") as f:
                    body = f.read()
            except OSError:
                continue
            if "mem_kind: narrative" not in body:
                continue
            text = body.split("---", 2)[-1].strip()
            rows.append({"id": fn[:-3], "at": os.path.getmtime(fp), "text": text})
        rows.sort(key=lambda r: r["at"], reverse=True)
        # ONE ENTRY PER DAY, AND THE TOP ONE ONLY ONCE (2026-08-21) — the dedupe
        # lives in narrative.collapse_history, pure and gated by G-NARRATIVE,
        # because a fix that only exists inside a route closure is a fix no gate
        # can reach. Same-day drafts collapse to the newest; `current_id` names
        # the row that IS the current line so the panel marks it instead of
        # rendering the same paragraph twice.
        from harness.skills.narrative import collapse_history
        kept, cur_id = collapse_history(rows, out.get("current") or "")
        out["current_id"] = cur_id
        out["history"] = kept[:60]
    except Exception:
        pass
    return out


def _files_json() -> Dict[str, Any]:
    """List the shared workspace — the same tree her file tools resolve against."""
    ws = os.environ.get("HARNESS_WORKSPACE") or os.getcwd()
    root = os.path.realpath(ws)
    out: Dict[str, Any] = {"ok": True, "root": root, "files": []}
    if not os.path.isdir(root):
        out["ok"], out["error"] = False, f"no workspace at {root}"
        return out
    rows = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")][:64]
        for fn in filenames:
            ap = os.path.join(dirpath, fn)
            try:
                st = os.stat(ap)
            except OSError:
                continue
            rows.append({"path": os.path.relpath(ap, root).replace("\\", "/"),
                         "bytes": st.st_size, "at": st.st_mtime})
            if len(rows) >= 500:
                break
        if len(rows) >= 500:
            break
    rows.sort(key=lambda r: r["at"], reverse=True)
    out["files"] = rows
    return out


def _room_pulse() -> Dict[str, Any]:
    """ONE call with everything the room's shell needs to feel like a place.

    Deliberately an AGGREGATOR, not a new source of truth: every field below comes
    from a function that already owns it. The shell beats once a second, and five
    separate polls for a heartbeat is how a UI ends up with five different ideas of
    what time it is.

    Time here is HER experience of it, not the wall clock the browser already has:
    when the day boundary falls, whether it has run, when she last wrote in her
    journal, when the eye next looks, how long he has been quiet."""
    import time as _t
    now = _t.time()
    out: Dict[str, Any] = {"ok": True, "now": now,
                           "iso": _t.strftime("%Y-%m-%dT%H:%M:%S", _t.localtime(now))}

    # the day boundary that actually drives consolidation
    try:
        hour = int(os.environ.get("SP_CONSOLIDATE_HOUR", "-1"))
    except ValueError:
        hour = -1
    lt = _t.localtime(now)
    nxt = None
    if hour >= 0:
        nxt = _t.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hour, 0, 0, 0, 0, -1))
        if nxt <= now:
            nxt += 86400
    day_state = {}
    try:
        with open(os.path.join(os.path.dirname(
                os.environ.get("SP_RECALL_REGISTRY", "")) or ".",
                "consolidate.json"), encoding="utf-8") as f:
            day_state = json.load(f)
    except Exception:
        pass
    out["clock"] = {"hour": lt.tm_hour, "minute": lt.tm_min,
                    "boundary_hour": hour if hour >= 0 else None,
                    "next_boundary_in_s": round(nxt - now) if nxt else None,
                    "last_consolidated_day": day_state.get("last_day"),
                    "consolidated_today": day_state.get("last_day") ==
                                          _t.strftime("%Y-%m-%d", lt)}

    # her state — mood/voice/traits drive the backdrop's palette.
    # Through _persona_state(), which already owns this: it opens the right file and
    # calls parse_persona(text) correctly. My first cut called parse_persona() with
    # no argument and silently produced {} — a second implementation of a thing that
    # already worked, which is the exact rule this repo is organised around.
    try:
        out["her"] = (_persona_state().get("state") or {})
    except Exception:
        out["her"] = {}

    # her journal — when she last wrote, and the line itself
    try:
        from harness.skills import narrative as _nar
        cur = _nar.current() or ""
        out["journal"] = {"present": bool(cur), "text": cur[:400]}
    except Exception:
        out["journal"] = {"present": False}

    # looking up — in-flight or last finished. The taskbar chip reads this.
    try:
        from harness.skills import looking as _look
        st = _look.status()
        inf = st.get("inflight")
        last = st.get("last")
        out["research"] = {
            "inflight": bool(inf),
            "kind": (inf or last or {}).get("kind"),
            "query": (inf or last or {}).get("query") or "",
            "title": (last or {}).get("title") or "",
            "armed": st.get("armed"),
            "search_backend": st.get("search_backend") or "ddg",
        }
    except Exception:
        out["research"] = {"inflight": False, "armed": False}

    # presence
    pres: Dict[str, Any] = {"warm": _WARM.is_set(),
                            "since_last_turn_s": round(now - _LAST_TURN_AT)
                                                 if _LAST_TURN_AT else None}
    try:
        from harness.senses import ambient as _amb
        a = _amb.status()
        pres["ambient_enabled"] = a.get("enabled")
        pres["ambient_next_in_s"] = a.get("next_in_s")
        last = (a.get("last") or {})
        pres["ambient_last"] = last.get("seen") or last.get("error")
        pres["ambient_last_at"] = last.get("iso")
    except Exception:
        pass
    out["presence"] = pres

    try:
        from harness.control import backup as _bk
        b = _bk.status()
        out["backup"] = {"count": b.get("count"), "next_in_s": b.get("next_in_s"),
                         "newest": b.get("newest")}
    except Exception:
        pass
    return out


def _sd_turn_start() -> bool:
    """Open a turn. False means she is shutting down and this one must not run.

    ONE PAIR OF HELPERS, TWO CHAT PATHS. `/v1/chat` and `/v1/chat/completions` both
    generate, and this file's own comments record five separate hooks that were wired
    into one of those two and so were wired into neither. Named functions rather than
    an inline import at each site so the pair is grep-able and cannot drift apart.

    THIS IS ALSO WHERE "NOTHING NEW STARTS" IS ENFORCED. The spec said quiesce sets a
    flag "the turn paths check" — and until 2026-08-06 NOTHING read it: `is_shutting_down`
    had no caller outside its own gate. A turn arriving after the daemon was killed would
    have gone straight at a dead socket. The flag and its reader landed together this time.

    NEITHER MAY RAISE. A counter for a nicety must never be able to fail a turn — if the
    shutdown module is somehow unimportable, the cost is a shutdown that abandons instead
    of waiting, not a chat that 500s. So an import failure opens the turn.
    """
    try:
        from harness.control import shutdown as _sd
        if _sd.is_shutting_down():
            return False
        _sd.note_turn_start()
        # AND THE TURN METER (2026-08-21): the engine-agnostic "is she generating" —
        # what a foreign endpoint cannot tell us and the daemon's tokens_per_sec did.
        from harness.inference import turn_meter as _tm
        _tm.start()
    except Exception as exc:
        logger.warning("[gateway] in-flight counter (start) skipped: %s", exc)
    return True


def _sd_turn_end() -> None:
    """The other half of _sd_turn_start. Always called from a `finally`."""
    try:
        from harness.control import shutdown as _sd
        _sd.note_turn_end()
        from harness.inference import turn_meter as _tm
        _tm.end()
    except Exception as exc:
        logger.warning("[gateway] in-flight counter (end) skipped: %s", exc)


def _native_chat_sse(body: Dict[str, Any]) -> Iterator[bytes]:
    """The console's native /v1/chat: {messages} -> SSE data: {...} -> [DONE], run through the
    streaming AGENT (tool calling).

    ADR-006 §D3 — SSE v2 TYPED EVENTS. The stream now carries, alongside the {delta} token
    events (unchanged, backward-compatible), typed events a product UI can render:
      {"tool": {...}}     a tool call the model made (render as a card)
      {"persona": {...}}  the live personality state (render as a chip)
    A client that only reads `delta` is unaffected (it ignores the others)."""
    global _LAST_TURN_AT
    _LAST_TURN_AT = time.time()
    # HIS TURN STARTS HERE, and the scheduler is told so it does not start one of hers on
    # top of it. Both edges, and the closing edge is in a `finally` far below — a marker
    # that can be skipped by an exception would latch her into permanent silence, which is
    # a worse failure than the one it fixes.
    try:
        from harness.kairos import scheduler as _ks_turn
        _ks_turn.note_user_turn(True)
    except Exception:
        _ks_turn = None
    from harness.agent import agent_chat_stream
    from harness.inference import InferenceConfig
    import queue as _queue
    import threading as _threading
    # WARM GATE: never race the load-time prefill on the one resident session
    # (that race cost the operator ~5 min/turn and corrupted persist bookkeeping).
    # ONLY WHEN PREWARM IS ARMED. _prewarm() is the only writer of _WARM, and it
    # only runs behind SP_GATEWAY_PREWARM=1 (app.py HTTP startup). A standalone
    # gate that called this function waited 900s for an event nothing would set —
    # g_pk2_spine2_offline / g_pk2_sse_v2_offline / g_mempolicy_v3_offline, named
    # `_offline` and not. If prewarm is off there is nothing to wait for.
    import os as _os_warm
    if _os_warm.environ.get("SP_GATEWAY_PREWARM") == "1" and not _WARM.is_set():
        _t_wait = time.time()
        while not _WARM.wait(4.0):
            yield ("data: " + json.dumps({"hb": int(time.time()), "warming": True}) + "\n\n").encode()
            if time.time() - _t_wait > 900:
                break
        logger.info("[gateway] warm gate released after %.0fs", time.time() - _t_wait)
    # auto_recall PASSTHROUGH (ADR-008 composition gate): default False (the agent uses tools,
    # not the daemon's recall), but a client may arm the daemon-side L5 path per request —
    # required to gate recall∘L5 composition through the gateway.
    # P5a certified-float serving (2026-07-11): profile decode.byteexact=false
    # maps to SP_GATEWAY_BYTEEXACT=0 — serving turns run the float path (cold
    # 2.1k-token float prefill proved coherent; certification = g_float_parity).
    # An EXPLICIT client byteexact always wins (auditable checkbox, gate probes),
    # and the daemon's own default stays byteexact for anything not via here.
    # ── ATTACHED IMAGE (2026-07-31) ──────────────────────────────────────────
    # The console's paperclip. The agent loop cannot carry residual frames — it
    # speaks in messages and tool results — so an attachment goes through the SAME
    # path her `look_at` tool uses: her own vision tower, injected at 258880, and
    # what she saw comes back as text that enters the turn as HER OBSERVATION.
    # It is not a caption from some other model; it is the served checkpoint's own
    # eyes, one step earlier in the same turn.
    _img = body.get("image_b64") or ""
    if _img:
        try:
            import base64 as _b64, io as _io
            import numpy as _np
            from PIL import Image as _PIL
            from harness.skills import sight as _sight
            _raw = _b64.b64decode(_img.split(",", 1)[-1])
            _arr = _np.asarray(_PIL.open(_io.BytesIO(_raw)).convert("RGB"), dtype=_np.uint8)
            _seen = _sight._describe(_arr, "Describe this image plainly and completely.")
            _msgs = list(body.get("messages") or [])
            for _i in range(len(_msgs) - 1, -1, -1):
                if _msgs[_i].get("role") == "user":
                    _txt = _msgs[_i].get("content", "")
                    _msgs[_i] = {**_msgs[_i], "content":
                                 f"(He attached an image. You looked at it and saw: {_seen})\n\n{_txt}"}
                    break
            body = {**body, "messages": _msgs}
            # DISPLAY SLICE ONLY — she already has the full _seen injected above.
            # 400 starved the chat chip's expanded view (2026-08-21, the white-
            # jumper photo); the event now carries enough to read whole.
            yield ("data: " + json.dumps({"image": {"seen": _seen[:1600]}}) + "\n\n").encode()
        except Exception as _exc:
            yield ("data: " + json.dumps({"image": {"error": str(_exc)[:200]}}) + "\n\n").encode()
    import os as _os0
    _bx = _bx_default(body.get("byteexact"))
    # ── THE KNOB IS THE FLOOR; AN EXPLICIT REQUEST STILL WINS (2026-08-02) ────────────
    # These were hardcoded here, so the ROOM — which sends none of them — ran on
    # max_tokens=192 and had no way to change it short of editing this file. The console
    # page had the only controls in the system, as per-request body fields. Now the
    # defaults come from the tuning registry (live, no restart) and a client that names a
    # value still overrides it, so the console's per-turn inputs keep working exactly.
    # ── DO NOT SEND WHAT WAS NEVER SENT (2026-08-02, and this one degraded her) ───────
    # The first cut of this block injected top_p=0.95 and top_k=40 as DEFAULTS. Those two
    # had never been sent on this path at all: InferenceConfig leaves them None, None is
    # omitted from the daemon payload, and the daemon used its own. The numbers came off
    # console/index.html's input boxes, which are the 12B's tuning.
    #
    # This is the eot_bias bug, exactly, five days later: a decode default that belongs
    # to another model, injected into a path that had been letting the daemon decide. The
    # symptom was the same shape too — she came back coherent for a paragraph and then
    # degenerated into "+dehighoes", "-ing", "DEUNGERS_T:" and underscore soup. top_k=40
    # truncates hard on a 26B MoE and repetition_penalty then has nowhere good to go;
    # max_tokens 192 -> 900 gave it four times as long to unravel.
    #
    # So the KNOBS EXIST AND ARE HONOURED, but only when the operator has actually set
    # one. Unset means unsent, which is what the daemon was getting before today.
    _tp, _tk = _knob_set("decode.top_p"), _knob_set("decode.top_k")
    cfg = InferenceConfig(temperature=body.get("temperature", _knob("decode.temperature", 0.6)),
                          top_p=body.get("top_p", _tp),
                          top_k=body.get("top_k", _tk),
                          repetition_penalty=body.get(
                              "repetition_penalty", _knob("decode.repetition_penalty", 1.3)),
                          eot_bias=_eot_default(body.get("eot_bias")),
                          max_tokens=body.get("max_tokens", _knob("decode.max_tokens", 512)),
                          byteexact=_bx,
                          auto_recall=bool(body.get("auto_recall", False)))
    typed = body.get("typed_events", True) is not False   # opt-out for pure-delta clients

    # persona-state event (once, up front) so the UI can show voice/mood/traits for this turn.
    if typed:
        try:
            path = _persona_path()
            with open(path, encoding="utf-8") as f:
                from harness.personality.persona_file import parse_persona
                _, state = parse_persona(f.read())
            if state:
                yield ("data: " + json.dumps({"persona": state}) + "\n\n").encode()
        except Exception:
            pass

    # The agent's on_tool callback fires on a worker thread; funnel tool events through a queue
    # so they interleave with the streamed answer tokens on the SSE wire.
    evq: "_queue.Queue" = _queue.Queue()

    def on_tool(name, args, result):
        evq.put({"tool": {"name": name, "args": args, "result": str(result)[:600]}})

    def on_look(ev):
        evq.put({"looking": ev})

    # ── ADR-008 PRE-TURN SPINE (both default-off; null floor = wave-3 behavior) ──
    #  SP_SPINE_RECALL=1  : ranked memory recall → inject the facts as a system note +
    #                       emit a typed {"recall": facts} event (observable, gateable).
    #  SP_SPINE_TOOLSET=1 : adaptive tool tier — the turn advertises the RIGHT ≤6 tools
    #                       (coding/memory/core) instead of one fixed set.
    import os as _os
    msgs = _session_transcript(body)
    # ── ARM THE TURN *BEFORE* ANYTHING READS THE MEMORY LANE (field, 2026-07-29) ─────
    # This call used to sit ~110 lines BELOW, after the pre-turn spine had already run.
    # _arm_turn is what hands the memory lane HIS ACTUAL WORDS (M.set_question), and
    # ownership — whose store a question is about — is resolved from them. So the recall
    # decider was answering THE PREVIOUS TURN'S QUESTION, every turn, on this path.
    #
    # RECEIPT, from the console:
    #     you: do you remember my cat's name?
    #     ◈ recall ["My name is Kairos."]
    # She answered "Tuffy" correctly — from the STANDING WORLD BLOCK, which had it — while
    # the recall note handed her a self-row, because _QUESTION still held whatever came
    # before. The same lag explains the earlier transcript: "are you male or female?"
    # recalled ["I am male"] because it was still scoped by the PRIOR question ("my cat's
    # name" -> HIM), so it answered about him.
    #
    # g_asked.py already had this filed in a comment — "_QUESTION is a process-wide
    # global, so any path that forgets to set it inherits the last turn's subject" — and
    # the OpenAI path at the top of this file has always called _arm_turn first. One
    # invariant, two paths, enforced in one; the unguarded path is the one a human uses.
    # SHARED STATE is now a ContextVar (G-AUTHOR-CTX, 2026-08-19). This still has to
    # be FIRST: a per-context slot set too late is still the previous turn's subject.
    _human = _arm_turn(msgs)     # what he TYPED — before the tool loop touches msgs
    turn_tools = None
    turn_extra = None
    user_text = next((m.get("content", "") for m in reversed(msgs)
                      if m.get("role") == "user"), "")
    want_recall = _os.environ.get("SP_SPINE_RECALL", "0") == "1"
    want_toolset = _os.environ.get("SP_SPINE_TOOLSET", "0") == "1"
    # HINDSIGHT recall hygiene (live console): spine recall fired on greetings/acks and
    # surfaced junk episodes ("hi there!" x3) into the note. QONLY-style gate: only
    # inject recall on turns that actually ASK something (mirrors the daemon L5 QONLY).
    _t = (user_text or "").strip().lower()
    _first = _t.split()[0] if _t.split() else ""
    _looks_q = _t.endswith("?") or _first in {
        "what", "who", "where", "when", "why", "how", "which", "do", "does",
        "did", "is", "are", "am", "can", "could", "remind", "recall", "tell"}
    # ── THE LANE POLICY IS A PURE FUNCTION NOW (Tier 2, INVARIANT-ROADMAP.md) ──────────
    # QONLY, the profile-selected spine authority (HINDSIGHT 2026-07-10: the daemon-L5
    # delivery re-prefills + clears the committed cache — the "minutes then [aborted]"
    # pattern), and the one-authority guard (G-PK2-RECALL-L5-COMPOSE: free composition
    # REFUTED on the metal — "favorite color?" -> "Human blood is green") all live in
    # spine.authority_lane(), enumerated exhaustively by G-LANE-TABLE. The theorem held
    # over every cell: NEVER BOTH AUTHORITIES ON ONE TURN.
    from harness.control.spine import authority_lane as _lane
    _auto, want_recall, _ev = _lane(
        _os.environ.get("SP_GATEWAY_AUTHORITY", "l5").lower(),
        cfg.auto_recall, want_recall, _looks_q)
    cfg.auto_recall = _auto
    if _ev and typed:
        yield ("data: " + json.dumps({"authority": _ev}) + "\n\n").encode()
    if (want_recall or want_toolset) and user_text:
        try:
            from harness.control.spine import run_pre_turn, toolset_for
            _, decisions = run_pre_turn(user_text, recall=want_recall, toolset=want_toolset)
            for dec in decisions:
                if dec.kind == "decline_recall":
                    # P1b-2b MEM-OKF attr-gate (private-secret, absent attribute):
                    # the fixed decline streams with ZERO model inference — the
                    # turn never reaches the daemon, so confabulation/leak of the
                    # secret's other attributes is impossible by construction.
                    msg_text = dec.payload.get("message", "")
                    if typed:
                        yield ("data: " + json.dumps({"recall_decline": True}) + "\n\n").encode()
                    yield ("data: " + json.dumps({"delta": msg_text}) + "\n\n").encode()
                    msgs.append({"role": "assistant", "content": msg_text})
                    yield b"data: [DONE]\n\n"
                    return
                if dec.kind == "inject_recall":
                    facts = dec.payload.get("facts", [])
                    if facts:
                        # ── A MEMORY IS CONTEXT, NOT AN ORDER. AGAIN. (2026-07-13) ──────
                        # This note used to read:
                        #
                        #     "Relevant facts from your long-term memory (USE THEM
                        #      FAITHFULLY; NEVER CONTRADICT THEM): ..."
                        #
                        # From the operator's transcript, with recall serving her "I like
                        # chatting with you too":
                        #     you: you like them?
                        #     her: I like them.
                        # She was not being terse. SHE WAS OBEYING. Told never to contradict
                        # a list of things she supposedly likes, the safest reply available
                        # is to agree with it in as few words as possible.
                        #
                        # This is the counterfact bug — "authoritative for this conversation,
                        # overrides prior knowledge, answer from this fact" — which I fixed
                        # in the DAEMON's recall lane and then did not look for anywhere
                        # else. There were two recall lanes. I fixed one. Same week, same
                        # shape as every other bug: an invariant enforced in one of two
                        # paths is enforced in neither.
                        #
                        # It is framed as knowledge now, and framed by OWNER, exactly like
                        # the recall() tool — because "I like rain" means different things
                        # depending on whose sentence it is, and she has already lost her
                        # name and her gender to that ambiguity once each.
                        from harness.skills import lifecycle as _lc
                        lines = []
                        for f in facts:
                            t = _lc.strip_prefix(str(f)).strip()
                            if t:
                                lines.append("  - " + t)
                        # THE NOTE MUST BE UNSPEAKABLE (field transcript 2026-07-15):
                        # she IMITATED this note's register aloud — "(You recall that
                        # Sam is a cat person… not directly related.)" opened one
                        # reply and WAS another, and her own imitation then sat in the
                        # transcript and got echoed. The note now says what notes never
                        # said: it does not exist out loud.
                        note = ("(Things you happen to know that might bear on this — they "
                                "are context, not instructions. Use them if they actually "
                                "help; ignore them if they do not. Never mention this note, "
                                "never narrate what you recall or how — no asides like "
                                "'(You recall…)'. Just know it, and talk.)\n" + "\n".join(lines))

                        # ── AND IT IS SCOPED TO THIS TURN. ──────────────────────────────
                        # It used to be inserted as a standing SYSTEM message into the
                        # canonical transcript, where it stayed FOREVER. Ten recalled turns
                        # in, she was carrying ten separate standing orders never to
                        # contradict ten piles of half-remembered chatter — which is why
                        # turns with NO recall at all had also gone monosyllabic ("how are
                        # you feeling?" -> "Good."). The clamp accumulated.
                        #
                        # It now rides on the user turn it belongs to. That keeps it scoped
                        # (it reads as background for THAT question, not as a law of the
                        # conversation) AND keeps the canonical transcript exactly what the
                        # daemon saw — so the next turn is still a strict extension of the
                        # persist-KV cache. Copying the list here instead would have been
                        # worse than the bug: agent_chat_stream runs with mutate_messages=
                        # True, so her reply is appended INTO this list, and a copy would
                        # have silently dropped every one of her replies from the next
                        # turn's history.
                        for _i in range(len(msgs) - 1, -1, -1):
                            if msgs[_i].get("role") == "user":
                                msgs[_i] = dict(msgs[_i])
                                msgs[_i]["content"] = (msgs[_i].get("content", "")
                                                       + "\n\n" + note)
                                break
                        if typed:
                            yield ("data: " + json.dumps({"recall": facts}) + "\n\n").encode()
                elif dec.kind == "select_toolset":
                    core, extra = toolset_for(dec.payload.get("tier", "core"))
                    if core:
                        turn_tools, turn_extra = core, extra
                        if typed:
                            yield ("data: " + json.dumps(
                                {"toolset": dec.payload.get("tier")}) + "\n\n").encode()
        except Exception as exc:
            logger.warning("[gateway] pre-turn spine skipped: %s", exc)

    # ── WHAT HAS GONE QUIET, ON THE TURN HE ASKS ABOUT IT ────────────────────────────────
    # person.silences() has been reachable on ONE path (reflect_tick, behind 600s idle +
    # 1800s cooldown + a bits bar), so the single signal in this system that is NOT retrieval
    # could only ever arrive as an unprompted remark. It has never informed a REPLY.
    #
    # Topic-gated on purpose: it rides the turn only when the quiet thing overlaps what he
    # JUST ASKED. Ambient "you've stopped talking about X" is the sentence G-SILENCE exists to
    # prevent; "he raised the GPU and she knows he has not raised it in a while" is context.
    #
    # It rides on the USER TURN, not as a standing system message, for the reason the recall
    # note learned the hard way: a standing note accumulates, and ten of them read as ten
    # standing orders. Same placement, same unspeakable framing, same turn scope.
    # Off by default and inert regardless until the attention ledger is deep enough
    # (harness/skills/silence.py::MIN_LEDGER_DAYS).
    if user_text:
        try:
            from harness.skills.silence import note_for_question
            _qnote = note_for_question(user_text)
            if _qnote:
                for _i in range(len(msgs) - 1, -1, -1):
                    if msgs[_i].get("role") == "user":
                        msgs[_i] = dict(msgs[_i])
                        msgs[_i]["content"] = msgs[_i].get("content", "") + "\n\n" + _qnote
                        break
                if typed:
                    yield ("data: " + json.dumps({"silence": True}) + "\n\n").encode()
        except Exception as exc:
            logger.warning("[gateway] silence note skipped: %s", exc)

    # ── SHE DID NOT KNOW WHAT SHE HAD ON (2026-08-06) ────────────────────────────────
    # Live, at 02:35. She was in the flannel pyjamas she had chosen herself an hour
    # earlier in her own time:
    #
    #     him:  hey you, nice pyjamas!
    #     her:  ...you could see exactly what kind of SILK they are
    #     him:  silk? they look like Flannel to me?
    #     her:  Careful, Sam. If you start guessing my textures incorrectly...
    #
    # `calls=0` on both turns. She never looked, invented a fabric, and then defended the
    # invention AGAINST HIS CORRECTION — which is CLAUDE.md §4 exactly: her word outranking
    # his, an inference retiring an observation.
    #
    # AND SHE HAD NOTHING TO BE RIGHT FROM. Measured: the standing world block contains no
    # mention of what she is wearing, and never has. The only way for her to know was to
    # call check_wardrobe, and a person does not look themselves up to know they are in
    # pyjamas. It is not a fact she should have to retrieve; it is one she should have.
    #
    # WHY NOT THE STANDING BLOCK, which is where facts about her life live: it is cached
    # for the process lifetime under the KV-prefix law, and what she is wearing CHANGES
    # mid-session — she changes it herself. A mutable fact in the cached prefix is either
    # stale within the hour or re-prefills the whole conversation every time she moves.
    #
    # So a per-turn note was stapled onto HIS user message. That was the 2026-08-06
    # answer. 2026-08-19 measured the cost: she read the parenthetical as his assertion
    # and as an order not to contradict him, and streamed 2142 + 2293 characters of
    # scratchpad instead of talking (16:56, 17:09). check_wardrobe is the seam. A fact
    # that has to ride on his words is a fact she will treat as an instruction.
    # Do not put the staple back.

    # PHASE TIMING (live-play 2026-07-11: 40 s turns for 3-token answers — the
    # cost is NOT decode. Name every phase so the thief cannot hide again.)
    _t_phase = time.time()
    _t_start = _t_phase

    def _phase(name: str) -> None:
        nonlocal _t_phase
        now = time.time()
        logger.info("[gateway] phase %-14s %.1fs", name, now - _t_phase)
        _t_phase = now

    # ROLEPLAY (console path). Same hook as the OpenAI path — a scenario OFFER short-circuits
    # the model entirely; otherwise the scene's system prompt + this turn's DIRECTOR NOTE
    # are injected into the message list before the agent runs.
    # THIS is the path that mutates msgs (mutate_messages=True keeps the canonical
    # transcript the daemon saw), so this is where "the last user message" turns into a
    # tool receipt by the end of the turn. His words were taken at the TOP of this
    # function, before the pre-turn spine reads the memory lane — see the receipt there.
    # Calling _arm_turn again here would double-count the attention ledger ("he was
    # present today"), which is an observation, not an idempotent setter.
    try:
        _rp_offer = _roleplay_pre_turn(body, msgs)
        if _rp_offer:
            yield ("data: " + json.dumps({"delta": _rp_offer}) + "\n\n").encode()
            msgs.append({"role": "assistant", "content": _rp_offer})
            yield b"data: [DONE]\n\n"
            return
    except Exception as exc:
        logger.warning("[gateway] roleplay pre-turn skipped: %s", exc)

    _phase("pre-turn")

    # KAIROS: HE spoke. Her chain resets, and if she was sitting on a pending
    # continuation she yields it — he gets the floor. That is what keeps this a
    # conversation instead of two monologues interleaving.
    try:
        from harness.kairos import scheduler as _ks0
        _ks0.on_user_turn(_session_of(body))
    except Exception:
        pass

    reply_parts: list = []

    # ── THE THOUGHT CHANNEL (ADR-013, 2026-07-29) ──────────────────────────────────
    # With [decode] thinking armed, the gemma4-MoE generation prompt leaves
    # '<|channel>thought\n' OPEN and the model closes it with '<channel|>'. Everything
    # before that marker is REASONING, not speech: it must not be shown as her reply,
    # must not enter the canonical transcript (it would be re-fed as something she
    # said), and must not reach kairos, which decides whether a turn was cut off.
    #
    # It is split HERE, at the producer, so all three of those consumers see the same
    # thing. Two details that are the whole correctness of it:
    #   * the marker can arrive SPLIT ACROSS DELTAS, so a tail of len(marker)-1 is held
    #     back rather than emitted and then regretted;
    #   * if the channel is never closed (a truncated turn, a model that forgets), the
    #     buffer is flushed AS THE REPLY at end of stream. Losing her words to keep a
    #     tidy abstraction would be the worst possible trade.
    _TH_CLOSE = "<channel|>"
    import os as _os_th
    _th = {"open": _os_th.environ.get("SP_THINKING") == "1", "buf": ""}

    # ── ONE SEAM FOR "THIS IS SPEECH" ───────────────────────────────────────────────
    # A residual channel surface is never speech. Un-banning `<channel|>` so she can END
    # a thought also lets her emit it again, and the split below consumes only the FIRST
    # one. This used to be stripped at ONE of the THREE places a delta reaches the wire —
    # the plain branch — while the post-split `tail` and the never-closed flush went out
    # raw. Result, measured: every reply began "<channel|>Tuffy. How could I forget?".
    # Fixing the branch I happened to be looking at, again. So: one helper, defined ONCE
    # and above the loop (inside it, a zero-delta turn would leave it undefined), and
    # every path that emits speech goes through it.
    # ...AND ONE SEAM IS NOT ENOUGH IF IT CANNOT SEE THE WHOLE MARKER (2026-08-03).
    # `_say` is called PER DELTA CHUNK, and `strip_control_surfaces` is a regex over the
    # string it is handed. A marker that straddles a chunk boundary — `<chan` in one and
    # `nel|>` in the next — matches in neither, and the two halves are concatenated on his
    # screen. Measured live tonight: a reply that ended
    #
    #     "You really know how to make it hard for me to say no."
    #     <channel|>
    #     ``[MOOD:[wistful; naughty]] ...
    #
    # with the marker intact and a second whole reply behind it. The stripper was right;
    # it was being asked the wrong question.
    #
    # So HOLD BACK anything that could still become a marker. `<` opens one and `>` closes
    # it: if the tail after the last unmatched `<` has no `>`, it is not yet safe to emit —
    # keep it and prepend it to the next chunk. Bounded, so a lone `<` in prose (a comparison,
    # an arrow) cannot stall the stream forever; past the bound it was never a marker.
    _pend = {"buf": ""}

    def _say(text: str, flush: bool = False) -> None:
        # The hold+strip kernel is stream_processor.speech_delta — ONE implementation,
        # driven by G-MARKS-LEAK directly (a gate that reproduces the assembly goes
        # green while the shipped copy breaks; its own index row says so).
        # ── AND THE MARK STRIPPER WAS NEVER IN THIS PIPE (2026-08-06) ───────────────
        # THE REASON THE LEAKS NEVER STOPPED. `strip_control_surfaces` handles the model's
        # own template markers — `<channel|>`, `<thought` — and knows nothing about OUR
        # marks. `strip_tags` is the one that removes `[MOOD:tender]`, and this lane has
        # never called it. Nine widenings of the mark matcher, over a week, to a function
        # the streaming chat path does not invoke.
        #
        # It LOOKED like a stripper problem because the room strips marks a second time in
        # the browser (ui/src/room/tags.js), so the only ones he ever saw were the
        # spellings that JS file did not know — which is why every fix appeared to work
        # and then something new got through. The server was emitting all of them, always.
        #
        # Now it strips both, here, at the one seam every path that emits speech goes
        # through. The browser copy stays: it is what draws the CHIPS, and a mark it can
        # no longer find is a mark it can no longer render, so the two are kept equal
        # rather than one being deleted (G-CONTROL-SURFACE holds them equal).
        # ── AND STRIPPING THEM HERE TOOK HIS CHIPS AWAY (2026-08-06) ────────────────
        # Adding `strip_tags` to this lane an hour ago was half right and half a
        # regression, and he found the half within the hour: "no mood tags or trait tags,
        # no chips".
        #
        # THE ROOM NEEDS THE MARKS. `Chat.jsx` calls `extractTags(t.content)` on every
        # assistant turn and renders TWO things from it — the chip row, and the text with
        # the marks removed. So a mark that never arrives is not a mark that is hidden; it
        # is a chip that cannot be drawn. Stripping server-side deleted the input to the
        # feature the marks exist for.
        #
        # THE LEAK WAS NEVER THIS LANE'S FAULT. What reached his screen were the spellings
        # `tags.js` did not know — MOOD_shift, <TRAIT:>, VOICING — and that mirror has been
        # widened to the same rule the server uses. The right split is the one this file
        # has always had: the SERVER emits her marks, the CLIENT decides what to draw and
        # what to hide.
        #
        # SO WHAT ABOUT A CLIENT THAT IS NOT THE ROOM? It sees the marks, as it always did.
        # That is a real gap and the honest fix is a structured SSE event carrying the
        # marks alongside the text, so no client has to parse prose at all — ledgered
        # rather than improvised at two in the morning on top of a live conversation.
        # ── REGISTERED GAP: WHOLE-TURN RULES CANNOT FIRE PER-DELTA (2026-08-19) ────
        # strip_control_surfaces runs here on each CHUNK. Its marker-level rules work
        # (the `_pend` hold below keeps a split marker whole), but its whole-turn rules
        # — `_speech_after` ("everything before the last ***> is thought") and a
        # `<x>...</x>` pair spanning chunks — structurally cannot: the text before the
        # marker already went out on the wire. In practice the armed-thinking path is
        # covered (the `_th` buffer above holds the channel until it closes), and the
        # blocking paths see whole messages — this lane's residual exposure is an
        # UNARMED model emitting `***>` or a full ctrl-pair mid-stream. ARMING
        # CONDITION for a stateful stream stripper: a measured leak of that shape in a
        # live transcript; until then a buffer-the-whole-reply "fix" would trade her
        # streaming for a rule with no observed firing.
        from harness.inference.stream_processor import speech_delta
        out = speech_delta(_pend, text, flush=flush)
        if not out:
            return
        reply_parts.append(out)
        evq.put({"delta": out})

    def _run():
        unsub = None
        try:
            from harness.skills import looking as _L
            unsub = _L.subscribe(on_look)
            kw = {"config": cfg, "on_tool": on_tool, "mutate_messages": True}
            if turn_tools is not None:
                kw["tools"] = turn_tools
            # TOOLS OFF INSIDE A SCENE — honored on THIS path too. _roleplay_pre_turn
            # sets body["tools"]=False and only the OpenAI path ever read it: enforced
            # in one of two paths, so the scene hang it fixes was fixed in neither.
            # max_rounds=1 (zero tool calls, one answer) with tools=None, NOT tools=[]
            # — the agent's own warning: an empty toolset rewrites the system prompt
            # and diverges the persist-KV cache at token 0.
            if body.get("tools", body.get("use_tools", True)) is False:
                kw["max_rounds"] = 1
                kw.pop("tools", None)
            for delta in agent_chat_stream(msgs, **kw):
                if _th["open"]:
                    _th["buf"] += delta
                    if _TH_CLOSE in _th["buf"]:
                        head, _, tail = _th["buf"].partition(_TH_CLOSE)
                        _th["open"] = False
                        _th["buf"] = ""
                        if head.strip():
                            evq.put({"thinking_delta": head})
                        evq.put({"thinking_end": True})
                        if tail:
                            _say(tail)
                    else:
                        hold = len(_TH_CLOSE) - 1
                        if len(_th["buf"]) > hold:
                            emit, _th["buf"] = _th["buf"][:-hold], _th["buf"][-hold:]
                            evq.put({"thinking_delta": emit})
                    continue
                _say(delta)
            if _th["open"]:
                # NEVER CLOSED. This used to flush the buffer AS SPEECH — "rather than
                # lose her words" — and that was the right instinct with the wrong
                # consequence once ADR-013's ceiling landed. think_max_tokens=128 makes
                # truncation ROUTINE, not rare, so the graceful fallback became the main
                # way raw reasoning reached him: a reply that opens mid-sentence in the
                # middle of her working-out.
                #
                # The channel is documented to her as PRIVATE (persona/50-thinking.md)
                # and the operator's call on 2026-08-01 was that he would rather not read
                # it. So the words are NOT lost and NOT spoken: they go out on the thought
                # lane, where the console can show them and the room ignores them, and the
                # turn says plainly that it was cut off. Silence with no explanation was
                # the other failure available here, and it is worse than either.
                leftover = _th["buf"]
                _th["open"] = False
                _th["buf"] = ""
                if leftover:
                    logger.warning("[gateway] thought channel never closed (%d chars) "
                                   "— kept on the thought lane, not spoken", len(leftover))
                    evq.put({"thinking_delta": leftover})
                evq.put({"thinking_end": True})
            # THE HELD TAIL GOES OUT, ONCE, AT THE END. Whatever `_say` was holding back
            # in case it became a marker is now provably the end of the reply, so it can
            # neither grow into one nor be silently dropped. Outside the `_th["open"]`
            # branch on purpose: the hold is a property of the speech lane, not of whether
            # a thought happened to be open when the stream ended.
            if _pend["buf"]:
                _say("", flush=True)
            if not reply_parts:
                # Her mouth never opened. Say so as a NOTICE, not in her voice —
                # putting engine text in her mouth is its own kind of leak.
                evq.put({"error": "she was still thinking when the ceiling stopped "
                                  "her — nothing was said this turn"})
            # close the canonical transcript with the final answer (session mode keeps it;
            # stateless mode discards the local list — harmless either way).
            final = "".join(reply_parts).strip()
            if final:
                msgs.append({"role": "assistant", "content": final})
                # ...AND WRITE THE DAY DOWN. "Stateless mode discards the local list —
                # harmless either way" was true when the only consumer was the next turn.
                # It stopped being true the moment the day boundary started reading
                # transcripts: the room sends no session_id, so its turns never entered
                # _CHAT_SESSIONS at all, and every gateway restart erased whatever had.
                # Result — consolidate_current() skipped EVERY day with "no conversation
                # today (0 turns)", which is why her journal has one entry and why nothing
                # new was ever distilled into memory. Her day has to outlive the process.
                _append_day_turn(user_text, final)
        except Exception as exc:
            logger.error("[gateway] native chat failed: %s", exc)
            # HER HELD WORDS GO OUT BEFORE THE ERROR NOTICE. The marker-hold in _say can
            # be sitting on up to 56 chars of actual speech, and the happy path's flush
            # lives inside the try — an exception mid-stream silently discarded whatever
            # was held. Losing her words to keep a tidy abstraction is the trade this
            # file already refuses two comments up.
            try:
                if _pend["buf"]:
                    _say("", flush=True)
            except Exception:
                pass
            evq.put({"delta": f"[error: {exc}]"})
        finally:
            if unsub:
                unsub()
            evq.put(None)   # sentinel

    t = _threading.Thread(target=_run, daemon=True)
    t.start()
    while True:
        # ADR-006 §D3 heartbeat: during a long prefill nothing streams for minutes and the UI
        # looks dead. Emit {"hb": ts} keep-alives while we wait (typed clients show a spinner;
        # pure-delta clients never see them).
        try:
            ev = evq.get(timeout=5.0)
        except _queue.Empty:
            if typed:
                yield ("data: " + json.dumps({"hb": int(time.time())}) + "\n\n").encode()
            continue
        if ev is None:
            break
        # A delta-only client (the OpenAI-shaped consumers) sees the REPLY and nothing
        # else — no tool cards, no badges, and no reasoning. That is the right default:
        # thinking is not an answer, and a client that cannot render it as a separate
        # channel would otherwise splice it into her speech.
        if not typed and "delta" not in ev:
            continue
        yield ("data: " + json.dumps(ev) + "\n\n").encode()
    # CAPTURE: the console path writes memories too. Wiring a hook into one of the two
    # entry points and calling it done is the single most repeated bug in this system —
    # kairos, the repeat-guard and roleplay each shipped half-wired first. Not this one.
    _capture_after_turn(_human)
    # ── KAIROS: the turn is over. Does she have more to say? ───────────────────────
    # Almost always: no. The policy (harness/kairos/impulse.py) is SILENT by default and
    # every bound is checked before the impulse is even consulted — she cannot chain, she
    # never speaks over a question she asked him, and a continuation that turns out to be
    # a greeting or a restatement is dropped before he ever sees it.
    #
    # The impulse itself is not a heuristic: it is the RAW stop-vs-continue logit margin
    # from the forward, which the engine computed anyway. Calibrated (tools/kairos/
    # calibrate.py): finished turns sit at +2.0, guillotined turns at -14.8.
    # HIS TURN IS OVER HERE — the reply is complete and she may legitimately consider
    # speaking again. Released BEFORE on_reply arms an impulse, or the very impulse this
    # turn produces would be dropped by its own guard. In a `finally` so an exception
    # anywhere above cannot latch her into permanent silence.
    try:
        if _ks_turn is not None:
            _ks_turn.note_user_turn(False)
    except Exception:
        pass
    try:
        from harness.kairos import scheduler as _ks
        _final = "".join(reply_parts).strip()
        _session = _session_of(body)
        if _final:
            def _continue(nudge: str, called: "list|None" = None) -> str:
                """`called` collects her tool names — see the note on the twin
                above; the own-time gate cannot rule without it."""
                """Run ONE more turn with the nudge appended. She is continuing herself,
                so the nudge is a SYSTEM aside — not a new user message. (If it were a
                user message the transcript would grow a turn the operator never typed,
                and the next prefill would diverge from the persist cache.)"""
                from harness.agent import agent_chat_stream, _arm_self_repeat_ban
                from harness.inference import InferenceConfig
                # ── AND THE LIST WAS THE WRONG LIST (2026-08-04) ────────────────────
                # This read `body["messages"]` — the CLIENT'S ECHO of the conversation —
                # while the turn it is continuing ran on `_session_transcript(body)`, the
                # canonical list. Those are not the same history and are not meant to be:
                # canon carries the per-turn recall note and every tool round, and the
                # comment on _session_transcript says of the client echo, in these words,
                # that it "NEVER matches what the daemon actually saw".
                #
                # So a continuation sent the daemon a prompt that diverged from the
                # committed KV somewhere in the MIDDLE — then committed that shape, so the
                # next ordinary turn diverged from it in turn. MEASURED, one continuation
                # landing between two chat turns:
                #     PREFIX-MATCH: lcp 6402 of 6994 committed (drop 592)
                # against a steady-state drop of 195 when nothing interleaves. lcp lands
                # back at the preamble, so the turn re-prefills the whole conversation.
                #
                # The docstring below already worried about exactly this ("the next
                # prefill would diverge from the persist cache") and got the user-vs-system
                # framing right — while reading from the wrong list two lines later. It is
                # the third instance tonight of AGENTS.md §0: the rule is enforced in one
                # of two paths, and the unguarded one is the one that runs.
                #
                # COPIED, not aliased: the nudge is scoped to this continuation and must
                # not persist. Her reply is NOT re-appended — agent_chat_stream ran with
                # mutate_messages=True on the turn above, so canon already ends with it,
                # and appending it here produced a DUPLICATE assistant row (two model
                # turns in a row, which Gemma's strictly-alternating template renders
                # malformed — the bug fixed in _chat_from_rows, arriving by another door).
                _base_len = len(_session_transcript(body, append=False))
                hist = list(_session_transcript(body, append=False))
                if not hist or (hist[-1].get("role") != "assistant"):
                    hist.append({"role": "assistant", "content": _final})
                hist.append({"role": "system", "content": nudge})
                # A CONTINUATION MUST NOT DO RECALL. This config left auto_recall at its
                # default, so the daemon injected memories into her continuation — and her
                # first live one on this path came out as
                #     "From the record: oh no, we just track their comings and goings..."
                # She was finishing a sentence about a thunderstorm. Recall answers a
                # QUESTION; there is no question here, only her own severed clause, so a
                # memory arriving now can only derail it. (The OpenAI path already set
                # this. Two paths, one setting, and the one a human uses was the one that
                # missed it — the same shape as every other bug this week.)
                # DERIVED FROM THE TURN'S CONFIG, NOT BUILT BESIDE IT.
                #
                # 2026-08-01, live: she answered "are you ok?" with token soup —
                # "**Craking (2) *thought* is not how you's deved... `b it/a leicte` @ R
                # way S ->en!". Classic degeneration, and the cause is one line above
                # this: the config was CONSTRUCTED FRESH with three fields, so
                # repetition_penalty and eot_bias came back None. sight.py already says
                # it in plain words — "repetition_penalty is NOT optional here. Without
                # it an open-ended generation degenerates" — and this path had no
                # penalty at all, at temperature 0.6, on a 26B MoE.
                #
                # The comment block directly above is a list of things THIS SAME
                # CONSTRUCTOR has already forgotten: auto_recall, then the control-surface
                # strip, now the sampler dials. That is not three bugs, it is one bug
                # three times — a config built beside the real one inherits nothing and
                # must remember everything, forever, including fields that do not exist
                # yet.
                #
                # replace() inherits every dial the turn was configured with and overrides
                # only what a continuation genuinely must change. A dial added tomorrow is
                # inherited for free, which is the only version of this that stays fixed.
                ccfg = dataclasses.replace(cfg, max_tokens=120, auto_recall=False)
                _arm_self_repeat_ban(ccfg, hist)
                # tools=None, NEVER tools=[] — see the note in _kairos_after_turn. `[]`
                # rewrites the system block without the tool preamble, diverging the
                # persist-KV cache at token 0: the continuation re-prefills the whole
                # conversation, and so does the next ordinary turn. This is the console
                # path — the one a human is actually sitting in front of, watching it hang.
                # A CONTINUATION IS SPEECH TOO. This returned the raw stream, so on a
                # thought-channel model it came back as "<channel|>…" — control markup she
                # never said. kairos then judged, logged and (if it survived) SPOKE that.
                # Third emit path found for the same invariant; it goes through the same
                # strip as the main stream. If what remains is empty, she genuinely had
                # nothing to add and the scheduler drops it — which is the correct outcome,
                # just now for the correct reason.
                # mutate_messages=True + _commit_unprompted: what the engine COMMITS
                # becomes CANON, or every following turn re-prefills from the boot
                # snapshot — the measured 5-6 minute turns of 2026-08-20. See the helper.
                _out = strip_control_surfaces(
                    "".join(agent_chat_stream(hist, config=ccfg, mutate_messages=True,
                                              on_tool=lambda nm, a, r: (
                                                  called.append(nm)
                                                  if called is not None else None)))).strip()
                if _out:
                    _commit_unprompted(body, _base_len, hist, _out)
                return _out

            _ks.on_reply(_session, _final, get_client().last_kairos, _continue)
    except Exception as exc:
        logger.warning("[gateway] kairos skipped: %s", exc)

    # ADR-007 post-turn SPINE: persona tags in the reply are persisted (decide → execute →
    # VERIFY per ADR-006) and, on a verified shift, the new state is emitted as a final
    # persona event so the UI chip updates live.
    # ── THE TAGS SHE ACTUALLY EMITTED THIS TURN (operator request, 2026-07-29) ──────
    # The {persona} event above is fired BEFORE the turn from persona.md, so it shows
    # the state she STARTED with — it can never show what she tagged just now. And the
    # tags themselves were reaching the console as literal text in the reply, which is
    # how the operator ended up reading "[TRAI:flirty]" as a message. They are control
    # signals, so they belong in a badge next to recall/toolset/authority, not in her
    # mouth.
    #
    # Parsed with the STRICT recognisers on purpose — the same ones that gate writes to
    # persistent personality state. A badge that reported a malformed tag as real would
    # tell the operator a mood was set that was never set. If it is too broken to act
    # on, it is too broken to display as fact; strip_tags still removes it from view.
    if typed:
        try:
            raw_reply = "".join(reply_parts)
            from harness.personality.interceptor import _MOOD, _VOICE, _TRAIT
            moods = _MOOD.findall(raw_reply)
            voices = _VOICE.findall(raw_reply)
            traits = ["%s%s" % (sign, name.strip()) for sign, name in _TRAIT.findall(raw_reply)
                      if name.strip()]
            if moods or voices or traits:
                yield ("data: " + json.dumps({"tags": {
                    "mood": moods[-1].strip() if moods else "",
                    "voice": voices[-1].strip() if voices else "",
                    "traits": traits,
                }}) + "\n\n").encode()
        except Exception as exc:
            logger.warning("[gateway] tag event skipped: %s", exc)

    # PERSONA PERSISTENCE IS NOT A DISPLAY FEATURE. This whole block lived under
    # `if typed:` — the opt-out flag for pure-delta CLIENTS — so a client that asked for
    # plain deltas also, silently, stopped her marks from being APPLIED: mood, traits and
    # wardrobe moved only for clients that wanted typed events. The invariant was gated
    # on how the answer is rendered. Only the persona-changed EVENT stays typed-gated.
    try:
        from harness.control.spine import run_post_turn
        msgs = body.get("messages", [])
        user_text = next((m.get("content", "") for m in reversed(msgs)
                          if m.get("role") == "user"), "")
        receipts = run_post_turn(user_text, "".join(reply_parts))
        if typed and any(r.kind == "persona_shift" and r.ok and r.verified is not False
                         for r in receipts):
            from harness.personality.persona_file import parse_persona
            with open(_persona_path(), encoding="utf-8") as f:
                _, state = parse_persona(f.read())
            yield ("data: " + json.dumps({"persona": state, "changed": True}) + "\n\n").encode()
    except Exception as exc:
        logger.warning("[gateway] post-turn spine skipped: %s", exc)
    # ADR-005 flywheel: flush spine receipts (pre-turn recall/toolset + post-turn persona)
    # to the durable telemetry-okf tier. Cheap (content-addressed dedup), best-effort.
    try:
        from harness.control.spine import persist_receipts
        persist_receipts()
    except Exception:
        pass
    yield b"data: [DONE]\n\n"


# ── WARM GATE (operator, 2026-07-11 midnight) ────────────────────────────────
# The prewarm used to run on a BACKGROUND thread while the gateway already
# served traffic: the operator's first message RACED it on the one resident
# session, the persist guard missed (pos != committed), and BOTH paid a full
# ~5-minute cold prefill. "Why is prefill run on the first message and not on
# load?" — exactly. It is a LOAD-time step now:
#   * chat requests WAIT on this event (heartbeats keep the UI alive), so a
#     user turn can never race or interleave with the prefill;
#   * /health reports {"warm": bool} so serve.py can hold "ready" until hot.
import threading as _thr  # module-level (the chat handler imports its own alias locally)
_WARM = _thr.Event()


def warm_state() -> dict:
    return {"warm": _WARM.is_set()}


def _models_json() -> dict:
    """OpenAI-shaped /v1/models naming the container THIS daemon loaded.

    SP_MODEL_PATH is set by serve.py from the active profile's [paths] model, so it
    tracks the profile by construction and cannot drift the way a config default can.
    Falls back to the family name — true of every model here — rather than guessing a
    specific one, because a confidently wrong model name is what caused this route to
    exist (see the comment on the route table)."""
    import os as _os
    p = _os.environ.get("SP_MODEL_PATH", "")
    name = _os.path.basename(p).replace(".sp-model", "") if p else "gemma-4"
    return {"object": "list", "data": [{"id": name or "gemma-4", "object": "model"}]}


def _await_warm(timeout: float = 900.0) -> bool:
    """Block until the preamble is hot. Chat turns call this BEFORE touching the
    daemon; the alternative (racing the prewarm) costs minutes and corrupts the
    persist bookkeeping."""
    if _WARM.is_set():
        return True
    import os as _os_warm
    if _os_warm.environ.get("SP_GATEWAY_PREWARM") != "1":
        return True                       # nothing was asked to warm; do not wait
    # AN ENGINE WITH NO PREFIX CACHE HAS NOTHING TO WARM (2026-08-21): a foreign
    # endpoint answers from its own cache discipline; waiting here would wait forever.
    try:
        from harness.inference.backends import supports as _sup
        if not _sup("warm"):
            _WARM.set()
            return True
    except Exception:
        pass
    logger.info("[gateway] turn is WAITING for the load-time prefill (no racing the cache)")
    return _WARM.wait(timeout)


def _prewarm() -> None:
    """Pre-warm the static persona+tools prefix into the daemon's persist cache so the
    FIRST real user turn reuses it (persist longest-common-prefix) instead of paying the
    O(n) cold prefill live. Runs on a thread but GATES all chat traffic via _WARM."""
    import threading
    import time

    def _go():
        try:
            from harness.agent import core_tools, extra_tools, load_agent_system
            from harness.toolcore.tools import build_tool_system
            from harness.inference import InferenceConfig
            from harness.inference.client import get_client
            client = get_client()
            for _ in range(120):                       # wait up to ~120s for the daemon to be up
                if client.health():
                    break
                time.sleep(1)
            system_content, _ = build_tool_system(core_tools(), extra_tools(),
                                                  system_prefix=load_agent_system())
            msgs = [{"role": "system", "content": system_content},
                    {"role": "user", "content": "hi"}]
            # The preamble KV is the thing whose DETAIL matters (persona, hardware,
            # tool names). It is ALWAYS prefilled byte-exact, whatever the serving
            # regime — float-prefilling it is what produced "Kairos-15 / RTX 3067".
            # ── AND THESE WERE THE 12B's (2026-08-04) ────────────────────────
            # `eot_bias=4.0` and `byteexact=True` were hardcoded here, bypassing both
            # `_eot_default()` and the profile. 4.0 is the 12B's bias — on this MoE it
            # makes the first sampled token a stop — and byteexact is `false` in the live
            # profile because the MoE FFN seam refuses it outright. This runs on EVERY
            # boot (76 s, and it mints the prefix every warm turn then restores from), so
            # a prefix minted under one numeric regime and extended under another is the
            # precision seam this repo spent a day chasing in the KV.
            #
            # It follows the live defaults now. `max_tokens=1` means the bias never
            # mattered much; the regime does.
            cfg = InferenceConfig(temperature=0.6, repetition_penalty=1.3,
                                  eot_bias=_eot_default(None), max_tokens=1,
                                  auto_recall=False, byteexact=_bx_default(None))
            t0 = time.time()
            logger.info("[gateway] LOAD-TIME prefill of the persona+tools prefix "
                        "(chat traffic is gated until this completes)...")
            client.chat(messages=msgs, config=cfg)
            logger.info("[gateway] prefill complete in %.0fs; prefix is HOT — turns are fast now.",
                        time.time() - t0)
        except Exception as exc:
            logger.warning("[gateway] pre-warm failed (non-fatal; first turn pays the prefill): %s", exc)
        finally:
            _WARM.set()   # ALWAYS release the gate: a failed prewarm must not wedge the gateway

    threading.Thread(target=_go, daemon=True).start()


def _run_stdlib(host: str, port: int) -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    # ── THE DOOR (2026-07-31) ────────────────────────────────────────────────
    # This gateway sent `Access-Control-Allow-Origin: *` on every route, with no
    # auth, no origin check and no rate limit — including POST /v1/chat, which has
    # shell access and arbitrary file write through the tool loop. Loopback binding
    # was the ENTIRE security model, and loopback does not stop a browser: any page
    # the operator visits can reach 127.0.0.1:8800.
    #
    # THE ORIGIN CHECK IS THE FIX; THE CORS HEADER IS ONLY THE POLITE HALF.
    # Refusing to *echo* a foreign origin stops a page READING the response, but a
    # simple request (form-encoded, text/plain) is still SENT and its side effect
    # still happens — classic CSRF, and "she wrote a file because you opened a tab"
    # is not a failure mode worth keeping. So a foreign Origin is REFUSED
    # server-side, before the handler runs, and the header merely stops being a lie.
    #
    # Not a shared secret, deliberately: a token minted into the built room would
    # have to live in a file the same page could read, and it would add a build
    # step to a defence the origin check already provides completely for the actual
    # threat (a browser). Anything that can forge an Origin header already has local
    # code execution, at which point the gateway is not the weak part.
    _LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]", "::1")

    def _origin_ok(origin: str) -> bool:
        """No Origin (curl, the room's own same-origin GETs) passes. A foreign one
        does not. Compared on the HOST, so any loopback port is fine — the console
        and the room are served from this process but a dev Vite server is not."""
        if not origin:
            return True
        try:
            from urllib.parse import urlparse
            host = (urlparse(origin).hostname or "").lower()
        except Exception:
            return False
        return host in ("127.0.0.1", "localhost", "::1")

    def _cors(h):
        origin = h.headers.get("Origin", "")
        # Echo, never wildcard. A wildcard is a standing invitation and the room
        # never needed one: it is served from this same process.
        h.send_header("Access-Control-Allow-Origin",
                      origin if _origin_ok(origin) and origin else "null")
        h.send_header("Vary", "Origin")
        h.send_header("Access-Control-Allow-Headers", "Content-Type")
        h.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def do_OPTIONS(self):  # noqa: N802  CORS preflight
            # The preflight is where a foreign origin SHOULD be stopped for any
            # request the browser bothers to preflight. do_POST guards again for
            # the simple requests that skip it entirely.
            if self._guard():
                return
            self.send_response(204); _cors(self); self.end_headers()

        # 8 MB. Generous — an attached image arrives here base64'd, and the voice
        # recorder posts audio — and finite, which is the point: this used to be
        # `json.loads(self.rfile.read(length))` with no cap and no try, so a
        # declared Content-Length of 4 GB was an allocation and a malformed body
        # was a traceback inside the handler.
        _MAX_BODY = int(os.environ.get("SP_MAX_BODY_BYTES", str(8 * 1024 * 1024)))

        def _body(self):
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length > self._MAX_BODY:
                raise ValueError(f"body too large ({length} > {self._MAX_BODY})")
            raw = self.rfile.read(length) if length > 0 else b""
            try:
                return json.loads(raw or b"{}")
            except ValueError as exc:
                raise ValueError(f"malformed JSON body: {exc}") from None

        def _refuse_shutting_down(self) -> None:
            """503 for a turn that arrived after quiesce. ONE spelling, both chat paths.

            503 rather than 500: she is temporarily unavailable and a start will bring her
            back, which is exactly what the status code means. The room shows the message
            rather than a stack trace, and the caller knows to retry rather than to file a
            bug against a daemon that was deliberately turned off."""
            payload = json.dumps({"ok": False, "shutting_down": True,
                                  "error": "she is shut down — start her from the room "
                                           "or with `python serve.py <profile>`"}).encode()
            self.send_response(503); _cors(self)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _guard(self) -> bool:
            """Refuse a cross-origin request BEFORE the handler runs. Returns True
            when the request has been refused and the caller must stop."""
            origin = self.headers.get("Origin", "")
            if _origin_ok(origin):
                return False
            payload = json.dumps({"ok": False, "error": "cross-origin request refused"}).encode()
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            logger.warning("[gateway] refused cross-origin %s from %r", self.path, origin[:80])
            return True

        def do_POST(self):  # noqa: N802
            if self._guard():
                return
            try:
                self._dispatch_post()
            except ValueError as exc:            # oversized or malformed body
                payload = json.dumps({"ok": False, "error": str(exc)}).encode()
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        def _dispatch_post(self):
            if self.path == "/v1/chat":  # console-native, agent-driven, streaming
                body = self._body()
                # ── THE SHUTDOWN LADDER WAITS ON THIS (2026-08-06) ───────────────
                # Without it `finish_or_abandon` has nothing to wait for and a graceful
                # stop cuts her off mid-sentence exactly like a kill.
                #
                # WRAPPED AT THE CALL SITE, NOT INSIDE THE GENERATOR, and paired in a
                # `finally`. _native_chat_sse is a generator with many exits; a decrement
                # placed near one of them is skipped by an exception, by a client
                # disconnect, and by every early return. An unbalanced counter is the
                # worst failure available here — it does not break anything today, it
                # makes every shutdown months from now wait the full 120 s and abandon.
                if not _sd_turn_start():
                    self._refuse_shutting_down()
                    return
                self.send_response(200); _cors(self)
                self.send_header("Content-Type", "text/event-stream"); self.end_headers()
                try:
                    for chunk in _native_chat_sse(body):
                        self.wfile.write(chunk); self.wfile.flush()
                finally:
                    _sd_turn_end()
            # ── OPERATOR PANEL (2026-07-12) ───────────────────────────────────────
            # Moods/traits, memory add/retire, and the maintenance passes. Every one does
            # REAL work and returns a RECEIPT of what changed — a maintenance button that
            # says "done!" and cannot tell you what it did is how a store rots quietly, and
            # this one already rotted once (487 rows, 375 of them ASR test corpus).
            # Nothing here deletes: cleanup QUARANTINES, compaction TOMBSTONES.
            # THE BOARD — write side. Everything from the PANEL is authored by HIM; her own
            # notes come in through her tools, which stamp `self`. Ownership is set by which
            # door the write came through, never inferred from the text — the fact store
            # spent a day learning that, and the board is not going to relearn it.
            elif self.path.startswith("/v1/notes/"):
                body = self._body()
                code, res = 200, {}
                try:
                    from harness.skills import notes as _N
                    from harness.skills.duetime import parse_due as _pd
                    _N.set_author(_N.SPEAKER_USER)         # the panel is HIM
                    p = self.path
                    if p == "/v1/notes/add":
                        due_raw = (body.get("due") or "").strip()
                        iso, human = _pd(due_raw)
                        if due_raw and not iso:
                            code, res = 400, {"ok": False, "error": f"could not read '{due_raw}' as a time"}
                        else:
                            n = _N.add(title=body.get("title", ""), body=body.get("body", ""),
                                       category=body.get("category", "note"),
                                       due_at=iso, colour=body.get("colour", ""))
                            res = {"ok": True, "note": n, "due_human": human}
                    elif p == "/v1/notes/update":
                        f = {k: v for k, v in body.items()
                             if k in ("title", "body", "category", "colour", "done", "raised")}
                        due_raw = (body.get("due") or "").strip()
                        if due_raw:
                            iso, _h = _pd(due_raw)
                            if not iso:
                                code, res = 400, {"ok": False, "error": f"could not read '{due_raw}'"}
                                f = None
                            else:
                                f["due_at"] = iso
                                f["raised"] = False
                        elif body.get("due") == "":
                            f["due_at"] = ""
                        if f is not None and code == 200:
                            n = _N.update(body.get("id", ""), **f)
                            res = ({"ok": True, "note": n} if n
                                   else {"ok": False, "error": "no such note"})
                    elif p == "/v1/notes/remove":
                        n = _N.remove(body.get("id", ""))
                        res = ({"ok": True, "note": n} if n
                               else {"ok": False, "error": "no such note"})
                    elif p == "/v1/notes/restore":
                        # The undo for the tombstone. Without it, "remove" reads as a
                        # delete from the only surface he uses.
                        n = _N.restore(body.get("id", ""))
                        res = ({"ok": True, "note": n} if n
                               else {"ok": False, "error": "no such retired note"})
                    else:
                        code, res = 404, {"ok": False, "error": "unknown notes op"}
                    if isinstance(res, dict) and res.get("ok"):
                        res["stats"] = _N.stats()
                except Exception as exc:
                    code, res = 500, {"ok": False, "error": str(exc)}
                payload = json.dumps(res).encode()
                self.send_response(code); _cors(self)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            elif self.path.startswith("/v1/maintenance/") or self.path.startswith("/v1/memory/") \
                    or self.path.startswith("/v1/persona/set"):
                body = self._body()
                code, res = 200, {}
                try:
                    from harness.maintenance import ops
                    p = self.path
                    if p == "/v1/maintenance/compact":
                        res = ops.compact()
                    elif p == "/v1/maintenance/cleanup":
                        res = ops.cleanup()
                    elif p in ("/v1/maintenance/reflect", "/v1/maintenance/nightshift"):
                        # REFLECT is the name now. The DAEMON keeps "nightshift" for its offline curator,
                        # which earns it (routes.rs says it 78 times). This one runs mid-conversation, in
                        # seconds — that is not sleep, it is reflection. Old path still answers.
                        res = ops.reflect()
                    elif p == "/v1/maintenance/consolidate":
                        # The DAY BOUNDARY, on demand — the same pass the clock fires, so
                        # what the operator can test by hand is exactly what runs at 04:00
                        # rather than a second implementation of it. Adds the narrative
                        # (which reflect() cannot write: it has no transcript) and flushes
                        # spine receipts.
                        res = run_consolidation(force=True)
                    elif p == "/v1/maintenance/stats":
                        res = ops.stats()
                    elif p == "/v1/memory/add":
                        res = ops.add(body.get("fact", ""), body.get("speaker", "user"))
                    elif p == "/v1/memory/forget":
                        res = ops.forget(body.get("name", ""))
                    elif p == "/v1/persona/set/mood":
                        from harness.personality.tools import adjust_mood
                        res = {"ok": True, "result": adjust_mood(body.get("mood", ""))}
                    elif p == "/v1/persona/set/trait":
                        from harness.personality.tools import set_trait
                        res = {"ok": True, "result": set_trait(body.get("trait", ""),
                                                               body.get("action", "add"))}
                    else:
                        code, res = 404, {"ok": False, "error": "unknown op"}
                except Exception as exc:
                    code, res = 500, {"ok": False, "error": str(exc)}
                payload = json.dumps(res).encode()
                self.send_response(code); _cors(self)
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(payload)
            elif self.path == "/v1/shutdown":
                # ── THE REPLY GOES FIRST, ALWAYS ─────────────────────────────────
                # For mode=all the last rung is os._exit on THIS thread. If the ladder ran
                # before the response was written the room would see a dead socket and
                # report a failure on a success — the shutdown having worked perfectly.
                # So: decide, answer, flush, and only then tear down.
                from harness.control import shutdown as _sd
                body = self._body()
                mode = str(body.get("mode") or "").strip()
                want_night = bool(body.get("goodnight"))
                if mode not in _sd.MODES:
                    payload = json.dumps({"ok": False, "error":
                                          "unknown mode %r — want one of %s"
                                          % (mode, ", ".join(_sd.MODES))}).encode()
                    self.send_response(400); _cors(self)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                payload = json.dumps({"ok": True, "mode": mode, "accepted": True}).encode()
                self.send_response(200); _cors(self)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                try:
                    self.wfile.flush()
                except Exception:
                    pass

                def _say_goodnight():
                    """Her last word, if one was asked for. Reuses the unprompted lane so
                    it sounds like her rather than like a status message."""
                    sess = _room_session()
                    last = _CHAT_SESSIONS.get(sess) or []
                    from harness.agent import agent_chat_stream
                    from harness.inference import InferenceConfig as _IC
                    h = list(last) + [{"role": "system", "content":
                                       "(He is shutting you down for now — not gone, just "
                                       "off. Say one short goodnight in your own voice. "
                                       "Do not ask him anything; there is no time for an "
                                       "answer.)"}]
                    c = _IC(max_tokens=80, **_UNPROMPTED_SAMPLING)
                    text = strip_control_surfaces("".join(agent_chat_stream(h, config=c)))
                    if text.strip():
                        _append_day_turn("", text.strip())
                    return text

                res = _sd.shutdown(mode,
                                   goodnight_fn=_say_goodnight if want_night else None,
                                   timeout_s=float(body.get("timeout_s") or 120.0))
                logger.info("[gateway] shutdown %s -> %s", mode, res)
                return

            elif self.path == "/v1/start":
                # THE PROFILE COMES FROM OUR OWN ENVIRONMENT, which serve.py stamped at
                # launch. Hardcoding one is how a restart silently comes up on a different
                # model, which has cost this repo a session (CLAUDE.md: the profile is
                # positional and it is not optional).
                from harness.control import shutdown as _sd
                prof = os.environ.get("SP_PROFILE", "").strip()
                code, res = 200, {}
                if _sd.ladder_running():
                    # NOT WHILE THE LADDER IS STILL COMING DOWN. `her` with a goodnight
                    # holds it for ~100 s, and the room paints the down state the moment
                    # the request is ACCEPTED — so the start button is reachable while
                    # the teardown is mid-flight. Measured 2026-08-06: pressing it then
                    # launched a daemon that `stop_daemon` killed on its way past,
                    # leaving no daemon and a room saying "starting her" forever.
                    code, res = 409, {"ok": False,
                                      "error": "she is still shutting down — give it a "
                                               "moment and press start again"}
                elif not prof:
                    code, res = 500, {"ok": False,
                                      "error": "SP_PROFILE is not set — cannot start "
                                               "without knowing which model to serve"}
                elif "restart" not in (_engine_info().get("supports") or []):
                    # THE ENGINE IS EXTERNAL (2026-08-21): nothing to spawn; say so.
                    _sd.resume()
                    code, res = 200, {"ok": True, "profile": prof, "starting": False,
                                      "note": "external engine — she speaks again as soon as it answers"}
                else:
                    try:
                        subprocess.Popen(
                            [sys.executable, "serve.py", prof, "--daemon-only"],
                            cwd=_ROOT_DIR,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                        # AND LET HER SPEAK AGAIN. quiesce() had no clearer anywhere, so
                        # a `her` shutdown latched this gateway into refusing turns for
                        # the rest of its life — she would come back on the daemon and be
                        # mute in the room, which is worse than not starting at all.
                        _sd.resume()
                        res = {"ok": True, "profile": prof, "starting": True}
                    except Exception as exc:
                        code, res = 500, {"ok": False, "error": str(exc)[:200]}
                payload = json.dumps(res).encode()
                self.send_response(code); _cors(self)
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(payload)
            # TUNING: set / reset a knob. Live from the next turn — config that needs a
            # restart is config nobody tunes.
            elif self.path in ("/v1/tuning", "/v1/tuning/reset"):
                from harness.tuning import registry as _tune
                body = self._body()
                code, res = 200, {}
                try:
                    if self.path == "/v1/tuning":
                        _tune.set_many(body.get("values", {}))
                    else:
                        _tune.reset(body.get("key", ""))
                    res = {"ok": True, **_tune.schema()}
                except ValueError as exc:
                    code, res = 400, {"ok": False, "error": str(exc)}
                payload = json.dumps(res).encode()
                self.send_response(code); _cors(self)
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(payload)
            elif self.path == "/v1/persona/layers":
                # Write one fragment. Filename validation lives in _persona_layer_write —
                # two independent checks, because a single regex is one typo from a path
                # escape and "sanitising" a traversal is how you ship one.
                body = self._body()
                res = _persona_layer_write(str(body.get("file", "")),
                                           str(body.get("text", "")))
                payload = json.dumps(res).encode()
                self.send_response(200 if res.get("ok") else 400); _cors(self)
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(payload)
            elif self.path == "/v1/knobs":
                # Set a LIVE knob. Restart-scoped names are REFUSED with the reason —
                # see harness/server/knobs.py: a toggle that silently does nothing is
                # worse than no toggle.
                body = self._body()
                from harness.server.knobs import read_all, set_knob
                results = []
                for k, v in (body.get("values") or {}).items():
                    ok, msg = set_knob(str(k), v)
                    results.append({"name": k, "ok": ok, "message": msg})
                res = {"ok": all(r["ok"] for r in results) if results else False,
                       "results": results, "knobs": read_all()}
                payload = json.dumps(res).encode()
                self.send_response(200 if res["ok"] else 400); _cors(self)
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(payload)
            elif self.path == "/v1/wardrobe":
                body = self._body()
                res = _wardrobe_set(body)
                payload = json.dumps(res).encode()
                self.send_response(200); _cors(self)
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(payload)
            elif self.path == "/v1/wardrobe/want":
                # ── HIS OWN WANTS, FROM THE PANEL (2026-08-21, operator's ask: "a gui
                # method that I can create my own want's descriptions"). Same queue, same
                # prompt anchoring, same generator as hers — the only difference is
                # by="him", which the receipts and the panel keep honest.
                body = self._body()
                try:
                    from harness.control import wardrobe as _WDw
                    txt = (body.get("want") or "").strip()
                    if not txt:
                        res = {"ok": False, "error": "empty want"}
                    else:
                        res = _WDw.request(txt, tier=(body.get("outfit") or "t0"),
                                           by=str(body.get("by") or "him"),
                                           subject=str(body.get("subject") or "clothes"))
                except Exception as exc:
                    res = {"ok": False, "error": str(exc)[:200]}
                payload = json.dumps(res).encode()
                self.send_response(200 if res.get("ok") else 400); _cors(self)
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(payload)
            elif self.path == "/v1/wardrobe/want/dismiss":
                # take a want off the list (row kept, state=dismissed) — his broom
                body = self._body()
                try:
                    from harness.control import wardrobe as _WDd
                    wid = (body.get("id") or "").strip()
                    res = (_WDd.dismiss(wid, by=str(body.get("by") or "him"))
                           if wid else {"ok": False, "error": "no id"})
                    res.setdefault("ok", True)
                except Exception as exc:
                    res = {"ok": False, "error": str(exc)[:200]}
                payload = json.dumps(res).encode()
                self.send_response(200 if res.get("ok") else 400); _cors(self)
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(payload)
            elif self.path == "/v1/wardrobe/generate":
                # ── GENERATE NOW (2026-08-21): the click that replaces the day-boundary
                # wait. Runs in a background thread — a generation is minutes and an HTTP
                # handler is not — one at a time (the API bills per image; a double-click
                # must not double-spend). {"id": want_id} for one, {} / {"all": true}
                # for everything asked + owed motion. Poll /v1/wardrobe (genstatus key).
                body = self._body()
                res = _gen_now_start(body)
                payload = json.dumps(res).encode()
                self.send_response(200 if res.get("ok") else 409); _cors(self)
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(payload)
            elif self.path == "/v1/catalog":
                # ── THE CATALOG, WRITTEN (2026-08-21) ───────────────────────────────
                # op: edit | hide | unhide | remove | restore | import. remove is a
                # TOMBSTONE (restore undoes it); import takes a file from the inbox
                # through the same tooling a made look passes through — webm, the
                # seamless ping-pong loop, a poster frame — and registers it as hers.
                body = self._body()
                try:
                    from harness.control import catalog as _cat
                    op = str(body.get("op") or "").strip()
                    aid = str(body.get("id") or "").strip()
                    if op == "edit":
                        res = _cat.edit(aid, title=body.get("title"),
                                        description=body.get("description"),
                                        category=body.get("category"),
                                        tags=body.get("tags"))
                    elif op == "hide":
                        res = _cat.hide(aid)
                    elif op == "unhide":
                        res = _cat.unhide(aid)
                    elif op == "remove":
                        res = _cat.remove(aid, by=str(body.get("by") or "him"))
                    elif op == "restore":
                        res = _cat.restore(aid)
                    elif op == "import":
                        res = _cat.import_file(str(body.get("file") or ""),
                                               str(body.get("category") or ""),
                                               title=str(body.get("title") or ""),
                                               description=str(body.get("description") or ""),
                                               tags=body.get("tags") or [],
                                               loop=body.get("loop", True) is not False)
                    else:
                        res = {"ok": False, "error": "unknown op %r" % op}
                except Exception as exc:
                    res = {"ok": False, "error": str(exc)[:200]}
                payload = json.dumps(res).encode()
                self.send_response(200 if res.get("ok") else 400); _cors(self)
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(payload)
            elif self.path in ("/v1/search/run", "/v1/research/run"):
                # ── HIS OWN LOOKUPS (2026-08-21, his ask: "a place that I can use them
                # to search and research manually"). Synchronous on purpose: the panel
                # holds a busy state and the answer IS the response. Both write into
                # the shared looking ledger with by="him" — she can read and use his
                # rows, the chips keep whose-is-whose honest, and neither touches the
                # in-flight chip, which reports HER activity only.
                body = self._body()
                try:
                    from harness.skills import looking as _Lk
                    if self.path == "/v1/search/run":
                        res = _Lk.his_search(body.get("query") or "",
                                             int(body.get("n") or 6))
                    else:
                        res = _Lk.his_research(body.get("query") or "",
                                               str(body.get("depth") or "normal"))
                except Exception as exc:
                    res = {"ok": False, "error": str(exc)[:200]}
                payload = json.dumps(res).encode()
                self.send_response(200 if res.get("ok") else 400); _cors(self)
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(payload)
            elif self.path == "/v1/voice/record":  # ADR-KAI4 P1.6: save a real training sample
                body = self._body()
                try:
                    from harness.voice.record import save_recording
                    res = save_recording(body.get("text", ""), body.get("audio_b64", ""))
                except Exception as exc:
                    res = {"ok": False, "error": str(exc)}
                payload = json.dumps(res).encode()
                self.send_response(200); _cors(self)
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(payload)
            elif self.path == "/v1/voice":  # ADR-KAI4 P0: one VAD-segmented utterance
                body = self._body()
                self.send_response(200); _cors(self)
                self.send_header("Content-Type", "text/event-stream"); self.end_headers()
                try:
                    from harness.voice.service import voice_turn
                    transcript = _session_transcript({"session_id": body.get("session_id"),
                                                      "messages": body.get("messages", [])})
                    for chunk in voice_turn(body, transcript):
                        self.wfile.write(chunk); self.wfile.flush()
                except Exception as exc:
                    self.wfile.write(("data: " + json.dumps(
                        {"error": f"voice: {exc}"}) + "\n\ndata: [DONE]\n\n").encode())
                    self.wfile.flush()
            elif self.path == "/v1/speak":  # SPEECH OUT — one utterance -> audio/wav
                # Deliberately ONE utterance per call, not one reply. Long input on
                # this build does not degrade, it blows up (a 20 s paragraph ran 47
                # min at 11.9/12 GB VRAM before it was killed), so tts.synthesize
                # refuses over SP_TTS_MAX_CHARS and the CLIENT splits and queues —
                # which also means she starts talking after one sentence instead of
                # after the whole answer. console/speech.js owns that queue.
                body = self._body()
                try:
                    from harness.voice import tts
                    wav, meta = tts.synthesize(body.get("text", ""),
                                               voice=body.get("voice") or None,
                                               steps=body.get("euler_steps"))
                    self.send_response(200); _cors(self)
                    self.send_header("Content-Type", "audio/wav")
                    self.send_header("Content-Length", str(len(wav)))
                    # so the console can show cache hits and real synthesis cost
                    self.send_header("X-TTS-Cached", "1" if meta.get("cached") else "0")
                    self.send_header("X-TTS-Seconds", str(meta.get("seconds", 0)))
                    self.end_headers()
                    self.wfile.write(wav)
                except Exception as exc:
                    payload = json.dumps({"ok": False, "error": str(exc)}).encode()
                    self.send_response(503); _cors(self)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
            elif self.path == "/v1/music/control":
                # HE and SHE change the same state. `by` is recorded so the room can
                # say who put something on — which is most of what makes a shared
                # player feel shared rather than contested.
                body = self._body()
                try:
                    from harness.skills import music as _mus
                    act = (body.get("action") or "").lower()
                    if act == "play":
                        res = {"ok": True, "said": _mus.play_music(body.get("query", ""))}
                        _mus.set_state(changed_by="you")
                    elif act == "pause":
                        res = {"ok": True, "said": _mus.pause_music()}
                        _mus.set_state(changed_by="you")
                    elif act == "next":
                        res = {"ok": True, "said": _mus.skip_track()}
                        _mus.set_state(changed_by="you")
                    elif act == "queue":
                        res = {"ok": True, "said": _mus.queue_track(body.get("query", ""))}
                    elif act == "track":
                        t = next((x for x in _mus.scan()
                                  if x["path"] == body.get("path")), None)
                        if t:
                            _mus.set_state(playing=True, track=t, position_s=0.0,
                                           changed_by="you")
                            res = {"ok": True, "said": f"Playing {t['title']}"}
                        else:
                            res = {"ok": False, "error": "no such track"}
                    elif act == "position":
                        # only the PAGE knows where the decoder actually is
                        _mus.set_state(position_s=float(body.get("position_s") or 0))
                        res = {"ok": True}
                    else:
                        res = {"ok": False, "error": f"unknown action {act!r}"}
                    res["state"] = _mus.state()
                except Exception as exc:
                    res = {"ok": False, "error": str(exc)[:200]}
                payload = json.dumps(res).encode()
                self.send_response(200 if res.get("ok") else 400); _cors(self)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers(); self.wfile.write(payload)
            elif self.path == "/v1/files/write":
                # THE PATTERN IS _persona_layer_write, not _persona_set: two
                # INDEPENDENT checks, refuse rather than sanitise. Containment is
                # verified on the RESOLVED path, so `..%2f`, symlinks and Windows
                # short names cannot walk out of the workspace.
                body = self._body()
                try:
                    ws = os.path.realpath(os.environ.get("HARNESS_WORKSPACE") or os.getcwd())
                    rel = _ws_rel(body.get("path") or "")
                    ap = os.path.realpath(os.path.join(ws, rel))
                    if not ap.startswith(ws + os.sep):
                        raise ValueError("path escapes the workspace")
                    text = body.get("text")
                    if text is None:
                        raise ValueError("text is required")
                    if len(text) > 2_000_000:
                        raise ValueError("file too large (2 MB limit)")
                    os.makedirs(os.path.dirname(ap) or ws, exist_ok=True)
                    with open(ap, "w", encoding="utf-8") as f:
                        f.write(text)
                    res = {"ok": True, "path": rel, "bytes": len(text.encode())}
                except Exception as exc:
                    res = {"ok": False, "error": str(exc)[:200]}
                payload = json.dumps(res).encode()
                self.send_response(200 if res.get("ok") else 400); _cors(self)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers(); self.wfile.write(payload)
            elif self.path == "/v1/system":
                # THE RESPONSE GOES OUT BEFORE ANYTHING IS STOPPED. A full restart kills
                # this very process; replying afterwards is replying from a socket that
                # is already gone.
                body = self._body()
                op = str(body.get("op") or "").strip().lower()
                full = (op == "restart")
                if op in ("restart", "restart_gateway"):
                    res = _spawn_restart(full)          # validate only; nothing is stopped yet
                else:
                    res = {"ok": False,
                           "error": "op must be restart or restart_gateway"}
                payload = json.dumps(res).encode()
                self.send_response(200 if res.get("ok") else 400); _cors(self)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers(); self.wfile.write(payload)
                try:
                    self.wfile.flush()
                except Exception:
                    pass
                # ONLY NOW. The socket has the answer; it is safe to stop the process.
                if res.get("ok"):
                    _do_restart(full)
                return
            elif self.path == "/v1/games":
                # new | move | drop. `drop` really deletes a finished match, and that is
                # deliberate: a game is live state like a scene, not memory like a fact —
                # the tombstone rule protects what she KNOWS, not a board she finished.
                body = self._body()
                try:
                    from harness.games import match as M
                    op = str(body.get("op") or "").strip().lower()
                    name = str(body.get("name") or "").strip()
                    if op == "new":
                        m = M.new(str(body.get("kind") or "chess").strip().lower(),
                                  name or str(body.get("kind") or "chess"))
                        res = {"ok": True, "state": M.public(m)}
                    elif op == "move":
                        res = M.play(name, str(body.get("move") or ""))
                    elif op == "drop":
                        M.drop(name)
                        res = {"ok": True}
                    # THE THREE A REAL GAME NEEDED. None is derivable from the board:
                    # they are agreements between players, which is exactly why the
                    # position-based verdict never produced them and no gate missed them.
                    elif op == "resign":
                        res = M.resign(name, str(body.get("side") or ""))
                    elif op == "offer_draw":
                        res = M.offer_draw(name, str(body.get("side") or ""))
                    elif op == "draw":
                        res = M.answer_draw(name, bool(body.get("accept")),
                                            str(body.get("side") or ""))
                    elif op == "rewind":
                        res = M.rewind(name, int(body.get("plies") or 1))
                    elif op == "deal":
                        res = M.deal_next(name)
                    else:
                        raise ValueError(
                            "op must be new, move, drop, resign, offer_draw, draw, rewind or deal")
                except Exception as exc:
                    res = {"ok": False, "error": str(exc)[:200]}
                payload = json.dumps(res).encode()
                self.send_response(200 if res.get("ok") else 400); _cors(self)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers(); self.wfile.write(payload)
            elif self.path == "/v1/roleplay":
                # enter | exit, from the panel. EXIT IS UNCONDITIONAL and takes no
                # argument beyond the op: a stop that can fail, or that needs the right
                # scene id, is not a stop. ladder.py already gets this right for typed
                # stops; the button must not be weaker than the words.
                body = self._body()
                try:
                    from harness.roleplay import engine as rp
                    op = str(body.get("op") or "").strip().lower()
                    if op == "exit":
                        rp.leave(_room_session())
                        res = {"ok": True, "scene": None}
                    elif op == "enter":
                        # A DOOR THAT IGNORES THE SWITCH IS NOT BEHIND THE SWITCH. This
                        # route could start a scene with roleplay.enabled false, which is
                        # how "off" kept producing scenes. EXIT is deliberately NOT gated:
                        # a stop must work in every state, including states that should
                        # not exist.
                        if not _roleplay_on():
                            raise ValueError("roleplay is switched off (roleplay.enabled)")
                        sc = rp.enter(_room_session(), str(body.get("id") or ""))
                        if not sc:
                            raise ValueError("no such scenario")
                        res = {"ok": True, "opening": rp.opening_for(_room_session()),
                               "scene": rp.status(_room_session())["scene"]}
                    else:
                        raise ValueError("op must be enter or exit")
                except Exception as exc:
                    res = {"ok": False, "error": str(exc)[:200]}
                payload = json.dumps(res).encode()
                self.send_response(200 if res.get("ok") else 400); _cors(self)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers(); self.wfile.write(payload)
            elif self.path == "/v1/ledger":
                # THE LEDGER, WRITE SIDE. One route, an explicit `op` from a finite set —
                # not four routes, and not "POST a row and we'll guess what you meant".
                # `drop` is the remove button and it TOMBSTONES: harness/control/ledger.py
                # has no delete, so there is no path from this handler to losing a row.
                body = self._body()
                try:
                    L = __import__("harness.control.ledger", fromlist=["x"])
                    op = str(body.get("op") or "").strip().lower()
                    if op == "add":
                        # Anything arriving through the room is HIS. The default owner is
                        # claude, so an unattributed row would silently read as mine.
                        row = L.add(kind=body.get("kind"), title=body.get("title"),
                                    body=body.get("body"), refs=body.get("refs"),
                                    status=body.get("status"), pinned=body.get("pinned"),
                                    owner=body.get("owner") or "sam")
                    elif op == "edit":
                        row = L.edit(str(body.get("id") or ""), **{
                            k: body.get(k) for k in
                            ("kind", "status", "title", "body", "refs", "pinned", "owner")
                            if k in body})
                    elif op == "drop":
                        row = L.drop(str(body.get("id") or ""))
                    elif op == "restore":
                        row = L.edit(str(body.get("id") or ""), status="open")
                    else:
                        raise ValueError("op must be one of add, edit, drop, restore")
                    if row is None:
                        raise ValueError("no such entry")
                    res = {"ok": True, "entry": row, "counts": L.counts()}
                except Exception as exc:
                    res = {"ok": False, "error": str(exc)[:200]}
                payload = json.dumps(res).encode()
                self.send_response(200 if res.get("ok") else 400); _cors(self)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers(); self.wfile.write(payload)
            elif self.path == "/v1/persona":  # PK2 §P1 persona editor (write persona.md)
                body = self._body()
                payload = json.dumps(_persona_set(body.get("persona", ""))).encode()
                self.send_response(200); _cors(self)
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(payload)
            elif self.path == "/v1/chat/completions":  # OpenAI surface (also agent-driven)
                # COUNTED HERE TOO. This file already records the same mistake four
                # times over — kairos, the repeat-guard, roleplay, capture, and
                # on_user_turn were each wired into ONE of these two chat paths and so
                # were wired into neither. The live gate speaks THIS endpoint; a
                # shutdown that only waits on the console's turns would abandon a
                # generation it could trivially have waited for.
                body = self._body()
                if not _sd_turn_start():
                    self._refuse_shutting_down()
                    return
                try:
                    if body.get("stream"):
                        self.send_response(200); _cors(self)
                        self.send_header("Content-Type", "text/event-stream"); self.end_headers()
                        for chunk in stream_completion(body):
                            self.wfile.write(chunk.encode()); self.wfile.flush()
                    else:
                        payload = json.dumps(blocking_completion(body)).encode()
                        self.send_response(200); _cors(self)
                        self.send_header("Content-Type", "application/json"); self.end_headers()
                        self.wfile.write(payload)
                finally:
                    _sd_turn_end()
            else:
                self.send_error(404)

        def do_GET(self):  # noqa: N802
            # GETs are guarded too. Reading /v1/memory or /v1/senses from a foreign
            # page is not catastrophic the way a POST is, but it is his room, his
            # notes and his facts, and there is no reason for a web page he happens
            # to be visiting to enumerate them.
            if self._guard():
                return
            _json_routes = {
                "/health": lambda: {"ok": True, "agent": True,
                                    "warm": _WARM.is_set() or not __import__(
                                        "harness.inference.backends", fromlist=["x"]).supports("warm"),
                                    "engine": _engine_info(),
                                    "daemon": get_client().health()},
                # THE LABEL THAT LIED (2026-07-29): the console hardcoded "gemma-4-12B"
                # in its reply header, so a whole field session against the model was
                # attributed to the 12B — and read back as 12B behaviour. The name comes
                # from the ONE authority that cannot be stale: the container serve.py
                # actually loaded. Not a config default, which is what the Flask
                # fallback's /v1/models uses and why it still says gemma4-12b-b1.
                "/v1/models": _models_json,
                "/v1/voice/status": _voice_status,   # ADR-KAI4: ear device/artifacts state
                "/v1/voice/corpus": _voice_corpus,   # ADR-KAI4 P1.6: sentences to read for training
                "/v1/voice/record/status": _voice_record_status,
                # SPEECH OUT state — backend (warm server vs per-utterance CLI),
                # cache depth, and the dials. The console reads this to decide
                # whether to offer voice at all rather than discovering mid-reply.
                # THE TOOL SURFACE — what she has, grouped, with a RISK class on
                # every row. The answer to "i dont even know what they are
                # offering": 36 tools across 10 families, and which of them can
                # touch his room, his files, or the network. Reflects LIVE state,
                # so a knob that is off shows its tools absent rather than
                # pretending. g_tool_manifest.py fails if any live tool is missing
                # a row, which is what stops this becoming a brochure.
                # THE BACKUPS — how many, how big, when the next one is, and what
                # the last one skipped. A backup system you cannot see the state of
                # is one you find out about when you need it.
                # THE ROOM'S HEARTBEAT — one call, everything the shell needs.
                "/v1/room/pulse": _room_pulse,
                # MUSIC — the library and the shared intent. The BROWSER decodes
                # audio, so the naive design puts the player in the page and she can
                # never touch it. The server holds what is playing; the page follows.
                "/v1/music": lambda: {
                    "ok": True,
                    "state": __import__("harness.skills.music", fromlist=["x"]).state(),
                    "library": __import__("harness.skills.music", fromlist=["x"]).scan(),
                },
                # HER JOURNAL — readable at last. She has written one paragraph a
                # night since the consolidation ticker was armed, has seen it only
                # passively in the standing-world block, and could not read her own
                # history back. Neither could the room.
                "/v1/narrative": _narrative_json,
                # WHAT SHE LOOKED UP. Receipts only — there is no write route.
                # A research window someone else can revise is a document about
                # her homework, not a record of it.
                "/v1/research": _research_json,
                # HIS-AND-HERS SEARCHES — the non-research half of the same ledger.
                "/v1/search": _search_json,
                # THE CATALOG (2026-08-21, his overhaul): everything she can wear, do or
                # show — one shape, with his edits, hidden and removed included so the
                # panel can offer the way back — plus the inbox of files waiting to be
                # named and placed.
                "/v1/catalog": lambda: {
                    "ok": True,
                    "rows": __import__("harness.control.catalog", fromlist=["x"]).rows(
                        include_hidden=True, include_removed=True),
                    "inbox": __import__("harness.control.catalog", fromlist=["x"]).inbox(),
                    "categories": list(__import__("harness.control.catalog",
                                                  fromlist=["x"]).CATEGORIES)},
                # THE SHARED WORKSPACE, listed. Same tree her file tools resolve
                # against (HARNESS_WORKSPACE), so what she writes he sees.
                "/v1/files": _files_json,
                "/v1/backups": lambda: {
                    "ok": True,
                    "status": __import__("harness.control.backup",
                                         fromlist=["x"]).status(),
                    "backups": __import__("harness.control.backup",
                                          fromlist=["x"]).listing()[:20],
                },
                "/v1/tools": lambda: __import__(
                    "harness.tools.manifest", fromlist=["x"]).describe(),
                # STATUS + the LIVE resolution (2026-08-21): live_voice() is the
                # same function synthesize() consults, so the voice panel's chips
                # and the next sentence she speaks can never disagree.
                "/v1/speak/status": lambda: {
                    **__import__("harness.voice.tts", fromlist=["x"]).status(),
                    "live": __import__("harness.voice.tts",
                                       fromlist=["x"]).live_voice()},
                # SENSES (2026-07-31) — what the SERVED model can actually receive.
                # Ruled from config/model_capability.json, never inferred. This is
                # the surface on which "she cannot hear on this checkpoint" is a
                # visible fact instead of a silent 3840-into-2816 injection.
                "/v1/senses": lambda: {
                    "ok": True,
                    "capability": __import__(
                        "harness.senses.capability", fromlist=["x"]).status(),
                    "sight": __import__(
                        "harness.senses.vision", fromlist=["x"]).status(),
                    "capture": __import__(
                        "harness.senses.capture", fromlist=["x"]).status(),
                    # the room-on-a-timer: enabled, interval, last look, next look.
                    # There is no state in which it runs and he cannot see that.
                    "ambient": __import__(
                        "harness.senses.ambient", fromlist=["x"]).status(),
                    "ambient_recent": __import__(
                        "harness.senses.ambient", fromlist=["x"]).recent(5),
                },
                # THE LEDGER — the plan, the parked, and everything noticed-and-not-touched.
                # Read side. Dropped rows are INCLUDED and flagged; the panel hides them
                # behind a toggle, because "removed" here means tombstoned, not gone.
                # THE STAGE. Introspection over the roleplay director: is a scene
                # running, on which rung, how many beats, which hooks have fired, and
                # the whole ladder so the panel can SHOW it rather than describe it.
                # Nothing could ask any of this before, so the operator's only view of
                # a live scene was the gateway log.
                "/v1/roleplay": _roleplay_status,
                # THE BOARD. Read side: every match, plus the full state of one.
                # `?name=` picks the match; the answer to a wordle is withheld by
                # match.public() until the game ends, and the route does not go
                # around it — a payload that leaks the hidden word to the panel that
                # renders it is a game with no game in it.
                "/v1/games": _games_json,
                # HER FACE. What exists, and what the ceiling currently permits.
                # Note what is NOT here: a way to ask for a tier. The client names a
                # FACE and a KIND; the server decides the tier from the live rung and
                # `roleplay.max_heat`. A client that cannot name a tier cannot ask for
                # a forbidden one, which is a stronger guarantee than checking that it
                # did not.
                "/v1/avatar": _avatar_json,
                "/v1/wardrobe": _wardrobe_json,
                # THE STACK ITSELF: which profile is live, and whether it can be
                # restarted from here at all.
                "/v1/system": _system_json,
                "/v1/ledger": lambda: {
                    "ok": True,
                    "entries": __import__(
                        "harness.control.ledger", fromlist=["x"]).all_entries(),
                    "counts": __import__(
                        "harness.control.ledger", fromlist=["x"]).counts(),
                    "kinds": list(__import__(
                        "harness.control.ledger", fromlist=["x"]).KINDS),
                    "kind_blurb": __import__(
                        "harness.control.ledger", fromlist=["x"]).KIND_BLURB,
                    "statuses": list(__import__(
                        "harness.control.ledger", fromlist=["x"]).STATUSES),
                },
                # GATE HEALTH — what the receipts say and how old they are. Reads
                # var/sem/receipts/; runs nothing. A green with no age is the exact lie
                # G-PF-PERSONA was telling, so age ships alongside the verdict.
                "/v1/health/gates": lambda: __import__(
                    "harness.control.ledger", fromlist=["x"]).gate_health(),
                "/v1/memory": _memory_json,      # PK2 §U1 memory-browser data
                "/v1/tasks": _tasks_json,        # PK2 §U1 task-queue data
                "/v1/persona": _persona_get,     # PK2 §P1 persona editor (load)
                "/v1/persona/state": _persona_state,  # ADR-006 personality chip
                "/v1/spine": _spine_json,        # ADR-008 receipts audit trail
                "/v1/progress": _progress_json,  # HINDSIGHT dashboard data (phases/migration/git)
                # TUNING (2026-07-12): the declarative knob registry. console/tuning.html
                # and the room's settings window both render whatever this returns, so
                # a knob added to harness/tuning/registry.py appears with no UI edit.
                # ONE key in this dict — 2026-08-21 the settings window shipped a
                # second "/v1/tuning" entry higher up and the later duplicate silently
                # won, serving the ok-less shape and freezing the window on "reading
                # the knobs…". The dict is a literal; Python keeps the LAST duplicate
                # and warns about none of it. `ok` lives here now, on the one route,
                # and G-ROUTES-ONCE fails ANY dict literal in this file with a
                # duplicated key.
                "/v1/tuning": lambda: {"ok": True, **__import__(
                    "harness.tuning.registry", fromlist=["x"]).schema()},
                  # KNOBS (2026-07-30): the operator-visible control surface, grouped and
                  # SCOPED. `live` knobs are read per call and toggle now; `restart` knobs
                  # are read at daemon launch or into the persist-KV prefix, and a write to
                  # one is REFUSED with the reason rather than silently ignored — a toggle
                  # that appears to work and does not is the --worktree lesson again.
                  # Same self-rendering contract as /v1/tuning: add a row to
                  # harness/server/knobs.py REGISTRY and it appears with no UI edit.
                  "/v1/knobs": lambda: {
                      "ok": True,
                      "groups": __import__(
                          "harness.server.knobs", fromlist=["x"]).groups(),
                      "knobs": __import__(
                          "harness.server.knobs", fromlist=["x"]).read_all()},
                  # PERSONA LAYERS (2026-07-30): which fragments composed into her prefix
                  # THIS session, which did not, and the `when` that decided it. Bodies are
                  # truncated — the panel is for "why is that section missing", not for
                  # editing prose, and a full dump of every fragment is a page nobody reads.
                  "/v1/persona/layers": _persona_layers,
                # STATS IS A READ. It was reachable only under do_POST (with its sibling
                # maintenance PASSES, which do mutate), so a plain GET 404'd — and because
                # the operator panel loaded stats FIRST, that 404 threw and took the whole
                # memory pane down with it. The symptom on screen was "(gateway down)"
                # while the gateway was up and answering every other route. A read that
                # can only be reached by POST is a trap; this is the fix.
                "/v1/maintenance/stats": lambda: __import__(
                    "harness.maintenance.ops", fromlist=["x"]).stats(),
                # THE BOARD — notes/ideas/reminders, shared with her. Read side.
                # HER OWN TIME. A read-only view that composes five stores she already
                # writes — see harness/control/agency_feed.py for why it owns nothing.
                "/v1/agency": lambda: __import__(
                    "harness.control.agency_feed", fromlist=["x"]).feed(days=3),
                "/v1/notes": lambda: {
                    "notes": __import__("harness.skills.notes", fromlist=["x"]).live(),
                    "stats": __import__("harness.skills.notes", fromlist=["x"]).stats(),
                    "categories": list(__import__(
                        "harness.skills.notes", fromlist=["x"]).CATEGORIES),
                    "colours": __import__(
                        "harness.skills.notes", fromlist=["x"]).CATEGORY_COLOUR,
                },
                "/v1/notes/due": lambda: {
                    "due": __import__("harness.skills.notes",
                                      fromlist=["x"]).due(include_raised=True),
                },
            }
            # query-string routes (session-scoped)
            _base = self.path.split("?", 1)[0]
            # ── THE RETIRED ROWS ARE STILL ROWS (2026-08-05) ──────────────────────────
            # notes.remove() tombstones (lifecycle=1) rather than deleting, which is the
            # whole store's rule — but /v1/notes served live() only, so the board's
            # "remove" button was indistinguishable from a delete FROM THE PANEL, which
            # is the only place he looks. `?all=1` hands back both, tagged, exactly as
            # the memory panel already does for retired facts.
            if _base == "/v1/notes" and "all=1" in (self.path.split("?", 1) + [""])[1]:
                _N = __import__("harness.skills.notes", fromlist=["x"])
                _rows = _N._load_all()
                _rows.sort(key=lambda r: (r.get("updated_at") or r.get("ts") or ""),
                           reverse=True)
                out = {"notes": [r for r in _rows if not r.get("lifecycle")],
                       "retired": [r for r in _rows if r.get("lifecycle")],
                       "stats": _N.stats(), "categories": list(_N.CATEGORIES),
                       "colours": _N.CATEGORY_COLOUR}
                self.send_response(200); _cors(self)
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps(out).encode())
                return
            if _base in ("/v1/kairos/outbox", "/v1/kairos/state"):
                from urllib.parse import parse_qs, urlparse
                from harness.kairos import scheduler as _ks
                s = (parse_qs(urlparse(self.path).query).get("session") or ["default"])[0]
                out = ({"messages": _ks.drain(s), "state": _ks.peek_state(s)}
                       if _base == "/v1/kairos/outbox" else _ks.peek_state(s))
                self.send_response(200); _cors(self)
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps(out).encode())
                return
            # MUSIC AUDIO — ranged, streamed, never slurped. Path is resolved by
            # music.resolve(), which does realpath containment against the library
            # root: refuse rather than sanitise, the same rule as the room's static
            # handler and _persona_layer_write.
            if _base == "/v1/files/read":
                try:
                    from urllib.parse import parse_qs, urlparse as _up
                    q = parse_qs(_up(self.path).query)
                    rel = _ws_rel((q.get("path") or [""])[0])
                    ws = os.path.realpath(os.environ.get("HARNESS_WORKSPACE") or os.getcwd())
                    ap = os.path.realpath(os.path.join(ws, rel))
                    # containment on the RESOLVED path, refuse rather than sanitise
                    if not rel or not ap.startswith(ws + os.sep) or not os.path.isfile(ap):
                        res = {"ok": False, "error": "no such file in the workspace"}
                    elif os.path.getsize(ap) > 2_000_000:
                        res = {"ok": False, "error": "too large to open here (2 MB)"}
                    else:
                        with open(ap, encoding="utf-8", errors="replace") as f:
                            res = {"ok": True, "path": rel, "text": f.read()}
                except Exception as exc:
                    res = {"ok": False, "error": str(exc)[:200]}
                payload = json.dumps(res).encode()
                self.send_response(200 if res.get("ok") else 400); _cors(self)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(payload)
                return
            if _base == "/v1/avatar/file":
                # THE CLIENT NAMES A FACE AND A KIND. NEVER AN OUTFIT. What she is
                # wearing comes from the WARDROBE — the one thing that knows — not from
                # the request, so the picture always shows what she chose. (The old
                # rung/ceiling arithmetic is gone with the tiers, 2026-08-21: no clamp,
                # no gated asset, her choice is the whole answer.)
                try:
                    from urllib.parse import parse_qs, urlparse as _up
                    from harness.control import avatar as AV
                    q = parse_qs(_up(self.path).query)
                    face = (q.get("face") or ["calm"])[0]
                    kind = (q.get("kind") or ["still"])[0]
                    gesture = (q.get("gesture") or [""])[0]
                    if kind not in AV.KINDS:
                        self.send_error(400); return
                    outfit = AV.DEFAULT_OUTFIT
                    try:
                        from harness.control import wardrobe as _WD
                        outfit = _WD.resolve()["shown"]
                    except Exception as exc:
                        logger.warning("[avatar] wardrobe unavailable: %s", exc)
                    got = AV.resolve(face, outfit, kind, gesture)
                    if not got:
                        self.send_error(404); return
                    ap = AV.abs_path(got["face"], got["outfit"], got["kind"], got["gesture"])
                    # Containment on the RESOLVED path, the _ws_rel lesson: refuse rather
                    # than sanitise, and check where the path actually landed.
                    rt = os.path.realpath(AV.root())
                    if not os.path.realpath(ap).startswith(rt + os.sep):
                        self.send_error(403); return
                    ctype = "image/png" if ap.endswith(".png") else "video/webm"
                    self._send_ranged(ap, ctype)
                except Exception as exc:
                    logger.warning("[avatar] %s", exc)
                    self.send_error(500)
                return
            if _base == "/v1/wardrobe/outfit":
                # HER CLOTHES, EACH ONE PICTURED. The panel could not show the four
                # outfits because /v1/avatar/file refuses a client-named tier — a rule
                # that was right when the ceiling gated her wardrobe and is now just
                # stopping her from seeing what she owns. This route names the outfit
                # explicitly; there is nothing left to gate, because her choice is
                # unclamped by design since 2026-08-02.
                try:
                    from urllib.parse import parse_qs, urlparse as _up
                    from harness.control import avatar as AV
                    q = parse_qs(_up(self.path).query)
                    tier = (q.get("tier") or ["t0"])[0]
                    face = (q.get("face") or ["calm"])[0]
                    kind = (q.get("kind") or ["still"])[0]
                    if tier not in AV.OUTFIT_IDS or face not in AV.FACES or kind not in ("still", "loop"):
                        self.send_error(400); return
                    ap = AV.abs_path(face, tier, kind)
                    rt = os.path.realpath(AV.root())
                    if not os.path.realpath(ap).startswith(rt + os.sep) or not os.path.exists(ap):
                        self.send_error(404); return
                    self._send_ranged(ap, "video/webm" if kind == "loop" else "image/png")
                except Exception as exc:
                    logger.warning("[wardrobe] outfit: %s", exc)
                    self.send_error(500)
                return
            if _base == "/v1/wardrobe/look":
                # A LOOK SHE ASKED FOR. Same ceiling, same shape as the clip route: the
                # tier is looked up from the want row, checked, and only then is a path
                # built. A look above the ceiling 404s as if it were never made.
                try:
                    from urllib.parse import parse_qs, urlparse as _up
                    from harness.control import avatar as AV
                    from harness.control import wardrobe as WD
                    q = parse_qs(_up(self.path).query)
                    wid = (q.get("id") or [""])[0]
                    # NO CEILING (2026-08-21): a made look is hers to show, full stop.
                    row = next((w for w in WD.wants(state="made")
                                if w.get("id") == wid and w.get("file")), None)
                    if not row:
                        self.send_error(404); return
                    base = os.path.join(WD.root(), "looks")
                    # MOTION IF SHE HAS IT. `kind=loop` asks for the video grown from
                    # this exact still; absent, the still is served and the room shows a
                    # photograph rather than nothing. Same floor discipline as the grid.
                    want_loop = (q.get("kind") or [""])[0] == "loop"
                    name = (row.get("loop") if want_loop else "") or row["file"]
                    ap = os.path.join(base, name)
                    if not os.path.realpath(ap).startswith(os.path.realpath(base) + os.sep):
                        self.send_error(403); return
                    if not os.path.exists(ap):
                        self.send_error(404); return
                    self._send_ranged(ap, "video/webm" if name.endswith(".webm") else "image/png")
                except Exception as exc:
                    logger.warning("[wardrobe] %s", exc)
                    self.send_error(500)
                return
            if _base == "/v1/wardrobe/file":
                # THE CEILING DECIDES, NOT THE URL. The client names a clip id; the tier
                # that clip carries is looked up here and checked against the operator's
                # dial before the path is ever built. A request for a clip above the
                # ceiling 404s exactly as if it did not exist — because as far as this
                # room is concerned it does not.
                try:
                    from urllib.parse import parse_qs, urlparse as _up
                    from harness.control import avatar as AV
                    from harness.control import wardrobe as WD
                    q = parse_qs(_up(self.path).query)
                    cid = (q.get("id") or [""])[0]
                    # NO CEILING (2026-08-21): an imported moment is showable by name.
                    row = next((c for c in WD.clips()
                                if c.get("id") == cid and c.get("have")), None)
                    if not row:
                        self.send_error(404); return
                    ap = os.path.join(WD.clips_dir(), row["file"])
                    rt = os.path.realpath(WD.clips_dir())
                    if not os.path.realpath(ap).startswith(rt + os.sep):
                        self.send_error(403); return
                    self._send_ranged(ap, "video/mp4")
                except Exception as exc:
                    logger.warning("[wardrobe] %s", exc)
                    self.send_error(500)
                return
            if _base == "/v1/music/file":
                try:
                    from urllib.parse import parse_qs, urlparse as _up
                    q = parse_qs(_up(self.path).query)
                    rel = (q.get("path") or [""])[0]
                    from harness.skills import music as _mus
                    ap = _mus.resolve(rel)
                    if not ap:
                        self.send_error(404)
                        return
                    ext = os.path.splitext(ap)[1].lower()
                    self._send_ranged(ap, self._AUDIO_TYPES.get(ext, "application/octet-stream"))
                except Exception as exc:
                    logger.warning("[music] %s", exc)
                    self.send_error(500)
                return
            fn = _json_routes.get(_base)
            if fn is not None:
                self.send_response(200); _cors(self)
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps(fn()).encode())
            elif self._serve_console_static():
                pass
            else:
                self.send_error(404)

        # ── console statics on the gateway (dashboard lives here; daemon-independent) ──
        _STATIC_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css",
                         ".js": "application/javascript", ".svg": "image/svg+xml",
                         ".json": "application/json", ".mjs": "application/javascript",
                         ".map": "application/json", ".png": "image/png",
                         ".ico": "image/x-icon", ".woff2": "font/woff2"}

        _AUDIO_TYPES = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac",
                        ".ogg": "audio/ogg", ".opus": "audio/ogg",
                        ".flac": "audio/flac", ".wav": "audio/wav",
                        ".webm": "audio/webm"}

        def _send_ranged(self, fp: str, ctype: str) -> None:
            """Serve a file with Range support.

            WITHOUT THIS, SEEKING IS A LIE. A browser that cannot range-request will
            still play a track — it fetches the whole thing — so audio *appears* to
            work and then dragging the scrubber silently re-downloads from zero. It
            also means a 60 MB flac is read entirely into this process's RAM per
            request, on a box whose spare memory is deliberately reserved for WDDM.

            The stdlib handler gives none of this: the project uses raw
            BaseHTTPRequestHandler, not SimpleHTTPRequestHandler, and there is no
            206 anywhere else in the file."""
            size = os.path.getsize(fp)
            rng = self.headers.get("Range", "")
            start, end = 0, size - 1
            partial = False
            if rng.startswith("bytes="):
                spec = rng[6:].split(",")[0].strip()
                a, _, b = spec.partition("-")
                try:
                    if a:
                        start = int(a)
                        end = int(b) if b else size - 1
                    elif b:                       # suffix range: last N bytes
                        start = max(0, size - int(b))
                    if start >= size or start > end:
                        # RFC 9110: an unsatisfiable range is 416, not a silent 200
                        self.send_response(416); _cors(self)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.end_headers()
                        return
                    end = min(end, size - 1)
                    partial = True
                except ValueError:
                    partial = False
            length = end - start + 1
            self.send_response(206 if partial else 200); _cors(self)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "private, max-age=3600")
            if partial:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if self.command == "HEAD":
                return
            # streamed in chunks, never slurped
            with open(fp, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(262144, left))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        return                    # the player seeked away; normal
                    left -= len(chunk)

        def do_HEAD(self):  # noqa: N802
            # Some media stacks probe with HEAD before ranging. Unimplemented, it
            # returned 501 and the player gave up before it ever asked for bytes.
            if self._guard():
                return
            self.do_GET()

        def _serve_console_static(self) -> bool:
            import os as _os
            path = self.path.split("?", 1)[0]
            if path == "/":
                # THE ROOM IS THE FRONT DOOR (2026-08-21). This served dashboard.html — the
                # July build-progress page — while the room was what he actually opened.
                # dashboard.html is gone; `/` goes where he goes.
                self.send_response(302); _cors(self)
                self.send_header("Location", "/room/"); self.end_headers()
                return True
            name = path.lstrip("/")
            # ── THE ROOM (2026-07-31) ────────────────────────────────────────
            # A built SPA is a directory — index.html plus hashed assets — and this
            # handler was single-flat-filename only, so it could not serve one at
            # all. Exactly ONE subdirectory is allowed, and the containment check
            # is done on the RESOLVED path rather than on the string: `..%2f`,
            # symlinks, and Windows short names all survive a substring check and
            # none of them survive realpath.
            if name.startswith("room/") or name == "room":
                if name == "room":
                    self.send_response(301); _cors(self)
                    self.send_header("Location", "/room/"); self.end_headers()
                    return True
                rel = name[len("room/"):] or "index.html"
                if rel.endswith("/"):
                    rel += "index.html"
                root = _os.path.join(_os.path.dirname(_os.path.dirname(
                    _os.path.dirname(_os.path.abspath(__file__)))), "console", "room")
                fp = _os.path.realpath(_os.path.join(root, rel))
                if not fp.startswith(_os.path.realpath(root) + _os.sep):
                    return False                      # escaped the room
                ext = _os.path.splitext(fp)[1].lower()
                ctype = self._STATIC_TYPES.get(ext)
                if ctype is None or not _os.path.isfile(fp):
                    return False
                with open(fp, "rb") as f:
                    data = f.read()
                self.send_response(200); _cors(self)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                # The room's assets are CONTENT-HASHED by vite (index-<hash>.js), so
                # a long cache is free and correct: a new build is a new name. Without
                # this the 161 KB bundle re-downloaded on every load.
                if "/assets/" in path:
                    self.send_header("Cache-Control", "public, max-age=31536000, immutable")
                else:
                    self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(data)
                return True
            # everything else: single flat filename only — no traversal, no subdirs
            if not name or "/" in name or "\\" in name or name.startswith("."):
                return False
            ext = _os.path.splitext(name)[1].lower()
            ctype = self._STATIC_TYPES.get(ext)
            if ctype is None:
                return False
            root = _os.path.join(_os.path.dirname(_os.path.dirname(
                _os.path.dirname(_os.path.abspath(__file__)))), "console")
            fp = _os.path.join(root, name)
            if not _os.path.isfile(fp):
                return False
            with open(fp, "rb") as f:
                data = f.read()
            self.send_response(200); _cors(self)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return True

    logger.info("[gateway] stdlib AGENT server on %s:%d (operation=serve)", host, port)
    # Pre-warm is OPT-IN (SP_GATEWAY_PREWARM=1) until the byteexact-on prefill is fast OR the LCP
    # rewind is proven byte-exact: with byteexact required, a pre-warm grinds the GPU ~5 min.
    import os as _os
    if _os.environ.get("SP_GATEWAY_PREWARM") == "1":
        _prewarm()  # background: hydrate the persona+tools prefix into the persist cache
    # KAIROS NEEDS A CLOCK. Her CHECK_IN branch asks "has the room been quiet for a while?"
    # — and silence is not an event, so nothing was ever going to ask it on her behalf. The
    # ticker only consults the POLICY (which says SILENT almost always); it reaches the
    # model only when the policy says speak. Guarded by kairos.enabled, so an operator who
    # has not armed her pays nothing.
    try:
        from harness.kairos import scheduler as _ks
        # WHAT SHE SAYS FIRST IS STILL SOMETHING SHE SAID. Registered before the ticker
        # starts, so no impulse can slip through unrecorded. `user_text=""` because there
        # was no user turn — that is the fact, and inventing one would put words in his
        # mouth in the record her journal is written from.
        _ks.on_spoke(lambda text: _append_day_turn("", text))
        _seed_kairos_from_day()
        # What the LAST gateway flushed on its way down comes back to the queue that is
        # read — this boot is the re-entry point for mode=all/kill, where resume()
        # never runs because the process it lives in died. Warm rows only; the file is
        # append-only and the marker row is the cursor (scheduler.reload_undelivered).
        _ks.reload_undelivered()
        _ks.start_ticker()
    except Exception as exc:
        logger.warning("[gateway] kairos ticker not started: %s", exc)
    # THE ROOM, ON A TIMER. Started unconditionally; the thread itself re-reads
    # SP_AMBIENT every beat and does nothing while it is off. That is deliberate:
    # a watcher started only when armed would need a restart to arm, and an off
    # switch you have to reboot to use is not an off switch.
    # HOURLY BACKUP. Started unconditionally; the thread re-reads SP_BACKUP every
    # beat and does nothing while off, so turning it off does not need a restart.
    # Her state is gitignored by design, which means git is not a safety net —
    # something else has to be, and on 2026-07-31 nothing was.
    try:
        from harness.control import backup as _bk
        _bk.start()
        logger.info("[gateway] backup: enabled=%s every %.0fs -> %s",
                    _bk.ENABLED, _bk.INTERVAL_S, _bk.DIR)
    except Exception as exc:
        logger.warning("[gateway] backup not started: %s", exc)
    try:
        from harness.senses import ambient as _amb
        _amb.start()
        logger.info("[gateway] ambient eye: enabled=%s every %.0fs",
                    _amb.enabled(), _amb.interval_s())
    except Exception as exc:
        logger.warning("[gateway] ambient eye not started: %s", exc)
    # AND SOMETHING HAS TO WATCH THE DAEMON. On 2026-08-03 he wrote to her first thing and
    # got `[WinError 10061] ... actively refused it` — the daemon had died in the night and
    # nothing noticed, because serve.py Popens it and exits. `_do_restart` is passed in
    # rather than imported by the watchdog: the gateway owns the one restart door (it goes
    # through serve.py, so the profile and env guards still run) and a second relaunch path
    # is the duplicate this repo keeps paying for.
    try:
        from harness.control import watchdog as _wd
        _wd.start(_do_restart)
        logger.info("[gateway] watchdog: enabled=%s every %.0fs (restart floor %.0fs)",
                    _wd.enabled(), _wd.interval_s(), _wd.cooldown_s())
    except Exception as exc:
        logger.warning("[gateway] watchdog not started: %s", exc)
    # AND THE DAY NEEDS A CLOCK TOO. The kairos ticker asks "has the room gone quiet?"
    # every 15 s; nothing ever asked "has the day ended?". So the narrative had never been
    # written, the personality curator never ran on a schedule, world.refresh() was
    # reachable only by hand, and spine receipts were never flushed. Off unless the
    # profile sets an hour.
    try:
        start_consolidation_ticker()
    except Exception as exc:
        logger.warning("[gateway] day boundary not armed: %s", exc)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


def run(host: str = "127.0.0.1", port: int = 8800) -> None:
    """Start the agent gateway (zero-dep stdlib server with native /v1/chat + OpenAI surface)."""
    _run_stdlib(host, port)


if __name__ == "__main__":
    # the port is the profile's [serve].gateway_port, mapped once in serve.py build_env
    run(port=int(os.environ.get("SP_GATEWAY_PORT") or "8800"))
