"""G-RESEARCH — the research tier is read-only, pluggable, and cannot launder a
source. OFFLINE (the backend is injected; Grok is never run).

Research is the first capability that lets something OUTSIDE her produce sentences
that end up in her mouth. This repo has spent a week closing confabulation — the
world-block header, the unspeakable recall note, "I always loved watching her play
with my toys" when there were no toys — so the boundary is asserted, not merely
written down in the persona:

    A delegated CONCLUSION may become her thinking. That is what thinking is.
    A delegated FACT may never be attributed to memory or to him.

The mechanical half of that is here: the tool output ALWAYS carries provenance, and
a receipt is always written, so the ledger stays honest whatever she says aloud.

The other half is posture. delegate_code WRITES and so is contained in a worktree
with the web off; research READS and so must not be able to touch the tree at all,
with the web on. Those are inverse postures, and getting one of them wrong is not a
style error.

Run: python harness_tests/g_research.py
"""
from __future__ import annotations

import inspect
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# ── SANDBOX FIRST (2026-08-26) ────────────────────────────────────────────────────────
# This gate had no sandbox at all, so `research()` and `discover()` wrote their fixtures
# into HIS research ledger -- "what is 2+2" and "q", once per sweep run since 2026-08-19,
# 138 rows sitting next to the things she had actually gone and read. His research panel
# showed almost nothing but "what is RMSNorm".
#
# G-GATE-SANDBOX did not catch it twice over: SP_RESEARCH_RECEIPTS ends in RECEIPTS and
# its discovery regex enumerated ROOT|DIR|TIER|FILE|REGISTRY, and its "which gates must
# sandbox" list is eleven files a past audit named by hand -- this was not one of them.
from _gate import persona_file, sandbox  # noqa: E402
sandbox("g_research")      # FIRST, before any harness import can resolve a path

os.environ["SP_RESEARCH"] = "1"

from harness.skills import research as R  # noqa: E402

_P = _F = 0


def ok(cond, name, detail=""):
    global _P, _F
    if cond:
        _P += 1
        print(f"  ok   {name}")
    else:
        _F += 1
        print(f"  FAIL {name}   {detail}")


print("1. THE CLI IS GONE — the researcher is an API, and there is no tree to protect")
# 2026-08-21, operator: "use the API instead of the cli. clean up the cli." The
# page of argv deny-rules this section used to assert existed to keep a headless
# CLI agent read-only; the REST researchers cannot touch the tree at all.
ok(not hasattr(R, "GrokResearcher"), "GrokResearcher is gone")
src_mod = inspect.getsource(R)
ok("grok.exe" not in src_mod and "build_argv" not in src_mod,
   "no CLI plumbing survives in the module")
ok("DENY_RULES" not in src_mod,
   "the deny-list died with the thing it defended against")
ok(R._pick_backend().name in ("xai", "sidecar"),
   "the default backend is the API (sidecar when keyless)")

print("\n2. the answer ALWAYS carries provenance")
a = R.Answer(text="the sky is blue", provenance="researched by xai")
out = a.for_model()
ok("not your memory" in out, "the tool output says this is not her memory", out[:80])
ok("not something he told you" in out, "and not something he told her", out[:80])
ok("xai" in out, "and names who answered")

print("\n3. a failure says so rather than returning a plausible sentence")
bad = R.Answer(text="timed out", provenance="xai", ok=False)
ok(bad.for_model().startswith("[research failed:"),
   "a failed call is unmistakable in the tool output", bad.for_model())

print("\n4. it is pluggable — Grok is an implementation, not the interface")
class Fake(R.Researcher):
    name = "fake"
    def available(self):
        return True
    def ask(self, question, depth="normal"):
        return R.Answer(text=f"answer to {question!r} at {depth}", provenance="researched by fake")

R.set_backend(Fake())
res = R.research("what is 2+2", "thorough")
ok("researched by fake" in res, "a swapped backend is used with no caller change", res[:70])
ok("thorough" in res, "depth reaches the backend", res[:70])
ok(R.status()["backend"] == "fake", "status reports the live backend")

