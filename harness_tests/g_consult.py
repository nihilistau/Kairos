"""G-CONSULT — she can ask Claude something; this gate holds the doors that decide whether she may.

Section 1 (2026-10-21): THE LANE. The consult tool must be able to refuse in her own time when
the operator switches that off, which means the tool has to KNOW it is running inside one of
her unprompted turns. That is a per-context flag (harness/control/lane.py), set by the kairos
scheduler around every unprompted generation.

Sections 2-9 (2026-10-21): THE TOOL. One self-contained question out, an answer back with
provenance, a receipt every time, and the doors that refuse at call time (off the record, a
roleplay scene, an intimate presence mode, her own time with the toggle off). The transport is
a recording fake client; nothing leaves the machine and no key is real.

Lane: OFFLINE.
"""
import inspect
import io
import json
import os
import sys
import threading
import time
import tokenize as _tok
from types import SimpleNamespace as _NS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from harness_tests._gate import sandbox, check, finish, persona_file, utf8_stdout  # noqa: E402

utf8_stdout()

_SB = sandbox("g_consult")  # FIRST, before any harness. import
# the scheduler leg must not reach a real daemon, and a roleplay scene on HIS disk must not
# decide whether the scene door is shut in this gate
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"
os.environ["SP_SCENES_DIR"] = os.path.join(_SB, "scenes")

from harness.control import lane  # noqa: E402
from harness.kairos import scheduler as KS  # noqa: E402


def code_only(text):
    """Source with comments AND docstrings removed, string literals kept. A STRING token whose
    predecessor is a layout token is a docstring; `prev` moves on every token, layout included
    (see g_topic_stats.code_only for the history of getting that wrong)."""
    starts = (_tok.INDENT, _tok.DEDENT, _tok.NEWLINE, _tok.NL, _tok.ENCODING)
    out, prev = [], _tok.ENCODING
    for t in _tok.tokenize(io.BytesIO(text.encode("utf-8")).readline):
        if t.type == _tok.COMMENT:
            continue
        if t.type == _tok.STRING and prev in starts:
            prev = t.type
            continue
        prev = t.type
        out.append(t.string)
    return " ".join(out)


print("1. THE LANE")
check("lane defaults to his", lane.unprompted() is False)

_tok1 = lane.set_unprompted(True)
_during = lane.unprompted()
lane.reset(_tok1)
check("set/reset restores", _during is True and lane.unprompted() is False)

_outer = lane.set_unprompted(True)
_inner = lane.set_unprompted(False)
lane.reset(_inner)
_still = lane.unprompted()
lane.reset(_outer)
check("reset restores the PREVIOUS value, not False", _still is True and lane.unprompted() is False)

_seen = {}
_tok2 = lane.set_unprompted(True)


def _reader():
    _seen["b"] = lane.unprompted()


_t = threading.Thread(target=_reader)
_t.start()
_t.join()
lane.reset(_tok2)
check("a thread does not see another turn's lane", _seen.get("b") is False, _seen)

_arm_src = code_only(inspect.getsource(KS._arm))
check("the scheduler marks her unprompted turns",
      "set_unprompted ( True )" in _arm_src and "lane . reset (" in _arm_src,
      "_arm must set the lane and reset it")

# THE FIRE PATH, DRIVEN (2026-10-21, carried from section 1's review). The grep above proves
# _arm mentions the lane; this proves a generation the scheduler fires actually RUNS inside it,
# and that the flag is gone again once the turn is over.
from harness.kairos import impulse as _KI  # noqa: E402

_lane_seen = []


def _lane_gen(nudge, called=None, **_kw):
    _lane_seen.append(lane.unprompted())
    return ""


_lsess = "g_consult_lane"
with KS._LOCK:
    KS._STATE.pop(_lsess, None)
    KS._STATE[_lsess].last_spoke_at = 0.0
KS._arm(_lsess, _KI.Impulse(_KI.CHECK_IN, delay_s=0.0, score=0.0, reason="gate"), "ok.",
        _lane_gen, None)
with KS._LOCK:
    _lt = KS._TIMERS.get(_lsess)
