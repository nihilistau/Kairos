"""consult.py — her way up: one hard question to Claude, and an answer she can think with.

WRITTEN 2026-10-21 (the operator's design, docs/superpowers/specs/2026-10-21-claude-provider-
and-consult-design.md). Research hands a question to something with a browser; consult hands
it to something that REASONS — a long chain, a tricky fact, a problem she is stuck on. It has
no tools and no web. It goes through the one Claude door (skills/claude.py) like every Claude
feature, so off the record holds it there too.

ONLY THE QUESTION LEAVES. The payload is the question she wrote, as the single user message,
and SYSTEM below — a fixed instruction that says nothing about her. No persona, no memory, no
transcript, no names. The tool description tells her to write it that way; this file makes
sure nothing else rides along.

THE HONESTY RULE IS RESEARCH'S, unchanged (research.py): the answer comes back through
Answer.for_model(), opening "this is not your memory and not something he told you". She may
take the conclusion as her own thinking; a fact from it is never "you told me".

THE DOORS ARE CHECKED AT CALL TIME, NOT BY HIDING THE TOOL. The toolset is part of the one
cached system prefix, so a tool that came and went with a scene would cost a cold prefill per
flip. The tool is present whenever consult is armed and keyed; shut_reason() refuses, with no
network call and no receipt, in order:

    off the record      anon.holds("net.consult") — for her AND for his box
    a roleplay scene    hers only: what passes between them in a scene stays there
    intimate presence   hers only: a presence mode running with the intimate variants on
    her own time        hers only, and only when the operator switched consult.own_time off

His box (Task 7, the Research app) calls ask(q, by="him"): his click is the authorization, so
the arming knob and her session doors do not apply — off the record still does.

UNCAPPED, LOGGED. Every call that reaches the wire leaves a receipt under SP_CONSULT_RECEIPTS
(model, effort, usage, seconds, lane, by, stop_reason); her calls also write a row to the
looking ledger the room reads, exactly as research does.

Gate: harness_tests/g_consult.py (G-CONSULT sections 2-9).
"""
from __future__ import annotations

import inspect
import os
import time
from typing import List

from harness.skills.research import Answer, _receipt

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

DOOR = "net.consult"
TIMEOUT = 600.0
MAX_TOKENS = 16000

# THE WHOLE SYSTEM PROMPT. Fixed, and about the answer — never about who is asking.
SYSTEM = ("Answer the question carefully and completely. Reason it through step by step where "
          "that helps, say plainly what is uncertain or contested, and keep the answer "
          "self-contained.")

SCENE = "not sent — you are in a scene, and this stays between you"
INTIMATE = "not sent — this is an intimate time between you, and it stays between you"
OWN_TIME = "not sent — consulting in your own time is switched off"


def armed() -> bool:
    """Read per call, not at import: a gate (and a future panel toggle) flips it in-process."""
    return os.environ.get("SP_CONSULT", "0") == "1"


def _receipts_root() -> str:
    d = os.environ.get("SP_CONSULT_RECEIPTS", "")
    if d:
        return d
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "var", "consult")


def _pick(knob: str, env: str, default: str) -> str:
    """Override-only: his panel pick, else the profile's boot default, else the shipped one."""
    try:
        from harness.tuning import registry as _t
        v = str(_t.chosen(knob) or "").strip()
        if v:
            return v
    except Exception as _swx:
        _swallowed(_swlog, "_pick", _swx, lane="skills")
    return (os.environ.get(env) or default).strip()


def _model() -> str:
    return _pick("consult.model", "SP_CONSULT_MODEL", "claude-opus-5-5")


def _effort() -> str:
    return _pick("consult.effort", "SP_CONSULT_EFFORT", "high")


def _own_time_allowed() -> bool:
    # No profile carries this one, so the knob's declared default (on) IS the boot default
    # and tune.get is the honest read. A store that cannot be read refuses, because the
    # operator's "off" is the thing a broken read must not quietly overrule.
    try:
        from harness.tuning import registry as _t
        return bool(_t.get("consult.own_time", True))
    except Exception as _swx:
        _swallowed(_swlog, "_own_time_allowed", _swx, lane="skills")
        return False


def _scene_running() -> bool:
    """Is a roleplay scene running in the room?

    The session comes from harness/control/room.py, NEVER from importing harness.server.app:
    the gateway runs as __main__, so that import is a second copy of the server (room.py).

    FAILS OPEN ON THE IMPORT, CLOSED ON THE QUESTION (2026-10-21). If the roleplay engine
    cannot even be imported there is no room in this process to have a scene in; with no
    chat turn yet the room says "default", which has none. But a room that cannot SAY whether
    a scene is running might be mid-scene, and sending her question then is the one mistake
    this door exists to prevent: that raises, and the caller counts it as a scene."""
    try:
        from harness.roleplay import engine as rp
        from harness.control import room as _room
    except Exception as _swx:
        _swallowed(_swlog, "_scene_running import", _swx, lane="skills")
        return False
    return rp.active(_room.session()) is not None


