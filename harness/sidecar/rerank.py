"""COLBERT RERANK — late interaction over the archive's CLS candidates. DARK BY DEFAULT.

The CLS embedding door returns one vector per text: fast, tiny index, and blind to
word-level alignment. ColBERT keeps a vector PER TOKEN and scores by MaxSim — for
each query token, the best-matching document token, summed — which is what rescues
queries whose exact words matter ("the SILVER nightie", not any nightie).

ARMING CONDITION (OFF-BY-DEFAULT §11 / AUX-MODELS roadmap #2): a measured
deep_recall miss where CLS top-4 returns the wrong moment and this stage fixes it,
built from her real "do you remember" queries. Until that receipt exists this stays
dark: SP_AUX_RERANK=1 arms it, and a dark or failing rerank ALWAYS falls back to
the CLS order — reranking may only ever reorder, never lose a candidate.

The token-vector door is its own llama-server (`--pooling none`, port 8812 by
default, model LFM2.5-ColBERT-350M): per-token output is a different response
shape, so it cannot share the CLS instance. Live verification of that door's
response shape is PART of the arming condition — the offline gate proves the
MaxSim math and the fallback contract on stubs.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Callable, List, Optional

import numpy as np

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

_TIMEOUT = 60


def enabled() -> bool:
    return os.environ.get("SP_AUX_RERANK", "0") == "1"


def _url() -> str:
    return os.environ.get("SP_AUX_COLBERT_URL", "http://127.0.0.1:8812").rstrip("/")


def _token_embed(texts: List[str]) -> Optional[List[np.ndarray]]:
    """Per-token embeddings: one [n_tokens x d] matrix per text, or None on any
    failure. llama-server with --pooling none returns a list of token vectors in
    place of the pooled vector."""
    try:
        req = urllib.request.Request(_url() + "/v1/embeddings",
                                     data=json.dumps({"input": texts}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        rows = sorted(d["data"], key=lambda x: x.get("index", 0))
        out = []
        for row in rows:
            m = np.asarray(row["embedding"], dtype=np.float32)
            if m.ndim != 2 or not m.size:      # pooled shape = the wrong server
                return None
            n = np.linalg.norm(m, axis=1, keepdims=True)
            n[n == 0] = 1.0
            out.append(m / n)
        return out if len(out) == len(texts) else None
    except Exception as _swx:
        _swallowed(_swlog, "_token_embed", _swx, lane="sidecar")
        return None


# seam for the offline gate
_TOKEN_EMBED: Callable[[List[str]], Optional[List[np.ndarray]]] = _token_embed


def maxsim(q: np.ndarray, d: np.ndarray) -> float:
    """Late-interaction score: for each query token, its best document token,
    summed. Inputs are L2-normalized [n x dim] matrices."""
    if q.size == 0 or d.size == 0:
        return 0.0
    return float((q @ d.T).max(axis=1).sum())


def rerank(query: str, hits: List[dict], k: int) -> List[dict]:
    """Reorder `hits` (each carrying 'text') by MaxSim; top-k. THE CONTRACT:
    any failure — knob off, dark server, wrong shape — returns hits[:k] in the
    order they arrived. Reranking may reorder; it may never lose or invent."""
    if not enabled() or not hits:
        return hits[:k]
    qm = _TOKEN_EMBED([query[:512]])
    if not qm:
        return hits[:k]
    dm = _TOKEN_EMBED([h["text"][:2000] for h in hits])
    if not dm:
        return hits[:k]
    scored = sorted(zip(hits, (maxsim(qm[0], m) for m in dm)),
                    key=lambda p: -p[1])
    out = []
    for h, s in scored[:k]:
        h = dict(h)
        h["rerank"] = round(s, 4)
        out.append(h)
    return out
