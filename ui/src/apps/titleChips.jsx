import { usePoll } from './panel.jsx'
import * as api from '../api.js'

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
 * Style: the shared .tc chip classes in room.css (tc-on / tc-off / tc-busy).
 */
const Chip = ({ tone = '', title, children }) =>
  children ? <span className={'tc ' + tone} title={title}>{children}</span> : null
// While the FIRST poll is in flight a chip is absent, which reads as "no status" —
// indistinguishable from a window whose feature is off (his report, 2026-08-22). A quiet
// ellipsis says "asking"; null is reserved for "off / nothing to show".
const Pending = () => <span className="tc tc-off" title="asking…">…</span>

export function VoiceChip() {
  const s = usePoll(api.speakStatus, 20000)
  if (s.loading && !s.data) return <Pending />
  const lv = (s.data && s.data.live) || null
  if (!lv) return null
  return lv.enabled === false
    ? <Chip tone="tc-off" title="voice.enabled is off">muted</Chip>
    : <Chip tone="tc-on" title="provider · voice">{lv.method}{lv.method === 'xai' ? ' · ' + lv.xai_voice : (lv.local_gguf ? ' · ' + lv.local_gguf : '')}</Chip>
}

export function SearchChip() {
  const s = usePoll(api.search, 20000)
  if (s.loading && !s.data) return <Pending />
  const d = s.data
  if (!d || !d.ok) return null
  return <Chip tone="tc-on" title="the engine her next search uses">{d.search_backend}</Chip>
}

export function ResearchChip() {
  const s = usePoll(api.research, 20000)
  if (s.loading && !s.data) return <Pending />
  const d = s.data
  if (!d || !d.ok) return null
  if (d.inflight) return <Chip tone="tc-busy" title={d.inflight.query}>looking…</Chip>
  return d.armed
    ? <Chip tone="tc-on" title="her research tier">{d.backend}</Chip>
    : <Chip tone="tc-off" title="her tier is off; your manual box still works">tier off</Chip>
}

export function WardrobeChip() {
  const s = usePoll(api.wardrobe, 15000)
  if (s.loading && !s.data) return <Pending />
  const g = s.data && s.data.genstatus
  if (!g) return null
  if (g.running) return <Chip tone="tc-busy" title={g.last || g.what}>making…</Chip>
  const waiting = (s.data.wants || s.data.waiting || []).length
  return waiting ? <Chip tone="tc-on" title="wants waiting to be made">{waiting} waiting</Chip> : null
}

export function StageChip() {
  const s = usePoll(api.roleplay, 15000)
  if (s.loading && !s.data) return <Pending />
  const sc = s.data && s.data.scene
  if (!sc) return null
  return <Chip tone="tc-busy" title={(sc.role || '') + ' — ' + (sc.setting || '')}>
    {sc.level_name || 'rung ' + sc.level}
  </Chip>
}

export function MusicChip() {
  const s = usePoll(api.music, 20000)
  if (s.loading && !s.data) return <Pending />
  const st = s.data && s.data.state
  if (!st || !st.playing) return null
  return <Chip tone="tc-on" title="playing now">{(st.title || st.track || 'playing').slice(0, 24)}</Chip>
}

export function RoomChip() {
  const s = usePoll(api.senses, 20000)
  if (s.loading && !s.data) return <Pending />
  const a = s.data && s.data.ambient
  if (!a) return null
  if (!a.enabled) return <Chip tone="tc-off" title="the hourly look is off">eye off</Chip>
  if (a.waiting) return <Chip tone="tc-busy" title={a.waiting.why}>waiting for quiet</Chip>
  const m = a.next_in_s != null ? Math.max(0, Math.round(a.next_in_s / 60)) : null
  return <Chip tone="tc-on" title="the eye is on its schedule">
    {m != null ? 'next look ~' + m + 'm' : 'looking hourly'}
  </Chip>
}

export function GamesChip() {
  const s = usePoll(api.games, 30000)
  if (s.loading && !s.data) return <Pending />
  const n = ((s.data && s.data.games) || []).filter(g => !g.over && !g.done).length
  return n ? <Chip tone="tc-on" title="boards in play">{n} live</Chip> : null
}

export function PresenceChip() {
  const s = usePoll(api.presence, 15000)
  if (s.loading && !s.data) return <Pending />
  const st = (s.data && s.data.state) || {}
  if (!st.mode || st.mode === 'off') return <Chip tone="tc-off" title="presence.mode is off">off</Chip>
  if (st.reading && !st.reading.done) return <Chip tone="tc-busy" title={st.mode + ' · reading'}>reading {String(st.reading.title).slice(0, 18)}</Chip>
  const m = st.next_in_s != null ? Math.max(0, Math.round(st.next_in_s / 60)) : null
  return <Chip tone="tc-on" title="her mode, and when her next turn may come">{st.mode}{m != null ? ' · next ~' + m + 'm' : ''}</Chip>
}

export function AuxChip() {
  const s = usePoll(api.aux, 20000)
  if (s.loading && !s.data) return <Pending />
  const d = s.data || {}
  if (!d.armed) return <Chip tone="tc-off" title="SP_AUX is off in the profile">off</Chip>
  if (!d.embed_up) return <Chip tone="tc-off" title="the embedding door is not answering">embed dark</Chip>
  return <Chip tone={d.warming ? 'tc-busy' : 'tc-on'} title={'chat ' + (d.chat_up ? 'up' : 'dark') + ' · ' + (d.chat_model || '')}>
    embed ✓ {d.chat_up ? 'chat ✓' : 'chat dark'} · {d.chunks}{d.warming ? ' · warming' : ''}
  </Chip>
}

export function SensesChip() {
  const s = usePoll(api.senses, 20000)
  if (s.loading && !s.data) return <Pending />
  const e = (s.data && s.data.eyes) || null
  if (!e) return null
  if (e.backend === 'aux_vl') {
    if (!e.vl_model || e.door_up === false) return <Chip tone="tc-off" title="Sight — her eyes: aux_vl needs a model and the door up">eyes: dark</Chip>
    return <Chip tone="tc-on" title="an LFM VL model on the aux door">eyes: aux VL · {String(e.vl_model).slice(0, 18)}</Chip>
  }
  return <Chip tone="tc-on" title="Sight — her eyes">{e.backend === 'openai' ? 'eyes: seam' : 'eyes: engine'}</Chip>
}
