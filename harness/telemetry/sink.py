"""TelemetrySink — durable, content-addressed sink for engine LM-B2 telemetry.

The engine (gate G-LM-SSE) broadcasts every recall DECISION + TURN outcome on
``GET /v1/events`` as ``event: telemetry`` (already class-redacted: private-secret
queries/outputs are hashed). This module subscribes to that stream and appends each
record, content-addressed, into a durable store:

    <root>/records/<addr>.json   one file per UNIQUE record (addr = sha256[:16])
    <root>/log.jsonl             append-only index: one line per NEW record

Dedup is by content hash, so re-runs / reconnects are idempotent (the same record
sinks once). The store is deliberately SEPARATE from the Nexus KB (retrieval) and
the memory-okf/ fact store (episodes) — it is the raw telemetry corpus tier.

Run standalone against a live daemon (engine served with SP_TELEMETRY=1):
    python -m harness.telemetry.sink --root memory-okf-telemetry --seconds 20

Stdlib only (no engine/harness deps beyond the client) so it can run anywhere.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Tuple


def _addr(record_json: str) -> str:
    return hashlib.sha256(record_json.encode("utf-8")).hexdigest()[:16]


def _kind_and_class(rec: dict) -> Tuple[str, str]:
    """Classify a telemetry record: ('turn'|'decision'|'spine'|'?', mem_class)."""
    if rec.get("kind") == "turn":
        return "turn", str(rec.get("turn", {}).get("class", "-"))
    if rec.get("kind") == "spine":              # ADR-008: harness-spine receipt records
        return "spine", "-"
    if "recall" in rec:
        return "decision", str(rec.get("recall", {}).get("class", "-"))
    return "?", "-"


class TelemetrySink:
    """Content-addressed, idempotent sink for telemetry records."""

    def __init__(self, root: str = "memory-okf-telemetry") -> None:
        self.root = Path(root)
        self.records = self.root / "records"
        self.log = self.root / "log.jsonl"
        self.records.mkdir(parents=True, exist_ok=True)
        self.n_seen = 0
        self.n_new = 0

    def sink(self, record_json: str) -> Tuple[str, bool]:
        """Append one telemetry record. Returns (addr, is_new). Idempotent by hash.

        SAFETY: the record is written verbatim as received (already redacted by the
        engine); this sink never un-redacts and never inspects a secret value.
        """
        self.n_seen += 1
        record_json = record_json.strip()
        addr = _addr(record_json)
        path = self.records / f"{addr}.json"
        if path.exists():
            return addr, False  # dedup — already have it
        try:
            rec = json.loads(record_json)
        except json.JSONDecodeError:
            return addr, False  # not a JSON telemetry record — skip
        kind, mem_class = _kind_and_class(rec)
        path.write_text(record_json, encoding="utf-8")
        idx = {
            "addr": addr, "kind": kind, "class": mem_class,
            "redacted": bool(rec.get("redacted", False)),
            "ts_event": rec.get("ts"), "ts_ingest": int(time.time()),
        }
        with self.log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(idx) + "\n")
        self.n_new += 1
        return addr, True

    def run(self, client, stop: Optional[threading.Event] = None) -> None:
        """Long-lived loop: subscribe to /v1/events (telemetry only) and sink each.

        ``client`` is an ``SPDaemonClient``. Reconnects on stream error unless
        ``stop`` is set. Designed to run as a daemon thread beside the agency loop.
        """
        while stop is None or not stop.is_set():
            try:
                for ev in client.subscribe_events(want=["telemetry"]):
                    self.sink(ev.content)
                    if stop is not None and stop.is_set():
                        break
            except Exception:
                if stop is not None and stop.is_set():
                    break
                time.sleep(1.0)  # reconnect backoff

    def stats(self) -> Dict[str, int]:
        by_kind: Dict[str, int] = {}
        redacted = 0
        if self.log.exists():
            for line in self.log.read_text(encoding="utf-8").splitlines():
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                by_kind[o.get("kind", "?")] = by_kind.get(o.get("kind", "?"), 0) + 1
                if o.get("redacted"):
                    redacted += 1
        total = sum(by_kind.values())
        return {"records": total, "redacted": redacted, **{f"kind_{k}": v for k, v in by_kind.items()}}


def sink_record(record_json: str, root: str = "memory-okf-telemetry") -> Tuple[str, bool]:
    """One-shot convenience: sink a single record into ``root``."""
    return TelemetrySink(root).sink(record_json)


def _main() -> int:
    import argparse
    import threading as _t
    from harness.inference.client import get_client

    ap = argparse.ArgumentParser(description="Durable telemetry sink for /v1/events")
    ap.add_argument("--root", default="memory-okf-telemetry")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--seconds", type=float, default=0.0, help="0 = run forever")
    args = ap.parse_args()

    sink = TelemetrySink(args.root)
    client = get_client(args.base_url)
    stop = _t.Event()
    th = _t.Thread(target=sink.run, args=(client, stop), daemon=True)
    th.start()
    print(f"[telemetry-sink] subscribed to /v1/events -> {args.root} (stdlib content-address)", flush=True)
    try:
        if args.seconds > 0:
            time.sleep(args.seconds)
        else:
            while True:
                time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        time.sleep(0.3)
    print(f"[telemetry-sink] stats: {sink.stats()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