def _intimate_presence() -> bool:
    try:
        from harness.tuning import registry as _t
        return (str(_t.get("presence.mode") or "off") != "off"
                and bool(_t.get("presence.intimate")))
    except Exception as _swx:
        # same reasoning as the scene: unable to tell is not permission
        _swallowed(_swlog, "_intimate_presence", _swx, lane="skills")
        return True


def shut_reason(by: str = "her") -> str:
    """'' when a consult may go out; else the plain note she (or his box) gets back.

    Off the record first and for everyone. The rest are about HER session, so his box skips
    them. Checking here counts the held door for the anon receipt, so call it once per ask."""
    from harness.control import anon as _anon
    if _anon.holds(DOOR):
        return _anon.WHY
    if by != "her":
        return ""
    try:
        scene = _scene_running()
    except Exception as _swx:
        _swallowed(_swlog, "_scene_running", _swx, lane="skills")
        scene = True
    if scene:
        return SCENE
    if _intimate_presence():
        return INTIMATE
    from harness.control import lane as _lane
    if _lane.unprompted() and not _own_time_allowed():
        return OWN_TIME
    return ""


def ask(question: str, by: str = "her") -> Answer:
    """The shared core: her tool and his box both come through here. Never raises; a shut
    door, a dead path or a refusal is an ok=False Answer whose text is the whole note."""
    q = (question or "").strip()
    if not q:
        return Answer(text="consult: no question", provenance="consult", ok=False)
    reason = shut_reason(by)
    if reason:
        return Answer(text=reason, provenance="consult", ok=False, question=q)
    from harness.skills import claude as _c
    why = _c.why_unavailable()
    if why:
        return Answer(text="consult unavailable: " + why, provenance="consult", ok=False,
                      question=q)
    from harness.control import lane as _lane
    model, effort = _model(), _effort()
    lane_name = "own" if _lane.unprompted() else "conversation"
    t0 = time.perf_counter()
    r = _c.ask([{"role": "user", "content": q}], model=model, door=DOOR, system=SYSTEM,
               effort=effort, max_tokens=MAX_TOKENS, timeout=TIMEOUT)
    dt = round(time.perf_counter() - t0, 1)
    who = r.model or model                   # the server may have answered with a fallback
    prov = "from Claude (%s), consulted" % who
    text = (r.text or "").strip()
    if r.refusal:
        ans = Answer(text="consult failed: Claude declined (%s)" % r.refusal, provenance=prov,
                     ok=False, seconds=dt, question=q)
    elif not r.ok or not text:
        ans = Answer(text="consult failed: " + (_c.last_error() or "no answer came back"),
                     provenance=prov, ok=False, seconds=dt, question=q)
    else:
        if r.stop_reason == "max_tokens":
            text += "\n\n[truncated: the answer hit the token ceiling]"
        ans = Answer(text=text, provenance=prov, seconds=dt, question=q)
    # EVERY CALL THAT WENT OUT IS LOGGED, whatever came back (review, 2026-10-21): a timeout,
    # a 429 or a dropped connection is Reply(ok=False) with no stop_reason, and may still have
    # been billed. The doors and a missing key returned above, before anything went out.
    ans.receipt = _receipt(ans, ["claude", who, "consult", effort],
                           extra={"model": who, "effort": effort, "usage": r.usage,
                                  "stop_reason": r.stop_reason, "lane": lane_name,
                                  "by": by, "claude_seconds": round(r.seconds, 1)},
                           root=_receipts_root())
    return ans


def consult(question: str) -> str:
    """Ask a stronger model one hard question and think with what comes back.

    For long chains of reasoning, a tricky factual question, or a problem you are stuck on.
    Not for anything personal or intimate between you and him — those stay between you.
    Write the question so it stands alone: no names, no private detail, nothing from your
    memory. Only the question is sent. Takes up to a few minutes.
    """
    q = (question or "").strip()
    if not q:
        return "[consult: no question]"
    # The doors before the arming knob, as research() does: off the record must be counted
    # (and said) whatever else is true.
    reason = shut_reason("her")
    if reason:
        return "[" + reason + "]"
    if not armed():
        return "[consult is not armed — SP_CONSULT=0]"
    from harness.skills import claude as _c
    why = _c.why_unavailable()
    if why:
        return "[consult unavailable: %s]" % why
    from harness.skills import looking as L
    L.begin("consult", q)
    try:
        ans = ask(q, by="her")
        L.end(ans.ok, ans.text[:800], ans.sources, title=q[:80])
    except Exception as exc:
        L.end(False, str(exc)[:200], title=q[:80])
        raise
    return ans.for_model() if ans.ok else "[" + ans.text + "]"


def consult_tools() -> List:
    """Present only when armed AND keyed — a tool that can only ever say "not armed" is
    worse than absent (research_tools' rule). The description is the WHOLE docstring:
    from_callable keeps only its first line, and the lines after it are the instructions."""
    try:
        from harness.skills import claude as _c
        if not armed() or not _c.available():
            return []
        from harness.toolcore.tools import ToolSpec
        return [ToolSpec.from_callable(consult, description=inspect.cleandoc(consult.__doc__ or ""))]
    except Exception as _swx:
        _swallowed(_swlog, "consult_tools", _swx, lane="skills")
        return []
