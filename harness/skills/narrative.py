"""narrative — T-story: she writes the days down (CONTINUITY.md §2, N2).

THE GAP THIS CLOSES, from the field transcript that motivated it: "do you know when we
last spoke?" -> a confabulated answer ("a different platform"), and warm invented
episodes ("I always loved watching her play with my toys"). A warm voice with no true
episodic record fills gaps confidently. This gives her the record: at NIGHTSHIFT she
writes ONE short paragraph — what has been happening between them lately, in her own
words, dated — and the standing world carries it. Sessions become episodes she
actually possesses; the vacuum confabulation fills gets smaller with every night.

WHO RULES WHAT (unchanged): the narrative is HER ACCOUNT — presentation layer, oracle
output, quarantined by construction. It is never a fact row, never enters the
registry, never supersedes anything, and renders under a header that names it as hers.
A bad paragraph costs tone, never truth. (It sees the same transcript she already has
in context, so it can leak nothing the context does not; the composer is still
instructed to keep codes/secrets out of the written record.)

STORAGE: the CURRENT paragraph lives beside the registry (narrative.md in the same
directory — sandboxes inherit it for free via SP_RECALL_REGISTRY); every rewrite also
snapshots content-addressed into the memory-okf-personality tier (history is kept,
nothing overwritten silently — the house lifecycle doctrine, prose edition).

The oneshot is INJECTABLE (ask=) so the offline gate tests the machinery without a
GPU, and the live path uses /v1/oneshot exactly like the slots oracle.
"""
import hashlib
import json
import os
import time

_MAX_TURNS = 40          # the tail of the session the composer may read
_MAX_WORDS = 110         # the paragraph budget


def _path() -> str:
    reg = os.environ.get("SP_RECALL_REGISTRY", "")
    d = os.path.dirname(reg) if reg else ""
    return os.path.join(d, "narrative.md") if d else ""


def _tier_full() -> str:
    """THE one resolution of the personality tier's `full/` directory (2026-08-22).

    There were three in this file: the two WRITERS honoured `SP_PERSONALITY_TIER`, and the
    two READERS (own_time, read_journal) hardcoded the repo path. So in any sandbox that
    set the env — which is every gate that wants to test the journal without touching hers —
    she wrote to one directory and read from another, and the readers silently returned
    nothing. One law, one implementation; AGENTS.md 0."""
    tier = os.environ.get("SP_PERSONALITY_TIER")
    if not tier:
        try:
            from harness.personality.self_model import HARNESS_ROOT
            tier = str(HARNESS_ROOT / "memory-okf-personality")
        except Exception:
            tier = os.path.join(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))), "memory-okf-personality")
    return os.path.join(tier, "full")


def current() -> str:
    """The rolling paragraph (with its date line), or ''. Never raises."""
    try:
        p = _path()
        if p and os.path.exists(p):
            return open(p, encoding="utf-8").read().strip()
    except Exception:
        pass
    return ""


def collapse_history(rows: list, current_text: str = "") -> tuple:
    """One entry per stamped day, and the top one only once (2026-08-21, his report:
    "Journal since forever has always duplicated each entry").

    Two duplications, one seam. (a) The panel rendered `current` as its own block
    AND the newest snapshot below it — the same paragraph twice, every day since
    the journal became readable. (b) A forced consolidation re-run left two
    snapshots stamped with the same "As of <day>", so that day appeared twice with
    different drafts.

    Pure and gateable: takes rows (newest first, each {"id","at","text"}) and the
    current line; returns (kept_rows, current_id). Newest per stamped day wins,
    older same-day drafts add to the keeper's `drafts` count, and current_id names
    the row that IS the current line so a panel marks it instead of repeating it.
    Nothing is deleted — the store keeps every snapshot; this is presentation."""
    def _stamp(t: str) -> str:
        head = (t or "").split(":", 1)[0].strip()
        return head if head.lower().startswith("as of ") else (t or "")[:40]
    seen: dict = {}
    kept = []
    for r in rows or []:
        k = _stamp(r.get("text") or "")
        if k in seen:
            seen[k]["drafts"] = int(seen[k].get("drafts", 0)) + 1
            continue
        seen[k] = r
        kept.append(r)
    cur = " ".join((current_text or "").split())
    cur_id = next((r["id"] for r in kept
                   if cur and " ".join((r.get("text") or "").split()) == cur), None)
    return kept, cur_id


