import { useEffect, useRef } from 'react'

/* Backdrop2D — the room's weather.
 *
 * A slow field of drifting light behind everything, driven by the room description
 * (phase of day, her mood, whether anyone is here). It should read as WEATHER, not
 * decoration: something you notice having changed rather than something asking to
 * be looked at. If it draws attention to itself it has failed.
 *
 * Constraints that shaped it:
 *  - It must never compete with text. Everything here sits at very low alpha over
 *    a near-black base; the chat is the only thing with contrast.
 *  - It must cost nothing when nobody is looking. `requestAnimationFrame` stops on
 *    tab blur and on `prefers-reduced-motion`, and the particle count scales with
 *    the viewport rather than being a fixed 200 that melts a laptop.
 *  - It must degrade to a still image, not a blank one. If the pulse never arrives,
 *    `describeRoom` returns sane defaults and this paints a quiet night.
 *
 * The browser's GPU is free here — the 2060 constraint is CUDA and Gemma's, and
 * canvas compositing does not touch it.
 */

// mood -> (hue, saturation). Her state colours the room; the clock only dims it.
const MOODS = {
  peaceful: [190, 38], playful: [ 40, 55], wistful: [265, 34],
  tender:   [330, 40], sharp:   [  8, 50], quiet:   [210, 26],
  warm:     [ 30, 45], curious: [160, 42], flirty:  [320, 46],
}
const PHASE_DIM = { night: 0.55, dawn: 0.85, day: 1.0, dusk: 0.8 }

export default function Backdrop2D({ room }) {
  const ref = useRef(null)
  const state = useRef({ blobs: [], t: 0, w: 0, h: 0 })
  const live = useRef(room)
  live.current = room                       // read fresh each frame, no re-subscribe

  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const ctx = cv.getContext('2d', { alpha: false })
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let raf = 0
    let running = true

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const w = cv.clientWidth, h = cv.clientHeight
      cv.width = Math.max(1, w * dpr); cv.height = Math.max(1, h * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const s = state.current
      s.w = w; s.h = h
      // scale with the viewport — a fixed count melts a small laptop and looks
      // sparse on a big screen
      const n = Math.max(5, Math.min(14, Math.round((w * h) / 190000)))
      s.blobs = Array.from({ length: n }, (_, i) => ({
        x: Math.random() * w, y: Math.random() * h,
        r: 120 + Math.random() * 260,
        vx: (Math.random() - 0.5) * 0.05,
        vy: (Math.random() - 0.5) * 0.04,
        ph: Math.random() * Math.PI * 2,
        tint: i % 3,
      }))
    }
    resize()
    window.addEventListener('resize', resize)

    const draw = (ms) => {
      if (!running) return
      const s = state.current
      const r = live.current || {}
      s.t = ms / 1000

      const [hue, sat] = MOODS[r.mood] || MOODS.quiet
      const dim = PHASE_DIM[r.phase] ?? 0.7
      const energy = Math.max(0.15, Math.min(1, r.energy ?? 0.4))

      // base — never pure black, so the blobs have something to sit in
      ctx.fillStyle = `hsl(${hue} 22% ${2.5 + dim * 1.6}%)`
      ctx.fillRect(0, 0, s.w, s.h)

      // one slow breath for the whole room, so it feels like one thing
      const breath = 0.5 + 0.5 * Math.sin(s.t * (r.breath ?? 0.11) * Math.PI * 2)

      ctx.globalCompositeOperation = 'lighter'
      for (const b of s.blobs) {
        if (!reduced) {
          b.x += b.vx * (0.4 + energy); b.y += b.vy * (0.4 + energy)
          if (b.x < -b.r) b.x = s.w + b.r
          if (b.x > s.w + b.r) b.x = -b.r
          if (b.y < -b.r) b.y = s.h + b.r
          if (b.y > s.h + b.r) b.y = -b.r
        }
        const wob = 0.85 + 0.15 * Math.sin(s.t * 0.25 + b.ph)
        const h2 = hue + (b.tint - 1) * 16
        const a = (0.030 + 0.020 * breath) * energy * dim
        const g = ctx.createRadialGradient(b.x, b.y, 0, b.x, b.y, b.r * wob)
        g.addColorStop(0, `hsl(${h2} ${sat}% 52% / ${a})`)
        g.addColorStop(1, `hsl(${h2} ${sat}% 52% / 0)`)
        ctx.fillStyle = g
        ctx.beginPath(); ctx.arc(b.x, b.y, b.r * wob, 0, Math.PI * 2); ctx.fill()
      }
      ctx.globalCompositeOperation = 'source-over'

      // ALONE reads as a vignette closing in. Not a message, just a feeling —
      // the room is smaller when nobody has spoken for ten minutes.
      if (r.alone) {
        const v = ctx.createRadialGradient(
          s.w / 2, s.h / 2, Math.min(s.w, s.h) * 0.34,
          s.w / 2, s.h / 2, Math.max(s.w, s.h) * 0.78)
        v.addColorStop(0, 'rgba(0,0,0,0)')
        v.addColorStop(1, `rgba(0,0,0,${0.30 + 0.10 * breath})`)
        ctx.fillStyle = v; ctx.fillRect(0, 0, s.w, s.h)
      }

      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)

    // COSTS NOTHING WHEN NOBODY IS LOOKING.
    const vis = () => {
      if (document.hidden) { running = false; cancelAnimationFrame(raf) }
      else if (!running) { running = true; raf = requestAnimationFrame(draw) }
    }
    document.addEventListener('visibilitychange', vis)

    return () => {
      running = false
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
      document.removeEventListener('visibilitychange', vis)
    }
  }, [])

  return <canvas ref={ref} className="backdrop" aria-hidden="true" />
}
