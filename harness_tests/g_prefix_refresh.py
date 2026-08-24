"""G-PREFIX-REFRESH — she reads back what she becomes, on a schedule. OFFLINE.

THE CLAIM (2026-08-24 audit, B1-growth). The nightly loop's WRITE half worked — journal,
becoming, curated persona, world.refresh() — and the READ half was pinned to process
lifetime: the system bundle was cached once and invalidated by nothing, so she never
took any of it in until a restart, and the panel's staleness flag compared a fresh
compose against a fresh compose and could never fire.

Now: agent.system_bundle() is the ONE builder (stream path, blocking path, prewarm —
three builders became one, byte-identical); invalidate_system_prefix() is the ONE door,
called at exactly two moments (the 04:00 consolidation's step 5, and the operator's
/v1/maintenance/refresh); between them the prefix is DELIBERATELY frozen (the KV-prefix
law: token 0 must not move mid-session) and the panel says so honestly by comparing
against cached_system_content() — the string actually in her head.

MUTANTS, run live in-gate:
  (1) cached_system_content -> fresh load_agent_system() (the old lie): the staleness
      flag goes dark exactly when the prefix is stale;
  (2) invalidate_system_prefix -> no-op: the day boundary stops carrying freshness —
      the rebuilt bundle still lacks what the night wrote.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_prefix_refresh")
os.environ.setdefault("SP_DAEMON_URL", "http://127.0.0.1:9")
os.environ.pop("SP_GATEWAY_PREWARM", None)
# a fragments dir, so persona_layers.compose() is non-empty and the panel's staleness
# flag has a real composition to compare
FRAG_DIR = os.path.join(SB, "persona")
os.makedirs(FRAG_DIR, exist_ok=True)
FRAG = os.path.join(FRAG_DIR, "10-core.md")
with open(FRAG, "w", encoding="utf-8") as f:
    f.write("She is dry and warm, and she notices the weather.\n")
os.environ["SP_PERSONA_DIR"] = FRAG_DIR

import harness.agent as agent  # noqa: E402
import harness.server.app as app  # noqa: E402

# ── §1 one bundle, one cache ───────────────────────────────────────────────────────
c0, idx0 = agent.system_bundle()
check("§1 the bundle builds and is cached",
      agent.cached_system_content() == c0 and bool(c0))
check("§1 the fragment is in her head", "notices the weather" in c0)
v0 = agent._SYS["version"]

# ── §2 mid-day, the prefix is deliberately frozen — and the panel says so ──────────
with open(FRAG, "w", encoding="utf-8") as f:
    f.write("She is dry and warm, and she has learned to love the rain overnight.\n")
check("§2 the cached prefix does NOT move mid-day (KV-prefix law)",
      "love the rain" not in (agent.cached_system_content() or ""))
check("§2 a fresh compose WOULD differ (the difference is real)",
      "love the rain" in agent.load_agent_system())
pl = app._persona_layers()
check("§2 the panel's staleness flag FIRES against the actual cached prefix",
      pl.get("ok") and pl.get("stale") is True, str({k: pl.get(k) for k in
                                                     ("ok", "stale", "prefix_version")}))
check("§2 the panel reports version/built_at/token instruments",
      "prefix_version" in pl and "prefix_built_at" in pl and "prefix_tokens_est" in pl)

# ── §3 the invalidation door carries the night's writes in ─────────────────────────
v1 = agent.invalidate_system_prefix("gate")
c1, _ = agent.system_bundle()
check("§3 after invalidation the next build reads the change",
      "love the rain" in c1)
check("§3 the version moved", v1 == v0 + 1 and agent._SYS["version"] == v1)
check("§3 ...and the panel agrees she is current again",
      app._persona_layers().get("stale") is False)

# ── §4 three builders, one string: the prewarm sends the cached bundle ─────────────
sent = {}


class _FakeClient:
    def health(self):
        return True

    def chat(self, messages=None, config=None, **kw):
        sent["system"] = (messages or [{}])[0].get("content", "")

        class _R:
            text = "ok"
        return _R()


import harness.inference.client as _icl  # noqa: E402
_real_get = _icl.get_client
_icl.get_client = lambda: _FakeClient()
try:
    os.environ["SP_GATEWAY_PREWARM"] = "1"
    app._WARM.clear()
    app._prewarm()
    t0 = time.time()
    while "system" not in sent and time.time() - t0 < 10:
        time.sleep(0.05)
finally:
    _icl.get_client = _real_get
    os.environ.pop("SP_GATEWAY_PREWARM", None)
    app._WARM.set()
check("§4 the prewarmed prefix IS the served prefix, byte for byte",
      sent.get("system") == agent.cached_system_content(),
      "prewarm sent %d chars, cache holds %d" % (len(sent.get("system") or ""),
                                                 len(agent.cached_system_content() or "")))
check("§4 ...voice_coda included (the B5 divergence, closed)",
      "That was the plumbing" in (sent.get("system") or ""))

# ── §5 the day boundary is the scheduled freshness moment ──────────────────────────
with open(FRAG, "w", encoding="utf-8") as f:
    f.write("She is dry and warm, and tonight she decided she likes thunder.\n")
res = app.run_consolidation(force=True)
steps = {s.get("step"): s for s in res.get("steps", [])}
check("§5 run_consolidation carries a prefix_refresh step",
      "prefix_refresh" in steps, str(list(steps)))
check("§5 ...that bumped the version", steps.get("prefix_refresh", {}).get("version", 0)
      > v1)
check("§5 ...and the next build knows what the night wrote",
      "likes thunder" in agent.system_bundle()[0])

# ── §mutant (1): the old fresh-vs-fresh compare could never fire ───────────────────
with open(FRAG, "w", encoding="utf-8") as f:
    f.write("She is dry and warm, and she hums when she reads.\n")
_real_cached = agent.cached_system_content
app_cached = None
try:
    # the mutant: "what is in her head" answered by re-reading the files — the lie H1
    # documents. The flag must go DARK with it, proving the real comparison target is
    # load-bearing.
    import harness.agent as _ag_m
    _ag_m.cached_system_content = lambda: _ag_m.load_agent_system()
    pl_m = app._persona_layers()
    check("mutant(fresh-vs-fresh): the staleness flag goes dark — the cached target is "
          "load-bearing", pl_m.get("stale") is False, str(pl_m.get("stale")))
finally:
    agent.cached_system_content = _real_cached
check("(and the real flag fires on the same state)",
      app._persona_layers().get("stale") is True)

# ── §mutant (2): no invalidation, no freshness ─────────────────────────────────────
_real_inv = agent.invalidate_system_prefix
try:
    agent.invalidate_system_prefix = lambda reason: agent._SYS["version"]
    app.run_consolidation(force=True)
    check("mutant(no invalidation): the day boundary stops carrying freshness",
          "hums when she reads" not in agent.system_bundle()[0])
finally:
    agent.invalidate_system_prefix = _real_inv
agent.invalidate_system_prefix("gate cleanup")

finish("G-PREFIX-REFRESH")
