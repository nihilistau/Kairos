"""G-GAMES — the rules are a ruling, and perft is the committed table that proves it.

WHY PERFT IS THE WHOLE POINT. Every other way of testing a chess engine tells you it
feels right. Perft tells you it IS right: from a fixed position, count every legal move
sequence to depth N and compare against numbers the chess world settled decades ago. One
missing rule, one extra move, one castling right retained a ply too long, and the integer
is wrong. It cannot be argued with, and it is exactly this repo's idea of a verdict —
a ruling of a committed finite table over an order-invariant signature, not prose and not
a magnitude.

THE FIVE POSITIONS ARE NOT ARBITRARY. Each breaks a different naive engine:

  startpos   the baseline. If this is wrong nothing else matters.
  kiwipete   castling under fire, pins, and the one everyone gets wrong — CASTLING RIGHTS
             LOST WHEN A ROOK IS CAPTURED ON ITS HOME SQUARE, not merely when it moves.
  position 3 en passant, including the discovered-check pin that makes an otherwise legal
             en passant illegal.
  position 4 promotion under check, and promotion WITH capture.
  position 5 dense promotion and a cramped king; catches move ordering and legality bugs
             that the open positions hide.

And the wordle half asserts the one rule that file exists for: yellows come from a pool of
UNMATCHED answer letters with greens taken out first, so a guess cannot report more copies
of a letter than the answer holds. Getting that wrong is not cosmetic — it lies about the
hidden state, in the one place the player cannot check.

Offline. No GPU, no daemon. Perft depths are chosen to keep the whole gate near a minute.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import _src as _srcmod  # noqa: E402

SB = os.path.join(tempfile.gettempdir(), "_g_games")
shutil.rmtree(SB, ignore_errors=True)
os.makedirs(SB)
os.environ["SP_GAMES_DIR"] = SB

from harness.games import chess as CH     # noqa: E402
from harness.games import match as M      # noqa: E402
from harness.games import words as WD     # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s %s" % (name, detail))


# ── THE COMMITTED TABLE ──────────────────────────────────────────────────────────
PERFT = [
    ("startpos", CH.START, [20, 400, 8902, 197281]),
    ("kiwipete", "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
     [48, 2039, 97862]),
    ("position 3", "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", [14, 191, 2812, 43238]),
    ("position 4", "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
     [6, 264, 9467]),
    ("position 5", "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
     [44, 1486, 62379]),
]

print("1. PERFT — the node census against numbers the chess world agreed on")
t0 = time.time()
for name, fen, counts in PERFT:
    pos = CH.Position(fen)
    for depth, want in enumerate(counts, 1):
        got = CH.perft(pos, depth)
        check("%s depth %d == %d" % (name, depth, want), got == want, "got %d" % got)
print("   (%.1fs)" % (time.time() - t0))

print("\n2. FEN round-trips, so nothing is lost across a save")
for _, fen, _ in PERFT:
    check("round-trip %s" % fen.split()[0][:22], CH.Position(fen).fen() == fen)

print("\n3. terminal states are RULED, not guessed")
cases = [
    ("checkmate", "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3", "0-1"),
    ("stalemate", "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1", "1/2-1/2"),
    ("insufficient K v K", "7k/8/6K1/8/8/8/8/8 w - - 0 1", "1/2-1/2"),
    ("insufficient K+B v K", "7k/8/6K1/8/8/8/8/5B2 w - - 0 1", "1/2-1/2"),
]
for label, fen, want in cases:
    v = CH.Position(fen).verdict()
    check("%s -> %s" % (label, want), v["over"] and v["result"] == want, v)
check("a live position is NOT over", not CH.Position(CH.START).verdict()["over"])
check("K+N+N v K is not called insufficient (it is not a forced draw)",
      not CH.Position("7k/8/6K1/8/8/8/8/5NN1 w - - 0 1").insufficient())

print("\n4. notation is forgiving on FORM and strict on LEGALITY")
p = CH.Position(CH.START)
for text in ("e4", "e2e4", "e2-e4"):
    check("accepts %r" % text, CH.uci(CH.parse(p, text) or (0, 0, "")) == "e2e4")
check("refuses a legal-looking move that is not legal here", CH.parse(p, "e5") is None)
check("refuses nonsense", CH.parse(p, "banana") is None)
# Knights on b1 AND d1 both reach c3. My first cut used a2/h2, where h2 cannot reach
# c3 at all — so the position was never ambiguous and the gate was wrong, not the code.
amb = CH.Position("4k3/8/8/8/8/8/8/1N1NK3 w - - 0 1")
check("refuses an ambiguous SAN rather than guessing", CH.parse(amb, "Nc3") is None)
check("...and file disambiguation resolves it, both ways",
      CH.uci(CH.parse(amb, "Nbc3") or (0, 0, "")) == "b1c3"
      and CH.uci(CH.parse(amb, "Ndc3") or (0, 0, "")) == "d1c3")
castle = CH.Position("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
check("O-O resolves", CH.uci(CH.parse(castle, "O-O") or (0, 0, "")) == "e1g1")
check("O-O-O resolves", CH.uci(CH.parse(castle, "O-O-O") or (0, 0, "")) == "e1c1")
promo = CH.Position("8/P6k/8/8/8/8/8/K7 w - - 0 1")
check("promotion to a rook is distinguishable from a queen",
      CH.parse(promo, "a8r") is not None and CH.parse(promo, "a8r")[2] == "r")

print("\n5. castling refuses to pass THROUGH check, not merely to land in it")
thru = CH.Position("r3k2r/8/8/8/8/8/5q2/R3K2R w KQkq - 0 1")   # f2 queen hits f1 and d1
ms = {CH.uci(m) for m in thru.legal()}
check("kingside refused (crosses f1)", "e1g1" not in ms)
check("queenside refused (crosses d1)", "e1c1" not in ms)

print("\n6. THE MATCH admits or refuses — it never corrupts a board")
M.new("chess", "t")
for mv in ("e4", "e5", "Nf3", "Nc6", "Bb5"):
    check("plays %s" % mv, M.play("t", mv)["ok"])
bad = M.play("t", "e5")
check("an illegal move is refused", not bad["ok"])
check("...and the refusal CARRIES the legal list", bad.get("legal_count", 0) > 0)
before = M.load("t")["fen"]
M.play("t", "Qz9")
check("a refused move leaves the board untouched", M.load("t")["fen"] == before)

print("\n6b. the cache never outlives the file it came from")
# A plain memoise made load() answer from memory forever while listing() read the
# directory, so a board written from outside this process showed as move 1 of a
# five-move game — confidently. Two copies of one truth, again.
_p = M._path("t")
_out = json.load(io.open(_p, encoding="utf-8"))
_out["history"].append("SENTINEL")
io.open(_p, "w", encoding="utf-8").write(json.dumps(_out))
os.utime(_p, (time.time() + 2, time.time() + 2))
check("an external write is picked up, not served from cache",
      M.load("t")["history"][-1] == "SENTINEL")
_out["history"].pop()
io.open(_p, "w", encoding="utf-8").write(json.dumps(_out))
os.utime(_p, (time.time() + 4, time.time() + 4))
check("...and reverting it is picked up too", M.load("t")["history"][-1] != "SENTINEL")
check("the cache key never reaches the file",
      "_mtime" not in json.load(io.open(_p, encoding="utf-8")))
check("...nor a payload", "_mtime" not in M.public(M.load("t")))

print("\n7. a match survives a restart")
M._CACHE.clear()
check("reloaded from disk", M.load("t") is not None and len(M.load("t")["history"]) == 5)
check("the position came back intact", M.load("t")["fen"] == before)

print("\n8. THE WORDLE POOL RULE — the one that lies about hidden state if wrong")
check("BOBBY vs ABBEY: one green B, exactly one yellow B",
      WD.score("bobby", "abbey") == "y.g.g", WD.score("bobby", "abbey"))
check("BBBBB vs ABBEY: only as many marks as the answer holds",
      WD.score("bbbbb", "abbey").count("g") + WD.score("bbbbb", "abbey").count("y") == 2,
      WD.score("bbbbb", "abbey"))
check("an exact guess is all green", WD.score("abbey", "abbey") == "ggggg")
check("a disjoint guess is all absent", WD.score("crush", "petal").count(".") == 5)
check("every answer is five lowercase letters",
      all(len(w) == 5 and w.isalpha() and w.islower() for w in WD.ANSWERS))
check("no duplicate answers", len(set(WD.ANSWERS)) == len(WD.ANSWERS))
check("the pick is deterministic — a match can be replayed",
      WD.pick("seed-a") == WD.pick("seed-a"))

print("\n9. THE ANSWER IS NOT IN THE PAYLOAD until the game is over")
M.new("wordle", "w")
ans = M.load("w")["answer"]
M.play("w", "crane")
pub = M.public(M.load("w"))
check("hidden while playing", "answer" not in pub)
check("...and not smuggled in another field", ans not in json.dumps(pub))
for _ in range(WD.TRIES):
    if not M.load("w")["over"]:
        M.play("w", "slate" if M.load("w")["history"][-1] != "slate" else "brisk")
check("revealed once it is over", M.public(M.load("w")).get("answer") == ans)

print("\n10. a match id becomes a FILENAME, so it is hashed not sanitised")
for evil in ("../../etc/passwd", "..\\..\\win.ini", ".hidden", "a/b"):
    ap = os.path.realpath(M._path(evil))
    check("contained: %r" % evil[:16],
          ap.startswith(os.path.realpath(M.games_dir()) + os.sep)
          and os.sep not in os.path.basename(ap))

print("\n11. the board renders for the ENCODER, or says it cannot")
from harness.games import render as R    # noqa: E402
out = R.board_png(M.load("t")["fen"], os.path.join(SB, "b.png"), last="f1b5")
if out is None:
    check("PIL absent -> None, so the caller can fall back to text", True)
else:
    check("a PNG is written", os.path.getsize(out) > 4000)
    from PIL import Image
    im = Image.open(out)
    check("square, and large enough to survive a 3x3 pool", im.size[0] == im.size[1] >= 640)
    # A board the encoder cannot read is a board she cannot play from. Low variance is
    # exactly what made a dark terminal screenshot read as 91% uniform.
    import numpy as np
    a = np.asarray(im.convert("L"), dtype="float32")
    check("high contrast — not the low-variance frame the tower fails on", a.std() > 40,
          "std=%.1f" % a.std())

print("\n12. RESIGN, DRAW, TAKEBACK — the three a real game turned out to need")
# NONE of these is derivable from the position: they are agreements between players.
# That is exactly why the position verdict never produced them, why every gate above
# passed without them, and why the gap only appeared when someone played a game to
# the end and had nowhere to put "gg".
M.new("chess", "g")
for mv in ("e4", "e5", "Nf3"):
    M.play("g", mv)
check("resign ends the game", M.resign("g")["ok"] and M.load("g")["over"])
check("...crediting the OTHER side", M.load("g")["result"] == "1-0")   # black was on move
check("...with resignation as the reason", "resign" in M.load("g")["reason"])
check("a resigned game refuses further moves", not M.play("g", "Nc6")["ok"])

M.new("chess", "dr")
M.play("dr", "e4")
off = M.offer_draw("dr")["state"]["draw_offer"]
check("a draw can be offered", off in ("white", "black"))
# THE GUARD THAT LIVED ONLY IN A DOCSTRING on the first cut, which made offer-then-
# accept a one-sided button that ended any game as a draw. A rule written and not
# implemented is the same failure as a knob declared and read by nothing.
check("the offering side CANNOT accept its own offer",
      not M.answer_draw("dr", True, off)["ok"])
check("the opponent can", M.answer_draw("dr", True)["ok"]
      and M.load("dr")["result"] == "1/2-1/2")

M.new("chess", "dc")
M.play("dc", "e4")
M.offer_draw("dc")
check("declining clears the offer and play continues",
      M.answer_draw("dc", False)["ok"] and not M.load("dc")["over"]
      and M.public(M.load("dc"))["draw_offer"] is None)

M.new("chess", "dl")
M.play("dl", "e4")
M.offer_draw("dl")
M.play("dl", "e5")
# An offer is made alongside a move and dies with the reply. Left standing, an offer
# from twenty moves ago could be accepted in a position nobody offered it in.
check("an offer LAPSES when a move is played",
      M.public(M.load("dl"))["draw_offer"] is None)

M.new("chess", "rw")
for mv in ("e4", "e5", "Nf3", "Nc6", "Bb5"):
    M.play("rw", mv)
M.rewind("rw", 2)
st = M.public(M.load("rw"))
check("takeback shortens the history", st["history"] == ["e2e4", "e7e5", "g1f3"])
# BY REPLAY, NOT BY SNAPSHOT — so an INDEPENDENT replay of the shortened list must
# reproduce the stored position exactly. A stack of saved FENs would be a second copy
# of the same truth, and the two would disagree the first time anything else wrote.
_p = CH.Position(CH.START)
for _u in st["history"]:
    _p = _p.apply(CH.parse(_p, _u))
check("...and the position equals an independent replay", _p.fen() == st["fen"])
check("...including the repetition history", len(M.load("rw")["seen"]) == 4)
check("rewinding past the start is refused", not M.rewind("rw", 99)["ok"])

M.new("chess", "mate")
for mv in ("f3", "e5", "g4", "Qh4"):
    M.play("mate", mv)
check("fool's mate is mate", M.load("mate")["over"])
M.rewind("mate", 1)
check("a takeback UN-ENDS a finished game",
      not M.load("mate")["over"] and M.load("mate")["result"] is None)
check("...and play really resumes", M.play("mate", "Nc6")["ok"])

M.new("wordle", "wr")
M.play("wr", "crane")
_ans = M.load("wr")["answer"]
M.resign("wr")
check("resigning wordle reveals the word", M.public(M.load("wr")).get("answer") == _ans)
# A takeback that only thinks about the board forgets the secret has to go back in.
M.rewind("wr", 1)
check("...and a takeback puts it BACK in hiding",
      "answer" not in M.public(M.load("wr")) and not M.load("wr")["over"])

print("\n13. the gateway routes all three")
_app = _srcmod.pkg("harness", "server")
for _op in ('"resign"', '"offer_draw"', '"rewind"'):
    check("op %s is routed" % _op, _op in _app)

shutil.rmtree(SB, ignore_errors=True)
print("\nG-GAMES: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_games.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_games", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
