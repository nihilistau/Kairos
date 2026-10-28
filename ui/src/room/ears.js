/* ears.js — HIS VOICE INTO THE ROOM (2026-10-29).
 *
 * The room could speak (speech.js) and could not hear. LFM3-Audio on this machine's CPU can
 * (harness/voice/lfm3.py `transcribe`); this is the mic that feeds it.
 *
 * TWO MODES, ONE KNOB. `ears.mode` (Settings → Voice, or the Models window's ears row):
 *   push   — the mic in Chat opens on a click and sends on the next click. The default.
 *   always — while Chat is open the mic stays open; a line ends after `ears.silence_ms` of
 *            quiet and is sent on its own. Off by default (docs/OFF-BY-DEFAULT.md).
 *
 * WHAT HE SAYS STAYS IN MEMORY. Samples live in arrays here, are encoded to a 16 kHz mono
 * WAV in memory, POSTed raw to /v1/listen (which writes nothing), and dropped. No storage
 * API, no object URL, no file. The transcript goes to Chat, which sends it through the SAME
 * send() a typed line uses — so off the record holds a spoken turn exactly like a typed one.
 *
 * SHE IS NOT HIM. Opening the mic CUTS her reply (barge-in, reply.interrupt(), 2026-10-29: "yes
 * stop her reply when you speak") — her voice stops, the reply is aborted like the stop button,
 * and nothing more of it is spoken. Always-mode cuts her at his speech ONSET (a line's worth of
 * loud frames, not a cough). Always-listening still ignores every sample while she is speaking
 * and for 300 ms after, or the room would hear her through the speakers and answer itself —
 * so in always-mode he can cut a reply between her sentences, not over one she is voicing.
 *
 * THIS MACHINE ONLY. Over the LAN, his voice would leave the machine for the gateway's;
 * the mic works only when the room was opened as localhost / 127.0.0.1 / [::1].
 */
import * as speech from './speech.js'
import * as reply from './reply.js'

export const NOT_HERE = "voice input needs this machine's browser"
const RATE = 16000              // what the ears want (lfm3 resamples anything, but 16 kHz is 3x smaller)
const MAX_S = 60                // /v1/listen caps a body at 2 MB, about 65 s at 16 kHz
const LOUD = 0.015              // RMS above which a frame counts as speech (always-mode)
const MIN_SPEECH_MS = 250       // a line shorter than this is a cough, a click, a door
const PRE_MS = 300              // kept before the first loud frame so his first syllable survives

let mode = 'push'
let silenceMs = 800
let listening = false           // the mic is open
let recording = false           // push-to-talk: a line is being collected
let hearing = false             // a line is with /v1/listen
let error = ''
let stream = null, ctx = null, src = null, node = null, rate = 48000
let chunks = []                 // push-to-talk: the whole line, Float32 at `rate`
let seg = null, segLoudMs = 0, lastLoud = 0, pre = []      // always-mode: the line so far
let segCut = false              // always-mode: this line has already cut her reply
let shipping = Promise.resolve()
/* ONE OPEN AT A TIME (review fix, 2026-10-29). getUserMedia waits on his permission prompt, and
 * `listening` only flips after it — so a second click, Chat's sync() racing the Models
 * window's, or a release() while the prompt was up each opened a SECOND stream and
 * AudioContext. Two processors fed `take` doubled audio, and the first stream's refs were
 * overwritten, so closeMic() could never stop its tracks: the browser's mic light stayed on
 * after Chat closed. Now concurrent callers share `opening`, and closeMic() bumps `openGen`
 * so an open that resolves after a close stops its tracks at once and never marks listening. */
let opening = null
let openGen = 0
let utter = null
const listeners = new Set()

export function onChange(fn) { listeners.add(fn); return () => listeners.delete(fn) }
const emit = () => listeners.forEach(fn => { try { fn(state()) } catch (_) {} })
export function state() { return { listening, recording, hearing, mode, error } }
/* Always-mode hands each line here; Chat registers the function that sends it. */
export function onUtterance(fn) { utter = fn; return () => { if (utter === fn) utter = null } }

export function allowed(loc) {
  const l = loc || (typeof location !== 'undefined' ? location : null)
  return !!l && ['localhost', '127.0.0.1', '[::1]'].includes(l.hostname)
}

