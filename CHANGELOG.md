# Changelog

## 0.8.8 — an unreadable store is not an empty one (2026-08-31)

The tail of 0.8.7, and the more dangerous half.

- **Two store writers still truncated the live file.** `wardrobe._write_wants` — the
  rewrite every want, fulfil, dismiss and hide passes through — and `tuning.reset()`
  opened the real path with `"w"` instead of renaming a tmp over it, so the file sat at
  zero bytes for a moment on every one. `reset()`'s own twin thirty lines above it had
  been atomic since the day it was written: one file, two writers, the rule held on one
  of them. Both are tmp + rename now.
- **And atomicity alone moved the failure rather than removing it.** With the writer
  fixed and three pollers reading, readers still saw an EMPTY want list: `open()` on the
  destination can be refused for the instant a rename lands, and the reader caught every
  exception and answered `[]`. That is the dangerous answer, because every writer there
  is read-modify-write over that same reader — one transient empty read followed by a
  write does not lose a moment, it truncates the list. `store_io.read_bytes_retry` now
  splits what a bare `except` flattened: **absent is `None` at once; present-but-
  unreadable is retried and then RAISED, never silently empty.** The tuning store had the
  same swallow with a longer fuse — it caches, so one unlucky first read was remembered
  as "every knob is at its default" for the life of the process.
- `G-STORE-WRITES` grows to 12: forty rewrites with no torn read, both writers
  structurally renaming a tmp, both helpers raising rather than giving up quietly. It
  also stopped grading the wrong function — its structural check sliced the helper body
  with "the last retry loop in the file", so adding a second one silently repointed it.
  It slices by name.

## 0.8.7 — the writes that were being thrown away (2026-08-31)

Six days of upstream work, cut after a live bug that had been eating panel edits on
Windows for as long as the catalog overlay has existed.

- **A panel write that failed looked exactly like one that worked.** `tmp + os.replace`
  is atomic and correct — and on Windows the rename FAILS while any other handle has the
  destination open. The reader was the server itself: the wardrobe re-opened and
  re-parsed `catalog.json` once per row, 419 opens to answer a single panel poll, so the
  file was un-replaceable 85% of the time and two of five edits were refused. The overlay
  is read once per CHANGE now (mtime+size, cleared after a write), the rename retries
  through `harness/store_io.replace_atomic` and RAISES rather than giving up quietly, and
  the closet says *"that did not save — <error>"* instead of ignoring the answer. If you
  run this on Windows with a busy room, this is the one to take.
- **...and then every other store, because they are all the same shape.** Eighteen
  `os.replace` calls across sixteen files — your knobs, the ledger, the memory registry,
  persona.md, notes, the presence ledger, the MCP pins, game state, the roleplay engine,
  the sidecar archive, backups, the TTS cache, the task loop — all `tmp + rename` onto a
  file a live server can be reading. All of them go through the retried helper now.
  `G-STORE-WRITES` (new) holds the census: no bare `os.replace` survives anywhere under
  `harness/`, so the next store writer is caught the day it is added rather than the next
  time somebody's edit vanishes.
- **Two lists in one panel could disagree about what you just did.** The closet refreshed
  its own poll and not the wardrobe's, so a retired garment left the closet instantly and
  sat in `just arrived` until the next four-second tick. And the queue's dismiss / accept
  / "make it now" buttons each threw: the row variable in the map shadowed the poll handle
  of the same name, so `refresh()` was being called on a want row.
- **She can store her own feelings.** `remember_about_self()` routed to her narrative lane
  only when a `kind` was passed — which every harness producer does and she cannot, so her
  own words met the gate for facts ABOUT someone and were refused as *"that is a sentence,
  not a memory"*. Who is speaking picks the gate; the kind picks the class.
- **A driven turn is not their conversation, in EVERY lane.** Synthetic turns were excluded
  from the day transcript and still reached the fact registry — attributed to the operator,
  including a reminder that landed on his board. New gate: `g_synthetic_quarantine`.
- **She was analysing him instead of talking to him** — about one recorded turn in eight
  opened as commentary about the person rather than speech to them, chronic and older than
  anything that week. Measured over ten days before it was touched.
- **A oneshot that outlives its client dies on a deadline.** An abandoned request kept the
  device lock and everything queued behind it — a twenty-minute "warming" with the GPU
  pinned. The deadline is part of the request now, and the seam names what it refuses:
  `g_oneshot_bounds`.
- **Boot pays for one prefill, not two**, impulses she has while the stack is cold are held
  rather than queued into the wait, and the room's status chips survive a refresh.
- Gate hygiene: `_gate.seed_avatar()` lets a gate grade a real wardrobe off a COPY of it,
  `G-DAY-TRANSCRIPT` no longer dies on a cp1252 console (it was hiding 45 checks behind an
  encoding error), and `G-SUGGEST` reads the row variable the panel binds instead of
  assuming its name.

