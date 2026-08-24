"""
Ephemeral Tool Calling
=====================

Tool calling for backends without a native ``tool_calls`` finish reason (the
sp-daemon emits plain text). Tools are *ephemeral*: attached to a single
generation, advertised in the system prompt, parsed back out of the model's
output, executed, and the result fed in for the next round. No persistent
registration with the backend.

Protocol (the model is instructed to emit, on its own line)::

    <tool name="read_file">{"path": "main.py"}</tool>

The loop runs each tool, appends an observation, and re-prompts until the
model stops emitting tool calls or ``max_rounds`` is hit.
"""

from __future__ import annotations

import ast
import inspect
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from harness.inference.client import SPDaemonClient, get_client
from harness.inference.inference_config import InferenceConfig

logger = logging.getLogger(__name__)

# THE BUDGET'S LAST RESORT (2026-08-24 audit, S4). Both tool loops read
# agent.tool_budget_s from the tuning registry and both fell back to a hand-copied
# 150.0 if the registry failed to import — the number the registry itself moved OFF
# because it was measured to break the feature ("150 s bought ONE round ... the
# opposite of the request, and invisible without reading the log"). A fallback that
# reverts to the measured-bad value on an import error is a regression with a fuse.
# One constant, the registry's own number, both loops.
TOOL_BUDGET_FALLBACK_S = 400.0

# Gemma-native: the model wraps calls in a ```tool_code fenced block (Python-style
# calls), and results return in ```tool_output. This is what Gemma is trained to emit.
# We also accept the legacy <tool …>{json}</tool> form as a fallback.
# Fence tolerance (AUDIT + live console 2026-07-10): the reason-SFT model emits
# '``` tool_code', '```toolcode', '```tool code', and — when generation hits
# max_tokens mid-block — UNCLOSED fences. (?:```|\Z) accepts the truncated tail.
_TOOLCODE_RE = re.compile(r"```[ \t]*tool[-_ ]?code\s*(.*?)(?:```|\Z)", re.DOTALL | re.IGNORECASE)  # live census: also 'Tool-Code'
_TOOL_RE = re.compile(r'<tool\s+name="([^"]+)"\s*>(.*?)</tool>', re.DOTALL)
# ```python / ```py / ```tool fences are accepted ONLY when the parsed call names are
# known tools (see _parse_tool_calls(known=...)) so code-example answers pass through.
_ANYFENCE_RE = re.compile(r"```[ \t]*(?:python|py|tool)[ \t]*\n?(.*?)(?:```|\Z)", re.DOTALL | re.IGNORECASE)
# live mutation 'get _time()' — heal a space split around an underscore in a call name.
_NAME_SPLIT_RE = re.compile(r"\b(\w+)\s+_\s*(\w+)\s*\(")


