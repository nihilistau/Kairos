"""HINDSIGHT progress scanner — the data source for /v1/progress (console/dashboard.html,
its first reader, was removed 2026-08-21; the JSON route stays for anything that wants it).

Read-only: scans native git log, gates/ receipts, MIGRATION-MAP.md and the
phase charter (HINDSIGHT.md §6) and returns ONE JSON document. No policy, no
writes; the dashboard is an observability surface (PK2 §U pattern).

Status resolution order (most to least authoritative):
  1. gates/phase_status.json manual overrides   {"P1": "landed", ...}
  2. commit-subject markers (landed_re / progress_re below)
  3. default: pending

Heuristics are heuristics — when a gate seals, drop the receipt in gates/ and
(if the commit subject doesn't carry the marker) flip it in phase_status.json.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── phase charter (HINDSIGHT.md §6) ─────────────────────────────────────────
PHASES = [
    {"id": "P0", "name": "Genesis", "gate": "G-KAIROS-P0",
     "what": "Charter + MIGRATION-MAP + OKFS seed store + profiles sketch",
     "landed_re": r"PROJECT HINDSIGHT genesis", "progress_re": None},
    {"id": "P1", "name": "The kernel", "gate": "G-KAIROS-P1 + G-KAIROS-PERF",
     "what": "sp_daemon → engine/ (legacy_policy flag), math-core submodule, prefix snapshot, batch→persist handoff",
     "landed_re": r"G-KAIROS-P1(?!\w)", "progress_re": r"prefix[- ]snapshot|legacy_policy|engine/ (copy|migrat)"},
    {"id": "P2", "name": "The harness", "gate": "2026-07-10 audit suite (10 gates)",
     "what": "harness → harness/, policy moves kernel → harness executors",
     "landed_re": r"HINDSIGHT P2", "progress_re": None},
    {"id": "P3", "name": "Console + profiles", "gate": "G-KAIROS-P3 (live-play, zero bat edits)",
     "what": "Console autodetect; profiles/*.toml + serve.py replace the launcher zoo",
     "landed_re": r"HINDSIGHT P2\+P3|G-KAIROS-P3", "progress_re": None},
    {"id": "P4", "name": "Production cutover", "gate": "G-KAIROS-P4",
     "what": "Daily driver = kairos serve; staging repos get ARCHIVED READMEs; OKFS cross-linked",
     "landed_re": r"G-KAIROS-P4|cutover (COMPLETE|sealed)", "progress_re": r"[Ll]ive-play"},
    {"id": "P5", "name": "The perf ladder", "gate": "G-KAIROS-P5 (llama.cpp parity)",
     "what": "Float-path repair, prefill program, high-acceptance drafter → spec_step wired",
     "landed_re": r"G-KAIROS-P5|llama\.cpp parity SEALED",
     # NB: not plain "G-KAIROS-PERF" — descriptive commits (e.g. the dashboard
     # itself) mention the gate name; require actual perf-work markers.
     "progress_re": r"G-KAIROS-PERF (GREEN|sealed|numbers)|drafter H2H|float-path repair"},
]

# ── G-KAIROS-PERF bar (HINDSIGHT §4) — targets vs last measured ─────────────
PERF = [
    {"metric": "conversation turn (warm)", "target": "≤ 20 s", "measured": "4.6–17.3 s (G-CONVERSATION, 2026-07-12)", "ok": True},
    {"metric": "short answer turn", "target": "≤ 10 s", "measured": "3–7 s", "ok": True},
    {"metric": "recall turn", "target": "≤ 20 s", "measured": "6–17 s ('Sam.')", "ok": True},
    {"metric": "NEW chat (fresh session)", "target": "≤ 20 s", "measured": "~90 s — full prefill (needs safe prefix reuse)", "ok": False},
    {"metric": "boot / load prefill", "target": "one-time", "measured": "~90–420 s at load; traffic gated until HOT", "ok": True},
    {"metric": "decode tok/s", "target": "≥ 40 (drafter + float)", "measured": "12–13 byte-exact (graph path declined)", "ok": False},
    {"metric": "VERBATIM digits", "target": "must copy", "measured": "BROKEN: 4471 → 4481 (G-VERBATIM)", "ok": False},
]

# ── THE GATE SUITE (the dashboard's most important panel: what is PROVEN) ─────
# Every gate that guards a behavior the operator can feel. run: python <file>
GATES = [
    ("G-CONVERSATION", "harness_tests/g_conversation_e2e.py",
     "10 turns, one session, past ring_W: completeness, no degeneration, recall, latency"),
    ("G-VERBATIM", "harness_tests/g_verbatim.py",
     "can the model quote its own context? GREEN 6/6 — root cause was no_repeat_ngram=3 "
     "banning re-emission of any trigram in context, which IS verbatim copying"),
    ("G-MEMPOLICY-V3", "harness_tests/g_mempolicy_v3_offline.py",
     "per-entry policy: secret decline (zero-inference), counterfact framing, null floor"),
    ("G-PK2-SPINE", "harness_tests/g_pk2_spine_offline.py", "decide→execute→verify receipts"),
    ("G-PK2-SPINE-2", "harness_tests/g_pk2_spine2_offline.py", "gateway pre-turn composition"),
    ("G-PK2-TOOLROBUST", "harness_tests/g_pk2_toolrobust_offline.py", "tool parse + verify gate"),
    ("G-MCP-SERVER", "harness_tests/h_mcp_server.py", "MCP bridge + tool wiring"),
    ("G-PERSONALITY", "harness_tests/h_personality_persona.py", "persona state parse/inject/persist"),
    ("G-FLOAT-PARITY", "harness_tests/g_float_parity.py",
     "float vs exact serving (REOPENED: the old refutation was under-evidenced)"),
]


def _gate_suite() -> List[Dict[str, Any]]:
    """Gate name, file, what it guards, and whether the file exists (a gate that
    does not exist cannot be GREEN — the dashboard says so out loud)."""
    out = []
    for name, path, guards in GATES:
        out.append({"name": name, "path": path, "guards": guards,
                    "present": os.path.isfile(os.path.join(ROOT, path))})
    return out


_CACHE: Dict[str, Any] = {"ts": 0.0, "doc": None}
_TTL = 8.0  # seconds; the dashboard polls every ~10s


def _git(*args: str) -> str:
    try:
        # --no-optional-locks: this scanner polls in the background; `status` must
        # NEVER take index.lock (a killed poll orphans it and blocks real commits).
        out = subprocess.run(["git", "--no-optional-locks", *args], cwd=ROOT,
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip()
    except Exception:
        return ""


def _commits(n: int = 200) -> List[Dict[str, str]]:
    raw = _git("log", f"-{n}", "--date=short", "--format=%h%x1f%ad%x1f%s")
    rows = []
    for line in raw.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            sha, date, subj = parts
            m = re.match(r"^([A-Za-z0-9-]+(?:\s+[Pp]\d(?:\.\d)?)?)[ :]", subj)
            lane = (m.group(1).strip() if m else "misc")
            rows.append({"sha": sha, "date": date, "subject": subj, "lane": lane})
    return rows


def _phase_status(commits: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    overrides: Dict[str, str] = {}
    ovp = os.path.join(ROOT, "gates", "phase_status.json")
    if os.path.exists(ovp):
        try:
            with open(ovp, encoding="utf-8") as f:
                overrides = json.load(f)
        except Exception:
            pass
    subjects = [c["subject"] for c in commits]
    out = []
    for p in PHASES:
        status, evidence = "pending", None
        if p["progress_re"]:
            for s in subjects:
                if re.search(p["progress_re"], s):
                    status, evidence = "in-progress", s[:90]
                    break
        for s in subjects:
            if re.search(p["landed_re"], s):
                status, evidence = "landed", s[:90]
                break
        if p["id"] in overrides:
            status, evidence = overrides[p["id"]], "manual override (gates/phase_status.json)"
        out.append({**{k: p[k] for k in ("id", "name", "gate", "what")},
                    "status": status, "evidence": evidence})
    return out


def _dir_populated(rel: str) -> bool:
    d = os.path.join(ROOT, rel)
    if not os.path.isdir(d):
        return False
    entries = [e for e in os.listdir(d) if e not in ("__pycache__",)]
    return len(entries) > 1 or (len(entries) == 1 and entries[0] != "README.md")


def _migration_map() -> List[Dict[str, Any]]:
    path = os.path.join(ROOT, "MIGRATION-MAP.md")
    rows: List[Dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except Exception:
        return rows
    for ln in lines:
        if not ln.startswith("|") or ln.startswith("|--") or ln.startswith("|---"):
            continue
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) < 6 or cells[0] in ("subsystem", "---"):
            continue
        if set(cells[0]) <= {"-", " "}:
            continue
        subsystem, today, verdict_raw, home, gate, receipt = cells[:6]
        vm = re.search(r"(KEEP|REWRITE|RESEARCH|DEAD)", verdict_raw)
        verdict = vm.group(1) if vm else "?"
        landed = False
        if verdict in ("KEEP", "REWRITE"):
            hm = re.match(r"([a-z_./-]+)/", home)
            if hm:
                top = hm.group(1).split("/")[0]
                landed = _dir_populated(top)
                if top == "mcp" and not landed:  # MCP server landed under harness/mcp_server
                    landed = _dir_populated(os.path.join("harness", "mcp_server"))
            elif "submodule" in home or "serve.bat" in home or "profiles" in home:
                landed = _dir_populated("profiles")
        rows.append({"subsystem": re.sub(r"\*\*", "", subsystem), "verdict": verdict,
                     "home": re.sub(r"\*\*", "", home), "gate": gate,
                     "receipt": receipt, "landed": landed})
    return rows


def _gate_receipts() -> List[str]:
    d = os.path.join(ROOT, "gates")
    try:
        return sorted(e for e in os.listdir(d) if e != "README.md")
    except Exception:
        return []


def progress_json() -> Dict[str, Any]:
    now = time.time()
    if _CACHE["doc"] is not None and now - _CACHE["ts"] < _TTL:
        return _CACHE["doc"]
    commits = _commits()
    lanes: Dict[str, Dict[str, Any]] = {}
    for c in commits:
        L = lanes.setdefault(c["lane"], {"count": 0, "latest": c["date"], "latest_subject": c["subject"]})
        L["count"] += 1
    doc = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "repo": {
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "head": _git("rev-parse", "--short", "HEAD"),
            "commit_count": _git("rev-list", "--count", "HEAD"),
            "dirty": bool(_git("status", "--porcelain")),
        },
        "phases": _phase_status(commits),
        "migration": _migration_map(),
        "commits": commits[:40],
        "lanes": [{"lane": k, **v} for k, v in lanes.items()],
        "gate_receipts": _gate_receipts(),
        "gate_suite": _gate_suite(),
        "perf": PERF,
    }
    _CACHE.update(ts=now, doc=doc)
    return doc
