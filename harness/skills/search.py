"""search.py — ONE tool, several engines, DDG as the floor.

web_search is the name she calls. The bug class is two tools that both "search":
she picks the wrong one, or invents results when the one she picked is empty.

Backends (same return shape: [{title, url, snippet}]):

    ddg      DuckDuckGo HTML. Always available. The floor.
    brave    Brave Search API. Needs SP_SEARCH_BRAVE_KEY (or BRAVE_API_KEY).
    tavily   Tavily API. Needs SP_SEARCH_TAVILY_KEY (or TAVILY_API_KEY).
    searxng  A SearXNG instance. Needs SP_SEARCH_SEARXNG_URL.

xAI is NOT a searcher. It thinks about a question with web enabled — that is
research(), a different tier. Putting it here would make web_search take
minutes and cost a model call for a list of links.

SP_SEARCH_BACKEND selects. `auto` picks the first available paid engine, else
ddg. Default is ddg so a key in the environment cannot surprise-bill.
If the chosen engine returns nothing, DDG still runs — empty is empty, but a
dead API must not be the only look she gets.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from typing import List, Optional

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")


def _clean(s: str) -> str:
    import html
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def _empty(hits: list) -> bool:
    if not hits:
        return True
    if len(hits) == 1 and (hits[0].get("title") or "").startswith("[search error"):
        return True
    return not any((h.get("url") or "").strip() for h in hits)


class Searcher:
    name = "searcher"

    def available(self) -> bool:
        raise NotImplementedError

    def search(self, query: str, n: int = 5) -> list:
        raise NotImplementedError


# ── DDG (the floor) ──────────────────────────────────────────────────────────
# Verified against the live markup: result__a / result__snippet. A scraper
# written against remembered HTML is a scraper written against no HTML.
_DDG_RESULT = re.compile(
    r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
    r'(?:.*?class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>)?', re.S | re.I)


class DuckDuckGoSearcher(Searcher):
    name = "ddg"

    def available(self) -> bool:
        return True

    def search(self, query: str, n: int = 5) -> list:
        out = []
        try:
            data = urllib.parse.urlencode({"q": query}).encode()
            req = urllib.request.Request(
                "https://html.duckduckgo.com/html/", data=data,
                headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                html_text = r.read().decode("utf-8", "replace")
            for href, title, snip in _DDG_RESULT.findall(html_text)[:n]:
                url = urllib.parse.unquote(href)
                m = re.search(r"uddg=([^&]+)", url)
                if m:
                    url = urllib.parse.unquote(m.group(1))
                out.append({"title": _clean(title), "url": url,
                            "snippet": _clean(snip)})
        except Exception as exc:
            out.append({"title": f"[search error: {exc}]", "url": "", "snippet": ""})
        return out


class BraveSearcher(Searcher):
    name = "brave"

    def available(self) -> bool:
        return bool(_brave_key())

    def search(self, query: str, n: int = 5) -> list:
        key = _brave_key()
        if not key:
            return [{"title": "[search error: no brave key]", "url": "", "snippet": ""}]
        url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode(
            {"q": query, "count": max(1, min(int(n), 20))})
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "X-Subscription-Token": key,
            "User-Agent": UA,
        })
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                obj = json.loads(r.read().decode("utf-8", "replace"))
        except Exception as exc:
            return [{"title": f"[search error: {exc}]", "url": "", "snippet": ""}]
        rows = ((obj.get("web") or {}).get("results") or [])[:n]
        return [{"title": (h.get("title") or "").strip(),
                 "url": (h.get("url") or "").strip(),
                 "snippet": (h.get("description") or "").strip()}
                for h in rows if isinstance(h, dict)]


class TavilySearcher(Searcher):
    name = "tavily"

    def available(self) -> bool:
        return bool(_tavily_key())

    def search(self, query: str, n: int = 5) -> list:
        key = _tavily_key()
        if not key:
            return [{"title": "[search error: no tavily key]", "url": "", "snippet": ""}]
        body = json.dumps({"api_key": key, "query": query,
                           "max_results": max(1, min(int(n), 10))}).encode()
        req = urllib.request.Request(
            "https://api.tavily.com/search", data=body,
            headers={"Content-Type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                obj = json.loads(r.read().decode("utf-8", "replace"))
        except Exception as exc:
            return [{"title": f"[search error: {exc}]", "url": "", "snippet": ""}]
        rows = (obj.get("results") or [])[:n]
        return [{"title": (h.get("title") or "").strip(),
                 "url": (h.get("url") or "").strip(),
                 "snippet": (h.get("content") or h.get("snippet") or "").strip()}
                for h in rows if isinstance(h, dict)]


class SearXNGSearcher(Searcher):
    name = "searxng"

    def available(self) -> bool:
        return bool(_searx_url())

    def search(self, query: str, n: int = 5) -> list:
        base = _searx_url().rstrip("/")
        if not base:
            return [{"title": "[search error: no searxng url]", "url": "", "snippet": ""}]
        url = base + "/search?" + urllib.parse.urlencode(
            {"q": query, "format": "json", "language": "en"})
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                obj = json.loads(r.read().decode("utf-8", "replace"))
        except Exception as exc:
            return [{"title": f"[search error: {exc}]", "url": "", "snippet": ""}]
        rows = (obj.get("results") or [])[:n]
        return [{"title": (h.get("title") or "").strip(),
                 "url": (h.get("url") or "").strip(),
                 "snippet": (h.get("content") or "").strip()}
                for h in rows if isinstance(h, dict)]


# ── WIKIPEDIA (the substance) ────────────────────────────────────────────────
# Keyless, stable, and the one engine whose FIRST result carries an actual answer.
# The operator's words (2026-08-20): "she uses duck duck go and gets whatever is
# first" — and her own time reads these results, so whatever is first becomes her
# evening. Two API calls, both boring on purpose: MediaWiki list=search for ranked
# titles+snippets, and the REST page summary for a clean plaintext extract — no
# scraping, no key, no HTML archaeology. It is not a general searcher (news, prices
# and stock levels are not encyclopedic), so it is a BLEND in search_web rather than
# a replacement backend: DDG keeps the breadth, Wikipedia supplies the substance.
class WikipediaSearcher(Searcher):
    name = "wikipedia"

    def available(self) -> bool:
        return True

    def search(self, query: str, n: int = 5) -> list:
        url = ("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "query", "list": "search", "srsearch": query,
             "srlimit": max(1, min(int(n), 10)), "format": "json",
             "srprop": "snippet"}))
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                obj = json.loads(r.read().decode("utf-8", "replace"))
        except Exception as exc:
            return [{"title": f"[search error: {exc}]", "url": "", "snippet": ""}]
        rows = ((obj.get("query") or {}).get("search") or [])
        return [{"title": (h.get("title") or "").strip(),
                 "url": "https://en.wikipedia.org/wiki/"
                        + urllib.parse.quote((h.get("title") or "").replace(" ", "_")),
                 "snippet": _clean(h.get("snippet") or "")}
                for h in rows if isinstance(h, dict)]

    # ── SOMETHING SHE DID NOT GO LOOKING FOR (2026-08-23) ─────────────────────────
    # Her own-time act "look something up you have been curious about" can only ever
    # DEEPEN what she is already interested in: the query comes from her, so the result
    # comes back inside the same fence. A RANDOM article is the only mechanism here that
    # can introduce a subject she would never have asked for, which is the whole point.
    # No key, no scraping - the REST random endpoint returns a clean summary directly.
    MIN_EXTRACT = 240      # a two-line stub about a village is not worth her evening

    def random_page(self, tries: int = 4) -> dict:
        """A random article with enough substance to think about, or {} .

        RETRIES ON PURPOSE. Random Wikipedia is mostly stubs - a hamlet, a beetle, a
        footballer with two sentences - and handing her 40 characters produces an
        invented paragraph, which is the failure this codebase pays for most often.
        Up to `tries` draws for one with a real extract; if none has it, return {} and
        let the caller say so plainly. Never raises."""
        for _ in range(max(1, int(tries))):
            req = urllib.request.Request(
                "https://en.wikipedia.org/api/rest_v1/page/random/summary",
                headers={"User-Agent": UA, "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    obj = json.loads(r.read().decode("utf-8", "replace"))
            except Exception:
                continue
            extract = (obj.get("extract") or "").strip()
            title = (obj.get("title") or "").strip()
            if not title or len(extract) < self.MIN_EXTRACT:
                continue
            url = (((obj.get("content_urls") or {}).get("desktop") or {}).get("page")
                   or "https://en.wikipedia.org/wiki/"
                   + urllib.parse.quote(title.replace(" ", "_")))
            return {"title": title, "extract": extract, "url": url,
                    "description": (obj.get("description") or "").strip()}
        return {}

    def summary(self, title: str) -> str:
        """The REST page summary — a clean paragraph of actual encyclopedia, the thing
        a snippet only gestures at. Empty string on any failure; never raises."""
        url = ("https://en.wikipedia.org/api/rest_v1/page/summary/"
               + urllib.parse.quote(title.replace(" ", "_")))
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                obj = json.loads(r.read().decode("utf-8", "replace"))
            return (obj.get("extract") or "").strip()
        except Exception:
            return ""


def _brave_key() -> str:
    return (os.environ.get("SP_SEARCH_BRAVE_KEY") or
            os.environ.get("BRAVE_API_KEY") or "").strip()


def _tavily_key() -> str:
    return (os.environ.get("SP_SEARCH_TAVILY_KEY") or
            os.environ.get("TAVILY_API_KEY") or "").strip()


def _searx_url() -> str:
    return (os.environ.get("SP_SEARCH_SEARXNG_URL") or "").strip()


class XaiSearcher(Searcher):
    """Grok live search as a SEARCH ENGINE (2026-08-21, operator: "adding xAI as a
    search provider and as default"). One chat call with the web_search tool,
    instructed to return a strict JSON list — real, current results with the
    model's own snippet quality, at ~5-15 s a query against ddg's ~1 s. Empty on
    ANY failure (no key, refusal, unparseable) so the ddg floor catches it; the
    Wikipedia blend rides on top exactly as with every other engine."""
    name = "xai"

    def available(self) -> bool:
        try:
            from harness.skills import xai as _x
            return _x.available()
        except Exception:
            return False

    def search(self, query, n=5):
        try:
            from harness.skills import xai as _x
        except Exception:
            return []
        # THE RESPONSES DOOR, not chat/completions: live_search there answers 410
        # "deprecated — switch to the Agent Tools API". web_search on /v1/responses
        # IS that API, and it is the same door XaiResearcher already runs on.
        d = _x._post("/responses", {
            "model": os.environ.get("SP_SEARCH_XAI_MODEL", "grok-4-1-fast"),
            "input": [{"role": "user", "content":
                       "Web-search this query and return the %d most useful "
                       "results as STRICT JSON — an array of objects with keys "
                       "title, url, snippet (snippet <= 200 chars, factual, "
                       "from the page). No prose before or after the JSON.\n\n"
                       "Query: %s" % (max(1, int(n)), query)}],
            "tools": [{"type": "web_search"}]}, 60.0)
        if not d:
            return []
        try:
            from harness.skills.research import _parse_xai
            txt, _src = _parse_xai(d)
            i, j = txt.find("["), txt.rfind("]")
            rows = json.loads(txt[i:j + 1]) if i >= 0 and j > i else []
            out = []
            for r in rows[:n]:
                if isinstance(r, dict) and (r.get("url") or "").startswith("http"):
                    out.append({"title": str(r.get("title") or r["url"])[:200],
                                "url": r["url"],
                                "snippet": str(r.get("snippet") or "")[:300]})
            return out
        except Exception:
            return []


_ENGINES = {
    "ddg": DuckDuckGoSearcher,
    "brave": BraveSearcher,
    "tavily": TavilySearcher,
    "searxng": SearXNGSearcher,
    "wikipedia": WikipediaSearcher,   # selectable outright; also blended below
    "xai": XaiSearcher,               # Grok live search — the operator's default
}

_BACKEND: Optional[Searcher] = None
# The blend's wiki, as a seam: G-SEARCH is OFFLINE and stubs this — a gate that hits
# the live encyclopedia is measuring Wikimedia's uptime, not this module.
_WIKI = WikipediaSearcher


def _pick() -> Searcher:
    # LIVE KNOB FIRST (2026-08-21, the settings window): search.backend from the
    # tuning store rules per call; the env spelling is the boot default.
    name = ""
    try:
        from harness.tuning import registry as _t
        v = _t.chosen("search.backend")          # override-only; env is the default
        name = str(v or "").strip().lower()
    except Exception:
        name = ""
    if not name:
        name = (os.environ.get("SP_SEARCH_BACKEND") or "ddg").strip().lower()
    if name == "auto":
        for cand in ("brave", "tavily", "searxng", "ddg"):
            eng = _ENGINES[cand]()
            if eng.available():
                return eng
        return DuckDuckGoSearcher()
    cls = _ENGINES.get(name, DuckDuckGoSearcher)
    eng = cls()
    if not eng.available():
        return DuckDuckGoSearcher()
    return eng


def backend() -> Searcher:
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = _pick()
    return _BACKEND


def set_backend(s: Searcher) -> None:
    global _BACKEND
    _BACKEND = s


def random_article() -> dict:
    """One random encyclopedia article, or {}. Wikipedia only and deliberately: it is the
    one backend here that needs no key, and 'random' is not a thing a search engine does."""
    try:
        return WikipediaSearcher().random_page()
    except Exception:
        return {}


def search_web(query: str, n: int = 5) -> list:
    """THE HARNESS DOES THE SEARCHING. Returns [{title, url, snippet}].

    Chosen engine first; DDG if that comes back empty and it was not already DDG.
    Empty is empty. A dead API is not permission to invent."""
    q = (query or "").strip()
    if not q:
        return []
    # ANONYMOUS MODE (2026-08-24). A search query is the most legible summary of a
    # private conversation there is, and it goes to a third party in plain text.
    # Held. Returning [] rather than raising: an empty result is a shape every
    # caller here already handles ("Empty is empty. A dead API is not permission to
    # invent"), and the reason reaches her through the tool's own wording.
    from harness.control import anon as _anon
    if _anon.holds("net.search"):
        return []
    try:
        n = max(1, min(int(n), 10))
    except (TypeError, ValueError):
        n = 5
    b = backend()
    hits = b.search(q, n)
    if _empty(hits) and b.name != "ddg":
        hits = DuckDuckGoSearcher().search(q, n)
    # ── THE FIRST THING SHE READS IS SUBSTANCE (2026-08-20, operator's ask) ──────
    # "she uses duck duck go and gets whatever is first" — and her own time is built
    # on these results. When Wikipedia knows the topic, its top page goes FIRST with
    # the REST summary already attached as `extract` (clean plaintext — no page fetch,
    # no scraping), and the engine's breadth follows. When Wikipedia has nothing
    # relevant (prices, stock, news), the blend adds nothing and costs one quick
    # keyless call. Never raises; a dead Wikipedia is a no-op, not an error.
    if b.name != "wikipedia":
        try:
            wiki = _WIKI()
            w = wiki.search(q, 1)
            if w and not _empty(w):
                top = w[0]
                extract = wiki.summary(top["title"])
                if extract:
                    top["extract"] = extract[:700]
                    hits = [top] + [h for h in hits
                                    if (h.get("url") or "") != top["url"]][:max(1, n - 1)]
        except Exception:
            pass
    return hits


def status() -> dict:
    b = backend()
    return {
        "backend": b.name,
        "available": b.available(),
        "engines": {k: _ENGINES[k]().available() for k in _ENGINES},
    }
