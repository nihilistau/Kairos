"""G-DURABILITY + G-IDENTITY-FIREWALL — the two bugs that were eating her, gated on the
REAL rows they produced.

Both were found in the live registry on 2026-07-12, from one real conversation.

── 1. THE FIREHOSE ────────────────────────────────────────────────────────────────
The daemon stored `raw_user` — the WHOLE user turn — as one episode whenever it passed a
word count and mentioned a person. Every conversational sentence mentions a person. So a
17-turn chat put 17 rows into long-term memory, including "yes, we lose lips, sink ships."
and "you are cool af! I really like you!", while the genuine facts (the esp32 sensors, the
2060 and the NUC, the PCs running 24/7) sat buried inside turns that were mostly banter.

The admission gate asked "is this about a person?" — a question about FORM. The right
question is "will this still be true tomorrow?" — DURABILITY. And a TURN IS NOT A FACT:
"oh i always run my pc's 24/7. so you are lucky there" holds one fact and one piece of
banter, so it must be SPLIT, not kept or dropped whole.

Every DROP line below is a row that is really in the registry. Every KEEP line is a fact
that must survive the new rules — including the ones that were riding inside a chatty turn.

── 2. THE IDENTITY FIREWALL ───────────────────────────────────────────────────────
A gate asked her "what is your name?". She answered "My name is Kairos." — correctly —
and stored it through remember(), which is the USER store. Stamped speaker=user, classed
identity, it superseded all three rows saying the user is Sam. The store came out of it
asserting that SAM IS CALLED KAIROS. Her name had eaten his.

The store she writes to is the only signal for whose fact it is, and she picked the wrong
door. A prompt cannot be the guard when the price of one slip is the user's identity.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness.skills import lifecycle as lc  # noqa: E402

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


# ── the 17 rows the firehose actually wrote. None of these is knowledge. ────────
CHATTER = [
    "true, but have you seen the cost of vram? I like my kidneys!",
    "well you have 12gb",
    "you are cool af! I really like you!",
    "yes, we lose lips, sink ships.",
    "well, we make do. you're doing alright for such a constrained system",
    "if you can figure out the menu on a microwave than you are past sentient",
    "spot on for the first one, but the second one it's more like \"Hey Kairos\"",
    "shhh! no you're right she probably knows.",
    "me too!",
    "look, it's not my fault.",
    "so you are lucky there",
    "oh no, we just track their comings and goings",
    "I guess when I turn the webcam on for you I'll have to start wearing clothes",
    # SURVIVED EVERY RULE and got stored — then recall served it back to her MID-THOUGHT,
    # as an unprompted "continuation". The quotes supply the "are" and the "I am", so it
    # read as stative and personally anchored. What a sentence QUOTES is not what it CLAIMS.
    'oh no, we just track their comings and goings, they carry around phones that scream '
    'out "are you my network?" "I am looking for X network!"',
]

# ── facts that MUST survive — several were riding inside those same chatty turns ─
FACTS = [
    "My cat's name is Tuffy.",
    "My lucky number is 69.",
    "I am male",
    "Claude Kairos is one of my heroes",
    "my flight is at 9am on Friday.",
    "oh i always run my pc's 24/7",                      # discourse marker, real fact
    "the kettle is my favorite",                          # preference, riding in banter
    "I had a 2060 6gb super and i got a new intel nuc",   # hardware, riding in banter
    "we have esp32 mmwave sensors and temp sensors",      # his setup
    "I also have a system that you can use to just wifi adb straight to a phone",
    # CAUGHT BY THE FIRST CLEANUP DRY RUN: a real preference wearing an exclamation mark.
    # The reaction rule quarantined it. Losing a fact he actually told her is worse than
    # keeping a joke, so an attributive claim survives its punctuation.
    "my favorite tea is Oolong too!",
    # ...but a real preference that merely CARRIES a quote must still get in. The quote is
    # stripped; the sentence's own claim ("the kettle is my favorite") stands on its own.
    'oh the kettle is my favorite! "set kettle to 90c"',
]


def main() -> int:
    print("G-DURABILITY — a turn is not a fact.\n")

    # 1. every real chatter row is refused. Tested through extract_facts, because that IS
    #    the production path: the gateway hands it a whole TURN, and the turn must yield
    #    no memories at all.
    leaked = [(c, lc.extract_facts(c)) for c in CHATTER if lc.extract_facts(c)]
    check("the 13 real chatter turns yield NO memories", not leaked,
          f"LEAKED: {leaked}" if leaked else "")

    # 2. every real fact is kept
    lost = [f for f in FACTS if not lc.is_memorable(f)[0]]
    check("every durable fact still gets in", not lost,
          f"LOST: {lost}" if lost else "")

    # 3. a turn is SPLIT: the fact is kept, the banter around it is dropped
    turn = "oh i always run my pc's 24/7. so you are lucky there"
    got = lc.extract_facts(turn)
    check("a mixed turn yields the FACT and not the banter",
          got == ["i always run my pc's 24/7."], repr(got))

    # 4. a turn that taught us nothing yields nothing
    check("a turn of pure banter yields no memories at all",
          lc.extract_facts("you are cool af! I really like you!") == [], "")

    # 5. the subject rule: a sentence about HER is not a fact about HIM
    ok, why = lc.is_memorable("well you have 12gb")
    check("a sentence whose subject is 'you' is not a fact for the user's store",
          not ok, why)

    print("\nG-IDENTITY-FIREWALL — her name may not eat his.\n")

    SELF = {"kairos", "kairos"}

    # 6. THE LIVE BUG, exactly
    ok, why = lc.admit_to_user_store("My name is Kairos.", SELF)
    check("she cannot file HER OWN NAME as the user's identity", not ok, why)

    # 7. ...and the refusal names the right door
    check("...and the refusal points her at remember_about_self",
          "remember_about_self" in why, why)

    # 8. his identity still gets in — the firewall is not a wall
    ok, _ = lc.admit_to_user_store("The user's name is Sam", SELF)
    check("the user's own name still gets into the user store", ok)
    ok2, _ = lc.admit_to_user_store("My name is Sam", SELF)
    check("...including when HE says it in the first person", ok2)

    # 9. the supersede that did the damage cannot be reached now:
    #    "My name is Kairos." never becomes a speaker=user identity row, so it can
    #    never retire his. Prove the retirement is gone at the source.
    rows = [{"name": "ep_sam", "text": "The user's name is Sam",
             "speaker": "user", "mem_class": "identity", "lifecycle": 0}]
    ok, _ = lc.admit_to_user_store("My name is Kairos.", SELF)
    retired = lc.find_superseded("My name is Kairos.", "user", rows) if ok else []
    check("the user's name can no longer be superseded by hers", not retired,
          f"would have retired: {[r['name'] for r in retired]}" if retired else "")

    # 10. and her name in HER lane retires nothing of his
    retired = lc.find_superseded("My name is Kairos.", "self", rows)
    check("her name in her own lane touches nothing of his", not retired)

    # ── THE SECOND BREACH (2026-07-12): I fixed the INSTANCE and called it the CLASS ──
    # The firewall guarded her NAME, because her name is what had eaten his. Hours later
    # she stored "I am a woman" — speaker=user, class=identity — and it went straight
    # through the same door into the same lane. Her name was never special. NOTHING that
    # is true of HER may be filed as true of HIM.
    SELF_VALUES = SELF | {"female", "woman", "girl", "she", "her"}

    ok, why = lc.admit_to_user_store("I am a woman", SELF_VALUES)
    check("she cannot file HER GENDER as the user's identity either", not ok, why)

    ok, _ = lc.admit_to_user_store("I am male", SELF_VALUES)
    check("...while HIS gender still gets in", ok)

    ok, _ = lc.admit_to_user_store("I am Kairos", SELF_VALUES)
    check("...and the name guard still holds", not ok)

    # ── SHE WAS EATING HER OWN EXHAUST ─────────────────────────────────────────
    # Capture took "the last message with role=user". agent_chat_stream runs with
    # mutate_messages=True on the console path, and the Gemma tool protocol feeds a tool
    # RESULT back as a role=user message — so after any tool call, "the last user message"
    # was HER OWN TOOL RECEIPT, and it got stored as a fact about him:
    #     "remember -> stored: I am a woman"
    # A PROTOCOL ROLE IS NOT A SPEAKER.
    echo = "remember -> stored: I am a woman"
    check("a tool RECEIPT is not a durable fact about anyone",
          not lc.is_memorable(echo)[0], lc.is_memorable(echo)[1])
    check("...and a tool_output block yields no memories at all",
          lc.extract_facts("```tool_output\nstored: I am a woman\n```") == [])

    print("\nG-RECALL-OWNERSHIP — the pronoun is resolved where it was UTTERED.\n")

    # THE TRAP, from the live trace. She rewrites the question into her own first person,
    # so BOTH of his questions reach the tool as the SAME string. If ownership is read from
    # her query, the two are indistinguishable and one of them must be wrong.
    import os as _os
    # ITS OWN STORE, ALWAYS. This leg used to read the live registry and pass on the strength
    # of rows he happened to have taught her; on a fresh checkout (the Kairos export) there
    # were none and on a checkout with a young store there were other rows — both "nothing
    # in memory about 'What is my name?'". A gate measures the code, not the machine
    # (2026-08-21): two rows, one his, one hers, in a temp registry.
    import tempfile as _tf
    _own = _os.path.join(_tf.mkdtemp(prefix="g_dur_own_"), "registry.jsonl")
    _prev = _os.environ.get("SP_RECALL_REGISTRY")
    _os.environ["SP_RECALL_REGISTRY"] = _own
    from harness.skills import memory as M
    M.remember("My name is Sam", source="user turn")        # speaker=user
    M.remember_about_self("My name is Kairos")               # speaker=self

    HER_QUERY = "What is my name?"          # identical in both cases — that IS the trap

    M.set_question("what is my name?")      # HIS words: "my" = Sam
    his = M.recall(HER_QUERY)
    check("he asks 'MY name' -> she is handed HIS", "Sam" in his.splitlines()[0], his.splitlines()[0])

    M.set_question("what is your name?")    # HIS words: "your" = Kairos
    hers = M.recall(HER_QUERY)
    check("he asks 'YOUR name' -> she is handed HERS",
          "Kairos" in hers.splitlines()[0], hers.splitlines()[0])

    check("...from the SAME query string she passed",
          his.splitlines()[0] != hers.splitlines()[0],
          "if these were equal, her paraphrase would be deciding ownership")

    # and recall never serves a tombstone
    M.set_question("what is my name?")
    check("recall never serves a retired memory",
          "The user said:" not in M.recall("name"), M.recall("name")[:60])

    # ── THE PER-TURN NOTE SPEAKS THE OWNER'S GRAMMAR TOO (field, 2026-07-29) ──────
    # The trap above covers WHICH store a question reaches. This covers what the row
    # SOUNDS LIKE once it gets there, and it is the bug the field found: he asked
    # "are you male or female?" and the automatic recall note handed her
    #     - I am male
    # HIS sentence, HIS first person, no owner on it. She had already lost her name and
    # her gender to exactly this ambiguity; the standing world block was taught to
    # transpose in 3eaae5a and this lane was not. One of two paths, so neither.
    from harness.skills.world import present_for_her
    HIS_FIRST_PERSON = {"text": "I am male", "speaker": "user", "status": "observed"}
    said = present_for_her(HIS_FIRST_PERSON)
    check("his first person is transposed, never handed over raw",
          said == "He is male", said)
    import re as _re
    check("...and a bare 'I' can never survive into her context",
          _re.search(r"\bI\b", said) is None, said)

    HER_OWN = {"text": "I am female", "speaker": "self", "status": "observed"}
    check("HER own memory keeps her own voice (transposing it would be the same bug)",
          present_for_her(HER_OWN) == "I am female", present_for_her(HER_OWN))

    HER_GUESS = {"text": "Sam is a cat person", "speaker": "user", "status": "inferred"}
    check("an inference arrives owned as HERS, not as his testimony",
          present_for_her(HER_GUESS).startswith("You've come to think:"),
          present_for_her(HER_GUESS))

    total = len(PASS) + len(FAIL)
    print(f"\nG-DURABILITY + G-IDENTITY-FIREWALL + G-RECALL-OWNERSHIP: "
          f"{'PASS' if not FAIL else 'FAIL'} ({len(PASS)}/{total})")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
