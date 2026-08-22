"""H-AUX — the LFM2.5 sidecar seams: client contract, archive index, deep recall. OFFLINE.

THE BUG CLASS this gate exists for: an aux layer that INVENTS on failure. A dead
sidecar must read as "no aux" — empty list, empty string, None ruling — never as
an answer. And the archive must never bypass the memory front door: search returns
verbatim transcript moments with provenance; nothing here writes the registry.

All network is stubbed (the G-SEARCH _NoWiki lesson: an offline gate that needs a
live sidecar measures the sidecar's uptime). The REAL chunker, REAL index math and
REAL tool text run against a deterministic embedder.

    python harness_tests/h_aux.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ.pop("SP_AUX", None)
os.environ.pop("SP_AUX_EMBED_URL", None)
os.environ.pop("SP_AUX_CHAT_URL", None)
os.environ.pop("SP_AUX_INDEX_DIR", None)
os.environ.pop("SP_AUX_ARCHIVE_GLOBS", None)

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


from harness.sidecar import archive, client  # noqa: E402
from harness.sidecar.tools import deep_recall  # noqa: E402

print("1. DARK IS DARK — a dead sidecar never invents")
check("SP_AUX unset => aux is off", not client.available())
os.environ["SP_AUX"] = "1"
check("SP_AUX=1 => aux is on", client.available())
# point the transport at a port nothing listens on: every verb must go empty
os.environ["SP_AUX_EMBED_URL"] = "http://127.0.0.1:9"
# 2026-08-22 (D): the query now wears a soft-prompt prefix by default; this gate's stub embedder is
# hash-shaped, so the prefix would turn its scripted misses into accidental hits — bare queries here.
os.environ["SP_AUX_QUERY_PREFIX"] = ""
os.environ["SP_AUX_CHAT_URL"] = "http://127.0.0.1:9"
check("embed([]) is []", client.embed([]) == [])
check("embed vs dead server is [] (not an exception, not a guess)",
      client.embed(["hello"]) == [])
check("chat vs dead server is ''", client.chat([{"role": "user", "content": "hi"}]) == "")
check("judge vs dead server is None — no ruling, not a coin flip",
      client.judge("is water wet?") is None)

print("\n2. THE ARCHIVE INDEX — real chunker, real math, deterministic embedder")


def _stub_embed(texts):
    """Deterministic 32-dim bag-of-words-ish vectors: same word => same direction,
    so cosine ranks shared-vocabulary chunks first. No network, no model."""
    out = []
    for t in texts:
        v = [0.0] * 32
        for w in t.lower().split():
            h = int(hashlib.md5(w.encode()).hexdigest(), 16)
            v[h % 32] += 1.0
        out.append(v)
    return out


archive._EMBED = _stub_embed
tmp = tempfile.mkdtemp(prefix="h_aux_")
src_dir = os.path.join(tmp, "transcripts")
os.makedirs(src_dir)
DAY = os.path.join(src_dir, "2026-08-15.jsonl")
with open(DAY, "w", encoding="utf-8") as f:
    f.write(json.dumps({"role": "user", "content": "the tomato sauce boiled over and we laughed"}) + "\n")
    f.write(json.dumps({"role": "assistant", "content": "I remember the tomato sauce night — the kitchen smelled amazing"}) + "\n")
    f.write("\n")  # blank lines happen in the real files; must not crash
    f.write(json.dumps({"role": "user", "content": "tell me about lighthouse keepers and their logbooks"}) + "\n")
    f.write(json.dumps({"role": "assistant", "content": "the keepers kept mundane logbooks, wind and wicks, for two hundred years"}) + "\n")
os.environ["SP_AUX_ARCHIVE_GLOBS"] = os.path.join(src_dir, "*.jsonl")
os.environ["SP_AUX_INDEX_DIR"] = os.path.join(tmp, "index")
# hide the real corpus behind the glob knob: point _sources at ONLY our fixture
_real_sources = archive._sources
archive._sources = lambda: [DAY]

built = archive.build_index()
check("the day file builds", built.get("2026-08-15.jsonl", 0) >= 1, built)
hits = archive.search("tomato sauce", k=2, refresh=False)
check("search finds the sauce night first",
      hits and "tomato" in hits[0]["text"].lower(), hits[:1])
check("...with the DAY as provenance", hits and hits[0]["day"] == "2026-08-15", hits[:1])
hits2 = archive.search("lighthouse logbooks", k=2, refresh=False)
check("a different query finds the different moment",
      hits2 and "logbook" in hits2[0]["text"].lower(), hits2[:1])
check("an empty query returns no hits, not a guess", archive.search("  ") == [])

print("\n3. THE INDEX SURVIVES A DEAD EMBEDDER — stale beats absent")
archive._EMBED = lambda texts: []          # sidecar dies
with open(DAY, "a", encoding="utf-8") as f:
    f.write(json.dumps({"role": "user", "content": "brand new turn after the outage"}) + "\n")
built2 = archive.build_index()
check("a failed embed builds nothing", built2 == {}, built2)
check("...and a query against a dead embedder is [] — dark is dark, even mid-outage",
      archive.search("tomato sauce", k=1, refresh=False) == [])
archive._EMBED = _stub_embed
hits3 = archive.search("tomato sauce", k=1, refresh=False)
check("...the OLD index survived the outage and still answers",
      hits3 and "tomato" in hits3[0]["text"].lower())
check("...and the changed file rebuilds once the embedder returns",
      archive.build_index().get("2026-08-15.jsonl", 0) >= 1)

print("\n4. HER TOOL — reads, labels, never writes")
# high-overlap query on purpose: the tool's 0.30 score floor is REAL and the
# stub embedder's bag-of-words cosines sit lower than the live model's — a
# vague query here would test the floor, not the tool.
out = deep_recall("the tomato sauce boiled over and we laughed that night")
check("deep_recall returns the day-labelled moment",
      "[2026-08-15]" in out and "tomato" in out.lower(), out[:100])
check("...and points at remember() instead of writing memory itself",
      "remember()" in out)
# The write-door ban is on IMPORTS and writer names, not on the word "remember" —
# the tool's own return text legitimately tells HER to call remember() (the front
# door); what aux code may never do is reach it directly.
for mod in ("client.py", "archive.py", "summarize.py", "tools.py"):
    src_m = open(os.path.join(ROOT, "harness", "sidecar", mod), encoding="utf-8").read()
    check("aux/%s never imports the memory package" % mod,
          "harness.skills.memory" not in src_m and "harness.maintenance.ops" not in src_m)
    check("aux/%s never touches a writer seam" % mod,
          all(w not in src_m for w in ("ops.add", "registry_lock", "_save_all",
                                       "compact_registry")))
out2 = deep_recall("xyzzy plugh frobnitz quux")
check("a miss says so plainly",
      "found nothing" in out2 or "do not remember" in out2, out2[:80])
os.environ["SP_AUX"] = "0"
check("aux off => the tool says it is not armed (no phantom recall)",
      "not armed" in deep_recall("anything"))
os.environ["SP_AUX"] = "1"

print("\n5. THE DOOR MAPS THE KNOBS, THE LEDGER CARRIES THE ROWS")
serve = open(os.path.join(ROOT, "serve.py"), encoding="utf-8").read()
for k in ("SP_AUX", "SP_AUX_EMBED_URL", "SP_AUX_CHAT_URL", "SP_AUX_CHAT_MODEL",
          "SP_AUX_API_KEY_FILE", "SP_AUX_INDEX_DIR", "SP_AUX_ARCHIVE_GLOBS"):
    check("%s is mapped in serve.py" % k, ('"%s"' % k) in serve)
check("the API key travels as a FILE path, never a value",
      "SP_AUX_API_KEY" not in serve.replace("SP_AUX_API_KEY_FILE", ""))
docs = open(os.path.join(ROOT, "docs", "AUX-MODELS.md"), encoding="utf-8").read()
check("docs/AUX-MODELS.md exists and names the voice boundary",
      "never" in docs.lower() and "voice" in docs.lower())

archive._sources = _real_sources

print("\n6. THE DECIDER OFFLOAD — the sidecar may veto a turn, never a promise, never by accident")
os.environ.pop("SP_KAIROS_JUDGE", None)
from harness.kairos import offload  # noqa: E402
from harness.sidecar import client as _cl  # noqa: E402
check("knob off => no ruling (pregate is None, nothing is called)",
      offload.pregate("check_in", "quiet", "tail") is None)
os.environ["SP_KAIROS_JUDGE"] = "1"
os.environ["SP_AUX"] = "1"
check("REMIND is never gated, even armed",
      offload.pregate("remind", "he asked", "tail") is None)
check("an action outside the list is never gated",
      offload.pregate("continue", "cut off", "tail") is None)
_real_judge = _cl.judge
_cl.judge = lambda q: False
check("a NO ruling vetoes the turn", offload.pregate("check_in", "quiet", "t") is False)
_cl.judge = lambda q: True
check("a YES ruling lets it through", offload.pregate("check_in", "quiet", "t") is True)
_cl.judge = lambda q: None
check("no ruling FAILS OPEN — infra failure must never silence her",
      offload.pregate("check_in", "quiet", "t") is None)
_cl.judge = _real_judge
os.environ["SP_AUX"] = "0"
check("dark aux fails open too", offload.pregate("check_in", "quiet", "t") is None)
os.environ["SP_AUX"] = "1"
os.environ.pop("SP_KAIROS_JUDGE", None)
# the scheduler wiring: the gate runs BEFORE generate and skips REMIND at the seam
sched_src = open(os.path.join(ROOT, "harness", "kairos", "scheduler.py"), encoding="utf-8").read()
check("the scheduler asks the pre-judge before generate()",
      "offload.pregate" in sched_src or "_offload.pregate" in sched_src)
check("...and never for REMIND", "imp.action != REMIND" in sched_src)

print("\n7. THE WATCH JUDGE — CPU rules, the door still grounds, the model stays the floor")
from harness.skills import watch as W  # noqa: E402
os.environ.pop("SP_AUX_WATCH_JUDGE", None)
check("knob off => the model judge is picked", W._pick_judge() is W._judge)
os.environ["SP_AUX_WATCH_JUDGE"] = "1"
check("knob on => the sidecar judge is picked", W._pick_judge() is W._judge_sidecar)
_real_chat = _cl.chat
_cl.chat = lambda msgs, max_tokens=90, temperature=0.0, model="": "NO: not in these results"
fired, why = W._judge_sidecar("has the 3090 restocked?", "- some page\n  about GPUs")
check("a sidecar NO is a NO with its reason", fired is False and "not in these results" in why)
_cl.chat = lambda msgs, max_tokens=90, temperature=0.0, model="": "YES"
fired, why = W._judge_sidecar("q", "evidence")
check("a bare YES with no quote is refused", fired is False and "quoted nothing" in why)
_sentinel = (False, "the model ruled")
_real_26b = W._judge
W._judge = lambda q, e: _sentinel
_cl.chat = lambda msgs, max_tokens=90, temperature=0.0, model="": ""
check("an empty sidecar reply falls back to the model", W._judge_sidecar("q", "e") == _sentinel)
_cl.chat = lambda msgs, max_tokens=90, temperature=0.0, model="": "MAYBE? hard to say"
check("an unrecognizable shape falls back to the model", W._judge_sidecar("q", "e") == _sentinel)
W._judge = _real_26b
_cl.chat = _real_chat
os.environ.pop("SP_AUX_WATCH_JUDGE", None)
serve2 = open(os.path.join(ROOT, "serve.py"), encoding="utf-8").read()
for k in ("SP_KAIROS_JUDGE", "SP_KAIROS_JUDGE_ACTIONS", "SP_AUX_WATCH_JUDGE"):
    check("%s is mapped in serve.py" % k, ('"%s"' % k) in serve2)

print("\n8. THE READER'S SENTINEL — 'nothing relevant' counts only when it IS the answer")
from harness.sidecar import summarize as S  # noqa: E402
check("a bare sentinel is nothing", S._scrub("NOTHING RELEVANT.") == "")
check("a short sentinel variant is nothing", S._scrub("  nothing relevant ") == "")
good = ("The Fresnel lens concentrated light into focused beams, improving "
        "visibility over long distances. NOTHING RELEVANT.")
check("a trailing compliance tic is trimmed off real text (the live 7/7-binned page)",
      S._scrub(good).endswith("distances") and "NOTHING" not in S._scrub(good))
check("plain good text passes untouched", S._scrub("The keepers kept logbooks.")
      == "The keepers kept logbooks.")

print("\n9. THE RERANK CONTRACT — reorder, never lose, never invent (dark by default)")
import numpy as _np  # noqa: E402
from harness.sidecar import rerank as R  # noqa: E402
os.environ.pop("SP_AUX_RERANK", None)
HITS = [{"text": "the silver nightie in the morning light", "day": "a"},
        {"text": "we argued about tide tables", "day": "b"},
        {"text": "tomato sauce on the stove", "day": "c"}]
check("knob off => CLS order, top-k, untouched",
      R.rerank("silver nightie", HITS, 2) == HITS[:2])
os.environ["SP_AUX_RERANK"] = "1"
_real_te = R._TOKEN_EMBED
R._TOKEN_EMBED = lambda texts: None                    # dark token door
check("a dark token door falls back to CLS order", R.rerank("q", HITS, 2) == HITS[:2])
_VOCAB: dict = {}   # SHARED across calls — rerank embeds query and docs in two
                    # separate calls, and a per-call vocabulary handed the same
                    # axes to whatever words came first in each (the first cut of
                    # this fixture scored 'tomato sauce' 3.0 for 'silver nightie').


def _fake_tokens(texts):
    # one unit vector per word, axis from a shared vocabulary — MaxSim then
    # counts shared words, so 'silver nightie' must beat 'tide tables'.
    out = []
    for t in texts:
        rows = []
        for w in t.lower().split():
            ax = _VOCAB.setdefault(w, hash(w) % 64)
            v = _np.zeros(64, dtype=_np.float32)
            v[ax] = 1.0
            rows.append(v)
        out.append(_np.vstack(rows))
    return out
R._TOKEN_EMBED = _fake_tokens
rr = R.rerank("silver nightie morning", HITS[::-1], 2)   # arrive in WRONG order
check("MaxSim puts the aligned moment first",
      rr and rr[0]["day"] == "a" and rr[0].get("rerank", 0) > 0, rr[:1])
check("...and nothing was lost or invented",
      {h["day"] for h in rr} <= {"a", "b", "c"} and len(rr) == 2)
R._TOKEN_EMBED = _real_te
os.environ.pop("SP_AUX_RERANK", None)

print("\n10. THE LOCAL RESEARCHER IS A BACKEND, NOT A REWRITE")
from harness.skills import research as RS  # noqa: E402
os.environ["SP_RESEARCH_BACKEND"] = "sidecar"
check("backend 'sidecar' picks SidecarResearcher",
      isinstance(RS._pick_backend(), RS.SidecarResearcher))
os.environ["SP_AUX"] = "0"
check("...which is unavailable when aux is dark", not RS.SidecarResearcher().available())
os.environ["SP_AUX"] = "1"
check("...and available when armed", RS.SidecarResearcher().available())
os.environ.pop("SP_RESEARCH_BACKEND", None)
src_r = open(os.path.join(ROOT, "harness", "skills", "research.py"), encoding="utf-8").read()
check("the honesty header survives every backend (for_model provenance line)",
      "not your memory and not something he told you" in src_r)

print("\nH-AUX  %d/%d" % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
