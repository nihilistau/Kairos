"""G-LAUNCH-PROFILE — the Launch window edits her profile without eating it. OFFLINE.

`harness/launch/profile_doc.py` is the only thing the Launch window writes her profile
through. The profile is a hand-annotated toml (commented-out alternatives, a note on every
kernel knob), so what can go wrong is quiet: a round-trip through a dict drops every comment.

  (a) READ gives the live value, the knob's own trailing comment as help, and a hash.
  (b) AN EDIT CHANGES ONE LINE. A commented-out line stays byte-identical, the edited
      line keeps its trailing comment, every other line is untouched.
  (c) TYPES FOLLOW THE EXISTING KEY: 6 -> 6.0 for a float, "0" -> 0 for an int.
  (d) AN UNKNOWN KEY IS REFUSED (KeyError), file untouched.
  (e) A STALE HASH IS REFUSED (StaleError), for apply and save_raw alike.
  (f) INVALID RAW TOML IS REFUSED (ValueError), file untouched.
  (g) MUTANT: `apply` run over a plain-dict round-trip (comments gone) must turn the SAME
      assertions as (b) red -- the real writer path swapped, not a mutant written in the gate.

    python harness_tests/g_launch_profile.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _gate import check, finish, require, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
require("tomlkit", "G-LAUNCH-PROFILE", "launch")   # SKIP (exit 2) without the optional extra
sandbox("g_launch_profile")

pdir = tempfile.mkdtemp(prefix="g_launch_profile_dir_")
os.environ["SP_LAUNCH_PROFILES_DIR"] = pdir
FIXTURE = (
    "# fixture profile\n"
    "[paths]\n"
    "# model = 'old.sp-model'\n"
    "model = 'new.sp-model'  # the live one\n"
    "\n"
    "[kv]\n"
    "moe_cache_gb = 6.0\n"
    "\n"
    "[decode]\n"
    "attn_split = 1   # SP_G4_ATTN_SPLIT near-tie wording\n"
)
PATH = os.path.join(pdir, "fx.toml")


def _put(text):
    with open(PATH, "wb") as f:
        f.write(text.encode("utf-8"))


def _bytes():
    with open(PATH, "rb") as f:
        return f.read()


_put(FIXTURE)

from harness.launch import profile_doc as pd  # noqa: E402

check("profile_path honours SP_LAUNCH_PROFILES_DIR", pd.profile_path("fx") == PATH, pd.profile_path("fx"))
r = pd.read("fx")
check("read: hash is sha256 of the file bytes", r["hash"] == hashlib.sha256(_bytes()).hexdigest())
check("read: values flatten section.key", r["values"].get("paths.model") == "new.sp-model", r["values"])
check("read: help is the trailing comment", r["help"].get("decode.attn_split", "").startswith("SP_G4_ATTN_SPLIT"), r["help"])
check("read: text is the file", r["text"] == FIXTURE)

# (b) one-line edit. The assertions are a function so (g) can run THE SAME ones against a
# mutant writer and demand they fail.
def edit_results():
    _put(FIXTURE)
    h = pd.read("fx")["hash"]
    out = pd.apply("fx", {"paths.model": "old.sp-model"}, h)
    after = _bytes().decode("utf-8").split("\n")
    before = FIXTURE.split("\n")
    diff = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    return out, h, after, {
        "edit: exactly one line differs": len(before) == len(after) and len(diff) == 1,
        "edit: commented-out line byte-identical": "# model = 'old.sp-model'" in after,
        "edit: trailing comment survives": any(
            "old.sp-model" in l and l.endswith("# the live one") for l in after),
    }


out, _h, after, res = edit_results()
for _name, _ok in res.items():
    check(_name, _ok, after)
check("edit: apply returns the new read", out["values"]["paths.model"] == "old.sp-model" and out["hash"] != r["hash"])

# (b2) a literal-quoted value stays literal: the line is the fixture's own, one value swapped.
LIT = "[paths]\nmodel = 'models/a/old.sp-model'  # c\n[kv]\nmoe_cache_gb = 6.0\n"
_put(LIT)
pd.apply("fx", {"paths.model": "models/a/new.sp-model"}, pd.read("fx")["hash"])
_la, _lb = LIT.split("\n"), _bytes().decode("utf-8").split("\n")
check("literal: the edited line keeps its quotes and comment",
      _lb[1] == "model = 'models/a/new.sp-model'  # c", _lb)
check("literal: that is the only line that differs",
      len(_la) == len(_lb) and [i for i, (a, b) in enumerate(zip(_la, _lb)) if a != b] == [1], _lb)
_put(FIXTURE)
out = pd.apply("fx", {"paths.model": "old.sp-model"}, pd.read("fx")["hash"])

# (c) types
h = out["hash"]
out = pd.apply("fx", {"kv.moe_cache_gb": 6}, h)
check("float key writes 6.0", "moe_cache_gb = 6.0" in _bytes().decode(), _bytes())
out = pd.apply("fx", {"decode.attn_split": "0"}, out["hash"])
txt = _bytes().decode()
check("int key writes 0 as an int", "attn_split = 0" in txt and "'0'" not in txt and '"0"' not in txt, txt)
check("int edit keeps its trailing comment", "# SP_G4_ATTN_SPLIT" in txt)
try:
    pd.apply("fx", {"decode.attn_split": "abc"}, out["hash"])
    check("untyped value refused", False, "no error")
except ValueError:
    check("untyped value refused (ValueError)", True)

# (d) unknown key
b0 = _bytes()
h0 = hashlib.sha256(b0).hexdigest()
try:
    pd.apply("fx", {"decode.nope": 1}, h0)
    check("unknown key refused", False, "no error")
except KeyError as e:
    check("unknown key refused (KeyError names it)", "decode.nope" in str(e), e)
check("unknown key leaves file untouched", _bytes() == b0)

# (e) stale
try:
    pd.apply("fx", {"kv.moe_cache_gb": 7}, "0" * 64)
    check("stale hash refused by apply", False, "no error")
except pd.StaleError:
    check("stale hash refused by apply (StaleError)", True)
try:
    pd.save_raw("fx", FIXTURE, "0" * 64)
    check("stale hash refused by save_raw", False, "no error")
except pd.StaleError:
    check("stale hash refused by save_raw (StaleError)", True)
check("stale leaves file untouched", _bytes() == b0)

# (f) invalid raw
try:
    pd.save_raw("fx", "[paths\n", h0)
    check("invalid toml refused", False, "no error")
except ValueError:
    check("invalid toml refused (ValueError)", True)
check("invalid toml leaves file untouched", _bytes() == b0)
ok = pd.save_raw("fx", FIXTURE + "extra = 1\n", h0)
check("valid raw saved verbatim", _bytes().decode() == FIXTURE + "extra = 1\n" and ok["hash"] != h0)

# (f2) a list key takes a list and a table key a dict, never a string
_keep = _bytes()
_put(FIXTURE + "lanes = [1, 2]\n[extra]\nopts = {a = 1}\n")
_h = hashlib.sha256(_bytes()).hexdigest()
try:
    pd.apply("fx", {"decode.lanes": "oops"}, _h)
    check("a string for a list key is refused", False, "no error")
except ValueError:
    check("a string for a list key is refused (ValueError)", True)
try:
    pd.apply("fx", {"extra.opts": "oops"}, _h)
    check("a string for a table key is refused", False, "no error")
except ValueError:
    check("a string for a table key is refused (ValueError)", True)
_o = pd.apply("fx", {"decode.lanes": [3, 4]}, _h)
check("a list for a list key is written", _o["values"]["decode.lanes"] == [3, 4], _o["values"].get("decode.lanes"))
_put(_keep.decode())

# (g) MUTANT, REAL THIS TIME: swap the document `apply` edits for a plain dict (tomllib parse,
# tomlkit.dumps of the dict) -- the round-trip that eats comments -- run the SAME (b)
# assertions through it, and demand they FAIL. The previous leg only showed that a mutant
# writer loses comments, which no code of ours was involved in.
import tomllib  # noqa: E402
import types  # noqa: E402

_real_tk = pd.tomlkit
pd.tomlkit = types.SimpleNamespace(parse=lambda text: tomllib.loads(text), dumps=_real_tk.dumps)
try:
    _out_m, _h_m, _after_m, res_m = edit_results()
finally:
    pd.tomlkit = _real_tk
check("MUTANT (dict round-trip in apply) turns the edit assertions red",
      not all(res_m.values()), res_m)
check("MUTANT: it is the comment checks that fail, not the one-line edit itself",
      not res_m["edit: commented-out line byte-identical"]
      and not res_m["edit: trailing comment survives"], res_m)
_out_r, _h_r, _after_r, res_r = edit_results()
check("restored: the same assertions are green again", all(res_r.values()), res_r)

finish("G-LAUNCH-PROFILE")
