"""G-ROOM-KIT — the shared renderers draw through the kit (room redesign, stage 2).

THE SPEC: docs/superpowers/specs/2026-09-23-room-redesign-design.md §4-§5. The kit's parts
and the four shared renderers (apps/panel.jsx, apps/titleChips.jsx, apps/knobs.jsx,
apps/looks.jsx) are RENDERED — esbuild bundles the real source, react-dom/server draws it
under node — and the gate asserts on the markup. A gate that greps JSX passes on the
comment explaining the change; a rendered <span class="tc"> has nowhere to hide.

Legs, each shown red against a mutant before it was trusted (GATE-INDEX lists them):
  1. KIT PARTS — Chip tone / busy / warm; KV tones, including the 'good'/'bad' Setup has
     always passed and nothing ever styled; loading State is announced.
  2. PANEL — every panel's loading and error state is the kit's State; status rows are KV.
  3. TITLE CHIPS — every window's glance is a kit Chip; all eleven first-paint as Pending.
  4. TASKBAR CHIPS — looked up, in scene, off the record: kit Chips, rsc-chip retired.
  5. KNOBS — Settings, Voice and Search's engine box draw kit parts.
  6. LOOKS — the looking ledger: his gold, hers in her hue, one primary.
  7. RETIRED — no rendered markup and no stylesheet brings a retired chip class back.

Offline. Needs node and ui/node_modules (esbuild, react, react-dom); exit 2 without them.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, skip, utf8_stdout  # noqa: E402

utf8_stdout()
GATE = "G-ROOM-KIT"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NM = os.path.join(ROOT, "ui", "node_modules")

node = shutil.which("node")
if not node:
    skip("node is absent — the renderers cannot be drawn here", GATE)
if not all(os.path.isdir(os.path.join(NM, p)) for p in ("esbuild", "react", "react-dom")):
    skip("ui/node_modules lacks esbuild/react/react-dom — run `npm ci` in ui/", GATE)

# The banner runs before any bundled module. api.js only calls fetch inside functions,
# but a poll that fired would hang the probe — so here fetch never resolves.
# logLevel 'silent' + the catch (2026-09-26, task 1): buildSync THROWS an object whose
# dump is ~1.5 KB of stack and `errors: [...]` scaffolding, and the 600-char tail
# render() keeps landed in the middle of it. Printing only file:line and each error's
# text makes the FAIL line say which import failed.
# createRequire in the banner (same day): react-dom/server is CommonJS, and esbuild's ESM
# output replaces every require() it cannot hoist with a stub that throws — the first
# probe died with 'Dynamic require of "stream" is not supported' before drawing anything.
# Giving the module a real `require` keeps the output ESM (top-level await stays open to
# later legs) and lets react-dom load node's own stream/util.
BUNDLER = r"""
const [,, entry, out, nm] = process.argv
const BANNER = "import { createRequire as __cr } from 'module'; const require = __cr(import.meta.url);"
  + " globalThis.fetch = () => new Promise(() => {});"
