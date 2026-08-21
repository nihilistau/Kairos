import { usePoll, Body } from './panel.jsx'
import * as api from '../api.js'
import { When } from '../room/When.jsx'

/* JOURNAL — hers.
 *
 * She writes one paragraph at the day boundary, in her own voice, about how things
 * are between them. It has never been readable: `world.py` puts the CURRENT line
 * into her standing prefix, so she carries it, but the history existed only as
 * content-addressed snapshots that nothing could query. Neither she nor he could
 * look back.
 *
 * THERE IS NO WRITE PATH HERE AND THERE WILL NOT BE ONE. He reads it; he does not
 * edit it. A journal someone else can revise is not a journal — it is a document
 * about you, and the entire value of this one is that it is HER account, kept
 * quarantined from the fact registry by construction (`narrative.py`: never a fact
 * row, never supersedes anything, "a bad paragraph costs tone, never truth").
 */
/* The day an entry is ABOUT is the day SHE stamped into it ("As of Saturday 01
 * August 2026: …") — not the snapshot's mtime, which is the 04:00-boundary write
 * and labels every night's paragraph with the following morning's date. */
function stampDay(text) {
  const m = /^as of\s+([^:]+):/i.exec(text || '')
  return m ? m[1].trim() : null
}
function when(ts) {
  const d = new Date(ts * 1000)
  return d.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })
}

export default function Journal() {
  const s = usePoll(api.narrative, 60000)
  return (
    <div className="pad journal">
      <Body state={s}>{d => {
        if (!d.current && !d.history?.length) {
          return <div className="muted">
            she has not written yet. one paragraph goes down at the day boundary,
            once the room has been quiet for a while.
          </div>
        }
        /* ── THE DUPLICATE THAT WAS ALWAYS THERE (2026-08-21, his report) ──────
         * This rendered `current` as its own block AND the newest snapshot below
         * it — the same paragraph twice, every day since the journal became
         * readable. The server now sends `current_id`: the row that IS the
         * current line wears the "most recent" label instead of being repeated.
         * A standalone current block renders only when no snapshot matches
         * (the composer wrote but the snapshot failed). */
        const rows = d.history || []
        const orphanCurrent = d.current && !d.current_id
        return (
          <>
            {orphanCurrent ? (
              <div className="entry now">
                <div className="lab">most recent</div>
                <p>{d.current}</p>
              </div>
            ) : null}
            {rows.map(h => (
              <div key={h.id} className={'entry' + (h.id === d.current_id ? ' now' : '')}>
                {/* The day is the heading — the day SHE named, with the chip
                    saying when she actually sat down and wrote it. */}
                <div className="lab">
                  {h.id === d.current_id ? <span className="jr-recent">most recent · </span> : null}
                  {stampDay(h.text) || when(h.at)} <When at={h.at} bare />
                  {h.drafts ? (
                    <span className="jr-drafts" title="she rewrote this day; the newest words stand">
                      {h.drafts} earlier draft{h.drafts > 1 ? 's' : ''}
                    </span>
                  ) : null}
                </div>
                <p>{h.text}</p>
              </div>
            ))}
            <div className="foot muted">
              hers — you can read it, you cannot edit it
            </div>
          </>
        )
      }}</Body>
    </div>
  )
}