if _lt is not None:
    _lt.join(15.0)
time.sleep(0.05)
check("a turn the scheduler fires runs inside the lane", _lane_seen == [True], _lane_seen)
# The timer thread's context dies with it, so this cannot see a missing reset (the source leg
# above holds that); what it does hold is that her lane never reaches the thread that armed it.
check("...and the firing thread's lane never reaches this one", lane.unprompted() is False)

_ks_src = code_only(inspect.getsource(KS))
_arm_calls = _ks_src.count("_arm (") - _ks_src.count("def _arm (")
check("the scheduler has exactly two _arm call sites (the tick and the mode kick)",
      _arm_calls == 2, _arm_calls)

# ── THE TOOL ────────────────────────────────────────────────────────────────────────────
os.environ["SP_CONSULT"] = "1"
_KEY = "sk-gate-consult-NOT-A-KEY-7f3a"
for _k in ("SP_CLAUDE_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"):
    os.environ.pop(_k, None)
os.environ["SP_CLAUDE_API_KEY"] = _KEY
os.environ["SP_CLAUDE_KEY_FILE"] = os.path.join(_SB, "no-claude-key-here")

from harness.skills import claude as _CL  # noqa: E402
from harness.skills import consult as C  # noqa: E402
from harness.control import anon as AN  # noqa: E402
from harness.tuning import registry as tune  # noqa: E402
from harness.roleplay import engine as _RP  # noqa: E402

_CALLS: list = []
_QUEUE: list = []


def _msg(text="Here is the careful answer.", stop="end_turn", cat=None, model="claude-opus-5-5"):
    return _NS(content=[_NS(type="text", text=text, citations=None)],
               stop_reason=stop, stop_details=_NS(category=cat) if cat else None, model=model,
               usage=_NS(input_tokens=11, output_tokens=22, cache_read_input_tokens=0))


class _Stream:
    def __init__(self, m): self.m = m
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get_final_message(self): return self.m


class _Messages:
    def stream(self, **kw):
        _CALLS.append(dict(kw, messages=list(kw["messages"])))
        return _Stream(_QUEUE.pop(0) if _QUEUE else _msg())


_FACTORY_HITS: list = []


def _factory(key, base):
    _FACTORY_HITS.append(base)
    return _NS(beta=_NS(messages=_Messages()))


_CL._CLIENT_FACTORY = _factory
_CL._sdk = lambda: object()
_RECEIPTS = os.environ.get("SP_CONSULT_RECEIPTS", "")


def _receipts():
    try:
        return sorted(os.path.join(_RECEIPTS, f) for f in os.listdir(_RECEIPTS) if f.endswith(".json"))
    except OSError:
        return []


def _fresh():
    _CALLS.clear()
    _QUEUE.clear()
    _FACTORY_HITS.clear()


_Q = "Is every bounded monotone sequence of reals convergent, and why?"

print()
print("2. THE ANSWER AND WHAT LEAVES")
check("consult receipts are sandboxed", bool(_RECEIPTS) and
      os.path.abspath(_RECEIPTS).startswith(os.path.abspath(_SB)), _RECEIPTS)
_fresh()
_out = C.consult(_Q)
check("answer carries provenance",
      "not your memory" in _out and "not something he told you" in _out
      and "claude-opus-5-5" in _out and "Here is the careful answer." in _out, _out[:160])
_c0 = _CALLS[0] if _CALLS else {}
check("only the question is sent",
      _c0.get("messages") == [{"role": "user", "content": _Q}]
      and _c0.get("system") == ("Answer the question carefully and completely. Reason it through "
                                "step by step where that helps, say plainly what is uncertain or "
                                "contested, and keep the answer self-contained.")
      and "tools" not in _c0,
      {k: _c0.get(k) for k in ("messages", "system", "tools")})
check("...and the defaults are opus at high effort",
      _c0.get("model") == "claude-opus-5-5" and _c0.get("output_config") == {"effort": "high"},
      (_c0.get("model"), _c0.get("output_config")))

