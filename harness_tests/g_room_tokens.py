"""G-ROOM-TOKENS — the room's design system holds its own promises.

THE SPEC: docs/superpowers/specs/2026-09-23-room-redesign-design.md. Ten legs:

  1. CONTRAST. Every text role on every surface is >= 4.5:1 (WCAG AA for the 11-13px
     sizes these roles are used at). Computed from tokens.css, not eyeballed. Plus the
     pairs (2026-09-26, final review): ink on its fill (--on-accent, --on-err), the status
     colours on every surface, the idle window lights >= 3:1 on their bar, and every
     .ui-tone-* chip's text on its OWN tint composited over each surface (the err chip was
     4.47:1 on --surface-3); the mood tone at every hue, 10 degrees apart. And (stage-4
     final review) --text-3 on every accent-tinted selected row (`.X.on` in room.css) over
     the window body, --surface-2: Music's and Files' rows were 4.25:1 at a .10 tint.
  2. ICONS. Every `icon:` in appRegistry names a glyph in kit/icons.jsx; no emoji left.
  3. MOOD. resolveMood's precedence, driven under node; and only room/useMood.js reads
     roomMood.get, because owning the live read is owning the rule (AGENTS.md §0). Plus
     (2026-09-26) roomMood's thinking lifecycle: a mood mid-turn keeps it, only
     set(null, false) — Chat's stream `finally` — ends it.
  4. COLOUR RATCHET — ZERO. No raw colour literal outside kit/tokens.css (spec §6), counting
     template colours; one pinned exemption (Backdrop2D, spec §0), which is also the leg's
     positive control.
  5. RGBA TRIPLES. Every `rgba(var(--x), a)` names a variable that is a comma triple.
     Legs 4 and 5 have floors: counting nothing is a FAIL, not a pass.
     `--es-rgb` was `6 182 212` and made fifty declarations invalid for seven weeks.
  6. VOICES. The machine's words are mono on the chip Chat actually draws (`.act`).
  7. ALIASES. The legacy names are gone from ui/src, and every var(--x) names something
     that exists.
  8. CURSORS. Every cursor rule outside the kit names a kit cursor (or help).
  9. OPACITY. Text dimmed by opacity instead of a text role may only fall.
 10. FONTS. Latin, plus only the subsets her own words use (KEEP names the character that
     needs each): seven faces, seven files, where the package's wght.css shipped eighteen.

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
TEXTS = ["--text-1", "--text-2", "--text-3", "--accent", "--warm",
         # Memory's class marks set text in these three (redesign stage 5); --private also
         # colours her own time's "changed" kind (stage 4)
         "--private", "--feeling", "--self-narrative",
         # Chat's event kinds, the shell's soft red and the desktop tile's glyph (stage 6)
         "--solo", "--recall", "--wear", "--err-soft", "--tile-ink"]
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
        # THE GAME TABLE (stage 6): a card's ink on its face, and a Wordle tile's letter on
        # its mark. The tiles are 19px weight 700 — large text, so 3:1 is their floor.
        table = [("--piece-dark", "--card-face", 4.5), ("--card-red", "--card-face", 4.5),
                 ("--text-1", "--word-hit", 3.0), ("--piece-dark", "--word-near", 4.5)]
        unread_t = [p for p in table if rgb_token(p[0]) is None or rgb_token(p[1]) is None]
        check("the game table's pairs are hex tokens", not unread_t, unread_t)
        lowg = [(a, b, round(ratio(rgb_token(a), rgb_token(b)), 2)) for a, b, floor in table
                if not unread_t and ratio(rgb_token(a), rgb_token(b)) < floor]
        check("the game table reads: card ink >= 4.5:1 on its face, tile letters on their marks", not lowg, lowg)

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
    # Chat's four (stage 6, final wave): her state, recall, wear and her own time.
    need = {"neutral", "accent", "ok", "warn", "err", "an", "mood", "warm", "private", "recall", "wear", "solo"}
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

    # SELECTED ROWS (stage-4 final review, I3): a selected row is tinted with the accent, and
    # its meta is --text-3 (.ui-row-meta, .mus-ta). At .10 over the window body (--surface-2)
    # that measured 4.25:1. Every `.X.on` rule in room.css tinted with --accent-rgb is read
    # and --text-3 measured on it over --surface-2, where a window's rows sit.
    print("   selected rows — --text-3 on each accent-tinted .on row, over the window body")
    ROOM_CSS = os.path.join(UI, "room.css")
    rcss = blank_comments(read(ROOM_CSS)) if os.path.isfile(ROOM_CSS) else ""
    sel = {}
    for m in re.finditer(r"\.([\w-]+)\.on\s*\{([^}]*)\}", rcss):
        b = re.search(r"background\s*:\s*(rgba\(\s*var\(--accent-rgb\)\s*,\s*[\d.]+\s*\))", m.group(2))
        if b:
            sel[m.group(1)] = b.group(1)
    need_rows = {"mus-track", "fl-file"}
    check("the selected-row tints were read from room.css (Music's track, Files' file)",
          need_rows <= set(sel), sorted(need_rows - set(sel)))
    lowr, t3 = [], rgb_token("--text-3")
    for row, expr in sorted(sel.items()):
        pt = paint(expr, 210)
        c = ratio(t3, over(pt[0], pt[1], rgb_token("--surface-2"))) if pt and t3 else 0.0
        print("   %s.on (%s): --text-3 = %.2f:1" % (row, expr, c))
        if c < 4.5:
            lowr.append((row, expr, round(c, 2)))
    check("--text-3 >= 4.5:1 on every accent-tinted selected row over --surface-2", not lowr, lowr)

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
# EVERY GLYPH A WINDOW NAMES EXISTS (stage 6, final wave): <Icon> draws a dashed square for
# a name it does not know, which is a bug nobody sees until it is on screen. Every quoted
# name in an `icon=` / `<Icon name=` / `icon={a ? 'x' : 'y'}` under ui/src, comments blanked.
_named = set()
for p in glob.glob(os.path.join(UI, "**", "*.jsx"), recursive=True):
    # a `/*` closing a string (Chat's accept="image/*") is not a comment: left alone, the
    # blanker read it as one and ate the file down to the next `*/`, composer and all
    src = blank_comments(read(p).replace('/*"', '"'))
    for m in re.finditer(r"""(?:<Icon\s+name|\bicon)=(?:"([\w]+)"|\{([^{}]*)\})""", src):
        _named |= {m.group(1)} if m.group(1) else set(re.findall(r"'(\w+)'", m.group(2)))
check("the leg read the glyphs windows name (Chat's attach, speaker, speakerOff among them)",
      {"attach", "speaker", "speakerOff", "wardrobe"} <= _named, sorted(_named)[:12])
_unglyphed = sorted(n for n in _named if n not in glyphs)
check("every glyph a window names is drawn in icons.jsx", not _unglyphed, _unglyphed)
# NO EMOJI IN CHAT: its buttons were a paperclip and three speakers, and a worn outfit a dress.
# The typographic marks it keeps (the diamond, the fleuron, the triangle, the minus) sit below
# U+1F000 and carry no emoji presentation.
_emoji = sorted({"U+%04X" % ord(ch) for ch in read(os.path.join(UI, "Chat.jsx"))
                 if ord(ch) >= 0x1F000 or ord(ch) == 0xFE0F})
check("no emoji left in Chat.jsx", not _emoji, _emoji)
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
import { resolveMood } from '../../src/room/moodTheme.js'
import * as RM from '../../src/room/roomMood.js'
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
// THE THINKING LIFECYCLE, as Chat drives it: start, a mood mid-turn (the gateway's
// persona event arrives at the TOP of a turn), end. Omitted thinking used to mean false.
const snap = () => ({ ...RM.get() })
RM.set(null, true); out.lc_start = snap()
RM.set('playful'); out.lc_mark = snap()
RM.set(null, false); out.lc_end = snap()
console.log(JSON.stringify(out))
"""
    # under ui/node_modules/.cache, not the repo root (stage-2 review, M1): every tree
    # walker prunes node_modules, so a concurrent scan never meets the probe mid-delete.
    os.makedirs(os.path.join(ROOT, "ui", "node_modules", ".cache"), exist_ok=True)
    pp = os.path.join(ROOT, "ui", "node_modules", ".cache", "_g_room_tokens_probe.mjs")
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
        # 2026-09-26 (stage-2 live check): 0 of 803 samples over a 200 s turn had
        # mood-thinking, because set(mood) reset thinking and the persona event lands first.
        check("a mood arriving mid-turn keeps her thinking",
              g("lc_start", "thinking") is True and g("lc_mark", "thinking") is True
              and g("lc_mark", "mood") == "playful", [data.get("lc_start"), data.get("lc_mark")])
        check("set(null, false) ends thinking and leaves her mood standing",
              g("lc_end", "thinking") is False and g("lc_end", "mood") == "playful", data.get("lc_end"))
