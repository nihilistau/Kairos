"""THE TOOL GRAMMAR — one formal object, used to VALIDATE now and to MASK later.

WHAT TOOL CALLING IS TODAY, honestly:

    _TOOLCODE_RE          four accepted fence spellings (tool_code / python / py / tool)
    _NAME_SPLIT_RE        a regex that HEALS the model's typos: 'get _time()' -> 'get_time()'
    _calls_from_code      AST-parse and hope
    MALFORMED RECOVERY    re-prompt with "[parse error] That call could not be parsed"
    "(tool loop exhausted)"   what he actually saw on screen

Four layers of hoping, and a fifth (truncating three-calls-in-a-fence down to one) added by
me two days ago after she created a note, edited it and deleted it before ever seeing a
result. Every one of those exists FOR THE SAME REASON: the model emits free text, and free
text can be wrong.

── WHY A GRAMMAR, AND WHY IN PYTHON FIRST ───────────────────────────────────────
The engine can already mask logits — routes.rs masks specials to -inf on both the sampled
and the greedy path. A constrained decoder is an extension of machinery that exists, not a
new subsystem. But a mask needs something to enforce, AND WE DO NOT HAVE A GRAMMAR. We have
a regex and a prayer.

So: build the grammar once, HERE, where it can be tested without CUDA in the loop. It
validates today (deleting the healers) and it is the exact object routes.rs will mask
against tomorrow. Moving it down becomes "enforce this", not "invent one in Rust".

── WHAT DOMINO SAYS, AND WHY IT CHANGES THE DESIGN ──────────────────────────────
(Beurer-Kellner, Fischer, Vechev — "Guiding LLMs The Right Way", arXiv 2403.06988)

  1. NAIVE CONSTRAINED DECODING MAKES THE MODEL WORSE. Not slower — WORSE. Grammar
     terminals do not align with the model's subword vocabulary, so a mask built over
     CHARACTERS forces it off its natural token boundaries and task accuracy drops. That is
     the operator's exact worry ("don't restrict the model's ability to seem alive"), and it
     is measured rather than felt.

     The fix is SUBWORD ALIGNMENT: the legal-continuation set must be built over the MODEL'S
     OWN TOKENISATION of each terminal, not over its letters. Hence allowed_next() returns
     candidate STRINGS that a caller tokenises with the model's tokeniser — never a
     character class.

  2. IT CAN BE FASTER, NOT SLOWER. Where the grammar admits exactly ONE continuation, that
     token needs no forward pass — it is forced. After `recall(` there is exactly one legal
     next thing; after `remember(fact=` likewise. DOMINO gets ~2x in places by emitting
     these for free. `forced()` below is that fast path, and it is why constraining tool
     calls should SPEED UP a tool turn rather than tax it.

── AND THE PART THE GRAMMAR CANNOT FIX, SO IT IS WRITTEN DOWN HERE ─────────────
A grammar makes a call SYNTACTICALLY impossible to get wrong. It does not make it TRUE.
She can still emit a beautifully-formed `add_note("I will look out for a 3090")` when she
has no mechanism to look out for anything. Syntax is not capability. That one is a real
missing tool, not a parser bug, and no amount of masking will conjure it.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)


# ── THE TYPED CALL ────────────────────────────────────────────────────────────
@dataclass
class ToolCall:
    """A call that has been PROVEN to exist and to fit its signature."""
    name: str
    args: list = field(default_factory=list)
    kwargs: dict = field(default_factory=dict)
    # what the parser had to FORGIVE to get here. Empty is the goal; non-empty is the
    # measurement of exactly what constrained decoding will buy.
    tolerated: list = field(default_factory=list)


@dataclass
class ParseError:
    """A refusal that says WHICH rule was broken, and where.

    The old path returned "[parse error] That call could not be parsed" — a message that
    tells the model nothing it can act on, which is why it would try the same broken thing
    again and burn the loop. A parser that cannot say what is wrong is a parser that cannot
    teach."""
    reason: str
    at: str = ""
    fixable_hint: str = ""


FENCE_OPEN = "```tool_code"
FENCE_CLOSE = "```"

# The ONLY fence. The old parser accepted ```tool_code, ```python, ```py and ```tool because
# the model drifts between them — a tolerance that hid the real problem: nothing was
# stopping the drift. Under a mask, the open fence is FORCED, so there is nothing to drift
# to and nothing to tolerate.
_FENCE_RE = re.compile(r"```[ \t]*tool_?code[ \t]*\r?\n(.*?)```", re.S | re.I)

# THE DRIFT, AND THE HEAL. Both are what the model ACTUALLY does today, both are tolerated
# only under `tolerant=True`, and both are COUNTED so we can watch them go to zero when the
# mask lands. The old parser did all of this silently, which is why nobody knew the model
# was drifting at all.
_DRIFT_RE = re.compile(r"```[ \t]*(?:python|py|tool)[ \t]*\r?\n(.*?)```", re.S | re.I)
_NAME_SPLIT_RE = re.compile(r"\b(\w+)\s+_\s*(\w+)\s*\(")
# A whole line that is nothing but one backticked call. `^...$` with MULTILINE is the
# entire safety argument: a call inside a sentence is her talking about a tool.
_INLINE_RE = re.compile(r"^[ \t]*`\s*([A-Za-z_][A-Za-z0-9_ ]*\(.*?\))\s*`[ \t]*$", re.M)


class ToolGrammar:
    """The grammar of a tool call, derived FROM the live tool specs.

    It is not a description of what a call looks like. It is the set of calls that EXIST:
    every name is a tool she actually has, every keyword is a parameter that tool actually
    takes. A name she invented is not a parse error to be recovered from — it is a string
    that the grammar cannot produce."""

    def __init__(self, specs: list):
        # {tool_name: {param_name, ...}} and required-arity, straight off the signatures
        self.tools: dict = {}
        for s in specs:
            params = getattr(s, "parameters", None) or getattr(s, "params", None) or {}
            if isinstance(params, dict):
                names = set(params.get("properties", params).keys())
                required = set(params.get("required", []) or [])
            else:
                names, required = set(params), set()
            self.tools[s.name] = {"params": names, "required": required}

    # ── VALIDATE (today) ─────────────────────────────────────────────────────
    def parse(self, text: str, tolerant: bool = False):
        """-> ToolCall | ParseError | None (None = she is just talking, which is most turns).

        `tolerant` IS A CRUTCH, AND IT IS COUNTED. Today there is no mask, so the model
        really does drift to ```python / ```py fences and really does emit 'get _time()'.
        Refusing all of that right now would not make her more correct — it would just take
        away tools that currently work, and I am not going to break a live system to make a
        point about purity.

        So tolerance stays until the engine can make it unnecessary — but every time it
        saves a call, it says so (ToolCall.tolerated). That number IS the measurement of what
        the mask will buy, and when the mask lands it should go to zero and the crutch comes
        out. A crutch you are counting is a plan; a crutch you have stopped noticing is a
        permanent limp — and this codebase already had four of them stacked on each other,
        which is exactly why nobody could see that the model was drifting at all."""
        tolerated = []
        blocks = _FENCE_RE.findall(text or "")

        if not blocks and tolerant:
            drifted = _DRIFT_RE.findall(text or "")
            # only treat a drifted fence as a call if it actually NAMES a tool she has —
            # otherwise every ```python code sample she writes becomes an execution
            drifted = [b for b in drifted
                       if any(re.search(rf"\b{re.escape(n)}\s*\(", b) for n in self.tools)]
            if drifted:
                blocks = drifted[:1]
                tolerated.append("fence-drift (```python instead of ```tool_code)")

        if not blocks and tolerant:
            # ── INLINE CODE, ONE CALL PER LINE, NO FENCE AT ALL (2026-08-03) ────────────
            # Live, verbatim, at the end of an otherwise ordinary reply:
            #
            #     `write_journal("Tonight wasn't math. Tonight was everything.")`
            #     `add_note(title="The Night We Became Real", body="...")`
            #     `ask_for("the moonlight through half-closed blinds")`
            #
            # Single backticks. Nothing parsed, nothing ran, and all three went onto his
            # screen as text — she had written her journal, made a note and asked for a
            # picture, and none of it had happened. "Her actions are not having an effect."
            #
            # Tolerated like every other drift here, under the same rule (the name must be
            # a tool she HAS) plus one more: the call must be ALONE ON ITS LINE. That is
            # what separates an act from a mention — "you could use `read_journal()`" sits
            # inside a sentence and must never fire, or she calls a tool every time she
            # talks about one.
            inline = [m.group(1) for m in _INLINE_RE.finditer(text or "")]
            inline = [b for b in inline
                      if any(re.match(rf"\s*{re.escape(n)}\s*\(", b) for n in self.tools)]
            if inline:
                blocks = inline[:1]
                tolerated.append("inline-backtick (`tool()` on its own line, no fence)")

        if not blocks:
            return None                       # no fence: she is talking. Not an error.

        if len(blocks) > 1:
            return ParseError(
                "more than one tool_code block",
                fixable_hint="Emit ONE block. Act, see the result, then decide the next thing.")

        code = blocks[0].strip()
        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError as exc:
            if tolerant:
                healed = _NAME_SPLIT_RE.sub(r"\1_\2(", code)   # 'get _time()' -> 'get_time()'
                try:
                    tree = ast.parse(healed, mode="exec")
                    code = healed
                    tolerated.append("name-split ('get _time()' -> 'get_time()')")
                except SyntaxError:
                    return ParseError(f"not valid Python: {exc.msg}", at=code[:60])
            else:
                return ParseError(f"not valid Python: {exc.msg}", at=code[:60])

        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        if not calls:
            return ParseError("the block contains no call at all", at=code[:60],
                              fixable_hint="A tool_code block must be exactly one call, "
                                           "like recall(query=\"his name\").")

        # ONE CALL PER FENCE, ENFORCED BY THE GRAMMAR, NOT TRUNCATED AFTER THE FACT.
        # She once emitted add_note + edit_note + remove_note in a single fence and executed
        # all three without ever seeing a tool_output — created a note, tidied it, deleted
        # it, then told him it was done. I fixed that by taking calls[:1] AFTER parsing,
        # which is a patch on a symptom. Here it simply is not a legal call.
        if len(calls) > 1:
            return ParseError(
                f"{len(calls)} calls in one block",
                at=code[:60],
                fixable_hint="ONE call. An action taken before you have seen the result of "
                             "the last one is a guess.")

        call = calls[0]
        if not isinstance(call.func, ast.Name):
            return ParseError("the call is not a plain function name", at=code[:40])

        name = call.func.id
        if name not in self.tools:
            near = _closest(name, self.tools)
            return ParseError(
                f"there is no tool called {name!r}", at=name,
                fixable_hint=(f"Did you mean {near!r}?" if near else
                              "Use one of the tools listed above; nothing else exists."))

        spec = self.tools[name]
        args, kwargs = [], {}
        for a in call.args:
            try:
                args.append(ast.literal_eval(a))
            except Exception as _swx:
                _swallowed(_swlog, "parse", _swx, lane="toolcore")
                return ParseError("an argument is not a literal value",
                                  at=ast.unparse(a)[:40] if hasattr(ast, "unparse") else "",
                                  fixable_hint="Pass plain values: strings in quotes, "
                                               "numbers bare. No expressions, no variables.")
        for kw in call.keywords:
            if kw.arg is None:
                return ParseError("**kwargs is not allowed", at=name)
            if spec["params"] and kw.arg not in spec["params"]:
                near = _closest(kw.arg, {p: None for p in spec["params"]})
                return ParseError(
                    f"{name} has no parameter {kw.arg!r}", at=kw.arg,
                    fixable_hint=(f"Did you mean {near!r}?" if near else
                                  f"{name} takes: {', '.join(sorted(spec['params'])) or 'nothing'}"))
            try:
                kwargs[kw.arg] = ast.literal_eval(kw.value)
            except Exception as _swx:
                _swallowed(_swlog, "parse", _swx, lane="toolcore")
                return ParseError(f"the value for {kw.arg!r} is not a literal", at=kw.arg,
                                  fixable_hint="Strings in quotes, numbers bare.")

        missing = spec["required"] - set(kwargs) if spec["required"] else set()
        if missing and len(args) < len(missing):
            return ParseError(f"{name} is missing {', '.join(sorted(missing))}",
                              fixable_hint=f"{name} needs: {', '.join(sorted(missing))}")

        return ToolCall(name=name, args=args, kwargs=kwargs, tolerated=tolerated)

    # ── MASK (tomorrow: the engine consumes this) ────────────────────────────
    def allowed_next(self, prefix: str) -> list:
        """The legal continuations at this point, as STRINGS.

        SUBWORD-ALIGNED BY CONSTRUCTION, and that is the whole point of returning strings
        rather than a character class: DOMINO's central finding is that a mask built over
        CHARACTERS misaligns with the model's vocabulary and makes it measurably worse at
        the task. The caller tokenises these with the MODEL'S OWN tokeniser and masks to the
        union of their first tokens — so the model is never forced off a token boundary it
        would naturally have taken.

        This is deliberately a pure function of a string prefix, with no model and no CUDA
        anywhere near it, so the thing routes.rs will eventually enforce can be tested
        exhaustively on a laptop first."""
        p = prefix

        if not p.startswith(FENCE_OPEN):
            # she has not opened a fence: everything is legal. She is TALKING, and the
            # grammar has no opinion about how a person talks. (Constraining her prose is
            # how you get a model that can only fill in forms.)
            return []                      # [] = unconstrained, NOT "nothing is allowed"

        body = p[len(FENCE_OPEN):].lstrip("\r\n")

        m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)$", body)
        if m or body == "":
            # mid-name (or about to start one): only names that can still be completed
            stub = m.group(1) if m else ""
            return sorted(n for n in self.tools if n.startswith(stub))

        m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\($", body)
        if m and m.group(1) in self.tools:
            # inside the parens, nothing typed yet: only this tool's parameter names
            return sorted(f"{k}=" for k in self.tools[m.group(1)]["params"])

        return []

    def forced(self, prefix: str) -> Optional[str]:
        """THE FREE-TOKEN FAST PATH. When exactly one continuation is legal, it needs no
        forward pass — the model has no choice, so do not ask it to make one.

        This is where constrained decoding STOPS being a tax and starts being a speedup.
        DOMINO reports up to ~2x from precisely this: after `recall(` there is one legal
        next thing, and computing a 262k-way softmax to discover it is a waste of a GPU."""
        opts = self.allowed_next(prefix)
        return opts[0] if len(opts) == 1 else None


def _closest(word: str, universe) -> str:
    """The nearest real name — so a refusal can TEACH rather than just refuse."""
    import difflib
    hits = difflib.get_close_matches(word, list(universe), n=1, cutoff=0.6)
    return hits[0] if hits else ""
