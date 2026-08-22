# Changelog

## 0.2.1 — the gates 0.2.0 shipped red (2026-08-23)

A fix release. **0.2.0 shipped five OFFLINE gates that fail on a fresh clone** — if you
cloned it and ran the suite, this is why:

| | 0.2.0 | 0.2.1 |
|---|---|---|
| G-TUNING | 11/13 | 13/13 |
| G-KAIROS-POLICY | 9/12 | 12/12 |
| G-KAIROS-TICK | 5/9 | 9/9 |
| G-KAIROS-TABLE | 11/13 | 15/15 |
| G-KAIROS-QUIET | 16/19 | 28/28 |

All five passed at 0.1.0. Bisected upstream to the commit that made every `TurnState`
clock start at process boot instead of `0.0` — because a zero clock fails OPEN, and five
unrelated checks were being skipped when a clock was unset. That change is correct and
stays. **No behaviour changed in this release**: the five gates had gone stale against a
policy that legitimately moved, and three of them were red for a reason with no relation
to what they guard.

- Three drive small synthetic clocks (`100.0`, `5000.0`) and let `TurnState`'s default,
  which now sits in the fixture's *future* — so every decision came back
  `cooldown (112962s left)`. They pin the boot clock, as the gates updated alongside the
  original change already did.
- `G-KAIROS-TABLE` left two clocks defaulted, so `presence_idle()` was negative on all 512
  cells and every idle-floored ruling collapsed at once. It now **sets** the clocks: a gate
  whose claim is that a cell determines the world cannot leave a coordinate to a module
  global read at construction time. That exposed the one real change — 2 cells of 512,
  `muse -> silent`, both into a busy room, which is MUSE's new idle floor (a thought waits
  for a quiet room like everything else). Reviewed, written into the precedence artifact
  as two rows, asserted both ways, and re-frozen.
- `G-KAIROS-QUIET` read `scheduler.py`'s *source* for a literal that had moved into
  `impulse.decide()` — a gate reporting the location of a thing rather than the truth of
  it. It now drives the real policy, each action run twice (knob armed, knob off), because
  asserting silence proves nothing unless the knob is shown to be what caused it.

Also carried: the curate panels (re-file a memory without losing it, and a queue for what
only a human can settle), a correction to what the confluence divergence actually is
(dedup, not supersession), and the export procedure written down in one place.

Verified in the published tree, not upstream: **105 pass, 2 skip, 0 fail** across every
offline gate; G-KAIROS-SCRUB 17/17; the gateway imports with `SP_ENGINE_KIND=openai` and
no engine present; the bundled avatar set seeds 7/7 faces.

## 0.2.0 — narrative identity, the semantic floor, presence modes, and a default face (2026-08-23)

**Narrative identity, and the structure under it.** Distillates carry `derived_from` /
`support_days` / `support_kinds`, and a conclusion whose supports have all been retired is
retired with them — a conclusion should not outlive its evidence. Durability moved from
CLASS to KIND: what she concluded (journal, self_description, thought, dream, chapter)
never fades; what she did (narration, spoke_up) fades at 120 d. Decay is not deletion.
`kind="chapter"` rolls a week into one paragraph, and the self-block is who-she-is, then
the weeks, then four recent lines chosen round-robin across kinds so it spans threads
rather than one evening.

**The semantic floor.** A new embedding space, `aux-1024-v1`, from the CPU sidecar — which
matters more than it sounds for an engine-agnostic framework, because it is the only real
embedder a foreign backend has. Measured through the real seam on the frozen 160-query
corpus: recall@1 0.46 -> 0.53, decider hit rate 0.06 -> 0.17, both foreign-noise metrics
unchanged. Raw cosine, never centred, its own tau — measured, documented, gated.

**Presence, sight, and the librarians.** Narration / Company / Lucid Dream modes; the LFM
sidecar framework with model pickers and structured output; a vision backend choice; her
own journal reachable from the deep-recall archive, which it could not see before.

**A face out of the box.** `assets/avatar-default/` ships one outfit across all seven faces
plus six gestures, seeded on first boot — so a fresh clone has a face instead of the
fallback SVG, with no generation step and no API key. The drawn SVG stays underneath as the
floor. `docs/SETUP.md` and the **setup** window cover the endpoint, where every key file
goes, the model cards, and what each setting affects.

**Order invariance, measured rather than assumed.** G-CONFLUENCE asks whether ingesting the
same claims in a different order yields the same store. It does not — and that is correct,
since a store where a later correction does not win would be the broken one.

## 0.1.0 — first export (2026-08-21)
First public export from shannon-prime-kairos (see KAIROS-SOURCE.txt for the commit). The
engine-agnostic harness + room: the backend seam (`SP_ENGINE_KIND=openai` default here), memory
with tombstones and verdicts, kairos unprompted speech, personality, wardrobe/catalog, the xAI voice
with expressive tags, the ambient eye with its quiet guard, the room with its window framework, and
the gates that prove them. The source companion's own persona, profiles, engine and research stay
in the source repo.

Acceptance: `gates/KAIROS-BOOT-2026-08-21.md` — the tree booted against LM Studio (a 1.2B model on
CPU, auth on) from its own directory and held a turn with memory and the room: G-KAIROS-BOOT 12/12.
Five things broke on the way and each got a gate before the green (listed in the receipt).
