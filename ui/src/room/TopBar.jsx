import { usePoll } from '../apps/panel.jsx'
import * as api from '../api.js'
import { Chip, Orb } from '../kit/parts.jsx'
import { dayFacts, upFor, until } from './facts.js'
import Presence from './Presence.jsx'
import StackLight from './StackLight.jsx'

/* THE TOP BAR (redesign stage 3, spec §8). Her on the left, her day in the centre, the
 * machine on the right — what the room already knows, where it can be read. The taskbar
 * below keeps only what he acts on.
 *
 * A <div role="region">, not <header>: shell.css hides `.room header` (the old page
 * header), and this bar must never inherit that. TopBarView is pure — G-ROOM-KIT renders
 * it with a fixture pulse; TopBar is the two polls around it. */
export function TopBarView({ pulse, mood, health, healthError, system, refresh }) {
  const p = pulse || {}
  const m = mood || { word: 'quiet', known: true, thinking: false }
  const facts = dayFacts(p)
  const up = p.stack && p.stack.up_s != null ? upFor(p.stack.up_s) : null
  const bk = p.backup && p.backup.next_in_s != null ? until(p.backup.next_in_s) : null
  return (
    <div className="topbar" role="region" aria-label="the room">
      <div className="top-her">
        <span className="top-mood" role="status"
              title={m.known ? 'her mood' : 'her mood — a word with no colour on file'}
              aria-label={'her mood: ' + m.word + (m.thinking ? ', thinking' : '')}>
          <Orb thinking={m.thinking} /><span className="top-mood-t">{m.word}{m.thinking ? ' · thinking' : ''}</span>
        </span>
        <Presence pulse={p} />
      </div>
      <div className="top-day">
        {facts.map(f => (
          <span key={f.k} className="top-fact"><span className="top-k">{f.k}</span> {f.v}</span>
        ))}
      </div>
      <div className="top-stack">
        {system && system.profile
          ? <span className="top-prof"><Chip title="the profile this stack was launched with">{system.profile}</Chip></span>
          : null}
        {up ? (
          <span className="top-up"
                title={'the gateway, since ' + new Date(p.stack.started_at * 1000).toLocaleString()}>
            <span className="top-k">up</span> {up}
          </span>
        ) : null}
        <StackLight health={health} healthError={healthError} system={system} refresh={refresh} />
        {bk ? <span className="top-bk"><span className="top-k">backup</span> in {bk}</span> : null}
      </div>
    </div>
  )
}

export default function TopBar({ pulse, mood }) {
  const h = usePoll(api.health, 10000)
  const sys = usePoll(api.system, 60000)
  return <TopBarView pulse={pulse} mood={mood} health={h.data} healthError={h.error}
                     system={sys.data} refresh={h.refresh} />
}
