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

## 4. The framework — the settings section `Aux — the quiet librarians` (2026-08-22)

One section, the same knob framework as everything else (`harness/tuning/registry.py`): boot
defaults in the profile's `[aux]` block through serve.py's one door; live knobs read through the
override-only bridge (`registry.tune_or_env`) so an untouched panel still obeys the profile. The
window is **librarians** (📚) in the room; its chip says `embed ✓ chat ✓ · N` / `embed dark` / `off`.

| Knob | Scope | Meaning |
|---|---|---|
| `aux.enabled` (`SP_AUX`, `[aux].enabled`) | profile | the master arm; off = every caller keeps its pre-aux behaviour |
| `aux.chat_model` (`SP_AUX_CHAT_MODEL`) | live | the judge / extract model on the chat door; the picker's choices are what LM Studio lists right now (`client.list_models()`, cached 60 s) |
| `aux.embed_model` (`SP_AUX_EMBED_GGUF`, `[aux].embed_gguf`) | profile (restart) | the GGUF the embed sidecar is launched with; choices = the embedding / ColBERT `.gguf` files beside it |
| `aux.query_prefix` | live | **the soft prompt** — prepended to every deep-recall query before embedding; her-conditioned retrieval, the cheap way; empty = bare |
| `aux.doc_prefix` | live | prepended to every chunk at index time; the index stamp carries its hash, so a change re-embeds on the next refresh |
| `aux.spine_rerank` | live | the hybrid re-score (`sidecar/rank.py`): cosine + 0.25·lexical overlap + 0.10·recency (90 d) + 0.15·testimony bond (the chunk backs a live fact); off = raw cosine (A/B) |
| `aux.auto_recall` | live, **off** | the candidate lane: on turns that ask, the archive is searched IN PARALLEL with the spine; dropped unread at `aux.early_exit_hits` spine facts; else up to two labelled moments join the recall note (OFF-BY-DEFAULT §14) |
| `aux.early_exit_hits` | live | the lane's early exit (default 3) |
| `aux.rerank` (`SP_AUX_RERANK`) | profile | the ColBERT stage — dark (OFF-BY-DEFAULT §11) |
| `aux.judge_kairos`, `aux.judge_watch` | live | the two judges (were `SP_KAIROS_JUDGE` / `SP_AUX_WATCH_JUDGE`; the profile still carries the boot default) |
| **`sight.backend`** (section `Sight — her eyes`) | live | which eyes: `engine` (the served model's own vision / the seam's image_url on a foreign endpoint — today's logic, the default) · `aux_vl` (an LFM2.5-VL GGUF on the aux chat door — the 2060 stays hers) · `openai` (the seam's image_url regardless); every look (`look_at`, `take_photo`, `take_screenshot`, the hourly eye) goes through `sight._describe` and ONE scrub (`sight._scrub`) |
| `sight.vl_model` (`SP_AUX_VL_MODEL`, `[aux].vl_model`) | live | the VL model id on the door; choices = the door's ids with `vl`/`vision` in the name; a VL door ARMS her sight tools on a checkpoint without a vision row |
| `sight.vl_max_tokens`, `sight.vl_detail` | live | the VL description budget; `image_url.detail` where honoured |
| `SP_AUX_EMBED_URL` / `SP_AUX_CHAT_URL` / `SP_AUX_API_KEY_FILE` / `SP_AUX_INDEX_DIR` / `SP_AUX_ARCHIVE_GLOBS`, `[aux].autostart/llama_server/embed_ctx/embed_threads` | profile | the doors, the token FILE, the index home, extra corpus globs, the sidecar launch |

**The silent-librarian rule, in code** (`client.chat_json`): every aux judgement/extraction is
structured output only — JSON with named keys, validated, `None` on any failure; `judge()` is
JSON-first with the one-word fallback. `research.py` returns **extracts** (claims + sources, gaps)
and the model writes the answer; every `read_long` digest reaches her through `summarize.labelled()`
("context, not your words"). The archive **warms** at gateway start (`archive.warm()`), and the
window's *rebuild index* button calls the same.

Gates: `harness_tests/g_aux_librarian.py` (offline, a fake sidecar on the wire; 52 checks);
`harness_tests/h_aux.py` (offline; the dark-sidecar contract, aux never writes memory);
`harness_tests/h_aux_recall.py` (LIVE; the recall set four ways, receipts in `gates/AUX-RECALL-*.md`).

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
   of the embedding stage's top-50. Still dark (`aux.rerank`). Arming condition: a measured
   case where the shipped stage (soft-prompted query + spine rerank, 2026-08-22) returns
   the wrong moment in the top-4 and ColBERT fixes it — `h_aux_recall.py` is the eval;
   fill its set from her real "do you remember" queries, not synthetic ones.
3. **The candidate lane** — LANDED 2026-08-22 as `aux.auto_recall` (off): the archive
   searched in parallel with the spine's recall, dropped unread when the spine already has
   enough, else up to two labelled moments join the note — candidates, never authority.
   Arming condition: the H-AUX-RECALL receipt shows the lane finds moments the spine misses
   on the fixture. Registry rows as embedding candidates (3b) remain designed, not wired.
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
