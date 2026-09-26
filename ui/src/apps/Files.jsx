import { useState } from 'react'
import { usePoll, Body } from './panel.jsx'
import * as api from '../api.js'
import { Button, Chip, Row, State, TextArea } from '../kit/parts.jsx'

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

/* The window's body, split out so G-ROOM-KIT leg 11 can render it with a fixture.
 * A text file is a kit Row he can press — a keyboard reaches it now; the old row was a
 * clickable div. Anything else is a plain row: the write route takes a string, so there
 * is nothing to open. `note` is {t, tone}: a save or an add reads ok, a refusal reads
 * err (they were all the same cyan). Save is the window's one primary. */
export function FilesView({ d, open, text, setText, note, dragging, onRead, onSave, onClose }) {
  return (
    <>
      <div className="fl-root">{d.root}</div>
      {!d.files.length
        ? <State kind="empty">empty — drag a text file in to share it with her</State>
        : d.files.map(f => (
            <div key={f.path} className={'fl-file' + (open && open.path === f.path ? ' on' : '')}>
              <Row title={<span className="fl-path">{f.path}</span>} meta={size(f.bytes)}
                   onClick={TEXTY.test(f.path) ? () => onRead(f) : undefined} />
            </div>
          ))}
      {open ? (
        <div className="fl-viewer">
          <div className="fl-vh">
            <span className="fl-open">{open.path}</span>
            <Button size="sm" variant="primary" onClick={onSave}>save</Button>
            <Button size="sm" variant="ghost" onClick={onClose}>close</Button>
          </div>
          <TextArea className="fl-text" aria-label={'the text of ' + open.path}
                    value={text} onChange={e => setText(e.target.value)} spellCheck="false" />
        </div>
      ) : null}
      {note ? <div className="fl-note"><Chip tone={note.tone} wrap>{note.t}</Chip></div> : null}
      {dragging ? <div className="fl-drop">drop to share</div> : null}
    </>
  )
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
    setNote({ t: 'saving…', tone: 'neutral' })
    const r = await api.filesWrite({ path: open.path, text })
    setNote(r.ok ? { t: 'saved — she can read it now', tone: 'ok' } : { t: r.error, tone: 'err' })
    s.refresh?.()
  }

  async function drop(e) {
    e.preventDefault(); setDragging(false)
    for (const f of e.dataTransfer.files) {
      // Text only, deliberately: the write route takes a string. Binary sharing
      // wants a different endpoint and a size policy, and pretending otherwise
      // would silently corrupt whatever he dropped.
      if (!TEXTY.test(f.name)) { setNote({ t: `${f.name}: text files only for now`, tone: 'err' }); continue }
      const body = await f.text()
      const r = await api.filesWrite({ path: f.name, text: body })
      setNote(r.ok ? { t: `added ${f.name}`, tone: 'ok' } : { t: r.error, tone: 'err' })
    }
    s.refresh?.()
  }

  return (
    <div className={'pad fl' + (dragging ? ' fl-dragging' : '')}
         onDragOver={e => { e.preventDefault(); setDragging(true) }}
         onDragLeave={() => setDragging(false)}
         onDrop={drop}>
      <Body state={s}>{d => (
        <FilesView d={d} open={open} text={text} setText={setText} note={note} dragging={dragging}
                   onRead={read} onSave={save} onClose={() => { setOpen(null); setNote(null) }} />
      )}</Body>
    </div>
  )
}
