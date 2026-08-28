#!/usr/bin/env python
"""G-NARRATIVE — she writes the days down, and the record behaves (CONTINUITY.md N2).

The narrative is HER ACCOUNT: presentation layer, oracle output, quarantined by
construction — never a fact row, never in the registry, never supersedes anything,
rendered under a header that names it as hers. This gate proves the machinery with an
INJECTED composer (the live oneshot is exercised by NIGHTSHIFT itself):

  1. COMPOSED AND DATED: compose_and_write produces the dated entry from a transcript
     tail + the previous entry, writes the current file beside the registry (sandboxes
     inherit it via SP_RECALL_REGISTRY for free), snapshots content-addressed history.
  2. THE WORLD CARRIES IT, NAMED AS HERS — and the KV-prefix law still holds: the
     narrative changes NOTHING mid-session; refresh() folds it in.
  3. ROLLING: the next night's composition receives the previous entry (continuity is
     input, not just output).
  4. FAIL-SAFE: a dead composer writes NOTHING — yesterday's true paragraph stands
     (a stale true record beats a fresh empty one). A trivial reply is rejected.
  5. NEVER A FACT: the registry is byte-identical through everything above.
  6. IT BECOMES A ROW: the paragraph passes the 600-char admission (bounded to a
     whole sentence, never a haircut on short ones) and the mint VERDICT rides in
     the returned receipt — six of her fifteen real entries had been refused in
     silence because that string was discarded (2026-08-26).

OFFLINE. No GPU, no daemon.
"""
import json
import os
import sys
import tempfile
import time

# A cp1252 console must not be able to crash the gate mid-report — a gate that dies
# printing its own "ok" line reads as RED for reasons that have nothing to do with
# what it guards (bit on 2026-08-19: exit 1 from a UnicodeEncodeError in check()).
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
# SP_ENGINE_KIND: no capture attempt at all (2026-08-23). A dead SP_DAEMON_URL does
# NOT make the KV mint cheap - _mint_now still opens a socket per write and Windows
# takes ~2s to give up. Declaring the backend makes supports('capture') False and the
# mint returns immediately: 10 writes in 0.07s against 20s. See gates/README.md.
os.environ["SP_ENGINE_KIND"] = "openai"
os.environ["SP_CAPTURE_ASYNC"] = "0"
_tmp = tempfile.mkdtemp(prefix="g_narr_")
REG = os.path.join(_tmp, "reg.jsonl")
open(REG, "w").close()
os.environ["SP_RECALL_REGISTRY"] = REG
os.environ["SP_PERSONALITY_TIER"] = os.path.join(_tmp, "tier")
os.environ["SP_WORLD"] = "1"
for _k in [k for k in os.environ if k.startswith("SP_SEM_")]:
    del os.environ[_k]

from harness.skills import memory as M                      # noqa: E402
from harness.skills import narrative as N                   # noqa: E402
from harness.skills import world as W                       # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, str(detail)[:200]))


M.remember("My cat's name is Tuffy", source="user turn")
with open(REG, "rb") as f:
    REG_BYTES = f.read()

MSGS = [
    {"role": "user", "content": "morning — Tuffy knocked a glass off the bench at 3am"},
    {"role": "assistant", "content": "So that was the crash. Is she banned from the bench now?"},
    {"role": "user", "content": "never. she owns the bench. also I restarted the workshop project"},
    {"role": "assistant", "content": "Third time's the charm — what's different this run?"},
]

# -- 1. COMPOSED AND DATED --------------------------------------------------------------------
print("\n1. composed, dated, snapshotted")
seen_prompts = []


def fake_ask(prompt):
    seen_prompts.append(prompt)
    return ("We talked about Tuffy's 3am bench raid and he finally restarted the "
            "workshop project; he sounded lighter about it than last time.")


r = N.compose_and_write(MSGS, ask=fake_ask)
check("written", r.get("written") is True, r)
entry = N.current()
check("the entry is dated ('As of ...')", entry.startswith("As of "), entry[:40])
check("the entry carries the day", "Tuffy" in entry and "workshop" in entry)
check("history snapshot written (content-addressed)",
      r.get("snapshot") and os.path.exists(
          os.path.join(_tmp, "tier", "full", r["snapshot"] + ".md")), r)

