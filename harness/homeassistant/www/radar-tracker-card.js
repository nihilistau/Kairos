/* radar-tracker-card — the LD2450, live and in history.
 *
 * SPLIT FROM THE COMBINED CARD (2026-08-26, his ask). The two sensors were sharing one
 * drawing and it flattened the difference between them: the LD2450 reports a POSITION and
 * the LD2410 reports a DISTANCE WITH NO BEARING. One of those belongs on a map and the
 * other does not, so they now have a card each. See radar-presence-card.js for the other.
 *
 * TWO TABS, because they answer different questions:
 *
 *   LIVE      where is somebody NOW, and where have they been in the last five minutes
 *   HISTORY   what happened earlier — every visit, as a path you can select and read
 *
 * WHERE HISTORY COMES FROM, and why it is affordable. Home Assistant's recorder stores
 * state CHANGES, and when the room is empty the LD2450 parks x and y at 0, so an empty
 * room costs nothing: measured on this instance, three hours held THIRTEEN points, with a
 * single 2.7-hour gap covering the whole quiet stretch. Movement is dense, absence is free.
 *
 * IT IS FETCHED ON DEMAND, NEVER ON LOAD. The same measurement found the REST history API
 * taking 21 seconds for three entities over three hours against this database. So the
 * History tab asks over the WEBSOCKET api (much faster), only when opened, only for the
 * window chosen, and says it is working while it does.
 *
 * AN "EVENT" IS DERIVED, NOT RECORDED. Nothing in the system writes "somebody visited".
 * A visit is a contiguous run of non-zero positions, and this card segments the history
 * into those runs. That means the definition lives here, in EVENT_GAP_MS, and it is worth
 * knowing rather than trusting: a person who stands still long enough for the radar to
 * drop its lock will appear as two visits, because that is genuinely what the sensor saw.
 */

const LIVE_HOLD_MS = 300000;   // his ask: the last seen spot stays for five minutes
const FADE_MS = 60000;         // the last minute of that is spent fading out
const TICK_MS = 500;           // fade/expiry ticks; live updates come from the hass setter
const EVENT_GAP_MS = 20000;    // a break longer than this starts a new visit
const MAX_LIVE_PTS = 2000;     // ring buffer bound, so a busy hour cannot grow without end

const COLOURS = ["#7df0ff", "#ff6df5", "#ffd66b"];

