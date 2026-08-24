# CLAUDE.md — Kairos

**Read [`START-HERE.md`](START-HERE.md) for the two-minute map and [`AGENTS.md`](AGENTS.md) for
the rules. This file is a POINTER, not a copy — two copies of one truth is the exact bug this
codebase keeps getting hit by (AGENTS.md §0).**

- Start the stack: `python serve.py companion` — **the profile is positional and not optional**;
  `agent` is the 12B and looks healthy while serving the wrong model.
- Memory and recall, before touching `harness/skills/`: `docs/MEMORY-AND-RECALL.md`.
- What proves it still works: `gates/GATE-INDEX.md`. The whole offline suite in one command:
  `python tools/sweep.py` (~3 min, no GPU). **A green suite is not an audit** — the 2026-08-25
  pass found ~50 defects under 133 green gates (AGENTS.md §0).
- What is deliberately off: `docs/OFF-BY-DEFAULT.md`.
- What changed and when: `docs/CHANGELOG.md` — and **behaviour a reader would notice gets an
  entry there in the same commit**.
- New gates use `_gate.py`: `sandbox()` FIRST (before any `harness.` import), then
  `check()`/`finish()` so the verdict reaches the exit code.
- The math core (`core/`) is a different repo's `CLAUDE.md`; do not read its status as kairos status.
- **Kairos is a SNAPSHOT of this tree, never a place to write.** A file authored in
  `../Kairos` is destroyed by the next export. Anything that ships with it is written
  here; the re-export is manual and the procedure is in AGENTS.md §2.
  `../kairos-drift/` says how far behind the snapshot is (`python drift.py`).

Before you say you are done (offline, no GPU):

```
python harness_tests/g_claim.py
python harness_tests/g_durability.py
python harness_tests/g_memory_lifecycle.py
python harness_tests/g_docs_true.py
python harness_tests/g_real_her.py
```

If you touched `harness/personality/`, `harness/mcp_server/` or the persona, add the six
`h_personality_*` / `h_mcp_server` gates (about seven seconds for the lot).
