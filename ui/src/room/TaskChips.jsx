import { useEffect, useState } from 'react'
import { usePoll } from '../apps/panel.jsx'
import * as api from '../api.js'
import { Chip, Button } from '../kit/parts.jsx'
import * as speech from './speech.js'

/* THE TASKBAR'S CHIPS (moved out of main.jsx, redesign stage 2) — kit Chips, like every
 * window's title chip, so "a glance at state" has one shape wherever it sits.
 *
 * LOOKED UP — accent, because it is an act in the world, not a mood. In flight it pulses;
 * the last look stays, clickable, so the research window is one tap from the bar.
 * IN SCENE — warn, with a still dot: a running scene changes who she is, and he did not
 * know for 17 beats.
 */
export function LookingChip({ pulse, onOpen }) {
  const r = (pulse && pulse.research) || {}
  if (!r.inflight && !r.title && !r.query) return null
  // THE BAR SHEDS GLANCES, NEVER CONTROLS (stage-2 review, I1): the query hides at
  // <=1440px and a FINISHED look at <=1000px (shell.css), so off the record and Shut down
  // stay on screen. A look in flight always shows. Chip takes no className, hence the span.
  return (
    <span className={'tb-look' + (r.inflight ? ' tb-look-on' : '')}>
      <Chip tone="accent" busy={!!r.inflight} title={r.query || r.title || 'what she looked up'}
            onClick={onOpen}>
        <span className="tb-chip-k">{r.inflight ? (r.kind === 'research' ? 'researching' : 'looking up') : 'looked up'}</span>
        <span className="tb-chip-q">{' '}{(r.query || r.title || '').slice(0, 42)}</span>
      </Chip>
    </span>
  )
}

export function SceneChip() {
  const rp = usePoll(api.roleplay, 8000)
  const sc = rp.data && rp.data.scene
  const [busy, setBusy] = useState(false)
  if (!sc) return null
  return (
    <span className="tb-scene">
      {/* a static dot, not busy: a scene lasts hours, and a pulse that never stops is
          motion he cannot pause (WCAG 2.2.2; stage-2 review, M3) */}
      <Chip tone="warn" dot title={(sc.title || sc.id) + ' · ' + (sc.level_name || 'rung ' + sc.level) + ' · '
                                      + sc.beats + ' beats — ' + (sc.role || '') + ' — ' + (sc.setting || '')}>
        <span className="tb-chip-k">in scene</span>
        <span className="tb-chip-q">{' '}{sc.title || sc.id}
          {' · '}{sc.level_name || 'rung ' + sc.level} · {sc.beats} beats</span>
      </Chip>
      <Button size="sm" variant="ghost" disabled={busy}
              title="leave the scene — she comes back as herself"
              onClick={async () => { setBusy(true)
                try { await api.roleplayWrite({ op: 'exit' }); rp.refresh() } finally { setBusy(false) } }}>
        exit
      </Button>
    </span>
  )
}

/* WHY SHE IS QUIET (2026-10-29). Grok went silent on him and nothing in the room said why —
 * the player swallowed every failure. speech.js now keeps a reason; this shows it until he
 * clicks it (a click is also what unblocks autoplay, so the advice and the cure are one tap).
 * warn when she did not speak; warm when she spoke through a different voice than the one
 * chosen ("spoke with lfm3 — Grok: http 402: ..."). Nothing to say: no chip. */
export function VoiceChipView({ v, onDismiss }) {
  if (!v || !v.reason) return null
  return (
    <span className="tb-voice">
      <Chip tone={v.reasonKind === 'note' ? 'warm' : 'warn'} dot title={v.reason + ' — click to dismiss'}
            onClick={onDismiss}>
        <span className="tb-chip-k">voice</span>
        <span className="tb-chip-q">{' '}{v.reason.length > 64 ? v.reason.slice(0, 63) + '…' : v.reason}</span>
      </Chip>
    </span>
  )
}

export function VoiceChip() {
  const [v, setV] = useState(speech.state())
  useEffect(() => speech.onChange(setV), [])
  return <VoiceChipView v={v} onDismiss={() => speech.dismiss()} />
}
