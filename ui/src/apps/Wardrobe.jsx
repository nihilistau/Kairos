import { useState } from 'react'
import * as api from '../api.js'
import { usePoll } from './panel.jsx'

/* THE WARDROBE — everything she can be, and who decided.
 *
 * A view onto harness/control/wardrobe.py, which is the one place that answers "what is
 * she wearing" for the room, for her tools, and for the file route. Nothing is computed
 * here: the tiers this panel offers are the tiers the server would actually serve, so it
 * can never show a thumbnail for something the file route refuses.
 *
 * BOTH OF THEM CAN DRESS HER, and the panel says which of them did — `by: her` and
 * `by: him` are different facts and flattening them would hide the thing that makes this
 * hers. He can also take a clip down, which is the one control he needs that she has an
 * equivalent of (stop_showing).
 *
 * Prefix `wr-`, per the appRegistry CSS-ownership rule that G-ROOM-CSS enforces.
 */
export default function Wardrobe() {
  const w = usePoll(api.wardrobe, 4000)
  const [busy, setBusy] = useState('')
  const [ask, setAsk] = useState('')
  const d = w.data
  if (w.error) return <div className="wr-empty">wardrobe unreachable</div>
  if (!d || !d.ok) return <div className="wr-empty">reading the wardrobe…</div>

  const set = async (body) => {
    setBusy(JSON.stringify(body))
    try { await api.wardrobeSet({ ...body, by: 'him' }); w.refresh() } finally { setBusy('') }
  }
  // (the t0..t3 `order` array and the tier_words fallback left 2026-08-24, audit R4:
  // the tiers were renamed 2026-08-23 and are not a ladder any more; a stale ordering
  // constant nothing used was a landmine for whoever wired it up next)
  const words = d.outfit_words || {}

  return (
    <div className="wr">
      {/* HER STATE, HERE — because this IS that system. Mood, voice and traits are
          written by the same marks that now write what she is wearing, so showing them
          apart would be describing two systems where there is one. */}
      {d.her && (d.her.mood || d.her.traits) ? (
        <div className="wr-her">
          {d.her.mood ? <span className="wr-chip wr-mood">◆ {d.her.mood}</span> : null}
          {d.her.voice ? <span className="wr-chip wr-voice">❧ {d.her.voice}</span> : null}
          {String(d.her.traits || '').split(',').map(t => t.trim()).filter(Boolean)
            .slice(0, 8).map(t => <span key={t} className="wr-chip wr-trait">{t}</span>)}
        </div>
      ) : null}

      <div className="wr-now">
        {/* NAME WHAT SHE IS ACTUALLY WEARING. This panel got it right and the portrait
            caption, the heading below, and describe() — the text SHE reads — all got it
            wrong, because each of the four worked it out for itself. It is worked out
            once now, server-side, in wardrobe.wearing_now(). */}
        <b>{(d.wearing_now || {}).words || d.shown}</b>
        <span className="wr-by">{d.by === 'her' ? 'she chose this' :
          d.by === 'him' ? 'you chose this for her' : 'the default'}</span>
        {/* the ceiling badge left with Portrait's (audit R4): clamped is a constant
            false since tiers stopped being a ladder */}
      </div>

      {(d.arrivals || []).length ? (
        /* AN ARRIVAL IS AN EVENT FOR HIM TOO. She hears about it through kairos; this is
           his half of the same moment, and it is at the TOP because a thing that turned
           up while he was away is the first thing worth seeing.
           ── ONE ARRIVAL, NOT TWO (2026-08-05) ────────────────────────────────────────
           There used to be two — the picture, then the motion the next morning — and this
           filtered for the second because the first overstated it. His rule removes the
           first entirely: nothing is in the wardrobe until it moves, so the still is a
           queue stage and `arrivals()` only ever returns motion. The filter is gone
           because there is nothing left to filter.
           IT LEAVES WHEN SHE WEARS IT, not when anybody looks at it. */
        <div className="wr-new">
          <b>just arrived</b>
          <span className="wr-count"> — here until she wears them</span>
          {(d.arrivals || []).map(a => (
            <div key={a.id} className="wr-newrow">
              <video src={`/v1/wardrobe/look?id=${encodeURIComponent(a.id)}&kind=loop`}
                     autoPlay loop muted playsInline />
              <div className="wr-meta">
                <b>{a.want}</b>
                <span>it moves now{(a.kind || 'look') === 'gesture' ? ' · a moment' : ''}
                  {a.told ? '' : ' · she has not been told yet'}</span>
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {(d.wants || []).length ? (
        /* ── THE QUEUE, WITH WHERE EACH THING HAS GOT TO (2026-08-05) ───────────────
           This composed its own idea of "waiting" out of two sources — arrivals that
           were not motion, plus wants(state="asked") — and so a DELAYED row (state
           "delayed", not "asked") appeared in neither and simply vanished. A queue that
           silently drops the rows that need attention is worse than no queue.
           `waiting()` is the one reader now; it stages every row and this colours by it. */
        <>
          <div className="wr-sec">she is waiting on
            <span className="wr-count"> nothing hangs in the wardrobe until it moves</span>
          </div>
          <div className="wr-wants">
            {(d.wants || []).map(w => (
              <div key={w.id} className={'wr-want wr-' + (w.stage || 'ordered')}>
                {w.stage === 'making' || w.stage === 'delayed' ? (
                  /* THE PICTURE IT IS WAITING ON. A thumbnail says "this exists and is
                     half-made" in a way the word "making" does not. */
                  <img className="wr-thumb"
                       src={`/v1/wardrobe/look?id=${encodeURIComponent(w.id)}`} alt=""
                       onError={e => { e.currentTarget.style.display = 'none' }} />
                ) : null}
                <span className="wr-t">{(w.kind || 'look') === 'gesture' ? 'moment' : 'look'}</span>
                {w.want}
                <span className="wr-half" title={w.delay_reason || ''}>
                  {w.stage === 'ordered' ? 'ordered — picture being made'
                   : w.stage === 'making' ? 'picture done · motion still owed'
                   : w.stage === 'delayed' ? 'delayed' + (w.tries > 1 ? ` · ${w.tries} tries` : '')
                   : 'not going to be made'}
                </span>
                <button className="wr-gen wr-dismiss" title="take it off the list (kept in history)"
                        disabled={!!busy}
                        onClick={async () => {
                          setBusy('x' + w.id)
                          try { await api.wardrobeDismiss(w.id); w.refresh() }
                          finally { setBusy('') }
                        }}>✕</button>
                {w.stage !== 'refused' ? (
                  /* GENERATE NOW (2026-08-21): one click, this want, via the API —
                     the day-boundary wait is a fallback, not the plan. */
                  <button className="wr-gen" disabled={!!busy || d.genstatus?.running}
                          onClick={async () => {
                            setBusy(w.id)
                            try { await api.wardrobeGenerate(w.id); w.refresh() }
                            finally { setBusy('') }
                          }}>make it now</button>
                ) : null}
              </div>
            ))}
            <button className="wr-gen wr-gen-all" disabled={!!busy || d.genstatus?.running}
                    onClick={async () => {
                      setBusy('all')
                      try { await api.wardrobeGenerate('') ; w.refresh() }
                      finally { setBusy('') }
                    }}>make everything she is waiting on</button>
            {d.genstatus?.running ? (
              <span className="wr-half"> generating {d.genstatus.what}… (takes minutes; this page keeps up)</span>
            ) : d.genstatus?.last ? (
              <span className="wr-half"> last run: {d.genstatus.last}</span>
            ) : null}
          </div>
        </>
      ) : null}

      {/* ── HIS OWN WANTS (2026-08-21, his ask): describe a look in his words and it
             joins the same queue, same anchoring, same generator as hers. by="him"
             is recorded, so who asked stays a fact. */}
      <div className="wr-sec">ask for a look
        <span className="wr-count"> your words; her face is held automatically</span>
      </div>
      <div className="wr-askrow">
        <input className="wr-ask" placeholder="e.g. an oversized cream sweater by the window, morning light"
               value={ask} onChange={e => setAsk(e.target.value)}
               onKeyDown={async e => {
                 if (e.key === 'Enter' && ask.trim()) {
                   setBusy('ask')
                   try { await api.wardrobeWant(ask.trim()); setAsk(''); w.refresh() }
                   finally { setBusy('') }
                 }
               }} />
        <button className="wr-gen" disabled={!ask.trim() || !!busy}
                onClick={async () => {
                  setBusy('ask')
                  try { await api.wardrobeWant(ask.trim()); setAsk(''); w.refresh() }
                  finally { setBusy('') }
                }}>queue it</button>
      </div>

      {(() => {
        /* ── ONE WARDROBE. TWO LISTS OF CLOTHES WAS AN IMPLEMENTATION DETAIL ─────────
           His words, 2026-08-05: "wardrobe contains Her clothes section and Her wardrobe.
           this makes no sense and is redundant... and they contain separate items."

           He is right, and the split was never about her. "her clothes" rendered
           `d.outfits` — the four rows of the OUTFITS dict in wardrobe.py — and "hers to
           wear" rendered `d.looks`, which comes from the wants file. WHERE THE ROW IS
           STORED was showing through to the surface as two headings, and because they
           were two lists he had to look in both to see what she owned.

           From her side it is one question: what can I put on. `check_wardrobe()` now
           answers it as one list too, so the room and her own eyes describe one wardrobe
           — which is the whole reason that grouping exists.

           The two things that stay separate genuinely are: MOMENTS of her (a way she IS,
           not a garment) and CLIPS (the one act that goes on HIS screen, below).

           NEW is the just-arrived shelf, inline rather than a section of its own: a thing
           that arrived IS a thing hanging there she has not worn yet. It clears the first
           time it goes on her — see wardrobe.note_worn. */
        const newIds = new Set((d.arrivals || []).map(a => a.id))
        const outfits = (d.outfits || []).filter(o => o.have).map(o => ({
          key: 'o:' + o.id, kind: 'outfit', outfit: o.id, label: o.name, sub: o.wearing,
          moves: o.moves, on: d.shown === o.id && !d.look && !d.clip, isNew: false,
          src: `/v1/wardrobe/outfit?outfit=${o.id}`,
          loop: `/v1/wardrobe/outfit?outfit=${o.id}&kind=loop`,
          put: () => set({ outfit: o.id, look: '', clip: '' }),
        }))
        const asked = (d.looks || []).filter(l => l.kind === 'look').map(l => ({
          key: 'l:' + l.id, kind: 'look', outfit: l.made_in, label: l.label,
          sub: 'one she asked for', moves: l.moves, on: d.look === l.id,
          isNew: newIds.has(l.id),
          src: `/v1/wardrobe/look?id=${encodeURIComponent(l.id)}`,
          loop: `/v1/wardrobe/look?id=${encodeURIComponent(l.id)}&kind=loop`,
          put: () => set({ outfit: l.made_in, look: d.look === l.id ? '' : l.id }),
        }))
        const moments = (d.looks || []).filter(l => l.kind === 'gesture').map(l => ({
          key: 'g:' + l.id, kind: 'gesture', outfit: l.made_in, label: l.label,
          sub: 'a moment of her', moves: l.moves, on: d.look === l.id,
          isNew: newIds.has(l.id),
          src: `/v1/wardrobe/look?id=${encodeURIComponent(l.id)}`,
          loop: `/v1/wardrobe/look?id=${encodeURIComponent(l.id)}&kind=loop`,
          put: () => set({ outfit: l.made_in, look: d.look === l.id ? '' : l.id }),
        }))
        /* NEW FIRST, then what is on her, then the rest — the order he would look in. */
        const worn = [...outfits, ...asked].sort(
          (a, b) => (b.isNew - a.isNew) || (b.on - a.on))
        const tile = (t) => (
          <div key={t.key} className={'wr-clip' + (t.on ? ' playing' : '')
                                      + (t.isNew ? ' wr-fresh' : '')}>
            {t.moves
              ? <video src={t.loop} preload="metadata" muted playsInline loop
                       onMouseEnter={e => e.currentTarget.play().catch(() => {})}
                       onMouseLeave={e => e.currentTarget.pause()} />
              : <img src={t.src} alt="" />}
            {t.isNew ? <span className="wr-new-tag">new</span> : null}
            <div className="wr-meta">
              <b>{t.label}</b>
              <span>{t.sub}{t.moves ? ' · moves' : ' · still'}</span>
            </div>
            <button className="wr-play" disabled={!!busy} onClick={t.put}>
              {t.on ? (t.kind === 'outfit' ? 'on her now' : 'take it off') : 'put it on her'}
            </button>
          </div>
        )
        return (
          <>
            <div className="wr-sec">her wardrobe
              <span className="wr-count"> {worn.length} — everything she can put on{
                newIds.size ? ` · ${newIds.size} never worn` : ''}</span>
            </div>
            <div className="wr-clips">{worn.map(tile)}</div>
            {moments.length ? (
              <>
                {/* GENUINELY A DIFFERENT THING. A moment is a way she IS, not a garment —
                    it goes on by the same call, which is why it is here at all, but
                    "laughing properly" is not something hanging in a wardrobe. */}
                <div className="wr-sec">moments of her
                  <span className="wr-count"> {moments.length} — she wears one to say
                    something without saying it</span>
                </div>
                <div className="wr-clips">{moments.map(tile)}</div>
              </>
            ) : null}
          </>
        )
      })()}

      {(d.grid || []).length ? (
        <>
          {/* THE STANDARD SET belongs here too. A panel called "wardrobe" that omits
              three quarters of what she wears is describing a different system than
              the one running. */}
          {/* HONEST ABOUT WHICH IT IS. This read "her seven faces, at a black lace bra
              and panties" while she had the silver nightie on — true of the set, and read
              as a claim about her. When a look is over the top, say so. */}
          {/* IT IS AN OUTFIT, WORN BY SEVEN EXPRESSIONS. Called "the standard set — her
              seven faces", which is what it LOOKS like and not what it IS: t0..t3 are
              four outfits (mesh top / mesh tee / black lace bra and panties / black lace
              and not much of it) and the seven are how she wears the one that is on. So
              the heading led with the axis she does not choose and buried the one she
              does, and the outfit list read as a different system from her wardrobe when
              it is the rest of it. Her face follows her MOOD — express() — not a click,
              and saying so is the difference between a grid and a thing she operates. */}
          <div className="wr-sec">{(words[d.shown] || {}).wearing || d.shown}
            <span className="wr-count"> the standard set — seven ways she wears it{
              (d.wearing_now || {}).kind !== 'outfit'
                ? ', under what she has on' : ''} · her face follows her mood</span>
          </div>
          <div className="wr-grid">
            {(d.grid || []).map(g => (
              <div key={g.id} className={'wr-face' + (d.shown === g.outfit ? ' on' : '')}
                   title={g.face + (g.moves ? ' · moves' : ' · still')}>
                {/* SHE MOVES HERE TOO. Her portrait has preferred the loop since the set
                    was generated; this panel was the last surface still showing her as a
                    photograph. Plays on hover so opening the wardrobe does not start
                    seven videos at once. */}
                {g.moves
                  ? <video src={`/v1/avatar/file?face=${g.face}&kind=loop`}
                           preload="metadata" muted playsInline loop
                           onMouseEnter={e => e.currentTarget.play().catch(() => {})}
                           onMouseLeave={e => e.currentTarget.pause()} />
                  : <img src={`/v1/avatar/file?face=${g.face}&kind=still`} alt="" />}
                <span>{g.face}{g.moves ? ' ·' : ''}</span>
              </div>
            ))}
          </div>
        </>
      ) : null}

      {/* THE ONE GENUINELY DIFFERENT ACT. Everything above is a way she IS; these go on
          HIS screen, which is why they keep a section of their own rather than being
          folded in. Named for the act, so the difference is legible instead of implied. */}
      <div className="wr-sec">
        moments she can put on your screen {d.clips_total ? <span className="wr-count">
          {(d.clips || []).length} on offer{d.clips_total > (d.clips || []).length
            ? ` · ${d.clips_total - (d.clips || []).length} hidden or retired` : ''}</span> : null}
      </div>
      {(d.clips || []).length === 0 ? (
        <div className="wr-empty">
          none on offer — bring one in through the closet below (inbox), or unhide one.
        </div>
      ) : (
        <div className="wr-clips">
          {(d.clips || []).map(c => (
            <div key={c.id} className={'wr-clip' + (d.clip === c.id ? ' playing' : '')}>
              {/* preload=metadata: six videos that each fetch themselves in full would
                  cost tens of megabytes to open a panel. The poster frame is enough to
                  choose by. */}
              <video src={`/v1/wardrobe/file?id=${encodeURIComponent(c.id)}`}
                     preload="metadata" muted playsInline
                     onMouseEnter={e => { e.currentTarget.play().catch(() => {}) }}
                     onMouseLeave={e => { e.currentTarget.pause() }} />
              <div className="wr-meta">
                <b>{c.wearing}</b>
                <span>{c.where}{c.mood ? ' · ' + c.mood : ''}</span>
                {(c.tags || []).length ? <span className="wr-tags">{c.tags.join(' · ')}</span> : null}
              </div>
              <button className="wr-play" disabled={!!busy}
                      onClick={() => set({ clip: d.clip === c.id ? '' : c.id })}>
                {d.clip === c.id ? 'take down' : 'put on the stage'}
              </button>
            </div>
          ))}
        </div>
      )}

      <Closet />

      <div className="wr-note">
        Hers to drive — three kinds, one act each: clothing is <code>wear</code> /
        <code>[WEAR:…]</code>; a gesture is <code>express</code> or <code>gesture</code>;
        a moment is <code>show_him</code> / <code>[SHOW:…]</code> (<code>[SHOW:]</code> takes
        it down). <code>check_wardrobe</code> lists all three by the titles you gave them;
        <code>ask_for</code> and <code>ask_for_gesture</code> make new ones within minutes,
        picture and motion both. There is no ceiling. Hiding or retiring something here
        takes it off her list at once.
      </div>
    </div>
  )
}

/* ── THE CLOSET, MANAGED (2026-08-21, his overhaul) ─────────────────────────────────
 * "a way to remove clothing, gestures and moments (both delete and hide/unhide from the
 * UI)... take video I have generated... title them, describe them, categorize them...
 * edit the title, description and category of current ones."
 *
 * Reads /v1/catalog — everything she can wear, do or show, one shape, his edits on
 * top — and writes through one POST with an op. Remove is a TOMBSTONE (the row and the
 * file stay; restore brings it back); hide is the soft version. The inbox is
 * var/room/avatar/inbox: drop a file there, name it, pick a kind, and it goes through the
 * same tooling a made look does (webm, seamless loop, poster frame). */
function Closet() {
  const c = usePoll(api.catalog, 6000)
  const [busy, setBusy] = useState('')
  const [edit, setEdit] = useState(null)        // {id,title,description,category,tags}
  const [imp, setImp] = useState({})            // file -> {category,title,description,loop}
  const d = c.data
  if (!d || !d.ok) return null
  const op = async (body) => {
    setBusy(body.op + ':' + (body.id || body.file || ''))
    try { const r = await api.catalogOp(body); c.refresh(); return r } finally { setBusy('') }
  }
  const rows = d.rows || []
  const live = rows.filter(r => !r.hidden && !r.removed_at)
  const hidden = rows.filter(r => r.hidden && !r.removed_at)
  const removed = rows.filter(r => r.removed_at)
  const cats = d.categories || ['clothing', 'gesture', 'moment']
  const Row = ({ r, dim }) => (
    <>
      <div className={'wr-row' + (r.on ? ' wr-on' : '') + (dim ? ' wr-dim' : '')}>
        <span title={r.source || ''}>{r.source === 'imported' ? '⇩' : r.source === 'grid' ? '▦' : '✦'}</span>
        {r.still_url ? <img className="wr-thumb2" src={r.still_url} alt=""
                            onError={e => { e.currentTarget.style.visibility = 'hidden' }} />
                     : <video className="wr-thumb2" src={r.loop_url} muted preload="metadata" />}
        <div>
          <span className="wr-cat">{r.category}</span> <span className="wr-ttl">{r.title || r.label}</span>
          {r.on ? <span className="wr-cat"> on her</span> : null}
          {r.moves ? null : <span className="wr-cat"> still</span>}
          {r.description ? <div className="wr-desc">{r.description}</div> : null}
          {r.title && r.base_label && r.base_label !== r.title
            ? <div className="wr-desc">was: {r.base_label}</div> : null}
        </div>
        <div className="wr-acts">
          <button disabled={!!busy} title="edit title, description, kind"
                  onClick={() => setEdit(edit && edit.id === r.id ? null
                    : { id: r.id, title: r.title || '', description: r.description || '',
                        category: r.category, tags: (r.tags || []).join(', ') })}>✎</button>
          {r.removed_at
            ? <button disabled={!!busy} onClick={() => op({ op: 'restore', id: r.id })} title="bring it back">restore</button>
            : r.hidden
              ? <button disabled={!!busy} onClick={() => op({ op: 'unhide', id: r.id })} title="offer it again">unhide</button>
              : <button disabled={!!busy} onClick={() => op({ op: 'hide', id: r.id })} title="keep it, stop offering it">hide</button>}
          {!r.removed_at && r.kind !== 'outfit'
            ? <button disabled={!!busy} className="wr-dismiss" title="retire it (kept — restore below)"
                      onClick={() => op({ op: 'remove', id: r.id })}>✕</button> : null}
        </div>
      </div>
      {edit && edit.id === r.id ? (
        <div className="wr-edit">
          <input value={edit.title} placeholder="title — how you think of it"
                 onChange={e => setEdit({ ...edit, title: e.target.value })} />
          <select value={edit.category} onChange={e => setEdit({ ...edit, category: e.target.value })}>
            {cats.map(k => <option key={k} value={k}>{k}</option>)}
          </select>
          <textarea value={edit.description} placeholder="description — for her, in your words"
                    onChange={e => setEdit({ ...edit, description: e.target.value })} />
          <input value={edit.tags} placeholder="other words it answers to, comma-separated"
                 onChange={e => setEdit({ ...edit, tags: e.target.value })} />
          <div className="wr-editacts">
            <button disabled={!!busy} className="wr-gen"
                    onClick={async () => {
                      await op({ op: 'edit', id: r.id, title: edit.title, description: edit.description,
                                 category: edit.category,
                                 tags: edit.tags.split(',').map(t => t.trim()).filter(Boolean) })
                      setEdit(null)
                    }}>save</button>
            <button disabled={!!busy} onClick={() => setEdit(null)}>cancel</button>
          </div>
        </div>
      ) : null}
    </>
  )
  return (
    <div className="wr-closet">
      <div className="wr-sec">the closet, managed
        <span className="wr-count"> {live.length} on offer · {hidden.length} hidden · {removed.length} retired</span>
      </div>

      <details className="wr-fold" open={(d.inbox || []).length > 0}>
        <summary>bring in your own — inbox ({(d.inbox || []).length})</summary>
        <div className="wr-desc" style={{ marginBottom: 6 }}>
          drop a video or a still into <code>var/room/avatar/inbox</code>, name it here, pick a
          kind. A video becomes a seamless webm loop with a poster frame; a still comes in as a
          still and “make it now” grows its motion. Your file is copied, never moved.
        </div>
        <div className="wr-inbox">
          {(d.inbox || []).length === 0 ? <div className="wr-desc">the inbox is empty</div> : null}
          {(d.inbox || []).map(f => {
            const s = imp[f.file] || { category: f.kind === 'image' ? 'clothing' : 'gesture',
                                       title: '', description: '', loop: true }
            const setS = (p) => setImp({ ...imp, [f.file]: { ...s, ...p } })
            return (
              <div key={f.file} className="wr-inrow">
                <span className="wr-fname">{f.file}</span>
                <select value={s.category} onChange={e => setS({ category: e.target.value })}>
                  {cats.map(k => <option key={k} value={k}>{k}</option>)}
                </select>
                <input value={s.title} placeholder="title (how you think of it)"
                       onChange={e => setS({ title: e.target.value })} />
                <button className="wr-gen" disabled={!!busy}
                        onClick={() => op({ op: 'import', file: f.file, category: s.category,
                                            title: s.title, description: s.description, loop: s.loop })}>
                  bring it in
                </button>
                <input style={{ gridColumn: '1 / 3' }} value={s.description}
                       placeholder="description, for her (optional)"
                       onChange={e => setS({ description: e.target.value })} />
                <label style={{ gridColumn: '3 / 5' }}>
                  <input type="checkbox" checked={s.loop} onChange={e => setS({ loop: e.target.checked })}
                         style={{ width: 'auto', marginRight: 6 }} />
                  seamless loop (forward then back) — off for a one-way moment
                </label>
              </div>
            )
          })}
        </div>
      </details>

      <div className="wr-rows">{live.map(r => <Row key={r.id} r={r} />)}</div>
      {hidden.length ? (
        <details className="wr-fold">
          <summary>hidden ({hidden.length}) — still hers, not offered</summary>
          <div className="wr-rows">{hidden.map(r => <Row key={r.id} r={r} dim />)}</div>
        </details>
      ) : null}
      {removed.length ? (
        <details className="wr-fold">
          <summary>retired ({removed.length}) — nothing is deleted; restore brings one back</summary>
          <div className="wr-rows">{removed.map(r => <Row key={r.id} r={r} dim />)}</div>
        </details>
      ) : null}
    </div>
  )
}
