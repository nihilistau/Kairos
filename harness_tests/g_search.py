"""G-SEARCH — one tool, several engines, DDG as the floor. OFFLINE.

THE BUG CLASS. Two tools that both "search" is how she picks the wrong one,
or invents a finding when the one she picked is empty. web_search is the
name. The engines live behind it. Empty is empty.

xAI and Claude are BOTH researchers (G-RESEARCH) and searchers (XaiSearcher,
ClaudeSearcher, each behind its own transport door, never a raw URL in search.py);
the engine that costs a model call is opt-in by backend name, never the default.

    python harness_tests/g_search.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "harness_tests"))
# SANDBOX FIRST (2026-10-21): section 11 flips the search.backend knob, which writes
# the tuning store; without this it would write HER live var/tuning.json.
from _gate import sandbox  # noqa: E402
sandbox("g_search")
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ.pop("SP_SEARCH_BACKEND", None)
os.environ.pop("SP_SEARCH_BRAVE_KEY", None)
os.environ.pop("SP_SEARCH_TAVILY_KEY", None)
os.environ.pop("SP_SEARCH_SEARXNG_URL", None)
os.environ.pop("BRAVE_API_KEY", None)
os.environ.pop("TAVILY_API_KEY", None)

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


from harness.skills import search as S  # noqa: E402
from harness.skills import system_tools as ST  # noqa: E402


# THE BLEND IS STUBBED FOR THE WHOLE GATE (2026-08-20). search_web now asks Wikipedia
# for its top page and prepends it with a REST-summary extract — a LIVE network call.
# The first run of this gate after the blend landed failed two sections on real
# encyclopedia results arriving inside stubbed-engine tests: an OFFLINE gate that hits
# the live wiki measures Wikimedia's uptime. Sections that test the blend itself swap
# in their own fake below.
class _NoWiki(S.WikipediaSearcher):
    def search(self, query, n=5):
        return []


S._WIKI = _NoWiki


print("1. THE DEFAULT IS THE FLOOR")
S.set_backend(None) if hasattr(S, "set_backend") else None
S.set_backend(None)
b = S.backend()
check("default backend is ddg", b.name == "ddg", b.name)
check("ddg is always available", S.DuckDuckGoSearcher().available())
check("brave is not available without a key", not S.BraveSearcher().available())
check("tavily is not available without a key", not S.TavilySearcher().available())
check("searxng is not available without a url", not S.SearXNGSearcher().available())


print("\n2. A DEAD ENGINE FALLS TO DDG, NOT TO SILENCE")
class Dead(S.Searcher):
    name = "dead"
    def available(self):
        return True
    def search(self, query, n=5):
        return [{"title": "[search error: timeout]", "url": "", "snippet": ""}]

class Floor(S.Searcher):
    name = "ddg"
    def available(self):
        return True
    def search(self, query, n=5):
        return [{"title": "hit", "url": "https://example.test/" + query,
                 "snippet": "from the floor"}]

S.set_backend(Dead())
# search_web falls to DuckDuckGoSearcher when empty AND name != ddg.
# Inject the floor by monkeypatching the class used as fallback.
_real = S.DuckDuckGoSearcher
S.DuckDuckGoSearcher = Floor
hits = S.search_web("RTX 3090")
S.DuckDuckGoSearcher = _real
check("a dead paid engine still returns the floor",
      hits and hits[0].get("url", "").startswith("https://example.test/"), hits[:1])

S.set_backend(Floor())
hits2 = S.search_web("anything")
check("the chosen engine is used when it returns hits",
      hits2 and hits2[0]["snippet"] == "from the floor", hits2[:1])


print("\n3. EMPTY IS EMPTY, AND THERE IS STILL ONLY ONE TOOL")
S.set_backend(Floor())
check("an empty query returns no hits, not a guess", S.search_web("  ") == [])
src_st = open(os.path.join(ROOT, "harness", "skills", "system_tools.py"),
              encoding="utf-8").read()
check("web_search is the only search tool in system_tools",
      src_st.count("def web_search") == 1)
check("system_tools.search_web is a thin call into the seam",
      "from harness.skills.search import search_web" in src_st)
check("web_search still wraps looking.begin/end",
      'L.begin("web_search"' in src_st and src_st.count("L.end(") >= 2)
src_ag = open(os.path.join(ROOT, "harness", "agent.py"), encoding="utf-8").read()
check("the agent still offers one web_search, not a second name",
      "web_search" in src_ag and "brave_search" not in src_ag
      and "tavily_search" not in src_ag)


print("\n4. AUTO PICKS A KEYED ENGINE, DEFAULT DOES NOT SURPRISE-BILL")
os.environ["SP_SEARCH_BACKEND"] = "auto"
os.environ["SP_SEARCH_BRAVE_KEY"] = "test-key"
S.set_backend(None)
b_auto = S._pick()
check("auto with a brave key picks brave", b_auto.name == "brave", b_auto.name)
os.environ["SP_SEARCH_BACKEND"] = "ddg"
S.set_backend(None)
b_def = S._pick()
check("explicit ddg does not pick brave even with a key",
      b_def.name == "ddg", b_def.name)
os.environ["SP_SEARCH_BACKEND"] = "brave"
os.environ.pop("SP_SEARCH_BRAVE_KEY", None)
S.set_backend(None)
b_miss = S._pick()
check("a named engine with no key falls to ddg",
      b_miss.name == "ddg", b_miss.name)
os.environ.pop("SP_SEARCH_BACKEND", None)
S.set_backend(None)


print("\n5. THE PAID ENGINES GO THROUGH THEIR OWN DOORS")
src_s = open(os.path.join(ROOT, "harness", "skills", "search.py"), encoding="utf-8").read()
check("search.py does not call api.x.ai",
      "api.x.ai" not in src_s)
check("xAI also has a Researcher (research.py), beside its Searcher",
      "class XaiResearcher" in open(os.path.join(ROOT, "harness", "skills", "research.py"),
                                    encoding="utf-8").read())


print("\n6. THE DOOR MAPS THE KNOBS")
serve = open(os.path.join(ROOT, "serve.py"), encoding="utf-8").read()
for k in ("SP_SEARCH_BACKEND", "SP_SEARCH_BRAVE_KEY", "SP_SEARCH_TAVILY_KEY",
          "SP_SEARCH_SEARXNG_URL"):
    check("%s is mapped in serve.py" % k, k in serve)


print("\n7. THE FIRST THING SHE READS IS SUBSTANCE — the Wikipedia blend")
# "she uses duck duck go and gets whatever is first" (operator, 2026-08-20) — and her
# own time is built on these results. When wiki knows the topic, its page goes FIRST
# with a REST-summary extract attached; the engine's breadth follows, deduped. When
# wiki has nothing (prices, stock, news), the blend adds nothing. All FAKES here:
# deterministic, offline, and the shapes are the real APIs' shapes.


class _FakeWiki(S.WikipediaSearcher):
    def search(self, query, n=5):
        if "aurora" not in query:
            return []
        return [{"title": "Aurora", "url": "https://en.wikipedia.org/wiki/Aurora",
                 "snippet": "natural light display"}]

    def summary(self, title):
        return "An aurora is a natural light display in Earth's upper atmosphere."


class _FakeEngine(S.Searcher):
    name = "fake"

    def available(self):
        return True

    def search(self, query, n=5):
        return [{"title": "Aurora forecast tonight", "url": "https://x.example/f",
                 "snippet": "kp index"},
                {"title": "Aurora", "url": "https://en.wikipedia.org/wiki/Aurora",
                 "snippet": "dupe of the wiki page via the engine"}]


S._WIKI = _FakeWiki
S.set_backend(_FakeEngine())
hits = S.search_web("aurora borealis", 4)
check("the wiki page arrives FIRST, carrying its extract",
      hits and hits[0]["url"].endswith("/wiki/Aurora")
      and "upper atmosphere" in hits[0].get("extract", ""), hits[:1])
check("...and the engine's breadth follows, deduped by url",
      any(h["url"] == "https://x.example/f" for h in hits[1:])
      and sum(1 for h in hits if h["url"].endswith("/wiki/Aurora")) == 1,
      [h["url"] for h in hits])
hits2 = S.search_web("RTX 3090 in stock under $1500", 4)
check("a non-encyclopedic query is untouched (wiki had nothing)",
      hits2 and hits2[0]["url"] == "https://x.example/f", [h["url"] for h in hits2])
# and the reader: an extract the searcher shipped is not overwritten by a page scrape
st = open(os.path.join(ROOT, "harness", "skills", "system_tools.py"),
          encoding="utf-8").read()
check("web_search keeps a shipped extract instead of re-scraping the page",
      'not hits[0].get("extract")' in st)
S._WIKI = _NoWiki
S.set_backend(None)

print("\n8. GROK LIVE SEARCH IS AN ENGINE — and the panel's override-only rule holds")
# 2026-08-21, operator: "adding xAI as a search provider and as default". Default
# means the PROFILE env (search.backend = "xai"); the tuning knob is override-only
# (tune.chosen), so this env-scrubbed gate still lands on the ddg floor — which is
# exactly the surprise-bill guarantee section 4 asserts.
check("xai is a registered engine", "xai" in S._ENGINES)
check("...that satisfies the Searcher protocol", issubclass(S.XaiSearcher, S.Searcher))
os.environ["SP_XAI_KEY_FILE"] = os.path.join(ROOT, "nonexistent-key")
_had_keys = {k: os.environ.pop(k, None) for k in ("SP_XAI_API_KEY", "XAI_API_KEY")}
check("a keyless xai engine reports unavailable", not S.XaiSearcher().available())
for k, v in _had_keys.items():
    if v is not None:
        os.environ[k] = v
os.environ.pop("SP_XAI_KEY_FILE", None)
check("the tuning knob is consulted override-only (tune.chosen, never get)",
      'chosen("search.backend")' in open(os.path.join(ROOT, "harness", "skills",
                                         "search.py"), encoding="utf-8").read())

print()
print("11. THE ENGINE PICK IS LIVE (2026-10-21)")
from harness.tuning import registry as _TUNE  # noqa: E402
S.set_backend(None)
os.environ["SP_XAI_API_KEY"] = "test-key"      # xai must be AVAILABLE or _pick falls to ddg
_TUNE.set_many({"search.backend": "xai"})
_nx = S.backend().name
_TUNE.set_many({"search.backend": "ddg"})
_nd = S.backend().name
_TUNE.reset("search.backend")
os.environ.pop("SP_XAI_API_KEY", None)
check("knob flip is live", _nx == "xai" and _nd == "ddg",
      "xai -> %r, ddg -> %r (same process, no set_backend)" % (_nx, _nd))

print()
print("12. CLAUDE IS AN ENGINE TOO (2026-10-21) -- strict-JSON rows, tool type follows the model")
import json  # noqa: E402
from types import SimpleNamespace as _NS  # noqa: E402
from harness.skills import claude as _CL  # noqa: E402

_CCALLS: list = []
_CQUEUE: list = []


def _cmsg(text, stop="end_turn", cat=None, urls=()):
    return _NS(content=[_NS(type="text", text=text,
                            citations=[_NS(url=u) for u in urls])],
               stop_reason=stop, stop_details=_NS(category=cat) if cat else None,
               model="claude-haiku-5-5",
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
_had_ck = {k: os.environ.pop(k, None) for k in ("SP_CLAUDE_API_KEY", "ANTHROPIC_API_KEY",
                                                 "SP_SEARCH_CLAUDE_MODEL")}
os.environ["SP_CLAUDE_API_KEY"] = "k"
os.environ["SP_CLAUDE_KEY_FILE"] = os.path.join(ROOT, "nonexistent-claude-key")

check("claude is a registered engine that satisfies the Searcher protocol",
      "claude" in S._ENGINES and issubclass(S.ClaudeSearcher, S.Searcher)
      and S.ClaudeSearcher.name == "claude")
check("a keyed claude engine reports available", S.ClaudeSearcher().available())

_rows_json = json.dumps([
    {"title": "A page", "url": "https://a.example/x", "snippet": "from a"},
    {"title": "no url", "url": "", "snippet": "dropped"},
    {"title": "T" * 500, "url": "http://b.example/y", "snippet": "S" * 500},
])
_CCALLS.clear(); _CQUEUE.append(_cmsg("Here you go:\n" + _rows_json + "\nHope that helps."))
_rows = S.ClaudeSearcher().search("rmsnorm", 5)
check("claude searcher returns rows",
      len(_rows) == 2 and _rows[0] == {"title": "A page", "url": "https://a.example/x",
                                       "snippet": "from a"}
      and _rows[1]["url"] == "http://b.example/y"
      and len(_rows[1]["title"]) == 200 and len(_rows[1]["snippet"]) == 300, str(_rows)[:200])
_c0 = _CCALLS[0]
check("claude searcher sends only the query, low effort",
      _c0["output_config"]["effort"] == "low" and "rmsnorm" in _c0["messages"][0]["content"]
      and len(_c0["messages"]) == 1, str(_c0["messages"])[:120])

_TOOL_H = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]
_TOOL_S = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}]
_shape = {}
for _m in ("claude-haiku-5-5", "claude-sonnet-5-5"):
    os.environ["SP_SEARCH_CLAUDE_MODEL"] = _m
    _CCALLS.clear(); _CQUEUE.append(_cmsg(_rows_json))
    S.ClaudeSearcher().search("q", 3)
    _shape[_m] = (_CCALLS[0]["model"], _CCALLS[0].get("tools"))
os.environ.pop("SP_SEARCH_CLAUDE_MODEL", None)
check("haiku gets the basic tool",
      _shape["claude-haiku-5-5"] == ("claude-haiku-5-5", _TOOL_H), str(_shape))
check("sonnet gets the 20260209 tool",
      _shape["claude-sonnet-5-5"] == ("claude-sonnet-5-5", _TOOL_S), str(_shape))

_CCALLS.clear(); _CQUEUE.append(_cmsg(_rows_json))
S.ClaudeSearcher().search("q", 3)
check("model defaults to haiku", _CCALLS[0]["model"] == "claude-haiku-5-5", _CCALLS[0]["model"])
_TUNE.set_many({"search.claude_model": "claude-sonnet-5-5"})
_CCALLS.clear(); _CQUEUE.append(_cmsg(_rows_json))
S.ClaudeSearcher().search("q", 3)
_TUNE.reset("search.claude_model")
check("search.claude_model knob picks the model (override-only, live)",
      _CCALLS[0]["model"] == "claude-sonnet-5-5", _CCALLS[0]["model"])

_CCALLS.clear(); _CQUEUE.append(_cmsg("No JSON, sorry, see sources.",
                                      urls=("https://s.example/1", "https://s.example/1",
                                            "https://s.example/2")))
_srows = S.ClaudeSearcher().search("q", 5)
check("no JSON in the text falls back to the sources, title = url",
      [r["url"] for r in _srows] == ["https://s.example/1", "https://s.example/2"]
      and _srows[0]["title"] == "https://s.example/1", str(_srows))

_CCALLS.clear(); _CQUEUE.append(_cmsg("", stop="refusal", cat="cyber"))
_refused = S.ClaudeSearcher().search("q", 5)
_CCALLS.clear(); _CQUEUE.append(_cmsg("[this is not json ]["))
_garbage = S.ClaudeSearcher().search("q", 5)
S._WIKI = _NoWiki
S.DuckDuckGoSearcher = Floor
S.set_backend(S.ClaudeSearcher())
_CCALLS.clear(); _CQUEUE.append(_cmsg("", stop="refusal", cat="cyber"))
_floored = S.search_web("kairos")
S.DuckDuckGoSearcher = _real
S.set_backend(None)
check("empty on failure so ddg floors",
      _refused == [] and _garbage == [] and _floored
      and _floored[0]["snippet"] == "from the floor", str((_refused, _garbage, _floored[:1])))

_CCALLS.clear()
S.set_backend(None)
_TUNE.set_many({"search.backend": "claude"})
_picked = S.backend().name
os.environ.pop("SP_CLAUDE_API_KEY")
_keyless = S.backend().name
_TUNE.reset("search.backend")
os.environ["SP_CLAUDE_API_KEY"] = "k"
check("search.backend=claude is picked live; keyless falls to the ddg floor",
      _picked == "claude" and _keyless == "ddg", "%s / %s" % (_picked, _keyless))
os.environ.pop("SP_CLAUDE_API_KEY", None)
os.environ.pop("SP_CLAUDE_KEY_FILE", None)
for _k, _v in _had_ck.items():
    if _v is not None:
        os.environ[_k] = _v

print("\nG-SEARCH  %d/%d" % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