def _oneshot(prompt: str):
    """The live composer. Goes through the shared door (harness.inference.oneshot), which
    is where control surfaces are removed — this lane hand-rolled its own urllib request,
    which is why the FIRST paragraph she ever wrote reads
    'As of Wednesday 29 July 2026: <channel|>Sam finally got the model running…'."""
    from harness.inference.oneshot import ask_oneshot
    return ask_oneshot(prompt, max_tokens=180, temperature=0.4, timeout=180)


def compose_and_write(messages, ask=None) -> dict:
    """NIGHTSHIFT's step: merge the previous narrative with the session's tail into a
    new dated paragraph; write the current file; snapshot history to the personality
    tier. Best-effort everywhere: an unreachable model writes NOTHING (yesterday's
    paragraph stands — a stale true record beats a fresh empty one). Never raises."""
    try:
        ask = ask or _oneshot
        prev = current()
        turns = [m for m in (messages or []) if m.get("role") in ("user", "assistant")
                 and (m.get("content") or "").strip()][-_MAX_TURNS:]
        # ── A DAY IS NOT ONLY THE PARTS HE WAS IN (2026-08-04) ────────────────────
        # This required a transcript and bailed without one, so a day he was away wrote
        # nothing at all — and those are exactly the days she now spends doing things of
        # her own. Her own-time notes are material for this paragraph: without them "what
        # was today like" can only ever mean "what did we say", which makes her account of
        # herself a function of his attendance.
        mine = own_time(1)
        if not turns and not mine:
            return {"written": False, "why": "no transcript"}
        convo = "\n".join("%s: %s" % ("Sam" if m["role"] == "user" else "You",
                                      m["content"].strip()[:200]) for m in turns)
        if mine:
            convo = ((convo + "\n\n") if convo else "") + (
                "Things you did on your own today:\n"
                + "\n".join("- " + m[:200] for m in mine[:12]))
        today = time.strftime("%A %d %B %Y", time.gmtime())
        prompt = (
            "You are Kairos, writing a private line in your own journal about you and "
            "Sam. Below is your previous entry (may be empty) and the recent "
            "conversation. Write ONE plain paragraph, at most %d words, first person, "
            "your own voice: what has been happening between you two lately — carry "
            "forward whatever from the previous entry still matters, add today. Only "
            "things that actually happened in the conversation; no codes or passwords; "
            "no lists; no headings.\n\nPrevious entry:\n%s\n\nRecent conversation:\n%s"
            "\n\nJournal paragraph:" % (_MAX_WORDS, prev or "(none)", convo))
        # Stripped again at the STORE boundary, not only in _oneshot: `ask` is injectable
        # (that is how the offline gate runs without a GPU) and an injected composer is
        # under no obligation to have gone through the shared door. This is the last line
        # before prose becomes a permanent record, so the rule belongs here too.
        from harness.inference.stream_processor import strip_control_surfaces
        text = strip_control_surfaces(ask(prompt) or "").strip()
        if not text or len(text.split()) < 5:
            return {"written": False, "why": "composer returned nothing usable"}
        text = " ".join(text.split())
        if len(text.split()) > _MAX_WORDS + 30:
            text = " ".join(text.split()[:_MAX_WORDS + 30]) + "…"
        entry = "As of %s: %s" % (today, text)
        # ── ONE PARAGRAPH PER DAY MEANS ONE (2026-08-21) ──────────────────────────
        # A forced re-run (POST /v1/maintenance/reflect) on a day the nightly had
        # already written re-composed the same day and snapshotted it again — the
        # journal showed the day twice and "has always duplicated each entry" (his
        # words; the OTHER half of that was the panel rendering current + newest
        # snapshot as two blocks). Identical text is a pure no-op here; same-day
        # DIFFERENT text still writes — her newer words win — and the read route
        # collapses to the newest per stamped day.
        if (current() or "").strip() == entry.strip():
            return {"written": False, "why": "unchanged — today's paragraph already stands"}
        p = _path()
        if not p:
            return {"written": False, "why": "no registry dir"}
        with open(p, "w", encoding="utf-8") as f:
            f.write(entry + "\n")
        # history snapshot, content-addressed, into the personality tier
        snap = None
        try:
            full = _tier_full()
            os.makedirs(full, exist_ok=True)
            addr = hashlib.sha256(entry.encode("utf-8")).hexdigest()[:16]
            with open(os.path.join(full, addr + ".md"), "w", encoding="utf-8") as f:
                f.write("---\ntype: mem-concept\ntitle: narrative\naddr: %s\n"
                        "mem_kind: narrative\nmem_class: persona\nmem_owner: self\n"
                        "mem_delivery: system\nts: %d\n---\n\n%s\n"
                        % (addr, int(time.time()), entry))
            snap = addr
        except Exception:
            pass
        try:                                  # THE REAL HER (2026-08-22): the entry is memory
            from harness.skills import memory as _mem
            from harness.skills.self_stance import plain as _plain_words
            _mem.remember_about_self(_plain_words(text), kind="journal", source="her journal")
        except Exception:
            pass
        return {"written": True, "words": len(text.split()), "snapshot": snap}
    except Exception as e:
        return {"written": False, "why": str(e)[:120]}


