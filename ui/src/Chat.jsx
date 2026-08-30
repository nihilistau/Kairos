import { useEffect, useRef, useState } from 'react'
import * as api from './api.js'
import { extractTags, moodOf, traitHue, forSpeech } from './room/tags.js'
import { When } from './room/When.jsx'
import * as speech from './room/speech.js'

/* CHAT — the centre of the room.
 *
 * WHAT THIS DELIBERATELY IS NOT: OpenRoom's ChatPanel is 1,358 lines with prompt
 * building, the tool-calling loop, settings UI and the character portrait all
 * fused together. Kairos already HAS the agent loop, server-side in
 * run_with_tools, where it belongs. The room is a CLIENT. This file renders a
 * stream; it does not decide anything.
 *
 * TOOL CALLS ARE CARDS, NOT TEXT. The gateway emits SSE v2 typed events —
 * {delta} alongside {tool}, {persona}, {image}, {looking} — so a tool call can be shown as
 * what it is instead of as prose that happens to mention one. That distinction is
 * most of the difference between a chat window and a room.
 */
function Marks({ marks }) {
  if (!marks?.length) return null
  return (
    <div className="marks">
      {marks.map((m, i) => {
        // WEAR/SHOW get their own hue rather than borrowing a trait's, so the chip
        // row reads as three kinds of thing at a glance and not as one long list.
        const hue = m.kind === 'mood' ? moodOf(m.value).hue
                  : m.kind === 'wear' ? 288
                  : m.kind === 'show' ? 322
                  : traitHue(m.value)
        return (
          <span key={i} className={'mark ' + m.kind + (m.sign < 0 ? ' minus' : '')}
                style={{ '--h': hue }}>
            {m.kind === 'mood' ? '◆' : m.kind === 'voice' ? '❧'
             : m.kind === 'wear' ? '👗' : m.kind === 'show' ? '▶'
             : m.sign < 0 ? '−' : '+'}
            {m.value}
          </span>
        )
      })}
    </div>
  )
}

