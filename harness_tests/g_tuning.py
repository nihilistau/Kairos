"""G-TUNING — a knob that does not change behaviour is decoration.

The whole recurring failure of this system is capability that EXISTS but is not
REACHABLE: the supersede lane nothing wrote to, the personality pack never wired into a
toolset, the KAIROS kernel that was never compiled, the recall authority nobody could
see. A settings panel is the easiest possible place to repeat that mistake — sliders
that move and change nothing.

So this gate does not check that the UI renders. It checks that turning a knob CHANGES
WHAT SHE DOES:

  * the registry declares knobs with bounds, help, and PROVENANCE (measured vs chosen)
  * an unknown key is REFUSED (a typo must not become a dead setting)
  * values are CLAMPED to their declared bounds
  * an override PERSISTS, and reset restores the declared default
  * and the load-bearing one: moving kairos.max_chain / kairos.continue_margin
    actually changes the decision the scheduler makes on the very next turn.

Offline: no daemon, no model.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# SANDBOX FIRST (2026-08-24). This gate was one of nine the sandbox audit caught
# writing into her REAL stores; `_gate.sandbox` points every root at a temp dir and
# must run BEFORE any harness import, because a module resolves its root once.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import sandbox as _sandbox  # noqa: E402
_sandbox(os.path.basename(__file__))

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def main() -> int:
    print("G-TUNING - a knob that does not change behaviour is decoration.\n")

    # isolate the store so the gate never touches the operator's real settings
    tmp = tempfile.mkdtemp(prefix="g_tune_")
    from harness.tuning import registry as tune
    tune.STORE = os.path.join(tmp, "tuning.json")
    tune._CACHE = None

    s = tune.schema()
    check("the registry declares knobs", len(s["knobs"]) >= 8, f"{len(s['knobs'])} knobs")
    check("every knob carries help text", all(k["help"] for k in s["knobs"]))
    check("measured defaults cite a receipt",
          all(k["receipt"] for k in s["knobs"] if k["provenance"] == "measured"),
          "so the operator can see WHICH numbers were calibrated and which were a judgement call")

    # unknown key refused
    try:
        tune.set_many({"kairos.nonsense": 1})
        check("an UNKNOWN knob is refused", False, "it was accepted — a typo becomes a dead setting")
    except ValueError as exc:
        check("an UNKNOWN knob is refused", True, str(exc))

    # clamping
    tune.set_many({"kairos.max_chain": 99})
    check("values are CLAMPED to declared bounds", tune.get("kairos.max_chain") == 3,
          f"max_chain 99 -> {tune.get('kairos.max_chain')}")

    # persistence + reset
    tune.set_many({"kairos.cooldown_s": 120.0})
    tune._CACHE = None                                   # force a re-read from disk
    check("an override PERSISTS to disk", tune.get("kairos.cooldown_s") == 120.0)
    tune.reset("kairos.cooldown_s")
    check("reset restores the declared default", tune.get("kairos.cooldown_s") == 45.0)

    # ── THE LOAD-BEARING TEST: does the knob actually bite? ────────────────────
    from harness.kairos.impulse import CONTINUE, SILENT, TurnState, decide, note_spoke
    from harness.kairos import scheduler as ks

    # SYNTHETIC CLOCKS (2026-08-23): a fresh TurnState's clocks default to impulse.BOOT_AT,
    # the real monotonic boot time (a1ecf2a — "a zero clock fails OPEN"), which sits in the
    # FUTURE of the small fixtures below (100.0, 5000.0 ...) and silenced every decision with
    # a nonsense cooldown. Pin the boot to t=1.0 for this process: non-zero, so the
    # no-zero-clock rule is still exercised, and before every `now` this gate uses. Same pin
    # as g_kairos_latch / g_kairos_presence / g_kairos_reasons, which a1ecf2a updated; this
    # gate was one of the five it missed.
    import harness.kairos.impulse as _imp_pin  # noqa: E402
    _imp_pin.BOOT_AT = 1.0

    tune.set_many({"kairos.enabled": True, "kairos.max_chain": 1})
    cfg = ks.live_config()
    check("the scheduler reads the LIVE config", cfg.enabled and cfg.max_chain == 1,
          f"enabled={cfg.enabled} max_chain={cfg.max_chain}")

    # THE CUT-OFF MARGIN IS DERIVED, NOT HARDCODED (2026-07-30). This said -15.0, a
    # number chosen because it sat below the retired reference model's calibrated -11.75. The margin scale is
    # PER MODEL: re-calibrating on your model moved the threshold to -18.50, and -15.0
    # silently flipped to the FINISHED side — so this gate failed on a correct threshold
    # and a correct knob. A fixture that encodes a measured constant breaks every time the
    # measurement is legitimately re-taken, and it fails pointing at the wrong thing.
    # Ask the question the gate is actually about — "clearly past the threshold" — and let
    # the threshold be whatever it currently is.
    CUT = cfg.continue_margin - 5.0
    st = TurnState(last_user_at=100.0)
    d1 = decide(cfg=cfg, state=st, now=101.0, eot_margin=CUT, reply_text="mid thought")
    note_spoke(st, 101.0)
    d2 = decide(cfg=cfg, state=st, now=102.0, eot_margin=CUT, reply_text="still going")
    check("max_chain=1 -> she continues ONCE then stops",
          d1.action == CONTINUE and d2.action == SILENT,
          f"cut margin {CUT} vs threshold {cfg.continue_margin}")

    # Raise it in the UI; the NEXT decision must obey, with no restart.
    # NOTE: the cooldown is a SEPARATE bound and also applies here — the first cut of this
    # test raised max_chain and asserted she'd continue 2s later, which the cooldown
    # (correctly) refused. Two bounds, one assertion: a bad test, not a bad knob. Isolate
    # max_chain by taking the cooldown out of the way.
    tune.set_many({"kairos.max_chain": 2, "kairos.cooldown_s": 0.0})
    cfg2 = ks.live_config()
    d3 = decide(cfg=cfg2, state=st, now=103.0, eot_margin=cfg2.continue_margin - 5.0,
                reply_text="still going")
    check("raise max_chain in the UI -> the NEXT turn obeys (no restart)",
          cfg2.max_chain == 2 and d3.action == CONTINUE,
          "the knob BITES")
    # ...and the cooldown is genuinely independent: put it back and she goes quiet again
    tune.set_many({"kairos.cooldown_s": 45.0})
    d4 = decide(cfg=ks.live_config(), state=st, now=103.0, eot_margin=-15.0, reply_text="x")
    check("the COOLDOWN is an independent bound (it re-silences her)", d4.action == SILENT,
          d4.reason)

    # and the margin threshold really gates her
    tune.set_many({"kairos.max_chain": 1, "kairos.continue_margin": -13.75})
    st2 = TurnState(last_user_at=100.0)
    quiet = decide(cfg=ks.live_config(), state=st2, now=101.0,
                   eot_margin=2.0, reply_text="a finished thought.")
    check("at the calibrated margin, a FINISHED turn stays silent", quiet.action == SILENT)

    tune.set_many({"kairos.continue_margin": 5.0})       # operator cranks it wide open
    loud = decide(cfg=ks.live_config(), state=st2, now=101.0,
                  eot_margin=2.0, reply_text="a finished thought.")
    check("crank continue_margin up -> she starts talking over finished turns",
          loud.action == CONTINUE,
          "exactly what the knob's danger note warns about — and the operator can see it happen")

    print(f"\nG-TUNING: {'PASS' if not FAIL else 'FAIL'} ({len(PASS)}/{len(PASS)+len(FAIL)})")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
