import { useEffect, useRef, useState } from 'react'
import { usePoll, Body } from './panel.jsx'
import * as api from '../api.js'

/* MUSIC — one player, two people.
 *
 * The browser decodes; the SERVER holds the intent. So when she calls play_music
 * the audio here starts, and when he clicks a track she can say what is on. The
 * page owns only POSITION, because only it knows where the decoder actually is.
 *
 * The <audio> element is created ONCE and its src is only reassigned when the
 * TRACK changes — not on every poll. Reassigning src mid-play aborts the pending
 * play() promise, which is the same bug that made speech fail on every second
 * reply (see console/speech.js). A player that restarts the song every 4 seconds
 * is a very obvious version of the same mistake.
 */
export default function Music() {
  const s = usePoll(api.music, 4000)
  const audio = useRef(null)
  const curPath = useRef(null)
  const [err, setErr] = useState(null)
  const [q, setQ] = useState('')

  const st = s.data?.state
  const lib = s.data?.library || []

  useEffect(() => {
    if (!audio.current) {
      audio.current = new Audio()
      audio.current.preload = 'metadata'
      audio.current.addEventListener('error', () =>
        setErr('could not play that file'))
    }
    const a = audio.current
    if (!st) return
    const path = st.track?.path || null

    if (path !== curPath.current) {
      curPath.current = path
      setErr(null)
      if (path) {
        a.src = `/v1/music/file?path=${encodeURIComponent(path)}`
        if (st.position_s) a.currentTime = st.position_s
      } else {
        a.removeAttribute('src')
      }
    }
    if (st.playing && a.paused && path) {
      a.play().catch(e => { if (e.name !== 'AbortError') setErr(String(e.message || e)) })
    } else if (!st.playing && !a.paused) {
      a.pause()
    }
  }, [st?.track?.path, st?.playing])

  // let the server know where the decoder actually got to, occasionally
  useEffect(() => {
    const t = setInterval(() => {
      const a = audio.current
      if (a && !a.paused && a.currentTime > 0) {
        api.musicControl({ action: 'position', position_s: a.currentTime }).catch(() => {})
      }
    }, 15000)
    return () => clearInterval(t)
  }, [])

  const send = (action, extra = {}) =>
    api.musicControl({ action, ...extra }).then(() => s.refresh?.()).catch(() => {})

  return (
    <div className="pad music">
      <Body state={s}>{d => {
        const state = d.state
        if (!state.dir_exists) {
          return <div className="muted">
            no music library — nothing at <code>{state.dir}</code>.
            <br />point <code>[music] dir</code> at a folder in the profile.
          </div>
        }
        if (!d.library.length) {
          return <div className="muted">
            the library at <code>{state.dir}</code> is empty. drop some audio in and
            it will appear — mp3, m4a, flac, ogg, opus, wav.
          </div>
        }
        const t = state.track
        return (
          <>
            <div className="now">
              <div className="t">{t ? t.title : 'nothing playing'}</div>
              <div className="a">{t?.artist || (t ? t.album : `${d.library.length} tracks`)}</div>
              {state.changed_by ? <div className="by">put on by {state.changed_by}</div> : null}
              {err ? <div className="err">{err}</div> : null}
            </div>
            <div className="controls">
              <button onClick={() => send(state.playing ? 'pause' : 'play')}>
                {state.playing ? '⏸ pause' : '▶ play'}
              </button>
              <button onClick={() => send('next')}>⏭ next</button>
            </div>
            <input className="find" placeholder="find a track…"
                   value={q} onChange={e => setQ(e.target.value)} />
            <div className="tracks">
              {d.library
                .filter(x => !q || `${x.title} ${x.artist} ${x.album}`
                  .toLowerCase().includes(q.toLowerCase()))
                .slice(0, 200)
                .map(x => (
                  <div key={x.path}
                       className={'track' + (t?.path === x.path ? ' on' : '')}
                       onClick={() => send('track', { path: x.path })}>
                    <span className="tt">{x.title}</span>
                    <span className="ta">{x.artist}</span>
                  </div>
                ))}
            </div>
            {state.queue?.length ? (
              <div className="queue">next: {state.queue.map(x => x.title).join(' · ')}</div>
            ) : null}
          </>
        )
      }}</Body>
    </div>
  )
}
