---
type: reference
title: "ANON-MODE — the evening the room does not keep"
date: 2026-08-23
status: LIVE — the switch is in the dock; `harness/control/anon.py` is the truth, G-ANON is the proof
---

# Off the record

The operator's ask, 2026-08-23: *"an icon that activates anonymous mode that will still be her but
will not record any memory or logs etc until turned off or restarted."*

Both halves are load-bearing. **Still her** means she reads everything she has ever known,
recalls, uses her tools, changes mood, speaks in her own voice — a mode that made her
duller would be a different feature. **Records nothing** means nothing about the evening
reaches disk, and that is the claim `harness_tests/g_anon.py` exists to keep honest.

## How to use it

The dock, at the foot, above `shut down`: **👤 anonymous**. One click on, one click off, no
confirm. Turning it on is the direction that fails safe, and it is the one control here
that should be reachable in a hurry.

While it is on the room says so three times — the button reads **🕶 off the record**, a
violet chip appears in the taskbar with the elapsed time and the running tally, and a
violet rule is drawn around the whole room. That is deliberate over-signalling: the failure
mode of a private mode is forgetting which way it is set, and it is a failure in **both**
directions. Forgetting it is ON costs an evening of her memory. Forgetting it is OFF costs
the privacy you asked for.

Turning it off prints the receipt — *"held back 6 memories, 14 turns of the day transcript
and 2 journal notes — none of it written"*. That tally is the only copy that will ever
exist. It is process memory, it is cleared by the same call that shows it, and nothing
about it is written down.

## It is volatile, and that is the design

The switch lives in a module-level variable. It is never written to a file, never put in
the environment, and `harness/control/anon.py` contains no `open()`, no path and no env
var of its own — G-ANON §2 asserts all of that, and diffs the whole sandbox to prove that
turning it on writes nothing anywhere.

So **a restart ends it**, exactly as he asked, and a cold stack always comes up recording.
The alternative — persisting it — has an obvious failure: a month of her memory swallowed
on the strength of a click nobody remembers making, which is the shape
`disarmed-features-outlive-their-bug` describes and this repo has been bitten by before.

## The doors

Every id below is declared in `anon.DOORS` and guarded **at the write, not at the caller**.
`memory.remember()` is guarded once, at the top, which guards all thirty of its callers
including the ones written next year. Guarding callers is how you get `_capture_after_turn`
covered and `self_stance.extract` not, and a mode that claims nothing was recorded over an
evening sitting in the registry is worse than no mode at all.

| door | what it holds | where |
|---|---|---|
| `memory.row` | every fact, hers and his — and with it the episode mint and the semantic index that hang off the write | `skills/memory::remember` |
| `transcript.day` | the day's turns, verbatim — and therefore tomorrow's consolidation of tonight | `server/app.py::_append_day_turn` |
| `journal.own` | her own-time notes | `skills/narrative.py::note_own` |
| `journal.night` | the composed nightly paragraph — held **before** the model call, not after | `skills/narrative.py::compose_and_write` |
| `speech.log` | what she said and what she almost said, with the text | `kairos/speechlog.py::record` |
| `persona.state` | her dials, into a **shadow** rather than into persona.md — see below | `personality/persona_file.py::write_state` |
| `wardrobe.want` | a new want; **not** dismissing or fulfilling an existing one | `control/wardrobe.py::request` |
| `senses.ambient` | the hourly eye — held before the **shutter**, not before the append | `senses/ambient.py::observe_once` |
| `lookup.receipt` | the query and 800 chars of what came back, hers and his | `skills/looking.py::_write` |
| `spine.receipt` | the turn's decisions, into a durable training corpus | `control/spine.py::persist_receipts` |
| `decisions.card` | a new card; **not** his answer to an old one | `skills/decisions.py::ask` |
| `log.speech` | her actual words in the three `kairos` log lines — **redacted, not silenced**, so the turn is still provable from `var/gateway.log` | `kairos/scheduler.py` via `anon.say()` |

### ...and the doors that face outward (2026-08-24, his question)

*"Does anon mode leak anywhere? eg via voice either local or sent to providers such as the
xai api? Ensure all surfaces are covered."*

It did, and this was the worse half. Everything above stops the evening reaching **his
disk**, which he can audit and delete. These stop it leaving **the machine**, which he
cannot. `voice.method` is `xai` on his profile, so every sentence she spoke off the record
was posted to `api.x.ai` in full.

