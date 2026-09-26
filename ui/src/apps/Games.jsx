import { useState } from 'react'
import { usePoll, Body } from './panel.jsx'
import { Button, Chip, Input, State, Tabs } from '../kit/parts.jsx'
import * as api from '../api.js'

/* GAMES — a board you both touch.
 *
 * THE ENGINE RULES, NOT THIS PANEL. Clicking a square sends a move to /v1/games and
 * the server admits or refuses it; the refusal comes back with the legal list. So this
 * file has no idea what a bishop does, which is the point — the rules live in
 * harness/games/chess.py where they can be proved by perft, and a UI that duplicated
 * them would be a second copy of the truth that drifts from the first.
 *
 * SHE PLAYS FROM THE SAME STATE. `see_board` renders this position and runs it through
 * her vision tower, so what she looks at and what he clicks on are one board, not two
 * representations that agree until they don't.
 *
 * The wordle grid never shows the answer. It cannot: match.public() withholds it until
 * the game ends, so it is not in the payload to leak.
 */

const GLYPH = { k: '♚', q: '♛', r: '♜', b: '♝', n: '♞', p: '♟' }
// Each square's accessible name — chrome words, so a keyboard can play. Not hers.
const PIECE = { k: 'king', q: 'queen', r: 'rook', b: 'bishop', n: 'knight', p: 'pawn' }
// A wordle mark, for the eye and in words: colour alone is not a mark (WCAG 1.4.1).
const WMARK = { g: ['hit', 'in place'], y: ['near', 'elsewhere'], '.': ['miss', 'not in the word'] }

export function Board({ st, onMove, startFrom = null }) {
  const [from, setFrom] = useState(startFrom)
  const rows = st.fen.split(' ')[0].split('/')
  const grid = []
  for (const row of rows) {
    for (const c of row) {
      if (/\d/.test(c)) for (let i = 0; i < +c; i++) grid.push('.')
      else grid.push(c)
    }
  }
  const name = (i) => 'abcdefgh'[i % 8] + (8 - Math.floor(i / 8))
  // Highlight from the LEGAL LIST the server sent, never from our own idea of the rules.
  const targets = from ? st.legal.filter(m => m.slice(0, 2) === from).map(m => m.slice(2, 4)) : []
  const last = st.history?.length ? st.history[st.history.length - 1] : ''

  const click = (i) => {
    const sq = name(i)
    if (from && targets.includes(sq)) {
      // Promotion is always to a queen from the board; the tools take e7e8r if he
      // wants something else. Offering a chooser for the 1% costs the 99% a click.
      const promo = st.legal.includes(from + sq + 'q') ? 'q' : ''
      onMove(from + sq + promo); setFrom(null); return
    }
    setFrom(st.legal.some(m => m.slice(0, 2) === sq) ? sq : null)
  }

  return (
    <div className="gm-board" role="group" aria-label="the board">
      {grid.map((c, i) => {
        const sq = name(i)
        const dark = (Math.floor(i / 8) + i % 8) % 2 === 1
        const to = targets.includes(sq)
        const cls = ['gm-sq', dark ? 'gm-sq-d' : 'gm-sq-l',
                     from === sq ? 'gm-sq-from' : '',
                     to ? 'gm-sq-to' : '',
                     (last.slice(0, 2) === sq || last.slice(2, 4) === sq) ? 'gm-sq-last' : ''].filter(Boolean).join(' ')
        const who = c !== '.' ? (c === c.toUpperCase() ? ' white ' : ' black ') + PIECE[c.toLowerCase()] : ''
        return (
          <button key={i} type="button" className={cls} title={sq}
                  aria-label={sq + who + (to ? ', a legal move' : '')} aria-pressed={from === sq ? true : undefined}
                  onClick={() => click(i)}>
            {c !== '.' ? (
              <span className={'gm-p ' + (c === c.toUpperCase() ? 'gm-p-lt' : 'gm-p-dk')} aria-hidden="true">
                {GLYPH[c.toLowerCase()]}
              </span>
            ) : null}
          </button>
        )
      })}
    </div>
  )
}

export function Wordle({ st, onMove, startGuess = '' }) {
  const [g, setG] = useState(startGuess)
  return (
    <>
      <div className="gm-wgrid">
        {st.history.map((w, r) => (
          <div key={r} className="gm-wrow">
            {w.split('').map((ch, i) => {
              const m = WMARK[st.marks[r][i]] || WMARK['.']
              return <span key={i} className={'gm-w gm-w-' + m[0]} title={m[1]}>{ch}<span className="gm-sr">{', ' + m[1]}</span></span>
            })}
          </div>
        ))}
      </div>
      {!st.over ? (
        <div className="gm-ctl">
          <Input className="gm-in" value={g} maxLength={5} placeholder="five letters" aria-label="five letters"
                 onChange={e => setG(e.target.value.replace(/[^a-z]/gi, '').toLowerCase())}
                 onKeyDown={e => { if (e.key === 'Enter' && g.length === 5) { onMove(g); setG('') } }} />
          <Button variant="primary" disabled={g.length !== 5} onClick={() => { onMove(g); setG('') }}>guess</Button>
          <span className="gm-n">{st.tries_left + ' left'}</span>
        </div>
      ) : <p className="gm-n">{st.result + ' — ' + st.reason}</p>}
    </>
  )
}