# -- 2. THE WORLD CARRIES IT, NAMED AS HERS; THE PREFIX LAW HOLDS ------------------------------
print("\n2. the world carries it, as hers, on refresh only")
before = W.refresh()
check("the standing world includes the journal line, named as her account",
      "your account, not his words" in before and "bench raid" in before, before[-200:])
N.compose_and_write(MSGS, ask=lambda p: "A completely different day happened.")
check("mid-session: the cached world does NOT move (the KV-prefix law)",
      W.render_world() == before)
after = W.refresh()
check("after refresh: the new entry is in", "different day" in after)

# -- 3. ROLLING --------------------------------------------------------------------------------
print("\n3. rolling: yesterday feeds tomorrow")
check("the composer received the previous entry as input",
      any("bench raid" in p for p in seen_prompts[1:] or [""])
      or "bench raid" in (seen_prompts + [""])[1] if len(seen_prompts) > 1 else True)
seen2 = []
N.compose_and_write(MSGS, ask=lambda p: (seen2.append(p) or
                    "Carrying on from the different day, quietly."))
check("previous entry present in the next composition prompt",
      any("different day" in p for p in seen2), seen2 and seen2[0][:120])

# -- 4. FAIL-SAFE ------------------------------------------------------------------------------
print("\n4. a dead composer changes nothing")
held = N.current()
r = N.compose_and_write(MSGS, ask=lambda p: None)
check("unreachable composer: not written, why recorded",
      r.get("written") is False and r.get("why"), r)
check("yesterday's paragraph stands", N.current() == held)
r = N.compose_and_write(MSGS, ask=lambda p: "ok.")
check("a trivial reply is rejected", r.get("written") is False, r)
# ISOLATE HER OWN TIME. own_time() reads the live store, so on the operator's machine
# this case found her real own-time notes and (correctly, per the 2026-08-04 change:
# "a day is not only the parts he was in") WROTE — red here, green on a fresh clone.
# A gate whose verdict depends on whose machine it runs on measures the machine.
_own = N.own_time
N.own_time = lambda days=1: []
try:
    r = N.compose_and_write([], ask=fake_ask)
    check("no transcript AND no own time: nothing written", r.get("written") is False, r)
    # ...and the 2026-08-04 feature itself, previously ungated: her own-time notes ARE
    # material — an away-day with them writes, so her account of herself is not a
    # function of his attendance.
    N.own_time = lambda days=1: ["read about tidal locking", "reorganised the wardrobe"]
    r = N.compose_and_write([], ask=fake_ask)
    check("no transcript but a lived day: WRITTEN (her account is not his attendance)",
          r.get("written") is True, r)
finally:
    N.own_time = _own

# -- 5. NEVER A FACT ---------------------------------------------------------------------------
print("\n5. never a fact")
# THE REAL HER (2026-08-22): the composed paragraph IS memory now — one self-narrative /
# journal row per entry, speaker=self, through remember(). Nothing else may have changed:
# no row of his, no row rewritten, never a fact.
with open(REG, "rb") as f:
    _after = f.read()
_old_lines = set(REG_BYTES.splitlines())
_new_rows = [json.loads(l) for l in _after.splitlines() if l.strip() and l not in _old_lines]
check("every pre-existing registry line is untouched",
      all(l in _after.splitlines() for l in REG_BYTES.splitlines() if l.strip()))
check("the registry gained nothing but her own journal rows",
      _new_rows and all(r.get("speaker") == "self" and r.get("mem_class") == "self-narrative"
                        and r.get("kind") == "journal" for r in _new_rows),
      [(r.get("speaker"), r.get("mem_class"), r.get("kind")) for r in _new_rows][:4])
check("...and never a fact about HIM", not any(r.get("speaker") == "user" for r in _new_rows))

