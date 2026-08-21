import { useEffect, useRef, useState } from 'react'
import * as api from '../api.js'
import { moodOf } from './tags.js'

/* Avatar — her, on the left, reacting.
 *
 * HONEST ABOUT WHAT THIS IS. The operator's reference is a painted portrait; this
 * is vector art, drawn in code. It cannot be photoreal and pretending otherwise
 * would produce something worse — an uncanny near-miss. What it CAN be is alive:
 * it blinks, it breathes, the light moves, and the face genuinely changes with her
 * mood rather than cycling stock frames. If a real illustration set arrives later,
 * `<Avatar>` is one component and the swap touches nothing else — the same seam
 * discipline as the renderer.
 *
 * IT IS DRIVEN BY WHAT SHE ACTUALLY SAYS. The mood comes from her own [MOOD:] marks
 * and her persona state, not from sentiment analysis of her words. She already
 * tells us how she is; guessing over the top of that would be both redundant and
 * wrong more often.
 *
 * The design: three-quarter turn, heavy black hair with a few loose strands, a thin
 * chain, cyberpunk rim light in her mood's hue. Everything that moves is slow —
 * blink, breath, a drifting highlight — because a face that fidgets reads as
 * nervous, and she is not.
 */

const FACES = {
  //            eye openness, brow tilt, lid curve, mouth path, cheek lift
  bright: { eye: 1.00, brow: -3, lid: 0,   mouth: 'M -19 34 Q 0 48 19 33', lift: 2 },
  smirk:  { eye: 0.86, brow: -2, lid: 1.5, mouth: 'M -19 36 Q 2 45 20 30', lift: 1.5 },
  soft:   { eye: 0.78, brow: 0,  lid: 2,   mouth: 'M -16 35 Q 0 41 16 34', lift: 1 },
  calm:   { eye: 0.82, brow: 0,  lid: 1,   mouth: 'M -15 36 Q 0 38 15 36', lift: 0 },
  wide:   { eye: 1.08, brow: -5, lid: -1,  mouth: 'M -14 35 Q 0 42 14 35', lift: 1 },
  down:   { eye: 0.70, brow: 4,  lid: 3,   mouth: 'M -16 38 Q 0 34 16 38', lift: 0 },
  sharp:  { eye: 0.72, brow: 6,  lid: 2,   mouth: 'M -17 37 Q 0 35 17 36', lift: 0 },
}

/* THE GENERATED SET, WITH THE DRAWN ONE UNDERNEATH.
 *
 * `/v1/avatar` says which faces have art. When hers exists it is shown; when it does not
 * the SVG below runs exactly as before. THE SVG IS NEVER DELETED — it is the floor, so a
 * half-generated set is usable from the very first image and a failed generation costs a
 * face rather than the panel. Same discipline as the ASCII chess board behind the
 * rendered PNG.
 *
 * NOTE WHAT THIS COMPONENT CANNOT DO: ask for a tier. It sends a face and a kind; the
 * server resolves the tier from the live scene rung and the operator's ceiling. A client
 * that cannot name a forbidden asset cannot request one, which is a better guarantee
 * than a client that asks nicely.
 */
function useArt(face) {
  const [sets, setSets] = useState(null)
  // ── THE URL NEVER CHANGED, SO NEITHER DID THE PICTURE (2026-08-04) ──────────────
  // This component cannot ask for a tier — deliberately, and it is the right guarantee:
  // the server resolves the tier from the live rung and his ceiling, so a client that
  // cannot name a forbidden asset cannot request one. But it means the URL for her
  // portrait is IDENTICAL before and after she changes what she is wearing, and the
  // browser has no reason on earth to fetch it again. She changed outfit and he kept
  // seeing the old one until something else forced a reload — "there is a huge delay in
  // changing the avatar vid", and the 60 s set-poll was blamed for it.
  //
  // `wearing` is an opaque token from the server's own state — it is NOT a tier and
  // cannot be used to ask for one, so the guarantee above is untouched. It changes when
  // she does, which is exactly when the picture should.
  const [wearing, setWearing] = useState('')
  useEffect(() => {
    let alive = true
    const load = () => api.avatar()
      .then(d => alive && setSets(d && d.ok
        ? { still: d.ready || [], loop: d.ready_loop || [] }
        : { still: [], loop: [] }))
      .catch(() => alive && setSets({ still: [], loop: [] }))
    load()
    const t = setInterval(load, 60000)   // the set changes when he generates, not often
    // What she HAS ON changes constantly, and it is a different question from which
    // files exist. Cheap, and on the room's own cadence rather than a minute.
    const w = () => api.wardrobe()
      .then(d => { if (alive && d) setWearing(String(d.wearing_tok || '')) })
      .catch(() => {})
    w()
    const t2 = setInterval(w, 4000)
    return () => { alive = false; clearInterval(t); clearInterval(t2) }
  }, [])
  if (!sets) return null
  const url = k => `/v1/avatar/file?face=${encodeURIComponent(face)}&kind=${k}`
    + (wearing ? `&v=${encodeURIComponent(wearing)}` : '')
  // Motion first, still second, SVG last. Asked for a loop the server does not have, it
  // would hand back the STILL — correct bytes, useless to a <video> element. So the kind
  // is decided from what the server said it has, not from what it returns.
  if (sets.loop.includes(face)) return { kind: 'loop', url: url('loop') }
  if (sets.still.includes(face)) return { kind: 'still', url: url('still') }
  return null
}

