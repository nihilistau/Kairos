"""System tools — the model's hands on the machine: filesystem, shell, PowerShell, web.

Exposed as ephemeral tools (ToolSpec.from_callable). These give the served model REAL
local access — read/write files, run shell + PowerShell commands, and search the web.
That is the agentic intent of the harness; treat it like any local automation (the model
runs on, and acts on, the operator's own machine). Every action has a timeout and a capped
output. Pair with harness.skills.memory.MEMORY_TOOLS + harness.toolcore.run_python.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

_OUT_CAP = 2000


def _cap(s: str) -> str:
    s = (s or "").strip()
    return s if len(s) <= _OUT_CAP else s[:_OUT_CAP] + "\n…(truncated)"


# ──── Filesystem ───────────────────────────────────────────────────────────
def list_dir(path: str = ".") -> str:
    """List the entries in a directory."""
    try:
        items = sorted(os.listdir(path))
        return _cap("\n".join(items)) or "(empty)"
    except Exception as exc:
        return f"[list_dir error: {exc}]"


def read_file(path: str) -> str:
    """Read and return the text contents of a file."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return _cap(f.read())
    except Exception as exc:
        return f"[read_file error: {exc}]"


def write_file(path: str, content: str) -> str:
    """Write text content to a file (overwrites)."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"wrote {len(content)} chars to {path}"
    except Exception as exc:
        return f"[write_file error: {exc}]"


# ──── Shell / PowerShell ─────────────────────────────────────────────────────
def run_shell(command: str) -> str:
    """Run a shell command and return its output (30s timeout)."""
    try:
        p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        return _cap(p.stdout + p.stderr) or "(no output)"
    except Exception as exc:
        return f"[run_shell error: {exc}]"


def run_powershell(command: str) -> str:
    """Run a Windows PowerShell command and return its output (30s timeout)."""
    try:
        p = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=30)
        return _cap(p.stdout + p.stderr) or "(no output)"
    except Exception as exc:
        return f"[run_powershell error: {exc}]"


# ──── Code ───────────────────────────────────────────────────────────────────
def run_python(code: str) -> str:
    """Execute Python code and return its output; a final bare expression is auto-printed (REPL-style, 15s timeout)."""
    wrapper = (
        "import ast\n"
        "src=" + repr(code) + "\n"
        "try:\n"
        "    t=ast.parse(src)\n"
        "    if t.body and isinstance(t.body[-1], ast.Expr):\n"
        "        last=ast.Expression(t.body.pop().value)\n"
        "        exec(compile(t,'<t>','exec'), globals())\n"
        "        v=eval(compile(last,'<t>','eval'), globals())\n"
        "        (print(v) if v is not None else None)\n"
        "    else:\n"
        "        exec(compile(t,'<t>','exec'), globals())\n"
        "except Exception as e:\n"
        "    print('Error:', repr(e))\n"
    )
    try:
        p = subprocess.run([sys.executable, "-c", wrapper], capture_output=True, text=True, timeout=15)
        return _cap(p.stdout + p.stderr) or "(no output)"
    except Exception as exc:
        return f"[run_python error: {exc}]"


# ──── Time ───────────────────────────────────────────────────────────────────
def get_time() -> str:
    """Return the current local date, time, and timezone."""
    import datetime
    now = datetime.datetime.now().astimezone()
    return now.strftime("%A %Y-%m-%d %H:%M:%S %Z (UTC%z)")


def fetch_page_text(url: str, max_chars: int = 40_000) -> str:
    """The FULL fetched page as stripped text — for READERS, not for tool output.

    Split out of web_fetch (2026-08-20): the tool's 2,000-char `_cap` is a display
    budget for the model's context, and the SidecarResearcher inherited it by
    calling the tool — so the 'whole page' its reader summarized was two thousand
    characters of nav bar and cookie banner, and every page came back NOTHING
    RELEVANT. Raises nothing; returns '' on failure so callers treat empty as
    empty."""
    import re as _re
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Kairos)"})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read(400_000).decode("utf-8", "replace")
        text = _re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=_re.DOTALL | _re.IGNORECASE)
        text = _re.sub(r"<[^>]+>", " ", text)
        text = _re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception:
        return ""


def web_fetch(url: str) -> str:
    """Fetch a URL and return its text content (HTML tags stripped, 15s timeout)."""
    text = fetch_page_text(url)
    if not text:
        return f"[web_fetch error: could not fetch {url}]"
    return _cap(text) or "(empty page)"


# ──── Web ────────────────────────────────────────────────────────────────────
# THE SEARCHING LIVES IN harness/skills/search.py. One tool name, several engines,
# DDG as the floor. This file only exposes the tool and fetches the first page.

def search_web(query: str, n: int = 5) -> list:
    """THE HARNESS DOES THE SEARCHING. Returns [{title, url, snippet}].

    The engines live in harness/skills/search.py so a second search tool cannot
    grow in here. web_search is the name she calls; empty is empty."""
    from harness.skills.search import search_web as _search
    return _search(query, n)


def read_something_new() -> str:
    """Read a random encyclopedia article — something you did NOT go looking for.

    Takes no query, on purpose: the point is a subject you would never have thought to
    ask about. Say what caught you, or that nothing did — a shrug is a real answer and
    more honest than a paragraph about a village you have no feeling about."""
    from harness.skills import looking as L
    from harness.skills.search import random_article
    L.begin("read_something_new", "a random article")
    a = random_article()
    if not a:
        L.end(False, "nothing came back", title="random article")
        return ("(nothing came back - say that plainly rather than inventing an "
                "article you did not read)")
    head = a["title"] + ((" — " + a["description"]) if a.get("description") else "")
    out = _cap(head + "\n\n" + a["extract"] + "\n" + a["url"])
    L.end(True, out[:800], [a["url"]], title=a["title"][:80])
    return out


def web_search(query: str) -> str:
    """Search the web. Returns the top real results — titles, snippets and links.

    e.g. web_search("RTX 3090 price 2026")
    Answer him from what comes back. If it comes back empty, SAY SO — never fill the gap
    with something that sounds right."""
    from harness.skills import looking as L
    L.begin("web_search", query)
    hits = search_web(query, n=5)
    if not hits or (len(hits) == 1 and hits[0]["title"].startswith("[search error")):
        L.end(False, "nothing came back", title=query[:80])
        return (f"(the search for {query!r} returned nothing — say that plainly, "
                "do not invent an answer)")
    # THE HARNESS READS THE FIRST PAGE. Snippets alone are how she invents
    # the rest. One fetch, capped, failure is silent — the snippets still stand.
    # ...unless the searcher already attached an extract (the Wikipedia blend ships a
    # clean REST summary) — scraping the page again would replace a paragraph of
    # encyclopedia with HTML archaeology of the same article.
    sources = [h["url"] for h in hits if h.get("url")]
    if hits[0].get("url") and not hits[0].get("extract"):
        extract = web_fetch(hits[0]["url"])
        if extract and not extract.startswith("[web_fetch"):
            # ── THE AUX READER (2026-08-20). A raw page truncated at 700 chars is
            # HTML archaeology; the 1.2B sidecar reads the WHOLE fetched text on CPU
            # in seconds and hands back the substance, oriented by her query. Dark
            # sidecar (or SP_AUX off) => byte-identical old behavior: truncate.
            digest = ""
            try:
                from harness.sidecar import client as _aux, summarize as _auxsum
                if _aux.available():
                    # the READER gets the whole page, not the tool-display cap
                    full = fetch_page_text(hits[0]["url"]) or extract
                    digest = _auxsum.read_long(full, question=query)
            except Exception:
                digest = ""
            hits[0]["extract"] = (_auxsum.labelled(digest, "the page")[:900] if digest
                                  else extract[:700])   # the silent librarian: labelled, never bare
    lines = []
    for h in hits:
        block = f"- {h['title']}\n  {h['snippet'][:180]}\n  {h['url']}"
        if h.get("extract"):
            block += "\n  extract: " + h["extract"]
        lines.append(block)
    out = _cap("\n".join(lines))
    L.end(True, out[:800], sources, title=query[:80])
    return out


FILESYSTEM_TOOLS = [list_dir, read_file, write_file]
SHELL_TOOLS = [run_shell, run_powershell]
CODE_TOOLS = [run_python]
WEB_TOOLS = [web_search, web_fetch]
TIME_TOOLS = [get_time]
SYSTEM_TOOLS = FILESYSTEM_TOOLS + SHELL_TOOLS + CODE_TOOLS + WEB_TOOLS + TIME_TOOLS
