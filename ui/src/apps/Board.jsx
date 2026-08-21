import { useState } from 'react'
import { usePoll, Body } from './panel.jsx'
import { When } from '../room/When.jsx'
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
export default function Board() {
  const s = usePoll(() => api.notes(true), 20000)
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
      <Body state={s}>{d => {
        const rows = d.notes || d.items || []
        const retired = d.retired || []
        const cats = d.categories || ['note', 'idea', 'reminder', 'task', 'important', 'watch']
        return (
          <>
            <div className="bd-bar">
              <button className="bd-btn bd-add" onClick={() =>
                setDraft(draft ? null : { title: '', body: '', category: 'note', due: '' })}>
                {draft ? 'cancel' : '+ add'}
              </button>
              {retired.length ? (
                <button className={'bd-btn' + (showRetired ? ' on' : '')}
                        onClick={() => setShowRetired(v => !v)}>
                  retired ({retired.length})
                </button>
              ) : null}
              <span className="bd-count">{rows.length} on the board</span>
            </div>
            {err ? <div className="err">{err}</div> : null}

            {draft ? (
              <NoteForm value={draft} cats={cats} busy={!!busy} submit="put it up"
                        onChange={setDraft}
                        onSave={async () => {
                          if (!draft.title.trim()) { setErr('a note needs a title'); return }
                          const r = await write(api.noteAdd, draft)
                          if (r && r.ok) setDraft(null)
                        }} />
            ) : null}

            {!rows.length && !draft ? <div className="muted">the board is empty</div> : null}

            {rows.map((n, i) => editing === n.id ? (
              <NoteForm key={n.id || i} value={n} cats={cats} busy={!!busy} submit="save"
                        onChange={v => { rows[i] = v; setEditing(n.id) }}
                        onSave={async (v) => {
                          const r = await write(api.noteUpdate, { id: n.id, ...v })
                          if (r && r.ok) setEditing('')
                        }}
                        onCancel={() => { setEditing(''); s.refresh() }} />
            ) : (
              <div key={n.id || i} className={'note' + (n.done ? ' done' : '')}>
                <div className="t">{n.title}</div>
                <div className="meta">
                  <span className="cat">{n.category}</span>
                  <span className="who">{n.author || n.speaker || '—'}</span>
                  {/* WHEN, on every row, in the same words as everywhere else. */}
                  <When at={n.updated_at || n.ts} />
                  {n.due_at ? <span className="due">due <When at={n.due_at} bare /></span> : null}
                </div>
                {n.body ? <div className="b">{n.body}</div> : null}
                <div className="bd-acts">
                  <button className="bd-btn" disabled={!!busy}
                          onClick={() => setEditing(n.id)}>edit</button>
                  <button className={'bd-btn' + (n.done ? ' on' : '')} disabled={!!busy}
                          onClick={() => write(api.noteUpdate, { id: n.id, done: !n.done })}>
                    {n.done ? 'not done' : 'done'}
                  </button>
                  <button className="bd-btn bd-danger" disabled={!!busy}
                          onClick={() => write(api.noteRemove, { id: n.id })}>retire</button>
                </div>
              </div>
            ))}

            {showRetired && retired.length ? (
              <div className="bd-retired">
                <div className="bd-head">retired — kept, not deleted</div>
                {retired.map((n, i) => (
                  <div key={n.id || i} className="note gone">
                    <div className="t">{n.title}</div>
                    <div className="meta">
                      <span className="cat">{n.category}</span>
                      <span className="who">{n.author || n.speaker || '—'}</span>
                      <When at={n.updated_at || n.ts} />
                    </div>
                    <div className="bd-acts">
                      <button className="bd-btn" disabled={!!busy}
                              onClick={() => write(api.noteRestore, { id: n.id })}>
                        put it back
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </>
        )
      }}</Body>
    </div>
  )
}

/* One form for add and for edit, because they are the same fields and two copies of a
 * form is two places for the due-date parsing to disagree. `due` is sent as the RAW
 * words — "friday", "in an hour" — and parsed server-side by duetime.parse_due, so the
 * panel and her `add_note(due=...)` tool read times identically. A second parser here
 * is exactly how a reminder ends up firing on a different Friday. */
function NoteForm({ value, cats, busy, submit, onChange, onSave, onCancel }) {
  const [v, setV] = useState({
    title: value.title || '', body: value.body || '',
    category: value.category || 'note', due: '',
  })
  const set = (k, x) => { const nv = { ...v, [k]: x }; setV(nv); onChange && onChange(nv) }
  return (
    <div className="bd-form">
      <input className="bd-in" placeholder="what to keep in view" value={v.title}
             onChange={e => set('title', e.target.value)} />
      <textarea className="bd-in bd-area" placeholder="anything more (optional)" value={v.body}
                onChange={e => set('body', e.target.value)} />
      <div className="bd-frow">
        <select className="bd-in bd-sel" value={v.category}
                onChange={e => set('category', e.target.value)}>
          {cats.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <input className="bd-in bd-due" placeholder={value.due_at
          ? 'due ' + String(value.due_at).slice(0, 16) + ' — type to change'
          : 'when? "friday", "in an hour" (optional)'}
               value={v.due} onChange={e => set('due', e.target.value)} />
      </div>
      <div className="bd-acts">
        <button className="bd-btn bd-save" disabled={busy} onClick={() => onSave(v)}>{submit}</button>
        {onCancel ? <button className="bd-btn" disabled={busy} onClick={onCancel}>cancel</button> : null}
      </div>
    </div>
  )
}