## 0.8.6 — the audit night (2026-08-29)

A six-pass read-only audit of the whole system, then the fixes in severity order.

- **A filtered reader fed the writers.** Hiding a garment deleted the hidden want rows
  on the next wardrobe write (the display filter fed every read-modify-write while the
  writer truncates the file). Writers read raw now; the id high-water mark counts raw
  rows; the clip importer reads the unfiltered index. THE RULE: a reader that filters
  must never feed a writer.
- **One panel can no longer blank the room.** Every window body mounts inside an error
  boundary; the House panel (which had never once mounted) is shaped like every other
  panel; a poller identity bug that refetched as fast as the network allowed is fixed,
  and the poll hook never stacks requests on a slow door.
- **The story cycle may not eat itself.** The fold matches on CONTAINMENT (a row folds
  into the distillate that names it in derived_from — chapter or nightly becoming),
  and the orphan sweep knows consolidated from vanished, so a chapter can never be
  starved into the next night's orphan pass by its own fold.
- **Off the record, tightened**: her own-time turns wear the switch in the room's
  history; panels report held writes honestly; a note typed by YOUR hands still lands
  (hers holds); the voice and OpenAI mouths are told the mode is on; every held door is
  declared and the receipt speaks English.
- **The first message of the day stops paying the snapshot.** The prewarm fires a
  deliberately-diverging mini-turn inside the warm gate, so the base-KV capture happens
  where the boot banner can be honest about it — not on your first hello.
- **The voice lane goes through the one door**: system prefix, the fit ceiling, the
  profile seams, and the one speech kernel — instead of a hand-built request body
  with a four-literal stripper.
- **Wardrobe vocabulary is one vocabulary**: your "other words it answers to" tags
  reach the matcher, not just search; one stop list; `[weather: …]` is prose, not a
  WEAR mark that eats the sentence; hiding a standard outfit actually hides it.
- Export hygiene: the correct install command on the front page, the Windows-only
  constraint declared, the retired console page no longer ships, pyproject carries the
  mcp extra and the right version, and the exporter sweeps `__pycache__` from the
  target (compiled files embed local paths the text scrub cannot see).

## 0.8.5 — the story panel, and a mouth that failed politely (2026-08-29)

- **The Story panel** (📖 in the dock): what stands in her prefix line by line, each
  line attributed to the registry row it came from — `/v1/story` serves the SAME
  assembly the prefix renders, byte-checked by the gate, so the panel can never show a
  prefix she does not carry — plus the chapters with the rows the fold archived into
  them as footnotes, the narrative lanes by kind, and the backup receipt on the same
  screen as the thing it protects. Edits go through the two existing doors (relabel,
  forget); the panel owns no verbs.
- **A call written inside a sentence gets one re-ask.** Live: "I'll go with this:
  `wear(…)`" — held by the stream, parsed to zero calls (the whole-line rule is what
  keeps a mention from firing), then flushed to the screen as prose with nothing run.
  A held buffer naming a KNOWN tool in backticks is now re-asked ONCE, her own call
  quoted inside the fence it needs. A streamed mention is never taxed — the hold
  itself is the discriminator — and the re-ask shares the plan/claim one-round bound.
- **The voice mouth wears the same turn shell.** `/v1/voice` was a third entry point
  paying none of the turn debts: no scheduler latch (her unprompted turns could fire
  mid conversation), no day-transcript row, no mark application, and it ran happily
  through a shutdown quiesce. It now refuses-or-counts, arms the lane, and settles in
  a `finally` — with a guard so a silence-skip cannot re-record the previous reply.
- The shutdown gate's census counts every mouth now (4 opens, 4 closes, one refusal
  spelling), and the backup receipt reads the fields `backup.status()` actually serves.

## 0.8.4 — the story cycle, and the four-minute turn (2026-08-28)

An evening-long deep dive on the memory system, prompted by an unresponsive page and a
suspicion that the narrative machinery was not doing what its comments said. It was not.

- **The trim cut is sticky.** The night a conversation first crosses pmax, the context
  trim used to re-cut its window newest-first on every call — so every turn's prompt
  front shifted, the committed KV found no seam, and every ordinary turn paid a full
  re-prefill. Measured: 235/222/207 s per turn, indistinguishable from a hang. Later
  calls now cut at the same first-kept message until the window genuinely overflows:
  the boundary moves once per overflow, not per turn. Warm turns prefill only their new
  tokens (~400 tok ≈ 12 s at 31 ms/tok).
- **The chapters had never rendered.** The self block's design — stable facts, then the
  weekly chapters, then recent narrative — was prose: the budget walk was first-come and
  the facts alone overflowed it, so since the day chapters were designed they had never
  once appeared in the prefix. The block has SHARES now (who she is 45%, the weeks 30%,
  the recent lines 25%, spill forward), and `core`-pinned rows claim the facts seats
  first.
