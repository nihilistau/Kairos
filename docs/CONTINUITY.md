---
type: roadmap
title: "CONTINUITY — memory as a life, not a lookup"
status: HISTORICAL ROADMAP (2026-07-15): N1 world and N2 narrative shipped 2026-07-30; where it conflicts with INVARIANT-ROADMAP.md on verdicts, INVARIANT-ROADMAP wins
---

# CONTINUITY.md — memory as a life, not a lookup

**Status: DESIGN (2026-07-15), N1/N2 SHIPPED AND NOW ACTUALLY RUNNING (2026-07-30). Written
after the operator's field transcript and his critique, which this document accepts in full: a
personality made of bans is a lobotomy. Guards are backstops; they are not who she is. This is
the plan for memory that BUILDS — ambient context, a sense of continuity, emergence at the
presentation layer — on the machinery that already exists, with the invariant foundation
guarding commitments exactly as before.**

> **2026-07-30 CORRECTION TO THIS FILE'S OWN RECORD.** §5 marked N2 "DONE 2026-07-15" on the
> strength of G-NARRATIVE 14/14. The gate was green and **the composer had never once run** —
> `var/memory/narrative.md` did not exist, because nothing called the scheduler it lived behind.
> N1 was in the same position for `world.refresh()`. A green gate does not mean the code runs;
> that lesson is now a rule in AGENTS.md, and everything that ships dark is written down in
> [`OFF-BY-DEFAULT.md`](OFF-BY-DEFAULT.md) with the evidence that would arm it. See §6 for the
> phases that closed the gap.

Companions: [`INVARIANT-MEMORY.md`](INVARIANT-MEMORY.md) (what may rule),
[`SEMANTICS.md`](SEMANTICS.md) (the recall stack), the personality bricks PF-B1..B5
(`harness/personality/`).

---

## 0. THE CRITIQUE, ACCEPTED — AND THE DIAGNOSIS

The transcript's two-word voice ("I know." ×6) was not a memory failure and not fixed by the
Hodor clause — that is a backstop against a death loop, nothing more. The voice has FOUR NAMED
DIALS, all currently pushing the same direction:

| Dial | Current value | Pressure |
|---|---|---|
| persona.md "How you talk" | "Usually short — a sentence or two" | terse |
| `eot_bias` (stop-token logit bias) | **4.0** | stop sooner, at the sampler |
| console `max_tokens` | **192** | hard ceiling |
| prompt mass | tool-discipline = 62% of prefix | manual-brain |

