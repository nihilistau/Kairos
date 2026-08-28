import { useState } from 'react'
import { usePoll, Body } from './panel.jsx'
import * as api from '../api.js'

/* STORY — the narrative machinery, on one screen (2026-08-28, his ask).
 *
 * "Her chapters, her episodes, her becoming, her narrative … a panel that renders
 * exactly her memories that are used, which parts they are, editable, retirable,
 * and all backed up." Three answers, in order:
 *
 *   1. WHAT STANDS IN HER PREFIX NOW — self_block_lines() via /v1/story, the SAME
 *      assembly render_self_model() joins into her standing prompt (verified
 *      byte-identical at the refactor). Every line names the registry row it came
 *      from, so "which parts they are" is attribution, not guesswork.
 *   2. THE CHAPTERS — kind=chapter rows, live and retired, each with the rows the
 *      fold archived into it as footnotes (tombstones, superseded_by=chapter).
 *   3. THE LANES — the self-narrative kinds (becoming lives in the journal panel;
 *      this shows the registry lanes: thought, dream, feeling, narration…).
 *
 * ACTIONS GO THROUGH THE EXISTING DOORS — memoryRelabel (text correction, core
 * star) and memoryForget (tombstone, never delete). This panel owns no verbs of
 * its own; ops.relabel is the law, same as the memory panel.
 *
 * The backup receipt renders at the foot: the question "is all of this backed
 * up" is answered on the same screen that shows what would be lost. */

const SECTION_LABELS = {
  fact: 'who she is — the facts that stand in her prefix (core lead)',
  chapter: 'the chapter that stands',
  narrative: 'her recent becoming',
}
const LANE_ORDER = ['chapter', 'journal', 'self_description', 'dream', 'feeling',
                    'thought', 'narration', 'spoke_up', 'secret_thought']

function StoryRow({ r, onDone, faded }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [errm, setErrm] = useState('')
  const [txt, setTxt] = useState('')            // a WORDING correction; '' = untouched

  async function send(body) {
    setBusy(true); setErrm('')
    try {
      const res = await api.memoryRelabel({ name: r.name, ...body })
      if (!res || res.ok === false) setErrm((res && res.error) || 'refused')
      else onDone()
    } catch (e) { setErrm(String(e).slice(0, 80)) }
    setBusy(false)
  }
  async function retire() {
    if (!window.confirm('Retire this row? It is tombstoned, never deleted.')) return
    setBusy(true)
    try { await api.memoryForget(r.name); onDone() } catch (e) { setErrm(String(e).slice(0, 80)) }
    setBusy(false)
  }

  return (
    <div className={'sty-row' + (faded ? ' gone' : '')}>
      <div className="sty-line" onClick={() => setOpen(!open)}>
        {r.core ? <span className="sty-core" title="core — leads the facts, fold-immune">★</span> : null}
        <span className="sty-text">{r.text}</span>
        {r.kind ? <span className="cls sty-k">{r.kind}</span> : null}
      </div>
      {open ? (
        <div className="sty-act">
          {r.ts ? <span className="muted">{String(r.ts).slice(0, 10)}</span> : null}
          <span className="sal" title="salience">{(r.salience ?? 0).toFixed(2)}</span>
          <button disabled={busy} onClick={() => send({ core: r.core ? 0 : 1 })}
                  title="core: leads the facts section, immune to the fold — never louder in recall">
            {r.core ? 'unpin core' : '★ pin as core'}
          </button>
          <button disabled={busy} onClick={retire}>retire</button>
          <input value={txt} placeholder="correct the wording — keeps the row, notes the edit"
                 onChange={e => setTxt(e.target.value)}
                 onKeyDown={e => { if (e.key === 'Enter' && txt.trim()) send({ text: txt.trim() }) }} />
          {errm ? <span className="err">{errm}</span> : null}
        </div>
      ) : null}
    </div>
  )
}