| door | what it holds | where |
|---|---|---|
| `net.voice` | a sentence sent to a **remote** voice. A LOCAL voice still speaks — silencing her would be the mode disabling the room. It **raises** rather than returning silence, so "she went quiet" is never mistaken for "she had nothing to say" | `voice/tts.py::synthesize` |
| `voice.cache` | the wav on disk. Keyed by a text hash, but the file *is* her voice saying the private thing, and the cache is trimmed by size, not age. A cache **read** is deliberately left alone: a hit means she said it before, on the record | `voice/tts.py::synthesize` |
| `net.search` | the query. A search string is the most legible summary of a private conversation there is, and it goes to a third party in plain text | `skills/search.py::search_web` |
| `net.research` | the question and the context it carries. It has its **own** client, so guarding `skills/xai.py` would have covered images and video and left this open | `skills/research.py::research` |
| `net.provider` | the one door out of `skills/xai.py` — images, video, uploads, and the remote voice all reach `api.x.ai` through `_post`, so one guard covers every one of them including the ones added next year | `skills/xai.py::_post`, `::upload_image` |

**The gate drives these against a tripwire**, not a grep: `urllib.request.urlopen` is
replaced with a function that records the attempt and fails the gate. A guard that let the
call through and merely discarded the answer would pass a "did it return nothing" test and
fail the actual claim. Three of the five mutants fire that tripwire.

**Known residual, named rather than papered over:** external **MCP servers**
(`mcp_servers.json`) are not held. A tool call to one carries whatever she passes it. Left
open because the set is operator-configured and may be entirely local; if a remote one is
added, it becomes a door.

**Adding a door**: add the row to `anon.DOORS`, guard the write, add the case to G-ANON.
The gate fails on an id that is declared and never held, so a row added without its guard
convicts itself instead of sitting there decorative.

### ...and the third door is neither of those: HER PROMPT (2026-08-25, the operator's report)

*"she remembers what happened on exit."*

**THE CONTRACT, IN ONE SENTENCE (2026-08-29): off the record means _not written down and
not sent off the machine_ — it does not mean gone from her head, and it cannot: the
evening stays in her live context until the switch goes off and the room stops re-sending
it (below), or the stack restarts.** External MCP servers are the one surface neither
table covers — a bridged tool call is its own egress, named here so nobody reads the
switch as covering it.

Both tables above answer the question *what got WRITTEN* — the fourteen write doors stop
the evening reaching his disk (notes.add and conversation.store joined the declared table
2026-08-29; they were guarded from 08-28 but the receipt named them by id), the five
egress doors stop it leaving the machine, and both were doing their job. A note typed BY
HIS HANDS on the board is the one deliberate exception on the write side — his act, not
the evening's content — while her tool path to the same board holds. The server never persisted a single OTR turn. She carried the private hour
anyway — after the switch went off, for as long as the room's scrollback lasted — because
**the ROOM kept re-sending those turns as prompt history**. Nothing was recorded and nothing leaked; the conversation simply stayed
in her context, which is the one place a two-door structure built around *disk* and *wire* had
no row for.

Fixed in `ui/src/Chat.jsx`: a turn is **marked at send time** with whether the switch was on
(one cheap `GET /v1/anon` per send; **a failed read errs to privacy** — it marks the turn
private rather than assuming it is not), and marked turns stop being sent once the switch is
off. They stay **on screen**. That is the whole rule, and it is worth saying in five words:
**display, not prompt.** Same rule the day-restore already runs on (`x.restored` turns are
re-shown and never re-sent) — this is its second instance, which is a good sign the rule is
real and not a patch.

**The lesson, and it is the one to carry into the next feature.** This door is not in
`anon.DOORS`, and it should not be: the eighteen ids there (thirteen write, five egress) are
all places that write or send, and this one does neither. It is a door because **it is a way
the evening survives the switch** — and that is the definition the next audit should use.
Ask of any new surface: *after the switch goes off, can this thing still put the private hour
in front of her?* Disk and wire were the two obvious answers. Her own context was the third,
it sat open for two days, and the person who found it was him, not a gate.

