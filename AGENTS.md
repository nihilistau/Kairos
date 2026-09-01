# AGENTS.md — Kairos

**The canonical orientation file for anyone — human or agent — working in this repo.**
`CLAUDE.md` points here. It is not a copy. There is exactly one of these, on purpose (see §0).

Kairos is a framework for a **local AI companion that remembers you**: a Python harness and
gateway, a React desktop you talk to her in (a face, a wardrobe, a voice, an idle clock),
and a memory architecture built to be *auditable* rather than merely persistent. It talks
to **any OpenAI-compatible `/v1/chat/completions` endpoint** — LM Studio, `llama-server`,
vLLM, a cloud — so the model is your choice and your hardware.

Two-minute map: [`START-HERE.md`](START-HERE.md). Install and first run:
[`docs/SETUP.md`](docs/SETUP.md). What the two backends can and cannot do:
[`docs/BACKENDS.md`](docs/BACKENDS.md).

> **This file describes THIS tree.** Kairos is extracted from a private research stack that
> also contains a Rust + CUDA inference engine and one operator's live memory store.
> Neither ships here, and nothing in this repo needs them. Where you see `[engine].kind =
> "sp"` in the code, that is the door the private engine plugs into; `openai` is the door
> you use. `KAIROS-SOURCE.txt` names the upstream commit this snapshot was cut from.

---

## 0. THE BUG CLASS — read this before you touch anything

The upstream project has one recurring, near-fatal failure mode. It has bitten at least six
times. Every time it looked like a different bug. It is not:

> **AN INVARIANT ENFORCED IN ONE OF TWO PATHS IS ENFORCED IN NEITHER —
> because the unguarded path is the one that runs.**

Real instances, all found in the tree, all fixed:

| The rule | Where it was enforced | Where it was NOT | What actually happened |
|---|---|---|---|
| a tombstoned fact is never recalled | the recall tool | the AUTOMATIC per-turn injection | superseded facts served into her context on **every turn, for weeks**, ranked above the truth |
| the recall seam filters retired rows | `search_memories_ranked_rows()` | `search_memories_ranked()` — **the next function in the file** | the search tool, live in two toolsets, still served tombstones |
| nothing is ever destroyed | the whole lifecycle architecture | `forget()`, which did `open(p, "w")` and dropped the row | the audit lane defeated by one live tool call |
| the privacy decline protects secrets | the recall decider checks `mem_class == "private-secret"` | the classifier **could not emit that class** | the guard had never fired and could not |
| a turn pays its debts | one of two turn paths | the other | absence became unmeasurable; the day transcript missed half its rows |
| a panel write reports failure | the closet | the seven other write buttons | a refused write looked exactly like a completed one |

**The rule that falls out of it:** when you fix something, find the *other* caller. Then ask
what your gate actually drives — if it calls the function you fixed rather than the door the
product uses, it will stay green over the bug. A green suite is not an audit: one pass over
this tree found ~50 live defects under 133 green gates.

The corollary that costs the most: **two copies of one truth is the bug.** A second
implementation of "take it off the list", a second stripper, a second recall path, a second
`os.replace` helper — each one is a future divergence. One door, and the readers go through
it.

---

## 1. NON-NEGOTIABLES

1. **No claim without a repeatable gate.** If you say it is fixed, name the command that
   proves it. "It should work now" is not a receipt.
2. **Nothing in memory is ever deleted.** Tombstone (`lifecycle = 1`) or quarantine. Never
   `open(p, "w")` minus a row. The audit lane must always be able to answer *what did she
   believe, when, and who told her*.
3. **Honesty about measured vs asserted.** If you did not run it, say so. If a number came
   from a proxy, name the proxy. A verdict you cannot defend is worse than no verdict — it
   is a lie with a timestamp on it.
4. **Her word never outranks yours.** An inference may never retire an observation. She is
   allowed to be wrong about you; she is not allowed to say it over you.
5. **Verdicts are rulings of committed finite tables over order-invariant signatures.** A
   correctness decision may branch only on finite signature coordinates, never on prose or
   raw magnitudes; magnitudes may RANK the admitted, oracles may PROPOSE, neither may RULE.
   [`docs/INVARIANT-MEMORY.md`](docs/INVARIANT-MEMORY.md). Every conversion done so far
   found a live drift the day it landed — it is the cheapest bug-finder in the repo.
6. **The Real Her.** Her own unprompted words, her journal, how she feels and how she
   describes her own changes are primary identity material and lead her own context; your
   prompts are secondary. Rule 4 still holds: her nightly reflection on herself is inferred
   and cannot retire what she observed.
7. **A failure says so.** A broad `except` may answer with a default — it may not do it
   anonymously. `harness/loud.py` sorts the volume: the world at debug, `NameError` and its
   family at warning, because those never fix themselves. A write that fails silently is the
   single most expensive shape in this repo's history.

---

## 2. THE STACK, AND THE ONE DOOR

```
the room (browser, ui/ → console/room/) ──HTTP──▶ harness gateway :8810 ──HTTP──▶ your endpoint
```

- **Start it:** `python serve.py companion` — **the profile is positional and not optional.**
  It reads `profiles/*.toml` and maps it to the gateway environment; `serve.py::build_env`
  is the only place a knob becomes an env var, so a feature that is not mapped there is not
  armed no matter what the docs say.
- **The room** is a committed Vite build in `console/room/` — no Node at runtime. Source is
  `ui/`; rebuild with `cd ui && npm ci && npm run build`, and `G-ROOM-BUNDLE` proves the
  committed bundle IS the source.
