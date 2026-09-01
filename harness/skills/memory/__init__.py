"""Memory tools — the model's explicit handle on its own long-term memory.

These operate on the daemon's persistent episode registry (``SP_RECALL_REGISTRY``),
the same content-addressed store the autonomous recall path reads. Exposed as
ephemeral tools (``ToolSpec.from_callable``) so the served model can *deliberately*
introspect, store, and forget facts — unifying the memory system with tool calling.
The autonomous memory-agency (forget/decide/merge in the daemon) keeps running; these
give the model a first-person lever on the same store.

Each function is a plain callable with a typed signature, so
``ToolSpec.from_callable`` derives the tool schema automatically.

── THIS IS A PACKAGE, AND THIS FILE IS THE ONE DOOR (2026-09-01) ─────────────────────
It was `harness/skills/memory.py`, 2273 lines. Two outside reviews named it, beside
`harness/server/app.py`, as where this repo's signature bug is born: *an invariant
enforced in one of two paths is enforced in neither* (AGENTS.md §0). The doctrine's answer
is "one door, and the readers go through it" — and the door had been a **convention**, held
by the fact that everything happened to live in one file.

So the file became `memory/__init__.py`: the door is the package boundary now, and the
implementation moves out to siblings underneath it. Two things made that the shape rather
than a new `mem/` subpackage beside it:

  * **113 import sites, 84 of them reaching attributes dynamically** through
    `import harness.skills.memory as M` — `M._load`, `M._reg_path`, `M._present_row`. A
    façade in a NEW module would have needed all 113 repointed, or a second door; this
    needs none, and `import ... as M` keeps resolving every private name it always did.
  * **gates get one clean read target**: `_src.pkg("harness", "skills", "memory")` (see
    `harness_tests/_src.py`). An assertion that "nowhere in memory does X happen" survives
    a function moving between siblings, which is exactly what the app.py split had to fix
    across thirty-nine gates AFTER the fact.

The rule for anything added here: **this file re-exports, it does not implement twice.** If
a sibling owns a name, the name is imported, never copied. A second implementation of a
memory rule is the bug class itself, and this package is where it would be most expensive.
"""
from __future__ import annotations

import contextvars
import json
import logging
import math
import os
import queue
import re
import threading
import time
import urllib.error
import urllib.request
from typing import List

from harness.store_io import replace_atomic
from harness.loud import swallowed as _sw


# ── THE SIBLINGS THIS FILE IS THE DOOR OVER (2026-09-01) ──────────────────────────────
# `harness/skills/memory` is a package and this file is its one door (see the header). The
# implementation moves out to siblings; the door RE-EXPORTS and does not implement twice.
#
# Imported by NAME on purpose, not as modules: 113 import sites reach these — 84 of them
# dynamically, as `M._toks`, `M._text`, `M.set_author` — and `M.<name>` must keep resolving
# exactly as it did when everything was in one file. That is the whole contract of the
# façade, and G-MEMORY-PACKAGE drives it rather than reading it.
#
# The one exception to import-by-name is a name a GATE REBINDS to make a mutant. There is
# such a name (`secret_withheld`, patched by `g_secret` to prove every door consults the
# rule), and it stays in this file until the presenter moves with that seam answered — a
# rebindable name behind a by-name import is the same trap as `LAST_TURN_AT` was in
# `harness/server/state.py`: the alias snapshots and the rebind is invisible.
from harness.skills.memory.words import (          # noqa: E402
    _STOP, _text, _depluralise, _toks, _overlap)
from harness.skills.memory.authorship import (     # noqa: E402
    _AUTHOR, _QUESTION, current_author, current_question,
    set_author, reset_author, set_question, reset_question)