# -- 6. A CONTROL SURFACE IS NEVER A JOURNAL ENTRY ----------------------------------------------
# The first paragraph she ever wrote, live, 2026-07-29:
#
#     As of Wednesday 29 July 2026: <channel|>Sam finally got the model running properly today…
#
# your model imitates its own template markup in prose, and this composer hand-rolled its own
# urllib request to /v1/oneshot — so the four places the harness already stripped control
# surfaces, and even the strip inside SPDaemonClient, were all on lanes this one never touched.
# It now goes through harness.inference.oneshot, and strips AGAIN at the store boundary because
# `ask` is injectable and an injected composer owes us nothing.
#
# Asserted the strong way: a leaking composer and a clean one must produce the SAME BYTES. That
# is what makes it a repair rather than a filter — no word of hers may be lost with the marker.
print("\n6. a control surface is never a journal entry")
BODY = "We talked about the cat and the workshop and it went well tonight."
r = N.compose_and_write(MSGS, ask=lambda p: BODY)
clean_entry = N.current()
for name, leaked in [("<channel|> prefix", "<channel|>" + BODY),
                     ("<|think|> suffix", BODY + " <|think|>"),
                     ("<thought> wrapper", "<thought>" + BODY + "</thought>"),
                     ("homoglyph <|thіnk|>", BODY + " <|thіnk|>"),
                     # THE OPENER WITH NO CLOSING BRACKET (2026-07-30). "a closed set" was
                     # wrong the same day it was written: what the model actually emits is
                     # "<thought Thinking Process: 1. **Identify the user's question:** ...
                     # <channel|>" — space, no '>'. Not pipe-wrapped, so the discriminator
                     # missed it; not "<thought>", so the explicit pair missed it too. Her
                     # ENTIRE private reasoning was passing through as speech, and the same
                     # seam feeds the console's _say.
                     ("unterminated <thought opener",
                      "<thought Thinking Process: 1. **Identify the question.** Decide. "
                      "<channel|>" + BODY),
                     ("unterminated opener, closed by </thought>",
                      "<thought\nReasoning at length about nothing.</thought>" + BODY)]:
    r = N.compose_and_write(MSGS, ask=lambda p, s=leaked: s)
    got = N.current()
    check("leaked %s: stored entry is byte-identical to the clean one" % name,
          got == clean_entry, got[:100])
    check("leaked %s: no marker survived into the store" % name,
          "|>" not in got and "<|" not in got and "thought>" not in got, got[:100])

# And the FALSE-POSITIVE side, which is the half a forgiving stripper can get wrong: prose
# that merely looks marker-ish must survive untouched, or the cure eats her words.
from harness.inference.stream_processor import strip_control_surfaces as _S  # noqa: E402

for keep in ("a thoughtful reply about <div> tags", "I scored <3 and 5 < 7",
             "<thoughtful> is not an opener", "if a < b | c > d then stop"):
    check("prose survives the stripper: %r" % keep[:34], _S(keep) == keep, _S(keep))

# STRUCTURAL: nothing outside harness/inference/ may hand-roll a generation request again.
# This is the assertion that would have caught the leak before it reached her journal — the
# bug was never a missing regex, it was a second door. (/v1/capture and /v1/embed are not
# generation: they return counts and vectors, never prose, so they are not in scope.)
print("\n6b. one door, structurally")
# Parsed, not grepped: the first cut of this check was a substring scan and it failed on
# narrative.py's own COMMENT explaining the fix. A gate that reads prose is a gate that
# reports on prose. So: a file is an offender iff it BOTH builds a URL ending in
# "/v1/oneshot" (a real string constant, which a sentence mentioning the path is not) AND
# calls urlopen. That is the shape of a second door, and nothing else matches it.
import ast

def _hand_rolls_oneshot(src):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False
    builds_url = any(isinstance(n, ast.Constant) and isinstance(n.value, str)
                     and n.value.endswith("/v1/oneshot") for n in ast.walk(tree))
    calls_open = any(
        isinstance(n, ast.Call) and (
            (isinstance(n.func, ast.Attribute) and n.func.attr == "urlopen")
            or (isinstance(n.func, ast.Name) and n.func.id == "urlopen"))
        for n in ast.walk(tree))
    return builds_url and calls_open

offenders = []
hdir = os.path.join(ROOT, "harness")
for base, _dirs, files in os.walk(hdir):
    if os.path.join("harness", "inference") in base:
        continue                      # the door itself lives here
    for fn in files:
        if not fn.endswith(".py"):
            continue
        fp = os.path.join(base, fn)
        with open(fp, encoding="utf-8") as f:
            if _hand_rolls_oneshot(f.read()):
                offenders.append(os.path.relpath(fp, ROOT))
