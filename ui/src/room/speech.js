/* speech.js — HER VOICE IN THE ROOM, the last mile (2026-08-21).
 *
 * The room never spoke her replies. The old console had a queue (console/speech.js);
 * the room was built later and got the test button (knobs.jsx) and nothing else —
 * "if I click test voice the Ara test plays but there is no voice from rendered
 * dialog" (his words). This is the player the room never had.
 *
 * ONE SENTENCE PER CALL, IN ORDER. POST /v1/speak refuses long input by design (the
 * local chain blows up on it; the xAI voice does not but the contract is the same),
 * so the reply is split here on sentence ends, each piece is fetched as its own wav,
 * and they play back to back. The NEXT sentence is fetched while the current one
 * plays, so the gap between them is the network, not the synth. Time-to-first-audio
 * is one sentence — she starts talking while she is still writing — which is why
 * the websocket streaming endpoint is an arming condition, not a need.
 *
 * THE TAGS RIDE ALONG. The text handed here has her marks stripped but her voice
 * tags kept (tags.forSpeech); the gateway's TTS edge decides per method whether the
 * voice reads them. Display never sees them.
 *
 * THE SWITCH IS THE SERVER'S. voice.enabled (live knob) is the authority: when it is
 * off the gateway answers 503 and nothing plays. The room additionally asks
 * /v1/speak/status before it queues, so an off switch costs zero requests.
 */
import { isProbe } from './probe.js'

const MAX_CHARS = 240          // mirrors SP_TTS_MAX_CHARS; the server refuses above it
const ENDS = /([.!?…]+)(\s+|$)/

let queue = []                 // [{text, got?}] — `got` is a fetched sentence kept for a retry
let playing = false
let current = null             // {a, done}: the Audio playing now, and how to release its wait
let enabled = true             // mirrors voice.enabled, refreshed by status()
let lastStatusAt = 0
/* WHY SHE IS QUIET, OR WHO SPOKE INSTEAD (2026-10-29). Grok went silent on him and the room
 * said nothing: every failure here was `.catch(() => null)` or an onerror that resolved
 * quietly, so a 402 from the API and a muted tab looked identical to "she had nothing to say".
 * Every failure path now sets `reason`; the taskbar's VoiceChip shows it. `kind` is 'fail'
 * (she did not speak) or 'note' (she spoke, through a different voice than the one chosen). */
let reason = ''
let reasonKind = ''
let reasonAt = 0
let blockedItem = null         // the sentence autoplay refused, waiting for his first click
let epoch = 0                  // bumped by stop(): a sentence fetched before a hush is not played
/* HELD WHILE HE TALKS (final review, 2026-10-29). Barge-in hushed her ONCE — and her reply was
 * still streaming, so feed() queued the next sentence and she spoke again into his push-to-talk
 * recording. ears.js holds her for as long as the line is being recorded; under the hold
 * say() (and so feed()/flush(), whose cursors still advance) drops what it is given. */
let held = false
const listeners = new Set()

export function onChange(fn) { listeners.add(fn); return () => listeners.delete(fn) }
const emit = () => listeners.forEach(fn => { try { fn(state()) } catch (_) {} })
export function state() { return { playing, queued: queue.length, enabled, reason, reasonKind, reasonAt } }

function fail(why) { reason = String(why || 'speak failed'); reasonKind = 'fail'; reasonAt = Date.now(); emit() }
function note(why) { reason = why; reasonKind = 'note'; reasonAt = Date.now(); emit() }
/* A clean sentence clears the reason — but not one he has had under ten seconds to read. */
function clear() { if (reason && Date.now() - reasonAt > 10000) { reason = ''; reasonKind = ''; emit() } }
/* He has read it (the VoiceChip's click). */
export function dismiss() { reason = ''; reasonKind = ''; emit() }

/* "xai: http 402: out of credit" -> "spoke with lfm3 — Grok: http 402: out of credit". The
 * header names the engine that failed first; xai is Grok to him, any other keeps its name. */
export function fallbackNote(backend, fell) {
  const m = /^\s*([\w-]+):\s*([\s\S]*)$/.exec(String(fell || ''))
  const who = !m || m[1] === 'xai' ? 'Grok' : m[1]
  const why = m ? m[2] : String(fell || '')
  return `spoke with ${backend || 'another voice'} — ${who}: ${why}`
}

/* Sentence split that keeps a tag attached to the sentence it belongs to — a [laugh]
 * at the end of a line stays with that line, a <soft> wrapper is not cut in half. */
