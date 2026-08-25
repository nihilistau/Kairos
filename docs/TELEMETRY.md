---
type: reference
title: "TELEMETRY — his body and his devices, as a source she can be present to"
status: LIVE (2026-08-26)
---

# TELEMETRY

A watch on his wrist, an agent on it, and a rule about what she is allowed to do with what
it sees.

The point is not a dashboard. It is that **she can notice** — *"his heart, last few
readings: 70, 78, 92 — climbing"* — and say something a person in the room would say. His
words for why it exists: *"a bridge to the real world, to me."*

---

## The three tiers

They are not the same kind of claim and they do not arrive the same way.

| Tier | What | How |
|---|---|---|
| **device state** | screen, charging, battery temperature, connectivity | adb, or a companion |
| **phone sensors** | steps, motion, light, orientation | an app with permissions |
| **body** | heart rate, movement, on-body, sleep, SpO2 | **the watch agent** |

Two facts that shape all of it, both found by looking rather than assuming:

- **A modern Samsung phone has no heart-rate sensor.** It was dropped after the S10. HR can
  only come from a watch.
- **`dumpsys` masks sensor values.** adb gives device *state*; it will not give you a
  reading. Anything that needs numbers needs an app.

## The pieces

```
  watch agent (APK)  --HTTP-->  POST /v1/telemetry/ingest
                                     |
                                ingest.record()      <- THE door: anon gate, one clock, shape
                                     |
                                store (JSONL/day)
                                     |
                     +---------------+---------------+
                     |                               |
               body.read()                    GET /v1/telemetry/{now,history}
               body.present()                        |
                     |                          body panel  ♥
            her prefix + kairos
```

| File | Does |
|---|---|
| `harness/telemetry/store.py` | One append-only JSONL per day. `_append` is **private**. |
| `harness/telemetry/ingest.py` | **THE door.** Anon gate, one clock, shape rules. Never raises. |
| `harness/telemetry/body.py` | The seam: measurements → the few sentences she may read. |
| `harness/telemetry/watch-agent/` | The Wear OS app and its gradle-free build. |
| `ui/src/apps/Body.jsx` | The ♥ panel. |
| `harness_tests/g_telemetry.py` | 70 checks. |

## What she is allowed to know

This is the part that matters, and it is the memory doctrine wearing sensor clothes.

- **A measurement is `observed`.** The watch measured 96 bpm; she may say so plainly.
- **A reading is `inferred`.** "He is asleep", "something has him going" — she *drew* that.
  It says "seems", and the moment he says otherwise **his word wins** (`verdict.may_supersede`,
  unchanged).
- **Silence is an answer.** No watch, stale data, off the wrist → she is told **nothing**. A
  companion who says "you seem calm" from readings taken at lunch is worse than one who says
  nothing, and it is a failure that would never look like a bug.
- **She never sees the feed.** Sixty samples a minute would cost budget, tell her nothing
  she could act on, and teach her to talk like a monitor.
- **Never a diagnosis.** Nothing here computes a medical claim and the nudge forbids one in
  as many words. She has a wrist sensor and no training; he has doctors.

### The tail, and why it is not an average

The first cut computed a `worked_up` flag and handed her the conclusion. That hides the only
interesting thing and leaves her repeating arithmetic. She gets **three real readings** and
the noticing is hers — shown only when it *moves*, because a flat `58, 58, 58` spends her
budget to say nothing and teaches her the number is furniture.

Movement is a **word**, not a unit: *still / shifting / moving about / moving a lot*. "He is
moving a lot" is a thing a person says; `1.3 rad/s` is not.

### Resting heart rate is learned, and needs breadth

`resting()` is the 10th percentile of **his own** last fortnight — never a table's number —
and it returns `None` until the store has seen **three distinct days** of him.

