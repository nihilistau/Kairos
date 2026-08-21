"""G-KAIROS-SCRUB — the public tree carries no one's name, paths, secrets or stores. OFFLINE.

Ships in the Kairos export and runs there; in the source repo it runs against the export
target (KAIROS_TARGET, default ../Kairos) and skips when there is none. The rule it holds
(memory: "scrub before pushing public"): the operator's handle and his companion's inferences
about him come out; everyday facts may stay; nothing under var/, persona/, memory-okf*,
no key files, no absolute machine paths, no source-only profiles.

    python harness_tests/g_kairos_scrub.py
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _gate import check, finish, skip, utf8_stdout  # noqa: E402

utf8_stdout()
ROOT = os.path.dirname(HERE)
# In the source repo this file lives beside the exporter; the TREE under test is the target.
if os.path.exists(os.path.join(ROOT, "kairos-export", "kairos-export.toml")):
    ROOT = os.environ.get("KAIROS_TARGET") or os.path.normpath(os.path.join(ROOT, "..", "Kairos"))
    if not os.path.isdir(ROOT):
        skip("no export target at %s — run tools/kairos_export.py first" % ROOT, "G-KAIROS-SCRUB")

FORBIDDEN = ["Sam", "sam112358", "D:/F/", "D:\\F\\", "agent-26b", "gemma4-26b"]
TEXT = (".py", ".md", ".toml", ".txt", ".json", ".jsx", ".js", ".css", ".html", ".bat", ".sh", ".yml")

print("1. NO FORBIDDEN TOKEN SURVIVES IN ANY TEXT FILE")
hits = []
n_files = 0
for dp, dns, fns in os.walk(ROOT):
    # var/ and persona/ are the tree's LOCAL state (gitignored there; never exported) — the
    # running companion's token and registry live in them by design
    dns[:] = [d for d in dns if d not in (".git", "node_modules", "__pycache__", "var", "persona")]
    for fn in fns:
        if not fn.endswith(TEXT) and fn != ".gitignore":
            continue
        p = os.path.join(dp, fn)
        n_files += 1
        try:
            txt = open(p, encoding="utf-8").read()
        except UnicodeDecodeError:
            continue
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        if rel == "harness_tests/g_kairos_scrub.py":
            continue                                  # this file names the tokens it forbids
        for tok in FORBIDDEN:
            if tok in txt:
                ln = next((i for i, l in enumerate(txt.splitlines(), 1) if tok in l), 0)
                hits.append("%s:%d  %s" % (rel, ln, tok))
check("%d text files scanned, zero forbidden tokens" % n_files, not hits, hits[:12])

print("\n2. NOTHING OF HERS OR HIS IS IN THE TREE")
# "in the export" means TRACKED (or present, when the tree has no git yet): a running companion
# makes its own var/ and persona/ beside the code, and those are gitignored there by design.
def _tracked():
    try:
        import subprocess
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True)
        if out.returncode == 0 and os.path.isdir(os.path.join(ROOT, ".git")):
            return {p.decode("utf-8", "replace") for p in out.stdout.split(b"\x00") if p}
    except Exception:
        pass
    return None
_T = _tracked()
for d in ("var", "persona", "memory-okf", "memory-okf-personality", "_task_state", "engine", "core", "papers"):
    if _T is not None:
        check("no %s/ in the export (tracked)" % d, not any(p.startswith(d + "/") for p in _T))
    else:
        check("no %s/ in the export" % d, not os.path.isdir(os.path.join(ROOT, d)))
bad_profiles = [f for f in os.listdir(os.path.join(ROOT, "profiles")) if f.startswith("agent")] \
    if os.path.isdir(os.path.join(ROOT, "profiles")) else []
check("no source-only profiles (agent*.toml)", not bad_profiles, bad_profiles)
check("profiles/companion.toml ships", os.path.exists(os.path.join(ROOT, "profiles", "companion.toml")))
keyish = []
for dp, dns, fns in os.walk(ROOT):
    dns[:] = [d for d in dns if d not in (".git", "node_modules", "var", "persona")]
    for fn in fns:
        if fn.endswith((".py", ".md", ".jsx", ".js")):
            continue                                  # code and docs may be ABOUT secrets
        if re.search(r"(secret|token|\.env$|api[_-]?key|\.pem$|\.key$)", fn, re.I):
            keyish.append(os.path.relpath(os.path.join(dp, fn), ROOT))
check("no key/secret-shaped files", not keyish, keyish)
check("persona-template/ ships and persona/ is gitignored",
      os.path.isdir(os.path.join(ROOT, "persona-template"))
      and "persona/" in open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read())
check("KAIROS-SOURCE.txt names the source commit",
      os.path.exists(os.path.join(ROOT, "KAIROS-SOURCE.txt"))
      and "exported from" in open(os.path.join(ROOT, "KAIROS-SOURCE.txt"), encoding="utf-8").read())
check("LICENSE and README ship", os.path.exists(os.path.join(ROOT, "LICENSE")) and os.path.exists(os.path.join(ROOT, "README.md")))
if _T is not None:
    # The first fresh clone (2026-08-21) had NO harness/**/__init__.py and no harness_tests/_gate.py:
    # the overlay .gitignore carried an unanchored `_*.py`. A tree that imports by accident
    # (namespace packages) is one refactor away from not importing at all.
    _inits = [p for p in _T if p.startswith("harness/") and p.endswith("/__init__.py")]
    check("harness/**/__init__.py are TRACKED (%d)" % len(_inits), len(_inits) >= 10, len(_inits))
    check("harness_tests/_gate.py is TRACKED", "harness_tests/_gate.py" in _T)

finish("G-KAIROS-SCRUB")
