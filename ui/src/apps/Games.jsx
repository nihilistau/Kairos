import { useState } from 'react'
import { usePoll, Body } from './panel.jsx'
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

function Board({ st, onMove }) {
  const [from, setFrom] = useState(null)
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
    <div className="gm-board">
      {grid.map((c, i) => {
        const sq = name(i)
        const dark = (Math.floor(i / 8) + i % 8) % 2 === 1
        const cls = ['gm-sq', dark ? 'd' : 'l',
                     from === sq ? 'from' : '',
                     targets.includes(sq) ? 'to' : '',
                     (last.slice(0, 2) === sq || last.slice(2, 4) === sq) ? 'last' : ''].join(' ')
        return (
          <div key={i} className={cls} onClick={() => click(i)} title={sq}>
            {c !== '.' ? (
              <span className={'gm-p ' + (c === c.toUpperCase() ? 'gm-lt' : 'gm-dk')}>
                {GLYPH[c.toLowerCase()]}
              </span>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

function Wordle({ st, onMove }) {
  const [g, setG] = useState('')
  return (
    <>
      <div className="gm-wgrid">
        {st.history.map((w, r) => (
          <div key={r} className="gm-wrow">
            {w.split('').map((ch, i) => (
              <span key={i} className={'gm-w ' + st.marks[r][i]}>{ch}</span>
            ))}
          </div>
        ))}
      </div>
      {!st.over ? (
        <div className="gm-ctl">
          <input className="gm-in" value={g} maxLength={5} placeholder="five letters"
                 onChange={e => setG(e.target.value.replace(/[^a-z]/gi, '').toLowerCase())}
                 onKeyDown={e => { if (e.key === 'Enter' && g.length === 5) { onMove(g); setG('') } }} />
          <button className="on" disabled={g.length !== 5}
                  onClick={() => { onMove(g); setG('') }}>guess</button>
          <span className="muted">{st.tries_left} left</span>
        </div>
      ) : <p className="muted">{st.result} — {st.reason}</p>}
    </>
  )
}


/* THE TABLE. Poker is imperfect information, so this panel renders THE VIEW THE SERVER
 * SENT FOR SEAT 0 and nothing else. Her hole cards are not withheld by this file — they
 * were never in the payload. That distinction is the whole design: a UI that hides cards
 * it possesses is one refactor away from showing them. */
const SUIT = { s: '♠', h: '♥', d: '♦', c: '♣' }

function Card({ c }) {
  if (!c) return <span className="pk-card back" />
  const red = c[1] === 'h' || c[1] === 'd'
  return (
    <span className={'pk-card' + (red ? ' red' : '')}>
      {c[0] === 'T' ? '10' : c[0]}<i>{SUIT[c[1]]}</i>
    </span>
  )
}

function Poker({ st, onAct, onDeal }) {
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
      <div className="pk-head">
        <span>hand {st.hand_no}</span><span className="pk-street">{st.street}</span>
        <span className="muted">{st.sb}/{st.bb}</span>
      </div>

      <div className="pk-seat them">
        <span className="pk-name">{them.name}{st.button === 1 - st.seat ? ' ◉' : ''}</span>
        <span className="pk-hole">
          <Card c={them.hole && them.hole[0]} /><Card c={them.hole && them.hole[1]} />
        </span>
        <span className="pk-stack">{them.stack}</span>
        {them.street_bet ? <span className="pk-bet">{them.street_bet}</span> : null}
        {them.folded ? <span className="muted">folded</span> : null}
      </div>

      <div className="pk-pot">pot <b>{st.pot}</b></div>
      <div className="pk-board">
        {[0, 1, 2, 3, 4].map(i => <Card key={i} c={st.board[i]} />)}
      </div>

      <div className="pk-seat mine">
        <span className="pk-name">{me.name}{st.button === st.seat ? ' ◉' : ''}</span>
        <span className="pk-hole">
          <Card c={me.hole && me.hole[0]} /><Card c={me.hole && me.hole[1]} />
        </span>
        <span className="pk-stack">{me.stack}</span>
        {me.street_bet ? <span className="pk-bet">{me.street_bet}</span> : null}
      </div>

      {st.over ? (
        <div className="pk-ctl">
          {st.winners.map((w, i) => (
            <span key={i} className="good">
              {st.seats[w.seat].name} wins {w.amount}{w.hand ? ' with ' + w.hand : ''}
            </span>
          ))}
          <button className="on" onClick={onDeal}>deal next</button>
        </div>
      ) : yours ? (
        <div className="pk-ctl">
          {o.actions.includes('fold') ? <button onClick={() => onAct('fold')}>fold</button> : null}
          {o.actions.includes('check') ? <button onClick={() => onAct('check')}>check</button> : null}
          {o.actions.includes('call')
            ? <button onClick={() => onAct('call')}>call {call} <i className="muted">({need}%)</i></button>
            : null}
          {(o.actions.includes('raise') || o.actions.includes('bet')) ? (
            <>
              <input className="pk-in" type="number" value={amt || o.min_raise_to || 0}
                     min={o.min_raise_to} max={o.max_raise_to}
                     onChange={e => setAmt(Number(e.target.value))} />
              <button className="on"
                      onClick={() => onAct(o.actions.includes('bet') ? 'bet' : 'raise',
                                           amt || o.min_raise_to)}>
                {o.actions.includes('bet') ? 'bet' : 'raise'} to
              </button>
            </>
          ) : null}
          {o.actions.includes('allin') ? <button className="r-off" onClick={() => onAct('allin')}>all in</button> : null}
        </div>
      ) : <div className="pk-ctl muted">waiting for {them.name}…</div>}

      <div className="pk-log">{(st.log || []).slice(-6).map((l, i) => <div key={i}>{l}</div>)}</div>
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
      <Body state={s}>{d => {
        if (d.ok === false) return <div className="err">games unavailable — {d.error}</div>
        const ids = Object.keys(d.states || {})
        const cur = (pick && d.states[pick]) || d.states[ids[0]] || null
        return (
          <>
            <div className="chips">
              {ids.map(id => (
                <button key={id} className={cur && cur.id === id ? 'on' : ''}
                        onClick={() => { setPick(id); setErr('') }}>{id}</button>
              ))}
              {(d.kinds || []).map(k => (
                <button key={k} onClick={() => act({ op: 'new', kind: k, name: k })}>+ {k}</button>
              ))}
              {cur ? <button className="r-off" onClick={() => { act({ op: 'drop', name: cur.id }); setPick(null) }}>
                remove</button> : null}
            </div>

            {err ? <div className="err gm-err">{err}</div> : null}
            {!cur ? <p className="muted">No game yet — start one above, or ask her to.</p> : null}

            {cur && cur.kind === 'chess' ? (
              <>
                <div className="gm-head">
                  {cur.over
                    ? <b>{cur.result} — {cur.reason}</b>
                    : <><b>{cur.side}</b> to move{cur.in_check ? <span className="bad"> — in check</span> : null}</>}
                  <span className="muted">{cur.history.length} moves</span>
                </div>
                <Board st={cur} onMove={m => act({ op: 'move', name: cur.id, move: m })} />
                <div className="gm-moves">{cur.history.join(' ')}</div>
                {/* RESIGN, DRAW, TAKEBACK. Found by playing rather than by reading:
                    the rules were complete and "gg" still had nowhere to live, so a
                    resigned game sat in the listing forever with no result. */}
                <div className="gm-ctl gm-agree">
                  {cur.draw_offer ? (
                    <>
                      <span className="warn">{cur.draw_offer} offers a draw</span>
                      <button className="on" onClick={() => act({ op: 'draw', name: cur.id, accept: true })}>accept</button>
                      <button onClick={() => act({ op: 'draw', name: cur.id, accept: false })}>decline</button>
                    </>
                  ) : !cur.over ? (
                    <button onClick={() => act({ op: 'offer_draw', name: cur.id })}>offer draw</button>
                  ) : null}
                  {!cur.over ? (
                    <button className="r-off" onClick={() => act({ op: 'resign', name: cur.id })}>resign</button>
                  ) : null}
                  {cur.history.length ? (
                    <button onClick={() => act({ op: 'rewind', name: cur.id, plies: 1 })}
                            title="takes back one half-move; un-ends a finished game">take back</button>
                  ) : null}
                </div>
              </>
            ) : null}

            {cur && cur.kind === 'holdem' ? (
              <Poker st={cur}
                     onAct={(a, n) => act({ op: 'move', name: cur.id,
                                            move: n ? a + ' ' + n : a })}
                     onDeal={() => act({ op: 'deal', name: cur.id })} />
            ) : null}

            {cur && cur.kind === 'wordle' ? (
              <Wordle st={cur} onMove={w => act({ op: 'move', name: cur.id, move: w })} />
            ) : null}
          </>
        )
      }}</Body>
    </div>
  )
}
