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
const MAX_CHARS = 240          // mirrors SP_TTS_MAX_CHARS; the server refuses above it
const ENDS = /([.!?…]+)(\s+|$)/

let queue = []                 // [{text}]
let playing = false
let current = null             // the Audio playing now
let enabled = true             // mirrors voice.enabled, refreshed by status()
let lastStatusAt = 0
const listeners = new Set()

export function onChange(fn) { listeners.add(fn); return () => listeners.delete(fn) }
const emit = () => listeners.forEach(fn => { try { fn(state()) } catch (_) {} })
export function state() { return { playing, queued: queue.length, enabled } }

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
  } catch (_) { /* leave it as it was */ }
  emit()
  return enabled
}

async function fetchWav(text) {
  const r = await fetch('/v1/speak', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!r.ok) throw new Error('speak ' + r.status)
  return URL.createObjectURL(await r.blob())
}

async function pump() {
  if (playing) return
  playing = true; emit()
  let ahead = null           // the prefetch promise for the next piece
  try {
    while (queue.length) {
      if (!(await refreshStatus())) { queue = []; break }
      const item = queue.shift()
      const url = await (ahead || fetchWav(item.text)).catch(() => null)
      ahead = queue.length ? fetchWav(queue[0].text).catch(() => null) : null
      if (!url) continue
      await new Promise(res => {
        const a = new Audio(url)
        current = a
        a.onended = a.onerror = () => { URL.revokeObjectURL(url); current = null; res() }
        a.play().catch(() => { current = null; res() })
      })
    }
  } finally { playing = false; current = null; emit() }
}

/* Queue text to be spoken, in order behind whatever is queued. */
export function say(text) {
  const parts = sentences(text)
  if (!parts.length) return
  queue.push(...parts.map(t => ({ text: t })))
  emit()
  pump()
}

export function stop() {
  queue = []
  if (current) { try { current.pause() } catch (_) {} current = null }
  emit()
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
