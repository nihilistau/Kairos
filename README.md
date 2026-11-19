# Kairos

**An AI companion that runs on your own computer and actually remembers you.**

Kairos gives a local language model a memory, a personality, a face and a voice, and a place to
talk to her: a little desktop that opens in your browser. She remembers what you tell her, can show
you where each memory came from, keeps herself busy while you're away, and only speaks first when
she has a reason to. Everything she knows stays on your disk.

It works with any model server that speaks the OpenAI chat API (LM Studio, llama.cpp, vLLM, or a
cloud provider), and it's built to run well on a single consumer graphics card.

![The room: desktop app icons down the left, the Chat window with a reply, her portrait on the right, and the top bar showing her mood, the day, uptime and the next backup](docs/screenshots/room-chat.webp)

*Screenshots are from a long-running install. A fresh copy looks the same, with an empty memory and
the default face.*

## What she does

- **Remembers you, and shows her working.** Facts about you and about herself go into a memory you
  can browse. Nothing is ever deleted: when something changes, the old version is kept, marked as
  retired. Anything she worked out on her own (rather than being told) has a **why** button that
  shows what it was based on.
- **Has her own time.** When you go quiet she can read, search the web, write in her journal or
  pick up an earlier thread. The *Her own time* window shows what she got up to. Every night she
  writes a journal entry, and once a week a short chapter about how she's been changing.
- **Speaks first, but sparingly.** She can check in, follow up on something she promised, or keep
  you company overnight. The default is silence: every reason to speak has limits, and an idea she
  decides against still counts against them.
- **Has a face and a wardrobe.** A set of portraits, outfits and short animations that follow her
  mood as she talks. One outfit ships with the project; with an xAI key she can grow more from a
  reference image you choose.
- **Can talk and listen.** She speaks her replies out loud. With a local speech model you can talk
  back using a push-to-talk mic. Your speech is transcribed on your machine and never saved.
- **Looks things up.** Web search works out of the box (DuckDuckGo, free), with optional slower
  "homework" research that she files where you can read it.
- **Goes off the record.** One switch in the taskbar and nothing from the evening is written down.
- **Can use tools.** She can connect to MCP tools, and to Home Assistant if you allow it, limited to
  a list of devices you write yourself.

![The Memory window listing live and retired facts, beside the Wardrobe window with mood chips and recently arrived looks](docs/screenshots/room-memory-wardrobe.webp)

## Getting started

**You'll need:**

