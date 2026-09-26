# Kairos — a local AI companion framework that owns its memory

Kairos is the engine-agnostic companion framework distilled from a private working
repository: a Python harness that owns **durable, auditable memory**, unprompted speech,
personality, presence, a wardrobe and a voice — and a React room you talk to her in — running
against **any OpenAI-compatible chat endpoint** (LM Studio, llama.cpp's `llama-server`, vLLM, a
cloud) on one consumer GPU. She remembers the person she talks to, speaks when she has a
reason to, spends time on her own while you are away, and has a face, a wardrobe and a voice.

**The one rule over everything: nothing she knows is ever deleted.** Facts are tombstoned,
never dropped; every row says who said it, what it came from, and when; an inference may never
retire an observation; every verdict is a ruling of a committed finite table, not prose.

![The room: a column of desktop app icons, the Chat window with a reply, the portrait on the right, and the top bar with the mood pill, the day's facts, the profile chip, uptime, the stack light and the next backup](docs/screenshots/room-chat.webp)

*The screenshots on this page are the room of the reference install, the long-running
companion Kairos was extracted from. A fresh clone draws the same room with an empty memory
and the default face.*

```
 the room (browser)  --->  gateway :8810 (Python, harness/server/)  --->  any /v1/chat/completions server
        ^                         |  memory . spine . kairos . wardrobe . voice . senses        (LM Studio . llama-server . vLLM . cloud)
        |                         '-->  optional: the xAI API (voice, images/motion, live search) . CPU sidecars
```

## What is in the room

The room is a desktop in the browser: loose app icons you arrange, windows you move, resize,
maximise, minimise and restore, a taskbar along the bottom (a button per window, off the
record, Shut down, the clock) and a top bar that says how she is (her mood and voice), how her
day is going (when you last spoke, whether her day has closed) and how the machine is (the
profile, uptime, the stack light with its bounce / restart actions, the next backup). Every
window is listed with the route it reads and whose it is in
[`docs/PANELS.md`](docs/PANELS.md); the room itself is [`ui/README.md`](ui/README.md).

**She has her own time.** When the room goes quiet, the idle clock (`harness/kairos/`) gives
her reasons to act: continue a thread, check in, remind, think on her own, and the presence
modes that keep you company while you sleep. Every impulse is metered, judged, and dropped by
default. What she did while you were away is in the *Her own time* window — journal lines,
notes, what she wore, what she asked for — and it is read-only by construction: there is no
write route behind it.

![The Her own time window open over Chat, listing her own-time notes and a look she asked for, with the taskbar below showing window buttons, the looked-up chip, the Anonymous switch and Shut down](docs/screenshots/room-her-own-time.webp)

**She remembers, and can say why.** One append-only fact registry with two lanes — what she
knows about you and what she knows about herself. A changed fact is tombstoned forward with
its provenance, never dropped, so the Memory window shows the retired rows beside the live
ones, and a row she *concluded* carries a **why** button: what it was drawn from, and whether
each support is still live. Every night she writes her journal and a short paragraph on who
she has been becoming; weekly, a chapter. Neither consolidator may read a distillate, so what
she concludes cannot quietly rest on what she concluded before. The rules:
[`docs/MEMORY-AND-RECALL.md`](docs/MEMORY-AND-RECALL.md).

**She has a face and clothes.** A catalog of looks, gestures and moments — stills and motion
loops, generated through the xAI API when a key is present — chosen by her or by you, with a
chip saying which. Her marks (`[MOOD:]`, `[VOICE:]`, `[TRAIT:]`, `[WEAR:]`, `[SHOW:]`) move
real state mid-sentence: the mood pill, her voice, the portrait.

![The Memory window with its live / his / hers / core / retired counts, a filter, an add box and a re-file control on each row, beside the Wardrobe window with mood chips, what she has on and the looks that just arrived](docs/screenshots/room-memory-wardrobe.webp)

**She looks things up, and does homework.** Web search answers in the turn (DuckDuckGo by
default, free; xAI live search, Brave, Tavily or SearxNG if you choose); the optional research
tier is a real, slower model call whose receipts land in the Research window — hers you can
read and cannot edit, and there is a box to set her one yourself. Every knob is in the
Settings window, each saying whether it is live or needs a restart, and whether you have
overridden it from the room; everything that ships off has its arming condition written down
in [`docs/OFF-BY-DEFAULT.md`](docs/OFF-BY-DEFAULT.md).

![The Research window with research rows marked hers and a box to run one, beside the Settings window showing Voice, Web search, Research and Wardrobe knobs with live, restart to change and changed chips](docs/screenshots/room-research-settings.webp)

**And the rest:**

| | |
|---|---|
| **a voice** | xAI Ara with expressive tags when a key is present, a local chain otherwise; the room speaks her replies (`harness/voice/`). |
| **eyes** | an hourly ambient look behind a quiet guard (off until you arm it), and sight through whatever the served model can receive (`harness/senses/`). |
| **hands** | an MCP server for her tools and a bridge for yours ([`docs/MCP.md`](docs/MCP.md)); Home Assistant, on request, limited to an allowlist you write ([`docs/HOME-ASSISTANT.md`](docs/HOME-ASSISTANT.md)). |
| **off the record** | one switch in the taskbar: she stays entirely herself and nothing about the evening is written down, held by a gate that diffs the whole sandbox ([`docs/ANON-MODE.md`](docs/ANON-MODE.md)). |
| **a design system** | the room is drawn from one kit (`ui/src/kit/`) — tokens, parts, one icon family — rendered and checked under node by G-ROOM-KIT and G-ROOM-TOKENS. |

## Quick start

> **Windows is the tested platform.** `serve.py` has had one platform seam since 0.8.14 — it
> spawns and stops its processes on Linux and macOS too, held by `G-BACKEND-SEAM`, and CI runs
> the offline suite on Linux — but the launcher has not been exercised end to end on real
> Linux hardware; [`docs/BACKENDS.md`](docs/BACKENDS.md) says so plainly.

```bash
pip install -e ".[http]"                      # zero hard deps on the core path; httpx for the client
cp -r persona-template persona                # her identity — yours to edit, gitignored
# start an OpenAI-compatible server: LM Studio (default :1234) or llama-server (:8080)
# (LM Studio with 'require authentication' on: put its API token in var/secrets/engine.token — a file, never committed)
python serve.py companion                     # boots the gateway; the engine is yours
```

Open http://127.0.0.1:8810/room/ and talk to her. `profiles/companion.toml` is the one door:
`[engine] base_url / model / dialect / api_key_file` point at your server; everything else is a
knob in the Settings window (live) or the profile (restart). **The profile is positional and
not optional** — a mistyped name fails loudly instead of quietly serving the wrong config.
Stop her from Shut down in the taskbar, or `python serve.py --stop`.

**If anything above is not obvious, open [`docs/SETUP.md`](docs/SETUP.md)** — the endpoint, every
key file and where it goes, the model cards, what each setting actually affects, and a symptom
table. The room has a live version of it: the **Setup** window reports which step you are on
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

`config/models.json` is the committed list with cards, and the Setup window reads that same file
so the two cannot drift. In short: **[`google/gemma-4-26B-A4B-it-qat-q4_0-gguf`](https://hf.co/google/gemma-4-26B-A4B-it-qat-q4_0-gguf)**
for her — a 26B mixture-of-experts with ~4B active, which is the whole reason a companion can
think in real time on one consumer card, and what every decode knob in the profile was tuned
against. **[`LiquidAI/LFM2.5-1.2B-Instruct-GGUF`](https://hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF)**
and **[`LFM2.5-Embedding-350M-GGUF`](https://hf.co/LiquidAI/LFM2.5-Embedding-350M-GGUF)** for the
CPU librarians (off by default). **[`Voxtral-Mini-4B-Realtime-2602`](https://hf.co/mistralai/Voxtral-Mini-4B-Realtime-2602)**
if you want to talk to her out loud.

### Will it run on my card?

The reference machine is **one RTX 2060, 12 GB** — deliberately, because the interesting
question is not whether a companion runs on an H100. Gemma-4-26B-A4B is a mixture of 128
experts with top-8 routing, so **~4B parameters are active per token** out of 26B, and about
10.6 GB streams from host memory onto the card. A *dense* 31B on the same hardware would
cross 8–9 GB of PCIe every token for a 3–5 tok/s ceiling; the sparsity is the whole reason
this is a conversation and not a batch job.

Measured on that card, with the optional Rust + CUDA engine, before and after the work that
made it liveable — **the memory-tiering work, 2026-09-08 to 09-10**, which is about where the
weights live and how often a token has to cross PCIe:

| | before | after |
|---|---|---|
| prefill (expert-major) | 230 ms/tok | **8 ms/tok** |
| decode (resident hot-expert cache) | ~6 tok/s | **23.8 tok/s** |
| cold prefill, live gateway | 209 s | **25.5 s** |
| warm prefill | 25.5 s | **~1.0 s** |
| prewarm, 2,922 tok | 689 s | **29 s** |

The one worth reading is the cache row: **33.4% of experts resident buys ~4×**, because MoE
routing is skewed — capacity share is not hit rate.

**That is not the same table as the engine's, and the two should not be added together.**
[`kairos-engine`](https://github.com/nihilistau/kairos-engine)'s README carries a *later* and
*separate* experiment — the CUDA **kernel** work of 2026-09-11/12, where coalescing the
attention kernels and moving the weight GEMM onto fp16 tensor cores took a 3,750-token prefill
from 36.6 s to ~13.3 s and decode from 16.6 to 21.1 tok/s. Different prompt, different date,
different knobs; the decode figures differ between the two files for that reason and not
because one of them is wrong.

That pinned workload has **now been measured** (2026-09-12): one prompt, one sitting, every
kernel armed, with `llama.cpp -ncmoe 8` on the same row. The engine's combined kernel win is
**2.12×**, not the ~2.7× that stitching two traces implied — and prefill is now **1.16× faster**
than `llama.cpp`, with decode **2.37× slower**, which is where the whole remaining gap now is.
The table is in the engine README. It is still a different experiment from the tiering one
above, and still not to be added to it.

**Those are sp-daemon numbers, not a promise about your setup.** Kairos is engine-agnostic
and most people will point it at LM Studio, `llama-server` or vLLM, where throughput is that
server's business and not this framework's. What carries over is the shape of the problem:
pick a sparse model, expect the first turn after a cold start to cost real seconds of
prefill, and expect a dense model of the same total size to be much worse. The harness is
built around those facts — the warm gate, the prefill budget and the unprompted loop's
metering all exist because of them.

### She comes with a face

`assets/avatar-default/` ships one outfit across all seven of the faces her `[MOOD:]` marks reach,
six gestures, and the reference they were grown from; the gateway lays them into `var/room/avatar/`
the first time it sees that set. It fills gaps only and runs once — it cannot overwrite a wardrobe
and cannot hand back something you deleted. The drawn SVG stays underneath as the floor and is
never removed. Replace `_reference.png` and `character.txt` **together** and everything the
generator makes from then on is yours ([`docs/AVATAR-PIPELINE.md`](docs/AVATAR-PIPELINE.md)).

## How she is present, and how she consolidates

Two things here are easy to miss from a feature list, and they are the architecture rather
than the decoration.

**She runs on a clock, not only on your turn.** `harness/kairos/` is an idle loop that asks,
on every beat, whether there is a REASON to speak — and the reasons are named, not a
temperature: *continue* (she was cut off mid-thought), *check-in* (the room has been quiet),
*remind* (she promised), *solo* (her own time: reading, searching, writing in her journal),
*muse* (a conclusion she has drawn), and the *presence modes* — narration, company, lucid
dream — for the hours you are asleep. The policy is SILENT by default and every bound is
checked before the model is consulted: a cooldown, an hourly cap, a chain limit, an idle
floor, and a rule that she never speaks over a question she asked you. **An attempt spends
the clock whether or not she speaks**, so a turn that is generated and then vetoed cannot be
re-proposed four seconds later — that loop cost eleven minutes of GPU per cycle before it was
metered, and the gate that holds it now drives every drop door.

**She consolidates without overwriting.** At the day boundary a pass reads the day's
transcript and writes her journal, distils durable facts, curates her traits from evidence,
refreshes the standing block she reads every turn, and — once a week — rolls the week into one
paragraph. Everything it produces is a *derived artefact*: it carries `derived_from`, the days
and kinds it rests on, and the status `inferred`. **It never edits testimony.** A conclusion
whose supports are all retired is retired with it (a conclusion should not outlive its
evidence); an inference may never retire an observation, and the verdict table enforces that
rather than a convention. The tombstoned base rows stay exactly where they were, answerable
by `provenance`.

The two connect: what the night writes is folded into her prefix at the same boundary, so she
wakes up having taken in what she became — for a long time the write half worked and the read
half did not, which is the kind of thing a suite of green tests will not tell you.

## Her body-awareness — optional, and off unless you build it

A companion that can *notice* — "his heart, last few readings: 70, 78, 92 — climbing" — and
say something a person in the room would say. It ships as a framework plus a Wear OS agent
you build yourself; nothing is running until you do.

```
  watch agent (APK)  --HTTP-->  POST /v1/telemetry/ingest
                                     |
                                ingest.record()      <- one door: privacy gate, one clock, shape
                                     |
                                store (one JSONL per day)
                                     |
                     +---------------+----------------+
                     |                                |
               body.read() / present()         GET /v1/telemetry/{now,history}
                     |                                |
              her prefix + reasons               the Body window
```

**Build the agent** (no gradle needed — it stays on the platform SDK on purpose, so
`aapt2 → javac → d8 → apksigner` is the whole toolchain, about 16 KB):

```bash
cd harness/telemetry/watch-agent
python build.py --install --arm        # --arm grants the sensors and starts it
```

`--arm` is a separate word deliberately: installing an app that reads your heart is one
decision, turning it on is another. Set `TELEMETRY_ENDPOINT` to your harness — the default
in the source is an example and will not resolve on your network.

**What it does and does not do.** It reduces motion to one number per window rather than
posting 100 Hz of raw accelerometer; it batches on the heart-rate sensor's own 600-event
FIFO rather than posting per beat; and it puts failed batches back at the *front* of the
queue, so an outage leaves a gap in the link and not in your history.

**What she is allowed to do with it** is the part worth reading before you turn it on:

- a **measurement** is `observed` — she may state it plainly;
- a **reading** ("he is asleep") is `inferred` — it says *seems*, and your own word
  outranks it the moment you speak;
- **silence is an answer** — no watch, stale data, or off the wrist and she is told
  *nothing*, because "you seem calm" from readings taken at lunch is worse than nothing;
- she gets the **last few readings**, not an average, and only when they *move* — a flat
  tail costs context to say nothing;
- **never a diagnosis.** Nothing computes a medical claim and her prompt forbids one in as
  many words. It is a wrist sensor, not a doctor.

Your privacy mode holds it: `telemetry.sample` is a door in `anon.DOORS`, and readings taken
off the record are **held, not queued** — a queue is the same leak with a delay on it.

Two knobs, both on once data arrives: `telemetry.turn_note` (she is handed it per turn) and
`telemetry.reasons` (she may speak first about it). Full detail, including the three tiers
and what the hardware will and will not give you: [`docs/TELEMETRY.md`](docs/TELEMETRY.md).

> **Reaching the gateway.** It binds `127.0.0.1` and **loopback is its security model** — the
> origin check defends against a browser, not against a script. A watch is not on that
> machine, so either tunnel (`adb reverse tcp:8810 tcp:8810` for the companion profile's port)
> or widen `[serve].bind` and scope it with a firewall rule. That second one is a real decision
> about who can reach her; `python tools/lan_bind.py --status` tells you whether your scoping
> is actually in place.

## Where this sits, and what it is not

There is a lot of good software next to this one and most of it is solving a different
problem. The honest way to place Kairos is by the decisions it makes differently, not by a
feature count — so this compares **stances**, and says what each stance costs.

| | a chat front-end<br>(LM Studio, Open WebUI, SillyTavern) | an agent/memory framework<br>(LangChain, Letta/MemGPT, mem0) | **Kairos** |
|---|---|---|---|
| **what memory IS** | the conversation, plus what you paste | retrieved context — usually a vector store, often summarised forward | an **append-only ledger of facts**, each with speaker, source, time and status; the transcript is a separate durable record |
| **forgetting** | delete a chat, it is gone | eviction, summarisation, re-embedding; the original is usually not kept | **tombstoned, never dropped.** `forget` retires a row and `provenance` still answers about it |
| **who said it** | roles in a transcript | usually flattened at ingest | a first-class column, and an **inference may never retire an observation** — enforced by a committed verdict table, not a convention |
| **speaking first** | never; you send, it replies | on a schedule or a trigger you write | a **named-reason idle loop** — continue, check-in, remind, solo, muse, presence modes — SILENT by default, every bound checked before the model is consulted |
| **identity** | a system prompt you edit | a prompt plus tools | persona, traits curated **from evidence**, wardrobe and mood marks she emits and that actually move state |
| **what proves it** | manual testing | unit tests | ~160 offline gates, each a named claim with a receipt, most with a mutant proving the check is load-bearing |

**What it is not.** Not a model server — bring your own endpoint. Not a RAG framework for
your documents; the memory here is about a *person*, and pointing it at a corpus is not what
any of it was tuned for. Not multi-user: one companion, one person, loopback by default. Not
a product — it is a working system with its reasoning written down, and the reasoning is
most of the value.

**The cost of these stances, stated plainly.** An append-only ledger grows and needs
hygiene passes. A companion that speaks first can speak when you would rather it did not,
which is why every bound is a knob and the default is silence. And a gate culture this dense
is slow to change — that is the trade, and it is deliberate.

## What works, and what the custom engine adds

Everything here runs engine-agnostically: memory with tombstones and verdicts, the recall seam,
unprompted speech (remind / solo / muse / check-in), personality marks, the wardrobe and catalog,
the voice (xAI Ara with expressive tags, or a local chain), the ambient eye's quiet guard, the
room and all its windows, the gate culture (`harness_tests/`).

The optional **sp-daemon** backend adds what a generic endpoint cannot give: the raw
stop-vs-continue margin that drives her *continue* and *expand* impulses, byte-exact
decoding, residual vision/audio frames (sight and voice-in), engine-side episode minting and
L5 embeddings, the prefix warm gate. Without it those degrade with a stated loss — see
`docs/BACKENDS.md` and `docs/OFF-BY-DEFAULT.md` §12.

That engine is public too: **[`kairos-engine`](https://github.com/nihilistau/kairos-engine)**
— the Rust + CUDA daemon these numbers were measured on, with the MoE expert cache, the
expert-major prefill and the KV ring. It is a separate repo because it is a separate
decision: Kairos is complete without it, and you should only reach for it once a generic
endpoint is the thing in your way.

```bash
git clone --recurse-submodules https://github.com/nihilistau/kairos-engine engine
```

## Read next

| | |
|---|---|
| how to set it up: endpoint, keys, models, settings | [`docs/SETUP.md`](docs/SETUP.md) |
| the two-minute map | [`START-HERE.md`](START-HERE.md) |
| the rules, the bug class this project keeps paying for, the traps | [`AGENTS.md`](AGENTS.md) |
| the documents and which is authoritative | [`docs/README.md`](docs/README.md) |
| what proves it still works | [`gates/GATE-INDEX.md`](gates/GATE-INDEX.md) |
| what is deliberately off, and what would turn it on | [`docs/OFF-BY-DEFAULT.md`](docs/OFF-BY-DEFAULT.md) |
| the room: windows, the kit, how to rebuild it | [`ui/README.md`](ui/README.md) |
| every window, what it reads, and whose it is | [`docs/PANELS.md`](docs/PANELS.md) |
| the six ways a fact reaches her, and which one yours belongs in | [`docs/LANES.md`](docs/LANES.md) |
| what changed, by version | [`CHANGELOG.md`](CHANGELOG.md) |
| the optional Rust + CUDA engine, and what it adds | [`kairos-engine`](https://github.com/nihilistau/kairos-engine) |

Read [`docs/LANES.md`](docs/LANES.md) before adding anything to her context: two of the six
lanes have already been measured wrong, and the receipts are in there.

## Before you say you are done

```bash
python harness_tests/g_claim.py && python harness_tests/g_durability.py && python harness_tests/g_memory_lifecycle.py && python harness_tests/g_backend_seam.py && python harness_tests/g_docs_true.py
```

Those five are OFFLINE; the whole offline suite is `python tools/sweep.py` (no GPU). The LIVE
gates read `SP_GATEWAY_URL` / `SP_BOOT_GATEWAY` (default `http://127.0.0.1:8800`; the companion
profile serves `:8810`, so set it) — `g_kairos_boot.py` is the acceptance run, and
`gates/KAIROS-BOOT-<date>.md` holds the receipts.

Kairos is exported from the source repo (see `KAIROS-SOURCE.txt`, `CONTRIBUTING.md`). MIT.
