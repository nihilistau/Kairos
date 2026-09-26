import { usePoll, Body } from './panel.jsx'
import * as api from '../api.js'
import { KnobGroups } from './knobs.jsx'
import { Chip, Button, State } from '../kit/parts.jsx'

/* PRESENCE — her modes (2026-08-22, his ask: "a lucid dream / company / narration mode").
 *
 * Narration / Company / Lucid Dream are a KAIROS ACTION that waits its turn — the same
 * presence clock, quiet-after-him and shutdown guards as every other unprompted word,
 * plus its own hourly cap. This window is the picker, the knobs, the shelf she reads
 * from (var/library/), and the honest state: off / next in ~m / reading <title>.
 * Nothing speaks unless he arms it here (or in Settings, same knobs).
 */
/* The window's body, split out so G-ROOM-KIT leg 10 can render it with a fixture.
 * The live mode is the kit Button's `secondary` variant with aria-pressed; the
 * others are ghosts. The handlers are the default export's, which talk to her. */
export function PresenceView({ d, onEnter, onLeave, onPickUp, onPutDown }) {
  const st = d.state || {}
  const shelf = d.shelf || []
  const inHand = shelf.find(b => b.in_hand)
  const line = (!st.mode || st.mode === 'off')
    ? <Chip wrap>off — she speaks only as kairos allows</Chip>
    : <Chip tone="ok" dot wrap>
        {st.mode}
        {st.next_in_s != null ? ' — next in ~' + Math.max(0, Math.round(st.next_in_s / 60)) + 'm' : ''}
        {inHand ? ' · reading ' + inHand.title : ''}
      </Chip>
  return (
    <>
      <div className="prs-state">{line}</div>
      {/* MANUAL ENTRY (his ask, 2026-08-22): enter a mode NOW — her first turn comes right
          after her next reply instead of after the idle floor; stop is one click. */}
      <div className="prs-now">
        {['narration', 'company', 'lucid'].map(m => (
          <Button key={m} variant={st.mode === m ? 'secondary' : 'ghost'} aria-pressed={st.mode === m}
                  onClick={() => onEnter(m)}>
            {m === 'narration' ? 'narrate now' : m === 'company' ? 'keep me company' : 'dream now'}
          </Button>
        ))}
        {st.mode && st.mode !== 'off'
          ? <Button className="prs-stop" variant="ghost" onClick={onLeave}>stop</Button> : null}
      </div>
      <KnobGroups only={['Presence — her modes']} />
      <h4 className="prs-shelf-h">the shelf <span className="muted">(var/library/ — drop .txt / .md / .epub in)</span></h4>
      {!shelf.length ? <State kind="empty">empty</State> : shelf.map(b => (
        <div key={b.title} className="prs-book">
          <span className="k">{b.title}{b.in_hand ? ' · in her hands' : ''}</span>
          <span className="v">
            {b.done ? 'finished' : Math.round(100 * b.pos / Math.max(1, b.chars)) + '%'}
            {' '}
            {b.in_hand
              ? <Button className="prs-act" size="sm" onClick={() => onPutDown()}>put it down</Button>
              : <Button className="prs-act" size="sm" onClick={() => onPickUp(b.title)}>hand it to her</Button>}
          </span>
        </div>
      ))}
    </>
  )
}

export default function Presence() {
  const s = usePoll(api.presence, 10000)
  return (
    <div className="pad">
      <Body state={s}>{d => (
        <PresenceView d={d}
                      onEnter={m => api.presenceEnter(m).then(s.refresh)}
                      onLeave={() => api.presenceLeave().then(s.refresh)}
                      onPickUp={t => api.presencePickUp(t).then(s.refresh)}
                      onPutDown={() => api.presencePutDown().then(s.refresh)} />
      )}</Body>
    </div>
  )
}
