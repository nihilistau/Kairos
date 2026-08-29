# START HERE — the two-minute map

**Kairos is a local AI companion framework.** You bring any OpenAI-compatible chat
endpoint — LM Studio, llama.cpp's `llama-server`, vLLM, a cloud key — and Kairos brings
everything that is not the model: memory with provenance, the recall spine, her own time
(kairos), the wardrobe, voice, senses, and a room to live in.

*(This file is written for this public framework tree. It is not the source stack's
START-HERE: there is no bundled inference engine here, no CUDA build, and nothing to
compile — the engine is whichever server you point the profile at.)*

## Boot

```
pip install -e ".[http]"
# start an OpenAI-compatible server: LM Studio (default :1234) or llama-server (:8080)
python serve.py companion            # boots the GATEWAY; the engine is yours
```

Open **http://127.0.0.1:8810/room/** and talk to her. **The profile is positional and not
optional** — a mistyped profile fails loudly instead of quietly serving the wrong config.

`profiles/companion.toml` is the one door: `[engine] base_url / model / dialect /
api_key_file` point at your server; everything else is a knob with its reasoning written
next to it. If your server requires authentication, put its token in
`var/secrets/engine.token` — a file, never committed.

## The map

| What | Where |
|---|---|
| The rules of the road | [`AGENTS.md`](AGENTS.md) — written for the source stack; its *principles* (§0: two copies of one truth is the recurring bug; gates are the audit trail) apply here verbatim, but its boot lines and engine sections describe hardware this tree does not ship |
| Memory and recall, before touching `harness/skills/` | [`docs/MEMORY-AND-RECALL.md`](docs/MEMORY-AND-RECALL.md) |
| What proves it still works | [`gates/GATE-INDEX.md`](gates/GATE-INDEX.md); the whole offline suite: `python tools/sweep.py` (no GPU needed) |
| What is deliberately off, and what would turn it on | [`docs/OFF-BY-DEFAULT.md`](docs/OFF-BY-DEFAULT.md) — rows marked as armed describe the *source install's* decisions; on this tree every arming is yours to make |
| What changed and when | [`CHANGELOG.md`](CHANGELOG.md) |
| Setting up a fresh companion | [`docs/SETUP.md`](docs/SETUP.md) |

## What starts empty, on purpose

Her memory, her journal, her chapters, her wardrobe history — all of it starts blank and
grows from your conversations. The narrative machinery (a nightly "becoming" paragraph, a
weekly chapter that stands in her prefix, the fold that archives its sources) begins
producing on its own schedule: the first chapter after about a week, the first folds a
fortnight after that. Nothing is pre-written; the persona template is a voice, not a past.

## Before you say you are done (offline, no GPU)

```
python tools/sweep.py
```

A green suite is not an audit — but a red one is always a finding. New gates use
`harness_tests/_gate.py`: `sandbox()` FIRST, then `check()`/`finish()` so the verdict
reaches the exit code.
