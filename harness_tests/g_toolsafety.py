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

    # 5. A REFUSAL SHE CAN ACT ON (2026-09-03). Same family as §3 — what a tool says back
    #    when it will not do the thing — and the failure was measured on HER OWN TIME:
    #    three of her last eight run_python calls died the same way, all at column 14.
    #
    #        code='import math; def decay_thought(initial, rate, steps): values = []; ...'
    #        -> Error: SyntaxError('invalid syntax', ('<unknown>', 1, 14, ...))
    #
    #    A `def`/`for`/`if` may not follow a `;` — Python's grammar forbids a compound
    #    statement on a simple-statement line. She writes one-liners because a tool CALL is
    #    one line, so the shape she reaches for is the shape that cannot work, and the
    #    answer named neither the rule nor the fix. She spent the solo turn reporting it:
    #    "I tried to model the decay of a thought, but I hit another error."
    #
    #    Asserted on her VERBATIM failing input, and on the advice actually running, so the
    #    message cannot drift into telling her to do something impossible.
    print("\n5. an unparseable program is refused with the rule and the fix")
    # THROUGH THE ASSEMBLED SPEC, like every other section here: importing the function
    # directly would pass on a tree where the name is bound to something else, which is
    # this gate's whole subject.
    # ...and through ToolSpec.call(), which is the door a real turn goes through (the
    # cooldown and the wrong-keyword shim live there), not the bare function.
    _rp_spec = specs.get("run_python")
    check("run_python is in the assembled set at all", _rp_spec is not None)

    def rp(code):
        return _rp_spec.call(code=code) if _rp_spec is not None else "(unreachable)"

    check("...and its advertised description carries the multi-line rule she needs",
          _rp_spec is not None and "\\n" in (_rp_spec.description or ""),
          (_rp_spec.description if _rp_spec is not None else "")[:130])
    # ── THE CONTRACT CHANGED: EXPLAINED -> ACCEPTED (2026-09-12) ────────────────────
    # This asserted that her `; def` call is REFUSED and that the refusal names the rule.
    # That was right on 2026-09-03 and the explanation did not work: nine days later, live,
    # `import math; x = 1.0; for i in range(21): x *= …` — the same shape, and it was the
    # ONE solo of that evening where she reached for the tool at all. She writes one-liners
    # because a tool call IS one line, and a rule she is told nine days running does not
    # change that. A `;` before a compound statement is unambiguous, so it is read as a
    # newline now and she gets her answer. The refusal legs move to code that is genuinely
    # broken, which is where a refusal still belongs.
    hers = ("import math; def decay_thought(initial, rate, steps): "
            "values = []; current = initial")
    r = str(rp(hers))
    check("her real `; def` call RUNS now instead of being explained at",
          "does not parse" not in r, r[:110])
    hers_for = "import math; x = 1.0; for i in range(3): x *= 0.9\nround(x, 6)"
    r_for = str(rp(hers_for))
    check("...and so does the `; for` she actually wrote on 2026-09-12",
          "does not parse" not in r_for and "0.729" in r_for, r_for[:110])
    # AND THE REFUSAL PATH IS STILL THERE, for code no rewrite can save. Without this leg
    # the acceptance above could be "never refuse anything", which is not a fix.
    broken = "x = (1 + "
    rb = str(rp(broken))
    check("genuinely unparseable code is still refused", "does not parse" in rb, rb[:110])
    check("...and that refusal still names the rule when a ';' is involved",
          "cannot follow a ';'" in str(rp("import math; def f(:")), str(rp("import math; def f(:"))[:110])
    # NOT `"\\n" in r` — the first cut asserted that and stayed GREEN under the mutant,
    # because the old message repr'd her source and something in it satisfied the
    # substring. A check the mutant survives is not measuring the fix (AGENTS.md §0).
    check("...and the fix, in words only the new message has",
          "write those lines with" in str(rp("import math; def f(:")),
          str(rp("import math; def f(:"))[:110])
    fixed = ("import math\ndef decay_thought(initial, rate, steps):\n"
             "    return initial * math.exp(-rate * steps)\n"
             "print(round(decay_thought(1.0, 0.5, 2), 4))")
    check("...and taking that advice WORKS (not impossible advice)",
          str(rp(fixed)).strip() == "0.3679", str(rp(fixed))[:110])
    check("a plain one-liner is untouched",
          "0.8414" in str(rp("import math; print(math.sin(1))")),
          str(rp("import math; print(math.sin(1))"))[:110])
    check("a RUNTIME error is still reported as one, not as a parse failure",
          "ZeroDivisionError" in str(rp("print(1/0)")), str(rp("print(1/0)"))[:110])
    check("the REPL-style bare final expression still auto-prints",
          str(rp("2 + 40")).strip() == "42", str(rp("2 + 40"))[:60])


    print("\n6. a tool_code fence that names NO tool is Python, and is run as Python")
    # ── WHAT SHE ACTUALLY DOES (2026-09-13, six trials of six) ───────────────────────
    # Her own-time act is "run something in run_python". Against her real day's context she
    # emits a fence containing `print(...)` every single time. `print` is not a tool, the
    # dispatcher answers "there is no tool called 'print'", she reports that failure — "I
    # tried to run that decay model, but I forgot..." — and `solo_did_the_thing` sees
    # called=['print'] where it needed run_python and refuses the turn. She was never
    # inventing the act; she was calling the wrong thing and telling the truth about it.
    #
    # Routed at the PARSER, not the dispatcher, because `print(math.exp(-0.05 * t))` walks
    # into ('print', [None], {}) — the argument is not a literal and the code she meant
    # survives only in the block. So the block goes to run_python whole.
    from harness.toolcore.tools import _parse_tool_calls as _ptc
    _known = {"run_python", "web_search", "check_wardrobe", "recall"}

    _hers = _ptc("```tool_code\nprint(math.exp(-0.05 * 3))\n```", known=_known)
    check("her real `print(...)` fence becomes a run_python call",
          len(_hers) == 1 and _hers[0][0] == "run_python", _hers)
    check("...carrying the WHOLE block, not the unparsed arg",
          _hers and "math.exp" in (_hers[0][2].get("code") or ""), _hers)

    _multi = _ptc("```tool_code\nimport math\nx = 1.0\nfor i in range(3): x *= 0.9\n"
                  "print(round(x, 4))\n```", known=_known)
    check("a multi-line program routes too",
          len(_multi) == 1 and _multi[0][0] == "run_python"
          and "import math" in (_multi[0][2].get("code") or ""), _multi)

    # THE LEG THAT MATTERS: a real tool call must never be hijacked. Without this the
    # routing could be "send everything to run_python", which would break every tool.
    _real = _ptc("```tool_code\ncheck_wardrobe()\n```", known=_known)
    check("a REAL tool call is untouched (the leg that matters)",
          len(_real) == 1 and _real[0][0] == "check_wardrobe", _real)
    _args = _ptc("```tool_code\nrecall('rain')\n```", known=_known)
    check("...including its arguments", _args == [("recall", ["rain"], {})], _args)

    # ...and it cannot fire where run_python is not on the table for this turn.
    _nope = _ptc("```tool_code\nprint(1)\n```", known={"web_search"})
    check("it does not fire when run_python is not offered",
          _nope and _nope[0][0] == "print", _nope)

    # the legacy <tool>{json} form is a different path and must be unaffected
    _legacy = _ptc('<tool name="run_python">{"code": "2+2"}</tool>', known=_known)
    check("the legacy <tool> json form still parses as before",
          _legacy == [("run_python", [], {"code": "2+2"})], _legacy)

    print("\nG-TOOLSAFETY: %s (%d/%d)" % ("PASS" if not FAIL else "FAIL",
                                          PASS, PASS + FAIL))
    if FAIL:
        print("  ^ the assembled toolset is handing her an UNSANDBOXED filesystem verb.")
        print("    Check the concatenation order in harness/agent.py all_tools(): the")
        print("    dedupe is first-wins, so CODING_TOOLS must come before SYSTEM_TOOLS.")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
