import { useState } from 'react'
import * as api from '../api.js'
import { usePoll } from './panel.jsx'
import { Chip, Button, Input, Select, State } from '../kit/parts.jsx'

/* knobs.jsx — the tuning registry, rendered — SHARED (2026-08-21).
 *
 * Extracted from Settings.jsx the day the voice and search panels were born:
 * three windows rendering knobs is three copies of the control row unless the
 * renderer is one component, and two copies of one truth is the house bug class.
 * Settings renders every group; Voice renders only its own; Search embeds one
 * select. Same rows, same chips, same POST.
 *
 * Prefix `st-` throughout — the settings window owns the style, the others
 * borrow the furniture (G-ROOM-CSS lists st- as this file's shared prefix).
 * Chips, fields, the test button and the states are the kit's since redesign
 * stage 2; st- keeps the row layout.
 */

// THE CONTROL IS NAMED BY ITS KNOB (stage-2 review, M4): the label sits in a sibling div,
// not a <label>, so a screen reader met "checkbox, checked" with no name. aria-label says it.
export function KnobControl({ k, busy, onSet }) {
  const dis = busy === k.key || k.scope === 'profile'
  if (k.type === 'bool') {
    return <input type="checkbox" checked={!!k.value} disabled={dis} aria-label={k.label}
                  onChange={e => onSet(k.key, e.target.checked)} />
  }
  if (k.type === 'enum') {
    return (
      <Select className="st-field" value={String(k.value)} disabled={dis} aria-label={k.label}
              onChange={e => onSet(k.key, e.target.value)}>
        {(k.choices || []).map(c => <option key={c} value={c}>{c}</option>)}
      </Select>
    )
  }
  if (k.type === 'str') {
    // a free-text knob (the first: presence.cue, 2026-08-22) — committed on blur like the numbers
    return <Input className="st-field" type="text" defaultValue={k.value || ''} disabled={dis} maxLength={200}
                  aria-label={k.label}
                  onBlur={e => { if (e.target.value !== (k.value || '')) onSet(k.key, e.target.value) }} />
  }
  return <Input className="st-field" type="number" defaultValue={k.value} disabled={dis} aria-label={k.label}
                min={k.min ?? undefined} max={k.max ?? undefined}
                step={k.step ?? undefined}
                onBlur={e => {
                  const v = k.type === 'int' ? parseInt(e.target.value, 10)
                                             : parseFloat(e.target.value)
                  if (!Number.isNaN(v) && v !== k.value) onSet(k.key, v)
                }} />
}

export function KnobRow({ k, busy, onSet }) {
  return (
    <div className="st-row" title={k.danger || ''}>
      <div className="st-label">
        {k.label}
        <Chip tone={k.scope === 'live' ? 'ok' : 'warn'}>{k.scope === 'live' ? 'live' : 'restart to change'}</Chip>
        {k.provenance === 'measured' ? <Chip tone="accent" title={k.receipt}>measured</Chip> : null}
        {k.overridden ? <Chip tone="mood">changed</Chip> : null}
        {k.engine ? <Chip title="only the sp-daemon backend honours this knob; under an OpenAI-compatible engine it is moot">{k.engine}-daemon only</Chip> : null}
      </div>
      <div className="st-ctl"><KnobControl k={k} busy={busy} onSet={onSet} /></div>
      <div className="st-help">{k.help}</div>
    </div>
  )
}

export function TestVoice({ busy, setBusy, setNote }) {
  const go = async () => {
    setBusy('voice-test')
    try {
      const r = await fetch('/v1/speak', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'Settings check. This is my voice right now.' }),
      })
      if (!r.ok) { setNote('voice test: ' + r.status + ' (voice off, or synth failed)'); return }
      const blob = await r.blob()
      const a = new Audio(URL.createObjectURL(blob))
      await a.play()
      setNote('')
    } catch (e) {
      setNote('voice test: ' + String(e).slice(0, 100))
    } finally { setBusy('') }
  }
  return (
    <Button size="sm" disabled={!!busy} onClick={go}>▶ test her voice</Button>
  )
}

/* The whole renderer: groups (optionally filtered to `only`), ordered by `first`,
 * with optional per-group extra header content. */
export function KnobGroups({ only, first = [], extras = {} }) {
  const t = usePoll(api.tuning, 6000)
  const [busy, setBusy] = useState('')
  const [note, setNote] = useState('')
  const d = t.data
  if (t.error) return <State kind="error" title="Settings unreachable">{t.error}</State>
  if (!d || !d.ok) return <State kind="loading" title="Reading the knobs…" />

  const knobs = (d.knobs || []).filter(k => !only || only.includes(k.group))
  const groups = []
  for (const k of knobs) {
    let g = groups.find(x => x.name === k.group)
    if (!g) { g = { name: k.group, rows: [] }; groups.push(g) }
    g.rows.push(k)
  }
  groups.sort((a, b) =>
    (first.includes(a.name) ? first.indexOf(a.name) : 99)
    - (first.includes(b.name) ? first.indexOf(b.name) : 99))

  const set = async (key, value) => {
    setBusy(key)
    try {
      await api.tuningSet({ [key]: value })
      setNote('')
      t.refresh()
    } catch (e) {
      setNote(String(e).slice(0, 120))
    } finally { setBusy('') }
  }

  return (
    <div className="st">
      {note ? <State kind="error">{note}</State> : null}
      {groups.map(g => (
        <div key={g.name} className="st-sec">
          <div className="st-head">{g.name}
            {extras[g.name] === 'voice-test'
              ? <TestVoice busy={busy} setBusy={setBusy} setNote={setNote} />
              : (extras[g.name] || null)}
          </div>
          {g.rows.map(k => <KnobRow key={k.key} k={k} busy={busy} onSet={set} />)}
        </div>
      ))}
    </div>
  )
}
