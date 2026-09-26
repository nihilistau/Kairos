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
  8-10. (stage 3) TOP BAR, MINIMISE, APPS — see GATE-INDEX; the stage-3 fix wave added
     the desktop-local clamps, the stack light as a disclosure, the presence note's fade,
     restore's own keyframe, the kit's scrolling Tabs, wrapping state chips, and phone-
     width windows that fill the desktop.
  11. (stage 4) APPS — Files, House, Decisions, Her own time, Music, Stage, Setup, Story:
     each window's pure view rendered with fixtures; kit parts, words verbatim; closes
     with a scan that no stage-4 render draws, and room.css no longer styles, a class the
     stage retired.

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


def _code(rel: str) -> str:
    """The source with its comments blanked: a gate that greps JSX passes on the comment
    explaining the change, so the comments go first."""
    t = io.open(os.path.join(ROOT, rel), encoding="utf-8").read()
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    return re.sub(r"(?<![:'\"])//[^\n]*", "", t)


def grab(d: dict, key: str) -> str:
    v = d.get(key, "")
    return v if isinstance(v, str) else ""


print("1. KIT PARTS — the shapes every renderer below draws through")
d = render(r"""
import { Chip, KV, State, Tabs } from '../ui/src/kit/parts.jsx'
const two = [{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }]
const out = {
  chip_ok: html(h(Chip, { tone: 'ok' }, 'on')),
  chip_wrap: html(h(Chip, { tone: 'warn', dot: true, wrap: true }, 'due — waiting for quiet (his turn)')),
  tabs_named: html(h(Tabs, { tabs: two, value: 'b', label: 'filter by risk', onChange: () => {} })),
  tabs_gone: html(h(Tabs, { tabs: two, value: 'vanished', onChange: () => {} })),
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
# STAGE-3 FIX WAVE (final review M6, M7, Q3)
check("a state-line chip can wrap, its words verbatim (M6)",
      "ui-chip-wrap" in g("chip_wrap") and "due — waiting for quiet (his turn)" in g("chip_wrap")
      and "ui-chip-wrap" not in g("chip_ok"))
check("Tabs names its list (M7)", 'role="tablist" aria-label="filter by risk"' in g("tabs_named"))
check("a selected id that vanished still leaves one tab in the tab order (M7)",
      g("tabs_gone").count('tabindex="0"') == 1, g("tabs_gone"))
_kit_css = re.sub(r"/\*.*?\*/", "", io.open(os.path.join(ROOT, "ui/src/kit/kit.css"), encoding="utf-8").read(), flags=re.S)
_tabs_rule = re.search(r"\.ui-tabs\s*\{([^}]*)\}", _kit_css)
# SELECTION FOLLOWS THE SAME CLAMP (stage-4 review): a strip whose value vanished (a kind
# whose count fell to 0 on a later poll) kept its tab order but showed NO selected tab.
_gone_sel = re.findall(r'<button[^>]*aria-selected="true"[^>]*>([^<]*)<', g("tabs_gone"))
check("a selected id that vanished still leaves exactly one tab selected — the first",
      _gone_sel == ["A"] and g("tabs_gone").count("ui-tab-on") == 1, _gone_sel)
_pressed = re.search(r'\.ui-btn\[aria-pressed="true"\]\s*\{([^}]*)\}', _kit_css)
check("a pressed kit button looks pressed — kit.css styles .ui-btn[aria-pressed=\"true\"]",
      _pressed is not None and "box-shadow" in _pressed.group(1), _pressed and _pressed.group(1))
# THE RING SURVIVES PRESSING (stage-4 final review, I1): the pressed rule ties
# .ui-btn:focus-visible on specificity and comes later, so its box-shadow replaced the focus
# ring — a keyboard-focused pressed toggle (Decisions, Presence) showed only its underline.


def _shadows(rule_body):
    m = re.search(r"box-shadow\s*:\s*([^;}]+)", rule_body or "")
    parts, depth, cur = [], 0, ""
    for ch in (m.group(1) if m else ""):
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [re.sub(r"\s+", " ", p).strip() for p in parts if p.strip()]


_ring = re.search(r"\.ui-btn:focus-visible\s*\{([^}]*)\}", _kit_css)
_pfocus = re.search(r'\.ui-btn\[aria-pressed="true"\]:focus-visible\s*\{([^}]*)\}', _kit_css)
_want = (_shadows(_ring.group(1)) if _ring else []) + (_shadows(_pressed.group(1)) if _pressed else [])
check("a focused pressed button wears the focus ring AND its underline (I1, WCAG 2.4.7)",
      _pfocus is not None and len(_want) >= 3 and all(w in _shadows(_pfocus.group(1)) for w in _want),
      [_want, _pfocus and _shadows(_pfocus.group(1))])
_ghover = re.search(r'\.ui-btn-ghost\[aria-pressed="true"\]:hover:not\(:disabled\)\s*\{([^}]*)\}', _kit_css)
check("a pressed ghost keeps its border under the pointer (the ghost hover blanks it)",
      _ghover is not None and "var(--hair-strong)" in _ghover.group(1), _ghover and _ghover.group(1))
check("the kit's tab strip scrolls sideways when it outruns its box (Q3)",
      _tabs_rule is not None and re.search(r"overflow-x:\s*auto", _tabs_rule.group(1)) is not None,
      _tabs_rule and _tabs_rule.group(1))
_room_css = re.sub(r"/\*.*?\*/", "", io.open(os.path.join(ROOT, "ui/src/room.css"), encoding="utf-8").read(), flags=re.S)
check("no app keeps its own tab-strip wrapper (Q3: .tl-tabs is gone)", ".tl-tabs" not in _room_css
      and "tl-tabs" not in _code("ui/src/apps/Tools.jsx"))

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
// The music chip's label, over the state the server really sends: track is an OBJECT.
const ml = (st) => { try { return T.musicLabel ? String(T.musicLabel(st)) : 'NO HELPER' } catch (e) { return 'THREW: ' + e.message } }
out.ml_server = ml({ playing: true, track: { path: 'b.mp3', title: 'Rain', artist: 'Ola' } })
out.ml_string = ml({ playing: true, track: 'Tides' })
out.ml_title = ml({ playing: true, title: 'Shore', track: null })
out.ml_none = ml({ playing: true })
out.ml_long = ml({ playing: true, track: { title: 'a'.repeat(40) } })
out.ml_untitled = ml({ playing: true, track: { path: 'c.mp3' } })
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
# THE MUSIC CHIP READ THE TRACK AS A STRING (stage 4, 3/6). The server sends track as an
# object ({path, title, artist, album}), so `.slice` on it threw while music played, and the
# title bar sits outside the window's error boundary: the whole room went black.
check("the music chip names the track the server sends (an object), not a throw",
      d.get("ml_server") == "Rain", d.get("ml_server"))
check("...a string track is itself, a top-level title is used, neither says 'playing'",
      d.get("ml_string") == "Tides" and d.get("ml_title") == "Shore" and d.get("ml_none") == "playing"
      and d.get("ml_untitled") == "playing",
      [d.get(k) for k in ("ml_string", "ml_title", "ml_none", "ml_untitled")])
check("...still cut to 24", d.get("ml_long") == "a" * 24, d.get("ml_long"))



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
check("the music chip speaks through musicLabel, not its own copy of the expression",
      "musicLabel(st)" in _fn(TCS, "MusicChip") and ".slice" not in _fn(TCS, "MusicChip"))

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

print("\n8. TOP BAR — her, her day, the machine (spec §8)")
d = render(r"""
import { TopBarView } from '../ui/src/room/TopBar.jsx'
import { upFor, dayFacts } from '../ui/src/room/facts.js'
const pulse = {
  her: { voice: 'soft' },
  clock: { boundary_hour: 4, consolidated_today: true, next_boundary_in_s: 55000 },
  presence: { warm: true, since_last_turn_s: 2760, ambient_enabled: true, ambient_next_in_s: 720 },
  backup: { next_in_s: 2280 },
  stack: { started_at: 1790378000, up_s: 12240 },
}
const mood = { word: 'wistful', known: true, thinking: false }
const sys = { profile: 'companion', restartable: true }
const out = {
  full: html(h(TopBarView, { pulse, mood, health: { ok: true, warm: true }, system: sys, refresh: () => {} })),
  thinking: html(h(TopBarView, { pulse, mood: { ...mood, thinking: true }, health: { ok: true, warm: true }, system: sys })),
  down: html(h(TopBarView, { pulse: {}, mood, health: null, healthError: 'refused', system: null })),
  up_5m: upFor(300), up_3h: upFor(12240), up_1d: upFor(90000), up_90m: upFor(5400),
  facts: JSON.stringify(dayFacts(pulse)),
  soon: JSON.stringify(dayFacts({ presence: { ambient_enabled: true, ambient_next_in_s: null } })),
}
""")
check("the top-bar probe rendered", "_error" not in d, d.get("_error", ""))
g = lambda k: grab(d, k)
check("her mood is named, as a status", ">wistful<" in g("full") and 'role="status"' in g("full")
      and 'aria-label="her mood: wistful"' in g("full"))
check("while she generates it says so", "thinking" in g("thinking") and "ui-orb-think" in g("thinking"))
check("her day: when he spoke, and whether her day has closed",
      "46m ago" in g("full") and "closed" in g("full"))
check("the eye's next look shows when the eye is on", "12m" in g("full"))
check("the machine: the starting profile as a kit chip", "ui-chip" in g("full") and ">companion<" in g("full"))
check("the machine: uptime", "3h 24m" in g("full"))
check("the machine: the next backup", "38m" in g("full"))
# A DISCLOSURE, NOT A MENU (final review, I2): role=menu promised arrow keys and typeahead
# it never had. The light that can open says so; the inert one says nothing.
check("the stack light is a disclosure button, shut: aria-expanded + aria-controls, no menu roles",
      'aria-expanded="false"' in g("full") and "aria-controls=" in g("full") and ">warm<" in g("full")
      and "aria-haspopup" not in g("full") and 'role="menu' not in g("full"))
check("an inert light announces nothing — no aria-expanded when it cannot open (I2)",
      "aria-expanded" not in g("down") and "aria-controls" not in g("down"), g("down")[-400:])
check("the menu is shut until asked — no restart button is drawn on first paint",
      "yes, restart" not in g("full") and ">bounce<" not in g("full"))
_SL = _code("ui/src/room/StackLight.jsx")
check("the panel is a named group, and nothing in it is a menuitem (I2)",
      re.search(r'role="group"\s+aria-label="restart the stack"', _SL) is not None
      and "menuitem" not in _SL and 'role="menu"' not in _SL)
check("Escape hands focus back to the light (I2)",
      re.search(r"'Escape'\)\s*\{[^}]*light\.current\.focus\(\)", _SL) is not None)
check("a finished action hands focus back to the light (I2)",
      re.search(r"async function go\(op\)\s*\{[^}]*?light\.current\.focus\(\)", _SL) is not None)
# each <Button …>word</Button> of the panel, by its word (an onClick's `=>` defeats [^>]*)
_btns = {seg.split("</Button>")[0].rsplit(">", 1)[-1]: seg.split("</Button>")[0]
         for seg in _SL.split("<Button")[1:]}
check("entering the confirm focuses 'no', the safe default (I2)",
      "autoFocus" in _btns.get("no", "") and "autoFocus" not in _btns.get("yes, restart", "x autoFocus"),
      sorted(_btns))
# autoFocus fires only on MOUNT: two bare fragments reconciled by position, "restart"
# reused the "yes, restart" node, and after "no" focus fell to the page (found live).
check("each panel state mounts its own buttons — keyed fragments, so autoFocus runs (I2)",
      re.search(r'<Fragment key="ask">', _SL) is not None and re.search(r'<Fragment key="acts">', _SL) is not None
      and "autoFocus={back}" in _btns.get("restart", ""))
check("it closes if the stack stops being restartable while open (M9)",
      re.search(r"if \(open && !canRestart\)\s*shut\(\)", _SL) is not None)
check("only a light that can open wears the hover border (I2)",
      re.search(r"\.top-light:hover", _shell) is None
      and re.search(r"\.top-light\[aria-expanded\]:hover", _shell) is not None)
check("a dead gateway says so, in words and in the light",
      "gateway unreachable" in g("down") and "led off" in g("down"))
check("no pulse, no uptime and no invented facts",
      'class="top-up"' not in g("down") and 'class="top-bk"' not in g("down") and 'class="top-fact"' not in g("down"))
_ups = (d.get("up_5m"), d.get("up_3h"), d.get("up_1d"), d.get("up_90m"))
check("upFor reads like a person: 5m / 3h 24m / 1d 1h / 1h 30m",
      _ups == ("5m", "3h 24m", "1d 1h", "1h 30m"), _ups)
_f = json.loads(d.get("facts") or "[]")
check("dayFacts is the one owner of the day's words (3 facts from this pulse)",
      [x.get("k") for x in _f] == ["you spoke", "her day", "next look"], _f)
# HER DAY'S WORDS ARE CLOCK'S, VERBATIM (fix round 1): the first cut of facts.js rewrote
# them ("closed · she wrote", "in 12m", "a moment") and every check above stayed green.
check("her day's words are Clock's own: 'closed — she has written'",
      "closed — she has written" in g("full"), g("full")[:300])
check("the eye's next look reads '12m', no 'in ' prefix",
      [x.get("v") for x in _f if x.get("k") == "next look"] == ["12m"], _f)
_s = json.loads(d.get("soon") or "[]")
check("an eye with no time yet says 'soon'",
      [x.get("v") for x in _s if x.get("k") == "next look"] == ["soon"], _s)
# the top bar sheds glances, never the pill or the light (spec §8). _shed and _shell are
# leg 4's: every selector a max-width block hides, comments blanked.
_top_ctl = sorted(x for x in _shed if re.search(r"\.(top-mood|top-light|top-light-wrap)\b(?!-)", x))
check("no width hides her mood or the stack light", not _top_ctl, _top_ctl)
# the WHOLE day, as a selector of its own: `.top-day .top-fact + .top-fact` (the 1280px
# rule) contains ".top-day" too, and a substring test passed with the day never hidden.
check("a narrow top bar sheds her day first", ".top-day" in _shed, sorted(_shed))
_css_top = re.search(r"\.desktop\s*\{[^}]*inset:\s*var\(--top-h\)", _shell)
check("the desktop starts below the top bar", _css_top is not None)
# HER VOICE WORD AND THE NEXT BACKUP LEAVE TOGETHER (spec §8; final review, M8): which
# max-width block hides each, comments blanked.
_shed_at = {}
for _mq in re.finditer(r"@media\s*\(max-width:\s*(\d+)px\)\s*\{(.*?)\}\s*\}", _shell, re.S):
    for _rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", _mq.group(2) + "}"):
        if re.search(r"display:\s*none", _rule.group(2)):
            for _x in _rule.group(1).split(","):
                _shed_at.setdefault(_x.strip(), set()).add(int(_mq.group(1)))
check("her voice word sheds with the backup, at one width (M8)",
      _shed_at.get(".topbar .her-state") == _shed_at.get(".top-bk") == {1024},
      (_shed_at.get(".topbar .her-state"), _shed_at.get(".top-bk")))
# THE CLAMPS ARE THE DESKTOP'S (final review, I1). The Portrait and the icons live in
# .desktop, which now starts below a top bar: `innerHeight - 70` (the portrait's reach
# floor) and `innerHeight - ICON_H - 46` (the taskbar) were window arithmetic, and put her
# fully under the taskbar. No `innerHeight - …` may remain; both measure a clientHeight.
_clamp_bad = [rel for rel in ("ui/src/room/Portrait.jsx", "ui/src/room/DeskIcons.jsx")
              if re.search(r"innerHeight\b(?:\s*\|\|\s*\d+\s*\))?\s*-", _code(rel))]
check("no clamp subtracts a bar height from innerHeight (I1)", not _clamp_bad, _clamp_bad)
check("the Portrait and the icons clamp against the desktop's own height (I1)",
      all("clientHeight" in _code(rel) for rel in ("ui/src/room/Portrait.jsx", "ui/src/room/DeskIcons.jsx")))
check("a drag cannot drop her out of reach — the move clamps to maxY too (I1)",
      re.search(r"Math\.min\(d\.maxY", _code("ui/src/room/Portrait.jsx")) is not None)
# THE PRESENCE NOTE FADES (final review, Q1): its 14 s timer lived in the effect keyed to
# the pulse, whose cleanup ran every beat, so it never fired. The effect that sets the
# fade must be keyed to the note, never to the pulse.
_PR = _code("ui/src/room/Presence.jsx")
_fx = [m.group(0) for m in re.finditer(r"useEffect\(\(\) => \{.*?\n  \}, \[[^\]]*\]\)", _PR, re.S)]
_fade = [x for x in _fx if "setNote(null)" in x]
check("the presence note's fade is keyed to the note, not the pulse (Q1)",
      len(_fade) == 1 and re.search(r"\}, \[noteId\]\)$", _fade[0]) is not None
      and "setTimeout" in _fade[0], _fade)

print("\n9. MINIMISE — a flag and a timer; the shell draws the flight (spec §8)")
d = render(r"""
import * as wm from '../ui/src/windowManager.js'
const pick = (id) => { const w = wm.getWindows().find(x => x.appId === id); return w ? { minimizing: !!w.minimizing, minimized: !!w.minimized, restoredAt: w.restoredAt || 0 } : null }
const wait = (ms) => new Promise(r => setTimeout(r, ms))
wm.open('a'); wm.minimize('a')
const during = pick('a')
await wait(260)
const after = pick('a')
wm.open('a')
const restored = pick('a')
wm.minimize('a'); wm.open('a'); await wait(260)
const cancelled = pick('a')
wm.minimize('a', { delay: 0 })
const instant = pick('a')
wm.open('b'); wm.minimize('b'); wm.close('b'); await wait(260)
const closed = pick('b')
// a cancelled flight's timer must die with it: minimise, cancel, minimise again — the
// first timer (due at 400) must not cut the second flight (due at ~600) short.
wm.open('c'); wm.minimize('c', { delay: 400 }); await wait(200)
wm.open('c'); wm.minimize('c', { delay: 400 }); await wait(300)
const reflown = pick('c')
// a maximise mid-flight cancels the minimise (M1): its timer must not fire afterwards
wm.open('m'); wm.minimize('m'); wm.maximize('m'); await wait(260)
const maxed = pick('m')
// ...and its timer dies with it: the flight's own `minimizing` guard hides a live timer in
// the case above (mutant: stopTimer out of maximize stayed green), so fly again — the
// first timer (due at 400) must not cut the second flight (due at ~600) short.
wm.open('n'); wm.minimize('n', { delay: 400 }); await wait(200)
wm.maximize('n'); wm.minimize('n', { delay: 400 }); await wait(300)
const maxReflown = pick('n')
const out = {
  during: JSON.stringify(during), after: JSON.stringify(after), restored: JSON.stringify(restored),
  cancelled: JSON.stringify(cancelled), instant: JSON.stringify(instant), closed: JSON.stringify(closed),
  reflown: JSON.stringify(reflown), maxed: JSON.stringify(maxed), max_reflown: JSON.stringify(maxReflown),
  min_ms: String(wm.MIN_MS),
}
""")
check("the minimise probe ran", "_error" not in d, d.get("_error", ""))
J = lambda k: json.loads(d.get(k) or "null")
check("minimising first: the window is still on the page, marked minimizing",
      J("during") == {"minimizing": True, "minimized": False, "restoredAt": 0}, J("during"))
check("then minimised, after the flight", (J("after") or {}).get("minimized") is True
      and (J("after") or {}).get("minimizing") is False, J("after"))
check("restoring stamps restoredAt, so the shell can fly it back",
      (J("restored") or {}).get("minimized") is False and (J("restored") or {}).get("restoredAt", 0) > 0, J("restored"))
check("opening it mid-flight cancels the minimise — it stays shown",
      (J("cancelled") or {}).get("minimized") is False and (J("cancelled") or {}).get("minimizing") is False, J("cancelled"))
check("delay 0 (reduced motion) minimises at once", (J("instant") or {}).get("minimized") is True
      and (J("instant") or {}).get("minimizing") is False, J("instant"))
check("closing mid-flight leaves nothing behind", J("closed") is None, J("closed"))
check("a cancelled flight's timer is stopped, so a second minimise flies its full length",
      (J("reflown") or {}).get("minimizing") is True and (J("reflown") or {}).get("minimized") is False, J("reflown"))
check("a maximise mid-flight cancels the minimise — the window stays up (M1)",
      J("maxed") == {"minimizing": False, "minimized": False, "restoredAt": 0}, J("maxed"))
check("...and its timer is stopped, so a minimise after the maximise flies its full length (M1)",
      (J("max_reflown") or {}).get("minimizing") is True and (J("max_reflown") or {}).get("minimized") is False,
      J("max_reflown"))
check("the flight is --dur-base long (200ms)", d.get("min_ms") == "200", d.get("min_ms"))
# THE SHELL'S HALF, read from source with comments blanked (a probe of the store cannot
# see a call site that forgot the delay, and reduced motion would fly anyway).
_main = re.sub(r"/\*.*?\*/|//[^\n]*", "", io.open(os.path.join(ROOT, "ui/src/main.jsx"), encoding="utf-8").read(), flags=re.S)
_mins = re.findall(r"wm\.minimize\((\w[\w.]*(?:\s*,\s*\{[^}]*\})?)\)", _main)
_mins_all = _main.count("wm.minimize(")
check("every minimise call site passes the reduced-motion delay",
      _mins and len(_mins) == _mins_all and all("delay: minDelay()" in x for x in _mins), _mins)
check("taskbar buttons carry data-app, so a window can find its button",
      re.search(r"className=\{'tb-win'[^>]*data-app=\{w\.appId\}", _main, re.S) is not None)
# A TITLE CHIP IS INSIDE A BOUNDARY (stage-4 final review, M1): chips mount in the bar,
# outside the body's PanelBoundary, so any throwing chip blanked the whole room.
_tc_all = _main.count("<app.TitleChip")
_tc_held = re.findall(r"<(ChipBoundary|PanelBoundary)\b[^>]*>\s*<app\.TitleChip\s*/>\s*</\1>", _main)
_cb = re.search(r"class ChipBoundary extends React\.Component\s*\{(.*?)\n\}", _main, re.S)
check("every title chip renders inside an error boundary (M1)",
      _tc_all >= 1 and len(_tc_held) == _tc_all
      and (_tc_held[0] == "PanelBoundary" or (_cb is not None and "getDerivedStateFromError" in _cb.group(1))),
      [_tc_all, _tc_held])
_rm = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{(.*?)\n\}", _shell, re.S)
_foc = re.search(r"const focusedId = windows\.filter\(([^)]*)\)", _main)
check("a window in its minimise flight is not the focused one (M2)",
      _foc is not None and "!w.minimized" in _foc.group(1) and "!w.minimizing" in _foc.group(1),
      _foc and _foc.group(1))
# RESTORE HAS ITS OWN KEYFRAME (final review, Q2): `win-min` reversed also reversed its
# easing, so the window crept out of the button; and the end handler matched only win-min.
_rst = re.search(r"\.win\.win-restore\s*\{([^}]*)\}", _shell)
check("restore plays win-restore forwards, not win-min reversed (Q2)",
      _rst is not None and "win-restore" in _rst.group(1) and "reverse" not in _rst.group(1)
      and re.search(r"@keyframes win-restore\s*\{\s*from\s*\{[^}]*scale\(\.12\)", _shell) is not None,
      _rst and _rst.group(1))
check("the restore class comes off at win-restore's end, and on a cancelled animation (Q2)",
      "e.animationName === 'win-restore'" in _main and "onAnimationCancel=" in _main)
check("reduced motion turns the flight off", _rm is not None
      and re.search(r"\.win\.win-min-out\b[^{}]*\.win\.win-restore\b[^{]*\{\s*animation:\s*none", _rm.group(1)) is not None)

print("\n10. APPS — the seven stage-3 windows draw kit parts (views rendered with fixtures)")
d = render(r"""
import Apps from '../ui/src/apps/Apps.jsx'
import * as L from '../ui/src/apps/Librarians.jsx'
import * as S from '../ui/src/apps/Senses.jsx'
const aux = { armed: true, embed_up: true, chat_up: false, chunks: 812, files: 40, chat_model: 'lfm2', query_prefix: 'q', doc_prefix: '' }
const sen = { capability: { model: 'gemma', hidden_size: 2816, sight: true, hearing: false, why_no_hearing: 'no mic' },
              eyes: { backend: 'engine' }, ambient: { enabled: false, interval_s: 3600, next_in_s: null }, capture: { backends: { cam: true } } }
const out = {
  apps: html(h(Apps)),
  lib: L.LibrariansView ? html(h(L.LibrariansView, { d: aux, onRebuild: () => {} })) : 'NO VIEW',
  lib_off: L.LibrariansView ? html(h(L.LibrariansView, { d: { armed: false }, onRebuild: () => {} })) : 'NO VIEW',
  sen: S.SensesView ? html(h(S.SensesView, { d: sen })) : 'NO VIEW',
  voice: S.VoiceView ? html(h(S.VoiceView, { d: { backend: 'local', warm: true, cached: 9, live: {} } })) : 'NO VIEW',
}
""")
check("the apps probe rendered (5-7)", "_error" not in d, d.get("_error", ""))
g = lambda k: grab(d, k)
check("Apps says desktop, not dock — the dock is gone", "desktop" in g("apps") and "dock" not in g("apps"))
check("Apps' checkboxes are named by their app", g("apps").count('aria-label="') >= 20)
check("Librarians' state is a kit chip — warn while one door is dark",
      "ui-tone-warn" in g("lib") and "armed" in g("lib"))
check("Librarians off is a quiet chip, its words verbatim",
      "ui-tone-neutral" in g("lib_off") and "SP_AUX is off in the profile" in g("lib_off"))
check("rebuild index is a kit button", "ui-btn" in g("lib") and "rebuild index" in g("lib"))
check("Librarians' state lines are wrapping chips — sentences, not clipped (M6)",
      "ui-chip-wrap" in g("lib") and "ui-chip-wrap" in g("lib_off"))
check("Senses' rows are KV", 'class="ui-kv"' in g("sen") and ">gemma<" in g("sen"))
check("her voice's rows are KV", 'class="ui-kv"' in g("voice") and "ui-kv-ok" in g("voice"))

d = render(r"""
import * as R from '../ui/src/apps/Room.jsx'
import * as P from '../ui/src/apps/Presence.jsx'
import * as J from '../ui/src/apps/Journal.jsx'
const noop = () => Promise.resolve()
const out = {
  room_off: R.RoomView ? html(h(R.RoomView, { d: { ambient: { enabled: false }, ambient_recent: [] } })) : 'NO VIEW',
  room_on: R.RoomView ? html(h(R.RoomView, { d: { ambient: { enabled: true, next_in_s: 600 }, ambient_recent: [{ iso: '2026-09-26T10:00:00', seen: 'the lamp is on' }] } })) : 'NO VIEW',
  prs: P.PresenceView ? html(h(P.PresenceView, { d: { state: { mode: 'company', next_in_s: 300 }, shelf: [{ title: 'Dune', pos: 50, chars: 100, in_hand: true }] }, onEnter: noop, onLeave: noop, onPickUp: noop, onPutDown: noop })) : 'NO VIEW',
  prs_empty: P.PresenceView ? html(h(P.PresenceView, { d: { state: { mode: 'off' }, shelf: [] }, onEnter: noop, onLeave: noop, onPickUp: noop, onPutDown: noop })) : 'NO VIEW',
  jr_empty: J.JournalView ? html(h(J.JournalView, { d: { current: '', history: [] } })) : 'NO VIEW',
  jr: J.JournalView ? html(h(J.JournalView, { d: { current: 'As of Saturday: a good day.', current_id: 'x', history: [{ id: 'x', at: 1790380000, text: 'As of Saturday: a good day.' }] } })) : 'NO VIEW',
}
""")
check("the apps probe rendered (room/presence/journal)", "_error" not in d, d.get("_error", ""))
g = lambda k: grab(d, k)
check("the room's eye, off, is a warn chip in its own words",
      "ui-tone-warn" in g("room_off") and "the hourly look is off" in g("room_off"))
check("the room's eye, on, is an ok chip", "ui-tone-ok" in g("room_on") and "looking hourly" in g("room_on"))
check("no look yet is the kit's empty state, verbatim",
      "ui-state-empty" in g("room_off") and "nothing written yet" in g("room_off"))
check("her mode buttons are kit buttons, the live one pressed",
      g("prs").count("ui-btn") >= 4 and 'aria-pressed="true"' in g("prs"))
check("the book in her hands offers 'put it down' as a kit button", "put it down" in g("prs") and "ui-btn-sm" in g("prs"))
check("an empty shelf is the kit's empty state", "ui-state-empty" in g("prs_empty"))
check("an unwritten journal is the kit's empty state, her words verbatim",
      "ui-state-empty" in g("jr_empty") and "she has not written yet" in g("jr_empty"))
check("her journal entry is in her voice's type", "entry" in g("jr") and "a good day" in g("jr"))
check("Room's and Presence's state lines are wrapping chips (M6)",
      all("ui-chip-wrap" in g(k) for k in ("room_off", "room_on", "prs", "prs_empty")),
      [k for k in ("room_off", "room_on", "prs", "prs_empty") if "ui-chip-wrap" not in g(k)])

d = render(r"""
import * as T from '../ui/src/apps/Tools.jsx'
const d = { counts: { total: 3 }, by_risk: { read: 2, world: 1 }, groups: { memory: 'what she keeps' },
            tools: [ { name: 'recall', group: 'memory', risk: 'read', tier: 'core', description: 'look back' },
                     { name: 'web_search', group: 'memory', risk: 'world', tier: 'opt', arms: 'SP_SEARCH', description: 'look out' },
                     { name: 'note', group: 'memory', risk: 'read', tier: 'core', description: 'write down' } ] }
const out = {
  all: T.ToolsView ? html(h(T.ToolsView, { d, filter: '', setFilter: () => {} })) : 'NO VIEW',
  world: T.ToolsView ? html(h(T.ToolsView, { d, filter: 'world', setFilter: () => {} })) : 'NO VIEW',
}
""")
check("the tools probe rendered", "_error" not in d, d.get("_error", ""))
g = lambda k: grab(d, k)
check("the risk filter is the kit's Tabs", 'role="tablist"' in g("all") and g("all").count('role="tab"') == 3)
check("'all' is the selected tab by default", re.search(r'aria-selected="true"[^>]*>all 3<', g("all")) is not None)
check("with the world filter on, the world tab is the selected one",
      re.search(r'aria-selected="true"[^>]*>world 1<', g("world")) is not None)
check("filtering to world leaves only web_search", "web_search" in g("world") and ">recall<" not in g("world"))
check("an arming knob is a warm chip", "ui-tone-warm" in g("all") and "SP_SEARCH" in g("all"))
check("no .chips filter row is left", 'class="chips"' not in g("all"))
check("the risk filter's tab list is named (M7)", 'role="tablist" aria-label="filter by risk"' in g("all"))
# PHONE WIDTH: A WINDOW IS THE DESKTOP (final review, Q4). Windows opened at their registry
# width and ran off the right edge at 375px; the 620px block pins every .win to the desktop.
_m620 = re.search(r"@media\s*\(max-width:\s*620px\)\s*\{(.*?)\}\s*\}", _shell, re.S)
# + "}": the block regex stops at the first "}" + "}", which eats the last rule's own brace
_win620 = _m620 and re.search(r"(?:^|\})\s*\.win\s*\{([^}]*)\}", _m620.group(1) + "}")
check("at phone width a window fills the desktop (Q4)",
      bool(_win620) and all(re.search(p + r"\s*!important", _win620.group(1))
                             for p in (r"left:\s*0", r"top:\s*0", r"width:\s*100%", r"height:\s*100%")),
      _win620 and _win620.group(1))
check("...and has no resize grips there (Q4)", ".win > .grip" in _shed_at and 620 in _shed_at[".win > .grip"])

print("\n11. APPS — the eight stage-4 windows draw kit parts (views rendered with fixtures)")
# Each block below adds the classes its window retired to RETIRED_S4; the scan at the end
# of the leg (kept LAST) proves no render draws them and room.css styles none of them.
RETIRED_S4: set = set()

d = render(r"""
import * as F from '../ui/src/apps/Files.jsx'
import * as H from '../ui/src/apps/House.jsx'
const noop = () => {}
const tree = { root: '/srv/shared', files: [ { path: 'notes.md', bytes: 2048 }, { path: 'photo.png', bytes: 3000000 } ] }
const FV = F.FilesView
const fv = (p) => FV ? html(h(FV, { d: tree, open: null, text: '', setText: noop, note: null, dragging: false,
                                    onRead: noop, onSave: noop, onClose: noop, ...p })) : 'NO VIEW'
const HV = H.HouseView
const hv = (d) => HV ? html(h(HV, { d })) : 'NO VIEW'
const ents = [ { entity_id: 'sensor.phone_sleep_confidence', kind: 'sleep', value: 0.82 },
               { entity_id: 'sensor.phone_activity', kind: 'activity', value: null, why: 'unavailable' } ]
const out = {
  fl: fv({}),
  fl_open: fv({ open: { path: 'notes.md' }, text: 'hello', note: { t: 'saved — she can read it now', tone: 'ok' } }),
  fl_refused: fv({ note: { t: 'photo.png: text files only for now', tone: 'err' } }),
  fl_empty: fv({ d: { root: '/srv/shared', files: [] } }),
  fl_drag: fv({ dragging: true }),
  ha_up: hv({ configured: true, alive: true, url: 'http://ha.local:8123', total_entities: 392, entities: ents, watching: [] }),
  ha_down: hv({ configured: true, alive: false, why: 'connection refused' }),
  ha_off: hv({ configured: false }),
  ha_quiet: hv({ configured: true, alive: true, total_entities: 392, entities: [] }),
}
""")
check("the files/house probe rendered", "_error" not in d, d.get("_error", ""))
g = lambda k: grab(d, k)
# FILES — the tree they share
check("a text file is a kit row he can press; a picture is not (the write route takes a string)",
      g("fl").count("ui-row-main") == 1 and g("fl").count('class="ui-row"') == 1, g("fl")[:400])
check("sizes read as sizes, in the machine's type", ">2.0K<" in g("fl") and ">2.9M<" in g("fl"))
check("the tree's root is shown", ">/srv/shared<" in g("fl"))
check("an empty tree is the kit's empty state, the sentence verbatim",
      "ui-state-empty" in g("fl_empty") and "empty — drag a text file in to share it with her" in g("fl_empty"))
check("the open file: save is the window's one primary, close a ghost",
      g("fl_open").count("ui-btn-primary") == 1
      and re.search(r'ui-btn-primary[^"]*"[^>]*>save<', g("fl_open")) is not None
      and re.search(r'ui-btn-ghost[^"]*"[^>]*>close<', g("fl_open")) is not None)
check("the editor is a kit field, named by the file it holds",
      "ui-field-area" in g("fl_open") and 'aria-label="the text of notes.md"' in g("fl_open"))
check("the open file's row is marked", 'class="fl-file on"' in g("fl_open"))
check("a save says so in ok, a refusal in err — the words verbatim",
      "ui-tone-ok" in g("fl_open") and "saved — she can read it now" in g("fl_open")
      and "ui-tone-err" in g("fl_refused") and "photo.png: text files only for now" in g("fl_refused"))
check("dropping says so, only while dragging", "drop to share" in g("fl_drag") and "drop to share" not in g("fl"))
# HOUSE — a beachhead: three states and a link, and no buttons
check("connected is an ok chip with a dot", "ui-tone-ok" in g("ha_up") and ">connected<" in g("ha_up")
      and "ui-chip-dot" in g("ha_up"))
check("three states, three tones — unreachable is err, not configured is quiet",
      "ui-tone-err" in g("ha_down") and ">unreachable<" in g("ha_down")
      and "ui-tone-neutral" in g("ha_off") and ">not configured<" in g("ha_off")
      and "ui-tone-err" not in g("ha_off"))
check("the reason it is down is said, verbatim", "connection refused" in g("ha_down"))
check("what crosses: each entity and its value; a missing value says why",
      "sensor.phone_sleep_confidence" in g("ha_up") and ">0.82<" in g("ha_up") and ">unavailable<" in g("ha_up"))
check("nothing crossing yet is the kit's empty state, the sentence verbatim",
      "ui-state-empty" in g("ha_quiet")
      and "Nothing here reaches her yet. The bridge takes a sleep confidence and an activity from the "
          "companion app — enable those sensors on the phone and they appear." in g("ha_quiet"))
check("the house still offers no button — nothing in it can call a service",
      all("<button" not in g(k) for k in ("ha_up", "ha_down", "ha_off", "ha_quiet")))
check("the link out is a link, its words verbatim",
      'href="http://ha.local:8123"' in g("ha_up") and "open Home Assistant ↗" in g("ha_up"))
check("the foot points at the Body window, not a heart glyph the room no longer draws",
      "Her body readings are in the Body window." in g("ha_up") and "♥" not in g("ha_up"))
RETIRED_S4 |= {"files", "fp", "fs", "viewer", "vh", "dropzone",
               "ha-dot", "ha-up", "ha-down", "ha-off", "ha-state", "ha-empty", "ha-dim"}

d = render(r"""
import * as D from '../ui/src/apps/Decisions.jsx'
import * as A from '../ui/src/apps/Agency.jsx'
const noop = () => {}
const dec = { open: [ { id: 'a', kind: 'route', area: 'voice', title: 'arm the voice knob?', body: 'asked twice', options: ['arm', 'leave off'] },
                      { id: 'b', kind: 'once', title: 'relabel row 12', options: ['yes'] } ],
              decided: [ { id: 'z', kind: 'note', choice: 'arm', title: 'the old one', decided_at: '2026-09-20T10:00:00' } ] }
const DV = D.DecisionsView
const dv = (p) => DV ? html(h(DV, { d: dec, showPast: false, setShowPast: noop, onDone: noop, ...p })) : 'NO VIEW'
const day = { ok: true, days: 7, total: 3, counts: { own_time: 2, journal: 1 },
              rows: [ { kind: 'own_time', id: '1', at: 1790380000, text: 'read about tides' },
                      { kind: 'journal', id: '2', at: 1790300000, text: 'As of Friday: quiet.' },
                      { kind: 'own_time', id: '3', at: 1790290000, text: 'wrote a list', state: 'delayed' } ],
              sources_failed: { wore: 'missing' } }
const AV = A.AgencyView
const av = (p) => AV ? html(h(AV, { d: day, only: '', setOnly: noop, ...p })) : 'NO VIEW'
const out = {
  dec: dv({}), dec_past: dv({ showPast: true }), dec_none: dv({ d: { open: [], decided: [] } }),
  ag: av({}), ag_journal: av({ only: 'journal' }), ag_vanished: av({ only: 'wore' }),
  ag_kindless: av({ only: 'journal', d: { ...day, rows: day.rows.filter(r => r.kind !== 'journal') } }),
  ag_none: av({ d: { ok: true, days: 7, total: 0, counts: {}, rows: [] } }),
  ag_bad: av({ d: { ok: false } }),
}
""")
check("the decisions/agency probe rendered", "_error" not in d, d.get("_error", ""))
g = lambda k: grab(d, k)
# DECISIONS — what only he can settle
check("a decision's kind is a kit chip in its own tone — route accent, once warm",
      re.search(r'ui-tone-accent"[^>]*title="applied immediately by code when you choose"', g("dec")) is not None
      and re.search(r'ui-tone-warm"[^>]*title="one-off', g("dec")) is not None)
_bs = re.findall(r"<button[^>]*>", g("dec"))
check("every answer is a kit button, and none is primary — no answer is the default",
      len(_bs) == 4 and all("ui-btn" in b for b in _bs) and "ui-btn-primary" not in g("dec")
      and ">leave off<" in g("dec"), _bs)
check("the why box is a kit field, named by its own words",
      g("dec").count('aria-label="why (optional, kept with the answer)"') == 2 and "ui-field" in g("dec"))
check("the head row is not a .chips row: a count chip, and a toggle that says whether it is pressed",
      'class="chips"' not in g("dec")
      and re.search(r'ui-tone-accent"><span class="ui-chip-t">2 waiting on you<', g("dec")) is not None
      and re.search(r'aria-pressed="false"[^>]*>1 decided<', g("dec")) is not None)
check("the decided list opens with its heading, each verdict a chip",
      re.search(r'aria-pressed="true"[^>]*>1 decided<', g("dec_past")) is not None
      and "decided — kept, never removed" in g("dec_past")
      and re.search(r'ui-chip-t">arm<', g("dec_past")) is not None)
check("nothing waiting is the kit's empty state, the sentence verbatim",
      "ui-state-empty" in g("dec_none")
      and "Nothing is waiting. Anything I cannot settle myself lands here rather than in a reply "
          "that scrolls away." in g("dec_none"))
# HER OWN TIME — a record of what she did
check("her kinds are the kit's Tabs, named — all, plus one per kind she has rows in",
      'role="tablist" aria-label="filter by kind"' in g("ag") and g("ag").count('role="tab"') == 3)
check("'all' (the sum of her kinds) is selected by default",
      re.search(r'aria-selected="true"[^>]*>all 3<', g("ag")) is not None)
check("filtering to the journal selects its tab and leaves only its row",
      re.search(r'aria-selected="true"[^>]*><span class="ag-dot ag-k-journal"', g("ag_journal")) is not None
      and "As of Friday: quiet." in g("ag_journal") and "read about tides" not in g("ag_journal"))
check("no emoji or text glyph stands for a kind — a dot in the kind's colour",
      not any(c in g("ag") for c in ("◈", "📔", "👗", "✧", "📋")) and "ag-ic" not in g("ag")
      and g("ag").count('class="ag-dot ag-k-own_time"') == 3)
check("KINDS carries no icon field — the glyphs are gone at the source", "icon:" not in _code("ui/src/apps/Agency.jsx"))
check("a source that failed is said out loud, as an err chip",
      "ui-tone-err" in g("ag") and "could not read: wore" in g("ag"))
check("a row's state is a chip", re.search(r'ui-chip-t">delayed<', g("ag")) is not None)
check("no time to herself is the kit's empty state, her sentence verbatim",
      "ui-state-empty" in g("ag_none") and "she has not had any time to herself in the last 7 days" in g("ag_none"))
check("a kind with nothing in it says so, verbatim", "nothing of that kind in the last 7 days" in g("ag_kindless"))
# A CHOSEN KIND THAT VANISHED (stage-4 final review, M2): 'wore' has no count, so no tab;
# the strip selected "all" (Tabs' clamp) while the rows still filtered to 'wore' — nothing.
check("a chosen kind whose tab has gone shows all her rows under 'all' (M2)",
      re.search(r'aria-selected="true"[^>]*>all 3<', g("ag_vanished")) is not None
      and all(t in g("ag_vanished") for t in ("read about tides", "As of Friday: quiet.", "wrote a list"))
      and "nothing of that kind" not in g("ag_vanished"))
check("an unreadable day is the kit's error state, verbatim",
      "ui-state-error" in g("ag_bad") and "could not read her day" in g("ag_bad"))
RETIRED_S4 |= {"dec-kind", "dec-k-once", "dec-k-route", "dec-k-note", "dec-choice",
               "ag-bar", "ag-fil", "ag-ic", "ag-n", "ag-state"}

d = render(r"""
import * as M from '../ui/src/apps/Music.jsx'
import * as S from '../ui/src/apps/Stage.jsx'
const noop = () => {}
const lib = [ { path: 'a.mp3', title: 'Tides', artist: 'Nils', album: 'Shore' },
              { path: 'b.mp3', title: 'Rain', artist: 'Ola', album: 'Grey' } ]
const playing = { dir_exists: true, dir: '/srv/music', playing: true, track: lib[0], changed_by: 'her', queue: [ { title: 'Rain' } ] }
const MV = M.MusicView
const mv = (p) => MV ? html(h(MV, { d: { state: playing, library: lib }, err: null, q: '', setQ: noop, onSend: noop, ...p })) : 'NO VIEW'
const ladder = ['warm', 'near', 'close', 'heated', 'hot'].map((name, level) => ({ level, name, dwell: 2, direction: 'd' + level }))
const scene = { title: 'Lighthouse', theme: 'storm', role: 'the keeper', setting: 'a tower', level: 1, beats: 5,
                beats_at_level: 1, hooks: ['the lamp fails', 'a knock'], hooks_fired: [0], opened: false }
const SV = S.StageView
const sv = (d) => SV ? html(h(SV, { d, act: noop })) : 'NO VIEW'
const out = {
  mus: mv({}),
  mus_paused: mv({ d: { state: { ...playing, playing: false }, library: lib } }),
  mus_rain: mv({ q: 'rain' }),
  mus_err: mv({ err: 'could not play that file' }),
  mus_nodir: mv({ d: { state: { dir_exists: false, dir: '/srv/none' }, library: [] } }),
  mus_empty: mv({ d: { state: { dir_exists: true, dir: '/srv/music' }, library: [] } }),
  stg_live: sv({ enabled: true, max_heat: 3, dwell_scale: 1.5, ladder, scene, stop_words: 'say stop, any time' }),
  stg_idle: sv({ enabled: true, max_heat: 3, ladder, pending: true, stop_words: '',
                 deck: [ { id: 'lh', title: 'Lighthouse', theme: 'storm', premise: 'a night watch', authored: true } ] }),
  stg_off: sv({ enabled: false, ladder: [], deck: [] }),
  stg_bad: sv({ ok: false, error: 'roleplay module missing' }),
}
""")
check("the music/stage probe rendered", "_error" not in d, d.get("_error", ""))
g = lambda k: grab(d, k)
_tracks = lambda k: g(k).split('class="mus-tracks"')[-1]
# MUSIC — one player, two people
check("play/pause is the window's one primary, and says what it will do",
      g("mus").count("ui-btn-primary") == 1
      and re.search(r'ui-btn-primary[^"]*"[^>]*>pause<', g("mus")) is not None
      and re.search(r'ui-btn-primary[^"]*"[^>]*>play<', g("mus_paused")) is not None)
check("next is a kit button", re.search(r'class="ui-btn ui-btn-secondary[^"]*"[^>]*>next<', g("mus")) is not None)
check("no emoji-presentation glyph on the controls",
      not any(c in g("mus") + g("mus_paused") for c in ("⏸", "▶", "⏭")))
check("the find box is a kit field, named", "ui-field" in g("mus") and 'aria-label="find a track"' in g("mus"))
check("every track is a kit row he can press", g("mus").count("ui-row-main") == 2)
check("the track on now carries one chip that says so", g("mus").count('ui-chip-t">now<') == 1)
# THE TRACK BUTTON'S NAME (stage-4 final review, M3): its text, tags stripped, is what a
# screen reader hears — it was "TidesNils", and which track plays was outside the button.
_tnames = [re.sub(r"<!-- -->|<[^>]+>", "", b) for b in
           re.findall(r'<button type="button" class="ui-row-main"[^>]*>(.*?)</button>', _tracks("mus"))]
check("each track button is named title · artist, and the one playing says so (M3)",
      _tnames == ["Tides · Nils, now playing", "Rain · Ola"], _tnames)
check("finding filters the rows", ">Rain<" in _tracks("mus_rain") and ">Tides<" not in _tracks("mus_rain"))
check("who put it on is said, verbatim", "put on by her" in g("mus"))
check("a player error is an err chip, verbatim", "ui-tone-err" in g("mus_err") and "could not play that file" in g("mus_err"))
check("no library is the kit's empty state, its words verbatim",
      "ui-state-empty" in g("mus_nodir") and "no music library — nothing at" in g("mus_nodir") and ">/srv/none<" in g("mus_nodir"))
check("an empty library is the kit's empty state, its words verbatim",
      "ui-state-empty" in g("mus_empty") and "is empty. drop some audio in and" in g("mus_empty"))
# STAGE — the director, made visible; stop is always one click
check("the status row is not a .chips row: armed, ceiling and pacing are chips",
      'class="chips"' not in g("stg_live")
      and re.search(r'ui-tone-ok"><span class="ui-chip-dot"></span><span class="ui-chip-t">armed<', g("stg_live")) is not None
      and 'ui-chip-t">ceiling heated<' in g("stg_live") and 'ui-chip-t">pacing ×1.5<' in g("stg_live"))
check("stop is a danger kit button, drawn only while a scene is live, its words verbatim",
      re.search(r'ui-btn-danger[^"]*"[^>]*>■ stop the scene<', g("stg_live")) is not None
      and "stop the scene" not in g("stg_idle"))
check("every button in the window is a kit button — begin and stop included",
      all("ui-btn" in b for k in ("stg_live", "stg_idle") for b in re.findall(r"<button[^>]*>", g(k)))
      and ">begin<" in g("stg_idle"))
check("an opening not yet delivered is a warn chip",
      re.search(r'ui-tone-warn"><span class="ui-chip-t">opening not yet delivered<', g("stg_live")) is not None)
check("the ladder is still shown: the wall struck, the rung's dwell said",
      "above the ceiling" in g("stg_live") and "beats before the next rung can open" in g("stg_live"))
check("an authored card wears an ok chip",
      re.search(r'ui-tone-ok"[^>]*><span class="ui-chip-t">authored<', g("stg_idle")) is not None)
check("switched off is a quiet chip, and the off paragraph stays verbatim",
      re.search(r'ui-tone-neutral"><span class="ui-chip-t">switched off<', g("stg_off")) is not None
      and "Roleplay is off. Turn on" in g("stg_off"))
check("she has offered, verbatim", "She has offered — pick one in the chat." in g("stg_idle"))
check("an unavailable stage is the kit's error state, verbatim",
      "ui-state-error" in g("stg_bad") and "stage unavailable — roleplay module missing" in g("stg_bad"))
RETIRED_S4 |= {"music", "controls", "tracks", "track", "tt", "ta", "stg-auth"}

d = render(r"""
import * as U from '../ui/src/apps/Setup.jsx'
const setup = {
  engine: { kind: 'openai', base_url: 'http://127.0.0.1:1234/v1', model: 'm', dialect: 'generic', probe: '200 OK', reachable: true,
            key: { configured: true, present: false, path: 'config/engine-token' } },
  xai: { key: { configured: false, present: false, path: 'config/xai-token' }, voice: { armed: false, method: 'off' },
         images: { armed: false }, search: { backend: 'ddg', armed: false }, research: { armed: false } },
  persona: { present: true, dir: 'persona', fragments: 12 },
  avatar: { have_face: false, bundled: true, set: 'kairos-1', seeded: false, faces_with_art: 0, faces_total: 7 },
  sidecars: { enabled: false },
  memory: { present: true, registry: 'var/memory/registry.jsonl', rows: 812 },
  models: { engine: { note: 'what the decode knobs were tuned on',
                      recommended: [ { id: 'org/model-GGUF', card: 'https://example.org/model', format: 'gguf', knob: '[engine].model', note: 'the default' } ] } },
}
const out = { su: U.SetupView ? html(h(U.SetupView, { d: setup })) : 'NO VIEW' }
""")
check("the setup probe rendered", "_error" not in d, d.get("_error", ""))
g = lambda k: grab(d, k)
check("a ready section is an ok chip", re.search(r'ui-tone-ok"><span class="ui-chip-t">ready<', g("su")) is not None)
check("needs attention is a warn chip (her face: bundled, not yet laid down)",
      re.search(r'ui-tone-warn"><span class="ui-chip-t">needs attention<', g("su")) is not None)
check("not set is a quiet chip — absent is not an error",
      re.search(r'ui-tone-neutral"><span class="ui-chip-t">not set<', g("su")) is not None)
check("a key file made but empty is its own state, in warn",
      re.search(r'ui-tone-warn"><span class="ui-chip-t">empty file<', g("su")) is not None)
check("a key file never made is quiet", re.search(r'ui-tone-neutral"><span class="ui-chip-t">not created<', g("su")) is not None)
check("no su-mark and no bare good/bad/warn class is drawn — those tones only ever lived in .su-mark.*",
      "su-mark" not in g("su") and not re.search(r'class="[^"]*(?<![\w-])(good|bad|warn)(?![\w-])', g("su")))
check("its rows stay KV, and 'good'/'bad' still colour them",
      'class="ui-kv"' in g("su") and "ui-kv-ok" in g("su") and "ui-kv-err" in g("su"))
check("a model's format and its knob are chips; the knob warm, as Tools' arming knob is",
      re.search(r'ui-tone-neutral"><span class="ui-chip-t">gguf<', g("su")) is not None
      and re.search(r'ui-tone-warm"><span class="ui-chip-t">\[engine\]\.model<', g("su")) is not None)
check("the lead is verbatim", "Everything below is read from the running stack." in g("su"))
check("Setup still has no write authority — no button anywhere", "<button" not in g("su"))
RETIRED_S4 |= {"su-mark", "su-fmt", "su-knob"}

d = render(r"""
import * as Y from '../ui/src/apps/Story.jsx'
const noop = () => {}
const facts = [
  { name: 'r1', text: 'she likes tides', kind: 'fact', core: 1, salience: 0.9, ts: '2026-09-20T08:00:00' },
  { name: 'c1', text: 'Chapter one: the first quiet week', kind: 'chapter', ts: '2026-09-21' },
  { name: 'f1', text: 'an old thought', kind: 'thought', lifecycle: 'retired', retired_because: 'folded into the chapter c1', superseded_by: 'c1' },
  { name: 't1', text: 'a thought about rain', kind: 'thought', ts: '2026-09-22' },
  { name: 'd1', text: 'a dream of a lighthouse', kind: 'dream', ts: '2026-09-23' },
]
const st = { block: [ { section: 'fact', name: 'r1', label: 'she likes tides' }, { section: 'narrative', name: 'nope', label: 'an unattributed line' } ],
             backup: { ok: true, count: 12, newest: '2026-09-26 10:00', bytes: 52428800 } }
const V = Y.StoryView
const sv = (p) => V ? html(h(V, { d: st, facts, lane: '', setLane: noop, refresh: noop, ...p })) : 'NO VIEW'
const R = Y.StoryRow
const out = {
  sty: sv({}), sty_thought: sv({ lane: 'thought' }), sty_gone: sv({ lane: 'feeling' }),
  sty_nochap: sv({ facts: facts.filter(r => r.kind !== 'chapter') }),
  sty_nobk: sv({ d: { block: [], backup: { enabled: false } } }),
  row_open: R ? html(h(R, { r: facts[0], onDone: noop, startOpen: true })) : 'NO ROW',
}
""")
check("the story probe rendered", "_error" not in d, d.get("_error", ""))
g = lambda k: grab(d, k)
_LANE_NOTE = ("her becoming — the nightly paragraph — reads in the journal panel; these are the "
              "registry lanes behind it.")
check("her lanes are the kit's Tabs, named — one per lane with live rows; no .chips row",
      'role="tablist" aria-label="filter by lane"' in g("sty") and g("sty").count('role="tab"') == 3
      and 'class="chips"' not in g("sty"))
check("choosing a lane selects its tab and shows its rows",
      re.search(r'aria-selected="true"[^>]*>thought 1<', g("sty_thought")) is not None
      and "a thought about rain" in g("sty_thought") and "a thought about rain" not in g("sty"))
# Tabs always hold one selected tab (the clamped index): with no lane chosen, or a chosen
# lane whose rows are gone, the FIRST lane is selected — and its rows are the ones shown,
# so a selected tab never sits over an empty section.
check("no lane chosen (or a lane that emptied) selects the first lane and shows its rows",
      all(re.search(r'aria-selected="true"[^>]*>chapter 1<', g(k)) is not None
          and g(k).count("Chapter one: the first quiet week") == 2 for k in ("sty", "sty_gone")))
check("the lanes' note stands, verbatim, whether or not a lane is chosen",
      all(_LANE_NOTE in g(k) for k in ("sty", "sty_thought")))
check("a row's kind is a kit chip; the old cls chip is gone",
      re.search(r'ui-chip-t">fact<', g("sty")) is not None and "sty-k" not in g("sty") and 'class="cls' not in g("sty"))
check("a row opens by a button that says whether it is open",
      '<button type="button" class="sty-line" aria-expanded="false"' in g("sty"))
check("the core mark stays", "★" in g("sty"))
check("an open row: pin and retire are kit buttons, retire in danger, the words verbatim",
      'aria-expanded="true"' in g("row_open")
      and re.search(r'ui-btn-secondary[^"]*"[^>]*>unpin core<', g("row_open")) is not None
      and re.search(r'ui-btn-danger[^"]*"[^>]*>retire<', g("row_open")) is not None)
check("the wording box is a kit field, named by its own words",
      "ui-field" in g("row_open")
      and 'aria-label="correct the wording — keeps the row, notes the edit"' in g("row_open"))
check("no chapter yet is the kit's empty state, the sentence verbatim",
      "ui-state-empty" in g("sty_nochap")
      and "none yet — the first is written after about a week, at the 04:00 boundary of a quiet night." in g("sty_nochap"))
check("the backup receipt is a chip: ok when backed up, warn when not — the words verbatim",
      re.search(r'ui-tone-ok[^"]*"><span class="ui-chip-t">backed up hourly — 12 archives, newest 2026-09-26 10:00, 50 MB kept<', g("sty")) is not None
      and re.search(r'ui-tone-warn[^"]*"><span class="ui-chip-t">backups are OFF<', g("sty_nobk")) is not None)
check("an unattributed prefix line still shows, and the fold still archives under its chapter",
      "an unattributed line" in g("sty") and "an old thought" in g("sty"))
# WHO STILL DRAWS .chips — no stage-4 window does; the global rule stays for the rest
_S4 = {"Files", "House", "Decisions", "Agency", "Music", "Stage", "Setup", "Story"}
_apps_dir = os.path.join(ROOT, "ui", "src", "apps")
_chips_users = sorted(f[:-4] for f in os.listdir(_apps_dir) if f.endswith(".jsx")
                      and re.search(r"""className=(?:"|\{')[^>]*(?<![\w-])chips(?![\w-])""", _code("ui/src/apps/" + f)))
check("no stage-4 window draws a .chips row", not (set(_chips_users) & _S4), _chips_users)
print("   .chips is still drawn by: %s — its rule stays until the last of them migrates (stages 5-6)"
      % (", ".join(_chips_users) or "nobody"))
RETIRED_S4 |= {"sty-lane", "sty-k"}

# ── leg 11's retired scan — keep this block last, directly above finish(GATE) ──
_drawn4 = set()
for s in ALL_HTML:
    for cls in re.findall(r'class="([^"]*)"', s):
        _drawn4 |= set(cls.split()) & RETIRED_S4
check("no stage-4 window draws a class it retired", bool(RETIRED_S4) and not _drawn4, sorted(_drawn4))
_room_now = re.sub(r"/\*.*?\*/", "", io.open(os.path.join(ROOT, "ui/src/room.css"), encoding="utf-8").read(), flags=re.S)
_written4 = sorted(c for c in RETIRED_S4 if re.search(r"\." + re.escape(c) + r"(?![\w-])", _room_now))
check("...and room.css styles none of them", not _written4, _written4)

finish(GATE)
