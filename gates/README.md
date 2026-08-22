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
