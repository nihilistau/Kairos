---
type: reference
title: "SETUP — from a clone to a companion: the endpoint, the keys, the models, the knobs"
status: LIVE — the setup panel (`/v1/setup`) reports the same facts live; this is the prose half
updated: 2026-08-23
---

# SETUP — getting her running, and getting her good

Two audiences, one document. **§1–§3 get her talking** and take about ten minutes with a
model you already have. **§4–§8 are the optional surfaces** — a voice, a face that grows,
web search, the CPU librarians — each of which ships **off** and each of which costs
something (a key, a download, a GPU). Nothing below §3 is needed for a complete Kairos:
the memory system, the personality, unprompted speech, the room and every gate run
offline against any endpoint.

**The room has a live version of this page.** Open the ⚙︎-adjacent **setup** window and it
tells you which step you are actually on — whether your endpoint answered, which keys it
can see, whether her face is seeded. It reads `/v1/setup`, writes nothing, and never
returns the contents of a key file.

---

## 1. Install, and pick an endpoint

```bash
git clone <this repo> && cd Kairos
pip install -e ".[http]"          # the core path has zero hard deps; httpx is for the client
cp -r persona-template persona    # her identity — yours to edit, gitignored
```

She talks to **any OpenAI-compatible `/v1/chat/completions` server**. Pick one, start it,
and note the port:

| server | default | `[engine].dialect` | notes |
|---|---|---|---|
| **LM Studio** | `http://127.0.0.1:1234` | `generic` | easiest start. If *require authentication* is on, see §3. |
| **llama.cpp `llama-server`** | `http://127.0.0.1:8080` | `llamacpp` | `llamacpp` additionally sends `top_k` and `repeat_penalty`, which `generic` cannot. |
| **vLLM** | `http://127.0.0.1:8000` | `generic` | for the unquantised weights. |
| **a cloud endpoint** | its own URL | `generic` | set `api_key_file` (§3). Everything she remembers still stays on your disk. |
| **the sp-daemon** | — | — | the custom Rust + CUDA engine in the source repo. `kind = "sp"`. See [`BACKENDS.md`](BACKENDS.md). |

### Which model

`config/models.json` is the committed list, with cards — the setup panel reads that same
file, so it cannot drift from this page. The short version:

