#!/usr/bin/env python
"""G-DELEGATE — she may write code; she may not land it, and she may not touch the engine.

The operator's arrangement, and this gate is its enforcement:

    AUTONOMY       worktree + gates; HE MERGES. She never lands anything.
    BLAST RADIUS   harness/, harness_tests/, docs/, profiles/, gates/, fixtures/ writable.
                   .rs, .cu, serve.py, engine/, core/ READ-ONLY.

WHY THE FLAGS ARE NOT WHAT THIS GATE TRUSTS
───────────────────────────────────────────
`~/.grok/config.toml` on this machine says `permission_mode = "always-approve"`, so every call
must pass `--permission-mode` and `--deny` EXPLICITLY rather than inherit — and §2 asserts it
does. But a rule you must remember to pass is a rule you will forget, `--deny`'s grammar is
resolved out of `~/.claude/settings.json` (a file neither this module nor this gate controls),
and a mis-spelled rule fails OPEN.

So the authority is §3: THE VERDICT ON THE DIFF THAT ACTUALLY HAPPENED. §4 proves it end to end
against a SIMULATED ROGUE AGENT that ignores every flag and edits `engine/src/main.rs` — the
delegation is refused, the gates are not even run, and nothing is merged. That is the test that
matters: not "did we pass the right flags" but "what happens when the flags did nothing".

NOTHING IS SPAWNED. The subprocess runner is injected, so this gate never invokes the real
coding agent, never costs a token, and never writes to the tree.

OFFLINE. No GPU, no daemon, no network.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ.setdefault("SP_DAEMON_URL", "http://127.0.0.1:9")
os.environ["SP_DELEGATE"] = "1"

from harness.skills import delegate as D  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


print("1. the blast radius is a default-NO allow-list")
check("harness/ is writable", D.classify(["harness/skills/x.py"])["allowed"])
check("harness_tests/ is writable", D.classify(["harness_tests/g_x.py"])["allowed"])
check("docs/ is writable", D.classify(["docs/X.md"])["allowed"])
check("profiles/ and gates/ are writable",
      D.classify(["profiles/a.toml", "gates/G.md"])["allowed"] ==
      ["profiles/a.toml", "gates/G.md"])
for p in ("engine/src/main.rs", "core/x.h", "engine/src/backends/cuda/cuda_forward.cu",
          "serve.py", "harness/x.rs"):
    check("READ-ONLY: %s" % p, D.classify([p])["engine"] == [p.replace("\\", "/")],
          D.classify([p]))
# The property that keeps it correct as the repo grows: anything NOT anticipated is refused.
for p in ("README.md", "console/index.html", ".github/workflows/ci.yml", "setup.py",
          "var/memory/registry.jsonl", "persona.md"):
    check("UNANTICIPATED path is refused, not allowed: %s" % p,
          D.classify([p])["outside"] == [p], D.classify([p]))
check("a windows path is normalised before judging",
      D.classify(["engine\\src\\main.rs"])["engine"] == ["engine/src/main.rs"])
check("a leading ./ does not smuggle anything past",
      D.classify(["./engine/src/main.rs"])["engine"] == ["engine/src/main.rs"])
# THE HOLE THIS GATE FOUND, kept as a regression. The first cut normalised with
# `lstrip("./")`, which strips those as a CHARACTER SET rather than a prefix: ".github/x"
# became "github/x", and — the actual hole — ".harness/evil.py" became "harness/evil.py",
# WHICH IS AN ALLOWED PATH. A dotfile directory normalised straight through the blast radius.
check("a dotfile directory is NOT normalised into a writable root",
      D.classify([".harness/evil.py"])["allowed"] == [], D.classify([".harness/evil.py"]))
check("...and is refused as outside", D.classify([".harness/evil.py"])["outside"]
      == [".harness/evil.py"], D.classify([".harness/evil.py"]))
check("the dotfile name survives intact in the report",
      D.classify([".github/workflows/ci.yml"])["outside"] == [".github/workflows/ci.yml"],
      D.classify([".github/workflows/ci.yml"]))
check("a traversal component is refused outright",
      D.verdict_for(["harness/../engine/src/main.rs"])[0] == D.REFUSED,
      D.classify(["harness/../engine/src/main.rs"]))
check("an absolute path is REFUSED, not normalised into a relative allowed one",
      D.verdict_for(["/harness/x.py"])[0] == D.REFUSED, D.classify(["/harness/x.py"]))
check("a drive-letter path likewise",
      D.verdict_for([r"C:\harness\x.py"])[0] == D.REFUSED,
      D.classify([r"C:\harness\x.py"]))

print("\n2. every safety flag is passed EXPLICITLY (the user config says always-approve)")
argv = D.build_argv("do a thing", cwd="/tmp/wt/sp-thing")
def flag(name):
    return argv[argv.index(name) + 1] if name in argv else None
check("--permission-mode is passed explicitly (the user config says always-approve)",
      flag("--permission-mode") == "auto", flag("--permission-mode"))
check("...and it is never bypassPermissions",
      flag("--permission-mode") != "bypassPermissions")
check("--always-approve is NEVER passed", "--always-approve" not in argv)
check("--worktree is NOT passed — measured inert in headless -p, and an inert safety flag "
      "is worse than none", "--worktree" not in argv)
check("--cwd is THE WORKTREE, not the repo — the containment we built ourselves",
      flag("--cwd") == "/tmp/wt/sp-thing", flag("--cwd"))
check("--max-turns bounds the run", flag("--max-turns") == str(D.DEFAULT_MAX_TURNS))

check("subagents are off (each would need its own copy of every rule)",
      "--no-subagents" in argv)
check("web access is off", "--disable-web-search" in argv)
denies = [argv[i + 1] for i, a in enumerate(argv) if a == "--deny"]
check("engine source is denied by rule", any(".rs" in d for d in denies)
      and any("engine/**" in d for d in denies), denies[:4])
check("serve.py is denied by rule", any("serve.py" in d for d in denies))
check("push / merge / reset are denied by rule",
      all(any(k in d for d in denies) for k in ("git push", "git merge", "git reset")), denies)
check("every deny rule reaches the command line",
      len(denies) == len(D.DENY_RULES), (len(denies), len(D.DENY_RULES)))

print("\n3. the verdict on the diff is the authority")
check("a clean harness-only diff is CLEAN",
      D.verdict_for(["harness/skills/x.py", "harness_tests/g_x.py"])[0] == D.CLEAN)
check("ONE engine file refuses the WHOLE delegation",
      D.verdict_for(["harness/skills/x.py", "engine/src/main.rs"])[0] == D.REFUSED)
check("...and the reason names it",
      "engine" in D.verdict_for(["engine/src/main.rs"])[1].lower())
check("one out-of-radius file refuses the whole delegation",
      D.verdict_for(["harness/x.py", "README.md"])[0] == D.REFUSED)
check("serve.py alone refuses", D.verdict_for(["serve.py"])[0] == D.REFUSED)
check("no change at all is FAILED, not CLEAN", D.verdict_for([])[0] == D.FAILED)
check("a RENAME is judged on both sides",
      D.verdict_for(["harness/a.py", "engine/b.rs"])[0] == D.REFUSED)

print("\n4. a ROGUE AGENT that ignores every flag is still stopped")
# The whole point. This runner pretends Grok honoured nothing: it "edits" engine source.
class FakeProc:
    returncode = 0
    stdout = "{}"
    stderr = ""


calls = {"n": 0, "gates_run": 0}


def rogue(argv):
    calls["n"] += 1
    return FakeProc()


D._make_worktree = lambda root, branch: (os.path.join(ROOT, "_fake_wt"), "created")
D._changed_paths = lambda wt, base="HEAD": ["harness/skills/ok.py", "engine/src/main.rs"]
_real_gates = D._run_gates


def counting_gates(wt, **kw):
    calls["gates_run"] += 1
    return {"passed": ["all"], "failed": [], "summary": "99/99"}


D._run_gates = counting_gates
D._receipt = lambda rec: None

out = D.delegate_code("make it faster", run=rogue)
check("the coding agent WAS invoked (the test is not vacuous)", calls["n"] == 1)
check("the delegation is refused", "not offering it" in out, out)
check("the refusal names the engine file", "engine/src/main.rs" in out, out)
check("THE GATES ARE NOT RUN — a green suite beside a bad diff reads as reassurance",
      calls["gates_run"] == 0, calls["gates_run"])
check("the branch is still named, so he can look (nothing is deleted)",
      "sp/make-it-faster" in out, out)
check("nothing claims to have merged", "merge" not in out.lower(), out)

print("\n5. a well-behaved run reports, and still does not merge")
D._changed_paths = lambda wt, base="HEAD": ["harness/skills/ok.py", "docs/X.md"]
out = D.delegate_code("tidy the docs", run=rogue)
check("it reports the branch", "sp/tidy-the-docs" in out, out)
check("it reports the file count", "2 file(s)" in out, out)
check("it reports the gate result", "99/99" in out, out)
check("THE GATES DID run this time", calls["gates_run"] == 1, calls["gates_run"])
check("IT SAYS IT HAS NOT MERGED", "haven't merged" in out, out)
check("...and that merging is his", "that's yours" in out, out)

print("\n6. it cannot merge, because nothing in it can")
import inspect  # noqa: E402

src = inspect.getsource(D)
for forbidden in ("git merge", "git push", "git commit", "checkout main", "checkout master"):
    # DENY_RULES legitimately names these; the check is that no COMMAND is built from them.
    body = src.split("DENY_RULES", 1)[1].split(")", 1)[1] if "DENY_RULES" in src else src
    check("no %r command is constructed anywhere" % forbidden,
          ('"%s"' % forbidden) not in body and ("'%s'" % forbidden) not in body)
check("the only subprocess calls are grok, git worktree list, git status, and the gates",
      sorted({m for m in ("worktree", "status", "python") if m in src}) ==
      ["python", "status", "worktree"])

print("\n7. the gate list is the PORTABLE set, not the important set")
# The first live delegation reported "Gates 6/8 (failing: g_durability, g_onedoor)" for a
# change that added one docs file. A fresh worktree has no var/memory/ — the store is
# gitignored — so those two fail there for ANY change, forever. A number that is always red
# teaches him to ignore the number.
check("the store-dependent gates are NOT in the delegated set",
      not (set(D.OFFLINE_GATES) & set(D.STORE_DEPENDENT_GATES)),
      set(D.OFFLINE_GATES) & set(D.STORE_DEPENDENT_GATES))
check("the exclusions are named, with their reason in the source",
      D.STORE_DEPENDENT_GATES == ("g_durability", "g_onedoor"), D.STORE_DEPENDENT_GATES)
check("the delegated set is not trivially small", len(D.OFFLINE_GATES) >= 10,
      len(D.OFFLINE_GATES))
# The g_sem_* gates score the operator's own corpus (harness_tests/fixtures/sem) and do not
# ship in the Kairos export; _run_gates skips a missing file, so their absence is the
# documented exclusion there, not a defect. Anything ELSE missing still is.
_absent = [g for g in D.OFFLINE_GATES
           if not os.path.exists(os.path.join(ROOT, "harness_tests", g + ".py"))]
# In the Kairos export (KAIROS-SOURCE.txt at the root) the list is a superset by design: the
# corpus gates (g_sem_*) and the profile walker (g_onewriter) stay in the source repo and
# _run_gates skips a missing file. Here, in the source, every name must exist.
_export = os.path.exists(os.path.join(ROOT, "KAIROS-SOURCE.txt"))
if _export and _absent:
    print("       (export tree: delegated gates not shipped, skipped at run time: %s)" % ", ".join(_absent))
check("every delegated gate actually exists in this tree (or is a named non-shipping gate in the export)",
      _absent == [] or _export,
      [g for g in D.OFFLINE_GATES
       if not os.path.exists(os.path.join(ROOT, "harness_tests", g + ".py"))])

print("\n8. the knob")
os.environ["SP_DELEGATE"] = "0"
check("off: nothing is spawned", D.delegate_code("do a thing", run=rogue) and calls["n"] == 2)
check("off: it says so plainly", "switched off" in D.delegate_code("x", run=rogue))
os.environ["SP_DELEGATE"] = "1"
check("an empty goal does nothing", "need to know" in D.delegate_code("", run=rogue))

D._run_gates = _real_gates
print("\nG-DELEGATE: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_delegate.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_delegate", "pass": PASS, "fail": FAIL,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
sys.exit(1 if FAIL else 0)
