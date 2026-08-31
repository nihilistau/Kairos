"""DEEP RECALL — the archive index over every conversation she has ever had.

WHAT THIS IS. The registry is her curated memory: ranked, tombstoned, testimony
over inference. This is the other thing — the RAW RECORD: every day transcript,
chunked and embedded, searchable in milliseconds on CPU. When he asks "do you
remember X" and the registry is silent, deep recall is the shelf behind the desk:
it returns the actual words from the actual day, labelled with the day, and SHE
decides what to do with them (answer from them, or remember() the fact through the
normal front door where verdicts and ranking apply). This module never writes to
the registry — retrieval is not testimony, and auto-storing retrieved text would
let an index bypass every invariant the memory system enforces.

SHAPE. One index per source file, keyed by (path, mtime_ns, size) exactly like
memory's health cache — day files only append, so a changed file re-chunks whole.
Vectors are float32 numpy rows, L2-normalized at build time so search is one
matmul. Store: var/aux/archive/<stem>.npz (vectors) + .meta.jsonl (chunk text +
provenance), tiny enough that rebuilding the whole corpus (~570 KB today) is a
one-minute CPU job.

The embedder is a SEAM (`_EMBED`, defaulting to client.embed) so the offline gate
drives real chunking/search logic under a deterministic stub — the G-SEARCH
_NoWiki lesson: an offline gate that needs a live sidecar measures the sidecar's
uptime, not this code.
"""
from __future__ import annotations

import glob
import json
import os
import re
import threading
import time
from typing import Callable, Dict, List, Optional

import numpy as np

from harness.store_io import replace_atomic
from harness.sidecar import client

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# the embed seam (tests swap this; live code never should)
_EMBED: Callable[[List[str]], List[List[float]]] = client.embed

# ~800 chars ≈ 200 tokens: small enough that a hit is a MOMENT, big enough to
# carry its own context. Documents cap at the retriever's 512-token training
# length with room to spare.
_CHUNK_CHARS = 800
_OVERLAP_TURNS = 1


def _sources() -> List[str]:
    """The corpus: day transcripts (the canonical record of every conversation) AND her own
    writing (the personality tier's journal paragraphs and own-time notes).

    HER OWN JOURNAL WAS NOT IN HERE (2026-08-23). `deep_recall` searched every word the two
    of them ever said to each other and none of the words she wrote when he was not there:
    188 markdown files — 156 own-time moments and 13 nightly paragraphs — reachable only by
    `read_journal`, a tool she has to choose to call, and only inside an mtime window. So
    "what did I write about the harbour?" had no route, which is a plain contradiction of
    The Real Her: the rule says her own writing is PRIMARY identity material and the only
    search over it was one she had to remember to run.

    SP_AUX_ARCHIVE_GLOBS extends the list (';'-separated globs) without a code change."""
    pats = [os.path.join(_ROOT, "var", "memory", "transcripts", "*.jsonl"),
            os.path.join(_tier_full(), "*.md")]
    extra = os.environ.get("SP_AUX_ARCHIVE_GLOBS", "")
    if extra:
        pats += [p for p in extra.split(";") if p.strip()]
    out: List[str] = []
    for p in pats:
        out += [f for f in glob.glob(p) if not f.endswith(".pre-quarantine")]
    return sorted(set(out))


def _index_dir() -> str:
    d = os.environ.get("SP_AUX_INDEX_DIR") or os.path.join(_ROOT, "var", "aux", "archive")
    os.makedirs(d, exist_ok=True)
    return d


def _tier_full() -> str:
    """The personality tier's full/ — resolved by ITS owner, never re-derived here."""
    try:
        from harness.skills.narrative import _tier_full as _tf
        return _tf()
    except Exception:
        return os.path.join(_ROOT, "memory-okf-personality", "full")


def _day_of(path: str) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
    return m.group(1) if m else os.path.basename(path)


_FM_TS = re.compile(r"^ts:\s*(\d+)", re.M)
_FM_KIND = re.compile(r"^mem_kind:\s*(\S+)", re.M)