export default function Story() {
  const st = usePoll(api.story, 30000)
  const mem = usePoll(api.memory, 30000)
  const [lane, setLane] = useState('')
  const refresh = () => { st.refresh(); mem.refresh() }

  return (
    <div className="pad sty">
      <Body state={st}>{d => {
        const facts = (mem.data && mem.data.facts) || []
        const byName = Object.fromEntries(facts.map(r => [r.name, r]))
        const block = d.block || []
        const sections = ['fact', 'chapter', 'narrative'].map(s => (
          [s, block.filter(b => b.section === s)])).filter(([, rows]) => rows.length)

        /* chapters + their folded sources: a fold tombstones the source with
         * superseded_by = the chapter's row name — the footnote joins on that. */
        const chapters = facts.filter(r => r.kind === 'chapter')
        const foldedUnder = {}
        for (const r of facts) {
          if (r.lifecycle && (r.retired_because || '').startsWith('folded into the chapter')) {
            (foldedUnder[r.superseded_by] = foldedUnder[r.superseded_by] || []).push(r)
          }
        }
        const laneRows = lane
          ? facts.filter(r => r.kind === lane && !r.lifecycle)
              .sort((a, b) => (b.ts || '').localeCompare(a.ts || '')).slice(0, 12)
          : []
        const counts = {}
        for (const r of facts) if (r.kind && !r.lifecycle) counts[r.kind] = (counts[r.kind] || 0) + 1
        const bk = d.backup || {}

        return (
          <>
            {/* ── 1. what stands in her prefix, line by line, attributed ── */}
            {sections.map(([s, rows]) => (
              <div key={s} className="sty-sect">
                <div className="sty-h">{SECTION_LABELS[s] || s}
                  <span className="sty-n">{rows.length}</span></div>
                {rows.map((b, i) => byName[b.name]
                  ? <StoryRow key={b.name} r={byName[b.name]} onDone={refresh} />
                  : <div key={s + i} className="sty-row"><div className="sty-line">
                      <span className="sty-text">{b.label}</span></div></div>)}
              </div>
            ))}
            {d.block_error ? <div className="err">{d.block_error}</div> : null}

            {/* ── 2. the chapters, with what the fold archived into them ── */}
            <div className="sty-sect">
              <div className="sty-h">chapters<span className="sty-n">{chapters.length}</span></div>
              {chapters.length === 0 ? (
                <div className="muted">none yet — the first is written after about a week,
                  at the 04:00 boundary of a quiet night.</div>
              ) : chapters
                .sort((a, b) => (b.ts || '').localeCompare(a.ts || ''))
                .map(c => {
                  const fr = foldedUnder[c.name] || []
                  return (
                    <div key={c.name}>
                      <StoryRow r={c} onDone={refresh} faded={!!c.lifecycle} />
                      {fr.length ? (
                        <details className="sty-fold">
                          <summary>{fr.length} memor{fr.length === 1 ? 'y' : 'ies'} folded
                            into this chapter — archived, not erased</summary>
                          {fr.map(f => (
                            <div key={f.name} className="sty-row gone"><div className="sty-line">
                              <span className="sty-text">{f.text}</span>
                              {f.kind ? <span className="cls sty-k">{f.kind}</span> : null}
                            </div></div>
                          ))}
                        </details>
                      ) : null}
                    </div>
                  )
                })}
            </div>

            {/* ── 3. the lanes of her story — becoming itself lives in the journal ── */}
            <div className="sty-sect">
              <div className="sty-h">the lanes</div>
              <div className="chips">
                {LANE_ORDER.filter(k => counts[k]).map(k => (
                  <button key={k} className={'sty-lane' + (lane === k ? ' on' : '')}
                          onClick={() => setLane(lane === k ? '' : k)}>
                    {k} {counts[k]}
                  </button>
                ))}
              </div>
              {lane ? laneRows.map(r => <StoryRow key={r.name} r={r} onDone={refresh} />) : (
                <div className="muted">her becoming — the nightly paragraph — reads in the
                  journal panel; these are the registry lanes behind it.</div>
              )}
            </div>

            {/* ── the backup receipt: same screen as the thing it protects ── */}
            <div className="sty-bk muted">
              {bk.ok
                ? <>backed up hourly — {bk.count ?? '?'} archives,
                    {' '}newest {bk.newest || '?'},
                    {' '}{bk.bytes ? Math.round(bk.bytes / 1048576) + ' MB kept' : ''}</>
                : <span className="warn">
                    {bk.enabled === false ? 'backups are OFF' : 'no backup archive yet'}
                    {bk.error ? ' — ' + bk.error : ''}</span>}
              {' · '}nothing here is deleted — retire tombstones, the fold archives
            </div>
          </>
        )
      }}</Body>
    </div>
  )
}
