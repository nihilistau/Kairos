/* parts — the kit's shared furniture (2026-09-24). One shape per job, so the 27
 * windows stop growing 27 spellings of "a chip" and "an empty list". Every class here is
 * `ui-`, a family only this directory may coin (G-ROOM-CSS §4b). */
import { Icon } from './icons.jsx'

/* CHIP. tone: neutral | accent | ok | warn | err | mood | an */
export function Chip({ tone = 'neutral', icon, dot, title, onClick, children }) {
  const inner = (
    <>
      {dot ? <span className="ui-chip-dot" /> : null}
      {icon ? <Icon name={icon} size={12} /> : null}
      <span className="ui-chip-t">{children}</span>
    </>
  )
  return onClick
    ? <button type="button" className={'ui-chip ui-chip-btn ui-tone-' + tone}
              title={title} onClick={onClick}>{inner}</button>
    : <span className={'ui-chip ui-tone-' + tone} title={title}>{inner}</span>
}

/* BUTTON. variant: secondary (default) | primary | ghost | danger. At most ONE primary
 * per window — the restraint rule; a window of primaries has no primary. */
export function Button({ variant = 'secondary', size = 'md', icon, children, ...rest }) {
  return (
    <button type="button" {...rest}
            className={'ui-btn ui-btn-' + variant + ' ui-btn-' + size
                       + (children ? '' : ' ui-btn-icon') + (rest.className ? ' ' + rest.className : '')}>
      {icon ? <Icon name={icon} size={size === 'sm' ? 14 : 16} /> : null}
      {children}
    </button>
  )
}

export const Input = (p) => <input {...p} className={'ui-field' + (p.className ? ' ' + p.className : '')} />
export const TextArea = (p) => <textarea {...p} className={'ui-field ui-field-area' + (p.className ? ' ' + p.className : '')} />
export const Select = (p) => <select {...p} className={'ui-field ui-field-select' + (p.className ? ' ' + p.className : '')} />

/* TABS — role=tablist, arrow keys move, the selected one carries the mood underline. */
export function Tabs({ tabs, value, onChange }) {
  const i = Math.max(0, tabs.findIndex(t => t.id === value))
  const key = (e) => {
    const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
    if (d) { e.preventDefault(); onChange(tabs[(i + d + tabs.length) % tabs.length].id) }
  }
  return (
    <div className="ui-tabs" role="tablist" onKeyDown={key}>
      {tabs.map(t => (
        <button key={t.id} type="button" role="tab" aria-selected={t.id === value}
                tabIndex={t.id === value ? 0 : -1}
                className={'ui-tab' + (t.id === value ? ' ui-tab-on' : '')}
                onClick={() => onChange(t.id)}>{t.label}</button>
      ))}
    </div>
  )
}

/* ROW — a dense list row: lead (icon/dot), title, meta (mono, dim), trail (actions). */
export function Row({ lead, title, meta, trail, onClick }) {
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag type={onClick ? 'button' : undefined} onClick={onClick}
         className={'ui-row' + (onClick ? ' ui-row-btn' : '')}>
      {lead ? <span className="ui-row-lead">{lead}</span> : null}
      <span className="ui-row-title">{title}</span>
      {meta ? <span className="ui-row-meta">{meta}</span> : null}
      {trail ? <span className="ui-row-trail">{trail}</span> : null}
    </Tag>
  )
}

/* STATE — loading | empty | error, in one voice. An empty state is an invitation, an
 * error says what happened and what to do; neither apologises. */
export function State({ kind = 'empty', title, children, action }) {
  return (
    <div className={'ui-state ui-state-' + kind} role={kind === 'error' ? 'alert' : undefined}>
      {kind === 'loading' ? <span className="ui-spin" aria-hidden="true" /> : null}
      {title ? <div className="ui-state-t">{title}</div> : null}
      {children ? <div className="ui-state-b">{children}</div> : null}
      {action || null}
    </div>
  )
}

/* ORB — her mood, alive: breathes slowly, quickens while she is thinking. */
export function Orb({ thinking }) {
  return <span className={'ui-orb' + (thinking ? ' ui-orb-think' : '')} aria-hidden="true" />
}
