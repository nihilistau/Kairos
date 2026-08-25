---
type: reference
title: "HOME ASSISTANT — the house as a framework, and the sleep socket it fills"
status: LIVE (2026-08-26)
---

# HOME ASSISTANT

A separate framework that plugs into kairos through the doors that already exist. It is not
part of the telemetry package and it must not become part of it: the watch agent is ours and
posts to us, Home Assistant is somebody else's server that we ask, and those two things fail
completely differently.

## Why it exists

One sentence: **Home Assistant knows whether he is asleep, and nothing we can reach does.**

[`TELEMETRY.md`](TELEMETRY.md) has the finding in full. Enumerating his Galaxy Watch4 rather
than trusting a spec sheet, every sleep-capable sensor on it — `SContext`, `movement`,
`wrist_down`, and with them ECG, BIA and the thermistor — is `perm:
com.samsung.permission.SSENSOR`, a signature permission. Not grantable, not `adb`-able.

What *does* produce a sleep confidence is **Google's Sleep API**, a classifier inside Play
Services that emits a calibrated 0–100 about every ten minutes. It is not a sensor, so no
amount of `SensorManager` reaches it. Home Assistant's companion app already computes it and
calls it **Sleep Confidence**.

`harness/telemetry/store.py` has had a `sleep_confidence` kind and a reader waiting behind it
since the day that was discovered. This framework is the piece that carries one to the other.

## The shape

```
  Home Assistant  --REST-->  client.py     token from var/, never a profile
                                 |
                             bridge.py     suffix table -> kairos kinds
                                 |
                    telemetry.ingest.record()      <- THE EXISTING DOOR (anon gate lives here)
                                 |
                             the store
                                 |
                          body.read()  ->  she is told, or is not
```

| File | Does |
|---|---|
| `harness/homeassistant/client.py` | REST. Four endpoints, never raises, token from `var/`. |
| `harness/homeassistant/bridge.py` | The suffix table and the poll. Writes only via `ingest.record`. |
| `harness/homeassistant/house.py` | What she may *say* about the house. Empty by default. |
| `harness/homeassistant/stack/` | The containers, and why they are containers. |
| `harness_tests/g_homeassistant.py` | 36 checks. |

## The five rules it inherits

1. **It is not a second door.** Everything crosses through `telemetry.ingest.record()`, the
   existing writer, because that is where the **anon gate** sits. A framework that wrote to
   the store directly would be a second set of rules within a month, and the anon gate is
   the one rule that must never be second. Off the record, a sleep confidence is **held, not
   queued** — and held is not marked as handled, so the value that lands when he comes back
   on the record is the *current* one.
2. **Off until configured.** No token means every entry point returns empty and **no socket
   is opened at all** — the gate asserts that by counting connections, because "off" must
   mean silent rather than "fails politely".
3. **It never raises.** Home Assistant is a container that restarts on upgrade. That may not
   cost him a turn, so every call answers with a value and a reason.
4. **The credential is not configuration.** Everything in `profiles/` is committed and
   everything committed is exported, so a long-lived token in a TOML file is a token in the
   public repository a fortnight later. It lives in `var/ha_token` or `SP_HA_TOKEN`, and the
   gate asserts the client cannot even *import* the config system.
5. **Silence is an answer.** The house watch list ships empty. She is told nothing about his
   house until he names entities, because which lights matter is not something this file can
   know and a default that guessed would be wrong in his house specifically.

## What crosses, and what deliberately does not

Matched by **suffix**, never by whole entity id — the companion app names entities after the
device (`sensor.sm_s908e_sleep_confidence`), so a hard-coded id would silently stop working
the day he changed handsets. Silently is the part that matters: a missing row looks exactly
like a man who is awake.

| Suffix | Becomes | Why it is worth taking |
|---|---|---|
| `_sleep_confidence` | `sleep_confidence` | The whole reason. Nothing local can produce it. |
| `_detected_activity`, `_activity` | `activity` | Google's Activity Recognition — *trained*, where our movement number is thresholded. |

**Battery, steps and charging are deliberately NOT taken**, though Home Assistant has them.
Our own agent already posts them, and two spellings of one reading leaves the seam picking
between them — the two-copies bug this codebase keeps paying for.

`activity` is kept under its own name rather than mapped onto `motion`, because phone-sourced
`motion` is deliberately *not* a claim about him (a phone on a desk is not a man sitting
still) and reusing the name would smuggle a phone's opinion into a body fact. In the sleep
estimate it is treated asymmetrically and on purpose: **locomotion from it is near-certain**
— a man Google believes is walking is not asleep, whatever the wrist and the screen say —
while stillness from it is only weak corroboration, because a still phone is still a phone.

