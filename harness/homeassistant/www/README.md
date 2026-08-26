# Lovelace cards that ship with this framework

Copy into Home Assistant's `config/www/`, then register each as a **module** resource
(Settings → Dashboards → ⋮ → Resources, or `lovelace/resources/create` over the websocket):

```
/local/radar-trails-card.js
```

### Two things that will waste an afternoon

**Version the URL when you change the file.** A Lovelace resource is a plain script URL and
the browser caches it like any other, so editing the file on disk changes nothing for a
client that already has it. Append `?v=<timestamp>` and update the resource; HACS does the
same with `?hacstag=`.

**A newly registered resource is not fetched by a page that is already open.** The frontend
loads its resource list at boot, so the card will be missing — and therefore blank — until
the browser is reloaded. That is the first thing to try, before reading any code.

## `radar-tracker-card` — the LD2450

Live x/y tracking with a **five-minute** tail, and a **History** tab that browses past
visits. Sensor at the bottom facing up the page.

Select a visit and its whole path is drawn start to end — the line runs dim at the start and
bright at the end, so direction of travel is readable without an arrowhead on every segment.
The table gives, per visit: when it started, how long it lasted, metres walked, closest
approach, top speed, and how many points it is built from.

**An "event" is derived, not recorded.** Nothing writes "somebody visited"; a visit is a
contiguous run of non-zero positions, and `EVENT_GAP_MS` decides where one ends. Worth
knowing rather than trusting: someone who stands still long enough for the radar to drop its
lock appears as two visits, because that is genuinely what the sensor saw.

**History is affordable because absence is free.** The recorder stores state *changes*, and
an empty room parks x and y at 0 — measured here, three hours held **thirteen** points with a
single 2.7-hour gap over the quiet stretch. It is fetched **on demand over the websocket
API**, never on load: the REST history endpoint took **21 seconds** for three entities over
three hours against this database.

```yaml
type: custom:radar-tracker-card
title: LD2450 · tracking
room_width_mm: 4500
room_depth_mm: 4200
# prefix: sensor.bedroom_ld2450_bedroom_ld2450_target_
```

## `radar-presence-card` — the LD2410

This sensor reports a **distance and no bearing**, so it never gets a dot. Each reading is
drawn as a **band at that radius** across the whole fan — "somebody is about this far away,
somewhere in front" — which is the honest shape of what the hardware knows.

Moving and still get separate bands, because telling them apart is the entire reason to have
an LD2410 in a bedroom: a tracker loses somebody who lies still, and this one does not.
**Return strength is drawn as opacity** rather than a number in a column — a weak return at
three metres and a strong one at three metres mean different things, and the first is
probably a curtain.

It has a **History** tab too, and it cannot be a map. The tracker draws a path because it
knows where somebody was; this sensor never does, so a visit is drawn as a **trace in time**:
the visit runs left to right as its own duration, banded by state (moving / still / merely
occupied) with return strength as the height. Same question, the only honest shape for this
answer. Visits are derived from `occupancy` — 29 transitions in twenty-four hours here.

**Watch `still_energy` if the database gets large.** It reports the 3–6% noise floor and
every flicker is a state change the recorder keeps: **7,654 rows in a day**, against 29 for
occupancy. It is fetched anyway, because "how strong was the return from somebody lying
there" is the reason to own an LD2410 — but that is where the rows are.

```yaml
type: custom:radar-presence-card
title: LD2410 · presence
max_mm: 6000
```

### Two things that will waste an afternoon

**Version the URL when you change the file.** A Lovelace resource is a plain script URL and
the browser caches it like any other, so editing the file on disk changes nothing for a
client that already has it. Append `?v=<timestamp>` and update the resource; HACS does the
same with `?hacstag=`.

**A newly registered resource is not fetched by a page that is already open.** The frontend
loads its resource list at boot, so the card will be missing — and therefore blank — until
the browser is reloaded. That is the first thing to try, before reading any code.

## `radar-trails-card`

Two mmWave nodes on one plan: sensor at the bottom facing up the page, targets plotted in
its own frame, three minutes of fading trail per target in its own colour.

It distinguishes the two kinds of sensor rather than flattening them:

- An **LD2450** reports a signed X and a Y per target. That is a position, so it is a dot.
- An **LD2410** reports a **distance and no bearing**. It is drawn as an **arc at that
  radius** — "somebody is this far away, somewhere along here" — because a dot straight
  ahead would invent a direction the hardware never measured.

Trails are held in the card and lost on reload, deliberately: a position every 250 ms is
14,000 rows an hour, and the recorder should not keep them so that a canvas can draw a comet
tail. The history graphs are the record; this is a visualisation.

```yaml
type: custom:radar-trails-card
title: Bedroom · both sensors
room_width_mm: 4500
room_depth_mm: 4200
show_ld2410: true
# defaults assume the entity names ESPHome produces; override if yours differ
# ld2450_prefix: sensor.bedroom_ld2450_bedroom_ld2450_target_
# ld2410_distance: sensor.bedroom_ld2410_bedroom_ld2410_detection_distance
# ld2410_occupancy: binary_sensor.bedroom_ld2410_bedroom_ld2410_occupancy
```

`image:` is deliberately unset. Point it at a **room-scale** plan if you have one — a
whole-dwelling floorplan behind a single room's radar misplaces every target.

### Why this card draws on state change rather than on a timer

Home Assistant calls `set hass` on every state change, which is exactly when the picture is
stale, and unlike an interval it cannot be throttled away. Measured while debugging this
card: **in a background tab Chrome froze a 400 ms interval completely**, so the canvas kept
whatever it drew on its first frame and looked broken. The interval that remains exists only
to age trails out, since a trail must fade even when nothing is moving and therefore no state
change arrives.

### And it was invisible, not blank

The first version drew correctly from the first frame and could not be seen: range rings at
**7% white** and a room outline at 16% on a near-black card, in a fixed 900x800 buffer
stretched down to 462px — so every hairline was scaled by 1.95 and every 13px label rendered
at about six. Reading the canvas back settled it: all 720 sampled pixels had non-zero alpha
while the screen showed nothing.

The general lesson is the sizing, not the colours: **size the backing store to the element
times `devicePixelRatio`** so one canvas unit is one device pixel. A fixed buffer stretched
to whatever width a column happens to be turns a diagram into a smear.
