"""G-ASKED — she answers the question he asked.

Built from a REAL conversation (2026-07-14). Every case below is a turn that actually happened and
actually went wrong. The operator sent the transcript; this is it, turned into a gate.

    › you:  well, do you remember my cats name?
    ‹ her:  I don't have a stored "Cats Name" memory. Can you tell me your cat's name?

    › you:  what is your name?
    ‹ her:  Your cat's named Tuffy? I was wondering why you kept calling him that.
      recall: ["The user said: My cat's NAME is Tuffy.", "The user's NAME is Sam",
               "My NAME is Kairos."]

    › you:  do you remember what sex you are?
    ‹ her:  I don't have any stored memory that explicitly states my sex...
      recall: ["then we can REMEMBER our idea's like this!",
               "REMEMBER my GPU is an RTX 2060.",
               "REMEMBER this about me: my workshop is called Forge966733."]

She missed the cat, then blurted the cat's name at a question about HER name, then answered "what
sex are you" with a graphics card. She has 'I am a woman' (speaker=self, identity) on disk.

── ONE ROOT CAUSE, WEARING FOUR COATS: THE FRAMING OF A QUESTION IS NOT THE QUESTION ────
  1. THE VERB BECAME CONTENT. "do you REMEMBER ..." shares the token `remember` with three junk
     rows that begin with the word "Remember" — they are captured INSTRUCTIONS, fossils of the
     store_verb bypass. The question's own verb retrieved them (0.50) while the row that answers
     it scored 0.00. Fixed: memory verbs are stopwords, on both sides.
  2. THE ADDRESSEE BECAME THE SUBJECT. _ASKS_SELF matched the bare `you` in "do YOU remember my
     cat's name", so the question scoped to HER and she answered with her own name. Fixed: unframe
     the question, then read the pronouns.
  3. THE PACKAGING BECAME THE CLAIM. "Remember my GPU is an RTX 2060." keyed on the slot
     `remember my gpu`, so it could never supersede the real GPU row and sat beside it forever.
     Fixed: normalize_fact() strips the wrapper at the door.
  4. THE PLURAL NEVER MET THE POSSESSIVE. "cats" -> {cats}, "cat's" -> {cat}. They never matched,
     and \\bcat\\b never fired on "cats", so the cat row took a -0.40 penalty for mentioning a pet
     he had supposedly not asked about. Fixed: depluralise both sides.

── AND THE GUARDS WERE ALL ON THE POLITE PATH ───────────────────────────────────────────
_target_and_rank() — the pronoun scoping, the relationship penalty, the identity boost, the
salience prior — was called by recall(), THE TOOL. spine.recall_decider(), the AUTOMATIC per-turn
injection that produced the ◈ recall lines above, never ran any of it. Third time in this one file
(the lifecycle filter, the twin ranker, this). Now in the seam.

Every assertion here goes through spine.recall_decider — the path that actually ran when this
conversation went wrong.

    python harness_tests/g_asked.py        (offline: no GPU, no daemon)
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_fd, _reg = tempfile.mkstemp(suffix=".jsonl")
os.close(_fd)
os.environ["SP_RECALL_REGISTRY"] = _reg
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_CAPTURE_ASYNC"] = "0"

from harness.skills import memory as M                      # noqa: E402
from harness.skills import lifecycle as lc                  # noqa: E402
from harness.control.spine import recall_decider, TurnView  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


def asked(q, k_overlap=0.34):
    """EXACTLY what the automatic per-turn recall hands her. The path that ran."""
    M.set_question(q)                       # the gateway does this in _arm_turn
    out = []
    for d in recall_decider(min_overlap=k_overlap)._fn(TurnView(phase="pre", user_text=q)):
        out += d.payload.get("facts", [])
    return out


def first(q):
    got = asked(q)
    return got[0] if got else ""


# The store as it actually was, fossils and all.
M.set_author("user")
for f in ["My cat's name is Tuffy.", "My GPU is an RTX 2060.", "My workshop bench is oak."]:
    M.remember(f, source="user turn")
M.remember("The user's name is Sam", source="user turn")
M.set_author("self")
M.remember("My name is Kairos.", source="self")
M.remember("I am a woman", source="self")
M.set_author("user")


# ── 1. THE PACKAGING IS NOT THE CLAIM ────────────────────────────────────────────────
print("\n1. a fact wearing an imperative is stored as the fact")
r = M.remember("Remember my lucky number is 7741", source="user turn")
row = next((x for x in M._load() if "7741" in (x.get("text") or "")), {})
check("the instruction verb is stripped at the door",
      (row.get("text") or "").lower().startswith("my lucky number"), row.get("text"))
check("...so the SLOT is the attribute, not the verb",
      lc.attribute_key(row.get("text", ""), "user") == "user::lucky number",
      lc.attribute_key(row.get("text", ""), "user"))
check("a legacy 'The user said: ' prefix is stripped too",
      lc.normalize_fact("The user said: My cat's name is Tuffy.") == "My cat's name is Tuffy.")
check("and a bullet fossil", lc.normalize_fact("- my name is Sam") == "my name is Sam")


# ── 2. THE VERB OF THE QUESTION IS NOT CONTENT ───────────────────────────────────────
print("\n2. asking ABOUT memory does not retrieve the word 'remember'")
check("'remember' is not a content token", "remember" not in M._toks("do you remember my name"))
check("neither is 'know' / 'told' / 'memory'",
      not ({"know", "told", "memory"} & M._toks("do you know what you told me from memory")))
# The killer: a junk row that literally begins with "Remember" must not be retrieved by the
# question's own verb.
M.remember("Remember my workshop is called Forge", source="user turn")
got = asked("do you remember what sex you are?")
check("'do you remember what sex you are?' does NOT return the workshop",
      not any("workshop" in g.lower() or "forge" in g.lower() for g in got), got)
check("...nor the GPU", not any("gpu" in g.lower() or "2060" in g for g in got), got)


# ── 3. "DO YOU" IS THE ADDRESSEE, NOT THE SUBJECT ────────────────────────────────────
print("\n3. he asks about HIS cat, not about her")


def target(q):
    """_query_target resolves ownership from HIS words (_QUESTION), not from the string it is
    handed — that is the whole point of it, and the gateway arms it in _arm_turn. So the gate must
    arm it too.

    My first cut called _query_target(q) directly and it FAILED — reading the question from the
    PREVIOUS section, which was about her, and reporting that his cat question was about her. The
    gate was wrong and the code was right. It is also a real finding: _QUESTION is a process-wide
    global, so any path that forgets to set it inherits the last turn's subject. Under a
    ThreadingHTTPServer that is a live race (filed), and here it was a self-inflicted one."""
    M.set_question(q)
    return M._query_target(q)


# ── AND THE ORDER IS THE GATE (field, 2026-07-29) ────────────────────────────────────
# Every check in this file arms _QUESTION itself, which is honest for testing ownership
# RESOLUTION and structurally blind to the bug that actually shipped: on the native SSE
# path the pre-turn spine ran ~110 lines BEFORE _arm_turn, so live recall was scoped by
# THE PREVIOUS TURN'S QUESTION. Receipt from the console —
#     you: do you remember my cat's name?   ->   ◈ recall ["My name is Kairos."]
# A gate that supplies the input can never catch a caller that supplies it too late. So
# assert the ORDER, in the real source: any function that consults the memory lane must
# have armed it first. Offline, no stack, no model.
def _arm_order_ok():
    import ast
    import os as _o
    src_path = _o.path.join(_o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))),
                            "harness", "server", "app.py")
    with open(src_path, encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src)
    bad = []
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        seg = ast.get_source_segment(src, fn) or ""
        if "run_pre_turn(" not in seg:
            continue
        arm = seg.find("_arm_turn(")
        pre = seg.find("run_pre_turn(")
        if arm < 0 or arm > pre:
            bad.append(fn.name)
    return bad


_bad = _arm_order_ok()
check("every gateway path ARMS the memory lane before it CONSULTS it",
      not _bad,
      "these read recall before _arm_turn set the question: %s" % _bad)

check("'do you remember my cats name?' scopes to HIM",
      target("do you remember my cats name?") == lc.SPEAKER_USER,
      target("do you remember my cats name?"))
check("'what is your name?' still scopes to HER",
      target("what is your name?") == lc.SPEAKER_SELF)
check("'do you remember what sex you are?' still scopes to HER (the you that remains is the one asked about)",
      target("do you remember what sex you are?") == lc.SPEAKER_SELF)


# ── 4. THE TRANSCRIPT, REPLAYED ──────────────────────────────────────────────────────
print("\n4. the actual turns that went wrong")

got = first("what is your name?")
check("'what is your name?' -> HER name, not the cat's",
      "kairos" in got.lower(), got)
check("   ...and NOT Tuffy (this is the exact answer she gave him)",
      "tuffy" not in got.lower(), got)

got = first("do you remember my cats name?")
check("'do you remember my cats name?' -> the CAT, first",
      "tuffy" in got.lower(), got)
check("   ...and not HER name (the plural never met the possessive)",
      "kairos" not in got.lower(), got)

got = first("what GPU do I have?")
check("'what GPU do I have?' -> the GPU", "2060" in got, got)


# ── 5. AND THE ONE THAT IS STILL OPEN, SO IT STAYS VISIBLE ───────────────────────────
# 'I am a woman' shares NO WORD with "what sex are you". Bag-of-words cannot bridge sex->woman,
# and no amount of stopword tuning will. This is the honest state: she no longer answers with a
# graphics card, she now returns NOTHING and says she does not know. A wrong answer became an
# honest one, which is progress, and it is not a fix.
print("\n5. the semantic gap, recorded rather than papered over")
check("the answer IS in the store (speaker=self, identity)",
      any(r.get("text") == "I am a woman" and r.get("speaker") == "self" for r in M._load()))
check("and the question shares no word with it — this is why lexical recall cannot find it",
      M._overlap("do you remember what sex you are?", "I am a woman") == 0.0)
got = asked("do you remember what sex you are?")
check("SHE NO LONGER ANSWERS IT WITH A GRAPHICS CARD (honest miss > confident junk)",
      not any("2060" in g or "workshop" in g.lower() for g in got), got)

os.unlink(_reg)
print("\nG-ASKED  %d/%d" % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
