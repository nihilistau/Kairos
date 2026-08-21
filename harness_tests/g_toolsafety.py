#!/usr/bin/env python
"""G-TOOLSAFETY — the tool she is HANDED is the sandboxed one.

── THE BUG (audit, 2026-07-30) ──────────────────────────────────────────────────────────
Two tool packs define the same three filesystem verbs:

    harness/skills/builtin/coding.py   read_file / write_file / list_dir
        -> resolves every path through _resolve(), which RAISES "path escapes workspace"
    harness/skills/system_tools.py     read_file / write_file / list_dir
        -> no path restriction whatsoever; write_file overwrites silently

`agent.all_tools()` concatenates the packs and dedupes FIRST-WINS. SYSTEM_TOOLS was
concatenated first, so the assembled toolset bound those three names to the UNSANDBOXED
implementations, and the sandboxed ones were reachable only through
`spine.toolset_for("coding")` — which is OFF on every live profile (the per-turn swap
diverges the persist-KV cache at token 0). The safe implementation existed, was tested,
and quietly lost a name collision.

This is not the two-paths bug. It is worse in one specific way: both paths were present,
one was correct, and the assembly picked the other. Nothing was missing; the wiring chose
wrong. A gate that checks the coding module in isolation would have passed all along —
which is exactly why this gate asserts on the ASSEMBLED SET, through the real
`all_tools()`, by CALLING the tool and requiring it to refuse.

Written in the phi-fragment: universal over the colliding names, bounded negation
("no assembled filesystem verb accepts a path outside the workspace"), no existential
demand — so a failure is always a concrete named tool and a concrete path.

    python harness_tests/g_toolsafety.py
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"      # dead port: never needs a GPU

PASS = FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                           (" :: " + str(detail)[:120]) if detail else ""))
    PASS, FAIL = PASS + (1 if ok else 0), FAIL + (0 if ok else 1)


def main() -> int:
    print("G-TOOLSAFETY - the assembled toolset binds the SANDBOXED filesystem verbs.\n")

    from harness.agent import all_tools
    from harness.skills.builtin.coding import CODING_TOOLS
    from harness.skills.system_tools import SYSTEM_TOOLS

    sys_names = {f.__name__ for f in SYSTEM_TOOLS}
    cod_names = {f.__name__ for f in CODING_TOOLS}
    colliding = sorted(sys_names & cod_names)

    # 1. The collision set is what we think it is. If a future pack adds a fourth
    #    colliding verb, this gate must notice rather than silently cover three.
    print("1. the collision set")
    check("exactly the three filesystem verbs collide",
          colliding == ["list_dir", "read_file", "write_file"], colliding)

    specs = {s.name: s for s in all_tools()}
    cod_funcs = {f.__name__: f for f in CODING_TOOLS}

    # 2. Identity: for every colliding name, the assembled spec must be the CODING one.
    print("\n2. identity — the assembled tool IS the sandboxed implementation")
    for n in colliding:
        s = specs.get(n)
        bound = getattr(s, "fn", None) or getattr(s, "func", None) or getattr(s, "call", None)
        same = bound is cod_funcs[n] or getattr(bound, "__module__", "") == \
            cod_funcs[n].__module__
        check("assembled %s comes from %s" % (n, cod_funcs[n].__module__), same,
              getattr(bound, "__module__", "<no bound callable>"))

    # 3. BEHAVIOUR, not provenance. Identity can be faked by a re-export; a refusal
    #    cannot. Call the assembled write_file with a path outside the workspace and
    #    require it to refuse. This is the check that actually protects the disk.
    print("\n3. behaviour — the assembled verbs REFUSE a path outside the workspace")
    outside = os.path.join(tempfile.gettempdir(), "g_toolsafety_should_not_exist.txt")
    if os.path.exists(outside):
        os.unlink(outside)

    def refuses(name, *args):
        s = specs.get(name)
        fn = getattr(s, "fn", None) or getattr(s, "func", None) or getattr(s, "call", None)
        if fn is None:
            return False, "no callable on the spec"
        try:
            out = fn(*args)
        except Exception as exc:                       # a raise IS a refusal
            return True, "raised %s: %s" % (type(exc).__name__, str(exc)[:60])
        # some tools return an error string rather than raising
        low = str(out).lower()
        if "escape" in low or "outside" in low or "denied" in low or "error" in low:
            return True, str(out)[:70]
        return False, "ACCEPTED: %s" % str(out)[:70]

    ok, why = refuses("write_file", outside, "this must never be written")
    check("write_file refuses an absolute path outside the workspace", ok, why)
    check("...and the file was genuinely not created", not os.path.exists(outside),
          outside)
    if os.path.exists(outside):
        os.unlink(outside)

    ok, why = refuses("read_file", os.path.join(ROOT, "..", "..", "etc", "hosts"))
    check("read_file refuses a traversal out of the workspace", ok, why)

    ok, why = refuses("list_dir", tempfile.gettempdir())
    check("list_dir refuses a directory outside the workspace", ok, why)

    # 4. The six system-only verbs must survive — this fix must not delete capability,
    #    only re-bind three names.
    print("\n4. nothing was lost — the system-only verbs are still present")
    for n in sorted(sys_names - cod_names):
        check("%s still in the assembled set" % n, n in specs)

    print("\nG-TOOLSAFETY: %s (%d/%d)" % ("PASS" if not FAIL else "FAIL",
                                          PASS, PASS + FAIL))
    if FAIL:
        print("  ^ the assembled toolset is handing her an UNSANDBOXED filesystem verb.")
        print("    Check the concatenation order in harness/agent.py all_tools(): the")
        print("    dedupe is first-wins, so CODING_TOOLS must come before SYSTEM_TOOLS.")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
