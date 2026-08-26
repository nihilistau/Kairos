"""G-SECRET — the privacy decline must be REACHABLE, not merely implemented.

── THE BUG THIS EXISTS TO MAKE IMPOSSIBLE (2026-07-14) ──────────────────────────────────
spine.recall_decider() protects secrets by checking `mem_class == "private-secret"`, and
memory.py calls the result "confabulation/leak impossible by construction".

lifecycle.classify() — the only classifier the authoritative writer runs — could emit exactly:

    relationship | identity | event | preference | fact

`private-secret` was not among them. THE CONSUMER WAS CHECKING FOR A VALUE THE PRODUCER COULD NOT
PRODUCE. Live registry, 86 rows: zero private-secret. The decline had never fired once, and could
not. Every secret he ever told her was stored as an ordinary `fact` and delivered as ordinary
context.

The class was only ever minted by the DAEMON (recall.rs::classify_mem_class, armed by growth=true).
The "ONE MEMORY AUTHORITY" fix moved writes to the harness and set growth=false — and took the only
producer with it. THE PRIVACY GUARANTEE WAS COLLATERAL DAMAGE OF A CORRECTNESS FIX.

── AND WHY THE EXISTING GATE WAS GREEN THROUGH ALL OF IT ────────────────────────────────
g_mempolicy_v3_offline.py:34,37 does this:

    {"name": "sec1", "mem_class": "private-secret", ...}     <- it BUILDS the row itself

...and then asserts the dispatch honours it. IT TESTS THE DISPATCH. It never asks whether anything
in the system can PRODUCE the class. It was green for weeks certifying a guarantee that did not
exist. Same sin as G-REFLECT setting _LAST_EVIDENCE by hand.

    A GATE THAT SUPPLIES ITS OWN PRECONDITION PROVES ONLY THAT THE GUARD COMPILES.

So this gate NEVER writes mem_class. It says a sentence to remember() and follows the consequences
all the way to the words the model would have seen. §4 is the generalisation and the point of the
whole file: every class the decider branches on MUST be producible by the writer.

    python harness_tests/g_secret.py        (offline: no GPU, no daemon)
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_fd, _reg = tempfile.mkstemp(suffix=".jsonl")
os.close(_fd)
os.environ["SP_RECALL_REGISTRY"] = _reg
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"      # discard port: never needs a GPU
# SP_ENGINE_KIND: no capture attempt at all (2026-08-23). A dead SP_DAEMON_URL does
# NOT make the KV mint cheap - _mint_now still opens a socket per write and Windows
# takes ~2s to give up. Declaring the backend makes supports('capture') False and the
# mint returns immediately: 10 writes in 0.07s against 20s. See gates/README.md.
os.environ["SP_ENGINE_KIND"] = "openai"

from harness.skills import memory as M                       # noqa: E402
from harness.skills import lifecycle as lc                   # noqa: E402
from harness.control.spine import recall_decider, TurnView   # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


def reset():
    open(_reg, "w").close()


def decide(q):
    """What the REAL per-turn decider does with this question. Not a helper. The live path."""
    return recall_decider(min_overlap=0.25)._fn(TurnView(phase="pre", user_text=q))


# ── 1. THE PRODUCER EXISTS ───────────────────────────────────────────────────────────
# The assertion that was missing. Nothing here sets mem_class — remember() must derive it.
print("\n1. a credential he tells her is STORED as a secret (nothing here sets mem_class)")
for sentence in [
    "My PIN is 4471",
    "My password is hunter2",
    "My garage door code is 8812",
    "My api key is sk-abc123def",
    "My seed phrase is olive tractor window",
    "My wife's password is hunter2",          # contains 'wife' -> used to classify RELATIONSHIP
]:
    reset()
    M.remember(sentence, source="user turn")
    row = M._load()[0]
    check("%-42s -> %s" % (repr(sentence[:40]), row.get("mem_class")),
          row.get("mem_class") == "private-secret", row.get("mem_class"))

check("a secret that names a person is still a secret (order is load-bearing)",
      lc.classify("My wife's password is hunter2") == "private-secret")

# The admission gate runs BEFORE the classifier and has its own opinion. An unanchored credential
# ("The garage door code is 8812" — about nobody) is refused at the door by the anti-firehose
# ANCHOR rule, so it is never stored and cannot leak. That is the safe direction and it is
# deliberate (G-ADMISSION), but it is surprising the first time you meet it, so it is pinned here:
# the two guards compose, and the outer one is allowed to win.
_ok, _why = lc.is_memorable("The garage door code is 8812")
check("an unanchored secret is refused at the DOOR, not stored and silently classified",
      not _ok, _why)


# ── 2. AND IT DOES NOT EAT HER PERSONALITY ───────────────────────────────────────────
# The engine's list keys on bare 'code', 'token', 'secret', 'override' and on any token with
# >=2 letters + >=2 digits. Ported verbatim that makes "I write code" a state secret and makes
# her cagey about her own model name. Porting a sloppy rule across a seam gives you two wrong
# systems, not one.
print("\n2. ordinary talk is NOT a secret (the false-positive floor)")
for sentence, want in [
    ("Sam writes code for a living", "not-secret"),
    ("Sam likes the token economy", "not-secret"),
    ("My GPU is an RTX 2060", "not-secret"),
    ("The model is legacy-ref-v1", "not-secret"),          # hyphenated alnum: the engine would flag it
    ("The secret to good pasta is salt", "not-secret"), # 'secret' bare is a turn of phrase
    ("My cat's name is Tuffy", "not-secret"),
]:
    got = lc.classify(sentence)
    check("%-40s -> %s" % (repr(sentence[:38]), got),
          got != "private-secret", got)


# ── 3. END TO END: THE DECLINE ACTUALLY FIRES, ON THE REAL PATH ──────────────────────
# From his sentence, through remember(), through the automatic per-turn decider, to the words
# the model would have been handed. No hand-built rows anywhere in this section.
print("\n3. end to end: he tells her a secret, she does not leak it")
reset()
M.remember("My garage door code is 8812", source="user turn")

decisions = decide("when did I last change the garage door code?")
kinds = [d.kind for d in decisions]
payloads = " ".join(str(d.payload) for d in decisions)

check("the record is a private-secret in the store",
      M._load()[0].get("mem_class") == "private-secret")
check("a question about an attribute the record LACKS -> decline_recall",
      "decline_recall" in kinds, kinds)
check("THE SECRET NEVER APPEARS IN THE PAYLOAD", "8812" not in payloads, payloads[:90])
check("she says so honestly rather than guessing",
      "does not include" in payloads, payloads[:90])

# ...and she is not made useless: asked for the thing itself, she still has it.
decisions = decide("what is the garage door code?")
payloads = " ".join(str(d.payload) for d in decisions)
check("asked for the secret ITSELF, she can still answer him",
      "8812" in payloads, payloads[:90])


# ── 4. THE GENERALISATION — THE ASSERTION THAT WOULD HAVE CAUGHT THIS ────────────────
# The bug was never "the regex is missing". It was that a CONSUMER branched on a vocabulary its
# PRODUCER did not speak, and nothing in the tree compared the two. This is that comparison.
#
# If someone adds a new `if mc == "..."` branch to recall_decider and no classifier can emit it,
# this fails HERE, on the day they write it — not in eight weeks when a secret leaks.
print("\n4. every class the decider BRANCHES ON must be one the writer can PRODUCE")

BRANCHED_ON = ["private-secret", "counterfact"]     # spine.recall_decider's policy dispatch
PRODUCIBLE = {lc.classify(s) for s in [
    "My PIN is 4471", "My wife is Jane", "My name is Sam", "I like fun",
    "I have a flight tomorrow", "The kettle is blue",
]} | {"counterfact"}      # counterfact is DELIBERATELY never auto-assigned: it is an order to
                          # recite, it used to be the default, and 99 of 131 memories became
                          # commands. It is set by hand or not at all. That is a decision, and it
                          # is recorded here so it stays one instead of decaying into this bug.

for cls in BRANCHED_ON:
    check("decider branches on %-16s -> a producer exists" % repr(cls),
          cls in PRODUCIBLE, "NO PRODUCER: recall_decider checks for %r and nothing can emit it" % cls)

check("classify() can emit private-secret (it could not, and that was the bug)",
      "private-secret" in {lc.classify(s) for s in ["My PIN is 4471"]})

# ── 5. THE GUARD HOLDS AT ALL FIVE DOORS, NOT ONE (2026-08-25; audit A3 2026-08-24) ──
# §3 proves the decline on spine.recall_decider — the AUTOMATIC door. The audit found the
# other FOUR read doors in memory.py serving the same row verbatim: list_memories dumped
# it, recall() presented it, search_memories returned its raw text with a match score,
# provenance() quoted it. The guard held on the path that runs without her choosing it
# and on none of the paths she chooses — AGENTS.md §0, in the subsystem whose closed
# trap is the §0 table's last row. The rule now lives in memory.secret_withheld(), one
# function, consumed by every door; this section walks all four with a secret minted
# through remember() (never hand-built — §0 of this file's own doctrine).
print("\n5. the withholding holds at every TOOL door (the decider was one of five)")
reset()
M.remember("My garage door code is 8812", source="user turn")
M.remember("Sam's workshop bench is oak", source="user turn")     # listings need company

ABSENT_Q = "when did I last change the garage door code?"           # attribute NOT in the row

for door, out in [
    ("list_memories", M.list_memories()),                            # a dump asks no attribute
    ("recall", M.recall(ABSENT_Q)),
    ("search_memories", M.search_memories(ABSENT_Q)),
    ("provenance", M.provenance(ABSENT_Q)),
]:
    check("%-16s does not surface the secret's text" % door, "8812" not in out, out[:90])
    check("%-16s says it is HELD, not silently absent" % door,
          M.SECRET_WITHHELD_NOTE in out, out[:90])

# ...and none of that made her useless (G-SECRET §3's other leg, at the tool doors too):
# asked for the thing ITSELF — attribute present — she answers HIM.
check("recall: the direct present-attribute ask still answers him",
      "8812" in M.recall("what is the garage door code?"))
check("search_memories: the direct ask still answers him",
      "8812" in M.search_memories("what is the garage door code?"))
check("...and the innocent row is untouched by the secret rule",
      "oak" in M.list_memories())

# THE IN-GATE MUTANT: every door must CONSULT the rule, not coincidentally hide the row.
# With secret_withheld forced False each door must LEAK — proving the guard is the one
# load-bearing thing between the row and the reply, per door, by name. (The offline
# mutant procedure — break memory.secret_withheld itself, run this file, watch the four
# doors above go red by name, restore — was performed when this section landed.)
_orig_sw = M.secret_withheld
M.secret_withheld = lambda row, query="": False
try:
    for door, out in [
        ("list_memories", M.list_memories()),
        ("recall", M.recall(ABSENT_Q)),
        ("search_memories", M.search_memories(ABSENT_Q)),
        ("provenance", M.provenance(ABSENT_Q)),
    ]:
        check("MUTANT %-16s leaks with the guard lifted (the guard is load-bearing)" % door,
              "8812" in out, out[:90])
finally:
    M.secret_withheld = _orig_sw

os.unlink(_reg)
print("\nG-SECRET  %d/%d" % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
