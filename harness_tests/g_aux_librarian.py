"""G-AUX-LIBRARIAN — the quiet librarians: structured output only, her-conditioned
retrieval, a spine-aware rerank, a warm index, a candidate lane that waits its turn. OFFLINE.

A fake sidecar in-process (stdlib HTTP) plays both doors — /v1/models, /v1/chat/completions
with SCRIPTED replies, /v1/embeddings with deterministic vectors — so the REAL client,
archive, rank, research and summarize code is exercised on the wire.

    python harness_tests/g_aux_librarian.py
"""
from __future__ import annotations

import hashlib
import json
import io
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ.setdefault("SP_DAEMON_URL", "http://127.0.0.1:9")
os.environ["SP_CAPTURE_ASYNC"] = "0"
REG = os.path.join(tempfile.mkdtemp(prefix="g_aux_"), "registry.jsonl")
open(REG, "w").close()
os.environ["SP_RECALL_REGISTRY"] = REG
IDX = tempfile.mkdtemp(prefix="g_aux_idx_")
os.environ["SP_AUX_INDEX_DIR"] = IDX
os.environ["SP_AUX"] = "1"
os.environ.pop("SP_AUX_API_KEY_FILE", None)

# ── the fake sidecar ────────────────────────────────────────────────────────────────
SEEN = {"paths": [], "bodies": [], "embedded": []}
REPLIES: list = []          # scripted chat replies, popped in order; "" when empty