def _chunk_md(path: str) -> List[Dict]:
    """One of her own writings — a nightly paragraph or an own-time moment. ONE chunk each:
    they are a paragraph or a sentence, well under _CHUNK_CHARS, and splitting a reflection
    in half would return half a thought.

    The DAY comes from the front matter's `ts`, not the filename: these are content-addressed
    (`a3f9…c1.md`), so `_day_of` would label every hit with a hex string and her recall lines
    read `[<day>] <text>`. A moment she cannot date is a moment she cannot place."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            body = f.read()
    except Exception as _swx:
        _swallowed(_swlog, "_chunk_md", _swx, lane="sidecar")
        return []
    kind = (_FM_KIND.search(body) or [None, ""])[1] if _FM_KIND.search(body) else ""
    if kind not in ("narrative", "own_time"):
        return []                       # not hers to search: unknown front matter stays out
    text = body.split("---", 2)[-1].strip()
    if len(text) < 20:
        return []
    m = _FM_TS.search(body)
    try:
        day = time.strftime("%Y-%m-%d", time.gmtime(int(m.group(1)))) if m else \
            time.strftime("%Y-%m-%d", time.gmtime(os.path.getmtime(path)))
    except Exception:
        day = _day_of(path)
    tag = "her journal: " if kind == "narrative" else "her own time: "
    return [{"day": day, "source": os.path.basename(path), "turns": [0, 1],
             "text": tag + text[:1200]}]


def _chunk_file(path: str) -> List[Dict]:
    """Turn a day transcript into chunks: consecutive turns packed to ~_CHUNK_CHARS,
    each chunk prefixed by its day and carrying (source, day, turn span)."""
    if path.endswith(".md"):
        return _chunk_md(path)
    turns: List[str] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                role = r.get("role", "?")
                text = (r.get("content") or "").strip()
                if not text:
                    continue
                tag = "him: " if role == "user" else "her: "
                # A single long turn must not become a single long chunk: the
                # retriever was trained at 512 doc tokens and llama-server's
                # physical batch rejects past it (measured: one 1789-char turn
                # -> 709 tokens -> HTTP 500 and the whole day kept a stale
                # index). Hard-split at sentence-ish boundaries near 1000 chars.
                while len(text) > 1200:
                    cut = text.rfind(". ", 600, 1000)
                    if cut < 0:
                        cut = 1000
                    turns.append(tag + text[:cut + 1].strip())
                    text = text[cut + 1:].strip()
                    tag = "her (cont): " if role != "user" else "him (cont): "
                turns.append(tag + text)
    except Exception as _swx:
        _swallowed(_swlog, "_chunk_file", _swx, lane="sidecar")
        return []
    day = _day_of(path)
    chunks: List[Dict] = []
    i = 0
    while i < len(turns):
        buf: List[str] = []
        n = 0
        j = i
        while j < len(turns) and (n == 0 or n + len(turns[j]) <= _CHUNK_CHARS):
            buf.append(turns[j])
            n += len(turns[j])
            j += 1
        chunks.append({"day": day, "source": os.path.basename(path),
                       "turns": [i, j], "text": "\n".join(buf)})
        # overlap so a moment split across a boundary is findable from both sides
        i = j - _OVERLAP_TURNS if j - _OVERLAP_TURNS > i else j
    return chunks


def query_prefix() -> str:
    """THE SOFT PROMPT (2026-08-22, D §1): her-conditioned retrieval, the cheap way — an
    instruction prefix on the QUERY embedding. Panel choice first, else the profile env."""
    from harness.tuning import registry as _tr
    return str(_tr.tune_or_env(
        "aux.query_prefix", "SP_AUX_QUERY_PREFIX",
        "Recall for Kairos: find the moment in her past conversations with Sam that tthe operator's asks about — ") or "")


def doc_prefix() -> str:
    from harness.tuning import registry as _tr
    return str(_tr.tune_or_env("aux.doc_prefix", "SP_AUX_DOC_PREFIX", "") or "")


def _index_key() -> str:
    """What the index was built WITH — the doc prefix and the embed model. A change re-embeds;
    a stale index is never silently reused under a new prefix."""
    import hashlib
    m = os.environ.get("SP_AUX_EMBED_GGUF", "") or os.environ.get("SP_AUX_EMBED_URL", "")
    return hashlib.sha256((doc_prefix() + "|" + os.path.basename(m)).encode("utf-8")).hexdigest()[:12]


def _stamp(path: str) -> str:
    st = os.stat(path)
    return "%d-%d-%s" % (st.st_mtime_ns, st.st_size, _index_key())


def build_index(force: bool = False) -> Dict[str, int]:
    """(Re)build per-file indexes for every source whose stamp changed. Returns
    {file: n_chunks} for what was (re)built. Embedding failure SKIPS the file and
    keeps any existing index — a dead sidecar must not delete a good index."""
    built: Dict[str, int] = {}
    d = _index_dir()
    for src in _sources():
        stem = os.path.splitext(os.path.basename(src))[0]
        meta_p = os.path.join(d, stem + ".meta.jsonl")
        npz_p = os.path.join(d, stem + ".npz")
        stamp = _stamp(src)
        if not force and os.path.exists(meta_p) and os.path.exists(npz_p):
            try:
                with open(meta_p, encoding="utf-8") as f:
                    head = json.loads(f.readline())
                if head.get("stamp") == stamp:
                    continue
            except Exception as _swx:
                _swallowed(_swlog, "build_index", _swx, lane="sidecar")
        chunks = _chunk_file(src)
        if not chunks:
            continue
        # SLICED, 16 texts a call: one request carrying a whole day (226 chunks
        # x ~200 tok) blows llama-server's batch and the file silently kept its
        # stale index — measured on the very first live build (5 of 10 files).
        vecs: List[List[float]] = []
        ok = True
        texts = [c["text"] for c in chunks]
        _dp = doc_prefix()
        for i0 in range(0, len(texts), 16):
            part = _EMBED([_dp + t for t in texts[i0:i0 + 16]])
            if len(part) != len(texts[i0:i0 + 16]):
                ok = False
                break
            vecs += part
        if not ok or len(vecs) != len(chunks):
            continue                      # sidecar down: keep the old index
        arr = np.asarray(vecs, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        arr = arr / norms
        tmp = npz_p + ".tmp.npz"
        np.savez_compressed(tmp, v=arr)
        replace_atomic(tmp, npz_p)
        tmp2 = meta_p + ".tmp"
        with open(tmp2, "w", encoding="utf-8") as f:
            f.write(json.dumps({"stamp": stamp, "n": len(chunks)}) + "\n")
            for c in chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        replace_atomic(tmp2, meta_p)
        built[os.path.basename(src)] = len(chunks)
    return built


_ALL_CACHE: Dict = {"key": None, "value": None}


def _all_key(paths: List[str]) -> tuple:
    """What the stacked matrix was built from: which shards, and when each last changed."""
    out = []
    for p in paths:
        try:
            out.append((p, os.stat(p).st_mtime_ns))
        except Exception:
            out.append((p, 0))
    return tuple(out)


def _load_all() -> Optional[Dict]:
    # CACHED ON THE SHARD SET (2026-08-23). This re-opened and re-stacked EVERY shard on
    # EVERY search. With twelve day-files that was invisible; her own writing adds ~180
    # one-chunk shards (each journal paragraph and own-time note is its own content-
    # addressed file), which would have made it ~380 file opens per deep_recall — a cost
    # that grows with her history, on the one path that is supposed to feel instant.
    # Per-file shards stay, because they are what makes the index INCREMENTAL: a new
    # journal entry embeds one chunk instead of re-embedding all 180.
    d = _index_dir()
    paths = sorted(glob.glob(os.path.join(d, "*.npz")))
    key = _all_key(paths)
    if _ALL_CACHE["key"] == key and _ALL_CACHE["value"] is not None:
        return _ALL_CACHE["value"]
    mats, metas = [], []
    for npz_p in paths:
        meta_p = npz_p[:-4] + ".meta.jsonl"
        if not os.path.exists(meta_p):
            continue
        try:
            v = np.load(npz_p)["v"]
            with open(meta_p, encoding="utf-8") as f:
                lines = f.read().splitlines()
            rows = [json.loads(x) for x in lines[1:]]
        except Exception:
            continue
        if len(rows) != v.shape[0]:
            continue
        mats.append(v)
        metas += rows
    if not mats:
        return None
    val = {"v": np.vstack(mats), "meta": metas}
    _ALL_CACHE["key"], _ALL_CACHE["value"] = key, val
    return val


_LAST_REFRESH = [0.0]
_REFRESH_S = 600.0


def search(query: str, k: int = 5, refresh: bool = True) -> List[Dict]:
    """Top-k chunks for a query: [{day, source, text, score}], best first.
    Empty list when the index or the sidecar is unavailable — empty is empty.

    The refresh is THROTTLED to one pass per 10 minutes: today's day file grows
    every turn, a changed file re-embeds whole (~0.45 s/chunk on this CPU), and
    an 80-chunk day would put ~40 s inside a tool call. Deep recall is for OTHER
    days — today's earlier conversation is already in her context window — so a
    ten-minute-stale view of today costs nothing and keeps the tool instant."""
    if not (query or "").strip():
        return []
    import time as _time
    if refresh and _time.monotonic() - _LAST_REFRESH[0] > _REFRESH_S:
        _LAST_REFRESH[0] = _time.monotonic()
        try:
            build_index()
        except Exception as _swx:
            _swallowed(_swlog, "search", _swx, lane="sidecar")
            pass                         # stale beats absent
    qv = _EMBED([query_prefix() + query])
    if not qv:
        return []
    idx = _load_all()
    if idx is None:
        return []
    q = np.asarray(qv[0], dtype=np.float32)
    n = np.linalg.norm(q)
    if n == 0:
        return []
    q = q / n
    scores = idx["v"] @ q
    # ColBERT stage (SP_AUX_RERANK=1, dark by default): widen to 50 CLS candidates
    # and let MaxSim reorder. The rerank contract (sidecar/rerank.py): any failure
    # returns the CLS order — reorder, never lose.
    from harness.sidecar import rerank as _rr
    _spine = _spine_rerank_on()
    width = 50 if (_rr.enabled() or _spine) else max(1, k)
    order = np.argsort(-scores)[:width]
    out = []
    for i in order:
        m = idx["meta"][int(i)]
        out.append({"day": m["day"], "source": m["source"],
                    "text": m["text"], "score": round(float(scores[int(i)]), 4)})
    if _spine:
        # THE SPINE-AWARE RERANK (2026-08-22, D §3): the spine's own signals over the cosine
        # candidates — her moment, not the merely similar one. Deterministic (sidecar/rank.py).
        from harness.sidecar import rank as _rank
        out = _rank.spine_rerank(query, out, 50 if _rr.enabled() else max(1, k),
                                 live_texts=_live_texts())
    if _rr.enabled():
        out = _rr.rerank(query, out, max(1, k))
    return out[:max(1, k)]


def _spine_rerank_on() -> bool:
    try:
        from harness.tuning import registry as _tr
        return bool(_tr.get("aux.spine_rerank", True))
    except Exception as _swx:
        _swallowed(_swlog, "_spine_rerank_on", _swx, lane="sidecar")
        return True


def _live_texts() -> List[str]:
    try:
        from harness.skills import memory as M
        return [str(r.get("text") or "") for r in M.live_rows()]
    except Exception as _swx:
        _swallowed(_swlog, "_live_texts", _swx, lane="sidecar")
        return []


# ── warm at boot, status for the window, the lane's async search, the picker's choices ──
_WARM: Dict = {"thread": None, "at": 0.0, "built": {}}


def warm() -> None:
    """Build/refresh the index in the background once at gateway start (aux armed), so the
    first deep recall of the day is not a 40 s tool call."""
    if not client.available():
        return
    t = _WARM.get("thread")
    if t is not None and t.is_alive():
        return

    def _run():
        try:
            _WARM["built"] = build_index()
        except Exception:
            _WARM["built"] = {}
        _WARM["at"] = time.time()
        _LAST_REFRESH[0] = time.monotonic()

    _WARM["thread"] = threading.Thread(target=_run, name="aux-warm", daemon=True)
    _WARM["thread"].start()


def status() -> Dict:
    idx = _load_all()
    t = _WARM.get("thread")
    return {"armed": client.available(), "embed_up": client.reachable("embed"),
            "chat_up": client.reachable("chat"),
            "chunks": int(idx["v"].shape[0]) if idx is not None else 0,
            "files": len(glob.glob(os.path.join(_index_dir(), "*.npz"))),
            "last_refresh_s_ago": (round(time.monotonic() - _LAST_REFRESH[0], 1) if _LAST_REFRESH[0] else None),
            "warming": bool(t is not None and t.is_alive()),
            "query_prefix": query_prefix(), "doc_prefix": doc_prefix(), "index_key": _index_key(),
            "chat_model": client.chat_model()}


def search_async(query: str, k: int = 4):
    """Start a search on a thread; returns getter(timeout_s) -> hits, or [] if still running."""
    box = {"hits": []}

    def _run():
        try:
            box["hits"] = search(query, k=k)
        except Exception:
            box["hits"] = []

    t = threading.Thread(target=_run, name="aux-lane", daemon=True)
    t.start()

    def _get(timeout_s: float = 1.5):
        t.join(timeout_s)
        return list(box["hits"]) if not t.is_alive() else []

    return _get


def embed_choices() -> list:
    """The picker's choices: embedding / ColBERT *.gguf files under the current one's grandparent."""
    cur = os.environ.get("SP_AUX_EMBED_GGUF", "")
    if not cur:
        return []
    base = os.path.dirname(os.path.dirname(cur))
    out = []
    try:
        for dp, _dns, fns in os.walk(base):
            for fn in fns:
                full = os.path.join(dp, fn).replace("\\", "/")
                low = full.lower()                 # the FOLDER names carry the kind (…-Embedding-350M-GGUF/)
                if low.endswith(".gguf") and ("embed" in low or "colbert" in low):
                    out.append(full)
    except Exception as _swx:
        _swallowed(_swlog, "embed_choices", _swx, lane="sidecar")
    return sorted(set(out + [cur.replace("\\", "/")]))
