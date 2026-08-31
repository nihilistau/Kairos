"""semindex — S0 of the SEM stack (docs/SEMANTICS.md): the sidecar semantic index.

One JSONL file (`SP_SEM_INDEX`), one row per signed fact. DERIVED DATA: recomputable
from registry + model, so losing it costs a backfill, never a memory.

The rules, each one a bug this repo has already paid for (SEMANTICS.md §3):
  - NEVER writes the registry. This module imports nothing that can.
  - Append-only. Nothing here deletes, including its own rows. An upgraded embedding
    is a NEW row; the reader takes the best row per (addr, ts).
  - Tombstone-BLIND by design: lifecycle lives in the registry and is honored at the
    read seam by joining on (addr, ts). A second copy of the tombstone flag is the
    two-paths bug with a new hat on.
  - The model tag is checked at read. Cosine between two models' spaces is noise
    with a confidence interval; alien rows are skipped, never compared.
  - NEVER blocks speech, never raises out: a failed mint is a telemetry counter
    (`dropped()`), not an error in her mouth.

Embedding spaces (the `model` tag):
  hash256-v1  sha1 bag-of-words hashing, 256-dim, L2-normed — byte-compatible with
              harness/nexus HashingEmbeddingProvider(256). Honest about being weak;
              exists so the machinery is real and gateable before the engine seam is.
  l5-512-v1   the engine's L5 query-key: raw LE f32[hd()] read from <episode_dir>/ep.l5
              (recall.rs episode format). /v1/capture DOES mint ep.l5 when
              SP_CAPTURE_L5=1 (routes.rs capture path, 2026-07-14; mapped from
              [sem] capture_l5). The retired daemon-writer path (B4/store_verb)
              is off. Sidecars are model artifacts — geom_tag must match or the
              reader skips them. Hash-space remains the fallback when no sidecar
              is present.
  aux-1024-v1 the CPU sidecar's LFM embedding (harness/sidecar/client.embed, the same
              door the archive uses), 1024-dim, L2-normed.

              WHY IT EXISTS (2026-08-23). l5-512-v1 IS UNOBTAINABLE ON THIS MODEL. The
              route that mints ep.l5 refuses on the model MoE — "gemma4_decode_cuda:
              gemma4-MoE not supported on this path (ADR-013)" — so 253 of 253 rows
              written since 2026-08-19 carry npos=0 and there has not been one ep.l5 in
              three weeks. The doc index was therefore 93% hash256 bag-of-words, which
              means EVERY embedding contender this repo measured and rejected was
              measured against a bag-of-words document index.

              MEASURED on the frozen corpus (fixtures/sem/, 50 facts / 100 paraphrase /
              60 foreign queries — the same rig that set the lexical bar):

                                    recall@1   recall@3   foreign false-hit
                  lexical baseline    0.4600     0.4600         0.5333
                  aux @ tau 0.40      0.5300     0.5300         0.5333

              More recall at IDENTICAL foreign noise. Through the real seam, and the
              decider hit rate - what actually reaches her context - goes 0.06 -> 0.17.

              RAW COSINE, NOT CENTERED, and this is load-bearing: centering on
              space_mean() — which l5-space NEEDS — collapses this space to recall@1
              0.2900, WORSE than lexical. The anisotropy centered_cosine was written for
              is an l5 pathology, not a property of embeddings. Wiring the new space
              through the existing centred branch "for consistency" would have shipped a
              measured regression. G-SEM-RANK holds the branch.

Address: addr_of(text) — sha256(norm(text))[:16], NORM IDENTICAL to tools/okf_mem.py
addr_of (the MEM-OKF content address). One address vocabulary across stores, by design.
"""
import hashlib
import json
import math
import os
import struct
import threading

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

