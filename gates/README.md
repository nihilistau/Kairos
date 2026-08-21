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

## Rules bought with regressions
1. **Assert through the real path**, not a hand-called helper.
2. **Do not supply your own precondition** — a gate that hand-builds the row that makes the guard
   fire has tested the guard, not the system.
3. **Verify the mutant**: break the fix once, confirm the gate fails by name, restore.
4. **A gate touched ⇒ its GATE-INDEX row edited in the same commit.** `g_docs_true.py` fails on an
   unindexed gate.

Minimum bar after touching memory: `g_claim`, `g_durability`, `g_memory_lifecycle`. After touching
docs: `g_docs_true`, `g_profile_door`. After the room: `g_room_css`, `g_room_bundle`.
