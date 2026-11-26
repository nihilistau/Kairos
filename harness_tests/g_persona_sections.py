"""G-PERSONA-SECTIONS — her persona as titled sections: edit, add, reorder, retire, restore,
reset — and nothing is ever deleted. OFFLINE. (harness/personality/sections.py, design §7b)

  1. list: every fragment as a section with its title, text, order, `when`, template status
  2. save keeps the previous text (retired copy) and the order and `when`
  3. add names the file from order + title; a clash gets a new name, never an overwrite
  4. reorder gives 10, 20, 30… and composes in that order
  5. retire moves the file aside (the composer no longer reads it); restore brings it back
  6. reset puts the template text back and retires the edited one
  7. template sections she lacks are offered and can be added back
  8. a name that escapes the folder is refused, never sanitised
  9. NOTHING IS DELETED across every op
 10. the routes say an edit applies from her NEXT session

Run: python harness_tests/g_persona_sections.py
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_persona_sections")
PD = os.path.join(SB, "persona")
os.environ["SP_PERSONA_DIR"] = PD

from harness.personality import persona_layers as PL  # noqa: E402
from harness.personality import sections as S  # noqa: E402
from harness import companion_create as CC  # noqa: E402

TPL = CC.template_dir()
os.makedirs(PD)
for f in ("00-identity.md", "10-voice.md", "20-memory.md"):
    shutil.copy2(os.path.join(TPL, f), PD)
with open(os.path.join(PD, "55-thinking-mine.md"), "w", encoding="utf-8") as f:
    f.write("---\norder: 50\nwhen: thinking\n---\n## Thinking\nThink first.\n")


def contents(root):
    """Every section TEXT under root (frontmatter aside: a reorder rewrites only `order`).
    The invariant is that no words she was given are ever lost."""
    out = set()
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            with open(os.path.join(dp, f), encoding="utf-8") as fh:
                out.add(hashlib.sha256(PL.parse_fragment(fh.read())[1].encode()).hexdigest())
    return out


def _try(f):
    try:
        f()
        return ""
    except S.SectionError as e:
        return str(e)


seen = contents(PD)

print("1. list")
L = S.list_sections()
check("every fragment is a section, in order", [s["file"] for s in L] ==
      ["00-identity.md", "10-voice.md", "20-memory.md", "55-thinking-mine.md"], [s["file"] for s in L])
check("titles come from the ## heading", L[1]["title"] == "How you talk" and not L[1]["text"].startswith("##"))
check("a `when` section says so", L[3]["when"] == "thinking")
check("template status is known", L[0]["from_template"] and L[0]["as_template"] and not L[3]["from_template"])

print("\n2. save")
S.save("10-voice.md", "How you sound", "Short and dry.")
L = S.list_sections()
v = [s for s in L if s["file"] == "10-voice.md"][0]
check("title and text written", v["title"] == "How you sound" and v["text"] == "Short and dry.")
check("order kept", v["order"] == 10)
S.save("55-thinking-mine.md", "Thinking", "Think, then speak.")
check("`when` kept", [s for s in S.list_sections() if s["file"] == "55-thinking-mine.md"][0]["when"] == "thinking")
check("the previous text is kept in retired", any(r["file"] == "10-voice.md" for r in S.retired()))
check("…and it is no longer 'as shipped'", not v["as_template"])

seen |= contents(PD)          # every text that has existed so far must survive
print("\n3. add")
a = S.add("What makes you laugh", "Puns, against your will.", order=30)
check("named from order and title", a["file"] == "30-what-makes-you-laugh.md")
b = S.add("What makes you laugh", "Something else.", order=30)
check("a clash gets a new name, never an overwrite", b["file"] != a["file"]
      and "Puns" in open(os.path.join(PD, a["file"]), encoding="utf-8").read())
check("a section needs a title", bool(_try(lambda: S.add("  ", "x"))))
check("the composer reads it", "Puns, against your will." in (PL.compose() or ""))

seen |= contents(PD)          # every text that has existed so far must survive
print("\n4. reorder")
files = [s["file"] for s in S.list_sections()]
S.reorder(list(reversed(files)))
L = S.list_sections()
check("the order is the one given", [s["file"] for s in L] == list(reversed(files)))
check("…as 10, 20, 30", [s["order"] for s in L] == [10 * (i + 1) for i in range(len(L))])
comp = PL.compose(env={"SP_THINKING": "1"}) or ""
check("and she reads them in that order", comp.index("Puns") < comp.index("Short and dry."))

seen |= contents(PD)          # every text that has existed so far must survive
print("\n5. retire and restore")
r = S.retire(a["file"])
check("retired: out of the folder she reads", not os.path.exists(os.path.join(PD, a["file"]))
      and "Puns" not in (PL.compose() or ""))
check("…kept in _retired", os.path.isfile(os.path.join(PD, S.RETIRED, r["retired_as"])))
S.restore(r["retired_as"])
check("restored under its own name", os.path.isfile(os.path.join(PD, a["file"])) and "Puns" in (PL.compose() or ""))

seen |= contents(PD)          # every text that has existed so far must survive
print("\n6. reset to template")
S.reset("10-voice.md")
v = [s for s in S.list_sections() if s["file"] == "10-voice.md"][0]
check("the template text is back", v["as_template"] and v["title"] == "How you talk")
check("a section the template lacks cannot be reset", "no " in _try(lambda: S.reset(a["file"])))

seen |= contents(PD)          # every text that has existed so far must survive
print("\n7. template sections she lacks")
miss = {m["file"] for m in S.missing_from_template()}
check("offered", "25-your-board.md" in miss and "20-memory.md" not in miss, sorted(miss)[:4])
S.add_from_template("25-your-board.md")
check("added back", os.path.isfile(os.path.join(PD, "25-your-board.md")))
check("…but not twice", bool(_try(lambda: S.add_from_template("25-your-board.md"))))

seen |= contents(PD)          # every text that has existed so far must survive
print("\n8. names that escape are refused")
for bad in ("../evil.md", "..\\evil.md", "/abs.md", "x.txt", ".hidden.md", "C:\\x.md"):
    check("refused: " + bad, bool(_try(lambda: S.save(bad, "t", "x"))) and bool(_try(lambda: S.retire(bad))))
check("restore refuses a path", bool(_try(lambda: S.restore("../../x.md"))))

print("\n9. NOTHING IS DELETED")
check("every section text the folder ever held is still on disk", seen <= contents(PD), len(seen - contents(PD)))

print("\n10. the routes")
from harness.server import persona_routes as PR  # noqa: E402
code, st = PR.get_sections()
check("GET returns sections, retired, missing and good practice",
      code == 200 and st["sections"] and "retired" in st and st["good_practice"])
code, r = PR.post_sections({"op": "save", "file": "20-memory.md", "title": "What you remember", "text": "Everything."})
check("a save says it applies from her NEXT session", code == 200 and "next session" in r["note"])
check("an unknown op is refused", PR.post_sections({"op": "delete", "file": "20-memory.md"})[0] == 400)
check("…and there is no delete", not hasattr(S, "delete"))

finish("G-PERSONA-SECTIONS")