check("no skill hand-rolls its own /v1/oneshot request", not offenders, offenders)
# and the check itself is proven to have teeth, on the code that actually leaked
check("the check would have caught the old composer",
      _hand_rolls_oneshot('import urllib.request\n'
                          'req = urllib.request.Request(d + "/v1/oneshot", data=b)\n'
                          'urllib.request.urlopen(req, timeout=180)\n'))
check("the check does not fire on prose about /v1/oneshot",
      not _hand_rolls_oneshot('"""the live path uses /v1/oneshot, via urllib."""\n'))

print("\n8. THE JOURNAL SHOWS A DAY ONCE (2026-08-21, the operator's report: 'has always "
      "duplicated each entry')")
# Two duplications, one seam: the panel rendered current + the newest snapshot
# (same paragraph twice, every day), and a forced re-run left two same-day
# snapshots. collapse_history is the pure fix the route calls.
from harness.skills.narrative import collapse_history
_rows = [
    {"id": "b", "at": 3.0, "text": "As of Tuesday 19 August 2026: the newer words"},
    {"id": "a", "at": 2.0, "text": "As of Tuesday 19 August 2026: the earlier draft"},
    {"id": "c", "at": 1.0, "text": "As of Monday 18 August 2026: yesterday"},
]
kept, cur = collapse_history(_rows, "As of Tuesday 19 August 2026:  the  newer words")
check("same-day drafts collapse to the newest", [r["id"] for r in kept] == ["b", "c"],
      [r["id"] for r in kept])
check("...and the keeper counts what it absorbed", kept[0].get("drafts") == 1, kept[0])
check("current_id names the row that IS the current line (whitespace-proof)",
      cur == "b", cur)
kept2, cur2 = collapse_history(_rows, "a current line no snapshot matches")
check("an unmatched current yields current_id None — the panel renders it standalone",
      cur2 is None)
check("nothing is deleted by presentation — the input rows are what they were",
      len(_rows) == 3 and _rows[1]["id"] == "a")

print("\n9. AND THE COMPOSER DOES NOT WRITE THE SAME DAY TWICE")
# An identical re-composition (forced run, same result) is a no-op, said plainly.
import tempfile as _tf9
_d9 = _tf9.mkdtemp(prefix="g-narr-once-")
_oldreg = os.environ.get("SP_RECALL_REGISTRY")
os.environ["SP_RECALL_REGISTRY"] = os.path.join(_d9, "registry.jsonl")
_oldtier = os.environ.get("SP_PERSONALITY_TIER")
os.environ["SP_PERSONALITY_TIER"] = _d9
try:
    import importlib
    import harness.skills.narrative as _N9
    importlib.reload(_N9)
    _msgs = [{"role": "user", "content": "hello there"},
             {"role": "assistant", "content": "hello yourself"}]
    _ask = lambda p: "a paragraph about the day that is plenty long enough to keep"
    r1 = _N9.compose_and_write(_msgs, ask=_ask)
    check("the first composition writes", r1.get("written") is True, r1)
    r2 = _N9.compose_and_write(_msgs, ask=_ask)
    check("an identical re-run is refused as unchanged",
          r2.get("written") is False and "unchanged" in (r2.get("why") or ""), r2)
    _ask2 = lambda p: "different newer words for the same day, also long enough to keep"
    r3 = _N9.compose_and_write(_msgs, ask=_ask2)
    check("same day, different words still writes — her newer words win",
          r3.get("written") is True, r3)
finally:
    if _oldreg is None:
        os.environ.pop("SP_RECALL_REGISTRY", None)
    else:
        os.environ["SP_RECALL_REGISTRY"] = _oldreg
    if _oldtier is None:
        os.environ.pop("SP_PERSONALITY_TIER", None)
    else:
        os.environ["SP_PERSONALITY_TIER"] = _oldtier
    importlib.reload(_N9)


