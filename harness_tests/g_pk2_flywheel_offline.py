"""G-PK2-FLYWHEEL (offline) — ADR-005 flywheel ∘ ADR-008 ring: spine receipts persist into the
durable telemetry-okf tier (content-addressed, idempotent, kind='spine'), via the EXISTING
TelemetrySink (anti-rebuild). No daemon.

    python tests/g_pk2_flywheel_offline.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REG = os.path.join(tempfile.gettempdir(), "sp_pk2_flywheel.jsonl")
PERSONA = os.path.join(tempfile.gettempdir(), "sp_pk2_flywheel_persona.md")
ROOT = tempfile.mkdtemp(prefix="pk2_telemokf_")
os.environ["SP_RECALL_REGISTRY"] = REG
os.environ["SP_PERSONA_FILE"] = PERSONA
os.environ["SP_TELEMETRY_OKF_ROOT"] = ROOT
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:59999"
open(REG, "w").close()
with open(PERSONA, "w", encoding="utf-8") as f:
    f.write("You are Kairos.\n\n## Personality state\nmood: neutral\n")

from harness.control.spine import run_post_turn, persist_receipts
from harness.telemetry.sink import TelemetrySink


def check(name, ok):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    return ok


def main() -> int:
    res = []

    # make two spine decisions (a verified persona shift + a quiet turn)
    run_post_turn("hey", "Sure thing. [MOOD:helpful]")
    n1 = persist_receipts()
    res.append(check("receipts persisted to telemetry-okf", n1 >= 1))

    recdir = os.path.join(ROOT, "records")
    files = os.listdir(recdir) if os.path.isdir(recdir) else []
    res.append(check("content-addressed record files exist", len(files) == n1))
    rec = json.loads(open(os.path.join(recdir, files[0]), encoding="utf-8").read())
    res.append(check("record is kind=spine with verify verdict",
                     rec.get("kind") == "spine" and "verified" in rec and rec.get("decision") == "persona_shift"))

    # idempotence: nothing new to flush; and a re-flush of the same ring adds nothing
    n2 = persist_receipts()
    res.append(check("second flush is a no-op (watermark)", n2 == 0))

    # the sink's index sees them as kind_spine (the flywheel corpus classifier)
    stats = TelemetrySink(ROOT).stats()
    res.append(check("sink stats count kind_spine", stats.get("kind_spine", 0) == n1))

    # a NEW decision after the flush persists incrementally
    run_post_turn("hey", "Right. [MOOD:focused]")
    n3 = persist_receipts()
    res.append(check("incremental flush picks up only new receipts", n3 >= 1))

    ok = all(res)
    print(f"\nG-PK2-FLYWHEEL (offline): {'PASS' if ok else 'FAIL'} ({sum(res)}/{len(res)})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
