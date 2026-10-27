import { useState } from 'react'
import { Input } from '../kit/parts.jsx'

/* LAUNCH, THE FOLDED HALF — "everything else in the profile", grouped by section, one
 * input per key with its comment as help. Split out of Launch.jsx so the window file
 * stays the window: setups, the labelled controls, the bar, the progress.
 *
 * The input's TYPE comes from the value the file holds today, not from a table: a number
 * stays a number, a bool a checkbox, a string a text box. Anything else (a list, a table)
 * is shown as JSON and parsed back on blur; text that does not parse is refused here with
 * a message and nothing is sent (the server refuses a string for a list as well).
 * An emptied number box writes nothing. Prefix `ln-`.
 */
export const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)

const base = (p) => String(p ?? '').split(/[\\/]/).pop()

/* Equal as the restart would see them: a model is its file, not its directory. */
export const differs = (key, a, b) =>
  key === 'paths.model' ? base(a) !== base(b) : !same(a, b)

function Field({ k, v, onSave }) {
  const kind = typeof v === 'boolean' ? 'bool' : typeof v === 'number' ? 'num'
    : typeof v === 'string' ? 'str' : 'json'
  const shown = kind === 'json' ? JSON.stringify(v) : String(v ?? '')
  const [draft, setDraft] = useState(null)
  const text = draft ?? shown
  const [bad, setBad] = useState('')
  const commit = () => {
    if (draft === null || draft === shown) { setDraft(null); setBad(''); return }
    let out = draft
    if (kind === 'num') {
      out = Number(draft)
      if (draft.trim() === '' || Number.isNaN(out)) { setDraft(null); return }
    } else if (kind === 'json') {
      try { out = JSON.parse(draft) } catch (e) { setBad('not valid JSON — nothing was saved'); return }
    }
    setDraft(null); setBad('')
    onSave({ [k]: out })
  }
  if (kind === 'bool') {
    return <input type="checkbox" checked={v} aria-label={k}
                  onChange={e => onSave({ [k]: e.target.checked })} />
  }
  return (
    <>
      <Input className="ln-field" aria-label={k} value={text}
             type={kind === 'num' ? 'number' : 'text'} step="any"
             onChange={e => setDraft(e.target.value)} onBlur={commit}
             onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur() }} />
      {bad ? <div className="ln-help" role="alert">{bad}</div> : null}
    </>
  )
}

export default function LaunchSections({ values, help, skip, onSave }) {
  const groups = {}
  for (const k of Object.keys(values).sort()) {
    if (skip.has(k)) continue
    const dot = k.indexOf('.')
    const sec = dot < 0 ? '(top level)' : k.slice(0, dot)
    ;(groups[sec] = groups[sec] || []).push(k)
  }
  return (
    <div className="ln-sections">
      {Object.entries(groups).map(([sec, keys]) => (
        <details key={sec} className="ln-sec">
          <summary>[{sec}] <span className="ln-dim">{keys.length}</span></summary>
          {keys.map(k => (
            <div className="ln-kv" key={k}>
              <label className="ln-kv-k">{k.slice(k.indexOf('.') + 1)}</label>
              <Field k={k} v={values[k]} onSave={onSave} />
              {help[k] ? <div className="ln-help">{help[k]}</div> : null}
            </div>
          ))}
        </details>
      ))}
    </div>
  )
}
