/* Shared panel furniture. Every app is a fetch, a loading state, an ERROR STATE,
 * and a body — and the error state is not optional. A panel that renders empty on
 * a failed fetch is indistinguishable from a panel whose subject is genuinely
 * empty, which is how "her memory is gone" and "the endpoint 404'd" become the
 * same picture. */
import { useEffect, useRef, useState } from 'react'

export function usePoll(fn, ms = 0) {
  const [state, set] = useState({ loading: true, data: null, error: null })
  const runRef = useRef(null)
  useEffect(() => {
    let alive = true
    const run = () => fn()
      .then(d => alive && set(s => ({ loading: false, data: d, error: null })))
      .catch(e => alive && set(s => ({ loading: false, data: s.data, error: String(e.message || e) })))
    runRef.current = run
    run()
    if (!ms) return () => { alive = false }
    const t = setInterval(run, ms)
    return () => { alive = false; clearInterval(t) }
  }, [fn, ms])   // re-subscribe when the poller changes (2026-08-22) — `[]` froze the first fn
  // A panel that WRITES needs to re-read without waiting for the next tick —
  // otherwise saving a file appears to do nothing for fifteen seconds.
  // Note the error branch keeps the last good `data`: a transient failed poll
  // should not blank a panel that was showing something a second ago.
  return { ...state, refresh: () => runRef.current && runRef.current() }
}

export function Body({ state, children }) {
  if (state.loading) return <div className="muted pad">…</div>
  if (state.error) return <div className="err pad">could not load — {state.error}</div>
  return children(state.data)
}

export const Row = ({ k, v, tone }) => (
  <div className="row"><span className="k">{k}</span><span className={'v ' + (tone || '')}>{v}</span></div>
)
