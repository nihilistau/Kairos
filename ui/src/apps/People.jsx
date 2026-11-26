import { useCallback, useState } from 'react'
import * as api from '../api.js'
import { usePoll, Body } from './panel.jsx'
import { Button, Chip, Input, Select, State, TextArea } from '../kit/parts.jsx'

/* PEOPLE — who and what she knows: people, pets, places, things; and who her users are
 * (2026-11-26, design §2, §7b; harness/people.py).
 *
 * USERS are people she talks to (user1, user2…). Switching who she is talking to takes a
 * ~20 s restart, because her prefix names you; the window says so and offers it.
 *
 * PROPOSED people come from HER — she met a name in conversation and suggested it. They are
 * not anyone until you confirm them here. Rejecting keeps the row, retired with the reason:
 * nothing is deleted.
 *
 * Prefix `pp-` (G-ROOM-CSS).
 */

const KIND_WORD = { person: 'Person', pet: 'Pet or animal', place: 'Place', thing: 'Thing', org: 'Organisation' }
const KIND_PLURAL = { person: 'People', pet: 'Pets and animals', place: 'Places', thing: 'Things', org: 'Organisations' }

function Row({ r, refresh, setM, kinds }) {
  const [edit, setEdit] = useState(false)
  const [f, setF] = useState({ names: r.names.join(', '), kind: r.kind, pronouns: r.pronouns || '', relation: r.relation || '', notes: r.notes || '' })
  const op = async (b, ok) => {
    const x = await api.peopleOp(b)
    setM(x.ok ? { ok: true, text: x.note || ok } : { ok: false, text: x.error })
    refresh()
    return x
  }
  return (
    <div className={'pp-card' + (r.status === 'proposed' ? ' pp-prop' : '')}>
      <div className="pp-head">
        <span className="pp-name">{r.names[0]}</span>
        {r.names.length > 1 ? <span className="pp-meta">also {r.names.slice(1).join(', ')}</span> : null}
        <Chip tone="neutral">{KIND_WORD[r.kind] || r.kind}</Chip>
        {r.user ? <Chip tone="ok">{r.handle}</Chip> : null}
        {r.active ? <Chip tone="ok">talking to now</Chip> : null}
        {r.status === 'proposed' ? <Chip tone="warn">she suggested this</Chip> : null}
      </div>
      {!edit ? (
        <div className="pp-body">
          {r.relation ? <div>{r.relation}</div> : null}
          {r.pronouns ? <div className="pp-meta">{r.pronouns}</div> : null}
          {r.notes ? <div className="pp-notes">{r.notes}</div> : null}
        </div>
      ) : (
        <div className="pp-edit">
          <Input value={f.names} onChange={e => setF({ ...f, names: e.target.value })} aria-label="names" placeholder="name, then any other names, separated by commas" />
          <div className="pp-row">
            <Select value={f.kind} onChange={e => setF({ ...f, kind: e.target.value })} aria-label="kind">
              {kinds.map(k => <option key={k} value={k}>{KIND_WORD[k] || k}</option>)}
            </Select>
            <Input className="pp-grow" value={f.pronouns} onChange={e => setF({ ...f, pronouns: e.target.value })} placeholder="pronouns" aria-label="pronouns" />
          </div>
          <Input value={f.relation} onChange={e => setF({ ...f, relation: e.target.value })} placeholder="who they are to you, e.g. my sister" aria-label="relation" />
          <TextArea rows={3} value={f.notes} onChange={e => setF({ ...f, notes: e.target.value })} placeholder="anything she should know" aria-label="notes" />
          <div className="pp-row">
            <Button size="sm" variant="primary" onClick={async () => { const x = await op({ op: 'update', id: r.id, ...f, names: f.names.split(',') }, 'Saved.'); if (x.ok) setEdit(false) }}>Save</Button>
            <Button size="sm" variant="ghost" onClick={() => setEdit(false)}>Cancel</Button>
          </div>
        </div>
      )}
      {!edit ? (
        <div className="pp-row">
          {r.status === 'proposed' ? <>
            <Button size="sm" variant="primary" onClick={() => op({ op: 'confirm', id: r.id }, 'Confirmed.')}>Yes, add them</Button>
            <Button size="sm" variant="ghost" onClick={() => op({ op: 'reject', id: r.id }, 'Not added — kept in the record as not confirmed.')}>No</Button>
          </> : null}
          <Button size="sm" onClick={() => setEdit(true)}>Edit</Button>
          {r.user && !r.active ? <Button size="sm" onClick={() => op({ op: 'switch', id: r.id }, 'Switched.')}>Talk as {r.names[0]}</Button> : null}
          {!r.active ? <Button size="sm" variant="ghost" onClick={() => op({ op: 'retire', id: r.id }, 'Retired — kept in the record.')}>Retire</Button> : null}
        </div>
      ) : null}
    </div>
  )
}