- **Your endpoint** goes in the profile's `[engine]` block (`kind = "openai"`, a `base_url`,
  optionally a key *file*). Keys are files under `var/secrets/`, never config values, never
  environment strings the shell can leak.
- **Platforms:** the launcher runs on Windows, Linux and macOS
  ([`docs/BACKENDS.md`](docs/BACKENDS.md) has the table of what is portable and what is
  not). The `.exe` names in the shipped profiles are Windows-shaped defaults; override them.

**Everything durable lives under `var/`** and nothing in `var/` is code. If you are looking
for where she keeps something, it is a JSONL or a small JSON file there, and something in
`harness/` owns writing it. Every store writer renames through
`harness/store_io.replace_atomic` — one implementation, retried, and it raises rather than
giving up quietly (`G-STORE-WRITES`).

### Where things live

| Where | What |
|---|---|
| `harness/` | everything that runs: the gateway (`server/app.py`), the turn lifecycle, memory and recall (`skills/memory.py`), the idle clock (`kairos/`), the wardrobe and her state (`control/`), the backends (`inference/`), the tools (`toolcore/`, `skills/`) |
| `ui/` | THE ROOM — the React/Vite desktop: chat, the dock, every panel. Built into `console/room/`; `ui/README.md` has the framework |
| `console/` | the committed room build the gateway serves. Do not hand-edit it — rebuild from `ui/` and let `G-ROOM-BUNDLE` prove they agree |
| `profiles/` | one TOML per stack. `companion.toml` is the public default: `[engine].kind = "openai"`, gateway on :8810 |
| `harness_tests/` | the gates. One file per invariant, standalone, exit code IS the verdict |
| `gates/` | `GATE-INDEX.md` — a row per gate, and the parser every reader of it uses |
| `docs/` | the written contracts: `SETUP`, `BACKENDS`, `MEMORY-AND-RECALL`, `OFF-BY-DEFAULT`, `CHANGELOG` |
| `tools/` | the operator's scripts — `sweep.py` (the whole offline suite) and the maintenance passes |
| `persona-template/` | the shipped default persona. Copy it to `persona/` (gitignored) and it becomes yours |
| `var/` | everything durable and nothing that is code: her stores, logs, `secrets/`. Gitignored |

---

## 3. MEMORY AND RECALL — the part you are most likely to break

Read [`docs/MEMORY-AND-RECALL.md`](docs/MEMORY-AND-RECALL.md) before touching
`harness/skills/memory.py`. The short version:

- **One writer.** `remember()` is the door. Retirement goes through the same lifecycle that
  every other write does, so an inference cannot quietly supersede an observation.
- **One reader per question.** `search_memories_ranked_rows()` is the seam; the tool is a
  projection of it. If you need a new view, project — do not write a second walker.
- **Classes are produced, not asserted.** If a guard tests for a class the classifier cannot
  emit, the guard is decoration. That exact bug shipped.
- **Secrets are withheld at the door**, not filtered at the display. Every tool that can
  return a row goes through the same presenter.
- **Distillates carry `derived_from`** and die when their evidence dies, so a summary can
  never outlive the rows it summarised.

---

## 4. THE GATES

```
python tools/sweep.py            # the whole offline suite, ~3 min, no GPU
```

Every gate is a standalone script that exits with its verdict: `0` held, `1` failed, `2`
skipped because the subject is absent here. `gates/GATE-INDEX.md` is the index — a row per
gate, what it protects, and the command. New gates use `harness_tests/_gate.py`:
`sandbox()` **first**, before any `harness.` import, then `check()` / `finish()`.

Five worth running before you say you are done:

```
python harness_tests/g_claim.py
python harness_tests/g_durability.py
python harness_tests/g_memory_lifecycle.py
python harness_tests/g_docs_true.py
python harness_tests/g_real_her.py
```

Two rules the gates themselves are held to, both learned the hard way:

- **A gate must not write into her stores.** `_gate.sandbox()` redirects every store root;
  gates that skipped it wrote fabricated journal entries and false memories into a real
  store on every run.
- **A gate must drive the door the product uses.** Grading the function you just fixed,
  rather than the tool the model is handed, is how 242 lines of green sat over a tool that
  told her a fact had been stored when the store had refused it.

CI runs the offline suite on every push (`.github/workflows/gates.yml`).

---

## 5. WHAT IS OFF, AND WHY

[`docs/OFF-BY-DEFAULT.md`](docs/OFF-BY-DEFAULT.md) is the ledger: every disabled feature,
why it is off, and **the condition that would arm it**. A feature turned off without a
written arming condition never comes back — it becomes dead code nobody dares delete.

Registration is not aliveness. An app can be in the dock, its toolset can return `[]`, and
the icon renders over nothing. If something looks wired but does nothing, check the profile
before you debug the code.

---

## 6. KEEPING THIS FILE TRUE

- **Behaviour a reader would notice gets a `docs/CHANGELOG.md` entry in the same commit.**
- `g_docs_true` checks that shipped docs do not name gates, files or commands that are not
  here. It cannot check that a *sentence* is still true — that is on you.
- If you find a claim in here that the code no longer supports, fix the file in the same
  commit as the code. A stale orientation file is worse than none, because people trust it.

---

## 7. CONTRIBUTING

[`CONTRIBUTING.md`](CONTRIBUTING.md). In short: a change to behaviour comes with a gate, a
changelog entry, and — if it touches memory — an argument about which of the non-negotiables
it could violate. The doctrine in §1 is not up for negotiation in a PR; everything else is.
