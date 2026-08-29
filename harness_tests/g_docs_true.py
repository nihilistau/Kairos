"""G-DOCS-TRUE — the docs may not keep describing what was retired. OFFLINE.

THE CLASS. Ceilings and tiers died on 2026-08-21 and docs/AVATAR-PIPELINE.md kept gating
on `roleplay.max_heat` under a front matter that said they were gone; the Grok CLI was
replaced by the REST API and two lines kept "shelling out" to it in the present tense;
three README stubs pointed at a `staging/` that never existed in this repo; AGENTS.md
said "~54 gates" over 149; and a mistyped profile survived in a gate
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
     "`agent` is the retired reference model profile — the live one is companion"),
    (re.compile(r"Migration target \(see MIGRATION-MAP\.md\)"), "2026-08-21",
     "the 1-line README stubs were replaced with real orientation files"),
    # ── 2026-08-29 audit: START-HERE said "`agent` ... still runnable" for THREE DAYS
    # after the profile was deleted, and hid from this gate two ways at once — the
    # command pattern above bans only the literal launch-command form, and the line carried the
    # word "retired", which the amnesty below waves through. "Still runnable" (or
    # present-tense running-ness of a deleted profile) is a CLAIM, not a history note,
    # so it gets its own pattern — and the amnesty word-list cannot save it, because
    # this entry is checked with amnesty=False in the loop below.
    (re.compile(r"still runnable|still boots|can still be (?:run|served|booted)", re.I),
     "2026-08-26",
     "nothing deleted is 'still runnable' — the retired profiles are gone from profiles/"),
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
        _amnesty = any(w in low for w in ("removed", "retired", "replaced", "gone", "died", "history",
                                          "no longer", "used to", "never existed", "was the", "were the",
                                          "until 2026", "before 2026", "first cut", "the old ", "legacy"))
        for pat, when, why in RETIRED:
            # "still runnable" is a live CLAIM even on a line that says "retired" —
            # that exact line hid here for three days (2026-08-29 audit).
            if _amnesty and "still runnable" not in pat.pattern:
                continue
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
# ── AND EVERY ROW PARSES, WHICH IS NOT THE SAME CLAIM (2026-08-28) ────────────────────
# The two checks above ask whether a gate is DOCUMENTED. The sweep asks something else of
# the same rows — which lane is this gate in — and reads it out of a fixed cell. A pipe in
# the DESCRIPTION shifts every later cell along, so the lane comes out as a fragment of the
# sentence before it and the row is quietly not OFFLINE any more. Ten rows were in that
# state and NINE OFFLINE GATES had dropped out of `tools/sweep.py` — g_narrative,
# g_sight_backends, g_control_surface, g_persona_layers, g_backend_seam, g_cfg_derive,
# g_reflection_loop, g_wardrobe, g_marks_leak — while this gate reported the index green,
# because "has a row" was all it ever asked. Write prose pipes as \\| .
sys.path.insert(0, ROOT)
from gates import index_rows as _ix      # noqa: E402  (the sweep's own parser, not a copy)
_bent = _ix.malformed()
check("every GATE-INDEX gate row parses into its five cells", not _bent, _bent[:6])
# AND THE SHAPE IS LOAD-BEARING, so the lane must actually read as a lane.
_lanes = {cs[_ix.LANE].split()[0] for cs, _l in _ix.rows() if len(cs) == _ix.CELLS
          and cs[_ix.LANE]}
_odd = sorted(x for x in _lanes if not x.startswith(("OFFLINE", "LIVE", "VOICE", "SKIP")))
check("...and every lane cell names a lane", not _odd, _odd[:6])
readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
check("README links the four doors (START-HERE, AGENTS, docs/README, GATE-INDEX)",
      all(x in readme for x in ("START-HERE.md", "AGENTS.md", "docs/README.md", "gates/GATE-INDEX.md")))
start = open(os.path.join(ROOT, "START-HERE.md"), encoding="utf-8").read()
check("START-HERE names the live profile and the one door", "serve.py companion" in start and "profiles/companion.toml" in start)
agents = open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8").read()
check("AGENTS.md §2 table names ui/, console/, tools/", all(("| `%s` |" % d) in agents for d in ("ui/", "console/", "tools/")))

# ── 4. THE CHANGELOG IS A LEDGER, SO IT OBEYS A LEDGER'S RULES (2026-08-25) ──────────
# AGENTS.md §6 now says behaviour a reader would notice gets a dated entry in the same
# commit. That is a promise until something checks it — and the two cheap structural
# truths are worth more than a word count: every heading is a REAL DATE (a typo'd
# 2026-18-25 sorts wrong and is invisible for a year), and the entries run NEWEST FIRST
# (a changelog out of order is a changelog nobody trusts twice). Deliberately NOT
# asserted: that the newest entry is recent. That check would go red mid-session, every
# session, and a gate that cries during normal work is a gate people learn to ignore.
import datetime as _dt  # noqa: E402

# TWO TREES, TWO SHAPES, ONE CLAIM (2026-08-25). This gate SHIPS in the Kairos export,
# where the DATED log under docs/ deliberately does not: that log is this tree's history,
# including engine work the framework has no engine for, and the export carries a semver
# `CHANGELOG.md` at the root instead. Asserting the upstream shape unconditionally would
# have shipped a red gate to the public repo — which is the exact failure 0.2.1 was
# released to fix, so this file is not going to be how it happens again. The CLAIM in both
# trees is the same: this tree keeps a changelog, and it is ordered.
chpath = os.path.join(ROOT, "docs", "CHANGELOG.md")
export_ch = os.path.join(ROOT, "CHANGELOG.md")
check("this tree keeps a changelog (dated upstream, semver in the export)",
      os.path.exists(chpath) or os.path.exists(export_ch))
if not os.path.exists(chpath) and os.path.exists(export_ch):
    exp = open(export_ch, encoding="utf-8").read()
    vers = re.findall(r"^## (\d+\.\d+\.\d+)", exp, re.M)
    check("...the export's is versioned, newest first", len(vers) >= 1 and vers == sorted(
        vers, key=lambda v: [int(x) for x in v.split(".")], reverse=True), vers)
elif os.path.exists(chpath):
    ch = open(chpath, encoding="utf-8").read()
    heads = re.findall(r"^## (\d{4}-\d{2}-\d{2})", ch, re.M)
    check("...with dated entries (## YYYY-MM-DD)", len(heads) >= 5, len(heads))
    bad = []
    for h in heads:
        try:
            _dt.date.fromisoformat(h)
        except ValueError:
            bad.append(h)
    check("...every heading is a real date", not bad, bad)
    check("...newest first", heads == sorted(heads, reverse=True),
          [h for i, h in enumerate(heads[:-1]) if h < heads[i + 1]][:4])
    check("...and the semver changelog is the EXPORT's, named as such",
          "kairos-export/CHANGELOG.md" in ch)

# ── 5. A LINK THAT GOES NOWHERE IS A DOC DESCRIBING SOMETHING THAT IS NOT THERE ──────
# THE SAME CLASS THIS FILE IS ABOUT, one layer down (2026-08-25). Sections 1-4 hold what
# the prose SAYS; nothing held where it POINTS. Measured in the public export the day this
# was written: 24 relative markdown links resolving to nothing — including `README.md ->
# ui/README.md` (never in the manifest) and five files naming `CHANGELOG.md`, which
# that tree deliberately does not ship. A newcomer's first click, on the front page.
#
# RELATIVE LINKS ONLY, and deliberately only real markdown links: backticked bare names
# like `app.py` are prose shorthand, not promises, and gating them would fail on 235
# innocent mentions and be switched off within a day. http(s), mailto and pure anchors
# are somebody else's problem.
#
# It runs in BOTH trees off the same list, so the export cannot drift into dangling links
# again without a red — which is exactly the 0.2.1 lesson (upstream-green is not
# export-green) applied to prose instead of to gates.
print("\n5. EVERY RELATIVE LINK IN A SHIPPED DOC RESOLVES")
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)")
_dangling = []
for p in PROSE:
    base = os.path.dirname(p)
    rel = os.path.relpath(p, ROOT).replace("\\", "/")
    for n, line in _prose_lines(p):
        for m in _LINK.finditer(line):
            t = m.group(1).split("#")[0].strip()
            if not t or t.startswith(("http://", "https://", "mailto:", "#")):
                continue
            if not os.path.exists(os.path.join(base, t)):
                _dangling.append("%s:%d -> %s" % (rel, n, t))
for d in _dangling[:12]:
    print("       " + d)
check("no shipped doc links to a file that is not there", not _dangling,
      "%d dangling" % len(_dangling))

finish("G-DOCS-TRUE")
