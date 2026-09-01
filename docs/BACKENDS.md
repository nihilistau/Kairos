---
type: reference
title: "BACKENDS — one inference surface, two backends, and what degrades"
status: LIVE (2026-08-21, Phase 3 of the Kairos plan) — gate: harness_tests/g_backend_seam.py
---

# BACKENDS — one inference surface, two backends

Everything in the harness that talks to a model goes through `harness.inference.client.get_client()`.
It returns ONE of two backends behind one surface (`chat_stream / chat / oneshot / abort / metrics /
health / subscribe_events / last_kairos / kind / supports`):

| `[engine].kind` | what | where |
|---|---|---|
| `sp` (the default on every existing profile) | the Rust + CUDA **sp-daemon** — Kairos's own engine | `harness/inference/client.py::SPDaemonClient` |
| `openai` (`profiles/companion.toml`) | any `/v1/chat/completions` server: LM Studio, `llama-server`, vLLM, a cloud | `harness/inference/backends/openai.py::OpenAIClient` |

`supports` is the honest capability set. Every seam that needs a daemon-only capability asks it and
**degrades with a stated loss** — never fails, never pretends. `InferenceConfig.to_openai_chat` sends
only the PORTABLE fields (`top_k` / `repeat_penalty` only under `dialect = "llamacpp"`); every SP-ONLY
field is dropped and the drop is logged once.

## What the sp-daemon gives, and what the openai backend does instead

| capability | sp-daemon | openai backend |
|---|---|---|
| `eot_margin` — the raw stop-vs-continue logit gap | drives kairos CONTINUE / EXPAND | `None` → CONTINUE/EXPAND dark; REMIND / SOLO / MUSE / CHECK_IN live. Opt-in `SP_ENGINE_MARGIN_APPROX=1`: a `length` finish reads as cut off (crude, no magnitude) |
| byte-exact decoding, `eot_bias`, `raw_logits`, `auto_recall`, `replay`, `single_entry`, `tool_names`, `prompt_tokens` | yes | dropped (no wire field); the knobs are tagged `engine="sp"` and the room shows the chip |
| residual vision frames (`inject_frames`) | sight through her own vision tower | `SP_ENGINE_VISION=1` → an `image_url` content part (multimodal endpoints only), else "sight is not available on this engine" |
| residual audio frames — voice-in | the native ear | off; `voice/service.py` says so as a reply. `[engine].asr_url` is reserved for ASR-then-text |
| `/v1/capture` episode mint | `npos` on every fact | skipped; rows land with `npos=0`, recall is text/sem |
| `/v1/embed` L5 vector | the engine's own space | the sidecar's `/v1/embeddings` or the hash floor (same-space only; the seam never compares across spaces) |
| the warm gate / persist-KV prefix | prefill once, strict extension | nothing to warm; `/health` is warm at once; the foreign server owns its cache discipline |
| `/v1/metrics` `tokens_per_sec` | the engine's | `harness/inference/turn_meter.py` — the gateway's own in-flight count (one writer, two readers) |
| `/v1/events` bus | telemetry sink | empty generator; the watchdog polls health |
| start / restart / watchdog relaunch | the harness owns the process | the engine is external: `/v1/start` and a full restart refuse politely; the gateway can still be bounced |
| `/v1/oneshot` scratch session | protects the resident cache | a plain non-stream completion |
| `abort` | `/v1/abort/{id}` | closing the stream |

## What runs off Windows, and what does not

**The launcher is portable; the sp engine is not** (2026-08-31, external review: *"the
launcher is Windows-only"*). It was worse than Windows-only — off Windows it did not
degrade, it **crashed**: `subprocess.CREATE_NO_WINDOW` does not exist on POSIX, so the
first spawn raised `AttributeError` before anything started, and `python serve.py
companion` is the first command in the public README.

| | Windows | Linux / macOS |
|---|---|---|
| `python serve.py <profile>` (gateway, TTS, aux) | yes | **yes** — one platform seam in `serve.py`: `NO_WINDOW` for spawning, `kill_image` / `kill_by_cmdline` for stopping |
| `[engine].kind = "openai"` — LM Studio, `llama-server`, vLLM, a cloud | yes | yes; the endpoint is the platform's problem, not this repo's |
| `[engine].kind = "sp"` — the Rust + CUDA daemon | yes | build it for the box; the `.exe` names in the shipped profiles are Windows-shaped, and `engine/` is not in the public tree at all |
| the room (`console/room/`, committed build) | yes | yes — static files, no Node at runtime |
| voice (`tts.server_exe`) | yes | whatever binary the profile names; the default name is `.exe` |

`G-BACKEND-SEAM` §10 holds it: no bare `CREATE_NO_WINDOW`, `taskkill` or `Get-CimInstance`
survives outside the seam, every spawn takes the seam's flag, and `NO_WINDOW` is **driven**
with `os.name = "posix"` to prove it evaluates to a usable `creationflags` rather than to
`None`. Untested on real Linux hardware as of the cut — the assertion is about the code,
and the honest state of the claim is written here rather than in a badge.

## The TURN path, not just the engine

The table above is about engine capabilities. Adopters ask a different question: *which of
the presence features degrade on a foreign endpoint?* Verified against the source
(2026-08-31), because the answer had drifted in both directions:

| | native `/v1/chat` (sp) | `/v1/chat/completions` (openai) |
|---|---|---|
| the epilogue — day row, capture, self-stances, spine post-turn, presence ledger, latch release | `_settle_turn` | **the same `_settle_turn`** (`_finish_openai_turn`) — one list, shared since the 2026-08-19 audit found the second inline copy |
| his actual words held before the tool loop | `_arm_turn` | the same |
| the anon / off-the-record staple in her prompt | yes | **yes** — added 2026-08-29 ("she is told on this mouth too"); AGENTS.md trap 6 is stale where it says otherwise |
| `<channel|>` thought stripping | the one door | the same door (`g_backend_seam` plants one to prove it) |
| the roleplay pre-turn hook | yes | yes |
| named phase timing in the log (`pre-turn`, `generate`, `epilogue`) | yes | no — the openai turn is one span |
| SSE v2 typed events (`{"tool":…}`, `{"persona":…}`) | yes | no — `{delta}` only |
| the warm gate / base-KV snapshot | yes | nothing to warm; the foreign server owns its cache |

**So the epilogue is not the thin part** — the observability is. What a Kairos user loses
against Kairos is the phase log, the typed event stream, and the engine column in the
first table; what she DOES is settled by the same code on both mouths.

## Running two stacks on one box
`profiles/companion.toml` puts its gateway on **:8810**, beside hers on :8800. `serve.py` stops a
gateway **by port** (`--gateway-port` rides on the spawn argv for identification; `app.py` reads no
argv), so a companion bounce never takes her down. `python serve.py companion` starts only the
gateway (+ TTS / aux if configured) and reports once whether the endpoint answers `/v1/models`.

## Gates
`g_backend_seam.py` (OFFLINE — the real OpenAIClient against an in-process fake, with a planted
`<channel|>` to prove the one-door stripper still applies; the sp body unchanged field for field);
`g_kairos_boot.py` (LIVE, any backend — the acceptance run). The ledger rows for the dark knobs are
`docs/OFF-BY-DEFAULT.md` §12.
