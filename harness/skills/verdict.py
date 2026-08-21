"""verdict — Phase B of docs/INVARIANT-MEMORY.md: THE evaluator. Rules are DATA.

The committed verdict table (harness_tests/fixtures/sem/verdict-table.json, frozen by
sem_enum.py --freeze, pinned by G-SEM-TABLE) is the law. This module is the ONE
implementation of the signature: it computes a row's CELL from the system's OPERATIONAL
relations and looks the ruling up. The enumerator imports THESE functions — if a second
copy of sigma() ever exists, it will drift, and that is the two-paths bug with a
mathematician's hat on.

NORMALIZATION LAW (read off the running code, not invented):
    status   missing -> observed     (lifecycle.testimony_wins: `or STATUS_OBSERVED` —
                                      77 of her 81 live rows predate the status field)
    speaker  missing -> user         (same seam, same default)
    mem_class missing -> fact        (lifecycle.salience's default)

THE EVALUATOR NEVER GUESSES. A cell absent from the table returns None (UNMAPPED) and
shadow mode COUNTS it — it does not invent a ruling. An unmapped cell reaching the
counter is Phase A's completeness failing in the field, which is exactly the news you
want loudly.

SHADOW MODE (SP_SEM_LAW=1, mapped in serve.py): the seam calls shadow() on its FINAL
result set. One direction is checked, and it is the load-bearing one:

    EVERYTHING ADMITTED MUST BE TABLE-ADMISSIBLE.

(The other direction — something the table would admit that the seam did not — is not
checkable here: absence may lawfully be the lexical match-gate, and the match-gate is
admission-by-MATCH, not policy.) Divergences and unmapped cells are counters plus
optional witness lines (SP_SEM_LAW_LOG). Shadow NEVER raises, NEVER alters results,
NEVER blocks speech. Cutover (the seam consulting ruling() as its filter) is Phase B2,
and its precondition is a zero-divergence receipt from this shadow.
"""
import json
import os
import threading

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TABLE_PATH = os.path.join(_ROOT, "harness_tests", "fixtures", "sem", "verdict-table.json")

_LOCK = threading.RLock()
_TABLE = {"mtime": None, "cells": None}
_STATS = {"checked": 0, "divergent": 0, "unmapped": 0}


# ── the ONE signature implementation ───────────────────────────────────────────────────
def sigma(row: dict) -> dict:
    """Normalized signature coordinates of a row. Status comes from lifecycle.status_of —
    THE normalization (Tier 1.3): the first cut of this function used a plain
    observed-default and DIVERGED from render()/_is_evidence()'s legacy src-shim, so a
    legacy reflection row was testimony at the seam and a conclusion at the mouth.
    One law now, owned where the STATUS_* vocabulary lives."""
    from harness.skills import lifecycle as lc
    return {
        "speaker": row.get("speaker") or "user",
        "status": lc.status_of(row),
        "lifecycle": 1 if row.get("lifecycle") else 0,
        "mem_class": row.get("mem_class") or "fact",
    }


def _ground_truth():
    from harness.skills import lifecycle as lc
    return getattr(lc, "_GROUND_TRUTH", frozenset({"observed", "confirmed"}))


def competition(row: dict, rows: list) -> str:
    """OPERATIONAL competition coordinate: does a LIVE ground-truth row of the SAME
    speaker cover this row's topic? Two detectors feed the ONE coordinate:
      1. prose — topic_of overlap >= 2 (testimony_wins's exact relation);
      2. Phase C — an oracle-proposed same-subject LINK (slots sidecar), which closes
         the paraphrase gap prose cannot see (the "ladders" finding). Quarantine: a
         link can only push toward competition=1 — the silence direction. It cannot
         admit, cannot rank, cannot make her speak over him.
    Only meaningful for non-ground-truth rows; ground truth gets '.'."""
    from harness.skills import lifecycle as lc
    from harness.skills import semindex as sx
    from harness.skills import slots as sl
    s = sigma(row)
    if s["status"] in _ground_truth():
        return "."
    mine = lc.topic_of(lc.strip_prefix(row.get("text") or row.get("topic") or ""))
    my_addr = sx.addr_of(row.get("text") or "") if sl.enabled() else ""
    for r in rows:
        if r is row or r.get("name") == row.get("name"):
            continue
        rs = sigma(r)
        if rs["lifecycle"] == 0 and rs["status"] in _ground_truth() \
                and rs["speaker"] == s["speaker"]:
            theirs = lc.topic_of(lc.strip_prefix(r.get("text") or r.get("topic") or ""))
            if len(mine & theirs) >= 2:
                return "1"
            if my_addr and sl.linked(my_addr, sx.addr_of(r.get("text") or "")):
                return "1"
    return "0"


def attr(row: dict, query: str) -> str:
    """OPERATIONAL attr coordinate: attr_absent() itself, secrets only."""
    if sigma(row)["mem_class"] != "private-secret":
        return "."
    from harness.skills import memory as M
    return "-" if M.attr_absent(query, row.get("text") or "") else "+"


def cell(row: dict, query: str, rows: list) -> str:
    s = sigma(row)
    return "speaker=%s|status=%s|lifecycle=%d|class=%s|competition=%s|attr=%s" % (
        s["speaker"], s["status"], s["lifecycle"], s["mem_class"],
        competition(row, rows), attr(row, query))


# ── σ projections: the finite-field verdicts (Tier 1.3) ────────────────────────────────
# Three verdicts that always were functions of the signature now read committed tables
# here instead of local branches. G-SEM-PROJ walks every cell through the REAL consumers.

