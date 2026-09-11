# Changelog

## 0.8.33 — the one-door banner now proves what went through it (2026-09-12)

`serve.py` strips every inherited `SP_*` so the profile is the authority, and `SP_PASSTHROUGH`
is the documented way to keep one deliberately. It announced each requested name as
*"PASSTHROUGH (deliberate, **unmapped**, NOT from the profile)"* — **without checking whether
it was unmapped.**

The profile mapping runs *after* the passthrough loop and writes the same keys, so asking to
pass through a name the profile also maps announced success and then silently handed the
process the profile's value instead. Upstream this cost a whole diagnosis: `SP_MOE_TIMING=1`
was announced at three consecutive boots and arrived at the engine as `SP_MOE_TIMING=0`, so an
instrument read as armed and was dark, and the stale numbers still sitting in an append-only
log got quoted as fresh measurements.

The banner states the **request** now, and the receipt prints at the end of `build_env`, where
the answer is actually known:

    [serve] PASSTHROUGH held: SP_FOO='1' (unmapped by the profile)
    [serve] !! PASSTHROUGH OVERRIDDEN: SP_BAR='1' was requested and the profile mapped
            SP_BAR='0' — THE PROFILE WON. That name is not unmapped; set it in the
            profile instead.

If you have ever set `SP_PASSTHROUGH` for a knob the profile also owns, this is why it did
nothing. G-ONEDOOR 28/28.

Also in this cut: `serve.py` maps `SP_G4_ATTN_V2` from `[decode].attn_v2`. That knob selects a
prefill/decode attention kernel in the **upstream CUDA engine** and does nothing against an
OpenAI-compatible endpoint — it is here because a knob the source repo maps must be mapped in
the same one door, not because this tree can use it.

## 0.8.32 — the `exit=-11` in CI was a daemon thread nobody ever asked to stop (2026-09-11)

**If you have been seeing `exit=-11` from the offline suite, this is it, and it was never
your clone.** Since 0.8.26 these notes have carried an open question: a gate dying with
SIGSEGV, a different one each time, always after it printed a clean verdict, with
`PYTHONFAULTHANDLER=1` printing nothing. Timing and contention were both tried and both
returned clean negatives — the suite ran at `-j 1`, nothing else running, and a gate
segfaulted anyway.

### The mechanism

`PYTHONFAULTHANDLER` printing nothing was the clue rather than a dead end: faulthandler is
torn down during **interpreter finalization**, so a fault past that point has nobody left to
report it. Combined with "after the verdict" and "a different gate each time", that points at
shutdown rather than at any gate. An `atexit` probe over the suite — atexit runs *before*
daemon threads are killed, so it is the last moment the thread list means anything:

    gates that HAVE crashed        4 of 4 leave `sp-mint` alive at exit
    gates that have never crashed  4 of 5 leave no thread at all

`_mint_drain` has always had a `None` sentinel that makes it return, and **nothing ever sent
one**. So every process that minted an episode exited with that daemon thread still running,
and CPython killed it wherever it happened to be — which can be inside `urlopen`, or inside
`_save_all` **holding the registry lock, mid-write to the fact store.** The atomic
tmp+replace is what stood between that and a damaged registry. The crashing population is
"anything that writes memory"; which one dies is luck.

### The fix

`memory.mint_shutdown()` is registered with `atexit` the first time a worker starts — not at
import, so a process that never mints carries no hook. It sets a stop flag, sends the
sentinel, and joins with a bound.

The flag is read **before each item** rather than only as a sentinel, because `put(None)`
lands at the *back* of the queue: a shutdown behind a backlog previously had to mint every
pending episode before it could see the sentinel. Queued work is now abandoned deliberately —
those rows stay `unminted`, which `verify_registry()` already counts and prints, and a
recorded backlog is strictly better than being killed mid-write.

**What it does not fix, plainly:** a capture already inside `urlopen(timeout=120)` cannot be
interrupted from another thread, and hanging shutdown for two minutes to close that window
would be the worse bug. The contract is a bounded join and a loud line naming the backlog, so
if a crash ever follows again, that line says where it was.

**The honest limit:** a segfault in finalization is not something a test can assert. The
correlation is 4/4 and the mechanism is textbook, but the proof can only be CI going quiet —
and it did. **Four consecutive runs after the fix, 8 of 8 `bare` jobs green**, against the run
immediately before, where 2 of 2 `bare` jobs died with `exit=-11` on two different gates.
Every previous round had produced at least one. An intermittent fault can always be hiding at
a lower rate, but this is the first time the suite has been green end to end on that runner.

`G-MINT-SHUTDOWN` (17/17) grades the property that makes it impossible — a process that
minted reaches finalization with no worker alive — driven in a subprocess, because no run can
observe its own exit. Three mutants, each red by name.

Also noted: `mint_drain_blocking` is documented "gates and shutdown only" and has no callers
anywhere in the tree.

## 0.8.31 — the day boundary is its own module, and the README answers "will it run?" (2026-09-11)

### `harness/server/day.py`

Stage 4 of the app.py split. **Nineteen functions, 947 lines, byte-identical**, out of
`app.py` (5,263 → 4,284 lines) and into a module named after what they do. It is one seam: a
turn is appended to the day record, the record is read back as history by eight selectors,
and at the boundary it is consolidated and seeded into the next day.

Stage 3 had left `turn.py`'s `_settle_turn` reaching back into the gateway for
`_append_day_turn` and said so in writing rather than hiding it. That shim now points at the
module that owns the record.

If you have subclassed or imported these out of `harness.server.app`, **nothing breaks** —
app.py re-exports all nineteen, and `G-TURN-EPILOGUE` §10 asserts `app.X is day.X` so a
re-export cannot drift into a second copy.

**Worth knowing if you write gates against this tree:** four of ours went red, all one
class — a `monkeypatch` on `app.X` no longer reaching a call site that resolves `day.X`. The
patch still *succeeds*; it just reaches nobody. If you patch gateway internals in your own
tests, patch the module the call site lives in.

