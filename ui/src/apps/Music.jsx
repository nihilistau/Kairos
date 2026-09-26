import { useEffect, useRef, useState } from 'react'
import { usePoll, Body } from './panel.jsx'
import * as api from '../api.js'
import { Button, Chip, Input, Row, State } from '../kit/parts.jsx'

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
    <div className="pad mus">
      <Body state={s}>{d => <MusicView d={d} err={err} q={q} setQ={setQ} onSend={send} />}</Body>
    </div>
  )
}

/* The window's body, split out so G-ROOM-KIT leg 11 can render it with a fixture. It
 * renders only: the <audio> element, its effects and the position report stay in the
 * default export, because the page owns POSITION and nothing else.
 * Play/pause is the window's one primary; its label says what it will do, so it carries
 * no aria-pressed (a button whose name changes must not also report a pressed state).
 * The controls lost their emoji-presentation characters, which the icon rule
 * retires. A track is a kit Row: a keyboard reaches it now, and the one playing wears a
 * "now" chip, so which track is on is not told by colour alone. */
export function MusicView({ d, err, q, setQ, onSend }) {
  const state = d.state
  if (!state.dir_exists) {
    return (
      <State kind="empty">
        no music library — nothing at <code>{state.dir}</code>.
        <br />point <code>[music] dir</code> at a folder in the profile.
      </State>
    )
  }
  if (!d.library.length) {
    return (
      <State kind="empty">
        the library at <code>{state.dir}</code> is empty. drop some audio in and
        it will appear — mp3, m4a, flac, ogg, opus, wav.
      </State>
    )
  }
  const t = state.track
  return (
    <>
      <div className="mus-now">
        <div className="mus-t">{t ? t.title : 'nothing playing'}</div>
        <div className="mus-a">{t?.artist || (t ? t.album : `${d.library.length} tracks`)}</div>
        {state.changed_by ? <div className="mus-by">{'put on by ' + state.changed_by}</div> : null}
        {err ? <div className="mus-err"><Chip tone="err" wrap>{err}</Chip></div> : null}
      </div>
      <div className="mus-ctl">
        <Button variant="primary" onClick={() => onSend(state.playing ? 'pause' : 'play')}>
          {state.playing ? 'pause' : 'play'}
        </Button>
        <Button onClick={() => onSend('next')}>next</Button>
      </div>
      <Input className="mus-find" aria-label="find a track" placeholder="find a track…"
             value={q} onChange={e => setQ(e.target.value)} />
      <div className="mus-tracks">
        {d.library
          .filter(x => !q || `${x.title} ${x.artist} ${x.album}`
            .toLowerCase().includes(q.toLowerCase()))
          .slice(0, 200)
          .map(x => {
            const on = t?.path === x.path
            return (
              <div key={x.path} className={'mus-track' + (on ? ' on' : '')}>
                {/* THE BUTTON'S NAME (stage-4 final review, M3): the margin between title
                    and artist is not a word break, so it read "RainNils Frahm", and the "now"
                    chip sits outside the button. A hidden separator, and the state in the name. */}
                <Row title={<><span className="mus-tt">{x.title}</span><span className="mus-sr">{' · '}</span>
                              <span className="mus-ta">{x.artist}</span>
                              {on ? <span className="mus-sr">{', now playing'}</span> : null}</>}
                     trail={on ? <Chip tone="accent" dot>now</Chip> : null}
                     onClick={() => onSend('track', { path: x.path })} />
              </div>
            )
          })}
      </div>
      {state.queue?.length ? (
        <div className="mus-queue">next: {state.queue.map(x => x.title).join(' · ')}</div>
      ) : null}
    </>
  )
}