tune.set_many({"consult.model": "claude-sonnet-5-5", "consult.effort": "xhigh"})
_fresh()
_QUEUE.append(_msg(model="claude-sonnet-5-5"))
C.consult(_Q)
tune.reset("consult.model")
tune.reset("consult.effort")
_c1 = _CALLS[0] if _CALLS else {}
check("model and effort follow the knobs",
      _c1.get("model") == "claude-sonnet-5-5" and _c1.get("output_config") == {"effort": "xhigh"},
      (_c1.get("model"), _c1.get("output_config")))

print()
print("3. THE TOOL SHE SEES")
_DOC = ("Ask a stronger model one hard question and think with what comes back.\n\n"
        "For long chains of reasoning, a tricky factual question, or a problem you are stuck on.\n"
        "Not for anything personal or intimate between you and him — those stay between you.\n"
        "Write the question so it stands alone: no names, no private detail, nothing from your\n"
        "memory. Only the question is sent. Takes up to a few minutes.")
_specs = C.consult_tools()
check("armed and keyed, the tool is there", [s.name for s in _specs] == ["consult"],
      [s.name for s in _specs])
check("...and its description is the whole docstring, word for word",
      bool(_specs) and _specs[0].description == _DOC,
      repr(_specs[0].description[:120]) if _specs else "no spec")
os.environ["SP_CONSULT"] = "0"
check("unarmed means absent", C.consult_tools() == [])
os.environ["SP_CONSULT"] = "1"
os.environ.pop("SP_CLAUDE_API_KEY", None)
check("...and so does armed but keyless", C.consult_tools() == [])
_fresh()
_kl = C.consult(_Q)
check("keyless is honest", _kl == "[consult unavailable: no key]" and not _FACTORY_HITS, _kl)
os.environ["SP_CLAUDE_API_KEY"] = _KEY

print()
print("4. THE SHUT DOORS — a plain note back, nothing sent, nothing written")


def _shut(name, enter, leave, want):
    before = _receipts()
    _fresh()
    enter()
    try:
        out = C.consult(_Q)
    finally:
        leave()
    check(name, out.startswith("[") and want in out and not _FACTORY_HITS and not _CALLS
          and _receipts() == before, (out, len(_FACTORY_HITS), len(_receipts()) - len(before)))


_shut("OTR shuts it", AN.enter, AN.leave, AN.WHY)

_real_active = _RP.active
_SCENE = _NS(heat=_NS(level=1))


def _scene_on():
    _RP.active = lambda session: _SCENE


def _scene_off():
    _RP.active = _real_active


_shut("a roleplay scene shuts it", _scene_on, _scene_off, "you are in a scene")


def _presence(mode, intimate):
    return lambda: tune.set_many({"presence.mode": mode, "presence.intimate": intimate})


def _presence_off():
    tune.reset("presence.mode")
    tune.reset("presence.intimate")


_shut("intimate presence shuts it", _presence("narration", True), _presence_off, "not sent")
_presence("narration", False)()
_fresh()
_po = C.consult(_Q)
_presence_off()
check("...but a non-intimate presence mode leaves it open", "not your memory" in _po and _CALLS,
      _po[:100])
_presence("off", True)()
_fresh()
_po2 = C.consult(_Q)
_presence_off()
check("...and so does the intimate flag with no mode running", "not your memory" in _po2, _po2[:100])

print()
print("5. FAILING OPEN OR CLOSED ON THE SCENE CHECK")
# No roleplay engine to ask (it cannot be imported) means there is no scene to be in: open. A
# room that IS loaded but cannot answer is the dangerous case — it might be mid-scene: closed.
import harness.roleplay as _RPPKG  # noqa: E402
_saved_eng = sys.modules.get("harness.roleplay.engine")
delattr(_RPPKG, "engine")                         # `from pkg import sub` checks the attribute first
sys.modules["harness.roleplay.engine"] = None     # ...then the import raises ImportError
try:
    _nr = C.shut_reason("her")
finally:
    sys.modules["harness.roleplay.engine"] = _saved_eng
    _RPPKG.engine = _saved_eng
