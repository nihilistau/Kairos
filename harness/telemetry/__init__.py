"""Harness telemetry sink — the durable egress for the engine's LM-B2 flywheel.

Subscribes to the sp-daemon ``GET /v1/events`` SSE bus, filters ``event: telemetry``
records (already class-redacted by the engine), and appends each one, content-
addressed, into a durable store so the corpus accumulates across sessions. This is
what fills the pipe for the learned classifier / data-gen + finetuning framework.
"""
from harness.telemetry.sink import TelemetrySink, sink_record

__all__ = ["TelemetrySink", "sink_record"]
