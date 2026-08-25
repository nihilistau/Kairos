"""telemetry — TWO TENANTS, and they are not the same subject. Read this before adding a third.

This package predates the body work and I collided with it (2026-08-26). It held the
engine's LM-B2 flywheel sink; I wrote a body-telemetry subsystem into the same directory and
my `__init__.py` REPLACED the old one, silently deleting its re-exports. Nothing failed —
every consumer imports `harness.telemetry.sink` directly, so the whole suite stayed green
over an API that no longer existed. A green suite is not an audit, and this is what that
looks like from the inside.

Both re-exports are back below. What follows is the map, so the next person does not have to
work out which "telemetry" a module means.

  ── TENANT 1: THE ENGINE'S FLYWHEEL SINK ──────────────────────────────────────────────
  `sink.py`. Subscribes to the sp-daemon's `GET /v1/events` SSE bus, filters
  `event: telemetry` records (already class-redacted by the engine — private-secret
  queries and outputs arrive hashed), and appends each one content-addressed into a durable
  store under `memory-okf-telemetry/`. It is the corpus that feeds the learned classifier
  and the data-gen / finetuning work. Deliberately separate from the Nexus KB (retrieval)
  and the fact store (episodes): it is the raw telemetry corpus tier.
  Consumers: `harness/control/spine.py`, `g_pk2_flywheel_offline`, `h_telemetry_sse`.

  ── TENANT 2: HIS BODY ────────────────────────────────────────────────────────────────
  `store.py`, `ingest.py`, `body.py`. Heart rate, movement, on-body and sleep from a watch
  agent, in three tiers that are not the same kind of claim:

      device state   screen, charging, battery temperature.   adb / a companion.
      phone sensors  steps, motion, light, orientation.        needs permissions.
      body           heart rate, movement, on-body, sleep.     the watch.

  A heart rate of 96 is OBSERVED — the watch measured it. "He is stressed" is INFERRED, and
  the memory doctrine already has a word for what happens when an inference wears an
  observation's clothes. `store` and `ingest` handle measurements; `body` turns measurements
  into the bounded sentences she is allowed to read; nothing hands her a number stream.

  WHAT SHE NEVER GETS: the raw feed. Sixty heart-rate samples a minute in her prefix would be
  expensive, useless, and would teach her to talk like a monitor. She gets facts with edges —
  "he has not moved in two hours", "asleep since 23:40" — and `body` produces nothing else.

  ANON MODE HOLDS THAT DOOR. Off the record promises nothing is written down, and this is the
  most intimate row in the store. The gate is at `ingest.record`, the one writer.

  Doc: `docs/TELEMETRY.md`. Lanes it uses: `docs/LANES.md` (2 and 5).

THE TWO SHARE A WORD AND NOTHING ELSE. `SP_TELEMETRY_OKF_ROOT` is tenant 1's store;
`SP_TELEMETRY_DIR` is tenant 2's. They are different directories, different writers and
different subjects, and the only thing that makes that safe is this docstring — so if a
third arrives, split the package instead of adding a paragraph.
"""
from harness.telemetry.sink import TelemetrySink, sink_record

__all__ = ["TelemetrySink", "sink_record"]
