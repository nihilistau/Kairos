"""G-LAUNCH-SETUPS — saved setups and the settings change log. OFFLINE.

`harness/launch/setups.py` keeps named key -> value diffs under `var/launch-setups/`; the
Launch window loads one by asking `resolve` for the edits to apply to the CURRENT profile.
`harness/launch/changes.py` is the append-only `var/settings-changes.jsonl`.

  (a) SAVE -> LIST: `running` is true while the launched values match the setup, false the
      moment one launched value differs, and false for all when nothing was launched.
  (b) THE MODEL IS COMPARED BY FILENAME: the same file under another directory still runs.
  (c) RESOLVE: a key the profile no longer has comes back in `skipped`, the rest in `edits`;
      a stored model filename expands to the current model's directory.
  (d) NAMES: `../x` is a ValueError and writes nothing; rename/delete/overwrite behave.
  (e) CHANGE LOG: rows round-trip oldest-first, tail(n) is the last n, an unwritable var dir
      does not raise.

    python harness_tests/g_launch_setups.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _gate import check, finish, require, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
require("tomlkit", "G-LAUNCH-SETUPS", "launch")   # SKIP (exit 2) without the optional extra
sandbox("g_launch_setups")

VAR = tempfile.mkdtemp(prefix="g_launch_setups_var_")
PROF = tempfile.mkdtemp(prefix="g_launch_setups_prof_")
MODELS = tempfile.mkdtemp(prefix="g_launch_setups_models_")
os.environ["SP_LAUNCH_VAR"] = VAR
os.environ["SP_LAUNCH_PROFILES_DIR"] = PROF

cur_model = os.path.join(MODELS, "cur.sp-model").replace("\\", "/")
with open(os.path.join(PROF, "t.toml"), "w", encoding="utf-8") as f:
    f.write('[paths]\nmodel = "%s"\n\n[decode]\nattn_split = 4\ndequant_h8 = 1\n' % cur_model)

from harness.launch import changes, setups, stamp  # noqa: E402

# ── (a) save -> list -> running
check("nothing saved yet", setups.list_all("t") == [])
setups.save("Fast, split", {"decode.attn_split": 4, "paths.model": "cur.sp-model"})
rows = setups.list_all("t")
check("save then list returns the setup", [r["name"] for r in rows] == ["Fast, split"], rows)
check("not running when nothing was launched", rows and rows[0]["running"] is False)
check("the model is stored as a filename",
      json.load(open(os.path.join(VAR, "launch-setups", "fast-split.json"), encoding="utf-8"))
      ["values"]["paths.model"] == "cur.sp-model")

prof = {"_profile_name": "t", "paths": {"model": cur_model}, "decode": {"attn_split": 4}}
stamp.write_launched(prof, {}, "Fast, split")
check("running when every value matches", setups.list_all("t")[0]["running"] is True)

other = os.path.join(tempfile.gettempdir(), "elsewhere", "cur.sp-model").replace("\\", "/")
stamp.write_launched({"_profile_name": "t", "paths": {"model": other},
                      "decode": {"attn_split": 4}}, {}, "x")
check("model compared by basename (other directory still runs)",
      setups.list_all("t")[0]["running"] is True)

stamp.write_launched({"_profile_name": "t", "paths": {"model": cur_model},
                      "decode": {"attn_split": 5}}, {}, "x")
check("not running after one launched value differs", setups.list_all("t")[0]["running"] is False)

stamp.write_launched({"_profile_name": "t", "paths": {"model": "z/other.sp-model"},
                      "decode": {"attn_split": 4}}, {}, "x")
check("not running when the model filename differs", setups.list_all("t")[0]["running"] is False)

# ── (c) resolve
setups.save("Old", {"paths.model": "old.sp-model", "decode.attn_split": 2, "decode.gone": 1})
res = setups.resolve("t", "Old")
check("a key the profile lacks is skipped", res["skipped"] == ["decode.gone"], res)
check("the rest are edits", res["edits"].get("decode.attn_split") == 2
      and "decode.gone" not in res["edits"], res)
check("the model expands into the current model's directory",
      os.path.normpath(res["edits"].get("paths.model", ""))
      == os.path.normpath(os.path.join(MODELS, "old.sp-model")), res)
with open(os.path.join(PROF, "t.toml"), "w", encoding="utf-8") as f:
    f.write("[paths]\nmodel = 'x/models/a.sp-model'\n")
setups.save("Fwd", {"paths.model": "b.sp-model"})
check("the model swap keeps the current string's directory and separators",
      setups.resolve("t", "Fwd")["edits"].get("paths.model") == "x/models/b.sp-model",
      setups.resolve("t", "Fwd"))
setups.delete("Fwd")
with open(os.path.join(PROF, "t.toml"), "w", encoding="utf-8") as f:
    f.write('[paths]\nmodel = "%s"\n\n[decode]\nattn_split = 4\ndequant_h8 = 1\n' % cur_model)
try:
    setups.resolve("t", "nope")
    check("resolve of a missing setup raises KeyError", False)
except KeyError:
    check("resolve of a missing setup raises KeyError", True)

# ── (d) names, overwrite, rename, delete
before = sorted(os.listdir(os.path.join(VAR, "launch-setups")))
for bad in ("../x", "", "a/b", "x" * 61):
    try:
        setups.save(bad, {})
        check("name %r is refused" % bad, False)
    except ValueError:
        check("name %r is refused" % bad, True)
check("a refused name wrote nothing",
      sorted(os.listdir(os.path.join(VAR, "launch-setups"))) == before)
setups.save("Old", {"decode.attn_split": 8})
check("saving an existing name overwrites it",
      [r["name"] for r in setups.list_all("t")].count("Old") == 1
      and json.load(open(os.path.join(VAR, "launch-setups", "old.json"), encoding="utf-8"))
      ["values"] == {"decode.attn_split": 8})
try:
    setups.rename("Old", "Fast, split")
    check("rename onto an existing name raises ValueError", False)
except ValueError:
    check("rename onto an existing name raises ValueError", True)
setups.rename("Old", "Newer")
names = sorted(r["name"] for r in setups.list_all("t"))
check("rename moves the setup", names == ["Fast, split", "Newer"], names)
setups.delete("Newer")
check("delete removes it", [r["name"] for r in setups.list_all("t")] == ["Fast, split"])
for fn, args in ((setups.delete, ("Newer",)), (setups.rename, ("Newer", "Q"))):
    try:
        fn(*args)
        check("%s of a missing name raises KeyError" % fn.__name__, False)
    except KeyError:
        check("%s of a missing name raises KeyError" % fn.__name__, True)

# ── (f) two names, one slug: the second is refused, never an overwrite of the first
setups.save("Slug one", {"decode.attn_split": 4})
for other in ("Slug-one", "slug one", "Slug, one"):
    try:
        setups.save(other, {"decode.attn_split": 9})
        check("saving %r over 'Slug one' is refused" % other, False, "no error")
    except ValueError:
        check("saving %r over 'Slug one' is refused" % other, True)
_s = [r for r in setups.list_all("t") if r["name"].lower().startswith("slug")]
check("the first setup is untouched by the refused saves",
      len(_s) == 1 and _s[0]["name"] == "Slug one" and _s[0]["values"] == {"decode.attn_split": 4}, _s)
setups.save("Slug one", {"decode.attn_split": 5})
check("saving the SAME name again is an update",
      [r["values"] for r in setups.list_all("t") if r["name"] == "Slug one"] == [{"decode.attn_split": 5}])

# ── (e) change log (a fresh var root: write_launched above logged its own restart rows)
os.environ["SP_LAUNCH_VAR"] = VAR = tempfile.mkdtemp(prefix="g_launch_setups_var2_")
check("tail of nothing is empty", changes.tail() == [])
changes.log("launch", "decode.attn_split", 4, 8)
changes.log("settings", "kairos.max_chain", 3, 4)
with open(os.path.join(VAR, "settings-changes.jsonl"), "a", encoding="utf-8") as f:
    f.write("not json\n")
t = changes.tail()
check("rows come back oldest first", [r["what"] for r in t] == ["decode.attn_split",
                                                                 "kairos.max_chain"], t)
check("a row carries at/source/what/old/new",
      set(t[0]) == {"at", "source", "what", "old", "new"} and t[0]["old"] == 4 and t[0]["new"] == 8)
check("tail(1) is the last row", [r["what"] for r in changes.tail(1)] == ["kairos.max_chain"])

blocker = os.path.join(tempfile.mkdtemp(prefix="g_launch_setups_blk_"), "file")
open(blocker, "w").close()
os.environ["SP_LAUNCH_VAR"] = os.path.join(blocker, "sub")      # a dir under a FILE: unwritable
try:
    changes.log("launch", "x", 1, 2)
    check("log with an unwritable var dir does not raise", True)
except Exception as e:                                          # noqa: BLE001
    check("log with an unwritable var dir does not raise", False, repr(e))

finish("G-LAUNCH-SETUPS")
