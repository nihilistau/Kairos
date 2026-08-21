"""research.py — the tier above looking things up: handing a real question out.

THE LADDER SHE HAS, from cheapest to most expensive:

    think     the private channel. Free, hers, already there.
    recall    memory. Free, hers, and the only one that is about HIM.
    check     run_python / web_search. Seconds, external, shallow.
    RESEARCH  this. Minutes, external, and it actually THINKS about the question.
    work      delegate_code. A worktree, gates, a branch he may merge.

Research is a different SHAPE from delegate_code, not a variant of it, and the two
differ in exactly the ways that matter:

    delegate_code   WRITES. Isolated in a worktree, web DISABLED (a delegated edit
                    has no business browsing), diff-verdicted, never merged.
    research        READS. No worktree because there is nothing to contain, web
                    ENABLED because that is the entire point, and it must not be
                    able to touch the tree at all.

(The old CLI carried a page of deny rules to keep a headless agent read-only; the
REST researchers cannot touch the tree at all, which is the posture with no rules
left to enforce.)

PLUGGABLE ON PURPOSE. `Researcher` is a two-method protocol — the Grok CLI was the
first implementation (retired 2026-08-21 for the REST API), XaiResearcher is the
default, SidecarResearcher is the no-key local fallback, and the next one drops in
without touching a caller.

── THE HONESTY RULE, WHICH IS THE POINT OF THIS FILE ─────────────────────────────

This repo has spent a week closing confabulation: the world-block header, the
unspeakable recall note, "I always loved watching her play with my toys" when there
were no toys. Delegation makes a NEW way to be wrong available, so the line is drawn
before the capability ships:

    A delegated CONCLUSION may be integrated as her own thinking. That is what
    thinking IS, and demanding a citation for every inference would make her a
    search box again.

    A delegated FACT may never be attributed to memory or to him. "You told me"
    and "I remember" are claims about the world; they are only true when they
    are true.

Non-negotiable #4 — her word never outranks his, an inference may never retire an
observation — extended to a third party. The provenance is recorded on the receipt
whatever she says aloud, so the ledger stays honest even when the sentence is casual.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Callable, List, Optional

from harness.skills.delegate import repo_root

ARMED = os.environ.get("SP_RESEARCH", "0") == "1"
TIMEOUT = float(os.environ.get("SP_RESEARCH_TIMEOUT", "600"))
RECEIPTS = os.environ.get("SP_RESEARCH_RECEIPTS",
                          os.path.join(repo_root(), "var", "research"))

DEPTHS = {
    "quick":    {"max_turns": 6,  "hint": "Answer directly and briefly."},
    "normal":   {"max_turns": 14, "hint": "Look into this properly before answering."},
    "thorough": {"max_turns": 30, "hint": "Research this carefully. Check more than "
                                          "one source and say where they disagree."},
}


@dataclass
class Answer:
    """What came back, and where it came from. `provenance` is never empty."""
    text: str
    provenance: str                      # who answered, in one phrase
    confidence: str = "unknown"          # high | medium | low | unknown
    ok: bool = True
    seconds: float = 0.0
    question: str = ""
    receipt: str = ""
    sources: List[str] = field(default_factory=list)

    def for_model(self) -> str:
        """What the tool hands back to her.

        The provenance line is NOT decoration. She is told, in the tool output
        itself, that this came from outside her — so that integrating the reasoning
        is a choice she makes knowingly rather than a fact she has to reconstruct."""
        if not self.ok:
            return f"[research failed: {self.text}]"
        head = f"({self.provenance} — this is not your memory and not something he told you)"
        return f"{head}\n\n{self.text}"


class Researcher:
    """Two methods. Anything satisfying this can be the research tier."""
    name = "researcher"

    def available(self) -> bool:          # pragma: no cover - trivial
        raise NotImplementedError

    def ask(self, question: str, depth: str = "normal") -> Answer:  # pragma: no cover
        raise NotImplementedError


# ── THE GROK CLI RESEARCHER IS GONE (2026-08-21, operator: "use the API instead
# of the cli. clean up the cli."). It carried a GUI login's auth.json, an
# undocumented agent surface, and an argv deny-list to keep a headless agent
# read-only — a page of defence for a dependency the REST API simply does not
# have. XaiResearcher (Responses API + web_search) is the default; the local
# SidecarResearcher is the no-key fallback. delegate_code's worktree CLI is a
# different tool for a different job and is untouched.

def _xai_key() -> str:
    """ONE key source — harness/skills/xai.py (env spellings, then the key FILE
    under var/secrets/). The CLI's auth.json is gone with the CLI."""
    from harness.skills import xai as _x
    return _x.api_key()


