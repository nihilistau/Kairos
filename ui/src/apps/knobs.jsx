import { useState } from 'react'
import * as api from '../api.js'
import { usePoll } from './panel.jsx'

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
 */

export function KnobControl({ k, busy, onSet }) {
  const dis = busy === k.key || k.scope === 'profile'
  if (k.type === 'bool') {
    return <input type="checkbox" checked={!!k.value} disabled={dis}
                  onChange={e => onSet(k.key, e.target.checked)} />
  }
  if (k.type === 'enum') {
    return (
      <select value={String(k.value)} disabled={dis}
              onChange={e => onSet(k.key, e.target.value)}>
        {(k.choices || []).map(c => <option key={c} value={c}>{c}</option>)}
      </select>
    )
  }
  if (k.type === 'str') {
    // a free-text knob (the first: presence.cue, 2026-08-22) — committed on blur like the numbers
    return <input type="text" defaultValue={k.value || ''} disabled={dis} maxLength={200}
                  onBlur={e => { if (e.target.value !== (k.value || '')) onSet(k.key, e.target.value) }} />
  }
  return <input type="number" defaultValue={k.value} disabled={dis}
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
        <span className={'st-chip ' + (k.scope === 'live' ? 'st-live' : 'st-prof')}>
          {k.scope === 'live' ? 'live' : 'restart to change'}
        </span>
        {k.provenance === 'measured' ? <span className="st-chip st-meas" title={k.receipt}>measured</span> : null}
        {k.overridden ? <span className="st-chip st-ovr">changed</span> : null}
        {k.engine ? <span className="st-chip st-eng" title="only the sp-daemon backend honours this knob; under an OpenAI-compatible engine it is moot">{k.engine}-daemon only</span> : null}
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
    <button className="st-test" disabled={!!busy} onClick={go}>
      ▶ test her voice
    </button>
  )
}

/* The whole renderer: groups (optionally filtered to `only`), ordered by `first`,
 * with optional per-group extra header content. */
export function KnobGroups({ only, first = [], extras = {} }) {
  const t = usePoll(api.tuning, 6000)
  const [busy, setBusy] = useState('')
  const [note, setNote] = useState('')
  const d = t.data
  if (t.error) return <div className="st-empty">settings unreachable — {t.error}</div>
  if (!d || !d.ok) return <div className="st-empty">reading the knobs…</div>

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
      {note ? <div className="st-note">{note}</div> : null}
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