check("no room to ask (the import fails) is not a scene: open", _nr == "", _nr)


def _boom(session):
    raise RuntimeError("scene store unreadable")


_RP.active = _boom
try:
    _br = C.shut_reason("her")
finally:
    _RP.active = _real_active
check("a room that cannot say whether a scene is running is shut", "scene" in _br, _br)

print()
print("6. HER OWN TIME")
_lt1 = lane.set_unprompted(True)
try:
    tune.set_many({"consult.own_time": False})
    _fresh()
    _ot_off = C.consult(_Q)
    _off_calls = len(_CALLS)
    tune.set_many({"consult.own_time": True})
    _fresh()
    _n0 = set(_receipts())
    _ot_on = C.consult(_Q)
    _new = sorted(set(_receipts()) - _n0)
finally:
    lane.reset(_lt1)
    tune.reset("consult.own_time")
check("own time toggle: off refuses in her own time, and nothing is sent",
      "own time" in _ot_off and _off_calls == 0, (_ot_off, _off_calls))
try:
    _own_rec = json.load(open(_new[-1], encoding="utf-8")) if _new else {}
except Exception:
    _own_rec = {}
check("...on, it is sent, and the receipt says which lane it came from",
      "not your memory" in _ot_on and _own_rec.get("lane") == "own", (_ot_on[:80], _own_rec.get("lane")))
tune.set_many({"consult.own_time": False})
_fresh()
_his_turn = C.consult(_Q)
tune.reset("consult.own_time")
check("...and the toggle does not touch a turn of his", "not your memory" in _his_turn, _his_turn[:80])

print()
print("7. HIS BOX")
_scene_on()
try:
    _fresh()
    _ha = C.ask(_Q, by="him")
finally:
    _scene_off()
check("his box ignores her session doors (a scene is running, it is still sent)",
      _ha.ok and len(_CALLS) == 1, (_ha.ok, _ha.text[:80]))
AN.enter()
try:
    _fresh()
    _ho = C.ask(_Q, by="him")
finally:
    AN.leave()
# EXACTLY the door's note: claude.ask holds net.consult too, so a consult.py that skipped the
# door for him would still send nothing — and would answer "consult failed: ..." instead.
check("...but not off the record", _ho.ok is False and _ho.text == AN.WHY and not _FACTORY_HITS,
      (_ho.ok, _ho.text[:80]))

print()
print("8. EVERY CONSULT IS LOGGED")
_fresh()
_b0 = set(_receipts())
C.consult(_Q)
_nr2 = sorted(set(_receipts()) - _b0)
_raw = open(_nr2[-1], encoding="utf-8").read() if _nr2 else ""
try:
    _rec = json.loads(_raw) if _raw else {}
except Exception:
    _rec = {}
_want = ("model", "effort", "usage", "seconds", "lane", "by", "stop_reason")
check("a receipt is written with model, effort, usage, seconds, lane, by, stop_reason",
      len(_nr2) == 1 and all(k in _rec for k in _want)
      and _rec.get("by") == "her" and _rec.get("lane") == "conversation"
      and _rec.get("model") == "claude-opus-5-5" and _rec.get("effort") == "high",
      {k: _rec.get(k) for k in _want})
check("...and the key is nowhere in it", bool(_raw) and _KEY not in _raw)
try:
    _looks = [json.loads(l) for l in open(os.path.join(os.environ["SP_RESEARCH_RECEIPTS"], "looks.jsonl"),
                                          encoding="utf-8") if l.strip()]
except Exception:
    _looks = []
check("...and the looking ledger has a consult row", bool(_looks) and _looks[-1].get("kind") == "consult"
      and _looks[-1].get("query") == _Q, _looks[-1] if _looks else "no ledger")

_fresh()
_QUEUE.append(_msg(text="", stop="refusal", cat="cyber"))
_rf = C.consult(_Q)
check("refusal is an honest failure", _rf.startswith("[consult failed:") and "cyber" in _rf
      and "not your memory" not in _rf, _rf)
_rf_new = sorted(set(_receipts()) - _b0 - set(_nr2))
check("...and a refusal still leaves a receipt", len(_rf_new) == 1, _rf_new)

