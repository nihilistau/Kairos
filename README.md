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
