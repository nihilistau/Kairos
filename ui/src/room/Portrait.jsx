import { useEffect, useRef, useState } from 'react'
import Avatar from './Avatar.jsx'
import * as api from '../api.js'

/* THE PORTRAIT — her, on the canvas, where he put her.
 *
 * NOT "Stage": apps/Stage.jsx is the ROLEPLAY stage and owns the `stg-` prefix.
 * G-ROOM-CSS caught the collision on the first build, which is the whole reason
 * that gate exists. Two things with one name in one room is the bug, not the
 * class list.
 *
 * She was a 46px circle at the foot of the dock. That is a contact chip, not a person:
 * the generated set is a PORTRAIT, painted at a 3:4 rectangle, and cropping it to a
 * circle threw away most of the frame — the chains, the rain-blurred city, everything
 * below the jaw. The operator's words were "make it a rectangle again, slightly larger
 * than it was before, actually on the canvas".
 *
 * MOVABLE AND RESIZABLE, AND IT REMEMBERS. Position and size persist to localStorage,
 * because a panel that resets to the corner every reload is one he stops arranging. It
 * defaults to the top right — the space he circled on the screenshot.
 *
 * IT SHOWS WHAT SHE CHOSE. When she has put a clip on his screen this plays it; otherwise
 * it is her face at whatever she is wearing. The tier is never named by this component —
 * it asks the server what to show and the server resolves it under his ceiling, so a
 * gated asset is unrequestable rather than requested-and-refused.
 */
const KEY = 'kairos.portrait.box'
const MIN_W = 180, MIN_H = 200

function load() {
  try {
    const b = JSON.parse(localStorage.getItem(KEY) || 'null')
    if (b && typeof b.w === 'number') return b
  } catch (_) { /* a corrupt box must not cost her a stage */ }
  return null
}

export default function Portrait({ mood, thinking }) {
  const [box, setBox] = useState(() => load() || {
    x: Math.max(120, (window.innerWidth || 1280) - 400), y: 24, w: 340, h: 440,
  })
  const [wd, setWd] = useState(null)
  const drag = useRef(null)

  useEffect(() => {
    let alive = true
    const load = () => api.wardrobe().then(d => alive && setWd(d)).catch(() => {})
    load()
    const t = setInterval(load, 5000)
    return () => { alive = false; clearInterval(t) }
  }, [])

  const save = (b) => { setBox(b); try { localStorage.setItem(KEY, JSON.stringify(b)) } catch (_) {} }

  /* SHE MUST ALWAYS BE REACHABLE. The default is computed from innerWidth at first
   * render, and a stored box was saved against whatever screen he had last time — so
   * either can land her entirely off the canvas, where there is no way to drag her back.
   * Measured: default x=942 in a 420px-wide window. Clamped on mount and on every
   * resize, keeping a grabbable strip on screen rather than snapping her to a corner. */
  useEffect(() => {
    const clamp = () => setBox(b => {
      const maxX = Math.max(0, (window.innerWidth || 1280) - 90)
      const maxY = Math.max(0, (window.innerHeight || 800) - 70)
      const w = Math.min(b.w, Math.max(MIN_W, window.innerWidth - 20))
      const h = Math.min(b.h, Math.max(MIN_H, window.innerHeight - 20))
      const x = Math.min(Math.max(0, b.x), maxX)
      const y = Math.min(Math.max(0, b.y), maxY)
      if (x === b.x && y === b.y && w === b.w && h === b.h) return b
      const nb = { x, y, w, h }
      try { localStorage.setItem(KEY, JSON.stringify(nb)) } catch (_) {}
      return nb
    })
    clamp()
    window.addEventListener('resize', clamp)
    return () => window.removeEventListener('resize', clamp)
  }, [])

  const onDown = (e) => {
    if (e.target.closest('button') || e.target.closest('.por-grip')) return
    e.preventDefault()
    // The grab point and the box AT THE MOMENT OF GRABBING. Reading `box` inside the
    // move handler instead would compound each frame's delta onto the previous one and
    // the panel would accelerate away from the cursor.
    drag.current = { mx: e.clientX, my: e.clientY, ...box }
    const onMove = (ev) => {
      const d = drag.current; if (!d) return
      save({ w: d.w, h: d.h,
             x: Math.max(0, d.x + (ev.clientX - d.mx)),
             y: Math.max(0, d.y + (ev.clientY - d.my)) })
    }
    const up = () => {
      drag.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', up)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', up)
  }

  const onResize = (e) => {
    e.preventDefault(); e.stopPropagation()
    const s = { mx: e.clientX, my: e.clientY, ...box }
    const onMove = (ev) => save({
      x: s.x, y: s.y,
      w: Math.max(MIN_W, s.w + (ev.clientX - s.mx)),
      h: Math.max(MIN_H, s.h + (ev.clientY - s.my)),
    })
    const up = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', up)
      document.body.classList.remove('resizing')
    }
    document.body.classList.add('resizing')
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', up)
  }

  const clip = wd && wd.clip
  const look = wd && wd.look
  /* THE CAPTION DESCRIBES WHAT IS IN THE FRAME. It used to be `tier_words[shown]`
     unconditionally, so with a look on, the picture was the silver nightie and the words
     underneath said "a black lace bra and panties" — the outfit under it. The server
     computes this once now (wardrobe.wearing_now) in the same precedence this component
     paints in, which is the only arrangement where the two cannot drift. */
  const wearing = wd && wd.wearing_now
  return (
    <div className="por" style={{ left: box.x, top: box.y, width: box.w, height: box.h }}
         onMouseDown={onDown}>
      <div className="por-frame">
        {clip ? (
          /* SHE PUT THIS HERE. It loops and it is muted by default — a video that
             starts talking at him from the corner of the room is a jump-scare, not
             an intimacy. */
          <video className="por-clip" key={clip} autoPlay loop muted playsInline
                 src={`/v1/wardrobe/file?id=${encodeURIComponent(clip)}`} />
        ) : look ? (
          /* A LOOK SHE ASKED FOR AND IS WEARING. Ranked under a clip because a clip is
             something she deliberately PUT on his screen, while a look is just what she
             has on — the more deliberate act wins the frame.
             It BREATHES when the loop was grown from it, and falls back to the still
             when it was not: a look with no motion is still a look. */
          (wd.looks || []).some(l => l.id === look && l.moves) ? (
            <video className="por-look" key={look + ':loop'} autoPlay loop muted playsInline
                   src={`/v1/wardrobe/look?id=${encodeURIComponent(look)}&kind=loop`} />
          ) : (
            <img className="por-look" key={look} alt=""
                 src={`/v1/wardrobe/look?id=${encodeURIComponent(look)}`} />
          )
        ) : (
          <Avatar mood={mood} thinking={thinking} speaking={false} />
        )}
      </div>
      <div className="por-foot">
        <span className="por-mood">{mood || '—'}</span>
        {wearing ? <span className="por-wear" title={wearing.about}>{wearing.words}</span> : null}
        {/* the "held by your ceiling" badge left 2026-08-24 (audit R4): resolve()
            returns clamped:false as a CONSTANT since tiers stopped being a ladder —
            this branch could never render, and it was the last reader of the
            tier_words back-compat key the server was waiting to delete. */}
        {clip ? (
          <button className="por-stop" title="take it down"
                  onClick={() => api.wardrobeSet({ clip: '', by: 'him' }).then(setWd)}>×</button>
        ) : null}
      </div>
      <div className="por-grip" onMouseDown={onResize} title="resize" />
    </div>
  )
}
