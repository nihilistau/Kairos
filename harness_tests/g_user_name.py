#!/usr/bin/env python
"""G-USER-NAME — the companion calls the user what the profile says, and nothing else.

WHY THIS EXISTS (2026-11-19). A fresh clone's companion called every user by the operator's
name. It was a literal in about thirty prompt-visible strings: the coda ("You are TALKING to
<name>, not serving him"), the recall framing ("<name> told me: ..."), memory refusals, the
watch judge, the insight prompt and its parser, the standing-world header. The export's name
rule swapped one fixed name for another, so every public install shipped a fictional user and
called everyone "he".

Now there is one source, `[user] name` / `[user] pronouns` in the profile, carried by serve.py
as SP_USER_NAME / SP_USER_PRONOUNS and read through `harness/user.py`. Unset is neutral: "the
user", they/them.

    1. NO STRING NAMES HIM. Every non-docstring string literal under harness/ is scanned for
       the operator's name (and the export's stand-in for it). Three allowlisted data keys.
    2. UNSET IS NEUTRAL. The coda, the tool discipline, the recall framing, a memory refusal,
       the watch judge and the third-person rewrite say "the user" / they, with verbs that
       agree ("they are", "they have").
    3. HIS PROFILE IS UNCHANGED. With his name and he/him the same strings come out exactly as
       the old literals did, so his KV prefix does not move. Run in a subprocess, because
       _TOOL_DISCIPLINE is built at import.
    4. THE PROFILE REACHES THE ENV. serve.build_env carries [user] through.

OFFLINE. No GPU, no daemon.
"""
import io
import os
import re
import subprocess
import sys
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
sandbox("g_user_name")
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ.pop("SP_USER_NAME", None)
os.environ.pop("SP_USER_PRONOUNS", None)

OPERATOR = "Sam"          # the export rewrites this to its stand-in, which is NAMES[1]
NAMES = (OPERATOR, "Sam")
NAME_RX = re.compile(r"\b(?:%s)\b" % "|".join(NAMES), re.I)

# Data keys, not prose: a stored owner value on the operator's own work ledger (and the room's
# default for it), and a five-letter word in the word-game list (copied raw by the export).
ALLOW = {("ledger.py", "OWNERS"), ("app.py", "owner="), ("words.py", "")}


def _docstring_token(toks, i):
    j = i - 1
    while j >= 0 and toks[j].type in (tokenize.NL, tokenize.COMMENT):
        j -= 1
    k = i + 1
    while k < len(toks) and toks[k].type in (tokenize.NL, tokenize.COMMENT):
        k += 1
    before = j < 0 or toks[j].type in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                                       tokenize.ENCODING)
    after = k >= len(toks) or toks[k].type in (tokenize.NEWLINE, tokenize.ENDMARKER)
    return before and after


def scan(root):
    hits = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in ("__pycache__", "node_modules")]
        for f in fn:
            if not f.endswith(".py"):
                continue
            p = os.path.join(dp, f)
            src = io.open(p, encoding="utf-8", errors="replace").read()
            lines = src.splitlines()
            toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
            for i, t in enumerate(toks):
                if t.type != tokenize.STRING or not NAME_RX.search(t.string):
                    continue
                if _docstring_token(toks, i):
                    continue
                line = lines[t.start[0] - 1]
                if any(f == fa and (not key or key in line) for fa, key in ALLOW):
                    continue
                hits.append("%s:%d %s" % (os.path.relpath(p, ROOT), t.start[0],
                                          t.string[:70].replace("\n", " ")))
    return hits


print("\n1. no string literal under harness/ names the operator")
hits = scan(os.path.join(ROOT, "harness"))
check("no prompt-visible string carries %s" % "/".join(NAMES), not hits, "; ".join(hits[:6]))

print("\n2. unset is neutral: 'the user', they/them, verbs that agree")
from harness import user as U                     # noqa: E402
check("say() with nothing configured",
      U.say("{User} said {he} {is} tired; {he} ask{s} {his} questions") ==
      "The user said they are tired; they ask their questions",
      U.say("{User} said {he} {is} tired; {he} ask{s} {his} questions"))
check("say() leaves other braces alone", U.say("{t} {user} {0}") == "{t} the user {0}")
os.environ["SP_USER_PRONOUNS"] = "she/her/her"
check("she/her", U.say("{He} {has} {his} own") == "She has her own", U.say("{He} {has} {his} own"))
os.environ.pop("SP_USER_PRONOUNS")

from harness import agent as A                     # noqa: E402
from harness.skills import verdict as V            # noqa: E402
from harness.skills import lifecycle as L          # noqa: E402
from harness.skills import world as W              # noqa: E402
from harness.skills import watch as Wa             # noqa: E402

coda = A.voice_coda()
check("the coda talks to 'the user' as they",
      "You are TALKING to the user, not serving them. They are the one here with you" in coda,
      coda[:260])
check("the tool discipline uses a placeholder name, not 'the user's name is the user'",
      "remember(\"The user's name is Alex\")" in A._TOOL_DISCIPLINE
      and "facts about THE USER. What they tell you about themselves." in A._TOOL_DISCIPLINE,
      A._TOOL_DISCIPLINE[:200])
check("recall framing", V.framing_for("observed", "user") == "The user told me: {t}",
      V.framing_for("observed", "user"))
