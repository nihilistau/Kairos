import { usePoll, Body } from './panel.jsx'
import * as api from '../api.js'

/* STAGE — the roleplay director, made visible.
 *
 * The engine has always been the good part: a system prompt is advice, so pacing and
 * gating live in Python where they are law. What it never had was a WINDOW. Nothing
 * could ask "is a scene running, on which rung, how many beats, which hooks have
 * fired" — so the operator's only view of a live scene was the gateway log, and a
 * panel over it was impossible rather than merely absent.
 *
 * TWO THINGS THIS PANEL OWES THE ROOM, and they are the reason it exists:
 *
 * THE LADDER IS SHOWN, NOT DESCRIBED. Escalation is gated one rung at a time and the
 * gate only opens once the fiction has earned it. That is the whole design, and it was
 * invisible — you could not see which rung you were on, how many beats it still wants,
 * or where the operator's ceiling sits. Now it is a column you read at a glance.
 *
 * STOP IS ALWAYS ONE CLICK. ladder.py already treats a typed "stop" as absolute, at any
 * rung, checked before anything else. The BUTTON must not be weaker than the words: it
 * is rendered whenever a scene is live, it takes no argument, and it cannot fail on the
 * wrong scene id. A stop you have to remember how to phrase is not a stop.
 */

const RUNG_HUE = (lvl) => 210 - Math.min(lvl, 7) * 26   // cool at the bottom, hot at the top

export default function Stage() {
  const s = usePoll(api.roleplay, 5000)
  const act = async (body) => { await api.roleplayWrite(body); s.refresh() }

  return (
    <div className="pad stg">
      <Body state={s}>{d => {
        if (d.ok === false) return <div className="err">stage unavailable — {d.error}</div>
        const sc = d.scene
        const cap = d.max_heat ?? 7
        return (
          <>
            <div className="chips">
              <button className={d.enabled ? 'on' : 'r-off'}>
                {d.enabled ? 'armed' : 'switched off'}
              </button>
              <button title="the operator's hard ceiling — the scene never goes past it">
                ceiling {d.ladder?.[cap]?.name || cap}
              </button>
              <button title="the pacing dial: >1 makes the build slower">
                pacing ×{d.dwell_scale ?? 1}
              </button>
              {sc ? (
                <button className="stg-stop" onClick={() => act({ op: 'exit' })}
                        title="drops character immediately, from any rung">
                  ■ stop the scene
                </button>
              ) : null}
            </div>

            {!d.enabled ? (
              <p className="muted">
                Roleplay is off. Turn on <code>roleplay.enabled</code> in tuning — the
                director, the ladder and the deck are all here and simply are not consulted.
              </p>
            ) : null}

            {sc ? (
              <>
                <div className="stg-live" style={{ '--h': RUNG_HUE(sc.level) }}>
                  <h4>{sc.title} <span className="muted">{sc.theme}</span></h4>
                  <p className="stg-role">{sc.role}</p>
                  <p className="muted">{sc.setting}</p>
                  <div className="stg-nums">
                    <span>beat {sc.beats}</span>
                    <span>{sc.beats_at_level} at this rung</span>
                    <span>{sc.hooks_fired.length}/{sc.hooks.length} hooks fired</span>
                    {sc.opened ? null : <span className="warn">opening not yet delivered</span>}
                  </div>
                </div>

                {/* THE LADDER. Rungs above the ceiling are shown struck through rather
                    than hidden — knowing where the wall is beats wondering. */}
                <div className="stg-ladder">
                  {(d.ladder || []).map(r => {
                    const here = r.level === sc.level
                    const over = r.level > cap
                    return (
                      <div key={r.level}
                           className={'stg-rung' + (here ? ' here' : '') + (over ? ' over' : '')}
                           style={{ '--h': RUNG_HUE(r.level) }}
                           title={r.direction}>
                        <span className="stg-n">{r.level}</span>
                        <span className="stg-name">{r.name}</span>
                        {here ? (
                          <span className="stg-dwell">
                            {sc.beats_at_level}/{r.dwell} beats before the next rung can open
                          </span>
                        ) : null}
                        {over ? <span className="muted">above the ceiling</span> : null}
                      </div>
                    )
                  })}
                </div>

                {sc.hooks.length ? (
                  <div className="stg-hooks">
                    <h4>hooks <span className="muted">fired when the scene idles</span></h4>
                    {sc.hooks.map((h, i) => (
                      <div key={i} className={'stg-hook' + (sc.hooks_fired.includes(i) ? ' spent' : '')}>
                        {h}
                      </div>
                    ))}
                  </div>
                ) : null}
              </>
            ) : (
              <>
                <p className="muted">
                  No scene running. {d.pending ? 'She has offered — pick one in the chat.' : null}
                </p>
                <div className="stg-deck">
                  {(d.deck || []).map(c => (
                    <div key={c.id} className="stg-card">
                      <div className="stg-ct">
                        {c.title}
                        <span className="muted"> {c.theme}</span>
                        {c.authored ? <span className="stg-auth" title="authored: dropped into var/room/scenarios/">authored</span> : null}
                      </div>
                      <div className="muted">{c.premise}</div>
                      <button onClick={() => act({ op: 'enter', id: c.id })}>begin</button>
                    </div>
                  ))}
                </div>
              </>
            )}
            <p className="muted stg-foot">{d.stop_words}</p>
          </>
        )
      }}</Body>
    </div>
  )
}
