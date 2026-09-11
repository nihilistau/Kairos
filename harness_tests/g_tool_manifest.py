"""G-TOOL-MANIFEST — every tool she has is documented, and the manifest cannot rot.
OFFLINE.

The manifest is only worth having if it CANNOT drift from the code. Documentation
that is merely encouraged is documentation that is out of date, and this repo has
paid for that lesson repeatedly — which is why the SP_* closure check in
g_sem_conserve exists and why it keeps catching things (three times this week,
including twice on my own commits).

So the rule enforced here is exactly that one, applied to tools:

    A LIVE TOOL WITHOUT A MANIFEST ROW IS A GATE FAILURE.

Run: python harness_tests/g_tool_manifest.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Arm everything, so the gate sees the WIDEST surface she can ever have rather
# than whatever this shell happens to have on. A tool documented only when its
# knob is off is not documented.
os.environ.setdefault("SP_MODEL_PATH", "models/your model.sp-model")   # the BASENAME picks the capability row; the dir is irrelevant
# SP_MCP_TOOLS included since 2026-07-31: without it the gate could not see BRIDGED
# tools at all, and it duly passed while six browser tools sat undocumented — a
# coverage gate blind to a whole tier is worse than none, because it certifies the
# gap. The room's Tools panel is what surfaced it, which is the argument for
# rendering a manifest rather than only asserting one.
# SP_AUX arms deep_recall, which imports the sidecar archive, which imports numpy at
# module level — so on a clone without the [media] extra, arming it asked describe()
# to enumerate a tool that cannot be imported and took the whole census down before
# its first check. The manifest rule is about DOCUMENTATION, not about the sidecar:
# drop the one tool that cannot be here and grade the rest (2026-09-11).
from _gate import have as _have, omit as _omit   # noqa: E402
_AUX_OK = _have("numpy")
for _k in ("SP_DELEGATE", "SP_PERSONALITY", "SP_MCP_TOOLS", "SP_RESEARCH") + (("SP_AUX", "SP_SIGHT") if _AUX_OK else ()):   # SP_AUX: deep_recall joins only when armed (2026-08-21)
    os.environ[_k] = "1"
if not _AUX_OK:
    # SIGHT IS THE SAME SHAPE AND WORSE: `sight_tools` SWALLOWS the ImportError and
    # registers nothing, so arming SP_SIGHT without numpy does not raise — it produces
    # an empty sight surface and the assertion below convicts the gate instead of the
    # absence. A swallowed dependency is exactly why `loud.swallowed` logs.
    _omit("deep_recall and the sight tools in the enumerated surface",
          'numpy is not installed — pip install -e ".[media]"')
# The research tools register only when xai.available() — i.e. when a key exists. This gate
# lists tools, it never calls one; a placeholder in the env spelling (which wins over the
# key FILE) makes the tool set the same on a machine with no key (the Kairos export).
os.environ.setdefault("SP_XAI_API_KEY", "gate-placeholder-not-a-key")
os.environ.setdefault("SP_NOTES", "1")

from harness.tools import manifest as M  # noqa: E402

_P = _F = 0


def ok(cond, name, detail=""):
    global _P, _F
    if cond:
        _P += 1
        print(f"  ok   {name}")
    else:
        _F += 1
        print(f"  FAIL {name}   {detail}")


d = M.describe()

print("1. every live tool is documented")
ok(d["undocumented"] == [], "no live tool lacks a manifest row", d["undocumented"])
ok(d["counts"]["total"] > 20, "the surface is actually being enumerated",
   d["counts"])
ok(d["counts"]["core"] + d["counts"]["extra"] == d["counts"]["total"],
   "core + extra accounts for every tool", d["counts"])

print("\n2. the metadata is well-formed")
bad_group = [r["name"] for r in d["tools"] if r["group"] not in M.GROUPS]
bad_risk = [r["name"] for r in d["tools"] if r["risk"] not in M.RISK]
ok(not bad_group, "every group is a declared group", bad_group)
ok(not bad_risk, "every risk is a declared risk class", bad_risk)

print("\n3. orphan rows are only for tools that are CONDITIONAL, not stale")
# A row with no live tool is allowed ONLY if the tool is knob-armed, bridged, or
# synthetic — otherwise it is a row for something that no longer exists, which is
# the manifest rotting in the other direction.
ALLOWED_ORPHANS = {
    "disk_free",       # bridged over MCP; needs SP_MCP_TOOLS and a live server
    "load_tools",      # synthetic, minted by build_tool_system, not in any list
    "complete_note",   # task-bridge tier
    "count_memories",  # exported conditionally
}
# KNOB-ARMED ROWS EXCUSE THEMSELVES, by declaration rather than by a hardcoded name.
# The comment above already said conditional tools are allowed to be orphans; the
# implementation only allowed four listed by hand, so every new armed pack had to be
# pasted in here — and a list you must remember to update is the coupling that lives in
# someone's memory, which is the thing AGENTS.md §0 is about. A row that names an `arms`
# knob IS the declaration that the tool comes and goes with it.
#
# The check does not weaken: the excuse applies ONLY while that knob is off. A tool
# missing while its own knob is ON is still a failure, and still caught.
armed_off = {name for name, f in M.FACTS.items()
             if getattr(f, "arms", None) and os.environ.get(f.arms, "0") != "1"}

# ── AND A PROVIDER'S OWN PRECONDITION IS NOT AN ENV KNOB (2026-09-11) ─────────────────
# The music tools register only when a music library actually EXISTS on disk
# (`music.music_tools`: *"Absent unless a library actually exists — a tool that always
# answers 'no music' is worse than one that is not there, because she keeps reaching."*).
# On the operator's box `~/Music` is there and they register; on a CI runner it is not, so
# all five rows read as documentation for tools that do not exist and this leg convicted
# them. It surfaced the first time this suite ran on Linux.
#
# `arms="SP_MUSIC"` would be the WRONG fix and the tempting one. `armed_off` excuses a row
# when its knob is not "1", and `SP_MUSIC` DEFAULTS ON (`os.environ.get("SP_MUSIC", "1")`)
# — so an unset SP_MUSIC means the deck is armed and the LIBRARY is missing. The row would
# then be excused for a reason that is not the true one, which is a green bought with a
# false statement.
#
# So the gate asks the PROVIDER, which is the only thing that knows its own precondition,
# and derives the names from `_specs()` rather than keeping a second copy of them here —
# the same argument the `armed_off` comment above makes about hand-listed excuses.
absent_by_provider = set()
try:
    from harness.skills import music as _music
    if not _music.music_tools():
        absent_by_provider = {getattr(s, "name", "") for s in _music._specs()}
        _omit("the music deck in the enumerated surface",
              "no music library at %s" % _music.DIR)
except Exception as _exc:                                    # noqa: BLE001
    print("  --   could not ask the music provider (%s)" % _exc)

stale = sorted(set(d["orphan_rows"]) - ALLOWED_ORPHANS - armed_off - absent_by_provider)
ok(not stale, "no manifest row describes a tool that does not exist", stale)
# AND THE EXCUSE IS NOT A BLANKET ONE: whatever the provider DOES offer must still be
# documented, so a row deleted while its tool lives is still caught.
ok(not (absent_by_provider & {r["name"] for r in d["tools"]}),
   "...and a provider that declines its tools really offers none of them",
   sorted(absent_by_provider & {r["name"] for r in d["tools"]}))

print("\n4. the dangerous things are LABELLED as dangerous")
risk_of = {r["name"]: r["risk"] for r in d["tools"]}
for name, want in (("take_photo", "private"), ("take_screenshot", "private"),
                   ("run_shell", "machine"), ("run_python", "machine"),
                   ("write_file", "machine"), ("web_fetch", "world"),
                   ("delegate_code", "machine")):
    if name in risk_of:
        ok(risk_of[name] == want, f"{name} is risk={want}", risk_of.get(name))

print("\n5. sight is armed-gated, and says so")
sight = [r for r in d["tools"] if r["group"] == "sight"]
if _AUX_OK:
    ok(sight, "sight tools are present when SP_SIGHT=1", len(sight))
else:
    # SP_SIGHT was not armed above, so an empty sight group is the correct answer here
    # rather than a missing one. The rule that still holds without numpy is the one
    # below: whatever sight tools DO exist must name the knob that arms them.
    _omit("sight tools are present when SP_SIGHT=1", "SP_SIGHT not armed: numpy absent")
ok(all(r["arms"] == "SP_SIGHT" for r in sight),
   "every sight tool names the knob that arms it",
   [(r["name"], r["arms"]) for r in sight])

print("\n6. forget is not a delete, and the manifest says so")
f = next((r for r in d["tools"] if r["name"] == "forget"), None)
ok(f is not None and "tombstone" in (f["note"] or "").lower(),
   "forget's row records that it tombstones",
   f["note"] if f else "absent")

print(f"\nG-TOOL-MANIFEST: {_P} pass, {_F} fail")
sys.exit(1 if _F else 0)