export function sentences(text) {
  const out = []
  let rest = String(text || '').replace(/\s+/g, ' ').trim()
  while (rest.length) {
    const m = ENDS.exec(rest)
    let piece
    if (m && m.index + m[0].length <= MAX_CHARS) {
      piece = rest.slice(0, m.index + m[1].length)
      rest = rest.slice(m.index + m[0].length)
    } else if (rest.length <= MAX_CHARS) {
      piece = rest; rest = ''
    } else {
      let cut = rest.lastIndexOf(',', MAX_CHARS)
      if (cut < MAX_CHARS / 3) cut = rest.lastIndexOf(' ', MAX_CHARS)
      if (cut < MAX_CHARS / 3) cut = MAX_CHARS
      piece = rest.slice(0, cut + 1); rest = rest.slice(cut + 1)
    }
    // an unclosed wrapper at the cut is closed and reopened so each piece is whole
    const open = [...piece.matchAll(/<([a-z-]+)>/g)].map(x => x[1])
    const closed = [...piece.matchAll(/<\/([a-z-]+)>/g)].map(x => x[1])
    const dangling = open.filter(t => !closed.includes(t))
    if (dangling.length && rest) {
      piece += dangling.map(t => `</${t}>`).join('')
      rest = dangling.map(t => `<${t}>`).join('') + rest
    }
    piece = piece.trim()
    if (piece && /[a-z0-9]/i.test(piece.replace(/\[[a-z-]+\]|<\/?[a-z-]+>/g, ''))) out.push(piece)
    else if (piece) out.push(piece)   // a bare [laugh] is still worth voicing
  }
  return out
}

async function refreshStatus() {
  if (Date.now() - lastStatusAt < 10000) return enabled
  lastStatusAt = Date.now()
  try {
    const r = await fetch('/v1/speak/status')
    const d = await r.json()
    enabled = !(d && d.live && d.live.enabled === false)
  } catch (e) { fail('voice status unreadable: ' + (e.message || e)) }   // leave `enabled` as it was
  emit()
  return enabled
}

function speakFailed(status, why) {
  return new Error('speak failed: ' + status + ' ' + String(why || '').replace(/\s+/g, ' ').slice(0, 200))
}

/* One sentence -> {url, note}. Throws an Error whose message IS the reason he reads. */
async function fetchWav(text) {
  const r = await fetch('/v1/speak', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  }).catch(e => { throw speakFailed('network', e.message || e) })
  if (!r.ok) {
    const t = await r.text()
    let why
    try { why = JSON.parse(t).error } catch (e) { throw speakFailed(r.status, t) }
    if (/^voice is off/.test(why || '')) throw new Error('voice is switched off')
    throw speakFailed(r.status, why || t)
  }
  const fell = r.headers.get('X-TTS-Fallback') || ''
  return { url: URL.createObjectURL(await r.blob()),
           note: fell ? fallbackNote(r.headers.get('X-TTS-Backend') || '', fell) : '' }
}

/* A promise that never rejects: {v} or {e}. The prefetch may be abandoned by stop(), and an
 * abandoned rejection would otherwise surface as an unhandled one with no reason shown. */
const settle = p => p.then(v => ({ v }), e => ({ e }))

/* Play one url; resolves 'ended' | 'stopped' | 'failed' | 'blocked'. */
function play(url) {
  return new Promise(res => {
    const a = new Audio(url)
    current = { a, done: res }
    a.onended = () => res('ended')
    a.onerror = () => { fail('speak failed: playback ' + ((a.error && a.error.message) || 'the audio would not decode')); res('failed') }
    a.play().catch(e => {
      // A hush during a pending play() rejects it with AbortError — that is the hush, not a
      // failure (final review, 2026-10-29), and neither is anything from an Audio stop() let go.
      if ((e && e.name === 'AbortError') || !current || current.a !== a) return
      if (e && e.name === 'NotAllowedError') res('blocked')
      else { fail('speak failed: playback ' + ((e && e.message) || e)); res('failed') }
    })
  })
}

/* AUTOPLAY. A browser refuses sound until the page has had a click; the room used to drop
 * the sentence silently. Now the sentence is kept (its audio already fetched), the reason
 * says what to do, and his first click or key anywhere in the room plays it — once per
 * refusal — and the rest of the queue follows. */