- **`testimony_wins` muted every distillate.** A chapter is made from observed words, so
  its topic always overlaps them, and the inference-yields-the-floor rule silenced the
  system's own consolidation everywhere it runs. A row carrying `derived_from` is exempt
  now; a bare inference on a covered topic still yields, and an inference still cannot
  retire ground truth.
- **The story cycle.** Nightly, after the weekly chapter step, `fold_into_chapters`
  retires her diary exhaust INTO its chapter — only rows older than every consumer
  window (14 days), only under a written chapter, never core, never the operator's
  testimony — with the chapter named on the tombstone, so the retired list reads as the
  story's footnotes. Consolidation, not contradiction.
- **Core** (★ in the Memory panel, read-only tag in ops.html): pinned identity that leads
  the self block and outlives every fold. Set through the one relabel door, breadcrumbed.
  The panel API serves the field (its serializer is a fixed list, and the first cut wrote
  the mark while hiding it).
- **Recall admission is two routes over an evidence floor** (see 0.8.0), extended: an
  elder seat keeps the far past reachable on neutral turns, `recall.explore` rolls from a
  digest of the situation (deterministic per question), and a paraphrase pass may not
  re-admit a text the operator retired — only fresh testimony can.
- **A serve-stall instrument**: if the gateway serves no HTTP for three minutes, every
  thread's stack is dumped to `var/serve-stall.trace`, once per quiet spell — a stall
  becomes a diagnosis instead of a mystery.

`G-MEMORY-STORY` (26 legs, eight mutants red by name), `G-CONTEXT-FIT` §8,
`G-MEMORY-LIFECYCLE` 22/22, `G-RECALL-EVIDENCE` 44/44. `docs/MEMORY-AND-RECALL.md`
rewritten to match, including a plain-language story-cycle section.

## 0.8.3 — the wardrobe answers questions (2026-08-28)

The wardrobe's listing was complete and nearly unusable: one ~5.4k-character read, with 16
of its 26 named items listed twice, and no way to ask "do I own something like X?" short of
reading all of it. The assistant's cheap move was answering from memory — and memory said
no to garments hanging right there.