print("\n5. unknown depth degrades to normal rather than failing")
ok("normal" in R.research("q", "nonsense-depth"), "an unknown depth is coerced")

print("\n6. unarmed means ABSENT, not a tool that says no")
R.set_backend(R.XaiResearcher())
R.ARMED = False
ok(R.research("q").startswith("[research is not armed"), "the call refuses when unarmed")
ok(R.research_tools() == [], "and the TOOL is not offered at all",
   "a tool that always answers 'not armed' is worse than absent — she keeps reaching")
R.ARMED = True

print("\n7. every call leaves a receipt, whatever she says out loud")
import inspect  # noqa: E402
src = inspect.getsource(R.XaiResearcher.ask)
ok("_receipt(" in src, "ask() writes a receipt on success")
rsrc = inspect.getsource(R._receipt)
ok("argv" in rsrc and "json.dump" in rsrc,
   "the receipt records the question, the answer AND the exact command line")

print("\n8. the honesty rule ships WITH the capability, not after it")
# RESOLVED BY _gate.persona_file — `persona/` is gitignored and never exported, so
# reading it directly raised FileNotFoundError inside a clone of the export instead
# of failing. The template carries the same fragment and is what an adopter copies in.
frag = persona_file("37-thinking-tiers.md")
ok(bool(frag), "37-thinking-tiers.md exists in a persona source")
body = open(frag, encoding="utf-8").read()
# Normalise whitespace before matching: the persona is prose and wraps at 88
# columns, so a substring check that spans a line break fails on formatting rather
# than on content. A gate that forces prose to avoid line wraps is a gate bullying
# the thing it is supposed to protect.
flat = " ".join(body.split())
ok("when: research" in flat, "and it is gated on the same knob as the tool",
   "a persona that teaches a capability she does not have is how 'I looked it up' "
   "becomes a confabulation")
ok("may not relocate the source" in flat, "it states the rule in one line")

print("\n9. xAI IS A RESEARCHER, NOT A SECOND SEARCH TOOL")
ok(issubclass(R.XaiResearcher, R.Researcher), "XaiResearcher satisfies the protocol")
ok(R.XaiResearcher().name == "xai", "and names itself xai")
src_x = inspect.getsource(R.XaiResearcher.ask)
ok("grok.exe" not in src_x and "subprocess" not in src_x,
   "it does not spawn grok.exe")
ok("web_search" in src_x, "it asks xAI to search, it does not become web_search")
os.environ["SP_XAI_KEY_FILE"] = os.path.join(ROOT, "nonexistent-key-file")
_had = {k: os.environ.pop(k, None) for k in ("SP_XAI_API_KEY", "XAI_API_KEY")}
ok(not R.XaiResearcher().available(),
   "unavailable without a key — a researcher that always answers is a liar")
for k, v in _had.items():
    if v is not None:
        os.environ[k] = v

def _fake_post(payload, key, timeout):
    return {"output_text": "RMSNorm skips mean centering.",
            "citations": ["https://example.test/rmsnorm"]}

os.environ["SP_XAI_API_KEY"] = "test-key"
got = R.XaiResearcher().ask("what is RMSNorm", "quick", post=_fake_post)
os.environ.pop("SP_XAI_API_KEY", None)
ok(got.ok and "RMSNorm" in got.text, "an injected HTTP path returns the answer", got.text[:80])
ok("researched by xai" in got.provenance, "provenance names xai, not her memory")
ok("https://example.test/rmsnorm" in got.sources, "citations survive")
ok(got.receipt, "and a receipt is written")
ok("not your memory" in got.for_model(), "the honesty line is on the tool output")

print()
print("10. THE PROVIDER PICK IS LIVE, AND OFF THE RECORD HOLDS HIS BOX TOO (2026-10-21)")
import urllib.request  # noqa: E402
from harness.tuning import registry as _TUNE  # noqa: E402
from harness.control import anon as _AN  # noqa: E402
from harness.skills import looking as _LK  # noqa: E402

