/* api.js — every call the room makes to the gateway, in one file.
 *
 * ONE PLACE ON PURPOSE. OpenRoom's /api/* contract lives scattered through
 * lib/diskStorage.ts, configPersistence.ts and vite.config.ts as dev middleware —
 * which is why its production Docker image 404s every route and silently falls
 * back to localStorage. That failure is invisible until someone loses data.
 *
 * Here the endpoints are the Kairos gateway's real ones, always, and a failure is
 * an error the panel renders rather than a silent degrade.
 */
const BASE = ''

async function get(path) {
  const r = await fetch(BASE + path)
  if (!r.ok) throw new Error(`${path} ${r.status}`)
  return r.json()
}

export const senses  = () => get('/v1/senses')
export const tools   = () => get('/v1/tools')
export const memory  = () => get('/v1/memory')
/* THE BOARD. `all` asks for the retired rows too — `remove` is a TOMBSTONE in
 * harness/skills/notes.py, so a note he took down still exists and he should be
 * able to look at it. Same shape as the memory panel's live/retired split. */
export const notes   = (all) => get('/v1/notes' + (all ? '?all=1' : ''))
export const persona = () => get('/v1/persona/state')
export const health  = () => get('/health')
export const speakStatus = () => get('/v1/speak/status')
/* THE ROOM'S HEARTBEAT. One call for the shell — time, her state, presence,
 * journal, backups. Five separate polls for a heartbeat is how a UI ends up with
 * five different ideas of what time it is. */
export const pulse   = () => get('/v1/room/pulse')
export const backups = () => get('/v1/backups')
/* WHAT SHE SAID WITHOUT BEING ASKED. Polled under THIS TAB's session — the same key
 * chat() sends — because that is where the scheduler queues replies to this
 * conversation. (The old no-session call polled "default", which the scheduler RETIRES
 * the moment a real session exists: after his first message, every unprompted word of
 * hers went to a queue with no reader. The comment justifying it and the session_id
 * change that broke it were ten lines apart and nothing failed loudly.) Boot-time
 * seeds still land under "default"; the gateway's drain() hands that no-owner queue
 * to the first real listener, so nothing is lost on either side. */
export const kairosOutbox = () => get('/v1/kairos/outbox?session=' + encodeURIComponent(roomSession()))
/* THE WARDROBE. One reader for the stage and the panel, so they can never disagree
 * about what she is wearing. */
export const wardrobe = () => get('/v1/wardrobe')
export const music     = () => get('/v1/music')
export const narrative = () => get('/v1/narrative')
/* HER OWN TIME — one merged feed of what she did while he was away. Read-only by
 * construction: it composes stores she already writes, and there is no POST. */
export const agency    = () => get('/v1/agency')
export const research  = () => get('/v1/research')
/* THE SEARCH WINDOW — the non-research half of the same looking ledger. */
export const search    = () => get('/v1/search')
export const files     = () => get('/v1/files')