chat_src = blank_comments(read(os.path.join(UI, "Chat.jsx")))
check("Chat ends thinking in the stream's finally, on every exit",
      re.search(r"finally\s*\{[^}]*onMood\(\s*null\s*,\s*false\s*\)", chat_src) is not None)

readers = []
for p in sorted(glob.glob(os.path.join(UI, "**", "*.js*"), recursive=True)):
    rel = os.path.relpath(p, UI).replace(os.sep, "/")
    if rel == "room/useMood.js":
        continue
    if re.search(r"\broomMood\.get\b", blank_comments(read(p))):
        readers.append(rel)
check("only room/useMood.js reads roomMood.get", not readers, readers)

print("\n4. COLOUR RATCHET — zero raw colour literals outside kit/tokens.css (spec §6, stage 6)")
# WHAT COUNTS: a hex; rgb()/rgba()/hsl()/hsla() whose first argument is a number; and (stage 6)
# one whose first argument is a TEMPLATE — `hsl(${hue} 80% 55%)` is a literal colour computed
# in JS, which the ratchet did not see until the portrait's eleven were found.
# WHAT DOES NOT: `hsl(var(--mood-h) …)` / `hsl(var(--mhue) …)` / `hsl(var(--h) …)` — a colour
# whose hue is a mood or kind variable is the form spec §2 prescribes, and leg 1 measures the
# kit's at every hue. The hue TABLES in JS (tags.js MOODS/TRAIT_HUE, RUNG_HUE, KIND_HUE) are
# numbers, not colours. The cursor SVGs are images: url() cannot reach a custom property.
COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(\s*(?:\d|\$\{)|\bhsla?\(\s*(?:\d|\$\{)")
# THE ONE EXEMPTION, PINNED. Spec §0 keeps the backdrop renderer out of the redesign, and
# Backdrop2D paints a <canvas>, whose fillStyle cannot resolve var() without a per-frame
# getComputedStyle. So it is counted and pinned: a new literal there fails, and so does one
# fewer (whoever lifts §0 deletes this entry). The pin is also the leg's positive control —
# a regex or glob that stopped seeing the tree cannot match it.
EXEMPT = {"room/Backdrop2D.jsx": 5}
_probe = ["#fff", "rgba(0,0,0,.5)", "hsl(${h} 50% 50%)", "rgb( 1, 2, 3)",
          "rgba(var(--accent-rgb), .2)", "hsl(var(--mood-h) 70% 60%)", "url(#soften)", "var(--x)"]
_hits = [bool(COLOUR.search(s)) for s in _probe]
check("the regex counts literals and templates, and no token expression",
      _hits == [True, True, True, True, False, False, False, False], list(zip(_probe, _hits)))
count, where, exempt = 0, {}, {}
for p in sorted(glob.glob(os.path.join(UI, "**", "*.*"), recursive=True)):
    if not p.endswith((".css", ".jsx", ".js")) or os.path.abspath(p) == os.path.abspath(TOKENS):
        continue
    rel = os.path.relpath(p, UI).replace(os.sep, "/")
    n = len(COLOUR.findall(blank_comments(read(p))))
    if rel in EXEMPT:
        exempt[rel] = n
    elif n:
        where[rel] = n
        count += n
# History, for the record: 290 → raised once to 308 (kit.css's tones) → 186 at stage 4 →
# 147 at stage 5 → 109 (Games, stage 6 1/9) → 88 (Wardrobe, 2/9) → 81 (the closet, 3/9) →
# 34 (Chat's and the shell's furniture, 4/9) → 0 (the portrait, 5/9; the regex began counting
# template colours in the same commit, which is what made Backdrop2D's pin 5 and not 2).
print("   %d literals outside tokens.css (exempt: %s)" % (count, exempt))
for f, n in sorted(where.items(), key=lambda kv: -kv[1])[:8]:
    print("       %4d  %s" % (n, f))
check("the exemption is exactly its pin — the regex and the glob see the tree (positive control)",
      exempt == EXEMPT, "%s != %s" % (exempt, EXEMPT))
check("no raw colour literal outside tokens.css and the one pinned exemption", count == 0, where)

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

print("\n6. VOICES — the machine's words are mono on the chip that is actually drawn")
# 2026-09-26 (stage-2 live check): stage 1 put --font-mono on `.ev`, which no JSX
# draws; her tool line computed to Inter. Since stage 6's final wave each act is a kit Chip
# (whose own font is the UI face), and the words INSIDE it are Chat's: the label a <b>, the
# value `.act-out`. Read the rule that sets their face, and that Chat draws exactly those.
room_css = blank_comments(read(os.path.join(UI, "room.css")))
act = re.search(r"(?:^|\})\s*\.acts b\s*,\s*\.act-out\s*\{([^}]*)\}", room_css)
check("the event chips' word rule (.acts b, .act-out) exists", act is not None)
check("the event chips' words are mono", act is not None and "var(--font-mono)" in act.group(1))
chat_jsx = blank_comments(read(os.path.join(UI, "Chat.jsx")))
check("Chat draws its events as kit chips holding those words",
      re.search(r'<Chip key=\{j\} tone="accent" title=\{String\(ev\.tool\.result[^>]*>\s*<b>\{ev\.tool\.name', chat_jsx) is not None
      and chat_jsx.count('<span className="act-out') == 7)

print("\n7. ALIASES — the legacy names are gone, and every var() names something that exists")
# Spec §1: the console-era names and the --es-* set were aliases onto the roles from day one,
# "stage 6 deletes them". Deleted 2026-09-27. A name coming back — defined OR used — fails,
# anywhere under ui/src, comments blanked (the src-trap). The legacy console pages
# (console/index.html, ops.html) keep their own :root and are not under ui/src.
ALIASES = ["--bg", "--panel", "--line", "--ink", "--muted", "--cyan", "--cyan-dim", "--gold", "--off",
           "--es", "--es-rgb", "--es-glow", "--es-amber", "--es-red", "--es-green", "--es-ink",
           "--es-dim", "--es-900", "--es-800"]
_alias = re.compile(r"(?<![\w-])(" + "|".join(re.escape(a) for a in sorted(ALIASES, key=len, reverse=True)) + r")(?![\w-])")
SRCS = {os.path.relpath(p, UI).replace(os.sep, "/"): blank_comments(read(p))
        for p in sorted(glob.glob(os.path.join(UI, "**", "*.*"), recursive=True)) if p.endswith((".css", ".jsx", ".js"))}
roles_used = sum(len(re.findall(r"var\(--(?:accent|text-[123]|hair|surface-[0-3])\b", s)) for s in SRCS.values())
check("the leg reads the tree (positive control: the roles are used, >= 200 times)", roles_used >= 200, roles_used)
alias_hits = sorted({(f, m.group(1)) for f, s in SRCS.items() for m in _alias.finditer(s)})
check("no legacy alias is defined or used anywhere under ui/src", not alias_hits, alias_hits[:8])
# EVERY var(--x) NAMES SOMETHING. Found while planning stage 6: Wardrobe's var(--edge, #444)
# and var(--mono, …) named properties nothing had ever defined, so the fallback always ran.
defined = set(T) | {m for f, s in SRCS.items() if f.endswith(".css") for m in re.findall(r"(--[\w-]+)\s*:", s)}
runtime = {m for s in SRCS.values() for m in re.findall(r"""['"](--[\w-]+)['"]""", s)}   # style={{'--h': …}}, setProperty
uses = [(f, m.group(1)) for f, s in SRCS.items() for m in re.finditer(r"var\(\s*(--[\w-]+)", s)]
check("the leg read var() uses (floor)", len(uses) >= 300, len(uses))
undefined = sorted({u for u in uses if u[1] not in defined | runtime})
check("every var(--x) names a property some stylesheet defines or the room sets at runtime", not undefined, undefined[:8])
# PAINT IS NOT A ROLE: the game table's and the portrait's colours are read only where they paint.
table = sorted({f for f, s in SRCS.items() for _ in re.finditer(r"var\(--(?:board|piece|card|word)-", s)})
check("the game table's paint is read only by room.css", table == ["room.css"], table)
_rc = SRCS.get("room.css", "")
_table_sel = [sel.strip() for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", _rc)
              if re.search(r"var\(--(?:board|piece|card|word)-", body)
              for sel in sel.split(",") if not sel.strip().startswith(".gm-")]
check("...and only by .gm- rules", not _table_sel, _table_sel)
face = sorted({f for f, s in SRCS.items() if "var(--face-" in s})
check("the portrait's paint is read only by room/Avatar.jsx", face == ["room/Avatar.jsx"], face)
face_defined = {n for n in T if n.startswith("--face-")}
face_used = set(re.findall(r"var\((--face-[\w-]+)\)", SRCS.get("room/Avatar.jsx", "")))
check("every --face- token is used, and every one used exists", face_defined == face_used and face_defined,
      {"unused": sorted(face_defined - face_used), "undefined": sorted(face_used - face_defined)})

print("\n8. CURSORS — a per-class cursor names a kit cursor, never the system keyword it replaces")
# 2026-09-24 (stage 0): the kit's cursors "reach only surfaces with no more specific cursor:
# rule of their own"; room.css had 69 such rules. The kit's family (arrow, hand, text, no,
# busy, the grips) is what every rule outside it must name. `help` stays: the kit has none.
OK_CURSOR = re.compile(r"var\(--cur-[\w-]+\)|help|inherit|none|auto")
bad_c, n_c = [], 0
for rel in ("room.css", "room/shell.css"):
    for m in re.finditer(r"cursor\s*:\s*([^;}]+)", blank_comments(read(os.path.join(UI, rel)))):
        n_c += 1
        if not OK_CURSOR.fullmatch(m.group(1).strip()):
            bad_c.append((rel, m.group(1).strip()))
check("the leg read cursor rules (floor: the shell's grips alone are 10)", n_c >= 10, n_c)
check("no per-class cursor falls back to a system keyword the kit replaces", not bad_c, bad_c)

print("\n9. OPACITY — dimming by opacity instead of a text role may only fall")
# Opacity under a text colour defeats leg 1: --text-3 at .55 is not --text-3. Counted in
# room.css and shell.css, outside @keyframes and outside :disabled (WCAG 1.4.3 exempts an
# inactive control). Not all of what is left is text, and some is his call (the follow-up
# list in the stage-6 CHANGELOG); the ratchet keeps the list honest and short.
OPACITY_BASELINE = 12  # measured 2026-09-27 (stage 6; 16 once `opacity: 0` counted: the lights' svg; 12 after the final wave put Chat on the kit); lowering it is the only edit allowed
# THE DIMS THEMSELVES, pinned (final wave, M4): a count alone let one dim be swapped for another
# at the same total. Every dim found must be one of these; one that leaves must leave here too
# (the list and the baseline are the same number, checked below).
PINNED_DIMS = {
    ("room.css", ".mark.minus", ".55"), ("room.css", ".turn.solo", ".82"),
    ("room.css", ".thinking summary", ".55"), ("room.css", ".thinking summary:hover", ".85"),
    ("room.css", ".thinking-body", ".7"), ("room.css", ".sd-down-mark", ".8"),
    ("room.css", ".jr-drafts", ".55"), ("room.css", ".dec-done", ".55"),
    ("room/shell.css", ".dsk-drag", ".75"), ("room/shell.css", ".win > .bar .lt svg", "0"),
    ("room/shell.css", ".win > .g-se::after", ".5"), ("room/shell.css", ".win:hover > .g-se::after", ".9"),
}
# HIS DESIGN CALLS — dims a review measured and left to him, by name. They are printed on
# their own line and pinned here, never folded into the baseline, so the number above
# cannot quietly carry a decision nobody made. An entry leaves when he decides (and the
# stale check below fails if the rule changes without this list changing with it).
HIS_CALLS = {
    ("room.css", ".lgr-s-dropped", ".42"),   # stage 5: a dropped ledger row reads 3.5:1 / 1.9:1, its restore button dimmed with it
}
# Any value below 1: `0`, `0.x` and `.x`. The first cut matched only `0?\.\d+`, so a bare
# `opacity: 0` (hidden outright, the deepest dim there is) was invisible to it (fix round 1).
# `1`, `1.0` and `var(...)` never match. Non-text dims (a drag ghost, an image, the lights'
# hover glyph) are counted like the rest: the leg does not judge text-ness, the list does.
OPACITY_DIM = re.compile(r"(?<![\w-])opacity\s*:\s*(0(?:\.\d+)?|\.\d+)(?![\w.])")


def opacity_dims(rel, src):
    """(dims, rules) in one stylesheet: every opacity < 1 outside @keyframes and :disabled."""
    s = blank_comments(src)
    s = re.sub(r"@keyframes[^{]*\{(?:[^{}]*\{[^}]*\})*[^}]*\}", "", s)
    out, n = [], 0
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", s):
        n += 1
        for m in OPACITY_DIM.finditer(body):
            if ":disabled" not in sel:
                out.append((rel, " ".join(sel.split())[-60:], m.group(1)))
    return out, n


# POSITIVE CONTROL, in the same collection: a text rule hidden by `opacity: 0` is a dim.
_pc, _ = opacity_dims("control", """
.pc-zero { color: var(--text-2); opacity: 0; }   .pc-lead { opacity: 0.5; }  .pc-bare { opacity: .5 }
.pc-one { opacity: 1; }  .pc-onept { opacity: 1.0; }  .pc-var { opacity: var(--o); }
.pc-off:disabled { opacity: 0; }  @keyframes pc-in { from { opacity: 0; } to { opacity: 1; } }
""")
check("control: opacity 0, 0.5 and .5 are counted; 1, 1.0, var(), :disabled and @keyframes are not",
      [(x[1], x[2]) for x in _pc] == [(".pc-zero", "0"), (".pc-lead", "0.5"), (".pc-bare", ".5")], _pc)
dims, rules_read = [], 0
for rel in ("room.css", "room/shell.css"):
    _d, _n = opacity_dims(rel, read(os.path.join(UI, rel)))
    dims += _d
    rules_read += _n
his = [x for x in dims if x in HIS_CALLS]
dims = [x for x in dims if x not in HIS_CALLS]
print("   %d opacity dims in %d rules (baseline %d)" % (len(dims), rules_read, OPACITY_BASELINE))
for x in dims:
    print("       %s  %s  %s" % x)
print("   his design calls, still dimmed by opacity (named, not in the baseline):")
for x in his:
    print("       %s  %s  %s" % x)
check("the leg read the stylesheets (floor)", rules_read >= 300, rules_read)
check("opacity dims have not grown past the baseline", len(dims) <= OPACITY_BASELINE,
      "%d > %d" % (len(dims), OPACITY_BASELINE))
check("the pinned list is the baseline (one number, written twice, must agree)",
      len(PINNED_DIMS) == OPACITY_BASELINE, "%d pinned, baseline %d" % (len(PINNED_DIMS), OPACITY_BASELINE))
_unpinned = sorted(x for x in dims if x not in PINNED_DIMS)
check("every opacity dim is one of the pinned ones (a swap at the same count fails)", not _unpinned, _unpinned)
_gone = sorted(x for x in PINNED_DIMS if x not in dims)
check("no pinned dim is stale: one that left was taken off the list", not _gone, _gone)
check("his design calls are named and still true — .lgr-s-dropped { opacity: .42 } among them",
      sorted(his) == sorted(HIS_CALLS), {"listed": sorted(HIS_CALLS), "found": sorted(his)})
_named = [x for x in dims if re.search(r"\.stg-rung|\.stg-n\b|\.stg-dwell|\.stg-hook|\.sty-row\.gone", x[1])]
check("Stage's ladder and Story's retired lines dim by role, not opacity (stage-4/5 ledger)", not _named, _named)

print("\n10. FONTS — latin, plus the subsets her own words use; nothing the room never renders")
# Spec §1 says latin only. Measured at the cut (2026-09-27) over what the room renders: the
# Memory and Research windows (Inter) show her own words, which carry latin-ext (ș ć đ, in
# place names and surnames) and Greek (Φ), and one Ledger row quotes a Cyrillic і; so Inter keeps those four
# subsets and the rest go. Her voice (Source Serif, Chat) keeps latin-ext as well (controller
# ruling, fix round 1): she speaks from those memories. The mono carries no character
# outside latin in anything the room shows today. A subset joins KEEP only with the
# character that needs it named beside it.
KEEP = {
    ("inter", "latin"), ("jetbrains-mono", "latin"), ("source-serif-4", "latin"),
    ("inter", "latin-ext"),   # Memory: ș ć đ (her registry); Research/Search: ă ć ș ō đ (her looks)
    ("inter", "greek"),       # Memory: Φ (her registry); Research: β ψ (her looks)
    ("inter", "cyrillic"),    # Ledger: the quoted homoglyph і in one row's body
    ("source-serif-4", "latin-ext"),   # her voice in Chat: an accented name from her memories (ș ć đ) stays in her face
}
FJS, FCSS = os.path.join(UI, "kit", "fonts.js"), os.path.join(UI, "kit", "fonts.css")
fjs = blank_comments(read(FJS))
fcss = blank_comments(read(FCSS)) if os.path.isfile(FCSS) else ""
faces = re.findall(r"@font-face\s*\{([^}]*)\}", fcss)
urls = [u.strip("'\" ") for u in re.findall(r"url\(([^)]+)\)", fcss)]
got = set()
for u in urls:
    m = re.search(r"@fontsource-variable/([\w-]+)/files/\1-([\w-]+)-wght-normal\.woff2$", u)
    got.add((m.group(1), m.group(2)) if m else ("?", u))
check("fonts.js imports the kit's fonts.css and no package stylesheet",
      "./fonts.css" in fjs and "@fontsource" not in fjs, fjs.strip()[:120])
check("one face per kept subset, each the package's own -wght-normal file",
      len(faces) == len(urls) == len(KEEP) and got == KEEP,
      {"extra": sorted(got - KEEP), "missing": sorted(KEEP - got)})
check("each latin face carries the latin unicode-range",
      fcss.count("unicode-range: U+0000-00FF") == 3)
_pkg_ranges, _mismatch = 0, []
for fam, sub in sorted(KEEP):
    pcss = os.path.join(ROOT, "ui", "node_modules", "@fontsource-variable", fam, "wght.css")
    if not os.path.isfile(pcss):
        continue
    pm = re.search(r"/\* %s-%s-wght-normal \*/\s*@font-face\s*\{[^}]*?(unicode-range:[^;]+;)"
                   % (re.escape(fam), re.escape(sub)), read(pcss))
    mine = [f for f in faces if "/files/%s-%s-wght-normal." % (fam, sub) in f]
    _pkg_ranges += 1
    if not pm or not mine or pm.group(1) not in mine[0]:
        _mismatch.append((fam, sub))
if _pkg_ranges:
    check("each face's unicode-range is the package's own, verbatim", not _mismatch, _mismatch)
else:
    print("   (no ui/node_modules: the verbatim unicode-range check has nothing to compare)")
check("the three families are the ones tokens.css names",
      all(("font-family: '%s'" % f) in fcss for f in ("Inter Variable", "JetBrains Mono Variable", "Source Serif 4 Variable")))
woffs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "console", "room", "assets", "*.woff2")))
_wset = {(fam, sub) for fam, sub in KEEP for w in woffs if w.startswith("%s-%s-wght-normal-" % (fam, sub))}
check("the committed bundle ships exactly the kept files (%d woff2)" % len(KEEP),
      len(woffs) == len(KEEP) and _wset == KEEP, woffs)

finish("G-ROOM-TOKENS")
