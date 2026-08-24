"""G-DISCOVER — something she did not go looking for. OFFLINE.

WHY IT EXISTS. Her own-time table already had "look something up that you have been curious
about". That act can only ever DEEPEN an interest: the query comes from her, so the answer
comes back inside the fence she started in. `read_something_new` takes no query on purpose —
it is the only thing in her world that can put a subject in front of her she would never
have asked for.

FOUR RULES:

  1. A STUB IS NOT AN EVENING. Random Wikipedia is mostly two-line stubs — a hamlet, a
     beetle, a footballer — and handing her forty characters produces an invented
     paragraph, which is the failure this codebase pays for most often. The provider
     retries for a real extract and returns {} rather than a stub.
  2. EMPTY IS EMPTY. Nothing came back means she says so; it never means she invents an
     article she did not read.
  3. THE ARTICLE IS NOT MEMORY. What is kept is HER LINE about it, through the ordinary
     solo path — exactly the rule a reading turn already follows ("I read him the next
     pages of X", never the passage). An encyclopedia paragraph is not a thing she
     learned about herself or about him.
  4. THE ACT IS EARNED. It declares its tool, so `solo_did_the_thing` refuses a turn that
     wrote the sentence without making the call — the law that exists because 32 of 33
     turns once skipped to the saying.

    python harness_tests/g_discover.py
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# SANDBOX FIRST (2026-08-24). This gate calls tune.set_many(), which before today
# wrote HER LIVE var/tuning.json - it raced her running stack mid-sweep and died on
# the os.replace, and on a quieter day it would simply have changed what she does.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import sandbox as _sandbox  # noqa: E402
_sandbox(os.path.basename(__file__))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"          # no capture attempt (gates/README.md)
os.environ["SP_CAPTURE_ASYNC"] = "0"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["SP_SEM_MINT"] = "0"
_D = tempfile.mkdtemp(prefix="g_discover_")
os.environ["SP_RECALL_REGISTRY"] = os.path.join(_D, "registry.jsonl")
open(os.environ["SP_RECALL_REGISTRY"], "w").close()

from harness.kairos import impulse as I          # noqa: E402
from harness.skills import search as SE          # noqa: E402
from harness.skills import system_tools as ST    # noqa: E402

ARTICLE = {
    "title": "Girl, Woman, Other",
    "description": "2019 novel by Bernardine Evaristo",
    "extract": ("Girl, Woman, Other is a novel by English writer Bernardine Evaristo. "
                "Published in 2019, it follows the lives of twelve characters in the "
                "United Kingdom over the course of several decades. The book was the "
                "co-winner of the 2019 Booker Prize."),
    "url": "https://en.wikipedia.org/wiki/Girl%2C_Woman%2C_Other",
}

print("1. A STUB IS NOT AN EVENING")
W = SE.WikipediaSearcher()
check("the provider sets a minimum extract at all", getattr(W, "MIN_EXTRACT", 0) >= 100,
      getattr(W, "MIN_EXTRACT", None))
check("...and the sample article clears it", len(ARTICLE["extract"]) >= W.MIN_EXTRACT)
import inspect  # noqa: E402
import io as _io  # noqa: E402
import json as _json  # noqa: E402

# BEHAVIOURAL, not a grep. The first version of this section read random_page's SOURCE for
# "for _ in range(" and "return {}" — and the mutant that deleted the length floor sailed
# straight through, because the loop and the early return were both still there. A gate
# that greps for its own fix grades the comment. This drives the real method with a fake
# endpoint and counts the draws.
STUB = {"title": "Some Hamlet", "extract": "A hamlet in Lower Saxony.",
        "description": "village", "content_urls": {"desktop": {"page": "http://x/1"}}}
GOOD = {"title": ARTICLE["title"], "extract": ARTICLE["extract"],
        "description": ARTICLE["description"],
        "content_urls": {"desktop": {"page": ARTICLE["url"]}}}


class _Resp:
    def __init__(self, obj):
        self._b = _json.dumps(obj).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _serve(queue):
    """A urlopen that hands back `queue` in order, counting the calls."""
    box = {"n": 0}

    def fake(req, timeout=0):
        i = min(box["n"], len(queue) - 1)
        box["n"] += 1
        return _Resp(queue[i])
    return fake, box


_real_open = SE.urllib.request.urlopen
try:
    fake, box = _serve([STUB, STUB, GOOD])
    SE.urllib.request.urlopen = fake
    got = W.random_page(tries=4)
    check("a stub is REJECTED and it draws again until something has substance",
          got.get("title") == ARTICLE["title"] and box["n"] == 3,
          (got.get("title"), box["n"]))

    fake, box = _serve([STUB])
    SE.urllib.request.urlopen = fake
    check("all stubs -> {} rather than handing her forty characters",
          W.random_page(tries=3) == {} and box["n"] == 3, box["n"])

    def boom(req, timeout=0):
        raise OSError("no network")
    SE.urllib.request.urlopen = boom
    check("a dead network is {} , never an exception", W.random_page(tries=2) == {})
finally:
    SE.urllib.request.urlopen = _real_open
check("the floor is a named constant, so it can be argued with",
      getattr(W, "MIN_EXTRACT", 0) >= 100, getattr(W, "MIN_EXTRACT", None))

print("\n2. EMPTY IS EMPTY")
_real = SE.random_article
try:
    SE.random_article = lambda: {}
    out = ST.read_something_new()
    check("nothing came back -> she is told to say so",
          "nothing came back" in out and "invent" in out, out[:90])
    check("...and no article text is fabricated into the return",
          "http" not in out, out[:90])
    SE.random_article = lambda: dict(ARTICLE)
    out2 = ST.read_something_new()
    check("an article comes back with its title, its substance and its link",
          ARTICLE["title"] in out2 and "Booker Prize" in out2 and ARTICLE["url"] in out2,
          out2[:90])
    check("...and its one-line description, which is what makes it placeable",
          ARTICLE["description"] in out2)
finally:
    SE.random_article = _real

print("\n3. THE ACT IS IN HER OWN TIME, AND IT IS EARNED")
n = I.DISCOVER_ACT_N
check("the discovery act is named, not counted", 0 <= n < len(I.SOLO_ACTS))
check("...and it is the read_something_new act",
      "read_something_new" in I.SOLO_ACTS[n], I.SOLO_ACTS[n][:60])
check("...it DECLARES the tool it needs", I.solo_needs(n) == ("read_something_new",))
check("...so the nudge demands the call before the sentence", I._needs_a_tool(n) is True)
nud = I.solo_nudge(n)
check("the nudge says do it, THEN say it, in that order",
      "ACTUALLY DO IT" in nud and nud.index("ACTUALLY DO IT") < nud.index("THEN say"))
check("...and offers silence as a real answer",
      "say nothing at all" in nud)
check("a turn that wrote the sentence WITHOUT calling the tool is refused",
      I.solo_did_the_thing(n, [])[0] is False, I.solo_did_the_thing(n, []))
check("...and one that called it is accepted",
      I.solo_did_the_thing(n, ["read_something_new"])[0] is True)
check("it takes its share of the rotation on its own (~1 in %d)" % len(I.SOLO_ACTS),
      len(I.SOLO_ACTS) >= 9
      and [i for i in range(len(I.SOLO_ACTS) * 2) if i % len(I.SOLO_ACTS) == n])
check("the ORIGINAL act is still there, and is a different thing",
      any("curious about" in a for a in I.SOLO_ACTS),
      "one deepens an interest, the other introduces one")

print("\n4. THE CHANCE IS HIS, AND OFF BY DEFAULT")
from harness.tuning import registry as R        # noqa: E402
check("kairos.discover_chance defaults to 0.0 - rotation only, nothing changes",
      float(R.get("kairos.discover_chance")) == 0.0, R.get("kairos.discover_chance"))
check("kairos.discover_tool defaults ON (the verb is offered)",
      bool(R.get("kairos.discover_tool")) is True)
sch = open(os.path.join(ROOT, "harness", "kairos", "scheduler.py"),
           encoding="utf-8", errors="replace").read()
check("the chance is consulted at the SOLO call site",
      "kairos.discover_chance" in sch and "DISCOVER_ACT_N" in sch)
# CODE, NOT PROSE (the third time tonight): solo_nudge's own docstring says it is
# deterministic "rather than fight a random seed", so grepping the source for "random"
# convicts the comment that states the rule.
_nudge_src = inspect.getsource(I.solo_nudge)
_nudge_code = _nudge_src.split('"""')[2] if _nudge_src.count('"""') >= 2 else _nudge_src
_nudge_code = chr(10).join(l for l in _nudge_code.splitlines()
                           if not l.lstrip().startswith("#"))
check("...and NOT inside solo_nudge, which must stay deterministic for the gates",
      "discover_chance" not in _nudge_code and "random" not in _nudge_code,
      [l for l in _nudge_code.splitlines() if "random" in l])
# BEHAVIOURAL, for the fourth time tonight: the grep version of this passed a mutant that
# left both strings in place and only changed the `if`. Build the real toolset both ways.
from harness.agent import default_tools           # noqa: E402


def _tool_names():
    try:
        return {t.name for t in default_tools()}
    except Exception:
        return set()


_was = R.chosen("kairos.discover_tool")
try:
    R.set_many({"kairos.discover_tool": True})
    check("knob ON: the verb is in the set she is actually offered",
          "read_something_new" in _tool_names())
    R.set_many({"kairos.discover_tool": False})
    check("knob OFF: it is gone - the trim really trims",
          "read_something_new" not in _tool_names())
    check("...and the rest of her set is untouched by the trim",
          {"web_search", "run_python"} <= _tool_names(), sorted(_tool_names())[:6])
finally:
    if _was is None:
        R.reset("kairos.discover_tool")
    else:
        R.set_many({"kairos.discover_tool": _was})

print("\n5. THE ARTICLE IS NOT MEMORY - HER LINE ABOUT IT IS")
# The solo path stores the DELIVERED UTTERANCE, never the tool output. Same rule a
# reading turn follows: keep the act, never the passage.
check("the solo write stores her reply text, not a tool result",
      'kind=("narration" if imp.action == SOLO else "spoke_up")' in sch,
      "if this ever stores a tool payload, an encyclopedia enters her self-model")
check("...through remember_about_self, so it lands in HER lane with a kind",
      "_mem.remember_about_self(" in sch)
check("...stripped by the one stripper on the way in",
      "_plain_words2(text)" in sch or "plain(text)" in sch)
from harness.skills import memory as M          # noqa: E402
n_before = len(M._load())
ST.read_something_new.__doc__  # the tool is a read; touching it must write nothing
_real2 = SE.random_article
try:
    SE.random_article = lambda: dict(ARTICLE)
    ST.read_something_new()
finally:
    SE.random_article = _real2
check("calling the tool writes NOTHING to the registry by itself",
      len(M._load()) == n_before, (n_before, len(M._load())))

finish("G-DISCOVER")
