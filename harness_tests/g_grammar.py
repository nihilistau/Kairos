"""G-GRAMMAR — the tool grammar, tested against every failure this codebase has ACTUALLY had.

Nothing in here is invented. Every case below is a thing the model really did, that the old
parser really tried to survive by healing, re-prompting or giving up:

    _NAME_SPLIT_RE       'get _time()'  -> healed with a regex
    ```python / ```py    accepted, because the reason-SFT model drifts between fences
    MALFORMED RECOVERY   re-prompt: "[parse error] That call could not be parsed"
    calls[:1]            three calls in one fence: add_note, edit_note, remove_note — she
                         created a note, tidied it, deleted it, all without ever seeing a
                         result, then told him it was done
    "(tool loop exhausted)"   what he actually saw on screen

Four layers of hoping, and every one of them exists for the same reason: the model emits
free text, and free text can be wrong. The grammar's job is to make the wrong ones NOT EXIST
— and, where it cannot yet (until the engine masks), to refuse in a way that TEACHES rather
than one that just says "no".
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("SP_RECALL_REGISTRY", os.path.join(ROOT, "var", "memory", "registry.jsonl"))
os.environ.setdefault("SP_PERSONALITY", "1")

from harness.toolcore.grammar import ToolGrammar, ToolCall, ParseError, FENCE_OPEN  # noqa: E402
from harness.agent import default_tools                                        # noqa: E402

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def fence(code):
    return f"```tool_code\n{code}\n```"


def main() -> int:
    print("G-GRAMMAR - the calls that do not exist cannot be made.\n")
    G = ToolGrammar(default_tools())

    # ── 1. TALKING IS NOT AN ERROR ──────────────────────────────────────────────
    # Most turns have no tool in them. A grammar that treats prose as a parse failure is a
    # grammar that turns a companion into a form.
    check("plain prose is not a parse error, it is a person talking",
          G.parse("I'm good, thanks — I was thinking about your cat.") is None)

    # ── 2. A REAL CALL PARSES INTO A TYPED THING ───────────────────────────────
    r = G.parse(fence('recall(query="what is his name")'))
    check("a valid call parses to a TYPED ToolCall",
          isinstance(r, ToolCall) and r.name == "recall"
          and r.kwargs == {"query": "what is his name"}, str(r))

    # ── 3. A TOOL THAT DOES NOT EXIST IS NOT A PARSE ERROR TO RECOVER FROM ─────
    r = G.parse(fence('recal(query="x")'))
    check("an invented tool name is REFUSED",
          isinstance(r, ParseError) and "no tool called" in r.reason, str(r))
    check("...and the refusal TEACHES (the old one just said 'could not be parsed')",
          isinstance(r, ParseError) and "recall" in r.fixable_hint, r.fixable_hint)

    # ── 4. A PARAMETER THAT DOES NOT EXIST ─────────────────────────────────────
    # THE REAL ONE: she invented adjust_mood(new="calm") and blew the tool loop on a
    # TypeError, because the tool's help lived in a decorator and she never saw the schema.
    r = G.parse(fence('adjust_mood(new="calm")'))
    check("a parameter the tool does not take is REFUSED, not raised as a TypeError",
          isinstance(r, ParseError) and "no parameter" in r.reason, str(r))
    check("...and it names the parameters that DO exist",
          isinstance(r, ParseError) and bool(r.fixable_hint), r.fixable_hint)

    # ── 5. THREE CALLS IN ONE FENCE ────────────────────────────────────────────
    # Live: add_note, edit_note, remove_note in a single block. All three executed. The
    # board came back empty and she told him it was done. I patched it with calls[:1] AFTER
    # parsing. In a grammar it is simply not a legal call.
    r = G.parse(fence('add_note("Defrost the freezer", due="tomorrow 8am")\n'
                      'edit_note("abc", body="x")\n'
                      'remove_note("abc")'))
    check("three calls in one fence is NOT A LEGAL CALL (not a truncation after the fact)",
          isinstance(r, ParseError) and "calls in one block" in r.reason, str(r))
    check("...and it says WHY one call at a time matters",
          isinstance(r, ParseError) and "seen the result" in r.fixable_hint)

    # ── 6. THE THINGS THE HEALERS USED TO PAPER OVER ───────────────────────────
    r = G.parse(fence('get _time()'))
    check("'get _time()' is refused rather than HEALED by a regex",
          isinstance(r, ParseError), str(r)[:60])
    r = G.parse("```python\nrecall(query=\"x\")\n```")
    check("a ```python fence is not a tool call (the drift had nothing stopping it)",
          r is None, "under a mask the fence is FORCED, so there is nothing to drift to")
    r = G.parse(fence('recall(query=some_variable)'))
    check("a non-literal argument is refused (it could execute anything)",
          isinstance(r, ParseError) and "literal" in r.reason, str(r)[:60])

    # ── 7. THE MASK THE ENGINE WILL ENFORCE ────────────────────────────────────
    # Subword-aligned BY CONSTRUCTION: allowed_next returns STRINGS for the caller to
    # tokenise with the model's own tokeniser. DOMINO's central finding is that a mask built
    # over CHARACTERS misaligns with the vocabulary and makes the model measurably worse —
    # which is the operator's exact worry, and it is why this returns words, not a charset.
    opts = G.allowed_next(FENCE_OPEN + "\n")
    check("with the fence open, only REAL tool names are legal",
          opts and all(o in G.tools for o in opts), f"{len(opts)} names")
    check("...a hallucinated name is not merely wrong, it is UNREACHABLE",
          "recal" not in opts and "websearch" not in opts)

    opts = G.allowed_next(FENCE_OPEN + "\nrec")
    check("mid-name, only names that can still be COMPLETED survive",
          opts == ["recall"], str(opts))

    opts = G.allowed_next(FENCE_OPEN + "\nrecall(")
    check("inside the parens, only THAT tool's real parameters are legal",
          opts == ["query="], str(opts))

    # ── 8. THE FREE-TOKEN FAST PATH (this is why it gets FASTER, not slower) ───
    # Where the grammar admits exactly one continuation, no forward pass is needed. DOMINO
    # reports ~2x from this. Computing a 262k-way softmax to discover the only legal token
    # is a waste of a GPU.
    check("after 'recall(' there is exactly ONE legal continuation — it is FREE",
          G.forced(FENCE_OPEN + "\nrecall(") == "query=",
          "no forward pass needed: the model has no choice to make")
    check("...but where she has a real choice, nothing is forced",
          G.forced(FENCE_OPEN + "\n") is None,
          "constraining a genuine decision is how you make a model stupid")

    # ── 9. THE GRAMMAR HAS NO OPINION ABOUT HOW SHE TALKS ─────────────────────
    check("outside a fence the grammar constrains NOTHING",
          G.allowed_next("I've been thinking about") == [],
          "[] means unconstrained. A model that can only fill in forms is not alive.")

    total = len(PASS) + len(FAIL)
    print(f"\nG-GRAMMAR: {'PASS' if not FAIL else 'FAIL'} ({len(PASS)}/{total})")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
