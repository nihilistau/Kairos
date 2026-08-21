"""G-DOCS-TRUE — the docs may not keep describing what was retired. OFFLINE.

THE CLASS. Ceilings and tiers died on 2026-08-21 and docs/AVATAR-PIPELINE.md kept gating
on `roleplay.max_heat` under a front matter that said they were gone; the Grok CLI was
replaced by the REST API and two lines kept "shelling out" to it in the present tense;
three README stubs pointed at a `staging/` that never existed in this repo; AGENTS.md
said "~54 gates" over 149; and `python serve.py agent` (the 12B) survived in a gate
write-up. Each was true once. A doc that describes a retired thing in the present tense
is the 3am trap AGENTS.md §6 warns about, wearing a different coat.

RETIRED VOCABULARY carries the date it was retired. A History section (a heading containing
"History") and GATE-INDEX rows that open with a dated NO-CEILING marker are allow-listed —
the past is allowed to be described as the past.

    python harness_tests/g_docs_true.py
"""
from __future__ import annotations

import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, utf8_stdout  # noqa: E402

utf8_stdout()

PROSE = ([os.path.join(ROOT, f) for f in ("README.md", "START-HERE.md", "AGENTS.md", "CLAUDE.md",
                                           "harness/README.md", "engine/README.md", "ui/README.md",
                                           "console/README.md", "tools/README.md", "gates/README.md")]
         + sorted(glob.glob(os.path.join(ROOT, "docs", "*.md"))))
PROSE = [p for p in PROSE if os.path.exists(p)]

# (pattern, retired-on, why) — matched per LINE, outside fenced code, outside History sections
RETIRED = [
    (re.compile(r"roleplay\.max_heat|allowed_tiers|within your ceiling|held by your ceiling"), "2026-08-21",
     "wardrobe/avatar ceilings and tiers were removed — she or he decide limits in words"),
    (re.compile(r"(shells out to|drives|calls|invokes|uses) the Grok CLI", re.I), "2026-08-21",
     "the Grok CLI was replaced by the xAI REST API (harness/skills/xai.py)"),
    (re.compile(r"Staging source remains canonical|\bstaging/\b"), "never",
     "there is no staging/ directory in this repo; the migration happened"),
    (re.compile(r"~54"), "2026-08-21", "the gate count is ~150 g_*.py; see GATE-INDEX"),
    (re.compile(r"speechSynthesis"), "2026-08-21", "her voice is the xAI API + the room's speech.js"),
    (re.compile(r"python serve\.py agent(?!-26b)\b"), "2026-08-03",
     "`agent` is the 12B profile — the live one is companion"),
    (re.compile(r"Migration target \(see MIGRATION-MAP\.md\)"), "2026-08-21",
     "the 1-line README stubs were replaced with real orientation files"),
]


def _prose_lines(path):
    """Yield (lineno, line) outside fenced code and outside History sections."""
    text = open(path, encoding="utf-8", errors="replace").read()
    in_code = False
    in_history = False
    for n, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if line.startswith("#"):
            in_history = "history" in line.lower()
        if in_code or in_history:
            continue
        yield n, line


print("1. RETIRED VOCABULARY IS NOT DESCRIBED IN THE PRESENT TENSE")
hits = []
for p in PROSE:
    rel = os.path.relpath(p, ROOT).replace("\\", "/")
    for n, line in _prose_lines(p):
        # a line that itself says the thing is retired/removed/gone is allowed to name it
        low = line.lower()
        if any(w in low for w in ("removed", "retired", "replaced", "gone", "died", "history",
                                  "no longer", "used to", "never existed", "was the", "were the",
                                  "until 2026", "before 2026", "first cut", "the old ", "legacy")):
            continue
        for pat, when, why in RETIRED:
            if pat.search(line):
                hits.append("%s:%d  [%s, retired %s] %s" % (rel, n, pat.pattern[:28], when, line.strip()[:90]))
for h in hits:
    print("       " + h)
check("no prose doc describes a retired thing in the present tense", not hits, "%d hits" % len(hits))

print("\n2. THE TWO GATE-INDEX ROWS THAT CARRIED CEILING LANGUAGE WEAR THEIR HISTORY MARKER")
idx = open(os.path.join(ROOT, "gates", "GATE-INDEX.md"), encoding="utf-8").read()
for name in ("G-AVATAR", "G-WARDROBE"):
    row = next((l for l in idx.splitlines() if l.startswith("| %s |" % name)), "")
    check("%s row opens with the dated NO CEILING marker" % name,
          row.startswith("| %s | `harness_tests/" % name) and "NO CEILING since 2026-08-21" in row[:400])

print("\n3. STRUCTURAL TRUTHS")
docs_index = open(os.path.join(ROOT, "docs", "README.md"), encoding="utf-8").read()
missing = [os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "docs", "*.md"))
           if os.path.basename(p) != "README.md" and os.path.basename(p) not in docs_index]
check("every docs/*.md is in docs/README.md", not missing, missing)
nofm = [os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "docs", "*.md"))
        if not open(p, encoding="utf-8", errors="replace").read().startswith("---")]
check("every docs/*.md carries front matter (type/title/status)", not nofm, nofm)
gates = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "harness_tests", "g_*.py")))
unindexed = [g for g in gates if ("`harness_tests/%s`" % g) not in idx]
check("every harness_tests/g_*.py has a GATE-INDEX row", not unindexed, unindexed[:8])
# ROWS, not mentions: the index's prose may name a gate that was removed or lives
# elsewhere (the history notes do); the rows are the claims.
rowfiles = [m.group(1) for l in idx.splitlines() if l.startswith("| G-") or l.startswith("| H-")
            for m in [re.search(r"`harness_tests/([gh]_[a-z0-9_]+\.py)`", l)] if m]
dead = sorted({f for f in rowfiles if not os.path.exists(os.path.join(ROOT, "harness_tests", f))})
check("every GATE-INDEX row's file exists", not dead, dead[:8])
readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
check("README links the four doors (START-HERE, AGENTS, docs/README, GATE-INDEX)",
      all(x in readme for x in ("START-HERE.md", "AGENTS.md", "docs/README.md", "gates/GATE-INDEX.md")))
start = open(os.path.join(ROOT, "START-HERE.md"), encoding="utf-8").read()
check("START-HERE names the live profile and the one door", "serve.py companion" in start and "profiles/companion.toml" in start)
agents = open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8").read()
check("AGENTS.md §2 table names ui/, console/, tools/", all(("| `%s` |" % d) in agents for d in ("ui/", "console/", "tools/")))

finish("G-DOCS-TRUE")