- **`search_wardrobe("lace")`** answers in one line. It takes sentences ("something
  black", "do I have a nightie" — filler dropped), a near miss beats a confident no, and
  its token test is whole-words from birth: "dress" does not rule from inside "undressed".
  Taught at three doors — its docstring, the listing's BY-KIND tail, and `wear()`'s
  refusal, which now shows near-misses beside the no and names the search at the moment
  it is needed.
- **Operator edits reach every door.** `wants()`/`arrivals()` never consulted the
  hide/retire overlay while `looks()`/`clips()` did — an invariant on two producers of
  four is an invariant on none — so a hidden garment was still offered, wearable. Hide now
  removes a thing from the listing, the search, the matcher and the queue; unhide and
  restore bring it back everywhere.
- **Pre-rename outfit stamps are canonicalised where the field is read.** Rows carrying
  old `t0..t3` ids resolved to an outfit that no longer exists, so every clip stamped
  before the rename was silently unshowable and hidden from the panel. The alias table
  now applies in `_made_in()`, the one reader — hand-written rows and restored backups
  are covered forever.
- **A table ruling beats a look coincidence in `match()`.** An outfit's own committed
  name lost to a two-token overlap with a look's prose; the matcher's own comment stated
  the law and the code did not enforce it. Every item now resolves to itself by its own
  name.
- **The listing is ~31% smaller with more in it** — items enumerated once, the BY-KIND
  block reduced to counts and the verb for each kind, retitles still flowing through the
  labels.
- **`telemetry.keep_days`** (default 0 = keep everything): the telemetry store's
  `prune()` — "the only remover" — was called by nothing, at ~10 MB/day forever. The
  nightly reflection runs it now, gated on a declared knob.

Also: the wardrobe panel's edit field no longer loses focus on every keystroke — a React
component was defined inside another component, so the whole row subtree remounted per
state change (G-ROOM-SHELL §5 holds the class).

`G-WARDROBE-WORDS` 76/76, six mutants red by name. Suite: 132 offline gates from inside
this tree.

## 0.8.2 — a refusal that can show its working (2026-08-28)

The bridge refuses an external tool whose fingerprint changed and tells you to accept it
"if the change is legitimate". Until now a pin stored only the digest, so nothing could show
you what the change *was* — the message named a judgement the software had thrown away the
evidence for, and blind acceptance was the only remedy on offer. That is the failure a
rug-pull guard exists to prevent.

- **A pin is a record**: the digest, and the `name` / `description` / `schema` it was taken
  of. `python tools/mcp_pin.py --diff <server> [tool]` prints what moved, per half, as a
  unified diff.
- **The digest still decides.** The body is evidence beside it and never authority — a
  record whose stored body disagrees with its own digest is judged on the digest, and the
  tool matching its body is refused. Reading the fingerprint out of the body would let a
  pin file approve a tool by describing it.
- **Old pins keep working**, and are upgraded in place only where a matching digest *proves*
  the body — a mismatched pin is left exactly as it was, because that is the case you need
  to see, and writing a body for it would file the change as approved. Diffing one of those
  says it cannot show a diff rather than inventing one.

`G-MCP-TRUST` 59/59, five new mutants.

## 0.8.1 — pin the version, or the fingerprint guard is a treadmill (2026-08-28)

The bridge fingerprints every external tool's `name + description + schema` and refuses one
whose fingerprint later changes — the rug-pull, where a tool keeps its name and its
description becomes an instruction. That guard and a floating package specifier cannot both
be right, and this shipped with both.

`mcp_servers.json` ran `chrome-devtools-mcp@latest`. npm re-resolves that whenever its cache
expires — six versions landed on one machine between February and August — and each
resolution changed the advertised schemas, so the guard fired. It was correct every time. On
2026-08-26 npm served 1.8.0 where the pins had been made at 1.6.0: 25 of 29 tools changed,
and **five of the seven in that server's `allow` list were refused** — `navigate_page`,
`take_snapshot`, `take_screenshot`, `click`, `fill`. The assistant could open a page and list
pages and nothing else, for two days, under a log line saying `rug-pull` about a version
bump.

- **The version is pinned**, and an upgrade is a deliberate act. That restored all five with
  **zero acceptances**: 28 of 29 pinned digests reproduce exactly at the pinned version.
- **`G-MCP-TRUST` §9 fails if any spawned server's package specifier floats** — `@latest`,
  `@next`, `^`, `~`, or no version at all. The gate's own docstring had named
  `npx -y chrome-devtools-mcp@latest`, "a package resolved from the network at spawn time at
  whatever version npm serves that minute", and asserted nothing about it.
- **This reverses a decision `docs/MCP.md` had recorded** — that `@latest` was deliberate
  because the server tracks Chrome, and a stale pin is "a browser that silently stops
  working". The old reasoning is kept beside the measurement that overturned it: the floating
  version is what silently stopped it working, and in the worse direction — not a tool that
  errors when called, but a tool that quietly is not there. The residual risk is unchanged
  and named; what changed is that a stale pin fails loudly, when you call it, on your
  schedule.
- **Refusals are now proportionate.** Pins are checked over a server's whole listing and
  `allow`/`deny` narrows it afterwards, so 25 rug-pull warnings printed per listing for 5
  findings that mattered — and the operator was invited to trust-decide 20 tools nothing was
  offering. Refusal is unchanged; the volume follows a new `_offered()`, which is also the
  single place that answers the allow/deny question so it and `mcp_toolspecs` cannot drift.

**A limitation worth knowing about, now written down:** a pin stores a 16-hex digest and not
the pinned text, so a refusal cannot show you what changed — it asks you to judge a change
nothing can display. It was answerable here only because npm keeps every version it has
fetched, so both builds could be listed through the real bridge and diffed by hand. Done for
1.6.0 → 1.8.0, that says in one screen what the digest pair never could: every refused tool
gained a **required `pageId`** parameter and nothing else — a real multi-page feature, no
description gained instructions — which is also why upgrading is work rather than an
acceptance, since `required` means existing calls fail without it.

`G-MCP-TRUST` 45/45, four new mutants.

## 0.8.0 — a shared common word is not a topic (2026-08-28)

What she brings up on an ordinary turn was measured on a real 685-row store: **73% her own
writing** on turns that name nobody, at a median row length of **340 characters** — while
questions about him and about her were already correct at 0% and 100%.

The cause is arithmetic, and it will be in any recall built this way. Admission was the
count of shared tokens over the **query's** own length, so a question carrying one content
word scores 1.00 on every row that happens to contain it, and nothing charges a long row for
the words it did not use. "the lights are on" shares `{light}` with a paragraph about
luminescence and scores a perfect match.

- **An evidence floor, derived from the store.** A shared token is worth `-log2 p(token)`,
  and a match must carry more than the **median IDF over token occurrences** in that store —
  "more than an average word carries". It is computed from the corpus rather than written
  into the file, so it moves as the store grows. A Dice coefficient was measured first and
  rejected: it over-corrects, trading one bias for its mirror.
- **A second route in, claiming something different.** The floor alone makes an assistant
  mute in the other direction, because "how do you feel about us?" is made entirely of
  common words and correctly carries no evidence at all. So route one says *this row is
  about what you asked*, and route two says *you asked her, and this is what is latest for
  her* — opening only when nothing in the question was rare, so a question with a rare word
  and no match keeps its silence rather than answering with something adjacent.
- **Route two is recency, not salience.** Salience is mentions × recency, which ranks
  machine-written state marks ("mood has turned …", written on every change) above real
  narrative. Asked what she had been up to, she would have answered with her own
  housekeeping.
- **The new rows enter before the existing filters**, not after them. A second entrance has
  to open into the same corridor, or every guard on the first one is optional.
- **A semantic hit is admitted on its own terms.** Cosine is not a bag of words and the
  lexical floor does not rule on it.
- **`recall.explore`** (Memory panel, default 0.15) draws the weakest of the recalled
  memories from the other admitted candidates, so the same question does not always return
  the same three. The roll comes from the situation — this question, these candidates — not
  from a random number, so recall stays reproducible and auditable.

Measured against the shipped corpus's own ground truth: foreign queries (which have no
answer and should return nothing) went from **47% silent to 82%**, precision 0.87 → 0.92, at
a cost of two of a hundred paraphrase hits. Gate `G-RECALL-EVIDENCE`, 40 checks, eleven
mutants.

