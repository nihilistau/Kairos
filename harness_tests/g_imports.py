"""G-IMPORTS — every module under harness/ imports, and the only ones allowed not to are
the ones the PACKAGING says are optional.

WHY THIS IS A GATE AND NOT A CI STEP (2026-09-11). It was twenty lines of inline Python in
`.github/workflows/gates.yml`, which made it a rule nobody could run locally and nobody
could see fail until a push. It failed on EVERY push from the day the workflow landed —
the public tree's CI has never once reached the gate suite, because this step sits two
steps before it and exits 1 in about twenty seconds. Eleven of 163 modules: ten wanting
`numpy`, one wanting `fastmcp`.

WHAT IT ASSERTS, AND WHY THAT IS THE HONEST VERSION OF IT. The inline step required every
module to import, full stop — a stronger claim than the packaging makes, and therefore one
the bare install in front of it could never satisfy. `pyproject.toml` says the core has
zero third-party dependencies and names the rest as extras, so:

  * a module that fails on a DECLARED-optional dependency is fine when that extra is not
    installed — and is still required to import when it IS
  * a module that fails on anything else is a defect, including a ModuleNotFoundError for
    a distribution nothing declares. That is the 2026-08-31 rule stated as a check:
    *"an undeclared dependency is a claim the packaging cannot keep"*. numpy was exactly
    that, in ten modules, for as long as this repo has existed
  * the CORE never gets the exemption. `harness/skills/`, `harness/model/`,
    `harness/control/`, `harness/kairos/`, `harness/server/`, `harness/tools/` and
    `harness/toolcore/` must import with nothing installed at all, because that is what
    the README promises an adopter

The optional set is READ FROM pyproject rather than kept here. A list in a gate is complete
on the day it is written, and the numpy gap survived an audit precisely because that audit
fixed the instance it found instead of asking the packaging what else it was not saying.

MUTANTS (each verified red by name in the BARE environment, exit 1, then restored):
    undeclare numpy — from `media` AND from `all`       -> ten modules go red by name.
        Removing it from `media` alone changes nothing and that is correct, not a hole:
        `all` still declares it. The first attempt at this mutant made that mistake and
        the green it produced was the gate being right.
    add an undeclared `import scipy` to a harness module -> that module goes red
    add `import numpy` to harness/skills/memory/store.py -> the CORE leg goes red, because
        the core may not plead an extra. In an environment where numpy IS installed this
        mutant is invisible here — the import simply succeeds — which is the reason the
        full CI job exists beside the bare one rather than instead of it.

OFFLINE. No GPU, no daemon, no network.
    python harness_tests/g_imports.py
"""
from __future__ import annotations

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _gate import check, finish, have, optional_dists, utf8_stdout   # noqa: E402

utf8_stdout()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SP_DAEMON_URL", "http://127.0.0.1:9")
os.environ.setdefault("SP_ENGINE_KIND", "openai")

# THE CORE, as the README defines it: what runs with zero third-party dependencies. A
# module here may never plead an absent extra — if it grows one, the packaging has stopped
# describing the product and this is where that shows up.
CORE = ("harness.skills.", "harness.model.", "harness.control.", "harness.kairos.",
        "harness.server.", "harness.tools.", "harness.toolcore.", "harness.personality.")

OPTIONAL = optional_dists(ROOT)
print("packaging declares optional: %s" % (", ".join(sorted(OPTIONAL)) or "(nothing)"))
print("installed here            : %s"
      % (", ".join(sorted(d for d in OPTIONAL if have(d))) or "(none of them)"))
print()

mods = []
for here, dirs, files in os.walk(os.path.join(ROOT, "harness")):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for fn in sorted(files):
        if fn.endswith(".py") and not fn.startswith("_"):
            rel = os.path.relpath(os.path.join(here, fn), ROOT)
            mods.append(rel[:-3].replace(os.sep, "."))

broken, excused, core_broken = [], [], []
for m in sorted(mods):
    try:
        importlib.import_module(m)
        continue
    except BaseException as exc:                      # noqa: BLE001
        # `as exc` is unbound the moment this block ends (PEP 3110), so everything the
        # decision needs is read HERE. The first cut referenced `exc` below and died with
        # a NameError on the only environment it exists to grade.
        top = (getattr(exc, "name", "") or "").split(".")[0]
        is_missing_module = isinstance(exc, ModuleNotFoundError)
        why = "%s: %s" % (type(exc).__name__, str(exc)[:70])
    if is_missing_module and top in OPTIONAL and not have(top):
        # Declared optional AND genuinely not installed: a real state of a real tree.
        excused.append("%s (needs %s)" % (m, top))
        if m.startswith(CORE):
            core_broken.append("%s pleads %s — the core may not need an extra" % (m, top))
        continue
    broken.append("%s -> %s" % (m, why))

print("walked %d modules: %d imported, %d excused, %d broken"
      % (len(mods), len(mods) - len(excused) - len(broken), len(excused), len(broken)))
for e in excused:
    print("  --   %s" % e)
print()

check("every module imports, or names a declared-optional extra that is absent",
      not broken, broken[:8])
check("...and the excuse is never available to the CORE",
      not core_broken, core_broken[:6])
check("the walk actually found the tree", len(mods) > 100, len(mods))

# WITH THE EXTRAS INSTALLED THERE IS NO EXCUSE AT ALL. On the operator's machine and in
# the full CI job this is the strict form of the same rule, and it is the leg that catches
# a module which imports an optional package WITHOUT the packaging naming it — the excuse
# list would quietly absorb it otherwise.
if all(have(d) for d in OPTIONAL) and OPTIONAL:
    check("with every extra installed, nothing is excused", not excused, excused[:8])
else:
    print("  --   the strict leg (nothing excused) needs every extra installed")

finish("G-IMPORTS")