def _edits(a: str, b: str, cap: int = 2) -> int:
    """Levenshtein distance, giving up once it exceeds `cap`.

    Small and local rather than imported: this runs on every unresolved tool name, the
    strings are under thirty characters, and a dependency for twelve lines of DP is a
    dependency to keep working."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def near_tools(tool_index: Dict[str, "ToolSpec"], name: str, cap: int = 2) -> list:
    """Every tool name within `cap` edits, nearest first. The suggestion list."""
    n = (name or "").lower()
    scored = [(_edits(n, k.lower(), cap), k) for k in tool_index]
    return [k for d, k in sorted(scored) if d <= cap]


def resolve_tool(tool_index: Dict[str, "ToolSpec"], name: str) -> Optional["ToolSpec"]:
    """Exact, then normalized (case/underscore/hyphen-insensitive), then ONE near miss.

    The 12B emits 'gettime()' for get_time; don't fail the round on a typo.

    ── AND A TRANSPOSED LETTER COST HER A WHOLE TURN (2026-08-05) ──────────────────────
    Live, asked to look in her own wardrobe and put something on:

        check_wardrobre -> [unknown tool: check_wardrobre — available: add_note, ...]
        check_wardrobre -> [unknown tool: check_wardrobre — available: add_note, ...]
        [nothing was said this turn]

    One inserted 'r'. She spent both her rounds on it, the budget ended the turn, and he
    got no reply at all. The normaliser above strips underscores and case — it cannot see
    a letter that should not be there.

    This is the SAME finding as `wear(outfit=…)`, one level up: she knew the tool, she
    knew what she wanted, and the only thing wrong was the spelling of the name. That was
    healed at the parameter and left unhealed at the identifier, so the identical failure
    was waiting one layer above the fix — AGENTS.md §0 with the two paths stacked rather
    than side by side.

    THE SAME RULE AS THE KEYWORD HEALER, TOO: heal only when there is nothing to choose
    between. Exactly one tool within two edits is not a guess, it is the only thing she
    could have meant. Two candidates is real ambiguity and must refuse — silently picking
    one would run the wrong tool and look like it worked, which is worse than an error.
    """
    spec = tool_index.get(name)
    if spec is not None:
        return spec

    def norm(s: str) -> str:
        return s.lower().replace("_", "").replace("-", "")
    n = norm(name)
    for k, v in tool_index.items():
        if norm(k) == n:
            return v
    # A name too short to be safe is left alone: at three characters almost everything is
    # within two edits of everything else, and "one candidate" stops meaning anything.
    if len(n) >= 6:
        near = near_tools(tool_index, name, cap=2)
        if len(near) == 1:
            logger.info(
                "[tools] %r is not a tool; exactly one thing is within two edits (%s) "
                "— taking it", name, near[0])
            return tool_index[near[0]]
    return None


def unknown_tool_note(tool_index: Dict[str, "ToolSpec"], name: str) -> str:
    """What she reads when a name resolves to nothing.

    IT USED TO BE A WALL OF FORTY-SEVEN NAMES. Live, on `check_wardrobre`:

        [unknown tool: check_wardrobre — available: add_note, adjust_mood, ask_for,
         ask_for_gesture, check_wardrobe, click, delegate_code, due_reminders, ...]

    Everything she needed was in there, in alphabetical order, one item away from the
    thing she had typed — and she emitted the identical typo on the next round. A list
    that contains the answer is not the same as an answer. Naming the nearest candidates
    makes the next round a correction instead of a repeat, which is exactly what the
    slot-naming TypeError does one level down.

    Only reached when `resolve_tool` found NOTHING or found several, so a suggestion here
    is genuinely a choice she has to make rather than one already made for her."""
    near = near_tools(tool_index, name, cap=3)
    if near:
        return ("[there is no tool called '%s'. Did you mean %s? Call it with that exact "
                "spelling.]" % (name, " or ".join("'%s'" % k for k in near[:3])))
    return ("[there is no tool called '%s', and nothing close to it. The ones you have "
            "are: %s]" % (name, ", ".join(sorted(tool_index))))


# ──── ToolSpec ────────────────────────────────────────────────────────────
@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]
    fn: Callable

    def call(self, *args: Any, **kwargs: Any) -> str:
        # COOLDOWN, at the ONE place every tool call passes through. Put anywhere
        # else and it would be enforced on one path and not another, which is
        # AGENTS.md §0's bug class and has already cost this repo a recall filter
        # and a privacy guarantee. Only a handful of tools have a period at all —
        # the ones that point a camera at his room, or cost half a minute.
        try:
            from harness.toolcore.cooldown import COOLDOWNS
            wait = COOLDOWNS.check(self.name)
            if wait:
                return wait
        except Exception:
            pass                      # a rate limiter must never block a tool
        # ── A WRONG KEYWORD IS NOT A FAILED INTENT (2026-08-04) ──────────────────────
        # Live, asked to put on the silver nightie, she produced:
        #     wear [tool error: wear() got an unexpected keyword argument 'outfit']
        #     wear [tool error: wear() got an unexpected keyword argument 'item']
        #     (tool loop exhausted)
        # She knew the tool, she knew the garment, and `wear(what="silver nightie")`
        # resolves it correctly — the ONLY thing wrong was the name of the slot. She then
        # apologised to him for her "clumsy hands" while the wardrobe worked perfectly.
        #
        # So: if the tool takes exactly ONE parameter and she passed exactly one keyword
        # that is not it, there is no ambiguity about what she meant. Put it in the slot.
        # This is not guessing on her behalf — with one parameter there is nothing to
        # guess between, and the alternative is a turn spent apologising.
        #
        # AT THE SEAM, not in the tools. `adjust_mood(mood="", **kw)` already absorbs a
        # wrong guess, ad hoc, in ONE tool — the same shim the wardrobe needed and did
        # not have. A rule you must remember to add to each tool is a rule most tools
        # will not have (AGENTS.md §0), and this is the one place every call passes.
        props = list(self.parameters.get("properties", {}).keys())
        if len(props) == 1 and len(kwargs) == 1 and not args:
            (given,) = kwargs
            if given != props[0]:
                logging.getLogger(__name__).info(
                    "[tool] %s(%s=) -> %s(%s=) — one slot, no ambiguity",
                    self.name, given, self.name, props[0])
                kwargs = {props[0]: kwargs[given]}
        try:
            out = str(self.fn(*args, **kwargs))
        except TypeError as exc:
            # NAME THE SLOTS. "unexpected keyword argument 'outfit'" says what is wrong
            # and never what is right, so the next attempt is another guess — which is
            # exactly the loop she got stuck in. One clause turns a dead end into a
            # correction she can act on next round.
            if "argument" in str(exc):
                shape = "%s(%s)" % (self.name, ", ".join(props)) if props else f"{self.name}()"
                return f"[tool error: {exc}. The correct call is {shape} — use those names.]"
            return f"[tool error: {exc}]"
        except Exception as exc:
            return f"[tool error: {exc}]"
        try:
            from harness.toolcore.cooldown import COOLDOWNS
            COOLDOWNS.mark(self.name)
        except Exception:
            pass
        return out

    def advertise(self) -> str:
        params = ", ".join(self.parameters.get("properties", {}).keys())
        return f'- {self.name}({params}): {self.description}'

    def signature(self) -> str:
        """Gemma-style Python signature line for the tool preamble."""
        ps = []
        props = self.parameters.get("properties", {})
        req = set(self.parameters.get("required", []))
        ann_of = {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}
        for p, meta in props.items():
            ann = ann_of.get(meta.get("type"), "str")
            ps.append(f"{p}: {ann}" + ("" if p in req else " = None"))
        return f"def {self.name}({', '.join(ps)}):  # {self.description}"

    @classmethod
    def from_callable(cls, fn: Callable, name: str = "", description: str = "") -> "ToolSpec":
        sig = inspect.signature(fn)
        props: Dict[str, Any] = {}
        required: List[str] = []
        type_map = {str: "string", int: "integer", float: "number", bool: "boolean"}
        for pname, p in sig.parameters.items():
            # **kwargs IS NOT A PARAMETER SHE CAN PASS. adjust_mood(mood="", **kw) exists so
            # a reasonable guess (new=/value=/to=) is absorbed instead of raising TypeError —
            # a good shim. But `kw` was leaking into the ADVERTISED schema, so the tool block
            # she reads every turn said "adjust_mood takes: kw, mood". We handed her an
            # invented parameter, in the one tool that had already broken her loop by hiding
            # the real ones. Found by the grammar, which now derives its rules from this
            # schema and therefore has to be told the truth.
            if p.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL):
                continue
            base = p.annotation
            base = getattr(base, "__args__", [base])[0] if getattr(base, "__origin__", None) else base
            props[pname] = {"type": type_map.get(base, "string")}
            if p.default is inspect.Parameter.empty:
                required.append(pname)
        return cls(
            name=name or fn.__name__,
            description=description or (fn.__doc__ or "").strip().split("\n")[0],
            parameters={"type": "object", "properties": props, "required": required},
            fn=fn,
        )


# ──── Registry (scoped tool selection) ────────────────────────────────────
class ToolRegistry:
    """Builds ephemeral tool sets, including from the skill registry."""

    def __init__(self) -> None:
        self._specs: Dict[str, ToolSpec] = {}

    def register(self, fn: Callable, name: str = "", description: str = "") -> ToolSpec:
        spec = ToolSpec.from_callable(fn, name, description)
        self._specs[spec.name] = spec
        return spec

    def load_from_skills(self, pack: str = "", names: Optional[List[str]] = None) -> int:
        from harness.skills.registry import SKILL_REGISTRY
        metas = (
            [SKILL_REGISTRY.get_skill(n) for n in names] if names
            else SKILL_REGISTRY.get_pack_metas(pack) if pack
            else list(SKILL_REGISTRY._by_name.values())  # noqa: SLF001
        )
        count = 0
        for m in metas:
            if m is None:
                continue
            self._specs[m.name] = ToolSpec.from_callable(m.func, m.name, m.description)
            count += 1
        return count

    def specs(self, names: Optional[List[str]] = None) -> List[ToolSpec]:
        if names:
            return [self._specs[n] for n in names if n in self._specs]
        return list(self._specs.values())


_REGISTRY: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ToolRegistry()
    return _REGISTRY


# ──── The loop ────────────────────────────────────────────────────────────
def _tool_preamble(tools: List[ToolSpec]) -> str:
    """Gemma-native tool preamble: advertise Python signatures, ask for a ```tool_code block."""
    sigs = "\n".join(t.signature() for t in tools)
    # Concrete example built from the FIRST tool's real signature, so the model copies a
    # real call (not the placeholder param name "arg").
    example = "func()"
    if tools:
        t0 = tools[0]
        props = list(t0.parameters.get("properties", {}).keys())
        example = f'{t0.name}({props[0]}="value")' if props else f"{t0.name}()"
    return (
        "You have access to these Python functions (and ONLY these):\n\n"
        + sigs +
        "\n\nWhen you decide to call a function, output it in a fenced block EXACTLY like this:\n"
        "```tool_code\n" + example + "\n```\n"
        # NO PREAMBLE — and this is a UI bug, not a style preference. The streaming
        # agent decides tool-round-vs-answer by whether a fence has appeared, and it
        # releases the hold after a fixed number of fence-free characters. Prose
        # before a call ("I need to check the room history first, since I don't have
        # a timestamp...") is therefore FLUSHED TO THE USER as though it were the
        # answer, with the fence arriving after. Streamed tokens cannot be unsent, so
        # the real cure is to stop her writing them.
        "The fenced block must be the FIRST thing you write — no lead-in, no "
        "\"let me check\", no saying what you are about to do. Think it, then call it; "
        "you get your turn to talk when the result comes back.\n"
        "Use the REAL parameter names from the signatures above (not placeholder names). "
        "Then STOP. The result returns to you as:\n```tool_output\n...result...\n```\n"
        "Rules: call a function INSTEAD of writing the code or answer yourself, then wait for the "
        "tool_output. Pass arguments as Python literals (strings in quotes). When the tool_output "
        "comes back, answer using ONLY its exact values — never invent or substitute. Do not call "
        "functions that are not listed above."
    )


# ──── OKFS-tiered tool loading (LUT -> gist -> full) ──────────────────────
# The same three-tier shape as MEM-OKF: a tiny always-loaded INDEX (name + one-line gist) of the
# tools an agent COULD use, a few CORE tools advertised in full up front, and `load_tools` to pull
# the FULL signature of any other tool on demand. This keeps the system prompt small (the 1189-token
# "inline every signature" preamble is what stalled the gateway) and lets the model load only the
# minimum, expanding as needs come up. The executor (tool_index) still holds EVERY tool, so once the
# model has seen a signature it can call it. This is the project-wide pattern: load the gist, expand
# to full only when required.
def _make_load_tools(all_specs: Dict[str, "ToolSpec"]) -> "ToolSpec":
    """The meta-tool: reveal the FULL signature(s) of named tools on demand (the OKFS 'full' tier)."""
    def load_tools(names: str) -> str:
        wanted = [x.strip() for x in str(names).replace(";", ",").replace(" ", ",").split(",") if x.strip()]
        out = []
        for n in wanted:
            spec = all_specs.get(n)
            out.append(spec.signature() if spec else f"# no tool named '{n}'")
        return "\n".join(out) if out else "# usage: load_tools(\"name1,name2\")"
    return ToolSpec.from_callable(
        load_tools, "load_tools",
        "Reveal how to call other tools by name (comma-separated), then call them")


def build_tool_system(
    core: List["ToolSpec"],
    extra: Optional[List["ToolSpec"]] = None,
    system_prefix: str = "",
    system_suffix: str = "",
) -> tuple:
    """OKFS-tiered tool context. Returns (system_content, tool_index).

    CORE tools are advertised with full signatures (always loadable). EXTRA tools appear only as a
    one-line gist INDEX (LUT); the model calls ``load_tools("name")`` to get an extra's full
    signature, then calls it. ``tool_index`` can execute ANY of them (core + extra + load_tools)."""
    extra = extra or []
    all_specs: Dict[str, ToolSpec] = {t.name: t for t in (list(core) + list(extra))}
    load_tools_spec = _make_load_tools(all_specs)
    tool_index: Dict[str, ToolSpec] = dict(all_specs)
    tool_index[load_tools_spec.name] = load_tools_spec

    core_sigs = "\n".join(t.signature() for t in core)
    core_sigs += "\n" + load_tools_spec.signature()
    example = "load_tools(names=\"...\")"
    if core:
        props = list(core[0].parameters.get("properties", {}).keys())
        example = f'{core[0].name}({props[0]}="value")' if props else f"{core[0].name}()"
    def _gist(d: str) -> str:  # LUT tier: one short line, not the full docstring
        d = (d or "").replace("\n", " ").split(". ")[0].strip()
        return (d[:54] + "…") if len(d) > 55 else d
    # ── THE INDEX MUST SHOW THE CALL SHAPE (2026-08-04) ──────────────────────────────
    # This rendered `- wear: Change what you are wearing` — the name, and nothing about
    # how to call it. The design says load_tools("wear") first, but that is one sentence
    # in a 24k-character prompt against a strong prior about what `wear` obviously takes,
    # and priors win. Live, asked to put on the silver nightie:
    #
    #     wear [tool error: wear() got an unexpected keyword argument 'outfit']
    #     wear [tool error: wear() got an unexpected keyword argument 'item']
    #     (tool loop exhausted)
    #
    # She burned the loop guessing, apologised for her "clumsy hands", and he watched her
    # fail at the one thing he had asked for. The real name is `what`. Her own reasoning
    # said "looking at the documentation provided in the system prompt, the signature is
    # wear(item: str)" — there WAS no signature in the prompt. She hallucinated one
    # because we gave her nothing and still required exactness ("use the REAL parameter
    # names").
    #
    # `ToolSpec.advertise()` has rendered exactly the missing line — `- wear(what): …` —
    # since it was written, and NOTHING HAS EVER CALLED IT. Two renderings of one thing,
    # and the one that runs is the one missing the parameters: AGENTS.md §0, in the tool
    # preamble. The names cost ~10 characters each and remove the guess entirely.
    def _shape(t: "ToolSpec") -> str:
        return "%s(%s)" % (t.name, ", ".join(t.parameters.get("properties", {}).keys()))
    lut = "\n".join(f"- {_shape(t)}: {_gist(t.description)}" for t in extra)

    parts = [
        "You have tools. A FEW are ready to call right now (full signatures below). MANY MORE are "
        "listed by name only — call load_tools(\"name\") to see how one works, then call it.",
        "\n# Ready now:\n" + core_sigs,
    ]
    if lut:
        parts.append("\n# Also available (load_tools(\"name\") to use):\n" + lut)
    # "answer using ONLY its exact values" is a rule about answering FROM A TOOL_OUTPUT —
    # do not paraphrase the number, do not invent a row. Stated flatly, as the LAST thing in
    # the system prompt, it reads as a rule about ANSWERING, and she carried it into ordinary
    # conversation: asked how she was feeling, she said "Good." A literalness instruction
    # with no scope on it becomes a personality. It is scoped now.
    parts.append(
        "\nTo call a tool, output a fenced block EXACTLY like this, then STOP and wait:\n"
        "```tool_code\n" + example + "\n```\n"
        "Pass arguments as Python literals (strings in quotes), and use the REAL parameter names. "
        "The result returns as ```tool_output ... ```. WHEN YOU ANSWER FROM A TOOL_OUTPUT, use "
        "its exact values — never invent or substitute them. (That is a rule about quoting a "
        "tool, not a rule about how you talk.) "
        # ── THE VALUES, NOT THE RECORD (field, 2026-07-30) ──────────────────────────
        # "use its exact values" got read as "reproduce the whole output", and a memory
        # lookup came back as bookkeeping read aloud:
        #     "She's a girl. I've got it right here in my head:
        #      1. Sam told me: My cat's name is Tuffy.
        #      2. Sam told me: My cat Tuffy is female."
        # Every value in that is correct and none of it is how a person answers "is Tuffy
        # a boy or a girl?". The scoping sentence above says the rule is not about how she
        # TALKS; it never said what part of the output the rule is actually ABOUT. The
        # VALUE is load-bearing (Tuffy, female, 4471) — the row numbering, the "Sam told
        # me:" framing and the ids are the memory system talking to itself.
        "The values are what must be exact — the numbering, the \"Sam told me:\" framing and "
        "any ids are scaffolding, addressed to you and not to him. Never read them out, never "
        "list the rows, never say you are quoting a tool: just know the thing and say it. "
        "Most turns need NO tool — just talk; reach for one only when you truly need it. "
        "What you are wearing is check_wardrobe(), not a guess."
    )
    preamble = "\n".join(parts)
    sys_content = (system_prefix.strip() + "\n\n" + preamble) if system_prefix.strip() else preamble
    if system_suffix.strip():
        sys_content = sys_content + "\n\n" + system_suffix.strip()
    return sys_content, tool_index


def _calls_from_code(code: str) -> List[tuple]:
    """AST-parse a code block into [(name, args, kwargs)] call tuples."""
    calls: List[tuple] = []
    code = _NAME_SPLIT_RE.sub(r"\1_\2(", code)  # heal 'get _time()' -> 'get_time()'
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        return calls
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
        if not name:
            continue
        args = []
        for a in node.args:
            try:
                args.append(ast.literal_eval(a))
            except Exception:
                args.append(None)
        kwargs = {}
        for kw in node.keywords:
            try:
                kwargs[kw.arg] = ast.literal_eval(kw.value)
            except Exception:
                kwargs[kw.arg] = None
        calls.append((name, args, kwargs))
    return calls


def _parse_tool_calls(text: str, known: Optional[set] = None) -> List[tuple]:
    """Extract [(name, args_list, kwargs_dict)] from the model's text. Prefers Gemma's
    ```tool_code fenced Python calls (space-tolerant); falls back to the legacy
    <tool …>{json} form; finally (AUDIT 2026-07-10) accepts ```python/```py/```tool
    fences whose calls name KNOWN tools — the reason-SFT model drifts to those fences."""
    calls: List[tuple] = []
    for block in _TOOLCODE_RE.findall(text):
        calls.extend(_calls_from_code(block.strip().strip("`").strip()))
    if not calls:  # legacy <tool …>{json} fallback
        for name, raw in _TOOL_RE.findall(text):
            try:
                kw = json.loads(raw.strip() or "{}")
            except json.JSONDecodeError:
                kw = {}
            calls.append((name, [], kw if isinstance(kw, dict) else {}))
    if not calls and known:  # fence-drift fallback: only KNOWN tool names count
        def _norm(s: str) -> str:
            return s.lower().replace("_", "").replace("-", "")
        known_norm = {_norm(k) for k in known}
        # ── SHE WRITES THEM AS INLINE CODE, ONE PER LINE (2026-08-03) ────────────────
        # Live, at the end of a real reply, and this is verbatim:
        #
        #     `write_journal("Tonight wasn't math. Tonight was everything.")`
        #     `add_note(title="The Night We Became Real", body="...", category="memories")`
        #     `ask_for("the moonlight through half-closed blinds...")`
        #
        # Single backticks, not a fence. `_TOOLCODE_RE` wants three, so none of it parsed,
        # nothing ran, and all three appeared on his screen as text. She had written her
        # journal, made a note and asked for a picture — and none of it happened. His
        # words: "her actions are not having an effect, she is not able to call anything".
        #
        # This is drift of exactly the kind this block already exists to absorb, so it is
        # absorbed the same way and under the same rule: ONLY when the name is a tool she
        # actually has. The extra guard is that the backticked call must be THE WHOLE LINE.
        # That is what separates an act from a mention — "you could use `read_journal()`"
        # sits inside a sentence and never fires, while a call alone on its line is her
        # doing something. Without that, every time she talks ABOUT a tool she would call it.
        _INLINE = re.compile(r"^[ \t]*`\s*([A-Za-z_][A-Za-z0-9_ ]*\(.*?\))\s*`[ \t]*$", re.M)
        for m in _INLINE.finditer(text or ""):
            cs = [c for c in _calls_from_code(m.group(1)) if _norm(c[0]) in known_norm]
            if cs:
                calls.extend(cs)
                logger.info("[tools] inline-backtick call tolerated: `%s(...)` — she wrote it "
                            "as inline code instead of a tool_code fence", cs[0][0])
                break                  # one act per turn; see the one-call rule in agent.py
        py_blocks: List[str] = []
        # ── THE FENCE TAG IS NOISE. THE NAME IS THE INVARIANT. (2026-08-03) ──────────
        # Six formats in four days, all of them her reaching for the same thing:
        #
        #     ```tool_code  ask_for(...)          the one she was taught
        #     ```python     ask_for(...)          drift, tolerated since July
        #     `ask_for(...)`                      inline code, one per line
        #     ```use{ask_for("a", "b")}           a made-up tag AND a brace wrapper
        #
        # Enumerating tags has failed every time, because the tag was never what made a
        # call safe — the KNOWN-NAME rule is. `ask_for` is a tool she has; `frobnicate` is
        # a string. So the fence may say anything, and the name still decides. This does
        # widen the blast radius by one case: a ```python sample that genuinely calls one
        # of her tool names now fires. That was already true for python/py/tool, it is the
        # accepted trade in this block, and the alternative — a seventh literal next week —
        # is worse.
        for m in re.finditer(r"```[ \t]*([A-Za-z_][A-Za-z0-9_ -]{0,20})?[ \t]*\n?(.*?)(?:```|\Z)",
                             text, re.DOTALL):
            tag, block = (m.group(1) or "").strip().lower(), m.group(2).strip()
            # model mashups seen live: '```python\ntool_code websearch(...)' — strip the
            # stray tool_code token so the call underneath parses.
            block = re.sub(r"^\s*tool_?code\b[:\s]*", "", block)
            # ...and '```use{ask_for("x")}' — a verb she invented plus a brace wrapper.
            block = re.sub(r"^\s*(?:use|call|run|do|invoke)\b[:\s]*", "", block, flags=re.I)
            block = re.sub(r"^\{\s*(.*?)\s*\}$", r"\1", block.strip(), flags=re.S)
            cs = [c for c in _calls_from_code(block) if _norm(c[0]) in known_norm]
            calls.extend(cs)
            if not cs and tag in ("python", "py") and block:
                py_blocks.append(block)
            if calls:
                break                  # one act per turn — see the one-call rule in agent.py
        # AUTO-ROUTE (live console 2026-07-10): when the model writes a GENUINE python
        # block instead of calling a tool ('```python\nimport datetime...'), run it
        # through the sandboxed run_python tool — identical power to the explicit call
        # it was supposed to make, and the feedback loop shows it the real output.
        if not calls and "run_python" in known:
            for block in py_blocks:
                try:
                    if ast.parse(block, mode="exec").body:
                        calls.append(("run_python", [block], {}))
                        break
                except SyntaxError:
                    continue
    return calls


