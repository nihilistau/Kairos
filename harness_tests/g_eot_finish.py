"""G-EOT-FINISH — every way the decode loop ends must SAY which way it was.

WHY THIS EXISTS. `eot_margin` records how close the stop token was to winning; it cannot say
whether the turn ended because a stop token was sampled, because the harness matched a stop
STRING in the decoded text, because the judge halted it, because a cap ran out, because a
fault, or because the client hung up. Without that, 26.6% of non-capped turns sit at
margin <= 0 and are unattributable, and docs/SPEAK-OR-SILENT-2026-09-19.md can only publish
FALSE-CONTINUE as a bound instead of a rate.

`finish_reason` closes that. THE DEFECT THIS GUARDS is not the field going missing — it is a
NEW `break 'decode` added later without one, which would silently relabel a whole end
condition as the fall-through value `max_tokens` and quietly poison every rate computed
afterwards. That is AGENTS.md section 0: an invariant enforced at four of five exits is
enforced at none.

Source-shaped and offline on purpose: the four-synthetic-ends live test needs a GPU, a daemon
and a client that can hang up, so it could never run in the offline sweep where a regression
would actually be caught. Comments are stripped before any matching, because this file and
routes.rs both DESCRIBE the enum at length and a prose mention would satisfy a naive grep —
the trap this tree keeps stepping on (see g_hidden_tap.py, same reason).

NOT GATED HERE, deliberately: "an eos row has margin > 0". That holds only at temperature 0
(strict argmax). Her room turns run temperature 0.6, where a stop token can be sampled out of
the nucleus without leading the logits, so the invariant is false on the configuration she
actually uses. It was in an earlier draft of this gate and is left written down because
asserting it would have encoded a bug as a rule.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness_tests._gate import sandbox, check, finish, skip  # noqa: E402

sandbox()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RS = os.path.join(ROOT, "engine", "tools", "sp_daemon", "src", "routes.rs")
TOOL = os.path.join(ROOT, "tools", "eot_calibrate.py")

if not os.path.exists(RS):
    # engine/ is a nested clone and the public export ships no engine/, so a Kairos
    # checkout legitimately has nothing to check here.
    skip("engine/tools/sp_daemon/src/routes.rs absent (engine not cloned)", "G-EOT-FINISH")

src = open(RS, encoding="utf-8", errors="replace").read()
code = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
code = re.sub(r"//[^\n]*", " ", code)

# The enum as shipped. `thought_ceiling` is NOT here and must not be: the ceiling masks logits,
# it does not leave the loop, so no turn can end "because of" it.
EXPECTED = {"eos", "judge_halt", "stop_string", "error", "max_tokens", "cancel"}

# SCOPE: the function that EMITS the KAIROS line. routes.rs holds a SECOND decode loop, in
# `v1_chat`, whose breaks carry no reason -- correctly, because that loop emits no KAIROS line
# and so contributes no rows to the dataset this guards. Guarding it would be guarding nothing.
# The leg below instead pins that it stays a non-emitter, so the day a second producer appears
# this gate fails rather than quietly covering four exits out of seven.
print("0. THE GUARD COVERS EVERY PRODUCER OF THE LINE")
owner_start = code.find("fn run_kvdecode_chat(")
check("run_kvdecode_chat is present to guard", owner_start > 0,
      "the emitting function was renamed; this gate is measuring nothing")
elsewhere = code[:owner_start] if owner_start > 0 else code
check("no OTHER function emits the KAIROS terminal line",
      "KAIROS: turn ended" not in elsewhere,
      "a second emitter would put unlabelled rows into the same log this gate claims to cover")

print("\n1. EVERY `break 'decode` NAMES ITS REASON FIRST (inside the emitting function)")
owner = code[owner_start:] if owner_start > 0 else code
lines = owner.split("\n")
breaks = [i for i, l in enumerate(lines) if re.search(r"break\s+'decode", l)]
check("the decode loop still has break sites to guard", len(breaks) >= 4,
      "found %d; if the loop was restructured this gate is measuring nothing" % len(breaks))
unnamed = []
for i in breaks:
    window = "\n".join(lines[max(0, i - 4):i + 1])
    if not re.search(r'finish_reason\s*=\s*"', window):
        unnamed.append(i + 1)
check("no break leaves without setting finish_reason", not unnamed,
      "lines %s break out of the decode loop without a reason, so those turns would be "
      "logged as the fall-through value `max_tokens`" % unnamed)

print("\n2. THE VALUES ARE THE DOCUMENTED SET, AND `thought_ceiling` IS NOT ONE")
assigned = set(re.findall(r'finish_reason\s*=\s*"([a-z_]+)"', code))
assigned |= set(re.findall(r'finish_reason=\{\}"[^;]*?,\s*[^;]*?"([a-z_]+)"', code))
check("every assigned value is in the documented enum", assigned <= EXPECTED,
      "undocumented: %s" % sorted(assigned - EXPECTED))
check("thought_ceiling is not an end reason", "thought_ceiling" not in assigned,
      "the ceiling masks logits and does not exit the loop; a value that can never appear is "
      "worse than a missing one")
check("the fall-through default is max_tokens",
      re.search(r'let\s+mut\s+finish_reason[^=]*=\s*"max_tokens"', code) is not None,
      "running out of loop iterations is the one end with no statement of its own, so it must "
      "be the initial value")

print("\n3. IT REACHES BOTH READERS, WITH ONE DEFINITION")
check("the terminal log line carries it", re.search(r'finish_reason=\{\}', code) is not None,
      "tools/eot_calibrate.py reads the log, not the SSE")
check("the SSE payload carries it", '"finish_reason": finish_reason' in code,
      "a panel and a classifier reading the same turn must not disagree about why it ended")

print("\n4. THE CANCEL END EMITS BEFORE IT RETURNS")
# The client-disconnect path leaves the function early, so without its own emit a cancelled
# turn is ABSENT from the log rather than labelled -- and absent reads as 'did not happen'.
# A bounded WINDOW, not a brace-excluding run: the block legitimately contains braces
# (DaemonEvent::Chat { .. }), so `[^}]*?` can never span it and the first version of this
# leg failed on correct code -- a gate that cannot see the thing it guards.
cancel_blocks = []
for _m in re.finditer(r"cancel_child\.store\(1", owner):
    _w = owner[_m.start():_m.start() + 1600]
    _e = _w.find("return;")
    if _e > 0:
        cancel_blocks.append(_w[:_e])
check("a cancel path exists to guard", cancel_blocks != [],
      "no cancel_child store followed by return; the shape changed")
check("at least one cancel path logs its reason before returning",
      any("kairos" in b.lower() or "finish_reason" in b for b in cancel_blocks),
      "a client disconnect would vanish from the log entirely")

print("\n5. THE LOG LINE IS STILL ONE KEY=VALUE SPLIT (the reader's contract)")
# THERE ARE TWO "KAIROS: turn ended" LITERALS: the terminal one and the cancel one added so a
# client disconnect is labelled rather than absent. Taking the FIRST match grabbed the cancel
# line, which carries no first-step margin, and the leg below failed on correct code -- the
# same class of self-inflicted red as g_kv_tap matching a forward declaration. Pick the
# terminal literal by its own text, and assert the cancel one separately.
lits = re.findall(r'"KAIROS: turn ended[^"]*"', src)
check("both the terminal and the cancel line exist", len(lits) >= 2,
      "found %d; a cancel with no line of its own is a turn that vanishes from the log" % len(lits))
term = [l for l in lits if "more to say" in l]
check("the terminal line is identifiable", len(term) == 1,
      "cannot tell the two apart, so this section would guard whichever came first")
if term:
    lit = term[0]
    check("eot_margin= and n_gen= are still present and unspaced",
          "eot_margin={:.3}" in lit and "n_gen={}" in lit,
          "tools/eot_calibrate.py parses these with a regex, not a JSON load")
    check("finish_reason= carries no space before its value",
          "finish_reason={}" in lit,
          "a space would break the key=value split every reader uses")
    # THE SECOND OPERATING POINT. `eot_margin` is overwritten each step, so it answers "would
    # she stop HERE". `eot_margin_first` is captured once and never overwritten, so it answers
    # "would she start talking" -- the question a speak-or-silent policy consults BEFORE she
    # says anything. Measured live: a turn that self-stopped at n_gen=2 read -8.584 at the
    # first step and +4.080 at the last. One variable holding both would report the terminal
    # value on short turns and look like agreement.
    check("the first-step margin is on the line too", "eot_margin_first={:.3}" in lit,
          "without it the log answers only one of the two operating points")

print("\n5b. THE FIRST-STEP MARGIN IS CAPTURED ONCE, NOT OVERWRITTEN")
check("it is written under a step==0 guard",
      re.search(r"kairos_steps\s*==\s*0\s*\{\s*kairos_margin_first", code) is not None,
      "an unguarded assignment makes it a duplicate of the terminal margin")
check("the step counter advances",
      re.search(r"kairos_steps\s*\+=\s*1", code) is not None,
      "without the increment the guard is always true and the LAST step wins instead")

if os.path.exists(TOOL):
    print("\n6. THE READER KNOWS THE FIELD IS COMING")
    t = open(TOOL, encoding="utf-8", errors="replace").read()
    tcode = re.sub(r'""".*?"""', " ", t, flags=re.S)
    check("eot_calibrate still parses the two fields it needs",
          "eot_margin=" in tcode and "n_gen=" in tcode,
          "the new field must not have displaced the old parse")

finish("G-EOT-FINISH")