MODEL_HASH = "hash256-v1"
MODEL_L5 = "l5-512-v1"
MODEL_AUX = "aux-1024-v1"
# ORDER IS PREFERENCE for load(): it keeps the LAST-ranked vector when a row carries
# several. The QUERY side (query_embed) must land in whichever space the DOCUMENTS are
# actually in, or every cosine is 0 — same-space-only is the one rule this file has. On
# this model that is the aux space, and query_embed says why in full.
# ── PRECEDENCE IS MEASURED, NOT CHRONOLOGICAL (2026-08-23) ────────────────────────────
# load() keeps ONE row per (addr, ts) and later-in-this-tuple wins. That made it a ranking
# of embedding quality by accident of when each space was added, and on 2026-08-23 the
# accident bit: the episode backfill gave 259 of her 274 live rows an l5 vector, l5
# outranked aux by tuple position, and her document index silently swapped spaces.
#
# MEASURED on the frozen 50-fact / 160-query scoreboard, same corpus for all three:
#     l5-512-v1     seam_recall_at_1 0.10     (harness_tests/sem_rank_score.py --keep-index)
#     lexical floor                  0.46     (fixtures/sem/baseline-receipt.json)
#     aux-1024-v1                    0.53     (fixtures/sem/aux-receipt.json)
#
# l5's cosines LOOK healthy on true pairs (0.73-0.80) and it still ranks at 0.10, because
# a space that scores everything similar to everything discriminates nothing. So aux wins,
# and the tuple now says so out loud.
#
# This also makes load() agree with query_embed(), which already put aux first and whose
# comment asked for exactly this: "If capture is ever fixed, measure again and revisit
# this order." Capture was fixed this morning; this is the revisit. A query is embedded in
# aux space, so aux documents are what it can match — hiding them behind a better-numbered
# tag was the whole regression.
KNOWN_MODELS = (MODEL_HASH, MODEL_L5, MODEL_AUX)
_HASH_DIM = 256
_L5_DIM = 512
_AUX_DIM = 1024

_LOCK = threading.RLock()
_DROPPED = 0        # telemetry: silent mint failures (never an exception outward)


# ── address (MEM-OKF-identical) ────────────────────────────────────────────────────────
def norm(body: str) -> str:
    """EXACTLY tools/okf_mem.py norm(). Do not 'improve' one without the other."""
    return body.replace("\r\n", "\n").strip() + "\n"


def addr_of(text: str) -> str:
    return hashlib.sha256(norm(text).encode("utf-8")).hexdigest()[:16]


# ── config ─────────────────────────────────────────────────────────────────────────────
def index_path() -> str:
    return os.environ.get("SP_SEM_INDEX", "")


def enabled() -> bool:
    """Armed only when BOTH the flag and the path exist. Both are mapped in serve.py
    (G-ONEDOOR: an unmapped knob does not exist)."""
    return os.environ.get("SP_SEM_MINT", "0") == "1" and bool(index_path())


def dropped() -> int:
    return _DROPPED


# ── embedding providers ────────────────────────────────────────────────────────────────
def hash_embed(text: str, dim: int = _HASH_DIM):
    """Byte-compatible with nexus HashingEmbeddingProvider.embed (sha1 buckets, L2)."""
    vec = [0.0] * dim
    for tok in text.lower().split():
        h = int(hashlib.sha1(tok.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    n = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / n, 6) for v in vec]


def read_ep_l5(out_dir: str):
    """<out_dir>/ep.l5 — raw little-endian f32[512], already L2-normed by the engine.
    Returns None when absent/short/non-finite: the caller degrades, never errors."""
    try:
        p = os.path.join(out_dir or "", "ep.l5")
        if not os.path.isfile(p):
            return None
        with open(p, "rb") as f:
            raw = f.read()
        if len(raw) < _L5_DIM * 4:
            return None
        vec = list(struct.unpack("<%df" % _L5_DIM, raw[:_L5_DIM * 4]))
        if not all(math.isfinite(v) for v in vec):
            return None
        return [round(v, 6) for v in vec]
    except Exception as _swx:
        _swallowed(_swlog, "read_ep_l5", _swx, lane="skills")
        return None


def aux_enabled() -> bool:
    """The aux doc/query space, armed by [sem].aux_embed -> SP_SEM_AUX_EMBED."""
    return os.environ.get("SP_SEM_AUX_EMBED", "0") == "1"


