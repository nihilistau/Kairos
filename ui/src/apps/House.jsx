import { usePoll, Body } from './panel.jsx'

/* THE HOUSE — a beachhead, and honest about being one.
 *
 * HIS ASK, 2026-08-26, in his words: "lets add a HA panel in Kairos, just add like a
 * connected indicator, a hyper link maybe for the moment, just the beachhead for the
 * framework we can work out later how we will go about HA integration properly."
 *
 * SO IT DELIBERATELY DOES ALMOST NOTHING. It answers three questions and stops:
 *
 *   is Home Assistant reachable      — because "she did not mention I was asleep" has two
 *                                      very different causes and this separates them
 *   what is it giving her            — the entities the bridge takes, and what each becomes
 *   where do I go to change it       — a link out to Home Assistant itself
 *
 * WHAT IT IS NOT. It is not a second Home Assistant. Home Assistant is very good at being
 * Home Assistant and this window has no business re-drawing 392 entities, and none at all
 * offering to switch anything on: nothing in `harness/homeassistant/` can call a service,
 * and a panel with buttons would be the first argument for changing that. Lights are a
 * different product with different failure modes and they get their own decision, not a
 * gap filled in by a convenient button.
 *
 * THE READINGS THEMSELVES LIVE IN THE ♥ BODY PANEL, because that is where his body lives
 * whether it came from a watch on his wrist or a classifier on his phone. Sleep confidence
 * arriving through Home Assistant does not make it a house fact.
 *
 * Prefix `ha-`, per the appRegistry CSS-ownership rule G-ROOM-CSS enforces.
 */
export default function House () {
  const d = usePoll('/v1/house/now', 15000)

  if (!d) return <Body><div className="ha-dim">asking…</div></Body>

  const configured = !!d.configured
  const alive = !!d.alive
  const ents = d.entities || []
  const url = d.url || ''

  /* THREE STATES, NOT TWO. "off" and "unreachable" are different problems with different
   * fixes -- one is a missing token, the other is a container that is down -- and a single
   * red dot for both sends you looking in the wrong place. */
  const state = !configured ? 'off' : alive ? 'up' : 'down'
  const label = { off: 'not configured', up: 'connected', down: 'unreachable' }[state]

  return (
    <Body>
      <div className="ha-head">
        <span className={'ha-dot ha-' + state} />
        <span className="ha-state">{label}</span>
        {url ? <a className="ha-link" href={url} target="_blank" rel="noreferrer">
          open Home Assistant ↗
        </a> : null}
      </div>

      {d.why ? <div className="ha-why">{d.why}</div> : null}

      {alive ? (
        <div className="ha-count">
          {d.total_entities} entities in the house · {ents.length} of them reach her
        </div>
      ) : null}

      {/* WHAT CROSSES, AND WHAT IT BECOMES. The useful half of this panel: it answers
          "why does she not know I am asleep" without anyone reading the source. */}
      {ents.length ? (
        <ul className="ha-list">
          {ents.map(e => (
            <li key={e.entity_id} className={e.value === null ? 'ha-row ha-skip' : 'ha-row'}>
              <span className="ha-ent">{e.entity_id}</span>
              <span className="ha-arrow">→</span>
              <span className="ha-kind">{e.kind}</span>
              <span className="ha-val">
                {e.value === null ? (e.why || 'no value') : String(e.value)}
              </span>
            </li>
          ))}
        </ul>
      ) : alive ? (
        <div className="ha-empty">
          Nothing here reaches her yet. The bridge takes a sleep confidence and an activity
          from the companion app — enable those sensors on the phone and they appear.
        </div>
      ) : null}

      {/* SILENCE IS AN ANSWER HERE TOO. The house watch list ships empty and she is told
          nothing about it until he names entities; saying so beats an empty box. */}
      <div className="ha-foot">
        She is told nothing about the house itself
        {d.watching && d.watching.length ? ` except ${d.watching.length} watched entities` : ''}
        . Her body readings are in the ♥ panel.
      </div>
    </Body>
  )
}
