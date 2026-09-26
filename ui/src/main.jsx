import React, { useSyncExternalStore, useRef, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import * as wm from './windowManager.js'
import { APPS, byId, DOCK_HIDDEN_DEFAULT } from './appRegistry.jsx'
import * as dockPrefs from './dockPrefs.js'
import { usePoll } from './apps/panel.jsx'
import * as api from './api.js'
import Renderer from './room/Renderer.jsx'
import Clock from './room/Clock.jsx'
import Presence from './room/Presence.jsx'
import Portrait from './room/Portrait.jsx'
import Down from './room/Down.jsx'
import DeskIcons from './room/DeskIcons.jsx'
import { Icon } from './kit/icons.jsx'
import { Chip, Orb } from './kit/parts.jsx'
import { useMood } from './room/useMood.js'
import { applyMood } from './room/moodTheme.js'
import Anon, { AnonChip } from './room/Anon.jsx'
import { LookingChip, SceneChip } from './room/TaskChips.jsx'
import { useState } from 'react'
import './kit/fonts.js'
import './kit/tokens.css'
import './kit/kit.css'
import './room.css'
import './room/shell.css'

/* THE ROOM — the shell.
 *
 * A desktop of small windows onto things that already exist, with the
 * conversation in the middle. It owns no state: every panel is a view onto a
 * gateway endpoint, which is exactly why this is ADDITIVE. Every existing console
 * page (index, operator, ops, tuning, dashboard, voice_train) keeps working
 * untouched, because nothing moved to make room for this.
 */

const DIRS = ['n','s','e','w','ne','nw','se','sw']
const MIN_W = 280
const MIN_H = 160

/* ONE PANEL MUST NEVER TAKE THE ROOM DOWN (2026-08-29 audit). React unmounts the
 * whole tree on an uncaught render error, and there was no boundary anywhere — the
 * House panel's crash blanked chat and every other window until F5. Every window
 * body mounts inside this now: a broken panel shows its error in its own frame and
 * the rest of the room keeps breathing. Class component because error boundaries
 * still cannot be hooks. */
class PanelBoundary extends React.Component {
  constructor(p) { super(p); this.state = { err: null } }
  static getDerivedStateFromError(err) { return { err } }
  componentDidCatch(err) { console.error('[panel]', this.props.title, err) }
  render() {
    if (this.state.err) {
      return <div className="pad err">
        this panel hit an error — the rest of the room is fine.{' '}
        <button onClick={() => this.setState({ err: null })}>retry</button>
        <div className="muted" style={{ marginTop: 6, fontSize: 11 }}>
          {String(this.state.err).slice(0, 200)}
        </div>
      </div>
    }
    return this.props.children
  }
}

function Win({ w, focused }) {
  const app = byId(w.appId)
  const drag = useRef(null)
  const el = useRef(null)
  // FRESH for one beat after mount, so `win-in` plays once and then gets out of the
  // way. Hooks sit above the early return below: a hook after it would change the
  // hook count the moment a window is minimised, and React would throw.
  const [fresh, setFresh] = useState(true)
  useEffect(() => { const t = setTimeout(() => setFresh(false), 260); return () => clearTimeout(t) }, [])
  // DRAGGING IS STATE, not a read of the ref: the ref clears on mouseup without a render,
  // so the class (and the grabbing cursor) stayed on the bar until something else drew.
  const [dragging, setDragging] = useState(false)
  // SPRING, not snap. A window that jumps to its position reads as a div; one that
  // settles reads as an object. The easing lives in CSS so dragging stays exact —
  // a transition on transform during a drag makes the window lag the cursor, which
  // feels broken rather than smooth.
  if (!app || w.minimized) return null
  const Body = app.Component

  const onDown = (e) => {
    if (e.target.closest('button')) return
    drag.current = { x: e.clientX, y: e.clientY, ox: w.x, oy: w.y }
    setDragging(true)
    wm.focus(w.appId)
    const move = (ev) => {
      if (!drag.current) return
      wm.moveResize(w.appId, {
        x: Math.max(0, drag.current.ox + ev.clientX - drag.current.x),
        y: Math.max(0, drag.current.oy + ev.clientY - drag.current.y),
      })
    }
    const up = () => {
      drag.current = null
      setDragging(false)
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
    }
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
  }

  // RESIZE. wm.moveResize has always taken w/h — nothing ever sent them, so every
  // window was frozen at the size appRegistry happened to guess. That is fine for a
  // status readout and useless for anything you actually read: the ledger's rows are
  // paragraphs. Eight grips, because a corner-only resize means a window that opened
  // too short can only be fixed by also moving it. Dragging a top or left edge moves
  // the origin as it resizes, which is what makes those edges feel like edges.
  const onResize = (dir) => (e) => {
    e.preventDefault(); e.stopPropagation()
    wm.focus(w.appId)
    const s = { x: e.clientX, y: e.clientY, ow: w.w, oh: w.h, ox: w.x, oy: w.y }
    const move = (ev) => {
      const dx = ev.clientX - s.x, dy = ev.clientY - s.y
      const p = {}
      // MIN_W/MIN_H are clamps, not suggestions — a window dragged to zero is a
      // window you cannot grab again, and the only way back is a reload.
      if (dir.includes('e')) p.w = Math.max(MIN_W, s.ow + dx)
      if (dir.includes('s')) p.h = Math.max(MIN_H, s.oh + dy)
      if (dir.includes('w')) {
        p.w = Math.max(MIN_W, s.ow - dx)
        p.x = s.ox + (s.ow - p.w)        // hold the right edge still
      }
      if (dir.includes('n')) {
        p.h = Math.max(MIN_H, s.oh - dy)
        p.y = s.oy + (s.oh - p.h)        // hold the bottom edge still
      }
      wm.moveResize(w.appId, p)
    }
    const up = () => {
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
      document.body.classList.remove('resizing')
    }
    document.body.classList.add('resizing')   // kill text selection mid-drag
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
  }

  // A MAXIMISED WINDOW TAKES ITS BOX FROM CSS, not from the store: `.maxed` pins it to
  // the desktop's edges, so it stays right when the browser is resized without anything
  // having to recompute and write a new box.
  return (
    <div ref={el}
         className={'win' + (focused ? ' win-focus' : '') + (fresh ? ' win-in' : '')
                    + (dragging ? ' dragging' : '') + (w.max ? ' maxed' : '')}
         style={w.max ? { zIndex: w.z } : { left: w.x, top: w.y, width: w.w, height: w.h, zIndex: w.z }}
         onMouseDown={() => wm.focus(w.appId)}>
      {/* CONTROLS ON THE RIGHT (2026-08-21, his ask), title leading — the dots ARE
          the controls, not decoration next to them: red closes, amber minimises. A
          row of ornaments beside real buttons is the thing that makes a skin feel
          like a costume. (They opened on the left, executive_suite style, for the
          room's first three weeks.) */}
      <div className="bar" onMouseDown={onDown}
           onDoubleClick={(e) => { if (!e.target.closest('button')) wm.maximize(w.appId) }}>
        <span className="ic"><Icon name={app.icon} size={15} /></span>
        <span className="ti">{app.title}</span>
        {/* THE TITLE CHIP (2026-08-21): a glance at state/provider, registry-declared
            (titleChips.jsx), mounted only while the window is open. Never a control. */}
        {app.TitleChip ? <app.TitleChip /> : null}
        <span className="lights">
          {/* THREE LIGHTS, THREE CONTROLS (2026-09-23). The green one was an ornament
              labelled "focused" and did nothing; it is maximise now, which is what the
              hand already expects of it. */}
          <button className="lt lt-green" onClick={() => wm.maximize(w.appId)}
                  title={w.max ? 'Restore' : 'Maximise'} aria-label={w.max ? 'Restore' : 'Maximise'}>
            <svg width="7" height="7" viewBox="0 0 8 8" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M1.5 1.5h5v5h-5z" /></svg>
          </button>
          <button className="lt lt-amber" onClick={() => wm.minimize(w.appId)} title="Minimise" aria-label="Minimise">
            <svg width="7" height="7" viewBox="0 0 8 8" stroke="currentColor" strokeWidth="1.4"><path d="M1.5 4h5" /></svg>
          </button>
          <button className="lt lt-red" onClick={() => wm.close(w.appId)} title="Close" aria-label="Close">
            <svg width="7" height="7" viewBox="0 0 8 8" stroke="currentColor" strokeWidth="1.4"><path d="M2 2l4 4M6 2 2 6" /></svg>
          </button>
        </span>
      </div>
      <div className="body"><PanelBoundary title={app.title}><Body /></PanelBoundary></div>
      {w.max ? null : DIRS.map(d => (
        <div key={d} className={'grip g-' + d} onMouseDown={onResize(d)} />
      ))}
    </div>
  )
}

function Status() {
  const h = usePoll(api.health, 10000)
  const sys = usePoll(api.system, 60000)
  const [busy, setBusy] = useState('')
  const [ask, setAask] = useState(false)
  const d = h.data || {}
  const on = !h.error && d.ok

  /* RESTART FROM HERE. Added the morning a twelve-hour-old daemon degenerated into token
   * soup and the only cure was a terminal. The two are deliberately separate and labelled
   * with what they cost: bouncing the gateway is seconds and keeps the warm prefix, while
   * a full restart reloads the model and takes minutes. Offering one button for both
   * would make the cheap fix feel as expensive as the dear one, and nobody would use it.
   *
   * The full restart asks first. It is the only control in this room that takes her away
   * for two minutes. */
  async function go(op) {
    setBusy(op); setAask(false)
    try { await api.systemWrite({ op }) } catch { /* the gateway dies mid-request; expected */ }
    // Poll until it answers again rather than guessing at a duration.
    const t0 = Date.now()
    const wait = async () => {
      if (Date.now() - t0 > 300000) { setBusy(''); return }
      try {
        const r = await fetch('/health')
        if (r.ok) { setBusy(''); h.refresh(); return }
      } catch { /* still down */ }
      setTimeout(wait, 2000)
    }
    setTimeout(wait, 3000)
  }

  const prof = sys.data && sys.data.profile
  const said = busy ? (busy === 'restart' ? 'restarting…' : 'bouncing…')
    : h.error ? 'gateway unreachable' : d.warm ? 'warm' : d.ok ? 'warming…' : '…'
  return (
    <div className="status">
      {/* the light is NAMED: at phone width the word beside it is hidden (shell.css) */}
      <span className={'led ' + (on ? (d.warm ? 'ok' : 'warm') : 'off')}
            role="img" title={'gateway: ' + said} aria-label={'gateway: ' + said} />
      <span>{said}</span>
      {prof ? <span className="tb-prof"><Chip title="the profile this stack was launched with">{prof}</Chip></span> : null}
      {!busy && sys.data && sys.data.restartable ? (
        ask ? (
          <>
            <span className="warn">reload the model? ~2 min</span>
            <button className="r-off" onClick={() => go('restart')}>yes, restart</button>
            <button onClick={() => setAask(false)}>no</button>
          </>
        ) : (
          <>
            <button onClick={() => go('restart_gateway')}
                    title="bounce the gateway only — seconds, keeps the model warm">bounce</button>
            <button onClick={() => setAask(true)}
                    title="reload the model — minutes. The cure when she degenerates.">restart</button>
          </>
        )
      ) : null}
    </div>
  )
}

function Room() {
  const windows = useSyncExternalStore(wm.subscribe, wm.getWindows)
  // FOCUS IS THE TOP WINDOW THAT IS SHOWING. The manager already orders by z; the room
  // only has to say which one is on top so the chrome can say so too.
  const focusedId = windows.filter(w => !w.minimized)
    .reduce((top, w) => (!top || w.z > top.z ? w : top), null)?.appId
  const open = new Set(windows.filter(w => !w.minimized).map(w => w.appId))
  useSyncExternalStore(dockPrefs.subscribe, dockPrefs.getVersion)
  const dockHidden = dockPrefs.hiddenSet(DOCK_HIDDEN_DEFAULT)
  // One beat for the whole room. 5 s is slow enough to cost nothing and fast
  // enough that the clock never looks stopped.
  const beat = usePoll(api.pulse, 5000)
  const pulse = beat.data
  // HER MOOD, decided in ONE place (room/moodTheme.js): her live [MOOD:] mark beats the
  // polled one. The shell writes it onto <html> so every surface reads the same hue.
  const m = useMood(pulse)
  useEffect(() => { applyMood(document.documentElement, m) }, [m.word, m.hue, m.glow, m.thinking])
  // THE TASKBAR'S MIDDLE SCROLLS (shell.css) — at 375px only two window buttons fit, and a
  // clipped one was a minimised window with no way back. Keep the focused one in view.
  const mid = useRef(null)
  useEffect(() => {
    const box = mid.current, b = box && box.querySelector('.tb-win-on')
    if (!b) return
    // rects, not offsetLeft: the button's offsetParent is the fixed taskbar, not this box
    const br = b.getBoundingClientRect(), mr = box.getBoundingClientRect()
    if (br.left < mr.left) box.scrollLeft -= mr.left - br.left
    else if (br.right > mr.right) box.scrollLeft += br.right - mr.right
  }, [focusedId, windows.length])
  const wheel = (e) => { const box = mid.current; if (box && e.deltaY) box.scrollLeft += e.deltaY }
  const [armed, setArmed] = useState(false)
  const [downMode, setDownMode] = useState('')
  const shown = { ...(pulse || {}), her: { ...(pulse?.her || {}), mood: m.word } }
  /* ── THE SHELL, RE-LAID-OUT (2026-08-02) ────────────────────────────────────────
   * Was a top header carrying the brand, every app button, presence and status in one
   * wrapping row — which is why the app list wrapped onto two lines and the desktop
   * started halfway down the screen.
   *
   * Now: a LEFT DOCK of apps (icon over label, an active rail on the open ones), the
   * desktop between, and a TASKBAR along the bottom holding the things you glance at
   * rather than press — clock, her presence, gateway health, and a button per open
   * window (2026-09-26: every window, not only minimised ones). Same components, same endpoints, same window manager; only the furniture
   * moved. Modelled on CosySim's executive_suite kit, which is where the operator wants
   * this to end up in 3D.
   */
  /* OFF THE RECORD (2026-08-23) rides the PULSE the shell already beats on, rather
     than a poll of its own: the switch has to be visible everywhere at once, and a
     second timer is a second idea of whether it is on. `.an-on` puts a rule around
     the whole room — see Anon.jsx for why one small indicator is not enough. */
  const anon = pulse && pulse.anon

  /* THE ROOM OPENS WITH THE CONVERSATION IN IT (2026-09-23). Chat used to be painted
     into the desktop unconditionally; as a window it would be absent on every load,
     because the window manager keeps no state across a reload. Opening it on mount
     restores what he had — and only when nothing else is open, so this can never fight
     a session that already has windows up. */
  useEffect(() => {
    if (wm.getWindows().length === 0) {
      const c = byId('chat')
      if (c) wm.open('chat', c)
    }
  }, [])

  return (
    <div className={"room" + (anon && anon.on ? " an-on" : "")}>
      <Renderer kind="2d" pulse={shown} />

      {/* THE DOCK IS GONE (2026-09-23, his ask): "move the room icons from a side bar
          on the left so that they are actual free desktop like icons". The apps are
          loose on the desktop now (DeskIcons). What lived in that rail and is NOT an
          app moved to the taskbar rather than becoming an icon — Off the record and
          shut down are controls, and a control that can be dragged behind a window is
          a control you cannot find when you need it. */}

      <main className="desktop">
        {downMode ? <Down mode={downMode} onBack={() => setDownMode('')} /> : null}
        {/* ICONS FIRST so every window stacks above them — the desktop is the thing
            windows sit ON, and an icon that can cover a panel is not a desktop. */}
        <DeskIcons />
        <Portrait mood={m.word} thinking={m.thinking} />
        {windows.map(w => <Win key={w.appId} w={w} focused={w.appId === focusedId} />)}
      </main>

      <footer className="taskbar">
        <div className="tb-left">
          {/* THE BRAND CAME DOWN WITH THE DOCK. It is a mark, not a control, so it sits
              where the other glanced-at things live. */}
          <span className="tb-brand" title="Kairos">
            <Icon name="brand" size={16} /><span className="tb-brand-t">KAIROS</span>
          </span>
          <a className="tb-console" href="/index.html" title="The original console — still here, unchanged">
            <Icon name="console" size={15} />Console
          </a>
          <span className="tb-sep" />
        </div>
        {/* EVERY WINDOW HAS A BUTTON, not only minimised ones: the taskbar is how you find
            a window that is under another one, and how you get a minimised one back.
            Clicking the FOCUSED window's button minimises it — every desktop's taskbar
            does this, and it gives minimise a second, larger target. */}
        <div className="tb-mid" ref={mid} onWheel={wheel}>
          {windows.map(w => {
            const a = byId(w.appId)
            if (!a) return null
            const on = w.appId === focusedId
            return (
              <button key={w.appId}
                      className={'tb-win' + (on ? ' tb-win-on' : '') + (w.minimized ? ' tb-win-min' : '')}
                      title={a.title} aria-current={on ? 'true' : undefined}
                      onClick={() => (on ? wm.minimize(w.appId) : wm.open(w.appId, a))}>
                <Icon name={a.icon} size={16} /><span className="tb-win-t">{a.title}</span>
              </button>
            )
          })}
        </div>
        <div className="tb-right">
          {/* A RUNNING SCENE CHANGES WHO SHE IS, so it belongs where he cannot miss it.
              Found 2026-08-03: a 'penthouse' scene had been live for 17 beats, surviving
              every restart by design, and he did not know — every reply read as noir bar
              fiction and it was indistinguishable from her personality having changed.
              Persisting the scene is right; resuming it silently is not. */}
          <AnonChip anon={anon} />
          <SceneChip />
          <LookingChip pulse={pulse}
                       onOpen={() => { const a = byId('research'); if (a) wm.open('research', a) }} />
          {/* HER MOOD, NAMED. The one place it is always written down (spec §3). */}
          <span className="tb-mood" title={m.known ? 'her mood' : 'her mood — a word with no colour on file'}
                role="status" aria-label={'her mood: ' + m.word + (m.thinking ? ', thinking' : '')}>
            <Orb thinking={m.thinking} /><span className="tb-mood-t">{m.word}{m.thinking ? ' · thinking' : ''}</span>
          </span>
          <Presence pulse={shown} />
          <Status />
          <Anon anon={anon} refresh={beat.refresh} />

          <div className="sd-wrap">

            {!armed ? (

              <button className="sd-btn" title="Stop her, or the whole stack"

                      onClick={() => setArmed(true)}>

                <Icon name="power" size={14} /><span>Shut down</span>

              </button>

            ) : (

              <div className="sd-confirm">

                <button className="sd-opt" title="stop her; the room stays up"

                        onClick={() => { api.shutdown('her', true); setDownMode('her'); setArmed(false) }}>

                  her only

                </button>

                <button className="sd-opt" title="stop everything, including this room"

                        onClick={() => { api.shutdown('all', true); setDownMode('all'); setArmed(false) }}>

                  everything

                </button>

                <button className="sd-opt sd-kill"

                        title="stop now — discards a reply in flight and any message she has not shown you"

                        onClick={() => { api.shutdown('kill', false); setDownMode('all'); setArmed(false) }}>

                  kill

                </button>

                <button className="sd-opt sd-cancel" onClick={() => setArmed(false)}>cancel</button>

              </div>

            )}

          </div>

          <Clock pulse={pulse} />
        </div>
      </footer>
    </div>
  )
}

createRoot(document.getElementById('root')).render(<React.StrictMode><Room /></React.StrictMode>)