# A call that went out and died in transport (timeout, 429, a dropped connection) comes back
# with no stop_reason. It may still have been billed, so it is logged like any other.
def _dying_factory(key, base):
    _FACTORY_HITS.append(base)

    class _Dies:
        def stream(self, **kw):
            _CALLS.append(kw)
            raise TimeoutError("read timed out talking to the API with key %s" % key)
    return _NS(beta=_NS(messages=_Dies()))


_CL._CLIENT_FACTORY = _dying_factory
_fresh()
_b1 = set(_receipts())
try:
    _td = C.consult(_Q)
finally:
    _CL._CLIENT_FACTORY = _factory
_td_new = sorted(set(_receipts()) - _b1)
_td_raw = open(_td_new[-1], encoding="utf-8").read() if _td_new else ""
try:
    _td_rec = json.loads(_td_raw) if _td_raw else {}
except Exception:
    _td_rec = {}
check("a call that died in transport still leaves a receipt: ok False, the error, no key",
      len(_td_new) == 1 and _td_rec.get("ok") is False and "TimeoutError" in str(_td_rec.get("text"))
      and _KEY not in _td_raw and _td.startswith("[consult failed:"),
      (_td, _td_rec.get("ok"), str(_td_rec.get("text"))[:80], _KEY in _td_raw))
_fresh()
_QUEUE.append(_msg(stop="max_tokens"))
_tr = C.consult(_Q)
check("a max_tokens stop is flagged truncated", "truncated" in _tr, _tr[-80:])

print()
print("9. THE PERSONA FRAGMENT RIDES ON THE SAME KNOB")
from harness.personality import persona_layers as _PL  # noqa: E402
check("persona fragment gated on the same knob",
      _PL.KNOBS.get("consult") == "SP_CONSULT" and bool(persona_file("38-consult.md")),
      (_PL.KNOBS.get("consult"), persona_file("38-consult.md")))

print()
print("10. THE ROOM'S SESSION, ASKED WITHOUT IMPORTING THE GATEWAY")
# The gateway runs as `python -m harness.server.app`, so the module serving her is __main__ and
# an `import harness.server.app` elsewhere is a SECOND copy of it. Load app.py again under
# another name — the writer — and have IT record a chat session; the scene door (and the
# wardrobe's rung) must see the session that writer set.
import importlib.util as _ilu  # noqa: E402
from harness.control import room as _ROOM  # noqa: E402
from harness.skills import wardrobe as _WD  # noqa: E402
# located through the import system, not a pinned path (G-SRC-TRAP §3: the server is a package)
_spec = _ilu.spec_from_file_location("g_consult_served_app", _ilu.find_spec("harness.server.app").origin)
_served = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_served)
_LIVE = "g-consult-live-session"
_served._session_of({"session_id": _LIVE})
_RP.active = lambda session: (_NS(heat=_NS(level=3)) if session == _LIVE else None)
try:
    _seen_reason = C.shut_reason("her")
    _rung = _WD._ceiling()[0]
    import harness.server.app as _imported_app  # noqa: E402
    _served_seen, _imported_seen = _served._room_session(), _imported_app._room_session()
finally:
    _RP.active = _real_active
    _ROOM.set_session("default")
check("the scene door sees the session the SERVING copy of app.py recorded",
      _seen_reason == C.SCENE, _seen_reason)
check("...and so does the wardrobe's rung", _rung == 3, _rung)
check("...and so do the panels, through the same door",
      _served_seen == _LIVE and _imported_seen == _LIVE, (_served_seen, _imported_seen))


def _src(rel):
    return code_only(io.open(os.path.join(ROOT, rel), encoding="utf-8").read())


check("the chat handler writes the session through room.set_session",
      "_room . set_session (" in code_only(inspect.getsource(_served._session_of)))
for _rel in ("harness/skills/consult.py", "harness/skills/wardrobe.py"):
    _s = _src(_rel)
    check("%s does not import the gateway to ask for the session" % _rel,
          "harness . server . app" not in _s and "harness.server.app" not in _s
          and "_room_session" not in _s)