def _vec(text: str, dim: int = 8):
    h = hashlib.sha256(text.encode("utf-8")).digest()
    v = [((b / 255.0) - 0.5) for b in h[:dim]]
    # bias: texts sharing a keyword get a shared direction, so cosine means something
    for kw, axis in (("lighthouse", 0), ("tides", 1), ("kettle", 2)):
        if kw in text.lower():
            v[axis] += 2.0
    return v


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        SEEN["paths"].append(self.path)
        if self.path == "/v1/models":
            self._send({"data": [{"id": "fake-a"}, {"id": "fake-b"}]})
        elif self.path == "/health":
            self._send({"status": "ok"})
        else:
            self.send_error(404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        SEEN["paths"].append(self.path); SEEN["bodies"].append(body)
        if self.path == "/v1/embeddings":
            texts = body.get("input", [])
            SEEN["embedded"].extend(texts)
            self._send({"data": [{"index": i, "embedding": _vec(t)} for i, t in enumerate(texts)]})
        elif self.path == "/v1/chat/completions":
            reply = REPLIES.pop(0) if REPLIES else ""
            self._send({"choices": [{"message": {"role": "assistant", "content": reply}}]})
        else:
            self.send_error(404)


srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["SP_AUX_CHAT_URL"] = "http://127.0.0.1:%d" % PORT
os.environ["SP_AUX_EMBED_URL"] = "http://127.0.0.1:%d" % PORT

from harness.sidecar import client as C          # noqa: E402
from harness.tuning import registry as R         # noqa: E402

print("1. THE CLIENT — structured output only, a model list, reachability, a live model choice")
REPLIES[:] = ['{"answer": "no"}']
d = C.chat_json([{"role": "user", "content": "is water dry?"}], keys=["answer"])
check("chat_json returns the dict for a JSON reply", d == {"answer": "no"}, d)
check("...and the ask named the keys and said JSON only",
      "JSON" in SEEN["bodies"][-1]["messages"][-1]["content"] and '"answer"' in SEEN["bodies"][-1]["messages"][-1]["content"])
REPLIES[:] = ['```json\n{"answer": "yes", "why": "x"}\n```']
check("fences are stripped; extra keys tolerated", (C.chat_json([{"role": "user", "content": "q"}], keys=["answer"]) or {}).get("answer") == "yes")
REPLIES[:] = ["Sure! Water is wet, generally speaking."]
check("prose is None — fail closed", C.chat_json([{"role": "user", "content": "q"}], keys=["answer"]) is None)
REPLIES[:] = ['{"other": 1}']
check("a reply missing a key is None", C.chat_json([{"role": "user", "content": "q"}], keys=["answer"]) is None)
REPLIES[:] = ['{"answer": "no"}']
check("judge via JSON: no -> False", C.judge("is it?") is False)
REPLIES[:] = ["not json", "YES."]
check("judge falls back to the one-word ask: YES -> True", C.judge("is it?") is True)
REPLIES[:] = ["hmm", "maybe"]
check("neither shape -> None (no ruling)", C.judge("is it?") is None)
ids = C.list_models()
n_before = len([p for p in SEEN["paths"] if p == "/v1/models"])
ids2 = C.list_models()
n_after = len([p for p in SEEN["paths"] if p == "/v1/models"])
check("list_models reads the door and caches", ids == ["fake-a", "fake-b"] and ids2 == ids and n_after == n_before, (ids, n_before, n_after))
check("reachable: chat up, embed up (same fake), a dead port down",
      C.reachable("chat") and C.reachable("embed"))
_was = R.chosen("aux.chat_model")
try:
    R.set_many({"aux.chat_model": "fake-b"})
    check("chat_model() prefers the panel's choice over the profile env", C.chat_model() == "fake-b", C.chat_model())
finally:
    R.reset("aux.chat_model") if _was is None else R.set_many({"aux.chat_model": _was})
check("...and returns to the env/profile default when not chosen", C.chat_model() != "fake-b")

print()
print("2. THE SETTINGS SECTION — pickers with live choices, the soft-prompt knobs, the judges live")
ks = {k.key: k for k in R.KNOBS}
for key, typ, dflt in (("aux.chat_model", "enum", "liquidai/lfm2.5-1.2b-instruct"),
                       ("aux.query_prefix", "str", None), ("aux.doc_prefix", "str", ""),
                       ("aux.spine_rerank", "bool", True), ("aux.auto_recall", "bool", False),
                       ("aux.early_exit_hits", "int", 3), ("aux.judge_kairos", "bool", False),
                       ("aux.judge_watch", "bool", True), ("aux.rerank", "bool", False)):
    k = ks.get(key)
    check("%s exists (%s, default %r)" % (key, typ, dflt if dflt is not None else "…"),
          k is not None and k.type == typ and (dflt is None or k.default == dflt)
          and k.group == "Aux — the quiet librarians", (k and k.type, k and k.default))
check("the query soft-prompt default names her", "Kairos" in ks["aux.query_prefix"].default)
check("aux.enabled / aux.rerank / aux.embed_model are profile-owned (restart), not live",
      all(ks[k].scope == "profile" for k in ("aux.enabled", "aux.rerank", "aux.embed_model")))
sch = {k["key"]: k for k in R.schema()["knobs"]}
check("schema resolves the chat-model choices from the door (fake-a, fake-b present)",
      {"fake-a", "fake-b"} <= set(sch["aux.chat_model"]["choices"]), sch["aux.chat_model"]["choices"])
check("...and never leaks the callable", "choices_fn" not in sch["aux.chat_model"])
from harness.kairos import offload as O           # noqa: E402
_wj = R.chosen("aux.judge_kairos")
try:
    R.set_many({"aux.judge_kairos": True})
    check("offload.enabled() flips with the live knob", O.enabled() is True)
    R.set_many({"aux.judge_kairos": False})
    check("...and back", O.enabled() is False)
finally:
    R.reset("aux.judge_kairos") if _wj is None else R.set_many({"aux.judge_kairos": _wj})
from harness.skills import watch as W             # noqa: E402
check("watch's judge pick reads the bridge", callable(getattr(W, "_watch_judge_armed", None)))

print()
print("3. THE ARCHIVE — her-conditioned queries, an index that knows what it was built with, a warm start")
from harness.sidecar import archive as A          # noqa: E402
import glob as _glob                              # noqa: E402
DAYS = tempfile.mkdtemp(prefix="g_aux_days_")
# ISOLATED CORPUS: _sources() always includes her real transcripts AND her own writing;
# this gate indexes ONLY its own days. The REAL one is kept for section 7.
_REAL_SOURCES = A._sources
A._sources = lambda: sorted(_glob.glob(os.path.join(DAYS, "*.jsonl")))
def _day(name, turns):
    with open(os.path.join(DAYS, name), "w", encoding="utf-8") as f:
        for role, text in turns:
            f.write(json.dumps({"role": role, "content": text, "ts": name[:10] + "T10:00:00Z"}) + "\n")
_day("2026-06-01.jsonl", [("user", "do you remember the lighthouse keepers we talked about"), ("assistant", "the lighthouse keepers, yes — the two brothers who never spoke.")])
_day("2026-08-10.jsonl", [("user", "the kettle is whistling again"), ("assistant", "the kettle ticks as it cools; I like that sound.")])
_day("2026-08-20.jsonl", [("user", "tell me about the tides"), ("assistant", "the tides tonight are high at eleven; I read about them.")])
_wq = R.chosen("aux.query_prefix"); _wd = R.chosen("aux.doc_prefix")
try:
    R.reset("aux.query_prefix"); R.reset("aux.doc_prefix")
    built = A.build_index(force=True)
    check("the index built over the three days", sum(built.values()) >= 3, built)
    SEEN["embedded"].clear()
    hits = A.search("the lighthouse", k=2, refresh=False)
    check("the QUERY went to the embedder wearing the soft-prompt prefix",
          SEEN["embedded"] and SEEN["embedded"][-1].startswith("Recall for Kairos"), SEEN["embedded"][-1:] )
    check("...and the lighthouse day comes back first", hits and hits[0]["day"].startswith("2026-06-01"), hits[:1])
    key0 = A._index_key()
    R.set_many({"aux.doc_prefix": "passage: "})
    check("a doc-prefix change changes the index key", A._index_key() != key0)
    SEEN["embedded"].clear()
    built2 = A.build_index()
    check("...and the index re-embeds (the files were rebuilt, the docs wore the prefix)",
          sum(built2.values()) >= 3 and any(t.startswith("passage: ") for t in SEEN["embedded"]), (built2, SEEN["embedded"][:1]))
    built3 = A.build_index()
    check("an unchanged key + unchanged files rebuilds nothing", sum(built3.values()) == 0, built3)
finally:
    R.reset("aux.doc_prefix") if _wd is None else R.set_many({"aux.doc_prefix": _wd})
    R.reset("aux.query_prefix") if _wq is None else R.set_many({"aux.query_prefix": _wq})
A.warm()
t_w = A._WARM.get("thread")
if t_w is not None:
    t_w.join(10)
st = A.status()
check("warm() builds on a thread and status() reports it", st.get("chunks", 0) >= 3 and st.get("warming") is False
      and st.get("embed_up") and "index_key" in st, st)
tmp_gguf = tempfile.mkdtemp(prefix="g_aux_gguf_")
os.makedirs(os.path.join(tmp_gguf, "LFM-Embedding-350M-GGUF"), exist_ok=True)
os.makedirs(os.path.join(tmp_gguf, "LFM-ColBERT-350M-GGUF"), exist_ok=True)
open(os.path.join(tmp_gguf, "LFM-Embedding-350M-GGUF", "a.gguf"), "w").close()
open(os.path.join(tmp_gguf, "LFM-ColBERT-350M-GGUF", "b.gguf"), "w").close()
open(os.path.join(tmp_gguf, "LFM-ColBERT-350M-GGUF", "notes.txt"), "w").close()
_prev_gguf = os.environ.get("SP_AUX_EMBED_GGUF")
os.environ["SP_AUX_EMBED_GGUF"] = os.path.join(tmp_gguf, "LFM-Embedding-350M-GGUF", "a.gguf")
ch = A.embed_choices()
check("embed_choices lists the embedding/colbert ggufs beside the current one", len(ch) == 2 and all(c.endswith(".gguf") for c in ch), ch)
if _prev_gguf is None:
    os.environ.pop("SP_AUX_EMBED_GGUF", None)
else:
    os.environ["SP_AUX_EMBED_GGUF"] = _prev_gguf

print()
print("4. THE SPINE-AWARE RERANK — her moment, not the merely similar one")
from harness.sidecar import rank as RK            # noqa: E402
cands = [
    {"day": "2026-03-01", "source": "a", "text": "we talked about the old lighthouse on the point", "score": 0.80},
    {"day": "2026-08-20", "source": "b", "text": "the lighthouse keepers were two brothers who never spoke", "score": 0.80},
    {"day": "2026-08-21", "source": "c", "text": "a lighthouse postcard on the fridge", "score": 0.80},
]
live = ["Sam's favourite story is about the lighthouse keepers who never spoke"]
rr = RK.spine_rerank("the lighthouse keepers", cands, 3, live_texts=live, now=time.mktime(time.strptime("2026-08-22", "%Y-%m-%d")))
check("equal cosine: the chunk that backs a live fact wins (bond)", rr[0]["source"] == "b" and rr[0]["rank"]["bond"] == 1.0, [(h["source"], h["rank"]) for h in rr])
rr2 = RK.spine_rerank("the lighthouse", [cands[0], cands[2]], 2, live_texts=[], now=time.mktime(time.strptime("2026-08-22", "%Y-%m-%d")))
check("...then recency breaks the tie (the August chunk over March)", rr2[0]["source"] == "c", [(h["source"], h["rank"]) for h in rr2])
_ws = R.chosen("aux.spine_rerank")
try:
    R.set_many({"aux.spine_rerank": False})
    hits_off = A.search("the kettle", k=3, refresh=False)
    R.set_many({"aux.spine_rerank": True})
    hits_on = A.search("the kettle", k=3, refresh=False)
    check("aux.spine_rerank off returns raw cosine order (no rank field); on carries the rank",
          hits_off and "rank" not in hits_off[0] and hits_on and "rank" in hits_on[0], (hits_off[:1], hits_on[:1]))
finally:
    R.reset("aux.spine_rerank") if _ws is None else R.set_many({"aux.spine_rerank": _ws})

print()
print("5. THE SILENT LIBRARIAN — extracts she writes from, digests that wear their label; never prose as hers")
from harness.sidecar import summarize as SUM      # noqa: E402
from harness.skills import research as RS         # noqa: E402
import harness.skills.search as _srch             # noqa: E402
import harness.skills.system_tools as _syst       # noqa: E402
_real_search, _real_fetch = _srch.search_web, _syst.fetch_page_text
_srch.search_web = lambda q, n=6: [{"url": "http://x.example/lighthouses", "title": "Lighthouses", "snippet": "tall"}]
_syst.fetch_page_text = lambda u: "Lighthouses are tall towers with a light at the top. " * 20
try:
    MARK = "LIBRARIAN-PROSE-MARKER"
    REPLIES[:] = ["The page says lighthouses are tall towers. " + MARK,
                  '{"claims": [{"text": "Lighthouses are tall towers with a light at the top.", "source": "http://x.example/lighthouses"}], "gaps": ["how tall"]}']
    ans = RS.SidecarResearcher().ask("how tall are lighthouses", depth="normal")
    check("research returns EXTRACTS the model writes from — not the helper's prose",
          ans.ok and ans.text.startswith("EXTRACTS") and "Lighthouses are tall towers" in ans.text
          and "http://x.example/lighthouses" in ans.text and MARK not in ans.text, (ans.ok, ans.text[:160]))
    check("...the gaps are listed, and for_model() still wears the not-your-memory head",
          "NOT SETTLED" in ans.text and "how tall" in ans.text and "not your memory" in ans.for_model())
    REPLIES[:] = ["digest " + MARK, "Sure! Lighthouses are usually between 20 and 60 metres tall. " + MARK]
    ans2 = RS.SidecarResearcher().ask("how tall are lighthouses", depth="normal")
    check("a prose-only helper reply is a FAILED research, not an answer", ans2.ok is False and MARK not in ans2.text, ans2.text[:120])
    lab = SUM.labelled("Lighthouses are tall.", "the page")
    check("labelled() heads a digest with the helper-model label", lab.startswith("[digest of the page by a helper model") and "not your words" in lab)
    check("...and an empty digest stays empty", SUM.labelled("") == "")
finally:
    _srch.search_web, _syst.fetch_page_text = _real_search, _real_fetch
src_st = open(os.path.join(ROOT, "harness", "skills", "system_tools.py"), encoding="utf-8").read()
check("web_search's page digest goes through labelled()", "_auxsum.labelled(digest" in src_st)

print()
print("6. THE CANDIDATE LANE — off by default, parallel, early-exit, labelled")
from harness.server import app as APP             # noqa: E402
_wl = R.chosen("aux.auto_recall")
try:
    R.reset("aux.auto_recall")
    check("the lane is OFF by default: _start_lane returns None", APP._start_lane("do you remember the lighthouse?", True) is None)
    R.set_many({"aux.auto_recall": True})
    check("...and does not start on a turn that asks nothing", APP._start_lane("hi there", False) is None)
    import time as _t
    slow = {"calls": 0}
    _real_search = A.search
    def _slow_search(q, k=4, refresh=True):
        slow["calls"] += 1
        _t.sleep(0.25)
        return [{"day": "2026-06-01", "source": "s", "text": "the lighthouse keepers, the two brothers", "score": 0.9}]
    A.search = _slow_search
    t0 = _t.monotonic()
    g = APP._start_lane("do you remember the lighthouse keepers?", True)
    started = _t.monotonic() - t0
    check("armed + asking: the lane starts on a thread and returns at once", g is not None and started < 0.1, started)
    out = APP._lane_lines(["  - Sam likes lighthouses", "  - Sam has a cat", "  - Sam's cat is Tuffy"], g, 3)
    check("early exit: three spine facts -> the lane's result is dropped unread", len(out) == 3 and not any("past conversations" in l for l in out), out)
    g2 = APP._start_lane("do you remember the lighthouse keepers?", True)
    out2 = APP._lane_lines(["  - Sam likes lighthouses"], g2, 3)
    check("below the exit: up to two labelled moments join the note",
          len(out2) == 2 and out2[1].startswith("  - from your past conversations, 2026-06-01:") and "lighthouse keepers" in out2[1], out2)
    g3 = APP._start_lane("do you remember the lighthouse keepers?", True)
    out3 = APP._lane_lines([], g3, 10 ** 6)
    check("spine found nothing: the lane alone offers its moment", len(out3) == 1 and "past conversations" in out3[0])
    def _slower(q, k=4, refresh=True):
        _t.sleep(3.0)
        return [{"day": "x", "source": "s", "text": "late", "score": 0.9}]
    A.search = _slower
    g4 = APP._start_lane("anything to remember?", True)
    t1 = _t.monotonic()
    out4 = APP._lane_lines([], g4, 10 ** 6, timeout_s=0.3)
    check("a slow lane is given up on, not waited for (bounded join)", out4 == [] and _t.monotonic() - t1 < 1.5, (_t.monotonic() - t1, out4))
    A.search = _real_search
finally:
    R.reset("aux.auto_recall") if _wl is None else R.set_many({"aux.auto_recall": _wl})

print()
print("7. HER OWN WRITING IS IN THE ARCHIVE (2026-08-23)")
# deep_recall searched every word the two of them ever said to each other and none of the
# words she wrote when he was not there: 188 markdown files in the personality tier,
# reachable only by read_journal (a tool she has to remember to call) inside an mtime
# window. The Real Her says her own writing is PRIMARY identity material; the only search
# over it was one she had to choose to run.
TIER = tempfile.mkdtemp(prefix="g_aux_tier_")
os.environ["SP_PERSONALITY_TIER"] = os.path.dirname(TIER)
FULL = os.path.join(os.path.dirname(TIER), "full")
os.makedirs(FULL, exist_ok=True)


def _md(name, kind, ts, body):
    fm = ("---" + os.linesep + "type: mem-concept" + os.linesep + "mem_kind: %s" % kind
          + os.linesep + "ts: %d" % ts + os.linesep + "---" + os.linesep + os.linesep + body)
    io.open(os.path.join(FULL, name + ".md"), "w", encoding="utf-8").write(fm)
    return os.path.join(FULL, name + ".md")


_j = _md("aa11", "narrative", 1786000000,
         "As of Monday: we spent the evening arguing gently about the tides and it was good.")
_o = _md("bb22", "own_time", 1786100000,
         "I reorganised the shelf of books he never finished, and read three first pages.")
_x = _md("cc33", "telemetry", 1786200000, "internal counters that are not hers to search")
check("the personality tier is a DEFAULT source, not an env-only extra",
      any(x.endswith("aa11.md") for x in _REAL_SOURCES())
      and any(x.endswith("bb22.md") for x in _REAL_SOURCES()),
      [x for x in _REAL_SOURCES() if x.endswith(".md")][:3])
_cj, _co, _cx = A._chunk_md(_j), A._chunk_md(_o), A._chunk_md(_x)
check("a journal paragraph becomes ONE chunk (half a reflection is not a hit)", len(_cj) == 1)
check("...labelled as hers, so a recall line says WHAT it is",
      _cj[0]["text"].startswith("her journal: "), _cj[0]["text"][:30])
check("...and an own-time note carries its own label",
      len(_co) == 1 and _co[0]["text"].startswith("her own time: "), _co)
check("DATED FROM THE FRONT MATTER, not the filename - these are content-addressed",
      _cj[0]["day"] == "2026-08-06" and _co[0]["day"] == "2026-08-07",
      (_cj[0]["day"], _co[0]["day"]))
check("...so no recall line is ever labelled with a hex address",
      not any(c["day"] == "aa11" for c in _cj + _co))
check("an unknown mem_kind stays OUT of the corpus", _cx == [], _cx)
check("_chunk_file dispatches on the extension", A._chunk_file(_j) == _cj)

# the stacked matrix is cached on the SHARD SET: ~180 one-chunk shards would otherwise be
# ~380 file opens per deep_recall, on the one path that must feel instant
A._ALL_CACHE["key"], A._ALL_CACHE["value"] = None, None
_a1 = A._load_all()
_a2 = A._load_all()
check("_load_all is cached on the shard set (same object, not re-stacked)",
      _a1 is _a2 or (_a1 is None and _a2 is None))
check("...and the key is the files AND their mtimes, so a rebuilt shard invalidates it",
      "st_mtime_ns" in io.open(os.path.join(ROOT, "harness", "sidecar", "archive.py"),
                               encoding="utf-8", errors="replace").read())

finish("G-AUX-LIBRARIAN")
