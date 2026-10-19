"""G-EPS-COLD-RULE — which episodes may leave the hot disk, as a finite table. OFFLINE.

D2 (spec §6, confirmed §9): "an episode is cold when its row is tombstoned and has been for
more than 30 days, it is not `core`, and no live distillate names it in `derived_from`. A
support folded into a live distillate counts as standing, so it stays warm."

Rule 5: a finite table with named fields, not a prose conditional. lifecycle.EPS_COLD_RULE
holds the four clauses, and `_EPS_COLD_TESTS` holds exactly one test per clause.
`eps_cold_verdict` names the first clause that keeps a row hot, so every fixture row below
convicts exactly one clause. A mutant that disables a clause turns its row "cold", and the
leg named for that row goes red.

    python harness_tests/g_eps_cold_rule.py
"""
import calendar
import inspect
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from harness_tests._gate import sandbox, check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
sandbox("g_eps_cold_rule")  # FIRST, before any harness. import

from harness.skills import lifecycle as L  # noqa: E402

NOW = float(calendar.timegm((2026, 10, 19, 0, 0, 0)))
OLD, YOUNG, EXACT30 = "2026-08-01T00:00:00Z", "2026-10-01T00:00:00Z", "2026-09-19T00:00:00Z"


def row(name, **kw):
    r = {"name": name, "dir": "/eps/" + name, "lifecycle": 1, "superseded_at": OLD}
    r.update(kw)
    return r


ROWS = [
    row("cold"),
    row("live", lifecycle=0),
    row("young", superseded_at=YOUNG),
    row("exact30", superseded_at=EXACT30),
    {"name": "nostamp", "dir": "/eps/nostamp", "lifecycle": 1},
    row("newest-wins", retired_at="2026-10-10T00:00:00Z"),
    row("frac", superseded_at="2026-07-01T00:00:00.5Z"),
    row("retired-only", superseded_at=None, retired_at=OLD),
    row("forgotten-only", superseded_at=None, forgotten_at=OLD),
    row("core", core=1),
    row("folded", superseded_by="dist-live"),
    row("named-only"),
    {"name": "dist-live", "dir": "/eps/dist-live", "lifecycle": 0, "derived_from": ["folded", "named-only"]},
    row("dead-dep"),
    row("dist-dead", derived_from=["dead-dep"]),
    {"name": "nodir", "lifecycle": 1, "superseded_at": OLD},
]
EXPECT = {
    "cold": "cold", "live": "tombstoned", "young": "aged", "exact30": "aged", "nostamp": "aged",
    "newest-wins": "aged", "frac": "aged", "retired-only": "cold", "forgotten-only": "cold",
    "core": "not_core", "folded": "no_live_dependent", "named-only": "no_live_dependent",
    "dist-live": "tombstoned", "dead-dep": "cold", "dist-dead": "cold",
}
BY = {r["name"]: r for r in ROWS}
DEPS = L.live_dependents(ROWS)

print("§1 the table")
check("the rule is four named clauses, in order",
      [c for c, _ in L.EPS_COLD_RULE] == ["tombstoned", "aged", "not_core", "no_live_dependent"], L.EPS_COLD_RULE)
check("...every clause has a written condition", all(isinstance(w, str) and len(w) > 10 for _, w in L.EPS_COLD_RULE))
check("...and exactly one test each", list(L._EPS_COLD_TESTS) == [c for c, _ in L.EPS_COLD_RULE], list(L._EPS_COLD_TESTS))
check("the stamps are the three tombstone breadcrumbs",
      L.EPS_COLD_STAMPS == ("superseded_at", "retired_at", "forgotten_at"), L.EPS_COLD_STAMPS)

print("§2 each row is convicted by exactly the clause that keeps it hot")
for name, want in EXPECT.items():
    got = L.eps_cold_verdict(BY[name], DEPS, 30.0, NOW)
    check("%s -> %s" % (name, want), got == want, got)

print("§3 the dependents are live distillates only")
check("a live distillate's supports are dependents", {"folded", "named-only"} <= DEPS, sorted(DEPS))
check("a TOMBSTONED distillate keeps nothing hot", "dead-dep" not in DEPS, sorted(DEPS))

print("§4 the knob, and the boundary")
check("the knob's default is the spec's 30 days, on both entry points",
      L.EPS_COLD_AFTER_DAYS == 30.0
      and inspect.signature(L.eps_cold_verdict).parameters["after_days"].default == 30.0
      and inspect.signature(L.cold_episode_rows).parameters["after_days"].default == 30.0,
      L.EPS_COLD_AFTER_DAYS)
check("the after_days knob is honoured (young is cold at 10 days)",
      L.eps_cold_verdict(BY["young"], DEPS, 10.0, NOW) == "cold")
check("exactly 30 days dead is not MORE than 30", L.tombstone_age_days(BY["exact30"], NOW) == 30.0)
check("the newest stamp governs", round(L.tombstone_age_days(BY["newest-wins"], NOW), 3) == 9.0,
      L.tombstone_age_days(BY["newest-wins"], NOW))
check("no stamp has no age", L.tombstone_age_days(BY["nostamp"], NOW) is None)

print("§5 the list")
got = sorted(r["name"] for r in L.cold_episode_rows(ROWS, 30.0, NOW))
check("cold_episode_rows returns the cold rows that carry a dir",
      got == ["cold", "dead-dep", "dist-dead", "forgotten-only", "retired-only"], got)
src = inspect.getsource(L.cold_episode_rows) + inspect.getsource(L.eps_cold_verdict) + \
      inspect.getsource(L.live_dependents) + inspect.getsource(L.tombstone_age_days)
check("the rule is pure: no file, no store", "open(" not in src and "environ" not in src and "_load" not in src)
check("liveness is read through is_retired, the one row predicate",
      "is_retired(" in inspect.getsource(L.live_dependents) and '"lifecycle"' not in src)

finish("G-EPS-COLD-RULE")
