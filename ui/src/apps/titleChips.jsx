import { usePoll } from './panel.jsx'
import * as api from '../api.js'
import { Chip } from '../kit/parts.jsx'

/* titleChips — the status chip a window wears in its own title bar (2026-08-21,
 * his ask: "Include a chip/indicator like on the research panel for all panels
 * that show status, provider etc").
 *
 * THE FRAMEWORK: an app's registry row may carry `TitleChip`, a tiny component
 * the window chrome renders beside the title. It mounts only while the window
 * is open, so each chip's poll costs nothing when the window is closed. Chips
 * are GLANCES — one or two words about state/provider — never controls; the
 * panel body owns the controls.
 *
 * Style: the KIT'S Chip (redesign stage 2). Four states, one mapping: on → ok,
 * off → neutral, busy → accent with a pulsing dot, live → accent with a STILL dot.
 * BUSY IS FOR BOUNDED ACTIVITY (a look in flight, a picture being made): a scene, a
 * reading or a wait for quiet can last hours, and a pulse that never stops is motion he
 * cannot pause (WCAG 2.2.2; stage-2 review, M3). Those say `live`. The tc- classes are gone.
 */
const TONE = { on: 'ok', off: 'neutral', busy: 'accent', live: 'accent' }
export const Glance = ({ state = 'on', title, children }) =>
  children ? <Chip tone={TONE[state] || 'neutral'} busy={state === 'busy'} dot={state === 'live'}
                   title={title}>{children}</Chip> : null
// While the FIRST poll is in flight a chip is absent, which reads as "no status" —
// indistinguishable from a window whose feature is off (his report, 2026-08-22). A quiet
// ellipsis says "asking"; null is reserved for "off / nothing to show".
export const Pending = () => <Chip tone="neutral" title="asking…">…</Chip>

export function VoiceChip() {
  const s = usePoll(api.speakStatus, 20000)
  if (s.loading && !s.data) return <Pending />
  const lv = (s.data && s.data.live) || null
  if (!lv) return null
  return lv.enabled === false
    ? <Glance state="off" title="voice.enabled is off">muted</Glance>
    : <Glance state="on" title="provider · voice">{lv.method}{lv.method === 'xai' ? ' · ' + lv.xai_voice : (lv.local_gguf ? ' · ' + lv.local_gguf : '')}</Glance>
}

export function SearchChip() {
  const s = usePoll(api.search, 20000)
  if (s.loading && !s.data) return <Pending />
  const d = s.data
  if (!d || !d.ok) return null
  return <Glance state="on" title="the engine her next search uses">{d.search_backend}</Glance>
}

export function ResearchChip() {
  const s = usePoll(api.research, 20000)
  if (s.loading && !s.data) return <Pending />
  const d = s.data
  if (!d || !d.ok) return null
  if (d.inflight) return <Glance state="busy" title={d.inflight.query}>looking…</Glance>
  return d.armed
    ? <Glance state="on" title="her research tier">{d.backend}</Glance>
    : <Glance state="off" title="her tier is off; your manual box still works">tier off</Glance>
}

export function WardrobeChip() {
  const s = usePoll(api.wardrobe, 15000)
  if (s.loading && !s.data) return <Pending />
  const g = s.data && s.data.genstatus
  if (!g) return null
  if (g.running) return <Glance state="busy" title={g.last || g.what}>making…</Glance>
  const waiting = (s.data.wants || s.data.waiting || []).length
  return waiting ? <Glance state="on" title="wants waiting to be made">{waiting} waiting</Glance> : null
}

export function StageChip() {
  const s = usePoll(api.roleplay, 15000)
  if (s.loading && !s.data) return <Pending />
  const sc = s.data && s.data.scene
  if (!sc) return null
  return <Glance state="live" title={(sc.role || '') + ' — ' + (sc.setting || '')}>
    {sc.level_name || 'rung ' + sc.level}
  </Glance>
}

