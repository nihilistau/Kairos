# gates/ — the acceptance bar

**No claim without a repeatable gate.** `harness_tests/` holds the executable gates (`g_*.py` and
the `h_*.py` set); **`GATE-INDEX.md` is the full list** — every gate, what it protects, whether it
needs the stack, and its run command. This directory also keeps the write-ups and receipts
(`G-*.md`, `MEMORY-AUDIT-*`, `REGRESSION-*`) from the July phase gates.

## Modes
- **OFFLINE** — no GPU, no daemon; run freely (`SP_DAEMON_URL` points at a discard port).
- **LIVE** — the stack up: `python serve.py companion` (positional, not optional).
- **LIVE-SP** — needs the sp-daemon specifically (byte-exact, KV, the kairos margin); arrives with
  the engine-agnostic backend.
- **BROKEN** — red and said so, with the reason in the row.

## The exit convention
0 = asserted and held · 1 = asserted and failed · 2 = skipped (the subject is absent here; a run
that asserted nothing is a skip, not a pass). `harness_tests/_gate.py` implements it
(`check`, `finish`, `skip`, `utf8_stdout`) — new gates use it.

## A gate with a synthetic clock must pin the boot (2026-08-23)

Every `TurnState` clock defaults to `impulse.BOOT_AT` — the real monotonic boot time,
because a zero clock **fails open** (a1ecf2a: five unrelated checks were skipped when a clock
was unset). On a box that has been up a day that is ~1e5, which sits in the **future** of the
small synthetic fixtures gates use (`now=100.0`, `1000.1`, `5000.0`). `now - last_spoke_at`
goes hugely negative and every decision comes back `cooldown (98000s left)` — a gate red
for a reason with nothing to do with what it guards.

**Pin the boot, once, at import scope:**

```python
import harness.kairos.impulse as _imp_pin  # noqa: E402
_imp_pin.BOOT_AT = 1.0
```

Non-zero, so the no-zero-clock rule is still exercised, and before every `now` the gate uses.
**Seven gates** do this: `g_kairos_latch`, `g_kairos_presence`, `g_kairos_reasons`,
`g_kairos_policy`, `g_kairos_tick`, `g_tuning`, `g_notes`.

The alternative — leaving the global alone and offsetting every fixture time from
`BOOT_AT` — also works, and `g_notes` shipped that way for four hours before converging
here. It is not wrong; it is a SECOND ANSWER to one question, which is what AGENTS.md 0 is
about. One idiom. If you are writing a gate that drives `decide()` with made-up times, pin.

A gate whose subject is BOOT_AT itself (`g_kairos_latch` asserts a fresh state equals it) pins
too and then compares against the pinned value — the pin is a fixture, not a bypass.

## An offline gate that writes memory is paying 2 seconds a write (2026-08-23)

Pointing `SP_DAEMON_URL` at a dead port is the house pattern for "no engine here", and it
does **not** make the KV mint cheap: `memory._mint_now` still opens a socket per write, and
on Windows that connect costs about **two seconds** before it gives up. A gate that writes
forty rows spends eighty seconds doing nothing.

Declare the backend instead. `SP_ENGINE_KIND=openai` makes `backends.supports("capture")`
False, so `_mint_now` returns immediately:

```python
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"   # still: no engine
os.environ["SP_ENGINE_KIND"] = "openai"              # ...and no mint attempt at all
```

**Measured: 10 writes in 0.07 s against 20 s.** Adopted in gates touched from here on rather
than as a mass edit — but if you are wondering why the offline sweep takes as long as it
does, this is most of it.

## Rules bought with regressions
1. **Assert through the real path**, not a hand-called helper.
2. **Do not supply your own precondition** — a gate that hand-builds the row that makes the guard
   fire has tested the guard, not the system.
3. **Verify the mutant**: break the fix once, confirm the gate fails by name, restore.
4. **A gate touched ⇒ its GATE-INDEX row edited in the same commit.** `g_docs_true.py` fails on an
   unindexed gate.

Minimum bar after touching memory: `g_claim`, `g_durability`, `g_memory_lifecycle`. After touching
docs: `g_docs_true`, `g_profile_door`. After the room: `g_room_css`, `g_room_bundle`.

### G-VRAM evicts the resident prefix (2026-08-23)

`g_vram.py` posts to the **daemon** directly, which is correct for what it measures and
means it overwrites the gateway's ~7.9k persona prefix. Her next turn logs
`PERSIST-KV: guard miss (pos=0 != committed N) — full prefill` and pays ~97 s to rebuild it.

Worse, the gate's own `a short turn is short` check then queues behind that re-prefill and
reports ~80,000 ms with *"the daemon is paging over PCIe. Lower [kv].pmax"* — a gate
accusing the machine of what the gate did. Measured: three runs, three re-prefills, one
false FAIL, and a real regression hunt that found nothing because there was nothing.

Run it with `--daemon-only`, or accept one cold prefill afterwards.
