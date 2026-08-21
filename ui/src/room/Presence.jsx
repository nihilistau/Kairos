import { useEffect, useRef, useState } from 'react'

/* Presence — she is in the room whether or not he is typing.
 *
 * The single thing that separates a chat window from a place: in a chat window
 * nothing exists between messages. Here there is a slow light that breathes at her
 * mood's tempo, and occasionally the room says something true and quiet — the eye
 * looked, she wrote her day down, a backup landed.
 *
 * THE RULES, because ambient text is one bad decision away from being clippy:
 *  - It only ever states something that ACTUALLY HAPPENED, from the pulse. It never
 *    invents, never prompts, never asks a question.
 *  - It is never in her voice. She speaks in the chat; this is the room's own
 *    reporting, and blurring the two would put words in her mouth she did not say.
 *  - It appears slowly, sits, and fades. Nothing blinks, nothing demands.
 *  - It says nothing at all rather than repeating itself.
 */
export default function Presence({ pulse }) {
  const [note, setNote] = useState(null)
  const seen = useRef({})

  useEffect(() => {
    const p = pulse || {}
    const pres = p.presence || {}
    // Each candidate has a stable identity so it is announced ONCE, ever.
    const cands = []
    if (pres.ambient_last && pres.ambient_last_at) {
      cands.push({ id: 'eye:' + pres.ambient_last_at,
                   text: pres.ambient_last })
    }
    if (p.clock?.consolidated_today && p.clock?.last_consolidated_day) {
      cands.push({ id: 'journal:' + p.clock.last_consolidated_day,
                   text: 'she wrote the day down' })
    }
    if (p.backup?.newest) {
      cands.push({ id: 'backup:' + p.backup.newest, text: 'everything backed up' })
    }
    if (p.research?.inflight) {
      cands.push({ id: 'look:' + (p.research.query || 'now'),
                   text: 'she is looking something up' })
    } else if (p.research?.title) {
      cands.push({ id: 'looked:' + p.research.title,
                   text: 'she looked something up' })
    }
    const fresh = cands.find(c => !seen.current[c.id])
    if (!fresh) return
    seen.current[fresh.id] = true
    setNote(fresh)
    const t = setTimeout(() => setNote(null), 14000)
    return () => clearTimeout(t)
  }, [pulse])

  const her = (pulse || {}).her || {}
  const warm = (pulse || {}).presence?.warm

  return (
    <div className="presence">
      <div className={'her-light' + (warm ? ' warm' : '')}
           title={warm ? 'she is here' : 'still waking up'} />
      <div className="her-state">
        {her.mood ? <span className="mood">{her.mood}</span> : null}
        {her.voice ? <span className="voice">{her.voice}</span> : null}
      </div>
      {note ? <div className="note" key={note.id}>{note.text}</div> : null}
    </div>
  )
}
