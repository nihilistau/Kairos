import { usePoll, Body } from './panel.jsx'
import * as api from '../api.js'
import { KnobGroups } from './knobs.jsx'

/* PRESENCE — her modes (2026-08-22, his ask: "a lucid dream / company / narration mode").
 *
 * Narration / Company / Lucid Dream are a KAIROS ACTION that waits its turn — the same
 * presence clock, quiet-after-him and shutdown guards as every other unprompted word,
 * plus its own hourly cap. This window is the picker, the knobs, the shelf she reads
 * from (var/library/), and the honest state: off / next in ~m / reading <title>.
 * Nothing speaks unless he arms it here (or in Settings, same knobs).
 */
export default function Presence() {
  const s = usePoll(api.presence, 10000)
  return (
    <div className="pad">
      <Body state={s}>{d => {
        const st = d.state || {}
        const shelf = d.shelf || []
        const inHand = shelf.find(b => b.in_hand)
        const line = (!st.mode || st.mode === 'off')
          ? <span className="muted">off — she speaks only as kairos allows</span>
          : <span className="good">
              {st.mode}
              {st.next_in_s != null ? ' — next in ~' + Math.max(0, Math.round(st.next_in_s / 60)) + 'm' : ''}
              {inHand ? ' · reading ' + inHand.title : ''}
            </span>
        return (
          <>
            <div className="prs-state">{line}</div>
            {/* MANUAL ENTRY (his ask, 2026-08-22): enter a mode NOW — her first turn comes right
                after her next reply instead of after the idle floor; stop is one click. */}
            <div className="prs-now">
              {['narration', 'company', 'lucid'].map(m => (
                <button key={m} className={st.mode === m ? 'on' : ''}
                        onClick={() => api.presenceEnter(m).then(s.refresh)}>
                  {m === 'narration' ? 'narrate now' : m === 'company' ? 'keep me company' : 'dream now'}
                </button>
              ))}
              {st.mode && st.mode !== 'off'
                ? <button className="prs-stop" onClick={() => api.presenceLeave().then(s.refresh)}>stop</button>
                : null}
            </div>
            <KnobGroups only={['Presence — her modes']} />
            <h4 className="prs-shelf-h">the shelf <span className="muted">(var/library/ — drop .txt / .md / .epub in)</span></h4>
            {!shelf.length ? <div className="muted">empty</div> : shelf.map(b => (
              <div key={b.title} className="row prs-book">
                <span className="k">{b.title}{b.in_hand ? ' · in her hands' : ''}</span>
                <span className="v">
                  {b.done ? 'finished' : Math.round(100 * b.pos / Math.max(1, b.chars)) + '%'}
                  {' '}
                  {b.in_hand
                    ? <button onClick={() => api.presencePutDown().then(s.refresh)}>put it down</button>
                    : <button onClick={() => api.presencePickUp(b.title).then(s.refresh)}>hand it to her</button>}
                </span>
              </div>
            ))}
          </>
        )
      }}</Body>
    </div>
  )
}