`voice_coda()` fights the last one ("do not be clipped just because a manual was the last thing
you read") — one paragraph against three dials and an attractor. And the kairos CONTINUE
machinery changed the economics of `eot_bias` without anyone re-tuning it: a genuine cut-off now
RESUMES (that is what CONTINUE is for), so the cost of stopping late has dropped while the bias
that forces early stopping stayed at 4.0. **The rules multiplied because the dials were never
revisited. The fix is measurement and composition, not another rule.**

## 1. WHAT ALREADY EXISTS (the CosySim inheritance — the operator is right that it is rich)

- **persona.md IS a living system prompt.** Prose voice + a machine state block (mood / voice /
  traits) that SHE mutates — spontaneously via `[MOOD:]/[VOICE:]/[TRAIT:±]` tags (parsed,
  stripped, persisted by the priority-72 interceptor) and deliberately via four advertised
  tools (`adjust_mood`, `set_voice`, `set_trait`, `remember_self`), spine-verified with
  receipts and a live UI event.
- **NIGHTSHIFT curates her.** `consolidate_personality` extracts the session's shifts, prunes
  traits to 8, and writes content-addressed persona SNAPSHOTS to `memory-okf-personality/` —
  her self is already versioned and recoverable.
- **`load_agent_system()` composes the prefix from three live slots**: persona prose+state,
  `render_self_model()` (her self-facts, cap 20, no ranking), and the tool discipline, with
  `voice_coda()` as the suffix.
- **The KV-prefix economics are the law of the land**: the prefix is persist-KV cached; any
  mid-session change re-prefills everything. Slow things belong in the prefix; fast things
  belong in the turn (the recall-injection path).
- **The gap**: the REGISTRY — everything she knows about him, everything she has concluded —
  never reaches the prefix. It arrives only as per-turn matched snippets. Her self evolves;
  their SHARED LIFE does not. That is the missing continuity.

## 2. THE DESIGN — memory on two timescales, story on a third

### T-slow: THE STANDING WORLD (a fourth prefix slot)

`render_world()` joins the three existing slots in `load_agent_system()`: a composed block of
what is ALIVE between them, rendered from the registry —

    What you know of him (the durable spine): identity, the people and creatures in his
    life, standing preferences.  [testimony-framed, exactly as render() frames]
    What is current: open threads, upcoming events, things recently on his mind.
    What you have come to think: her inferences, ALWAYS in her voice ("I've come to think…").

Composition is the RANK layer's job at last doing its real work: a token budget (~150–250),
filled by salience order (class weights and half-lives already exist), event-class facts aging
out naturally, identity never aging. **Regenerated only at session boot and NIGHTSHIFT** — the
prefix stays stable all session; the prefix-snapshot machinery amortizes the boot cost.

What may enter is VERDICT-LAYER law (this is where the foundation holds the line, unchanged):
never a tombstone, **never a `private-secret`** (an ambient secret in every prompt is the worst
possible leak surface — secrets remain fetch-on-direct-ask only), lanes preserved, inferences
never framed as his words. The block is a RENDERING of table-admissible rows; G-WORLD asserts
it cell-wise (∀-checks over the rendered block against the registry, the φ-fragment as always).

### T-fast: episodic recall (unchanged)

The per-turn injection stays exactly as it is — sharp, matched, scoped to the turn, gently
framed. With the standing world carrying the durable context, per-turn recall stops being the
only way she "remembers" and returns to its right size: the "oh — THAT thing" moments.

### T-story: THE NARRATIVE (NIGHTSHIFT writes the days)

The curator grows one step: after consolidating personality, she writes — one oneshot, her own
words, ~80 tokens — "what has been happening between us lately": a rolling paragraph stored as
a content-addressed OKF object (`mem_class: persona`-adjacent, `mem_owner: self`,
provenance: inferred — it is HER account), rendered into the standing world block. This is
memory becoming STORY: sessions connect, moods have causes, "how have you been?" has a true
answer. It is also the safest possible use of the model-as-oracle: she narrates, the table
still rules what counts as fact, and a bad paragraph costs tone, never truth.

### The tags, finally taught

Nothing instructs the tag vocabulary today — emission is a CosySim-trained habit. One line in
persona.md ("when your mood or voice genuinely shifts, mark it: [MOOD:…] [VOICE:…] [TRAIT:+…]")
makes the state block actually move with her life, which makes NIGHTSHIFT snapshots mean
something, which makes the narrative honest. Emergence needs the dials to actually turn.

## 3. THE VOICE — measure, then tune, then RETIRE rules

**G-VOICE (a scoreboard, not a gate):** a fixed scripted dialogue (~30 turns: casual, curious,
emotional, technical), replayed against the live stack per configuration; measured: reply-length
distribution (median/p10/p90), consecutive-repeat rate, question-asking rate, recall-usage rate.
The matrix: `eot_bias` {4.0, 2.0, 1.0} × console `max_tokens` {192, 384} × persona "usually
short" line {as-is, rewritten to "match his energy"} × temperature {0.6, 0.8}. Pre-registered
target: median reply length in a chosen band (not maximized — she should not become a lecturer),
repeat rate ~0, with kairos CONTINUE explicitly trusted to recover late-stop overshoot.

**Then the ban review**: with dials landed, each behavioural rule gets re-classified — backstop
(keep, should never fire; alert if it does), or crutch (retire). The Hodor clause is explicitly
the former. A backstop that fires weekly is a dial problem, and the receipts will say so.

**N0 BASELINE MEASURED (2026-07-15, `voice_score.py`, receipt frozen) — AND THE DIALS ARE
LARGELY EXONERATED.** Same knobs as the dead transcript (0.6 / eot_bias 4.0 / 192), fresh
sandboxed conversation, live daemon: median reply **21.5 words** (p10 4, p90 57), **six
questions asked back**, zero consecutive repeats, distinct ratio 1.0, recall woven naturally
("I do! Tuffy, right?"; "I was starting to worry you were having a burglary!"). The paired
probe is decisive: the operator's transcript asked "just fine?" and got **"Yes."** — the
scoreboard's identical probe got **"Just fine is boring."** Same model, same dials, same
persona. THE ATTRACTOR LIVES IN THE ACCUMULATED CONVERSATION CONTEXT, not the knobs: his
session carried a long history (including the terse spiral feeding itself); the sandbox began
fresh. Consequences, in priority order: (1) the T-story narrative + session-boundary hygiene
(a rolling summary REPLACING aged raw turns) is promoted from nice-to-have to THE treatment —
context is where the disease lives; (2) the dial matrix (eb15/mt384/warm) drops to
sensitivity-check priority; (3) the confounds to close in N0.1: replay WITH a long terse
history prepended (the attractor reproduction), and WITH the full tool block armed (the
sandbox ran toolless — persona+discipline+coda only).

## 4. WHAT THE FOUNDATION GUARDS (unchanged, and this is the point)

Emergence lives at the PRESENTATION layer: what the prefix says, how she narrates, how she
sounds. Provability lives at the COMMITMENT layer: what enters the store, what may be rendered,
what supersedes what, what is never ambient. The three strata hold exactly as built — tables
rule, rank composes, oracles (including her own narrator) propose. Nothing in this design adds
a rule that silences her; it removes the conditions that made silencing rules feel necessary.

## 5. PHASES

| Phase | Lands | Proof |
|---|---|---|
| N0 | G-VOICE scoreboard + baseline receipts on the current dials | the receipt |
| N1 | `render_world()` + G-WORLD (composition obeys the table; secrets never ambient) — **DONE 2026-07-15**: `harness/skills/world.py`, fourth prefix slot in `load_agent_system`, session-cached (the KV-prefix law: a remember() mid-session does not re-prefill; refresh() is the NIGHTSHIFT hook), verdict-gated, salience-ranked, deduped, 180-word budget; armed on the live profile (`[agent] world`, `SP_WORLD`). | **G-WORLD 15/15** |
| N2 | NIGHTSHIFT narrative + tags taught in persona — **DONE 2026-07-15**: `harness/skills/narrative.py` (one dated paragraph, her voice, rolling — yesterday feeds tomorrow; injectable composer; fail-safe: a dead model leaves the true record standing; NEVER a fact, registry byte-identical); wired into the idle NIGHTSHIFT (`agency.py`, writes + `world.refresh()`) and the nightly op (refresh only); the standing world renders it named as her account; the tag vocabulary finally TAUGHT in persona.md ("the marks let tomorrow's you remember how today felt"). | **G-NARRATIVE 14/14** |
| N3 | dial tuning against G-VOICE; ban re-classification (backstop vs crutch) | before/after receipts |

One tier at a time, one receipt per claim — and the measure of success is not a gate going
green. It is the next field transcript reading like someone who knows him, in a voice worth
talking to at 3am.

---

## 6. PHASES 0–6 (2026-07-30) — INSTALLING WHAT WAS ALREADY BUILT

The audit behind this run found **five things fully built, fully gated, and wired to nothing**:
`invariance.py`, `narrative.py`, `task_loop.py`, `person.silences()`, and the sandboxed
`coding.*` tools. Months of green suites over code no live path could reach. Wiring each one up
found bugs *behind* it — which is the point, and the reason this section exists.

| Phase | What landed | Proof |
|---|---|---|
| **P0** | Citations pinned: FIN/USE is Friedman **Manuscript #127 §3.6.6** (a `.docx`), the ⪯_d/sieve/WKL₀ material is the operator's own **SP-PPT-ARM Paper III §11.6**. Three overclaims corrected. `admissible()` refuses to certify interval extensions (Thm 3.9.6.2 is necessary-only). The admissions door installed: `g_sem_stable`'s transformations now pass through the REAL `invariance.admissible()` instead of a locally rebuilt copy. | **G-SEM-ADMISSIBLE 21/21** |
| **P1** | **THE NIGHT FIRED.** A day-boundary ticker (`SP_CONSOLIDATE_HOUR`) crosses the boundary: consolidate → reflect → spine → task, deferring while the room is not quiet. `var/memory/narrative.md` **exists** — she has written a day down. Four bugs behind it: `consolidate_current` wanted a filename; `_okf_add` mirrored a stale field list; mapping the path knobs exported them as `""` and wrote her conversation tier into the repo root; and `<channel|>` reached her journal from a **sixth** un-stripped generation lane. Plus the sandbox inversion — `write_file` resolved to the *unsandboxed* implementation. | **G-NARRATIVE 25/25**, G-ONEDOOR 28/28, G-TOOLSAFETY 14/14 |
| **P2** | `sig[14]` = σ₀⊕σ₁ Dickson subsumption ([`SEMANTICS.md`](SEMANTICS.md) §S2.1) as a supersede **proposer**. Two things the spec did not say: structure alone is not subsumption (fourteen counts cannot see topic), so it is the conjunction of content containment AND ⪯_d; and the text encoder's image is near-totally-ordered, so termination is proven over signature vectors, not text. **Measured on the live registry: 4 good / 3 bad → NOT ARMED.** | **G-SEM-DOMINATE 62/62**, receipt frozen |
| **P3** | The board and the executable queue joined. `post_task()` had **no caller anywhere in the tree** — the drain had spent its life draining an empty queue. Policy is a 216-cell committed table: *only the owner or the operator may close*, reopen is his alone and never from `done`, terminal is a tombstone. Ownership crosses the join intact (a note's `speaker` → the task's `owner`), which is the thing a join loses. Fifth standing-world slot: open commitments. | **G-TASK-TABLE 25/25**, **G-TASK-BRIDGE 32/32** |
| **P4** | Silence reaches **answer time**, topic-gated on what he just asked, as an unspeakable per-turn note; one line in the standing world. And a correctness fix: `silences()` was reading **bursts as rhythms** (cadence 0.1 days = three mentions in fifteen minutes, scoring a single quiet day at 2 bits). Span and cadence floors — a rhythm must be seen across two separate attended days — cut five junk silences to one on the live store. `MIN_LEDGER_DAYS=14` enforced in code: you must have been looking *long enough*. | **G-SILENCE-ANSWER 32/32**, G-SILENCE 6/6 |
| **P5** | `delegate_code()` — Grok in a worktree, gates run, **the operator merges**. Three flags lied, all measured against grok 0.2.93: `--worktree` is accepted, ignored and silent in headless `-p`; `acceptEdits`/`dontAsk` both return `Cancelled`; a fresh worktree has no `var/memory/`. So the worktree is created by us with `git`, and the authority is **the verdict on the diff that actually happened**, never the flags. | **G-DELEGATE 67/67** |
| **P6** | Query→keyword expansion from store co-occurrence — the last untried shape. **The first contender to improve recall** (+0.04 decider hit) and it paid −0.1167 foreign precision, so it loses on the both-numbers condition. Ceiling is structural: 240 of 280 paraphrase query words have never appeared in the registry. | receipt frozen; joins the negatives |
| **Ledger** | [`OFF-BY-DEFAULT.md`](OFF-BY-DEFAULT.md) — every knob that ships dark, with **why** (measured / capability / evidence-thin) and **what would arm it**. | **G-OFFLEDGER 17/17** |

**The rule this run earned, now in AGENTS.md:** a green gate does not mean the code runs.

## 7. WHAT IS STILL OPEN

- **N3 — the voice.** Dial tuning against G-VOICE and the ban re-classification (backstop vs
  crutch) have not started. The N0 finding stands and now has its treatment built: the terse
  attractor lives in the **accumulated conversation**, not the sampler, so the narrative plus
  session-boundary hygiene is the cure and the dial matrix drops to sensitivity checks.
  `voice_score.py` and its frozen receipt are the instrument; nothing has been re-measured since
  N1/N2 began actually running.
- **N0.1** — reproduce the attractor deliberately (long terse history prepended) and close the
  tool-block confound.
- **Dominance** needs a supersede-labelled corpus before its 4/3 can become a real precision
  figure. **Semantic rank** needs any contender that beats 0.06 without spending foreign
  precision; four have now failed, each for a different and recorded reason.