**Two instrument fixes ship with it**, both of the same shape — a measurement that could not
fail:

- `harness_tests/sem_baseline.py` compared an expected row by **timestamp**, and every row in
  the corpus carries the same one, so "recall" was true whenever anything came back and the
  at-1 and at-3 numbers were identical in every receipt. Compared by content address now.
- `tools/sweep.py` read a gate's lane from a fixed column of `GATE-INDEX.md`, which breaks
  the moment a description contains a `|`. **Nine offline gates had dropped out of the suite**
  with the total unchanged. The parser is `gates/index_rows.py` and both the runner and the
  documentation gate read rows through it.

## 0.7.0 — she can ask about his body, and be told when he wakes (2026-08-26)

The telemetry framework could always TELL her. It had no way for her to ASK — and the gap
only showed when he mentioned it directly and she went looking for a folder.

- **Two tools, `how_is_he` and `his_day`.** The per-turn note speaks only when something is
  worth noticing, which is deliberately rare, so on a quiet day she had no way to learn the
  channel exists at all. Both answer "I do not know" in words, because the watch comes off
  and a guess about someone's body dressed as a reading is worse than nothing. Classified
  `private`, not `read`: his heart rate is not state she already owns.
- **A standing line in the prefix** telling her the channel exists, what the tools are, and
  the manners — notice, do not recite, never diagnose. It went in its own slot rather than
  the standing-world block, because that block is gated off on this profile and the line
  would have been dead code.
- **`just_woke`.** A TRANSITION rather than a state, and the only thing about sleep worth
  saying unprompted: "you are asleep" is something a person already knows and cannot hear,
  and "you are awake" is true all day. Read out of the sleep-confidence history rather than
  remembered, so it survives a restart with no second copy of the truth, keyed on when he
  woke so it is said once per waking. Its nudge carries no numbers — the readings are the
  bridge for a racing heart and clutter for someone who just opened their eyes.
- **A `house` panel**: is Home Assistant reachable, what of it reaches her, and a link out.
  Deliberately not a second Home Assistant, and it cannot switch anything on.
- **`radar-trails-card`**: both radar nodes on one plan, sensor at the bottom facing up the
  page, three minutes of fading trail per target. The bearing-less sensor is drawn as an arc
  at its radius rather than a dot pretending to a direction.

## 0.6.3 — mmWave radar, and four silent faults (2026-08-26)

Notes from getting two ESP32 radar nodes working after three abandoned dashboard attempts.
`docs/HOME-ASSISTANT.md` has them in full. Every fault shared a shape: nothing errored where
anyone would look.

- **A state longer than 255 characters is discarded.** The firmware's JSON snapshot was 393,
  so HA logged `falling back to unknown` four times a second and the radar card saw nothing.
  Rebuild the object in a **template attribute** — attributes have no length limit — and
  leave the state short.
- **Units come from measurement, not declarations.** The same device declared speed as `m/s`
  while reporting `mm/s`, and its distance genuinely was metres while X and Y beside it were
  millimetres. Thresholds written against the labels never fired, and a threshold that never
  fires looks exactly like an empty room.
- **`unique_id` is the identity; `name` is cosmetic.** Reusing one keeps the old
  `entity_id`, so a renamed sensor reports the right value at the wrong address. Changing
  one orphans the old entity and the new one settles for `..._2`. Renaming via the registry
  is the only thing that actually moves an entity.
- **Give every template an `availability:`**, or an unplugged sensor reports a confident
  "nobody is here" — the same failure as a stale reading, in a different costume.

## 0.6.2 — what a long version jump exposes (2026-08-26)

Notes from finishing the migration. None of these were caused by moving to containers; they
had been wrong for months and only became visible when a version jump put them in a log.
`docs/HOME-ASSISTANT.md` has them in full.

