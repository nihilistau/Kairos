import Backdrop2D from './Backdrop2D.jsx'
import { describeRoom } from './describe.js'
import { useMood } from './useMood.js'
import { usePoll } from '../apps/panel.jsx'
import * as api from '../api.js'

/* ROOM VIEW — the room's weather, in a frame you can move (2026-09-23, his ask).
 *
 * The full-bleed backdrop STAYS. His call, and the right one: closing this window
 * should cost you a framed view, not the room's ambience. So this is a second render
 * of the same description rather than a relocation of the first, and the two cannot
 * disagree because `describeRoom` is the only thing either of them reads.
 *
 * WHAT IT ADDS over the paint behind everything: it names what it is showing. The
 * backdrop is deliberately something you notice having changed rather than something
 * you look at — which makes "why is the room green" unanswerable. Here the phase, her
 * mood and whether anyone is about are written down under the picture.
 *
 * It owns no state and fetches nothing a panel does not already fetch. A renderer that
 * reaches for its own endpoint becomes the second place the room's mood lives, which is
 * the bug roomMood.js exists to avoid.
 */
export default function RoomView() {
  const beat = usePoll(api.pulse, 5000)
  const pulse = beat.data
  // THE SHELL'S PRECEDENCE, not a copy of it: room/moodTheme.js decides for both.
  const m = useMood(pulse)
  const shown = { ...(pulse || {}), her: { ...(pulse?.her || {}), mood: m.word } }
  const room = describeRoom(shown)

  return (
    <div className="rv-wrap">
      <div className="rv-stage">
        <Backdrop2D room={room} className="rv-canvas" />
        {m.thinking ? <div className="rv-think">she is thinking</div> : null}
      </div>
      <div className="rv-read">
        <span className="rv-k">phase</span><span className="rv-v">{room.phase}</span>
        <span className="rv-k">mood</span><span className="rv-v">{room.mood || 'unsaid'}</span>
        <span className="rv-k">presence</span>
        <span className="rv-v">{room.alone ? 'she is on her own' : 'someone is here'}</span>
        <span className="rv-k">energy</span>
        <span className="rv-v">{Math.round((room.energy || 0) * 100)}%</span>
      </div>
    </div>
  )
}