/* THE TABLE. Poker is imperfect information, so this panel renders THE VIEW THE SERVER
 * SENT FOR SEAT 0 and nothing else. Her hole cards are not withheld by this file — they
 * were never in the payload. That distinction is the whole design: a UI that hides cards
 * it possesses is one refactor away from showing them. */
const SUIT = { s: '♠', h: '♥', d: '♦', c: '♣' }

function Card({ c }) {
  if (!c) return <span className="gm-pk-card gm-pk-back" />
  const red = c[1] === 'h' || c[1] === 'd'
  return (
    <span className={'gm-pk-card' + (red ? ' gm-pk-red' : '')}>
      {c[0] === 'T' ? '10' : c[0]}<i>{SUIT[c[1]]}</i>
    </span>
  )
}

export function Poker({ st, onAct, onDeal }) {
  const [amt, setAmt] = useState(0)
  const me = st.seats[st.seat]
  const them = st.seats[1 - st.seat]
  const o = st.options || {}
  const yours = st.to_act === st.seat && !st.over
  const call = o.to_call || 0
  // THE PRICE, shown rather than left to be worked out. Calling `call` into `pot`
  // needs this much equity to break even — the single most useful number at a table.
  const need = call ? Math.round(100 * call / (st.pot + call)) : 0

  return (
    <>
      <div className="gm-pk-head">
        <span>{'hand ' + st.hand_no}</span><span className="gm-pk-street">{st.street}</span>
        <span className="gm-n">{st.sb + '/' + st.bb}</span>
      </div>

      <div className="gm-pk-seat">
        <span className="gm-pk-name">{them.name + (st.button === 1 - st.seat ? ' ◉' : '')}</span>
        <span className="gm-pk-hole">
          <Card c={them.hole && them.hole[0]} /><Card c={them.hole && them.hole[1]} />
        </span>
        <span className="gm-pk-stack">{them.stack}</span>
        {them.street_bet ? <span className="gm-pk-bet">{them.street_bet}</span> : null}
        {them.folded ? <Chip>folded</Chip> : null}
      </div>

      <div className="gm-pk-pot">pot <b>{st.pot}</b></div>
      <div className="gm-pk-board">
        {[0, 1, 2, 3, 4].map(i => <Card key={i} c={st.board[i]} />)}
      </div>

      <div className="gm-pk-seat gm-pk-mine">
        <span className="gm-pk-name">{me.name + (st.button === st.seat ? ' ◉' : '')}</span>
        <span className="gm-pk-hole">
          <Card c={me.hole && me.hole[0]} /><Card c={me.hole && me.hole[1]} />
        </span>
        <span className="gm-pk-stack">{me.stack}</span>
        {me.street_bet ? <span className="gm-pk-bet">{me.street_bet}</span> : null}
      </div>

      {st.over ? (
        <div className="gm-pk-ctl">
          {st.winners.map((w, i) => (
            <Chip key={i} tone="ok" wrap>
              {st.seats[w.seat].name + ' wins ' + w.amount + (w.hand ? ' with ' + w.hand : '')}
            </Chip>
          ))}
          <Button variant="primary" onClick={onDeal}>deal next</Button>
        </div>
      ) : yours ? (
        <div className="gm-pk-ctl">
          {o.actions.includes('fold') ? <Button size="sm" onClick={() => onAct('fold')}>fold</Button> : null}
          {o.actions.includes('check') ? <Button size="sm" onClick={() => onAct('check')}>check</Button> : null}
          {o.actions.includes('call')
            ? <Button size="sm" onClick={() => onAct('call')}>{'call ' + call}<span className="gm-pk-need">{' (' + need + '%)'}</span></Button>
            : null}
          {(o.actions.includes('raise') || o.actions.includes('bet')) ? (
            <>
              <Input className="gm-pk-in" type="number" aria-label="raise to" value={amt || o.min_raise_to || 0}
                     min={o.min_raise_to} max={o.max_raise_to}
                     onChange={e => setAmt(Number(e.target.value))} />
              <Button size="sm"
                      onClick={() => onAct(o.actions.includes('bet') ? 'bet' : 'raise',
                                           amt || o.min_raise_to)}>
                {(o.actions.includes('bet') ? 'bet' : 'raise') + ' to'}
              </Button>
            </>
          ) : null}
          {o.actions.includes('allin') ? <Button variant="danger" size="sm" onClick={() => onAct('allin')}>all in</Button> : null}
        </div>
      ) : <div className="gm-pk-ctl gm-n">{'waiting for ' + them.name + '…'}</div>}

      <div className="gm-pk-log">{(st.log || []).slice(-6).map((l, i) => <div key={i}>{l}</div>)}</div>
    </>
  )
}

