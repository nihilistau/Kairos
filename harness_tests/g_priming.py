#!/usr/bin/env python
"""G-PRIMING — a capability that ships unprimed is a capability nobody has.

THE RULE THIS FILE ENFORCES was already written, on the `research` knob in
persona_layers.KNOBS: *"the honesty rule ships WITH the capability, never after it."*
It was true of research and of nothing else.

WHAT THAT COSTS, measured 2026-08-27 against the shipped export:

    82 tools in the manifest, 15 named in the shipped persona — 67 unprimed
    her own persona: 12 fragments.  The export template: 5.
    SEVEN whole groups named nowhere at all: board, body, games, presence, self,
    system, conversation.

An adopter receives a task board, a bookshelf, games, presence modes, body telemetry and
the ability to adjust her own mood — and a persona that mentions none of them. The tool
SCHEMA says what a verb does; the PERSONA says when it is hers to reach for, and without
the second she has hands she does not know are hers. `keep_secret` shipped that way for
exactly one night: the drawer existed, the tool was registered, the manifest had its row,
and she was never told, so it would have stayed empty forever.

THE GRANULARITY IS THE GROUP, not the tool. A persona that lists eleven wardrobe verbs is
a manual, and she does not read manuals — she needs to know she HAS a wardrobe. So each
group in the manifest must be named somewhere in the shipped persona, and a group that
should not be is exempted BY NAME WITH A REASON, which is the pattern g_gate_sandbox's
NOT_A_STORE established for exactly this class of "it is fine, honestly".

OFFLINE. No GPU, no daemon.
"""
import io
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from _gate import sandbox   # noqa: E402
sandbox("g_priming")

os.environ["SP_ENGINE_KIND"] = "openai"
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"

from harness.personality import persona_layers as PL   # noqa: E402
from harness.tools import manifest as MF               # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


# ── GROUPS THAT ARE DELIBERATELY NOT IN THE PERSONA ─────────────────────────────────
# Each one needs a reason a reader can disagree with. "It is obvious" is not a reason;
# `keep_secret` was obvious too.
UNPRIMED_ON_PURPOSE = {
    "meta": "load_tools is the toolset router asking for more tools — machinery she uses "
            "without deciding to, and naming it would invite her to call it as a verb.",
    "delegate": "primed by its own fragment (30-hands, `when: delegate`), which is the "
                "pattern this gate exists to spread rather than an exception to it.",
    "compute": "run_python / run_tests are reached for when a question needs arithmetic "
               "or a test run; the tool description carries that and the disposition adds "
               "nothing. Revisit if she starts narrating instead of running.",
}


def persona_text(directory):
    out = []
    for fn in sorted(os.listdir(directory)):
        if fn.endswith(".md"):
            out.append(io.open(os.path.join(directory, fn), encoding="utf-8").read())
    return "\n".join(out)


def groups():
    g = {}
    for name, facts in MF.FACTS.items():
        g.setdefault(getattr(facts, "group", "?"), []).append(name)
    return {k: sorted(v) for k, v in g.items()}


LIVE = os.path.join(ROOT, "persona")
# THE TEMPLATE MOVES IN THE EXPORT (2026-08-27). Here it is staged under `kairos-export/`;
# there it IS the top-level `persona-template/`. This gate hardcoded the source-repo path,
# so run from inside a fresh export it did not fail — it raised FileNotFoundError and took
# the whole run with it. A gate that cannot survive the tree it ships into is not shipping a
# rule, and AGENTS.md §2 step 3 ("sanity-check the TARGET") is the step that caught it.
# Same detection the scrub gate uses: `kairos-export/` exists only upstream.
TMPL = os.path.join(ROOT, "kairos-export", "persona-template")
if not os.path.isdir(TMPL):
    TMPL = os.path.join(ROOT, "persona-template")
G = groups()

print("1. the shipped persona is a real persona, not a stub")
check("a template exists at all", os.path.isdir(TMPL))
tmpl_files = [f for f in os.listdir(TMPL) if f.endswith(".md")] if os.path.isdir(TMPL) else []
live_files = [f for f in os.listdir(LIVE) if f.endswith(".md")]
# NOT a count comparison — hers is hers and may hold things no adopter wants. What must
# hold is that the shipped one covers the shipped CAPABILITIES, which is section 2.
check("it ships more than a token handful", len(tmpl_files) >= 8,
      "%d fragments: %s" % (len(tmpl_files), sorted(tmpl_files)))

print("\n2. EVERY TOOL GROUP IS PRIMED, or exempted with a reason")
t_text = persona_text(TMPL).lower()
missing = []
for grp, tools in sorted(G.items()):
    if grp in UNPRIMED_ON_PURPOSE:
        continue
    named = [t for t in tools if t.lower() in t_text]
    if named:
        print("  ok   %-14s %d tool(s), named: %s" % (grp, len(tools), ", ".join(named[:3])))
        PASS += 1
    else:
        missing.append((grp, tools))
        print("  FAIL %-14s %d tool(s), NONE named — %s" % (grp, len(tools), ", ".join(tools[:5])))
        FAIL += 1
check("no group is silently unprimed", not missing, [g for g, _ in missing])

print("\n3. an exemption is a claim, and claims are checked")
for grp, why in sorted(UNPRIMED_ON_PURPOSE.items()):
    check("%-10s is a real group" % grp, grp in G, sorted(G))
    check("   ...and its exemption gives a reason", len(why) > 40, why[:40])

print("\n4. every fragment's `when:` names a knob that exists")
# The loader FAILS CLOSED on an unknown knob — a typo silently drops the fragment, so the
# capability ships and its priming does not, which is this gate's whole subject arriving
# through a spelling mistake.
bad = []
for d in (LIVE, TMPL):
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".md"):
            continue
        fm, _body = PL.parse_fragment(io.open(os.path.join(d, fn), encoding="utf-8").read())
        cond = (fm.get("when") or "").strip().lstrip("!")
        if cond and cond not in PL.KNOBS:
            bad.append("%s/%s -> %r" % (os.path.basename(d), fn, cond))
check("no fragment is gated on a knob that does not exist", not bad, bad)

print("\n5. the template does not promise what the export does not ship")
# The reverse failure: priming for a capability an adopter has no code for teaches her to
# reach for something that is not there, which is the confabulation the sight knob's
# comment already warns about ("teaching her about a sense she does not have").
tools_lower = {t.lower() for t in MF.FACTS}
claimed = [w for w in ("delegate_code", "look_at", "take_photo", "research",
                       "keep_secret", "read_journal")
           if w in t_text and w not in tools_lower]
check("every verb the template names is a real tool", not claimed, claimed)

print("\nG-PRIMING: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_priming.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_priming", "pass": PASS, "fail": FAIL,
               "groups": len(G), "tools": len(MF.FACTS),
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
sys.exit(1 if FAIL else 0)
