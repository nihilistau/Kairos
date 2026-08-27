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

print(f"\nG-RESEARCH: {_P} pass, {_F} fail")
sys.exit(1 if _F else 0)
