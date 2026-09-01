"""G-LOOKING — a look is visible, or it did not happen. OFFLINE.

THE BUG THIS EXISTS FOR. 2026-08-19 15:39–16:08 she told him she had been
researching neural architectures and immersive presence. Gateway log:

    15:41  round=0 is_tool=False calls=0
    15:52  is_tool=claim looked-up  (the hold fired once)
    15:55  round=0 is_tool=False calls=0   — "give me a minute to scan"
    16:08  round=0 is_tool=False calls=0   — synthesised RAG/affective-memory

SP_RESEARCH was off. web_search was never called. One receipt exists in the
whole tree, from 2026-07-31, about RMSNorm. The room had no surface that
could have shown the absence: no chip, no window, no SSE start event.

So the seam is the look itself, not a caller that remembers to announce it.
web_search and research() both begin/end here. Pulse and /v1/research read
here. A chip that says "researching" while nothing is running is a lie.

    python harness_tests/g_looking.py
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import _src as _srcmod  # noqa: E402
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"

_TMP = tempfile.mkdtemp(prefix="g-looking-")
os.environ["SP_RESEARCH_RECEIPTS"] = _TMP

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


from harness.skills import looking as L  # noqa: E402

L._NOW = {}      # per-thread map since 2026-08-24 (audit B10)
L._LAST = None
L._LISTENERS.clear()


print("1. IN-FLIGHT IS THE SEAM")
st0 = L.status()
check("nothing in flight at rest", st0.get("inflight") is None, st0.get("inflight"))
heard = []
unsub = L.subscribe(lambda ev: heard.append(ev))
row = L.begin("web_search", "RMSNorm vs LayerNorm")
st1 = L.status()
check("begin puts a look in flight",
      bool(st1.get("inflight")) and st1["inflight"]["query"].startswith("RMSNorm"),
      st1.get("inflight"))
check("begin emits a start event",
      heard and heard[-1].get("phase") == "start" and heard[-1].get("q"),
      heard[-1] if heard else None)
done = L.end(True, "RMSNorm skips mean centering.", sources=["https://example.test/rmsnorm"],
             title="RMSNorm vs LayerNorm")
st2 = L.status()
check("end clears in-flight", st2.get("inflight") is None, st2.get("inflight"))
check("end keeps last",
      (st2.get("last") or {}).get("title") == "RMSNorm vs LayerNorm",
      st2.get("last"))
check("end emits a done event",
      heard and heard[-1].get("phase") == "done" and heard[-1].get("ok") is True,
      heard[-1] if heard else None)
# Bounce restore MUST be asserted against THIS look, before any later end().
L._LAST = None
L._NOW = {}      # per-thread map since 2026-08-24 (audit B10)
restored = L.status()
check("status rereads last from the ledger after a bounce",
      (restored.get("last") or {}).get("title") == "RMSNorm vs LayerNorm"
      or "RMSNorm" in ((restored.get("last") or {}).get("query") or ""),
      restored.get("last"))
unsub()
heard2 = []
unsub2 = L.subscribe(lambda ev: heard2.append(ev))
unsub2()
L.begin("web_search", "should not hear")
L.end(False, "nope")
check("a dead subscriber is not called", not heard2, heard2)


print("\n2. THE LEDGER IS APPEND-ONLY")
looks_path = os.path.join(_TMP, "looks.jsonl")
check("end wrote looks.jsonl", os.path.isfile(looks_path), looks_path)
listed = L.list_looks(10)
check("list_looks returns the web_search look",
      any((r.get("kind") == "web_search" and "RMSNorm" in (r.get("title") or r.get("query") or ""))
          for r in listed),
      listed[:2])


print("\n3. CALLERS GO THROUGH THE SEAM, NOT AROUND IT")
src_web = open(os.path.join(ROOT, "harness", "skills", "system_tools.py"),
               encoding="utf-8").read()
check("web_search begins a look",
      "L.begin(\"web_search\"" in src_web or "L.begin('web_search'" in src_web)
check("web_search ends a look on success and failure",
      src_web.count("L.end(") >= 2)
src_res = open(os.path.join(ROOT, "harness", "skills", "research.py"),
               encoding="utf-8").read()
check("research() begins a look",
      "L.begin(\"research\"" in src_res or "L.begin('research'" in src_res)
check("research() ends a look on success and on raise",
      src_res.count("L.end(") >= 2)
src_app = _srcmod.pkg("harness", "server")
check("the pulse carries research",
      'out["research"]' in src_app)
check("GET /v1/research exists",
      '"/v1/research"' in src_app and "_research_json" in src_app)
check("SSE subscribes at the seam, not in each tool",
      "_L.subscribe(on_look)" in src_app)
check("SSE looking events are typed {looking: ...}",
      '{"looking": ev}' in src_app or "{'looking': ev}" in src_app)


print("\n4. THE ROOM HAS A WINDOW AND A CHIP FOR THIS, NOT A SECOND STORE")
reg = open(os.path.join(ROOT, "ui", "src", "appRegistry.jsx"), encoding="utf-8").read()
check("the dock has a research app",
      "id: 'research'" in reg and "css: 'rsc'" in reg)
rsc = open(os.path.join(ROOT, "ui", "src", "apps", "Research.jsx"), encoding="utf-8").read()
# 2026-08-21: the row renderer moved into looks.jsx, SHARED with the new search
# window — one ledger, one renderer. The expand behaviour lives there now.
lks = open(os.path.join(ROOT, "ui", "src", "apps", "looks.jsx"), encoding="utf-8").read()
check("the window expands a title to the returned text (looks.jsx, shared)",
      "LookRows" in rsc and "rsc-head" in lks and "r.summary" in lks)
check("her rows are read-only — the only write is HIS manual box",
      "api.research" in rsc and "researchRun" in rsc and "Write" not in rsc)
check("...and every row says whose it is", "ByChip" in lks and "rsc-by" in lks)
chip = open(os.path.join(ROOT, "ui", "src", "main.jsx"), encoding="utf-8").read()
check("the taskbar has a LookingChip next to presence",
      "LookingChip" in chip and "<Presence" in chip
      and chip.index("LookingChip") < chip.index("<Presence"))
css = open(os.path.join(ROOT, "ui", "src", "room.css"), encoding="utf-8").read()
check("rsc-chip and rsc-row are styled",
      ".rsc-chip" in css and ".rsc-row" in css)
api = open(os.path.join(ROOT, "ui", "src", "api.js"), encoding="utf-8").read()
check("the client has one reader, /v1/research",
      "export const research" in api and "/v1/research" in api)


print("\n5. SHE CAN READ THE LEDGER")
empty = L.my_research()
# we wrote looks in §1, so this tmp ledger is not empty
check("my_research reports a look that happened",
      "RMSNorm" in empty or "web_search" in empty, empty[:200])
L._NOW = {}      # per-thread map since 2026-08-24 (audit B10)
# a fresh tmp with no rows
import tempfile as _tf
_empty = _tf.mkdtemp(prefix="g-looking-empty-")
old = os.environ.get("SP_RESEARCH_RECEIPTS")
os.environ["SP_RESEARCH_RECEIPTS"] = _empty
# list_looks reads _root() each call, so this is a different ledger
blank = L.my_research()
os.environ["SP_RESEARCH_RECEIPTS"] = old
check("an empty ledger says so, and tells her not to invent",
      "have not looked anything up" in blank and "Do not invent" in blank, blank)
src_ag = open(os.path.join(ROOT, "harness", "agent.py"), encoding="utf-8").read()
check("my_research is always offered, not gated on SP_RESEARCH",
      "looking_tools" in src_ag)
check("looking_tools advertises my_research",
      any(t.name == "my_research" for t in L.looking_tools()))


print("\n6. HIS AND HERS — one ledger, whose-is-whose never guessed (2026-08-21)")
# His manual boxes in the room write by="him"; every tool call of hers defaults
# to "her". The taskbar chip and her my_research feed both read this field.
import tempfile as _tf6
_led6 = _tf6.mkdtemp(prefix="g-looking-by-")
_old6 = os.environ.get("SP_RESEARCH_RECEIPTS")
os.environ["SP_RESEARCH_RECEIPTS"] = _led6
try:
    row = L.begin("web_search", "her query")
    check("begin() defaults by to her", row.get("by") == "her", row)
    done = L.end(True, "found it", ["https://x.test"], title="her query")
    check("...and end() carries it to the ledger row", done.get("by") == "her", done)
    L._write({"kind": "web_search", "query": "his query", "by": "him",
              "ok": True, "ended": 2e9, "title": "his query",
              "summary": "his result", "phase": "done"})
    rows = L.list_looks(5)
    check("list_looks surfaces by on every row",
          all(r.get("by") in ("him", "her") for r in rows), rows)
    check("a legacy row with no by is normalized to hers",
          (lambda: (L._write({"kind": "web_search", "query": "old row",
                              "ok": True, "ended": 1.0, "phase": "done"}),
                    [r for r in L.list_looks(10) if r["query"] == "old row"]
                    [0].get("by"))[-1] == "her")())
    feed = L.my_research(10)
    check("my_research marks his rows as his, not her doing",
          "his search, not yours" in feed and "his query" in feed, feed[:200])
    # THE CHIP IS HERS: status()'s ledger fallback must skip his rows — his
    # search wore her "looked up" face within a minute of the run route landing.
    L._NOW = {}      # per-thread map since 2026-08-24 (audit B10)
    L._LAST = None
    st = L.status()
    check("status()'s last-look fallback never wears his rows",
          (st.get("last") or {}).get("by") != "him", st.get("last"))
    # his_search never touches the in-flight seam
    class _FloorEngine:
        name = "ddg"
        def available(self):
            return True
        def search(self, q, n=5):
            return [{"title": "hit", "url": "https://f.test/" + q, "snippet": "s"}]
    from harness.skills import search as S6
    S6.set_backend(_FloorEngine())
    L._NOW = {}      # per-thread map since 2026-08-24 (audit B10)
    L._LAST = None
    r = L.his_search("manual box", 3)
    check("his_search runs the real engine seam and returns hits",
          r.get("ok") and r["hits"], r)
    check("...writes the row by=him", r["row"].get("by") == "him", r.get("row"))
    check("...and never touches the in-flight chip (hers)",
          not L._NOW and L._LAST is None)   # the empty per-thread map (audit B10)
    S6._BACKEND = None
finally:
    if _old6 is None:
        os.environ.pop("SP_RESEARCH_RECEIPTS", None)
    else:
        os.environ["SP_RESEARCH_RECEIPTS"] = _old6

print("\nG-LOOKING  %d/%d" % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