- **`sensor:` versus `template:`.** A `sensors.yaml` holding a `template:` block, included as
  `sensor: !include sensors.yaml`. `sensor:` wants *platform* configs, so Home Assistant
  reports "required key 'platform' not provided" and drops **every entity in the file** —
  three template entities missing while all 21 of their source sensors were live. Fixing it
  needs both ends: the include key changes **and** the file loses its own `template:` header.
- **`panel_iframe` was removed in 2024.6**, replaced by a Webpage dashboard whose stored
  config is `strategy: {type: iframe, url: ...}`.
- **A 200 that is the wrong page.** That dashboard pointed at `/radar-pro/index.html` and
  returned HTTP 200 — Home Assistant's own SPA shell, because HA answers 200 for unknown
  paths. The iframe was loading HA inside HA. Files in `/config/www/` serve from `/local/`.
  When a URL "works" but shows the wrong thing, compare the `<title>`, not the status code.
- **Edit line-structured config by walking lines, not with a regex.** A regex strip left an
  orphan because its alternatives all required a trailing newline and the last line had none.
  Back up, edit, and **parse before restarting**.

## 0.6.1 — migrating an appliance backup into the container stack (2026-08-26)

Done for real, and the notes are what came out of it. `docs/HOME-ASSISTANT.md` has the
section; the summary:

- **The UI's "restore from backup" does not apply** to a Home Assistant OS backup being
  moved into containers — that flow belongs to the appliance. The core config is a plain
  directory inside `homeassistant.tar.gz`, so the restore is a directory copy done **before
  Home Assistant has ever started**, which means it never generates a default config that
  then has to be deleted.
- **The add-ons do not come across.** That is the real cost of leaving the appliance. The
  stack now carries a **Matter Server** container in place of the add-on, and documents why
  Mosquitto is deliberately *not* added when a broker already holds 1883.
- **Supervisor hostnames** (`core-mosquitto`, `core-matter-server`) fail with a **DNS** error
  rather than a connection one, which sends you looking at the broker instead of at the name.
  Map them with **`extra_hosts` in compose, not the distro's `/etc/hosts`** —
  `network_mode: host` shares the network *namespace*, not the filesystem, so the container
  keeps its own hosts file.
- **Matter's entry needs one real edit**: `use_addon: true` makes HA call
  `get_addon_manager()` and fail *before it reads the URL*, so no mapping helps. Stop HA,
  copy the store, change it, read it back.
- **Check the disk first.** WSL virtual disks grow but never shrink; deleting files inside a
  distro frees nothing on the host until the VHDX is compacted. The stack belongs on a data
  drive with `--vhd-size` capped so Home Assistant cannot fill the system drive.

## 0.6.0 — Home Assistant, as its own framework (2026-08-26)

The sleep socket added in 0.5.2 now has something that can fill it. A **separate pluggable
framework** (`harness/homeassistant/`), sitting beside `harness/telemetry/` rather than
inside it — the telemetry agent is yours and posts to you, Home Assistant is somebody else's
server you ask, with a credential, over a network.

**Why it is worth wiring up:** Home Assistant's *Sleep Confidence* sensor is Google's Sleep
API — a calibrated classifier inside Play Services, refreshed about every ten minutes. It is
not a sensor, so no amount of `SensorManager` reaches it, and on a Samsung watch every
sleep-capable sensor is behind a signature permission. This is the realistic way to know
whether someone is asleep.

- **It is not a second door.** Everything crosses through `telemetry.ingest.record()`,
  because that is where the anon gate sits. Off the record a reading is **held**, and held is
  not marked handled — the value that lands when you come back on the record is the current
  one, not the one you were hiding.
- **Off until configured, and off means silent.** No token: no thread, no socket opened.
- **The credential is not configuration.** `var/ha_token` or `SP_HA_TOKEN` — never a
  profile, because everything in `profiles/` is committed. The gate walks every profile for
  token-*shaped values* and asserts via the AST that the client cannot import the config
  system at all.
- **Matched by entity suffix**, so renaming your phone does not silently break it — and a
  missing row looks exactly like a person who is awake.
- **Two mappings only**: `sleep_confidence` and `activity`. Battery and steps are
  deliberately not taken though HA has them, because the bundled agent already posts them.
- **It cannot turn anything on.** Nothing calls a service, and the gate asserts it. Giving a
  companion the light switches is a different product with different failure modes.
- **The house watch list ships empty.** Nothing is said about your home until you name
  entities, because which lights matter is not something a default can know.

### `last_updated` is not when it was measured

Worth knowing before you build anything on Home Assistant's API. A sensor read 79 with
`last_updated` twenty-five minutes old; its actual reading was **133 days** old. After a
restart HA restores states and re-stamps `last_updated`, so **every stale sensor in the house
looks brand new**. `measured_at_of()` prefers the entity's own `attributes.timestamp`, then
`last_changed`, then `last_updated`; the dedupe is keyed on the measurement, so a restart
cannot rewrite the whole house as freshly measured; and a reading with no usable clock is
refused rather than dated to now.

