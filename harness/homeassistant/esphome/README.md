---
type: reference
title: "ESPHome nodes — the radar sensors, in version control at last"
status: LIVE (2026-08-27)
---

# ESPHome nodes

**These are a MIRROR. The live copies are in the `esphome-config` Docker volume, and that
is what the ESPHome container compiles.** Edit there, copy back here, commit — the same
one-way relationship `console/room/` has with `ui/`.

## Why they are here at all

They were not, until 2026-08-27. `stack/docker-compose.yml` opens by saying containers
"start with the machine, log where everything else logs, and are **recreated from this
file**" — and the node YAMLs, which are the actual source for three microcontrollers,
existed only inside a named volume. A `docker volume rm` and they were gone, with no
history of what any sensor had ever been told.

Nothing sensitive is here. `secrets.yaml` stays in the volume; the packages reference
`!secret wifi_ssid` / `!secret wifi_password` and never hold a value.

## The nodes

| file | device | hardware |
|---|---|---|
| `mmwave-zone-1.yaml` | `bedroom-ld2410` | **no hardware behind it.** The LD2410 was removed 2026-08-27 and an LD2450 wired to the same ESP32-C3. Kept so an LD2410 can be flashed again. |
| `mmwave-zone-2.yaml` | `bedroom-ld2450` | LD2450, bedroom |
| `mmwave-zone-3.yaml` | `bedroom-ld2450-2` | LD2450 on the C3 that used to carry the LD2410 |

Everything real lives in `packages/` — a node file is substitutions and one `!include`.

## Two things that cost time, so they are written down

**A new node's first OTA has nowhere to go.** OTA finds a device by its mDNS name, and the
name comes from `device_id` — so re-flashing an existing board under a NEW name means
looking for a host that does not exist yet. Set `wifi: use_address: <current ip>` for the
first upload and **delete it after**: left in, it pins the node to an address DHCP is free
to reassign.

**Silence is not one fault, and the log says which.** When `mmwave-zone-3` came up reading
nothing, the tell was in the device log:

```
[W][ld2450:774]: Max command length exceeded; ignoring
   Firmware version: 0.00.00000000     MAC address: unknown
```

Bytes were arriving and none of them framed — at 256000 **and** at 115200. A powered,
silent module sends *nothing* (an idle UART line sits high), so garbage at every rate is a
floating RX, not a dead module and not a baud mismatch. It was a cold solder joint on the
module's TX. That one line separates four hypotheses at once; two reflashes testing a pin
swap separated one, and were done first.

`ld2450_baud` is a per-node substitution (default 256000, the factory rate) so a module
that has been reconfigured can be met where it is — without editing the shared package and
taking the working unit down with it.
