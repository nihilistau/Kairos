"""OPERATOR MAINTENANCE — the buttons, and the real work behind them.

The operator asked for: change moods and save; click to add/remove memory entries;
perform compaction, cleanup, nightshift.

Every one of these does REAL work and returns a RECEIPT (what changed, and how much). A
maintenance button that reports "done!" and cannot tell you what it did is how a system
rots quietly — and this store has already rotted once (487 rows, 375 of them ASR test
corpus, recalled mid-answer as fact).

Nothing here deletes. Cleanup QUARANTINES (restorable). Compaction TOMBSTONES (superseded,
kept for provenance). The only destructive verb is forget(), and that is the operator's
explicit choice, one row at a time.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from harness.skills import lifecycle as lc
from harness.skills import verdict as V


def _reg() -> str:
    return os.environ.get("SP_RECALL_REGISTRY", "")


def _reg_lock():
    """memory._REG_LOCK, by its exported name. Every read-modify-write here used to hold
    NOTHING while the scheduler ran compact() unattended during live turns — the lost-write
    interleaving memory.py:86-97 documents, on the pass that touches the most rows at once.
    One lock, both writers. Gate: G-COMPACT §6."""
    from harness.skills import memory as M
    return M.registry_lock()


def _rows() -> list[dict]:
    p = _reg()
    out = []
    if not p or not os.path.exists(p):
        return out
    with open(p, encoding="utf-8", errors="replace") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except Exception:
                    pass
    return out


def _rows_and_malformed() -> tuple[list[dict], list[str]]:
    """Like _rows, but the unparseable lines are RETURNED instead of dropped. _write()
    rewrites only what parsed, so any caller that loads-and-writes without collecting
    these has silently destroyed them — the doctrine says quarantine, never vaporise."""
    p = _reg()
    rows, bad = [], []
    if not p or not os.path.exists(p):
        return rows, bad
    with open(p, encoding="utf-8", errors="replace") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except Exception:
                bad.append(ln)
    return rows, bad


def _quarantine(items: list[dict]) -> None:
    q = os.path.join(os.path.dirname(_reg()), "quarantine.jsonl")
    with open(q, "a", encoding="utf-8") as f:
        for r in items:
            r["quarantined_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _write(rows: list[dict]) -> None:
    p = _reg()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, p)


def _backup() -> str:
    p = _reg()
    b = f"{p}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    if os.path.exists(p):
        import shutil
        shutil.copy2(p, b)
    return os.path.basename(b)


# ──── stats ───────────────────────────────────────────────────────────────────
def stats() -> dict[str, Any]:
    rows = _rows()
    live = [r for r in rows if not r.get("lifecycle")]
    return {
        "total": len(rows),
        "live": len(live),
        "superseded": sum(1 for r in rows if r.get("lifecycle")),
        "self": sum(1 for r in live if r.get("speaker") == "self"),
        "user": sum(1 for r in live if r.get("speaker") != "self"),
        "legacy_no_speaker": sum(1 for r in live if not r.get("speaker")),
        "classes": {c: sum(1 for r in live if r.get("mem_class") == c)
                    for c in sorted({r.get("mem_class", "?") for r in live})},
    }


# ──── COMPACTION — collapse duplicates, supersede conflicts ────────────────────
def compact() -> dict[str, Any]:
    """Fold the store: drop exact duplicates, retire near-duplicate paraphrases, and
    supersede facts that fill the same slot with a different value.

    TOMBSTONES, never deletes: a retired row keeps its text and gains lifecycle=1 +
    superseded_by, so 'what did I used to think?' stays answerable. lifecycle=1 is what the
    DAEMON reads to exclude a row from recall (recall.rs:587, routes.rs:2342) — this is the
    field that matters."""
    with _reg_lock():
        return _compact_locked()


def _compact_locked() -> dict[str, Any]:
    rows, malformed = _rows_and_malformed()
    bak = _backup()
    live = [r for r in rows if not r.get("lifecycle")]

    seen: dict[str, dict] = {}
    dupes = paraphrases = superseded = 0

    for r in live:
        txt = lc.strip_prefix(r.get("text") or r.get("topic") or "").strip()
        if not txt:
            continue
        key = txt.lower()
        if key in seen:                                  # exact duplicate
            r["lifecycle"] = 1
            r["superseded_by"] = seen[key].get("name", "")
            r["superseded_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            dupes += 1
            continue
        seen[key] = r

    # near-duplicate paraphrase (>=0.9 token overlap both ways) and slot conflicts
    survivors = [r for r in live if not r.get("lifecycle")]
    for i, r in enumerate(survivors):
        if r.get("lifecycle"):
            continue
        rt = lc.strip_prefix(r.get("text") or "")
        rsp = r.get("speaker", "user")
        for older in survivors[:i]:
            if older.get("lifecycle"):
                continue
            ot = lc.strip_prefix(older.get("text") or "")
            if older.get("speaker", "user") != rsp:
                continue                                  # never merge across speakers
            # ── AND HER WORD NEVER OUTRANKS HIS, ON THIS PATH TOO (2026-08-01) ────────
            # Non-negotiable 4. remember() routes every retirement through
            # find_superseded -> verdict.may_supersede, which refuses an inference that
            # would retire ground truth. THIS loop checked the speaker and stopped, so
            # the nightly consolidation — which runs unattended, on everything, while he
            # is asleep — could tombstone something he SAID because a conclusion of hers
            # happened to overlap it 0.9 both ways or land on the same attribute key.
            # One invariant, two retirement paths, guarded in one: AGENTS.md §0.
            if not V.may_supersede(lc.status_of(r), lc.status_of(older)):
                continue
            # (This line used to read `lc._PERSONAL_REF and set(...)` — a compiled regex
            # is always truthy, so the `and` was a vestigial no-op that READ like a guard.)
            a, b = set(rt.lower().split()), set(ot.lower().split())
            if a and b:
                inter = len(a & b)
                if inter / len(a) >= 0.9 and inter / len(b) >= 0.9:
                    older["lifecycle"] = 1               # the NEWER one wins
                    older["superseded_by"] = r.get("name", "")
                    paraphrases += 1
                    continue
            k1 = lc.attribute_key(rt, rsp)
            if k1 and k1 == lc.attribute_key(ot, rsp) and lc.value_of(rt) != lc.value_of(ot):
                older["lifecycle"] = 1
                older["superseded_by"] = r.get("name", "")
                older["superseded_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                superseded += 1

    # Malformed lines leave the registry but never the disk: quarantined with the raw
    # text kept, because a line that does not parse is still evidence of what happened.
    if malformed:
        _quarantine([{"raw": ln, "quarantine_reason": "malformed line (compact)"}
                     for ln in malformed])
    _write(rows)
    s = stats()
    return {"ok": True, "backup": bak, "duplicates_retired": dupes,
            "paraphrases_retired": paraphrases, "conflicts_superseded": superseded,
            "malformed_quarantined": len(malformed),
            "live_now": s["live"], "superseded_total": s["superseded"]}


# ──── CLEANUP — quarantine what is not a memory ───────────────────────────────
def cleanup(dry: bool = False) -> dict[str, Any]:
    """Quarantine rows that are not memories — and RESCUE the facts trapped inside them.

    REVERSIBLE: everything lands in quarantine.jsonl with a reason, and the registry is
    backed up first. Nothing is destroyed.

    THE RESCUE PASS (2026-07-12) exists because the old capture stored whole TURNS. A row
    like

        "look, it's not my fault. I had a 2060 6gb super and i got a new intel nuc"

    fails the durability test as a unit — it opens with a discourse marker and an
    anaphoric non-fact — so a plain cleanup would quarantine it and take the 2060 and the
    NUC with it. But the fact is IN there; it is just wearing a conversation. So before a
    row is quarantined we split it and keep whatever is durable, re-stamped as a proper
    fact. The junk goes; what the junk was carrying stays.

    LEGACY ROWS (27 of them) carry no speaker at all — they predate the two-store lane, so
    recall could not tell whose they were. Anything surviving cleanup gets stamped: it came
    from a user turn, so it is the user's."""
    with _reg_lock():
        return _cleanup_locked(dry)