The exit edge is the one that matters here: on ENTRY she has always been told, per turn, by
the server staple (G-ANON holds it). What he actually saw on entry was an old room bundle not
drawing the anon chip; the current one does.

### Two exceptions to "guard at the write", both deliberate

`wardrobe._write_wants` and `decisions._append` each serve two semantics — creating a
record, and moving one that already exists to *dismissed* / *decided*. Holding both would
make his dismiss button silently do nothing, which is the mode disabling the room rather
than quieting it. **Only the door that creates is held.**

### The one that is not a refusal

`persona.state` writes into a shadow dict in `persona_file` instead of onto disk, and
`parse_persona` overlays it. A plain refusal would freeze her dials at whatever they read
when the switch went on, and the room's persona chip would show her marks visibly failing
to move. She feels the evening; the file does not learn it.

The shadow is dropped on **both** edges — entering, so a previous private evening cannot
bleed into this one, and leaving, so this one cannot bleed into the recorded life. The
consequence, stated rather than discovered: **she comes out of a private evening in the
state she went into it in.** An evening that left her measurably different would have been
recorded, just in a smaller file.

## She is told

One line, stapled to his turn, the same placement and the same unspeakable framing as the
recall and silence notes:

> *(Off the record: nothing from this conversation is being written down — no memory, no
> journal, no transcript. You are completely yourself; you simply will not have this later.
> He knows, so you need not raise it — but do not promise to remember any of it, and do not
> offer to store something you cannot.)*

This is not optional politeness. A companion who says *"I'll remember that"* into a mode
that keeps nothing is lying to him with her whole personality, and it is the harness that
made her do it. `remember()` returns her a **sentence** rather than failing silently, for
the same reason.

It rides on the user turn and not in the standing block because the standing block is the
cached KV prefix, and this toggles mid-evening by design — a mutable fact in the prefix
costs a cold re-prefill every time it moves. Same reason her clothes are a per-turn note.

## What it deliberately does not touch

A guard nobody can predict is a guard nobody trusts.

| | why |
|---|---|
| **Reads. All of them.** | She is herself, which means she has her memory. G-ANON §6 proves she still recalls a pre-anon fact while the switch is on. |
| **The KV cache and its snapshots** | A cache is not a record. Blocking it would cost her a cold prefill per turn to protect nothing. |
| **Operational logs carrying counts, never content** (`msgs=33 chars=54814`) | Those are how you tell a wedged stack from a slow one. The three lines that carried her actual words are redacted. |
| **Anything he does with his hands** — a board note he types, a ledger row, a setting, an answer to a decision card | Anonymous mode stops the room recording. It does not disable the room. |
| **The engine's own `var/daemon.log`** | It carries token counts and fault signatures, not text. If that ever changes, it becomes a door. |
| **The browser's scrollback** | It is on screen and it is not a record. **The reason changed on 2026-08-24 and the old one is now false**: this row used to say "React state — gone on reload, and the room has never persisted it", and the room now *does* restore the day on mount (`GET /v1/day`). The private turns are still safe, for a different reason — **they never reach the day transcript** (`transcript.day` is held), so there is nothing for the restore to draw. A right answer for a wrong reason is how the next regression hides: if the room ever gained a scrollback of its own, this row would have kept saying "safe" while the reason underneath it had already gone. |

## What proves it

```
python harness_tests/g_anon.py
```

**60 checks** (49 when this line was written; the count is re-run, 2026-08-25). It snapshots
the sandbox, drives every door for real, and diffs the disk — a
byte that appears is a failure whatever the code looked like. Six mutants, each convicted
by name: unguard the one door, fail an unknown door open, defer the spine flush, make the
persona hold a plain refusal, unguard the journal, declare a door with no guard behind it.

**Two defects the offline gate did not catch, and the live route did.** `leave()` answered
`on: true` to "turn it off" — it read the state before flipping the switch — and the receipt
said *"held back 1 memories"*, which is the tell that a sentence was assembled rather than
written. Both are now gate cases. A gate that only runs offline will not find the things you
only see when you press the button.

The third of those is the one worth remembering. `persist_receipts` returning `0` **looks**
like a hold and is not one: the receipts stay in the ring above the watermark, so the first
flush after the mode ends writes every private turn after all. A hold that only defers is
not a hold — the same shape as the free-before-drain and the inert wardrobe shim, a guard
whose failure mode is no guard.