print()
print("11. HIS BOX IN THE RESEARCH APP")
# The operator's own consult box (Task 7): his click is the authorization, so it is NOT gated on
# SP_CONSULT; the row is his, and it must never wear her taskbar chip (_NOW/_LAST).
from harness.skills import looking as _LK  # noqa: E402
_LOOKS_P = os.path.join(os.environ["SP_RESEARCH_RECEIPTS"], "looks.jsonl")


def _ledger():
    try:
        return [json.loads(l) for l in open(_LOOKS_P, encoding="utf-8") if l.strip()]
    except Exception:
        return []


os.environ["SP_CONSULT"] = "0"
_fresh()
_before_now, _before_last, _n0 = dict(_LK._NOW), _LK._LAST, len(_ledger())
_QUEUE.append(_msg(text="His careful answer."))
_hr = _LK.his_consult(_Q)
_rows = _ledger()[_n0:]
os.environ["SP_CONSULT"] = "1"
check("not gated on SP_CONSULT: armed off, key present, it still went out",
      len(_CALLS) == 1 and _hr.get("ok") is True and "His careful answer." in str(_hr.get("answer")),
      (len(_CALLS), _hr))
check("his consult is stamped his",
      len(_rows) == 1 and _rows[0].get("by") == "him" and _rows[0].get("kind") == "consult"
      and _rows[0].get("query") == _Q, _rows)
check("his consult does not wear her chip",
      _LK._NOW == _before_now and _LK._LAST is _before_last, (_LK._NOW, _LK._LAST))
check("...and its receipt says whose it was",
      json.load(open(_hr["receipt"], encoding="utf-8")).get("by") == "him", _hr.get("receipt"))
# The ledger row's summary is capped at 800 chars, so the room box must be handed the WHOLE
# answer in the return value (AskRow renders it, final review 2026-10-21). 3000 chars, no cut.
_fresh()
_LONG = ("Claude says this at length. " * 120)[:3000]
_QUEUE.append(_msg(text=_LONG))
_hl = _LK.his_consult(_Q)
check("his consult returns the full untruncated answer (3000 chars)",
      _hl.get("ok") is True and _hl.get("answer") == _LONG and len(_hl["answer"]) == 3000,
      (_hl.get("ok"), len(str(_hl.get("answer")))))
_ui = io.open(os.path.join(ROOT, "ui", "src", "apps", "looks.jsx"), encoding="utf-8").read()
check("the room's AskRow renders the returned answer (rsc-answer), not only ok/error",
      "r.answer" in _ui and "rsc-answer" in _ui)
_fresh()
_n1 = len(_ledger())
_he = _LK.his_consult("   ")
check("an empty question is refused with no call and no row",
      _he.get("ok") is False and not _CALLS and len(_ledger()) == _n1, _he)
_fresh()
_QUEUE.append(_msg(text="", stop="refusal", cat="cyber"))
_hf = _LK.his_consult(_Q)
check("a Claude refusal comes back ok False with the reason, not a raise",
      _hf.get("ok") is False and "cyber" in str(_hf.get("error")), _hf)

from harness.server import panels as _PN  # noqa: E402
_pj = _PN._research_json().get("consult") or {}
check("the research panel reports consult: armed, available, model, why",
      set(_pj) == {"armed", "available", "model", "why"} and _pj["armed"] is True
      and _pj["available"] is True and _pj["model"] == "claude-opus-5-5", _pj)
check("his consult rows show in the research window, not the search window",
      any(r.get("kind") == "consult" for r in _PN._research_json()["looks"])
      and not any(r.get("kind") == "consult" for r in _PN._search_json()["looks"]))
check("the run route serves /v1/consult/run through his_consult",
      '"/v1/consult/run"' in code_only(io.open(_ilu.find_spec("harness.server.app").origin,
                                               encoding="utf-8").read())
      and "his_consult" in code_only(io.open(_ilu.find_spec("harness.server.app").origin,
                                             encoding="utf-8").read()))

finish("G-CONSULT")
