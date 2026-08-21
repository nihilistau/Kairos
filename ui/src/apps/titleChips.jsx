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

export function VoiceChip() {
  const s = usePoll(api.speakStatus, 20000)
  const lv = (s.data && s.data.live) || null
  if (!lv) return null
  return lv.enabled === false
    ? <Chip tone="tc-off" title="voice.enabled is off">muted</Chip>
    : <Chip tone="tc-on" title="provider · voice">{lv.method}{lv.method === 'xai' ? ' · ' + lv.xai_voice : ''}</Chip>
}

export function SearchChip() {
  const s = usePoll(api.search, 20000)
  const d = s.data
  if (!d || !d.ok) return null
  return <Chip tone="tc-on" title="the engine her next search uses">{d.search_backend}</Chip>
}

export function ResearchChip() {
  const s = usePoll(api.research, 20000)
  const d = s.data
  if (!d || !d.ok) return null
  if (d.inflight) return <Chip tone="tc-busy" title={d.inflight.query}>looking…</Chip>
  return d.armed
    ? <Chip tone="tc-on" title="her research tier">{d.backend}</Chip>
    : <Chip tone="tc-off" title="her tier is off; your manual box still works">tier off</Chip>
}

export function WardrobeChip() {
  const s = usePoll(api.wardrobe, 15000)
  const g = s.data && s.data.genstatus
  if (!g) return null
  if (g.running) return <Chip tone="tc-busy" title={g.last || g.what}>making…</Chip>
  const waiting = (s.data.wants || s.data.waiting || []).length
  return waiting ? <Chip tone="tc-on" title="wants waiting to be made">{waiting} waiting</Chip> : null
}

export function StageChip() {
  const s = usePoll(api.roleplay, 15000)
  const sc = s.data && s.data.scene
  if (!sc) return null
  return <Chip tone="tc-busy" title={(sc.role || '') + ' — ' + (sc.setting || '')}>
    {sc.level_name || 'rung ' + sc.level}
  </Chip>
}

export function MusicChip() {
  const s = usePoll(api.music, 20000)
  const st = s.data && s.data.state
  if (!st || !st.playing) return null
  return <Chip tone="tc-on" title="playing now">{(st.title || st.track || 'playing').slice(0, 24)}</Chip>
}

export function RoomChip() {
  const s = usePoll(api.senses, 20000)
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
  const n = ((s.data && s.data.games) || []).filter(g => !g.over && !g.done).length
  return n ? <Chip tone="tc-on" title="boards in play">{n} live</Chip> : null
}