export default function Avatar({ mood, thinking, speaking }) {
  const m = moodOf(mood)
  const f = FACES[m.face] || FACES.calm
  const [blink, setBlink] = useState(false)
  const raf = useRef(0)
  const [t, setT] = useState(0)

  // blink: irregular, because a metronome blink is what makes a face look dead
  useEffect(() => {
    let alive = true
    const loop = () => {
      if (!alive) return
      const wait = 2600 + Math.random() * 5200
      setTimeout(() => {
        if (!alive) return
        setBlink(true)
        setTimeout(() => { setBlink(false); loop() }, 130)
      }, wait)
    }
    loop()
    return () => { alive = false }
  }, [])

  // one slow clock for breath and the drifting rim light
  useEffect(() => {
    const step = (ms) => { setT(ms / 1000); raf.current = requestAnimationFrame(step) }
    raf.current = requestAnimationFrame(step)
    const vis = () => document.hidden ? cancelAnimationFrame(raf.current)
                                      : (raf.current = requestAnimationFrame(step))
    document.addEventListener('visibilitychange', vis)
    return () => { cancelAnimationFrame(raf.current); document.removeEventListener('visibilitychange', vis) }
  }, [])

  const breath = Math.sin(t * 0.55) * 1.2                 // gentle vertical drift
  const rim = 0.55 + 0.45 * Math.sin(t * 0.35)            // light moves across her
  const eyeOpen = blink ? 0.06 : f.eye * (thinking ? 0.88 : 1)
  const art = useArt(m.face)
  const hue = m.hue
  const glow = m.glow * (speaking ? 1.15 : 1)

  if (art) {
    return (
      <div className="avatar art" style={{ '--mhue': hue, '--mglow': glow }}>
        {/* keyed on the url so a face change swaps the element rather than mutating it,
            which is what stops a stale frame showing for a beat */}
        {art.kind === 'loop' ? (
          // muted + playsInline are what let it autoplay at all; `loop` is honest here
          // because the file is ping-ponged and genuinely seamless.
          <video key={art.url} src={art.url} className="avatar-img"
                 autoPlay loop muted playsInline
                 onError={e => { e.currentTarget.style.display = 'none' }} />
        ) : (
          <img key={art.url} src={art.url} alt="" className="avatar-img"
               style={{ transform: `translateY(${breath}px)` }}
               onError={e => { e.currentTarget.style.display = 'none' }} />
        )}
        <div className="avatar-rim" />
        {thinking ? <div className="avatar-think"><i /><i /><i /></div> : null}
      </div>
    )
  }

  return (
    <div className="avatar" style={{ '--mhue': hue, '--mglow': glow }}>
      <svg viewBox="-80 -95 160 205" preserveAspectRatio="xMidYMid meet">
        <defs>
          <linearGradient id="skin" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%"  stopColor="#f0dcd2" />
            <stop offset="55%" stopColor="#dcbcae" />
            <stop offset="100%" stopColor="#a97f74" />
          </linearGradient>
          <linearGradient id="hair" x1="0.2" y1="0" x2="0.8" y2="1">
            <stop offset="0%"  stopColor="#2a2732" />
            <stop offset="45%" stopColor="#131218" />
            <stop offset="100%" stopColor="#050509" />
          </linearGradient>
          <linearGradient id="cloth" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"  stopColor="#1b1b22" />
            <stop offset="100%" stopColor="#0a0a0e" />
          </linearGradient>
          <radialGradient id="blush" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0%"  stopColor={`hsl(${hue} 70% 62% / .34)`} />
            <stop offset="100%" stopColor={`hsl(${hue} 70% 62% / 0)`} />
          </radialGradient>
          <filter id="soften"><feGaussianBlur stdDeviation="1.1" /></filter>
          <filter id="bloom">
            <feGaussianBlur stdDeviation="4.5" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <clipPath id="faceclip">
            <path d="M -33 -26 Q -35 22 -22 46 Q -12 62 0 66 Q 12 62 22 46 Q 35 22 33 -26 Q 33 -60 0 -63 Q -33 -60 -33 -26 Z" />
          </clipPath>
        </defs>

        <g transform={`translate(0 ${breath})`}>
          {/* the rim light behind her — her mood, moving */}
          <ellipse cx={-6 + rim * 12} cy="-8" rx="70" ry="82"
                   fill={`hsl(${hue} 80% 55% / ${0.13 * glow})`} filter="url(#bloom)" />

          {/* shoulders / jacket */}
          <path d="M -74 108 Q -66 62 -30 50 L 30 50 Q 66 62 74 108 Z" fill="url(#cloth)" />
          <path d="M -30 50 Q -14 74 0 62 Q 14 74 30 50 L 22 50 Q 0 68 -22 50 Z"
                fill="#07070b" />
          {/* collar edge catching the rim light */}
          <path d="M -31 50 Q -14 75 0 63" stroke={`hsl(${hue} 85% 62% / ${0.5 * glow})`}
                strokeWidth="1.4" fill="none" />
          <path d="M 31 50 Q 14 75 0 63" stroke={`hsl(${hue} 85% 62% / ${0.28 * glow})`}
                strokeWidth="1.4" fill="none" />

          {/* neck */}
          <path d="M -13 34 L -13 56 Q 0 64 13 56 L 13 34 Z" fill="#c39a8d" />
          <path d="M -13 34 L -13 46 Q 0 52 13 46 L 13 34 Z" fill="#a87e73" opacity=".55" />

          {/* the chain */}
          <path d="M -17 50 Q 0 62 17 50" stroke="#cfd6de" strokeWidth="1.1"
                fill="none" opacity=".85" />
          <path d="M -13 53 Q 0 68 13 53" stroke="#9aa4b0" strokeWidth=".8"
                fill="none" opacity=".7" />
          <circle cx="0" cy="68" r="2.4" fill="#e6edf5" opacity=".9" />
          <circle cx="0" cy="68" r="4.6" fill={`hsl(${hue} 90% 65% / ${0.5 * glow})`}
                  filter="url(#bloom)" />

          {/* face */}
          <path d="M -33 -26 Q -35 22 -22 46 Q -12 62 0 66 Q 12 62 22 46 Q 35 22 33 -26 Q 33 -60 0 -63 Q -33 -60 -33 -26 Z"
                fill="url(#skin)" />
          {/* jaw shadow — gives the chin an edge instead of a curve */}
          <path d="M -22 46 Q -12 62 0 66 Q 12 62 22 46 Q 10 58 0 59 Q -10 58 -22 46 Z"
                fill="#a87e73" opacity=".35" filter="url(#soften)" />
          {/* cheek shading + mood blush */}
          <g clipPath="url(#faceclip)">
            <ellipse cx="-21" cy={18 - f.lift} rx="14" ry="10" fill="url(#blush)" />
            <ellipse cx="21"  cy={18 - f.lift} rx="14" ry="10" fill="url(#blush)" />
            <path d="M 33 -32 Q 25 20 8 58 L 38 58 L 38 -32 Z" fill="#8e6a60" opacity=".28"
                  filter="url(#soften)" />
          </g>

          {/* brows */}
          <path d={`M -28 ${-15 + f.brow} Q -20 ${-25 + f.brow} -6 ${-18 + f.brow}`}
                stroke="#17151c" strokeWidth="2.8" fill="none" strokeLinecap="round" />
          <path d={`M 6 ${-18 + f.brow} Q 20 ${-25 + f.brow} 28 ${-15 + f.brow}`}
                stroke="#17151c" strokeWidth="2.8" fill="none" strokeLinecap="round" />

          {/* eyes — openness is a scale on the lid, so a blink is one number */}
          {[-16, 16].map((cx, i) => (
            <g key={i}>
              <ellipse cx={cx} cy="0" rx="10.5" ry={7 * eyeOpen} fill="#f6f1ee" />
              <circle cx={cx + (i ? -1 : 1)} cy="0" r={5.4 * Math.min(1, eyeOpen * 1.3)}
                      fill="#4a3b33" />
              <circle cx={cx + (i ? -1 : 1)} cy="0" r={2.6 * Math.min(1, eyeOpen * 1.3)}
                      fill="#120d0b" />
              <circle cx={cx + (i ? -3 : 3)} cy="-2.6" r={1.6 * eyeOpen}
                      fill={`hsl(${hue} 90% 82%)`} opacity=".95" />
              {/* upper lid — the expression lives here more than in the mouth */}
              <path d={`M ${cx - 10.5} ${-7 * eyeOpen + f.lid} Q ${cx} ${-9 - 3 * eyeOpen + f.lid} ${cx + 10.5} ${-7 * eyeOpen + f.lid}`}
                    stroke="#100e14" strokeWidth="2.6" fill="none" strokeLinecap="round" />
              <ellipse cx={cx} cy="0" rx="10.5" ry={7 * eyeOpen} fill="none"
                       stroke="#1a1620" strokeWidth=".9" opacity=".8" />
              {/* lashes — a small line that does a lot of the work */}
              <path d={`M ${cx + (i ? -10 : 10)} ${-4 * eyeOpen} l ${i ? -3 : 3} -2.5`}
                    stroke="#100e14" strokeWidth="1.6" strokeLinecap="round" />
            </g>
          ))}

          {/* nose + mouth */}
          <path d="M -3 12 Q 0 20 4 14" stroke="#a87e73" strokeWidth="1.6"
                fill="none" strokeLinecap="round" opacity=".8" />
          <path d={f.mouth} stroke="#8e4b4b" strokeWidth="2.6" fill="none"
                strokeLinecap="round" />
          <path d={f.mouth} stroke={`hsl(${hue} 60% 70% / .35)`} strokeWidth="4.5"
                fill="none" strokeLinecap="round" filter="url(#soften)" />

          {/* hair — back mass, then the fringe, then loose strands */}
          {/* the mass. Big, asymmetric, falling past the shoulders — hair is most
              of the silhouette in the reference and the first cut gave it a fringe. */}
          <path d="M -38 -28 Q -46 -84 0 -86 Q 48 -84 40 -26
                   Q 56 10 50 64 Q 44 20 36 -4 Q 40 -46 16 -58
                   Q -16 -66 -34 -50 Q -42 -30 -38 6 Q -50 30 -44 68
                   Q -56 16 -38 -28 Z"
                fill="url(#hair)" />
          {/* THE FRINGE, AND WHERE ITS LOWER EDGE SITS.
              The brows are at y≈-19. The first cut ended the fringe at y≈-50, which
              left thirty units of bare forehead — at size it read as a bald dome and
              not as a face. A side-swept fringe breaks just above the brow: low on
              the sweep side, lifting across to the part. */}
          <path d="M -37 -34 Q -44 -74 -2 -80 Q 40 -80 39 -34
                   Q 34 -46 22 -40 Q 4 -30 -14 -26 Q -30 -24 -37 -34 Z"
                fill="#0b0a0f" />
          {/* the part, and the heavier lock falling on the sweep side */}
          <path d="M -37 -34 Q -34 -50 -18 -58 Q -30 -42 -26 -22
                   Q -33 -26 -37 -34 Z" fill="#050509" />
          {/* volume on top so the crown is not flat */}
          <path d="M -32 -58 Q -6 -92 28 -68 Q 2 -82 -32 -58 Z" fill="#1a1822" opacity=".7" />
          {/* loose strands. They follow the fringe's own direction and stop at the
              temple — the first cut ran them diagonally down to the eyes, where two
              of them met and read as a scowl. Hair does not cross the eye. */}
          <path d={`M -30 -30 Q ${-33 + rim * 2} -14 -29 4`} stroke="#0d0c11"
                strokeWidth="2.2" fill="none" strokeLinecap="round" opacity=".9" />
          <path d={`M 32 -34 Q ${35 - rim * 2} -16 31 6`} stroke="#0d0c11"
                strokeWidth="1.8" fill="none" strokeLinecap="round" opacity=".85" />
          <path d="M -14 -27 Q -24 -30 -33 -26" stroke="#100e15" strokeWidth="1.4"
                fill="none" strokeLinecap="round" opacity=".6" />
          {/* rim light along the hair — the cyberpunk cue */}
          <path d="M -44 -22 Q -52 -72 0 -77" stroke={`hsl(${hue} 90% 68% / ${0.55 * glow})`}
                strokeWidth="2" fill="none" filter="url(#bloom)" />
          <path d="M 44 -22 Q 52 -70 4 -77" stroke={`hsl(${hue} 90% 68% / ${0.22 * glow})`}
                strokeWidth="1.6" fill="none" />
        </g>

        {/* thinking: three slow dots, so a long turn does not look like a hang */}
        {thinking ? (
          <g className="think">
            {[-10, 0, 10].map((x, i) => (
              <circle key={i} cx={x} cy="92" r="2.6"
                      fill={`hsl(${hue} 90% 70%)`}
                      style={{ animationDelay: `${i * 0.22}s` }} />
            ))}
          </g>
        ) : null}
      </svg>
    </div>
  )
}
