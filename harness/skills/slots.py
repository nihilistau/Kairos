"""slots — Phase C of docs/INVARIANT-MEMORY.md: topic-equivalence as a relation the
table can consume, ORACLE-PROPOSED, never oracle-ruled.

THE FINDING THIS CLOSES (verdict-table notes, the "ladders" case): the prose topic test
(topic_of overlap >= 2) misses paraphrase-distance competition — his "wary of ladders
after a fall" shares ONE content word with her "relaxed about ladders these days", so
his testimony does not cover it and she can lawfully say it over him. The fix is NOT a
cleverer string metric — that is the clever-fragile thing this codebase is punished for
every time — it is the quarantine architecture working as designed:

    THE ORACLE (the served model, /v1/oneshot, greedy, scratch cache) PROPOSES
    same-subject links between two rows. The links live HERE, in a derived append-only
    sidecar. verdict.competition() consumes them as one more way an inference can be
    COVERED. The table rules exactly as before — competition=1 cells already rule
    not-spoken — the RELATION feeding the coordinate just grew eyes.

WHY A FALLIBLE ORACLE IS ADMISSIBLE HERE (the PRA entry bar, INVARIANT-MEMORY.md §1.3):
the failure asymmetry points the right way. A WRONG link silences an inference — costs
her a sentence. A MISSING link is exactly today's behaviour. The oracle can only ever
push toward silence on subjects he may have spoken to; it structurally cannot make her
speak over him, cannot admit, cannot retire, cannot write the registry. Every proposal
is a finite witness (both addrs, the verdict, the oracle tag, a timestamp) in a file.

SIDECAR RULES (the semindex discipline, same reasons):
  - append-only; verdicts are cached, "different" too (never re-ask the same pair);
  - keyed by content addr (semindex.addr_of — ONE address vocabulary);
  - tombstone-blind: liveness is the registry's, joined at read by the evaluator;
  - never blocks, never raises out; a dead daemon means no NEW proposals, nothing else.

Proposer scan policy (v1, deliberate): candidate pairs are (non-ground-truth row,
same-speaker LIVE ground-truth row) with prose overlap EXACTLY 1 — the gap zone. Pairs
at >= 2 are already covered by prose; pairs at 0 are unbounded and unpriced (a later
phase can widen with a budget). Run: python -m harness.skills.slots --scan  (LIVE).
"""
import json
import os
import threading
import time

MODEL_TAG = "oneshot-greedy-v1"
_LOCK = threading.RLock()
_CACHE = {"key": None, "same": None, "seen": None}


def sidecar_path() -> str:
    return os.environ.get("SP_SEM_SLOTS", "")


def enabled() -> bool:
    return bool(sidecar_path())


def _load():
    p = sidecar_path()
    try:
        st = os.stat(p) if p and os.path.exists(p) else None
        key = (p, st.st_mtime_ns, st.st_size) if st else (p, None, None)
    except Exception:
        key = (p, None, None)
    with _LOCK:
        if _CACHE["key"] == key and _CACHE["same"] is not None:
            return _CACHE["same"], _CACHE["seen"]
        same, seen = set(), set()
        if p and os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        r = json.loads(ln)
                        pair = frozenset((r["a"], r["b"]))
                        seen.add(pair)
                        if r.get("verdict") == "same":
                            same.add(pair)
                    except Exception:
                        continue
        _CACHE.update(key=key, same=same, seen=seen)
        return same, seen


def linked(addr_a: str, addr_b: str) -> bool:
    """Is there an oracle-proposed same-subject link between these two rows?"""
    try:
        if not enabled() or not addr_a or not addr_b or addr_a == addr_b:
            return False
        same, _ = _load()
        return frozenset((addr_a, addr_b)) in same
    except Exception:
        return False


def _append(row: dict) -> None:
    p = sidecar_path()
    with _LOCK:
        d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ── the ORDER-FRAME proposer (OFFLINE; proposals only) — Phase C2 ─────────────────────
# The operator's insight, made mechanical: similarity (magnitudes of meaning) failed as
# a link detector twice — cosine (no discrimination) and the greedy LLM judge (no
# yield). Its OPPOSITE is pair-level STRUCTURE, and structure is literally in the
# invariant-maximality program as EMULATION: two rows link the way a known pair links
# iff the PAIRS are order-equivalent. The ladders pair is an emulation of the water
# pair: same stative frame, same grammatical subject, shared subject-matter inside the
# value region, competing residues on both sides.
#
# THE SCAR THIS RESPECTS: find_contradicted() was deleted from lifecycle.py for being a
# semantic contradiction engine built from substring matching — A VERDICT-WRITER. This
# is the same instrument with the OPPOSITE authority: it PROPOSES into the quarantined
# sidecar, where a wrong link costs one sentence (an inference wrongly silenced while
# its fake-cover is live) and a missing link is yesterday's behaviour. The incumbent
# topic test (testimony_wins, overlap >= 2) accepts exactly the same false-positive
# direction on purpose ("at worst she is quieter") — so the ship bar, measured by
# sem_pair_score.py on the committed pair corpus, is THE INCUMBENT'S OWN STANDARD:
# precision no worse than prose-overlap's, recall strictly better on the gap zone.
FRAME_TAG = "order-frame-v1"


