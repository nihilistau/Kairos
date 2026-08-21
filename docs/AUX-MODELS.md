---
type: design
title: "AUX-MODELS — the LFM2.5 sidecars"
status: LIVE (2026-08-20): deep recall, page reading, judges on CPU; rerank/consolidate dark
---

# AUX-MODELS — the LFM2.5 sidecars (2026-08-20)

Small, fast, CPU-resident helpers around the one big model. The operator's brief,
verbatim in spirit: *seamless offload and seamless integration so that she seems
herself still.* This file is the design, the receipts, the boundaries, and the
roadmap.

## 0. The one rule

**Aux models are never her voice.** They retrieve, embed, judge yes/no, and compress
long text INTO her context. Everything they produce arrives labelled with where it
came from, she reasons over it in her own forward pass, and nothing they emit is
shown to him as her words. The corollary is the memory rule: **aux never writes the
registry** — retrieval is not testimony, and an index that could mint memories would
bypass every invariant (verdicts, testimony-over-inference, tombstones) the memory
system enforces. What comes back worth keeping goes through `remember()` by her hand.

## 1. Why a sidecar, not the engine (and when that changes)

LFM2.5 is a hybrid architecture: gated **short convolutions** + GQA attention blocks.
Our CUDA engine implements gemma4/qwen3 transformer forwards; it has no conv-mixer
path, so "convert the GGUF to sp format" is the easy half of a port — the forward
kernels are the real work (double conv, per-block gating, the bidirectional variants
for the retrievers). Meanwhile llama.cpp runs these GGUFs today, ON CPU, at the
speeds Liquid ships them for (their QAD Q4_0 checkpoints hold ~97% of BF16 quality),
and this machine already carries `llama-server.exe` inside LM Studio's backend packs.
CPU is the point: **the 2060's 12 GB stays 100% Gemma's** (ADR-KAI6), and the aux
fleet costs host RAM only (~0.4–1.7 GB per loaded model).

**Registered:** a native sp-model LFM2.5 port. Arming condition: a measured aux
workload where HTTP+CPU is the demonstrated bottleneck (not a hunch), or an embedded
use that cannot tolerate a sidecar process (e.g. in-engine recall scoring). Until a
receipt like that exists, the port is a rewrite in search of a reason.

## 2. Topology

```
her (26B, CUDA, sp-daemon :3000)  ── the voice, the judgment, the memory authority
   │
harness (gateway :8800)
   ├── harness/sidecar/client.py ── SP_AUX master arm; all transport; empty-is-empty
   │       ├── EMBED door  :8811  llama-server --embedding (CPU, spawned by serve.py)
   │       │       model: LFM2.5-Embedding-350M Q8_0 (1024-dim CLS, bidirectional)
   │       └── CHAT door   :1234  LM Studio server (bearer token from a FILE)
   │               model: LFM2.5-1.2B-Instruct QAD Q4_0 (default; 2.6B available JIT)
   ├── harness/sidecar/archive.py ── deep recall index over var/memory/transcripts/*
   ├── harness/sidecar/summarize.py ── map/reduce long-text reading
   └── harness/sidecar/tools.py ── deep_recall, HER tool (SP_AUX=1 adds it to the set)
```

Two doors because of a measured LM Studio defect: its typing heuristic files the
LFM2.5 embedding GGUF (which carries proper `pooling_type=2`, `causal=0` metadata)
as an LLM and refuses it on `/v1/embeddings` — so embeddings get a raw llama-server
from LM Studio's own backend pack (`extensions/backends/llama.cpp-win-x86_64-avx2-*`).
Both doors are OpenAI-compatible and both are knobs: any server that speaks the
shape (LM Studio, llama-server, vLLM, a future sp-native port) plugs in by URL.

The embed sidecar is **not the stack's child**: CPU-only, ~400 MB, stateless between
requests. `serve.py` spawns it if armed+absent (`launch_aux_embed`, pidfile under
`var/aux/`), adopts it if present, and `stop()` leaves it resident — the same
standing LM Studio itself has on this machine.

## 3. What is wired today

| Surface | Path | Behavior when aux is dark |
|---|---|---|
| **deep_recall** (her tool) | `sidecar/tools.py` → `archive.search` | tool says it is not armed; she answers from active memory |
| **web_search page-read** | `system_tools.web_search` → `summarize.read_long` | byte-identical old behavior (700-char truncation) |
| **judge()** (kairos pre-judge + watch judge) | `sidecar/client.judge` | returns `None` = no ruling; callers keep pre-aux logic |
| **read_long()** (harness library) | `sidecar/summarize.py` | returns `''` |

