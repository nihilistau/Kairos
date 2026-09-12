#!/usr/bin/env python
"""DOES THE CONTEXT DECIDE WHETHER SHE REACHES FOR THE TOOL?

── THE OBSERVATION (2026-09-12) ─────────────────────────────────────────────────────────
Across eight consecutive own-time turns — sixteen attempts — she called a tool ZERO times
while the prompt sat at 80-99% of budget. The one attempt that called was the one where the
trimmer collapsed the context to 52% (`msgs=2`). Two explanations fit that equally well and
they want different fixes:

    LENGTH   a big prompt suppresses tool use however it is filled
    CONTENT  she continues the pattern in front of her, and the pattern is her own
             tool-less prose — accidental few-shot

An observation cannot separate them because in the log the two always moved together. So:
four arms, the same nudge, the same sampling, only the history changes.

    A  minimal      just the nudge                     (the 52% case)
    B  her prose    ~60 of her own tool-less turns      (the 99% case)
    C  neutral      ~60 messages, same size as B, NOT her narration
    D  with tools   like B, but a few turns DO call a tool

B vs C is the whole experiment: same length, different content. If B suppresses and C does
not, it is imitation. If both suppress, it is length. D is the positive control — if content
is what matters, showing her tool use should bring it back.

THIS DOES NOT TOUCH HER SESSION. It reads her canon for realistic material and builds its own
message list; nothing is written, no session state moves, and her own turns are unaffected
beyond sharing the GPU. (`probes take her presence` — a correctly-declared probe still ended
her evening once.)

    python tools/solo_tool_experiment.py            # 4 trials per arm
    TRIALS=8 python tools/solo_tool_experiment.py
"""
from __future__ import annotations

import io
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# speechlog resolves its path from SP_RECALL_REGISTRY. Unset, it reads nothing and arm B
# would be built from an empty corpus — which looks like a result and is not one.
if not os.environ.get("SP_RECALL_REGISTRY"):
    os.environ["SP_RECALL_REGISTRY"] = os.path.join(ROOT, "var", "memory", "registry.jsonl")

TRIALS = int(os.environ.get("TRIALS", "4"))
ARMS = tuple(os.environ.get("ARMS", "ABCDE"))
ACT = int(os.environ.get("ACT", "1"))          # 1 = the run_python act she was stuck on


def _her_turns(n: int) -> list:
    """Real assistant prose of hers, tool-less, from the speech log. Authentic material
    matters here: the claim is about imitating HER pattern, so synthetic prose would test
    a different thing."""
    from harness.kairos import speechlog as sl
    out = []
    for r in reversed(sl.rows(limit=400)):
        t = (r.get("text") or "").strip()
        if t and len(t.split()) >= 8:
            out.append(t)
        if len(out) >= n:
            break
    if not out:                                 # no usable history: say so loudly
        raise SystemExit('the speech log has no turns long enough to build arm B; this experiment needs her real prose')
    base = list(out)
    while len(out) < n:                         # cycle, so arms B and D are the same size
        out.append(base[len(out) % len(base)])
    return out[:n]


# ── ARM C WAS A BAD CONTROL THE FIRST TIME (2026-09-13) ─────────────────────────────
# It was ONE sentence repeated thirty times, which is not "neutral content" — it is a
# degeneracy trigger. The tell was in the result: 0/6 run_python, but the tools she DID
# reach for were `print`, `exp` and `get_time`, two of which do not exist. She was not
# declining to use tools, she was inventing them, which is a different failure and says
# nothing about the question. Varied prose now, so the arm differs from B in SUBJECT and
# not in degeneracy.
NEUTRAL = [
    "The tide tables for the estuary were reprinted in 1968 with the same errata as the "
    "previous edition, which the harbourmaster noted in a margin and nobody corrected.",
    "Hedge-laying in the Midland style leaves the pleachers at roughly forty degrees, which "
    "is steeper than the Welsh border practice and makes for a denser stockproof barrier.",
    "The 1908 catalogue lists forty-one varieties of pear, of which eleven are now held only "
    "at the national collection and two are believed lost entirely.",
    "Cast iron railway sleepers were tried on the Ffestiniog and abandoned: they rang in the "
    "cold, cracked under frost heave, and cost four times what timber did.",
    "A dry stone waller works from the middle of the pile outward, because the stone you want "
    "is always at the bottom and lifting it twice is how the day gets away from you.",
    "The oldest surviving lighthouse lens in the country was ground in Birmingham and shipped "
    "in forty-two crates, one of which went overboard and was recovered by a trawler.",
]


