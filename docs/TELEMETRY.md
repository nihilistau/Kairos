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
| **device state** | screen, charging, battery level and temperature | **the same agent** (broadcasts) |
| **phone sensors** | steps, motion, light, barometric pressure | **the same agent** |
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
| `harness_tests/g_telemetry.py` | 113 checks. |

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

## Sleep has three possible sources, and they are not the same claim

His question — *"there is a sleeping sensor... it returns a pretty accurate percentage
chance of being asleep"* — turned out to have a precise answer, and it is not a sensor.

| Rank | Source | Kind | State |
|---|---|---|---|
| 1 | The watch's own staging | `sleep_stage` | **unavailable** — see below |
| 2 | A classifier's confidence | `sleep_confidence` | **socket built, nothing fills it** |
| 3 | Ours | `sleep_confidence` + `sleep_terms` | **live**, and labelled `inferred` |

**The watch cannot tell us.** Enumerating the Watch4's own sensor list rather than trusting
a spec sheet: every sleep-capable sensor on it — `SContext`, `movement`, `wrist_down`, and
with them ECG, BIA and the thermistor — is marked `perm: com.samsung.permission.SSENSOR`. A
signature permission, held only by apps Samsung signed. Not grantable, not `adb`-able.

**Home Assistant's "Sleep Confidence" is Google's Sleep API.** Not a sensor at all: a
Play Services classifier on the *phone*, updating about every ten minutes, Play-Store
flavour only. It is genuinely good and it is the right thing to want. Two ways it can reach
us — the HA framework when that lands, or an agent linked against `play-services-location`
— and both write the same `sleep_confidence` row, which is why the kind exists now with a
reader already behind it. **Linking GMS costs the gradle-free build**: androidx, a
dependency chain, and an APK that goes from 16 KB to megabytes. That is a decision, not an
oversight, and it is his to make.

### So we estimate it, and the estimate shows its working

A number invented in `body.py` and printed with a `%` after it is exactly the failure this
module exists to prevent — a confident guess wearing a measurement's clothes. So
`sleep_estimate()` returns **the terms that produced it** alongside the number, and the
panel and the seam both render them:

> 78% — *phone untouched for 94 min; his wrist still for 51 min; heart at his resting band
> (57)*

If she could only say "78%" she would be bluffing. With the terms, the number is a summary
of things that were actually measured and he can contradict any one of them.

Four rules hold it honest:

- **`None` is not `0`.** Too little evidence returns `None`, never a low confidence.
  "We have no idea" and "he is awake" are different claims, and an empty store supports
  only the first. Returning `0.0` would have her quietly certain he was up all night, every
  night the watch sat on its charger.
- **Between the bands she says nothing.** Above 70 she may say it; below 30 he is awake;
  in between `asleep` is left **unset** rather than set to `False`, and every reader
  downstream treats a missing key as *do not claim it*.
- **The wrist and the screen are vetoes, not weights.** A man who just looked at his watch
  is awake, and no amount of accumulated stillness gets to outvote him.
- **No time-of-day prior.** Every sleep model wants one; for this user it would be actively
  harmful. He is routinely working at 03:00, so "it is 3am, therefore asleep" would make her
  confidently wrong at exactly the hour she is most likely to be talking to him.

### He looked at his watch

`wrist_tilt_gesture` — sensor type 26, and one of the few on this watch that is **not**
permission-locked. It fires when he raises his arm to check the time, and it is the only
free awake-signal that comes from *his body* rather than from a device he might have put
down: a phone screen can be lit by a notification, a wrist tilt cannot happen without him.

The constant is spelled out as `26` in the agent because `Sensor.TYPE_WRIST_TILT_GESTURE`
is hidden from the public `android.jar` — it exists on the device and compiling against the
name fails. The number was read off this watch's own `dumpsys`, not a doc page.

### `motion` is derived, because nothing posts it

The `motion` state kind has **never had a single row** — 0 in 6,820 live samples. The agent
reduces to `gyro_rms` per window and posts that; the state was something the seam invented
for itself and then depended on, so `moving`, `motion_for_s` and the stillness term were all
reading a key that is never there. `still_run()` derives it from the RMS rows, still prefers
a classified `motion` state if any source ever posts one, and both it and `movement_word`
share a single `MOVE_RMS` threshold.

### The wrist alone cannot conclude sleep

A still wrist and a resting heart rate describe a sleeping man and a man reading in a chair
equally well. The phone is what tells them apart, so watch-only data sits in the unsure band
and she says nothing. That is not a gap — it is the honest reading, and the gate asserts it.

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

## One agent, two bodies

The **same APK** runs on the watch and on the phone. It detects which it is in
(`PackageManager.FEATURE_WATCH`), reports `source: "watch"` or `"phone"`, and registers
whatever sensors exist — a phone has no heart rate and no off-body detector, a watch has no
ambient light worth reading inside a sleeve, and absent sensors are simply skipped.

A separate phone app would have been a second implementation of *read, reduce, batch,
retry*, and this codebase knows what two implementations of one thing cost.

### A phone on a desk is not a man sitting still

Both devices post `motion`, `gyro_rms` and `steps` under the **same kind names**, and they
are not the same claim. A still watch on his wrist means *he* is still. A still phone means
the phone is on a table — perfectly compatible with him being out for a run wearing the
watch. Caught in testing before it ever ran live: the watch said still, the phone was moved,
and she said *"he is moving a lot."*

So the claims are **sourced**. Body facts — asleep, moving, worked up, heart — come from the
wrist only (`BODY_SOURCE`). The phone speaks about the phone and about the room, which are
real signals with a different subject.

### The phone's screen is the cheapest truth in the building

A screen that came on two minutes ago is a man who is **awake**, and it beats any amount of
stillness inferred from an accelerometer. It is computed before the sleep rules so it can
**veto** them — the crude fallback ("still, and his heart is at his resting band") is exactly
what a man reading in bed would break.

`ACTION_SCREEN_ON/OFF` are transitions and not sticky, so the agent pushes the **current**
state at startup. Without that the veto was silently unavailable after every restart until
he next toggled the screen — found by watching for a `screen` row that never came.

## The agent

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

- **Sleep staging from the watch.** Not "not built" — **not available**. Verified by
  enumerating the device: every sleep-capable sensor is behind
  `com.samsung.permission.SSENSOR`. The `sleep_stage` kind and its reader stay, because a
  future watch or a rooted one would fill them.
- **ECG, BIA, skin temperature.** Same wall, same permission.
- **Google's Sleep API.** The socket (`sleep_confidence`) is built and read; nothing writes
  it. Filling it means either the Home Assistant framework or linking `play-services-
  location` into the agent, and the second one ends the gradle-free 16 KB build.
- **The watch's own screen, light and pressure.** It posts all three, and the seam reads
  them from the phone only — a watch spends its life inside a sleeve, so its light reading
  describes his cuff. The rows are kept; nothing reads them yet.
