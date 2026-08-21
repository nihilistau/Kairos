"""CHESS — full legal rules, as a ruling rather than a vibe.

WHY A REAL ENGINE AND NOT A PROMPT. Ask a 26B to "play chess" and it will produce moves
that look like chess and are not: pieces teleport, pins are ignored, a king walks into
check, and the game quietly stops being a game some time around move ten. There is no way
to argue a model out of that, because it is not reasoning about legality — it is
completing text that resembles a game.

So legality is decided HERE, in code, and the model's move is CHECKED against the legal
list. That is the same shape as every other verdict in this repo: a ruling of a committed
table, not prose and not a magnitude. She proposes; the engine rules.

WHAT IS IMPLEMENTED. Everything that decides legality: sliding and stepping pieces,
double pawn push, en passant (including the fact that it expires after one ply), both
castles with all four of their conditions, promotion to all four pieces, and full
self-check filtering. Terminal states are real: checkmate, stalemate, the fifty-move rule,
and insufficient material.

HOW IT IS PROVED. `perft` — the standard node-count census. From a given position, count
every legal move sequence to depth N and compare against numbers the chess world has
agreed on for decades. It is the one test where a single missing rule shows up as a wrong
integer rather than as a game that feels slightly off, and it is exactly a committed
finite table. G-GAMES holds five positions chosen because each one breaks a different
naive implementation.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

Move = Tuple[int, int, str]          # (from, to, promotion piece or "")

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

# Square 0 is a8 and square 63 is h1, which is FEN's own reading order — so parsing is a
# straight walk and there is never a flip to get wrong.
def rf(sq: int) -> Tuple[int, int]:
    return sq >> 3, sq & 7


def sq_name(sq: int) -> str:
    r, f = rf(sq)
    return "abcdefgh"[f] + str(8 - r)


def name_sq(name: str) -> int:
    return (8 - int(name[1])) * 8 + "abcdefgh".index(name[0])


KNIGHT = ((-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1))
KING = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
BISHOP = ((-1, -1), (-1, 1), (1, -1), (1, 1))
ROOK = ((-1, 0), (1, 0), (0, -1), (0, 1))


class Position:
    __slots__ = ("board", "side", "castling", "ep", "half", "full")

    def __init__(self, fen: str = START):
        parts = fen.split()
        rows = parts[0].split("/")
        b: List[str] = []
        for row in rows:
            for c in row:
                if c.isdigit():
                    b.extend("." * int(c))
                else:
                    b.append(c)
        if len(b) != 64:
            raise ValueError("bad FEN board")
        self.board = b
        self.side = parts[1] if len(parts) > 1 else "w"
        self.castling = parts[2] if len(parts) > 2 and parts[2] != "-" else ""
        self.ep = name_sq(parts[3]) if len(parts) > 3 and parts[3] != "-" else None
        self.half = int(parts[4]) if len(parts) > 4 else 0
        self.full = int(parts[5]) if len(parts) > 5 else 1

    def copy(self) -> "Position":
        p = Position.__new__(Position)
        p.board = list(self.board)
        p.side, p.castling, p.ep = self.side, self.castling, self.ep
        p.half, p.full = self.half, self.full
        return p

    def fen(self) -> str:
        rows = []
        for r in range(8):
            row, empty = "", 0
            for f in range(8):
                c = self.board[r * 8 + f]
                if c == ".":
                    empty += 1
                else:
                    if empty:
                        row += str(empty)
                        empty = 0
                    row += c
            if empty:
                row += str(empty)
            rows.append(row)
        return "%s %s %s %s %d %d" % (
            "/".join(rows), self.side, self.castling or "-",
            sq_name(self.ep) if self.ep is not None else "-", self.half, self.full)

    # ── attack detection ────────────────────────────────────────────────────────
    def attacked(self, sq: int, by_white: bool) -> bool:
        """Is `sq` attacked by the given side? Written from the TARGET outwards — ask
        'what could hit me from here', which needs no move list and therefore cannot
        recurse into legality while legality is asking about it."""
        b = self.board
        r, f = rf(sq)
        # pawns: a white pawn on r+1 attacks upward into r
        pr = r + 1 if by_white else r - 1
        if 0 <= pr < 8:
            for df in (-1, 1):
                nf = f + df
                if 0 <= nf < 8 and b[pr * 8 + nf] == ("P" if by_white else "p"):
                    return True
        for dr, df in KNIGHT:
            nr, nf = r + dr, f + df
            if 0 <= nr < 8 and 0 <= nf < 8 and b[nr * 8 + nf] == ("N" if by_white else "n"):
                return True
        for dr, df in KING:
            nr, nf = r + dr, f + df
            if 0 <= nr < 8 and 0 <= nf < 8 and b[nr * 8 + nf] == ("K" if by_white else "k"):
                return True
        for dirs, pieces in ((BISHOP, "BQ" if by_white else "bq"),
                             (ROOK, "RQ" if by_white else "rq")):
            for dr, df in dirs:
                nr, nf = r + dr, f + df
                while 0 <= nr < 8 and 0 <= nf < 8:
                    c = b[nr * 8 + nf]
                    if c != ".":
                        if c in pieces:
                            return True
                        break
                    nr += dr
                    nf += df
        return False

    def king_sq(self, white: bool) -> Optional[int]:
        k = "K" if white else "k"
        try:
            return self.board.index(k)
        except ValueError:
            return None

    def in_check(self, white: Optional[bool] = None) -> bool:
        w = (self.side == "w") if white is None else white
        ks = self.king_sq(w)
        return ks is not None and self.attacked(ks, not w)

    # ── move generation ─────────────────────────────────────────────────────────
    def pseudo(self) -> List[Move]:
        b, out = self.board, []
        white = self.side == "w"
        for sq in range(64):
            c = b[sq]
            if c == "." or c.isupper() != white:
                continue
            r, f = rf(sq)
            u = c.upper()
            if u == "P":
                d = -1 if white else 1
                start_r = 6 if white else 1
                last_r = 0 if white else 7
                one = sq + d * 8
                if 0 <= one < 64 and b[one] == ".":
                    if one >> 3 == last_r:
                        out.extend((sq, one, p) for p in ("q", "r", "b", "n"))
                    else:
                        out.append((sq, one, ""))
                        two = sq + d * 16
                        if r == start_r and b[two] == ".":
                            out.append((sq, two, ""))
                for df in (-1, 1):
                    nf, nr = f + df, r + d
                    if not (0 <= nf < 8 and 0 <= nr < 8):
                        continue
                    t = nr * 8 + nf
                    tc = b[t]
                    if (tc != "." and tc.isupper() != white) or t == self.ep:
                        if nr == last_r:
                            out.extend((sq, t, p) for p in ("q", "r", "b", "n"))
                        else:
                            out.append((sq, t, ""))
            elif u in "NK":
                for dr, df in (KNIGHT if u == "N" else KING):
                    nr, nf = r + dr, f + df
                    if 0 <= nr < 8 and 0 <= nf < 8:
                        t = nr * 8 + nf
                        if b[t] == "." or b[t].isupper() != white:
                            out.append((sq, t, ""))
            else:
                dirs = BISHOP if u == "B" else ROOK if u == "R" else BISHOP + ROOK
                for dr, df in dirs:
                    nr, nf = r + dr, f + df
                    while 0 <= nr < 8 and 0 <= nf < 8:
                        t = nr * 8 + nf
                        if b[t] == ".":
                            out.append((sq, t, ""))
                        else:
                            if b[t].isupper() != white:
                                out.append((sq, t, ""))
                            break
                        nr += dr
                        nf += df
        out.extend(self._castles())
        return out

    def _castles(self) -> List[Move]:
        """All four conditions, because dropping any one of them is the classic bug: the
        right still held, the squares between empty, the king not currently in check, and
        the two squares it CROSSES not attacked. Passing THROUGH check is illegal even
        though the destination is safe."""
        out: List[Move] = []
        white = self.side == "w"
        b = self.board
        if white:
            if "K" in self.castling and b[61] == "." == b[62] and b[60] == "K" and b[63] == "R":
                if not any(self.attacked(s, False) for s in (60, 61, 62)):
                    out.append((60, 62, ""))
            if "Q" in self.castling and b[59] == "." == b[58] and b[57] == "." \
                    and b[60] == "K" and b[56] == "R":
                if not any(self.attacked(s, False) for s in (60, 59, 58)):
                    out.append((60, 58, ""))
        else:
            if "k" in self.castling and b[5] == "." == b[6] and b[4] == "k" and b[7] == "r":
                if not any(self.attacked(s, True) for s in (4, 5, 6)):
                    out.append((4, 6, ""))
            if "q" in self.castling and b[3] == "." == b[2] and b[1] == "." \
                    and b[4] == "k" and b[0] == "r":
                if not any(self.attacked(s, True) for s in (4, 3, 2)):
                    out.append((4, 2, ""))
        return out

    def legal(self) -> List[Move]:
        """THE RULING. Pseudo-legal moves filtered by 'does this leave my own king
        attacked' — which is also what makes pins, discovered checks and the en-passant
        pin fall out for free instead of needing a rule each."""
        white = self.side == "w"
        out = []
        for m in self.pseudo():
            nxt = self.apply(m)
            if not nxt.in_check(white):
                out.append(m)
        return out

    def apply(self, m: Move) -> "Position":
        p = self.copy()
        b = p.board
        frm, to, promo = m
        piece = b[frm]
        white = piece.isupper()
        cap = b[to] != "."

        # EN PASSANT removes a pawn that is not on the destination square — the one
        # capture in chess where the taken piece is somewhere else.
        if piece.upper() == "P" and to == self.ep and not cap:
            b[to + (8 if white else -8)] = "."
            cap = True

        b[to] = promo.upper() if (promo and white) else (promo or piece)
        b[frm] = "."

        if piece.upper() == "K" and abs((frm & 7) - (to & 7)) == 2:
            if to == 62:
                b[61], b[63] = "R", "."
            elif to == 58:
                b[59], b[56] = "R", "."
            elif to == 6:
                b[5], b[7] = "r", "."
            elif to == 2:
                b[3], b[0] = "r", "."

        # Castling rights die when the king or rook MOVES, and also when a rook is
        # CAPTURED on its home square — the half everyone forgets, and the reason
        # perft(3) of the Kiwipete position is the number it is.
        lost = ""
        if piece == "K":
            lost += "KQ"
        elif piece == "k":
            lost += "kq"
        for sq, right in ((63, "K"), (56, "Q"), (7, "k"), (0, "q")):
            if frm == sq or to == sq:
                lost += right
        p.castling = "".join(c for c in p.castling if c not in lost)

        p.ep = None
        if piece.upper() == "P" and abs(frm - to) == 16:
            p.ep = (frm + to) // 2

        p.half = 0 if (piece.upper() == "P" or cap) else self.half + 1
        if not white:
            p.full = self.full + 1
        p.side = "b" if white else "w"
        return p

    # ── terminal states ─────────────────────────────────────────────────────────
    def insufficient(self) -> bool:
        men = [c for c in self.board if c != "."]
        if any(c.upper() in "PRQ" for c in men):
            return False
        minors = [c for c in men if c.upper() in "BN"]
        if len(minors) <= 1:
            return True
        # K+B vs K+B is drawn only when both bishops sit on the same colour complex.
        if len(minors) == 2 and all(c.upper() == "B" for c in minors):
            sqs = [i for i, c in enumerate(self.board) if c.upper() == "B"]
            return ((sqs[0] >> 3) + (sqs[0] & 7)) % 2 == ((sqs[1] >> 3) + (sqs[1] & 7)) % 2
        return False

    def verdict(self) -> Dict[str, object]:
        """The ruling on the POSITION, not on the story so far. Threefold repetition is
        deliberately absent: it is a property of the game's history, so it belongs to the
        match record in state.py, not to a position that does not know how it got here."""
        moves = self.legal()
        if not moves:
            if self.in_check():
                return {"over": True, "result": "0-1" if self.side == "w" else "1-0",
                        "reason": "checkmate"}
            return {"over": True, "result": "1/2-1/2", "reason": "stalemate"}
        if self.half >= 100:
            return {"over": True, "result": "1/2-1/2", "reason": "fifty-move rule"}
        if self.insufficient():
            return {"over": True, "result": "1/2-1/2", "reason": "insufficient material"}
        return {"over": False, "result": None,
                "reason": "check" if self.in_check() else None}


def uci(m: Move) -> str:
    return sq_name(m[0]) + sq_name(m[1]) + (m[2] or "")


def parse(pos: Position, text: str) -> Optional[Move]:
    """Accept a move the way a PLAYER would type it, then rule on it.

    Deliberately forgiving on FORM and absolutely strict on LEGALITY: `e2e4`, `e2-e4`,
    `Nf3`, `O-O`, `exd5`, `e8=Q` all resolve, and anything that is not in the legal list
    comes back None. Being fussy about notation while being loose about rules would be
    exactly the wrong way round."""
    t = (text or "").strip().replace("-", "").replace("=", "").replace("+", "").replace("#", "")
    if not t:
        return None
    legal = pos.legal()
    low = t.lower()
    for m in legal:                                   # UCI, the unambiguous form
        if uci(m).lower() == low:
            return m
    if low in ("oo", "00"):
        return next((m for m in legal if pos.board[m[0]].upper() == "K"
                     and m[1] - m[0] == 2), None)
    if low in ("ooo", "000"):
        return next((m for m in legal if pos.board[m[0]].upper() == "K"
                     and m[0] - m[1] == 2), None)
    # SAN-ish: an optional piece letter, optional disambiguation, optional x, target,
    # optional promotion. Resolved by FILTERING THE LEGAL LIST rather than by parsing
    # into a move — if the filter leaves exactly one, that is the move; ambiguity is a
    # refusal, never a guess.
    body = t.replace("x", "")
    promo = ""
    if body and body[-1] in "QRBNqrbn" and len(body) > 2 and body[-2].isdigit():
        promo, body = body[-1].lower(), body[:-1]
    if len(body) < 2 or not body[-1].isdigit() or body[-2].lower() not in "abcdefgh":
        return None
    target = name_sq(body[-2].lower() + body[-1])
    rest = body[:-2]
    piece = "P"
    if rest and rest[0] in "KQRBN":
        piece, rest = rest[0], rest[1:]
    cands = [m for m in legal
             if m[1] == target
             and pos.board[m[0]].upper() == piece
             and (not promo or m[2] == promo)]
    for hint in rest:                                  # file and/or rank disambiguation
        if hint in "abcdefgh":
            cands = [m for m in cands if (m[0] & 7) == "abcdefgh".index(hint)]
        elif hint.isdigit():
            cands = [m for m in cands if (m[0] >> 3) == 8 - int(hint)]
    return cands[0] if len(cands) == 1 else None


def perft(pos: Position, depth: int) -> int:
    """The census. Every legal sequence to `depth`, counted. A single missing or extra
    rule shows up as a wrong integer instead of as a game that merely feels off."""
    if depth == 0:
        return 1
    if depth == 1:
        return len(pos.legal())
    return sum(perft(pos.apply(m), depth - 1) for m in pos.legal())