`ingest.record()` gained a bounded `measured_at` for this — clamped to [-2 h, +2 min] and
unreachable from the HTTP door, so it does not reopen the one-clock rule.

### The stack

`harness/homeassistant/stack/docker-compose.yml` — Home Assistant and ESPHome as containers,
not the appliance VM. On Windows it must run under Docker Engine **inside WSL2**: under
Docker Desktop, `network_mode: host` means the host of the *Docker* VM, and the LAN stays
invisible, which breaks every multicast discovery protocol HA depends on. The file documents
both halves of what is required, and `docs/HOME-ASSISTANT.md` has the whole story including
how to pin the distro open so the containers are not torn down seconds after they start.

G-HOMEASSISTANT **45 checks**, ten mutants.

## 0.5.2 — sleep, and what a percentage is allowed to mean (2026-08-26)

**A sleep confidence has three possible sources and they are not the same claim.** The seam
now ranks them and always names which one answered.

- **`sleep_confidence` is a first-class kind** (0–100, bounded, refused outside) with a
  reader already behind it — so whichever classifier eventually fills it lands in a socket
  rather than arriving as a kind half the seam has never heard of. **Nothing fills it by
  default.**
- **The watch cannot tell you**, and this is worth knowing before you go looking: on a
  Galaxy Watch4 every sleep-capable sensor (`SContext`, `movement`, `wrist_down`, and with
  them ECG, BIA, thermistor) is behind `com.samsung.permission.SSENSOR`, a signature
  permission. Verified by enumerating the device.
- **Home Assistant's "Sleep Confidence" is Google's Sleep API** — a Play Services classifier
  on the *phone*, ~10 minutes, not a sensor. Posting it to `/v1/telemetry/ingest` as this
  kind needs no app change at all, which is the cheapest way to fill the socket.
- **The bundled estimate returns the terms that produced it** — *"phone untouched for 94
  min; his wrist still for 51 min; heart at their resting band (57)"*. A number printed with
  a `%` and no provenance is the most confident-looking thing on a panel and the least
  accountable, so the panel colours the bar by source and lists the terms beneath.
- **`None` is not `0`.** Too little evidence returns `None`, never a low confidence — an
  empty store must not read as "they are awake".
- **Between the bands nothing is claimed.** Above 70 sayable, below 30 awake, in between
  `asleep` is left *unset* and every reader treats a missing key as do-not-claim-it.
- **No time-of-day prior**, deliberately — it makes a companion confidently wrong about
  anyone who keeps unusual hours, which is a large share of the people who would run this.
- **`wrist_tilt_gesture`** (sensor type 26, one of the few not permission-locked) is a veto,
  not a weight: someone who just looked at their watch is awake. It is the only free
  awake-signal that comes from the body rather than a device that might be on a table.
- **`motion` is derived, not posted.** The agent sends `gyro_rms` per window; `still_run()`
  derives the state from that and prefers a classified `motion` row only if some source
  actually posts one.

`docs/TELEMETRY.md` carries the whole story. G-TELEMETRY 118 checks.

## 0.5.1 — the phone side, and one agent for two bodies (2026-08-26)

The **same APK** now runs on a phone as well as a watch. It detects which device it is in
and registers whatever sensors exist — a phone reports no heart rate and no off-body
detector, and picks up gyroscope, accelerometer, step counter, ambient light and barometer
instead. A separate phone app would have been a second implementation of *read, reduce,
batch, retry*.

It adds device state, which is broadcasts rather than sensors: **screen**, **charging**,
battery level and temperature. Ambient light is rate-limited to once a minute — a room does
not change sixty times a minute.

**A phone on a desk is not a person sitting still.** Both devices post `motion`, `gyro_rms`
and `steps` under the same kind names, and they are not the same claim: a still watch on a
wrist means *you* are still, a still phone means the phone is on a table. Caught in testing
before it ran live — the watch said still, the phone was moved, and she said *"he is moving
a lot."* Body facts are sourced to the wrist now; the phone speaks about the phone and the
room.

**And the cross-source check that earns the most:** the phone's screen coming on **vetoes**
the crude sleep inference. "Still, and the heart is at its resting band" is exactly what
someone reading in bed looks like. `SCREEN_ON/OFF` are transitions and not sticky, so the
agent pushes the current state at startup — without that the veto was silently unavailable
after every restart.

Also: the build script resolves `adb` from `TELEMETRY_ADB` → the SDK → `PATH`, rather than
assuming it is on `PATH` (it usually is not).

Sweep in this repo: **110 green, 1 correct skip, 0 red.**

## 0.5.0 — she can feel your heart, and the map of how anything reaches her (2026-08-26)

