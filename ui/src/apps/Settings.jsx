import { useState } from 'react'
import * as api from '../api.js'
import { open } from '../windowManager.js'
import { usePoll } from './panel.jsx'
import { Input, State } from '../kit/parts.jsx'
import { KnobRow, TestVoice } from './knobs.jsx'

/* SETTINGS — the tuning registry, rendered whole (2026-08-21, his ask: "a settings
 * icon/window that contains these things with a nice layout, sections etc and
 * include all other settings in their own sections").
 *
 * NOTHING IS HAND-BUILT PER KNOB. The registry declares {group, label, type,
 * choices, help, scope}; KnobGroups (shared with the voice and search panels)
 * renders whatever it finds, grouped. A knob added server-side appears here with
 * no UI edit — the registry's founding rule, honored by a first-class window.
 *
 * LIVE vs PROFILE, said honestly: scope="live" knobs take effect on the next
 * call that reads them (voice on her next sentence, search on her next query) —
 * the LIVE chip. scope="profile" knobs are owned by the profile through serve.py;
 * the panel shows the value in force read-only with a "restart to change" chip,
 * because a control that displays a stale number and changes nothing is worse
 * than no control (the registry's own history, End-of-turn bias 4.00).
 *
 * SIX AREAS, NOT TWENTY-ONE SECTIONS (2026-10-27): the registry's groups are filed under the
 * AREAS below, a sidebar picks one, and a search box / "only what I've changed" filter cut
 * across all of them. The registry stays the one truth — AREAS only says where a group
 * sits, and a group it does not name lands in "Other" so a new knob can never vanish.
 * (That net is for runtime; g_tuning fails if a registry group is missing from AREAS.)
 * KnobGroups in knobs.jsx is still what the Voice and Search panels render.
 *
 * Prefix `st-`, per the appRegistry CSS-ownership rule.
 */
// Group strings are the registry's, em dash and all (g_tuning parses this constant).
const AREAS = [
  { name: 'How she talks', groups: ['Personality', 'Decode — sampling', 'Roleplay'] },
  { name: 'When she speaks up', groups: ['Kairos — speaking unprompted', 'Kairos — her own time', 'Presence — her modes', 'Reflection — thinking between turns'] },
  { name: 'Senses', groups: ['Sight — her eyes', 'Senses — the room on a timer', 'Telemetry', 'Home Assistant', 'Voice'] },
  { name: 'Memory', groups: ['Memory', 'Aux — the quiet librarians'] },
  { name: 'Help from outside', groups: ['Tools — how long she may work', 'Research', 'Web search', 'Consult'] },
  { name: 'Looks', groups: ['Wardrobe'] },
]
const OTHER = 'Other'

const short = (g) => g.split(' — ')[0]

export default function Settings() {
  const t = usePoll(api.tuning, 6000)
  const [area, setArea] = useState(AREAS[0].name)
  const [q, setQ] = useState('')
  const [changed, setChanged] = useState(false)
  const [busy, setBusy] = useState('')
  const [note, setNote] = useState('')
  const d = t.data
  if (t.error) return <State kind="error" title="Settings unreachable">{t.error}</State>
  if (!d || !d.ok) return <State kind="loading" title="Reading the knobs…" />

  const filed = new Set(AREAS.flatMap(a => a.groups))
  const areas = AREAS.map(a => ({ ...a }))
  const stray = [...new Set((d.knobs || []).filter(k => !filed.has(k.group)).map(k => k.group))]
  if (stray.length) areas.push({ name: OTHER, groups: stray })

  const needle = q.trim().toLowerCase()
  const matches = (k) =>
    (!needle || (k.label + ' ' + (k.help || '')).toLowerCase().includes(needle))
    && (!changed || k.overridden)
  const wide = !!needle || changed                   // the filters span every area
  const nChanged = (d.knobs || []).filter(k => k.overridden).length

  // area -> [{group, rows}] in the area's own group order
  const view = (a) => a.groups
    .map(g => ({ group: g, rows: (d.knobs || []).filter(k => k.group === g && matches(k)) }))
    .filter(x => x.rows.length)
  const shown = wide ? areas : areas.filter(a => a.name === area)

  const run = async (key, fn) => {
    setBusy(key)
    try {
      const r = await fn()
      setNote(r && r.ok === false ? String(r.error || 'refused').slice(0, 160) : '')
      t.refresh()
    } catch (e) {
      setNote(String(e).slice(0, 120))
    } finally { setBusy('') }
  }
  const set = (key, value) => run(key, () => api.tuningSet({ [key]: value }))
  const reset = (key) => run(key, () => api.tuningReset(key))

  const blocks = shown.map(a => ({ a, groups: view(a) })).filter(b => b.groups.length)

  return (
    <div className="st-win">
      <nav className="st-side" aria-label="Settings areas">
        <Input type="search" placeholder="search settings…" aria-label="search settings"
               value={q} onChange={e => setQ(e.target.value)} />
        <label className="st-only">
          <input type="checkbox" checked={changed} onChange={e => setChanged(e.target.checked)} />
          only what I&apos;ve changed ({nChanged})
        </label>
        <div className="st-areas">
          {areas.map(a => (
            <button type="button" key={a.name}
                    className={'st-area' + (!wide && a.name === area ? ' st-on' : '')}
                    aria-current={!wide && a.name === area ? 'page' : undefined}
                    onClick={() => { setArea(a.name); setQ(''); setChanged(false) }}>
              <b>{a.name}</b>
              <small>{a.groups.map(short).join(' · ')}</small>
            </button>
          ))}
        </div>
        <div className="st-foot">
          Model, kernels and restart-only settings →{' '}
          <button type="button" className="st-link" onClick={() => open('launch')}>Launch window</button>
        </div>
      </nav>
      <div className="st-main">
        {note ? <State kind="error">{note}</State> : null}
        {blocks.length === 0
          ? <div className="st-none">{wide ? 'nothing matches' : 'nothing in this area'}</div>
          : blocks.map(({ a, groups }) => (
            <section key={a.name} className="st-sec">
              {wide ? <h3 className="st-area-h">{a.name}</h3> : null}
              {groups.map(({ group, rows }) => (
                <div key={group}>
                  <div className="st-head">{group}
                    {group === 'Voice' ? <TestVoice busy={busy} setBusy={setBusy} setNote={setNote} /> : null}
                  </div>
                  {rows.map(k => (
                    <KnobRow key={k.key} k={k} busy={busy} onSet={set} onReset={reset}
                             onLaunch={() => open('launch')} />
                  ))}
                </div>
              ))}
            </section>
          ))}
      </div>
    </div>
  )
}
