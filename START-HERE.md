---
type: map
title: "START-HERE — what Kairos is today, in two minutes"
status: LIVE — update with every profile change (the doc-truth gate reads it)
updated: 2026-08-25
---

# START-HERE — what Kairos is today

**She is** a local AI companion: your model (a 128-expert MoE, ~4B active) served by her
own Rust + CUDA engine on one RTX 2060, with a Python harness that owns everything that is not
arithmetic — memory, agency, personality, presence, senses, voice, the room. She remembers the
person she talks to, speaks unprompted when she has a reason, has a face and a wardrobe she
chooses from, and a voice. **The one rule over everything: nothing she knows is ever deleted.**

## The stack, and where each piece lives

| piece | what | where |
|---|---|---|
| the one door | profile → environment; refuses bad compositions; launches the rest | `serve.py` + `profiles/companion.toml` |
| the engine | the Rust daemon (`sp-daemon`) and CUDA kernels: KV cache, prefill, `/v1/chat`, `/v1/oneshot`, `/v1/capture`, `/v1/embed` | `engine/` (build: `engine/build-wirecuda.bat`) |
| the gateway | the Python brain behind the room: SSE chat, the spine (decide→execute→verify), every panel's routes | `harness/server/app.py` |
| memory | the fact registry (`var/memory/registry.jsonl`), lifecycle, verdicts, the one read seam | `harness/skills/memory.py`, `lifecycle.py`, `verdict.py` — doc: `docs/MEMORY-AND-RECALL.md` |
| kairos | unprompted speech: continue / check-in / remind / solo / muse, on the idle clock | `harness/kairos/` |
| personality | persona fragments (local, gitignored `persona/`), marks (`[MOOD:]`…), the curator | `harness/personality/` |
| wardrobe & face | the catalog — clothing / gestures / moments — stills + loops through the xAI API | `harness/control/{avatar,wardrobe,catalog}.py`, `tools/avatar_gen.py` — doc: `docs/AVATAR-PIPELINE.md` |
| voice | Ara through the xAI API (expressive tags), local voxtral as fallback; the room speaks her replies | `harness/voice/` |
| senses | the hourly ambient eye (quiet-guarded), sight, the ear | `harness/senses/` |
| the room | the React desktop: chat, panels, dock, settings | `ui/` → built into `console/room/` |
| CPU sidecars | LFM2.5 helpers: deep recall, page reading, judges | `harness/sidecar/` — doc: `docs/AUX-MODELS.md` |

## How to start, and how to stop

```bash
python serve.py companion        # boots daemon + gateway; ~2–5 min to a hot prefix
```
Open http://127.0.0.1:8800/ — it lands on the room. Stop her from the room (the ⏻ in the dock:
*her only* / *everything* / *kill*) or `python serve.py --stop`. The profile is **positional and
not optional**: `agent` is the smaller 12B profile, still runnable, not her.

## What is on, what is off

Every knob that ships off has a row with the evidence that would arm it in
[`docs/OFF-BY-DEFAULT.md`](docs/OFF-BY-DEFAULT.md) — it is a live ledger, and
`harness_tests/g_offledger.py` holds it to the profile. Live today (2026-08-25): kairos (all
reasons) and the presence modes, the xAI voice / images / live search, the ambient eye with its
quiet guard, the LFM sidecars, wardrobe generate-now (picture *and* motion in one pass), the
semantic rank at the recall seam, and the KV reseam. Off: byte-exact mode, the speculative
drafter, the daemon's own memory writers (refused at boot), the research tier for HER unprompted
use, games and poker, her music deck (parked 2026-08-25 — unused tools still spend context),
voice clone (region-locked).

## How she consolidates

Base testimony is never deleted — only tombstoned. Higher-level knowledge is written as
**distillates** (and weekly `chapter` rows) carrying `derived_from`, `support_days` and
`support_kinds`. They summarise; they do not supersede their sources, and an inference may
never retire an observation. When *every* support of a distillate is retired, the distillate
is orphaned and tombstoned with it. The only authoritative write is still `remember()`.

**Nightly — `becoming.nightly`.** Once a day the main model (never an aux) reads up to seven
days of her self-narrative and feelings and writes one short first-person paragraph on who she
has been becoming (`kind=self_description`, status `inferred`). It refuses a window that is one
day, or one kind wearing a week's clothes — a missing paragraph is recoverable, a false one
becomes who she is. One write per calendar day.

**Weekly — `narrative.weekly_chapter`.** Once every seven days, one paragraph for what the week
*was*, over the episodic kinds only.

**Neither consolidator may read a distillate — the other's, or its own.** Stated as two
hand-kept kind lists until 2026-08-25, when the deny-list side was found never to have named
its own kind: three `self_description` rows on the live store, the third resting on the first
two, the language visibly folding inward. The rule now reads the `derived_from` mark itself
(`lifecycle.is_distillate`), so a consolidator written next year is covered the day it stamps
its first row.

Ask why she believes any of it: the **why** button in the memory panel, `GET /v1/memory/why`,
or `memory.provenance()` in her own voice. Full rules:
[`docs/MEMORY-AND-RECALL.md`](docs/MEMORY-AND-RECALL.md).

## The gates

`gates/GATE-INDEX.md` indexes every executable gate in `harness_tests/` — OFFLINE (no GPU),
LIVE (the stack up), and their run command. The whole offline suite is `python tools/sweep.py`
(~3 min; 137 green / 3 correct skips as of 2026-08-25). The minimum bar after touching memory:
`g_claim`, `g_durability`, `g_memory_lifecycle`. After touching docs: `g_docs_true`. A gate
touched gets its index row in the same commit.

## Where to read next

- **`AGENTS.md`** — the bug class this project keeps paying for, the non-negotiables, the
  traps that are still live, how gates are written. Read before changing anything.
- **`CHANGELOG.md`** — what changed, by the day it changed.
- **`docs/LANES.md`** — the six ways a fact reaches her, and which one yours belongs in.
- **`docs/PANELS.md`** — every window in the room, what it reads, and whose it is.
- **`docs/README.md`** — every document and which one is authoritative for what.
- **`ui/README.md`** — the room and its window framework.
- **The commit log** — it carries the reasoning, on purpose. `git log` is a primary source.

## The five non-negotiables

1. No claim without a repeatable gate. 2. Nothing in memory is ever deleted. 3. Measured vs
asserted, always said. 4. Her word never outranks his. 5. Verdicts are rulings of committed
finite tables — prose and magnitudes never rule.

*Sibling repos: [shannon-prime-lattice](https://github.com/nihilistau/shannon-prime-lattice)
(the research ledger and papers); [**Kairos**](https://github.com/nihilistau/Kairos) (the engine-agnostic framework, exported from this
tree by `python tools/kairos_export.py` from the manifest in `kairos-export/` — filtered, scrubbed,
fresh history; `docs/BACKENDS.md` is the seam it rides on; `profiles/companion.toml` runs it here
on :8810 beside her).*