# render framing: first match on (status, speaker); '*' is any. STATUS OUTRANKS SPEAKER —
# an inference reads as hers whatever lane it lives in ("she is allowed to be wrong about
# him; she is not allowed to be wrong about him IN HIS VOICE"), and a confirmed thing is
# a thing they AGREED on. Unknown statuses (disputed is vocabulary-only) fall through to
# the speaker rows — today's behaviour, pinned.
FRAMING = [
    ("inferred", "*", "I've come to think: {t}"),
    ("confirmed", "*", "We settled that: {t}"),
    ("*", "self", "About myself: {t}"),
    ("*", "*", "Sam told me: {t}"),
]


def framing_for(status: str, speaker: str) -> str:
    for st, sp, tpl in FRAMING:
        if st in ("*", status) and sp in ("*", speaker):
            return tpl
    return "Sam told me: {t}"      # unreachable; the last row is total


# supersede permission: may `incoming` retire `held`? THE asymmetry (find_superseded's
# docstring, now data): an inference NEVER retires ground truth. Everything else may —
# he corrects her, he changes his mind, she revises her own view.
def may_supersede(incoming_status: str, held_status: str) -> bool:
    from harness.skills import lifecycle as lc
    gt = getattr(lc, "_GROUND_TRUTH", frozenset({"observed", "confirmed"}))
    return not (incoming_status == lc.STATUS_INFERRED and held_status in gt)


def is_evidence(row: dict) -> bool:
    """The reflection loop's input gate as a σ projection: live, his lane, ground truth.
    (A tombstone is not news; her own voice is not news from the world; a conclusion is
    not an observation — scheduler._is_evidence's history, now one line over σ.)"""
    s = sigma(row)
    return s["lifecycle"] == 0 and s["speaker"] == "user" \
        and s["status"] in _ground_truth()


# ── the table ──────────────────────────────────────────────────────────────────────────
def load_table() -> dict:
    with _LOCK:
        try:
            mt = os.path.getmtime(TABLE_PATH)
        except Exception:
            return {}
        if _TABLE["mtime"] == mt and _TABLE["cells"] is not None:
            return _TABLE["cells"]
        try:
            with open(TABLE_PATH, encoding="utf-8") as f:
                cells = {c: v["ruling"] for c, v in json.load(f)["table"].items()}
        except Exception:
            cells = {}
        _TABLE.update(mtime=mt, cells=cells)
        return cells


def ruling(row: dict, query: str, rows: list):
    """The law's answer for this row under this query: {'seam','spoken','declined'}
    or None (UNMAPPED — never guessed)."""
    return load_table().get(cell(row, query, rows))


# ── shadow (read-only, unarmed unless SP_SEM_LAW=1) ───────────────────────────────────
def stats() -> dict:
    with _LOCK:
        return dict(_STATS)


# ── Phase B2: enforcement (armed by SP_SEM_VERDICT=1) ─────────────────────────────────
def enforce(query: str, scored: list, all_rows: list) -> list:
    """THE CUTOVER, silence-direction only: drop any (score, row) whose cell the law
    rules seam-inadmissible. Three deliberate properties:
      - the law can only EXCLUDE. It cannot admit around the match gate and cannot
        reorder — authority moved, code did not get deleted (belt-and-braces).
      - an UNMAPPED cell is KEPT and counted, loudly. Unlegislated is not forbidden:
        silencing her on cells MY enumeration missed punishes her for my gaps (the
        self-preference rows were one field-run away from exactly that). The meta-
        gates and counters make holes loud; enforcement does not make them mute.
      - a missing table disables enforcement entirely (there is no law to apply).
    NEVER raises; on any internal failure the input passes through untouched."""
    try:
        if os.environ.get("SP_SEM_VERDICT", "0") != "1":
            return scored
        table = load_table()
        if not table:
            return scored
        kept = []
        with _LOCK:
            for s, e in scored:
                # cell() ONCE per row: it runs competition() — a full O(n) scan with
                # per-row tokenization — and this loop computed it up to three times
                # for one verdict (the lookup, then again for each witness line).
                c = cell(e, query, all_rows)
                r = table.get(c)
                if r is None:
                    _STATS["unmapped"] += 1
                    _witness("unmapped", query, c)
                    kept.append((s, e))
                elif r.get("seam", False):
                    kept.append((s, e))
                else:
                    _STATS["enforced_drops"] = _STATS.get("enforced_drops", 0) + 1
                    _witness("enforced_drop", query, c)
        return kept
    except Exception:
        return scored


def _witness(kind: str, q: str, c: str):
    p = os.environ.get("SP_SEM_LAW_LOG", "")
    if not p:
        return
    try:
        d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps({"kind": kind, "query": q[:120], "cell": c}) + "\n")
    except Exception:
        pass


def shadow(query: str, admitted_rows: list, all_rows: list) -> None:
    """Called by the seam on its FINAL results. Checks: everything admitted is
    table-admissible. Counters + optional witnesses; never raises, never alters."""
    try:
        if os.environ.get("SP_SEM_LAW", "0") != "1":
            return
        table = load_table()
        if not table:
            return
        with _LOCK:
            for e in admitted_rows:
                c = cell(e, query, all_rows)
                r = table.get(c)
                _STATS["checked"] += 1
                if r is None:
                    _STATS["unmapped"] += 1
                    _witness("unmapped", query, c)
                elif not r.get("seam", False):
                    _STATS["divergent"] += 1
                    _witness("divergent", query, c)
    except Exception:
        pass                     # the law's shadow may never cost her a sentence