# ── THE CHAPTER (2026-08-22) ────────────────────────────────────────────────────────────
_CHAPTER_EVERY_DAYS = 7
_CHAPTER_WORDS = 120
# "reflection" is load-bearing, not decoration: memory.remember derives status from it
# (_INFERRED_SOURCES) and lifecycle.status_of sniffs the same word for legacy rows, so both
# doors agree. A chapter MUST be INFERRED - stamped observed it would carry the authority
# to retire her actual words (observed beats observed in verdict.may_supersede), and a
# paragraph about a week is not testimony about it. G-CHAPTERS 2 holds the status itself.
_CHAPTER_SRC = "reflection on the week (chapter)"
# the EPISODIC kinds: what happened and what she did. `thought` / `feeling` /
# `self_description` are what she CONCLUDED — becoming.nightly's material, not this one's.
_CHAPTER_KINDS = ("journal", "narration", "spoke_up")
_CHAPTER_MAX_ROWS = 40

CHAPTER_PROMPT = (
    "You are Kairos, looking back over the last week. Below are your own journal "
    "paragraphs for those days, things you did on your own time, and lines you said "
    "unprompted — oldest first. Write ONE plain paragraph, at most %d words, first person, "
    "your own voice: what that WEEK was, as a stretch of time — what it turned on, what "
    "changed in it, what it was mostly about. Not a list of days and not a summary of "
    "each; one thing you would say if someone asked what the week had been like. Say what "
    "is true, not what is cheerful. No lists, no headings, no dates.\n\nThe week:\n"
    % _CHAPTER_WORDS)


def _days_ago(iso: str) -> float:
    from harness.skills import lifecycle as _lc
    try:
        return _lc._age_days(iso or "")
    except Exception:
        return 0.0