try {
  require(nm + '/esbuild').buildSync({
    entryPoints: [entry], bundle: true, platform: 'node', format: 'esm',
    jsx: 'automatic', outfile: out, logLevel: 'silent', nodePaths: [nm],
    banner: { js: BANNER },
  })
} catch (e) {
  const errs = (e && e.errors) || []
  for (const x of errs) {
    const l = x.location
    process.stderr.write((l ? l.file + ':' + l.line + ': ' : '') + x.text + '\n')
  }
  if (!errs.length) process.stderr.write(String(e && e.stack || e) + '\n')
  process.exit(1)
}
"""
ALL_HTML: list = []


def render(body: str) -> dict:
    """Bundle `body` (JS that assigns `const out = {...}`) and run it. `html(el)` is
    renderToStaticMarkup, `h` is createElement. Bodies import '../ui/src/...' (as if
    from one level below the repo root); render() rewrites that to the real relative path
    from the temp dir. Never raises — a probe that could not run returns
    {"_error": ...}, which the leg reports as a FAIL, never a pass."""
    # The probe EXITS once its line is flushed (2026-09-26): a renderer that starts a
    # timer at import (a poll, an interval) would otherwise keep node alive until the
    # 60 s timeout, and one hung probe is a minute of the parallel sweep. The exit waits
    # on the write callback because a pipe is asynchronous on POSIX.
    src = ("import { renderToStaticMarkup as html } from 'react-dom/server'\n"
           "import { createElement as h } from 'react'\n"
           + body + "\nprocess.stdout.write(JSON.stringify(out) + '\\n', () => process.exit(0))\n")
    # THE TEMP DIR LIVES UNDER node_modules/.cache (stage-2 review, M1): under the repo
    # root, G-KAIROS-SCRUB's os.walk in ../Kairos met it mid-delete and went red on a
    # FileNotFoundError, and read the react-dom bundle inside it as shipped text. Every
    # walker prunes node_modules, and nothing ships from it.
    cache = os.path.join(NM, ".cache")
    os.makedirs(cache, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="_g_room_kit_", dir=cache)
    src = src.replace("'../ui/src/", "'" + os.path.relpath(os.path.join(ROOT, "ui", "src"), tmp).replace("\\", "/") + "/")
    try:
        entry, outf, bun = (os.path.join(tmp, n) for n in ("probe.jsx", "probe.mjs", "bundle.cjs"))
        with io.open(entry, "w", encoding="utf-8") as f:
            f.write(src)
        with io.open(bun, "w", encoding="utf-8") as f:
            f.write(BUNDLER)
        b = subprocess.run([node, bun, entry, outf, NM], capture_output=True, text=True, timeout=120,
                           encoding="utf-8", errors="replace")
        if b.returncode:
            return {"_error": "bundle: " + b.stderr[-600:]}
        # node writes UTF-8; without an explicit encoding Windows decodes it as cp1252 and
        # every "…" in a probed string arrives as mojibake (found by leg 3, 2026-09-26).
        r = subprocess.run([node, outf], capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace")
        if r.returncode:
            # node prints the thrown line and a caret FIRST and the stack after, so the
            # thrown error's own line is what names the fault; the tail is only frames.
            m = re.search(r"^\w*Error\b.*$", r.stderr, re.M)
            return {"_error": "run: " + (m.group(0) if m else r.stderr[:600])}
        d = json.loads(r.stdout.strip().splitlines()[-1])
        ALL_HTML.extend(v for v in d.values() if isinstance(v, str))
        return d
    except Exception as exc:
        return {"_error": "%s: %s" % (type(exc).__name__, exc)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def grab(d: dict, key: str) -> str:
    v = d.get(key, "")
    return v if isinstance(v, str) else ""


print("1. KIT PARTS — the shapes every renderer below draws through")
d = render(r"""
import { Chip, KV, State } from '../ui/src/kit/parts.jsx'
const out = {
  chip_ok: html(h(Chip, { tone: 'ok' }, 'on')),
  chip_busy: html(h(Chip, { tone: 'accent', busy: true }, 'looking')),
  chip_warm: html(h(Chip, { tone: 'warm' }, 'his')),
  kv_ok: html(h(KV, { k: 'sight', v: 'yes', tone: 'ok' })),
  kv_good: html(h(KV, { k: 'engine', v: 'up', tone: 'good' })),
  kv_bad: html(h(KV, { k: 'engine', v: 'down', tone: 'bad' })),
  kv_none: html(h(KV, { k: 'backend', v: 'xai', tone: '' })),
  kv_junk: html(h(KV, { k: 'x', v: 'y', tone: 'purple' })),
  loading: html(h(State, { kind: 'loading', title: 'Loading…' })),
}
""")
check("the kit probe rendered", "_error" not in d, d.get("_error", ""))
g = lambda k: grab(d, k)
check("a chip carries its tone", "ui-tone-ok" in g("chip_ok"))
check("a busy chip is marked busy and carries its dot",
      "ui-chip-busy" in g("chip_busy") and "ui-chip-dot" in g("chip_busy"))
check("his words have a warm tone", "ui-tone-warm" in g("chip_warm"))
check("a KV says its key and its value",
      'class="ui-kv"' in g("kv_ok") and ">sight<" in g("kv_ok") and ">yes<" in g("kv_ok"))
check("tone ok colours the value", "ui-kv-ok" in g("kv_ok"))
check("'good' — which Setup passes and nothing ever styled — reads as ok", "ui-kv-ok" in g("kv_good"))
check("'bad' reads as err", "ui-kv-err" in g("kv_bad"))
check("no tone, no tone class", 'class="ui-kv-v"' in g("kv_none"))
check("an unknown tone is dropped, never echoed into a class", "purple" not in g("kv_junk")
      and 'class="ui-kv-v"' in g("kv_junk"))
check("a loading state is announced, not only drawn", 'role="status"' in g("loading"))

print("\n2. PANEL — every panel's loading and error state is the kit's State")
d = render(r"""
import { Body, Row } from '../ui/src/apps/panel.jsx'
const kid = (x) => h('i', null, 'got ' + x)
const out = {
  loading: html(h(Body, { state: { loading: true } }, kid)),
  error: html(h(Body, { state: { loading: false, error: '/v1/memory 502' } }, kid)),
  data: html(h(Body, { state: { loading: false, data: 'rows' } }, kid)),
  row: html(h(Row, { k: 'warm', v: 'true', tone: 'ok' })),
  row_good: html(h(Row, { k: 'engine', v: 'reachable', tone: 'good' })),
}
""")
check("the panel probe rendered", "_error" not in d, d.get("_error", ""))
g = lambda k: grab(d, k)
check("loading draws the kit's loading state", "ui-state-loading" in g("loading"))
check("an error draws the kit's error state, as an alert",
      "ui-state-error" in g("error") and 'role="alert"' in g("error"))
check("the error says what failed, verbatim", "/v1/memory 502" in g("error"))
check("data renders the panel's own body, not a state",
      "got rows" in g("data") and "ui-state" not in g("data"))
check("a status row is the kit's KV", 'class="ui-kv"' in g("row") and "ui-kv-ok" in g("row"))
check("Setup's 'good' finally colours its row", "ui-kv-ok" in g("row_good"))

print("\n3. TITLE CHIPS — every window's glance is a kit Chip")
d = render(r"""
import * as T from '../ui/src/apps/titleChips.jsx'
const out = {
  on: T.Glance ? html(h(T.Glance, { state: 'on', title: 't' }, 'xai')) : 'NO GLANCE',
  off: T.Glance ? html(h(T.Glance, { state: 'off' }, 'muted')) : 'NO GLANCE',
  busy: T.Glance ? html(h(T.Glance, { state: 'busy' }, 'looking…')) : 'NO GLANCE',
  live: T.Glance ? html(h(T.Glance, { state: 'live' }, 'in a scene')) : 'NO GLANCE',
  empty: T.Glance ? html(h(T.Glance, { state: 'on' }, null)) : 'NO GLANCE',
  pending: T.Pending ? html(h(T.Pending)) : 'NO PENDING',
}
// Every chip, first paint: its poll has not answered, so each shows Pending.
const names = Object.keys(T).filter(n => /Chip$/.test(n))
out.n_chips = String(names.length)
for (const n of names) out['first_' + n] = html(h(T[n]))
""")
check("the title-chip probe rendered", "_error" not in d, d.get("_error", ""))
g = lambda k: grab(d, k)
check("on is ok", "ui-tone-ok" in g("on") and ">xai<" in g("on"))
check("off is neutral", "ui-tone-neutral" in g("off"))
check("busy is accent, and pulses", "ui-tone-accent" in g("busy") and "ui-chip-busy" in g("busy"))
check("live is accent with a STILL dot — it lasts, so it does not pulse (WCAG 2.2.2)",
      "ui-tone-accent" in g("live") and "ui-chip-dot" in g("live") and "ui-chip-busy" not in g("live"))
check("nothing to say renders nothing", g("empty") == "")
check("asking… is a quiet neutral chip", "ui-chip" in g("pending") and "…" in g("pending")
      and 'title="asking…"' in g("pending"))
n = int(d.get("n_chips", "0") or 0)
check("all eleven title chips were drawn", n >= 11, n)
firsts = {k: v for k, v in d.items() if k.startswith("first_")}
check("every chip's first paint is the kit's Pending",
      firsts and all("ui-chip" in v and 'class="tc' not in v for v in firsts.values()),
      sorted(k for k, v in firsts.items() if "ui-chip" not in v))


def _code(rel: str) -> str:
    """The source with its comments blanked: a gate that greps JSX passes on the comment
    explaining the change, so the comments go first."""
    t = io.open(os.path.join(ROOT, rel), encoding="utf-8").read()
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    return re.sub(r"(?<![:'\"])//[^\n]*", "", t)


def _fn(src: str, name: str) -> str:
    m = re.search(r"export function " + name + r"\b.*?(?=\nexport |\Z)", src, re.S)
    return m.group(0) if m else ""


# THE LONG-LIVED STATES ARE STILL (stage-2 review, M3). Their populated branch needs a poll
# that answers, which an effect-less server render never has (M6, stage 3), so this reads
# the comment-blanked source: which state each long-lived branch passes.
TCS = _code("ui/src/apps/titleChips.jsx")
_line = lambda needle: next((l for l in TCS.splitlines() if needle in l), "")
check("a scene, a reading and a wait for quiet say live, not busy",
      'state="live"' in _fn(TCS, "StageChip") and 'state="busy"' not in _fn(TCS, "StageChip")
      and 'state="live"' in _line(">reading ") and 'state="live"' in _line(">waiting for quiet<"),
      [_line(">reading "), _line(">waiting for quiet<")])
check("bounded work still pulses: looking… and making… say busy",
      'state="busy"' in _line(">looking…<") and 'state="busy"' in _line(">making…<"))

print("\n4. TASKBAR CHIPS — looked up, off the record: kit Chips, rsc-chip retired; the bar sheds them")
d = render(r"""
import * as TC from '../ui/src/room/TaskChips.jsx'
import { AnonChip } from '../ui/src/room/Anon.jsx'
const L = TC.LookingChip
const out = {
  looking: L ? html(h(L, { pulse: { research: { inflight: true, kind: 'search', query: 'tide times' } }, onOpen: () => {} })) : 'NO MODULE',
  looked: L ? html(h(L, { pulse: { research: { title: 'tide times' } }, onOpen: () => {} })) : 'NO MODULE',
  quiet: L ? html(h(L, { pulse: {}, onOpen: () => {} })) : 'NO MODULE',
  scene_first: TC.SceneChip ? html(h(TC.SceneChip)) : 'NO MODULE',
  anon_on: html(h(AnonChip, { anon: { on: true, for_s: 600, held_total: 3 } })),
  anon_off: html(h(AnonChip, { anon: { on: false } })),
}
""")
check("the taskbar probe rendered", "_error" not in d, d.get("_error", ""))
g = lambda k: grab(d, k)
check("a look in flight is an accent chip that pulses",
      "ui-tone-accent" in g("looking") and "ui-chip-busy" in g("looking"))
check("the chip opens research — it is a button", "<button" in g("looking"))
# THE BAR SHEDS GLANCES, NEVER CONTROLS (stage-2 review, I1): shell.css hides .tb-chip-q at
# <=1440px and a finished look (.tb-look without .tb-look-on) at <=1000px.
check("the query sits in .tb-chip-q, so a narrow bar can shed it",
      re.search(r'class="tb-chip-q">[^<]*tide times', g("looking")) is not None
      and re.search(r'class="tb-chip-q">[^<]*tide times', g("looked")) is not None)
check("a look in flight is wrapped in .tb-look.tb-look-on — it never sheds",
      g("looking").startswith('<span class="tb-look tb-look-on">'))
check("a finished look is wrapped in .tb-look without tb-look-on — it sheds at <=1000px",
      g("looked").startswith('<span class="tb-look">'))
check("it says what she is doing, verbatim", "looking up" in g("looking") and "tide times" in g("looking"))
check("a finished look stays, still, clickable",
      "looked up" in g("looked") and "ui-chip-busy" not in g("looked") and "<button" in g("looked"))
check("nothing looked up, no chip", g("quiet") == "")
check("no scene before the poll answers, no chip", g("scene_first") == "")
check("off the record is the an tone", "ui-tone-an" in g("anon_on") and "off the record" in g("anon_on"))
check("it carries the elapsed time and the tally", "10m" in g("anon_on") and "3 held" in g("anon_on"))
check("on the record, no chip", g("anon_off") == "")
SCN = _fn(_code("ui/src/room/TaskChips.jsx"), "SceneChip")
_scn_chip = re.search(r"<Chip\b[^>]*>", SCN, re.S)
check("in scene wears a still dot, not busy — a scene lasts hours (M3)",
      _scn_chip is not None and re.search(r"\bdot\b", _scn_chip.group(0)) is not None
      and not re.search(r"\bbusy\b", _scn_chip.group(0)), _scn_chip and _scn_chip.group(0))
check("in scene's words sit in .tb-chip-q too", 'className="tb-chip-q"' in SCN)
# ...and the stylesheet does the shedding, and never sheds a control. Every selector that a
# max-width block hides, comments blanked; the controls are off the record (.an-*), Shut
# down (.sd-*) and the scene's chip-and-exit (.tb-scene).
_shell = re.sub(r"/\*.*?\*/", "", io.open(os.path.join(ROOT, "ui/src/room/shell.css"), encoding="utf-8").read(), flags=re.S)
_shed = set()
for _mq in re.finditer(r"@media\s*\(max-width:\s*\d+px\)\s*\{(.*?)\}\s*\}", _shell, re.S):
    for _rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", _mq.group(1) + "}"):
        if re.search(r"display:\s*none", _rule.group(2)):
            _shed |= {x.strip() for x in _rule.group(1).split(",")}
check("a narrow bar sheds the query and a finished look (shell.css)",
      ".tb-chip-q" in _shed and ".tb-look:not(.tb-look-on)" in _shed, sorted(_shed))
_ctl = sorted(x for x in _shed if re.search(r"\.(an-btn|an-wrap|sd-btn|sd-wrap|sd-confirm|tb-scene)\b(?!\s+\S)", x))
check("no width sheds a control — off the record, Shut down, the scene's exit", not _ctl, _ctl)

print("\n5. KNOBS — Settings, Voice and Search's engine box draw kit parts")
d = render(r"""
import { KnobRow, TestVoice } from '../ui/src/apps/knobs.jsx'
import Voice from '../ui/src/apps/Voice.jsx'
const noop = () => {}
const live = { key: 'voice.enabled', label: 'Voice on', type: 'bool', value: true, scope: 'live', help: 'h' }
const prof = { key: 'engine.ctx', label: 'Context', type: 'enum', value: '8k', choices: ['8k', '16k'], scope: 'profile', help: 'h' }
const str = { key: 'presence.cue', label: 'Cue', type: 'str', value: 'x', scope: 'live', help: 'h' }
const num = { key: 'x.n', label: 'N', type: 'int', value: 3, scope: 'live', help: 'h',
              provenance: 'measured', receipt: 'r', overridden: true, engine: 'sp' }
