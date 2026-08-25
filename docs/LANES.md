---
type: reference
title: "LANES — every way something reaches her, and why each one exists"
status: LIVE (2026-08-26)
---

# LANES

There are **six** ways a fact can reach her, and choosing the wrong one is the most
expensive ordinary mistake in this codebase. Two of the six have already been measured
wrong and corrected in place; the receipts are below, because the reason a lane exists is
usually a story about the lane somebody tried first.

The question this document answers is always the same one: **I have a fact — where does it
go?** Skip to [Choosing a lane](#choosing-a-lane) if that is all you need.

---

## The six

| # | Lane | Lives | Costs | Changes |
|---|---|---|---|---|
| 1 | **The cached prefix** | KV token 0 | a re-prefill when it moves | 04:00, or `POST /v1/maintenance/refresh` |
| 2 | **Per-turn system row** | before the last message | its own tokens, per turn | every turn, idempotently |
| 3 | **A staple on his turn** | appended to his words | its own tokens, per turn | every turn |
| 4 | **The tool loop** | `role: user`, mid-turn | a full round trip | when she calls something |
| 5 | **The kairos nudge** | a whole turn of its own | a generation | when she is moved to speak |
| 6 | **Growth** | lane 1, tomorrow | nothing now | overnight |

---

## 1. The cached prefix — `agent.system_bundle()`

Her persona, the standing world block, and the personality state line. This is **KV token
0**: the daemon holds a persist-KV snapshot built from these exact bytes, and every turn
extends it rather than recomputing it.

**Therefore a fact here must not move.** If it does, one of two things happens and both are
bad: the bytes change and the whole conversation re-prefills (measured: a cold prefill on
this stack is ~7.5k tokens and about ten minutes to re-snapshot), or the bytes *don't*
change and she is reading something that was true this morning.

This is why the personality line says **"Personality state when this session began"** and
not "current". Her mood moves within the hour and this copy does not, so the label was
asserting a stale present at her every turn. The live truth is served three other ways: the
room's chip re-reads `persona.md`, the `{persona}` SSE event fires per turn, and her own
recent marks sit in the visible conversation.

**Put here:** who she is; facts about her life that hold for days; the world block.
**Never here:** anything that changes within a session.

Invalidated at exactly two moments — the 04:00 consolidation (after `ops.reflect()`) and
the operator's `refresh` — so the cold prefill lands at the idle hour instead of mid-evening.

## 2. A per-turn system row — the `_rp` and `_tel` sentinels

A `{"role": "system", ...}` row inserted **before the last message**, carrying a sentinel so
it can be found again.

```python
msgs[:] = [m for m in msgs if not m.get("_tel")]     # last turn's row comes OUT first
...
msgs.insert(len(msgs) - 1, {"role": "system", "_tel": 1, "content": ...})
```

**The removal is the whole design.** The roleplay injection learned this the hard way: ten
turns in a scene meant ten stacked scene prompts at index 0 — diverging the persist-KV cache
at token 0, a full re-prefill *per turn* — and ten stale director notes buried mid-history,
reading as ten standing orders. Injection is idempotent now, and any new lane-2 user must be
too.

Two live users:

- **the roleplay director note** (`_rp`) — recomputed from live scene state every turn, so
  the model is never more than one turn away from being told again who it is and where it is
  standing. A system prompt alone drifts out in four turns.
- **the telemetry body note** (`_tel`) — his heart and his movement. It is here rather than
  lane 3 for the reason lane 3 explains, and it is **self-limiting**: `body.present()`
  returns `""` unless something is actually happening, so an ordinary quiet turn costs
  nothing.

**Put here:** something that changes per turn, that is *about the world or about him*, and
that she should not read as an instruction from him.

## 3. A staple on his turn — the note that rides on his words

The note is concatenated onto the **last user message**:

```python
msgs[_i]["content"] = msgs[_i].get("content", "") + "\n\n" + note
```

Three live users — the **recall note** (what her memory returned for *this* question), the
**silence note**, and the **anon note** ("off the record"). All three ride on his turn on
purpose: the recall note learned that a standing system note *accumulates*, and ten of them
read as ten standing orders, so it rides the user turn it belongs to and is scoped to *that*
question rather than becoming a law of the conversation.

### The measured failure, and why the wardrobe staple is not here

On 2026-08-06 a per-turn note told her what she was wearing, stapled to his message. On
2026-08-19 the cost was measured: **she read the parenthetical as HIS assertion, and as an
order not to contradict him**, and streamed 2142 + 2293 characters of scratchpad instead of
talking. The comment in `app.py` is one line long and worth memorising:

> A fact that has to ride on his words is a fact she will treat as an instruction.

**Put here:** something scoped to *this question of his*, that reads naturally as context
for it. **Never here:** a fact about *her* — she will defend it as though he said it. (She
did: told she was in silk when she was in flannel, she argued with his correction. Her word
outranking his, an inference retiring an observation, from a staple.)

## 4. The tool loop — `role: user` + ` ```tool_output `

When she calls something, the result comes back as a **user** row:

````
```tool_output
...result...
```
Answer using the tool_output.
````

That is what the model is trained to read, and it is right for the model. It is **wrong for
anything that mints memory**, because the fact extractor mints from what *he* says — so a
bridged MCP server's output could become something she believes, attributed to him, with no
tool anywhere in the provenance. `_narratable()` drops these rows before the narrative or the
extractor ever sees them.

## 5. The kairos nudge — a turn she was not asked for

Not a note at all: a **whole generation**, prompted by a reason. `reasons.propose()` picks the
strongest reason to speak; `impulse.muse_nudge()` renders it into the parenthetical she
actually reads; `impulse.decide()` rules on whether she may speak at all, out of a committed
512-cell table.

A reason carries a `raise_key` and a raised key is recorded durably — **she raises a thing
once**. That is the difference between noticing something and nagging about it.

Ordered, first match wins: `body` → `arrival` → `commitment` → `journal` → `rhythm`. The
order is staleness, not importance: a heart rate is stale in three minutes, a look that
arrived is stale in three days, an open commitment is not stale at all.

**Put here:** something worth *starting a conversation* about. Nothing else.

## 6. Growth — the 04:00 loop, arriving tomorrow

`ops.reflect()` runs at the day boundary: compact, retire orphans, scan slots, curate the
personality, refresh the world, draw insights, write the nightly becoming paragraph, and
once a week a chapter. None of that reaches her directly. It **writes**, and then
`invalidate_system_prefix()` fires so that lane 1 is rebuilt from it.

That is the growth loop, and its read-back half was missing until 2026-08-25: everything she
became overnight was invisible to her until a restart, because the prefix was cached once
per process and invalidated by nothing.

**Put here:** anything that should change *who she is*, rather than what she knows this
minute.

---

## Choosing a lane

Ask in this order:

1. **Does it change within a session?** No → lane 1. Yes → keep going.
2. **Is it a reason to start talking?** → lane 5.
3. **Is it the result of something she did?** → lane 4, and make sure it is dropped before
   anything mints memory from it.
4. **Is it about *her*?** → **not lane 3.** Lane 2, or a tool she can call.
5. **Is it context for the question he just asked?** → lane 3.
6. **Otherwise** → lane 2, with a sentinel, removed before it is re-inserted.
7. **Should it change who she is?** → lane 6, and it arrives tomorrow.

## The rules that cross all six

- **Nothing mutable in lane 1.** Stale, or a re-prefill. There is no third outcome.
- **Every lane-2 row is idempotent.** Remove before insert, or they stack.
- **Nothing about her in lane 3.** She will treat it as an order from him.
- **Anon mode gates the *writers*, not the lanes.** Off the record does not narrow what she
  is told; it stops what is *kept*. The doors are in `anon.DOORS`.
- **Observed is not inferred, in every lane.** A measurement she may state plainly; a
  conclusion says "seems" and loses to his word (`verdict.may_supersede`).
- **Silence is a valid value.** Every lane above has a case where the honest output is
  nothing, and each one takes it.