def _xai_model() -> str:
    return (os.environ.get("SP_RESEARCH_XAI_MODEL") or "grok-4-1-fast").strip()


class XaiResearcher(Researcher):
    """xAI Responses API, web_search tool — no local process, no tree.

    A contractor with a browser, not her. Provenance is forced into the tool
    output like every researcher. Available only when a key is set.
    """
    name = "xai"

    def available(self) -> bool:
        return bool(_xai_key())

    def ask(self, question: str, depth: str = "normal",
            post: Optional[Callable] = None) -> Answer:
        t0 = time.perf_counter()
        key = _xai_key()
        if not key:
            return Answer(text="no xAI API key", provenance="xai", ok=False,
                          question=question)
        d = DEPTHS.get(depth, DEPTHS["normal"])
        payload = {
            "model": _xai_model(),
            "input": [{"role": "user", "content": f"{d['hint']}\n\n{question}"}],
            "tools": [{"type": "web_search"}],
        }
        poster = post or _xai_post
        try:
            obj = poster(payload, key, TIMEOUT)
        except Exception as exc:
            return Answer(text=f"{type(exc).__name__}: {exc}", provenance="xai",
                          ok=False, question=question,
                          seconds=time.perf_counter() - t0)
        text, sources = _parse_xai(obj)
        dt = time.perf_counter() - t0
        if not text:
            return Answer(text="no answer came back", provenance="xai",
                          ok=False, seconds=dt, question=question)
        ans = Answer(text=text, provenance="researched by xai",
                     seconds=round(dt, 1), question=question, sources=sources)
        ans.receipt = _receipt(ans, ["xai", _xai_model(), "web_search", depth])
        return ans


def _xai_post(payload: dict, key: str, timeout: float) -> dict:
    import urllib.request
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.x.ai/v1/responses", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _parse_xai(obj) -> tuple:
    """Responses API, defensively. Schema drift must not raise into her mouth."""
    if not isinstance(obj, dict):
        return str(obj).strip(), []
    # `text` drifted from a string to a config OBJECT ({"format": ...}) in the live
    # API (2026-08-21) and the old line raised — into exactly the mouth this
    # docstring promises to protect. Only a str counts as an answer.
    text = obj.get("output_text") or obj.get("text") or ""
    text = text.strip() if isinstance(text, str) else ""
    if not text:
        chunks = []
        for item in obj.get("output") or obj.get("choices") or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message" or item.get("role") == "assistant":
                content = item.get("content") or item.get("message") or ""
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict):
                            chunks.append(part.get("text") or part.get("content") or "")
                elif isinstance(content, str):
                    chunks.append(content)
                elif isinstance(content, dict):
                    chunks.append(content.get("content") or content.get("text") or "")
        text = "\n".join(c for c in chunks if c).strip()
    sources = []
    for c in obj.get("citations") or []:
        if isinstance(c, str) and c.startswith("http"):
            sources.append(c)
        elif isinstance(c, dict) and (c.get("url") or "").startswith("http"):
            sources.append(c["url"])
    if not sources:
        sources = sorted(set(re.findall(r"https?://[^\s\)\]\"']+", text)))[:8]
    return text, sources[:8]