const out = {
  live: html(h(KnobRow, { k: live, busy: '', onSet: noop })),
  prof: html(h(KnobRow, { k: prof, busy: '', onSet: noop })),
  num: html(h(KnobRow, { k: num, busy: '', onSet: noop })),
  str: html(h(KnobRow, { k: str, busy: '', onSet: noop })),
  test: html(h(TestVoice, { busy: '', setBusy: noop, setNote: noop })),
  voice: html(h(Voice)),
}
""")
check("the knobs probe rendered", "_error" not in d, d.get("_error", ""))
g = lambda k: grab(d, k)
check("a live knob wears an ok 'live' chip", "ui-tone-ok" in g("live") and ">live<" in g("live"))
check("a profile knob says 'restart to change' in warn",
      "ui-tone-warn" in g("prof") and "restart to change" in g("prof"))
check("a profile knob's control is a kit field, and read-only",
      "ui-field" in g("prof") and "disabled" in g("prof"))
# react-dom/server puts <!-- --> between adjacent text nodes: `{k.engine}-daemon only`
# renders as "sp<!-- -->-daemon only", so match the literal half.
check("measured, changed and daemon-only are chips",
      all(s in g("num") for s in ("ui-tone-accent", ">measured<", "ui-tone-mood", ">changed<", "-daemon only")))
check("a number knob is a kit field", 'type="number"' in g("num") and "ui-field" in g("num"))
check("a bool knob stays a native checkbox", 'type="checkbox"' in g("live"))
check("every knob's control is named by its label (M4)",
      'aria-label="Voice on"' in g("live") and 'aria-label="Context"' in g("prof")
      and 'aria-label="N"' in g("num") and 'aria-label="Cue"' in g("str"))
check("the voice test is a kit button, its words verbatim",
      "ui-btn" in g("test") and "test her voice" in g("test"))
check("the Voice window's status is kit chips", "ui-chip" in g("voice") and "voice on" in g("voice"))
check("no st-chip or vc-chip is drawn",
      not any(c in g(k) for k in ("live", "prof", "num", "voice") for c in ('st-chip', 'vc-chip')))

print("\n6. LOOKS — the looking ledger: his gold, hers in her hue, one primary")
d = render(r"""
import { ByChip, LookRows, AskRow } from '../ui/src/apps/looks.jsx'
import Search from '../ui/src/apps/Search.jsx'
import Research from '../ui/src/apps/Research.jsx'
const rows = [{ receipt: 'a', by: 'her', kind: 'search', title: 'tide times', ok: false, ended: 1 }]
const out = {
  him: html(h(ByChip, { by: 'him' })),
  hers: html(h(ByChip, { by: 'her' })),
  empty: html(h(LookRows, { rows: [], empty: 'nothing researched yet — a title appears here' })),
  rows: html(h(LookRows, { rows })),
  ask: html(h(AskRow, { placeholder: 'search the web yourself', busyLabel: 'searching…', run: async () => ({}) })),
  search: html(h(Search)),
  research: html(h(Research)),
}
""")
check("the looks probe rendered", "_error" not in d, d.get("_error", ""))
g = lambda k: grab(d, k)
check("his is warm — his words are gold", "ui-tone-warm" in g("him") and ">his<" in g("him"))
check("hers is in her hue", "ui-tone-mood" in g("hers") and ">hers<" in g("hers"))
check("an empty ledger is the kit's empty state, its sentence verbatim",
      "ui-state-empty" in g("empty") and "nothing researched yet — a title appears here" in g("empty"))
check("a failed look says so in err", "ui-tone-err" in g("rows") and ">failed<" in g("rows"))
check("the row still carries whose it is", "ui-tone-mood" in g("rows"))
check("his box is a kit field and the one primary button",
      "ui-field" in g("ask") and g("ask").count("ui-btn-primary") == 1)
check("go is disabled until he types", "disabled" in g("ask"))
check("his box is named by its placeholder (M4)", 'aria-label="search the web yourself"' in g("ask"))
check("Search and Research draw (their polls unanswered: the kit's loading state)",
      "ui-state-loading" in g("search") and "ui-state-loading" in g("research"))
check("no rsc-by, rsc-go or rsc-ok is drawn",
      not any(c in g(k) for k in ("him", "hers", "rows", "ask") for c in ("rsc-by", "rsc-go", "rsc-ok")))

print("\n7. RETIRED — no rendered markup and no stylesheet brings a retired chip class back")
RETIRED = {"tc", "tc-on", "tc-off", "tc-busy", "st-chip", "st-live", "st-prof", "st-meas", "st-ovr",
           "st-eng", "st-empty", "st-note", "st-test", "rsc-by", "rsc-him", "rsc-hers", "rsc-chip",
           "rsc-arm", "rsc-off", "rsc-now", "rsc-ok", "rsc-go", "an-chip", "an-held", "scn", "scn-b",
           "vc-chip", "vc-on", "vc-off", "sr-eng", "row"}
drawn = set()
for s in ALL_HTML:
    for cls in re.findall(r'class="([^"]*)"', s):
        drawn |= set(cls.split()) & RETIRED
check("the legs above rendered something to look through", len(ALL_HTML) >= 40, len(ALL_HTML))
check("no retired class is drawn by any renderer or window above", not drawn, sorted(drawn))
written = []
for rel in ("ui/src/room.css", "ui/src/room/shell.css", "ui/src/kit/kit.css"):
    css = re.sub(r"/\*.*?\*/", "", io.open(os.path.join(ROOT, rel), encoding="utf-8").read(), flags=re.S)
    for c in sorted(RETIRED):
        if re.search(r"\." + re.escape(c) + r"(?![\w-])", css):
            written.append((rel, c))
check("no stylesheet still styles a retired class", not written, written)

finish(GATE)