export default function People() {
  const state = usePoll(useCallback(() => api.people(), []), 20000)
  const [m, setM] = useState(null)
  const [n, setN] = useState({ name: '', kind: 'person', relation: '', pronouns: '', user: false })
  const [busy, setBusy] = useState(false)
  return (
    <Body state={state}>
      {d => {
        const add = async () => {
          const x = await api.peopleOp(n.user ? { op: 'add_user', name: n.name, pronouns: n.pronouns, relation: n.relation }
            : { op: 'add', name: n.name, kind: n.kind, relation: n.relation, pronouns: n.pronouns })
          setM(x.ok ? { ok: true, text: 'Added ' + x.row.names[0] + (x.row.user ? ' as ' + x.row.handle : '') + '.' } : { ok: false, text: x.error })
          if (x.ok) setN({ name: '', kind: 'person', relation: '', pronouns: '', user: false })
          state.refresh()
        }
        const restart = async () => {
          setBusy(true)
          const r = await api.systemWrite({ op: 'restart_gateway' }).catch(e => ({ ok: false, error: String(e) }))
          setBusy(false)
          setM(r.ok === false ? { ok: false, text: r.error || 'the restart was refused' } : { ok: true, text: 'Restarting — she will be talking to ' + d.active.names[0] + '. This window reconnects by itself.' })
        }
        const groups = [['Users', x => x.user], ['Suggested by her', x => !x.user && x.status === 'proposed'],
                        ...d.kinds.map(k => [KIND_PLURAL[k] || k, x => !x.user && x.status !== 'proposed' && x.kind === k])]
        return (
          <div className="pp pad">
            <div className="pp-lead">Who and what she knows. Facts you tell her are linked to the people they are about; she can suggest someone new, and you confirm.</div>
            {d.switch_pending ? (
              <div className="pp-banner" role="status">She is still talking to the previous user. <b>Restart her</b> to talk as {d.active.names[0]}.
                <Button size="sm" variant="primary" disabled={busy} onClick={restart}>Restart now (about 20 s)</Button></div>
            ) : null}
            {m ? <div className={'pp-msg ' + (m.ok ? 'pp-ok' : 'pp-err')} role={m.ok ? 'status' : 'alert'}>{m.text}</div> : null}

            {groups.map(([title, test]) => {
              const rows = d.people.filter(test)
              if (!rows.length) return null
              return (
                <div key={title} className="pp-group">
                  <div className="pp-gt">{title}</div>
                  {rows.map(r => <Row key={r.id} r={r} refresh={state.refresh} setM={setM} kinds={d.kinds} />)}
                </div>
              )
            })}
            {!d.people.length ? <State title="No one yet">Add the people, pets and places in your life below — or just tell her about them.</State> : null}

            <div className="pp-group pp-add">
              <div className="pp-gt">Add someone or something</div>
              <div className="pp-row">
                <Input className="pp-grow" value={n.name} onChange={e => setN({ ...n, name: e.target.value })} placeholder="name" aria-label="name" />
                <Select value={n.user ? 'user' : n.kind} onChange={e => setN({ ...n, user: e.target.value === 'user', kind: e.target.value === 'user' ? 'person' : e.target.value })} aria-label="kind">
                  <option value="user">A user (someone who talks to her)</option>
                  {d.kinds.map(k => <option key={k} value={k}>{KIND_WORD[k] || k}</option>)}
                </Select>
              </div>
              <div className="pp-row">
                <Input className="pp-grow" value={n.relation} onChange={e => setN({ ...n, relation: e.target.value })} placeholder="who they are to you, e.g. my dog" aria-label="relation" />
                {(n.user || n.kind === 'person') ? <Input className="pp-grow" value={n.pronouns} onChange={e => setN({ ...n, pronouns: e.target.value })} placeholder="pronouns (he / she / they)" aria-label="pronouns" /> : null}
              </div>
              <div className="pp-row"><Button variant="primary" disabled={!n.name.trim()} onClick={add}>Add</Button></div>
            </div>
          </div>
        )
      }}
    </Body>
  )
}
