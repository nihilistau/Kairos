import { useCallback, useState } from 'react'
import { usePoll, Body } from './panel.jsx'
import { When } from '../room/When.jsx'
import { Button, Chip, Input, Select, State, TextArea } from '../kit/parts.jsx'
import * as api from '../api.js'

/* BOARD — notes, reminders, watches. HIS SIDE OF IT, with hands.
 *
 * Deliberately NOT memory, and the distinction is load-bearing: memory is what is
 * TRUE about someone; the board is what either of them wants kept in view. Blurring
 * them is how the fact store filled up with shopping lists.
 *
 * ── IT WAS READ-ONLY, AND NOBODY HAD NOTICED (2026-08-05) ──────────────────────────
 * His words: "the board is no longer editable by me, it used to have and needs edit
 * button, add/remove button, completed, retired etc."
 *
 * The three routes were all there — /v1/notes/{add,update,remove} — fully implemented,
 * author-stamped, due-parsed, and reachable by nothing. This panel rendered rows and
 * offered not one control. So the board was a thing SHE could write and he could only
 * read, which is the precise inversion of what a shared board is for. Same shape as the
 * `Scenario.opening` finding: the capability existed, the button did not.
 *
 * FOUR CONTROLS, AND THEY ARE FOUR BECAUSE THEY MEAN FOUR THINGS:
 *   • edit      — fix the wording. update() keeps `prev` for one step of undo.
 *   • done      — it happened. Reversible, stays on the board, struck through.
 *   • retire    — off the board. TOMBSTONE (lifecycle=1), never a delete.
 *   • restore   — back on. The undo for retire, without which the tombstone is a
 *                 delete with better paperwork.
 * Collapsing done and retire into one "x" is how "I finished it" and "I never want to
 * see it again" become the same gesture, and then neither is recoverable.
 *
 * `author` is shown because ownership here is set by WHICH DOOR a write came
 * through, never inferred from the text — a rule the fact store spent a day
 * learning and the board is not going to relearn. This panel is HIS door: the server
 * stamps SPEAKER_USER on everything that arrives here, whatever the body says.
 *
 * Prefix `bd-`, per the appRegistry CSS-ownership rule that G-ROOM-CSS enforces.
 */

/* The window's body, split out so G-ROOM-KIT leg 12 can render it with a fixture. The
 * four controls stay four and stay kit Buttons: edit ghost, done secondary (its label says
 * what it will do, so no pressed state), retire danger, put it back secondary. "retired
 * (N)" shows or hides a list under a steady name, so it is a pressed toggle. The add
 * form's "put it up" is the window's one primary; an edit saves in secondary, because an
 * edit can be open beside the add form. */
