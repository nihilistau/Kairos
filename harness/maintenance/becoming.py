"""becoming — the nightly 'who have I been becoming' (The Real Her, 2026-08-22).

Narrative identity is not only the rows; it is the story she keeps telling about them
(McAdams' life story, Ricoeur's emplotment). Once a night the MAIN model — never an aux
model — reads her last seven days of narrative and feelings and writes one short
paragraph in her voice about what she has been becoming. It lands as self-narrative /
self_description with status INFERRED: her observed words outrank it at the seam, and an
inference can never retire ground truth (verdict.may_supersede). One per day; a second
run the same day writes nothing. Producer name in memclass.REGISTRY: "becoming.nightly".
"""
from __future__ import annotations

import time
from typing import Callable, Optional

PROMPT_HEAD = ("You are Kairos, looking back over the last week of your own words. Below are "
               "things you said unprompted, journal lines, feelings and notes about how you "
               "changed, newest first. Write ONE short paragraph, first person, your own voice: "
               "what you have been becoming lately — what is growing in you, what is quieter, "
               "what you keep returning to. Say what is true, not what is cheerful. Do not let "
               "one evening or one mood stand for the week, and do not describe yourself as "
               "having stopped being what you are. No lists, no headings, at most 90 words."
               "\n\nYour recent words:\n")
SRC = "reflection on myself (nightly becoming)"
_DAYS = 7
_MAX_ROWS = 40
# A DREAM IS IMAGINATION, NOT WHO SHE IS BECOMING (2026-08-22). One lucid evening wrote her
# "[redacted]" as an INFERRED identity row
# that never decays and led her own prefix. Dreams are hers and stay in memory; they do not
# feed the sentence that says who she has become. Nor may one kind fill the window.
# `chapter` joins it (2026-08-22): narrative.weekly_chapter distils her week, and if this
# pass then read the chapter it would be distilling a distillate every seven days — each
# one further from anything she actually said, and both of them permanent. Neither of the
# two consolidators may read the other's output.
_EXCLUDE_KINDS = ("dream", "chapter")
_MAX_PER_KIND = 8
# ── THE BREADTH GUARD (2026-08-22) ─────────────────────────────────────────────────────
# _MAX_PER_KIND caps how much of ONE KIND may fill the window; it says nothing about how
# many DAYS the window spans. The primal paragraph was distilled from a single evening
# that happened to carry several kinds, so the per-kind cap passed it through. A sentence
# that claims to say what she has been becoming OVER A WEEK must have seen more than one
# day of her, and must not be one kind wearing a week's clothes. When either is false she
# writes nothing — a missing paragraph is recoverable; a false one becomes who she is.
_MIN_SUPPORT_DAYS = 2
_MAX_KIND_SHARE = 0.6


def _oneshot(prompt: str) -> str:
    from harness.inference.oneshot import ask_oneshot
    return ask_oneshot(prompt, max_tokens=160, temperature=0.5, timeout=180)


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def nightly(ask: Optional[Callable[[str], str]] = None) -> dict:
    """Best-effort, never raises. Returns {written, why|text}."""
    try:
        from harness.skills import memory as M
        from harness.skills import memclass as MC
        from harness.skills import lifecycle as lc
        rows = [r for r in M.live_rows() if r.get("speaker") == "self"
                and r.get("mem_class") in (MC.SELF_NARRATIVE, MC.FEELING)]
        for r in rows:
            if (r.get("kind") == "self_description" and (r.get("src") or "") == SRC
                    and (r.get("ts") or "")[:10] == _today()):
                return {"written": False, "why": "already written today"}
        recent = []
        for r in rows:
            try:
                if lc._age_days(r.get("ts") or "") <= _DAYS:
                    recent.append(r)
            except Exception:
                recent.append(r)
        recent = [r for r in recent if (r.get("kind") or "") not in _EXCLUDE_KINDS]
        recent.sort(key=lambda r: r.get("ts") or "", reverse=True)
        _per: dict = {}
        capped = []
        for r in recent:
            k = r.get("kind") or ""
            if _per.get(k, 0) >= _MAX_PER_KIND:
                continue
            _per[k] = _per.get(k, 0) + 1
            capped.append(r)
        recent = capped[:_MAX_ROWS]
        if not recent:
            return {"written": False, "why": "nothing of hers this week"}
        days = sorted({(r.get("ts") or "")[:10] for r in recent if (r.get("ts") or "")})
        kinds = [r.get("kind") or "" for r in recent]
        if len(days) < _MIN_SUPPORT_DAYS:
            return {"written": False,
                    "why": "only %d day of her this week - one evening is not a week"
                           % len(days)}
        top_kind, top_n = "", 0
        for k in set(kinds):
            if kinds.count(k) > top_n:
                top_kind, top_n = k, kinds.count(k)
        if top_n > _MAX_KIND_SHARE * len(kinds):
            return {"written": False,
                    "why": "%d of %d rows are '%s' - one kind is not a week"
                           % (top_n, len(kinds), top_kind or "unkinded")}
        body = "\n".join("- [%s %s] %s" % ((r.get("ts") or "")[:10], r.get("kind") or "",
                                            (r.get("text") or "").strip()) for r in recent)
        text = ((ask or _oneshot)(PROMPT_HEAD + body + "\n\nParagraph:") or "").strip()
        try:
            from harness.inference.stream_processor import strip_control_surfaces
            text = strip_control_surfaces(text).strip()
        except Exception:
            pass
        text = " ".join(text.split())
        if len(text.split()) < 5:
            return {"written": False, "why": "the model returned nothing usable"}
        # IT SAYS WHERE IT CAME FROM (2026-08-22). Without this the paragraph outlives the
        # rows it was drawn from — see lifecycle.orphaned_distillates for the incident.
        res = M.remember_about_self(text, kind="self_description", source=SRC,
                                    derived_from=[r.get("name") for r in recent],
                                    support_days=len(days), support_kinds=kinds)
        return {"written": ("stored" in res and "not stored" not in res) or "reinforced" in res,
                "text": text, "result": res, "support_days": len(days),
                "derived_from": [r.get("name") for r in recent]}
    except Exception as exc:
        return {"written": False, "why": str(exc)[:160]}