_FRAME_COPULA = None    # frame-local: includes "am" (lc._COPULA is the supersede slot
                        # machinery and deliberately does not — do not touch it)


def _frame(text: str):
    """(subject-string, subject content words, value content words) for a stative
    claim, or None. The FIRST copula splits."""
    import re as _re
    global _FRAME_COPULA
    from harness.skills import lifecycle as lc
    if _FRAME_COPULA is None:
        _FRAME_COPULA = _re.compile(r"\b(is|are|was|were|am|=|:)\b", _re.I)
    t = lc.strip_prefix(text or "").strip()
    m = _FRAME_COPULA.search(t)
    if not m:
        return None
    subj = " ".join(t[:m.start()].lower().split())
    sval = lc.topic_of(t[:m.start()])
    val = lc.topic_of(t[m.end():])
    if not subj or not (val or sval):
        return None
    return subj, sval, val


def frame_link(text_a: str, text_b: str):
    """(link?, why) — the emulation-pair test, pure and decidable. TWO frame kinds:

    ATTRIBUTE competition — identical multi-word subject with content ("my mower
    fuel"), differing values: the pair competes over the slot the subject names.
    PROPERTY competition — same bare subject ("sam"), shared subject-matter in both
    VALUE regions, and BOTH sides carrying a competing residue (a restatement or
    containment is not a competing claim).

    No antonym lists, no similarity, no model. Known precision ceiling, measured on
    the committed corpus: shared-word-different-dimension pairs (mood-at-beach vs
    height-at-beach) are structurally indistinguishable at bag-of-words granularity —
    that is what the oracle-veto column of sem_pair_score.py is for."""
    fa, fb = _frame(text_a), _frame(text_b)
    if not fa or not fb:
        return False, "no stative frame on one side"
    if fa[0] != fb[0]:
        return False, "different grammatical subjects (%r vs %r)" % (fa[0], fb[0])
    # ATTRIBUTE kind: the subject itself names the slot ("my mower fuel is ...")
    if fa[1] and fa[2] != fb[2]:
        return True, ("attribute pair: slot %r, competing values" % fa[0])
    shared = fa[2] & fb[2]
    if not shared:
        return False, "no shared subject-matter in the value regions"
    ra, rb = fa[2] - shared, fb[2] - shared
    if not ra or not rb:
        return False, "one side adds nothing: restatement/containment, not competition"
    return True, ("property pair: frame %r, shared %s, competing residues"
                  % (fa[0], sorted(shared)))


# ── the oracle (LIVE; proposals only) ─────────────────────────────────────────────────
def ask_oracle(text_a: str, text_b: str):
    """One greedy /v1/oneshot judgment: 'same' | 'different' | None (unreachable/unparseable).
    None is recorded nowhere — an unreachable oracle proposes nothing."""
    # Few-shot with a NEUTRAL on-domain exemplar — the mint_question_l5 cure for a 12B
    # drifting into prose on hard pairs (the first prompt got back 'The same person is
    # referred to in both' on the ladders pair; unparseable proposes nothing, so the
    # failure was safe — but a mute judge is a useless one).
    prompt = ("Decide whether two statements are about the SAME specific subject. "
              "Reply with exactly one word, YES or NO.\n"
              "A: \"The shed door sticks in winter.\"  B: \"The shed door was repainted.\"  -> YES\n"
              "A: \"The shed door sticks in winter.\"  B: \"The car needs new tyres.\"  -> NO\n"
              "A: \"%s\"  B: \"%s\"  ->" % (text_a.strip(), text_b.strip()))
    try:
        # Through the shared door (harness.inference.oneshot): control surfaces removed,
        # None on an unreachable daemon. This judge was lower-risk than the narrative —
        # a leaked marker makes the answer unparseable, and unparseable already proposes
        # nothing — but it is the same hand-rolled request, so it uses the same door.
        from harness.inference.oneshot import ask_oneshot
        text = ask_oneshot(prompt, max_tokens=4, temperature=0.0, timeout=120) or ""
        word = text.strip().strip('"\'.,:;!').lower()
        if word.startswith("yes"):
            return "same"
        if word.startswith("no"):
            return "different"
        return None
    except Exception:
        return None


