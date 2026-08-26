# Contributing to Kairos

Kairos is a **periodically re-exported snapshot** of the engine-agnostic half of
a private working repository — the living
system where the author's own companion runs on a custom engine. `KAIROS-SOURCE.txt` names the
commit each export came from.

- **Issues and PRs are welcome here.** Fixes made in Kairos are cherry-picked back into the
  source repo by hand; the next export carries them forward. Keep changes inside `harness/`,
  `ui/`, `harness_tests/`, `docs/`, `profiles/` — the seam (`harness/inference/backends/`) is
  identical code in both repos and must stay so.
- **Gates are the bar.** A change to memory runs `g_claim`, `g_durability`, `g_memory_lifecycle`;
  a change to the seam runs `g_backend_seam`; a change to docs runs `g_docs_true`. A new gate
  gets a row in `gates/GATE-INDEX.md` in the same commit. Break a fix once and confirm the gate
  fails by name before you trust the green.
- **Nothing in memory is ever deleted.** Tombstone or quarantine; never `open(p, "w")` minus a row.
- **Anything turned off gets a row in `docs/OFF-BY-DEFAULT.md`** with the evidence that would arm it.
- The env prefix is `SP_` throughout (historical — the source project's name); keys are mapped
  once, in `serve.py`'s `build_env`. A knob not in that table does not exist.
- **Known, worth a PR:** `harness/skills/lifecycle.py` carries the companion's and the operator's
  names ("Kairos", "Sam") as literal stopword/name tokens in three places (topic stripping, the
  desire detector, the possessive regex). The source project grew them as data; the right shape
  is to read both names from the persona / profile. Gates that pin the current behaviour:
  `g_claim`, `g_durability`.