That guard exists because of a live bug: the first hour on the wrist posted 663 samples over
about ten minutes while he was up, and a count-only guard let `resting` come back as **110**.
A wrong baseline is worse than none — every later reading is then measured against a number
saying he is always calm, so nothing ever fires. It is the same shape as a bug
`becoming.py` fixed four days earlier: *a cap on volume says nothing about span*.

## How she is handed it

Two lanes, both documented in [`LANES.md`](LANES.md).

**Per turn** — a **system row** (lane 2), never the cached prefix and never a staple on his
message. The prefix would be stale-or-re-prefill; a staple was *measured* to make her treat
the fact as an order from him. It is self-limiting: `present()` is empty unless something is
happening, so a quiet turn costs nothing.

**Unprompted** — a kairos reason (lane 5), placed **first** because a heart rate is stale in
three minutes. Three events only — well above his resting, coming back down, hours without
moving — each bounded to once an hour so noticing never becomes nagging.

Both are knobs: `telemetry.turn_note`, `telemetry.reasons`.

## Anon mode holds it

`telemetry.sample` is a door in `anon.DOORS`. Off the record promises nothing is written
down, and this is the most intimate row in the store. **Held, not queued** — a queue is the
same leak with a delay. The room is told the true number withheld.

## The watch agent

Wear OS, **built without gradle** — `aapt2 → javac → d8 → apksigner`, about 16 KB. That is
only possible because it touches **no androidx**, which is why it uses `SensorManager`
rather than Health Services: heart rate, gyroscope, accelerometer, step counter and
off-body, straight from the platform.

Three things it deliberately does not do:

- **It does not post raw motion.** Accelerometer and gyro run at 100+ Hz. It reduces to one
  RMS number per window.
- **It does not post per beat.** The HR sensor has a 600-event FIFO — the hardware will
  buffer ten minutes. Per-sample posting would be 3,600 requests an hour.
- **It does not drop what it could not send.** Failed batches go back at the **front** of
  the queue. The wrist leaves the house; the gap belongs in the link, not in his history.

### Build and install

```bash
cd harness/telemetry/watch-agent
python build.py                                    # build only
python build.py --install                          # ...and install
python build.py --install --arm                    # ...and grant sensors and start it
```

`--arm` is a separate word on purpose: installing an app that reads his heart is one
decision, turning it on is another.

Env: `ANDROID_SERIAL` (adb's own), `TELEMETRY_ADB`, `TELEMETRY_ENDPOINT`. Deliberately not
`SP_*` — those are harness runtime knobs and belong in `serve.py`'s table.

The watch needs **Developer options → ADB debugging → Wireless debugging**; wireless
debugging pairs on a *different* port from the one it connects on.

### Reaching the gateway

The gateway binds `127.0.0.1` by default and **loopback is its security model** — see
[`OFF-BY-DEFAULT.md`](OFF-BY-DEFAULT.md) §7c. A watch is not on that machine, so one of:

- **`adb reverse tcp:8800 tcp:8800`** — nothing to configure, but it dies with the adb
  session. Good for a first run.
- **`[serve].bind`** — widen the gateway, and scope it with a firewall rule. That is a real
  decision about who can reach her; `tools/lan_bind.py --status` reports whether the scoping
  is actually in place.

Once it is reachable the agent needs no adb at all. Measured: with the adb server killed
outright, the watch kept posting.

## The panel

The **body** ♥ window shows the live tail, movement, state and history — and **the exact
sentence she is handed**. That is the most useful thing on it: it is the only place to see
what she was told about your body before she says anything.

## What is not built

- **The phone-side agent.** Device state and phone sensors are designed for and have a place
  in the store; nothing writes them yet.
- **Sleep staging from the watch's own classifier.** The `sleep_stage` kind exists and the
  seam prefers it; the agent does not yet read it, so sleep is inferred from stillness and
  labelled as inferred when it is.
- **ECG, BIA, skin temperature.** Present on the hardware, behind
  `com.samsung.permission.SSENSOR` — a signature permission, not grantable to us.