def _receipt(ans: Answer, argv: List[str]) -> str:
    """Every research call leaves one. The provenance survives whatever she says."""
    try:
        os.makedirs(RECEIPTS, exist_ok=True)
        p = os.path.join(RECEIPTS, f"r_{time.strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:6]}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({**asdict(ans), "argv": argv}, f, indent=2, ensure_ascii=False)
        return p
    except OSError:
        return ""


class SidecarResearcher(Researcher):
    """LOCAL research: search → read the actual pages → synthesize, all on CPU.

    The third implementation of the two-method protocol, and the first with no
    key, no CLI and no cloud: the existing search seam (Wikipedia-blended) finds
    the pages, web_fetch pulls their text, and the LFM sidecar reads each one
    ORIENTED BY THE QUESTION (sidecar/summarize.read_long) before a final
    synthesis pass. Depth is pages read: normal=2, deep=4.

    The honesty rule is inherited whole: the Answer's provenance says the pages
    were read by a local helper model, sources carry the URLs, and for_model()
    still opens with "this is not your memory and not something he told you"."""
    name = "sidecar"

    def available(self) -> bool:
        try:
            from harness.sidecar import client as _aux
            return _aux.available()
        except Exception:
            return False

    def ask(self, question: str, depth: str = "normal") -> Answer:
        t0 = time.time()
        from harness.sidecar import client as _aux, summarize as _sum
        from harness.skills.search import search_web as _search
        from harness.skills.system_tools import fetch_page_text as _fetch
        n_pages = 4 if depth == "deep" else 2
        model = os.environ.get("SP_AUX_RESEARCH_MODEL", "") or _aux.chat_model()
        hits = _search(question, n=6) or []
        urls = [h["url"] for h in hits if h.get("url")][: n_pages]
        if not urls:
            return Answer(text="the search returned no pages to read", ok=False,
                          provenance="local sidecar research", question=question,
                          seconds=time.time() - t0)
        notes: List[str] = []
        read: List[str] = []
        for u in urls:
            page = _fetch(u)
            if not page:
                continue
            digest = _sum.read_long(page, question=question)
            if digest and "NOTHING RELEVANT" not in digest.upper():
                notes.append(f"[{u}]\n{digest}")
                read.append(u)
        if not notes:
            return Answer(text="the pages fetched said nothing usable on this",
                          ok=False, provenance="local sidecar research",
                          question=question, seconds=time.time() - t0)
        synthesis = _aux.chat(
            [{"role": "user", "content":
              "Question: %s\n\nNotes from %d web pages (each labelled with its "
              "URL):\n\n%s\n\nWrite a direct, factual answer to the question from "
              "these notes ONLY. Name which source supports each main claim. If "
              "the notes disagree or fall short, say so plainly — never fill the "
              "gap." % (question, len(notes), "\n\n".join(notes))}],
            max_tokens=700, model=model)
        if not synthesis:
            return Answer(text="the sidecar went dark mid-synthesis", ok=False,
                          provenance="local sidecar research", question=question,
                          seconds=time.time() - t0)
        return Answer(text=synthesis,
                      provenance="local research — %d web pages read and "
                                 "synthesized by a small helper model on CPU"
                                 % len(read),
                      confidence="medium", question=question,
                      seconds=time.time() - t0, sources=read)


_BACKEND: Optional[Researcher] = None


def _pick_backend() -> Researcher:
    # LIVE KNOB FIRST (2026-08-21): research.backend from the tuning store rules
    # per call; env is the boot default.
    name = ""
    try:
        from harness.tuning import registry as _t
        v = _t.chosen("research.backend")        # override-only; env is the default
        name = str(v or "").strip().lower()
    except Exception:
        name = ""
    if not name:
        name = (os.environ.get("SP_RESEARCH_BACKEND") or "xai").strip().lower()
    if name == "sidecar":
        return SidecarResearcher()
    if name in ("xai", "grok"):        # "grok" spellings in old profiles mean the API now
        return XaiResearcher()
    # auto: the API when the key exists, else the local sidecar
    x = XaiResearcher()
    if x.available():
        return x
    return SidecarResearcher()


def backend() -> Researcher:
    """The active researcher. Grok CLI is the first implementation; xAI API is the second."""
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = _pick_backend()
    return _BACKEND


def set_backend(r: Researcher) -> None:
    """For tests, and for the day there is a second implementation."""
    global _BACKEND
    _BACKEND = r


def research(question: str, depth: str = "normal") -> str:
    """Hand a real question to a stronger system and think with what comes back."""
    q = (question or "").strip()
    if not q:
        return "[research: no question]"
    if not ARMED:
        return "[research is not armed — SP_RESEARCH=0]"
    b = backend()
    if not b.available():
        return f"[research unavailable: no {b.name} backend on this machine]"
    if depth not in DEPTHS:
        depth = "normal"
    from harness.skills import looking as L
    L.begin("research", q)
    try:
        ans = b.ask(q, depth)
        L.end(ans.ok, ans.text[:800], ans.sources, title=q[:80])
        return ans.for_model()
    except Exception as exc:
        L.end(False, str(exc)[:200], title=q[:80])
        raise


def status() -> dict:
    b = backend()
    return {"armed": ARMED, "backend": b.name, "available": b.available(),
            "depths": sorted(DEPTHS), "receipts": RECEIPTS,
            "timeout_s": TIMEOUT}


def research_tools():
    """Armed only when SP_RESEARCH is on AND a backend exists — a tool that always
    answers "not armed" is worse than absent, because she keeps reaching for it."""
    try:
        from harness.toolcore.tools import ToolSpec
        if not ARMED or not backend().available():
            return []
        return [ToolSpec.from_callable(research)]
    except Exception:
        return []


RESEARCH_TOOLS = research_tools()