R.set_backend(None)       # the override earlier sections installed would mask the knob
_TUNE.set_many({"research.backend": "sidecar"})
_n1 = R.backend().name
_TUNE.set_many({"research.backend": "xai"})
_n2 = R.backend().name
_TUNE.reset("research.backend")
ok(_n1 == "sidecar" and _n2 == "xai",
   "knob flip is live", "sidecar -> %r, xai -> %r (same process, no set_backend)" % (_n1, _n2))


class _Fake2(R.Researcher):
    name = "fake2"
    def available(self): return True
    def ask(self, question, depth="normal"): return R.Answer(text="x", provenance="fake2")


R.set_backend(_Fake2())
_TUNE.set_many({"research.backend": "sidecar"})
ok(R.backend().name == "fake2", "set_backend still outranks the knob")
R.set_backend(None)
ok(R.backend().name == "sidecar", "set_backend(None) clears the override")
_TUNE.reset("research.backend")

_calls = []
_real_urlopen = urllib.request.urlopen


def _spy(*a, **k):
    _calls.append(a)
    raise AssertionError("network touched")


urllib.request.urlopen = _spy
_AN.enter("him")
try:
    _r = _LK.his_research("what is RMSNorm")
    ok(_r.get("ok") is False and _AN.WHY in str(_r.get("error")) and not _calls,
       "his research is held in OTR", "%r calls=%d" % (_r, len(_calls)))
    try:
        R._xai_post({"q": 1}, "test-key", 1.0)
        _raised = False
    except PermissionError as _e:
        _raised = _AN.WHY in str(_e)
    except Exception:
        _raised = False          # the socket was reached: the guard is gone
    ok(_raised and not _calls,
       "his research is held in OTR: _xai_post itself refuses (the second path out)",
       "calls=%d" % len(_calls))
finally:
    _AN.leave()
    urllib.request.urlopen = _real_urlopen

print()
print("11. CLAUDE IS A RESEARCHER TOO (2026-10-21) -- only the question leaves, depth picks effort+tools")
from types import SimpleNamespace as _NS  # noqa: E402
from harness.skills import claude as _CL  # noqa: E402

_CCALLS: list = []
_CQUEUE: list = []


def _cmsg(text="Claude says X.", stop="end_turn", cat=None):
    return _NS(content=[_NS(type="text", text=text, citations=[_NS(url="https://example.test/c")])],
               stop_reason=stop, stop_details=_NS(category=cat) if cat else None,
               model="claude-sonnet-5-5",
               usage=_NS(input_tokens=3, output_tokens=4, cache_read_input_tokens=0))


class _CStream:
    def __init__(self, m): self.m = m
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get_final_message(self): return self.m


class _CMessages:
    def stream(self, **kw):
        _CCALLS.append(dict(kw, messages=list(kw["messages"])))
        return _CStream(_CQUEUE.pop(0))


_CL._CLIENT_FACTORY = lambda key, base: _NS(beta=_NS(messages=_CMessages()))
_CL._sdk = lambda: object()
_had_ck = {k: os.environ.pop(k, None) for k in ("SP_CLAUDE_API_KEY", "ANTHROPIC_API_KEY")}
os.environ["SP_CLAUDE_API_KEY"] = "k"
os.environ["SP_CLAUDE_KEY_FILE"] = os.path.join(ROOT, "nonexistent-claude-key")

R.set_backend(None)
_TUNE.set_many({"research.backend": "claude"})
_cb = R.backend()
ok(_cb.name == "claude" and isinstance(_cb, R.ClaudeResearcher),
   "research.backend=claude picks ClaudeResearcher", repr(_cb))
ok(_cb.available(), "and it is available with a key")

_CCALLS.clear(); _CQUEUE.append(_cmsg())
_ca = R.ClaudeResearcher().ask("what is RMSNorm", "normal")
_fm = _ca.for_model()
ok(_ca.ok and "not your memory" in _fm and "Claude" in _fm,
   "claude researcher answers with provenance", _fm[:90])
