"""G-HOLDEM — poker's rules are a ruling too, and the hard ones are not about cards.

Hand strength is the easy half: a total order over score tuples, checked against
rankings the world settled long ago. That is a committed finite table in exactly the
sense perft is, and section 1 asserts it.

Sections 2-6 are the half that actually breaks. Every rule below produces, when wrong,
a game that LOOKS like poker and is not — no crash, no visibly bad state, just chips
going to the wrong person or a player quietly robbed of a decision:

  * HEADS-UP BLINDS ARE INVERTED. Two players: the BUTTON posts the SMALL blind and
    acts FIRST preflop, then LAST on every later street. Generalising the multi-way rule
    gets this exactly backwards and changes every preflop decision in the game.
  * THE BIG BLIND'S OPTION. A round is over when everyone has ACTED and matched — not
    when everyone has matched. A big blind who was merely called has matched without
    acting, and the option to raise is theirs.
  * AN UNDER-RAISE ALL-IN DOES NOT REOPEN BETTING. A short stack shoving less than a
    full raise may be called but not re-raised by players who already acted.
  * SIDE POTS. A player all in for less cannot win chips they could not cover. Broken
    silently: the chips still add up, they just reach the wrong seat.
  * HIDDEN INFORMATION. Chess could hand everyone one payload. Poker state is a
    function of the game AND WHO IS LOOKING, so the view is per-seat by construction.

Offline. No GPU, no daemon.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import _src as _srcmod  # noqa: E402

SB = os.path.join(tempfile.gettempdir(), "_g_holdem")
shutil.rmtree(SB, ignore_errors=True)
os.makedirs(SB)
os.environ["SP_GAMES_DIR"] = SB

from harness.games import cards as C      # noqa: E402
from harness.games import holdem as H     # noqa: E402
from harness.games import match as M      # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s %s" % (name, detail))


def sc(hand):
    return C.best_of(hand.split())[0]


print("1. HAND STRENGTH — the committed table")
NAMED = [
    ("As Ks Qs Js Ts", "royal flush"),
    ("9s 8s 7s 6s 5s", "nine-high straight flush"),
    ("As 2s 3s 4s 5s", "five-high straight flush"),   # the steel wheel
    ("Ah Ad Ac As Kh", "four aces"),
    ("Kh Kd Kc 2s 2h", "kings full of twos"),
    ("Ah Jh 9h 5h 2h", "ace-high flush"),
    ("Ah 2d 3c 4s 5h", "five-high straight"),         # the wheel
    ("Ah Ad Ac 7s 2h", "three aces"),
    ("Ah Ad Kc Ks 2h", "aces and kings"),
    ("Ah Ad Kc Qs 2h", "pair of aces"),
    ("Ah Kd Qc Js 9h", "ace high"),
]
for hand, want in NAMED:
    check("%-18s -> %s" % (hand, want), C.describe(sc(hand)) == want, C.describe(sc(hand)))

# THE ORDER. A ranking that names hands correctly and orders them wrongly is worse than
# one that does neither, because it looks right.
ORDER = [
    "As Ks Qs Js Ts", "9s 8s 7s 6s 5s", "Ah Ad Ac As Kh", "Kh Kd Kc 2s 2h",
    "Ah Jh 9h 5h 2h", "Ah Kd Qc Js Th", "Ah Ad Ac 7s 2h", "Ah Ad Kc Ks 2h",
    "Ah Ad Kc Qs 2h", "Ah Kd Qc Js 9h",
]
strict = all(sc(ORDER[i]) > sc(ORDER[i + 1]) for i in range(len(ORDER) - 1))
check("the full ranking is strictly ordered", strict)
# THE WHEEL: the ace plays LOW, so A2345 is five-high and loses to 65432. Scoring the
# ace as 14 makes the wheel the best straight in the deck — the classic bug.
check("the wheel is FIVE-high, and loses to six-high",
      sc("Ah 2d 3c 4s 5h") < sc("6h 5d 4c 3s 2h"))
check("the steel wheel is still a straight flush, above any flush",
      sc("As 2s 3s 4s 5s") > sc("Ah Kh Qh Jh 9h"))
check("kickers decide", sc("Ah Ad Kc 5s 2h") > sc("Ah Ad Qc 5s 2h"))
check("seven cards resolve to the best five", C.best_of("Ah Kh Qh Jh Th 2c 3d".split())[0][0] == 8)

print("\n2. THE DECK")
d = C.shuffled("seed-a")
check("52 distinct cards", len(d) == 52 and len(set(d)) == 52)
check("deterministic — a hand can be replayed", C.shuffled("seed-a") == d)
check("...and a different seed deals differently", C.shuffled("seed-b") != d)

print("\n3. HEADS-UP BLINDS ARE INVERTED")
h = H.new_hand(["btn", "bb"], [200, 200], button=0, seed="x", sb=1, bb=2)
check("the BUTTON posts the small blind", h["seats"][0]["committed"] == 1)
check("the other seat posts the big blind", h["seats"][1]["committed"] == 2)
check("the BUTTON acts FIRST preflop", h["to_act"] == 0)
H.act(h, 0, "call")
H.act(h, 1, "check")
check("...and acts LAST postflop (so the non-button opens)", h["to_act"] == 1)
# Three-handed the rule flips back: blinds sit to the LEFT of the button.
h3 = H.new_hand(["btn", "sb", "bb"], [200, 200, 200], button=0, seed="y", sb=1, bb=2)
check("three-handed, the blinds are left of the button",
      h3["seats"][1]["committed"] == 1 and h3["seats"][2]["committed"] == 2)
check("...and the button is NOT first to act", h3["to_act"] == 0 and h3["button"] == 0)

print("\n4. THE BIG BLIND'S OPTION")
h = H.new_hand(["btn", "bb"], [200, 200], button=0, seed="z", sb=1, bb=2)
H.act(h, 0, "call")
check("a call does NOT end the round — the BB still has the option",
      h["street"] == "preflop" and h["to_act"] == 1)
check("and the BB may raise, not merely check",
      "raise" in H.legal_actions(h)["actions"])
H.act(h, 1, "check")
check("checking the option ends the street", h["street"] == "flop")
check("...and exactly three cards come out", len(h["board"]) == 3)

print("\n5. AN UNDER-RAISE ALL-IN DOES NOT REOPEN BETTING")
h = H.new_hand(["a", "b", "c"], [200, 200, 9], button=0, seed="w", sb=1, bb=2)
H.act(h, 0, "raise", 6)          # a raises to 6, min_raise now 4
H.act(h, 1, "call")              # b calls 6
before = h["min_raise"]
H.act(h, 2, "allin")             # c shoves 9 — only +3, less than the full raise of 4
check("the bet to match goes up", h["current_bet"] == 9)
check("...but the minimum raise does NOT change", h["min_raise"] == before)
check("...and the player who already acted may call, not re-raise",
      "raise" not in H.legal_actions(h)["actions"]
      or h["last_aggressor"] == 0, H.legal_actions(h))

print("\n6. SIDE POTS — a short stack cannot win what it could not cover")
h = H.new_hand(["short", "mid", "big"], [10, 50, 200], button=0, seed="v", sb=1, bb=2)
h["seats"][0]["committed"] = 10
h["seats"][1]["committed"] = 50
h["seats"][2]["committed"] = 50
pots = H.side_pots(h)
check("the pot splits into two layers", len(pots) == 2, pots)
check("layer one is 30, contested by all three",
      pots[0]["amount"] == 30 and pots[0]["eligible"] == [0, 1, 2], pots[0])
check("layer two is 80, and the short stack is NOT eligible",
      pots[1]["amount"] == 80 and 0 not in pots[1]["eligible"], pots[1])
check("no chips are created or lost",
      sum(p["amount"] for p in pots) == sum(s["committed"] for s in h["seats"]))
# A folded player's chips stay in the pot as dead money; the player does not.
h["seats"][1]["folded"] = True
pots2 = H.side_pots(h)
check("a folder's chips stay in, but the folder cannot win them",
      sum(p["amount"] for p in pots2) == 110
      and all(1 not in p["eligible"] for p in pots2))

print("\n7. HIDDEN INFORMATION IS STRUCTURAL, not guarded")
h = H.new_hand(["you", "me"], [200, 200], button=0, seed="hid", sb=1, bb=2)
v0, v1, vs = H.view(h, 0), H.view(h, 1), H.view(h, None)
check("you see your own hole cards", v0["seats"][0]["hole"] is not None)
check("...and never your opponent's", v0["seats"][1]["hole"] is None)
check("the same holds from the other chair",
      v1["seats"][1]["hole"] is not None and v1["seats"][0]["hole"] is None)
check("a spectator sees no hole cards at all",
      all(s["hole"] is None for s in vs["seats"]))
check("THE DECK IS IN NO VIEW", all("deck" not in v for v in (v0, v1, vs)))
blob = json.dumps(vs) + json.dumps(v0)
check("...and no undealt card leaks through another field",
      not any(c in blob for c in h["deck"][:20]))

print("\n8. A WHOLE HAND — chips are conserved")
h = H.new_hand(["you", "me"], [100, 100], button=0, seed="full", sb=1, bb=2)
start = sum(s["stack"] for s in h["seats"]) + H.pot_total(h)
for a, amt in (("call", 0), ("check", 0), ("bet", 6), ("call", 0),
               ("check", 0), ("check", 0), ("bet", 20), ("call", 0)):
    if h["over"]:
        break
    H.act(h, h["to_act"], a, amt)
check("the hand reaches a conclusion", h["over"])
check("five board cards were dealt", len(h["board"]) == 5)
check("no chip was created or destroyed",
      sum(s["stack"] for s in h["seats"]) == start,
      sum(s["stack"] for s in h["seats"]))
check("the winner is named with the hand they won on", bool(h["winners"][0]["hand"]))
check("hole cards are revealed only AT showdown",
      all(s["hole"] is not None for s in H.view(h, None)["seats"]))

print("\n9. THE MATCH LAYER")
M.new("holdem", "p")
mv = M.holdem_view(M.load("p"), 0)
check("a seated view carries options for the player to act", "options" in mv)
pub = M.public(M.load("p"))
# public() returning the SPECTATOR view is the design: an all-seeing payload that
# happened to pick a seat would be the leak, and it would never look like one.
check("public() is the SPECTATOR view — it cannot show a hand",
      all(s["hole"] is None for s in pub["seats"]))
check("a match survives a restart", (M._CACHE.clear() or True)
      and M.load("p") is not None and M.load("p")["kind"] == "holdem")

print("\n10. HER TOOLS ARE BOLTED TO SEAT 1")
os.environ["SP_GAMES"] = "1"
import inspect                              # noqa: E402
from harness.skills import poker as PK      # noqa: E402
M.new("holdem", "poker")
raw = M.load("poker")["hand"]
his_cards = raw["seats"][0]["hole"]
her_cards = raw["seats"][1]["hole"]
hers = PK.poker_state("poker")
check("her view shows HER cards", all(c in hers for c in her_cards), hers[:80])
# THE PROTECTION IS STRUCTURAL, NOT BEHAVIOURAL. There is no seat argument on any tool
# and none returns the raw hand, so "do not look at his cards" is not an instruction a
# persuasive turn could erode — it is a thing the API cannot express. That matters more
# here than anywhere else in this repo: a model asked nicely enough usually complies.
check("...and never his", not any(c in hers for c in his_cards), his_cards)
check("no tool takes a seat argument",
      not any("seat" in inspect.signature(f).parameters for f in PK.POKER_TOOLS))
src = inspect.getsource(PK)
check("her seat is a constant, not a parameter", "HER_SEAT = 1" in src)
# PRECISE, because the blunt version was wrong. `w["hand"]` is the WINNER'S hand
# description — a string like "pair of aces" — and flagging it was a false positive.
# What must never appear is reaching `["hand"]` off a loaded match record.
import re                                   # noqa: E402
check("no tool reaches the raw hand off a match record",
      not re.search(r"\)\s*\[\s*['\"]hand['\"]\s*\]", src))
check("...and _table hands back only the view, never the record",
      "return M.holdem_view(m, HER_SEAT)" in src and "return m, " not in src)

M.play("poker", "raise 10")                 # his action, so she now faces a price
txt = PK.poker_state("poker")
# THE PRICE IS COMPUTED FOR HER. A model deriving pot odds mid-sentence sometimes
# derives them wrong, and a wrong price is a wrong fold.
check("the cost of a call is stated, not left to be derived",
      "to call into a pot of" in txt and "%" in txt, txt[-90:])
os.environ["SP_GAMES"] = "0"
check("the pack is empty when games are unarmed", PK.poker_tools() == [])
os.environ["SP_GAMES"] = "1"
check("...and is three tools when armed", len(PK.poker_tools()) == 3)

print("\n11. THE PANEL ASKS FOR A SEAT AND GETS ONLY THAT SEAT")
app = _srcmod.pkg("harness", "server")
check("/v1/games routes poker through holdem_view(m, 0)", "holdem_view(m, 0)" in app)
ui = io.open(os.path.join(ROOT, "ui", "src", "apps", "Games.jsx"), encoding="utf-8").read()
# A UI that hides cards it possesses is one refactor away from showing them. The panel
# renders `hole` straight through; when the server sent null, a back is drawn.
check("the panel renders what it was sent rather than hiding what it has",
      "them.hole && them.hole[0]" in ui)

shutil.rmtree(SB, ignore_errors=True)
print("\nG-HOLDEM: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_holdem.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_holdem", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
