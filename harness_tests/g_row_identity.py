"""G-ROW-IDENTITY — a row's name is unique, and a tombstone lands only on the row the
ruling named.

THE DEFECT (2026-09-11, found by the public tree's first Linux CI run). `remember()`
minted `ep_tool_{int(time.time() * 1000)}` and used it as the row's `name`. That is a
clock reading, not an identity, and the tree treats it as a primary key:

    store.commit_row   tombstones the rows named in `retired`, BY NAME
    memory/__init__    by_name = {r["name"]: r for r in rows}   (twice) -- collisions vanish
    rank._SURP_CACHE   keyed (name, ts)                         -- two rows, one entry

MEASURED, replaying G-CONFLUENCE's 20-row corpus through the real writer:

    Windows   20 rows in 0.14 s    20 distinct names    0 collisions
    Linux     20 rows in 0.009 s   9-13 distinct names  up to FOUR rows sharing one name

So a legitimate supersession tombstoned every row that happened to share the retired row's
millisecond. On her own lane, observed:

    DEAD  "I like the hour just before sunrise"   killed by: "My favourite soup is pea and ham"
    DEAD  "I feel quietly content tonight"        killed by: "Sam is terrified of open water"

A fact about soup retiring a feeling about sunrise. **The supersede law never proposed any
of these** — `find_superseded` refused them correctly, and the tombstone was applied by a
key the law had not consulted. An invariant enforced in the DECISION and not in the
APPLICATION is enforced nowhere: AGENTS.md §0, on the one rule the store exists to keep.

Her live store was clean when this was found (1561 rows, 1561 distinct names) because her
writes are spaced by conversation on a slower machine. Latent there, live on any faster
box, in any batch write, and in Kairos's Linux CI.

WHY THE SPEED LEG IS WRITTEN THIS WAY. Leg 1 drives the REAL writer as fast as it will go.
It is deliberately sensitive to machine speed in the safe direction: a faster box makes it
a STRONGER test, never a weaker one, and the box that found the bug is the box that runs
this suite. A fixed sleep between writes would have hidden the defect exactly as Windows
did for the life of the file.

MUTANTS (each verified red by name, exit 1, then restored):
    store.new_row_name: drop the monotonic bump, back to int(time.time()*1000)
        -> "every row minted back-to-back has its own name" red on any machine fast
           enough to write twice inside a millisecond, and "the writer never issues one
           name twice" red everywhere
    store.commit_row: match on `name` alone again
        -> "a tombstone lands only on the row the ruling named" red

OFFLINE. No GPU, no daemon, no sidecar.
    python harness_tests/g_row_identity.py
"""
from __future__ import annotations

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _gate import check, finish, sandbox, utf8_stdout   # noqa: E402

utf8_stdout()
SBOX = sandbox("g_row_identity")                # FIRST, before any harness import
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"         # no capture socket per write (gates/README)
os.environ["SP_CAPTURE_ASYNC"] = "0"
os.environ["SP_SEM_MINT"] = "0"
os.environ.pop("SP_SEM_INDEX", None)

import harness.skills.memory as M               # noqa: E402
from harness.skills.memory import store as _store   # noqa: E402

REG = os.path.join(SBOX, "reg.jsonl")
os.environ["SP_RECALL_REGISTRY"] = REG
open(REG, "w").close()

print("1. THE NAME IS AN IDENTITY, NOT A CLOCK READING")

# Back to back, with nothing between them: on a fast machine these land in one millisecond.
names = [_store.new_row_name() for _ in range(500)]
check("every row minted back-to-back has its own name",
      len(set(names)) == len(names),
      "%d names, %d distinct" % (len(names), len(set(names))))
check("...and they are strictly increasing, so the order on disk is the order written",
      all(int(b.rsplit("_", 1)[1]) > int(a.rsplit("_", 1)[1])
          for a, b in zip(names, names[1:])),
      names[:3])

# And from threads, which is what the gateway is.
got, lock = [], threading.Lock()


def _mint():
    mine = [_store.new_row_name() for _ in range(100)]
    with lock:
        got.extend(mine)


ts = [threading.Thread(target=_mint) for _ in range(8)]
for t in ts:
    t.start()
for t in ts:
    t.join()
check("the writer never issues one name twice, across threads",
      len(set(got)) == len(got), "%d minted, %d distinct" % (len(got), len(set(got))))

print("\n2. THROUGH THE REAL WRITER, AS FAST AS IT WILL GO")
for i in range(25):
    M.remember("My locker number is %d" % (1000 + i), source="user turn")
rows = _store._load()
row_names = [r.get("name", "") for r in rows]
check("25 rapid remember() calls produce 25 rows", len(rows) >= 25, len(rows))
check("...each with its own name",
      len(set(row_names)) == len(row_names),
      "%d rows, %d distinct names" % (len(row_names), len(set(row_names))))

print("\n3. A TOMBSTONE LANDS ONLY ON THE ROW THE RULING NAMED")
# The seatbelt, tested where the name fix cannot help: two rows FORCED to share a name.
# commit_row matches (name, ts, text), so the collision cannot redirect the tombstone.
open(REG, "w").close()
_store.invalidate_cache()
M.remember("My cat's name is Tuffy", source="user turn")
tok = M.set_author("self")
try:
    M.remember_about_self("I like the hour just before sunrise", source="her own words")
finally:
    M._AUTHOR.reset(tok)

rows = _store._load()
cat = next(r for r in rows if "Tuffy" in (r.get("text") or ""))
hers = next(r for r in rows if "sunrise" in (r.get("text") or ""))
hers["name"] = cat["name"]                       # the collision, injected
_store._save_all(rows)
check("the collision was really injected",
      len({r.get("name") for r in _store._load()}) < len(_store._load()),
      [r.get("name") for r in _store._load()])

M.remember("My cat's name is Milo", source="user turn")     # supersedes Tuffy, and only it
after = _store._load()
dead = [r for r in after if r.get("lifecycle")]
check("the supersession actually fired", any("Tuffy" in (r.get("text") or "") for r in dead),
      [(r.get("text") or "")[:40] for r in dead])
check("a tombstone lands only on the row the ruling named — her line is untouched",
      not any("sunrise" in (r.get("text") or "") for r in dead),
      [(r.get("text") or "")[:44] for r in dead])
check("...and she is still live",
      any("sunrise" in (r.get("text") or "") and not r.get("lifecycle") for r in after),
      [(r.get("text") or "")[:44] for r in after if not r.get("lifecycle")])

finish("G-ROW-IDENTITY")
