import { useCallback } from 'react'
import * as api from '../api.js'
import { usePoll, Body, Row } from './panel.jsx'

/* SETUP — what is configured, what is not, and the exact file to create next.
 *
 * ONBOARDING IS A DIAGNOSIS, NOT A LEAFLET. `docs/SETUP.md` is the prose and it is
 * good prose, but a page of instructions cannot tell you which step you are actually
 * on. This can: it asks the gateway what is in force, probes the endpoint, and reports
 * each optional key as present or absent — so the answer is "nothing is listening on
 * :1234" rather than "check that your endpoint is running".
 *
 * IT NEVER SHOWS A KEY. The server side (`_setup_key` in harness/server/app.py) returns
 * a path, a boolean and a length, and that is all there is to render. A panel that
 * displayed a prefix "so you can check it pasted" would put an API key in a screenshot.
 *
 * THE MODEL LIST IS NOT IN THIS FILE. It comes down inside /v1/setup from
 * `config/models.json`, which docs/SETUP.md also points at — one list, two readers.
 * A copy here is the duplicate that goes stale without anything failing.
 *
 * Prefix `su-`, per the appRegistry CSS-ownership rule (G-ROOM-CSS).
 */

/* A dot and a word, from one boolean, everywhere — so "on" never renders green in one
 * section and grey in the next. `warn` is a real third state: an endpoint that answers
 * 401 is plainly running and plainly not usable yet, and calling that "off" sends people
 * to restart a server that is already up. */
function Mark({ state, on = 'ready', off = 'not set', warn = 'needs attention' }) {
  const tone = state === true ? 'good' : state === 'warn' ? 'warn' : 'bad'
  return <span className={'su-mark ' + tone}>{state === true ? on : state === 'warn' ? warn : off}</span>
}

const Section = ({ title, state, hint, children }) => (
  <div className="su-sec">
    <div className="su-head">
      <span className="su-title">{title}</span>
      {state === undefined ? null : <Mark state={state} />}
    </div>
    {hint ? <div className="su-hint">{hint}</div> : null}
    {children}
  </div>
)

/* A path you have to type into a terminal, rendered as one. Not a button: this panel
 * has no write authority and pretending otherwise ("create it for me") would need an
 * authority story the profile and the settings registry already own. */
const Path = ({ children }) => <code className="su-path">{children}</code>

function Models({ group }) {
  if (!group || !group.recommended) return null
  return (
    <div className="su-models">
      <div className="su-note">{group.note}</div>
      {group.recommended.map(m => (
        <div className="su-model" key={m.id}>
          <a className="su-id" href={m.card} target="_blank" rel="noreferrer">{m.id}</a>
          <span className="su-fmt">{m.format}</span>
          {m.knob ? <span className="su-knob">{m.knob}</span> : null}
          <div className="su-note">{m.note}</div>
        </div>
      ))}
    </div>
  )
}

function KeyRow({ label, k, why }) {
  if (!k) return null
  return (
    <div className="su-key">
      <div className="su-head">
        <span className="su-title">{label}</span>
        {/* CONFIGURED BUT EMPTY IS ITS OWN STATE. "I made the file and pasted nothing"
            and "I have not made the file" are different problems with different fixes,
            and collapsing them to one red dot sends half the people to the wrong one. */}
        <Mark state={k.present ? true : k.configured ? 'warn' : false}
              on="present" warn="empty file" off="not created" />
      </div>
      <Path>{k.path || '(no path configured)'}</Path>
      <div className="su-note">{why}</div>
    </div>
  )
}

