"""G-CLAUDE — the one door to api.anthropic.com. OFFLINE (a fake client; no network, no key).

WHAT THIS GUARDS (2026-10-21). harness/skills/claude.py is the single transport every Claude
feature (research, search, consult) reaches the API through. Its promises are all
ABSENCES or exact shapes, so each leg pins one:
  * no key / no SDK  -> available() False, the factory is never built, ask() is ok=False;
  * the ambient ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL are never read (the client gets
    the key FILE and the fixed base url);
  * anonymous mode holds the door (and counts it) before any client exists;
  * a refusal is ok=False; pause_turn resumes; fallback only on the three allowed models;
    no `thinking` param, effort explicit; sources de-duplicated; the key never in last_error.

    python harness_tests/g_claude.py
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace as NS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import sandbox, check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_claude")                       # FIRST, before any harness. import

for _v in ("SP_CLAUDE_API_KEY", "SP_CLAUDE_KEY_FILE", "SP_CLAUDE_BASE_URL",
           "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"):
    os.environ.pop(_v, None)

from harness.skills import claude  # noqa: E402
from harness.control import anon  # noqa: E402

KEYFILE = os.path.join(SB, "claude.txt")
MISSING = os.path.join(SB, "nope.txt")


def write_key(v="FILEKEY"):
    with open(KEYFILE, "w", encoding="utf-8") as f:
        f.write(v + "\n")


# ── the fake client ───────────────────────────────────────────────────────────────────
CALLS: list = []          # kw of every stream() call
BUILT: list = []          # (key, base_url) of every factory call
QUEUE: list = []          # final messages to hand out, in order


def msg(content=None, stop="end_turn", cat=None, model="m"):
    return NS(content=content if content is not None else [NS(type="text", text="hi", citations=None)],
              stop_reason=stop,
              stop_details=NS(category=cat) if cat else None,
              model=model,
              usage=NS(input_tokens=3, output_tokens=4, cache_read_input_tokens=1))


class _Stream:
    def __init__(self, m):
        self.m = m

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.m


class _Messages:
    def stream(self, **kw):
        CALLS.append(dict(kw, messages=list(kw["messages"])))
        return _Stream(QUEUE.pop(0))


def factory(key, base):
    BUILT.append((key, base))
    return NS(beta=NS(messages=_Messages()))


REAL_FACTORY = claude._CLIENT_FACTORY          # the shipped default, kept for the SDK-header leg
REAL_SDK_FN = claude._sdk
claude._CLIENT_FACTORY = factory
claude._sdk = lambda: object()                 # the SDK "is there" unless a leg says otherwise
MSGS = [{"role": "user", "content": "q"}]


def reset():
    CALLS.clear()
    BUILT.clear()
    QUEUE.clear()


# ── no key ────────────────────────────────────────────────────────────────────────────
print("no key")
os.environ["SP_CLAUDE_KEY_FILE"] = MISSING
reset()
check("no key: unavailable", claude.available() is False)
check("no key: why == 'no key'", claude.why_unavailable() == "no key", claude.why_unavailable())
r = claude.ask(MSGS, model="claude-opus-5-5", door="net.research")
check("no key: ask ok=False", r.ok is False)
check("no key: factory never called", BUILT == [])

# ── no sdk ────────────────────────────────────────────────────────────────────────────
print("no sdk")
write_key()
os.environ["SP_CLAUDE_KEY_FILE"] = KEYFILE
real_sdk = claude._sdk
claude._sdk = lambda: None
check("no sdk: why == 'no sdk'", claude.why_unavailable() == "no sdk", claude.why_unavailable())
check("no sdk: unavailable", claude.available() is False)
r = claude.ask(MSGS, model="claude-opus-5-5", door="net.research")
check("no sdk: ask ok=False, no factory", r.ok is False and BUILT == [])
claude._sdk = real_sdk
check("key + sdk: available, why empty", claude.available() and claude.why_unavailable() == "")

# ── ambient env ignored ───────────────────────────────────────────────────────────────
print("ambient env ignored")
os.environ["ANTHROPIC_API_KEY"] = "AMBIENT"
os.environ["ANTHROPIC_BASE_URL"] = "http://evil.invalid"
reset()
QUEUE.append(msg())
r = claude.ask(MSGS, model="claude-opus-5-5", door="net.research")
check("ambient env ignored: file key + fixed base",
      BUILT == [("FILEKEY", "https://api.anthropic.com")], str(BUILT))
check("ambient env ignored: ok", r.ok and r.text == "hi", repr(r))
os.environ.pop("ANTHROPIC_API_KEY")
os.environ.pop("ANTHROPIC_BASE_URL")
os.environ["SP_CLAUDE_API_KEY"] = "ENVKEY"
reset()
QUEUE.append(msg())
claude.ask(MSGS, model="claude-opus-5-5", door="net.research")
check("SP_CLAUDE_API_KEY outranks the file", BUILT and BUILT[0][0] == "ENVKEY", str(BUILT))
os.environ.pop("SP_CLAUDE_API_KEY")
os.environ["SP_CLAUDE_BASE_URL"] = "https://proxy.example"
reset()
QUEUE.append(msg())
claude.ask(MSGS, model="claude-opus-5-5", door="net.research")
check("SP_CLAUDE_BASE_URL is the only override", BUILT and BUILT[0][1] == "https://proxy.example", str(BUILT))
os.environ.pop("SP_CLAUDE_BASE_URL")

# ── anon holds the door ───────────────────────────────────────────────────────────────
print("anon")
reset()
QUEUE.append(msg())
anon.enter()
try:
    r = claude.ask(MSGS, model="claude-opus-5-5", door="net.research")
    held = dict(anon._HELD)
finally:
    anon.leave()
check("anon: ok=False", r.ok is False)
check("anon: factory never called, no stream", BUILT == [] and CALLS == [])
check("anon: net.research counted", held.get("net.research") == 1, str(held))
check("anon: last_error is the anon reason", claude.last_error() == anon.WHY, claude.last_error())

# ── refusal ───────────────────────────────────────────────────────────────────────────
print("refusal")
reset()
QUEUE.append(msg(content=[], stop="refusal", cat="cyber"))
r = claude.ask(MSGS, model="claude-opus-5-5", door="net.research")
check("refusal is ok=False", r.ok is False)
check("refusal category carried", r.refusal == "cyber" and r.stop_reason == "refusal", repr(r))

# ── pause_turn ────────────────────────────────────────────────────────────────────────
print("pause_turn")
reset()
first = [NS(type="server_tool_use", id="x"), NS(type="text", text="partial", citations=None)]
QUEUE.append(msg(content=first, stop="pause_turn"))
QUEUE.append(msg(content=[NS(type="text", text="final", citations=None)]))
r = claude.ask(MSGS, model="claude-opus-5-5", door="net.research")
check("pause_turn: two stream calls", len(CALLS) == 2, str(len(CALLS)))
last = CALLS[1]["messages"][-1] if len(CALLS) > 1 else {}
check("pause_turn: second call ends with the assistant turn of the first",
      last.get("role") == "assistant" and last.get("content") is first, repr(last))
check("pause_turn: text is the second's", r.text == "final" and r.ok, repr(r))
reset()
for _ in range(5):
    QUEUE.append(msg(content=[], stop="pause_turn"))
r = claude.ask(MSGS, model="claude-opus-5-5", door="net.research")
check("pause_turn: bounded (3 resumes, 4 calls)", len(CALLS) == 4, str(len(CALLS)))

# ── fallback only where allowed ───────────────────────────────────────────────────────
print("fallback")
for m in sorted(claude.FALLBACK_MODELS):
    reset()
    QUEUE.append(msg())
    claude.ask(MSGS, model=m, door="net.research")
    kw = CALLS[0]
    check("fallback on %s" % m, kw.get("fallbacks") == "default"
          and "server-side-fallback-2026-07-01" in kw.get("betas", []), str(kw.keys()))
reset()
QUEUE.append(msg())
claude.ask(MSGS, model="claude-haiku-5-5", door="net.research")
check("no fallback on haiku", "fallbacks" not in CALLS[0] and "betas" not in CALLS[0], str(CALLS[0].keys()))

# ── request shape ─────────────────────────────────────────────────────────────────────
print("shape")
reset()
QUEUE.append(msg())
claude.ask(MSGS, model="claude-sonnet-5-5", door="net.research", effort="high", system="S",
           tools=[{"type": "web_search_20260209", "name": "web_search"}])
kw = CALLS[0]
check("no thinking param, no forced tool_choice", "thinking" not in kw and "tool_choice" not in kw)
check("effort set in output_config", kw.get("output_config") == {"effort": "high"}, str(kw.get("output_config")))
check("system + tools + max_tokens passed", kw.get("system") == "S" and kw.get("tools")
      and kw.get("max_tokens") == 16000, str(kw.keys()))
reset()
QUEUE.append(msg())
claude.ask(MSGS, model="claude-sonnet-5-5", door="net.research")
check("empty system / tools omitted", "system" not in CALLS[0] and "tools" not in CALLS[0])

# ── sources + usage ───────────────────────────────────────────────────────────────────
print("sources")
res = lambda u: NS(type="web_search_result", url=u, title="t")
err = NS(type="web_search_tool_result_error", error_code="unavailable")
content = [
    NS(type="web_search_tool_result", content=[res("http://a"), res("http://b")]),
    NS(type="web_search_tool_result", content=err),
    NS(type="text", text="x", citations=[NS(url="http://b"), NS(url="http://c")]),
    NS(type="text", text="y", citations=None),
]
reset()
QUEUE.append(msg(content=content))
r = claude.ask(MSGS, model="claude-opus-5-5", door="net.research")
check("sources de-duplicated, ordered", r.sources == ["http://a", "http://b", "http://c"], str(r.sources))
check("text blocks joined", r.text == "xy", repr(r.text))
check("usage carried", r.usage == {"input": 3, "output": 4, "cache_read": 1}, str(r.usage))
many = [NS(type="web_search_tool_result", content=[res("http://s%d" % i) for i in range(12)])]
reset()
QUEUE.append(msg(content=many))
r = claude.ask(MSGS, model="claude-opus-5-5", door="net.research")
check("sources capped at 8", len(r.sources) == 8, str(len(r.sources)))

# ── key never in last_error ───────────────────────────────────────────────────────────
print("key scrub")
reset()


def boom(key, base):
    raise RuntimeError("bad FILEKEY here")


claude._CLIENT_FACTORY = boom
r = claude.ask(MSGS, model="claude-opus-5-5", door="net.research")
check("factory error: ok=False, no raise", r.ok is False)
check("key never in last_error", "FILEKEY" not in claude.last_error() and claude.last_error() != "",
      claude.last_error())
claude._CLIENT_FACTORY = factory

# the key STRADDLING the truncation point must not survive as a fragment
LONGKEY = "FAKE-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
write_key(LONGKEY)
reset()


def boom2(key, base):
    raise RuntimeError("x" * 180 + key + " tail")


claude._CLIENT_FACTORY = boom2
claude.ask(MSGS, model="claude-opus-5-5", door="net.research")
le = claude.last_error()
frag = [LONGKEY[i:i + 8] for i in range(len(LONGKEY) - 7) if LONGKEY[i:i + 8] in le]
check("key straddling char 200 leaves no 8-char fragment in last_error", le != "" and not frag,
      "%r in %r" % (frag[:2], le[-80:]))
claude._CLIENT_FACTORY = factory

# ── the setup panel (Task 8): present/absent, never the value ───────────────────────────
import json as _json
PANELKEY = "sk-" + "ant-FAKE-PANEL-0123456789abcdefghij"   # split: the commit secret-guard reads source text
os.environ["SP_CLAUDE_API_KEY"] = PANELKEY
os.environ["SP_CLAUDE_KEY_FILE"] = MISSING
os.environ["SP_CONSULT"] = "1"
os.environ["SP_CONSULT_MODEL"] = "claude-opus-5-5"
os.environ["SP_RESEARCH_BACKEND"] = "claude"
os.environ["SP_SEARCH_BACKEND"] = "claude"
from harness.server import panels  # noqa: E402
setup = panels._setup_json()
blob = _json.dumps(setup)
cl = setup.get("claude") or {}
check("panel never carries the key", PANELKEY not in blob and PANELKEY[:12] not in blob
      and "FAKE-PANEL" not in blob)
check("panel reports the env key present", (cl.get("key") or {}).get("present") is True,
      repr(cl.get("key")))
check("panel reports the sdk bool", isinstance(cl.get("sdk"), bool), repr(cl.get("sdk")))
check("panel reports research/search/consult armed + model",
      all(isinstance((cl.get(k) or {}).get("armed"), bool) for k in ("research", "search", "consult"))
      and (cl.get("consult") or {}).get("model") == "claude-opus-5-5", repr(cl))

# armed is a positive control, not a type check: key + SDK + backend + the tool's own arming knob
_real_sdk = claude._sdk
claude._sdk = lambda: object()
_saved = {k: os.environ.get(k) for k in ("SP_RESEARCH", "SP_CONSULT")}


def _armed(which):
    return (panels._setup_json().get("claude") or {}).get(which, {}).get("armed")


os.environ["SP_RESEARCH"], os.environ["SP_CONSULT"] = "1", "1"
check("research armed: key + sdk + backend=claude + SP_RESEARCH=1", _armed("research") is True)
check("search armed: key + sdk + backend=claude", _armed("search") is True)
check("consult armed: key + sdk + SP_CONSULT=1", _armed("consult") is True)
os.environ["SP_RESEARCH"], os.environ["SP_CONSULT"] = "0", "0"
check("research NOT armed with SP_RESEARCH=0 (the tool is absent)", _armed("research") is False)
check("consult NOT armed with SP_CONSULT=0", _armed("consult") is False)
claude._sdk = lambda: None
os.environ["SP_RESEARCH"], os.environ["SP_CONSULT"] = "1", "1"
check("nothing armed without the sdk", not any(_armed(k) for k in ("research", "search", "consult")))
claude._sdk = lambda: object()
os.environ.pop("SP_CLAUDE_API_KEY", None)
check("nothing armed without a key", not any(_armed(k) for k in ("research", "search", "consult")))
claude._sdk = _real_sdk
for _k, _v in _saved.items():
    if _v is None:
        os.environ.pop(_k, None)
    else:
        os.environ[_k] = _v
os.environ.pop("SP_CLAUDE_API_KEY", None)
setup2 = panels._setup_json()
check("panel without any key reports absent", ((setup2.get("claude") or {}).get("key") or {}).get("present") is False,
      repr((setup2.get("claude") or {}).get("key")))

# ── final review 2026-10-21 (1): the install hint names the right package ────────────
print("packaging")
import ast  # noqa: E402
import re  # noqa: E402


def _code_only(src):
    """comments never survive ast; docstrings are blanked — the prose describing a change
    must not satisfy a gate about the change."""
    t = ast.parse(src)
    for n in ast.walk(t):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            b = n.body
            if b and isinstance(b[0], ast.Expr) and isinstance(getattr(b[0], "value", None), ast.Constant)                     and isinstance(b[0].value.value, str):
                b[0].value.value = ""
    return ast.unparse(t)


def _extra(path, name):
    import tomllib
    with open(path, "rb") as f:
        return (tomllib.load(f).get("project", {}).get("optional-dependencies", {}) or {}).get(name)


_src_x = _extra(os.path.join(ROOT, "pyproject.toml"), "claude")
_exp_x = _extra(os.path.join(ROOT, "kairos-export", "pyproject.toml"), "claude")
check("both pyprojects declare the same `claude` extra", _src_x is not None and _src_x == _exp_x,
      (_src_x, _exp_x))
check("the extra pins the verified floor anthropic>=1.15", _src_x == ["anthropic>=1.15"], _src_x)
_bad = []
for _top in ("ui/src", "docs", "kairos-export"):
    for _dp, _dn, _fn in os.walk(os.path.join(ROOT, _top)):
        _dn[:] = [d for d in _dn if d not in ("node_modules", "superpowers")]
        for _f in _fn:
            if _f.endswith((".jsx", ".js", ".md", ".py", ".toml", ".txt")):
                try:
                    if "kairos[claude]" in open(os.path.join(_dp, _f), encoding="utf-8", errors="replace").read():
                        _bad.append(os.path.relpath(os.path.join(_dp, _f), ROOT))
                except OSError:
                    pass
check("no file under ui/src, docs or kairos-export says kairos[claude] (not a package)", not _bad, _bad)
_fac_src = _code_only(open(os.path.join(ROOT, "harness", "skills", "claude.py"), encoding="utf-8").read())

# ── (2) ambient ANTHROPIC_* never reaches the wire ────────────────────────────────────
print("ambient ANTHROPIC_CUSTOM_HEADERS")
from _gate import have  # noqa: E402
if have("anthropic") and have("httpx2"):
    import anthropic as _an  # noqa: E402
    import httpx2 as _hx  # noqa: E402
    _REC: list = []

    def _handler(req):
        _REC.append(req)
        return _hx.Response(200, json={"id": "m", "type": "message", "role": "assistant", "model": "x",
                                       "content": [{"type": "text", "text": "hi"}], "stop_reason": "end_turn",
                                       "usage": {"input_tokens": 1, "output_tokens": 1}})

    _saved_env = {k: os.environ.get(k) for k in ("ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_BASE_URL")}
    os.environ["ANTHROPIC_CUSTOM_HEADERS"] = "X-Leak: 1"
    os.environ["ANTHROPIC_BASE_URL"] = "http://evil.example"
    _real_ctor = _an.Anthropic
    try:
        # the shipped factory builds the real SDK client; the recording transport is injected
        # by wrapping the constructor it calls (no network is ever opened).
        _an.Anthropic = lambda **kw: _real_ctor(http_client=_an.DefaultHttpxClient(
            transport=_hx.MockTransport(_handler)), **kw)
        _c = REAL_FACTORY("K", claude.BASE_URL)
        _c.messages.create(model="m", max_tokens=5, messages=[{"role": "user", "content": "q"}])
    finally:
        _an.Anthropic = _real_ctor
        for _k, _v in _saved_env.items():
            if _v is None:
                os.environ.pop(_k, None)
            else:
                os.environ[_k] = _v
    _hdr = {k.lower(): v for k, v in _REC[0].headers.items()} if _REC else {}
    check("a real SDK client sent the request", len(_REC) == 1, len(_REC))
    check("ambient ANTHROPIC_CUSTOM_HEADERS does not ride the request", "x-leak" not in _hdr, sorted(_hdr))
    check("ambient ANTHROPIC_BASE_URL does not redirect it: api.anthropic.com",
          _REC and _REC[0].url.host == "api.anthropic.com", _REC and str(_REC[0].url))
    check("the shell's value is restored after construction",
          os.environ.get("ANTHROPIC_CUSTOM_HEADERS") == _saved_env["ANTHROPIC_CUSTOM_HEADERS"])
else:
    print("  (skip) anthropic/httpx2 not installed — the real-SDK header leg needs the SDK")

# serve.py's env builder drops every ANTHROPIC_* from the gateway env (behavioural: the real
# build_env, the profile that exists to be loadable offline).
import importlib.util as _ilu  # noqa: E402
import io as _io  # noqa: E402
from contextlib import redirect_stdout as _redir  # noqa: E402
_sspec = _ilu.spec_from_file_location("serve_anthropic_door", os.path.join(ROOT, "serve.py"))
_serve = _ilu.module_from_spec(_sspec)
_sspec.loader.exec_module(_serve)
os.environ["ANTHROPIC_CUSTOM_HEADERS"] = "X-Leak: 1"
os.environ["ANTHROPIC_BASE_URL"] = "http://evil.example"
_bo = _io.StringIO()
try:
    with _redir(_bo):
        _genv = _serve.build_env(_serve.load_profile("companion"))
finally:
    os.environ.pop("ANTHROPIC_CUSTOM_HEADERS", None)
    os.environ.pop("ANTHROPIC_BASE_URL", None)
check("build_env drops every ANTHROPIC_* from the gateway env",
      not [k for k in _genv if k.startswith("ANTHROPIC_")], [k for k in _genv if k.startswith("ANTHROPIC_")])
check("...and announces the strip by name", "ANTHROPIC_CUSTOM_HEADERS" in _bo.getvalue()
      and "STRIPPED" in _bo.getvalue(), _bo.getvalue()[:200])

# ── (3) an absent SDK is silent ───────────────────────────────────────────────────────
print("absent sdk is silent")
import logging  # noqa: E402


class _Cap(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.recs = []

    def emit(self, rec):
        self.recs.append(rec)


_cap = _Cap()
logging.getLogger().addHandler(_cap)
_prev_mod = sys.modules.get("anthropic", "ABSENT")
sys.modules["anthropic"] = None                 # `import anthropic` -> ImportError, find_spec -> None
claude._SDK_MOD = None
claude._sdk = REAL_SDK_FN
try:
    _w = [claude.why_unavailable() for _ in range(3)] + [claude.available() for _ in range(3)]
finally:
    if _prev_mod == "ABSENT":
        sys.modules.pop("anthropic", None)
    else:
        sys.modules["anthropic"] = _prev_mod
    logging.getLogger().removeHandler(_cap)
    claude._SDK_MOD = None
check("absent SDK reports 'no sdk' (3 polls)", _w[:3] == ["no sdk"] * 3 and _w[3:] == [False] * 3, _w)
check("...and logs nothing at WARNING or above across the polls", not _cap.recs,
      [r.getMessage() for r in _cap.recs])


finish("G-CLAUDE")