### A foreign clock, bounded

Sleep confidence refreshes every ten minutes. Stamping it on arrival would date a
nine-minute-old reading to now, and every freshness decision downstream would then be made
against the wrong number — the same defect as `latest()` returning yesterday's heart rate,
arriving by a different road.

So `ingest.record()` gained `measured_at`, and it is **bounded on both sides** so it cannot
become a hole in the one-clock rule: not more than two hours back, not more than two minutes
forward, and nothing arriving over `/v1/telemetry/ingest` can pass it — only in-process
callers. Outside the window the row still lands, stamped on arrival, with `clock_ignored`
returned to the caller. A watch that has been in a drawer for a week still does not get to
say when it thinks it is.

### Only on change

The poll runs every 60 s for a signal that changes every 600 s. Not to catch it sooner than
it changes — **to bound how badly it can be misdated**. Readings are written only when
Home Assistant's `last_updated` moves, so one measurement stays one row.

## Setting it up

### 1. The stack

Containers, not the Home Assistant OS appliance — the appliance is a virtual machine, which
is what this migration was getting away from: it needs a hypervisor, a console to recover,
and it fails in ways you cannot see from the host.

It runs under **Docker Engine inside a WSL2 distro**, and *not* Docker Desktop. Measured,
not assumed:

- Under Docker Desktop, `network_mode: host` means the host of the *Docker* VM. Home
  Assistant came up, listened on 8123 inside that namespace, and Windows could not reach it
  — let alone the LAN.
- A WSL2 distro with `networkingMode=mirrored` holds the Windows host's own LAN address
  (`10.0.0.150/24` on `eth0`, pinging the router). A container on host networking there is
  genuinely on the LAN.

That difference is the whole thing, because **every discovery protocol Home Assistant relies
on is multicast** — mDNS for ESPHome and Chromecast, SSDP for Hue and Sonos — and multicast
crosses neither a bridge network nor a NAT. Without it nothing is ever found and every device
is added by hand, by IP, forever.

Both halves are required: `networkingMode=mirrored` in `%USERPROFILE%\.wslconfig` **and**
`network_mode: host` in the compose file. Either alone leaves the LAN invisible.

```bash
wsl -d Ubuntu-24.04 -u root -- bash -c "cd /opt/homeassistant && docker compose up -d"
```

**The distro must be pinned open.** WSL2 tears a distro down seconds after the last attached
process exits — systemd being PID 1 is not enough. Measured: `dockerd`'s PID changed on every
`wsl.exe` call, so Home Assistant was cold-started and `SIGTERM`ed within seconds, over and
over. In its log that reads as a clean `exit code 0` and looks nothing like a crash. A logon
entry runs `/usr/local/bin/ha-keepalive`, which holds one process open forever and brings the
stack up.

### 2. The token

In Home Assistant: your profile → **Security** → **Long-lived access tokens** → *Create*.

```bash
printf '%s' 'PASTE_THE_TOKEN' > var/ha_token
```

`var/` is not committed and not exported. Do not put it in a profile.

### 3. Watch it work

```bash
curl -s localhost:8800/v1/house/now | python -m json.tool
```

`entities` is the useful part: it lists what the bridge *would* take and what each becomes,
so "why is she not being told I am asleep" has an answer that is not "read the source".

## What this framework will not do

**It cannot turn anything on.** Nothing here calls a service, and the gate asserts that by
grepping the whole package for `/api/services`. Giving a companion the light switches is a
genuinely different product with genuinely different failure modes, and it is not somewhere
to arrive at by accident while wiring up a sleep sensor. When it is wanted it gets its own
design, its own gate and its own row in [`OFF-BY-DEFAULT.md`](OFF-BY-DEFAULT.md).

**It does not enumerate the house to her.** Home Assistant will happily list several hundred
entities; handing her that is the *she never sees the feed* rule from telemetry with the
labels changed. `house.WATCH` is a committed list, one entity per line, and the point of it
is that a person decided each one was worth her attention.

## ESPHome

Runs as its own container because there is no Supervisor without the OS image, which is the
one real cost of not using the appliance. It is the same software, officially supported this
way, at `:6052`, and it needs host networking for exactly the same reason Home Assistant
does — it discovers and OTA-flashes nodes over mDNS.

## Migrating from an existing instance

Restore rather than re-pair. On the old instance: **Settings → System → Backups → Create**,
download the `.tar`, then in the new instance's onboarding choose **Restore from backup**.
That carries every device, entity, area and automation across.

USB radios (Zigbee, Z-Wave) need `usbipd-win` to attach the dongle to the WSL distro before
the container can see it; that is a separate step and is not automatic.