A fifth red was more interesting and is a general warning about source-scraping assertions.
One check took **the first** `def _append_day_turn(` in the concatenated package text — which,
once `turn.py` grew a `def _append_day_turn(*a, **k)` forwarder, could be the *shim*. It
would have gone on passing while grading the wrong function. Another sliced a text window
from one `def` to the next and swallowed the new re-export block, reading an **assignment as
a call**. Both ask `_src.body()` of the resolved object now. Assert over objects, not over
text windows whose neighbours can move.

### The README says what hardware this was measured on

New sections, because "can I run this?" and "how is this different?" were both fair questions
the front page did not answer:

- **Will it run on my card** — the reference machine is one **RTX 2060, 12 GB**, with the
  measured prefill/decode table (8 ms/tok prefill, 23.8 tok/s decode, 25.5 s cold prefill,
  ~1.0 s warm) and the MoE arithmetic that makes it possible: ~4B active of 26B, ~10.6 GB
  streaming from host. Stated as **sp-daemon numbers, not a promise about your endpoint** —
  throughput on LM Studio or `llama-server` is that server's business.
- **Where this sits, and what it is not** — a stance-by-stance comparison against chat
  front-ends and agent/memory frameworks (what memory *is*, what forgetting *means*, who said
  it, speaking first, what proves it), each with the cost of that stance. Plus what Kairos is
  explicitly not: a model server, a document-RAG framework, or multi-user.
