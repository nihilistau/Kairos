# Changelog

## 0.4.0 — the MCP release: what a server may see, and what it may become (2026-08-25)

An audit of the MCP layer in both directions, and the read side of provenance. **If you run
this framework and have ever put a server in `mcp_servers.json`, the first three were yours
too.**

**An external server could take the name of one of your agent's own tools.** The rule
`mcp_servers.json`, `docs/MCP.md` and `bridge.py` all state — on a collision the native tool
keeps the bare name, the bridged one arrives as `<server>_<name>` — ran **backwards** for nine
of the fourteen native packs. The bridge was spliced into the *middle* of `all_tools()`, so its
exclusion set was computed from the five packs above it, and every pack below skipped any name
already taken, against a set that by then held the bridged names. A native tool whose name an
external server claimed was silently **dropped**, and the namespacer never fired, because it
only renames what is already taken. Live on the reference profile: `chrome-devtools-mcp` is
allowed `take_screenshot`, which is also the local sight tool — the browser held the bare name
and the native tool did not load. The fix is one line of ordering; **G-MCP-SHADOW** (14/14) is
what stops it returning, driving a real greedy bridge through the real `all_tools()`.

**Every spawned server got your whole environment.** `_client_for` built `dict(os.environ)` and
handed it to the child — every API key you have exported, and the path to your entire memory
registry, given to whatever `npx -y …@latest` resolves to at spawn time. The default now
inverts: a child gets what an interpreter needs to *start* on the platform plus exactly what
its own `env` block declares. A server that genuinely needs more declares `"inherit_env": true`
and says why.

**A tool may no longer quietly become a different tool.** Name, description and schema are
fingerprinted on first sight and a changed fingerprint is **refused** by name — the rug-pull,
where a server is approved once and later returns the same tool with a new description. The
description *is* prompt, so a same-name swap is a complete exfiltration primitive that changes
nothing a human would notice. `python tools/mcp_pin.py --accept <server> <tool>` accepts a
legitimate change; `SP_MCP_PIN=0` disarms the whole mechanism. Trust on first use, said plainly:
it cannot vouch for the *first* listing, only that yesterday's offer is today's.

**A remote server is now a decision rather than a URL.** `{"url": …}` went straight to
`Client(url)`: any scheme, any host, no authorization. Loopback is fine; anything else is
refused unless the block says `"remote_ok": true`, and plain `http` to a remote host is refused
even then. **What is not built is written down**: OAuth 2.1 with PKCE and resource indicators is
unbuilt, so a remote server you *do* allow is unauthenticated. Ledgered in
`docs/OFF-BY-DEFAULT.md` §7b with its arming condition, because a guard that looks like more
than it is gets trusted.

**The outbound server now exposes *her*, not just her machine.** `docs/MCP.md` had claimed since
July that it exposes "her memory, her board and her skills"; it exposed a sandboxed filesystem,
web, a clock and five memory tools. The sentence was not deleted — the capability was built:
`why_she_believes`, `what_she_knows`, `what_she_is_wearing`, `what_she_has_been_doing`,
`why_she_is_quiet`, `whats_on_the_board`. Read-only, deliberately: an outbound client is across
a process boundary with no operator in the loop.

**And the receipts can finally be read.** `derived_from` had been written through one door,
enforced by the nightly orphan sweep and gated — while the only code that resolved a support
name to a row was a private dict inside a predicate. *"Why do you believe that?"* got zero
steps. Now: `memory.supports_of` / `dependents_of` / `missing_supports`, `provenance()` walking
the chain, `GET /v1/memory/why`, the epistemic fields `/v1/memory` had been dropping
(`status`, `derived_from`, `support_days`, `superseded_by`, `retired_because`), and a **why**
button in the memory panel showing each support's *current* liveness plus what would be orphaned
if you retired the row. The doctrine that survives it: provenance is a door *she speaks from*, so
a retired support is **counted and never quoted** — the audit lane shows the dead, the spoken
lane tallies them.

**A related bug this exposed: she had begun writing her nightly paragraph out of her own nightly
paragraphs.** `becoming.nightly` excluded the *other* consolidator's output and never its own
kind. Three rows deep on the reference store, the third naming the first two, the texts visibly
folding inward. The rule is no longer a hand-kept list of kinds — it reads the `derived_from`
mark itself (`lifecycle.is_distillate`), so a consolidator added later is covered the day it
stamps its first row.

Also: `fastmcp` and `mcp` are declared in `pyproject.toml` at last; `tools/mcp_pin.py` ships
(a refusal without its acceptance door is an outage with a dead link in the error text); and
`livestore.py` takes one cross-process lock, because the suite runs gates in parallel and a
reader of her live wardrobe was racing a writer — a gate red only when its neighbour is
mid-write teaches people that sweep reds are noise.

**And this release's committed bundle actually corresponds to its committed code.** The
manifest ships `ui/src/**` *and* the prebuilt `console/room/**`, and the scrub rewrites tokens
inside six of those source files — so every previous release shipped a bundle built from the
private tree's sources sitting beside somebody else's. Found by running *this* repo's own sweep:
G-ROOM-BUNDLE rebuilt from the scrubbed source, got a different hash, and said so. The export
now rebuilds the room here, from here (and the export's dependency install is no longer wiped on
every run, which is why the rebuild had been quietly declining to happen). The 0.2.1 lesson
again: upstream-green does not mean export-green, and the fix is to make the claim true rather
than to loosen the gate.

Upstream sweep at release: **137 green, 3 correct skips, 0 red.**
Sweep in *this* repo at release: **109 green, 1 correct skip, 0 red.**

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
