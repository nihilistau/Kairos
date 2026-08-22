# Kairos — a local AI companion framework that owns its memory

Kairos is the engine-agnostic companion framework distilled from
[shannon-prime-kairos](https://github.com/nihilistau/shannon-prime-kairos): a Python harness
that owns **durable, auditable memory**, unprompted speech, personality, presence, a wardrobe
and a voice — and a React room you talk to her in — running against **any OpenAI-compatible
chat endpoint** (LM Studio, llama.cpp's `llama-server`, vLLM, a cloud) on one consumer GPU.

**The one rule over everything: nothing she knows is ever deleted.** Facts are tombstoned,
never dropped; every row says who said it, what it came from, and when; an inference may never
retire an observation; every verdict is a ruling of a committed finite table, not prose.

```
 the room (browser)  --->  gateway :8810 (Python, harness/server/app.py)  --->  any /v1/chat/completions server
        ^                         |  memory . spine . kairos . wardrobe . voice . senses        (LM Studio . llama-server . vLLM . cloud)
        |                         '-->  optional: the xAI API (voice, images/motion, live search) . CPU sidecars
```

## Quick start

```bash
pip install -e ".[http]"                      # zero hard deps on the core path; httpx for the client
cp -r persona-template persona                # her identity — yours to edit, gitignored
# start an OpenAI-compatible server: LM Studio (default :1234) or llama-server (:8080)
# (LM Studio with 'require authentication' on: put its API token in var/secrets/engine.token — a file, never committed)
python serve.py companion                     # boots the gateway; the engine is yours
```

Open http://127.0.0.1:8810/room/ and talk to her. `profiles/companion.toml` is the one door:
`[engine] base_url / model / dialect / api_key_file` point at your server; everything else is a
knob in the settings window (live) or the profile (restart).

**If anything above is not obvious, open [`docs/SETUP.md`](docs/SETUP.md)** — the endpoint, every
key file and where it goes, the model cards, what each setting actually affects, and a symptom
table. The room has a live version of it: the **setup** window reports which step you are on
rather than which steps exist.

### Keys, in one paragraph

Every key in this system is a **file**, never a value in a config file and never a value in git
(`var/` is gitignored in its entirety). Your inference endpoint's token, if it needs one, goes in
`var/secrets/engine.token`. The optional **xAI API key** goes in `var/secrets/Xapi.txt` and turns
on four things at once — her voice (Ara, with expressive tags), her face and wardrobe
(still → motion, grown from your own reference), live web search, and the research tier. Get one
at <https://console.x.ai/>. **Nothing else needs it**: memory, personality, unprompted speech,
the room and every gate run offline against any endpoint.

### Which models

`config/models.json` is the committed list with cards, and the setup panel reads that same file
so the two cannot drift. In short: **[`google/gemma-4-26B-A4B-it-qat-q4_0-gguf`](https://hf.co/google/gemma-4-26B-A4B-it-qat-q4_0-gguf)**
for her — a 26B mixture-of-experts with ~4B active, which is the whole reason a companion can
think in real time on one consumer card, and what every decode knob in the profile was tuned
against. **[`LiquidAI/LFM2.5-1.2B-Instruct-GGUF`](https://hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF)**
and **[`LFM2.5-Embedding-350M-GGUF`](https://hf.co/LiquidAI/LFM2.5-Embedding-350M-GGUF)** for the
CPU librarians (off by default). **[`Voxtral-Mini-4B-Realtime-2602`](https://hf.co/mistralai/Voxtral-Mini-4B-Realtime-2602)**
if you want to talk to her out loud.

### She comes with a face

`assets/avatar-default/` ships one outfit across all seven of the faces her `[MOOD:]` marks reach,
six gestures, and the reference they were grown from; the gateway lays them into `var/room/avatar/`
the first time it sees that set. It fills gaps only and runs once — it cannot overwrite a wardrobe
and cannot hand back something you deleted. The drawn SVG stays underneath as the floor and is
never removed. Replace `_reference.png` and `character.txt` **together** and everything the
generator makes from then on is yours ([`docs/AVATAR-PIPELINE.md`](docs/AVATAR-PIPELINE.md)).

## What works, and what the custom engine adds

Everything here runs engine-agnostically: memory with tombstones and verdicts, the recall seam,
unprompted speech (remind / solo / muse / check-in), personality marks, the wardrobe and catalog,
the voice (xAI Ara with expressive tags, or a local chain), the ambient eye's quiet guard, the
room and all its panels, the gate culture (`harness_tests/`).

The optional **sp-daemon** backend (the Rust + CUDA engine in the source repo) adds what a
generic endpoint cannot give: the raw stop-vs-continue margin that drives her *continue* and
*expand* impulses, byte-exact decoding, residual vision/audio frames (sight and voice-in),
engine-side episode minting and L5 embeddings, the prefix warm gate. Without it those degrade
with a stated loss — see `docs/BACKENDS.md` and `docs/OFF-BY-DEFAULT.md` §12.

## Read next

| | |
|---|---|
| how to set it up: endpoint, keys, models, settings | [`docs/SETUP.md`](docs/SETUP.md) |
| the two-minute map | [`START-HERE.md`](START-HERE.md) |
| the rules, the bug class this project keeps paying for, the traps | [`AGENTS.md`](AGENTS.md) |
| the documents and which is authoritative | [`docs/README.md`](docs/README.md) |
| what proves it still works | [`gates/GATE-INDEX.md`](gates/GATE-INDEX.md) |
| what is deliberately off, and what would turn it on | [`docs/OFF-BY-DEFAULT.md`](docs/OFF-BY-DEFAULT.md) |
| the room | [`ui/README.md`](ui/README.md) |

## Before you say you are done

```bash
python harness_tests/g_claim.py && python harness_tests/g_durability.py && python harness_tests/g_memory_lifecycle.py && python harness_tests/g_backend_seam.py && python harness_tests/g_docs_true.py
```

Those four are OFFLINE. The LIVE gates read `SP_GATEWAY_URL` / `SP_BOOT_GATEWAY` (default
`http://127.0.0.1:8800`; the companion profile serves `:8810`, so set it) — `g_kairos_boot.py` is
the acceptance run, and `gates/KAIROS-BOOT-<date>.md` holds the receipts.

Kairos is exported from the source repo (see `KAIROS-SOURCE.txt`, `CONTRIBUTING.md`). MIT.