function blocked(item) {
  blockedItem = item
  fail('autoplay blocked — click the room once')
  const unlock = () => {
    document.removeEventListener('pointerdown', unlock, true)
    document.removeEventListener('keydown', unlock, true)
    const it = blockedItem
    blockedItem = null
    if (it) { queue.unshift(it); pump() }
  }
  document.addEventListener('pointerdown', unlock, true)
  document.addEventListener('keydown', unlock, true)
}

async function pump() {
  if (playing || blockedItem) return
  playing = true; emit()
  let ahead = null           // {item, p}: the prefetch for the NEXT item, tied to that item
  const drop = a => { if (a) a.p.then(r => { if (r.v) URL.revokeObjectURL(r.v.url) }) }
  try {
    while (queue.length) {
      const item = queue.shift()
      if (!item) break                     // a hush emptied the queue under us
      const at = epoch                     // taken before any await: a hush from here on drops it
      if (!item.now && !(await refreshStatus())) { queue = []; fail('voice is switched off'); break }
      if (ahead && ahead.item !== item) { drop(ahead); ahead = null }
      const got = item.got ? { v: item.got }
        : await (ahead ? ahead.p : settle(fetchWav(item.text)))
      // a wav already in hand (playNow, a retry) is never fetched again
      ahead = queue.length && !queue[0].got ? { item: queue[0], p: settle(fetchWav(queue[0].text)) } : null
      if (got.e) { fail(got.e.message || String(got.e)); continue }
      if (at !== epoch) { URL.revokeObjectURL(got.v.url); continue }   // hushed while it was fetched
      item.got = got.v
      const how = await play(item.got.url)
      current = null
      if (how === 'blocked') { blocked(item); break }
      URL.revokeObjectURL(item.got.url)
      if (how === 'ended') { if (item.got.note) note(item.got.note); else clear() }
    }
  } finally { drop(ahead); playing = false; current = null; emit() }
}

/* Queue text to be spoken, in order behind whatever is queued. */
export function say(text) {
  if (isProbe() || held) return   // a probe tab never speaks (probe.js); nor does she over him
  const parts = sentences(text)
  if (!parts.length) return
  queue.push(...parts.map(t => ({ text: t })))
  emit()
  pump()
}

/* Hush. RELEASES the wait on the playing sentence: pause() fires no `ended`, so before
 * 2026-10-29 a hush left pump() awaiting forever with `playing` stuck true — which the
 * mic's gate (ears.js) would have read as "she is speaking" for the rest of the session. */
export function stop() {
  queue = []
  epoch += 1
  if (blockedItem) { URL.revokeObjectURL(blockedItem.got.url); blockedItem = null }
  if (current) {
    const c = current; current = null
    // let go of its handlers FIRST: pause() rejects a pending play(), and the revoke that
    // follows can fire onerror — neither is a reason he should read (final review, 2026-10-29)
    c.a.onerror = null; c.a.onended = null
    c.a.pause(); c.done('stopped')
  }
  emit()
}

/* Hold her (on) while he records a line; release (off) when it is sent or abandoned. */
export function hold(on) { held = !!on; emit() }

/* A WAV ALREADY IN HAND, played through THIS queue (final review, 2026-10-29). The Models
 * window's voice Test used its own `new Audio`: it could overlap her speech, and the mic's gate
 * (ears.js, which reads `playing` here) never saw it — so always-listening heard "This is how
 * I sound right now." as his turn. It queues behind whatever she is saying, and is not
 * re-synthesised. `now` skips the voice.enabled check: he asked for this one by clicking. */
export function playNow(url) {
  if (isProbe() || held || !url) return
  queue.push({ text: '', got: { url, note: '' }, now: true })
  emit()
  pump()
}

/* INCREMENTAL: feed the growing reply and speak each sentence the moment it is
 * complete. Returns the new cursor; the caller keeps it per turn and calls flush()
 * at the end for the tail. */
export function feed(fullText, cursor) {
  const pending = String(fullText || '').slice(cursor || 0)
  // speak only COMPLETE sentences; leave the tail (it may still be growing)
  let idx = -1
  const re = /[.!?…]+\s/g
  let m
  while ((m = re.exec(pending))) idx = m.index + m[0].length
  if (idx <= 0) return cursor || 0
  say(pending.slice(0, idx))
  return (cursor || 0) + idx
}
export function flush(fullText, cursor) {
  const tail = String(fullText || '').slice(cursor || 0).trim()
  if (tail) say(tail)
  return String(fullText || '').length
}