export default function Chat({ onMood }) {
  const [turns, setTurns] = useState([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [img, setImg] = useState(null)
  const abort = useRef(null)
  const fileRef = useRef(null)
  const endRef = useRef(null)
  /* INPUT HISTORY (2026-08-25, his ask): up-arrow at the start of the box walks
     back through what he has sent; down walks forward and restores the draft. */
  const sentHistory = useRef([])
  const histIdx = useRef(-1)
  const draft = useRef('')
  /* HER VOICE (2026-08-21): the cursor into the reply that has already been handed to
     the speaker, so each sentence is spoken ONCE, the moment it completes. */
  const spoken = useRef(0)
  const [voice, setVoice] = useState(speech.state())
  useEffect(() => speech.onChange(setVoice), [])

  const scroll = () => requestAnimationFrame(() =>
    endRef.current && endRef.current.scrollIntoView({ block: 'end' }))

  /* ── THE DAY COMES BACK (2026-08-24 audit, R1) ─────────────────────────────────
   * This state started [] and NOTHING loaded history, so F5 — or the dock's own
   * bounce button — emptied the visible log while the server still held both
   * records: maximally divergent exactly when he most wants to scroll back. Her
   * unprompted turns were the worst case — once the outbox drained and the tab
   * refreshed, the room could never show them again. The day transcript is the
   * durable record (his words pre-staple, hers record-stripped), and it renders
   * here on mount. Only into an EMPTY log: a mid-session remount must not double
   * the evening. */
  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const d = await api.day()
        if (!alive || !d?.rows?.length) return
        setTurns(h => h.length ? h : d.rows.map(r => ({
          role: r.role, content: r.content || '', at: r.at, restored: true,
          // the writer files her marks as metadata beside the cleaned text, so a
          // restored turn keeps its chips (2026-08-25, his F5 report)
          savedMarks: Array.isArray(r.marks) ? r.marks : undefined,
          // and her ACTS the same way (2026-08-30, "chips still vanish on refresh"):
          // the day writer files the turn's tool/wear/recall/looked events beside the
          // text, and they render through the same acts row a live turn uses
          events: Array.isArray(r.acts) && r.acts.length ? r.acts : undefined,
          // a lone assistant row is one she spoke unprompted; say so, as live ones do
          unprompted: r.role === 'assistant' && r.unprompted ? true : undefined,
        })))
        scroll()
      } catch (_) { /* gateway down: an empty log is all there is to show */ }
    })()
    return () => { alive = false }
  }, [])

  async function send() {
    const t = text.trim()
    if ((!t && !img) || busy) return
    sentHistory.current.push(t); histIdx.current = -1; draft.current = ''
    /* OFF THE RECORD LEAVES HER HEAD ON EXIT (2026-08-25, his report: "she
       remembers what happened on exit"). The server never persisted the OTR turns —
       but the ROOM kept re-sending them as history, so she carried the private hour
       in-context after the switch went off. Turns made under the switch are marked,
       and once it is off they stop being sent (still visible: display, not prompt).
       One cheap GET per send; a failed read errs to "off", which errs to privacy. */
    let anonNow = false
    try { const a = await api.anon(); anonNow = !!(a && a.on) } catch (_) {}
    /* RESTORED TURNS ARE DISPLAY, NEVER PROMPT (2026-08-25, his 11-minute turn).
     * The day read-back put the whole evening into `turns`, and this line sent it
     * back as history — so his first message carried ~8k tokens the daemon had
     * never committed, and every turn re-prefilled it (65-92 s each, 11 min cold).
     * The server holds the durable record; what the room re-shows, it must not
     * re-send. Cost, stated: after a refresh she starts a fresh conversation —
     * exactly the pre-restore behaviour, now just with the evening visible. */
    const history = [...turns.filter(x => x.role && !x.restored && (!x.otr || anonNow)),
                     { role: 'user', content: t }]
    // WHEN, ON BOTH SIDES. His turn is stamped as he sends it and hers as the stream
    // opens, so a long generation reads as having started when she started rather than
    // when she finished — which on a cold prefill is two minutes of difference and the
    // whole reason he asked for the chip.
    const now = Date.now()
    setTurns(h => [...h, { role: 'user', content: t, img, at: now, otr: anonNow || undefined },
                         { role: 'assistant', content: '', events: [], at: now, otr: anonNow || undefined }])
    setText(''); setBusy(true); scroll()
    if (onMood) onMood(null, true)   // she is thinking
    const attached = img; setImg(null); if (fileRef.current) fileRef.current.value = ''

    abort.current = new AbortController()
    // A NEW TURN OF HIS INTERRUPTS HER OUT LOUD, the way it does on the screen.
    speech.stop(); spoken.current = 0
    let spokenText = ''
    try {
      for await (const ev of api.chat(history, { image_b64: attached, signal: abort.current.signal })) {
        setTurns(h => {
          // A NEW OBJECT, NEVER A MUTATED ONE (2026-08-22): under React.StrictMode an
          // updater runs twice, so `last.content +=` doubled deltas and `last.events`
          // took every act chip twice (index keys then collided). Build the new turn.
          const prev = h[h.length - 1]
          const last = { ...prev, events: prev.events ? [...prev.events] : [] }
          if (ev.delta) {
            last.content = (prev.content || '') + ev.delta
            const mk = extractTags(last.content).marks.filter(m => m.kind === 'mood')
            if (mk.length && onMood) onMood(mk[mk.length - 1].value)
            // SPEAK AS SHE WRITES: every sentence that has closed goes to the voice now,
            // with her marks stripped and her voice tags kept. The cursor is over the
            // speech text, not the raw, so a mark removed mid-stream cannot shift it.
            spokenText = forSpeech(last.content)
            spoken.current = speech.feed(spokenText, spoken.current)
          }
          // ONE PERSONA CHIP PER TURN, ALWAYS (2026-08-22). The gateway emits her state at the
          // top of a turn AND the verified shift after it: rendering both wore two chips, one
          // stale — but rendering only the SHIFT took away the state readout he actually reads
          // her by, and on a turn where nothing moved there was no chip at all. So: keep ONE,
          // let a later event replace an earlier one, and let the chip say whether it moved.
          else if (ev.persona) {
            const rest = last.events.filter(e => !e.persona)
            const prevP = last.events.find(e => e.persona)
            /* `changed` is a SIBLING of persona on the wire ({persona: state, changed: true})
               and was read as a child — the chip never once showed its ◆ (2026-08-29 audit,
               the same field/value mismatch the comment at the chip itself was written for).
               Fold it in here so the render side reads one object. And the LIVE mood chip
               re-syncs from the server state — live.mood was sticky on her last mark and
               ignored adjust_mood()/panel changes for the rest of the session. */
            const merged = { ...(prevP ? prevP.persona : {}), ...ev.persona,
                             changed: !!(ev.changed || (prevP && prevP.persona.changed)) }
            last.events = [...rest, { persona: merged }]
            if (onMood && ev.persona.mood) onMood(String(ev.persona.mood))
          }
          /* (`ev.final` handler removed 2026-08-24 — the gateway stopped emitting it
             when the analysis cut moved to the record; a dead handler over a retired
             event is how the next {"final"} means something else entirely.) */
          /* HER THINKING, ON HIS SCREEN (2026-08-24 audit, R2 — his call: "it is half
             her spoken content a lot of the time"). The gateway has emitted the
             thought lane since ADR-013 and only the LEGACY console rendered it; the
             room — the client he actually uses — silently dropped both events. */
          else if (ev.thinking_delta) last.thinking = (prev.thinking || '') + ev.thinking_delta
          else if (ev.thinking_end) last.thinking = (prev.thinking || '') || last.thinking
          else if (ev.tool || ev.image || ev.looking || ev.notice || ev.wear) last.events = [...last.events, ev]
          /* THE MACHINE'S WORDS ARE CHIPS, NEVER HER CONTENT (2026-08-24 audit, B11).
             `[error: …]` appended to content went back out in `history` on the next
             send — engine text committed into her mouth in the daemon's own cache. */
          else if (ev.error) last.events = [...last.events, { notice: String(ev.error) }]
          else if (ev.anon) last.events = [...last.events,
            { notice: 'off the record — nothing from this conversation is being kept' }]
          else if (ev.recall_decline) last.events = [...last.events,
            { notice: 'a private thing was asked about — held' }]
          else if (ev.recall) last.events = [...last.events, { recall: ev.recall }]
          else if (ev.silence) last.events = [...last.events,
            { notice: 'she noticed a quiet around this' }]
          return [...h.slice(0, -1), last]
        })
        scroll()
      }
    } catch (e) {
      if (e.name !== 'AbortError') {
        // a NEW object (the StrictMode double-append lesson, which this branch alone
        // had kept — audit R3) and a CHIP, not content (audit B11, same as ev.error)
        setTurns(h => {
          const prev = h[h.length - 1]
          const last = { ...prev, events: [...(prev.events || []),
                                           { notice: 'stream failed: ' + e.message }] }
          return [...h.slice(0, -1), last]
        })
      }
    } finally {
      setBusy(false); abort.current = null
      // the tail — whatever closed the reply without a sentence end behind it
      if (spokenText) spoken.current = speech.flush(spokenText, spoken.current)
    }
  }

  /* ── THE LAST MILE, MISSING FOR THE THIRD TIME ────────────────────────────────
   * Everything upstream of this worked. The impulse fired, the policy allowed it, she
   * generated, worth_saying let it through, the scheduler filed the message — and the
   * ROOM never asked for it. Measured 2026-08-02: 27 messages spoken, TWELVE still
   * sitting in the outbox, and the operator's report was "she hasn't spoken up at all".
   *
   * console/index.html has had this poller since 2026-07-31, and its own comment says
   * "THE LAST MILE, AND IT WAS MISSING TWICE" — first nothing polled, then only a fork
   * nobody opens. This is the third, in the interface that became the main one.
   *
   * HER TURN GOES INTO `turns`, not just onto the screen. `turns` is what send() slices
   * for the next request, so a message shown but not kept would leave a hole exactly
   * where she had spoken: she would say something and then not know she had said it.
   */
  useEffect(() => {
    let alive = true
    const tick = async () => {
      if (!alive || busy || abort.current) return   // never interleave with a live stream
      try {
        const { messages } = await api.kairosOutbox()
        if (!alive || !messages?.length) return
        /* HER OWN-TIME TURNS WEAR THE SWITCH TOO (2026-08-29 audit): send() stamps
           otr and this poller did not, so turns she SPOKE during a private hour sat
           unstamped and were re-sent as history forever after the switch went off —
           the exact bug the history filter was written for, on the other path that
           appends turns. Same cheap GET, same err-to-off. */
        let otrNow = false
        try { const a = await api.anon(); otrNow = !!(a && a.on) } catch (_) {}
        setTurns(h => [...h, ...messages.map(m => ({
          role: 'assistant', content: m.text, unprompted: true, otr: otrNow || undefined,
          // `at` is the scheduler's own stamp, not the moment the poll happened to
          // notice. She may have spoken three minutes before this tick drained it, and
          // showing the drain time would put her words at the wrong point in his evening.
          kind: m.kind, mode: m.mode, speak: m.speak, why: m.reason, at: m.at,
        }))])
        const last = messages[messages.length - 1]
        const mk = extractTags(last.text).marks.filter(m => m.kind === 'mood')
        if (mk.length && onMood) onMood(mk[mk.length - 1].value)
        // SHE SPEAKS UNPROMPTED OUT LOUD TOO — a check-in that only appears as text is
        // half a check-in when the room has a voice.
        // (a presence-mode turn with presence.voice off says speak:false — bubble only)
        messages.forEach(m => { if (m.speak !== false) speech.say(forSpeech(m.text)) })
        scroll()
      } catch (_) { /* gateway down: the room still works, she just cannot speak first */ }
    }
    const id = setInterval(tick, 4000)
    tick()
    return () => { alive = false; clearInterval(id) }
  }, [busy])

  function attach(e) {
    const f = e.target.files && e.target.files[0]
    if (!f) return
    const r = new FileReader()
    r.onload = () => setImg(r.result)
    r.readAsDataURL(f)
  }

  return (
    <div className="chat">
      <div className="log">
        {turns.map((t, i) => {
          // HER MARKS ARE NOT SPEECH. persona.md: "they vanish from what he sees".
          // The old console has stripped them since 2026-07-29; the room was built
          // later and never learned, so he has been reading her stage directions.
          const parsed = t.role === 'assistant' ? extractTags(t.content) : null
          return (
          <div key={i} className={'turn ' + t.role
            + (t.unprompted ? ' unprompted' : '')
            + (t.kind === 'solo' ? ' solo' : '')}>
            {/* SHE SAYS WHY, AND IT IS ON THE PAGE. An unprompted message with no
                account of itself is indistinguishable from a bug.
                AND THEY ARE NOT THE SAME KIND OF THING (2026-08-04). Four different acts
                were reaching him under one word: her finishing her own sentence, her
                reaching for him, her keeping a promise, and — new — her doing something
                of her own while he is out. "spoke up" for all of them is why an evening
                of them read as one machine repeating itself. A solo turn especially is
                NOT addressed to him; it is a diary line he happens to be able to read,
                and it is styled as one. */}
            {/* THE HEADER LINE. Who, why they spoke unasked, and WHEN — one row, on
                every turn, his and hers alike. His ask was "a date and time chip to all
                actions/dialog, both mine and hers", and "both" is the operative half:
                a timestamp on only her side reads as instrumentation of her rather than
                a record of the evening. */}
            <div className="turn-head">
              {t.unprompted ? (
                <span className={'kairos-tag k-' + (t.kind || 'spoke')} title={t.why || ''}>
                  {t.kind === 'continue' ? 'picked the thread back up'
                   : t.kind === 'expand'   ? 'one more thing'
                   : t.kind === 'remind' ? 'reminding you'
                   : t.kind === 'muse'   ? 'been thinking'
                   : t.kind === 'solo'   ? 'her own time'
                   : t.kind === 'mode'   ? (t.mode === 'lucid' ? 'dreaming'
                                            : t.mode === 'company' ? 'keeping you company'
                                            : 'narrating')
                   : 'spoke up'}
                </span>
              ) : null}
              <When at={t.at} />
            </div>
            {t.img ? <img className="thumb" src={t.img} alt="" /> : null}
            {/* WHAT SHE DID, AS THINGS SHE DID. These were a grey line of prose that
                read like debug output; they are ACTS — she looked something up, she
                looked at the room, she changed her mood — and a chip says so where a
                sentence fragment does not. Same row as her marks, immediately below,
                because from his side "she checked the board" and "she got happier" are
                the same kind of event in the same moment. */}
            {(t.events || []).length ? (
              <div className="acts">
                {(t.events || []).map((ev, j) => ev.tool ? (
                  <span key={j} className="act act-tool"
                        title={String(ev.tool.result || '')}>
                    <b>{ev.tool.name || 'tool'}</b>
                    <span className="act-out">{String(ev.tool.result || '').slice(0, 64)}</span>
                  </span>
                ) : ev.image ? (
                  /* WHAT SHE SAW, WIDE (2026-08-21, his ask). 64 chars made a real
                     description look truncated — the cut he chased was actually the
                     vision ceiling (sight._look_tokens), but the chip owes honesty
                     too: a readable first line, and the WHOLE text one click away.
                     SHE always received the full string; this is only display. */
                  <details key={j} className="act act-look act-img">
                    <summary>
                      <b>looked</b>
                      <span className="act-out">
                        {String(ev.image.seen || ev.image.error || '').slice(0, 220)}
                      </span>
                    </summary>
                    <div className="act-img-full">{String(ev.image.seen || ev.image.error || '')}</div>
                  </details>
                ) : ev.persona ? (
                  /* the gateway sends {"persona": state} — the flat mood/voice/traits dict
                     (app.py's persona events). There is no .field/.value; rendering those
                     produced a chip that said only "persona" (his report, 2026-08-22). */
                  /* her MOOD first and never cut mid-word (2026-08-22: "mood: prim"); the
                     rest of the state is in the title. */
                  <span key={j} className={'act act-persona' + (ev.persona.changed ? ' moved' : '')}
                        title={Object.entries(ev.persona)
                          .filter(([k, v]) => v && k !== 'changed')
                          .map(([k, v]) => k + ': ' + (Array.isArray(v) ? v.join(' ') : v)).join(' · ')
                          + (ev.persona.changed ? ' — she moved this turn' : ' — unchanged this turn')}>
                    <b>{ev.persona.changed ? '◆ mood' : 'mood'}</b>
                    <span className="act-out">
                      {[ev.persona.mood ? String(ev.persona.mood) : '',
                        ev.persona.voice ? 'voice: ' + String(ev.persona.voice) : '']
                        .filter(Boolean).join(' · ') || 'unchanged'}
                    </span>
                  </span>
                ) : ev.looking ? (
                  <span key={j} className="act act-look">
                    <b>{ev.looking.phase === 'start' ? 'looking up' : 'looked up'}</b>
                    <span className="act-out">{String(ev.looking.q || ev.looking.tool || '').slice(0, 64)}</span>
                  </span>
                ) : ev.wear ? (
                  /* SHE CHANGED, WHICHEVER DOOR SHE TOOK (2026-08-24, he caught it).
                     A `[WEAR:]` mark draws a chip because this file parses the mark out
                     of her text. `wear()` the TOOL drew nothing — and that is the half
                     she actually uses. The wardrobe emits at its one writer now, so the
                     chip no longer depends on which way she did it. Same glyph and same
                     hue as the mark's chip, deliberately: it is the same event. */
                  <span key={j} className="act act-wear"
                        title={'she is wearing ' + String(ev.wear.label || ev.wear.outfit || '')}>
                    <b>👗 wearing</b>
                    <span className="act-out">{String(ev.wear.label || ev.wear.outfit || '')}</span>
                  </span>
                ) : ev.recall ? (
                  /* WHAT SHE REMEMBERED INTO THIS TURN (2026-08-24, audit D8): the
                     gateway has emitted this event since ADR-008 and only the legacy
                     console drew it — in the room, recall was invisible. The facts
                     ride the title; the chip stays small. */
                  <span key={j} className="act act-recall"
                        title={(Array.isArray(ev.recall) ? ev.recall : []).join('\n')}>
                    <b>remembered</b>
                    <span className="act-out">
                      {(Array.isArray(ev.recall) ? ev.recall : []).length + ' thing' +
                       ((ev.recall || []).length === 1 ? '' : 's')}
                    </span>
                  </span>
                ) : ev.notice ? (
                  /* SOMETHING THE MACHINE DID TO THIS TURN — today only the context trim
                     (harness/inference/context.py). A chip and not her words, for the same
                     reason the wordless-turn message is a notice: engine text in her mouth
                     is its own kind of leak. The whole sentence is in the title AND in the
                     body, because a thing he needs to know is not a thing to make him hover. */
                  <span key={j} className="act act-notice" title={String(ev.notice)}>
                    <b>note</b>
                    <span className="act-out">{String(ev.notice)}</span>
                  </span>
                ) : null)}
              </div>
            ) : null}
            {parsed || t.savedMarks ? (
              <Marks marks={(parsed && parsed.marks && parsed.marks.length)
                            ? parsed.marks : (t.savedMarks || [])} />
            ) : null}
            {/* HER THINKING, folded (audit R2). Collapsed by default — it is hers —
                but one click away, because he told us he reads her by it. */}
            {t.thinking ? (
              <details className="thinking">
                <summary>her thinking</summary>
                <div className="thinking-body">{t.thinking}</div>
              </details>
            ) : null}
            <div className="txt">{parsed ? parsed.text : t.content}</div>
          </div>
        )})}
        <div ref={endRef} />
      </div>

      {img ? (
        <div className="attached">
          <img src={img} alt="" />
          <span>she will look at this</span>
          <button onClick={() => { setImg(null); if (fileRef.current) fileRef.current.value = '' }}>remove</button>
        </div>
      ) : null}

      <div className="composer">
        <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={attach} />
        <button className="tool-btn" onClick={() => fileRef.current && fileRef.current.click()} title="attach an image">📎</button>
        {/* HER VOICE, VISIBLE: lit while she is speaking, a click hushes the rest of
            what is queued. The on/off switch itself is the voice.enabled knob (voice
            panel / settings) — this never overrides it, it only stops the current run. */}
        <button className={'tool-btn spk' + (voice.playing ? ' on' : '') + (voice.enabled ? '' : ' off')}
                onClick={() => speech.stop()}
                title={!voice.enabled ? 'her voice is off (voice.enabled)'
                       : voice.playing ? 'speaking — click to hush' : 'her voice is on'}>
          {voice.enabled ? (voice.playing ? '🔊' : '🔈') : '🔇'}
        </button>
        <textarea value={text} placeholder="talk to her"
                  onChange={e => { setText(e.target.value); histIdx.current = -1 }}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
                    /* up/down walk his previous inputs — only from the box's edges,
                       so arrowing INSIDE a multi-line draft still moves the caret */
                    else if (e.key === 'ArrowUp' && e.target.selectionStart === 0
                             && sentHistory.current.length) {
                      e.preventDefault()
                      if (histIdx.current === -1) {
                        draft.current = text
                        histIdx.current = sentHistory.current.length
                      }
                      if (histIdx.current > 0) {
                        histIdx.current -= 1
                        setText(sentHistory.current[histIdx.current])
                      }
                    } else if (e.key === 'ArrowDown' && histIdx.current !== -1
                               && e.target.selectionStart >= text.length) {
                      e.preventDefault()
                      histIdx.current += 1
                      if (histIdx.current >= sentHistory.current.length) {
                        setText(draft.current || ''); histIdx.current = -1
                      } else {
                        setText(sentHistory.current[histIdx.current])
                      }
                    }
                  }} />
        {busy
          ? <button className="send stop" onClick={() => abort.current && abort.current.abort()}>stop</button>
          : <button className="send" onClick={send}>send</button>}
      </div>
    </div>
  )
}
