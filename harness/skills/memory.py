"""Memory tools — the model's explicit handle on its own long-term memory.

These operate on the daemon's persistent episode registry (``SP_RECALL_REGISTRY``),
the same content-addressed store the autonomous recall path reads. Exposed as
ephemeral tools (``ToolSpec.from_callable``) so the served model can *deliberately*
introspect, store, and forget facts — unifying the memory system with tool calling.
The autonomous memory-agency (forget/decide/merge in the daemon) keeps running; these
give the model a first-person lever on the same store.

Each function is a plain callable with a typed signature, so
``ToolSpec.from_callable`` derives the tool schema automatically.
"""
from __future__ import annotations

import contextvars
import json
import os
import queue
import re
import threading
import time
import urllib.error
import urllib.request
from typing import List

_STOP = {"the", "a", "an", "is", "are", "of", "to", "in", "on", "and", "or",
         "my", "your", "you", "it", "that", "this", "was", "were", "has", "have",
         # P1b-2b: question/aux words are MATCH NOISE — "when did my locker
         # combination last change?" scored 2/6=0.33 vs the 0.34 threshold
         # purely because "when"/"did"/"last" diluted the denominator. Facts
         # rarely contain these, so removing them sharpens matching symmetric-
         # ally (the audit gates re-ran GREEN after this change).
         "what", "who", "where", "when", "why", "how", "which",
         "did", "does", "do", "can", "could", "would", "should", "will",
         "had", "these", "those", "there", "here", "just", "please",
         # ── ASKING ABOUT MEMORY IS NOT A MEMORY (2026-07-14) ────────────────────
         # From the live transcript. He asked:
         #
         #     "do you REMEMBER what sex you are?"
         #
         # and the ranker handed her:
         #
         #     0.50  "then we can REMEMBER our idea's like this!"
         #     0.50  "REMEMBER my GPU is an RTX 2060."
         #     0.50  "REMEMBER this about me: my workshop is called Forge966733."
         #     0.00  'I am a woman'     <- speaker=self, identity, THE ACTUAL ANSWER
         #
         # THE VERB OF THE QUESTION MATCHED THE VERB OF THE JUNK. Her whole content vocabulary
         # for that question was {remember, sex}, so a row sharing the single word "remember"
         # scored 0.50 — while the row that answers it shares nothing lexically, because "sex"
         # is not "woman".
         #
         # And the junk rows contain "Remember" because they ARE captured instructions: the
         # store_verb bypass wrote "Remember my GPU is an RTX 2060." verbatim, instruction verb
         # and all. Junk begat junk. She was handed a GPU and a workshop when asked what she is,
         # and then confabulated the right answer from her persona — by luck, not memory.
         #
         # These words are how you ASK ABOUT the store. They are never what is IN it. Stopped on
         # BOTH sides, which also makes the fossil rows behave like the facts they were meant to
         # be ("Remember my GPU is an RTX 2060" -> {gpu, rtx, 2060}).
         "remember", "remembers", "remembered", "recall", "recalls", "know", "knows",
         "knew", "tell", "tells", "told", "say", "says", "said", "memory", "memories",
         "forget", "forgets", "forgot", "mention", "mentions", "mentioned", "stored"}


def _reg_path() -> str:
    return os.environ.get("SP_RECALL_REGISTRY", "")


def _load(path: str = "") -> List[dict]:
    # `path` (2026-08-24 audit, C): callers with an explicit registry (gates, PersonModel
    # pointed at a fixture) come through the same parser as everyone else instead of
    # keeping a private JSONL loop. Default is the live registry, as ever.
    p = path or _reg_path()
    if not p or not os.path.exists(p):
        return []
    eps = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                eps.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return eps


# ── THE REGISTRY IS READ-MODIFY-WRITTEN FROM SEVERAL THREADS (2026-07-14) ──────────────
# The gateway is a ThreadingHTTPServer — a thread per request — and the mint worker below is
# another. Every mutation here is load-all / change / rewrite-all. Two of those interleaving is a
# LOST WRITE: thread A loads 86 rows, thread B loads the same 86, A appends and rewrites 87, B
# appends its own and rewrites 87 — and A's fact is gone, silently, with no error and no tombstone.
#
# os.replace is atomic, so the FILE is never half-written. That is a guarantee about bytes, not
# about facts, and it is the guarantee we already had. The one we need is that a read-modify-write
# is not interleaved with another, and that takes a lock.
#
# It has to be an RLock: remember() takes it and calls _save_all(), which takes it again.
_REG_LOCK = threading.RLock()


def registry_lock():
    """The registry's read-modify-write lock, exported for the OTHER writer
    (harness/maintenance/ops.py). ops loaded, mutated and rewrote the store holding
    NOTHING, while the scheduler runs ops.compact() unattended DURING live turns —
    the exact interleaving the comment above describes, on the path that touches the
    most rows at once. One lock, both writers, or the lock guards one of two paths
    and therefore neither."""
    return _REG_LOCK


# ── THE MINT QUEUE: SHE ANSWERS FIRST, THE CACHE CATCHES UP ────────────────────────────
# One worker, one queue, daemon thread. Deliberately ONE: the daemon is a single GPU and the whole
# point is to stop contending with the turn she is trying to answer. Four parallel captures would
# just move the stall from the harness into the engine.
_MINT_Q: "queue.Queue" = queue.Queue()
_MINT_WORKER = None
_MINT_LOCK = threading.Lock()


def _mint_is_async() -> bool:
    """Async unless explicitly told otherwise. SP_CAPTURE_ASYNC is mapped in serve.py (it has to
    be: build_env now strips every unmapped SP_*, so an unmapped knob is an unreachable one —
    G-ONEDOOR made that structural, and it is what forced this to be a real profile knob rather
    than a getenv nobody could find)."""
    return os.environ.get("SP_CAPTURE_ASYNC", "1") == "1"


# ── THE ENGINE MAY REFUSE, AND IT DID, SILENTLY, FOR WEEKS (2026-08-23) ────────────────
# MEASURED on the live store: 253 of the 253 rows written since 2026-08-19 carry npos=0 and
# no minted_at — not one KV episode. 641 of the 747 directories under var/memory/eps/ are
# EMPTY. Zero ep.l5 sidecars in three weeks. The cause, straight from the route:
#
#   gemma4_decode_cuda: gemma4-MoE not supported on this path — its three internal FFN
#   copies are not on the g4_ffn_apply seam (ADR-013); use the served decode
#
# /v1/capture cannot run on the model MoE and has not since the model landed. Her MEMORY is
# unaffected — the registry is the recall authority and never touches the daemon — but the
# engine-side episode representation is empty for everything recent, and so is the L5 half
# of the semantic index. That second consequence is the load-bearing one: EVERY embedding
# contender this repo measured and rejected was measured against a 93%-hash document index.
#
# It failed silently because the whole call sat under a bare `except: return 0, False`,
# which cannot tell "the daemon is down" from "the engine says never". Those need different
# answers, and now they get them:
#   transport failure   -> quiet, retried on the next fact, exactly as before.
#   a REFUSAL with a body -> logged ONCE with the engine's own words, and not asked again
#                            this process. Retrying a structural no, per fact, forever, is
#                            how 641 empty directories happen.
_CAPTURE_REFUSED = {"why": "", "at": 0.0, "n": 0}


def capture_status() -> dict:
    """Why the KV mint is not running, if it is not. Read by _registry_health so the number
    reaches a surface instead of sitting in a stat nobody prints."""
    return dict(_CAPTURE_REFUSED)


def eps_root() -> str:
    """Where episodes live. Beside the registry unless told otherwise.

    AN EPISODE IS BIG AND COLD: ep.k + ep.v at full depth per position, mean 11.1 MB
    over her real ones, written once and read only on a deep recall. That is exactly
    the shape you want OFF the working drive, and this box has a 32 GB Optane sitting
    idle (F:). MEASURED at that shape (tools/disk_bench.py, unbuffered): F: writes at
    0.30 GB/s and random-reads 2.84 MB blocks at 1.36 GB/s -- slower than D:, and far
    too slow to stream EXPERTS from, which is why that idea was measured and dropped.
    For an 11 MB write-once blob it is ample: ~37 ms to mint, ~8 ms to read back.

    The row carries its own absolute `dir`, so moving the root does not orphan
    anything already written -- old episodes stay where they are and are still found.
    """
    d = (os.environ.get("SP_EPS_DIR") or "").strip()
    if d:
        return d.replace("\\", "/").rstrip("/")
    return os.path.join(os.path.dirname(_reg_path()), "eps").replace("\\", "/")


