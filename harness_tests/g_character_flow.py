"""G-CHARACTER-FLOW — making her a question at a time works, and every step can be skipped.
OFFLINE. (harness/personality/character.py + character_flow.json, design §7b)

  1. the flow is well-formed: every step has a question, a why and a hint; her name is the
     only required step; every section-writing step names a file and a title; examples exist
  2. answers become sections in her voice ("You…"), chips and choices read as English,
     an empty step writes nothing (the template's section stands)
  3. create(): a NEW companion whose persona holds the flow's sections AND the template's
     rest, her name in identity, local voice unless chosen otherwise, a look draft saved
  4. apply(): THIS companion's sections rewritten, each one replaced is retired
  5. the routes: flow with voices, preview, create (bad id refused), apply

Run: python harness_tests/g_character_flow.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_character_flow")

from harness import home as H  # noqa: E402
from harness.personality import character as C  # noqa: E402
from harness.personality import persona_layers as PL  # noqa: E402
from harness.personality import sections as S  # noqa: E402

H.COMPANIONS_DIR = os.environ["SP_COMPANIONS_DIR"]
H.VAR = os.path.join(SB, "var")


def read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


print("1. the flow is well-formed")
F = C.flow()
steps = F["steps"]
check("there is good practice", len(F.get("good_practice", [])) >= 5)
check("every step has a question, a why and a hint",
      all(s.get("question") and s.get("why") and s.get("hint") for s in steps),
      [s["id"] for s in steps if not (s.get("question") and s.get("why") and s.get("hint"))])
check("her name is the only required step", [s["id"] for s in steps if s.get("required")] == ["name"])
secs = [s for s in steps if s.get("section")]
check("every section step names a file, order and title",
      all(s["section"].get("file", "").endswith(".md") and isinstance(s["section"].get("order"), int)
          and s["section"].get("title") for s in secs))
check("no two steps write the same section", len({s["section"]["file"] for s in secs}) == len(secs))
check("text steps carry examples to click", all(s.get("examples") for s in secs))
check("…and the flow covers voice and look", {"voice", "look"} <= {s["id"] for s in steps})

print("\n2. answers become sections")
ans = {"name": "Ivy", "essence": "You are curious to a fault.",
       "sound": {"chips": ["warm", "dry", "brief"], "text": "You never use exclamation marks."},
       "relationship": {"choice": "a friend", "text": ""}, "cares": "", "look": "Copper hair, freckles."}
out = {s["step"]: s for s in C.sections_for(ans)}
check("an answer becomes its section", out["essence"]["text"] == "You are curious to a fault.")
check("chips read as English", out["sound"]["text"].startswith("You are warm, dry and brief."), out["sound"]["text"])
check("a choice reads as English", out["relationship"]["text"] == "To the person you talk to, you are a friend.")
check("an empty step writes nothing", "cares" not in out and "history" not in out)
check("chips alone, no text", C.sections_for({"name": "x", "sound": {"chips": ["calm"]}})[0]["text"] == "You are calm.")
check("a chip not on the list is ignored", "evil" not in json.dumps(C.sections_for({"name": "x", "sound": {"chips": ["evil"], "text": "t"}})))

print("\n3. create(): a new companion from the flow")
r = C.create({**ans, "voice": {"method": "lfm3", "lfm3": "male"}}, "ivy")
P = H.resolve(r["home"])
comp = PL.compose(directory=P["persona_dir"]) or ""
check("her flow sections are in her persona", "You are curious to a fault." in comp and "exclamation marks" in comp)
check("…and the template fills the rest (memory, voice marks)", "What you remember" in comp and "[MOOD:" in comp)
check("her name is in her identity", "Your name is Ivy." in comp and "Kairos" not in comp)
tun = json.loads(read(P["tuning"]) or "{}")
check("local voice, the one chosen", tun.get("voice.method") == "lfm3" and tun.get("voice.lfm3_voice") == "male", tun)
check("her look is saved as a DRAFT beside character.txt", "Copper hair" in read(os.path.join(P["avatar_dir"], "character-draft.txt"))
      and "Copper hair" not in read(os.path.join(P["avatar_dir"], "character.txt")))
r2 = C.create({"name": "Wren", "voice": {"method": "xai", "xai": "iris"}}, "wren")
t2 = json.loads(read(H.resolve(r2["home"])["tuning"]))
check("an xAI voice when chosen", t2.get("voice.method") == "xai" and t2.get("voice.xai_voice") == "iris", t2)
try:
    C.create({}, "nobody")
    check("a flow with no name is refused", False)
except H.HomeError as e:
    check("a flow with no name is refused", "name" in str(e))

print("\n4. apply(): rewrite THIS companion")
os.environ["SP_PERSONA_DIR"] = P["persona_dir"]
os.environ["SP_AVATAR_DIR"] = P["avatar_dir"]
before = read(os.path.join(P["persona_dir"], "01-who-you-are-at-heart.md"))
a = C.apply({"name": "Ivy", "essence": "You are steadier now."})
check("the section is rewritten", "steadier" in read(os.path.join(P["persona_dir"], "01-who-you-are-at-heart.md")))
check("the old one is retired, not lost", any("curious to a fault" in read(os.path.join(P["persona_dir"], S.RETIRED, x["name"]))
                                              for x in S.retired(P["persona_dir"])) and "curious" in before)
check("…and it says when it applies", "next session" in a["note"])

print("\n5. the routes")
from harness.server import persona_routes as PR  # noqa: E402
code, f = PR.get_flow()
check("the flow comes with the voices", code == 200 and f["voices"]["lfm3"] and f["voices"]["suggested_xai"])
code, p = PR.post_preview({"answers": ans})
check("preview", code == 200 and any(s["step"] == "essence" for s in p["sections"]))
check("create refuses a bad id", PR.post_create({"answers": ans, "id": "Bad Id"})[0] == 400)
code, c = PR.post_create({"answers": {"name": "Moss"}, "id": "moss"})
check("create from the room", code == 200 and c["name"] == "Moss", c)

finish("G-CHARACTER-FLOW")