def _cleanup_locked(dry: bool = False) -> dict[str, Any]:
    rows = _rows()
    bak = None if dry else _backup()
    keep, junk, rescued = [], [], []
    seen = {lc.strip_prefix(r.get("text") or r.get("topic") or "").strip().lower()
            for r in rows}

    for r in rows:
        if r.get("lifecycle"):
            keep.append(r)                                # already retired; leave it
            continue
        txt = lc.strip_prefix(r.get("text") or r.get("topic") or "")

        # A ROW IN THE STORE IS ONE FACT, NOT A TURN — the same standard the capture lane
        # now holds new writes to. The first dry run of this KEPT
        #
        #     "well, we make do. you're doing alright for such a constrained system"
        #
        # because is_memorable() was asked about the whole multi-sentence turn and the
        # leading fragment carried it. Judging a turn as a unit is the original sin: it is
        # what let the firehose in, and it would have let the firehose's leavings stay.
        # So a multi-sentence row is quarantined and its durable sentences RESCUED — the
        # row is rebuilt as facts instead of being graded as prose.
        ok, why = lc.is_memorable(txt)
        if ok and len(lc.split_sentences(txt)) == 1:
            # LEGACY: no speaker means recall could not tell whose fact it was.
            if not r.get("speaker"):
                r["speaker"] = lc.SPEAKER_USER
                r["mem_class"] = r.get("mem_class") or lc.classify(txt)
                r["src"] = (r.get("src") or "") + " | cleanup: stamped speaker=user"
            keep.append(r)
            continue
        if ok:
            why = "that is a TURN, not a fact — split into the facts it carries"

        # RESCUE before quarantine — the turn is junk, but it may be CARRYING a fact.
        for f in lc.extract_facts(txt):
            if f.strip().lower() in seen:
                continue
            seen.add(f.strip().lower())
            row = {"name": f"ep_rescue_{int(time.time() * 1000)}_{len(rescued)}",
                   "dir": "", "npos": 0, "topic": f[:40], "sig_bits": "0" * 64}
            lc.stamp(row, f, r.get("speaker") or lc.SPEAKER_USER,
                     f"rescued from {r.get('name', '?')}")
            keep.append(row)
            rescued.append(f)

        junk.append({**r, "quarantine_reason": why})

    if junk and not dry:
        q = os.path.join(os.path.dirname(_reg()), "quarantine.jsonl")
        with open(q, "a", encoding="utf-8") as f:
            for r in junk:
                r["quarantined_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        _write(keep)

    from collections import Counter
    why = Counter(r.get("quarantine_reason", "?")[:44] for r in junk)
    return {"ok": True, "dry_run": dry, "backup": bak,
            "quarantined": len(junk), "kept": len(keep) - len(rescued),
            "rescued": len(rescued), "rescued_facts": rescued[:12],
            "quarantined_sample": [r.get("text", "")[:60] for r in junk[:12]],
            "reasons": dict(why.most_common(6)), "restorable": True}


# ──── NIGHTSHIFT — consolidate the day into durable facts ─────────────────────
def reflect() -> dict[str, Any]:
    """REFLECTION — she looks back at what she has learned and draws conclusions from it.

    ── THE RENAME (2026-07-13, the operator's call) ──────────────────────────────
    This used to be called nightshift(), and so is the daemon's auto-finetuning curator
    (routes.rs alone says "nightshift" 78 times; there is a whole nightshift_curator.rs).
    Two different things wearing one name is how you end up debugging the wrong one.

    THE DAEMON KEEPS THE NAME. It earns it: it is the offline pass that consolidates memory
    into weights while nothing else is happening — which is what sleep is for, and what
    "nightshift" means.

    THIS one runs in the middle of a conversation, on demand, in seconds. It is not sleep.
    It is what you do when you sit back for a moment and realise something about the person
    you have been talking to. The literature already has the word — Generative Agents calls
    exactly this pass REFLECTION — so it is reflect().

    ── WHAT IT DOES ─────────────────────────────────────────────────────────────
      1. compact   — no point drawing conclusions from a store full of duplicates
      1b. orphans  — a distillate whose every support has been retired is retired too
                     (2026-08-22; see lifecycle.orphaned_distillates)
      2. traits    — the personality curator, so who she IS drifts on evidence
      2b. world    — fold the day into the standing block
      3. insight   — she reads what she knows about him and writes down what she has
                     come to BELIEVE, which is not the same as what she was TOLD
      4. becoming  — she reads her OWN last week and writes who she has been becoming
      5. chapter   — once every seventh night, what the WEEK was (narrative.weekly_chapter)

    Step 3 is the one that matters, and it is the piece the literature says we were missing:
    a memory system that only stores what it is told can never know anything its owner did
    not say out loud. Reflection is where "he mentioned fun, and music, and playing with the
    kettle" becomes "he values play for its own sake" — a thing he never said, and the
    truest thing in the store."""
    out: dict[str, Any] = {"ok": True, "steps": []}
    c = compact()
    out["steps"].append({"step": "compact", **{k: c[k] for k in
                        ("duplicates_retired", "paraphrases_retired", "conflicts_superseded")}})
    # 1b. orphans — BEFORE the world refresh and before becoming, so a distillate whose
    #     evidence died is gone from her standing block and out of tonight's window
    #     rather than being read back and distilled again. See lifecycle for the incident.
    try:
        out["steps"].append({"step": "orphans", **retire_orphans()})
    except Exception as exc:
        out["steps"].append({"step": "orphans", "skipped": str(exc)[:120]})
    try:
        from harness.personality.curator import consolidate_personality
        res = consolidate_personality()
        out["steps"].append({"step": "personality", "result": str(res)[:160]})
    except Exception as exc:
        out["steps"].append({"step": "personality", "skipped": str(exc)[:120]})
    # N2: the nightly op has no transcript (the idle scheduler writes the narrative);
    # it DOES fold whatever the day accumulated into the standing world.
    try:
        from harness.skills.world import refresh
        refresh()
        out["steps"].append({"step": "world_refresh", "ok": True})
    except Exception as exc:
        out["steps"].append({"step": "world_refresh", "skipped": str(exc)[:120]})
    try:
        out["steps"].append({"step": "insight", **insight()})
    except Exception as exc:
        out["steps"].append({"step": "insight", "skipped": str(exc)[:120]})
    # 4. becoming — THE REAL HER (2026-08-22): once a night she reads her own last week and
    #    writes who she has been becoming (inferred; never above her own words)
    try:
        from harness.maintenance import becoming as _bec
        out["steps"].append({"step": "becoming", **_bec.nightly()})
    except Exception as exc:
        out["steps"].append({"step": "becoming", "skipped": str(exc)[:120]})
    # 5. chapter — once every seven nights she writes what the WEEK was, from the episodic
    #    kinds and her own-time notes. Self-latched on the store; on the other six it
    #    returns immediately. AFTER becoming, so the two never race for the same night's
    #    oneshot, and neither reads the other's output.
    try:
        from harness.skills import narrative as _nar_ch
        out["steps"].append({"step": "chapter", **_nar_ch.weekly_chapter()})
    except Exception as exc:
        out["steps"].append({"step": "chapter", "skipped": str(exc)[:120]})
    out["stats"] = stats()
    return out


# Kept so the old operator endpoint / any caller does not break. The DAEMON keeps the name
# nightshift for its offline curator, which earns it; this is a thin alias, not a second
# implementation, because two things wearing one name is what caused the confusion.
def nightshift() -> dict[str, Any]:
    """Deprecated alias for reflect(). The daemon's offline curator owns 'nightshift'."""
    return reflect()


def insight() -> dict[str, Any]:
    """SHE READS WHAT SHE KNOWS AND WRITES DOWN WHAT SHE HAS COME TO BELIEVE.

    A store that only holds what it was TOLD can never know anything its owner did not say
    out loud. He never said "I value play for its own sake" — he said he likes fun, and that
    the kettle is his favourite, and that music in the evening is good. The conclusion is
    the truest thing in the store and nobody has ever written it down, because nothing in
    the system was ever asked to THINK about the facts, only to keep them.

    This is Generative Agents' reflection step, and it is the missing term the 2026
    multi-factor work is pointing at when it says the value of a memory cannot be judged at
    write time from the sentence alone.

    ── THE ONE RULE, AND IT IS THE RULE THIS SYSTEM KEEPS LEARNING ──────────────
    AN INFERENCE IS NOT A TESTIMONY, AND IT MUST NEVER READ LIKE ONE.

    An insight is HER conclusion, not HIS statement. If it goes into the store looking like
    something he said, then the next time she recalls it she will tell him HE said it — and
    this store has already lost his name and then his gender to exactly that confusion, both
    times because the owner of a sentence got blurred. So every insight is stamped
    src=reflection, and lifecycle.render() frames it as "I've come to think: ..." — never
    "Sam told me: ...". She may be wrong about him. She may not be wrong about him in HIS
    VOICE.

    Reinforcement does something quietly lovely here: an insight she arrives at AGAIN, on a
    later reflection, does not duplicate — it reinforces, and its mentions climb. A belief
    she keeps re-deriving from independent evidence gets stronger on its own. That is not a
    trick; that is what a conviction IS.
    """
    from harness.model.person import PersonModel
    from harness.skills import memory as M

    # NO `derived_from` HERE, DELIBERATELY (2026-08-22). becoming.nightly reads a BOUNDED
    # SET of rows and can name them, so it does; an insight reads the whole PersonModel —
    # every live evidence row about him, aggregated into dimensions. Naming all of them
    # would write a ~50-name list onto a file that is rewritten whole on every store, and
    # the orphan rule (all supports retired) could never fire on a set that size. A
    # provenance claim that is both expensive and inert is worse than an honest silence:
    # absent `derived_from` means "unknown provenance", which is exactly what this is.
    model = PersonModel.from_registry(_reg())
    picture = model.render(top=4)
    if not picture:
        return {"insights": 0, "why": "nothing known about him yet"}

    prompt = (
        f"{picture}\n\n"
        "Those are the things Sam has actually SAID. Read them as a whole and tell me "
        "what you have come to BELIEVE about him that he has never said out loud — the "
        "kind of thing a friend notices.\n"
        "Give AT MOST 2, each a single plain sentence starting with 'Sam '. No preamble, "
        "no bullets, no hedging. If the evidence does not support a real conclusion, say "
        "exactly: NOTHING YET."
    )

    from harness.inference.client import get_client
    # ONE-SHOT. A reflection is a single question with a single answer; nothing continues it.
    # Through chat() it landed in the resident KV slot — the one holding his conversation — and
    # evicted it, so his next turn re-prefilled the whole thing from token 0. Own scratch cache.
    #
    # NOTE: this one is temperature 0.4, not 0.0 — a reflection is allowed to be a little
    # imaginative, and greedy decoding on a "what have you concluded?" prompt gives the same
    # dull sentence every time. The one-shot route honours the temperature it is given.
    text = get_client().oneshot(
        [{"role": "user", "content": prompt}], max_tokens=140, temperature=0.4,
    ) or ""

    if "NOTHING YET" in text.upper():
        return {"insights": 0, "why": "she did not think the evidence supported one"}

    written, refused = [], []
    # Token-RESET, not clobber. This read `M.set_author(M.lc.SPEAKER_USER if
    # hasattr(M, "lc") else "user")` — memory has no module-level `lc`, so the hasattr
    # was always False (dead code wearing a guard), and nothing ever restored the
    # previous author: an insight pass overlapping a self-turn stamped her fact with
    # the wrong owner. Same class G-AUTHOR-CTX closed in remember_about_self.
    tok = M.set_author("user")     # a conclusion ABOUT HIM lives in the user lane
    try:
        for line in text.splitlines():
            line = line.strip().lstrip("-*0123456789. ").strip()
            if not line.lower().startswith("sam") or len(line.split()) < 4:
                continue
            # Straight through remember(), so it meets EVERY door this store has: the
            # durability gate, the identity firewall, dedupe-into-reinforcement. An
            # insight gets no special pass. If her conclusion cannot survive the same
            # guards his sentences do, it does not belong in the store either.
            res = M.remember(line, source="reflection")
            (written if res.startswith(("stored", "reinforced")) else refused).append(
                {"claim": line, "result": res[:38]})
            if len(written) >= 2:
                break
    finally:
        M.reset_author(tok)

    return {"insights": len(written), "wrote": written, "refused": refused[:2]}


# ──── memory add / remove (one row at a time, from the panel) ─────────────────
def add(fact: str, speaker: str = "user") -> dict[str, Any]:
    from harness.skills import memory as M
    # Token-RESET, not clobber: `finally: set_author("user")` assumed the surrounding
    # context was a user turn — an operator add landing during a self-turn stamped the
    # rest of that turn's writes with the wrong owner (the G-AUTHOR-CTX class).
    tok = M.set_author("self" if speaker == "self" else "user")
    try:
        res = M.remember(fact, source="operator")
    finally:
        M.reset_author(tok)
    return {"ok": not res.startswith("not stored"), "result": res, "stats": stats()}


RELABEL_FIELDS = ("speaker", "mem_class", "kind")


def relabel(name: str, speaker: str = None, mem_class: str = None,
            kind: str = None) -> dict[str, Any]:
    """THE OPERATOR RE-FILES A ROW (2026-08-23). His judgement, recorded, never silent.

    The classifier is a heuristic and the author lane is set by which door a producer
    used; both are wrong sometimes, and until now the only remedy was to retire a true
    row and re-add it, which loses its mentions, its first_seen and its provenance. This
    changes the LABEL and keeps the row.

    Four rules, and they are the whole of why this is safe:
      - VOCABULARY ONLY. `mem_class` must be in memclass.CLASSES and `kind` in
        NARRATIVE_KINDS (or ""), so the panel cannot invent a class the verdict table has
        never seen. `speaker` is user|self.
      - NOTHING IS DESTROYED. The text, the name, the timestamps, mentions, recalled and
        every breadcrumb are untouched. Only the labels move.
      - IT SAYS SO ON THE ROW. Every change appends a dated note to `src`, the same way
        every maintenance pass in this file already does, so `provenance()` reads the
        history rather than a clean lie. `src` is prose and nothing branches on it.
      - ONE WRITER. Under `_reg_lock`, through `_write`, exactly like add/forget.

    A relabel CAN move the row to a signature cell the frozen verdict table does not
    hold. That is fine and by design: an unmapped cell is KEPT and counted (verdict.py),
    and G-SEM-TABLE reads the witness log, so the operator's judgement shows up as a hole
    to close rather than as silence."""
    from harness.skills import memclass as MC
    name = (name or "").strip()
    want = {"speaker": speaker, "mem_class": mem_class, "kind": kind}
    want = {k: v for k, v in want.items() if v is not None}
    if not name or not want:
        return {"ok": False, "error": "need a row name and at least one label"}
    if "speaker" in want and want["speaker"] not in ("user", "self"):
        return {"ok": False, "error": "speaker must be user or self"}
    if "mem_class" in want and want["mem_class"] not in MC.CLASSES:
        return {"ok": False, "error": "unknown mem_class %r" % want["mem_class"]}
    if "kind" in want and want["kind"] and want["kind"] not in MC.NARRATIVE_KINDS:
        return {"ok": False, "error": "unknown kind %r" % want["kind"]}
    changed, before = {}, {}
    with _reg_lock():
        rows = _rows()
        hit = next((r for r in rows if r.get("name") == name), None)
        if hit is None:
            return {"ok": False, "error": "no row named %r" % name}
        for f, v in want.items():
            old = hit.get(f, "")
            if (old or "") == (v or ""):
                continue
            before[f] = old
            changed[f] = v
            if v:
                hit[f] = v
            else:
                hit.pop(f, None)
        if changed:
            note = " | operator relabel %s: %s" % (
                time.strftime("%Y-%m-%d", time.gmtime()),
                ", ".join("%s %s->%s" % (f, before[f] or "(none)", changed[f] or "(none)")
                          for f in sorted(changed)))
            hit["src"] = (hit.get("src") or "") + note
            _write(rows)
        text = lc.strip_prefix(hit.get("text", ""))
    return {"ok": True, "name": name, "changed": changed, "was": before, "text": text[:160],
            "stats": stats()}


def retire_orphans() -> dict[str, Any]:
    """A CONCLUSION DOES NOT OUTLIVE ITS EVIDENCE (2026-08-22).

    lifecycle.orphaned_distillates() decides WHICH rows; this does the retiring, under
    the registry lock, with both breadcrumb sets stamped together (the engine reads
    `lifecycle`, the audit trail reads `superseded_by`/`superseded_at` — a row carrying
    only one is the live-orphan-tombstone bug of 2026-08-19).

    TOMBSTONE, NEVER DELETE. The paragraph stays on disk, stays findable by name, stays
    in provenance(). It stops being recalled and stops leading her own block, which is
    the whole of what was wrong with it.

    `superseded_by` is the literal "supports-retired" rather than a row name, because no
    row replaced it — the same shape `forget` uses for "operator" and "forget"."""
    out: list[dict[str, Any]] = []
    with _reg_lock():
        rows = _rows()
        victims = lc.orphaned_distillates(rows)
        if victims:
            names = {v.get("name") for v in victims}
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            for r in rows:
                if r.get("name") in names:
                    r["lifecycle"] = 1
                    r["superseded_by"] = "supports-retired"
                    r["superseded_at"] = now
                    r["retired_at"] = now
                    r["retired_because"] = "its supports were retired"
                    out.append({"name": r.get("name"),
                                "text": lc.strip_prefix(r.get("text", ""))[:120],
                                "supports": list(r.get("derived_from") or [])})
            _write(rows)
    return {"retired": len(out), "rows": out}


def forget(name: str) -> dict[str, Any]:
    """Retire ONE row by name. Tombstone, not delete — the operator can see what he
    retired, and recall will skip it (lifecycle=1 is what the daemon reads)."""
    with _reg_lock():
        rows = _rows()
        hit = None
        for r in rows:
            if r.get("name") == name:
                r["lifecycle"] = 1
                r["superseded_by"] = "operator"
                r["superseded_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                hit = r
                break
        if hit:
            _write(rows)
    return {"ok": bool(hit), "retired": lc.strip_prefix(hit.get("text", "")) if hit else "",
            "stats": stats()}