const fmtClock = (ms) => new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const fmtDur = (ms) => {
  const s = Math.round(ms / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
};

class RadarTrackerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._cfg = null;
    this._live = [[], [], []];
    this._tab = "live";
    this._events = [];
    this._sel = -1;
    this._hours = 6;
    this._busy = false;
    this._note = "";
    this._timer = null;
    this._pending = false;
  }

  setConfig(config) {
    this._cfg = {
      title: config.title || "LD2450 · tracking",
      room_width_mm: Number(config.room_width_mm) || 4500,
      room_depth_mm: Number(config.room_depth_mm) || 4200,
      prefix: config.prefix || "sensor.bedroom_ld2450_bedroom_ld2450_target_",
      count: Number(config.count) || 3,
      // ── LIVE GEOMETRY (2026-08-27) ────────────────────────────────────────────
      // Optional. Point these at input_number helpers and the room and the sensor's
      // position in it become knobs you can drag while watching the plot. Leave them
      // out and every number above is used exactly as before.
      room_width_entity: config.room_width_entity || "",
      room_depth_entity: config.room_depth_entity || "",
      origin_x_entity: config.origin_x_entity || "",
      origin_y_entity: config.origin_y_entity || "",
      // Where the sensor sits IN the room, mm from the left wall and from the back
      // wall. Defaults put it mid-wall, which is what the card used to assume with no
      // way to say otherwise.
      origin_x_mm: config.origin_x_mm === undefined ? null : Number(config.origin_x_mm),
      origin_y_mm: Number(config.origin_y_mm) || 0,
    };
    this._render();
  }

  /** A number from a live entity when one is configured, else the literal.
   *  NEVER a silent zero: an entity that is missing, unavailable or non-numeric falls
   *  back to the configured value, because a room 0 mm wide divides by zero and a
   *  sensor at origin 0 looks like a real answer. */
  _num(entityId, fallback) {
    if (entityId && this._hass) {
      const st = this._hass.states[entityId];
      if (st && st.state !== "unavailable" && st.state !== "unknown") {
        const v = Number(st.state);
        if (Number.isFinite(v)) return v;
      }
    }
    return fallback;
  }

  set hass(hass) {
    this._hass = hass;
    this._sample();
    if (!this._pending) {
      this._pending = true;
      requestAnimationFrame(() => { this._pending = false; this._paint(); });
    }
  }

  getCardSize() { return 10; }
  disconnectedCallback() { if (this._timer) clearInterval(this._timer); }

  _num(id) {
    const s = this._hass && this._hass.states[id];
    if (!s || s.state === "unknown" || s.state === "unavailable") return null;
    const v = parseFloat(s.state);
    return Number.isFinite(v) ? v : null;
  }

  _sample() {
    if (!this._cfg || !this._hass) return;
    const now = Date.now();
    for (let i = 0; i < this._cfg.count; i++) {
      const p = `${this._cfg.prefix}${i + 1}_`;
      const x = this._num(p + "x"), y = this._num(p + "y");
      // (0,0) is the firmware's way of saying "no target", not a position at the sensor.
      if (x !== null && y !== null && !(x === 0 && y === 0)) {
        this._live[i].push({ t: now, x, y, s: this._num(p + "speed") || 0 });
        if (this._live[i].length > MAX_LIVE_PTS) this._live[i].shift();
      }
      this._live[i] = this._live[i].filter(q => now - q.t < LIVE_HOLD_MS);
    }
  }

  // ── history ──────────────────────────────────────────────────────────────────────
  async _loadHistory() {
    if (!this._hass || this._busy) return;
    this._busy = true; this._note = "asking the recorder…"; this._paint();
    const end = new Date();
    const start = new Date(end.getTime() - this._hours * 3600 * 1000);
    const ids = [];
    for (let i = 1; i <= this._cfg.count; i++) {
      ids.push(`${this._cfg.prefix}${i}_x`, `${this._cfg.prefix}${i}_y`,
               `${this._cfg.prefix}${i}_speed`);
    }
    try {
      // THE WEBSOCKET API, not REST: measured at 21 s for three entities over three hours
      // through /api/history/period against this database, which is far too long to hold a
      // card open for.
      const res = await this._hass.callWS({
        type: "history/history_during_period",
        start_time: start.toISOString(),
        end_time: end.toISOString(),
        entity_ids: ids,
        minimal_response: true,
        no_attributes: true,
        significant_changes_only: false,
      });
      this._events = this._segment(res || {}, start.getTime());
      this._note = this._events.length
        ? `${this._events.length} visit${this._events.length === 1 ? "" : "s"} in the last ${this._hours}h`
        : `nothing moved in the last ${this._hours}h`;
      this._sel = this._events.length ? 0 : -1;
    } catch (e) {
      this._events = []; this._sel = -1;
      this._note = "the recorder said no: " + (e && (e.message || e.code) || "unknown");
    }
    this._busy = false;
    this._paint();
  }

  /* Turn three parallel state series per target into visits.
   *
   * The series are NOT aligned: x, y and speed each record only when they change, so a
   * point in one has no partner in the others. They are merged onto x's timeline and the
   * others are carried forward, which is what the sensor meant -- a value holds until it
   * is contradicted. */
  _segment(res, since) {
    const out = [];
    const at = (r) => {
      const v = r.lu ?? r.last_updated ?? r.last_changed ?? r.lc;
      if (typeof v === "number") return v * 1000;
      const p = Date.parse(v); return Number.isFinite(p) ? p : null;
    };
    const val = (r) => {
      const v = r.s ?? r.state;
      const n = parseFloat(v); return Number.isFinite(n) ? n : null;
    };
    for (let i = 1; i <= this._cfg.count; i++) {
      const xs = res[`${this._cfg.prefix}${i}_x`] || [];
      const ys = res[`${this._cfg.prefix}${i}_y`] || [];
      const sp = res[`${this._cfg.prefix}${i}_speed`] || [];
      if (!xs.length) continue;
      // A LINEAR MERGE, NOT A LOOKUP PER POINT.
      //
      // This was `pick(arr, t)` scanning the whole y and speed arrays for every x point --
      // O(n*n). With thirteen points that is invisible; with a busy hour at 250 ms it is
      // tens of millions of comparisons on the UI thread, and the tab simply stops. It did:
      // Chrome reported the renderer unresponsive and the screenshot timed out.
      //
      // The three series are already sorted, so two indices walking forward are enough.
      // Values carry forward between their own updates, which is what the sensor meant --
      // a reading holds until it is contradicted.
      let iy = 0, isp = 0, lastY = null, lastS = null;
      let cur = null;
      for (const r of xs) {
        const t = at(r); if (t === null || t < since) continue;
        const x = val(r);
        while (iy < ys.length) { const ty = at(ys[iy]); if (ty === null || ty > t) break; lastY = val(ys[iy]); iy++; }
        while (isp < sp.length) { const ts = at(sp[isp]); if (ts === null || ts > t) break; lastS = val(sp[isp]); isp++; }
        const y = lastY;
        const s = lastS;
        const live = x !== null && y !== null && !(x === 0 && y === 0);
        if (!live) { if (cur && cur.pts.length > 1) out.push(cur); cur = null; continue; }
        if (!cur || t - cur.pts[cur.pts.length - 1].t > EVENT_GAP_MS) {
          if (cur && cur.pts.length > 1) out.push(cur);
          cur = { target: i, pts: [] };
        }
        cur.pts.push({ t, x, y, s: s === null ? 0 : s });
      }
      if (cur && cur.pts.length > 1) out.push(cur);
    }
    for (const e of out) {
      const p = e.pts;
      e.start = p[0].t; e.end = p[p.length - 1].t; e.dur = e.end - e.start;
      let path = 0, near = Infinity, far = 0, fast = 0;
      for (let k = 0; k < p.length; k++) {
        if (k) path += Math.hypot(p[k].x - p[k - 1].x, p[k].y - p[k - 1].y);
        const d = Math.hypot(p[k].x, p[k].y);
        if (d < near) near = d;
        if (d > far) far = d;
        const sp2 = Math.abs(p[k].s);
        if (sp2 > fast) fast = sp2;
      }
      e.path_mm = path; e.near_mm = near; e.far_mm = far; e.fast_mms = fast;
    }
    out.sort((a, b) => b.start - a.start);
    return out.slice(0, 60);
  }

  // ── rendering ────────────────────────────────────────────────────────────────────
  _render() {
    if (!this.shadowRoot || !this._cfg) return;
    this.shadowRoot.innerHTML = `
      <ha-card>
        <style>
          ha-card { padding: 14px; }
          h3 { margin: 0 0 8px; font-size: 1.05rem; font-weight: 600; }
          .tabs { display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap; }
          button {
            background: rgba(255,255,255,.06); color: inherit; font: inherit;
            border: 1px solid rgba(255,255,255,.12); border-radius: 999px;
            padding: 4px 12px; font-size: 12px; cursor: pointer;
          }
          button.on { background: rgba(125,240,255,.18); border-color: rgba(125,240,255,.5); }
          button:disabled { opacity: .5; cursor: default; }
          .spacer { flex: 1; }
          canvas { width: 100%; display: block; border-radius: 10px; background: #05070d; }
          .note { font-size: 11px; opacity: .7; margin: 8px 0 0; min-height: 14px; }
          table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 11px; }
          th { text-align: left; font-weight: 500; opacity: .6; padding: 3px 4px; }
          td { padding: 4px; border-top: 1px solid rgba(255,255,255,.06); }
          tr.row { cursor: pointer; }
          tr.row:hover td { background: rgba(255,255,255,.04); }
          tr.sel td { background: rgba(125,240,255,.12); }
          .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; }
          .num { text-align: right; font-variant-numeric: tabular-nums; }
          .live { margin-top: 8px; font-size: 11px; }
          .live div { display: grid; grid-template-columns: 24px 1fr 1fr 1fr 1fr;
                      gap: 6px; padding: 3px 0; align-items: baseline; }
          .muted { opacity: .45; }
        </style>
        <h3>${this._cfg.title}</h3>
        <div class="tabs" id="tabs"></div>
        <canvas id="c"></canvas>
        <div id="body"></div>
        <p class="note" id="note"></p>
      </ha-card>`;
    this._wire();
    this._paint();
    if (this._timer) clearInterval(this._timer);
    // Only for expiry/fade. Live updates arrive through the hass setter, which cannot be
    // throttled the way a background tab's interval can.
    this._timer = setInterval(() => { this._sample(); this._paint(); }, TICK_MS);
  }

  _wire() {
    const t = this.shadowRoot.getElementById("tabs");
    const mk = (label, on, fn, dis) => {
      const b = document.createElement("button");
      b.textContent = label; if (on) b.className = "on"; if (dis) b.disabled = true;
      b.addEventListener("click", fn); t.appendChild(b); return b;
    };
    t.innerHTML = "";
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
    if (!this.shadowRoot || !this._cfg) return;
    const note = this.shadowRoot.getElementById("note");
    if (note) note.textContent = this._tab === "history"
      ? (this._busy ? "asking the recorder…" : this._note)
      : "Sensor at the bottom, facing up the page. The last seen spot stays five minutes.";
    this._drawCanvas();
    this._drawBody();
  }

  _geom(cv) {
    const dpr = window.devicePixelRatio || 1;
    const cssW = cv.clientWidth || 460;
    const cssH = Math.round(cssW * 0.86);
    cv.style.height = cssH + "px";
    if (cv.width !== Math.round(cssW * dpr)) { cv.width = Math.round(cssW * dpr); }
    if (cv.height !== Math.round(cssH * dpr)) { cv.height = Math.round(cssH * dpr); }
    const g = cv.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const RW = this._num(this._cfg.room_width_entity, this._cfg.room_width_mm);
    const RD = this._num(this._cfg.room_depth_entity, this._cfg.room_depth_mm);
    const pad = 34;
    const s = Math.min((cssW - pad * 2) / RW, (cssH - pad * 2) / RD);
    // ── THE SENSOR IS WHERE IT IS, NOT WHERE THE CARD ASSUMED ──────────────────────
    // Targets arrive in the SENSOR's frame (x=0 straight ahead), so moving the sensor
    // moves everything it reports with it — which is the whole point of the knob and
    // the reason two radars in one room stop drawing the same person twice.
    // origin_x defaults to mid-wall so an unconfigured card is unchanged.
    const oxMM = this._num(this._cfg.origin_x_entity,
                           this._cfg.origin_x_mm === null ? RW / 2 : this._cfg.origin_x_mm);
    const oyMM = this._num(this._cfg.origin_y_entity, this._cfg.origin_y_mm);
    const left = (cssW - RW * s) / 2, bottom = (cssH - pad);
    const ox = left + oxMM * s;          // sensor, across the room
    const oy = bottom - oyMM * s;        // sensor, up from the back wall
    return { g, W: cssW, H: cssH, RW, RD, pad, s, ox, oy, left, bottom,
             px: mm => ox + mm * s, py: mm => oy - mm * s };
  }

  _drawRoom(q) {
    const { g, W, H, RW, RD, ox, oy, px, py } = q;
    g.clearRect(0, 0, W, H);
    g.fillStyle = "#05070d"; g.fillRect(0, 0, W, H);
    g.strokeStyle = "rgba(190,205,225,.55)"; g.lineWidth = 1.5;
    // THE ROOM IS FIXED, THE SENSOR MOVES INSIDE IT. Drawn from the room's own left
    // edge rather than from the sensor, or sliding the origin would drag the walls.
    g.strokeRect(q.left, q.bottom - RD * q.s, RW * q.s, RD * q.s);
    g.strokeStyle = "rgba(125,240,255,.22)";
    g.fillStyle = "rgba(160,225,245,.75)";
    g.font = "11px ui-monospace, monospace"; g.lineWidth = 1;
    for (let m = 1; m * 1000 <= RD; m++) {
      g.beginPath(); g.arc(ox, oy, m * 1000 * q.s, Math.PI, 2 * Math.PI); g.stroke();
      g.fillText(`${m} m`, ox + 7, py(m * 1000) - 5);
    }
    g.beginPath(); g.moveTo(ox, oy); g.lineTo(ox, py(RD)); g.stroke();
    g.fillStyle = "#fff";
    g.beginPath(); g.arc(ox, oy, 5, 0, Math.PI * 2); g.fill();
    g.fillStyle = "rgba(255,255,255,.7)";
    g.fillText("LD2450", ox + 12, oy - 7);
  }

  _drawCanvas() {
    const cv = this.shadowRoot.querySelector("#c");
    if (!cv) return;
    const q = this._geom(cv); const g = q.g;
    this._drawRoom(q);
    if (this._tab === "history") return this._drawEvent(q);

    const now = Date.now();
    let any = false;
    this._live.forEach((buf, i) => {
      if (!buf.length) return;
      any = true;
      const col = COLOURS[i % COLOURS.length];
      // the path so far, as a line rather than loose dots -- a route is a shape
      g.strokeStyle = col; g.globalAlpha = .35; g.lineWidth = 1.5;
      g.beginPath();
      buf.forEach((p, k) => k ? g.lineTo(q.px(p.x), q.py(p.y)) : g.moveTo(q.px(p.x), q.py(p.y)));
      g.stroke();
      for (const p of buf) {
        const age = now - p.t;
        const a = Math.max(0, 1 - Math.max(0, age - (LIVE_HOLD_MS - FADE_MS)) / FADE_MS);
        if (a <= 0) continue;
        g.globalAlpha = a * .55; g.fillStyle = col;
        g.beginPath(); g.arc(q.px(p.x), q.py(p.y), 2.5, 0, Math.PI * 2); g.fill();
      }
      const cur = buf[buf.length - 1];
      const fresh = now - cur.t < 3000;
      g.globalAlpha = fresh ? 1 : .5; g.fillStyle = col;
      g.beginPath(); g.arc(q.px(cur.x), q.py(cur.y), 6, 0, Math.PI * 2); g.fill();
      g.globalAlpha = fresh ? .5 : .2; g.strokeStyle = col; g.lineWidth = 2;
      g.beginPath(); g.arc(q.px(cur.x), q.py(cur.y), 12, 0, Math.PI * 2); g.stroke();
      g.globalAlpha = 1; g.fillStyle = col; g.font = "12px ui-monospace, monospace";
      g.fillText(`T${i + 1}`, q.px(cur.x) + 14, q.py(cur.y) - 9);
    });
    g.globalAlpha = 1;
    if (!any) {
      g.fillStyle = "rgba(200,215,235,.8)"; g.font = "13px ui-monospace, monospace";
      g.fillText(this._hass ? "no targets — the room is clear" : "waiting for Home Assistant…",
                 q.pad + 6, q.pad + 20);
    }
  }

  _drawEvent(q) {
    const g = q.g;
    const e = this._events[this._sel];
    if (!e) {
      g.fillStyle = "rgba(200,215,235,.8)"; g.font = "13px ui-monospace, monospace";
      g.fillText(this._busy ? "asking the recorder…" : "select a visit below",
                 q.pad + 6, q.pad + 20);
      return;
    }
    const col = COLOURS[(e.target - 1) % COLOURS.length];
    // THE WHOLE PATH, start to end, with the direction of travel readable: the line runs
    // dim at the start and bright at the end, so you can see which way they walked without
    // needing an arrowhead on every segment.
    for (let k = 1; k < e.pts.length; k++) {
      const f = k / (e.pts.length - 1);
      g.strokeStyle = col; g.globalAlpha = .18 + f * .72; g.lineWidth = 2;
      g.beginPath();
      g.moveTo(q.px(e.pts[k - 1].x), q.py(e.pts[k - 1].y));
      g.lineTo(q.px(e.pts[k].x), q.py(e.pts[k].y));
      g.stroke();
    }
    const a = e.pts[0], b = e.pts[e.pts.length - 1];
    g.globalAlpha = 1;
    g.strokeStyle = col; g.lineWidth = 2;
    g.beginPath(); g.arc(q.px(a.x), q.py(a.y), 7, 0, Math.PI * 2); g.stroke();   // start: hollow
    g.fillStyle = col;
    g.beginPath(); g.arc(q.px(b.x), q.py(b.y), 6, 0, Math.PI * 2); g.fill();     // end: solid
    g.font = "11px ui-monospace, monospace";
    g.fillStyle = "rgba(255,255,255,.75)";
    // WHERE SOMEBODY CAME IN AND WHERE THEY STOPPED are often the same doorway, so the two
    // labels land on top of each other and read as one word of nonsense -- it rendered as
    // "stardse". When they are close, push them apart vertically rather than shortening
    // them: the pair is only useful if you can tell which is which.
    const ax = q.px(a.x), ay = q.py(a.y), bx = q.px(b.x), by = q.py(b.y);
    const close = Math.hypot(ax - bx, ay - by) < 34;
    g.fillText("start", ax + 11, ay + (close ? 14 : -8));
    g.fillText("end", bx + 11, by - 8);
  }

  _drawBody() {
    const el = this.shadowRoot.getElementById("body");
    if (!el) return;
    if (this._tab === "live") {
      const rows = [];
      for (let i = 0; i < this._cfg.count; i++) {
        const p = `${this._cfg.prefix}${i + 1}_`;
        const x = this._num(p + "x"), y = this._num(p + "y");
        const on = x !== null && y !== null && !(x === 0 && y === 0);
        const d = on ? Math.hypot(x, y) / 1000 : null;
        rows.push(`<div class="${on ? "" : "muted"}">
          <span class="dot" style="background:${COLOURS[i % 3]}"></span>
          <span>T${i + 1}</span>
          <span class="num">${on ? d.toFixed(2) + " m" : "—"}</span>
          <span class="num">${on ? `x ${Math.round(x)}` : ""}</span>
          <span class="num">${on ? `y ${Math.round(y)}` : ""}</span>
        </div>`);
      }
      el.innerHTML = `<div class="live">${rows.join("")}</div>`;
      return;
    }
    if (!this._events.length) { el.innerHTML = ""; return; }
    const rows = this._events.map((e, i) => `
      <tr class="row ${i === this._sel ? "sel" : ""}" data-i="${i}">
        <td><span class="dot" style="background:${COLOURS[(e.target - 1) % 3]}"></span></td>
        <td>${fmtClock(e.start)}</td>
        <td class="num">${fmtDur(e.dur)}</td>
        <td class="num">${(e.path_mm / 1000).toFixed(1)} m</td>
        <td class="num">${(e.near_mm / 1000).toFixed(2)} m</td>
        <td class="num">${(e.fast_mms / 1000).toFixed(2)} m/s</td>
        <td class="num">${e.pts.length}</td>
      </tr>`).join("");
    el.innerHTML = `<table>
      <tr><th></th><th>started</th><th class="num">lasted</th><th class="num">walked</th>
          <th class="num">closest</th><th class="num">fastest</th><th class="num">pts</th></tr>
      ${rows}</table>`;
    el.querySelectorAll("tr.row").forEach(tr => tr.addEventListener("click", () => {
      this._sel = Number(tr.dataset.i); this._paint();
    }));
  }
}

customElements.define("radar-tracker-card", RadarTrackerCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "radar-tracker-card",
  name: "Radar tracker (LD2450)",
  description: "Live x/y tracking with a five-minute tail, plus a browsable history of visits",
});