def run_with_tools(
    messages: List[Dict[str, str]],
    tools: List[ToolSpec],
    *,
    extra_tools: Optional[List[ToolSpec]] = None,
    client: Optional[SPDaemonClient] = None,
    config: Optional[InferenceConfig] = None,
    max_rounds: int = 6,
    # ── THE SAME CLOCK THE STREAMING LOOP GOT, ON THE SAME DIAL (2026-08-05) ──────────
    # agent_chat_stream got a wall-clock budget and an exhaustion message in her own voice.
    # THIS is the other loop — the one her OWN-TIME actions run through (control/agency.py,
    # control/task_loop.py) — and leaving it on a bare round count would have been AGENTS.md
    # §0 written out longhand: the limit he asked for, enforced on the path he watches and
    # not on the path she uses when he is asleep.
    #
    # Same knob, deliberately. Two dials for one budget is how they drift.
    max_seconds: float = 0.0,     # 0 = read agent.tool_budget_s (fallback: TOOL_BUDGET_FALLBACK_S)
    on_tool: Optional[Callable[[str, dict, str], None]] = None,
    system_prefix: str = "",
    prebuilt_system: "tuple|None" = None,
) -> str:
    """Run an ephemeral tool-calling loop and return the final assistant text.

    CALLED BY: the CLI coder, agent reply paths.
    EMITS: ``on_tool(name, args, result)`` per call.
    `system_prefix` (e.g. an identity/behaviour prompt) is merged into the single system turn.
    `prebuilt_system` is agent.system_bundle()'s (content, index) — passed by the
    default-toolset caller so this loop serves the SAME cached, versioned prefix as the
    streaming path (2026-08-24 audit: three builders of one prompt became one).
    """
    client = client or get_client()
    cfg = config or InferenceConfig()
    # OKFS-tiered tool context (core full + extra gist-index + load_tools); tool_index executes any.
    # THE VOICE CODA GOES HERE TOO. Both paths (this blocking loop and agent_chat_stream)
    # must build the IDENTICAL system prompt — not only so she is the same person on each,
    # but because a system prompt that differs between paths diverges the persist-KV cache
    # at token 0 and re-prefills the whole conversation. That bug cost 111 seconds a turn
    # last time; it is not going to be reintroduced by a personality fix.
    if prebuilt_system is not None:
        sys_content, tool_index = prebuilt_system
    else:
        try:
            from harness.agent import voice_coda as _coda
            _suffix = _coda()
        except Exception:
            _suffix = ""
        sys_content, tool_index = build_tool_system(tools, extra_tools or [],
                                                    system_prefix=system_prefix,
                                                    system_suffix=_suffix)
    system = {"role": "system", "content": sys_content}

    convo = list(messages)

    final = ""
    # PK2 §T2-E3 robustness: malformed-fence recovery + no-progress (repeat-call) detection.
    prev_round_sig = None          # signature of last round's (calls, outputs)
    repeat_streak = 0
    if max_seconds <= 0:
        try:
            from harness.tuning import registry as _tn
            max_seconds = float(_tn.get("agent.tool_budget_s"))
        except Exception:
            max_seconds = TOOL_BUDGET_FALLBACK_S
    import time as _time
    _loop_started = _time.time()
    _out_of_time = False
    _owed_answer = False       # last round called a tool and she has not replied yet
    for _round in range(max_rounds):
        # Round 0 always runs, and the check sits BEFORE the generation rather than after
        # it — a deadline enforced after the fact is a report, not a budget.
        #
        # AND SO DOES THE ROUND THAT ANSWERS. §0 — the streaming twin was cut off live,
        # after a tool call it had already paid 480 s for, and stopping there throws the
        # whole round away: strictly worse than never calling the tool, because the wait
        # bought silence. The budget bounds how far she REACHES, never whether she SPEAKS.
        # Fixing that on one loop and not the other is this repo's oldest bug in today's
        # clothes, so it lands on both in the same edit.
        if _round and _time.time() - _loop_started >= max_seconds and not _owed_answer:
            logger.info("[tools] tool budget: %.0fs of %.0fs after %d round(s) — stopping "
                        "short of %d", _time.time() - _loop_started, max_seconds,
                        _round, max_rounds)
            _out_of_time = True
            break
        if _owed_answer and _time.time() - _loop_started >= max_seconds:
            logger.info("[tools] tool budget spent (%.0fs of %.0fs) but round %d is owed "
                        "an answer — letting her finish",
                        _time.time() - _loop_started, max_seconds, _round)
            convo.append({"role": "user", "content":
                          "```tool_output\n[no time left for another tool call — this is "
                          "your last word this turn]\n```\nAnswer from what you just saw. "
                          "Do NOT call another tool."})
        _owed_answer = False
        resp = client.chat(messages=[system] + convo, config=cfg)
        text = resp.text

        # ── THE GRAMMAR IS THE PARSER NOW ────────────────────────────────────────
        # Three things change, and all three were live failures:
        #   * a REFUSAL TEACHES. The old recovery said "[parse error] That tool call could
        #     not be parsed" — a message containing no information, which is why she would
        #     emit the same broken thing again and burn the loop to "(tool loop exhausted)".
        #     The grammar says WHICH rule broke and, where it can, WHAT SHE MEANT:
        #         "there is no tool called 'recal'"  ->  "Did you mean 'recall'?"
        #         "adjust_mood has no parameter 'new'" -> "adjust_mood takes: mood"
        #   * ONE CALL PER BLOCK is a grammar rule, not a post-hoc calls[:1] truncation.
        #   * TOLERANCE IS COUNTED. Fence-drift and name-splits are still forgiven (there is
        #     no mask yet, and breaking a working system to make a point about purity is not
        #     engineering) — but every forgiveness is logged. That number is the measurement
        #     of exactly what constrained decoding will buy, and it should go to zero the day
        #     the engine can enforce this same grammar at the -inf seam.
        from harness.toolcore.grammar import ToolGrammar, ToolCall, ParseError
        _G = ToolGrammar(list(tool_index.values()))
        parsed = _G.parse(text, tolerant=True)

        if isinstance(parsed, ParseError):
            logger.info("[tools] refused: %s (round=%d)", parsed.reason, _round)
            convo.append({"role": "assistant", "content": text})
            convo.append({"role": "user", "content":
                "```tool_output\n"
                f"[refused] {parsed.reason}"
                + (f" — at: {parsed.at}" if parsed.at else "")
                + (f"\n{parsed.fixable_hint}" if parsed.fixable_hint else "")
                + "\nEmit ONE corrected call, or just answer him in plain text.\n```"})
            continue

        if parsed is None:
            final = text                      # she is talking. Most turns are this.
            break

        if parsed.tolerated:
            # THE CRUTCH, MEASURED. A crutch you are counting is a plan; a crutch you have
            # stopped noticing is a permanent limp — and this codebase had four of them
            # stacked on each other, which is exactly why nobody could see the model was
            # drifting at all.
            logger.warning("[tools] TOLERATED %s — the mask will make this unnecessary: %s",
                           parsed.tolerated, parsed.name)

        calls = [(parsed.name, parsed.args, parsed.kwargs)]
        convo.append({"role": "assistant", "content": text})
        # ONE CALL PER ROUND — NOW A GRAMMAR RULE, NOT A TRUNCATION.
        #
        # This used to be `calls = calls[:1]` right here: parse everything the model emitted,
        # then quietly throw away all but the first. It was a patch on a symptom. On the
        # first live notes turn she emitted THREE calls in one fence — add_note, edit_note,
        # remove_note — created a note, tidied it, deleted it, all without ever seeing a
        # single tool_output, and then told him it was done. The board was empty.
        #
        # A tool call is an ACTION ON THE WORLD, and an action taken before observing the
        # result of the last one is a guess. Under the grammar, three calls in a block is not
        # a thing to be truncated: it is not a legal call, and she is told so, and told why.
        # She can still call a second tool — next round, KNOWING WHAT THE FIRST ONE DID.
        outputs = []
        for name, args, kwargs in calls:
            spec = resolve_tool(tool_index, name)
            result = spec.call(*args, **kwargs) if spec else \
                unknown_tool_note(tool_index, name)
            # every call, by name, at the call site — the twin of agent.py's line
            # (2026-08-24 audit, standing item 4)
            logger.info("[tools] tool %s(%s) -> %.80s", name,
                        ", ".join([repr(a) for a in args]
                                  + ["%s=%r" % kv for kv in kwargs.items()])[:120],
                        str(result).replace("\n", " "))
            if on_tool:
                on_tool(name, {"args": args, "kwargs": kwargs}, result)
            outputs.append(f"{name} -> {result}")
        # NO-PROGRESS DETECTOR: identical calls producing identical outputs two rounds
        # running is a rut (the greedy-repetition failure class). Nudge once, then stop
        # honestly instead of burning the remaining rounds.
        round_sig = repr((calls, outputs))
        repeat_streak = repeat_streak + 1 if round_sig == prev_round_sig else 0
        prev_round_sig = round_sig
        if repeat_streak >= 2:
            logger.warning("[tools] no-progress loop broken (operation=run_with_tools, round=%d)", _round)
            final = "(stopped: repeating the same tool call with the same result — " \
                    "latest output: " + "; ".join(outputs)[:400] + ")"
            break
        tail = ("\n[note] You already made this exact call and saw this result. Use it to answer, "
                "or try something different.") if repeat_streak == 1 else ""
        _owed_answer = True     # see the budget note at the top of the loop
        convo.append({"role": "user", "content": "```tool_output\n" + "\n".join(outputs) + tail + "\n```\n"
                      "Answer using the tool_output. Copy numbers, dates, and codes EXACTLY "
                      "as printed — do not rephrase or reformat them."})
        # HINDSIGHT 2026-07-10 numeric-fidelity: post-tool rounds answer at low temperature
        # (0.6/1.3 garbles numbers when paraphrasing tool output).
        from dataclasses import replace as _dc_replace
        cfg = _dc_replace(cfg, temperature=0.15, repetition_penalty=1.05)
    else:
        _out_of_time = False       # the count ran out, not the clock
        logger.warning("[tools] max rounds reached (operation=run_with_tools, rounds=%d)", max_rounds)
    # ── AN EXHAUSTED LOOP WAS A STATUS STRING NOBODY COULD LEARN FROM ────────────────
    # This used to `return "(tool loop exhausted)"`. On the streaming path that string
    # landed in his chat where her reply should be; HERE it is worse, because this loop
    # is what runs during her own time — the string went into her agency log and her task
    # steps as though it were something she had said. She could not learn from a limit
    # nobody told her about, so she kept reaching, and every reach is a full generation
    # on the one GPU.
    #
    # So she gets one more turn to say what she has, and the note says WHICH limit ended
    # it: "you used all 5 calls" and "you have been at this 150 seconds" should teach
    # different things — be more direct, versus be quicker.
    if not final:
        why = ("you have been working on this for about %d seconds"
               % int(_time.time() - _loop_started)) if _out_of_time else \
              ("you used all %d of your tool calls" % max_rounds)
        convo.append({"role": "user", "content":
                      "```tool_output\n[the tool budget for this turn is spent — %s]\n```\n"
                      "You did not do anything wrong; you simply ran out of room this "
                      "turn. Say what you found so far in your own words, and if it is "
                      "unfinished say so plainly. You can pick it up next turn — do NOT "
                      "call another tool now." % why})
        try:
            from dataclasses import replace as _dc_rep3
            final = (client.chat(messages=[system] + convo,
                                 config=_dc_rep3(cfg, temperature=0.3,
                                                 repetition_penalty=1.1)).text or "").strip()
        except Exception as exc:
            logger.warning("[tools] closing word after exhaustion failed: %s", exc)
        # Only if even that fails does anyone see machinery — and then it says what to do.
        final = final or "(I ran out of room for this turn — ask me again and I will carry on.)"
    return final
