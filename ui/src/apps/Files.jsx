import { useState } from 'react'
import { usePoll, Body } from './panel.jsx'
import * as api from '../api.js'

/* FILES — the tree they share.
 *
 * This is the SAME directory her file tools resolve against (HARNESS_WORKSPACE),
 * so what she writes appears here and what he drops in she can read. Until Phase 0
 * that variable was unset and defaulted to the process cwd, which meant her
 * "sandbox" was the entire repo — `_resolve()` had been doing its job perfectly
 * against a boundary nobody had drawn.
 *
 * Drag a file in to share it. Click one to read it. Editing writes back through
 * /v1/files/write, which follows `_persona_layer_write`'s discipline rather than
 * `_persona_set`'s: two independent checks, containment verified on the RESOLVED
 * path, refuse rather than sanitise.
 */
const TEXTY = /\.(md|txt|json|jsonl|py|js|jsx|ts|tsx|css|html|toml|yaml|yml|csv|log|rs|sh)$/i

function size(n) {
  if (n < 1024) return `${n}B`
  if (n < 1048576) return `${(n / 1024).toFixed(1)}K`
  return `${(n / 1048576).toFixed(1)}M`
}

export default function Files() {
  const s = usePoll(api.files, 15000)
  const [open, setOpen] = useState(null)
  const [text, setText] = useState('')
  const [note, setNote] = useState(null)
  const [dragging, setDragging] = useState(false)

  async function read(f) {
    setOpen(f); setNote(null); setText('…')
    try {
      const r = await fetch(`/v1/files/read?path=${encodeURIComponent(f.path)}`)
      const j = await r.json()
      setText(j.ok ? j.text : `[${j.error}]`)
    } catch (e) { setText(`[${e.message}]`) }
  }

  async function save() {
    setNote('saving…')
    const r = await api.filesWrite({ path: open.path, text })
    setNote(r.ok ? 'saved — she can read it now' : r.error)
    s.refresh?.()
  }

  async function drop(e) {
    e.preventDefault(); setDragging(false)
    for (const f of e.dataTransfer.files) {
      // Text only, deliberately: the write route takes a string. Binary sharing
      // wants a different endpoint and a size policy, and pretending otherwise
      // would silently corrupt whatever he dropped.
      if (!TEXTY.test(f.name)) { setNote(`${f.name}: text files only for now`); continue }
      const body = await f.text()
      const r = await api.filesWrite({ path: f.name, text: body })
      setNote(r.ok ? `added ${f.name}` : r.error)
    }
    s.refresh?.()
  }

  return (
    <div className={'pad files' + (dragging ? ' dragging' : '')}
         onDragOver={e => { e.preventDefault(); setDragging(true) }}
         onDragLeave={() => setDragging(false)}
         onDrop={drop}>
      <Body state={s}>{d => (
        <>
          <div className="root muted">{d.root}</div>
          {!d.files.length
            ? <div className="muted">empty — drag a text file in to share it with her</div>
            : d.files.map(f => (
                <div key={f.path} className={'file' + (open?.path === f.path ? ' on' : '')}
                     onClick={() => TEXTY.test(f.path) ? read(f) : null}>
                  <span className="fp">{f.path}</span>
                  <span className="fs">{size(f.bytes)}</span>
                </div>
              ))}
          {open ? (
            <div className="viewer">
              <div className="vh">
                <b>{open.path}</b>
                <button onClick={save}>save</button>
                <button onClick={() => { setOpen(null); setNote(null) }}>close</button>
              </div>
              <textarea value={text} onChange={e => setText(e.target.value)} spellCheck="false" />
            </div>
          ) : null}
          {note ? <div className="note">{note}</div> : null}
          {dragging ? <div className="dropzone">drop to share</div> : null}
        </>
      )}</Body>
    </div>
  )
}
