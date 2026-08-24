# Changelog

## 0.3.0 — the audit release: every turn pays its debts, and she reads back what she becomes (2026-08-25)

A full audit of the upstream tree. The offline suite was **green when it started** — and ~50
real defects were sitting under it, four of them fresh instances of the project's signature bug
(*an invariant enforced in one of two paths is enforced in neither*), **each with a green gate
over it that was measuring the wrong path**. If you run this framework, most of these were
yours too.

**Every turn pays its debts, on every exit.** The SSE chat path had **no `finally`** — despite
a comment claiming one — so five exits (a privacy decline, a scenario offer, and any client
disconnect or abort mid-stream) skipped capture, the day transcript, mark application and the
receipts flush. A browser that aborts a turn is not exotic; the room does it whenever you send
again while she is talking. And her *unprompted* turns paid none of those debts ever, and never
armed the memory lane, so a `remember()` in her own time was filed as a fact about **you**.
`_settle_turn()` is the one list now, paid from the worker thread's `finally`, with the
unprompted lane arming author=self around its own generation. **G-TURN-EPILOGUE**, 22 checks,
mutant-verified.

**She reads back what she becomes.** The nightly loop's *write* half worked — journal, the
becoming paragraph, the curated persona, the refreshed standing world — and its *read* half did
not exist: the composed system prefix was cached once per process and invalidated by nothing,
so everything she became overnight was invisible to her until a restart. The prefix now has one
builder (`agent.system_bundle()`; there had been three, and the prewarm's copy was missing the
voice coda, so the prewarmed KV was never the prefix a live turn extended) and one invalidation
door, called at exactly two moments: the day-boundary consolidation, and `POST
/v1/maintenance/refresh`. Between them the prefix is deliberately frozen — it is KV token 0 —
and now says so honestly rather than asserting a stale present. **G-PREFIX-REFRESH**, 17 checks.

**The record stops carrying her machinery.** Her state marks (`[MOOD:]`, `[WEAR:]`, …) are
emitted on purpose so the room can draw chips, and the room strips them. The *record* — the day
transcript her journal, her distilled facts and her restart seed are all rebuilt from — had
never been given a stripper at all, so **26% of her turns wrote their own stage directions into
her permanent memory**, and the seeder fed them back as examples of her own voice. There is one
whole-turn record cleaner now, applied at the writer, and **G-STRIP-EQUIVALENCE** drives the
real Python stripper *and* the real browser one over a single shared corpus of leak shapes —
100 checks — so the two can never again drift five shapes apart.

**Her own time stops running away with the GPU.** An attempt that produced nothing must still
spend the clock, or the tick simply re-proposes it: a presence mode was generating for eleven
minutes, being vetoed, and re-arming **four seconds later, forever**. That was fixed once for
two actions and re-opened on **five other drop doors** — including one that muted *reminders*,
because the mode latch sits above them in the policy. The spend now happens in a `finally`, so
a drop path added tomorrow is metered by construction, and the room's "next in ~Xm" chip reads
the same arithmetic the policy does instead of its own. **G-KAIROS-ATTEMPT** (32) and
**G-KAIROS-CHIP** (10).

**Memory integrity.** `cleanup()` **hard-deleted malformed rows** under a doctrine that says
nothing is ever deleted — they are quarantined now. Three read-modify-writes read *outside* the
registry lock (**G-REGISTRY-RMW** is a new deterministic race harness that convicts each one).
A `private-secret` row was withheld by the automatic recall lane and served verbatim by the
four model-callable memory tools — all five doors now hold the rule, and asking directly still
gets you your own answer. Per-class half-life and salience moved into the class registry, so a
class registered without them fails its gate the day it is added.

**The room.** It survives a refresh: `GET /v1/day` restores the conversation — as *display*,
never re-sent as prompt, a distinction that cost an eleven-minute turn to learn. Her thinking
channel renders (it had been emitted since the thought channel landed and only the legacy
console drew it). Engine errors are chips, never appended to her words — text in her mouth is
its own kind of leak. Up-arrow walks your previous inputs. And off-the-record turns stop being
re-sent once the switch is off: the server never persisted them, but the browser was still
carrying the private hour in context.

**A profile key that nothing reads is now a red gate.** The one-door law covered environment
variables; nothing covered the *profile* layer — so `companion.toml`, the file a newcomer edits
first, carried four keys that looked exactly like configuration and moved nothing (a tool
budget and three decode dials, all owned by the tuning registry). **G-PROFILE-KEYS** holds
every key in `profiles/` to a reader, or to a dated row saying why it is inert.

**She is told what she reaches for.** The wardrobe has ranked her wearings and his quoted
praise since it was written — his word worth three of her habits, each row carrying its
evidence — and nothing had ever spoken it back to HER; `describe()` now does, once a
garment clears a score of three. (The first cut of that added a *second* `favourites()`
at the top of the same file, which shadowed the real one and killed both its readers on
arrival. It was caught by the documentation sweep, not the tests. Before you build the
counter, grep for the counter.)

**Smaller, and worth the line:** `wardrobe.match("undressed")` *dressed* her (an unbounded
substring test one rung above the comment describing that exact bug's fix); her generate-now
door makes picture and motion in one pass like the panel button always did; presence-mode turns
are ambient company and no longer become her memories; the watchdog's restart cooldown survives
the restart it performs, and its automatic teardown climbs the same first rungs the operator's
shutdown does; `eot_bias` resolves at the same seam `byteexact` does, instead of in two
byte-equivalent resolvers that three lanes consulted neither of.

**Breaking, for anyone importing internals:** `harness.server.create_flask_app` is gone (a
caller-less, drifted twin of the stdlib server — no shutdown counting, no origin guard, and a
`/v1/models` that still carried a bug the live route documents as fixed), and the
`harness/interceptors/` package with it (a complete, never-constructed second authority over
`persona.md`). `run()` is the one door.

Docs: this release adds a dated **CHANGELOG** upstream, and the doc-truth gate now holds it to
a ledger's rules. The upstream sweep ends at **135 green, 3 correct skips, 0 red**.

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