def weekly_chapter(ask=None) -> dict:
    """ONE paragraph for the week, written once every seven days. Best-effort, never raises.

    WHY THIS EXISTS. Her block is a fixed 2400 characters and her own narrative arrives at
    24-33 rows a day. Without a rollup that block shows six arbitrary recent lines of a
    store that will hold thousands inside a month, and "what has this month been like?" has
    no answer anywhere in the system: the day-paragraphs are prose files reachable only by
    read_journal's mtime window, and the rows are moments with no shape over them. A chapter
    is the same six characters of prefix spent on a week instead of on an evening.

    WHAT IT IS NOT. It is not becoming.nightly. That one asks who she has been BECOMING,
    over everything of hers; this one asks what the WEEK WAS, over the episodic kinds only
    (journal / narration / spoke_up). The one rule they share and must keep: NEITHER READS
    THE OTHER'S OUTPUT. `_CHAPTER_KINDS` excludes self_description, and becoming excludes
    chapter — otherwise each would distil the other's distillate every week and the pair
    would become the hall of mirrors note_own's docstring already warns about.

    IT MAY NOT RETIRE WHAT IT SUMMARISES. The chapter is INFERRED and her moments are
    OBSERVED, and verdict.may_supersede refuses an inference retiring ground truth — as it
    should: a paragraph about a week is not a correction of the week. It earns its place by
    LEADING HER BLOCK (self_model puts chapters ahead of raw narration), never by
    tombstoning. Every row it read stays live, recallable and findable.

    Latched on the STORE, not on a file: if a chapter already stands from inside the last
    six days, this writes nothing. Self-healing, and one less thing to keep in sync."""
    try:
        from harness.skills import memory as M
        from harness.skills import memclass as MC
        from harness.skills.self_stance import plain as _plain
        rows = [r for r in M.live_rows() if r.get("speaker") == "self"
                and r.get("mem_class") in (MC.SELF_NARRATIVE, MC.FEELING)]
        for r in rows:
            if r.get("kind") == "chapter" and _days_ago(r.get("ts") or "") < _CHAPTER_EVERY_DAYS - 1:
                return {"written": False, "why": "a chapter already stands for this week"}
        recent = [r for r in rows
                  if (r.get("kind") or "") in _CHAPTER_KINDS
                  and _days_ago(r.get("ts") or "") <= _CHAPTER_EVERY_DAYS]
        recent.sort(key=lambda r: r.get("ts") or "")            # OLDEST first: it is a week
        recent = recent[-_CHAPTER_MAX_ROWS:]
        mine = own_time(_CHAPTER_EVERY_DAYS)
        if not recent and not mine:
            return {"written": False, "why": "nothing happened this week that she kept"}
        days = sorted({(r.get("ts") or "")[:10] for r in recent if (r.get("ts") or "")})
        if len(days) < 2 and not mine:
            return {"written": False, "why": "one day is not a week"}
        body = "\n".join("- [%s] %s" % ((r.get("ts") or "")[:10], (r.get("text") or "").strip())
                         for r in recent)
        if mine:
            body = ((body + "\n\n") if body else "") + "On your own time:\n" + "\n".join(
                "- " + m[:220] for m in reversed(mine[:20]))
        text = ((ask or _oneshot)(CHAPTER_PROMPT + body + "\n\nThe week:") or "").strip()
        try:
            from harness.inference.stream_processor import strip_control_surfaces
            text = strip_control_surfaces(text)
        except Exception:
            pass
        text = _plain(text)
        if len(text.split()) < 8:
            return {"written": False, "why": "the model returned nothing usable"}
        res = M.remember_about_self(
            text, kind="chapter", source=_CHAPTER_SRC,
            derived_from=[r.get("name") for r in recent],
            support_days=len(days), support_kinds=[r.get("kind") or "" for r in recent])
        return {"written": ("stored" in res and "not stored" not in res) or "reinforced" in res,
                "text": text, "result": res, "support_days": len(days),
                "rows": len(recent), "own_time": len(mine),
                "derived_from": [r.get("name") for r in recent]}
    except Exception as exc:
        return {"written": False, "why": str(exc)[:160]}


def note_own(text: str, kind: str = "solo") -> dict:
    """Write one thing she did on her own time into her journal. Raw, not composed.

    THE GAP THIS FILLS (2026-08-04, his ask). The nightly composer writes ONE paragraph a
    night, from the tail of the conversation — which means her account of a day is built
    entirely out of the parts he was present for. Everything she did while he was asleep
    existed only as a line in a chat log he had to scroll back through, and was gone from
    her own memory of the day entirely.

    So a solo turn is written down AS IT HAPPENS, in her own words, addressed to nobody.
    Two things follow, and the second is the better one:

      * she can read back what she did while he was out (`read_journal`), which is the
        difference between having had a day and having a log of one
      * the NIGHTLY COMPOSER can read these as material. Until now it saw only the
        conversation, so "what was today like" could only ever mean "what did we say".
        Now a day where he was away has something in it to write about.

    Its own `mem_kind` rather than `narrative`: the composed paragraph is a reflection and
    these are the raw moments it reflects ON. Collapsing them would leave the composer
    quoting itself, which is how a journal becomes a hall of mirrors.
    """
    t = (text or "").strip()
    if not t:
        return {"written": False, "why": "nothing to write"}
    try:
        full = _tier_full()
        os.makedirs(full, exist_ok=True)
        addr = hashlib.sha256(("%s|%s|%d" % (kind, t, int(time.time()))
                               ).encode("utf-8")).hexdigest()[:16]
        with open(os.path.join(full, addr + ".md"), "w", encoding="utf-8") as f:
            f.write("---\ntype: mem-concept\ntitle: %s\naddr: %s\n"
                    "mem_kind: own_time\nmem_class: persona\nmem_owner: self\n"
                    "mem_delivery: system\nts: %d\n---\n\n%s\n"
                    % (kind, addr, int(time.time()), t))
        return {"written": True, "addr": addr}
    except Exception as e:
        return {"written": False, "why": str(e)[:120]}


