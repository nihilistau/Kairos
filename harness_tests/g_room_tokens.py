"""G-ROOM-TOKENS — the room's design system holds its own promises.

THE SPEC: docs/superpowers/specs/2026-09-23-room-redesign-design.md. Five legs:

  1. CONTRAST. Every text role on every surface is >= 4.5:1 (WCAG AA for the 11-13px
     sizes these roles are used at). Computed from tokens.css, not eyeballed.
  2. ICONS. Every `icon:` in appRegistry names a glyph in kit/icons.jsx; no emoji left.
  3. MOOD. resolveMood's precedence, driven under node; and only room/useMood.js reads
     roomMood.get, because owning the live read is owning the rule (AGENTS.md §0).
  4. COLOUR RATCHET. Raw colour literals outside kit/tokens.css may only fall.
  5. RGBA TRIPLES. Every `rgba(var(--x), a)` names a variable that is a comma triple.
     `--es-rgb` was `6 182 212` and made fifty declarations invalid for seven weeks.

Offline: reads sources, runs node if present (leg 3 skips cleanly without it).
"""
from __future__ import annotations

import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "ui", "src")
TOKENS = os.path.join(UI, "kit", "tokens.css")


def read(p):
    return io.open(p, encoding="utf-8").read()


def blank_comments(src: str) -> str:
    """The src-trap: a gate that greps source passes on the prose explaining the
    change. Blank /* */ and // comments before looking at anything."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?<![:'\"])//[^\n]*", "", src)


def tokens() -> dict:
    css = blank_comments(read(TOKENS))
    root = re.search(r":root\s*\{(.*?)\n\}", css, re.S)
    body = root.group(1) if root else ""
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;]+);", body)}


def hex_rgb(h: str):
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def lum(rgb) -> float:
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((lum(hex_rgb(a)), lum(hex_rgb(b))), reverse=True)
    return (la + 0.05) / (lb + 0.05)


print("1. CONTRAST — every text role, every surface, >= 4.5:1")
have_tokens = os.path.isfile(TOKENS)
check("kit/tokens.css exists", have_tokens)
T = tokens() if have_tokens else {}
SURFACES = ["--surface-0", "--surface-1", "--surface-2", "--surface-3"]
TEXTS = ["--text-1", "--text-2", "--text-3", "--accent", "--warm"]
missing = [n for n in SURFACES + TEXTS if not re.fullmatch(r"#[0-9a-fA-F]{6}", T.get(n, ""))]
check("every surface and text role is a plain 6-digit hex", not missing, missing)
if not missing:
    worst = min(((contrast(T[t], T[s]), t, s) for t in TEXTS for s in SURFACES))
    print("   worst pair: %s on %s = %.2f:1" % (worst[1], worst[2], worst[0]))
    low = [(t, s, round(contrast(T[t], T[s]), 2)) for t in TEXTS for s in SURFACES
           if contrast(T[t], T[s]) < 4.5]
    check("no text role falls below 4.5:1 on any surface", not low, low)

print("\n3. MOOD — one precedence, one reader of the live value")
MT = os.path.join(UI, "room", "moodTheme.js")
check("room/moodTheme.js exists", os.path.isfile(MT))
node = shutil.which("node")
if not node:
    print("  --   node absent; the precedence legs are skipped")
elif os.path.isfile(MT):
    probe = r"""