def aux_tau() -> float:
    """The admission threshold for THE AUX SPACE. Its own knob, and it must be: SP_SEM_TAU
    (0.60, chosen for l5's inflated raw cosines) admits nothing at all here.

    0.40 IS MEASURED THROUGH THE REAL SEAM (harness_tests/sem_aux.py), not off a notebook.
    A top-1-only calculation said 0.20 looked best; the seam admits EVERY row over tau, so
    at 0.20 it also injected an unrelated fact on 55% of foreign queries — the "she recited
    a memory nobody asked about" bug, bought back. Swept on the frozen corpus:

        tau   recall@1  decider_hit  foreign_seam  foreign_inject
        lex     0.4600       0.0600        0.5333          0.1333   <- the bar
        0.25      0.83         0.62        0.6333          0.4
        0.30      0.70         0.45        0.5333          0.2
        0.35      0.58         0.24        0.5333          0.15
        0.40      0.53         0.17        0.5333          0.1333   <- nothing is worse
        0.50      0.47         0.07        0.5333          0.1333

    0.40 is the MOST recall available for which NOT ONE metric degrades. 0.35 buys another
    41% of true injections for one extra foreign injection in sixty; that is a real trade
    and it is his to make, not one to smuggle into a default."""
    try:
        return float(os.environ.get("SP_SEM_TAU_AUX", "0.40"))
    except Exception as _swx:
        _swallowed(_swlog, "aux_tau", _swx, lane="skills")
        return 0.40


def aux_embed(texts):
    """Embed through the CPU sidecar. Returns a list of vectors, or None on any failure —
    the caller degrades to hash-space, never raises, never blocks a turn. Never imports
    the memory package; this is the derived side asking the librarian for a number."""
    try:
        if not aux_enabled():
            return None
        from harness.sidecar import client as _c
        out = _c.embed(list(texts))
        if not out or len(out) != len(list(texts)):
            return None
        for v in out:
            if len(v) != _AUX_DIM or not all(math.isfinite(x) for x in v):
                return None
        return [[round(float(x), 6) for x in v] for v in out]
    except Exception as _swx:
        _swallowed(_swlog, "aux_embed", _swx, lane="skills")
        return None