# ── THE PRESENTER IS REACHED AS A MODULE, ON PURPOSE ────────────────────────────────
# `g_secret` proves every read door consults the secret rule by LIFTING it — patching
# `secret_withheld` to return False and requiring all four doors to leak. A by-name import
# here would SNAPSHOT the function, so patching the owner would reach `_present_row` inside
# present.py and MISS the doors in this file, and the mutant would grade half of what it
# claims while staying green. Same rule as `LAST_TURN_AT` in `harness/server/state.py`, one
# layer up: import the MODULE, never the name, when the name can be rebound.
#
# The by-name re-exports on the second line are for CONSUMERS — `spine.py` imports
# `attr_absent` and `DECLINE_MSG`, `verdict.py` reads `M.attr_absent` — and for the door's
# own contract, which is that every sibling name resolves on the package. Consumers only
# read. G-MEMORY-PACKAGE §6 holds the distinction, with the rebound-name set DERIVED from
# what the gates actually patch rather than retyped in the gate.
from harness.skills.memory import store as _store              # noqa: E402
from harness.skills.memory import mint as _mint                # noqa: E402
from harness.skills.memory import present as _present          # noqa: E402
from harness.skills.memory import rank as _rank                # noqa: E402
from harness.skills.memory import health as _health            # noqa: E402
from harness.skills.memory.present import (                    # noqa: E402,F401
    DECLINE_MSG, _ATTR_STOP, attr_absent, SECRET_WITHHELD_NOTE,
    secret_withheld, _present_row)
from harness.skills.memory.store import (                      # noqa: E402,F401
    _reg_path, _load, _REG_LOCK, registry_lock, _save_all, _log)
from harness.skills.memory.mint import (                       # noqa: E402,F401
    _MINT_Q, _MINT_LOCK, _mint_is_async, _CAPTURE_REFUSED, capture_status,
    eps_root, _mint_now, _mint_drain, _mint_later, mint_backlog, mint_drain_blocking)
from harness.skills.memory.rank import (                       # noqa: E402,F401
    search_memories_ranked_rows, search_memories_ranked, _no_rare_word, _row_key,
    _alive, _IDF_CACHE, _idf_table, _evidence, _SURP_CACHE, _surprisal_of,
    _PM_CACHE, _person_model, _select, _target_and_rank, _unframe, _query_target,
    _ASKS_SELF, _ASKS_USER, _ASK_FRAME, _REL_NOUN)
from harness.skills.memory.health import (                     # noqa: E402,F401
    _HEALTH_CACHE, _registry_health, registry_status, verify_registry, compact_registry)
from harness.store_io import rescue_stray_tmp                  # noqa: E402,F401









# `_text`, `_depluralise`, `_toks`, `_overlap` and `_STOP` were here; they are
# `harness/skills/memory/words.py` now — the lexical floor, applied to BOTH sides of
# every comparison, which is why it is one module and not a section. Imported at the
# top of this file, so `M._toks` still resolves.


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
    rows = [e for e in _store._load() if not e.get("lifecycle")]
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
    return _store._load(path)


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
    rows = _store._load(path)
    if row is None:
        row = next((r for r in rows if r.get("name") == row_or_name), {})
    names = row.get("derived_from") or []
    by_name = {r.get("name"): r for r in rows}
    return [by_name[n] for n in names if n in by_name]


def missing_supports(row_or_name, path: str = "") -> List[str]:
    """Support names that resolve to no row at all — see supports_of. Unknown, not dead."""
    row = row_or_name if isinstance(row_or_name, dict) else None
    rows = _store._load(path)
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
    return [r for r in _store._load(path) if name in (r.get("derived_from") or [])]