export function BoardView({ d, busy, err, setErr, editing, setEditing, draft, setDraft,
                            showRetired, setShowRetired, write, refresh }) {
  const rows = d.notes || d.items || []
  const retired = d.retired || []
  const cats = d.categories || ['note', 'idea', 'reminder', 'task', 'important', 'watch']
  return (
    <>
      <div className="bd-bar">
        <Button size="sm" onClick={() =>
          setDraft(draft ? null : { title: '', body: '', category: 'note', due: '' })}>
          {draft ? 'cancel' : '+ add'}
        </Button>
        {retired.length ? (
          <Button size="sm" variant="ghost" aria-pressed={showRetired}
                  onClick={() => setShowRetired(v => !v)}>
            {'retired (' + retired.length + ')'}
          </Button>
        ) : null}
        <span className="bd-count"><Chip>{rows.length + ' on the board'}</Chip></span>
      </div>
      {err ? <div className="bd-err"><Chip tone="err" wrap>{err}</Chip></div> : null}

      {draft ? (
        <NoteForm value={draft} cats={cats} busy={!!busy} submit="put it up" primary
                  onChange={setDraft}
                  onSave={async () => {
                    if (!draft.title.trim()) { setErr('a note needs a title'); return }
                    const r = await write(api.noteAdd, draft)
                    if (r && r.ok) setDraft(null)
                  }} />
      ) : null}

      {!rows.length && !draft ? <State kind="empty">the board is empty</State> : null}

      {rows.map((n, i) => editing === n.id ? (
        <NoteForm key={n.id || i} value={n} cats={cats} busy={!!busy} submit="save"
                  onChange={v => { rows[i] = v; setEditing(n.id) }}
                  onSave={async (v) => {
                    const r = await write(api.noteUpdate, { id: n.id, ...v })
                    if (r && r.ok) setEditing('')
                  }}
                  onCancel={() => { setEditing(''); refresh() }} />
      ) : (
        <div key={n.id || i} className={'bd-note' + (n.done ? ' bd-done' : '')}>
          <div className="bd-t">{n.title}</div>
          <div className="bd-meta">
            <Chip>{n.category}</Chip>
            <span className="bd-who">{n.author || n.speaker || '—'}</span>
            {/* WHEN, on every row, in the same words as everywhere else. */}
            <When at={n.updated_at || n.ts} />
            {n.due_at ? <span className="bd-due-at">due <When at={n.due_at} bare /></span> : null}
          </div>
          {n.body ? <div className="bd-b">{n.body}</div> : null}
          <div className="bd-acts">
            <Button size="sm" variant="ghost" disabled={!!busy}
                    onClick={() => setEditing(n.id)}>edit</Button>
            <Button size="sm" disabled={!!busy}
                    onClick={() => write(api.noteUpdate, { id: n.id, done: !n.done })}>
              {n.done ? 'not done' : 'done'}
            </Button>
            <Button size="sm" variant="danger" disabled={!!busy}
                    onClick={() => write(api.noteRemove, { id: n.id })}>retire</Button>
          </div>
        </div>
      ))}

      {showRetired && retired.length ? (
        <div className="bd-retired">
          <div className="bd-head">retired — kept, not deleted</div>
          {retired.map((n, i) => (
            <div key={n.id || i} className="bd-note bd-gone">
              <div className="bd-t">{n.title}</div>
              <div className="bd-meta">
                <Chip>{n.category}</Chip>
                <span className="bd-who">{n.author || n.speaker || '—'}</span>
                <When at={n.updated_at || n.ts} />
              </div>
              <div className="bd-acts">
                <Button size="sm" disabled={!!busy}
                        onClick={() => write(api.noteRestore, { id: n.id })}>put it back</Button>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </>
  )
}

export default function Board() {
  /* STABLE IDENTITY OR AN UNBOUNDED LOOP (2026-08-29 audit): an inline arrow is a
   new fn every render; usePoll re-subscribes on [fn, ms], run() sets state, state
   re-renders — /v1/notes was refetched as fast as the network allowed. Same fix
   Setup.jsx already carries. */
  const pollNotes = useCallback(() => api.notes(true), [])
  const s = usePoll(pollNotes, 20000)
  const [busy, setBusy] = useState('')
  const [editing, setEditing] = useState('')   // note id being edited
  const [draft, setDraft] = useState(null)     // the add form, or null when closed
  const [showRetired, setShowRetired] = useState(false)
  const [err, setErr] = useState('')

  // ONE WRITER for every button on this panel. Each control is a different intent and
  // they must not grow their own error handling — a failed write that renders nothing
  // is the same picture as a write that worked, which is the bug class this whole file
  // is annotated with.
  const write = async (fn, body) => {
    setBusy(JSON.stringify(body))
    setErr('')
    try {
      const r = await fn(body)
      if (r && r.ok === false) setErr(r.error || 'refused')
      else s.refresh()
      return r
    } catch (e) {
      setErr(String(e.message || e))
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="pad">
      <Body state={s}>{d => (
        <BoardView d={d} busy={busy} err={err} setErr={setErr} editing={editing} setEditing={setEditing}
                   draft={draft} setDraft={setDraft} showRetired={showRetired} setShowRetired={setShowRetired}
                   write={write} refresh={() => s.refresh()} />
      )}</Body>
    </div>
  )
}

/* One form for add and for edit, because they are the same fields and two copies of a
 * form is two places for the due-date parsing to disagree. `due` is sent as the RAW
 * words — "friday", "in an hour" — and parsed server-side by duetime.parse_due, so the
 * panel and her `add_note(due=...)` tool read times identically. A second parser here
 * is exactly how a reminder ends up firing on a different Friday. */
function NoteForm({ value, cats, busy, submit, primary, onChange, onSave, onCancel }) {
  const [v, setV] = useState({
    title: value.title || '', body: value.body || '',
    category: value.category || 'note', due: '',
  })
  const set = (k, x) => { const nv = { ...v, [k]: x }; setV(nv); onChange && onChange(nv) }
  const duePh = value.due_at
    ? 'due ' + String(value.due_at).slice(0, 16) + ' — type to change'
    : 'when? "friday", "in an hour" (optional)'
  return (
    <div className="bd-form">
      <Input aria-label="what to keep in view" placeholder="what to keep in view" value={v.title}
             onChange={e => set('title', e.target.value)} />
      <TextArea aria-label="anything more (optional)" placeholder="anything more (optional)" value={v.body}
                onChange={e => set('body', e.target.value)} />
      <div className="bd-frow">
        <Select className="bd-sel" aria-label="category" value={v.category}
                onChange={e => set('category', e.target.value)}>
          {cats.map(c => <option key={c} value={c}>{c}</option>)}
        </Select>
        <Input className="bd-due" aria-label={duePh} placeholder={duePh}
               value={v.due} onChange={e => set('due', e.target.value)} />
      </div>
      <div className="bd-acts">
        <Button size="sm" variant={primary ? 'primary' : 'secondary'} disabled={busy}
                onClick={() => onSave(v)}>{submit}</Button>
        {onCancel ? <Button size="sm" variant="ghost" disabled={busy} onClick={onCancel}>cancel</Button> : null}
      </div>
    </div>
  )
}