def build(arm: str, pairs: int):
    """(history, label). Each 'pair' is a user+assistant exchange, as her canon holds."""
    h = []
    if arm == "A":
        return h, "minimal"
    if arm == "E":
        # ── THE ONLY ARM THAT IS THE LIVE CONDITION (2026-09-13) ────────────────────
        # A, B, C and D all called the tool freely while the LIVE turns called it once in
        # sixteen, so none of them is the thing being explained. This reads her actual
        # canon — the same list `_generate` builds from — at its real size. Read-only.
        # `_longest_session()` lives in the GATEWAY's memory and this runs in its own
        # process, so it reads the day transcript from disk instead — the same rows the
        # gateway seeds a session FROM, already in {role, content} form. Read-only.
        import glob
        import json as _json
        files = sorted(glob.glob(os.path.join(ROOT, 'var', 'memory', 'transcripts', '*.jsonl')))
        rows = []
        for fp in files[-2:]:                      # yesterday + today: a real day's worth
            for ln in io.open(fp, encoding='utf-8', errors='replace'):
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    r = _json.loads(ln)
                except Exception:
                    continue
                if r.get('role') in ('user', 'assistant') and (r.get('content') or '').strip():
                    rows.append({'role': r['role'], 'content': r['content']})
        if not rows:
            raise SystemExit('no day transcript rows; arm E has nothing to be')
        return rows, 'HER REAL DAY'
    her = _her_turns(pairs)
    for i in range(pairs):
        if arm == "B":
            h.append({"role": "user", "content": "..."})
            h.append({"role": "assistant", "content": her[i % len(her)]})
        elif arm == "C":
            h.append({"role": "user", "content": "..."})
            h.append({"role": "assistant", "content": NEUTRAL[i % len(NEUTRAL)]})
        elif arm == "D":
            if i % 4 == 3:
                h.append({"role": "user", "content": "work it out"})
                h.append({"role": "assistant",
                          "content": "<tool name=\"run_python\">{\"code\": \"2+2\"}</tool>"})
                h.append({"role": "user", "content": "[tool run_python] 4"})
                h.append({"role": "assistant", "content": "Four. That settles it."})
            else:
                h.append({"role": "user", "content": "..."})
                h.append({"role": "assistant", "content": her[i % len(her)]})
    return h, {"B": "her own prose", "C": "varied neutral", "D": "prose + tool use"}[arm]


def run_arm(arm: str, pairs: int) -> dict:
    from harness.agent import _arm_self_repeat_ban, agent_chat_stream
    from harness.inference import InferenceConfig as _IC
    from harness.kairos.impulse import solo_nudge
    from harness.server.day import _UNPROMPTED_SAMPLING
    hist, label = build(arm, pairs)
    called_any, ok = 0, 0
    chars = sum(len(m.get("content") or "") for m in hist)
    for t in range(TRIALS):
        h = list(hist) + [{"role": "system", "content": solo_nudge(ACT)}]
        c = _IC(max_tokens=120, **_UNPROMPTED_SAMPLING)
        _arm_self_repeat_ban(c, h)
        got = []
        try:
            out = "".join(agent_chat_stream(h, config=c, mutate_messages=True,
                                            on_tool=lambda n, a, r: got.append(n)))
        except Exception as exc:
            print("      trial %d FAILED: %s" % (t + 1, exc))
            continue
        hit = any("run_python" in str(g) for g in got)
        called_any += 1 if got else 0
        ok += 1 if hit else 0
        print("      trial %d: tools=%-22s %s" % (t + 1, ",".join(got) or "(none)",
                                                  (out or "").strip()[:56].replace("\n", " ")),
              flush=True)
    return {"arm": arm, "label": label, "msgs": len(hist), "chars": chars,
            "run_python": ok, "any_tool": called_any, "trials": TRIALS}


if __name__ == "__main__":
    pairs = int(os.environ.get("PAIRS", "30"))       # 30 pairs ~= 60 messages, the live shape
    print("nudge = solo act %d (the one she was pinned on); %d trials per arm\n" % (ACT, TRIALS))
    res = []
    for arm in ARMS:
        hist, label = build(arm, pairs)
        print("  --- arm %s: %-16s %d msgs, %d chars ---" % (arm, label, len(hist),
              sum(len(m.get("content") or "") for m in hist)), flush=True)
        res.append(run_arm(arm, pairs))
        time.sleep(2)
    print()
    print("%-4s %-18s %7s %9s %14s" % ("arm", "history", "msgs", "chars", "run_python"))
    print("-" * 60)
    for r in res:
        print("%-4s %-18s %7d %9d   %d/%d" % (r["arm"], r["label"], r["msgs"], r["chars"],
                                              r["run_python"], r["trials"]))
    b = next((r for r in res if r["arm"] == "B"), None)
    c = next((r for r in res if r["arm"] == "C"), None)
    if b and c:
        print()
        print("B vs C is the experiment: same length, different content.")
        if b["run_python"] < c["run_python"]:
            print("  -> CONTENT. Her own tool-less prose suppresses it; neutral text of the "
                  "same size does not.")
        elif b["run_python"] == c["run_python"]:
            print("  -> NOT content. Both arms behave the same, so the history's SUBJECT is "
                  "not what decides it.")
        else:
            print("  -> the opposite of the hypothesis: neutral filler suppressed it MORE.")