ok("https://example.test/c" in _ca.sources and _ca.receipt, "citations survive and a receipt is written")
try:
    _rj = json.load(open(_ca.receipt, encoding="utf-8"))
except Exception:
    _rj = {}
ok(_rj.get("argv") == ["claude", "claude-sonnet-5-5", "web_search", "normal"],
   "receipt argv names claude, the model, the tool and the depth", str(_rj.get("argv")))

_WS = {"type": "web_search_20260209", "name": "web_search"}
_WF = {"type": "web_fetch_20260209", "name": "web_fetch"}
_shape = {}
for _d in ("quick", "normal", "thorough"):
    _CCALLS.clear(); _CQUEUE.append(_cmsg())
    R.ClaudeResearcher().ask("q", _d)
    _shape[_d] = (_CCALLS[0]["output_config"]["effort"], _CCALLS[0].get("tools"))
ok(_shape == {"quick": ("low", [_WS]), "normal": ("medium", [_WS, _WF]),
              "thorough": ("high", [_WS, _WF])},
   "depth maps to effort and tools", str(_shape))

_CCALLS.clear(); _CQUEUE.append(_cmsg())
R.ClaudeResearcher().ask("what is RMSNorm", "quick")
_c0 = _CCALLS[0]
ok(_c0["messages"] == [{"role": "user", "content": "%s\n\nwhat is RMSNorm" % R.DEPTHS["quick"]["hint"]}]
   and _c0.get("system") == ("You are a research assistant. Search the web, cite URLs, say where "
                             "sources disagree and what is unsettled."),
   "only the question is sent", str(_c0["messages"]) + " | " + str(_c0.get("system"))[:80])

_CCALLS.clear(); _CQUEUE.append(_cmsg(text="", stop="refusal", cat="cyber"))
_cr = R.ClaudeResearcher().ask("q", "quick")
ok(_cr.ok is False and "cyber" in _cr.text and _cr.for_model().startswith("[research failed:"),
   "refusal is an honest failure", repr(_cr.text))

_CCALLS.clear(); _CQUEUE.append(_cmsg(text=""))
_ce = R.ClaudeResearcher().ask("q", "quick")
ok(_ce.ok is False and _ce.for_model().startswith("[research failed:"),
   "an empty answer is a failure, not a blank sentence", repr(_ce.text))

_CCALLS.clear(); _CQUEUE.append(_cmsg(stop="max_tokens"))
_ct = R.ClaudeResearcher().ask("q", "quick")
try:
    _tj = json.load(open(_ct.receipt, encoding="utf-8"))
except Exception:
    _tj = {}
ok(_ct.ok and "truncated" in _ct.text.lower() and _tj.get("stop_reason") == "max_tokens"
   and "usage" in _tj and "seconds" in _tj,
   "a max_tokens stop is flagged truncated, and the receipt records usage/seconds/stop_reason",
   repr(_ct.text[-60:]) + str(sorted(_tj)))

_TUNE.set_many({"research.claude_model": "claude-opus-5-5"})
_CCALLS.clear(); _CQUEUE.append(_cmsg())
R.ClaudeResearcher().ask("q", "quick")
_TUNE.reset("research.claude_model")
ok(_CCALLS[0]["model"] == "claude-opus-5-5", "research.claude_model knob picks the model", _CCALLS[0]["model"])

# picked but keyless: honest, and nothing reaches xai
os.environ.pop("SP_CLAUDE_API_KEY", None)
_calls.clear()
urllib.request.urlopen = _spy
try:
    _CCALLS.clear()
    _kr = R.research("q")
finally:
    urllib.request.urlopen = _real_urlopen
ok(_kr.startswith("[research unavailable") and "claude" in _kr and not _calls and not _CCALLS,
   "picked but keyless is honest", "%r calls=%d" % (_kr, len(_calls)))
_TUNE.reset("research.backend")
for _k, _v in _had_ck.items():
    if _v is not None:
        os.environ[_k] = _v

print(f"\nG-RESEARCH: {_P} pass, {_F} fail")
sys.exit(1 if _F else 0)