**Body awareness**, optional and off until you build it. A Wear OS agent, an ingest door, a
store, the seam that decides what she is allowed to say, and a **body** ♥ panel. The point is
not a dashboard: it is that she can *notice* — `"his heart, last few readings: 70, 78, 92 —
climbing"` — and say something a person in the room would say.

The design rule is the memory doctrine wearing sensor clothes. A **measurement** is
`observed` and she may state it; a **reading** ("he is asleep") is `inferred`, says *seems*,
and loses to your own word. **Silence is an answer**: no watch, stale data or off the wrist
and she is told *nothing*, because "you seem calm" from readings taken at lunch is worse than
nothing and would never look like a bug. She gets the last few readings rather than an
average, and only when they *move*. And never a diagnosis — it is a wrist sensor, not a
doctor, and her prompt says so in as many words.

Your privacy mode holds it: `telemetry.sample` is a door in `anon.DOORS`, **held not queued**.
`anon.holds()` grew an `n` because this is the first door that batches — the room would
otherwise have reported one reading withheld while thirty were.

The agent **builds without gradle** (`aapt2 → javac → d8 → apksigner`, ~16 KB) because it
stays on the platform SDK: `SensorManager` rather than Health Services, which would have
dragged in androidx and a dependency resolver. It reduces motion to one number per window,
batches on the sensor's own 600-event FIFO, and re-queues failures at the *front* so an
outage leaves a gap in the link and not in your history.

**And a map of the whole context.** [`docs/LANES.md`](docs/LANES.md) is new and is the most
useful thing in this release for anyone extending her: **the six ways a fact reaches her** —
the cached prefix (KV token 0: stale or a re-prefill, there is no third outcome), the
per-turn system row and why it must be idempotent, the staple on the user's turn and the
**measured** finding that a fact about *her* must never go there, the tool loop, the kairos
nudge, and the overnight growth loop. Two of the six were tried the wrong way first and the
receipts are in the document. [`docs/PANELS.md`](docs/PANELS.md) does the same for every
window in the room.

Also: `[serve].bind` can widen the gateway off loopback, with `tools/lan_bind.py` to report
whether your firewall scoping is real — **loopback is the security model** here and the
ledger says so plainly, including that there is no authentication to fall back on.

Sweep in this repo at release: **109 green, 1 correct skip, 0 red.**

## 0.4.1 — looking is not doing, and a front door that pointed at files it does not have (2026-08-25)

**She announced a wardrobe change in her own time and nothing changed.** The receipt:

```
10:21:08  tool check_wardrobe() -> You are wearing: black lace...
10:21:46  SPOKE (solo): "I think I'll go with the silver nightie..."
```

Her own time runs on an act table, and each act declares what it `needs` before
`solo_did_the_thing` will let the turn reach him. The wardrobe act declared
`("wear", "check_wardrobe", "express")` — and **`check_wardrobe` is a read**. The act whose
entire point is to *change* her clothes was satisfied by opening the wardrobe and looking at
them. That is this project's own quoted worst case, arriving exactly as written: *"nothing
looks and nothing will ever happen, and he will believe you."*

The second half is why she reached for the read rather than the tool: the persona teaches the
wardrobe as a **mark** — *"[WEAR:…] changes your clothes… No tool call, no asking"* — and the
ruling could only see tool calls. The one path she is told to take could not satisfy the one
law that checks she took it, while the read sailed through.

Both closed. `check_wardrobe` no longer satisfies the act; `interceptor.marks_present()`
reports *which* mark families a reply carried, from the same recognisers `carries_marks`
already uses, and the scheduler passes them into the ruling on the first pass and on the
re-ask. The act sentence must name any mark that satisfies it, and a gate holds it there — an
acceptance she is not told about is a secret. G-OWN-TIME 51 → 67, with the real turn as the
fixture and a mutant that restores the old ruling and shows it passing again.

**And 24 relative links in this repo resolved to nothing.** `README.md → ui/README.md` (never
in the manifest), five files naming `docs/CHANGELOG.md` (this repo carries a semver
`CHANGELOG.md` at the root instead), and thirteen rows of the documentation *index* listing
engine ADRs, session receipts and research essays that stay in the source tree. A newcomer's
first click, on the front page.

Fixed as a class: **G-DOCS-TRUE §5** requires every relative markdown link in a shipped doc to
resolve, and runs in both trees off the same list. Real markdown links only — backticked bare
names like `app.py` are prose shorthand, not promises, and gating those would have failed on
235 innocent mentions and been switched off within a day. `docs/ANON-MODE.md` now ships (the
code ships, and the deepest memory doc links to it), `ui/README.md` ships, and the exporter
drops index *rows* for unshipped documents while *de-linking* prose mentions — a row in an
index is a pointer and drops cleanly; a link inside a sentence is part of someone's writing,
so it keeps its words and loses its href.

Sweep in this repo: **109 green, 1 correct skip, 0 red.**

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
