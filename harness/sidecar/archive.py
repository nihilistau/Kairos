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
from typing import Callable, Dict, List, Optional

import numpy as np

from harness.sidecar import client

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# the embed seam (tests swap this; live code never should)
_EMBED: Callable[[List[str]], List[List[float]]] = client.embed

# ~800 chars ≈ 200 tokens: small enough that a hit is a MOMENT, big enough to
# carry its own context. Documents cap at the retriever's 512-token training
# length with room to spare.
_CHUNK_CHARS = 800
_OVERLAP_TURNS = 1


def _sources() -> List[str]:
    """The corpus: day transcripts (the canonical record of every conversation).
    SP_AUX_ARCHIVE_GLOBS extends it (';'-separated globs) without a code change."""
    pats = [os.path.join(_ROOT, "var", "memory", "transcripts", "*.jsonl")]
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


def _day_of(path: str) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
    return m.group(1) if m else os.path.basename(path)


def _chunk_file(path: str) -> List[Dict]:
    """Turn a day transcript into chunks: consecutive turns packed to ~_CHUNK_CHARS,
    each chunk prefixed by its day and carrying (source, day, turn span)."""
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
    except Exception:
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


def _stamp(path: str) -> str:
    st = os.stat(path)
    return "%d-%d" % (st.st_mtime_ns, st.st_size)


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
            except Exception:
                pass
        chunks = _chunk_file(src)
        if not chunks:
            continue
        # SLICED, 16 texts a call: one request carrying a whole day (226 chunks
        # x ~200 tok) blows llama-server's batch and the file silently kept its
        # stale index — measured on the very first live build (5 of 10 files).
        vecs: List[List[float]] = []
        ok = True
        texts = [c["text"] for c in chunks]
        for i0 in range(0, len(texts), 16):
            part = _EMBED(texts[i0:i0 + 16])
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
        os.replace(tmp, npz_p)
        tmp2 = meta_p + ".tmp"
        with open(tmp2, "w", encoding="utf-8") as f:
            f.write(json.dumps({"stamp": stamp, "n": len(chunks)}) + "\n")
            for c in chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        os.replace(tmp2, meta_p)
        built[os.path.basename(src)] = len(chunks)
    return built


def _load_all() -> Optional[Dict]:
    d = _index_dir()
    mats, metas = [], []
    for npz_p in sorted(glob.glob(os.path.join(d, "*.npz"))):
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
    return {"v": np.vstack(mats), "meta": metas}


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
        except Exception:
            pass                         # stale beats absent
    qv = _EMBED([query])
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
    width = 50 if _rr.enabled() else max(1, k)
    order = np.argsort(-scores)[:width]
    out = []
    for i in order:
        m = idx["meta"][int(i)]
        out.append({"day": m["day"], "source": m["source"],
                    "text": m["text"], "score": round(float(scores[int(i)]), 4)})
    if _rr.enabled():
        out = _rr.rerank(query, out, max(1, k))
    return out
