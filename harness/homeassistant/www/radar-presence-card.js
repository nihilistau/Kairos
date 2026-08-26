/* radar-presence-card — the LD2410, drawn as what it actually is.
 *
 * SPLIT FROM THE TRACKER CARD (2026-08-26). Sharing one drawing with the LD2450 flattened
 * the difference between the two sensors, and the difference is the reason to own both:
 *
 *   LD2450  reports a POSITION. It belongs on a map, and it loses a person who lies still.
 *   LD2410  reports a DISTANCE AND NO BEARING, split into MOVING and STILL, each with a
 *           return strength. It cannot be put on a map without inventing a direction, and
 *           it keeps answering about the person the tracker just lost.
 *
 * So this card never draws a dot. It draws a BAND at the reported radius across the whole
 * fan -- "somebody is about this far away, somewhere in front" -- which is the honest shape
 * of what the hardware knows. Two bands, because moving and still are separate readings
 * from the same device and the whole value of an LD2410 in a bedroom is telling them apart.
 *
 * A HISTORY TAB, AND IT CANNOT BE A MAP (2026-08-26, his ask). The tracker's history
 * draws a path through the room because the LD2450 knows where somebody was. This sensor
 * never does, so its visits are drawn as a TRACE IN TIME instead: the length of the visit
 * along the page, banded by what it was -- moving, or still, or merely occupied -- with the
 * return strength as the height. Same question, the only honest shape for this answer.
 *
 * A VISIT IS DERIVED FROM `occupancy`, not recorded anywhere. Measured on this instance,
 * twenty-four hours held 29 occupancy transitions -- cheap to fetch and easy to segment.
 *
 * ONE SERIES IS NOT CHEAP AND IT IS WORTH KNOWING: `still_energy` wrote 7,654 rows in the
 * same twenty-four hours, because it reports the 3-6% noise floor and every flicker of it is
 * a state change the recorder keeps. It is fetched anyway, since "how strong was the return
 * from somebody lying there" is the whole reason to own an LD2410 -- but if the database
 * ever needs trimming, that sensor is where the rows are.
 *
 * STRENGTH IS DRAWN AS OPACITY, not as a number bolted to the side. A weak return at three
 * metres and a strong one at three metres mean different things -- the first is probably a
 * curtain -- and putting the confidence into how solid the band looks says that without
 * asking anyone to read a second column.
 */

const TICK = 700;
const MOVING = "#ffd66b", STILL = "#5df9c4", HERE = "#9aa4b2";

const fmtClock = (ms) => new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const fmtDur = (ms) => {
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m}m ${String(s % 60).padStart(2, "0")}s`
                : `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
};

class RadarPresenceCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null; this._cfg = null; this._timer = null; this._pending = false;
    this._tab = 'live'; this._events = []; this._sel = -1;
    this._hours = 6; this._busy = false; this._note = '';
  }

  setConfig(config) {
    this._cfg = {
      title: config.title || "LD2410 · presence",
      max_mm: Number(config.max_mm) || 6000,
      prefix: config.prefix || "sensor.bedroom_ld2410_bedroom_ld2410_",
      bprefix: config.bprefix || "binary_sensor.bedroom_ld2410_bedroom_ld2410_",
    };
    this._render();
  }

  set hass(h) {
    this._hass = h;
    if (!this._pending) {
      this._pending = true;
      requestAnimationFrame(() => { this._pending = false; this._paint(); });
    }
  }

  getCardSize() { return this._tab === "history" ? 10 : 6; }

  // ── history ────────────────────────────────────────────────────────────────────
  async _loadHistory() {
    if (!this._hass || this._busy) return;
    this._busy = true; this._note = "asking the recorder…"; this._paint();
    const end = new Date(), start = new Date(Date.now() - this._hours * 3600e3);
    const P = this._cfg.prefix, B = this._cfg.bprefix;
    const ids = [B + "occupancy", B + "motion", B + "still_presence",
                 P + "moving_energy", P + "still_energy",
                 P + "moving_distance", P + "still_distance"];
    try {
      const res = await this._hass.callWS({
        type: "history/history_during_period",
        start_time: start.toISOString(), end_time: end.toISOString(),
        entity_ids: ids, minimal_response: true, no_attributes: true,
        significant_changes_only: false,
      });
      this._events = this._segment(res, start.getTime(), Date.now());
      this._note = this._events.length
        ? `${this._events.length} visit${this._events.length === 1 ? "" : "s"} in the last ${this._hours}h`
        : `nobody detected in the last ${this._hours}h`;
      this._sel = this._events.length ? 0 : -1;
    } catch (e) {
      this._events = []; this._sel = -1;
      this._note = "the recorder said no: " + ((e && (e.message || e.code)) || "unknown");
    }
    this._busy = false; this._paint();
  }

  /* Occupancy transitions become visits; everything else is sampled along them.
   *
   * LINEAR, DELIBERATELY. The tracker card's first attempt looked a value up per point by
   * scanning the whole series, which is O(n*n) and froze the tab outright once a series got
   * long. `still_energy` here is 7,600 points a day, so the same mistake would be worse.
   * Every series is already sorted; one forward index each is enough. */
  _segment(res, since, until) {
    const at = (r) => {
      const v = r.lu ?? r.last_updated ?? r.last_changed ?? r.lc;
      if (typeof v === "number") return v * 1000;
      const p = Date.parse(v); return Number.isFinite(p) ? p : null;
    };
    const st = (r) => String(r.s ?? r.state ?? "");
    const P = this._cfg.prefix, B = this._cfg.bprefix;
    const occ = (res[B + "occupancy"] || [])
      .map(r => ({ t: at(r), v: st(r) })).filter(r => r.t !== null).sort((a, b) => a.t - b.t);
    if (!occ.length) return [];

    // contiguous runs of "on"
    const runs = [];
    let open = null;
    for (const r of occ) {
      if (r.v === "on" && open === null) open = r.t;
      else if (r.v !== "on" && open !== null) { runs.push([open, r.t]); open = null; }
    }
    if (open !== null) runs.push([open, until]);

    const series = (id) => (res[id] || [])
      .map(r => ({ t: at(r), v: st(r) })).filter(r => r.t !== null).sort((a, b) => a.t - b.t);
    const mo = series(B + "motion"), stl = series(B + "still_presence");
    const me = series(P + "moving_energy"), se = series(P + "still_energy");
    const md = series(P + "moving_distance"), sd = series(P + "still_distance");

    const out = [];
    // ONE walking index per series across ALL runs, since runs are in time order too.
    const advance = (arr, k, t, cur) => {
      while (k.i < arr.length && arr[k.i].t <= t) { cur.v = arr[k.i].v; k.i++; }
      return cur.v;
    };
    const K = { mo: { i: 0 }, stl: { i: 0 }, me: { i: 0 }, se: { i: 0 }, md: { i: 0 }, sd: { i: 0 } };
    const C = { mo: { v: "off" }, stl: { v: "off" }, me: { v: "0" }, se: { v: "0" },
                md: { v: "0" }, sd: { v: "0" } };

    for (const [a, b] of runs) {
      if (b < since) continue;
      // sample the run on a grid; 120 steps is plenty for a strip a few hundred px wide
      const steps = Math.max(8, Math.min(160, Math.round((b - a) / 1000)));
      const pts = [];
      for (let k = 0; k <= steps; k++) {
        const t = a + ((b - a) * k) / steps;
        const moving = advance(mo, K.mo, t, C.mo) === "on";
        const still = advance(stl, K.stl, t, C.stl) === "on";
        const mE = parseFloat(advance(me, K.me, t, C.me)) || 0;
        const sE = parseFloat(advance(se, K.se, t, C.se)) || 0;
        const mD = parseFloat(advance(md, K.md, t, C.md)) || 0;
        const sD = parseFloat(advance(sd, K.sd, t, C.sd)) || 0;
        pts.push({ t, moving, still, mE, sE, mD, sD });
      }
      const ev = { start: a, end: b, dur: b - a, pts };
      ev.moving_ms = 0; ev.still_ms = 0;
      const step = (b - a) / steps;
      let peakM = 0, peakS = 0, near = Infinity, far = 0;
      for (const p of pts) {
        if (p.moving) ev.moving_ms += step;
        else if (p.still) ev.still_ms += step;
        if (p.mE > peakM) peakM = p.mE;
        if (p.sE > peakS) peakS = p.sE;
        const d = p.moving ? p.mD : p.still ? p.sD : 0;
        if (d > 0) { if (d < near) near = d; if (d > far) far = d; }
      }
      ev.peak_moving = peakM; ev.peak_still = peakS;
      ev.near_cm = near === Infinity ? null : near;
      ev.far_cm = far || null;
      out.push(ev);
    }
    out.sort((x, y) => y.start - x.start);
    return out.slice(0, 60);
  }
  disconnectedCallback() { if (this._timer) clearInterval(this._timer); }

  _n(id) {
    const s = this._hass && this._hass.states[id];
    if (!s || s.state === "unknown" || s.state === "unavailable") return null;
    const v = parseFloat(s.state); return Number.isFinite(v) ? v : null;
  }
  _on(id) {
    const s = this._hass && this._hass.states[id];
    return s ? s.state === "on" : null;
  }

  _render() {
    if (!this.shadowRoot || !this._cfg) return;
    this.shadowRoot.innerHTML = `
      <ha-card>
        <style>
          ha-card { padding: 14px; }
          h3 { margin: 0 0 4px; font-size: 1.05rem; font-weight: 600; }
          .sub { margin: 0 0 10px; font-size: 11px; opacity: .65; line-height: 1.5; }
          canvas { width: 100%; display: block; border-radius: 10px; background: #05070d; }
          .rows { margin-top: 10px; font-size: 12px; }
          .r { display: grid; grid-template-columns: 10px 1fr auto auto;
               gap: 8px; align-items: baseline; padding: 4px 0;
               border-top: 1px solid rgba(255,255,255,.06); }
          .sw { width: 10px; height: 10px; border-radius: 2px; }
          .num { font-variant-numeric: tabular-nums; opacity: .9; }
          .off { opacity: .4; }
          .tabs { display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap; }
          button {
            background: rgba(255,255,255,.06); color: inherit; font: inherit;
            border: 1px solid rgba(255,255,255,.12); border-radius: 999px;
            padding: 4px 12px; font-size: 12px; cursor: pointer;
          }
          button.on { background: rgba(93,249,196,.18); border-color: rgba(93,249,196,.5); }
          button:disabled { opacity: .5; cursor: default; }
          .spacer { flex: 1; }
          .note { font-size: 11px; opacity: .7; margin: 8px 0 0; min-height: 14px; }
          table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 11px; }
          th { text-align: left; font-weight: 500; opacity: .6; padding: 3px 4px; }
          td { padding: 4px; border-top: 1px solid rgba(255,255,255,.06); }
          tr.row { cursor: pointer; }
          tr.row:hover td { background: rgba(255,255,255,.04); }
          tr.sel td { background: rgba(93,249,196,.12); }
          .num { text-align: right; font-variant-numeric: tabular-nums; }
        </style>
        <h3>${this._cfg.title}</h3>
        <p class="sub">
          No bearing — this sensor knows how far, not which way. Each band is a distance,
          drawn across the whole fan; how solid it looks is the return strength.
        </p>
        <div class="tabs" id="tabs"></div>
        <canvas id="c"></canvas>
        <div class="rows" id="rows"></div>
        <p class="note" id="note"></p>
      </ha-card>`;
    this._wire();
    this._paint();
    if (this._timer) clearInterval(this._timer);
    this._timer = setInterval(() => this._paint(), TICK);
  }

  _wire() {
    const t = this.shadowRoot.getElementById("tabs");
    if (!t) return;
    t.innerHTML = "";
    const mk = (label, on, fn, dis) => {
      const b = document.createElement("button");
      b.textContent = label; if (on) b.className = "on"; if (dis) b.disabled = true;
      b.addEventListener("click", fn); t.appendChild(b);
    };
    mk("Live", this._tab === "live", () => { this._tab = "live"; this._wire(); this._paint(); });
    mk("History", this._tab === "history", () => {
      this._tab = "history"; this._wire(); this._paint();
      if (!this._events.length) this._loadHistory();
    });
    if (this._tab === "history") {
      const sp = document.createElement("span"); sp.className = "spacer"; t.appendChild(sp);
      for (const h of [1, 6, 24]) {
        mk(`${h}h`, this._hours === h, () => {
          this._hours = h; this._events = []; this._sel = -1; this._wire(); this._loadHistory();
        }, this._busy);
      }
    }
  }

  _paint() {
    if (this._tab === "history") return this._paintHistory();
    const cv = this.shadowRoot && this.shadowRoot.querySelector("#c");
    if (!cv || !this._cfg) return;
    const dpr = window.devicePixelRatio || 1;
    const W = cv.clientWidth || 440, H = Math.round(W * 0.58);
    cv.style.height = H + "px";
    if (cv.width !== Math.round(W * dpr)) cv.width = Math.round(W * dpr);
    if (cv.height !== Math.round(H * dpr)) cv.height = Math.round(H * dpr);
    const g = cv.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H); g.fillStyle = "#05070d"; g.fillRect(0, 0, W, H);

    const pad = 26, ox = W / 2, oy = H - pad;
    const s = Math.min((W / 2 - pad) / this._cfg.max_mm, (H - pad * 2) / this._cfg.max_mm);

    // range rings, labelled
    g.strokeStyle = "rgba(125,240,255,.20)"; g.fillStyle = "rgba(160,225,245,.7)";
    g.lineWidth = 1; g.font = "11px ui-monospace, monospace";
    for (let m = 1; m * 1000 <= this._cfg.max_mm; m++) {
      g.beginPath(); g.arc(ox, oy, m * 1000 * s, Math.PI, 2 * Math.PI); g.stroke();
      g.fillText(`${m} m`, ox + 6, oy - m * 1000 * s - 4);
    }

    const P = this._cfg.prefix, B = this._cfg.bprefix;
    const band = (mm, energy, colour, on) => {
      if (mm === null || mm <= 0 || !on) return;
      const r = mm * s;
      const a = Math.max(.18, Math.min(1, (energy === null ? 40 : energy) / 100));
      g.strokeStyle = colour; g.globalAlpha = a; g.lineWidth = 7;
      g.beginPath(); g.arc(ox, oy, r, Math.PI * 1.06, Math.PI * 1.94); g.stroke();
      g.globalAlpha = 1;
    };
    // firmware reports these in CENTIMETRES
    band((this._n(P + "still_distance") || 0) * 10, this._n(P + "still_energy"),
         "#5df9c4", this._on(B + "still_presence"));
    band((this._n(P + "moving_distance") || 0) * 10, this._n(P + "moving_energy"),
         "#ffd66b", this._on(B + "motion"));

    g.fillStyle = "#fff";
    g.beginPath(); g.arc(ox, oy, 5, 0, Math.PI * 2); g.fill();
    g.fillStyle = "rgba(255,255,255,.7)";
    g.fillText("LD2410", ox + 12, oy - 7);

    if (!this._hass) {
      g.fillStyle = "rgba(200,215,235,.8)"; g.font = "13px ui-monospace, monospace";
      g.fillText("waiting for Home Assistant…", pad, pad + 14);
    } else if (!this._on(B + "occupancy")) {
      g.fillStyle = "rgba(200,215,235,.8)"; g.font = "13px ui-monospace, monospace";
      g.fillText("nobody detected", pad, pad + 14);
    }

    const rows = this.shadowRoot.getElementById("rows");
    if (rows) {
      const line = (sw, label, on, dist, en) => `
        <div class="r ${on ? "" : "off"}">
          <span class="sw" style="background:${sw}"></span>
          <span>${label}${on ? "" : " — none"}</span>
          <span class="num">${dist === null ? "—" : (dist / 100).toFixed(2) + " m"}</span>
          <span class="num">${en === null ? "—" : Math.round(en) + "%"}</span>
        </div>`;
      rows.innerHTML =
        line("#ffd66b", "moving", this._on(B + "motion"),
             this._n(P + "moving_distance"), this._n(P + "moving_energy")) +
        line("#5df9c4", "still", this._on(B + "still_presence"),
             this._n(P + "still_distance"), this._n(P + "still_energy")) +
        line("#9aa4b2", "occupancy", this._on(B + "occupancy"),
             this._n(P + "detection_distance"), null);
    }
    const note = this.shadowRoot.getElementById("note");
    if (note) note.textContent = "";
  }

  // ── history painting ───────────────────────────────────────────────────────────
  _paintHistory() {
    const note = this.shadowRoot.getElementById("note");
    if (note) note.textContent = this._busy ? "asking the recorder…" : this._note;
    this._drawStrip();
    this._drawTable();
  }

  /* A VISIT AS A TRACE IN TIME. The tracker draws a path because it knows where somebody
   * was; this sensor never does, so the visit runs left to right as its own duration, and
   * the two things it DOES know are drawn against it: what state it was in (the band) and
   * how strong the return was (the height). */
  _drawStrip() {
    const cv = this.shadowRoot.querySelector("#c");
    if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    const W = cv.clientWidth || 440, H = Math.round(W * 0.44);
    cv.style.height = H + "px";
    if (cv.width !== Math.round(W * dpr)) cv.width = Math.round(W * dpr);
    if (cv.height !== Math.round(H * dpr)) cv.height = Math.round(H * dpr);
    const g = cv.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H); g.fillStyle = "#05070d"; g.fillRect(0, 0, W, H);
    g.font = "11px ui-monospace, monospace";

    const e = this._events[this._sel];
    if (!e) {
      g.fillStyle = "rgba(200,215,235,.8)"; g.font = "13px ui-monospace, monospace";
      g.fillText(this._busy ? "asking the recorder…" : "select a visit below", 16, 26);
      return;
    }
    const padL = 34, padR = 12, padT = 18, padB = 26;
    const x = (k) => padL + ((W - padL - padR) * k) / (e.pts.length - 1 || 1);
    const base = H - padB, top = padT;
    const yE = (v) => base - ((base - top) * Math.max(0, Math.min(100, v))) / 100;

    // strength gridlines, so the height means something
    g.strokeStyle = "rgba(255,255,255,.07)"; g.fillStyle = "rgba(160,225,245,.6)";
    g.lineWidth = 1;
    for (const v of [0, 50, 100]) {
      g.beginPath(); g.moveTo(padL, yE(v)); g.lineTo(W - padR, yE(v)); g.stroke();
      g.fillText(`${v}%`, 4, yE(v) + 4);
    }

    // the state band along the bottom: what the sensor thought was happening
    for (let k = 0; k < e.pts.length - 1; k++) {
      const p = e.pts[k];
      g.fillStyle = p.moving ? MOVING : p.still ? STILL : HERE;
      g.globalAlpha = p.moving || p.still ? .85 : .35;
      g.fillRect(x(k), base + 4, Math.max(1, x(k + 1) - x(k)), 7);
    }
    g.globalAlpha = 1;

    // the two strengths as lines
    const line = (key, colour) => {
      g.strokeStyle = colour; g.lineWidth = 1.8; g.beginPath();
      e.pts.forEach((p, k) => k ? g.lineTo(x(k), yE(p[key])) : g.moveTo(x(k), yE(p[key])));
      g.stroke();
    };
    line("sE", STILL);
    line("mE", MOVING);

    g.fillStyle = "rgba(255,255,255,.7)";
    g.fillText(fmtClock(e.start), padL, H - 8);
    const endLabel = fmtClock(e.end);
    g.fillText(endLabel, W - padR - g.measureText(endLabel).width, H - 8);
    g.fillStyle = "rgba(255,255,255,.55)";
    g.fillText(fmtDur(e.dur), (W - g.measureText(fmtDur(e.dur)).width) / 2, H - 8);
  }

  _drawTable() {
    const el = this.shadowRoot.getElementById("rows");
    if (!el) return;
    if (!this._events.length) { el.innerHTML = ""; return; }
    const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
    const rows = this._events.map((e, i) => `
      <tr class="row ${i === this._sel ? "sel" : ""}" data-i="${i}">
        <td>${fmtClock(e.start)}</td>
        <td class="num">${fmtDur(e.dur)}</td>
        <td class="num" style="color:${MOVING}">${pct(e.moving_ms, e.dur)}%</td>
        <td class="num" style="color:${STILL}">${pct(e.still_ms, e.dur)}%</td>
        <td class="num">${Math.round(e.peak_moving)}%</td>
        <td class="num">${Math.round(e.peak_still)}%</td>
        <td class="num">${e.near_cm === null ? "—" : (e.near_cm / 100).toFixed(2) + " m"}</td>
      </tr>`).join("");
    el.innerHTML = `<table>
      <tr><th>started</th><th class="num">lasted</th><th class="num">moving</th>
          <th class="num">still</th><th class="num">pk mv</th><th class="num">pk st</th>
          <th class="num">closest</th></tr>${rows}</table>`;
    el.querySelectorAll("tr.row").forEach(tr => tr.addEventListener("click", () => {
      this._sel = Number(tr.dataset.i); this._paint();
    }));
  }
}

customElements.define("radar-presence-card", RadarPresenceCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "radar-presence-card",
  name: "Radar presence (LD2410)",
  description: "Moving and still distance bands with return strength — no bearing invented",
});