def cosine(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


# ── the file ───────────────────────────────────────────────────────────────────────────
def _append(row: dict) -> None:
    p = index_path()
    with _LOCK:
        d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load(models=KNOWN_MODELS) -> dict:
    """{(addr, ts): row} — best row per key. Later rows win within a model; l5-space
    outranks hash-space (an upgrade is an append, never an edit). Alien model tags
    are SKIPPED — dead rows are kept on disk and ignored, never compared."""
    p = index_path()
    out = {}
    if not p or not os.path.exists(p):
        return out
    rank = {m: i for i, m in enumerate(KNOWN_MODELS)}     # later in tuple = better
    with open(p, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if r.get("model") not in models:
                continue
            k = (r.get("addr", ""), r.get("ts", ""))
            prev = out.get(k)
            if prev is None or rank.get(r["model"], -1) >= rank.get(prev["model"], -1):
                out[k] = r
    return out


# ── mint (the ONLY writers, both silent-failure) ───────────────────────────────────────
def mint(fact: str, ts: str, out_dir: str = None) -> bool:
    """Index one fact. Called by memory.remember() right after the registry append.
    Prefers the engine's ep.l5 when out_dir already has one; else hash-space. NEVER
    raises; a False is a telemetry tick, not a problem the turn needs to hear about."""
    global _DROPPED
    try:
        if not enabled() or not fact:
            return False
        # ts may be missing: 12 live rows are store-verb-era daemon writes (ep_live_m*,
        # ts:null — the G-ONEWRITER story). Their join key degrades to (addr, "") rather
        # than excluding them from semantics forever. Same text ⇒ same addr, so the
        # degenerate key stays unambiguous.
        vec = read_ep_l5(out_dir) if out_dir else None
        model = MODEL_L5
        if vec is None:
            # the engine's L5 is unobtainable on the model MoE (see the header) — ask the
            # CPU sidecar before falling to the bag-of-words floor
            got = aux_embed([fact])
            if got:
                vec, model = got[0], MODEL_AUX
        if vec is None:
            vec, model = hash_embed(fact), MODEL_HASH
        _append({"addr": addr_of(fact), "ts": ts or "", "model": model, "vec": vec})
        return True
    except Exception:
        _DROPPED += 1
        return False


def upgrade(out_dir: str, fact: str, ts: str) -> bool:
    """Worker-side second chance: after the async capture lands, append an l5-space
    row IF the engine wrote ep.l5 into the episode dir. No-op today (see header);
    live the day the engine mints ep.l5 on the /v1/capture path."""
    global _DROPPED
    try:
        if not enabled() or not fact:
            return False
        vec = read_ep_l5(out_dir)
        if vec is None:
            return False
        _append({"addr": addr_of(fact), "ts": ts or "", "model": MODEL_L5, "vec": vec})
        return True
    except Exception:
        _DROPPED += 1
        return False


# ── read-side: cached load + query embedding (S1 support) ────────────────────────────
_CACHE = {"key": None, "idx": None}


def load_cached(models=KNOWN_MODELS) -> dict:
    """load(), memoized on (path, mtime, size). Size is in the key because an in-place
    rewrite inside one mtime tick is exactly how a stale cache served a dead vector
    during G-SEM-RANK's own bring-up — measure the thing, not the proxy."""
    p = index_path()
    try:
        st = os.stat(p) if p and os.path.exists(p) else None
        key = (p, st.st_mtime_ns, st.st_size) if st else (p, None, None)
    except Exception:
        key = (p, None, None)
    with _LOCK:
        if _CACHE["key"] == key and _CACHE["idx"] is not None:
            return _CACHE["idx"]
        idx = load(models)
        _CACHE.update(key=key, idx=idx, mu={})
        return idx


def space_mean(model=MODEL_L5):
    """Mean vector of the index rows in one embedding space — the anisotropy correction.

    MEASURED (2026-07-14, the tau-sweep receipt): raw l5 question-space cosine does not
    discriminate as an ABSOLUTE threshold — every (query, fact) pair scored >= 0.70,
    foreign precision 0.0167 even at tau 0.80 — because the space is anisotropic: all
    vectors share a dominant common direction. G-REP-LAYER-L5's 88.5% is recall@1, a
    RANKING number; the engine only ever uses this signal as an argmax. To use it as an
    admission threshold, subtract the population mean first (the standard all-but-the-top
    correction): after centering, unrelated pairs fall near 0 and related pairs keep
    their margin. The mean is over HER indexed facts — the population she actually knows —
    and is cached with the index. None when the space has < 3 rows (fall back to raw)."""
    idx = load_cached()
    with _LOCK:
        mu = _CACHE.get("mu", {}).get(model)
        if mu is not None:
            return mu or None                        # [] sentinel -> None
        vecs = [r["vec"] for r in idx.values()
                if r.get("model") == model and r.get("vec")]
        if len(vecs) < 3:
            _CACHE.setdefault("mu", {})[model] = []  # remember the miss too
            return None
        dim = len(vecs[0])
        mu = [sum(v[i] for v in vecs) / len(vecs) for i in range(dim)]
        _CACHE.setdefault("mu", {})[model] = mu
        return mu


def centered_cosine(a, b, mu) -> float:
    if mu is None or len(mu) != len(a) or len(a) != len(b):
        return cosine(a, b)
    return cosine([x - m for x, m in zip(a, mu)], [y - m for y, m in zip(b, mu)])


_EMBED_DOWN_UNTIL = 0.0     # negative cache: a dead daemon costs ONE probe a minute,
_EMBED_HOLDOFF = 60.0       # not a timeout per recall — the seam runs every turn.


def query_embed(query: str):
    """(vec, model_tag) for a live query. The tag rides along so the seam only ever
    compares same-space vectors: cosine across spaces is noise.

    ORDER, and it is measured, not conventional (2026-08-23): the AUX space first when it
    is armed, then the daemon's /v1/embed (the engine's l5_query_embed — the
    88.5%-paraphrase selector) with a short timeout, then the hash floor. On ANY failure
    it degrades and holds daemon retries off for a minute. The order is explained in full
    at the branch below; the short version is that the engine can embed a QUERY and cannot
    embed a DOCUMENT on this model, so an l5 query has almost nothing to match."""
    global _EMBED_DOWN_UNTIL
    import time as _time
    import urllib.request
    # ── THE ASYMMETRY THAT DECIDES THE ORDER (2026-08-23) ─────────────────────────────
    # /v1/embed WORKS on the model MoE and answers in ~1.47 s. /v1/capture does NOT — it
    # refuses (ADR-013), so no ep.l5 has been minted in three weeks. The engine can embed
    # a QUERY and cannot embed a DOCUMENT. Asking it first would spend 1.47 s of every
    # turn producing an l5 vector with 57 stale rows to match against, out of 229 live
    # ones — a real per-turn cost for a gate that cannot fire. So when the aux space is
    # armed it goes first: it is the only space with a COMPLETE document side on this
    # model. If capture is ever fixed, measure again and revisit this order — that is
    # what G-SEM-RANK's coverage check is for.
    #
    # AND IT COMES BEFORE THE BACKEND CHECK, NOT AFTER (caught the same day, by the gate
    # speed-up of all things). The engine capability gate below returns the hash floor when
    # the backend has no /v1/embed — and the aux space is a CPU SIDECAR that has nothing to
    # do with the backend. With the aux branch after it, ANY foreign engine made the aux
    # space unreachable: hash-space queries against an aux-space document index, every
    # cosine 0, the whole gate silently dead. That is precisely Kairos's configuration,
    # where aux is the ONLY space there is.
    if aux_enabled():
        got = aux_embed([query])
        if got:
            return got[0], MODEL_AUX
        # AND IF THE SIDECAR IS DOWN, THE FLOOR — NOT the engine. Falling through to l5
        # here would be worse on both counts at once: 1.47 s for a vector with 57 stale
        # documents to match, against ~0 ms for a hash vector with 757. When the documents
        # are in the aux space, an l5 query is not a degradation, it is a dead end.
        return hash_embed(query), MODEL_HASH
    # ENGINE-AGNOSTIC (2026-08-21): the daemon's L5 only when the backend HAS one; then
    # the hash floor. Reached only when the aux space is not armed or its sidecar is down.
    try:
        from harness.inference.backends import supports as _sup
        _has_l5 = _sup("embed")
    except Exception:
        _has_l5 = True
    if not _has_l5:
        return hash_embed(query), MODEL_HASH
    if _time.monotonic() >= _EMBED_DOWN_UNTIL:
        daemon = os.environ.get("SP_DAEMON_URL", "http://127.0.0.1:3000")
        try:
            body = json.dumps({"text": query}).encode()
            req = urllib.request.Request(daemon + "/v1/embed", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=1.5) as r:
                j = json.loads(r.read().decode())
            vec = j.get("l5") or []
            if len(vec) == _L5_DIM and all(math.isfinite(v) for v in vec):
                return [round(float(v), 6) for v in vec], MODEL_L5
            _EMBED_DOWN_UNTIL = _time.monotonic() + _EMBED_HOLDOFF
        except Exception:
            _EMBED_DOWN_UNTIL = _time.monotonic() + _EMBED_HOLDOFF
    return hash_embed(query), MODEL_HASH


# ── maintenance: coverage / verify / backfill ─────────────────────────────────────────
def _live(registry_rows):
    return [r for r in registry_rows if not r.get("lifecycle") and r.get("text")]


def _key(r) -> tuple:
    return (addr_of(r["text"]), r.get("ts") or "")


def coverage(registry_rows) -> dict:
    idx = load()
    live = _live(registry_rows)
    have = sum(1 for r in live if _key(r) in idx)
    return {"live": len(live), "indexed": have,
            "coverage": round(have / len(live), 4) if live else None}


def verify(registry_rows) -> list:
    """Recompute-and-diff, MEM-OKF-conformance-shaped. hash-space rows must equal the
    recomputation from the registry text they claim to index; l5-space rows must be
    512-dim, finite, unit-norm (the engine's contract). Returns a list of finite
    witnesses — (addr, ts, why) — empty means green."""
    bad = []
    by_key = {}
    for r in _live(registry_rows):
        by_key[_key(r)] = r
    for (a, ts), row in load().items():
        vec = row.get("vec") or []
        if row["model"] == MODEL_HASH:
            reg = by_key.get((a, ts))
            if reg is None:
                continue        # tombstoned or superseded since — dead rows are kept, not errors
            if vec != hash_embed(reg["text"]):
                bad.append((a, ts, "hash-space vector does not recompute from registry text"))
        elif row["model"] == MODEL_L5:
            if len(vec) != _L5_DIM:
                bad.append((a, ts, "l5-space row is not 512-dim"))
            elif not all(math.isfinite(v) for v in vec):
                bad.append((a, ts, "l5-space row has non-finite components"))
            elif abs(math.sqrt(sum(v * v for v in vec)) - 1.0) > 0.02:
                bad.append((a, ts, "l5-space row is not unit-norm"))
    return bad


def backfill(registry_rows) -> dict:
    """Mint a hash-space row for every live registry row that has none. Idempotent.
    Requires enabled(); refuses silently otherwise (the flag is the contract)."""
    if not enabled():
        return {"minted": 0, "skipped": 0, "refused": 0,
                "note": "SP_SEM_MINT off or SP_SEM_INDEX unset"}
    idx = load()
    minted = skipped = refused = 0
    for r in _live(registry_rows):
        if _key(r) in idx:
            skipped += 1
        elif mint(r["text"], r.get("ts") or "", out_dir=r.get("dir")):
            minted += 1
        else:
            refused += 1        # never a silent third bucket
    return {"minted": minted, "skipped": skipped, "refused": refused}


def backfill_aux(registry_rows, batch: int = 32) -> dict:
    """UPGRADE every live row that has no aux-space vector yet (2026-08-23).

    An upgrade is an APPEND — the hash row stays on disk, exactly as the l5 upgrade path
    works, because this file is append-only and tombstone-blind by construction. Batched
    because the sidecar embeds a list far faster than one at a time (measured: 210 texts
    in 6.1 s), and this runs over the whole store.

    Idempotent: a row that already carries an aux vector is skipped. Requires enabled()
    AND aux_enabled(); says which one is missing rather than returning a silent zero."""
    if not enabled():
        return {"upgraded": 0, "skipped": 0, "note": "SP_SEM_MINT off or SP_SEM_INDEX unset"}
    if not aux_enabled():
        return {"upgraded": 0, "skipped": 0, "note": "SP_SEM_AUX_EMBED off"}
    have = set()
    try:
        with open(index_path(), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("model") == MODEL_AUX:
                    have.add((r.get("addr"), r.get("ts") or ""))
    except Exception as _swx:
        _swallowed(_swlog, "backfill_aux", _swx, lane="skills")
    live = list(_live(registry_rows))
    todo = [r for r in live if (addr_of(r["text"]), r.get("ts") or "") not in have]
    upgraded = failed = 0
    for i in range(0, len(todo), max(1, int(batch))):
        chunk = todo[i:i + max(1, int(batch))]
        vecs = aux_embed([r["text"] for r in chunk])
        if not vecs:
            failed += len(chunk)
            continue
        for r, v in zip(chunk, vecs):
            _append({"addr": addr_of(r["text"]), "ts": r.get("ts") or "",
                     "model": MODEL_AUX, "vec": v})
            upgraded += 1
    return {"upgraded": upgraded, "skipped": len(live) - len(todo), "failed": failed}


if __name__ == "__main__":
    import sys
    reg_path = os.environ.get("SP_RECALL_REGISTRY", "")
    rows = []
    if reg_path and os.path.exists(reg_path):
        with open(reg_path, encoding="utf-8") as f:
            rows = [json.loads(x) for x in f if x.strip()]
    if "--backfill" in sys.argv:
        print(json.dumps(backfill(rows)))
    if "--backfill-aux" in sys.argv:
        print(json.dumps(backfill_aux(rows)))
    if "--verify" in sys.argv:
        bad = verify(rows)
        print(json.dumps({"bad": bad[:10], "count": len(bad)}))
        sys.exit(1 if bad else 0)
    if "--coverage" in sys.argv or len(sys.argv) == 1:
        print(json.dumps(coverage(rows)))