/* The music chip's words. The server sends `track` as an OBJECT ({path, title, artist,
 * album} — harness/skills/music.py, and Music.jsx reads track.title), never a string. The
 * old `(st.title || st.track || 'playing').slice(0, 24)` called .slice on that object
 * while music played; the title bar sits outside the window's error boundary, so the
 * whole room went black (stage 4, 3/6). A string field is picked first, then cut. */
export const musicLabel = (st) => {
  const t = st.track
  const name = (t && typeof t === 'object' && typeof t.title === 'string' && t.title)
    || (typeof t === 'string' && t)
    || (typeof st.title === 'string' && st.title)
    || 'playing'
  return String(name).slice(0, 24)
}

export function MusicChip() {
  const s = usePoll(api.music, 20000)
  if (s.loading && !s.data) return <Pending />
  const st = s.data && s.data.state
  if (!st || !st.playing) return null
  return <Glance state="on" title="playing now">{musicLabel(st)}</Glance>
}

export function RoomChip() {
  const s = usePoll(api.senses, 20000)
  if (s.loading && !s.data) return <Pending />
  const a = s.data && s.data.ambient
  if (!a) return null
  if (!a.enabled) return <Glance state="off" title="the hourly look is off">eye off</Glance>
  if (a.waiting) return <Glance state="live" title={a.waiting.why}>waiting for quiet</Glance>
  const m = a.next_in_s != null ? Math.max(0, Math.round(a.next_in_s / 60)) : null
  return <Glance state="on" title="the eye is on its schedule">
    {m != null ? 'next look ~' + m + 'm' : 'looking hourly'}
  </Glance>
}

export function GamesChip() {
  const s = usePoll(api.games, 30000)
  if (s.loading && !s.data) return <Pending />
  const n = ((s.data && s.data.games) || []).filter(g => !g.over && !g.done).length
  return n ? <Glance state="on" title="boards in play">{n} live</Glance> : null
}

export function PresenceChip() {
  const s = usePoll(api.presence, 15000)
  if (s.loading && !s.data) return <Pending />
  const st = (s.data && s.data.state) || {}
  if (!st.mode || st.mode === 'off') return <Glance state="off" title="presence.mode is off">off</Glance>
  if (st.reading && !st.reading.done) return <Glance state="live" title={st.mode + ' · reading'}>reading {String(st.reading.title).slice(0, 18)}</Glance>
  const m = st.next_in_s != null ? Math.max(0, Math.round(st.next_in_s / 60)) : null
  return <Glance state="on" title="her mode, and when her next turn may come">{st.mode}{m != null ? ' · next ~' + m + 'm' : ''}</Glance>
}

export function AuxChip() {
  const s = usePoll(api.aux, 20000)
  if (s.loading && !s.data) return <Pending />
  const d = s.data || {}
  if (!d.armed) return <Glance state="off" title="SP_AUX is off in the profile">off</Glance>
  if (!d.embed_up) return <Glance state="off" title="the embedding door is not answering">embed dark</Glance>
  return <Glance state={d.warming ? 'busy' : 'on'} title={'chat ' + (d.chat_up ? 'up' : 'dark') + ' · ' + (d.chat_model || '')}>
    embed ✓ {d.chat_up ? 'chat ✓' : 'chat dark'} · {d.chunks}{d.warming ? ' · warming' : ''}
  </Glance>
}

export function SensesChip() {
  const s = usePoll(api.senses, 20000)
  if (s.loading && !s.data) return <Pending />
  const e = (s.data && s.data.eyes) || null
  if (!e) return null
  if (e.backend === 'aux_vl') {
    if (!e.vl_model || e.door_up === false) return <Glance state="off" title="Sight — her eyes: aux_vl needs a model and the door up">eyes: dark</Glance>
    return <Glance state="on" title="an LFM VL model on the aux door">eyes: aux VL · {String(e.vl_model).slice(0, 18)}</Glance>
  }
  return <Glance state="on" title="Sight — her eyes">{e.backend === 'openai' ? 'eyes: seam' : 'eyes: engine'}</Glance>
}