/* HER VOICE IS NOT HIS. `playing` is speech.js's own flag: true from the first fetch of a
 * reply to the end of its last sentence. Push-to-talk is exempt — opening the mic already
 * hushed her, and the 300 ms tail would eat the first syllable of what he says. */
let quietSince = 0
let wasPlaying = false
speech.onChange(s => {
  if (wasPlaying && !s.playing) quietSince = Date.now()
  if (s.playing) { seg = null; pre = [] }   // she started over him: what was collected is hers too
  wasPlaying = s.playing
})
export function gated() {
  return mode === 'always' && (speech.state().playing || Date.now() - quietSince < 300)
}

/* Float32 pieces at `inRate` -> a 16 kHz mono 16-bit WAV, in memory. Averaging decimation:
 * cheap, and the ears are robust to it. */
export function toWav(pieces, inRate) {
  const n = pieces.reduce((a, c) => a + c.length, 0)
  const flat = new Float32Array(n)
  let o = 0
  for (const c of pieces) { flat.set(c, o); o += c.length }
  const ratio = inRate / RATE
  const outN = Math.floor(n / ratio)
  const v = new DataView(new ArrayBuffer(44 + outN * 2))
  const str = (at, s) => { for (let i = 0; i < s.length; i++) v.setUint8(at + i, s.charCodeAt(i)) }
  str(0, 'RIFF'); v.setUint32(4, 36 + outN * 2, true); str(8, 'WAVE')
  str(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true)
  v.setUint32(24, RATE, true); v.setUint32(28, RATE * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true)
  str(36, 'data'); v.setUint32(40, outN * 2, true)
  for (let i = 0; i < outN; i++) {
    const a = Math.floor(i * ratio), b = Math.min(n, Math.floor((i + 1) * ratio))
    let s = 0
    for (let j = a; j < b; j++) s += flat[j]
    s = b > a ? s / (b - a) : (flat[a] || 0)
    s = Math.max(-1, Math.min(1, s))
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  return new Uint8Array(v.buffer)
}

async function transcribe(wav) {
  const r = await fetch('/v1/listen', { method: 'POST', headers: { 'Content-Type': 'audio/wav' }, body: wav })
  const d = await r.json().catch(() => ({}))
  if (!r.ok || !d.ok) throw new Error(d.error || ('listen failed: ' + r.status))
  return String(d.text || '').trim()
}

function micWhy(e) {
  const n = e && e.name
  if (n === 'NotAllowedError' || n === 'SecurityError') return 'the microphone is blocked for this page — allow it in the address bar'
  if (n === 'NotFoundError') return 'no microphone found'
  return 'mic: ' + ((e && e.message) || e)
}

const total = a => a.reduce((s, c) => s + c.length, 0)

function take(x) {
  const piece = new Float32Array(x)          // the buffer is reused by the browser; copy it
  const ms = 1000 * piece.length / rate
  if (recording) {
    if (total(chunks) < MAX_S * rate) chunks.push(piece)
    return
  }
  if (mode !== 'always') return
  let sq = 0
  for (let i = 0; i < piece.length; i++) sq += piece[i] * piece[i]
  const now = Date.now()
  const loud = Math.sqrt(sq / (piece.length || 1)) > LOUD
  if (loud) lastLoud = now
  if (!seg) {
    if (!loud) {
      pre.push(piece)
      while (pre.length > 1 && 1000 * total(pre.slice(1)) / rate >= PRE_MS) pre.shift()
      return
    }
    seg = pre; pre = []; segLoudMs = 0; segCut = false
  }
  seg.push(piece)
  if (loud) segLoudMs += ms
  // HIS SPEECH ONSET: a line's worth of him (not a cough) cuts her current reply, once
  if (!segCut && segLoudMs >= MIN_SPEECH_MS) { segCut = true; reply.interrupt() }
  if (now - lastLoud >= silenceMs || total(seg) >= MAX_S * rate) {
    const line = seg, enough = segLoudMs >= MIN_SPEECH_MS
    seg = null
    if (enough) ship(line)
  }
}

/* Always-mode: lines go to /v1/listen one at a time, in the order he said them. */
function ship(line) {
  const wav = toWav(line, rate)
  shipping = shipping.then(async () => {
    hearing = true; emit()
    try {
      const said = await transcribe(wav)
      if (said && utter) utter(said)
      error = ''
    } catch (e) { error = 'ears: ' + e.message }
    hearing = false; emit()
  })
}

/* Resolves true when the mic is open, false when a close cancelled it while it was opening. */
function openMic() {
  if (listening) return Promise.resolve(true)
  if (opening) return opening
  const gen = openGen
  const p = (async () => {
    const s = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } })
    if (gen !== openGen) { s.getTracks().forEach(t => t.stop()); return false }   // closed during the prompt
    stream = s
    ctx = new (window.AudioContext || window.webkitAudioContext)()
    rate = ctx.sampleRate
    src = ctx.createMediaStreamSource(stream)
    node = ctx.createScriptProcessor(4096, 1, 1)
    node.onaudioprocess = e => {
      if (gated()) return
      take(e.inputBuffer.getChannelData(0))
    }
    src.connect(node)
    node.connect(ctx.destination)              // a processor only runs when connected; it writes silence
    listening = true
    if (ctx.state === 'suspended') {
      // reopened without a click (always-mode after a reload): the browser holds audio until one
      error = 'the mic opens on your first click in the room'
      const wake = () => {
        document.removeEventListener('pointerdown', wake, true)
        if (ctx) ctx.resume().then(() => { error = ''; emit() })
      }
      document.addEventListener('pointerdown', wake, true)
    }
    return true
  })()
  opening = p
  const done = () => { if (opening === p) opening = null }
  p.then(done, done)
  return p
}