def _mint_now(daemon: str, fact: str, out_dir: str):
    """The blocking capture. Still used when async is off (gates that want determinism) and by the
    background worker, which is the only place it belongs.

    NO ENGINE, NO MINT (2026-08-21): under a foreign backend there is no /v1/capture; the
    row still lands with npos=0 — recall is text/sem, no episode. Said once, not retried
    into a timeout per fact."""
    try:
        from harness.inference.backends import supports as _sup
        if not _sup("capture"):
            return 0, False
    except Exception:
        pass
    if _CAPTURE_REFUSED["why"]:
        _CAPTURE_REFUSED["n"] += 1        # counted, not retried: the engine already said no
        return 0, False
    # ── THE DISK FLOOR (2026-08-23, the day the mint came back). ──────────────────
    # An episode is not small: MEASURED over her 51 real ones, mean 11.1 MB and max
    # 79.1 MB (ep.k + ep.v are the full-depth K/V rows for every position). While
    # /v1/capture was refusing on the MoE this cost nothing, and the drive filled up
    # for other reasons — 930 of 932 GB, 2.57 GB free, about 231 episodes of headroom.
    # Turning the mint back on without a floor would quietly spend that in a week.
    #
    # A FULL DISK IS NOT A MEMORY PROBLEM, it is an everything problem: the gateway
    # log, the KV snapshot capture and the registry write all fail on it, and the
    # registry write is the one that would actually lose something of hers. So the
    # mint yields first. The row still lands with npos=0 — recall is text + semantic,
    # no episode — which is exactly the documented degradation for "no engine, no
    # mint", reached by a different road.
    #
    # Said ONCE through the same breaker as a structural refusal, because "the disk is
    # full" is also a standing no rather than a transient one; it clears on restart,
    # by which time somebody has either freed space or not.
    #
    # THE PROBE IS INSIDE THE try; THE REFUSAL IS NOT. First draft put the whole thing
    # in one try/except and called a `logger` this module does not have — the NameError
    # was swallowed by the except, execution fell through, and the mint ran anyway. A
    # guard whose failure mode is "no guard" is worse than no guard, because it reads
    # like protection. So: measure defensively, decide in the open.
    # ...AND THE PROBE MUST ASK A DIRECTORY THAT EXISTS. `out_dir` is the episode dir
    # and it has NOT been created yet at this point, so disk_usage() on it (or on its
    # parent, the first time) raises and the guard silently skips — measured: the floor
    # set to an impossible 9000 GB and the mint ran anyway, npos=12. Walk up to the
    # nearest ancestor that exists; the free space of any of them is the same volume.
    _free_gb = None
    try:
        import shutil
        _p = os.path.abspath(out_dir)
        for _ in range(6):
            if os.path.isdir(_p):
                break
            _up = os.path.dirname(_p)
            if _up == _p:
                break
            _p = _up
        _free_gb = shutil.disk_usage(_p if os.path.isdir(_p) else ".").free / 1e9
    except Exception:
        _free_gb = None                   # a broken probe must never block a memory
    if _free_gb is not None:
        try:
            _floor = float(os.environ.get("SP_CAPTURE_MIN_FREE_GB", "2") or 2)
        except ValueError:
            _floor = 2.0
        if _free_gb < _floor:
            why = ("disk floor: %.2f GB free, below the %.2f GB floor — the mint yields "
                   "so the registry write does not fail. Rows land with npos=0; recall is "
                   "text + semantic until there is room." % (_free_gb, _floor))
            _CAPTURE_REFUSED.update(why=why, at=time.time(), n=1)
            return 0, False
    try:
        body = json.dumps({"text": fact, "out_dir": out_dir}).encode()
        req = urllib.request.Request(
            daemon + "/v1/capture", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            j = json.loads(r.read().decode())
        npos = int(j.get("npos", 0))
        return npos, (bool(j.get("ok", False)) or npos > 0)
    except urllib.error.HTTPError as exc:
        # THE ENGINE ANSWERED, AND THE ANSWER WAS NO. Its body says why; say it once.
        why = ""
        try:
            why = str((json.loads(exc.read().decode()) or {}).get("error", ""))[:400]
        except Exception:
            why = "HTTP %s" % getattr(exc, "code", "?")
        if why and not _CAPTURE_REFUSED["why"]:
            _CAPTURE_REFUSED.update(why=why, at=time.time(), n=1)
            try:
                import logging
                logging.getLogger("harness.memory").warning(
                    "[memory] /v1/capture REFUSED by the engine; rows will carry npos=0 and "
                    "no ep.l5 until this is fixed. Not asked again this process. Engine said: %s",
                    why)
            except Exception:
                pass
        return 0, False
    except Exception:
        return 0, False                   # transport: quiet, and tried again next time


def _mint_drain():
    while True:
        item = _MINT_Q.get()
        try:
            if item is None:
                return
            fact, out_dir = item
            daemon = os.environ.get("SP_DAEMON_URL", "http://127.0.0.1:3000")
            npos, minted = _mint_now(daemon, fact, out_dir)
            if not minted:
                continue
            # Update the row IN PLACE, found by its out_dir — NOT by its text.
            #
            # By the time this lands, the turn is long over and the store has moved on. If we
            # matched on text, a reinforcement or a supersede could have changed which row that
            # text belongs to, and we would stamp npos onto the wrong memory. `dir` is unique per
            # capture and was written at the same instant as the row. It is the only key that
            # still means what it meant when we queued it.
            with _REG_LOCK:
                rows = _load()
                hit = next((r for r in rows if r.get("dir") == out_dir), None)
                if hit is not None:
                    hit["npos"] = npos
                    hit["minted_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    _save_all(rows)
            # SEM S0: if the engine wrote an ep.l5 sidecar into this episode dir, append
            # the l5-space index row (an UPGRADE is an APPEND — nothing is edited).
            # /v1/capture mints ep.l5 when SP_CAPTURE_L5=1. upgrade() no-ops when the
            # sidecar is absent. Never raises.
            if hit is not None:
                from harness.skills import semindex as _sem
                _sem.upgrade(out_dir, fact, hit.get("ts", ""))
        except Exception:
            pass
        finally:
            _MINT_Q.task_done()


def _mint_later(fact: str, out_dir: str) -> None:
    global _MINT_WORKER
    with _MINT_LOCK:
        if _MINT_WORKER is None or not _MINT_WORKER.is_alive():
            _MINT_WORKER = threading.Thread(target=_mint_drain, name="sp-mint",
                                            daemon=True)
            _MINT_WORKER.start()
    _MINT_Q.put((fact, out_dir))


def mint_backlog() -> int:
    """How many episodes are still waiting to be minted. For the gate and the ops panel."""
    return _MINT_Q.qsize()


def mint_drain_blocking(timeout: float = 30.0) -> bool:
    """Wait for the queue to empty. Gates and shutdown only — never a turn."""
    t0 = time.time()
    while _MINT_Q.qsize() and time.time() - t0 < timeout:
        time.sleep(0.05)
    return _MINT_Q.qsize() == 0


# ── A STRANDED .tmp IS EVIDENCE, NOT LITTER (2026-08-24 audit, H4) ─────────────────────
# tmp+os.replace means a crash between the write and the replace leaves `<store>.tmp` on
# disk — a complete candidate registry that never became the registry. One is sitting in
# the live var/memory right now. The next _save_all would open that same path "w" and
# SILENTLY OVERWRITE it: the only record of what the dying process was about to commit,
# gone, from the store whose one doctrine is that nothing is destroyed. So the first
# write per path per process moves it aside to a timestamped quarantine name and says so
# in the log. Never deleted, never auto-restored — restoring would resurrect a rewrite
# whose context is unknowable; the operator can diff it against the store at leisure.
# Checked once per path per process: a crash kills the process, so the next stranding
# can only be met by a fresh process. Shared with notes._write_all — ONE implementation,
# both tmp+replace writers, or the doctrine holds in one of two lanes and thus neither.
_TMP_RESCUED: set = set()


def rescue_stray_tmp(path: str) -> str:
    """Quarantine a stranded `path + '.tmp'` (crash leftover). Returns the quarantine
    filename, or '' when there was nothing to rescue. Logged, never silent."""
    if not path or path in _TMP_RESCUED:
        return ""
    _TMP_RESCUED.add(path)
    tmp = path + ".tmp"
    try:
        if not os.path.exists(tmp):
            return ""
        dest = "%s.stranded-%s" % (tmp, time.strftime("%Y%m%d-%H%M%S", time.gmtime()))
        os.replace(tmp, dest)
        try:
            import logging
            logging.getLogger("harness.memory").warning(
                "[memory] stranded %s found beside its store (a crash between the tmp "
                "write and os.replace) — quarantined to %s. Nothing deleted, nothing "
                "auto-restored; diff it against %s if you want to know what was lost.",
                tmp, dest, path)
        except Exception:
            pass
        return dest
    except Exception:
        return ""                         # a broken rescue must never block a write


def _save_all(rows: List[dict]) -> None:
    """Rewrite the registry. Atomic via os.replace — a half-written memory file is worse
    than a stale one, and this is now called on the hot path (every reinforcement)."""
    p = _reg_path()
    if not p:
        return
    with _REG_LOCK:
        rescue_stray_tmp(p)               # BEFORE open(tmp,"w") clobbers the evidence (H4)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, p)


def _text(e: dict) -> str:
    return e.get("text") or e.get("topic") or ""


def _depluralise(w: str) -> str:
    """cats -> cat, names -> name, sensors -> sensor.

    ── HE ASKED ABOUT HIS "CATS NAME" AND GOT HIS OWN (2026-07-14) ─────────────────────
    From the live transcript, after the ownership fix landed and the question correctly scoped
    to HIM — it still answered with the wrong row:

        "do you remember my CATS name?"  ->  "The user's name is Sam"

    Because the tokenizer strips punctuation, so the STORE holds cat's -> {cat}, while the
    QUESTION holds cats -> {cats}. The possessive and the plural never touch, so the only token
    left in common with any row was `name` — and every name row matched it equally.

    The relationship penalty missed for the same reason: _REL_NOUN is \\bcat\\b, and "cats" is not
    "cat", so the cat row was never even recognised as being about a cat.

    Crude, deliberately: a real stemmer is a dependency and a new failure surface, and this is a
    bag-of-words matcher, not a linguist. It only has to be applied IDENTICALLY to both sides,
    which is the one property that actually matters. 'glass' -> 'glas' on both sides still matches
    'glass' -> 'glas'.
    """
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def _toks(s: str) -> set:
    words = "".join(c.lower() if c.isalnum() else " " for c in s).split()
    return {_depluralise(w) for w in words if len(w) >= 3 and w not in _STOP}


def _overlap(query: str, target: str) -> float:
    qt = _toks(query)
    if not qt:
        return 0.0
    return len(qt & _toks(target)) / len(qt)


# ──── the tools ────────────────────────────────────────────────────────────
def live_rows(testimony: bool = False) -> List[dict]:
    """Every LIVE row, in store order — THE non-ranking sibling of
    search_memories_ranked_rows(). A reader that does not rank still may not see the
    dead: nine readers across the tree were re-implementing this filter privately, with
    THREE different predicates (`lifecycle`, `superseded_by`, `verdict.sigma`) — and the
    2026-08-19 audit found a live orphan tombstone (lifecycle=1, no superseded_by) that
    was dead to every reader and alive to the whole supersede machinery. One predicate,
    one function; a new reader calls this or the seam, never neither.

    testimony=True additionally applies lifecycle.testimony_wins() — for MODEL-FACING
    readers (tools she speaks from): a covered inference does not take the floor. The
    audit lane and maintenance passes want testimony=False: they must see everything
    live, judged or not."""
    rows = [e for e in _load() if not e.get("lifecycle")]
    if testimony:
        from harness.skills import lifecycle as lc
        rows = [e for _s, e in lc.testimony_wins([(0.0, e) for e in rows])]
    return rows


def all_rows(path: str = "") -> List[dict]:
    """Every row, TOMBSTONES INCLUDED, in store order — THE AUDIT LANE DOOR (2026-08-24
    audit, C). live_rows() is for readers that serve; this is for readers that ACCOUNT:
    maintenance, PersonModel's evidence walk, anything answering "what did she believe,
    when". It exists so an audit reader stops opening SP_RECALL_REGISTRY itself with a
    private JSONL loop (person.py did; malformed-line policy and parse behaviour then
    drift per reader). Callers apply lifecycle.is_retired() themselves — asking for the
    dead is the point of this door. `path` serves callers pointed at a fixture."""
    return _load(path)


def supports_of(row_or_name, path: str = "") -> List[dict]:
    """The rows a distillate was drawn FROM, resolved to actual rows — TOMBSTONES INCLUDED.

    THE GAP THIS CLOSES (2026-08-25 audit). `derived_from` has been written since
    2026-08-22, enforced nightly by orphaned_distillates/retire_orphans, and gated by
    G-PROVENANCE. Nothing could READ it. The only code in the tree that resolved a name
    to a row was a private dict inside `lifecycle.orphaned_distillates`, and the only
    place the names ever left the process was a maintenance POST body listing rows it had
    just killed. The receipts were on disk and nothing could print them, so "why do you
    believe that?" got exactly zero steps.

    RETIRED SUPPORTS ARE THE POINT, not an edge case: a conclusion resting on things she
    no longer holds is the single most useful thing this can say. Callers decide what to
    do with them — `lifecycle.is_retired()` is right there. A name that matches no row is
    dropped rather than faked; unknown is not dead (the same narrowness
    orphaned_distillates keeps), and `missing_supports` names them for anyone who cares.

    Order follows `derived_from`, which is the order the consolidator read them in."""
    row = row_or_name if isinstance(row_or_name, dict) else None
    rows = _load(path)
    if row is None:
        row = next((r for r in rows if r.get("name") == row_or_name), {})
    names = row.get("derived_from") or []
    by_name = {r.get("name"): r for r in rows}
    return [by_name[n] for n in names if n in by_name]


def missing_supports(row_or_name, path: str = "") -> List[str]:
    """Support names that resolve to no row at all — see supports_of. Unknown, not dead."""
    row = row_or_name if isinstance(row_or_name, dict) else None
    rows = _load(path)
    if row is None:
        row = next((r for r in rows if r.get("name") == row_or_name), {})
    have = {r.get("name") for r in rows}
    return [n for n in (row.get("derived_from") or []) if n not in have]


def dependents_of(row_or_name, path: str = "") -> List[dict]:
    """The other direction: every distillate that names THIS row among its supports.

    The forward walk answers "what is this conclusion made of". This one answers the
    question a curate panel actually asks before he retires something — "what rests on
    this, if I take it away?" — and it is what makes the nightly orphan sweep legible
    BEFORE it fires rather than only in the log line after. Tombstoned distillates are
    included: a dead conclusion still rested on this row, and hiding that would be the
    audit lane lying to make a listing tidier."""
    name = row_or_name.get("name") if isinstance(row_or_name, dict) else row_or_name
    if not name:
        return []
    return [r for r in _load(path) if name in (r.get("derived_from") or [])]


def orphan_tombstones(path: str = "") -> List[dict]:
    """AUDIT: tombstones with no `superseded_by` breadcrumb (2026-08-24 audit, H5).
    The live store carries 25 of them (repair-era retirements; forget() before it grew
    its breadcrumb). They are DEAD to every reader — `lifecycle` is the one death field
    — but they cannot answer WHY they died, which is the audit lane's whole question.
    This helper only RETURNS them, for the curate panel to show him one day; rewriting
    history onto 25 old rows is his call row by row, never a maintenance pass's."""
    return [r for r in _load(path) if r.get("lifecycle") and not r.get("superseded_by")]


def list_memories() -> str:
    """List every fact currently stored in long-term memory."""
    # LIVE (not retired), FRAMED, and SPEAKABLE. It used to dump every row raw — including
    # superseded ones — so she read back tombstones as current, and read HIS first-person
    # facts ("My name is Sam") as if they were her own. And until 2026-08-19 it skipped
    # testimony_wins(), so 8 seam-silenced inferences took the floor through this door
    # verbatim. The owner is stamped on the row; render it. The floor is his; hold it.
    # _present_row (2026-08-24, A3): a private-secret row is listed as withheld, never
    # dumped — a listing asks no attribute, so it may serve none. G-SECRET §5.
    eps = live_rows(testimony=True)
    if not eps:
        return "(memory is empty)"
    return "\n".join(f"{i + 1}. {_present_row(e)}" for i, e in enumerate(eps))


def remember(fact: str, source: str = "", *, kind: str = "", mem_class: str = "",
             derived_from: "list[str] | None" = None, support_days: int = 0,
             support_kinds: "list[str] | None" = None) -> str:
    """Store a fact in long-term memory. Pass the COMPLETE fact as a full standalone sentence
    (e.g. "The user's favorite color is teal", not just "teal") so it is meaningful on its own later.
    `source` (optional) records WHERE the fact came from (e.g. "user turn", "consolidator",
    "operator") for the MEM-OKF v2 provenance lane — recallable via provenance().
    `kind` / `mem_class` (keyword-only; The Real Her, 2026-08-22): ONLY for her own
    narrative — honoured when the author is self and mem_class is self-narrative or
    feeling; otherwise ignored and the fact goes through the ordinary admission.
    `derived_from` / `support_days` / `support_kinds` (2026-08-22): for DISTILLATES only —
    the row names this conclusion was drawn from and how broad that window was. Set by the
    harness's own consolidating producers (becoming, the journal, insight, the
    consolidator); the model never passes them. See lifecycle.orphaned_distillates."""
    p = _reg_path()
    if not p:
        return "[no registry configured]"
    # ── ANONYMOUS MODE (2026-08-23, his ask) ─────────────────────────────────────────
    # THE ONE DOOR IS WHY THIS IS ONE LINE. Everything that ever enters this store comes
    # through remember() — the tool, _capture_after_turn, the consolidator, the reflector,
    # remember_about_self and therefore every self-narrative row, the episode mint and the
    # semantic index that hang off the write below. Guarding HERE guards all of them,
    # including callers written after this line. Guarding callers instead is how you get a
    # mode that says "nothing was recorded" over an evening sitting in the registry.
    # It returns a SENTENCE, not a silent no-op: she reads this string, and a store verb
    # that quietly fails is how she ends up promising to remember what she cannot.
    from harness.control import anon as _anon
    if _anon.holds("memory.row"):
        return _anon.WHY
    # ADMISSION AT THE STORE (2026-07-12). The daemon's B4 gate now refuses impersonal
    # sentences — and she immediately stored one THROUGH THIS TOOL instead (G-ADMISSION
    # caught an ep_tool_ row holding "The kind nurse painted the tall building..."). An
    # invariant guarded in only ONE of the paths into memory is not guarded. Every path
    # enforces it now.
    from harness.skills import lifecycle as lc

    # THE PACKAGING COMES OFF AT THE DOOR (2026-07-14). "Remember my GPU is an RTX 2060." is a
    # FACT WEARING AN IMPERATIVE. Stored whole, the verb becomes content (it retrieved itself on
    # "do you REMEMBER what sex you are?") and the slot is wrong ("remember my gpu", not
    # "user::gpu", so it never superseded the real GPU row). Every guard below must see the CLAIM,
    # not the wrapper. See lifecycle.normalize_fact.
    _raw = fact                         # her narrative is judged and kept AS SAID (below)
    fact = lc.normalize_fact(fact)

    # ── THE REAL HER (2026-08-22): her narrative is admitted as HERS, by its own rule ──
    # A producer (the kairos speak path, the journal, a verified persona shift, the
    # stance extractor, the nightly becoming) names the class and the kind; the author
    # must be self. Outside her lane the explicit class means nothing.
    from harness.skills import memclass as _mc
    _self_narr = (_AUTHOR.get() == "self" and mem_class in (_mc.SELF_NARRATIVE, _mc.FEELING)
                  and kind in _mc.NARRATIVE_KINDS)
    if _self_narr:
        # NOT normalized: normalize_fact() strips an imperative wrapper ("remember ...")
        # off a fact HE states; her journal line is not an instruction, and stripping it
        # also hid a tool receipt from the machine-text check (G-REAL-HER §1).
        fact = " ".join(_raw.split())
        ok, why = lc.is_narratable(fact)
        if not ok:
            return f"not stored — {why}"
    else:
        mem_class, kind = "", ""
        ok, why = lc.is_memorable(fact)
        if not ok:
            return f"not stored — {why}"
    # ── THE IDENTITY FIREWALL (2026-07-12) ──────────────────────────────────────
    # She answered "what is your name?" with "My name is Kairos." — correctly — and then
    # stored that sentence HERE, in the USER store. It was stamped speaker=user, classed
    # identity, and superseded all three rows that said the user is Sam. The store came
    # out of it asserting that SAM IS CALLED KAIROS.
    #
    # Which door she writes to is the ONLY signal for whose fact it is, and she picked the
    # wrong one. The prompt already tells her; a prompt is advice, and the price of one
    # slip is the user's identity. So the door refuses it, and names the right door.
    if _AUTHOR.get() != lc.SPEAKER_SELF:
        ok, why = lc.admit_to_user_store(fact, _self_names())
        if not ok:
            return f"not stored — {why}"
    # ── A REPEAT IS NOT A DUPLICATE. IT IS A SECOND DATA POINT. (2026-07-13) ────────
    #
    # These two guards used to read:
    #     if <exact match>:      return f"already in memory: {fact}"
    #     if <paraphrase>:       return f"already in memory (paraphrase of): {...}"
    #
    # and that was the end of it. Every time he told her something AGAIN, the store said
    # "I know" and threw the event away. It was proud of not duplicating a row.
    #
    # But the repetition IS THE SIGNAL. A thing a person tells you five times is not the
    # same thing as a thing they told you once, and we were recording them identically.
    # She said it herself, unprompted, on a kairos check-in: "memory has context — WHO told
    # you what, WHEN, maybe even HOW MANY TIMES." She had who. She had when. The third one
    # was arriving on every restatement and being deleted at the door.
    #
    # So a repeat REINFORCES: mentions += 1, last_seen = now, first_seen preserved. Still
    # exactly one row — the dedupe was right about the STORAGE and wrong about the EVENT.
    def _reinforce(e: dict, why: str) -> str:
        lc.reinforce(e)
        _save_all(existing)
        n = e.get("mentions", 2)
        return (f"reinforced ({n}x): {_text(e)}"
                + (f"  [{why}]" if why else ""))

    # ── THE REINFORCE BRANCH IS A READ-MODIFY-WRITE, SO IT HOLDS THE LOCK (2026-08-24
    # audit, A2). The invariant at _REG_LOCK's definition says a load/change/rewrite is
    # not interleaved with another — and this branch loaded OUTSIDE the lock, mutated a
    # row, and _save_all'd the stale list: a remember() landing between the read and the
    # write was silently rewritten away, the exact lost-write shape the comment up there
    # narrates, on the hottest write path in the file. The store branch below re-reads
    # inside its own locked block and was always right; this one now matches it.
    # The lock is RELEASED before the mint/supersede work that follows — _mint_now can
    # block on HTTP for up to 120 s when SP_CAPTURE_ASYNC=0, and a registry lock held
    # across a GPU call would serialize every concurrent turn behind it. A stale
    # `existing` beyond this block is safe by construction: the store branch applies
    # its tombstones by NAME against a fresh locked read. RLock, so _save_all's own
    # acquire nests without deadlock; nothing in this block does I/O beyond the store.
    # Gate: G-REGISTRY-RMW (mutant: lift this `with` and it goes red by name).
    with _REG_LOCK:
        existing = _load()

        for e in existing:
            if e.get("lifecycle"):
                continue                   # a tombstone is not reinforced back to life
            if _text(e).strip() == fact.strip():
                return _reinforce(e, "")

        ft = _toks(fact)
        if ft:
            for e in existing:
                if e.get("lifecycle"):
                    continue
                et = _toks(_text(e))
                if not et:
                    continue
                inter = len(ft & et)
                if inter / len(ft) >= 0.9 and inter / len(et) >= 0.9:
                    return _reinforce(e, "said again, in different words")
    # ── SHE WAS MADE TO WAIT ON A GPU BEFORE SHE WAS ALLOWED TO ANSWER HIM (2026-07-14) ────
    #
    # This block used to POST /v1/capture SYNCHRONOUSLY, with timeout=120, right here — on the
    # write path of every single fact. And _capture_after_turn() calls remember() once PER DURABLE
    # SENTENCE, up to four, BEFORE the gateway returns her reply (app.py:116, :128).
    #
    # MEASURED against the live daemon, warm, nothing else running:
    #
    #     527 ms  'My workshop bench is made of oak'
    #     403 ms  'Sam has an esp32 running the sensors'
    #     475 ms  'My NUC runs 24/7 in the cupboard'
    #     297 ms  'Sam is teaching himself the guitar'
    #     ------
    #    1702 ms  ADDED TO A ~4,400 ms TURN, before he sees a single token of what she says.
    #
    # And that is the GOOD case. timeout=120, four facts: THE WORST CASE IS EIGHT MINUTES OF
    # SILENCE because she is waiting on a GPU to finish building a cache. Exactly the shape of the
    # judge-call bug (#19-#22): AN AUX MODEL CALL SITTING INLINE ON A PATH A HUMAN IS WAITING ON.
    #
    # ── AND THE THING SHE WAS WAITING FOR IS NOT READ ON THIS PROFILE ──────────────────────
    # The mint builds ep.k/ep.v/ep.mf: KV blobs for the ENGINE's L5/replay recall. On the live
    # profile `authority = 'spine'`, and app.py:816 sets `cfg.auto_recall = False` on EVERY gateway
    # turn — so the engine's recall, THE ONLY CONSUMER OF THESE EPISODES, never runs on a turn.
    # In the harness, `npos` is read by exactly two functions: memory_stats() and verify_registry().
    # Both of them are REPORTING. Nothing on the recall path reads it.
    #
    # So she was being held silent for up to 1.7 seconds building an artifact that the live recall
    # path is structurally incapable of reading. Not useless — the episodes serve the daemon-direct
    # fallback when the gateway is down — but they have no business on the critical path.
    #
    # THE ROW IS WHAT MATTERS AND THE ROW IS WRITTEN HERE, SYNCHRONOUSLY, WITH EVERY GUARD. Only
    # the KV mint is deferred: queued, done by one background worker, and the row is updated in
    # place with its npos when it lands. Nothing is lost, nothing is racy (see _REG_LOCK), and if
    # the process dies before the queue drains, the fact is still on disk — exactly as it already
    # was whenever the daemon happened to be unreachable.
    daemon = os.environ.get("SP_DAEMON_URL", "http://127.0.0.1:3000")
    out_dir = os.path.join(eps_root(), f"ep_tool_{int(time.time() * 1000)}")
    out_dir = out_dir.replace("\\", "/")
    npos = 0
    minted = False
    if _mint_is_async():
        _mint_later(fact, out_dir)                 # she answers him now; the cache catches up
    else:
        npos, minted = _mint_now(daemon, fact, out_dir)
    # ── MEM-OKF v2 LIFECYCLE (2026-07-12) ───────────────────────────────────────
    # SUPERSEDE-ON-CONFLICT. A fact that fills the same slot with a DIFFERENT value
    # retires the old one — tombstoned, never deleted, so "what did I used to think?"
    # stays answerable. Without this the registry was an append-only tape: it could
    # accumulate "My cat's name is Tuffy" AND "My cat's name is Milo" and recall would
    # cheerfully surface whichever matched first.
    from harness.skills import lifecycle as lc
    speaker = lc.infer_speaker(fact, _AUTHOR.get())

    # WHERE DID THIS CLAIM COME FROM, and therefore what may it do to the rest of the store?
    # An INFERENCE may be recalled, may be spoken in her own voice, and may be corrected by
    # anything he says — but it may NEVER retire something he told her. Proven necessary: she
    # concluded "Sam is comfortable in open water" and it TOMBSTONED his own "Sam is
    # terrified of open water". Her guess ate his testimony. See find_superseded().
    # THE one derivation, and it is passed everywhere it is needed (find_superseded,
    # dominance, stamp) instead of being re-derived from src prose at each door.
    # "consolidator" is here because its rows are the MODEL'S PARAPHRASES of a transcript,
    # not his words — stamped observed, 14 of them sat in the live store with full
    # authority to retire his actual testimony (verdict.may_supersede lets observed beat
    # observed). A paraphrase is her account of what he said: inferred.
    _INFERRED_SOURCES = ("reflection", "consolidator")
    status = (lc.STATUS_INFERRED
              if any(s in (source or "") for s in _INFERRED_SOURCES)
              else lc.STATUS_OBSERVED)
    # narrative ACCUMULATES — a new feeling or journal line never retires an older one;
    # only tombstoning does (The Real Her, 2026-08-22). Everything else supersedes as before.
    retired = [] if _self_narr else lc.find_superseded(fact, speaker, existing, status=status)

    # ── DOMINANCE PROPOSES; find_superseded AND verdict DISPOSE (docs/SEMANTICS.md §S2.1) ──
    # find_superseded fires only on an EXACT attribute_key match, so it cannot see this pair:
    #
    #     held  "Sam has a cat."
    #     new   "Sam's cat Tuffy is a female tabby."
    #
    # — nothing retires the vaguer row and both render. `dominance.find_subsumed` adds the
    # structurally-subsumed rows: topic containment AND 14-byte Dickson dominance, same
    # speaker, same `verdict.may_supersede` ruling as everything else.
    #
    # DEFAULT OFF (SP_SEM_DOMINATE). With the knob off `find_subsumed` returns [] and this
    # block is a no-op, so every verdict is byte-identical to pre-dominance behaviour — the
    # G-SEM-CONSERVE law. It stays off until the supersede rate has a measured bar: a proposer
    # with better recall than the thing it augments also has more ways to be wrong, and Paper
    # IV's own eviction measurement (93.86%, above its own 80% alarm) says which way it errs.
    # The knob is read INSIDE find_subsumed and nowhere else — one authority for one flag, so
    # there is no second place to forget it.
    from harness.skills import dominance as _dom
    _seen = {id(r) for r in retired}
    # ── AND HER LANE IS EXCLUDED ON A MEASUREMENT, NOT ONLY ON DOCTRINE (2026-08-23) ──────
    # "Narrative accumulates" is the rule; this is the evidence that the rule is also the
    # only safe engineering. fixtures/sem/dominate-self-receipt.json: SP_SEM_DOMINATE run
    # read-only over her 27 live narrative rows proposes 12 retirements — 0.44 per row
    # against 0.083 on his facts — and TWELVE OF TWELVE ARE WRONG, all the same way.
    # dominance's content carrier is topic_of plus names and numbers, built for ATTRIBUTIVE
    # facts ("Sam owns a blue kettle": a subject and an attribute). Her narrative is
    # EXPRESSIVE PROSE with almost no attributive content — a bare affectionate line reduces
    # to roughly ONE content word — so any longer sentence sharing that word dominates it
    # structurally, and a warmer variant is proposed to retire the plainer one.
    #
    # The hypothesis that lost was that her lane would be dominance's BEST case, because
    # near-duplicate restatement is rife there and retiring one of her own repeated lines is
    # low-stakes. The first half is true. The second does not follow: dominance cannot
    # IDENTIFY a near-duplicate in her lane, it identifies "shares a content word and is
    # longer" — on the material where being wrong costs the most. G-SEM-DOMINATE §10.
    for _r in ([] if _self_narr else _dom.find_subsumed(fact, speaker, existing, status=status)):
        if id(_r) not in _seen:
            retired.append(_r)
            _seen.add(id(_r))

    line = {
        "name": os.path.basename(out_dir),
        "dir": out_dir,
        "npos": npos,
        "topic": fact[:40],
        "sig_bits": "0" * 64,
    }
    lc.stamp(line, fact, speaker, source, supersedes=[r.get("name", "") for r in retired],
             status=status, mem_class=(mem_class or None), kind=kind,
             derived_from=derived_from, support_days=support_days,
             support_kinds=support_kinds)

    # INTEROP (load-bearing): the DAEMON already excludes superseded episodes from the
    # live recall set — but it keys on the integer `lifecycle` field (recall.rs:587,
    # routes.rs:2342: `if ep.lifecycle != 0 { continue }`), NOT on `superseded_by`.
    # A tombstone that only carries `superseded_by` is invisible to the engine and the
    # retired fact keeps getting recalled. Stamp BOTH: `lifecycle` for the engine,
    # `superseded_by`/`superseded_at` for the audit trail.
    line["lifecycle"] = 0

    # ── AN INFERENCE THAT ARGUES WITH HIM IS SILENCED, NOT CONVICTED (2026-07-14) ───────
    # She may not retire his testimony (find_superseded refuses it), so a wrong conclusion sits
    # LIVE alongside the thing it denies:
    #
    #     LIVE  observed  'Sam is terrified of open water'
    #     LIVE  inferred  'Sam is comfortable in open water'
    #
    # ...and unhandled she would say BOTH. "You told me you're terrified" and "I've come to think
    # you're comfortable", in one breath. Not a mind holding two hypotheses — a mind that HEARD HIM
    # AND CARRIED ON REGARDLESS, which is exactly what makes a companion feel like it isn't
    # listening.
    #
    # I first handled it HERE, at write time: detect the contradiction, mark it DISPUTED, retire
    # it. Then I went to build the detector and caught myself assembling a semantic contradiction
    # engine out of substring matching and a hand-written antonym list — the clever-fragile thing
    # this codebase has punished me for every single time, and with the worst possible failure
    # mode: A VERDICT I CANNOT DEFEND, WRITTEN TO DISK, WITH A TIMESTAMP ON IT.
    #
    # So the write path passes no judgment at all. It stores what she thinks, honestly labelled.
    # The rule that matters is not "her belief must be destroyed" — it is SHE DOES NOT GET TO SAY
    # IT OVER HIM, and that is a rule about SPEAKING. It lives at the recall seam
    # (lifecycle.testimony_wins), where a false positive costs a sentence instead of a fact.
    # ONE writer, under the same lock _save_all already holds. The previous shape
    # was a raw open("w") + open("a") beside a locked _save_all — two write paths,
    # and the unguarded one is the one remember() actually runs. Concurrent turns
    # (G-AUTHOR-CTX) hit PermissionError on Windows replacing a file the other
    # thread still had open.
    with _REG_LOCK:
        rows = _load()
        if retired:
            names = {r.get("name") for r in retired}
            for r in rows:
                if r.get("name") in names:
                    r["lifecycle"] = 1                     # the engine reads THIS
                    r["superseded_by"] = line["name"]      # the audit trail reads these
                    r["superseded_at"] = line["ts"]
        rows.append(line)
        _save_all(rows)

    # ── SEM S0 (docs/SEMANTICS.md): the sidecar semantic index ──────────────────────────
    # DERIVED data in a SEPARATE file — semindex can never write the registry, never
    # blocks, never raises (a failed mint is a telemetry tick, not an error in her
    # mouth). Off unless SP_SEM_MINT=1 AND SP_SEM_INDEX is set, both mapped in serve.py
    # (G-ONEDOOR). Gate: G-SEM-INDEX.
    from harness.skills import semindex as _sem
    _sem.mint(fact, line.get("ts", ""), out_dir=out_dir)

    note = ""
    if retired:
        old = lc.strip_prefix(_text(retired[0]))
        note = f" (superseded: '{old}')"
    return (f"stored: {fact}{note}"
            + ("" if minted else " (note: episode not minted; recall-on-restart only)"))


# WHO IS SPEAKING THIS TURN. The gateway sets this before dispatching tools. It is the
# load-bearing bit for identity: the SAME sentence ("I am male") is a fact about the
# USER when the user says it and a fact about KAIROS when she says it. Inferring the
# owner from the words at READ time is exactly how she started speaking as the user.
#
# PER-CONTEXT, NEVER PROCESS-WIDE (2026-08-19). These used to be module globals under
# a ThreadingHTTPServer. Concurrent turns (him typing + a kairos speak-up, or two
# tabs) crossed speaker attribution: turn A set _AUTHOR="self" for remember_about_self,
# turn B's remember() raced it, and B's fact was stamped with A's author. ContextVar
# is the seam — a thread/task cannot see another turn's author. Gate: G-AUTHOR-CTX.
_AUTHOR: contextvars.ContextVar[str] = contextvars.ContextVar("memory_author", default="user")
_QUESTION: contextvars.ContextVar[str] = contextvars.ContextVar("memory_question", default="")


def current_author() -> str:
    return _AUTHOR.get()


def current_question() -> str:
    return _QUESTION.get()


def set_author(who: str):
    """Stamp this context's author. Returns the ContextVar token so a caller can
    RESET the previous value instead of assuming it was 'user'."""
    return _AUTHOR.set("self" if who == "self" else "user")


def reset_author(token) -> None:
    """RESET to whatever the author was before set_author — the other half of the
    contract. Callers that did `finally: set_author("user")` were clobbering a
    surrounding self-turn (the exact class G-AUTHOR-CTX fixed in remember_about_self,
    left alive in ops.add/ops.insight until 2026-08-19)."""
    _AUTHOR.reset(token)


def reset_question(token) -> None:
    """The question's half of the same contract (2026-08-24 audit, A5): her unprompted
    turns now arm the lane with author=self and the impulse nudge, and must restore
    BOTH on the way out — resetting the author while leaving the previous turn's
    question standing is the lag _arm_turn's own receipt documents."""
    _QUESTION.reset(token)


_GENDER_WORDS = {
    "female": {"female", "woman", "girl", "she", "her"},
    "male": {"male", "man", "boy", "he", "him"},
}


def _self_names() -> set:
    """EVERY VALUE THAT CONSTITUTES HER — not just her name.

    The first firewall guarded the name, because the name is what had eaten his. Then she
    filed "I am a woman" as HIS identity and supersede retired "I am male": the store came
    out asserting that Sam is a woman. Same mechanism, one attribute to the left. I had
    fixed the instance and called it the class.

    So this returns her name AND her gender words, read live from the persona — a rename or
    a re-gender moves the firewall with her. The literals are the floor, not the truth."""
    vals = {"kairos", "kairos"}
    try:
        from harness.personality.persona_file import parse_persona
        from harness.personality.persona_file import persona_path
        path = persona_path()
        with open(path, encoding="utf-8") as f:
            _, state = parse_persona(f.read())
        for k in ("name", "self_name"):
            v = (state or {}).get(k)
            if isinstance(v, str) and v.strip():
                vals.add(v.strip().lower())
        g = (state or {}).get("gender")
        if isinstance(g, str) and g.strip():
            vals |= _GENDER_WORDS.get(g.strip().lower(), {g.strip().lower()})
    except Exception:
        pass
    return vals


def remember_about_self(fact: str, *, kind: str = "", source: str = "self",
                        derived_from: "list[str] | None" = None, support_days: int = 0,
                        support_kinds: "list[str] | None" = None) -> str:
    """Store a fact about YOURSELF (Kairos) — your own traits, your history, what you
    think or have come to believe. Use this for things true of YOU, not of the user.
    e.g. remember_about_self("I find astronomy genuinely moving") — NOT the user's facts.
    (`kind`/`source` and the provenance arguments are set by the harness's own producers
    for her narrative — journal, thought, narration, dream, self_description, spoke_up,
    feeling, chapter; you need not pass any of them.)"""
    from harness.skills import memclass as _mc
    tok = set_author("self")
    try:
        if kind in _mc.NARRATIVE_KINDS:
            cls = _mc.FEELING if kind == "feeling" else _mc.SELF_NARRATIVE
            return remember(fact, source=source, kind=kind, mem_class=cls,
                            derived_from=derived_from, support_days=support_days,
                            support_kinds=support_kinds)
        return remember(fact, source=source, derived_from=derived_from,
                        support_days=support_days, support_kinds=support_kinds)
    finally:
        _AUTHOR.reset(tok)


def provenance(fact: str) -> str:
    """Answer "where/when did I learn X?" — return the source + timestamp of the stored fact
    that best matches the query (MEM-OKF v2 §M1). The recallable provenance lane.

    Retired rows are skipped: this is a TOOL SHE CAN SPEAK FROM, not the audit lane. Asked "where
    did I learn that?" she must not answer out of a tombstone — the source of a fact that is no
    longer true is a true answer to a question nobody asked. And a seam-silenced inference does
    not get provenance-laundered back onto the floor either: same door class, same rule."""
    eps = live_rows(testimony=True)
    if not eps:
        return "(memory is empty)"
    best, hit = -1.0, None
    for e in eps:
        ov = _overlap(fact, _text(e))
        if ov > best:
            best, hit = ov, e
    if best < 0.3 or hit is None:
        return f"no stored fact matches '{fact}'"
    src = hit.get("src", "unknown source")
    ts = hit.get("ts", "unknown time")
    # Through _present_row, not a raw quote (2026-08-24, D2 + A3). This door quoted the
    # bare first-person row — "'My name is Sam' — learned from..." — while
    # docs/MEMORY-AND-RECALL.md has listed provenance among the render() doors since
    # 2026-08-19: the code catches up to the doc. It also quoted a private-secret's text
    # verbatim; now the secret rule runs first, and a direct ask (attribute present)
    # still answers, because provenance carries the query. G-MEMORY-LIFECYCLE / G-SECRET §5.
    out = f"{_present_row(hit, fact)} — learned from {src} at {ts}"
    # ── AND IF IT IS A CONCLUSION, WHAT IT RESTS ON (2026-08-25) ─────────────────────
    # `src` is prose and the doc forbids branching on it, so asked about a nightly
    # becoming paragraph this door used to answer "learned from reflection on myself
    # (nightly becoming)" — true, and useless, and the one question it exists for.
    # `derived_from` is the structured answer and was sitting on the row untouched.
    #
    # THE TOMBSTONE RULE STILL HOLDS, which is why this counts rather than quotes: a
    # retired support is NAMED IN THE TALLY and never spoken. "Two of them I no longer
    # hold" is the honest sentence — it tells him the conclusion is standing on thinner
    # ground than it was without her reading a dead row back as current. Every live
    # support goes through _present_row, so the framing and the secret rule apply here
    # exactly as they do at the four other doors.
    from harness.skills import lifecycle as _lc
    if _lc.is_distillate(hit):
        sup = supports_of(hit)
        live = [s for s in sup if not _lc.is_retired(s)]
        dead = len(sup) - len(live)
        gone = len(missing_supports(hit))
        bits = ["drawn from %d thing%s I'd kept" % (len(sup), "" if len(sup) == 1 else "s")]
        if hit.get("support_days"):
            bits.append("across %d days" % int(hit["support_days"]))
        if dead:
            bits.append("%d of which I no longer hold" % dead)
        if gone:
            bits.append("%d I can no longer find" % gone)
        out += "\n  " + ", ".join(bits) + "."
        for s in live[:5]:
            out += "\n    · " + _present_row(s, fact)
        if len(live) > 5:
            out += "\n    · ...and %d more." % (len(live) - 5)
    return out


def forget(fact: str) -> str:
    """Retire a stored fact (matches the closest LIVE fact by overlap). It stops being recalled
    and stops being spoken. It is NOT erased — see below.

    ── THIS TOOL HARD-DELETED THE ROW. FOR MONTHS. (2026-07-14) ────────────────────────────
    It read:

        kept = [e for e in eps if _text(e) != victim]
        with open(p, "w", encoding="utf-8") as f:      # <- rewrites the registry WITHOUT it
            for e in kept:
                f.write(json.dumps(e) + "\\n")

    The single doctrine this store has — NOTHING IS EVER DESTROYED; tombstone or quarantine, never
    delete — and sitting in the LIVE core toolset the whole time was a function that opened the
    registry in "w" and wrote it back short a line. Every tombstone, every supersede chain, every
    `superseded_by` breadcrumb, the entire audit lane that exists so we can ask "what did she
    believe, and when, and who told her" — all of it defeated by one tool call.

    And she can call it herself, on a 0.3 overlap match, mid-conversation. "You can forget about
    the water thing" and the closest row by bag-of-words overlap leaves the disk forever.

    I built the lifecycle system ON TOP of a function that deletes. Nobody grepped for the "w".

    NOW: it tombstones. lifecycle=1 (which is what the ENGINE keys on — recall.rs:587 skips it),
    plus a `forgotten_at` and a `superseded_by` breadcrumb so the audit lane can always answer WHY
    a row went quiet. She cannot recall it, she cannot speak it, and it is still there. Forgetting
    and destroying are not the same act, and only one of them is reversible.

    (2026-08-19: the "deliberate out-of-band hard delete" this note used to point at —
    compact_registry — turned out to be wired to the AUTOMATIC hygiene tick and to a
    model-callable tool, and it deleted the wrong twin. Nothing hard-deletes any more;
    compaction tombstones and quarantines. Gate: G-COMPACT.)
    """
    # The whole match-and-tombstone is ONE read-modify-write under the lock (2026-08-24
    # audit, A2): it read outside and rewrote inside, so a concurrent remember() between
    # the load and the _save_all was silently rewritten away — by the tool whose entire
    # docstring is about how it used to destroy things. Pure string matching inside; no
    # I/O beyond the store, no nesting hazard (RLock).
    with _REG_LOCK:
        rows = _load()
        if not rows:
            return "(memory is empty)"
        best, hit = -1.0, None
        for e in rows:
            if e.get("lifecycle"):
                continue                   # already retired: forgetting it again is a no-op
            ov = _overlap(fact, _text(e))
            if ov > best:
                best, hit = ov, e
        if best < 0.3 or hit is None:
            return f"no stored fact matches '{fact}'"
        hit["lifecycle"] = 1
        hit["superseded_by"] = "forget"
        hit["forgotten_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _save_all(rows)
    return f"forgotten (retired, not erased): {_text(hit)}"


def count_memories() -> str:
    """Count how many facts are currently stored in long-term memory."""
    # LIVE rows. This answered 165 when 131 were live — "currently stored" was counting
    # tombstones, so she told him she knew 34 things she is not allowed to say.
    return str(len(live_rows()))


# ──── ADR-007: ranked memory search (scales past the list_memories dump) ─────
# ── MEM-OKF per-entry policy dispatch (P1b-2b, G-MEMPOLICY-V3 doctrine) ──────
# The fixed decline for a private-secret whose asked-about attribute is NOT in
# the record: streamed with ZERO model inference so confabulation/leak is
# impossible by construction (mirrors the engine attr-gate + mempolicy_run.py).
DECLINE_MSG = "I have a record for that, but it does not include that specific detail."

_ATTR_STOP = set(
    "the a an of to in on at for and or is are was what which who where when "
    "my your name number code colour color brand breed seat".split())


def attr_absent(query: str, fact: str) -> bool:
    """Deterministic attr-gate (G-MEMPOLICY-V3 doctrine, recalibrated): the query
    matched the record (ranked overlap got us here) but asks for an attribute the
    record lacks. CALIBRATION NOTE: the engine runner's `>= len(qs)*0.6` rule is
    untrippable on its own printed test data (e.g. {installed, workshop, door}
    with one absent = 1 < 1.8) — those cases fell to the tolerated forward
    branch. Rehomed rule: decline iff ≥2 salient query tokens are absent AND
    they are at least HALF the salient set — elaborated-but-present questions
    ("…combination for the gym?", one stray token) still recite; genuinely
    different-attribute questions ("when did … last change?") decline."""
    qs = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2} - _ATTR_STOP - _STOP
    if not qs:
        return False
    fs = {w for w in re.findall(r"[a-z0-9]+", fact.lower()) if len(w) > 2}
    salient_absent = [w for w in qs if w not in fs]
    return len(salient_absent) >= 2 and len(salient_absent) * 2 >= len(qs)


# ── THE SECRET WAS GUARDED AT ONE OF FIVE DOORS (2026-08-24 audit, A3) ─────────────────
# spine.recall_decider — the automatic per-turn injection — has honoured private-secret
# since G-SECRET landed: absent attribute -> zero-inference decline, present attribute ->
# she may answer him. And EVERY OTHER READ DOOR in this file served the row verbatim:
# list_memories dumped it (model-callable, no question asked), recall() presented it,
# search_memories returned its raw text, provenance() quoted it. The live store holds a
# real credential as a private-secret row, so this was not hypothetical: the guard held
# on the path that runs automatically and on none of the paths she chooses. AGENTS.md §0,
# in the exact subsystem whose closed trap ("the privacy decline cannot fire") is the §0
# table's last row.
#
# THE RULE, once, here, consumed by every door in this file:
#   no question (a listing)      -> withheld. A dump has no attribute to test, and a
#                                   secret in a listing is a leak with pagination.
#   asked, attribute ABSENT      -> withheld (the decider's own attr_absent test).
#   asked, attribute PRESENT     -> served. He told her the secret; asked for the thing
#                                   itself she answers HIM — the decider's existing
#                                   semantics (G-SECRET §3: she is not made useless).
# The decider keeps its own dispatch (it needs the row to decline loudly rather than
# quietly); the ranked seam is deliberately NOT filtered, because dropping the row there
# would make the decider's decline unreachable — the guard must fire, not evaporate.
SECRET_WITHHELD_NOTE = "a private thing, held — ask me directly about it"


def secret_withheld(row: dict, query: str = "") -> bool:
    """Must this row's text stay out of a reply to this question? (See the note above.)"""
    if (row.get("mem_class") or "") != "private-secret":
        return False
    if not (query or "").strip():
        return True
    return attr_absent(query, _text(row))


def _present_row(row: dict, query: str = "") -> str:
    """THE class-aware render for the speaks-ABOUT-the-store doors in this file
    (list_memories, search_memories, provenance): lifecycle.render()'s framing, with the
    secret rule applied first. recall() speaks TO HER through world.present_for_her and
    applies secret_withheld itself — presentation differs by addressee (two rendering
    doors, on purpose), the withholding rule does not."""
    if secret_withheld(row, query):
        return SECRET_WITHHELD_NOTE
    from harness.skills import lifecycle as lc
    return lc.render(row)


def search_memories_ranked_rows(query: str, k: int = 5, min_overlap: float = 0.25,
                                include_retired: bool = False):
    """Like search_memories_ranked but returns (score, ROW) so callers can read
    per-entry policy fields (mem_class etc.). The policy dispatch rides this.

    ── THE SUPERSEDE MACHINERY WAS BYPASSED ON THE MAIN TURN PATH (2026-07-14) ────────────
    This function iterated _load() — EVERY row, tombstones included — and left the lifecycle
    filter to whoever called it. Two callers. ONE of them remembered:

        memory.recall()        [e for e in ... if not e.get("lifecycle")]     <- filtered
        spine.recall_decider() hits = search_memories_ranked_rows(...)        <- DID NOT

    recall_decider is the AUTOMATIC recall — the context injection that runs on EVERY TURN,
    without her choosing it. PROVEN, on the real code path:

        THE STORE:                     TOMBSTONE 'My GPU is an RTX 2060'
                                       LIVE      'My GPU is an RTX 3090'

        the recall() TOOL:             1. Sam told me: My GPU is an RTX 3090     correct
        INJECTED EVERY TURN:           -> My GPU is an RTX 2060      THE DEAD ONE, AND FIRST
                                       -> My GPU is an RTX 3090

    He tells her he upgraded his card. Supersede fires perfectly, writes the tombstone — and then
    every turn for the rest of her life the automatic recall hands her the corpse ANYWAY, ranked
    ABOVE the truth, and she has no way to know one of them is dead.

    So the entire lifecycle system — supersede, the identity firewall, all of MEM-OKF v2, every
    correction he has ever made — was live ONLY when she happened to call the recall() TOOL. On
    the path that actually feeds her context, it never ran at all.

    THE BUG IS NOT THE MISSING FILTER. It is that an invariant every reader must hold was written
    in a CALLER instead of in the SEAM they share — the same shape as on_user_turn armed on one
    path of two, and the shear guard testing a proxy. A rule enforced in one of two paths is
    enforced in NEITHER, because the unguarded path is the one that runs.

    It lives here now. A caller can no longer forget it; it must ASK for the dead
    (include_retired=True), which is a thing only the audit lane has any business doing.

    ── AND TESTIMONY OUTRANKS INFERENCE, IN THE SAME SEAM ─────────────────────────────────
    An inference is not a memory of something that happened; it is a conclusion she drew. She is
    allowed to be wrong about him. SHE IS NOT ALLOWED TO SAY IT OVER HIM. If she has concluded
    something about a topic HIS OWN WORDS already cover, his words go and her guess stays home:

        observed  'Sam is terrified of open water'   <- he told her
        inferred  'Sam is comfortable in open water' <- she decided otherwise

    Surfacing both is not scrupulous, it is deaf: she would say "you told me you're terrified" and
    "I've come to think you're comfortable" in one breath. This is a SPEECH rule, not a storage
    rule — nothing is destroyed, the inference stays on disk and stays auditable. It simply does
    not get to take the floor on a subject he has already spoken to.

    It is deliberately a TOPIC test and not a contradiction test, because I cannot detect semantic
    contradiction with string operations and a verdict I cannot defend is a lie with a timestamp.
    A topic test fails SAFE in the only direction that matters: at worst she is quieter than she
    needed to be. It can never delete a fact and never assert something false.
    """
    from harness.skills import lifecycle as lc
    clause = re.split(r"[.:;!]", query)[-1].strip() or query
    eps = _load()

    # ── SEM S1 (docs/SEMANTICS.md): the DUAL admission gate, in THE seam ──────────────────
    # A paraphrase shares no content tokens with the fact it asks about, so the lexical gate
    # alone recalls it at 0.06 on the frozen corpus (fixtures/sem/baseline-receipt.json). A
    # row may now ALSO be admitted by semantic match: cosine >= SP_SEM_TAU against its
    # semindex row, SAME embedding space only (cross-space cosine is noise). This is
    # admission by MATCH, not by salience — G-SALIENCE's law is untouched, salience still
    # only breaks ties among the admitted. Off (SP_SEM_RANK unset) is byte-identical to the
    # lexical path: G-SEM-CONSERVE holds the golden. Any failure inside SEM degrades to
    # lexical silently — a ranker may never cost her a sentence. It lives HERE because the
    # three comments below this one are all the same story: a guard in a caller guards
    # nothing. Gates: G-SEM-RANK, G-SEM-CLAIM.
    sem_idx, qvec, qmodel, sem_tau, smean = {}, None, None, 2.0, None
    if os.environ.get("SP_SEM_RANK", "0") == "1":
        from harness.skills import semindex as sx
        try:
            sem_tau = float(os.environ.get("SP_SEM_TAU", "0.60"))
            sem_idx = sx.load_cached()
            if sem_idx:
                qvec, qmodel = sx.query_embed(query)
                # TAU IS PER SPACE (2026-08-23). SP_SEM_TAU=0.60 was set for l5's inflated
                # raw cosines; the aux space's paraphrase median is 0.293 and its measured
                # operating point is 0.20, so the shared threshold would admit nothing at
                # all and the whole gate would look "safe" by being dead.
                if qmodel == sx.MODEL_AUX:
                    sem_tau = sx.aux_tau()
                if qvec is not None and qmodel == sx.MODEL_L5:
                    # ONCE, not per candidate row: space_mean() stats the index file
                    # and takes a lock on every call, and the loop below ran it for
                    # every row in the store.
                    smean = sx.space_mean()
        except Exception:
            sem_idx, qvec = {}, None      # degrade to lexical, never block

    scored = []
    for e in eps:
        if not include_retired and e.get("lifecycle"):
            continue                      # superseded is superseded — on EVERY path, not just the polite one
        t = _text(e)
        ov = _overlap(query, t)
        if clause != query:
            ov = max(ov, _overlap(clause, t))
        cos = 0.0
        if qvec is not None:
            srow = sem_idx.get((sx.addr_of(e.get("text") or t), e.get("ts") or ""))
            if srow is not None and srow.get("model") == qmodel:
                # l5-space is anisotropic (measured: every raw pair >= 0.70) — center on
                # the index population so the absolute threshold means something. Raw
                # cosine for hash-space (sparse, no common-direction pathology).
                if qmodel == sx.MODEL_L5:
                    cos = sx.centered_cosine(qvec, srow.get("vec") or [], smean)
                else:
                    cos = sx.cosine(qvec, srow.get("vec") or [])
        if ov >= min_overlap or cos >= sem_tau:
            scored.append((max(ov, cos), e))
    scored.sort(key=lambda x: -x[0])
    if not include_retired:
        scored = lc.testimony_wins(scored)
        # ── AND THE OWNERSHIP SCOPING LIVES HERE NOW, FOR THE SAME REASON (2026-07-14) ────
        #
        # _target_and_rank() — the pronoun scoping, the relationship penalty, the identity
        # boost, the salience prior — was called by recall(). THE TOOL. Not by the seam.
        #
        # So spine.recall_decider(), the AUTOMATIC per-turn injection, never ran any of it, and
        # the live transcript is what that costs:
        #
        #     you: "what is your NAME?"
        #     recall: ["The user said: My cat's NAME is Tuffy.", "The user's NAME is Sam",
        #              "My NAME is Kairos."]
        #     her: "Your cat's named Tuffy? I was wondering why you kept calling him that."
        #
        # She answered a question about HER NAME with HIS CAT'S NAME. The query token was {name};
        # the cat row contains "name"; it scored 1.00. _target_and_rank would have caught it
        # THREE WAYS — "your" scopes to speaker=self, the cat is a relationship noun the question
        # never mentioned (-0.40), and the identity row gets +0.30 — and its own comment says so,
        # in as many words. It just was not on the path that runs.
        #
        # Third time in this one file: the lifecycle filter, the twin ranker, and now this. The
        # polite path had every guard; the automatic one had none of them.
        scored = _target_and_rank(query, scored)
        # ── SEM PHASE B2 CUTOVER (docs/INVARIANT-MEMORY.md): the table RULES ─────────────
        # Behind SP_SEM_VERDICT (mapped in serve.py). Silence-direction only: the law can
        # drop a row it rules inadmissible (this is what closes the ladders leak once a
        # slot link exists); it cannot admit, cannot reorder, keeps unmapped cells (loud,
        # counted — unlegislated is not forbidden). Old conditionals stay: authority
        # moved, code did not get deleted. Gate: G-SEM-VERDICT.
        if os.environ.get("SP_SEM_VERDICT", "0") == "1":
            from harness.skills import verdict as _law2
            scored = _law2.enforce(query, scored, eps)
        # ── SEM PHASE B SHADOW (docs/INVARIANT-MEMORY.md): the law watches the seam ──────
        # Read-only, behind SP_SEM_LAW (mapped in serve.py). Checks the one direction that
        # is checkable and load-bearing: EVERYTHING ADMITTED IS TABLE-ADMISSIBLE. Counters
        # + optional witnesses (SP_SEM_LAW_LOG); never raises, never reorders, never costs
        # a sentence. Cutover to ruling-as-filter is Phase B2, gated on a zero-divergence
        # receipt. Gate: G-SEM-LAW.
        if os.environ.get("SP_SEM_LAW", "0") == "1":
            from harness.skills import verdict as _law
            _law.shadow(query, [e for _s, e in scored[:k]], eps)
    return scored[:k]


def search_memories_ranked(query: str, k: int = 5, min_overlap: float = 0.25,
                           include_retired: bool = False):
    """Internal: [(score, TEXT)] of the top-k live facts. The search tool rides this.

    ── I FIXED ONE OF TWO TWINS, AND THE OTHER ONE WAS RIGHT HERE (2026-07-14) ─────────────
    Hours after committing the fix for search_memories_ranked_rows — with a commit message
    explaining at length that AN INVARIANT ENFORCED IN ONE OF TWO PATHS IS ENFORCED IN NEITHER —
    the sweep for OTHER instances of that class found this function, DIRECTLY BELOW IT, doing the
    identical thing: `eps = _load()` over every row, tombstones included.

    And it is not dead code. It is the `search_memories` TOOL, and that tool is LIVE:

        MEMORY_TOOLS_EXTRA = [provenance, search_memories, memory_stats]
        spine.py:287   core = MEMORY_TOOLS + MEMORY_TOOLS_EXTRA[:2]     <- both of them
        agent.py:230   tools = MEMORY_TOOLS + MEMORY_TOOLS_EXTRA        <- all three

    So while I was congratulating myself for moving the lifecycle filter into "the seam", there
    were TWO seams. I had found the class, named the class, written the class on the wall — and
    then fixed the instance in front of me and stopped looking. THAT is the actual bug, and it is
    mine, not the code's.

    THE FIX IS NOT A THIRD COPY OF THE FILTER. A rule you have to remember is a rule you will
    forget; there is now exactly ONE function that reads the store for recall, and this one is a
    projection of it. The twin cannot drift because the twin no longer exists.
    """
    return [(s, _text(e)) for s, e in
            search_memories_ranked_rows(query, k=k, min_overlap=min_overlap,
                                        include_retired=include_retired)]


def search_memories(query: str) -> str:
    """Search long-term memory for facts relevant to a query (ranked; better than
    list_memories when memory is large)."""
    # ROWS, so the result can be FRAMED (2026-08-24, D1 + A3). This tool returned the
    # raw first-person text — a row HE spoke ("My workshop bench is oak") arrived in a
    # voice with no owner on it, the exact blur lifecycle.render() exists to prevent,
    # through the one speaking door that skipped it. And a private-secret's text rode
    # out with a match score attached. _present_row applies the framing and the secret
    # rule; a direct ask (attribute present) still serves, same as the decider.
    hits = search_memories_ranked_rows(query, k=5)
    if not hits:
        return f"(no stored facts match '{query}')"
    return "\n".join(f"{i+1}. {_present_row(e, query)}  [match {s:.2f}]"
                     for i, (s, e) in enumerate(hits))


def recall(query: str) -> str:
    """Look up what you KNOW about something — the fast, targeted way to answer a question
    from memory. Use this for any question about the user or about yourself
    (recall("what is the user's name") -> Sam told me: The user's name is Sam).
    Prefer this over list_memories, which dumps everything.

    WHY THIS TOOL EXISTS (2026-07-12). Her whole live toolset for READING memory was
    list_memories() — a dump of every row. It is expensive and undiscriminating, so she
    simply did not call it: asked "what is my name?" she skipped memory entirely and
    answered "I am Kairos." from her persona. She had no cheap way to LOOK SOMETHING
    UP, so she guessed. The ranked search had existed the whole time, parked in
    MEMORY_TOOLS_EXTRA and wired into no live toolset — the same drawer the personality
    tools were found in.

    And it renders through lifecycle.render(), which is the other half of the identity fix:
    a row that reads "My name is Sam" — first person, because HE said it — comes back
    from an unframed search looking like something SHE said. Framing the owner at READ time
    ("Sam told me: ..." / "About myself: ...") is what stops his facts arriving in her
    voice. Retired rows are excluded: superseded is superseded."""
    from harness.skills import lifecycle as lc
    # (the `if not e.get("lifecycle")` filter that used to live HERE is gone: it is the seam's job
    #  now. Keeping a private copy of a shared invariant is precisely how recall_decider came to be
    #  injecting tombstones on every turn for weeks while this function looked fine.)
    # The ownership scoping and the salience rerank used to be applied HERE, and only here —
    # which is why the automatic per-turn injection answered "what is your name?" with the cat's.
    # The seam does it now, for every reader. This function keeps no private copy of anything.
    hits = list(search_memories_ranked_rows(query, k=5, min_overlap=0.25))
    if not hits:
        return f"(nothing in memory about '{query}')"
    top = hits

    # SHE USED THESE. Counted — but into `recalled`, NEVER into `mentions`. `mentions` is
    # evidence about what matters TO HIM; her own lookups say nothing about that. She
    # recalls his name constantly, and that is not a fact about how much his name matters.
    # Letting a lookup feed the significance score would be a system marking its own
    # homework, and the loop is vicious: recalled -> more salient -> recalled more.
    # Under the lock as ONE read-modify-write (2026-08-24 audit, A2): the load, the
    # counter bumps and the rewrite used to straddle the lock (only _save_all held it),
    # so a remember() landing mid-count was rewritten out of the store by a READ path —
    # a lookup that could cost a fact. Same fix as the reinforce branch; RLock nests.
    try:
        with _REG_LOCK:
            rows = _load()
            by_name = {r.get("name"): r for r in rows}
            touched = False
            for _s, e in top:
                r = by_name.get(e.get("name"))
                if r is not None:
                    lc.note_recalled(r)
                    touched = True
            if touched:
                _save_all(rows)
    except Exception:
        pass

    # ── THE THIRD SURFACE, SPEAKING THE SAME GRAMMAR (field, 2026-07-30) ────────────
    # This returned a NUMBERED render() list — "1. Sam told me: My cat's name is Tuffy."
    # Correct values, and unusable as speech: asked "is Tuffy a boy or a girl?" she replied
    #     "She's a girl. I've got it right here: 2. Sam told me: My cat Tuffy is female."
    # She was obeying "answer using ONLY its exact values" and reading the bookkeeping out
    # loud. Tightening that instruction only shortened the recital, because the problem is
    # the DATA, not the wording: an output shaped like a ledger gets read like a ledger.
    #
    # There are THREE surfaces that hand her stored facts — the standing world block, the
    # per-turn recall note, and this tool. The first two were taught owner-correct prose
    # ("His cat's name is Tuffy." / "You've come to think: ...") and this one was not, so
    # the same fact arrived in two different grammars depending on which door it came
    # through. One presentation, all three doors.
    #
    # The OWNER FRAMING IS NOT LOST: present_for_her() carries it in the pronoun (his facts
    # read as his, her inferences read as hers) instead of in a "Sam told me:" prefix she
    # can quote. render() is untouched — the provenance lane and G-SEM-PROJ still use it.
    from harness.skills.world import present_for_her
    # THE FOURTH DOOR (2026-08-24 audit, A3). _present_row's docstring promised this
    # line before it existed — the claim outran the code by one door, which is the
    # exact §0 shape the other three doors were fixed for. recall() speaks TO HER, so
    # a withheld secret keeps present_for_her's grammar out of it entirely.
    return "\n".join(
        "- " + (SECRET_WITHHELD_NOTE if secret_withheld(e, query)
                else present_for_her(e))
        for _s, e in top)


# ── WHO IS THE QUESTION ABOUT? (2026-07-12) ───────────────────────────────────
# The trace that forced this. Asked "what is my name?", recall returned:
#
#     1. Sam told me: My cat's name is Tuffy.
#     2. Sam told me: The user's name is Sam
#     3. About myself: My name is Kairos.
#
# ...and she answered "My name is Kairos." Of course she did — of the three, row 3 is the
# one whose SURFACE FORM matches the question. Pure token overlap cannot tell "my name" in
# HIS mouth from "my name" in HERS; it just sees the words line up.
#
# But the store already knows whose each fact is — `speaker` is stamped on every row. The
# missing step is reading the PRONOUN IN THE QUESTION: when he says "my", he is asking
# about HIM; when he says "your", he is asking about HER. Scope the search to that person
# and the ambiguity is gone at the source, rather than being left for the model to resolve
# by guessing — which is precisely the guess that keeps coming out wrong.
#
# The relationship penalty is the second half: "My cat's name is Tuffy" tied with "The
# user's name is Sam" at 1.00, because the query token was {name} and both rows have it.
# A row that drags in an entity the question never mentioned (a cat) is answering a
# question that was not asked.
_ASKS_SELF = re.compile(r"\b(your|yours|you|you're|youre)\b", re.I)
_ASKS_USER = re.compile(r"\b(my|mine|me|i|i'm|im)\b", re.I)

# ── "DO YOU" IS NOT A QUESTION ABOUT YOU (2026-07-14) ─────────────────────────────────
# Caught replaying the live transcript after the first fix. He asks:
#
#     "do YOU remember my cat's name?"
#
# _ASKS_SELF matches the bare word `you`, and it is checked first — so the question scoped to
# SPEAKER_SELF and she answered HIS CAT'S NAME with "My name is Kairos."
#
# The `you` in "do you remember ..." is the ADDRESSEE. It is who he is TALKING TO, not who he is
# ASKING ABOUT. And it is in front of practically every memory question a person actually asks:
# "do you remember", "do you know", "can you tell me", "do you recall". So the ownership resolver
# was reading the wrong pronoun on nearly every real question, and the only reason it ever worked
# is that people also say "what is my name?" with no framing at all.
#
# Same shape as the _STOP fix one function up: THE FRAMING OF A QUESTION IS NOT THE QUESTION.
# There it made the verb into content; here it made the addressee into the subject. Strip the
# frame, THEN read the pronouns — after which a bare `you` is meaningful again ("what sex are
# YOU" -> hers) because the only `you` left is the one he actually asked about.
_ASK_FRAME = re.compile(
    r"^\s*(?:"
    r"(?:hey|hi|ok|okay|so|and|well|but)\b[\s,]*"
    r"|(?:do|did|can|could|would|will|does)\s+you\b"
    r"|(?:do|did)\s+you\s+(?:still\s+)?(?:remember|recall|know|have)\b"
    r"|(?:can|could|would)\s+you\s+(?:please\s+)?(?:tell|remind|say)\s+me\b"
    r"|(?:tell|remind)\s+me\b"
    r"|(?:what|which)\s+do\s+you\s+(?:remember|know)\b"
    r"|please\b"
    r")[\s,:]*", re.I)


def _unframe(q: str) -> str:
    """Peel the conversational wrapper off a question until only the question is left."""
    t = (q or "").strip()
    prev = None
    while t != prev:
        prev = t
        t = _ASK_FRAME.sub("", t, count=1).strip()
    return t or (q or "").strip()
# The trailing `s?` is load-bearing and I got it wrong once: I depluralised the RESULT of findall
# instead of what it SEARCHES, so `\bcat\b` still did not match "cats", q_rel stayed empty, and the
# cat row kept taking the -0.40 "you never asked about a pet" penalty on a question that was
# literally about his cat. Match the plural at the source; the group still yields the singular.
_REL_NOUN = re.compile(
    r"\b(wife|husband|partner|girlfriend|boyfriend|brother|sister|mother|father|mum|mom|"
    r"dad|son|daughter|friend|cat|dog|pet)s?\b", re.I)


# THE USER'S ACTUAL WORDS THIS TURN. The gateway sets this before the agent runs.
#
# WHY IT HAS TO BE HIS SENTENCE AND NOT HER QUERY (2026-07-12, from the trace). Asked
# "what is YOUR name?", she called recall(query="What is my name?") — she rewrites the
# question into her own first person, which is the natural thing to do. Asked "what is MY
# name?", she called recall(query="What is my name?") — the identical string. Two opposite
# questions, one query. So the pronoun in the string SHE passes carries no information
# about who is being asked after; it only tells you whose mouth the paraphrase is in.
#
# The pronoun is only reliable where it was UTTERED. In HIS sentence "my" means Sam and
# "your" means Kairos, always. So ownership is resolved from the human's words, and her
# query is used for what it is actually good for: matching the content.
#
# Same ContextVar seam as _AUTHOR (G-AUTHOR-CTX). The second assignment used to live
# here as `_QUESTION = ""` — a process-wide slot. It is defined with _AUTHOR above.


def set_question(text: str):
    return _QUESTION.set(text or "")


def _query_target(query: str):
    """Whose fact is this question asking for? Resolved from HIS sentence, not from her
    paraphrase of it — see _QUESTION. 'your' -> hers. 'my' -> his.

    UNFRAMED FIRST: "do YOU remember MY cat's name" has both pronouns in it, and the `you` is the
    addressee. Peel the frame and only the pronoun he is actually asking about survives."""
    from harness.skills import lifecycle as lc
    src = _unframe(_QUESTION.get() or query)   # his words if we have them; hers only as a fallback
    if _ASKS_SELF.search(src):
        return lc.SPEAKER_SELF
    if _ASKS_USER.search(src):
        return lc.SPEAKER_USER
    return None


def _target_and_rank(query: str, hits):
    from harness.skills import lifecycle as lc
    target = _query_target(query)
    if target:
        owned = [(s, e) for s, e in hits
                 if (e.get("speaker") or lc.SPEAKER_USER) == target]
        if owned:                      # only narrow when the person HAS a matching fact
            hits = owned

    # Depluralised on BOTH sides, for the same reason the tokens are: _REL_NOUN is \bcat\b, so a
    # question about his "cats name" did not register as being about a cat at all, and the row
    # that answered it took the -0.40 penalty for mentioning a pet he supposedly never asked about.
    q_rel = set(_depluralise(m.lower()) for m in _REL_NOUN.findall(query))
    qt = _toks(query)

    def adjust(s, e):
        t = _text(e)
        # a row that introduces a relative/pet the question never mentioned is off-target
        row_rel = set(m.lower() for m in _REL_NOUN.findall(t))
        if row_rel - q_rel:
            s -= 0.40
        # an identity question wants the identity row, not everything containing "name"
        if "name" in qt and e.get("mem_class") == "identity":
            s += 0.30
        # THE REAL HER (2026-08-22): asked about HER (day / feelings / thoughts), her own
        # narrative is the answer's shape — a small nudge on top of its salience weight
        if target == lc.SPEAKER_SELF and e.get("mem_class") in ("self-narrative", "feeling"):
            s += 0.15

        # ── SALIENCE: THE PRIOR (2026-07-13) ────────────────────────────────────
        # What the match score CANNOT know: that he has told her this five times, or that
        # he mentioned it once in March and never again. Two facts can match a question
        # equally well and not deserve the same answer.
        #
        # It is a PRIOR, so it is small and it breaks ties — it does not overrule what the
        # question actually matched. A frequently-repeated fact about his cat still loses
        # to a one-off fact about his GPU when he asks about his GPU. That ordering matters:
        # salience decides which of the RELEVANT memories to surface, never which memories
        # are relevant. Let it dominate and she answers every question with her favourite
        # fact.
        #
        # The old tie-breakers above (the relationship penalty, the identity boost) are what
        # you write when you have no prior and two rows both score 1.00. This is the
        # principled version of the same instinct, and it is derived from what he actually
        # did rather than from what I guessed he meant.
        return s + 0.22 * lc.salience(e)

    return sorted(((adjust(s, e), e) for s, e in hits), key=lambda x: -x[0])


def memory_stats() -> str:
    """A one-line summary of the memory store: live count, provenance mix, minted fraction."""
    # LIVE rows lead; the retired are a count, not entries in the mix — a tool docstring
    # that says "currently stored" and then tallies tombstones is lying politely.
    all_rows = _load()
    eps = [e for e in all_rows if not e.get("lifecycle")]
    if not eps:
        return "(memory is empty)"
    srcs: dict = {}
    minted = 0
    for e in eps:
        # DISPLAY grouping only (rendering never rules): src is append-only prose, so
        # maintenance passes grow it (" | cleanup: ...", " | audit ..."); the mix groups
        # by the first segment or every appended row becomes its own category.
        k = (e.get("src") or "unknown").split(" | ")[0].strip() or "unknown"
        srcs[k] = srcs.get(k, 0) + 1
        if int(e.get("npos", 0) or 0) > 0:
            minted += 1
    retired = len(all_rows) - len(eps)
    mix = ", ".join(f"{k}:{v}" for k, v in sorted(srcs.items(), key=lambda x: -x[1]))
    return (f"{len(eps)} facts ({minted} minted for recall, {retired} retired); "
            f"sources: {mix}")


# ──── MEM-OKF v2 §M3: registry hygiene (verify + compaction) ────────────────
# CACHED BY FILE IDENTITY (mtime_ns, size) — the semindex cache-key lesson (an
# mtime-keyed cache once served a dead vector; ns+size is the honest key). The health
# scan is O(n²) over live rows and the operator panel polls /v1/memory every 15 s:
# measured 129 ms per call at 165 rows BEFORE the token precompute, and still a whole
# re-scan per poll after it, for a file that changes a few times an hour.
_HEALTH_CACHE: dict = {"key": None, "value": None}


def _registry_health():
    """(stats dict, status enum). The ONE computation behind both the human report and
    the machine verdict — Tier 2 (INVARIANT-ROADMAP.md): the hygiene decider used to
    sniff 'NEEDS COMPACTION' out of the report STRING, which is branching on a
    paragraph, the src-trap in a lab coat. Status is an enum now; the prose is for
    people."""
    p = _reg_path()
    if not p or not os.path.exists(p):
        return None, "unconfigured"
    try:
        st = os.stat(p)
        key = (p, st.st_mtime_ns, st.st_size)
    except OSError:
        key = None
    if key is not None and _HEALTH_CACHE["key"] == key:
        return _HEALTH_CACHE["value"]
    rows, malformed = 0, 0
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows += 1
            try:
                json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
    eps = _load()
    # Duplicates are counted among LIVE rows only. A tombstone sharing text with a live
    # row is HISTORY (forgotten-then-restated; a retired duplicate), not a pending chore —
    # counting it made the tombstone-based compactor structurally unable to ever satisfy
    # its own verifier: every tick decided compaction, forever. Malformed still counts
    # over the raw file.
    live = [e for e in eps if not e.get("lifecycle")]
    texts = [_text(e).strip() for e in live]
    exact_dups = len(texts) - len(set(texts))
    # _toks once per row, not once per PAIR — the inner loop retokenized texts[j] for
    # every i, ~n²/2 tokenizations: 129 ms measured at 165 rows, on a 15-second poll.
    toksets = [_toks(t) for t in texts]
    near = 0
    for i in range(len(live)):
        ti = toksets[i]
        if not ti:
            continue
        for j in range(i + 1, len(live)):
            tj = toksets[j]
            if tj and len(ti & tj) / len(ti) >= 0.9 and len(ti & tj) / len(tj) >= 0.9:
                near += 1
    no_ep = sum(1 for e in eps if not e.get("dir") or int(e.get("npos", 0) or 0) <= 0)
    no_prov = sum(1 for e in eps if not e.get("src"))
    stats = {"path": p, "rows": rows, "parsed": len(eps), "malformed": malformed,
             "exact_dups": exact_dups, "near_dups": near, "unminted": no_ep,
             "no_provenance": no_prov}
    # `unminted` has been in this dict since it was written and has never reached a surface
    # or the verdict, which is how 253 consecutive unminted rows went unnoticed. The REASON
    # rides along now — when the engine has refused, that string is the whole diagnosis.
    # The verdict is deliberately NOT changed: 'needs-compaction' means compact() would help,
    # and compact() cannot mint an episode. A refusal is news, not a chore.
    _cap = capture_status()
    if _cap.get("why"):
        stats["capture_refused"] = _cap["why"]
        stats["capture_skipped"] = _cap.get("n", 0)
    status = "ok" if (malformed == 0 and exact_dups == 0) else "needs-compaction"
    if key is not None:
        _HEALTH_CACHE["key"], _HEALTH_CACHE["value"] = key, (stats, status)
    return stats, status


def registry_status() -> str:
    """The machine verdict: 'ok' | 'needs-compaction' | 'unconfigured'."""
    return _registry_health()[1]


def verify_registry() -> str:
    """Integrity check on the fact registry: count rows, malformed lines, exact duplicates,
    near-duplicate paraphrase pairs, and rows missing an episode dir. Read-only report."""
    s, status = _registry_health()
    if s is None:
        return "[no registry configured]"
    out = (f"registry {s['path']}: rows={s['rows']} parsed={s['parsed']} "
           f"malformed={s['malformed']} exact_dups={s['exact_dups']} "
           f"near_dups={s['near_dups']} unminted={s['unminted']} "
           f"no_provenance={s['no_provenance']} "
           f"-> {'OK' if status == 'ok' else 'NEEDS COMPACTION'}")
    if s.get("capture_refused"):
        out += (f"{os.linesep}  KV MINT IS OFF - the engine refused /v1/capture: "
                f"{s['capture_refused']}{os.linesep}"
                f"  {s['unminted']} rows carry no episode and no ep.l5. The registry is "
                f"unaffected (it is the recall authority); the engine-side episode "
                f"representation and the L5 half of the semantic index are.")
    return out


def compact_registry() -> str:
    """Compact the registry: tombstone duplicates, quarantine malformed lines. Hygiene,
    not forgetting — nothing is destroyed.

    ── THIS FUNCTION HARD-DELETED ROWS, UNLOCKED, ON THE AUTOMATIC PATH (2026-08-19) ──────
    It read the file raw, dropped malformed lines and exact duplicates, and rewrote with a
    bare open(p, "w") — no _REG_LOCK, no tmp+replace. forget()'s conviction, three doors
    down, still live in a HYGIENE_TOOL she can call herself AND in the tick's hygiene
    executor. And its dedupe keyed on text across ALL rows keeping the FIRST — tombstones
    sort first, so a fact that was forgotten and honestly re-stated was resolved by
    DELETING THE LIVE ROW AND KEEPING THE CORPSE (G-COMPACT §4 demonstrates it).

    ops.compact() did the same job correctly the whole time: backup, tombstone with
    superseded_by, may_supersede so her paraphrase never retires his testimony. Twin
    functions, and the automatic path ran the unguarded one — so the twin no longer
    exists. This is a projection of ops.compact(), same as search_memories_ranked is a
    projection of the seam. Gate: G-COMPACT."""
    p = _reg_path()
    if not p or not os.path.exists(p):
        return "[no registry configured]"
    from harness.maintenance import ops
    r = ops.compact()
    return ("compacted: %d duplicates retired, %d paraphrases retired, %d conflicts "
            "superseded, %d malformed quarantined; %d live of %d"
            % (r.get("duplicates_retired", 0), r.get("paraphrases_retired", 0),
               r.get("conflicts_superseded", 0), r.get("malformed_quarantined", 0),
               r.get("live_now", 0), r.get("live_now", 0) + r.get("superseded_total", 0)))


# HOT chat set stays curated (the banked ≤6-tools rule: a small model stalls exploring a big set).
# remember_about_self is READY-NOW, not an extra. It is the SELF lane — the one she
# never had. Leaving it behind a load_tools() call is exactly how she ended up with 404
# memories of the user and none of herself. count_memories drops to the index tier to
# keep the ready-now set small (list_memories subsumes it).
# recall() JOINS THE LIVE SET. Without it her only way to READ memory was list_memories —
# a dump of everything — so she did not read at all, and answered from persona instead.
# A memory she cannot cheaply look up is a memory she does not have.
MEMORY_TOOLS = [remember, remember_about_self, recall, list_memories, forget]
# Extra tier: discoverable via the OKFS load_tools index (full signature on demand).
MEMORY_TOOLS_EXTRA = [provenance, search_memories, memory_stats]
# Hygiene tools are curation-tier (not in the hot chat set); used by the agency round + operator.
HYGIENE_TOOLS = [verify_registry, compact_registry]