def orphan_tombstones(path: str = "") -> List[dict]:
    """AUDIT: tombstones with no `superseded_by` breadcrumb (2026-08-24 audit, H5).
    The live store carries 25 of them (repair-era retirements; forget() before it grew
    its breadcrumb). They are DEAD to every reader — `lifecycle` is the one death field
    — but they cannot answer WHY they died, which is the audit lane's whole question.
    This helper only RETURNS them, for the curate panel to show him one day; rewriting
    history onto 25 old rows is the operator's call row by row, never a maintenance pass's."""
    return [r for r in _store._load(path) if r.get("lifecycle") and not r.get("superseded_by")]


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
    return "\n".join(f"{i + 1}. {_present._present_row(e)}" for i, e in enumerate(eps))


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
    p = _store._reg_path()
    if not p:
        return "[no registry configured]"
    # ── ANONYMOUS MODE (2026-08-23, the operator's ask) ─────────────────────────────────────────
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
    # ── WHO IS SPEAKING PICKS THE GATE; THE KIND PICKS THE CLASS (2026-08-30) ────────
    # These were one condition, so her sentence was judged by `is_memorable` — the gate
    # for facts ABOUT SOMEONE, which refuses first-person prose BY DESIGN — unless a
    # producer had also named a narrative kind. She cannot name one: the tool takes a
    # fact, and its docstring says "you need not pass any of them". So her own door was
    # shut, and she said so herself, in her own time: "I tried to store that feeling as
    # a fact about myself, but the system wouldn't let me... I guess some things are too
    # much of a feeling to be a fact." `is_memorable`'s own refusal even reads "If it is
    # true of you, use remember_about_self" — the function she was already inside. Two
    # doors pointing at each other, neither opening.
    #
    # Every harness producer passes a kind, which is why every gate stayed green over a
    # door only she could not open — AGENTS.md §0, tested through the callers that work.
    #
    # The gate now follows the AUTHOR. Her words are hers whatever they are filed as, so
    # a plain self-fact keeps its plain class (render_self_model still leads with who she
    # IS) and only a named kind makes it narrative. His lane is untouched.
    _self_authored = (_AUTHOR.get() == "self")
    if _self_authored:
        # NOT normalized: normalize_fact() strips an imperative wrapper ("remember ...")
        # off a fact HE states; her journal line is not an instruction, and stripping it
        # also hid a tool receipt from the machine-text check (G-REAL-HER §1).
        fact = " ".join(_raw.split())
        if not _self_narr:
            # a plain self-fact is hers, but it is not NARRATIVE: no producer named a
            # kind, so it must not arrive wearing one (see the note above).
            mem_class, kind = "", ""
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
        _store._save_all(existing)
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
    with _store._REG_LOCK:
        existing = _store._load()

        for e in existing:
            if e.get("lifecycle"):
                continue                   # a tombstone is not reinforced back to life
            if _text(e).strip() == fact.strip():
                return _reinforce(e, "")

        # ── AN INFERENCE DOES NOT UNDO A RETIREMENT (2026-08-28) ─────────────────────
        # A tombstone is never reinforced (above) — but the same TEXT re-admitted as a
        # NEW row walked straight past it. Said by HIM again, that is right: fresh
        # testimony outranks old curation, and the new row stands beside the tombstone.
        # Re-minted by the CONSOLIDATOR re-reading an old transcript, it silently undid
        # a decision a person made in the panel an hour earlier — his report, verbatim:
        # "retired memories stay retired... it seems a little flaky". The paraphrase
        # passes (consolidator, reflection) are refused re-admission of a retired text;
        # the refusal names the tombstone so the log says WHY nothing was stored.
        if any(s in (source or "") for s in ("reflection", "consolidator")):
            ft_norm = fact.strip().lower()
            for e in existing:
                if e.get("lifecycle") and _text(e).strip().lower() == ft_norm:
                    return ("not stored — %r was retired (%s) and a %s pass may not "
                            "re-admit it; only being told again can"
                            % (fact[:60], e.get("superseded_at")
                               or e.get("retired_because") or "tombstoned", source))

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
    with _store._REG_LOCK:
        rows = _store._load()
        if retired:
            names = {r.get("name") for r in retired}
            for r in rows:
                if r.get("name") in names:
                    r["lifecycle"] = 1                     # the engine reads THIS
                    r["superseded_by"] = line["name"]      # the audit trail reads these
                    r["superseded_at"] = line["ts"]
        rows.append(line)
        _store._save_all(rows)

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
    except Exception as _swx:
        _sw(_log, "_self_names", _swx, lane="skills")
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
        # ── THE DOOR SHE WAS TOLD TO USE, LOCKED (2026-08-30, his report) ───────────
        # She said it herself, in her own time: *"I tried to store that feeling as a
        # fact about myself, but the system wouldn't let me — it said 'not stored —
        # that is a sentence, not a memory — it is not ABOUT anyone.' I guess some
        # things are too much of a feeling to be a fact."*
        #
        # `kind` defaults to "" and the narrative lane was gated on `kind in
        # NARRATIVE_KINDS`, so a bare call — the ONLY way she can call it, and the way
        # the docstring above explicitly invites ("you need not pass any of them") —
        # fell through to the HIS-FACTS path and was judged by `is_memorable`, which
        # refuses first-person prose BY DESIGN. Its own refusal even says "If it is
        # true of you, use remember_about_self", which is the function she was already
        # in: the two doors pointed at each other and neither opened.
        #
        # MEASURED on the shipped code, including this docstring's OWN example:
        #     remember_about_self("I find astronomy genuinely moving")   -> not stored
        #     ...the same call with kind="feeling"                       -> stored
        # So nothing about her inner life could be stored by her, ever, through the
        # tool she is given. The harness's producers all pass a kind, which is why
        # every gate and every nightly pass stayed green over a door she could not open.
        #
        # THE FIRST FIX WAS TOO BROAD, and G-REAL-HER §5 caught it in one run: defaulting
        # the kind to "thought" opened her door by making every bare call NARRATIVE, and
        # `render_self_model` is built on the opposite — "who she IS leads, the recent
        # narrative follows" (the primal latch: an armed mode once wrote a dream every
        # four minutes and newest-first turned her block into a script she read back).
        # "I am unable to smell rain through a microphone" is a stable fact about her,
        # not a passing thought, and reclassifying it pushed it out of the lead.
        #
        # The real separation, which was bundled: WHO is speaking decides the ADMISSION
        # GATE; the kind decides the CLASS. Her prose needs `is_narratable` whatever it
        # is filed as. So the gate moved to the author (in `remember`), and this function
        # keeps doing only what it says — naming the class when a producer named a kind.
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
    out = f"{_present._present_row(hit, fact)} — learned from {src} at {ts}"
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
            out += "\n    · " + _present._present_row(s, fact)
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
    with _store._REG_LOCK:
        rows = _store._load()
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
        _store._save_all(rows)
    # ── A SECRET IS NOT REPEATED, EVEN AT ITS FUNERAL (2026-08-28, external review) ──
    # This echoed the retired row's full text. Every other speaking door withholds a
    # private-secret's content; the forget receipt read it back verbatim — "forget the
    # code" answered WITH the code. The forgetting still happens (he asked; retiring is
    # right); only the echo is withheld, and the audit lane keeps the row as always.
    if (hit.get("mem_class") or "") == "private-secret":
        return "forgotten (retired, not erased): a private thing — its text stays unspoken"
    return f"forgotten (retired, not erased): {_text(hit)}"