- **Windows.** It's the tested platform. Linux and macOS should work but haven't been tried end to end.
- **Python 3.11 or newer.**
- **A model server.** [LM Studio](https://lmstudio.ai) is the easiest. Load
  [`gemma-4-26B-A4B-it-qat-q4_0`](https://hf.co/google/gemma-4-26B-A4B-it-qat-q4_0-gguf), the model
  everything was tuned on. It runs on a 12 GB graphics card.

**Then:**

1. Download it and install:

   ```bash
   git clone https://github.com/nihilistau/Kairos && cd Kairos
   pip install -e ".[http]"
   ```

2. Give her a personality to start from. This copy is yours to edit, and git ignores it:

   ```bash
   cp -r persona-template persona
   ```

   Her default name is Kairos. Change it, and anything else about her, in `persona/00-identity.md`.

3. Tell her who you are. In `profiles/companion.toml`, fill in `name` (and `pronouns` if you like)
   under `[user]`. Left blank, she calls you "the user".

4. Start your model server. LM Studio listens on port 1234 by default, which is what the profile
   expects. If yours is somewhere else, change `base_url` under `[engine]` in the same file.

5. Start her:

   ```bash
   python serve.py companion
   ```

6. Open **http://127.0.0.1:8810/room/** and say hello.

To stop her, click **Shut down** in the taskbar, or run `python serve.py --stop`.

**If something doesn't work,** open the **Setup** window in the room. It checks each step and tells
you which one you're stuck on. [`docs/SETUP.md`](docs/SETUP.md) has the full walkthrough: other
servers, keys, models, every setting, and a table of common problems.

## Optional extras

Everything above runs fully offline. These are add-ons, and all of them ship turned off.

- **An xAI API key** turns on four things at once: her expressive voice (Ara), new outfits and
  animations, live web search and the research tier. Save the key in `var/secrets/Xapi.txt`. Keys
  are always files, never typed into config, and `var/` is never committed. Get a key at
  <https://console.x.ai/>.
- **Local voice and ears.** Point the `[lfm3]` section of the profile at an LFM3-Audio model and a
  recent llama.cpp build (b11960 or newer), and she can hear you and speak without any cloud
  service. See [`docs/SETUP.md`](docs/SETUP.md) §6.
- **CPU helper models.** Small models that file and index her memory on the CPU:
  [`LFM2.5-1.2B-Instruct`](https://hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF) and
  [`LFM2.5-Embedding-350M`](https://hf.co/LiquidAI/LFM2.5-Embedding-350M-GGUF).
- **Smartwatch awareness.** A tiny Wear OS app you build yourself lets her notice things like a
  climbing heart rate. She states readings plainly, says "seems" about guesses, says nothing when
  the data is stale, and never offers a diagnosis. Read [`docs/TELEMETRY.md`](docs/TELEMETRY.md)
  first, including the part about network access.
- **A faster engine.** [`kairos-engine`](https://github.com/nihilistau/kairos-engine) is a custom
  Rust + CUDA backend built for this model on a 12 GB card. You don't need it; reach for it only
  when your normal server is the bottleneck.

The **Models** window shows every model she uses, whether each is loaded, and a Test button. Anything
you haven't set up says so instead of failing quietly.

![The Models window with a status pill and Test button for each of her six model jobs](docs/screenshots/room-models.webp)

## Will it run on my machine?

The reference machine is a single **RTX 2060 with 12 GB**. Gemma 4 26B-A4B is a mixture-of-experts
model: only about 4B of its 26B parameters work on each token. That's why it can hold a real-time
conversation on a mid-range card, where a dense model of the same size would crawl.

With LM Studio or llama.cpp, speed is up to that server. With the optional custom engine on that
card, she generates about **35 tokens a second** and reads a 4,000-token prompt in about **6
seconds**. The full measurement history is in the
[`kairos-engine`](https://github.com/nihilistau/kairos-engine) README.

Whatever you run on, expect the first reply after a cold start to take a while as the model reads
her persona. Later replies are much faster.

Smaller models work, but she'll be noticeably less herself. Her mood and outfit cues and her tool
use take real instruction-following ability.

## A tour of the room

The room works like a small desktop. Apps live in five folders (Her, Together, Look it up, Home,
System). Windows can be moved, resized and minimised. A dock holds your favourites, and a top bar
shows her mood and the state of the machine. Drag apps between folders, onto the desktop, or onto
the dock. The layout is remembered per browser. [`docs/PANELS.md`](docs/PANELS.md) lists every
window and what it shows.

![The desktop with the Her folder open and the dock along the bottom](docs/screenshots/room-folders-dock.webp)

![The Her own time window showing her notes and a look she asked for](docs/screenshots/room-her-own-time.webp)

![The Research window beside Settings, where each option says whether it applies live or after a restart](docs/screenshots/room-research-settings.webp)

![The Voice window with the voice provider and listening options](docs/screenshots/room-voice.webp)

---

## Under the hood

The rest of this page is for people who want to know how it works or contribute to it.

```
 the room (browser)  --->  gateway :8810 (Python, harness/server/)  --->  any /v1/chat/completions server
        ^                         |  memory . idle loop . wardrobe . voice . senses        (LM Studio . llama-server . vLLM . cloud)
        |                         '-->  optional: xAI API (voice, images, live search) . CPU sidecars
```

### Memory

Memory is an append-only ledger of facts in two lanes, what she knows about you and what she knows
about herself, plus a separate durable transcript. Every row records who said it, where it came
from, when, and whether it was **observed** (you told her) or **inferred** (she concluded it).

- Changed or forgotten facts are retired, never removed. `provenance` can still answer about them.
- An inference can never retire an observation. This is enforced by a committed verdict table,
  not by convention.
- A conclusion whose supporting facts have all been retired is retired with them.
- The nightly and weekly consolidation passes write derived material (journal, distilled facts,
  self-summary, weekly chapter) tagged with what it was derived from. They never edit what you
  said, and they can't read each other's output, so conclusions can't quietly pile up on earlier
  conclusions.

Details: [`docs/MEMORY-AND-RECALL.md`](docs/MEMORY-AND-RECALL.md). Before adding anything to her
context, read [`docs/LANES.md`](docs/LANES.md), which covers the six ways information reaches her
and which ones have been measured wrong before.

### Speaking first

`harness/kairos/` is an idle loop that checks, on every tick, whether she has a named reason to
speak: *continue* (she was cut off), *check-in* (it's been quiet), *remind* (she promised), *solo*
(her own time), *muse* (something she concluded), or one of the overnight presence modes. Every
limit is checked before the model is asked: cooldown, hourly cap, chain length, minimum idle time,
and never talking over a question she's waiting on you to answer. An attempt uses up its slot even
if she decides not to speak. Before that rule existed, a vetoed turn could be re-proposed seconds
later, which burned eleven minutes of GPU per cycle.

### How it compares

| | chat front-ends<br>(LM Studio, Open WebUI, SillyTavern) | agent/memory frameworks<br>(LangChain, Letta, mem0) | **Kairos** |
|---|---|---|---|
| **memory** | the chat, plus what you paste | retrieved context, often summarised forward | a ledger of facts with speaker, source, time and status |
| **forgetting** | delete it and it's gone | evicted or re-summarised | retired, never deleted |
| **speaking first** | never | on a schedule you write | named reasons, silent by default |
| **personality** | a system prompt | a prompt plus tools | persona plus traits curated from evidence, with mood and outfit cues that change real state |
| **testing** | manual | unit tests | ~160 offline gates, each a named claim with a receipt |

**What it isn't:** a model server (bring your own), a document-search (RAG) tool (her memory is
about a person, not a corpus), or multi-user (one companion, one person, local-only by default).
The trade-offs: an append-only ledger grows and needs occasional cleanup, a companion who speaks
first sometimes picks the wrong moment, and a test suite this thorough makes changes slower.

### What the custom engine adds

Everything above works on any endpoint. The optional sp-daemon backend also provides the raw
stop-vs-continue signal behind her *continue* impulse, byte-exact decoding, audio and vision input
frames, engine-side memory embeddings, and the prefix warm gate. Without it those features degrade,
and the degradation is documented in [`docs/BACKENDS.md`](docs/BACKENDS.md) and
[`docs/OFF-BY-DEFAULT.md`](docs/OFF-BY-DEFAULT.md).

### Security note

The gateway binds to `127.0.0.1`, and being reachable only from your own machine is its security
model. If you open it to your network (for the watch, say), scope it with a firewall rule;
`python tools/lan_bind.py --status` checks that the scoping is actually in place.

### Contributing and testing

Run these before calling a change done. They're offline:

```bash
python harness_tests/g_claim.py && python harness_tests/g_durability.py && python harness_tests/g_memory_lifecycle.py && python harness_tests/g_backend_seam.py && python harness_tests/g_docs_true.py
```

The whole offline suite is `python tools/sweep.py`, and it needs no GPU. Live gates read
`SP_GATEWAY_URL` / `SP_BOOT_GATEWAY`; the companion profile serves on `:8810`, so set that.
`g_kairos_boot.py` is the acceptance run.

Kairos is exported from a private working repo (see `KAIROS-SOURCE.txt` and
[`CONTRIBUTING.md`](CONTRIBUTING.md)).

### Further reading

| | |
|---|---|
| a two-minute map of the code | [`START-HERE.md`](START-HERE.md) |
| full setup: endpoints, keys, models, settings | [`docs/SETUP.md`](docs/SETUP.md) |
| rules and known traps, for people and coding agents | [`AGENTS.md`](AGENTS.md) |
| index of all documentation | [`docs/README.md`](docs/README.md) |
| every test gate and what it proves | [`gates/GATE-INDEX.md`](gates/GATE-INDEX.md) |
| what ships off, and how to turn it on | [`docs/OFF-BY-DEFAULT.md`](docs/OFF-BY-DEFAULT.md) |
| the room's code and design kit | [`ui/README.md`](ui/README.md) |
| her face and how new looks are made | [`docs/AVATAR-PIPELINE.md`](docs/AVATAR-PIPELINE.md) |
| tools, MCP and Home Assistant | [`docs/MCP.md`](docs/MCP.md), [`docs/HOME-ASSISTANT.md`](docs/HOME-ASSISTANT.md) |
| off-the-record mode | [`docs/ANON-MODE.md`](docs/ANON-MODE.md) |
| what changed, by version | [`CHANGELOG.md`](CHANGELOG.md) |

MIT licensed.