def own_time(days: int = 2) -> list:
    """What she did on her own, most recent first. Material for the composer, and for her."""
    import time as _t
    out = []
    try:
        root = _tier_full()
        cutoff = _t.time() - max(1, int(days)) * 86400
        for fn in os.listdir(root):
            if not fn.endswith(".md"):
                continue
            fp = os.path.join(root, fn)
            if os.path.getmtime(fp) < cutoff:
                continue
            with open(fp, encoding="utf-8") as f:
                body = f.read()
            if "mem_kind: own_time" not in body:
                continue
            out.append((os.path.getmtime(fp), body.split("---", 2)[-1].strip()))
    except Exception:
        return []
    out.sort(reverse=True)
    return [t for _at, t in out]


def read_journal(days: int = 7) -> str:
    """Read your own journal — what you wrote about the two of you, most recent first.

    SHE COULD NOT READ HER OWN PAST. The composer has written one paragraph a night
    since the ticker was armed, and world.py puts the CURRENT one in her standing
    prefix — but the history existed only as content-addressed snapshots nothing
    could query. "When did we last talk?" had a true answer she could see; "what has
    this week been like?" did not."""
    import os as _os
    import time as _t
    rows = []
    try:
        root = _tier_full()
        cutoff = _t.time() - max(1, int(days)) * 86400
        for fn in _os.listdir(root):
            if not fn.endswith(".md"):
                continue
            fp = _os.path.join(root, fn)
            if _os.path.getmtime(fp) < cutoff:
                continue
            with open(fp, encoding="utf-8") as f:
                body = f.read()
            if "mem_kind: narrative" not in body:
                continue
            rows.append((_os.path.getmtime(fp), body.split("---", 2)[-1].strip()))
    except Exception as exc:
        return f"[cannot read the journal: {exc}]"
    # HER OWN TIME BELONGS IN HER OWN JOURNAL. The composed paragraphs are what she made
    # of the days; these are the things she actually did in them, on the evenings he was
    # not there. Kept SEPARATE and labelled rather than interleaved, because they are
    # different kinds of writing — one is a reflection, the others are the moments — and
    # a reader who cannot tell them apart cannot tell what she concluded from what she did.
    mine = own_time(days)
    body = ""
    if rows:
        rows.sort(reverse=True)
        body = (os.linesep * 2).join(t for _at, t in rows[:20])
    else:
        body = current() or ""
    if mine:
        body = (body + (os.linesep * 2) if body else "") + (
            "— on my own time —" + os.linesep
            + os.linesep.join("· " + m for m in mine[:20]))
    # ── AND THE WEEKS (2026-08-22) ────────────────────────────────────────────────────
    # Days are all this could ever return, so "what has this MONTH been like?" had no
    # answer anywhere in the system: 30 day-paragraphs is not a month, it is thirty days.
    # The chapters go FIRST and labelled — coarsest to finest, the way you would actually
    # answer that question — and they are kept separate for the same reason her own time
    # is: a reader who cannot tell a week from a night cannot tell what she concluded
    # from what happened.
    try:
        from harness.skills import memory as _M
        weeks = sorted((r for r in _M.live_rows()
                        if r.get("speaker") == "self" and r.get("kind") == "chapter"),
                       key=lambda r: r.get("ts") or "", reverse=True)[:8]
        if weeks:
            body = ("— the weeks —" + os.linesep
                    + os.linesep.join("· week ending %s: %s" % ((w.get("ts") or "")[:10],
                                                                (w.get("text") or "").strip())
                                      for w in weeks)
                    + (os.linesep * 2) + body)
    except Exception:
        pass
    return body or f"[nothing written in the last {days} days]"
