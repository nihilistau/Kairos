"""THE BOARD AS A PICTURE — so she can LOOK at it.

This is the most direct use of the vision tower yet, and it is the reason chess is the
first game rather than the easiest one. She could be handed a FEN, but a FEN is a string
to be parsed and she is bad at that in exactly the way she is bad at legality. A board is
a THING TO SEE, and she has eyes now: `look_at` runs the 27-block ViT and comes back with
a description. He draws, she sees it, they talk about it.

DRAWN FOR THE ENCODER, NOT FOR A HUMAN. The tower resizes to 672x960 and pools 3x3, so
detail below roughly a dozen pixels is gone before the model sees anything. Every choice
here follows from that:

  * BIG glyphs, high contrast, no ornament. A serif knight rendered at board scale
    survives as a grey smudge.
  * The letter of the piece is drawn as well as its symbol, because a white B and a black
    B differ by fill and a pooled patch reports mostly fill.
  * Coordinates in the margin, large. "Which square" is the question she will be asked
    and the answer has to be legible after pooling.
  * A pale board with dark ink. The ambient captures showed the tower does badly on
    low-variance dark frames, which is the same failure that made a dark terminal
    screenshot read as 91% uniform.

PIL only, no cairo, no network. If PIL is missing this returns None and the caller falls
back to the ASCII board — a fallback that only exists in theory is not a fallback.
"""
from __future__ import annotations

import os
from typing import Optional

from harness.games import chess as CH

SQ = 96                      # square size in pixels
MARGIN = 54
SIZE = SQ * 8 + MARGIN * 2

LIGHT = (238, 232, 218)
DARK = (146, 158, 140)
INK = (18, 18, 22)
PALE = (250, 250, 248)
EDGE = (60, 62, 70)
HILITE = (214, 176, 92)

GLYPH = {"K": "♚", "Q": "♛", "R": "♜",
         "B": "♝", "N": "♞", "P": "♟"}


def _font(size: int):
    from PIL import ImageFont
    # DejaVu ships with PIL and carries the chess glyphs; the Windows fallbacks are there
    # because this runs on his machine, not on a CI image.
    for name in ("DejaVuSans.ttf", "seguisym.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size)
    except Exception:
        return None


def board_png(fen: str, path: str, last: Optional[str] = None) -> Optional[str]:
    """Render `fen` to `path`. Returns the path, or None when PIL is unavailable."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None

    pos = CH.Position(fen)
    img = Image.new("RGB", (SIZE, SIZE), PALE)
    d = ImageDraw.Draw(img)
    big = _font(int(SQ * 0.78))
    tag = _font(int(SQ * 0.30))
    coord = _font(int(MARGIN * 0.52))

    hl = set()
    if last and len(last) >= 4:
        try:
            hl = {CH.name_sq(last[:2]), CH.name_sq(last[2:4])}
        except Exception:
            hl = set()

    for r in range(8):
        for f in range(8):
            x0, y0 = MARGIN + f * SQ, MARGIN + r * SQ
            sq = r * 8 + f
            fill = LIGHT if (r + f) % 2 == 0 else DARK
            d.rectangle([x0, y0, x0 + SQ, y0 + SQ], fill=fill)
            if sq in hl:
                # The last move, marked. Without it she cannot answer "what just
                # happened" from the picture alone, only "what is there".
                d.rectangle([x0 + 3, y0 + 3, x0 + SQ - 3, y0 + SQ - 3],
                            outline=HILITE, width=6)
            c = pos.board[sq]
            if c == ".":
                continue
            white = c.isupper()
            g = GLYPH[c.upper()]
            # A filled glyph for black, the same glyph outlined for white — drawn as a
            # halo of offsets rather than as a stroke, because PIL's stroke_width is not
            # available on every build and a missing outline makes the two sides identical
            # after pooling.
            if white:
                for dx in (-3, 0, 3):
                    for dy in (-3, 0, 3):
                        d.text((x0 + SQ * .5 + dx, y0 + SQ * .46 + dy), g,
                               font=big, fill=INK, anchor="mm")
                d.text((x0 + SQ * .5, y0 + SQ * .46), g, font=big, fill=PALE, anchor="mm")
            else:
                d.text((x0 + SQ * .5, y0 + SQ * .46), g, font=big, fill=INK, anchor="mm")
            # THE LETTER TOO. Fill is most of what survives 3x3 pooling, so a white
            # bishop and a black bishop can converge; the letter does not.
            d.text((x0 + SQ - 13, y0 + SQ - 11), c, font=tag,
                   fill=INK if white else PALE, anchor="rs")

    d.rectangle([MARGIN, MARGIN, MARGIN + SQ * 8, MARGIN + SQ * 8], outline=EDGE, width=4)
    for f in range(8):
        x = MARGIN + f * SQ + SQ // 2
        for y in (MARGIN // 2, SIZE - MARGIN // 2):
            d.text((x, y), "abcdefgh"[f], font=coord, fill=EDGE, anchor="mm")
    for r in range(8):
        y = MARGIN + r * SQ + SQ // 2
        for x in (MARGIN // 2, SIZE - MARGIN // 2):
            d.text((x, y), str(8 - r), font=coord, fill=EDGE, anchor="mm")

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    img.save(path)
    return path