function closeMic() {
  openGen += 1                               // an open still at the prompt is cancelled
  opening = null
  if (node) { node.onaudioprocess = null; node.disconnect() }
  if (src) src.disconnect()
  if (stream) stream.getTracks().forEach(t => t.stop())
  if (ctx) ctx.close()
  stream = ctx = src = node = null
  listening = false
  seg = null; pre = []
}

/* PUSH-TO-TALK: open the mic and start a line. Hushes her first. */
export async function start() {
  if (!allowed()) { error = NOT_HERE; emit(); return false }
  reply.interrupt()                           // barge-in: he is talking now — her reply is cut
  speech.hold(true)                           // ...and nothing else of hers speaks until he sends
  error = ''
  try {
    if (!(await openMic())) { speech.hold(false); emit(); return false }   // released while the prompt was up
  } catch (e) { error = micWhy(e); closeMic(); speech.hold(false); emit(); return false }
  chunks = []; recording = true; emit()
  return true
}

/* ...and end it: the line goes to /v1/listen; resolves to the text ('' when nothing was
 * heard or the ears failed — `error` then says why). */
export async function stopAndSend() {
  if (!recording) return ''
  recording = false
  speech.hold(false)                          // his line is done; her next reply speaks
  const line = chunks
  chunks = []
  if (mode !== 'always' || !utter) closeMic()   // always-mode keeps listening only while Chat is open
  hearing = true; emit()
  try {
    if (!line.length) throw new Error('nothing was heard')
    const said = await transcribe(toWav(line, rate))
    if (!said) throw new Error('nothing was heard')
    error = ''
    return said
  } catch (e) {
    error = 'ears: ' + e.message
    return ''
  } finally { hearing = false; emit() }
}

/* ALWAYS-LISTENING on or off for this tab. On opens the mic (localhost only); off closes it. */
export async function setAlways(on) {
  mode = on ? 'always' : 'push'
  if (!on) { if (!recording) closeMic(); emit(); return }
  if (!allowed()) { error = NOT_HERE; emit(); return }
  error = ''
  try { await openMic() } catch (e) { error = micWhy(e); closeMic() }
  emit()
}

/* Read `ears.mode` / `ears.silence_ms` from the registry and follow them. */
export async function sync() {
  try {
    const r = await fetch('/v1/tuning')
    const d = await r.json()
    const k = Object.fromEntries((d.knobs || []).map(x => [x.key, x.value]))
    if (Number.isFinite(k['ears.silence_ms'])) silenceMs = Math.max(300, Math.min(3000, k['ears.silence_ms']))
    const want = k['ears.mode'] === 'always'
    if (!want) { if (mode === 'always') await setAlways(false) }
    else if (!utter) { mode = 'always'; emit() }            // opens when Chat does: nowhere to send a line yet
    else if (mode !== 'always' || !listening) await setAlways(true)
  } catch (e) { error = 'ears: could not read ears.mode (' + e.message + ')'; emit() }
}

/* Chat closed: nothing listens with no window to show what it heard. */
export function release() {
  speech.hold(false)
  recording = false; chunks = []
  closeMic()
  emit()
}