ok, why = L.is_memorable("you should edit your personality settings")
check("a memory refusal names the user", (not ok) and "about the user" in why
      and "Sam" not in why, why)
check("third person in they", W._third_person("I've been busy and my cat is mine.") ==
      "They have been busy and their cat is theirs.", W._third_person("I've been busy and my cat is mine."))
jp = Wa._judge_prompt("a {he} question", "page")
check("watch judge: neutral, and braces in his question untouched",
      jp.startswith("The user asked you") and "they are waiting" in jp and "a {he} question" in jp,
      jp[:160])

print("\n2b. the tool descriptions she reads are neutral too")
# A description is the docstring's first line (ToolSpec.from_callable, skill.py) or, for
# consult, the whole docstring; both run through user.say(). Graded on what the BUILDERS
# produce, not on the source, because that is the text that reaches her.
import inspect as _inspect                         # noqa: E402
from harness.toolcore.tools import ToolSpec as _TS  # noqa: E402
_descs = {}
for _t in list(A.default_tools()) + list(A.all_tools()):
    _descs[_t.name] = _t.description
from harness.skills import house as _house, consult as _consult  # noqa: E402
from harness.kairos import presence as _presence                 # noqa: E402
for _f in (_house.set_light, _house.set_fan, _house.what_i_can_reach,
           _presence.enter_mode, _presence.leave_mode):
    _descs[_f.__name__] = _TS.from_callable(_f).description
_descs["consult"] = _TS.from_callable(
    _consult.consult, description=_inspect.cleandoc(_consult.consult.__doc__ or "")).description
_HE_RX = re.compile(r"\b(?:he|him|his|himself|%s)\b|\{(?:user|he|him|his|is|has|s)\}" % "|".join(NAMES), re.I)
_bad = sorted("%s: %s" % (k, v[:60]) for k, v in _descs.items() if _HE_RX.search(v or ""))
check("no tool description says he/him/his or a name (%d described)" % len(_descs), not _bad,
      "; ".join(_bad[:5]))
check("...and the converted ones read as they",
      _descs.get("how_is_he", "").startswith("What their body is doing right now")
      and "whether they seem awake" in _descs.get("how_is_he", "")
      and _descs.get("add_note", "").endswith("shared board that the user can see."),
      (_descs.get("how_is_he"), _descs.get("add_note")))

print("\n3. his profile renders exactly what the literals said")
probe = (
    "import os,sys; sys.path.insert(0, %r); os.environ['SP_DAEMON_URL']='http://127.0.0.1:9';"
    "from harness import agent as A; from harness.skills import verdict as V;"
    "from harness.skills import world as W;"
    "print(A.voice_coda()); print('\\x1e'); print(A._TOOL_DISCIPLINE); print('\\x1e');"
    "print(V.framing_for('observed','user')); print('\\x1e'); print(W._third_person('I like tea and I am tired.'));"
    "from harness.skills import body as B; from harness.toolcore.tools import ToolSpec as T;"
    "print('\\x1e'); print(T.from_callable(B.how_is_he).description)"
) % ROOT
env = dict(os.environ, SP_USER_NAME=OPERATOR, SP_USER_PRONOUNS="he/him/his", PYTHONIOENCODING="utf-8")
out = subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True, text=True,
                     encoding="utf-8").stdout.split("\x1e")
if len(out) == 5:
    k_coda, k_disc, k_frame, k_t3, k_tool = [s.strip("\n") for s in out]
    check("a tool description: the old docstring line, byte for byte",
          k_tool == "What his body is doing right now — heart, movement, whether he seems awake.",
          k_tool)
    check("coda: the old sentence, byte for byte",
          ("You are TALKING to %s, not serving him. He is the one here with you: say "
           "'you' to him — 'he' is for telling someone else about him, and there is no one "
           "else in the room." % OPERATOR) in k_coda, k_coda[:300])
    check("tool discipline: the old example and the old store line",
          ("(remember(\"The user's name is %s\"), not remember(\"%s\"))." % (OPERATOR, OPERATOR)) in k_disc
          and ("facts about %s. What he tells you about himself." % OPERATOR.upper()) in k_disc
          and ("\"%s told me: ...\" is about HIM" % OPERATOR) in k_disc
          and "WHEN HE ASKS YOU SOMETHING" in k_disc, k_disc[:200])
    check("recall framing", k_frame == "%s told me: {t}" % OPERATOR, k_frame)
    check("third person", k_t3 == "He likes tea and he is tired.", k_t3)
else:
    check("the profile subprocess ran", False, out)

print("\n4. the profile reaches the env")
import serve as _serve                             # noqa: E402
e = _serve.build_env(dict(_serve.load_profile("companion"), user={"name": "Robin", "pronouns": "she"}))
check("build_env carries [user]", e.get("SP_USER_NAME") == "Robin" and e.get("SP_USER_PRONOUNS") == "she",
      (e.get("SP_USER_NAME"), e.get("SP_USER_PRONOUNS")))
e0 = _serve.build_env(_serve.load_profile("companion"))
check("the shipped profile leaves the user unnamed", not e0.get("SP_USER_NAME")
      and not e0.get("SP_USER_PRONOUNS"), (e0.get("SP_USER_NAME"), e0.get("SP_USER_PRONOUNS")))

finish("G-USER-NAME")
