"""G-MOE-SEAM — the routed FFN has ONE implementation and ONE forward at a time. OFFLINE.

TWO CLAIMS ABOUT THE ENGINE, both of which were false on 2026-08-22 and cost a month.

  1. ONE FFN. ADR-013 collapsed five copies of the gemma-4 FFN block onto `g4_ffn_apply`
     and got two of them. `gemma4_decode_cuda` kept three, and rather than let them do
     what the prefill copy once did — quietly compute a dense-only FFN and return
     plausible, wrong numbers — it REFUSED a MoE model. /v1/capture reaches that function,
     so episode capture was dead on the daily driver: 253 of 253 rows with npos=0, no
     ep.l5 in three weeks, and 93% of the semantic index left on bag-of-words hashing.

  2. ONE FORWARD. The MoE branch works out of PROCESS GLOBALS (g_moe_*) that
     moe_scratch_ensure frees and reallocates when n_tok grows. Nothing owned them. While
     one route ran forwards that was survivable; the moment `gemma4_decode_cuda` joined,
     concurrent forwards began resizing each other's working memory — measured 1 in 8
     captures, a different layer each time, and the fault variant poisons the CUDA context.

WHY THIS GATE IS STRUCTURAL, and what that costs. The behaviour needs a GPU, a 9 GB model
and two concurrent forwards; it cannot run offline. So this holds the SHAPE, the way
G-THINK-BUDGET holds the sampler's — and it is written as a CLOSURE rather than a grep,
which is the difference between a gate and a decoration: it computes which functions can
reach `g4_ffn_apply` and demands the lock of every externally-reachable one. Add a new
forward entry point without the lock and this goes red by name; that is the failure it
exists to catch, and a grep for one string could not.

The live half is the 12-capture concurrency run recorded in the commit
(before 1 ok / 11 fail, after 12 ok / 0 fail) — a receipt, not an assertion.

    python harness_tests/g_moe_seam.py
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, utf8_stdout  # noqa: E402

utf8_stdout()

CU = os.path.join(ROOT, "engine", "src", "backends", "cuda", "cuda_forward.cu")
RS = os.path.join(ROOT, "engine", "tools", "sp_daemon", "src", "routes.rs")
# NO ENGINE, NO VERDICT (2026-08-25). This gate reads the CUDA source, and the Kairos
# export ships no engine at all — so in that tree it did not fail, it CRASHED with a
# traceback, which the sweep reads as red. Found by running the suite inside the export
# for the first time (the runner had never shipped). A gate whose subject is absent is a
# SKIP; `_gate.skip` exits 2 and says so.
if not (os.path.exists(CU) and os.path.exists(RS)):
    from _gate import skip
    skip("no engine/ in this tree — the MoE seam is the daemon's, and there is no daemon "
         "here to hold to it", "G-MOE-SEAM")
cu = open(CU, encoding="utf-8", errors="replace").read()
rs = open(RS, encoding="utf-8", errors="replace").read()

# ── split the .cu into function bodies by brace depth ────────────────────────────
_SIG = re.compile(r"^(?:extern \"C\" )?(?:static )?[A-Za-z_][\w \*]*?\b(\w+)\s*\([^;]*?\)\s*\{",
                  re.M)


def functions(src: str) -> dict:
    """{name: body} for every top-level function. Brace-counted, not regexed —
    a regex that tries to match a body stops at the first `}` in a string."""
    out = {}
    for m in _SIG.finditer(src):
        name, i, depth = m.group(1), m.end() - 1, 0
        while i < len(src):
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out[name] = src[m.end():i]
    return out


FN = functions(cu)
check("the .cu parsed into real functions", len(FN) > 80, len(FN))
check("...including the seam itself", "g4_ffn_apply" in FN)

print("\n1. ONE FFN — the copies are gone and the refusal with them")
dec = FN.get("gemma4_decode_cuda", "")
check("gemma4_decode_cuda exists and was read", len(dec) > 2000, len(dec))
check("it no longer REFUSES a MoE model outright",
      "not supported on this path" not in dec,
      "the ADR-013 refusal is still there")
check("...it calls the ONE seam instead", dec.count("g4_ffn_apply(") >= 3,
      dec.count("g4_ffn_apply("))
# The copies were: rmsnorm(ffn_norm) -> Wgate -> Wup -> gelu_mul -> Wdown. The marker
# is the COMPUTATION, not the symbol: `g_w.Wgate[L].out` is a width lookup and stays
# (the FF scratch is sized from it). `MMD(&g_w.Wgate` and `k_gelu_mul` are the block.
for w in ("MMD(&g_w.Wgate", "MMD(&g_w.Wup", "MMD(&g_w.Wdown", "k_gelu_mul"):
    check("...and no open-coded FFN remains (%s)" % w, w not in dec,
          "a copy of the FFN block is back in gemma4_decode_cuda")
check("...while the WIDTH lookup is still allowed (it sizes the scratch, it is not an FFN)",
      "g_w.Wgate[L].out" in dec)
check("the guard that EARNS its place survives: MoE with no experts staged still refuses",
      "no expert weights staged" in dec)
check("...and moe_on is announced unconditionally on a MoE arch",
      "decode_cuda moe_on=%d" in dec,
      "silence must not be ambiguous between 'ran clean' and 'never ran'")
check("the graph path excludes MoE (its router syncs per layer; a sync is not capturable)",
      re.search(r"use_graph\s*=.*!moe_on", dec) is not None)

print("\n2. THE SCRATCH IS OWNED, SO THE FORWARD PATH TAKES NO LOCK")
# WHAT THIS SECTION USED TO ASSERT, and why it inverted the same day (2026-08-23).
# It demanded that EVERY external forward entry take a process-wide recursive mutex,
# because the MoE branch worked out of process globals that a concurrent forward could
# free and resize. True, and a hammer: MEASURED, a /v1/oneshot issued during a 91-second
# prefill waited the full 91 seconds. The scratch is per-caller now (g4_moe_scratch,
# owned by the session or by the one-shot frame), so the demand INVERTS — the forward
# path must take NO lock, and only the genuinely shared state takes a narrow one.
#
# Same closure, opposite verdict, which is exactly why it is computed and not listed.
# The measurement that replaced the old assertion: oneshot-during-prefill 92.82s -> 8.20s,
# and 8 concurrent forwards (4 oneshots + 4 captures) all correct with zero CUDA faults.
SEAM = "g4_ffn_apply"
reach = {SEAM}
for _ in range(8):
    grew = False
    for name, body in FN.items():
        if name in reach:
            continue
        if any(re.search(r"\b%s\s*\(" % re.escape(t), body) for t in reach):
            reach.add(name)
            grew = True
    if not grew:
        break
check("the call graph closes on more than the seam itself", len(reach) > 3, sorted(reach))
ext = set(re.findall(r'^extern "C" \w[\w \*]*?\b(\w+)\s*\(', cu, re.M))
entries = sorted(reach & ext)
check("there are external entry points into the seam", len(entries) >= 4, entries)
still = [e for e in entries if "G4_FWD_LOCK()" in FN.get(e, "")]
check("NO forward entry point holds a process-wide lock any more", not still,
      "still locked: %s — the whole point was to stop a oneshot waiting out a prefill"
      % still)
check("...and the old macro is gone entirely, not merely unused",
      "G4_FWD_LOCK" not in cu, "a dead lock macro invites its own re-use")

# The scratch must be a MEMBER of something a caller owns, never a file-scope bank again.
check("the scratch is a type, not a bank of globals",
      "typedef struct g4_moe_scratch_s {" in cu)
check("...the session owns one", re.search(r"g4_moe_scratch\s+moe;", cu) is not None)
check("...and each one-shot entry owns its own",
      cu.count("g4_moe_scratch g4_ms = {0};") == 2,
      cu.count("g4_moe_scratch g4_ms = {0};"))
check("...freed on every exit path, or a one-shot leaks device memory per call",
      cu.count("moe_scratch_free(&g4_ms)") == 2, cu.count("moe_scratch_free(&g4_ms)"))
for nm in ("gemma4_cuda_probe", "gemma4_decode_cuda"):
    b = FN.get(nm, "")
    i_drain, i_free = b.find("cudaStreamSynchronize"), b.find("moe_scratch_free")
    check("%s drains BEFORE it frees its scratch" % nm, 0 <= i_drain < i_free,
          "freeing device memory that queued kernels still read is the fault that lands "
          "on the NEXT caller — this file paid for that once already")
for g in ("g_moe_rin", "g_moe_acc", "g_moe_bkt", "g_moe_capT"):
    check("no file-scope `%s` survives" % g,
          re.search(r"^static [\w \*]*\b%s\b" % g, cu, re.M) is None)

print("\n2b. WHAT STAYS SHARED KEEPS A NARROW LOCK")
# The expert CACHE is a cache of the model's weights: per-session copies would multiply
# GB of VRAM to solve a problem they do not have. It is mutated on every miss (the LRU
# rewrites the map), so it needs a lock — the point is that it is held for a lookup
# rather than for a prefill.
check("there is exactly one shared-state mutex, declared once",
      cu.count("std::mutex g_moe_shared_mtx") == 1
      and cu.count("#define G4_MOE_SHARED_LOCK()") == 1)
check("...and moe_resident takes it (the LRU map and the staging slots)",
      "G4_MOE_SHARED_LOCK();" in FN.get("moe_resident", ""))
check("...as does the one-time arena registration, double-checked",
      FN.get("moe_arena_pin_try", "").count("G4_MOE_SHARED_LOCK()") == 1
      and FN.get("moe_arena_pin_try", "").count("g_moe_arena_pinned >= 0") == 2,
      "a once-per-process init raced by two forwards can flip its own answer")
check("the staging ring is reachable only under that lock",
      all("moe_stage(" not in b for n, b in FN.items()
          if n not in ("moe_resident", "moe_stage")),
      "moe_stage writes the shared slot; a caller outside the lock would race it")
print("\n3. THE ROUTES HOLD THE LOCK THEY SAY THEY HOLD")
# RETARGETED 2026-08-30. This section asserted the 08-23 fix — the SESSION lock held
# at statement level through the forward — and the 08-29 engine session PROVED that
# invariant was the wrong one: the streaming chat worker serializes on the DEVICE
# lock (`cuda_kvdecode_handle`) and never touches `app.session` mid-forward, so a
# session-held capture ran CONCURRENTLY with a live turn, the shared MoE scratch was
# freed under running kernels, and the context wedged for 25 minutes (the routes.rs
# preamble carries the full incident). The invariant NOW: borrow `qm` under a brief
# session lock that is DROPPED (borrow_qm), then hold the device lock for the whole
# forward (device_guard) — never the session lock into the device lock (AB-BA with
# the chat worker's device→session order). This gate went red the night the better
# invariant landed, which is the correct behaviour of a gate over a superseded rule;
# it holds the new one now.
block_scoped = re.findall(r"let qm = \{\s*\n\s*let mut sguard[^}]*?\n\s*\};", rs)
check("no route re-acquires-and-drops the session lock just to borrow qm",
      not block_scoped, "%d route(s) still scope the guard to the borrow" % len(block_scoped))
for route in ("v1_capture", "v1_recall_rank", "v1_embed"):
    i = rs.find("pub async fn %s(" % route)
    check("%s exists" % route, i > 0)
    body = rs[i:i + 9000]
    check("...%s borrows qm briefly and then holds the DEVICE lock" % route,
          "borrow_qm(&app)?" in body
          and re.search(r'device_guard\(&app, "', body) is not None,
          "the forward must run under the device lock, not the session lock")
    check("...%s never holds the session lock through its forward" % route,
          re.search(r"\n        let mut sguard = app\.session", body) is None,
          "a session-held forward races the chat worker on the MoE scratch (the wedge)")
check("the lock-order invariant is written where the next reader will be",
      "LOCK-ORDER INVARIANT" in rs and "ONE FORWARD AT A TIME ON THIS DEVICE" in rs)
check("...and the fallback path is a lock too, never a no-op",
      "DEVICE_FALLBACK_LOCK" in rs and "no kvdecode handle" in rs,
      "Option::map's 'no handle, no lock' is the F-3 silent no-op")

print("\n4. THE PROBE THAT FOUND IT IS OFF, AND REACHABLE")
check("SP_G4_NAN_PROBE is mapped in serve.py (a knob not mapped there does not exist)",
      'SP_G4_NAN_PROBE' in open(os.path.join(ROOT, "serve.py"),
                                encoding="utf-8", errors="replace").read())
prof = open(os.path.join(ROOT, "profiles", "companion.toml"),
            encoding="utf-8", errors="replace").read()
check("...and the live profile ships it OFF (a D2H+sync per layer when armed)",
      re.search(r"^nan_probe\s*=\s*false", prof, re.M) is not None,
      "nan_probe is ARMED in the profile — that is a per-layer sync on her turns")
check("the probe reports the FIRST bad layer and stage, not just 'something is NaN'",
      "FIRST non-finite residual at L=%d stage='%s'" in cu)

print("\n5. DRAIN BEFORE YOU FREE")
check("the one-shot decode drains the stream before its teardown frees the working set",
      "drain before teardown" in dec or "DRAIN BEFORE YOU FREE" in dec,
      "freeing dx/dnx/dg/dup/ddn while kernels still read them faults the NEXT caller")

finish("G-MOE-SEAM")
