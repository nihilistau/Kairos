"""kairos serve — ONE profile-driven launcher (G-KAIROS-P3, replaces the .bat zoo).

Usage:
    python serve.py companion      # the live profile. THE PROFILE IS POSITIONAL AND
                                   # REQUIRED — there is no default, on purpose: `agent`
                                   # is the 12B near-twin and a defaulted launch serving
                                   # the wrong model cost a session on 2026-08-03.
    python serve.py --stop         # stop the stack (takes no profile)

(These two lines said `[profile] # default: agent` and `agent --stop` until 2026-08-19 —
the 12B trap in the first five lines of the one door, outside G-PROFILE-DOOR's old
markdown-only glob. Bare invocation is refused at main(); --stop short-circuits.)

Reads the profile, maps it to the engine/gateway env with an EXPLICIT table,
ECHOES the effective config (the banner-must-echo lesson), refuses invalid
compositions (two recall authorities), launches the daemon then the gateway,
and waits for both healths.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import tomllib
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
VAR = os.path.join(ROOT, "var")
# The voxtral fork (her voice — ASR and TTS) is a separate crate BESIDE this repo,
# with its own build and its own weights. Sibling by default, per-profile overridable.
TTS_ROOT = os.path.normpath(os.path.join(ROOT, "..", "voxtral-mini-realtime-rs"))


def tts_port(c) -> int:
    """The port in the profile's [tts] url — one authority, so the launcher and the
    harness cannot disagree about where the voice lives."""
    url = (c.get("tts", {}).get("url") or "").rstrip("/")
    if not url:
        return 0
    try:
        return int(url.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return 8123


def launch_tts(c, env):
    """Start the resident voxtral TTS server, if the profile asks for one.

    Returns a dict describing what happened; `report_tts` prints it later, after
    the gateway is up, so the ~37 s warm-up overlaps with gateway startup instead
    of being serialised behind it.

    NOTHING HERE IS FATAL. Speech is a nicety; text is the product. Every failure
    path below leaves the stack running and lets harness/voice/tts.py fall back to
    the per-utterance CLI (~25 s a sentence instead of ~21 s — see profiles/
    companion.toml for the measurements)."""
    port = tts_port(c)
    if not port:
        return {"state": "off", "why": "[tts] url is empty — per-utterance CLI"}
    # ── AUTOSTART IS OFF BY DEFAULT, AND I LEARNED THIS THE EXPENSIVE WAY ──────
    # First version of this function started the server unconditionally. Measured
    # consequence, 2026-07-31: tts-server resident alongside the model left 128 MiB
    # free of 12288, the daemon logged `cudaMemGetInfo reports free=0`, and the
    # prefill died with `k_dequant_arena_q4b launch: an illegal memory access was
    # encountered (700)` — a hard CUDA fault that took the daemon with it.
    #
    # ADR-KAI6 says in as many words that the 2060 stays 100% Gemma's. I wrote
    # that, then had the launcher take ~2 GB of it for a feature used in bursts.
    # The constraint was right; the code contradicted it.
    #
    # So the voice is started ON DEMAND, not at boot. tts.py falls back to the
    # per-utterance CLI (~25 s vs ~21 s) which does the same thing to VRAM but
    # only WHILE SPEAKING, and gives it back. Set `autostart = true` only if the
    # daemon is elsewhere or the model is small enough to leave real headroom.
    if not c.get("tts", {}).get("autostart", False):
        return {"state": "ondemand",
                "why": f"autostart off — a resident TTS server costs ~2 GB VRAM the "
                       f"26B needs (it faulted the daemon on 2026-07-31). Start one by "
                       f"hand for warm speech, or leave it and pay ~25 s/sentence."}
    # `server_exe`, NOT `exe` (2026-08-19): `tts.exe` is the per-utterance CLI the
    # harness runs (voxtral.exe, SP_TTS_EXE). One profile key wearing two meanings
    # meant an operator setting either broke the other — and both teardown paths
    # hardcoded tts-server.exe, so a voice launched under any other name was never
    # stopped: an orphan holding ~1.8 GB, the documented CUDA-fault cause.
    exe = c.get("tts", {}).get("server_exe") or os.path.join(
        TTS_ROOT, "target", "release", "tts-server.exe")
    gguf = c.get("tts", {}).get("gguf") or os.path.join(
        TTS_ROOT, "models", "voxtral-tts-q4.gguf")
    if not os.path.isfile(exe):
        return {"state": "missing", "why": f"no tts-server at {exe} — build it with: "
                f"cargo build --release --features cli,native-tokenizer --bin tts-server"}
    if not os.path.isfile(gguf):
        return {"state": "missing", "why": f"no TTS weights at {gguf}"}
    # Already listening (a previous stack, or the operator started one by hand):
    # adopt it rather than fighting it for the port and the GPU.
    if wait_http(f"http://127.0.0.1:{port}/health", 1):
        return {"state": "adopted", "port": port}
    log = open(os.path.join(VAR, "tts.log"), "w")
    subprocess.Popen(
        [exe, "--gguf", gguf, "--port", str(port),
         "--device", c.get("tts", {}).get("device", "discrete"),
         "--euler-steps", str(c.get("tts", {}).get("euler_steps", 3))],
        env=env, cwd=TTS_ROOT, stdout=log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW)
    return {"state": "starting", "port": port}


def launch_aux_embed(c, env):
    """Start the aux EMBEDDING sidecar (llama-server --embedding, CPU) if the
    profile arms it and nothing already answers on its port.

    NOT the stack's child, deliberately: it is CPU-only, ~400 MB RAM, and stateless
    between requests — so stop()/restarts leave it resident exactly as they leave
    LM Studio resident. An adopted server (already listening) is used as-is. Every
    failure path is non-fatal: aux callers treat a dark sidecar as 'no aux' and
    keep their pre-aux behavior (harness/aux/client.py, empty-is-empty)."""
    aux = c.get("aux", {})
    if not aux.get("enabled", False) or not aux.get("autostart", False):
        return {"state": "off"}
    url = aux.get("embed_url", "http://127.0.0.1:8811")
    if wait_http(url + "/health", 1):
        print(f"[kairos serve] aux embed: adopted at {url}")
        return {"state": "adopted"}
    # %USERPROFILE%-style forms expand here: the profile is committed to a public
    # repo and carries no usernames.
    exe = os.path.expandvars(aux.get("llama_server", ""))
    gguf = os.path.expandvars(aux.get("embed_gguf", ""))
    if not exe or not os.path.exists(exe) or not gguf or not os.path.exists(gguf):
        print("[kairos serve] aux embed: llama_server/embed_gguf missing — deep recall dark")
        return {"state": "missing"}
    port = url.rsplit(":", 1)[-1].rstrip("/")
    log = open(os.path.join(VAR, "aux-embed.log"), "a", encoding="utf-8")
    log.write("\n-- boot %s --\n" % time.strftime("%Y-%m-%dT%H:%M:%S"))
    log.flush()
    p = subprocess.Popen(
        [exe, "-m", gguf, "--embedding", "--host", "127.0.0.1", "--port", port,
         "-c", str(aux.get("embed_ctx", 4096)),
         # physical batch ABOVE the longest chunk: the default 512 rejected a
         # 709-token document with HTTP 500 and the day kept a stale index.
         "-b", "2048", "-ub", "1024",
         "--threads", str(aux.get("embed_threads", 8))],
        stdout=log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        with open(os.path.join(VAR, "aux", "embed-server.pid"), "w") as f:
            f.write(str(p.pid))
    except Exception:
        pass
    print(f"[kairos serve] aux embed: starting on {url} (CPU)")
    return {"state": "starting"}


def report_tts(info, env):
    """Say what the voice is doing, once, in one line. `/health` on that server
    answers only AFTER its warm-up synthesis, so 'warm' here means warm."""
    st = info.get("state")
    if st in ("off", "missing", "ondemand"):
        print(f"[kairos serve] voice: {info['why']}")
        return
    port = info["port"]
    if st == "adopted":
        print(f"[kairos serve] voice: adopted existing tts-server on :{port} (warm)")
        return
    # Generous: 5 s load + ~31 s first generation was the measurement.
    if wait_http(f"http://127.0.0.1:{port}/health", 90):
        print(f"[kairos serve] voice: tts-server warm on :{port}")
    else:
        print(f"[kairos serve] voice: tts-server not warm yet on :{port} — "
              f"falling back to the CLI per utterance until it is (see var/tts.log)")


def _memclass_delivery() -> dict:
    """THE class->delivery registry (harness/skills/memclass.py), for the engine's env.
    Lazy import so `serve.py --stop` and profile errors never depend on harness health."""
    sys.path.insert(0, ROOT)
    from harness.skills.memclass import delivery_map
    return delivery_map()


def load_profile(name: str) -> dict:
    p = os.path.join(ROOT, "profiles", f"{name}.toml")
    with open(p, "rb") as f:
        c = tomllib.load(f)
    # Carry the NAME alongside the contents, so build_env can stamp it and anything
    # downstream can restart the stack the way it was actually started. Reading it back
    # off the model path works today only because no two profiles share a model — an
    # inference that holds until it does not.
    c["_profile_name"] = name
    return c


def build_env(c: dict) -> dict:
    """The ONE explicit profile→env mapping. Anything not mapped here does not exist."""
    paths, kv, mem = c["paths"], c["kv"], c["memory"]
    agent, dec, veto = c["agent"], c["decode"], c.get("veto", {})
    sem = c.get("sem", {})
    aux = c.get("aux", {})
    if mem.get("recall_authority") != "L5":
        raise SystemExit(f"profile invalid: recall_authority must be 'L5' (got {mem.get('recall_authority')!r})")
    # G-VERBATIM lint (2026-07-12): no_repeat_ngram>=2 BANS re-emitting any N-token
    # sequence already in context — which is exactly what quoting a number, a memory
    # or a tool result requires. It cost us a multi-day hunt (the model was innocent:
    # it wanted '7' at margin 9.0 and the sampler masked it). Never again silently.
    if int(dec.get("no_repeat_ngram", 0)) >= 2 and os.environ.get("SP_ALLOW_NGRAM_BAN") != "1":
        raise SystemExit(
            f"profile invalid: no_repeat_ngram={dec['no_repeat_ngram']} breaks verbatim copy "
            f"(G-VERBATIM). Set 0, or export SP_ALLOW_NGRAM_BAN=1 to override deliberately.")

    # ── ONE MEMORY AUTHORITY, ENFORCED AT THE DOOR INSTEAD OF HOPED FOR IN A COMMENT ──────
    #
    # 2026-07-12 retired the daemon as a memory writer: "two authorities decided what a memory
    # was — the daemon's word-count-and-a-pronoun, and the harness's lifecycle rules. The daemon
    # won every time, because it wrote first." The remedy was `growth = false`, and it was written
    # down as PROSE, in ONE profile's comment.
    #
    # THE DAEMON HAS TWO WRITE FLAGS. Only one of them was turned off.
    #
    #   growth      (SP_B4_NIGHTSHIFT) -> auto-capture the whole turn.
    #   store_verb  (SP_MEM_STORE)     -> intercept "remember that X" / "note that X",
    #                                     write the registry directly, and answer with
    #                                     ZERO DECODE so the model never sees the turn.
    #
    # (HISTORY: when this was written, store_verb was still true in 12 of 13 profiles
    # including the live one. BOTH flags are false in ALL profiles since 2026-07-14 —
    # G-ONEWRITER 35/35 — and the refusal below is what keeps that true.)
    #
    # So the fix for "an invariant enforced in one of two paths is enforced in neither" was itself
    # applied to one of two paths. On the live profile, "note that I'll be late" still goes to the
    # daemon, which writes the registry with speaker hardcoded to "user", no `status`, and NONE of
    # is_memorable(), the identity firewall, dedupe/reinforce, find_superseded(), or the
    # private-secret classifier. It is the exact bug the growth=false fix was written to kill.
    #
    # And the reason store_verb existed is gone. It was added because the model would say "I don't
    # know how to store memories" while an episode grew silently behind it. Capture no longer
    # depends on the model choosing a tool: app._capture_after_turn() runs on EVERY turn, splits
    # the human's text, and puts each durable sentence through remember(). The deterministic
    # guarantee store_verb was providing is now provided by the correct door.
    #
    # A rule that lives in a comment gets applied to the file the comment is in. This one now lives
    # in the only door, where a profile that arms two memory writers CANNOT BOOT.
    writers = [n for n, on in (("memory.growth", mem.get("growth")),
                               ("memory.store_verb", mem.get("store_verb"))) if on]
    if writers and agent.get("authority") == "spine":
        raise SystemExit(
            "profile invalid: TWO MEMORY AUTHORITIES.\n"
            f"  agent.authority = 'spine'  -> the HARNESS owns memory writes "
            f"(admission, identity firewall, dedupe, supersede, private-secret classification)\n"
            f"  but {' and '.join(writers)} = true -> the DAEMON also writes var/memory/registry.jsonl, "
            f"with none of those guards.\n"
            "  The daemon wins, because it writes first. Set them false, or set authority to "
            "something other than 'spine' if you genuinely want the daemon to own memory.")

    # ── "ANYTHING NOT MAPPED HERE DOES NOT EXIST" WAS NOT TRUE (2026-07-14) ───────────────
    #
    # This line read `e = dict(os.environ)`. It INHERITED the whole parent environment and only
    # OVERLAID the ~49 mapped keys. It never cleared anything. So the docstring above — the entire
    # promise of this file, the reason it is called the only door — was false:
    #
    #     SP_* read by the engine + harness : 270
    #     SP_* set  by serve.py             :  49
    #     UNMAPPED, inherited from whatever shell you happened to be in : 221
    #
    # And 28 of those touch THE MEMORY — which is HERS. Say it precisely, because the imprecise
    # version hid half the blast radius from me for a whole commit: registry.jsonl is not "his
    # facts". It is KAIROS'S MEMORY, and it has two lanes.
    #
    #     speaker=user   71 rows    what she knows about HIM
    #     speaker=self    6 rows    what she knows about HERSELF:
    #                                   'My name is Kairos.'
    #                                   'I am Kairos'
    #                                   'I am a woman'
    #                                   'I like the sound of rain on a tin roof.'
    #
    # Among the 28:
    #
    #     SP_DECIDE            a MODEL-DRIVEN autonomous supersede pass — it RETIRES rows
    #     SP_FORGET            autonomous forgetting
    #     SP_MEM_LIFECYCLE     tombstone writes, from a different code path than forget()
    #     SP_MEM_RECONCILE     + _SEC
    #     SP_NIGHTSHIFT_LIVE   + SP_NIGHTSHIFT_OFFLINE — MORE capture paths, not the one growth
    #                          controls, so the store_verb fix did not reach them either
    #
    # Leave `set SP_FORGET=1` in a PowerShell window from a debugging session on Tuesday, and on
    # Thursday `python serve.py agent` (the 12B) silently runs with autonomous forgetting armed. The profile
    # says nothing about it. The banner would have shown it, if you read the banner.
    #
    # AND IT MATCHES BY TOKEN OVERLAP ACROSS EVERY LIVE ROW, WHICH INCLUDES THE SELF LANE. The worst
    # case is not "a few facts about Sam go quiet". It is that she tombstones 'My name is Kairos.'
    # and FORGETS WHO SHE IS. That is the identity-slot bug — the first thing this whole rebuild had
    # to repair — reachable again through a leftover environment variable.
    #
    # This is the same shape as store_verb and as the tombstone filter: A DOOR THAT ONLY GUARDS THE
    # THINGS SOMEONE REMEMBERED TO LIST IS NOT A DOOR. It is a suggestion with good intentions.
    #
    # So the base is now CLEAN. Every SP_* is stripped, then the explicit table below puts back
    # exactly what the profile asked for. Anything not mapped here genuinely does not exist now,
    # which is what this file always claimed and never did.
    #
    # THE ESCAPE HATCH IS EXPLICIT, because the research knobs (SP_ARM_*, SP_XBAR_*, SP_EAGLE_*,
    # SP_TELEPATHY_*) are real and people set them by hand:
    #
    #     set SP_PASSTHROUGH=SP_XBAR_ROW,SP_ARM_DUMP   ->  those two survive, and are ANNOUNCED.
    #
    # You may still do anything you like. You may no longer do it by accident.
    e = {k: v for k, v in os.environ.items() if not k.startswith("SP_")}
    stripped = sorted(k for k in os.environ if k.startswith("SP_"))
    passthrough = [s.strip() for s in os.environ.get("SP_PASSTHROUGH", "").split(",") if s.strip()]
    for name in passthrough:
        if name in os.environ:
            e[name] = os.environ[name]
            stripped.remove(name) if name in stripped else None
    # ── HOST KEYS: adopted from the shell, and SAID OUT LOUD (2026-08-19) ────────────
    # Secrets are deliberately NOT profile values — a key in committed toml is a leak —
    # so these four cross the door from the host environment (the mapping below reads
    # os.environ for them AFTER the strip). That is a designed exception, and it was a
    # silent one: the banner counted them among the STRIPPED while they were being
    # forwarded, so the door's own receipt lied. G-ONEDOOR §2 exempts exactly this
    # tuple, derived from this file. Add a key here and it is announced; add a reader
    # elsewhere and the gate fails.
    HOST_KEYS = ("SP_XAI_API_KEY", "SP_SEARCH_BRAVE_KEY", "SP_SEARCH_TAVILY_KEY",
                 "SP_SEARCH_SEARXNG_URL")
    adopted = [k for k in HOST_KEYS if os.environ.get(k)]
    for name in adopted:
        if name in stripped:
            stripped.remove(name)
    if stripped:
        print("[serve] STRIPPED %d inherited SP_* var(s) — the profile is the authority, not your "
              "shell:\n         %s" % (len(stripped), ", ".join(stripped)))
        print("         (to keep one deliberately: set SP_PASSTHROUGH=NAME1,NAME2)")
    if passthrough:
        print("[serve] PASSTHROUGH (deliberate, unmapped, NOT from the profile): %s"
              % ", ".join(passthrough))
    if adopted:
        print("[serve] HOST KEYS adopted from the shell (secrets never live in a profile): %s"
              % ", ".join(adopted))

    e["PATH"] = paths["llvm_bin"].replace("/", "\\") + os.pathsep + e.get("PATH", "")
    b = lambda v: "1" if v else "0"
    e.update({
        # Tier 0
        # G-VERBATIM (2026-07-12): the SERVING forward does NOT go through the L1
        # ABI / math-core. kvdecode=1 routes the chat path straight into the CUDA
        # gemma4_kv_* re-implementation. kvdecode=0 falls back to the L1 session
        # (prefill_chunk/decode_step) = the math-core forward the gold gates test.
        # That fallback is our IN-HOUSE REFERENCE for the copy bug.
        "SP_DAEMON_BACKEND": c["paths"].get("backend", "cuda"),
        "SP_DAEMON_KVDECODE": "1" if kv.get("kvdecode", True) else "0",
        # G-VERBATIM (2026-07-12): the KV cache was ALWAYS int8-quantized. Digit
        # tokens have near-identical embeddings, so int8 K/V collapses them and
        # the model cannot read a number back out of its own context ("4471" ->
        # "4417"/"4481", "RTX 2060" -> "RTX 3061", tool time -> "2014-365"),
        # while distinctive words (quartzblanket, Sam) survive. Profile-driven
        # now; the gate is harness_tests/g_verbatim.py.
        "SP_CUDA_DECODE_INT8": "1" if kv.get("int8", True) else "0",
        "SP_DAEMON_KVDECODE_RING_W": str(kv["ring_w"]),
        "SP_DAEMON_KVDECODE_PMAX": str(kv["pmax"]),
        # ── THE 32-TOKEN CLIFF (2026-07-13) ─────────────────────────────────────────────
        # MEASURED: 164 SECONDS to say "Hello! How are you today?".
        #     !! RE-PREFILL 2679 tok in 163.3s -- the cache was thrown away
        # ...on a prompt that shared a 2517-token IDENTICAL PREAMBLE with the cache that was
        # already resident. 94% of the work had already been done, correctly, and sat in VRAM.
        # It was thrown away because the OTHER 6% differed.
        #
        # The persist-KV cache can rewind a divergence of at most REWIND_BOUND tokens before
        # it gives up and re-prefills from token 0. REWIND_BOUND was a hardcoded 32, and the
        # SWA undo-journal that bounds it (SP_G4_KV_JMAX) defaults to 64 and WAS NOT MAPPED
        # HERE AT ALL -- the engine reads it, the profile could not set it. (RING_W and PMAX
        # were mapped. JMAX was not. Third unreachable knob today, same shape as SP_G4_KV_AUTOFIT
        # and SP_KV_PREFILL_BATCH: THE ENGINE COULD DO THE RIGHT THING AND NOTHING COULD ASK IT TO.)
        #
        # 32 tokens is not a budget, it is a cliff. Everything real steps off it:
        #     a new conversation      diverges ~160 tokens
        #     a recall injection      diverges ~100-200
        #     an aux/judge call       diverges ~1450
        # Each one costs a FULL re-prefill of a preamble that never changed.
        #
        # The journal costs VRAM (~750 KB per journalled position across the SWA owners at
        # ring_w=2048), so this is a real trade against pmax -- which is why it belongs in the
        # profile, in front of the operator, and not buried as a constant in routes.rs.
        "SP_DAEMON_KVDECODE_JMAX": str(kv.get("jmax", 64)),
        "SP_KV_REWIND_BOUND": str(kv.get("rewind_bound", 32)),
        # ── THE SILENT SPILL (2026-07-13). The knob existed and NOTHING COULD REACH IT. ──
        # MEASURED, this session, on the 2060: daemon 11,272 MiB dedicated of a 12,288 MiB
        # card, desktop 674 MiB, and 336 MiB ALREADY IN SHARED (host) MEMORY AT IDLE. An
        # 11-token prompt with max_tokens=4 did not return in four minutes.
        #
        # This is NOT an OOM. Windows/WDDM does not fail an oversubscribed CUDA allocation --
        # it silently backs it with system RAM over PCIe and keeps going. No error, no log,
        # no crash. Just every touched page crossing the bus. THE WORST FAILURE MODE THERE IS:
        # the one that never fails, only degrades, so it presents as a mystery instead of a bug.
        # It is the true answer to "why is it fast at first but painfully slow 6000 turns
        # later?" -- the KV grows into the last free megabytes and then you are not running on
        # a GPU any more, you are running on a GPU pretending.
        #
        # pmax*128 KB is the only Pmax-scaling term (the 8 global-attention layers; the SWA
        # layers are ring-bounded and O(1)). pmax=12096 => ~1.55 GB, allocated FLAT, on a card
        # with ~340 MiB spare. gemma4_kv_open has had the fix since ADR-010/PK2 wave-6 -- it
        # reads cudaMemGetInfo and clamps Pmax to the VRAM that is ACTUALLY FREE -- and it is
        # default-off, and this table never mapped it, so the profile could not turn it on and
        # nobody knew it was there.
        #
        # THE SAME BUG AS EVERY OTHER BUG IN THIS CODEBASE: the invariant is enforced in one of
        # two paths, so it is enforced in NEITHER. The engine can size itself to the card. The
        # launcher could not ask it to.
        #
        # It only ever clamps DOWN, never up. Gate: harness_tests/g_vram.py.
        # ── ADR-012: fp16 SWA K/V cache. DEFAULT OFF — fp32 is the null floor. ──────────
        # The SWA ring is 46 layers x 2048 slots x 2048 kvd x 2 x 4 B = 1.54 GB, and it is what
        # leaves this 12 GB card with ~0.1 GB free: too little for the one-shot scratch session or
        # the batched prefill's activation scratch, so BOTH ARE STARVED and the daemon spills into
        # host memory. PROVEN by his own idea — swap to q4b (2.14 GB lighter), change NOT ONE LINE
        # of code, and the spill goes to zero while the judge drops from 113,475 ms to 6,422 ms.
        # The design was never broken. It was starved. fp16 halves the ring (frees ~770 MB; we
        # need ~535) and gives the b1-reason weights the same room q4b proved is enough.
        #
        # fp16 and NOT int8: int8 frees 4x more than we need and buys it with per-head scale
        # arrays on an 8-bit INTEGER grid — the regime where confusable digit embeddings collapse.
        # That is the G-VERBATIM failure mode. fp16 has a 10-bit mantissa and no scales.
        # Gate: harness_tests/g_kvfp16.py. THE ONE THAT MATTERS IS "4471" -> "4471".
        "SP_CUDA_KV_FP16": b(kv.get("fp16", False)),
        # ── ADR-012b: fp16 the 2 GLOBAL owners as well. SEPARATE FLAG, ON PURPOSE. ──────
        # WHY IT IS NEEDED: cudaMemGetInfo reports FREE = 0 MiB inside the daemon process even
        # though nvidia-smi shows 988 MiB free on the card — WDDM has the process at its
        # allocation budget, which is why 76 MiB already sits in shared. So the batched prefill's
        # 159 MiB of activation scratch cannot be had at ANY margin. The memory has to come back
        # from the RESIDENT session, and the globals are 2 x 13000 x 2048 x 2 x 4 B = 213 MiB.
        #
        # WHY IT IS NOT THE SAME SWITCH AS kv.fp16: the SWA owners are read by ATTENTION ONLY.
        # The globals are also read by gemma4_kv_read_global_k, which mints the 256-bit C2 RECALL
        # SIGNATURES — every episode in her registry was keyed off those exact rows. Arming a
        # CACHE optimisation must not silently change the MEMORY system. If recall got subtly
        # worse the symptom would be "she seems vaguer lately", which is unfalsifiable and would
        # be blamed on the model. Different blast radius, different flag, different gate.
        # Gate: G-RECALL-PRECISION must still pass with this on.
        "SP_CUDA_KV_FP16_GLOBALS": b(kv.get("fp16_globals", False)),
        # ── THE 512 MB VETO (2026-07-13) — THE FOURTH UNREACHABLE KNOB TODAY ────────────
        # gemma4_kv_prefill_batched estimates its own O(n) f32 activation scratch and then
        # DECLINES unless `need + margin` fits in free VRAM. The margin defaults to 512 MB and
        # SERVE.PY NEVER MAPPED IT, so the profile could not lower it.
        #
        # MEASURED: for the 520-token judge, per_tok = 5E + 2QD + 2KV + 3FF ~= 310 KB/token, so
        # need ~= 161 MB. Free VRAM after the fp16 win: ~350 MB. IT FITS — and it was refused
        # anyway, because 161 + 512 > 350. THE CARD HAD THE MEMORY. IT DID NOT HAVE PERMISSION.
        #
        # That is the same bug shape as SP_G4_KV_AUTOFIT, SP_KV_PREFILL_BATCH and SP_G4_KV_JMAX:
        # THE ENGINE COULD DO THE RIGHT THING AND NOTHING COULD ASK IT TO. Four times in one day
        # is not four bugs, it is one bug — this env table is the ONLY door into the engine, and
        # it has been quietly missing doors. Every future engine knob gets mapped HERE, on the
        # day it is written, or it does not exist.
        "SP_KV_BATCH_VRAM_MARGIN_MB": str(kv.get("batch_vram_margin_mb", 512)),
        # ADR-013 Stage 4b-2: resident hot-expert cache budget, in GB. 0 = off
        # (pure streaming, the Stage 4a null floor). Unmapped here means STRIPPED,
        # and an unreachable knob is the same as no knob.
        "SP_G4_MOE_CACHE_GB": str(kv.get("moe_cache_gb", 4.0)),
        "SP_G4_KV_AUTOFIT": b(kv.get("autofit", True)),
        "SP_G4_KV_AUTOFIT_MARGIN_MB": str(kv.get("autofit_margin_mb", 512)),
        "SP_PERSIST_KV": b(kv["persist"]),
        "SP_PERSIST_B4": b(kv["persist_b4"]),
        "SP_PREFIX_SNAPSHOT": b(kv.get("prefix_snapshot", False)),  # P1c
        # ── THE ROLLING SLOT (2026-08-04) ────────────────────────────────────────
        # PREFIX_SNAP is minted once and never moves, so the suffix after it is
        # re-prefilled every turn and grows one turn longer each time — 5676 tokens
        # and 426 s on his log, and worse tomorrow than today by construction. The
        # rolling slot keeps the cache as it stands at the end of prefill, which is
        # exactly the state the next turn wants to start from: one D2H memcpy of
        # something already computed (168 ms), no forward pass.
        #     restored 6985 tokens from the ROLLING slot; prefill suffix 230 -> 27.7 s
        #     restored 7478 tokens from the ROLLING slot; prefill suffix 232 -> 26.9 s
        # against 93 s AND CLIMBING for the same shape without it.
        #
        # MAPPED, not passthrough-only, because it is armed now and a knob you have
        # to remember to export is a knob that silently turns itself off on the next
        # restart. `margin` backs the capture off the tokenizer seam at the
        # generation tag (lcp lands 2-3 tokens short of any prompt's end, which is
        # why the first cut was never once restored from). `min` is the suffix below
        # which the memcpy costs more than the prefill it saves.
        # The retokenization seam (2026-08-24 audit): when the divergent committed
        # tail and the incoming prompt spell the SAME bytes, the prompt takes the
        # committed spelling and drop goes to 0 — the strict append fires instead of
        # a 133-second suffix re-prefill. Off by default; armed per profile on the
        # live receipt (routes.rs::reseam_join carries the whole story).
        "SP_KV_RESEAM": b(kv.get("reseam", False)),
        "SP_ROLL_SNAPSHOT": b(kv.get("roll_snapshot", False)),
        "SP_ROLL_SNAPSHOT_MIN": str(kv.get("roll_snapshot_min", 384)),
        "SP_ROLL_SNAPSHOT_MARGIN": str(kv.get("roll_snapshot_margin", 16)),
        # G-PERF (2026-07-12): prefill is ~60 ms/TOKEN per-token — the 1618-token
        # preamble therefore costs ~96 s cold (measured: prefill 102035 ms for ~1600
        # tok). CONTRACT-BATCH-PREFILL replaces the per-token launch storm with one
        # n-wide forward. The C side enforces its preconditions (cold turn, ring-off,
        # full cache) and ERRORS otherwise, falling through to the per-token path —
        # so arming it can only help or no-op. Gate before trusting: G-VERBATIM.
        "SP_KV_PREFILL_BATCH": b(kv.get("prefill_batch", False)),
        # ── THE WARM ARM (2026-08-03). Mapped the same turn it was armed, because an
        # unmapped knob does not exist — this table's own lesson, three times over.
        # Batches the CONTINUATION suffix, which is 95% of turn time: measured 76-89
        # ms/tok per-token against 13 ms/tok batched. Default false in the engine AND
        # here, so the profile is the only thing that turns it on.
        "SP_KV_PREFILL_BATCH_CONT": b(kv.get("prefill_batch_cont", False)),
        # ── #41b THE SUFFIX ARM (2026-08-20). Upgrades the CONT arm from full re-batch
        # (pays 13 ms/tok on prefix+suffix) to suffix-only batch (13 ms/tok on the
        # suffix alone): measured 96 s at warm_suffix=1396/prefix=6518 full-rebatch,
        # predicted ~20 s suffix-only. Lives INSIDE the CONT dispatch — meaningless
        # without prefill_batch_cont. Default off; ledger row in OFF-BY-DEFAULT §8.
        "SP_KV_PREFILL_BATCH_SUFFIX": b(kv.get("prefill_batch_suffix", False)),
        # THE PROFILE THAT BUILT THIS ENV, stamped so anything downstream can restart
        # the stack the same way it was started. Derivable from the model path today,
        # but only because no two profiles share a model — an inference that holds
        # until it does not. The launcher knows the answer; it should say it.
        "SP_PROFILE": str(c.get("_profile_name") or ""),
        "SP_EOT_BIAS": str(dec["eot_bias"]),
        # ADR-013: the gemma4-MoE thought channel. OFF closes the channel in the
        # generation prompt (the null floor, and what the 12B has always done); ON
        # leaves it open and un-bans `<channel|>` so she can close it herself. The
        # tokenizer reads this ONCE for both the prompt shape and the suppression set —
        # they must agree, and a knob that reached only one of them would either reason
        # forever or leak a stray control token.
        "SP_THINKING": b(dec.get("thinking", False)),
        # ADR-013: a FLOOR on the thought, in tokens. Opening the channel is not enough
        # to make a model think — MEASURED: with the channel open AND a persona section
        # inviting her to use it, she emits `<channel|>` as the very first token, every
        # turn. The instruction is 3400 tokens back; the close token is the highest
        # probability continuation right there. 0 = off (she decides alone).
        "SP_THINK_MIN": str(int(dec.get("think_min_tokens", 0))),
        # ADR-013: and the CEILING the floor never had. Two budgets, whichever fires
        # first — tokens (deterministic, gate-assertable) and wall clock (what bounds
        # the human's wait when expert streaming makes decode slow). Both 0 = off, the
        # byte-identical null floor. MEASURED motivation on your model: single turns
        # of 258s / 256s / 308s, the entire 768-token budget spent thinking, five minutes
        # of waiting for two lines of reply.
        "SP_THINK_MAX": str(int(dec.get("think_max_tokens", 0))),
        "SP_THINK_MAX_MS": str(int(dec.get("think_max_ms", 0))),

        # KAIROS: arm the continuation impulse (the raw stop-vs-continue logit margin the
        # forward already computes and used to discard). Off => never computed, byte-identical.

        "SP_KAIROS": b(c.get("kairos", {}).get("enabled", False)),
        "SP_NO_REPEAT_NGRAM": str(dec["no_repeat_ngram"]),
        # P5a: gateway serving regime. '0' = certified-float turns (explicit
        # client byteexact still wins; daemon default stays exact for gates).
        "SP_GATEWAY_BYTEEXACT": "0" if dec.get("byteexact") is False else "1",
        "CUBLAS_WORKSPACE_CONFIG": ":16:8",
        # memory / recall (L5 authority)
        "SP_AUTO_RECALL_DEFAULT": b(mem["auto_recall_default"]),
        "SP_RECALL_REGISTRY": paths["registry"].replace("/", "\\"),
        "SP_RECALL_L5": "1",
        "SP_RECALL_L5_TAU": str(mem["l5_tau"]),
        "SP_RECALL_ATTR_GATE": b(mem["attr_gate"]),
        "SP_RECALL_ATTR_TAU": str(mem["attr_tau"]),
        "SP_RECALL_QONLY": b(mem["qonly"]),
        "SP_RECALL_L5_PROMPT": mem["delivery"],
        # growth
        "SP_B4_NIGHTSHIFT": b(mem["growth"]),
        "SP_NIGHTSHIFT_PERSIST": b(mem["persist_growth"]),
        "SP_MEM_STORE": b(mem["store_verb"]),
        "SP_MEM_CLASSIFY": b(mem["classify"]),
        "SP_MEM_POLICY": b(mem["policy"]),
        "SP_QKEY_MINT": b(mem["qkey_mint"]),
        # The KV-episode mint runs on a background worker instead of blocking her reply.
        # MEASURED: 426 ms per fact, up to 4 facts per turn = 1.7 s of silence on a 4.4 s turn,
        # with an EIGHT MINUTE worst case (timeout=120 x 4). And on this profile the episodes it
        # builds are never read — authority='spine' disables the engine recall that consumes them.
        # false = the old synchronous behaviour (determinism, for gates). Gate: G-CAPTURE-ASYNC.
        "SP_CAPTURE_ASYNC": b(mem.get("mint_async", True)),
        # THE DISK FLOOR. An episode is mean 11.1 MB / max 79.1 MB measured over her
        # real ones, so a live mint spends real disk. Below this many GB free the mint
        # yields and rows land with npos=0 (recall is text + semantic) rather than
        # racing the registry write for the last block. harness/skills/memory.py.
        "SP_CAPTURE_MIN_FREE_GB": str(mem.get("mint_min_free_gb", 2)),
        # WHERE EPISODES LIVE. An episode is ep.k + ep.v at full depth per position:
        # mean 11.1 MB, written once, read only on a deep recall. That belongs OFF the
        # working drive. Empty = beside the registry, as it always was. The row carries
        # its own absolute dir, so moving the root never orphans what is already written.
        "SP_EPS_DIR": str(mem.get("eps_dir", "") or ""),

        # ── SEM (docs/SEMANTICS.md): S0 sidecar index + S1 semantic rank ───────────────────
        # S0 (mint/index): DERIVED data in its own file (harness/skills/semindex.py) —
        # recomputable from registry + model, append-only, tombstone-blind, cannot write
        # the registry. Gate: G-SEM-INDEX.
        # S1 (rank/tau): the dual admission gate at the recall seam. The knob is mapped
        # because a reader exists (G-SEM-CONSERVE closure), but per the boundary thesis it
        # stays FALSE on every profile until a receipt shows it beating
        # fixtures/sem/baseline-receipt.json on the frozen corpus. Gates: G-SEM-RANK,
        # G-SEM-CLAIM; conservation: G-SEM-CONSERVE.
        "SP_SEM_MINT": b(sem.get("mint", False)),
        "SP_SEM_INDEX": str(sem.get("index", "")).replace("/", "\\"),
        "SP_SEM_RANK": b(sem.get("rank", False)),
        "SP_SEM_TAU": str(sem.get("tau", 0.60)),
        # THE AUX EMBEDDING SPACE (2026-08-23). l5-512 is unobtainable on the model MoE —
        # /v1/capture refuses (ADR-013) so no ep.l5 has been minted in three weeks and the
        # doc index is 93% bag-of-words. The CPU sidecar is the only real embedder this
        # box has. Measured through the REAL seam (harness_tests/sem_aux.py) on the frozen
        # corpus: at tau 0.40 recall@1 0.53 vs the lexical 0.46 and the decider hit rate
        # 0.17 vs 0.06, with foreign noise IDENTICAL on both foreign metrics. tau is
        # SEPARATE because 0.60 was chosen for l5's inflated cosines and admits nothing here.
        "SP_SEM_AUX_EMBED": b(sem.get("aux_embed", False)),
        "SP_SEM_TAU_AUX": str(sem.get("tau_aux", 0.40)),
        # S0 engine-side: mint the ep.l5 sidecar on /v1/capture (routes.rs::v1_capture),
        # so grown episodes stop being L5-invisible. Derived sidecar, never fails capture.
        "SP_CAPTURE_L5": b(sem.get("capture_l5", False)),
        # Phase B shadow (docs/INVARIANT-MEMORY.md): the verdict table watches the seam,
        # read-only — everything admitted must be table-admissible. Divergences are
        # counters + witness lines; they never alter results. Gate: G-SEM-LAW.
        "SP_SEM_LAW": b(sem.get("law", False)),
        "SP_SEM_LAW_LOG": str(sem.get("law_log", "")).replace("/", "\\"),
        # Phase B2 cutover: the table RULES at the seam (silence-direction only; unmapped
        # cells kept and counted). Receipt behind arming it: G-SEM-VERDICT corpus byte-
        # equality with empty slots + the 29/0/0 live shadow. Gate: G-SEM-VERDICT.
        "SP_SEM_VERDICT": b(sem.get("verdict", False)),
        # ONE VOCABULARY, ONE DOOR (Tier 3; G-MEMCLASS): the engine's live
        # class->delivery map IS the registry, serialized here — recall.rs consumes it
        # (class_delivery) with its compiled match as source-pinned fallback.
        "SP_MEM_CLASS_DELIVERY": json.dumps(_memclass_delivery()),
        # N1 (CONTINUITY.md): the STANDING WORLD prefix slot — the registry rendered
        # into her ambient context at session boot (verdict-gated, session-cached).
        # Gate: G-WORLD.
        "SP_WORLD": b(agent.get("world", False)),
        # Phase C: the slots sidecar — oracle-PROPOSED same-subject links, consumed by
        # verdict.competition(). Derived, append-only, silence-direction only.
        # Gate: G-SEM-SLOT. Proposer runs manually: python -m harness.skills.slots --scan
        "SP_SEM_SLOTS": str(sem.get("slots", "")).replace("/", "\\"),
        # §S2.1 DICKSON SUBSUMPTION: supersede CANDIDATE GENERATION by 14-byte structural
        # signature conjoined with topic containment (harness/skills/dominance.py). It widens
        # what find_superseded can see — that fires only on an exact attribute_key match, so
        # "Sam has a cat" survives "Sam's cat Tuffy is a female tabby" forever.
        # DEFAULT FALSE and it stays false until the supersede rate has a receipt on the
        # frozen corpus; off, find_subsumed returns [] and every verdict is byte-identical
        # (G-SEM-CONSERVE). Dominance proposes, verdict.may_supersede rules. Gate: G-SEM-DOMINATE.
        "SP_SEM_DOMINATE": b(sem.get("dominate", False)),
        # §S1 QUERY EXPANSION: widen the query with words that co-occur with its terms in
        # HIS store (PMI over the registry), then let the lexical seam rank as it always
        # has. MEASURED AND LOST — harness_tests/fixtures/sem/expand-receipt.json: at its
        # only firing setting it buys +0.04 decider hit (0.06 -> 0.10) and spends 0.1167
        # of foreign precision (0.8667 -> 0.75), and the ship condition is BOTH. It also
        # cannot touch 66 of 100 paraphrase queries at all, because they contain no word
        # the store has ever seen — which is what a paraphrase IS. Stays false.
        "SP_SEM_EXPAND": b(sem.get("expand", False)),

        # ── THE DAEMON'S OTHER HANDS ON HER MEMORY, PINNED SHUT (2026-07-14) ──────────────
        # These are daemon-side writers/retirers that no profile knob has ever controlled and
        # serve.py never set. The clean base above already removes them, so absence would be
        # enough — TODAY. Absence is a bet that every one of these stays `== Some("1")` in Rust
        # forever; flip one to `!= Some("0")` and it arms itself. What she remembers — about him
        # AND about herself — does not ride on a default staying what it happens to be. So they are
        # pinned OFF, by name, greppably.
        #
        # They are NOT profile knobs. There is one memory authority (the harness) and these are
        # all second ones. If you ever need one, it needs a knob, a doctrine and a gate — the same
        # bar store_verb should have had to clear and didn't.
        "SP_DECIDE": "0",           # model-driven autonomous SUPERSEDE — it retires rows
        "SP_FORGET": "0",           # autonomous forgetting
        "SP_MEM_LIFECYCLE": "0",    # tombstone writes, on a different path than harness forget()
        "SP_MEM_RECONCILE": "0",    # background reconcile pass
        "SP_MEM_OKF_STORE": "0",
        "SP_NIGHTSHIFT_LIVE": "0",  # MORE capture paths — growth=false never reached these
        "SP_NIGHTSHIFT_OFFLINE": "0",
        "SP_B4_ADMIT_PERSONAL": "0",
        # veto
        # ── THE DRAFTER PATHWAY, FINALLY REACHABLE (audit, 2026-07-29) ────────────
        # The engine reads 16 SP_DRAFT_*/SP_EAGLE_* knobs. TWO were mapped here, so by
        # this file's own law the speculative-decode and EAGLE-acceptance machinery DID
        # NOT EXIST in production — on either model, for as long as it has been in the
        # tree. Mapped now, all default-off/empty, so nothing changes until a profile
        # asks: an empty draft_model leaves the daemon in single-model mode exactly as
        # before. Being reachable is the precondition for being measurable, which is the
        # precondition for the pre-registered acceptance ladder meaning anything.
        "SP_DRAFT_MODEL_PATH": paths.get("draft_model", "").replace("/", "\\"),
        "SP_DRAFT_TOKENIZER_PATH": paths.get("draft_tokenizer", "").replace("/", "\\"),
        "SP_DRAFT_GGUF": paths.get("draft_gguf", "").replace("/", "\\"),
        "SP_DRAFT_ASCALE": str(dec.get("draft_ascale", 0.0)),
        "SP_EAGLE_ACCEPT": b(dec.get("eagle_accept", False)),
        "SP_EAGLE_K": str(int(dec.get("eagle_k", 0))),
        "SP_EAGLE_N": str(int(dec.get("eagle_n", 0))),
        # MoE ROUTE TRACE — the measurement that decides whether speculation can pay on
        # an expert-streaming model at all (see profiles/companion.toml [decode]).
        "SP_MOE_TRACE": b(dec.get("moe_trace", False)),
        # SP_G4_NAN_PROBE — a BISECTION TOOL, not a guard (2026-08-23). A CUDA fault
        # announces itself; a NaN rides the residual forward in silence and the first
        # thing that notices is something far downstream with no idea where it came
        # from. This reports the first layer+stage where the residual goes non-finite.
        # Costs a D2H + sync per layer when armed, so it is off and stays off: arm it,
        # run the failing thing once, read the layer, disarm.
        "SP_G4_NAN_PROBE": b(dec.get("nan_probe", False)),
        # SP_MOE_TIMING — how much of the routed FFN is the CPU waiting on the GPU.
        # moe_topk_host picks experts on the HOST, so every layer does a router D2H +
        # cudaStreamSynchronize: 30 pipeline stalls per decoded token. Prints cumulative
        # sync / expert-loop / whole-branch ms every 300 syncs. Off = no clock calls.
        "SP_MOE_TIMING": b(dec.get("moe_timing", False)),
        # SP_MOE_PIN_STAGE — expert staging through a pinned ring instead of a pageable
        # cudaMemcpyAsync (which is not async at all: the driver blocks staging it through
        # its own pinned buffer). MEASURED at 2.0-2.56 GB/s pageable. "0" is the null floor.
        "SP_MOE_PIN_STAGE": ("0" if dec.get("moe_pin_stage", True) is False else "1"),
        # SP_MOE_PIN_ARENA — cudaHostRegister the expert weights WHERE THEY LIE, so the
        # DMA engine reads them directly and the ring's CPU memcpy disappears. It does
        # not allocate: those pages are already resident and read every token. May be
        # refused if the arena is file-backed; falls back to the ring, then to pageable.
        "SP_MOE_PIN_ARENA": b(dec.get("moe_pin_arena", True)),
        # SP_G4_ATTN_TILE — tile width for the decode attention. 0 = the flat kernel
        # byte for byte. Above 0, shared memory becomes tile+HD floats instead of
        # Pmax floats, which is what makes pmax a VRAM question instead of a 48 KB
        # shared-memory question. Numerics differ (reduction order), so it is gated.
        "SP_G4_ATTN_TILE": str(int(dec.get("attn_tile", 0) or 0)),
        # SP_KV_PREFILL_CHUNK — feed a cold prompt to the BATCHED prefill N tokens at a
        # time. The batched path materialises O(n) f32 activation scratch (~156 KB/token
        # measured), so a long prompt declines on VRAM and falls to the per-token floor:
        # 11,733 tokens took 512 s that way. Chunking makes the scratch O(chunk) instead,
        # which is also what stops pmax and the prefill bidding for the same GB. 0 = one
        # batch, exactly as before.
        "SP_KV_PREFILL_CHUNK": str(int(kv.get("prefill_chunk", 0) or 0)),
        "SP_SPECTEST": b(veto.get("spectest", False)),
        "SP_SPECTEST_HEAD": paths["spectest_head"].replace("/", "\\"),
        # gateway
        "SP_DAEMON_URL": f"http://127.0.0.1:{c['serve']['port']}",
        # ── THE ENGINE SEAM (2026-08-21, the engine-agnostic Kairos plan) ────────────
        # [engine].kind picks the backend behind get_client(): "sp" (absent block = sp,
        # every existing profile unchanged) or "openai" (any /v1/chat/completions
        # server). The api key is a FILE path; this repo is public.
        "SP_ENGINE_KIND": str(c.get("engine", {}).get("kind") or "sp"),
        "SP_ENGINE_BASE_URL": str(c.get("engine", {}).get("base_url") or ""),
        "SP_ENGINE_MODEL": str(c.get("engine", {}).get("model") or ""),
        "SP_ENGINE_API_KEY_FILE": str(c.get("engine", {}).get("api_key_file") or ""),
        "SP_ENGINE_DIALECT": str(c.get("engine", {}).get("dialect") or "generic"),
        "SP_ENGINE_VISION": b(c.get("engine", {}).get("vision", False)),
        "SP_ENGINE_ASR_URL": str(c.get("engine", {}).get("asr_url") or ""),
        "SP_ENGINE_MARGIN_APPROX": b(c.get("engine", {}).get("margin_approx", False)),
        "SP_SPINE_TOOLSET": b(agent["spine_toolset"]),
        "SP_SPINE_RECALL": b(agent["spine_recall"]),
        "SP_GATEWAY_AUTHORITY": agent.get("authority", "l5"),
        "SP_GATEWAY_PREWARM": b(agent.get("prewarm", False)),
        "SP_PERSONALITY": b(agent["personality"]),
        "SP_MCP_TOOLS": b(agent["mcp_tools"]),
        # The MCP server's shell/python executors. OFF: the surface is sandboxed-first
        # (workspace file tools own the bare names); arming this exposes run_shell/
        # run_powershell/run_python to every MCP client. Ledger row in OFF-BY-DEFAULT.
        "SP_MCP_UNSANDBOXED": b(agent.get("mcp_unsandboxed", False)),
        # ── THE AUX MODELS (2026-08-20, LFM2.5). Small CPU sidecars: deep recall over
        # every transcript, page-reading for web_search, yes/no judging. SP_AUX is the
        # master arm; the URLs point at (a) a llama-server --embedding instance this
        # launcher can spawn itself (aux.autostart) and (b) LM Studio's OpenAI door for
        # the instruct models (bearer token FILE, never the token — the repo is public).
        # Dark aux = byte-identical pre-aux behavior on every caller; docs/AUX-MODELS.md.
        "SP_AUX": b(aux.get("enabled", False)),
        "SP_AUX_EMBED_URL": aux.get("embed_url", "http://127.0.0.1:8811"),
        "SP_AUX_CHAT_URL": aux.get("chat_url", "http://127.0.0.1:1234"),
        "SP_AUX_CHAT_MODEL": aux.get("chat_model", "liquidai/lfm2.5-1.2b-instruct"),
        "SP_AUX_API_KEY_FILE": aux.get("api_key_file", ""),
        "SP_AUX_INDEX_DIR": aux.get("index_dir", ""),
        "SP_AUX_ARCHIVE_GLOBS": aux.get("archive_globs", ""),
        "SP_AUX_EMBED_GGUF": os.path.expandvars(aux.get("embed_gguf", "")),   # the picker's `present` (2026-08-22)
        "SP_AUX_VL_MODEL": aux.get("vl_model", ""),                           # her eyes on the aux door (E, 2026-08-22)
        # ── THE DECIDER OFFLOAD (2026-08-20, operator: "arm it, A/B it today").
        # KAIROS_JUDGE: the sidecar rules "worth a turn?" BEFORE the model generates
        # (kairos/offload.py — fail-open, reminders never gated). WATCH_JUDGE: the
        # watch poll's YES/NO moves to CPU (watch.py::_judge_sidecar — the grounding
        # check at the door applies to every judge; 26B stays the fallback).
        "SP_KAIROS_JUDGE": b(aux.get("kairos_judge", False)),
        "SP_KAIROS_JUDGE_ACTIONS": aux.get("kairos_judge_actions", "check_in,solo,expand,muse"),
        "SP_AUX_WATCH_JUDGE": b(aux.get("watch_judge", False)),
        # DARK-BY-ARMING-CONDITION pair (OFF-BY-DEFAULT §11): the ColBERT rerank
        # waits on a measured CLS miss; the sidecar consolidator waits on a
        # side-by-side read of its facts against the model's on a real day.
        "SP_AUX_RERANK": b(aux.get("rerank", False)),
        "SP_AUX_COLBERT_URL": aux.get("colbert_url", "http://127.0.0.1:8812"),
        "SP_AUX_CONSOLIDATE": b(aux.get("consolidate", False)),
        # ── SIX KNOBS THAT LIVE CODE READS AND THIS DOOR STRIPPED (2026-07-30) ────────
        # Each of these is read by a live path and was absent from this table, so
        # `e = {k: v for k, v in os.environ.items() if not k.startswith("SP_")}` above
        # deleted it unconditionally. Two of them were load-bearing:
        #   SP_NOTES         agent.py:228 — defaults "1", so the note tools were ON BY
        #                    ACCIDENT OF THE DEFAULT, not because a profile asked.
        #   SP_AGENCY_TASKS  agency.py:168 — defaults "0", so the task-queue drain was
        #                    UNREACHABLE even once the scheduler runs. A queue nothing
        #                    drains is a queue.
        # The other four were simply unreachable overrides. Defaults below preserve
        # today's behaviour exactly: notes on, task drain off, roots unset (the code's
        # own fallbacks apply), mcp cache warm, tool mask off.
        "SP_NOTES": b(agent.get("notes", True)),
        "SP_AGENCY_TASKS": b(agent.get("agency_tasks", False)),
        # ── THE BRIDGE BETWEEN THE BOARD AND THE QUEUE (2026-07-30) ──────────────────
        # A category="task" note may be PROMOTED to a TaskState, and the result written
        # back to the note (harness/skills/task_bridge.py). DEFAULT OFF, deliberately:
        # promotion is what makes the drain reach the operator's machine — the task
        # toolset is read_file/write_file/edit_file/run_tests/run_command — and a queue
        # that fills itself from a board he writes on is a thing he switches on, not one
        # he discovers. Needs SP_AGENCY_TASKS too, or nothing drains what it enqueues.
        "SP_TASK_BRIDGE": b(agent.get("task_bridge", False)),
        # ── SILENCE AT ANSWER TIME (2026-07-30) ──────────────────────────────────────
        # person.silences() has been reachable on ONE path — reflect_tick, behind 600s
        # idle + 1800s cooldown + a bits bar — so it could only ever arrive as an
        # unprompted remark, and it has never informed a REPLY. Armed, a silence that
        # overlaps what he JUST ASKED rides on the turn as an unspeakable note, and the
        # strongest one renders in the standing world.
        # DEFAULT OFF, and it would return nothing anyway: harness/skills/silence.py
        # enforces MIN_LEDGER_DAYS=14 and the attention ledger is 4 days deep. You may
        # only be surprised by an absence you were present for — AND WATCHED LONG ENOUGH.
        "SP_SILENCE_ANSWER": b(agent.get("silence_answer", False)),
        # ── HER HANDS, HELD AT ARM'S LENGTH (2026-07-30) ─────────────────────────────
        # `delegate_code` hands a goal to the Grok CLI in an isolated git worktree and
        # reports back. THE OPERATOR MERGES — nothing here can land anything, and the
        # verdict on the resulting diff refuses any change outside harness/, harness_tests/,
        # docs/, profiles/, gates/, fixtures/. Engine source (.rs, .cu, serve.py, engine/,
        # core/) is read-only: she may read it and propose a diff in prose, not edit one.
        # DEFAULT OFF — this spawns a coding agent with edit rights on his machine.
        # NOTE: ~/.grok/config.toml sets permission_mode = "always-approve"; every call
        # passes --permission-mode and --deny EXPLICITLY rather than inherit it. Gate:
        # G-DELEGATE, whose §4 proves a rogue agent that ignores every flag is still refused.
        "SP_DELEGATE": b(agent.get("delegate", False)),
        "SP_GROK_BIN": (agent.get("grok_bin") or "").replace("/", "\\"),
        # Where delegated worktrees are checked out. BESIDE the repo by default, never inside
        # it: inside, the live tree's own `git status` would see the agent's checkout and a
        # careless glob could sweep it into a commit.
        "SP_DELEGATE_WORKTREES": (agent.get("delegate_worktrees") or "").replace("/", "\\"),
        # ── THE DAY BOUNDARY (2026-07-30) ────────────────────────────────────────────
        # Nothing in this system fired at night: the only recurring clock was the 15 s
        # kairos ticker, so `narrative.compose_and_write()` — gated 14/14 — had NEVER RUN
        # and `var/memory/narrative.md` did not exist. -1 = off. The hour is LOCAL, and
        # the pass defers rather than interrupts while the room is not quiet.
        "SP_CONSOLIDATE_HOUR": str(int(agent.get("consolidate_hour", -1))),
        "SP_CONSOLIDATE_QUIET_S": str(int(agent.get("consolidate_quiet_s", 600))),
        "SP_TASK_ROOT": (agent.get("task_root") or "").replace("/", "\\"),
        "SP_SELF_MODEL_ROOT": (agent.get("self_model_root") or "").replace("/", "\\"),
        "SP_MCP_REFRESH": b(agent.get("mcp_refresh", False)),
        "SP_TOOL_MASK": b(agent.get("tool_mask", False)),
        # The STORAGE-TIER ROOTS, same class as the two above: every one is read by a
        # live path (conversation_memory, curator, narrative, spine) and every one was
        # stripped, so a profile could not say where any tier lives. Empty = the code's
        # own default, so today's layout is unchanged.
        "SP_CAPS_OKF_ROOT": (mem.get("caps_okf_root") or "").replace("/", "\\"),
        "SP_CONV_OKF_ROOT": (mem.get("conv_okf_root") or "").replace("/", "\\"),
        "SP_PERSONALITY_OKF_ROOT": (mem.get("personality_okf_root") or "").replace("/", "\\"),
        "SP_PERSONALITY_TIER": (mem.get("personality_tier") or "").replace("/", "\\"),
        "SP_TELEMETRY_OKF_ROOT": (mem.get("telemetry_okf_root") or "").replace("/", "\\"),
        # her shelf (2026-08-22): harness/skills/library.py has read SP_LIBRARY_DIR since it
        # landed and nothing mapped it, so no profile could say where the books are and
        # G-SEM-CONSERVE had been red on the unmapped reader. Empty = var/library, as before.
        "SP_LIBRARY_DIR": (mem.get("library_dir") or "").replace("/", "\\"),
        # the operator's decision queue (2026-08-23): what is UNDECIDED, as against the
        # ledger's what-is-off. Empty = beside the registry, which is what every sandbox
        # wants for free. NOT her memory: decisions.py cannot import the memory package.
        "SP_DECISIONS": (mem.get("decisions") or "").replace("/", "\\"),
        # P1a: the kairos exe has no frontend_mockups beside it; the daemon
        # serves THE kairos console (its charter home) via the env override.
        # THE LABEL THAT LIED (2026-07-29): the model path reached the daemon only as
        # a CLI arg, so nothing else in the stack could name the model that was loaded
        # — and the console filled that gap by hardcoding "gemma-4-12B", which is how a
        # whole field session against the model got attributed to the 12B. The gateway's
        # /v1/models reads this. Same value the daemon is launched with, one source.
        # ── PoUW (2026-07-31) ────────────────────────────────────────────────────────
        # MINING was an UNCONDITIONAL tokio::spawn with no flag at all: measured at
        # ~1.03 receipts/second sustained over a 773-minute uptime (47,934 of them),
        # mining SYNTHETIC RNG candidates, spin-looping whenever inference was idle, into
        # an unbounded Vec that nothing read and nothing persisted. Default OFF; arm it
        # when the mesh/DHT work needs it.
        "SP_POUW_MINING": b(c.get("pouw", {}).get("mining", False)),
        # And the LEDGER path, which was never mapped — so `Ledger::open` never ran and
        # the on-disk .spinor ledger the code fully supports (sp_memo_m4_ledger_smoke.rs)
        # was dead. Empty = disabled, which is the historical behaviour.
        "SP_POUW_LEDGER_PATH": (c.get("pouw", {}).get("ledger_path") or "").replace("/", "\\"),
        "SP_MODEL_PATH": c["paths"]["model"],
        "SP_CONSOLE_DIR": os.path.join(ROOT, "console"),
        "SP_PERSONA_FILE": os.path.join(ROOT, "persona.md"),
        # LAYERED PERSONA (2026-07-30): a directory of fragments, each with `order` and an
        # optional `when: <knob>`, composed ONCE at session start. Its composition REPLACES
        # persona.md's prose when the directory exists (the `## Personality state` block
        # still comes from persona.md — its writer rewrites that block on tag shifts).
        # Absent directory = persona.md exactly as before. This is what stops "turn thinking
        # off" from meaning "remember to hand-edit the section that teaches the channel".
        "SP_PERSONA_DIR": os.path.join(ROOT, "persona"),
        "SP_MCP_CONFIG": os.path.join(ROOT, "mcp_servers.json"),
        # POOLED MCP SESSIONS. Connect-per-call measured 2.2 s EVERY call with 24 ms
        # variance — a process spawn, not a slow tool. 0 falls back to the old path,
        # which is slow and known-good.
        "SP_MCP_POOL": b(c.get("mcp", {}).get("pool", True)),
        "SP_MCP_CALL_TIMEOUT": str(c.get("mcp", {}).get("call_timeout_s", 60)),
        # TOOL PINNING (2026-08-25). Every bridged tool's name + description + schema is
        # fingerprinted on first sight and a CHANGED fingerprint is refused by name — the
        # rug-pull defence, because a tool's description is prompt. ON by default; this is
        # the hatch, so a refusal is never the reason the stack is down at 3am. Accepting
        # a legitimate change is `python tools/mcp_pin.py --accept <server> <tool>`, which
        # is what the refusal message tells you to run.
        "SP_MCP_PIN": b(c.get("mcp", {}).get("pin", True)),
        # ── TELEMETRY (2026-08-26) ──────────────────────────────────────────────
        # His body and his devices, as a source she can be present to. The store is a
        # day-per-file JSONL under var/, same shape as her speech ledger. RETENTION IS
        # DELIBERATELY OFF: "nothing is ever deleted" is a rule about what she BELIEVES,
        # and instrument data at 1 Hz is a different question — so the knob exists, the
        # default keeps everything, and `store.prune()` is the only remover.
        # WHERE THE GATEWAY LISTENS. 127.0.0.1 unless a profile says otherwise, because
        # loopback IS the security model (app.py's __main__ says why in full). A profile
        # that widens it is making a decision about who can reach her, and it should look
        # like one in the file.
        "SP_GATEWAY_BIND": (c.get("serve", {}).get("bind") or "127.0.0.1"),
        # HOME ASSISTANT (2026-08-26). The URL and the interval are operator config and
        # belong in the profile like everything else. THE TOKEN IS NOT HERE and must never
        # be: everything in profiles/ is committed and everything committed is exported, so
        # a long-lived token in a TOML file is a token in the public repo a fortnight later.
        # Only the PATH to it is mapped; the secret itself lives in var/, which is neither.
        "SP_HA_URL": str(c.get("homeassistant", {}).get("url", "") or ""),
        "SP_HA_POLL_S": str(c.get("homeassistant", {}).get("poll_s", 60)),
        "SP_HA_TOKEN_FILE": os.path.join(VAR, "ha_token"),
        "SP_TELEMETRY_DIR": os.path.join(VAR, "telemetry"),
        "SP_TELEMETRY_KEEP_DAYS": str(c.get("telemetry", {}).get("keep_days", 0)),

        "SP_MCP_PINS": os.path.join(VAR, "mcp", "pins.json"),
        "SP_DAEMON_LOG": os.path.join(VAR, "daemon.log"),
        # ── SENSES (2026-07-31) ────────────────────────────────────────────────
        # WHAT THE SERVED MODEL CAN RECEIVE, ruled from a committed table rather
        # than assumed. This is the fix for a live defect: var/voice/embed_audio.npz
        # is the 12B's [3840,640] projection, and the served 26B has hidden size
        # 2816 with `audio_config: null` — no audio embedder at all. Nothing on
        # either side compared the widths, so the voice path was feeding a 2816-wide
        # model 3840-wide frames. harness/senses/capability.py now refuses.
        # How many fence-free characters the streaming agent holds before deciding a
        # generation is an ANSWER rather than a tool round. Too short and a reasoning
        # preamble gets flushed to the console as her reply (it was 80 — shorter than
        # one sentence of planning). Streamed tokens cannot be retracted.
        "SP_TOOL_HOLD_CHARS": str(c.get("agent", {}).get("tool_hold_chars", 320)),
        # RESEARCH TIER. Grok, read-only, web ENABLED (the inverse of delegate_code's
        # posture). Off by default: it costs minutes and reaches off the machine.
        "SP_RESEARCH": b(c.get("research", {}).get("enabled", False)),
        "SP_RESEARCH_TIMEOUT": str(c.get("research", {}).get("timeout_s", 600)),
        "SP_RESEARCH_RECEIPTS": os.path.join(VAR, "research"),
        # RESEARCH BACKEND. grok = CLI headless (existing). xai = Responses API
        # with web_search, no grok.exe. auto = grok if present, else xai if keyed.
        # Keys are NOT profile values — a key in committed toml is a leak. Read
        # from the host env at boot (XAI_API_KEY / SP_XAI_API_KEY).
        "SP_RESEARCH_BACKEND": (c.get("research", {}).get("backend") or "grok"),
        "SP_RESEARCH_XAI_MODEL": (c.get("research", {}).get("xai_model") or "grok-4-1-fast"),
        # #41-aux: the LOCAL researcher's synthesis model (SidecarResearcher —
        # backend "sidecar", or "auto" when grok/xai are unavailable). The 2.6B is
        # tool/agent-trained and JIT-loads on the chat door; empty = the aux default.
        "SP_AUX_RESEARCH_MODEL": (c.get("research", {}).get("sidecar_model") or ""),
        # ── THE xAI API (2026-08-21, operator: "use the API instead of the cli").
        # ONE key, as a FILE under var/secrets/ (this repo is public): research,
        # her voice (Ara), and the image/video generator all read it through
        # harness/skills/xai.py. The CLI's auth.json dependency is gone.
        "SP_XAI_KEY_FILE": (c.get("xai", {}).get("key_file") or ""),
        "SP_TTS_METHOD": (c.get("tts", {}).get("method") or ""),
        "SP_TTS_XAI_VOICE": (c.get("tts", {}).get("xai_voice") or "ara"),
        "SP_TTS_SPEED": str(c.get("tts", {}).get("speed", 1.0)),   # her pace (knob voice.speed)
        "SP_XAI_IMAGE_MODEL": (c.get("xai", {}).get("image_model") or "grok-imagine-image-2.0"),
        "SP_XAI_VIDEO_MODEL": (c.get("xai", {}).get("video_model") or "grok-imagine-video-1.5"),
        "SP_XAI_API_KEY": (os.environ.get("SP_XAI_API_KEY")
                           or os.environ.get("XAI_API_KEY") or ""),
        # SEARCH. Same tool name (web_search). ddg is the floor. brave/tavily/
        # searxng need a key or a URL. auto picks the first keyed engine, else ddg.
        "SP_SEARCH_BACKEND": (c.get("search", {}).get("backend") or "ddg"),
        # which Grok answers the live-search engine (harness/skills/search.py XaiSearcher)
        "SP_SEARCH_XAI_MODEL": (c.get("search", {}).get("xai_model") or "grok-4-1-fast"),
        "SP_SEARCH_BRAVE_KEY": (os.environ.get("SP_SEARCH_BRAVE_KEY")
                                or os.environ.get("BRAVE_API_KEY") or ""),
        "SP_SEARCH_TAVILY_KEY": (os.environ.get("SP_SEARCH_TAVILY_KEY")
                                 or os.environ.get("TAVILY_API_KEY") or ""),
        "SP_SEARCH_SEARXNG_URL": (c.get("search", {}).get("searxng_url")
                                  or os.environ.get("SP_SEARCH_SEARXNG_URL") or ""),
        # MID-STREAM WATCHER (salvaged from CosySim's engine/pipeline). Stops a
        # generation that has started looping, rather than letting it run to the
        # token limit. ON by default — every threshold is tuned from real captured
        # degenerations, and the failure it prevents was observed five times today.
        "SP_WATCHER": b(c.get("quality", {}).get("watcher", True)),
        "SP_WATCHER_NGRAM": str(c.get("quality", {}).get("watcher_ngram", 6)),
        "SP_WATCHER_MIN_WORDS": str(c.get("quality", {}).get("watcher_min_words", 20)),
        "SP_WATCHER_RUN": str(c.get("quality", {}).get("watcher_run", 5)),
        "SP_WATCHER_RUN_MIN_WORDS": str(c.get("quality", {}).get("watcher_run_min_words", 12)),
        # ── THE WATCHDOG, FINALLY REACHABLE (2026-08-19) ──────────────────────────
        # watchdog.py read these three and build_env mapped NONE of them — and the
        # strip above means an unmapped knob reads only its hardcoded default in a
        # served stack. So the watchdog was on, at 30 s, uncooled-off-able, with NO
        # WAY TO DISABLE IT THROUGH THE ONE DOOR — which mattered the day it was
        # found un-shutting a deliberate shutdown. G-SEM-CONSERVE §1 had been red
        # on exactly these three names.
        "SP_WATCHDOG": b(c.get("watchdog", {}).get("enabled", True)),
        "SP_WATCHDOG_S": str(c.get("watchdog", {}).get("interval_s", 30)),
        "SP_WATCHDOG_COOLDOWN_S": str(c.get("watchdog", {}).get("cooldown_s", 600)),
        # Voice-lane knobs with live readers and no mapping (same class): defaults
        # preserved exactly; a profile may now actually change them.
        "SP_VOICE_DIR": c.get("voice", {}).get("dir") or os.path.join(VAR, "voice"),
        "SP_VOICE_EAR": b(c.get("voice", {}).get("force_ear", False)),
        "SP_VOICE_SOFT": b(c.get("voice", {}).get("soft", False)),
        "SP_VOICE_VAD_RMS": str(c.get("voice", {}).get("vad_rms", 0.010)),
        "SP_AUDIO_SCALE": str(c.get("voice", {}).get("audio_scale", 1.0)),
        "SP_VOICE_PROMPT": c.get("voice", {}).get("prompt")
                           or "The user just spoke to you out loud. First understand "
                              "exactly what they said, then reply directly and briefly "
                              "to their actual words — do not invent content you did "
                              "not hear:",
        # Directory knobs with in-code defaults identical to these (mapped so a
        # profile can move them; unmapped they simply did not exist).
        "SP_AVATAR_DIR": c.get("paths", {}).get("avatar_dir")
                         or os.path.join(VAR, "room", "avatar"),
        # the bundled default set (2026-08-23, his avatar_seed work). Mapped so the
        # closure holds - G-SEM-CONSERVE went red on it the moment it landed. Empty =
        # assets/avatar-default, which is avatar_seed's own default, so behaviour is
        # unchanged; rename the profile key if [paths] is the wrong home for it.
        "SP_AVATAR_DEFAULTS": (c.get("paths", {}).get("avatar_defaults") or ""),
        "SP_LEDGER_FILE": c.get("paths", {}).get("ledger_file")
                          or os.path.join(VAR, "room", "ledger.json"),
        # HER LIVE KNOBS (2026-08-24). `harness/tuning/registry.py:STORE` was a bare
        # constant with no override — the one store a gate could not be pointed away
        # from, and several gates call set_many(). One of them raced her RUNNING stack
        # over this file mid-sweep and died on the os.replace; on a quieter day it would
        # simply have changed her presence mode or her voice and said nothing. The
        # default is the path the constant already used, so nothing moves.
        "SP_TUNING_FILE": c.get("paths", {}).get("tuning_file")
                          or os.path.join(VAR, "tuning.json"),
        # (defaults below copied from the READERS — match.py/engine.py/scenarios.py all
        # fall back to var/room/<name>; the first draft of this mapping said var/<name>,
        # which would have silently moved three stores: the exact bug this table's own
        # empty-is-not-a-path comment documents, nearly re-shipped while fixing it.)
        "SP_GAMES_DIR": c.get("paths", {}).get("games_dir")
                        or os.path.join(VAR, "room", "games"),
        "SP_SCENES_DIR": c.get("paths", {}).get("scenes_dir")
                         or os.path.join(VAR, "room", "scenes"),
        "SP_SCENARIOS_DIR": c.get("paths", {}).get("scenarios_dir")
                            or os.path.join(VAR, "room", "scenarios"),
        # THE SHARED WORKSPACE. HARNESS_WORKSPACE defaulted to the process cwd, so
        # the "sandbox" harness/skills/builtin/coding.py resolves against was THE
        # WHOLE REPO — its _resolve() was doing its job perfectly against a boundary
        # nobody had drawn. Now a real directory, which is also what the room's file
        # browser will show. (Note the sandbox is tidiness for the FILE tools only:
        # run_shell/run_python in system_tools are unsandboxed by construction, and
        # the boundary that matters is which tools are in the set at all.)
        "HARNESS_WORKSPACE": os.path.join(VAR, "room", "files"),
        "SP_MAX_BODY_BYTES": str(c.get("serve", {}).get("max_body_bytes", 8 * 1024 * 1024)),
        # the gateway BINDS this (app.py reads env, never argv); 8800 is hers, companion.toml says 8810.
        # Found 2026-08-21: without it the Kairos gateway bound 8800 BESIDE her gateway (Windows lets
        # two listeners share a port) and the room could land on either.
        "SP_GATEWAY_PORT": str(c.get("serve", {}).get("gateway_port", 8800)),
        # HOURLY BACKUP of everything small and irreplaceable. See
        # harness/control/backup.py for what is included and what is deliberately
        # not (var/memory/eps is 1.2 GB and would fill the disk in a day).
        "SP_BACKUP": b(c.get("backup", {}).get("enabled", True)),
        "SP_BACKUP_INTERVAL_S": str(c.get("backup", {}).get("interval_s", 3600)),
        "SP_BACKUP_DIR": c.get("backup", {}).get("dir") or os.path.join(VAR, "backups"),
        "SP_BACKUP_KEEP": str(c.get("backup", {}).get("keep_hourly", 48)),
        "SP_BACKUP_KEEP_DAILY": str(c.get("backup", {}).get("keep_daily", 30)),
        "SP_BACKUP_EPISODES": b(c.get("backup", {}).get("include_episodes", False)),
        # THE RECORD PLAYER. Defaults to his Music folder; empty is fine and the
        # panel says so rather than looking broken.
        "SP_MUSIC": b(c.get("music", {}).get("enabled", True)),
        "SP_MUSIC_DIR": c.get("music", {}).get("dir") or os.path.join(
            os.path.expanduser("~"), "Music"),
        "SP_MUSIC_MAX": str(c.get("music", {}).get("max_tracks", 5000)),
        "SP_CAPABILITY_TABLE": os.path.join(ROOT, "config", "model_capability.json"),
        # SIGHT: the model's own 27-block ViT (mmproj-BF16.gguf) reimplemented in numpy.
        # OFF until G-SIGHT compares it against a reference on the same image — a
        # vision encoder that is subtly wrong does not error, it hallucinates.
        "SP_SIGHT": b(c.get("senses", {}).get("sight", False)),
        "SP_GAMES": b(c.get("senses", {}).get("games", False)),
        "SP_CAM_INDEX": str(c.get("senses", {}).get("cam_index", 0)),
        # SPEECH OUT: `url` set => the warm resident server; empty => per-utterance
        # CLI, which pays model load and shader warm-up every sentence.
        "SP_TTS_URL": (c.get("tts", {}).get("url") or ""),
        "SP_TTS_VOICE": c.get("tts", {}).get("voice", "casual_female"),
        "SP_TTS_STEPS": str(c.get("tts", {}).get("euler_steps", 3)),
        "SP_TTS_DEVICE": c.get("tts", {}).get("device", "discrete"),
        # The cap that stops the 47-minute run: long input on this build does not
        # degrade, it blows up (a 20 s paragraph hit 11.9/12 GB VRAM). Callers split.
        "SP_TTS_MAX_CHARS": str(c.get("tts", {}).get("max_chars", 240)),
        "SP_TTS_CACHE": os.path.join(VAR, "voice", "tts"),
        "SP_TTS_CACHE_MAX": str(c.get("tts", {}).get("cache_max", 512)),
        "SP_TTS_TIMEOUT": str(c.get("tts", {}).get("timeout_s", 600)),
        "SP_TTS_ROOT": c.get("tts", {}).get("root") or TTS_ROOT,
        # `exe` is the per-utterance CLI (harness/voice/tts.py); the resident server
        # binary is `server_exe` (launch_tts). Two tools, two keys — see launch_tts.
        "SP_TTS_EXE": c.get("tts", {}).get("exe")
                      or os.path.join(TTS_ROOT, "target", "release", "voxtral.exe"),
        "SP_TTS_GGUF": c.get("tts", {}).get("gguf")
                       or os.path.join(TTS_ROOT, "models", "voxtral-tts-q4.gguf"),
        # WHAT TEARDOWN KILLS, derived from the profile rather than hardcoded twice:
        # the engine binary is per-profile (target-wirecuda vs target — a renamed or
        # relocated build made stop() a silent no-op), and so is the voice server.
        "SP_ENGINE_IMAGE": os.path.basename(c["paths"]["engine_exe"]),
        "SP_TTS_SERVER_IMAGE": os.path.basename(
            c.get("tts", {}).get("server_exe")
            or os.path.join(TTS_ROOT, "target", "release", "tts-server.exe")),
        # Cameras hand back the first frames black while auto-exposure settles, so
        # frame 0 is reliably a photo of nothing. Discard this many first.
        "SP_CAM_WARMUP": str(c.get("senses", {}).get("cam_warmup", 5)),
        # THE ROOM, ON A TIMER. Default ON — but the LIVE profile has it OFF with a
        # written arming condition (CUDA-fault suspect; see companion.toml and the
        # OFF-BY-DEFAULT ledger). This comment used to say "ON by default at the
        # operator's explicit instruction", describing a state the profile had
        # reverted — the launcher asserting what the profile denies is the two-copies
        # bug in miniature. Re-read every tick, so flipping it takes the next beat.
        "SP_AMBIENT": b(c.get("senses", {}).get("ambient", True)),
        "SP_AMBIENT_S": str(c.get("senses", {}).get("ambient_interval_s", 3600)),
        # the quiet window a due capture waits for (2026-08-21, the re-arm guard)
        "SP_AMBIENT_QUIET_S": str(c.get("senses", {}).get("ambient_quiet_s", 300)),
        # the ceiling on what one look may say (2026-08-21 — 220 cut his white-jumper
        # photo's description mid-thought; the chip was innocent, it trims at its edge)
        "SP_SIGHT_LOOK_TOKENS": str(c.get("senses", {}).get("look_tokens", 512)),
        # may an overdue capture fire straight after a start/bounce? (2026-08-21,
        # same shape as the kairos act-first-at-bounce knobs — default no)
        "SP_AMBIENT_ON_BOOT": b(c.get("senses", {}).get("ambient_on_boot", False)),
        "SP_AMBIENT_LOG": os.path.join(VAR, "senses", "ambient.jsonl"),
        # HER ROOM NOTE IS PERSONAL (2026-08-21, his ask: "it should be about me...
        # His bed, his desk... a shared, more personalized experience"). The eye is
        # her window into HIS world, and only he lives there — so the note names
        # Sam, never "a man", and the room's things are his. The stranger clause
        # stays load-bearing: it is also the seed of "notice if others are here".
        "SP_AMBIENT_PROMPT": c.get("senses", {}).get("ambient_prompt",
            "You are Kairos, glancing into Sam's room — your person, and the "
            "only one who lives there. One or two short sentences in your own "
            "warm voice: what he is doing if you can see him (he is Sam, never "
            "'a man' or 'a person'), or how his room sits without him — his desk, "
            "his bed, his things, the light. Plain observations, fondly said. If "
            "someone who is not Sam is there, say so plainly."),
        "PYTHONPATH": ROOT,
    })
    # ── EMPTY IS NOT A PATH (2026-07-30) ─────────────────────────────────────────────
    # The seven path knobs above are documented as "empty = the code's own default". That
    # was false, and it did damage the same night it landed. Every reader spells it
    #
    #     CONV_ROOT = os.environ.get("SP_CONV_OKF_ROOT", <harness>/memory-okf-conv)
    #
    # and `os.environ.get` returns the DEFAULT only when the key is ABSENT. Exporting the
    # key as "" makes it present-and-empty, so the fallback never runs and the root becomes
    # "" — after which `os.path.join("", "full")` is `"full"`, relative to CWD.
    #
    # MEASURED: the first day-boundary pass wrote her conversation tier into the REPO ROOT
    # — bare `full/`, `sum/`, `LUT.md`, `index.md` beside serve.py, none of them covered by
    # .gitignore's `memory-okf*` lines, so they turned up as untracked files one command
    # away from being committed. The earlier run, before this mapping existed, had written
    # to `memory-okf-conv/` correctly. Mapping the knob is what broke it.
    #
    # So: a knob the profile did not set is DELETED, not blanked. Absent means absent.
    # (This is the G-ONEDOOR promise applied to the value as well as the key: a knob that is
    # mapped but exported empty is not reachable-with-a-default, it is silently wrong.)
    #
    # THE PROPERTY, NOT A LIST (2026-08-19). This was ten names, and the same bug had
    # already regrown OUTSIDE the list: SP_TTS_EXE/GGUF/ROOT, SP_SEM_INDEX,
    # SP_SEM_LAW_LOG, SP_SEM_SLOTS and the SP_DRAFT_* knobs were all exported
    # possibly-empty. A guard that only guards the things someone remembered to list is
    # not a guard — this file says that about the strip itself, 500 lines up. Every
    # empty-valued SP_* is deleted now: for a get(k, "")-style reader, absent and ""
    # are behaviourally identical; for a get(k, <real default>) reader, absent is the
    # only value that lets the default run — which is the whole point.
    for _k in [k for k, v in list(e.items()) if k.startswith("SP_") and v == ""]:
        del e[_k]

    # [debug] knobs (P5): optional taps, unset unless the profile arms them.
    dbg = c.get("debug", {})
    if dbg.get("hidden_dump"):
        os.makedirs(os.path.dirname(dbg["hidden_dump"].replace("/", "\\")), exist_ok=True)
        e["SP_HIDDEN_DUMP"] = dbg["hidden_dump"].replace("/", "\\")
    # G-VERBATIM: keep the tap open through the DECODE steps (the ones that make
    # every token the user sees). Without this we only ever measured prefill.
    if dbg.get("hidden_dump_decode"):
        e["SP_HIDDEN_DUMP_DECODE"] = "1"
    return e


def echo(env: dict) -> None:
    keys = [k for k in sorted(env) if k.startswith(("SP_", "CUBLAS"))]
    print("-- effective config --")
    for k in keys:
        print(f"  {k}={env[k]}")


def _probe_models(base: str, key_file: str) -> bool:
    """GET base/v1/models once, WITH the bearer from the key FILE if there is one — an
    endpoint with auth on (LM Studio 0.3.2x) answers 401 to a bare probe and the banner
    said 'NOT answering yet' while the gateway was already talking to it (2026-08-21)."""
    try:
        req = urllib.request.Request(base + "/v1/models")
        if key_file and os.path.exists(key_file):
            with open(key_file, encoding="utf-8") as f:
                k = f.read().strip()
            if k:
                req.add_header("Authorization", "Bearer " + k)
        urllib.request.urlopen(req, timeout=3).read()
        return True
    except Exception:
        return False


def wait_http(url: str, secs: int) -> bool:
    for _ in range(secs):
        try:
            urllib.request.urlopen(url, timeout=2).read()
            return True
        except Exception:
            time.sleep(1)
    return False


def launch_daemon(c: dict, env: dict) -> bool:
    """Start the engine and wait for it to answer. True if it came up.

    ONE COPY, TWO CALLERS (2026-08-06). The full launch and `--daemon-only` both need
    exactly this, and a second copy of it is how the daemon-only path ends up launching
    with last month's arguments the first time these change — the unguarded path being
    the one that runs is this repo's own named bug class.
    """
    # APPEND, and stamp each boot — this was "w", truncating the previous boot's stdout
    # on every launch, 200 lines under the comment explaining why the gateway log must
    # never do exactly that. On a failed boot the traceback lives HERE, not in
    # var/daemon.log (the engine's own runtime log) — the error messages now say so.
    # utf-8 EXPLICITLY: the default Windows encoding is cp1252 and the stamp below
    # crashed the very first boot after it was written. (Popen writes the daemon's raw
    # bytes through the fileno; the encoding governs only this header line.)
    # THE SP-SPECIFIC HALF LIVES IN engine/launch.py (2026-08-21) — imported lazily so
    # this launcher runs with no engine/ directory at all (the engine-agnostic export).
    from engine.launch import launch_daemon as _launch
    return _launch(c, env)


def stop(c=None) -> None:
    # BY THE PROFILE'S OWN BASENAMES when we have a profile: engine_exe and the voice
    # server are both per-profile knobs, and killing hardcoded image names worked by
    # coincidence of all 14 profiles agreeing — a renamed build made stop() a silent
    # no-op. The bare `--stop` path has no profile and keeps the defaults.
    # The daemon and the voice server — by the profile's own image basenames — through
    # engine/launch.py when it is present; under an external engine there is nothing of
    # ours to kill but the voice server and the gateway. An orphaned tts-server holds
    # ~1.8 GB and, mid-generation, the GPU at 100%, so it is in `stop`, not only in the
    # ctrl-C path, because a full launch calls stop() first.
    try:
        from engine.launch import stop_daemon as _stop_daemon
        _stop_daemon(c)
    except ImportError:
        tts_img = os.path.basename((c or {}).get("tts", {}).get("server_exe") or "tts-server.exe")
        subprocess.run(["taskkill", "/F", "/IM", tts_img], capture_output=True)
    # the gateway — BY PORT when a profile names one (two stacks may share the box now)
    stop_gateway_only((c or {}).get("serve", {}).get("gateway_port") if c else None)
    print("stack stopped")


def _daemon_model_of(cfg) -> str:
    """The model path this profile would serve.

    Read through `c["paths"]["model"]` — the SAME expression the daemon launch uses
    below and that build_env maps to SP_MODEL_PATH. My first cut guessed `c["model"]`,
    got None, and the guard passed silently on the very mismatch it was written for:
    a check that cannot find its subject reports agreement. Hence one expression, and
    an empty result is treated as "could not determine" rather than "fine".
    """
    try:
        from engine.launch import daemon_model_of as _dm
        return _dm(cfg)
    except ImportError:
        try:
            return str(cfg["paths"]["model"]).strip()
        except Exception:
            return ""


def _running_daemon_model() -> str:
    """The model the LIVE daemon is actually serving, read from its own command line.

    Ground truth on purpose. A launch record written by serve.py would be a second copy
    of the same fact and would go stale the first time a daemon was started any other
    way — and the whole point of this guard is to catch the case where the two halves
    of the stack disagree. The process argv cannot be stale: it is what is running.

    Returns "" when it cannot be determined, and the caller says so out loud rather than
    passing silently.
    """
    try:
        from engine.launch import running_daemon_model as _rdm
        return _rdm()
    except ImportError:
        return ""


def stop_gateway_only(port=None) -> None:
    """Kill the gateway — BY PORT when one is given (2026-08-21): two stacks may now
    run side by side (hers on 8800, the engine-agnostic companion on 8810 while Kairos
    is developed), and a stop that killed every `harness.server.app` would take hers
    down to bounce the other. The port rides on the spawn argv for exactly this;
    app.py reads no argv. A bare stop (no profile, no port) still kills them all."""
    m = "harness.server.app"
    if port:
        m = "harness.server.app.*--gateway-port %s\\b" % int(port)
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                    "Where-Object {$_.CommandLine -match '%s'} | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" % m], capture_output=True)


def main() -> int:
    # ── THE ARGUMENT THAT WASN'T (2026-07-29) ────────────────────────────────
    # This took the FIRST non-dash arg and dropped the rest on the floor, so
    #     python serve.py agent --profile companion      <- the 12B, NOT what he meant
    # booted the 12B under profile `agent` and said "profile=agent" while the
    # operator read it as the model. That is this repo's own bug class wearing a
    # different hat: a knob that does not exist, silently accepted. serve.py is
    # THE ONE DOOR — it strips every unmapped SP_*, and it has no business being
    # laxer about its own argv than it is about the environment. Unknown flags
    # and a second profile name are now hard errors.
    KNOWN_FLAGS = {"--stop", "--gateway-only", "--daemon-only"}
    pos = [a for a in sys.argv[1:] if not a.startswith("-")]
    bad = [a for a in sys.argv[1:] if a.startswith("-") and a not in KNOWN_FLAGS]
    if bad:
        raise SystemExit(
            "serve.py: unknown option(s): %s\n"
            "  usage: python serve.py [profile] [--stop] [--gateway-only] [--daemon-only]\n"
            "  the profile is POSITIONAL — `python serve.py companion`, not `--profile companion`."
            % " ".join(bad))
    if len(pos) > 1:
        raise SystemExit(
            "serve.py: more than one profile given: %s\n"
            "  usage: python serve.py [profile] [--stop] [--gateway-only] [--daemon-only]" % " ".join(pos))
    if "--gateway-only" in sys.argv and "--daemon-only" in sys.argv:
        # --gateway-only was checked first, so this combination silently did a gateway
        # bounce — half of what was asked, with no word about the other half. This
        # file's own doctrine: no business being laxer about its own argv.
        raise SystemExit(
            "serve.py: --gateway-only and --daemon-only are mutually exclusive.\n"
            "  a full launch (no flag) starts both halves.")
    # ── A BARE `python serve.py` BOOTED THE 12B (2026-08-04) ────────────────────────
    # The default was "agent", which is `profiles/agent.toml` — the retired 12B, with
    # eot_bias 4.0, byteexact on and pmax 13000. It starts, warms, answers, and reports
    # healthy while serving a different model: this file's own comment below records the
    # outage it caused (eight --gateway-only bounces on `agent` against a running 26B,
    # every turn coming back zero characters while /health said ok), and agent.toml's
    # header records it costing a restart mid-measurement on a second occasion.
    #
    # A default that silently picks a MODEL is not a convenience. It is refused now, and
    # the message names the two real choices rather than making the caller guess — the
    # 12B is still runnable on purpose, just never by omission.
    # --stop FIRST: it kills processes and needs no profile, so it must not be gated by a
    # check about which model to start. (The first cut of this guard raised SystemExit
    # with an empty message on the --stop path — which still EXITS, so `serve.py --stop`
    # silently stopped stopping. Caught by running it.)
    if "--stop" in sys.argv:
        # A named profile sharpens the kill to that profile's own image basenames;
        # bare --stop keeps the defaults (it must never require a profile).
        _c = None
        if pos:
            try:
                _c = load_profile(pos[0])
            except Exception:
                pass
        stop(_c)
        return 0
    if not pos:
        raise SystemExit(
            "serve.py: name the profile — it selects the MODEL, so there is no safe default.\n"
            "  python serve.py companion     <- her. your model, the daily driver.\n"
            "  python serve.py agent         <- the retired 12B, on purpose.\n"
            "  (profiles/*.toml for the rest; --stop needs no profile)")
    name = pos[0]
    c = load_profile(name)
    os.makedirs(VAR, exist_ok=True)
    env = build_env(c)
    # ── --gateway-only (P1b-2a lesson): restart JUST the gateway with the SAME
    # schema-checked env the full boot uses. Hand-rolled envs wedged a daemon
    # turn on 2026-07-11 (receipt G-KAIROS-P1b-2a) — the launcher owns the env.
    if "--gateway-only" in sys.argv:
        # THE PROFILE MUST AGREE WITH THE DAEMON THAT IS ALREADY RUNNING.
        #
        # 2026-08-01, and this cost a live outage. The daemon was serving the model;
        # eight gateway bounces were done with `serve.py agent`, which is the 12B
        # profile. It carries eot_bias = 4.0, tuned for the 12B — and companion.toml
        # sets 0.0 with a comment saying exactly why: on your model at 4.0 the FIRST
        # sampled token is a stop. So every turn came back with zero characters and she
        # went completely silent, while /health said ok, warm and daemon:true.
        #
        # That is the worst shape a bug can have: a mismatched gateway is INDISTINGUISH-
        # ABLE from a working one until she stops speaking, and the decode knobs that
        # differ between profiles are exactly the ones with no visible symptom short of
        # silence. `--gateway-only` exists to be run often and casually; it therefore
        # has to be the thing that checks.
        want = _daemon_model_of(c)
        running = _running_daemon_model()
        if (c.get("engine", {}).get("kind") or "sp") != "sp":
            want = running = ""          # an external engine: no daemon to agree with
        if running and want and os.path.normcase(running) != os.path.normcase(want):
            print("!! REFUSED: profile %r serves\n     %s\n   but the running daemon is\n     %s"
                  % (name, want, running))
            print("   A gateway built from the wrong profile sends that model's decode\n"
                  "   knobs to this one. Bounce with the matching profile, or stop the\n"
                  "   daemon and do a full boot.")
            return 2
        if not running or not want:
            # Cannot verify — say so LOUDLY rather than imply a check happened. A silent
            # unverified pass is how the original bug survived eight bounces, and it is
            # also how my own first cut of this guard passed the mismatch it exists for.
            print("[kairos serve] WARNING: could not verify profile/model agreement "
                  "(profile=%r daemon=%r)" % (want or "?", running or "no daemon found"))
        print(f"[kairos serve] profile={name} (gateway-only bounce; daemon untouched)")
        stop_gateway_only(c["serve"]["gateway_port"])
        # ── APPEND, DO NOT TRUNCATE (2026-08-05) ────────────────────────────────
        # This was "w". Every restart erased the gateway log — and her unprompted
        # life lives ONLY there: what she did on her own time, why kairos allowed
        # it, which session ticked. An evening of it was analysed and then wiped by
        # the very restart that shipped the fixes for what it showed. A log you
        # destroy to deploy is a log you cannot learn from twice.
        #
        # The daemon's own log has always been "a", which is why the CUDA fault
        # count could be compared across a week. This is the same rule, three
        # lines later, in the file that starts both.
        gw_log = open(os.path.join(VAR, "gateway.log"), "a")
        subprocess.Popen(
            [sys.executable, "-m", "harness.server.app",
         "--gateway-port", str(c["serve"]["gateway_port"])],   # identification only (app.py reads no argv): stop() kills BY PORT
            env=env, cwd=ROOT, stdout=gw_log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW)
        if not wait_http(f"http://127.0.0.1:{c['serve']['gateway_port']}/health", 45):
            print("!! gateway did not come up — see var/gateway.log")
            return 1
        print(f"[kairos serve] gateway up on :{c['serve']['gateway_port']}")
        return 0
    # BACK UP HER STATE BEFORE ANYTHING RUNS. persona.md holds the personality
    # block — voice, mood, traits — and it is gitignored, so a bad write is
    # unrecoverable. On 2026-07-31 a GATE overwrote it with a test payload (the
    # refusal it was proving was not live yet), and the only backup was a day old
    # from an unrelated layer write. One copy per launch costs nothing and would
    # have made that a non-event.
    try:
        _pm = os.path.join(ROOT, "persona.md")
        if os.path.isfile(_pm) and os.path.getsize(_pm) > 200:
            import shutil as _sh
            _bk = os.path.join(VAR, "persona-backups")
            os.makedirs(_bk, exist_ok=True)
            _sh.copy2(_pm, os.path.join(
                _bk, "persona-%s.md" % time.strftime("%Y%m%d-%H%M%S")))
            _old = sorted(os.listdir(_bk))
            for _f in _old[:-30]:            # keep the last 30
                os.remove(os.path.join(_bk, _f))
    except Exception as _e:
        print(f"[kairos serve] persona backup skipped: {_e}")
    print(f"[kairos serve] profile={name}")
    echo(env)

    # ── BRING HER BACK WITHOUT KILLING THE CALLER (2026-08-06) ────────────────
    # The room's start button runs this. It CANNOT run the ordinary launch: `stop()` two
    # lines below kills every python process matching harness.server.app — which is the
    # gateway that spawned it. A start button built the obvious way would kill the thing
    # that pressed it.
    #
    # So: no stop(), no gateway, and the profile comes from argv exactly as it does for a
    # full launch, because a restart that silently comes up on a different model has cost
    # this repo a session before.
    daemon_only = "--daemon-only" in sys.argv
    external = (c.get("engine", {}).get("kind") or "sp") != "sp"
    if daemon_only and external:
        print("[kairos serve] --daemon-only: this profile's engine is EXTERNAL (%s) — "
              "there is no daemon to start; start the engine yourself."
              % (c.get("engine", {}).get("base_url") or "?"))
        return 0
    if daemon_only:
        # ── ADOPTION IS NOT SUCCESS (2026-08-19) ──────────────────────────────
        # launch_daemon Popens the exe and then polls /v1/metrics — so if a daemon
        # was ALREADY bound to :3000, the new process died on the port bind, the
        # OLD daemon answered the poll, and this branch printed "daemon up" and
        # returned 0. From the room's start button that silently adopts whatever
        # is running — the exact 2026-08-01 wrong-model outage shape that
        # --gateway-only was hardened against, unguarded on the OTHER launch path.
        # Same check, both callers. What this must NEVER do is stop(): that kills
        # the gateway that pressed the button. It kills the daemon image only.
        running = _running_daemon_model()
        want = _daemon_model_of(c)
        if running and want and os.path.normcase(running) == os.path.normcase(want):
            print(f"[kairos serve] a daemon already serves this profile's model — "
                  f"adopted (daemon-only)")
            report_tts(launch_tts(c, env), env)
            return 0
        if running:
            print("!! a daemon is already up serving\n     %s\n   but profile %r wants\n"
                  "     %s\n   Replacing THE DAEMON ONLY (the gateway is the caller and "
                  "is never touched)." % (running, name, want))
            _img = os.path.basename(c["paths"]["engine_exe"])
            subprocess.run(["taskkill", "/F", "/IM", _img], capture_output=True)
            if _img.lower() != "sp-daemon.exe":
                subprocess.run(["taskkill", "/F", "/IM", "sp-daemon.exe"],
                               capture_output=True)
            time.sleep(1.0)
        if not launch_daemon(c, env):
            print("!! daemon did not come up — see var/daemon.boot.log (stdout) "
                  "and var/daemon.log")
            return 1
        print(f"[kairos serve] daemon up on :{c['serve']['port']} (daemon-only)")
        # The voice's fate was computed and DISCARDED here — room-button restarts got
        # no TTS status at all while the full launch printed one.
        report_tts(launch_tts(c, env), env)
        return 0

    stop(c)
    if external:
        # THE ENGINE IS YOURS (2026-08-21, the engine-agnostic profile): the harness
        # starts nothing but itself. It does say whether the endpoint answers, once.
        _base = (c.get("engine", {}).get("base_url") or "").rstrip("/")
        _up = _probe_models(_base, env.get("SP_ENGINE_API_KEY_FILE", "")) if _base else False
        print("[kairos serve] engine: EXTERNAL at %s — %s" % (
            _base or "?", "answering /v1/models" if _up else
            "NOT answering yet (start LM Studio / llama-server; she will speak when it does)"))
    elif not launch_daemon(c, env):
        print("!! daemon did not come up — see var/daemon.boot.log (stdout) "
              "and var/daemon.log")
        return 1
    else:
        print(f"[kairos serve] daemon up on :{c['serve']['port']}")

    # ── HER VOICE (2026-07-31) ────────────────────────────────────────────────
    # Started BEFORE the gateway and NOT waited on. Both of those are deliberate.
    #
    # Before, because it takes ~37 s to become useful (5 s model load + ~31 s for
    # the first generation to compile shaders) and starting it early means that
    # runs concurrently with the gateway coming up instead of after it.
    #
    # Not waited on, because SPEECH IS NOT LOAD-BEARING. If voxtral is missing,
    # the GPU is busy, or the binary was never built, she should still be able to
    # talk to him in text — a stack that refuses to boot because the voice failed
    # has its priorities backwards. tts.py falls back to the per-utterance CLI on
    # its own, and /v1/speak/status says which way it went.
    _tts = launch_tts(c, env)
    launch_aux_embed(c, env)
    gw_log = open(os.path.join(VAR, "gateway.log"), "a")   # append: see above
    subprocess.Popen(
        [sys.executable, "-m", "harness.server.app",
         "--gateway-port", str(c["serve"]["gateway_port"])],   # identification only (app.py reads no argv): stop() kills BY PORT
        env=env, cwd=ROOT, stdout=gw_log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW)
    if not wait_http(f"http://127.0.0.1:{c['serve']['gateway_port']}/health", 45):
        print("!! gateway did not come up — see var/gateway.log")
        return 1
    print(f"[kairos serve] gateway up on :{c['serve']['gateway_port']}")
    report_tts(_tts, env)
    # ── LOAD-TIME PREFILL (operator, 2026-07-11): do NOT report ready while the
    # preamble is still prefilling. The old behavior (background prewarm + open
    # gateway) let the first user turn race the prefill on the one resident
    # session -> persist guard miss -> BOTH paid ~5 minutes. Wait for it here;
    # the gateway also gates chat traffic on the same event.
    if c["agent"].get("prewarm", False) and not external:
        print("[kairos serve] prefilling the persona+tools prefix (load-time; ~2-5 min cold)...", flush=True)
        t0 = time.time()
        hot = False
        for _ in range(900):
            try:
                h = json.loads(urllib.request.urlopen(
                    f"http://127.0.0.1:{c['serve']['gateway_port']}/health", timeout=3).read())
                if h.get("warm"):
                    hot = True
                    break
            except Exception:
                pass
            time.sleep(1)
        print(f"[kairos serve] {'prefix HOT in %.0fs — first turn is fast' % (time.time() - t0) if hot else 'prewarm did not confirm; first turn may be slow'}")
    print(f"[kairos serve] READY. the room: http://127.0.0.1:{c['serve']['gateway_port']}/room/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