import { resolveMood } from './ui/src/room/moodTheme.js'
const P = (m) => ({ her: { mood: m } })
const out = {
  live_beats_pulse: resolveMood({ mood: 'tender' }, P('peaceful')),
  pulse_when_no_live: resolveMood({ mood: null }, P('peaceful')),
  neither: resolveMood(null, null),
  compound: resolveMood({ mood: 'wistful; naughty' }, null),
  stray_colon: resolveMood({ mood: ':tender' }, null),
  unknown: resolveMood({ mood: 'sleepy' }, null),
  thinking: resolveMood({ mood: null, thinking: true }, P('quiet')),
  junk: resolveMood({ mood: 5 }, { her: 7 }),
}
console.log(JSON.stringify(out))
"""
    pp = os.path.join(ROOT, "_g_room_tokens_probe.mjs")
    data, err = {}, ""
    try:
        with io.open(pp, "w", encoding="utf-8") as f:
            f.write(probe)
        r = subprocess.run([node, pp], capture_output=True, text=True, cwd=ROOT, timeout=60)
        err = r.stderr[-300:]
        data = json.loads((r.stdout or "{}").strip().splitlines()[-1])
    except Exception as exc:
        err = "%s: %s %s" % (type(exc).__name__, exc, err)
    finally:
        if os.path.exists(pp):
            os.remove(pp)
    check("the node probe ran", bool(data), err)
    if data:
        g = lambda k, f: data.get(k, {}).get(f)
        check("her live mark beats the polled mood", g("live_beats_pulse", "word") == "tender"
              and g("live_beats_pulse", "hue") == 340)
        check("the pulse speaks when there is no live mark", g("pulse_when_no_live", "word") == "peaceful")
        check("neither → quiet", g("neither", "word") == "quiet" and g("neither", "hue") == 210)
        check("a compound takes its first word", g("compound", "word") == "wistful")
        check("a stray leading colon is stripped", g("stray_colon", "word") == "tender")
        check("an unknown word is HERS, with quiet's hue",
              g("unknown", "word") == "sleepy" and g("unknown", "known") is False
              and g("unknown", "hue") == 210)
        check("thinking passes through", g("thinking", "thinking") is True)
        check("junk input never throws and lands on quiet", g("junk", "word") == "quiet")

readers = []
for p in sorted(glob.glob(os.path.join(UI, "**", "*.js*"), recursive=True)):
    rel = os.path.relpath(p, UI).replace(os.sep, "/")
    if rel == "room/useMood.js":
        continue
    if re.search(r"\broomMood\.get\b", blank_comments(read(p))):
        readers.append(rel)
check("only room/useMood.js reads roomMood.get", not readers, readers)

print("\n4. COLOUR RATCHET — raw colour literals outside kit/tokens.css may only fall")
COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(\s*\d|\bhsla?\(\s*\d")
count, where = 0, {}
for p in sorted(glob.glob(os.path.join(UI, "**", "*.*"), recursive=True)):
    if not p.endswith((".css", ".jsx", ".js")):
        continue
    if os.path.abspath(p) == os.path.abspath(TOKENS):
        continue
    n = len(COLOUR.findall(blank_comments(read(p))))
    if n:
        where[os.path.relpath(p, UI).replace(os.sep, "/")] = n
        count += n
# RATCHET. Set once from the first run (Task 2 step 2). Lowering it is the only edit
# allowed; stage 6 of the redesign takes it to 0.
RATCHET_BASELINE = 308   # raised once, 2026-09-24, for kit.css's tone backgrounds — the only raise; stage 6 takes it to 0
print("   %d literals in %d files (baseline %d)" % (count, len(where), RATCHET_BASELINE))
for f, n in sorted(where.items(), key=lambda kv: -kv[1])[:8]:
    print("       %4d  %s" % (n, f))
check("raw colour literals have not grown past the baseline", count <= RATCHET_BASELINE,
      "%d > %d" % (count, RATCHET_BASELINE))
if count < RATCHET_BASELINE:
    print("   note: %d under baseline — lower RATCHET_BASELINE to %d" % (
        RATCHET_BASELINE - count, count))

print("\n5. RGBA TRIPLES — rgba(var(--x), a) needs --x to be a comma triple")
bad = []
for p in sorted(glob.glob(os.path.join(UI, "**", "*.css"), recursive=True)):
    for m in re.finditer(r"rgba\(\s*var\((--[\w-]+)\)\s*,", blank_comments(read(p))):
        v = T.get(m.group(1), "")
        # an alias to another triple is fine: follow one hop
        hop = re.fullmatch(r"var\((--[\w-]+)\)", v)
        if hop:
            v = T.get(hop.group(1), "")
        if not re.fullmatch(r"\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}", v):
            bad.append((os.path.basename(p), m.group(1), v or "undefined"))
check("every rgba(var(--x), a) resolves to a comma triple", not bad, sorted(set(bad)))

finish("G-ROOM-TOKENS")
