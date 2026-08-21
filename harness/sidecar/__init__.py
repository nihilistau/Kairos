"""AUX MODELS — small, fast, CPU-resident helpers around the one big model.

THE DIVISION OF LABOR (2026-08-20, the LFM2.5 integration). The 26B is HER — voice,
memory authority, judgment about him. The aux models are hands and reading glasses:
they retrieve, embed, judge yes/no, and compress long text INTO her context. They
never speak as her, never write memory on their own authority, and everything they
return arrives in her context labelled with where it came from. Seamless offload,
not a second self.

WHY A SIDECAR AND NOT THE ENGINE. LFM2.5 is a hybrid conv+attention architecture
(gated short convolutions + GQA); our CUDA engine implements gemma4/qwen3 forwards
and nothing conv-shaped. A native sp-model port is REGISTERED work (docs/AUX-MODELS.md
carries the arming condition), not tonight's: llama.cpp already runs these GGUFs on
CPU at the speeds Liquid ships them for, LM Studio's backend packs already carry
`llama-server.exe` on this machine, and CPU is the entire point — the model keeps
every megabyte of VRAM.

Two doors, both OpenAI-compatible, both env-configured through serve.py's one door:
  SP_AUX_EMBED_URL  — a llama-server --embedding instance (default :8811). Serves
                      LFM2.5-Embedding-350M (1024-dim CLS). LM Studio's typing
                      heuristic mis-files that GGUF as an LLM and refuses it on
                      /v1/embeddings, so embeddings get their own server.
  SP_AUX_CHAT_URL   — LM Studio's server (default :1234, bearer token from
                      SP_AUX_API_KEY_FILE). Serves the LFM2.5 instruct models for
                      judge/summarize work; JIT-loads what is asked for.

The seams:
  client.embed / client.chat / client.judge   — transport, timeouts, empty-is-empty
  archive.search / archive.build_index        — deep recall over every conversation
  summarize.read_long                         — long text -> short text, map/reduce
  tools.deep_recall                           — HER tool: the archive, with provenance
"""