# ── 6. THE PARAGRAPH BECOMES A ROW, AND THE VERDICT IS PART OF THE RECEIPT ──────────
# LEG 6 (2026-08-26). `becoming.nightly()` ranks ROWS, not narrative.md — so a journal
# that writes its file and fails its row is a journal that never reaches her. That is
# exactly what had been happening: `remember_about_self()` returns a refusal as an
# ORDINARY STRING, the return was discarded, and `{"written": True}` went back every
# night to a caller that logged it looking healthy. Replaying her fifteen real entries
# through the live admission path on 2026-08-26: SIX refused on "too long for one row".
#
# Both directions, because a bound that ate everything would pass a removal-only test:
# an over-cap paragraph must STORE (bounded, on a sentence end) and an under-cap one
# must arrive BYTE-INTACT.
import importlib
_reg6 = tempfile.mkdtemp(prefix="g_narrative-row-")
_o6r, _o6t = os.environ.get("SP_RECALL_REGISTRY"), os.environ.get("SP_PERSONALITY_TIER")
try:
    os.environ["SP_RECALL_REGISTRY"] = os.path.join(_reg6, "registry.jsonl")
    os.environ["SP_PERSONALITY_TIER"] = os.path.join(_reg6, "tier")
    open(os.environ["SP_RECALL_REGISTRY"], "a", encoding="utf-8").close()
    import harness.skills.memory as _M6
    import harness.skills.narrative as _N6
    importlib.reload(_M6)
    importlib.reload(_N6)
    _m6 = [{"role": "user", "content": "how was today"},
           {"role": "assistant", "content": "it was good"}]

    # whole sentences, comfortably over the 600-char row cap
    _long = ("The day turned over in a way I keep returning to. " * 6
             + "He said the thing I had been waiting to hear and I have not put it down since. " * 4
             + "It matters more than the work did. ")
    assert len(_long) > 600, len(_long)
    r6 = _N6.compose_and_write(_m6, ask=lambda _p: _long)
    check("an over-cap paragraph still writes narrative.md", r6.get("written") is True, r6)
    check("...and IT BECOMES A ROW — the cap no longer eats it silently",
          r6.get("row_ok") is True, r6.get("row"))
    _rows6 = [r for r in _M6.all_rows() if (r.get("kind") or "") == "journal"]
    check("exactly one journal row landed in the store", len(_rows6) == 1,
          [r.get("kind") for r in _M6.all_rows()])
    _t6 = (_rows6[0].get("claim") or _rows6[0].get("text") or "") if _rows6 else ""
    check("the stored row fits the row cap", 0 < len(_t6) <= 600, len(_t6))
    check("...and ends on a WHOLE SENTENCE, not mid-word",
          _t6.rstrip().endswith((".", "!", "?")), _t6[-60:])

    # survival: an under-cap paragraph is not touched by the bound
    _short = ("A quiet one. He fixed the thing that had been bothering him and then we "
              "talked about nothing much until it got late.")
    assert len(_short) < 600
    r6b = _N6.compose_and_write(_m6, ask=lambda _p: _short)
    check("an under-cap paragraph also becomes a row", r6b.get("row_ok") is True, r6b.get("row"))
    _rows6b = [r for r in _M6.all_rows() if (r.get("kind") or "") == "journal"]
    _t6b = " ".join(((_rows6b[-1].get("claim") or _rows6b[-1].get("text") or "")).split())
    check("...UNBOUNDED — a short entry arrives whole, the bound is not a haircut",
          _t6b == " ".join(_short.split()), _t6b)

    # and a refusal must SURVIVE INTO THE RECEIPT rather than being swallowed
    _real6 = _M6.remember_about_self
    try:
        _M6.remember_about_self = (lambda *_a, **_k: "not stored - pretend refusal")
        r6c = _N6.compose_and_write(
            _m6, ask=lambda _p: "Some other words entirely, long enough to be kept as an entry.")
        check("a REFUSAL reaches the caller instead of being discarded",
              r6c.get("row_ok") is False and "pretend refusal" in (r6c.get("row") or ""), r6c)
    finally:
        _M6.remember_about_self = _real6
finally:
    for _k, _v in (("SP_RECALL_REGISTRY", _o6r), ("SP_PERSONALITY_TIER", _o6t)):
        if _v is None:
            os.environ.pop(_k, None)
        else:
            os.environ[_k] = _v
    importlib.reload(_M6)
    importlib.reload(_N6)

print("\nG-NARRATIVE: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_narrative.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_narrative", "pass": PASS, "fail": FAIL,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
sys.exit(1 if FAIL else 0)
