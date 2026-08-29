import React, { useSyncExternalStore, useRef } from 'react'
import { createRoot } from 'react-dom/client'
import * as wm from './windowManager.js'
import { APPS, byId, DOCK_HIDDEN_DEFAULT } from './appRegistry.jsx'
import * as dockPrefs from './dockPrefs.js'
import Chat from './Chat.jsx'
import { usePoll } from './apps/panel.jsx'
import * as api from './api.js'
import Renderer from './room/Renderer.jsx'
import Clock from './room/Clock.jsx'
import Presence from './room/Presence.jsx'
import Portrait from './room/Portrait.jsx'
import Down from './room/Down.jsx'
import Anon, { AnonChip } from './room/Anon.jsx'
import { useState } from 'react'
import './room.css'

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

function Win({ w }) {
  const app = byId(w.appId)
  const drag = useRef(null)
  const el = useRef(null)
  // SPRING, not snap. A window that jumps to its position reads as a div; one that
  // settles reads as an object. The easing lives in CSS so dragging stays exact —
  // a transition on transform during a drag makes the window lag the cursor, which
  // feels broken rather than smooth.
  if (!app || w.minimized) return null
  const Body = app.Component

  const onDown = (e) => {
    if (e.target.closest('button')) return
    drag.current = { x: e.clientX, y: e.clientY, ox: w.x, oy: w.y }
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

  return (
    <div ref={el}
         className={'win' + (drag.current ? ' dragging' : '')}
         style={{ left: w.x, top: w.y, width: w.w, height: w.h, zIndex: w.z }}
         onMouseDown={() => wm.focus(w.appId)}>
      {/* CONTROLS ON THE RIGHT (2026-08-21, his ask), title leading — the dots ARE
          the controls, not decoration next to them: red closes, amber minimises. A
          row of ornaments beside real buttons is the thing that makes a skin feel
          like a costume. (They opened on the left, executive_suite style, for the
          room's first three weeks.) */}
      <div className="bar" onMouseDown={onDown}>
        <span className="ic">{app.icon}</span>
        <span className="ti">{app.title}</span>
        {/* THE TITLE CHIP (2026-08-21): a glance at state/provider, registry-declared
            (titleChips.jsx), mounted only while the window is open. Never a control. */}
        {app.TitleChip ? <app.TitleChip /> : null}
        <span className="lights">
          <span className="lt lt-green" title="focused" />
          <button className="lt lt-amber" onClick={() => wm.minimize(w.appId)} title="minimise" />
          <button className="lt lt-red" onClick={() => wm.close(w.appId)} title="close" />
        </span>
      </div>
      <div className="body"><PanelBoundary title={app.title}><Body /></PanelBoundary></div>
      {DIRS.map(d => (
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
  return (
    <div className="status">
      <span className={'led ' + (on ? (d.warm ? 'ok' : 'warm') : 'off')} />
      <span>{busy ? (busy === 'restart' ? 'restarting…' : 'bouncing…')
             : h.error ? 'gateway unreachable' : d.warm ? 'warm' : d.ok ? 'warming…' : '…'}</span>
      {prof ? <span className="st-prof" title="the profile this stack was launched with">{prof}</span> : null}
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

function LookingChip({ pulse }) {
  const r = (pulse && pulse.research) || {}
  if (!r.inflight && !r.title && !r.query) return null
  const a = byId('research')
  return (
    <button className={'rsc-chip' + (r.inflight ? ' on' : '')}
            title={r.query || r.title || 'what she looked up'}
            onClick={() => a && wm.open('research', a)}>
      <b>{r.inflight ? (r.kind === 'research' ? 'researching' : 'looking up') : 'looked up'}</b>
      <span>{(r.query || r.title || '').slice(0, 42)}</span>
    </button>
  )
}

function SceneChip() {
  const rp = usePoll(api.roleplay, 8000)
  const sc = rp.data && rp.data.scene
  const [busy, setBusy] = useState(false)
  if (!sc) return null
  return (
    <span className="scn" title={(sc.role || '') + ' — ' + (sc.setting || '')}>
      <b>in scene</b> {sc.title || sc.id}
      <span className="scn-b">{sc.level_name || 'rung ' + sc.level} · {sc.beats} beats</span>
      <button disabled={busy}
              onClick={async () => { setBusy(true)
                try { await api.roleplayWrite({ op: 'exit' }); rp.refresh() } finally { setBusy(false) } }}
              title="leave the scene — she comes back as herself">exit</button>
    </span>
  )
}

function Room() {
  const windows = useSyncExternalStore(wm.subscribe, wm.getWindows)
  const open = new Set(windows.filter(w => !w.minimized).map(w => w.appId))
  useSyncExternalStore(dockPrefs.subscribe, dockPrefs.getVersion)
  const dockHidden = dockPrefs.hiddenSet(DOCK_HIDDEN_DEFAULT)
  // One beat for the whole room. 5 s is slow enough to cost nothing and fast
  // enough that the clock never looks stopped.
  const beat = usePoll(api.pulse, 5000)
  const pulse = beat.data
  // HER LIVE MOOD beats the polled one. The pulse reads persona.md, which only
  // changes when the curator writes; her [MOOD:] mark in the current reply is what
  // she is feeling RIGHT NOW, and that is what the room should be wearing.
  const [live, setLive] = useState({ mood: null, thinking: false })
  const [armed, setArmed] = useState(false)
  const [downMode, setDownMode] = useState('')
  const onMood = (mood, thinking) =>
    setLive(v => ({ mood: mood ?? v.mood, thinking: thinking ?? false }))
  const mood = live.mood || pulse?.her?.mood
  const shown = { ...(pulse || {}), her: { ...(pulse?.her || {}), mood } }
  /* ── THE SHELL, RE-LAID-OUT (2026-08-02) ────────────────────────────────────────
   * Was a top header carrying the brand, every app button, presence and status in one
   * wrapping row — which is why the app list wrapped onto two lines and the desktop
   * started halfway down the screen.
   *
   * Now: a LEFT DOCK of apps (icon over label, an active rail on the open ones), the
   * desktop between, and a TASKBAR along the bottom holding the things you glance at
   * rather than press — clock, her presence, gateway health, and a pin per minimised
   * window. Same components, same endpoints, same window manager; only the furniture
   * moved. Modelled on CosySim's executive_suite kit, which is where the operator wants
   * this to end up in 3D.
   */
  const minimized = windows.filter(w => w.minimized)
  /* OFF THE RECORD (2026-08-23) rides the PULSE the shell already beats on, rather
     than a poll of its own: the switch has to be visible everywhere at once, and a
     second timer is a second idea of whether it is on. `.an-on` puts a rule around
     the whole room — see Anon.jsx for why one small indicator is not enough. */
  const anon = pulse && pulse.anon
  return (
    <div className={"room" + (anon && anon.on ? " an-on" : "")}>
      <Renderer kind="2d" pulse={shown} />

      <aside className="dock">
        <div className="dock-brand">
          <div className="dock-mark">◈</div>
          <div className="dock-name">KAIROS</div>
        </div>
        <div className="dock-rule" />
        <div className="dock-apps">
          {/* HIS DOCK (2026-08-21): the registry says what exists; dockPrefs says
              what earns a slot — live, per browser, edited in the apps launcher.
              Pinned rows (the launcher itself) cannot be hidden: it is the way
              back to everything else. */}
          {APPS.filter(a => a.pinned || !dockHidden.has(a.id)).map(a => (
            <button key={a.id} title={a.blurb}
                    className={'dock-app' + (open.has(a.id) ? ' active' : '')}
                    onClick={() => (open.has(a.id) ? wm.minimize(a.id) : wm.open(a.id, a))}>
              <span className="dock-ic">{a.icon}</span>
              <span className="dock-lb">{a.title}</span>
            </button>
          ))}
        </div>
        {/* SHE IS NOT A CONTACT CHIP. A 46px circle at the foot of the dock threw
            away the portrait — the chains, the city behind her, everything below the
            jaw. She is on the canvas now, in <Portrait>, at the size and place he puts
            her. What is left here is only a way back to her if she is dragged off. */}
        {/* ── STOPPING HER (2026-08-06) ────────────────────────────────────────
            At the foot of the dock, separated and red, because it is the one control
            here that ends things. NOT in the taskbar, which is clicked constantly.

            TWO STEPS, AND THE MODE IS THE CONFIRM. One click only arms it; the second
            click both chooses what to stop and confirms it. No modal and nothing to
            type — a misclick costs an extra click, not her evening. */}
        <Anon anon={anon} refresh={beat.refresh} />
        <div className="sd-wrap">
          {!armed ? (
            <button className="sd-btn" title="stop her, or the whole stack"
                    onClick={() => setArmed(true)}>
              <span className="dock-ic">⏻</span>
              <span className="dock-lb">shut down</span>
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
      </aside>

      <main className="desktop">
        {downMode ? <Down mode={downMode} onBack={() => setDownMode('')} /> : null}
        <Chat onMood={onMood} />
        <Portrait mood={mood} thinking={live.thinking} />
        {windows.map(w => <Win key={w.appId} w={w} />)}
      </main>

      <footer className="taskbar">
        <div className="tb-left">
          <a className="tb-console" href="/index.html"
             title="the original console — still here, unchanged">console</a>
          {/* A MINIMISED WINDOW MUST HAVE A WAY BACK. It had none: minimise removed it
              from the desktop and the only route back was the dock button, which is
              easy to read as "it closed". */}
          {minimized.map(w => {
            const a = byId(w.appId)
            return a ? (
              <button key={w.appId} className="tb-pin" title={'restore ' + a.title}
                      onClick={() => wm.open(w.appId, a)}>
                <span>{a.icon}</span>{a.title}
              </button>
            ) : null
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
          <LookingChip pulse={pulse} />
          <Presence pulse={shown} />
          <Status />
          <Clock pulse={pulse} />
        </div>
      </footer>
    </div>
  )
}

createRoot(document.getElementById('root')).render(<React.StrictMode><Room /></React.StrictMode>)