export default function Setup() {
  const state = usePoll(useCallback(() => api.setup(), []), 15000)
  return (
    <div className="su pad">
      <Body state={state}>{d => {
        const eng = d.engine || {}
        const xai = d.xai || {}
        const av = d.avatar || {}
        const side = d.sidecars || {}
        const models = d.models || {}
        return (
          <>
            <div className="su-lead">
              Everything below is read from the running stack. The full prose — every knob,
              what it affects, and the symptom table — is <Path>docs/SETUP.md</Path>.
            </div>

            <Section title="1 · the engine"
                     state={eng.reachable ? true : 'warn'}
                     hint="any OpenAI-compatible /v1/chat/completions server. profiles/companion.toml is the one door; a change here needs a restart.">
              <Row k="kind" v={eng.kind || '?'} />
              <Row k="base_url" v={eng.base_url || '(unset)'} />
              <Row k="model" v={eng.model || '(the server default)'} />
              <Row k="dialect" v={eng.dialect || 'generic'} />
              <Row k="probe" v={eng.probe || 'nothing listening'}
                   tone={eng.reachable ? 'good' : 'bad'} />
              {eng.reachable ? null : (
                <div className="su-note">
                  Nothing answered on that address. Start your server (LM Studio :1234,
                  llama-server :8080, vLLM :8000), or correct <Path>[engine].base_url</Path>
                  in the profile and restart.
                </div>
              )}
              <KeyRow label="endpoint token" k={eng.key}
                      why="only needed if your own server requires auth — LM Studio's 'require authentication', or a cloud endpoint." />
              <Models group={models.engine} />
            </Section>

            <Section title="2 · the xAI key"
                     state={(xai.key || {}).present ? true : false}
                     hint="one key, four features. All of them are dark without it, and everything else in Kairos works anyway.">
              <KeyRow label="xAI API key" k={xai.key}
                      why="get one at console.x.ai. Billed per call — and every attempt bills, including a refused one." />
              <Row k="her voice" v={(xai.voice || {}).armed ? 'armed (' + (xai.voice.voice_id || '') + ')' : 'method = ' + ((xai.voice || {}).method || 'off')}
                   tone={(xai.voice || {}).armed ? 'good' : ''} />
              <Row k="face + wardrobe" v={(xai.images || {}).armed ? (xai.images.image_model || 'armed') : 'needs the key'}
                   tone={(xai.images || {}).armed ? 'good' : ''} />
              <Row k="web search" v={(xai.search || {}).backend || 'ddg'}
                   tone={(xai.search || {}).armed ? 'good' : ''} />
              <Row k="research tier" v={(xai.research || {}).armed ? 'on' : 'off (ships off)'} />
            </Section>

            <Section title="3 · her identity"
                     state={(d.persona || {}).present}
                     hint="persona-template/ copied to persona/ — yours to edit, gitignored, backed up on every launch.">
              <Path>{(d.persona || {}).dir || 'persona'}</Path>
              <Row k="fragments" v={String((d.persona || {}).fragments ?? 0)} />
              {(d.persona || {}).present ? null : (
                <div className="su-note">Not there yet: <Path>cp -r persona-template persona</Path></div>
              )}
            </Section>

            <Section title="4 · her face"
                     state={av.have_face ? true : av.bundled ? 'warn' : false}
                     hint="Kairos ships one outfit across all seven faces plus six gestures. The gateway lays them down once; the drawn SVG stays underneath as the floor.">
              <Row k="bundled set" v={av.set || 'none found'} />
              <Row k="seeded" v={av.seeded ? 'yes' : 'not yet'} tone={av.seeded ? 'good' : ''} />
              <Row k="faces with art" v={(av.faces_with_art ?? 0) + ' / ' + (av.faces_total ?? 7)}
                   tone={av.have_face ? 'good' : 'bad'} />
              <div className="su-note">
                To make her yours, replace <em>both</em> halves of the identity together —
                <Path>var/room/avatar/_reference.png</Path> and
                <Path>var/room/avatar/character.txt</Path>. Changing one without the other
                is how a wardrobe fills with fifty different women (docs/AVATAR-PIPELINE.md).
              </div>
            </Section>

            <Section title="5 · the librarians"
                     state={side.enabled ? true : false}
                     hint="small CPU models that embed, retrieve, judge and read for her. Never her voice. All of [aux] ships off.">
              <Row k="enabled" v={side.enabled ? 'yes' : 'no'} />
              <Row k="chat sidecar" v={side.chat_url || '—'} />
              <Row k="embed sidecar" v={side.embed_url || '—'} />
              <Models group={models.sidecars} />
            </Section>

            <Section title="6 · her memory"
                     state={(d.memory || {}).present}
                     hint="the one rule over everything: nothing she knows is ever deleted. Facts are tombstoned, never dropped.">
              <Path>{(d.memory || {}).registry || 'var/memory/registry.jsonl'}</Path>
              <Row k="live rows" v={String((d.memory || {}).rows ?? '—')} />
            </Section>
          </>
        )
      }}</Body>
    </div>
  )
}
