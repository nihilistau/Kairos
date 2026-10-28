import { usePoll } from '../apps/panel.jsx'
import * as api from '../api.js'
import * as wm from '../windowManager.js'
import { byId } from '../appRegistry.jsx'

/* THE MODEL STRIP (2026-10-29, the lights from mockup B) — one light per model job, in the
 * taskbar, so "is everything loaded" is a glance and not a window. Green loaded, cyan
 * pulsing loading, grey off, amber missing or error — or loaded but its last request failed
 * (`degraded`: Grok answering 402). Each light's tooltip is
 * `title: model — state`; the whole strip is ONE button (one tab stop, not six) that opens
 * the Models window, where the why and the pickers live.
 *
 * Same route as the window (/v1/models/status), polled slower: the strip is a glance, and
 * every poll touches six doors. A failed poll leaves the strip off rather than lying. */
/* READY MEANS LOADED AND WELL (final review, 2026-10-29): a degraded row (Grok answering 402)
 * is amber in the strip and was still counted as ready. One count for the strip and the window. */
export const readyCount = jobs => (jobs || []).filter(j => j.state === 'loaded' && !j.degraded).length

export default function ModelStrip() {
  const s = usePoll(api.modelsStatus, 8000)
  const jobs = (s.data && s.data.jobs) || []
  if (!jobs.length) return null
  const ready = readyCount(jobs)
  const openIt = () => { const a = byId('models'); if (a) wm.open('models', a) }
  return (
    <button type="button" className="mst" onClick={openIt}
            aria-label={'models: ' + ready + ' of ' + jobs.length + ' ready — open the Models window'}>
      {jobs.map(j => (
        <span key={j.id} className={'mst-light mst-' + j.state + (j.degraded ? ' mst-degraded' : '')}
              title={j.title + ': ' + (j.model || '—') + ' — ' + j.state + (j.degraded ? ' (' + j.why + ')' : '')} />
      ))}
    </button>
  )
}