`deep_recall` is the memory extension the operator asked for: *"when I ask if she
remembers X and it's not in her immediate memory."* It searches EVERY day transcript
(chunked ~800 chars with 1-turn overlap, embedded at 1024-dim, cosine over one
numpy matmul), returns verbatim moments labelled `[YYYY-MM-DD]`, and its own return
text tells her to `remember()` anything worth keeping — the front door, where
verdicts and ranking live.

Index mechanics: per-file `.npz` + `.meta.jsonl` under `var/aux/archive/`, keyed by
`(mtime_ns, size)` like memory's health cache; day files only append so a change
re-chunks that file whole; a dead embedder **keeps the stale index** (stale beats
absent) and rebuilds on the next healthy pass. Embed calls are sliced 16 texts at a
time — one request carrying a 226-chunk day blew llama-server's batch on the first
live build.

Measured on this machine (CPU, Q8_0 embedder): query embed ~150 ms; corpus build
~3.6 s/chunk one-time (≈880 chunks ≈ 50 min for the full history, then incremental);
search itself is a matmul over a few thousand rows — microseconds.

## 4. Knobs (all through serve.py's one door; ledger rows in OFF-BY-DEFAULT §10)

| Knob | Profile key | Meaning |
|---|---|---|
| `SP_AUX` | `aux.enabled` | master arm; off = every caller pre-aux |
| `SP_AUX_EMBED_URL` | `aux.embed_url` | embedding door (default :8811) |
| `SP_AUX_CHAT_URL` | `aux.chat_url` | instruct door (default :1234) |
| `SP_AUX_CHAT_MODEL` | `aux.chat_model` | default `liquidai/lfm2.5-1.2b-instruct` |
| `SP_AUX_API_KEY_FILE` | `aux.api_key_file` | bearer token FILE (repo is public; the token itself never enters env or git) |
| `SP_AUX_INDEX_DIR` | `aux.index_dir` | archive index home (default `var/aux/archive`) |
| `SP_AUX_ARCHIVE_GLOBS` | `aux.archive_globs` | extra `;`-separated corpus globs |
| — | `aux.autostart` | serve.py spawns the embed sidecar |
| — | `aux.llama_server`, `aux.embed_gguf`, `aux.embed_ctx`, `aux.embed_threads` | sidecar launch parameters |

Gate: `harness_tests/h_aux.py` (offline; stubbed embedder drives the real chunker,
index math, tool text, and the dark-sidecar contract).

## 5. Roadmap — designed, not yet wired (each needs its own receipt)

1. **Kairos decider offload** — **WIRED AND ARMED 2026-08-20 09:xx** on the
   operator's explicit call. `kairos/offload.py` pre-judges "worth a turn?" on the
   CPU 1.2B before any 26B work (fail-open, REMIND never gated, the sidecar never
   shapes her words); `watch.py::_judge_sidecar` moves the watch poll's YES/NO to
   CPU with the at-the-door grounding unchanged and the model as fallback. H-AUX
   §6/§7. The A/B reads from `[kairos] sidecar pre-judge` lines vs TURN-PHASE
   cadence in var/daemon.log.
2. **ColBERT rerank** — `LFM2.5-ColBERT-350M-Q8_0.gguf` is on disk. Late interaction
   needs per-token vectors (llama-server `--pooling none`), MaxSim in numpy, rerank
   of the embedding stage's top-50. Arming condition: a measured case where CLS
   retrieval returns the wrong moment in the top-4 and ColBERT fixes it — build the
   eval from her real "do you remember" queries, not synthetic ones.
3. **Registry-assist recall** — embed registry rows too, as a *candidate generator*
   for the existing ranked recall (never a replacement for the seam; the verdicts
   still rule). Arming condition: a measured recall miss the lexical path cannot fix.
4. **Research/search breadth** — `research.py` map/reduce through the 2.6B
   (tool-trained, 128K context) for multi-page reading; the model gets the synthesis.
5. **Consolidation prefilter** — the nightly consolidator reads whole days through
   the model; the 1.2B can pre-cluster and dedupe candidate facts first.
6. **sp-native port** — §1's arming condition.

## 6. What this deliberately does not do

- No aux text is ever emitted as her speech (voice boundary, §0).
- No registry writes from aux code — enforced by gate section 4 (import scan).
- No GPU: the sidecars are CPU-pinned (`--gpu off` on the chat door, avx2 pack on
  the embed door). The 26B's VRAM is not shared, per ADR-KAI6 and the 2026-07-31
  TTS CUDA-fault receipt.
- No auth secrets in the repo: the LM Studio token lives in `var/secrets/` (ignored)
  and travels as a file path.