async function post(path, body) {
  const r = await fetch(BASE + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return r.json()
}
/* The player's intent lives on the SERVER, so both of them change the same thing. */
export const musicControl = (b) => post('/v1/music/control', b)
export const filesWrite   = (b) => post('/v1/files/write', b)
export const wardrobeSet  = (b) => post('/v1/wardrobe', b)
// 2026-08-21: his wants + generate-now (the click that replaces the day boundary)
export const wardrobeWant     = (want) => post('/v1/wardrobe/want', { want, by: 'him' })
export const wardrobeGenerate = (id)   => post('/v1/wardrobe/generate', id ? { id } : {})
export const wardrobeDismiss  = (id)   => post('/v1/wardrobe/want/dismiss', { id, by: 'him' })
// 2026-08-21: the settings window — the whole tuning registry, live
export const tuning    = () => get('/v1/tuning')
export const tuningSet = (values) => post('/v1/tuning', { values })
/* HIS OWN LOOKUPS (2026-08-21) — the manual boxes in the search and research
 * panels. Synchronous: the response IS the answer, so these can take a while
 * (search ~10-25 s, research up to a couple of minutes). Rows land in the same
 * ledger as hers, marked by="him". */
export const searchRun   = (query, n) => post('/v1/search/run', { query, n })
/* THE CATALOG (2026-08-21): everything she can wear, do or show, his edits included.
 * ops: edit | hide | unhide | remove (tombstone) | restore | import (from the inbox). */
export const catalog   = () => get('/v1/catalog')
export const catalogOp = (b) => post('/v1/catalog', b)
export const researchRun = (query, depth) => post('/v1/research/run', { query, depth })

/* STOPPING HER. Three modes, and the mode IS the confirmation in the UI — see main.jsx.
 * `all` takes the gateway with it, so this request is the last one that will succeed;
 * the server replies before it tears itself down, so a resolved promise here means the
 * shutdown was accepted, not that it has finished. */
export const shutdown = (mode, goodnight) => post('/v1/shutdown', { mode, goodnight })
export const startHer = () => post('/v1/start', {})

/* THE BOARD, WRITTEN. Three routes that already existed on the server and had no
 * button anywhere — /v1/notes/{add,update,remove}. `remove` tombstones; `update`
 * with {done:true} is "completed" and is reversible, which is why they are two
 * different controls rather than one. The panel sets author = him, server-side,
 * from WHICH DOOR the write came through — never from the text. */
export const noteAdd    = (b) => post('/v1/notes/add', b)
export const noteUpdate = (b) => post('/v1/notes/update', b)
export const noteRemove  = (b) => post('/v1/notes/remove', b)
export const noteRestore = (b) => post('/v1/notes/restore', b)

/* THE LEDGER — the plan, the parked, and everything noticed. One POST with an
 * explicit `op`, matching the route: add | edit | drop | restore. `drop` is the
 * remove button and it TOMBSTONES — there is no delete beneath it, here or in
 * harness/control/ledger.py. */
export const ledger      = () => get('/v1/ledger')
export const ledgerWrite = (b) => post('/v1/ledger', b)
/* Gate receipts and their AGE. Reads var/sem/receipts/; runs nothing, so this is
 * what was last recorded, never a live verdict. */
export const gateHealth  = () => get('/v1/health/gates')
/* HER FACE. Returns which faces have art and what the ceiling allows — never a tier,
 * because the client is not permitted to name one. */
export const avatar = () => get('/v1/avatar')
// WHAT IS SET UP AND WHAT IS NOT (2026-08-23). Read-only; the server never
// returns the contents of a key file, only whether one is there.
export const setup  = () => get('/v1/setup')

/* THE STACK. `restart` reloads the model (~2-3 min); `restart_gateway` bounces only the
 * gateway (~20s) and leaves the daemon and its warm prefix alone. */
export const system      = () => get('/v1/system')
export const systemWrite = (b) => post('/v1/system', b)

/* THE STAGE — the roleplay director, which had no introspection at all until now.
 * `roleplayWrite({op:'exit'})` takes no scene id on purpose: a stop that needs the
 * right argument is not a stop. */
export const roleplay      = () => get('/v1/roleplay')
/* PRESENCE (2026-08-22): her modes' state + the shelf; the two shelf verbs. */
export const presence        = () => get('/v1/presence')
export const presencePutDown = () => post('/v1/presence/put_down', {})
export const presencePickUp  = (title) => post('/v1/presence/pick_up', { title })
export const presenceEnter   = (mode) => post('/v1/presence/enter', { mode })
export const presenceLeave   = () => post('/v1/presence/leave', {})
/* THE LIBRARIANS (2026-08-22): the aux doors, the index, the pickers. */
export const aux             = () => get('/v1/aux')
export const auxRebuild      = () => post('/v1/aux/rebuild', {})
export const roleplayWrite = (b) => post('/v1/roleplay', b)

/* THE BOARD. One call returns every match and its public state — the answer to a
 * wordle is withheld server-side until the game ends, so it is not in this payload
 * to leak. Moves are RULED ON by harness/games/, never by the panel. */
export const games      = () => get('/v1/games')
export const gamesWrite = (b) => post('/v1/games', b)

/* The chat stream. Yields {delta}/{tool}/{persona}/{image} events as they arrive —
 * the gateway's SSE v2 typed events, so a panel can render a tool call as a card
 * instead of as text that happens to look like one. */
/* ── THE ROOM NEVER SENT A session_id, AND THAT IS WHERE THE MINUTES WENT ───────────
 * The gateway keeps a CANONICAL transcript per session — the exact message list the
 * daemon saw, including the per-turn recall note and every tool round — so that each
 * turn is a STRICT EXTENSION of the persist-KV cache and costs O(new tokens). Without a
 * session_id it falls through to `list(body["messages"])`: the client's own echo.
 *
 * app.py says of that echo, in its own words, that it "NEVER matches what the daemon
 * actually saw — so the turn AFTER any recall/tool turn diverged from the persist-KV
 * committed cache and paid a full preamble re-prefill". And app.py:1422 says plainly
 * "the room does not [send one]". Both true, in the same file, for weeks.
 *
 * So the whole strict-extension machinery has been live for anything that sends an id
 * and inactive for the client he actually uses. MEASURED: a driver sending a session_id
 * held a constant `drop 195` in steady state; his real turns were re-prefilling suffixes
 * of 5676 tokens at 426 s. That is not a different bug, it is the same machinery running
 * for one caller and not the other — AGENTS.md §0, in the one place nobody looked because
 * it is four lines of JavaScript rather than anything in the engine.
 *
 * STABLE ACROSS RELOADS, deliberately: sessionStorage, so a refresh continues the same
 * conversation instead of minting a new canon and re-prefilling from the preamble. Per
 * TAB rather than per browser, because two tabs are two conversations and sharing one
 * canon between them would interleave two histories into one cache — the exact trampling
 * this is meant to stop. */
function roomSession() {
  try {
    let s = sessionStorage.getItem('sp-room-session')
    if (!s) {
      s = 'room-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8)
      sessionStorage.setItem('sp-room-session', s)
    }
    return s
  } catch { return 'room' }   // private mode / storage disabled: one shared id beats none
}

export async function* chat(messages, opts = {}) {
  // THE CEILING IS HIS KNOB, NOT THIS FILE'S (2026-08-21). This sent max_tokens: 512
  // on every turn, which the gateway honours over the decode.max_tokens knob — so the
  // Settings dial never reached the room and "she is constantly hitting the ceiling".
  // Unset means the knob rules; a caller that names a value still wins.
  const body = { messages, session_id: opts.session_id || roomSession() }
  if (opts.max_tokens) body.max_tokens = opts.max_tokens
  if (opts.image_b64) body.image_b64 = opts.image_b64
  const r = await fetch(BASE + '/v1/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: opts.signal,
  })
  const reader = r.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop()
    for (const line of lines) {
      const t = line.trim()
      if (!t.startsWith('data:')) continue
      const p = t.slice(5).trim()
      if (p === '[DONE]') return
      try { yield JSON.parse(p) } catch { /* partial frame */ }
    }
  }
}
