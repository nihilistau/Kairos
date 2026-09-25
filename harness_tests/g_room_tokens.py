"""G-ROOM-TOKENS — the room's design system holds its own promises.

THE SPEC: docs/superpowers/specs/2026-09-23-room-redesign-design.md. Five legs:

  1. CONTRAST. Every text role on every surface is >= 4.5:1 (WCAG AA for the 11-13px
     sizes these roles are used at). Computed from tokens.css, not eyeballed. Plus the
     pairs (2026-09-26, final review): ink on its fill (--on-accent, --on-err), the status
     colours on every surface, the idle window lights >= 3:1 on their bar, and every
     .ui-tone-* chip's text on its OWN tint composited over each surface (the err chip was
     4.47:1 on --surface-3); the mood tone at every hue, 10 degrees apart.
  2. ICONS. Every `icon:` in appRegistry names a glyph in kit/icons.jsx; no emoji left.
  3. MOOD. resolveMood's precedence, driven under node; and only room/useMood.js reads
     roomMood.get, because owning the live read is owning the rule (AGENTS.md §0).
  4. COLOUR RATCHET. Raw colour literals outside kit/tokens.css may only fall.
  5. RGBA TRIPLES. Every `rgba(var(--x), a)` names a variable that is a comma triple.
     Legs 4 and 5 have floors: counting nothing is a FAIL, not a pass.
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


def rgb_token(name: str):
    """A token's colour as 0..1 rgb: a hex, or one alias hop to a hex. None if neither."""
    v = T.get(name, "")
    hop = re.fullmatch(r"var\((--[\w-]+)\)", v)
    if hop:
        v = T.get(hop.group(1), "")
    return hex_rgb(v) if re.fullmatch(r"#[0-9a-fA-F]{6}", v) else None


def ratio(a, b) -> float:
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def hsl_rgb(h, s, l):
    import colorsys
    return colorsys.hls_to_rgb((h % 360) / 360.0, l, s)


def over(fg, a, bg):
    """fg at alpha a composited over an opaque bg — what the eye gets from a tint."""
    return tuple(f * a + b * (1 - a) for f, b in zip(fg, bg))


HUES = list(range(0, 360, 10))   # every mood hue the room can wear, 10 degrees apart