/* The window's body, split out so G-ROOM-KIT leg 13 can render it with fixtures. The poll
 * and act() stay in the default export. Your games are the kit's Tabs — they were a
 * single-select row of bare buttons inside a `.chips` row; the actions beside them are
 * kit Buttons, and remove (which drops a game) is danger. */
export function GamesView({ d, pick, setPick, err, setErr, act, startFrom, startGuess }) {
  if (d.ok === false) return <State kind="error">{'games unavailable — ' + d.error}</State>
  const ids = Object.keys(d.states || {})
  const cur = (pick && d.states[pick]) || d.states[ids[0]] || null
  return (
    <>
      <div className="gm-bar">
        {ids.length ? (
          <div className="gm-tabs">
            <Tabs value={cur ? cur.id : ''} label="your games" onChange={id => { setPick(id); setErr('') }}
                  tabs={ids.map(id => ({ id, label: id }))} />
          </div>
        ) : null}
        <div className="gm-new">
          {(d.kinds || []).map(k => (
            <Button key={k} size="sm" onClick={() => act({ op: 'new', kind: k, name: k })}>{'+ ' + k}</Button>
          ))}
          {cur ? (
            <Button variant="danger" size="sm" onClick={() => { act({ op: 'drop', name: cur.id }); setPick(null) }}>remove</Button>
          ) : null}
        </div>
      </div>

      {err ? <div className="gm-err"><Chip tone="err" wrap>{err}</Chip></div> : null}
      {!cur ? <State kind="empty">No game yet — start one above, or ask her to.</State> : null}

      {cur && cur.kind === 'chess' ? (
        <>
          <div className="gm-head">
            {cur.over
              ? <b>{cur.result + ' — ' + cur.reason}</b>
              : <><b>{cur.side}</b>{' to move'}{cur.in_check ? <Chip tone="err">in check</Chip> : null}</>}
            <span className="gm-n">{cur.history.length + ' moves'}</span>
          </div>
          <Board st={cur} startFrom={startFrom} onMove={m => act({ op: 'move', name: cur.id, move: m })} />
          <div className="gm-moves">{cur.history.join(' ')}</div>
          {/* RESIGN, DRAW, TAKEBACK. Found by playing rather than by reading:
              the rules were complete and "gg" still had nowhere to live, so a
              resigned game sat in the listing forever with no result. */}
          <div className="gm-ctl gm-agree">
            {cur.draw_offer ? (
              <>
                <Chip tone="warn" wrap>{cur.draw_offer + ' offers a draw'}</Chip>
                <Button variant="primary" size="sm" onClick={() => act({ op: 'draw', name: cur.id, accept: true })}>accept</Button>
                <Button size="sm" onClick={() => act({ op: 'draw', name: cur.id, accept: false })}>decline</Button>
              </>
            ) : !cur.over ? (
              <Button size="sm" onClick={() => act({ op: 'offer_draw', name: cur.id })}>offer draw</Button>
            ) : null}
            {!cur.over ? (
              <Button variant="danger" size="sm" onClick={() => act({ op: 'resign', name: cur.id })}>resign</Button>
            ) : null}
            {cur.history.length ? (
              <Button variant="ghost" size="sm" onClick={() => act({ op: 'rewind', name: cur.id, plies: 1 })}
                      title="takes back one half-move; un-ends a finished game">take back</Button>
            ) : null}
          </div>
        </>
      ) : null}

      {cur && cur.kind === 'holdem' ? (
        <Poker st={cur}
               onAct={(a, n) => act({ op: 'move', name: cur.id, move: n ? a + ' ' + n : a })}
               onDeal={() => act({ op: 'deal', name: cur.id })} />
      ) : null}

      {cur && cur.kind === 'wordle' ? (
        <Wordle st={cur} startGuess={startGuess} onMove={w => act({ op: 'move', name: cur.id, move: w })} />
      ) : null}
    </>
  )
}

export default function Games() {
  const s = usePoll(api.games, 4000)
  const [pick, setPick] = useState(null)
  const [err, setErr] = useState('')

  async function act(body) {
    const r = await api.gamesWrite(body)
    // The server's refusal is shown VERBATIM. Rewording "e5 is not legal here" into
    // "invalid move" would throw away the only part worth reading.
    setErr(r && r.ok === false ? (r.error || 'refused') : '')
    s.refresh()
  }

  return (
    <div className="pad gm">
      <Body state={s}>{d => <GamesView d={d} pick={pick} setPick={setPick} err={err} setErr={setErr} act={act} />}</Body>
    </div>
  )
}