- The optional Rust + CUDA engine is now **linked from the front page**
  ([`kairos-engine`](https://github.com/nihilistau/kairos-engine)) rather than only from
  `docs/BACKENDS.md`.

Also: the pre-flight block said "those four are OFFLINE" above a list of five.

## 0.8.30 — `coverage: 1.0` does not mean "findable" (2026-09-11)

Two changes to `harness/skills/semindex.py`. The second is the one to read.

### Appending a vector no longer re-reads the whole index

`load_cached()` was memoized on `(path, models, mtime_ns, size)`, and `mint()` appends a row
every time the agent remembers anything — so **every write invalidated the memo**, and the
next recall re-parsed the entire file to learn about one new line. On the store this was
developed against that is **264 ms for a 21.4 MB / 3,183-row index**, on a cost that grows
with the store and a store that only ever grows.

The index is append-only, which is what makes the shortcut sound. When the path and the
model set are unchanged, the file has grown, and the bytes ending the region already parsed
are still byte-identical, then only the tail is new — `load()` is a left-to-right fold, so
folding prefix-then-suffix gives the same index. Both paths share `_fold`, so the
model-precedence rule cannot drift between them. Anything else — a shrunken file, a changed
prefix, a different path or model set, a cold process — falls back to a full load.

**Cold 303.8 ms, one appended row 8.3 ms, unchanged 0.2 ms.** If you run a large index, this
is the change you will feel.

It also closed a pre-existing hole the old docstring had already worried about: two
consecutive writes can measure as **the same `st_mtime_ns` (delta 0 ns, observed)**, so a
same-size rewrite inside one tick was invisible and size in the key did not help — size was
what did not change. The tail anchor is verified on the cache-hit path now, which costs one
512-byte read and catches any whole-file rewrite.

Compaction was considered and declined: best-row-per-key measured **21.4 MB → 15.9 MB, 26%**,
because the rows it keeps are the biggest, and it would drop vectors from a space the local
backend can no longer regenerate. The re-parse was the real cost and this removes it without
dropping a row.

### `coverage()` now names the SPACE, because the space is the capability

The recall seam compares **same space only** — `query_embed()` returns its model tag
precisely so it can, since a cosine between two embedding spaces is noise with a confidence
interval. `coverage()` answered *"has a vector at all"*, which is a different question: a
fact indexed in `hash256-v1` while queries land in `aux-1024-v1` **cannot be matched by
meaning at all.** It is reachable by the lexical floor and nothing else — 0.12 recall@1
against 0.72 on the corpus that set the thresholds.

On the store this was developed against: 1,057 live facts, coverage **1.0**, and twenty of
them in the wrong space. Twenty facts semantically invisible, under a report that said
everything was fine.

`coverage()` returns `by_space`, `query_space` and `unmatchable` alongside the old fields,
and `verify_registry()` — which the memory panel prints verbatim — names the count, the
spaces, and `backfill_aux()` as the remedy. It says nothing when nothing is unfindable.

**This matters more in Kairos than upstream**, because with a CPU sidecar armed the aux space
is typically the only complete document space you have: anything minted while the sidecar was
down sits in the hash floor and stays there silently. Check it with
`verify_registry()`; fix it with `semindex.backfill_aux()`, which appends and destroys
nothing.

`query_space` is the **armed** space (`aux_enabled()`, no I/O), not a promise about the next
query — if the sidecar is down, `query_embed()` drops to the hash floor and the number
inverts. That is the standing configuration, which is what a coverage report is for; the
live answer costs a round-trip and does not belong on a 15-second poll.

`_registry_health()`'s cache also gained the semindex's stamp. It memoized on the registry's
stat alone while now reporting a number computed from a different file, so a backfill — which
writes the index and never the registry — would have been invisible to the panel until the
next time anything was remembered.

### And the gate ships

`G-SEM-INCREMENTAL` (15/15) is new and **now included in the export**. It was being dropped
by an exclusion glob, `harness_tests/g_sem_*.py`, that reads "the SEM scoreboard over a
private corpus" — true of the thirteen gates that existed when it was written, and not a
property of the name. Kairos ships `semindex.py`, so a semindex gate that needs no corpus
grades code this tree actually runs. The thirteen are named individually now.

## 0.8.29 — the sweep no longer loses a crashing gate's output (2026-09-11)

`tools/sweep.py` runs each gate with `-u`. Captured stdout is block-buffered, so a gate
killed by a signal lost everything it printed and the report showed only the logging lines
that happen to go to stderr — no verdict, no location, and no way to tell whether the gate
had finished its work and died on the way out or fallen over in the middle. Those are
different bugs and the tool could not distinguish them.

Context, for anyone seeing an `exit=-11` in their own CI: `PYTHONFAULTHANDLER=1` printed
nothing here, which is itself a clue — faulthandler is torn down during interpreter
finalization, so a fault after that point prints no stack. What the surviving output does
show is that the crashing gates all stop on the same line, immediately after the turn
epilogue, and that every failure has been in the bare-install job and none in the full one.

The `-j` comment added in 0.8.26 has also been rewritten: it argued a contention theory that
the serial run disproved, and it guessed at the runner's core count (it is four). The change
itself stands — parallelism should come from the machine — but the reasoning it shipped with
did not.

## 0.8.28 — the serial experiment ended, and CI dumps a stack now (2026-09-11)

`-j 1` was an experiment and it returned a clean negative: serial, with nothing else
running, still segfaulted (`g_pk2_sse_v2_offline`, `exit=-11`, 83 s). Contention is not the
cause, so `-j` is back to the derived default and the suite is fast again. The diagnostic
echo also settled a number worth knowing: a hosted runner reports **`cpu_count = 4`**.

`PYTHONFAULTHANDLER=1` is now set on the `offline` job, so an interpreter-level crash prints
a Python stack instead of only a signal number. It costs nothing when nothing crashes, and
it is set at job level because the crash has already moved between gates.

**If you run this suite in CI and see a gate die with `exit=-11`, that env var is how you
find out where.** The remaining evidence here points at a code path taken only when an
optional extra is absent: every failure so far has been in the bare-install job and none in
the full one.

## 0.8.27 — CI runs the sweep serially, as a diagnostic (2026-09-11)

The `offline` jobs now run `tools/sweep.py -j 1` and print `os.cpu_count()` first. **This is
a deliberate experiment, not a settled setting**, and the suite will be slower while it runs
(2.2× here, for the same verdict).

Why: one job per run has been failing with a different gate each time — twice with a
SIGSEGV — while every one of those gates passes alone. Capping `-j` at
`min(6, cpu_count())` did not stop it, and that change was made without ever seeing what
`-j` resolved to on a runner. Serial removes parallelism entirely: several green runs say
contention and we pick a number; a red run says look elsewhere.

If you fork this and want the speed back, `-j` still takes whatever you give it.

## 0.8.26 — the sweep ran six gates on two cores (2026-09-11)

`tools/sweep.py` took `-j` as a flat **6** on every machine. A GitHub-hosted runner has
**two vCPUs**, so CI was running six gate subprocesses on two cores — and the sweep there
went red on a *different* gate on each of two consecutive attempts of the same job, once
with `exit=-11` (SIGSEGV), while 143 of 144 passed each time and every one of those gates
passes alone.

`-j` now defaults to `min(6, os.cpu_count())`. Capped rather than uncapped because several
gates drive real HTTP servers and temp stores; `-j` still overrides.

If you run this suite in CI, or on anything smaller than a workstation, this is the release
that stops it flaking under its own parallelism.

**Stated as a hypothesis:** both gates pass alone and neither was changed, so contention is
the best explanation — but only several green runs prove it.

## 0.8.25 — the last CI red was the host's uptime (2026-09-11)

`g_room_veto` was red in every CI job and green on a developer box, which is the shape of a
gate measuring the machine rather than the rule.

It fakes "he spoke N seconds ago" as `time.monotonic() - N`. **`monotonic()` is time since
boot**, so a runner three minutes old reports ~180 and the largest age the gate fakes (840 s)
lands at about −660. `body._seconds_since_he_spoke` treats `last_user_at <= 0.0` as "nothing
can say", so the faked turn read as no session at all and nothing vetoed.

The product guard is right and untouched: a real `last_user_at` is a monotonic reading taken
at an actual turn, always positive and never near the sentinel. Only a test subtracting from
the clock can manufacture a negative. The gate owns the clock now.

**If you write a gate that fakes a past event against `monotonic()`, it will do this to you
on a fresh machine.** The gate carries a short recipe for running any gate under a clock that
lies about uptime, so this class is reproducible on demand instead of on your CI's
scheduling. Measured with it: patch removed at 180 s uptime is the CI failure verbatim; patch
removed at 20,000 s passes, which is why nobody saw it locally.

## 0.8.24 — a bridged tool was Windows-only, and Pillow was undeclared (2026-09-11)

The three gates that skip in a bare install and had never executed anywhere until the `all`
CI job existed. Three causes, one of which was hiding another.

**`disk_free` could not run off Windows.** `drive: str = "D:"` with
`shutil.disk_usage(drive + "\\")` is the operator's drive letter and a backslash separator,
in a tool that ships. It now takes `os.path.abspath(os.sep)` — the filesystem root wherever
it runs — and still accepts a drive or any path. **This is also why `g_mcp_pool` looked
broken:** `disk_free` is its marker tool, so a tool throwing on every call made the session
pool report reconnects and multi-second calls. The pool was right; the tool was not.

**Pillow was an undeclared dependency in five unguarded places** (`skills/sight.py`,
`skills/sight_vl.py`, `senses/vision.py`, `senses/capture.py`, `games/render.py`). If you use
sight, the eye, or the games renderer you now want `pip install -e ".[media]"` — and before
this release you needed it without being told. Third instance of that rule this week after
numpy and tomllib, and the first the import census could not have caught: all five are inside
functions, so the modules imported fine and it bit at call time.

`G-IMPORTS` closes it with a static leg — every import at any depth, read with `ast`.
**Guarded imports stay exempt**, which is deliberate: `voice/ear.py` wraps `openvino` in a
`try:` and raises `EarUnavailable` with an install line, and that is the correct shape for an
optional native backend rather than something to convict.

One note for anyone bridging MCP servers: changing a tool's signature or docstring changes
its fingerprint, and the bridge will refuse it until you accept the change with
`tools/mcp_pin.py --accept <server> <tool>`. That is the rug-pull guard doing its job — the
description is prompt, and a description that changes under you is the attack. It caught this
change during development.

## 0.8.23 — the new floor gate named a path that only exists upstream (2026-09-11)

`G-IMPORTS`'s floor legs, added in 0.8.22, read the workflow and the public `pyproject.toml`
from `kairos-export/` — which is the **upstream staging directory**. It does not exist here;
in this tree the same two files are `pyproject.toml` and `.github/workflows/gates.yml` at the
root. The legs degraded quietly, but `G-SRC-TRAP` convicted the dangling names, which is
exactly its job: *"a gate is allowed to skip what is absent; it is not allowed to name
something that never existed."* 0.8.22 shipped with that red in it.

Both locations are now read, each behind its own `os.path.exists`, so each tree checks the
pair it actually has. They are written out as literal guarded reads rather than joined from
a list on purpose: `G-SRC-TRAP` matches `open(os.path.join(ROOT, "a", "b"))` and exempts the
same literals under an existence test, so building the path dynamically would have *evaded*
the scan instead of satisfying it.

## 0.8.22 — the declared Python floor was never true: 3.11 is the minimum (2026-09-11)

**BREAKING, in the sense that it stops being a lie: the minimum supported Python is now
3.11.** If you are on 3.10 this package never worked — `serve.py`, the one command the
README gives you, has imported `tomllib` (3.11+) since it learned to read a profile, so the
launcher died at import on the floor `requires-python` advertised.

It surfaced as three CI gates red on 3.10 and green on 3.12, with one traceback between
them. `g_backend_seam` was only involved because it imports `serve.py`.

Same class as the `media` extra in 0.8.19: *the packaging may not claim what the code cannot
keep*. The declaration moves to meet the code rather than the other way round, and the CI
matrix becomes `["3.11", "3.12"]`. Widening back to 3.10 is a real option and a separate
decision — it costs a `tomli` dependency on the core path, which is why it is not smuggled
in here. **If you need 3.10, say so and it can be done properly.**

### `G-IMPORTS` grows the two legs that would have caught it

The census walked `harness/` and stopped, so the launcher was covered by nothing.

* **root scripts are parsed, not imported** — `ast` reads their top-level imports without
  executing them, and only top-level `Import`/`ImportFrom` nodes count. An import inside a
  `try:` is a node of a `Try`, so the AST structure itself encodes "guarded, and allowed to
  be absent". Verified with a control: the same bad import, guarded, is not flagged.
* **CI must test the floor the packaging declares**, and it must be the lowest version in
  the matrix. The floor is the version nobody develops on, which is exactly why a claim can
  be false about it for months.

Run on Python 3.10 the gate now tells you `serve.py -> tomllib` instead of letting the
launcher crash.

### `g_asked` was flaky for a reason worth knowing

`row["ts"]` has one-second resolution, and the lane top-up orders by recency. Two rows
written back to back share a second and sort stably; if the clock ticks between them they
are a second apart and the order flips. Forced on an identical store and question, the two
scores simply trade rows. The affected gate's seeded timestamps are pinned now — but the
underlying fact is worth knowing if you rank on recency: **the store cannot distinguish two
writes inside one second.**

## 0.8.21 — two gates were measuring the machine, not the store (2026-09-11)

The Linux CI reds that were *not* the row-identity bug. Both are instrument defects, both
the same shape: **an assertion resting on an assumption about how fast the box is.** If you
clone this repo and run the suite, these are the two that would have gone red on you for no
fault of your tree.

**`g_store_writes`** starts three 1 ms pollers, rewrites the want list forty times and
demands `>= 100 reads` — the check that the readers were really racing the writer, because
"no reader saw it torn" is also what a gate that never scheduled a reader would report. Good
intent, fixed count: forty writes take long enough on Windows, and on Linux the loop
finishes in ~20 ms and the readers managed 54. The writer now runs **until both conditions
hold** — the original forty rewrites *and* enough reads to mean something — with a
wall-clock cap so an unscheduled reader fails the leg instead of hanging it. It is a
stronger test for it: the torn-write mutant now fails with 389 rewrites against 202 reads,
where the old shape gave 40 against 54.

**`g_tool_manifest`** convicted the five music rows as documentation for tools that do not
exist. They exist — `music.music_tools()` declines to offer them unless a music library is
actually on disk, which a CI runner has not got. `arms="SP_MUSIC"` would have been the
tempting wrong fix: the excuse fires when a knob is not `"1"`, and **`SP_MUSIC` defaults
on**, so an unset knob means the deck is armed and the *library* is missing — the row would
have been excused for a reason that is not the true one. The gate asks the **provider**
instead, and derives the tool names from it rather than keeping a copy. A second leg keeps
the excuse narrow: whatever the provider does offer must still be documented, and a row for
a genuinely deleted tool is still caught.

## 0.8.20 — a row's name was a millisecond, and tombstones landed on the wrong rows (2026-09-11)

**Upgrade if you write memories faster than one per millisecond — which, on Linux, is
every batch write you have ever done.** This is a data-integrity fix on the one rule the
store exists to keep.

`remember()` minted the row's `name` as `ep_tool_{int(time.time() * 1000)}`. That is a
clock reading, not an identity, and the framework keys on it everywhere: `commit_row`
tombstones the rows a supersession retired **by name**, `memory/__init__` builds
`{row["name"]: row}` lookups in two places (a collision silently drops a row), and the
surprisal cache is keyed `(name, ts)`.

Replaying the confluence corpus through the real writer:

| | rows | wall | distinct names | collisions |
|---|---|---|---|---|
| Windows | 20 | 0.14 s | **20** | 0 |
| Linux | 20 | 0.009 s | **9–13** | up to **four** rows sharing one name |

So a legitimate supersession tombstoned every row that happened to share the retired row's
millisecond:

    DEAD  "I like the hour just before sunrise"   killed by: "My favourite soup is pea and ham"
    DEAD  "I feel quietly content tonight"        killed by: "Sam is terrified of open water"

A fact about soup retiring a feeling about sunrise. **The supersede law never proposed any
of them** — it refused them correctly, and the tombstone was applied afterwards by a key the
law had never consulted. An invariant enforced in the decision and not in the application is
enforced nowhere.

It was invisible on Windows because writes there are ~15× slower, and it surfaced the first
time this repo's CI ran the suite on Linux at all.

### What to do about an existing store

Check it: if every row's `name` is distinct, nothing was ever mis-tombstoned and there is
nothing to repair. Collisions cluster in bursts — imports, consolidations, anything that
wrote several facts in a row without a human between them.

### The fix

`store.new_row_name()`, monotonic within the process and never re-issued. The format is
unchanged (`ep_tool_<integer>`, still sortable), so existing rows, episode directories and
`tools/memory/quarantine_rows.py --name …` all keep working. Cross-process collisions stay
out of scope deliberately: the registry lock is in-process, so two writing processes lose
rows for a larger reason — single-writer is the standing assumption.

And the seatbelt, because the name fix should not be the only defence for a key this
load-bearing: `commit_row` matches `(name, ts, text)` and **logs loudly when the number of
rows it tombstoned disagrees with the number the ruling named**.

`G-ROW-IDENTITY` (9/9) drives the real minter as fast as it will go — deliberately
speed-sensitive in the safe direction, since a fixed sleep between writes is exactly what
hid this — and separately **injects** a name collision to prove the tombstone still finds
the right row.

`g_confluence` is now 38/38 on Linux across five consecutive runs, where it had been 23–28/38
and nondeterministic.

## 0.8.19 — CI runs the gate suite, which it had never done (2026-09-11)

**This repo's GitHub Actions has been red on every push since the workflow landed on
2026-09-01, and the offline suite has never run in it once.** The job dies at step 5 of 8,
`every module imports`, about twenty seconds in — two steps before `tools/sweep.py`. The
badge said "broken"; what it meant was "never started".

Eleven of 163 modules fail to import on a core install: ten want `numpy`, one wants
`fastmcp`.

### numpy was an undeclared dependency

`harness/senses/{capture,gguf,vision}`, `harness/sidecar/{archive,rerank,tools}` and
`harness/voice/{dsp,ear,native,service}` import numpy at module level, unguarded, and
nothing in `pyproject.toml` said so. **If you run the voice, the eye or the sidecar
archive, you now want `pip install -e ".[media]"`** — and before this release you needed it
without being told.

It is the same defect as the `mcp` extra, whose own comment in that file states the rule:
*"an undeclared dependency is a claim the packaging cannot keep."* That audit fixed the
instance it found and did not ask the packaging what else it was not saying. There were ten
more.

### The check asserted more than the packaging promised

It required every module to import, against an install that deliberately had almost nothing
in it — so it could only ever be red. What ships now:

* a module failing on a **declared-optional** dependency is fine when that extra is absent,
  and still required to import when it is present
* a module failing on anything else is a defect, **including a `ModuleNotFoundError` for a
  distribution nothing declares**
* the **core** never gets that exemption — zero third-party dependencies is what the README
  promises you, so `skills/`, `model/`, `control/`, `kairos/`, `server/`, `tools/`,
  `toolcore/` and `personality/` must import with nothing installed at all

The optional set is read from `pyproject.toml`, not kept in the gate. A list in a gate is
complete the day it is written, which is precisely how numpy survived.

### Nine gates were red for an absent dependency, not a broken rule

With the census bypassed the sweep here was **135 green / 4 skip / 9 RED**, and every red
was a missing extra. They skip or omit only the affected legs now. The distinction that
mattered: `g_secret` gets **42 checks** in before it reaches the sidecar and `g_marks_leak`
**125** — skipping either wholesale to buy a green would take the **privacy gate** off the
board in the environment you actually run.

### Two installs, because there are two claims

The `offline` job is now a matrix of `deps: [bare, all]` across Python 3.10 and 3.12. **bare**
proves the zero-dependency core promise; **all** proves everything else, and is the only
place a module importing an *undeclared* package can be caught — with nothing installed, its
absence looks identical to an optional one's.

`G-IMPORTS` is a gate you can run (`python harness_tests/g_imports.py`), not twenty lines of
YAML nobody could run until a push.

Sweeps after: **bare 170 green / 9 skip / 1 red**, **full 176 green / 3 skip / 1 red** — and
the one red is excluded from this export.

## 0.8.18 — recall no longer re-reads the whole store once per candidate (2026-09-11)

**If your fact store has grown, this is the release you want.** Every recall re-read and
re-parsed the entire registry between 145 and 479 times. Measured on a 1,561-row store that
is **2.1–7.1 seconds of pure Python per question**, on the automatic per-turn injection path —
the one that runs whether or not she chose to remember anything. It is quadratic in the number
of rows, and the founding rule guarantees the number of rows only goes up:

    rows        full re-parses per recall        one recall
     250                             ~470            0.97 s
   1,561                     145–479 (by query)   2.1–7.1 s
   2,500                           ~3,900           56.7 s

Not a cold-cache artefact: asking the identical question again cost the same.

`rank._idf_table()` and `rank._person_model()` used `len(store._load())` as their
cache-validity key — a full read and parse of the whole file, performed in order to decide
whether a parse was still needed. `_evidence()` calls the first once per candidate row and
`_surprisal_of()` called the second once per candidate row, so the parse count scaled with
candidates × rows.

### The fix is the key, not a faster parser

`store.registry_stamp()` → `(path, mtime_ns, size)`, which is the key `semindex.load_cached()`
already used one module over. One rule, not two. `_load` memoises its parse on that stamp,
`_save_all` invalidates it under the lock that already made the write safe, and both caches in
`rank.py` key on the stamp instead of on a row count.

The stamp is also **more correct** than the count it replaces. A relabel, a `core` pin, or a
reinforcement that bumps `mentions` and `last_seen` changes no row count — so both caches were
being served stale after every one of those, and the person model behind `_surprisal_of` is
built from exactly those fields. Two different registries with equal row counts collided
outright.

After: **1–3 reads and 5–122 ms** on the same questions, and byte-identical output — 12
queries plus `list_memories`, `live_rows` and `search_memories`, diffed against the tree before
the change.

`_load` still hands every caller rows it owns, because `commit_row`, `forget` and the
reinforce branch all mutate what it returns before rewriting it. The memo therefore returns a
row-wise copy with list values copied: 1.99 ms against a 10.89 ms re-read, where
`copy.deepcopy` measured 16.58 ms — slower than the bug it would have been fixing.

### `G-RECALL-COST` — the gate counts calls, not milliseconds

Wall time is a property of your machine; the call count is what regressed and is the same
number anywhere. Its second leg runs the same query against 4× the rows and requires the count
not to move, which is the O(N) claim as a finite check. It runs in this repo's CI.

**The fourth mutant passed the first version of that gate, 8/8**, and that is worth recording
rather than quietly fixing: the leg meant to cover `_save_all`'s cache invalidation asserted
that an ordinary write is visible to the next read — which the stamp already guarantees — so it
held with the invalidation deleted and was testing nothing. It now constructs the one case the
stamp is blind to: a rewrite of exactly the same byte count with mtime restored, so
`(path, mtime_ns, size)` is unchanged and only the writer can know.

## 0.8.17 — remember() is a pipeline you can read in one screen (2026-09-02)

`remember()` is the door every fact enters memory by — the tool, the per-turn capture, the
consolidator, the reflector, `remember_about_self` and therefore every self-narrative row. It
was 360 lines of interleaved policy. It is **46 lines of code**:

    configured -> admit -> dedupe -> mint -> verdict -> row -> commit -> sidecar -> answer

Four more modules under `harness/skills/memory/`, and the package is finished at eleven:

- **`admission.py`** — what may enter, in what form, filed as what. The anon hold; the
  imperative coming off the wrapper (*"Remember my GPU is an RTX 2060"* is a fact wearing an
  imperative, and stored whole the verb becomes content); the AUTHOR picking the gate; the
  identity firewall. Every refusal is a **sentence she reads**, and the writer returns it
  verbatim — a store verb that fails quietly is how a companion ends up promising to remember
  what it cannot.
- **`dedupe.py`** — a repeat is not a duplicate, it is a second data point.
- **`supersede.py`** — what a new row retires and by what authority. An inference may never
  retire an observation; narrative accumulates.
- **`store.commit_row`** — the row append and its tombstones, in the module that owns the
  file. **The only row append in the tree**, and that is now checked rather than claimed.

**Nothing changed behaviourally, and here is how that was established rather than asserted:** a
19-scenario digest of every sentence `remember()` returns and every row it writes, captured
before the first line moved and diffed after each stage. Identical every time. Two of those
scenarios had to be fixed first because they were not exercising what they claimed — one
"supersede" case did not supersede and one "paraphrase" case did not reinforce. A golden file
whose golden-ness nobody checked is not a safety net.

### `G-REMEMBER-PIPELINE` — the order is the invariant

Every ordering in that pipeline is a bug if it reverses, and until now nothing enforced any of
them:

    admit before dedupe    a REFUSED fact must never reinforce a row
    dedupe before mint     a repeat must not pay for an episode it already has
    verdict before commit  the tombstones must exist before anything is put down
    commit before sidecar  the semantic index is DERIVED; an entry for a row that failed
                           to land points at nothing

So the order is asserted as byte offsets inside the function's own source, each phase must be
called exactly once, every refusal is driven through the door and required back word for word,
and the admission chain is proved not to write by driving it and finding the store untouched.
Eight mutants, each red by name. 28/28.

### And a test that had stopped measuring anything

`G-ADMISSION` exists because the registry once filled with ~375 rows of voice test corpus —
*"The kind nurse painted the tall building as the sun went down"* — grammatical, declarative,
and about nobody. It drove a real turn over HTTP and marked it `synthetic` so it would not
pollute the transcript. Then the synthetic-quarantine fix landed, capture began (correctly)
skipping synthetic turns, and **its "the impersonal sentence is refused" check began passing
because nothing was captured at all** — vacuously, over a firehose that could have been wide
open. It had been failing 1/5 for days without being noticed, because it was marked as a live
test and the offline suite skipped it.

A test whose subject is quarantined *for tests* is a test measuring the quarantine. It now
drives the capture function directly against a sandboxed registry, it is **offline** so the
suite runs it every time, and it has mutants in both directions: admit everything and it goes
red naming the corpus row it swallowed; refuse everything and it goes red on exactly the leg
that had gone vacuous.

    offline suite 140 green / 1 skip / 0 red, in this tree

## 0.8.16 — memory becomes a package, and its `__init__.py` is the one door (2026-09-02)

`harness/skills/memory.py` was 2273 lines. It is `harness/skills/memory/`, eight modules with
one door, and **no behaviour changed** — every moved block is byte-identical to the reviewed
one. If you import it, nothing changes for you: `from harness.skills.memory import remember`
and `import harness.skills.memory as M` resolve exactly as before, private names included.

**Why the shape.** The doctrine is *"one door, and the readers go through it"* (AGENTS.md §0).
Inside a single file that is a **convention** — it holds because everything is adjacent, and it
stops holding the moment somebody adds a second walker three hundred lines away. That is this
file's own history: `search_memories_ranked()` did not filter retired rows while
`search_memories_ranked_rows()`, *the next function in the file*, did, so the search tool
served tombstones from two toolsets. A package makes the door a module boundary.

    __init__.py  969   the DOORS and nothing else — remember, remember_about_self, forget,
                       recall, list_memories, provenance, search_memories, memory_stats
    rank.py      759   the recall seam, the evidence floor, the selection
    mint.py      263   the capture queue and its one worker
    health.py    161   registry hygiene: one computation, two projections
    present.py   110   what a row may SAY — the secret rule and the render that applies it
    store.py     101   the registry file and the read-modify-write lock over it
    words.py     100   the lexical floor, applied identically to both sides of a comparison
    authorship.py 87   who is speaking, and what they asked

**Two rules come with it, and they are the useful part if you are working in there.** The
façade re-exports; it does not implement twice. And you import the **package**, never a
sibling — reaching a sibling directly makes the second door the package exists to prevent.
The new `G-MEMORY-PACKAGE` holds both, from a census built out of the tree's own usage with the
AST rather than a name list kept in the gate.

**And one rule that cost more to learn than the split did:** *import the module, never the
name, when the name can be rebound.* A test that installs a mutant is rebinding a name, and a
by-name import **snapshots** — so if one caller binds the name and another reaches the module,
patching the owner reaches one and misses the other, and the mutant grades a subset while
printing a complete-looking pass. It happened here twice: once loudly, and once where a
lost-write gate went green **with every read-modify-write lock deleted**, because the sluggish
`_load` it installs to open the race was no longer the `_load` the doors called. Measured, then
fixed, then re-verified in both directions. `G-MEMORY-PACKAGE` now derives the set of
mutant-patched names from what the tests actually patch, so it constrains the next extraction
without anyone remembering to update a list.

**Three tests were found to be grading nothing on the way**, and only one was caused by the
split. Worth knowing, because each is a shape rather than an incident:

- One read `M.get_author()` behind `hasattr(M, "get_author")`. There is no `get_author` and
  never was — the reader is `current_author()` — so the guard was always False, the expression
  was always the literal `True`, and a check reading *"the lane was restored after her turn"*
  had proved nothing since the day it was written. **An optional-name guard makes a typo
  permanent and silent.**
- The lost-write one above, which the split caused and the split's own new test caught.
- One required the model to call `count_memories`, while the toolset it is handed is
  `[remember, remember_about_self, recall, list_memories, forget]`. Five tools given, a sixth
  demanded; asked *"how many facts do you have?"* she calls `list_memories`, which answers the
  question, and the test failed. That is §0's fourth row — *the guard tested for a class the
  producer could not emit* — living in a test instead of in the code, and it survived because
  it only runs against a live model. Its expectation is derived from the toolset now: write,
  read back through a tool **actually handed over**, and call nothing that was not.

    offline suite 138 green / 1 skip / 0 red, in this tree

## 0.8.15 — the gateway becomes four modules (2026-09-01)

`harness/server/app.py` was 6180 lines. It is 4976, and the three things that came out of it
are the three things it was hardest to reason about.

- **`server/turn.py` — the turn lifecycle.** `_settle_turn` is the one list of debts a
  finished turn owes: the latch released, facts captured from what you said, the day row
  written, her marks applied, the receipts flushed. It exists because that list had been
  re-implemented as trailing inline code with five bypasses, so an interrupted turn paid
  none of it. It is a module boundary now instead of a convention, and the gate asserts
  that as **identity** — one object, nine callers — plus the property those callers rely
  on: two owners, one payment.
- **`server/panels.py` — the room's read-only windows.** ~35 producers, each `() -> dict`
  and almost all documented NEVER RAISES, because a panel that throws takes the window with
  it. Which is exactly why a broken one is quiet, so the new `G-PANELS-SERVE` **calls** every
  one of them and treats `{ok: false}` as a failure, then asks the live gateway for every
  route `ui/src/api.js` names.
- **`server/state.py` — what the gateway knows right now.** The warm gate, the canonical
  per-session transcripts, the generate-now job, the last-turn clock. Reach it as `state.X`
  and never `from state import X`: `LAST_TURN_AT` is rebindable and an import would snapshot
  it. **None of it is locked**, which gathering it made legible rather than fixed — see
  AGENTS.md §4.

**Everything moved byte-identically**, asserted by the extractor: a moved function whose
text changed is one that has to be re-reviewed, and 1200 lines of re-review is where the
next twin gets born.

**The first commit moved no code at all.** 42 read sites across 39 gates opened app.py as a
FILE and asserted on its text — and when a function leaves a file, `.index()` fails loudly
but `X not in src` goes **green**, and an AST walk for functions matching a marker grades
nothing at all. So `harness_tests/_src.py` is now the one door for reading source: the
package for an absence or a count, `inspect.getsource` for an ordering, a file only for
things that really are one file. `G-SRC-TRAP` holds it, and also holds the cheaper rule
that caught two shipped reds this week: **a gate may not read a source path that does not
exist.**

Two bugs the split produced, and how each was caught: a module missing an import its
functions relied on (found by CALLING them, not reading them), and a second one on a path no
gate drives at all (found by a new static check that resolves every global name each gateway
module loads). Both are the same shape — moving a function strands whatever it used from the
old module's top-level imports.

## 0.8.14 — this tree gets its own orientation, a POSIX launcher, and CI (2026-09-01)

Everything here is about making the framework runnable by someone who is not its author.

- **`python serve.py <profile>` now runs on Linux and macOS.** It did not degrade off
  Windows — it crashed: `subprocess.CREATE_NO_WINDOW` does not exist on POSIX, so the first
  spawn raised `AttributeError`, and that command is the first line of the README. One
  platform seam now (`NO_WINDOW` for spawning, `kill_image` / `kill_by_cmdline` for
  stopping), and `G-BACKEND-SEAM` §10 holds it — including driving the constant with
  `os.name = "posix"` rather than only grepping for it. **Not yet exercised on real Linux
  hardware**; `docs/BACKENDS.md` says so plainly instead of a badge saying otherwise.
- **`AGENTS.md` describes THIS tree.** It used to be the private stack's file with names
  rewritten, which produced the sentence *"Kairos is the production rebuild of Kairos"* and
  then asked you for an RTX 2060, a Rust CUDA daemon on :3000, and a repo you do not have.
  The doctrine is the part worth publishing and all of it carries over — the bug class with
  its six real instances, the non-negotiables, the memory rules, the two rules the gates
  themselves are held to. The hardware and the private engine do not.
- **CI: `.github/workflows/gates.yml`.** Every module imports, the five gates AGENTS.md
  names, the whole offline suite, and the store rules — on ubuntu-latest, Python 3.10 and
  3.12, plus a Node job so the room-bundle gate actually runs instead of skipping.
  Running this suite for the first time found **two reds that had been sitting in the
  shipped tree**: a gate that constructs a JS file this tree deliberately excludes (red on
  a missing file, for a copy that cannot drift because it does not ship), and a docs gate
  whose requirement the new orientation file had not yet met. **The suite is green now —
  135 green, 1 skip, 0 red** — and from here a clone can tell.
- **`docs/BACKENDS.md`** answers the question adopters actually ask: what runs off Windows,
  and which presence features degrade on a foreign endpoint. Verified against the source,
  and it corrects the record in both directions — the turn epilogue is **shared** between
  the two backends (one `_settle_turn`), as are the off-the-record staple and the
  thought-channel stripper. What you lose is observability: named phase timing, typed SSE
  events, the warm gate.

## 0.8.13 — the doors above the fixes (2026-08-31)

An outside review, checked line by line against the source. Four findings were real, two
of them introduced by the previous two versions, and one was the opposite of what it said.

- **`overlay()` opened with `except OSError: return {}` on its `os.stat`.** `OSError`
  covers `PermissionError`, and `{}` means "you have edited nothing" — every hidden
  garment back on offer, every retired one back in her list. 0.8.10 added the careful
  three-way split and left the door to it standing open. Only `FileNotFoundError` answers
  `{}` now.
- **The wardrobe panel had eight write doors and 0.8.7 fixed one.** Put-it-on-her,
  dismiss, accept, make-it-now, make-everything and both ask boxes all awaited the
  server's answer and discarded it, so a refused write still looked like a completed one.
  One writer for all of them now, and a refused request keeps your words in the box.
- **The self-fact tool told her a fact had landed when the store had refused it.**
  `remember_self` called the writer, threw the writer's sentence away, and answered
  "noted about myself: …" either way. It returns what the store said now, and the gate
  calls the TOOL rather than the underlying function — which is why this survived.
- **The tree-wide swallow rule claimed more than it checked.** It matched a closed list of
  literal handler bodies while its sentence said "nothing fails without a name", so 134
  handlers answering with an assignment, a `continue` or `return <name>` were green under
  it. An `except Exception:` with no binding cannot report what it caught whatever it does
  next, so the binding is the whole rule now. Zero unbound handlers remain.
- A gate that recognised the logging helper only under two of its three import aliases was
  reporting audible handlers as silent ones; it no longer grades the spelling.

## 0.8.12 — nothing under harness/ fails without a name (2026-08-31)

The other half of 0.8.11, and a correction to its arithmetic.

- **Every remaining broad handler that answered with a bare default now says so** — 219
  sites, each carrying the enclosing function's name and its package as the lane. This is
  not extra noise: `loud.swallowed` SORTS it. The world stays at debug where nobody has to
  read it; `NameError`, `AttributeError`, `TypeError` and `ImportError` come out at
  warning, because those are the code being wrong, they never fix themselves, and they
  must not be indistinguishable from "nothing happened".
- **0.8.11's own numbers were wrong.** The census regex ended ``, and after a closing
  quote at end of line there is no word boundary — so `return ""`, `return {}` and
  `return []` never matched it. The real figures are **232 handlers over 71 files, ten of
  them writes**, not 192/67/9. Forty were invisible to the instrument written to find
  them, including one more write.
- **That tenth write was `memory.rescue_stray_tmp`**, whose docstring says *"Logged, never
  silent"*. What fails there is the quarantine of the one record of what a dying process
  was about to commit — and the next save opens that path `"w"` and overwrites it.
- The gate's rule is now the whole tree: nothing under `harness/` may answer with a bare
  default anonymously, `loud.py` must still sort our bugs from the world, and it must
  actually be adopted — a rule pointing at a helper nobody imports is not a rule.

Behaviour-neutral by construction: every handler still catches what it caught and answers
what it answered. It just says so first.

## 0.8.11 — 192 quiet failures, and nine of them wrote (2026-08-31)

The wardrobe audit, applied to the whole harness. 192 broad handlers answering with a bare
default across 67 files — classified by what the try-block actually DOES rather than
instrumented wholesale, because 192 edits of noise is how a real signal gets ignored.

- **Nine of them wrote**, which is the one class nothing downstream can detect: a write
  that failed and a write that worked are the same event to every reader. Eight are fixed
  and each says what it loses — the avatar seed marker (lost, and the next boot seeds the
  set again over a wardrobe that already has it), the backup's "never leave a .part
  behind" promise, the `SP_DUMP_PROMPT` diagnostic (a diagnostic that fails silently is
  worse than none), the presence day ledger, a decision row, the `by` stamp on a research
  receipt, her narrative snapshot, and the SEM law witness. The ninth is exempt with a
  written reason: an error goodbye to an SSE socket whose client has already gone.
- **Twelve of the reads were not ordinary either.** The author arm/reset pair that decides
  whether a stored fact is filed as hers or his was silent at both ends; the capture lane
  dropped facts without saying so; three optional toolsets could vanish from her turn with
  nothing explaining why she could no longer do something; and the "why she did not speak"
  ledger could fail to record, leaving a silence with no reason attached.
- `G-STORE-WRITES` grows the census that holds it: **no swallowed handler anywhere under
  `harness/` may contain a write**, and allow-list entries must carry a reason.
- One found by a gate, not by me: the backup cleanup's failure can land above the line
  that names the file it cleans up, so the old handler had been eating an
  UnboundLocalError — a cleanup that could never run looked like one that always did.

## 0.8.10 — twenty-two quiet failures in the wardrobe (2026-08-31)

An audit of every `except Exception: pass` in the wardrobe, after three days in which the
answer to "why did nothing happen" was always "nothing said".

- **Three of them decided something you can see.** `choose()` wrote her state through a
  swallow, so a refused write left her dressed in memory only — the chip said one thing
  and the next read said another. `current()` answered an unreadable state as "she has
  chosen nothing", and `choose()` read-modify-wrote over that, erasing the look and clip
  she had on. And `overlay()` answered an unreadable catalog as "you have edited
  nothing", which un-hides every garment you hid and puts every retired one back on
  offer. All three now follow the same three-way rule: **absent is a real state,
  unreadable is retried and then raised, corrupt is defaults said out loud.**
- **The rest are logged rather than silent**, and where a swallow decides something
  visible the warning names what YOU will see rather than which function failed — "she
  will be told she has no moments to put on your screen", "N of her garments will read as
  not owned", "she will be told she owns nothing like it", "anything generated now is
  anchored to nothing and will not be her". `praise()` was dropping your words verbatim
  while answering `{"ok": true}`; they are the one row in that store that cannot be
  reconstructed.
- `G-WARDROBE-WORDS` grows a swallow audit: the three are driven by making the write, the
  read and the overlay fail, plus a census — no `except Exception:` in `wardrobe.py` or
  `catalog.py` may answer with a bare default without binding the exception.

## 0.8.9 — a failed stamp is not a quiet one (2026-08-31)

- **Wearing something could silently fail to mark it as worn.** `note_worn` writes the
  `worn_at` stamp — the thing that takes a garment off the just-arrived shelf — and both
  halves of it were `except Exception: pass`. A failed write meant the item was worn and
  still read as NEW, with nothing anywhere saying why. It still does not raise (it is on
  the path every dressing takes, and the wearing has already happened by then), but the
  volume changes: the world at debug, programming errors at warning, and one plain
  warning that names the CONSEQUENCE rather than the function — *"it will still read as
  NEW until the next time it goes on"*. Self-healing: the stamp is retried on every wear.
- The two halves are split, because they fail for different reasons: the stamp is a
  read-modify-write over the want list, the wear log is an append, and sharing one
  handler meant a failed stamp also dropped the wearing that `favourites()` ranks over.

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