def paint(expr: str, hue: int):
    """(rgb, alpha) of a kit colour expression, or None if the gate cannot read it —
    which is a FAIL below, never a skip: an unreadable tone is an unmeasured one."""
    expr = expr.strip()
    m = re.fullmatch(r"var\((--[\w-]+)\)", expr)
    if m:
        c = rgb_token(m.group(1))
        return (c, 1.0) if c else None
    m = re.fullmatch(r"rgba\(\s*var\((--[\w-]+)\)\s*,\s*([\d.]+)\s*\)", expr)
    if m:
        t = re.fullmatch(r"(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", T.get(m.group(1), ""))
        return (tuple(int(x) / 255 for x in t.groups()), float(m.group(2))) if t else None
    m = re.fullmatch(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", expr)
    if m:
        return tuple(int(x) / 255 for x in m.groups()[:3]), float(m.group(4))
    m = re.fullmatch(r"hsl\(\s*var\(--mood-h\)\s+([\d.]+)%\s+([\d.]+)%\s*(?:/\s*([\d.]+))?\s*\)", expr)
    if m:
        return hsl_rgb(hue, float(m.group(1)) / 100, float(m.group(2)) / 100), \
            float(m.group(3) or 1)
    return None


if not missing:
    print("   pairs — ink on its fill, status colours on every surface, idle lights on their bar")
    fills = [("--on-accent", "--accent"), ("--on-err", "--err")]
    status = ["--ok", "--warn", "--err", "--an"]
    unread = [n for n in [x for p in fills for x in p] + status + ["--lt-idle", "--bar-idle"]
              if rgb_token(n) is None]
    check("every paired role is a hex token", not unread, unread)
    if not unread:
        lowf = [(a, b, round(ratio(rgb_token(a), rgb_token(b)), 2)) for a, b in fills
                if ratio(rgb_token(a), rgb_token(b)) < 4.5]
        check("ink on its fill >= 4.5:1 (--on-accent/--accent, --on-err/--err)", not lowf, lowf)
        lows = [(t, s, round(ratio(rgb_token(t), rgb_token(s)), 2)) for t in status for s in SURFACES
                if ratio(rgb_token(t), rgb_token(s)) < 4.5]
        check("--ok/--warn/--err/--an >= 4.5:1 on every surface", not lows, lows)
        r = ratio(rgb_token("--lt-idle"), rgb_token("--bar-idle"))
        check("an unfocused window's grey lights >= 3:1 on its bar (WCAG 1.4.11)", r >= 3.0,
              "%.2f:1" % r)

    print("   tones — each .ui-tone-* text on its own tint, composited over every surface")
    KIT_CSS = os.path.join(UI, "kit", "kit.css")
    kcss = blank_comments(read(KIT_CSS)) if os.path.isfile(KIT_CSS) else ""
    tones = {}
    for m in re.finditer(r"\.ui-(tone-[\w-]+|chip)\s*\{([^}]*)\}", kcss):
        decl = dict((k.strip(), v.strip()) for k, v in
                    re.findall(r"([\w-]+)\s*:\s*([^;]+);?", m.group(2)))
        if "color" in decl and "background" in decl:
            tones["neutral" if m.group(1) == "chip" else m.group(1)[5:]] = \
                (decl["color"], decl["background"])
    # A FLOOR: a regex that stops matching must not pass by measuring nothing.
    need = {"neutral", "accent", "ok", "warn", "err", "an", "mood"}
    check("every tone was read from kit.css", need <= set(tones), sorted(need - set(tones)))
    unreadable, lowt, worst_t = [], [], (99, "")
    for name, (fg_x, bg_x) in sorted(tones.items()):
        for hue in (HUES if "--mood-h" in fg_x + bg_x else [210]):
            fg, bg = paint(fg_x, hue), paint(bg_x, hue)
            if fg is None or bg is None or fg[1] != 1.0:
                unreadable.append(name)
                break
            for s in SURFACES:
                under = over(bg[0], bg[1], rgb_token(s))
                c = ratio(fg[0], under)
                worst_t = min(worst_t, (c, "%s on %s (hue %d)" % (name, s, hue)))
                if c < 4.5:
                    lowt.append((name, s, hue, round(c, 2)))
    check("every tone's colour and tint are readable by the gate", not unreadable, unreadable)
    if worst_t[1]:
        print("   worst tone: %s = %.2f:1" % (worst_t[1], worst_t[0]))
    check("every tone's text >= 4.5:1 on its own tint over every surface", not lowt, lowt[:6])

print("\n2. ICONS — every registry icon is a drawn glyph; no emoji left")
REG = blank_comments(read(os.path.join(UI, "appRegistry.jsx")))
ICONS_SRC = read(os.path.join(UI, "kit", "icons.jsx")) if os.path.isfile(
    os.path.join(UI, "kit", "icons.jsx")) else ""
glyphs = set(re.findall(r"^\s{2}(\w+):\s*\[", ICONS_SRC, re.M))
names = re.findall(r"icon:\s*'([^']*)'", REG)
check("the registry names icons at all", len(names) >= 20, len(names))
check("glyphs were read from icons.jsx", len(glyphs) >= 20, len(glyphs))
nonascii = [n for n in names if any(ord(ch) > 127 for ch in n)]
check("no emoji left in any icon field", not nonascii, nonascii[:6])
unknown = sorted(n for n in names if n not in glyphs and not any(ord(ch) > 127 for ch in n))
check("every registry icon names a glyph that exists", not unknown, unknown)
titles = re.findall(r"title:\s*'([^']*)'", REG)
lower = [t for t in titles if t[:1].islower()]
check("window titles are sentence case", not lower, lower[:6])

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
RATCHET_BASELINE = 272   # raised once, 2026-09-26, for kit.css's tone backgrounds — the only raise; 308 -> 299 when the shell left room.css (stage 1); 299 -> 291 when the taskbar and chat moved onto role tokens (stage 1, 3/4); 291 -> 272 when kit.css and the shell's tints read --ok/--warn/--err/--an-rgb and the ink tokens (final review, 2026-09-26); stage 6 takes it to 0
print("   %d literals in %d files (baseline %d)" % (count, len(where), RATCHET_BASELINE))
for f, n in sorted(where.items(), key=lambda kv: -kv[1])[:8]:
    print("       %4d  %s" % (n, f))
# A FLOOR: zero literals over the whole tree is a glob that found nothing, not stage 6.
# Stage 6 replaces this with its own check when it takes the count to zero.
check("the ratchet counted literals at all (the glob found the tree)", count > 0 and len(where) > 0,
      "%d literals in %d files" % (count, len(where)))
check("raw colour literals have not grown past the baseline", count <= RATCHET_BASELINE,
      "%d > %d" % (count, RATCHET_BASELINE))
if count < RATCHET_BASELINE:
    print("   note: %d under baseline — lower RATCHET_BASELINE to %d" % (
        RATCHET_BASELINE - count, count))

print("\n5. RGBA TRIPLES — rgba(var(--x), a) needs --x to be a comma triple")
bad, seen = [], 0
for p in sorted(glob.glob(os.path.join(UI, "**", "*.css"), recursive=True)):
    for m in re.finditer(r"rgba\(\s*var\((--[\w-]+)\)\s*,", blank_comments(read(p))):
        seen += 1
        v = T.get(m.group(1), "")
        # an alias to another triple is fine: follow one hop
        hop = re.fullmatch(r"var\((--[\w-]+)\)", v)
        if hop:
            v = T.get(hop.group(1), "")
        if not re.fullmatch(r"\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}", v):
            bad.append((os.path.basename(p), m.group(1), v or "undefined"))
print("   %d rgba(var(--x), a) uses read" % seen)
# A FLOOR: the stylesheets use this form dozens of times; reading none is a broken glob.
check("the leg read rgba(var(--x), a) uses at all", seen > 0, seen)
check("every rgba(var(--x), a) resolves to a comma triple", not bad, sorted(set(bad)))

finish("G-ROOM-TOKENS")