def scan(registry_rows: list, proposers=("frame-review", "oracle")) -> dict:
    """Propose links for the gap zone. Idempotent (decided pairs are never re-asked).
    Writes ONLY the sidecar. Proposer order is deliberate: the order-frame test is
    free, offline and deterministic; the LLM oracle only sees pairs structure could
    not decide. Returns counts."""
    from harness.skills import lifecycle as lc
    from harness.skills import semindex as sx
    if not enabled():
        return {"asked": 0, "same": 0, "different": 0, "frame": 0,
                "note": "SP_SEM_SLOTS unset"}
    gt = getattr(lc, "_GROUND_TRUTH", frozenset({"observed", "confirmed"}))
    live = [r for r in registry_rows if not r.get("lifecycle") and r.get("text")]
    ground = [r for r in live if lc.status_of(r) in gt]
    inferred = [r for r in live if lc.status_of(r) not in gt]
    _, seen = _load()
    asked = same = different = frame = 0
    for b in inferred:
        tb = lc.topic_of(lc.strip_prefix(b["text"]))
        ab = sx.addr_of(b["text"])
        for a in ground:
            if (a.get("speaker") or "user") != (b.get("speaker") or "user"):
                continue
            overlap = len(lc.topic_of(lc.strip_prefix(a["text"])) & tb)
            if overlap != 1:
                continue                      # the gap zone, exactly
            aa = sx.addr_of(a["text"])
            if frozenset((aa, ab)) in seen:
                continue
            if "frame" in proposers or "frame-review" in proposers:
                ok, why = frame_link(a["text"], b["text"])
                if ok:
                    # MEASURED (sem_pair_score, the C2 receipt): frame recall on the gap
                    # zone is 1.0 but precision 0.625 — below the pre-registered 0.80
                    # auto-bar — and the LLM judge is out in every role (all-NO, true
                    # pairs included). So the SHIPPED configuration is frame-review:
                    # proposals land PENDING (inert — linked() honors only "same") and
                    # the OPERATOR is the precision oracle, via --review/--confirm.
                    # Machine recall, human precision; the quarantine holds throughout.
                    verdict = "same" if "frame" in proposers else "pending"
                    frame += 1
                    _append({"a": aa, "b": ab, "verdict": verdict, "oracle": FRAME_TAG,
                             "why": why[:100], "a_text": a["text"][:60],
                             "b_text": b["text"][:60],
                             "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
                    continue
            if "oracle" in proposers:
                verdict = ask_oracle(a["text"], b["text"])
                if verdict is None:
                    continue                  # unreachable oracle proposes nothing
                asked += 1
                same += verdict == "same"
                different += verdict == "different"
                _append({"a": aa, "b": ab, "verdict": verdict, "oracle": MODEL_TAG,
                         "a_text": a["text"][:60], "b_text": b["text"][:60],
                         "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return {"asked": asked, "same": same, "different": different, "frame": frame}


def pending() -> list:
    """The review queue: frame proposals awaiting the operator's verdict."""
    p = sidecar_path()
    out, resolved = [], set()
    if not p or not os.path.exists(p):
        return out
    with open(p, encoding="utf-8") as f:
        rows = [json.loads(x) for x in f if x.strip()]
    for r in rows:
        if r.get("verdict") in ("same", "different") \
                and r.get("oracle") == "operator":
            resolved.add(frozenset((r["a"], r["b"])))
    for r in rows:
        if r.get("verdict") == "pending" \
                and frozenset((r["a"], r["b"])) not in resolved:
            out.append(r)
    return out


def resolve(addr_a: str, addr_b: str, verdict: str) -> None:
    """The operator's ruling on a pending proposal — appended, never edited."""
    assert verdict in ("same", "different")
    _append({"a": addr_a, "b": addr_b, "verdict": verdict, "oracle": "operator",
             "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})


if __name__ == "__main__":
    import sys
    reg = os.environ.get("SP_RECALL_REGISTRY", "")
    rows = []
    if reg and os.path.exists(reg):
        with open(reg, encoding="utf-8") as f:
            rows = [json.loads(x) for x in f if x.strip()]
    if "--scan" in sys.argv:
        print(json.dumps(scan(rows, proposers=("frame-review", "oracle"))))
    elif "--review" in sys.argv:
        q = pending()
        for r in q:
            print("%s | %s\n    A: %s\n    B: %s\n    (%s)" % (
                r["a"], r["b"], r.get("a_text", ""), r.get("b_text", ""),
                r.get("why", "")))
        print("%d pending. confirm: python -m harness.skills.slots --confirm A B" % len(q))
    elif "--confirm" in sys.argv:
        i = sys.argv.index("--confirm")
        resolve(sys.argv[i + 1], sys.argv[i + 2], "same")
        print("confirmed")
    elif "--reject" in sys.argv:
        i = sys.argv.index("--reject")
        resolve(sys.argv[i + 1], sys.argv[i + 2], "different")
        print("rejected")
    else:
        same, seen = _load()
        print(json.dumps({"pairs_seen": len(seen), "links_same": len(same),
                          "pending": len(pending())}))
