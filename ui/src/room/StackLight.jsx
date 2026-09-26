import { Fragment, useEffect, useId, useRef, useState } from 'react'
import * as api from '../api.js'
import { Button } from '../kit/parts.jsx'

/* THE STACK LIGHT (redesign stage 3). The light and its word, in the top bar; a click
 * opens the two restart actions that sat in the taskbar. They stay separate and say what
 * they cost — bounce is seconds and keeps the model warm, a full restart reloads the
 * model (~2 min) and asks first.
 *
 * RESTART FROM HERE. Added the morning a twelve-hour-old daemon degenerated into token
 * soup and the only cure was a terminal. The two are deliberately separate and labelled
 * with what they cost: bouncing the gateway is seconds and keeps the warm prefix, while
 * a full restart reloads the model and takes minutes. Offering one button for both
 * would make the cheap fix feel as expensive as the dear one, and nobody would use it.
 *
 * The full restart asks first. It is the only control in this room that takes her away
 * for two minutes.
 *
 * A DISCLOSURE, NOT A MENU (final review, I2). role=menu promises arrow-key navigation
 * and typeahead this never had; two buttons in a group that the light shows and hides is
 * what it is. The light says aria-expanded/aria-controls only when it can open — an inert
 * light announces nothing and wears no hover border. Escape and a finished action hand
 * focus back to the light (an outside click does not: he has clicked somewhere else).
 * Entering the confirm focuses "no", the safe default; "no" hands focus back to
 * "restart". If the stack stops being restartable while it is open, it closes. */
export default function StackLight({ health, healthError, system, refresh }) {
  const [open, setOpen] = useState(false)
  const [ask, setAsk] = useState(false)
  const [back, setBack] = useState(false)   // "no" was pressed: focus returns to "restart"
  const [busy, setBusy] = useState('')
  const wrap = useRef(null)
  const light = useRef(null)
  const panelId = useId()
  const shut = () => { setOpen(false); setAsk(false); setBack(false) }
  useEffect(() => {
    if (!open) return
    const away = (e) => { if (wrap.current && !wrap.current.contains(e.target)) shut() }
    const esc = (e) => { if (e.key === 'Escape') { shut(); if (light.current) light.current.focus() } }
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', away); document.removeEventListener('keydown', esc) }
  }, [open])

  async function go(op) {
    shut()
    if (light.current) light.current.focus()
    setBusy(op)
    try { await api.systemWrite({ op }) } catch { /* the gateway dies mid-request; expected */ }
    // Poll until it answers again rather than guessing at a duration.
    const t0 = Date.now()
    const wait = async () => {
      if (Date.now() - t0 > 300000) { setBusy(''); return }
      try {
        const r = await fetch('/health')
        if (r.ok) { setBusy(''); refresh && refresh(); return }
      } catch { /* still down */ }
      setTimeout(wait, 2000)
    }
    setTimeout(wait, 3000)
  }

  const d = health || {}
  const on = !healthError && d.ok
  const said = busy ? (busy === 'restart' ? 'restarting…' : 'bouncing…')
    : healthError ? 'gateway unreachable' : d.warm ? 'warm' : d.ok ? 'warming…' : '…'
  const canRestart = !!(!busy && system && system.restartable)
  // it can stop being restartable while open (a poll, a bounce elsewhere): close (M9)
  useEffect(() => { if (open && !canRestart) shut() }, [open, canRestart])
  const disclose = canRestart ? { 'aria-expanded': open, 'aria-controls': panelId } : {}
  return (
    <span className="top-light-wrap" ref={wrap}>
      <button type="button" className="top-light" ref={light} {...disclose}
              title={'gateway: ' + said + (canRestart ? ' — restart options' : '')}
              aria-label={'gateway: ' + said}
              onClick={() => { if (canRestart) { setOpen(o => !o); setAsk(false); setBack(false) } }}>
        <span className={'led ' + (on ? (d.warm ? 'ok' : 'warm') : 'off')} aria-hidden="true" />
        <span className="top-light-t">{said}</span>
      </button>
      {open && canRestart ? (
        <div className="top-menu" role="group" aria-label="restart the stack" id={panelId}>
          {/* KEYED, so each state MOUNTS its buttons: two bare fragments reconcile by
              position, "restart" reused the "yes, restart" node, and autoFocus (which
              fires only on mount) never ran after "no" — focus fell to the page. */}
          {ask ? (
            <Fragment key="ask">
              <span className="top-menu-warn">reload the model? ~2 min</span>
              <Button size="sm" variant="danger" onClick={() => go('restart')}>yes, restart</Button>
              <Button size="sm" variant="ghost" autoFocus onClick={() => { setAsk(false); setBack(true) }}>no</Button>
            </Fragment>
          ) : (
            <Fragment key="acts">
              <Button size="sm" onClick={() => go('restart_gateway')}
                      title="bounce the gateway only — seconds, keeps the model warm">bounce</Button>
              <Button size="sm" autoFocus={back} onClick={() => setAsk(true)}
                      title="reload the model — minutes. The cure when she degenerates.">restart</Button>
            </Fragment>
          )}
        </div>
      ) : null}
    </span>
  )
}