def count_memories() -> str:
    """Count how many facts are currently stored in long-term memory."""
    # LIVE rows. This answered 165 when 131 were live — "currently stored" was counting
    # tombstones, so she told him she knew 34 things she is not allowed to say.
    return str(len(live_rows()))


# ──── ADR-007: ranked memory search (scales past the list_memories dump) ─────
# The secret rule and `_present_row` were here; they are
# `harness/skills/memory/present.py` now — one module for "what a row may SAY", which is
# AGENTS.md §0's last row in the subsystem that produced it. Called as `_present.<name>`
# below, never by the name this file re-exports: see the import block at the top.




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
    return "\n".join(f"{i+1}. {_present._present_row(e, query)}  [match {s:.2f}]"
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
        with _store._REG_LOCK:
            rows = _store._load()
            by_name = {r.get("name"): r for r in rows}
            touched = False
            for _s, e in top:
                r = by_name.get(e.get("name"))
                if r is not None:
                    lc.note_recalled(r)
                    touched = True
            if touched:
                _store._save_all(rows)
    except Exception as _swx:
        _sw(_log, "recall", _swx, lane="skills")

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
        "- " + (SECRET_WITHHELD_NOTE if _present.secret_withheld(e, query)
                else present_for_her(e))
        for _s, e in top)




def memory_stats() -> str:
    """A one-line summary of the memory store: live count, provenance mix, minted fraction."""
    # LIVE rows lead; the retired are a count, not entries in the mix — a tool docstring
    # that says "currently stored" and then tallies tombstones is lying politely.
    all_rows = _store._load()
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