- **[`google/gemma-4-26B-A4B-it-qat-q4_0-gguf`](https://hf.co/google/gemma-4-26B-A4B-it-qat-q4_0-gguf)**
  — the default. A 26B mixture-of-experts with ~4B active, quantisation-aware trained to
  4-bit by Google: mid-size quality at small-model speed and VRAM, which is the whole
  reason a companion can think in real time on one consumer card. **Every decode knob in
  `profiles/companion.toml` was tuned against this model.**
- [`unsloth/gemma-4-26B-A4B-it-GGUF`](https://hf.co/unsloth/gemma-4-26B-A4B-it-GGUF) — the
  full quant ladder if the QAT build does not fit.
- [`google/gemma-4-26B-A4B-it`](https://hf.co/google/gemma-4-26B-A4B-it) — the safetensors
  weights, for vLLM or transformers.

Smaller models work and she will be noticeably less herself: the personality marks
(`[MOOD:]`, `[WEAR:]`) and the tool loop are instruction-following load, and a 7B spends
its whole budget on them.

---

## 2. Point the profile at it, and start

`profiles/companion.toml` is **the one door**. Every environment variable the harness reads
is built from it by `serve.py`; nothing else composes an environment, which is why a
mismatched profile is a refusal here rather than a silence three hours later.

```toml
[engine]
kind      = "openai"                      # "sp" for the Rust daemon
base_url  = "http://127.0.0.1:1234"       # your server
model     = ""                            # its model id; empty = whatever it has loaded
dialect   = "generic"                     # "llamacpp" sends top_k / repeat_penalty too
vision    = false                         # true only if the endpoint accepts image_url parts
```

```bash
python serve.py companion
```

**The profile name is positional and it is not optional.** It selects the model, so there
is no safe default — a stack that boots on the wrong profile looks completely healthy and
sends another model's decode knobs to yours. Open <http://127.0.0.1:8810/room/>.

Stop her from the room (the ⏻ in the dock: *her only* / *everything* / *kill*) or
`python serve.py --stop`.

---

## 3. Keys — where they go, and what each one buys

**Every key in this system is a FILE, never a value in a config file and never a value in
git.** `var/` is gitignored in its entirety. Create the file, paste the key, restart.

| what | file | needed for |
|---|---|---|
| your inference endpoint | `var/secrets/engine.token` | only if your server requires auth (LM Studio's *require authentication*, or a cloud endpoint) |
| **the xAI API key** | `var/secrets/Xapi.txt` | her voice, her face and wardrobe, live web search, the research tier |
| a sidecar endpoint | whatever `[aux].api_key_file` names | only if your sidecar server requires auth |

```bash
mkdir -p var/secrets
printf '%s' 'sk-...' > var/secrets/engine.token     # no trailing newline needed; it is stripped
printf '%s' 'xai-...' > var/secrets/Xapi.txt
```

The paths are knobs, not conventions — `[engine].api_key_file` and `[xai].key_file` in the
profile. An absent file is not an error: it means no `Authorization` header and, for xAI,
that those four features stay dark. **The setup panel reports each key as present/absent
and never returns a byte of it**, deliberately: a route that echoed a prefix "so you can
check" is a route that writes your API key into a browser's network log.

### Getting an xAI key

Console: <https://console.x.ai/> → create a key → paste it into `var/secrets/Xapi.txt`.
It is billed per call, and **every attempt bills, including a refused one** — an image the
moderation endpoint declines still costs. What the one key turns on:

| feature | knob | what it is |
|---|---|---|
| **her voice** | `[tts].method = "xai"` | Ara, with expressive tags. The room speaks her replies. |
| **her face and wardrobe** | `[xai].image_model` / `video_model` | still → motion, grown from your reference. See [`AVATAR-PIPELINE.md`](AVATAR-PIPELINE.md). |
| **live web search** | `[search].backend = "xai"` | the free floor is DuckDuckGo and needs no key at all. |
| **the research tier** | `[research].enabled = true` | ships off, and off for *her* unprompted use specifically — see [`OFF-BY-DEFAULT.md`](OFF-BY-DEFAULT.md). |

The environment spellings `SP_XAI_API_KEY` / `XAI_API_KEY` still win over the file when
set — the announced host-key exception, for people who already keep keys in their shell.

---

## 4. Her identity — the persona

`persona-template/` is a working, generic companion. Copy it to `persona/` (§1) and edit.
It is gitignored, which means **git is not your safety net for it**: `serve.py` copies
`persona.md` to `var/persona-backups/` on every launch, and the hourly backup
(`[backup]`) carries the rest.

The room's **persona** panel edits the fragments live. `harness/personality/` is the
machinery — marks, the curator, the layers. If you touch it, read
[`MEMORY-AND-RECALL.md`](MEMORY-AND-RECALL.md) first: the personality writes facts, and
facts are the thing this project refuses to lose.

---

## 5. Her face

**Kairos ships one.** `assets/avatar-default/` holds one outfit across all seven faces
plus six gestures, and the gateway lays them into `var/room/avatar/` the first time it
sees that set. So a fresh clone has a face rather than the fallback SVG, and a worked
example of what the pipeline produces.

Three things are true about it and worth knowing before you build your own:

1. **The seeder only fills gaps, and only once.** It never overwrites a file you have and
   never re-adds a gesture you deleted — `.seeded.json` in the avatar directory records
   which sets have been offered.
2. **The SVG is the floor and is never deleted.** A missing loop degrades to the still, a
   missing still degrades to the drawn face. A half-built set is usable from its first image.
3. **The bundled prompts are not published.** The receipts carry the model, the reference
   hash and the timestamp; `character.txt` is a written template describing the shipped
   reference, not anyone's own character file.

To make her yours, replace **both halves of the identity together** — `_reference.png` and
`character.txt` in `var/room/avatar/`. Changing one without the other is exactly how a
wardrobe fills with fifty different women; the full doctrine is
[`AVATAR-PIPELINE.md`](AVATAR-PIPELINE.md). Generation needs the xAI key (§3) and runs
from the wardrobe panel's *make it now*.

---

## 6. Her voice

`[tts].method`:

- `"xai"` — Ara through the API, with expressive tags. Needs the key.
- a local chain — `[tts].url` points at a resident TTS server you run yourself.
  `autostart = false` on purpose: a resident synth took ~2 GB and faulted a prefill once.
- off — she types. Everything else still works.

For **talking to her**, `[engine].asr_url` takes any `/v1/audio/transcriptions` endpoint.
[`mistralai/Voxtral-Mini-4B-Realtime-2602`](https://hf.co/mistralai/Voxtral-Mini-4B-Realtime-2602)
is the streaming one worth having — batch ASR makes a conversation feel like submitting a
form. A GGUF build is at
[`handy-computer/Voxtral-Mini-4B-Realtime-2602-gguf`](https://hf.co/handy-computer/Voxtral-Mini-4B-Realtime-2602-gguf).

---

## 7. The librarians — the CPU sidecars

Small models that embed, retrieve, judge and read for her, on the CPU, so recall and
page-reading cost no GPU time. **They are never her voice.** All of `[aux]` ships off;
[`AUX-MODELS.md`](AUX-MODELS.md) is the ledger of what each does and what stays dark.

| model | knob | what it does |
|---|---|---|
| [`LiquidAI/LFM2.5-1.2B-Instruct-GGUF`](https://hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF) | `[aux].chat_model` | deep recall, reading a fetched page down to what was asked, yes/no judging |
| [`LiquidAI/LFM2.5-Embedding-350M-GGUF`](https://hf.co/LiquidAI/LFM2.5-Embedding-350M-GGUF) | `[aux].embed_gguf` | the semantic half of recall |
| [`LiquidAI/LFM2.5-ColBERT-350M-GGUF`](https://hf.co/LiquidAI/LFM2.5-ColBERT-350M-GGUF) | `[aux].colbert_url` | late-interaction rerank — off, and measured before it is armed |

Without an embedder **and** without the sp-daemon's own L5, embeddings fall back to a hash
space. That is honest and it is blunt: recall still works, and it works on words rather
than meaning.

---

## 8. Settings — what affects what

Two kinds of knob, and the difference is stated on every row in the room's **settings**
window:

- **LIVE** — takes effect on the next call that reads it. Her voice on her next sentence,
  search on her next query. Change it and keep talking.
- **PROFILE** — owned by `profiles/companion.toml` through `serve.py`. Shown read-only
  with a *restart to change* chip, because a control that displays a stale number and
  changes nothing is worse than no control.

The settings window is generated from the tuning registry: a knob added server-side
appears there with no UI edit at all. What matters most, and why:

| knob | where | what it actually changes |
|---|---|---|
| `[decode].temperature` | profile | 0.6 is the tuned value. Above ~0.9 she starts losing the mark syntax the room parses. |
| `[decode].max_tokens` | profile | 768. The ceiling on one reply. |
| `[decode].repetition_penalty` | profile | 1.3. Below ~1.1 a long evening starts looping. |
| `[decode].eot_bias` | profile | **0.0 here, and the comment says why**: at 4.0 the default model's first sampled token is a stop and she goes completely silent while `/health` says warm. It is an sp-daemon knob; on a generic endpoint it is inert. |
| `[agent].personality` | profile | her marks and the curator. Off makes her an assistant. |
| `[agent].spine_recall` | profile | whether the decide→execute→verify spine may reach memory. |
| `[agent].mcp_tools` | profile | other servers' tools in her hands — [`MCP.md`](MCP.md). |
| `[senses].ambient` | profile | the hourly eye. **Off per machine, deliberately** — it looks at your screen, and it waits for `ambient_quiet_s` of quiet first. |
| `[memory].auto_recall_default` | profile | whether recall runs unasked. |
| `[memory].growth`, `store_verb`, `persist_growth`, `classify`, `policy` | profile | the daemon's own memory writers. **Refused at boot** on this profile — one writer, and it is the harness. |
| kairos reasons (continue / check-in / remind / solo / muse) | live | when she speaks unprompted. The idle clock is `harness/kairos/`. |
| `[backup]` | profile | hourly zip of `var/` and the persona. Her state is gitignored, so this is the safety net. |

**Read [`OFF-BY-DEFAULT.md`](OFF-BY-DEFAULT.md) before arming anything.** It is a live
ledger: every knob that ships off has a row saying what evidence would turn it on, and a
gate holds the ledger to the profile.

### For the best experience

- **Give the model room.** 8k+ context. She carries persona, memory and tool definitions
  before your first word; a 2k window spends all of it on the preamble.
- **Let her have the whole reply.** `max_tokens` under ~400 truncates her mid-thought and
  the mark syntax lands broken.
- **Match the dialect.** On `llama-server`, `dialect = "llamacpp"` — otherwise `top_k` and
  `repeat_penalty` are silently not sent and the model wanders.
- **Turn the ambient eye on only when you mean it**, and read its quiet guard first.
- **Do not run two profiles at one port.** `[serve].gateway_port` is 8810 here on purpose.
- **Back up before you experiment.** `restore.py` and `[backup]` exist because `var/` is
  gitignored and the one rule over everything is that nothing she knows is ever deleted.

---

## 9. When it does not work

| symptom | the actual cause, usually |
|---|---|
| `serve.py: name the profile` | the profile is positional. `python serve.py companion`. |
| the room loads, she never replies | the endpoint is not up, or `base_url` has the wrong port. The setup panel probes it and says which. |
| replies come back empty | a decode knob from another model — check `[decode]` against §8. |
| `401` from your own server | LM Studio's *require authentication* is on; put its token in `var/secrets/engine.token`. |
| no voice | `[tts].method` is not `"xai"`, or `var/secrets/Xapi.txt` is missing or empty. |
| the drawn SVG instead of a face | the bundled set was never seeded — check `var/room/avatar/` and the gateway log line `[gateway] avatar defaults:`. |
| she forgets | she does not. Facts are tombstoned, never dropped — read [`MEMORY-AND-RECALL.md`](MEMORY-AND-RECALL.md) and check the memory panel's retired rows. |

Then the gates. They are the answer to "is it actually working", and the offline set needs
no GPU and no endpoint:

```bash
python harness_tests/g_claim.py
python harness_tests/g_durability.py
python harness_tests/g_memory_lifecycle.py
python harness_tests/g_backend_seam.py
python harness_tests/g_docs_true.py
```

[`../gates/GATE-INDEX.md`](../gates/GATE-INDEX.md) indexes every one of them, offline and
live, with its run command.
