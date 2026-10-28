import { useState, useSyncExternalStore } from 'react'
import { APPS, DOCK_HIDDEN_DEFAULT } from '../appRegistry.jsx'
import * as vis from '../deskVisibility.js'
import * as layout from '../desktopLayout.js'
import { Icon } from '../kit/icons.jsx'
import { Button } from '../kit/parts.jsx'

/* APPS — the launcher, and the desktop's own switchboard (2026-08-21, his ask:
 * "an icon on the side bar that brings up a panel containing icons to
 * add/remove from the sidebar live"; the left dock left in stage 3, and the same list
 * now decides the desktop icons).
 *
 * Every app is listed here ALWAYS — hiding something from the desktop never makes
 * it unreachable, because this panel is the way back and is itself unhideable.
 * The toggle is live: the icons re-render on the spot, no reload. The choice is
 * per browser (localStorage), like taskbar pins on a real desktop.
 *
 * THE DOCK AND THE FOLDERS (2026-10-29). Each row can put its app on the bottom dock (an
 * alias — the app stays where it is), refused past eight with the dock's own words. And
 * once, after the folders upgrade, this window offers "undo — put my icons back": his
 * pre-folders icon positions, written back exactly, every app loose again (desktopLayout.js).
 *
 * The third argument to useSyncExternalStore is the server snapshot: without it
 * renderToStaticMarkup throws, and G-ROOM-KIT draws this panel that way.
 *
 * Prefix `ap-`, per G-ROOM-CSS.
 */

/* What the view is handed, read from the stores now; `onHint` takes a refusal's words. */
export function appsProps(onHint) {
  return {
    hidden: vis.hiddenSet(DOCK_HIDDEN_DEFAULT),
    docked: new Set(layout.dockItems()),
    canUndo: layout.canUndoMigration(),
    onToggle: (id) => vis.toggle(id, DOCK_HIDDEN_DEFAULT),
    onDock: (id) => { const r = layout.dockAdd(id); onHint(r.ok ? '' : r.why) },
    onUndock: (id) => { const r = layout.dockRemove(id); onHint(r.ok ? '' : r.why) },
    onUndo: () => layout.undoMigration(),
    onKeep: () => layout.dismissUndo(),
  }
}

/* The window, drawn from what it is handed. No hooks: the gate presses its buttons. */
export function AppsView({ hidden, docked, canUndo, hint, onToggle, onDock, onUndock, onUndo, onKeep }) {
  return (
    <div className="ap pad">
      {canUndo ? (
        <div className="ap-undo" role="group" aria-label="undo the folders">
          <div className="ap-undo-t">
            Your apps went into folders. Undo puts your old icon positions back — every app
            loose on the desktop again, where it was before the folders. Any position you have
            set since the upgrade is replaced.
          </div>
          <div className="ap-undo-t">
            Music and Games now show on the desktop (they were hidden before the folders) unless
            your saved icon list hides them.
          </div>
          <div className="ap-undo-b">
            <Button size="sm" onClick={onUndo}>undo — put my icons back</Button>
            <Button size="sm" variant="ghost" onClick={onKeep}>keep the folders</Button>
          </div>
        </div>
      ) : null}
      {/* DeskIcons reads the same deskVisibility.hiddenSet — this list decides the desktop icons */}
      <div className="muted ap-note">
        tick an app to keep it on the desktop. everything stays reachable here
        either way — this list never hides.
      </div>
      <div className="ap-hint" role="status">{hint || ''}</div>
      {APPS.filter(a => a.id !== 'apps').map(a => (
        <label key={a.id} className="ap-row">
          <input type="checkbox" checked={!hidden.has(a.id)}
                 aria-label={'show ' + a.title + ' on the desktop'}
                 onChange={() => onToggle(a.id)} />
          <span className="ap-ic"><Icon name={a.icon} size={16} /></span>
          <span className="ap-ti">{a.title}</span>
          <span className="ap-blurb">{a.blurb}</span>
          {docked.has(a.id)
            ? <Button size="sm" variant="ghost" aria-label={'remove ' + a.title + ' from the dock'}
                      onClick={(e) => { if (e) e.preventDefault(); onUndock(a.id) }}>remove from dock</Button>
            : <Button size="sm" variant="ghost" aria-label={'add ' + a.title + ' to the dock'}
                      onClick={(e) => { if (e) e.preventDefault(); onDock(a.id) }}>add to dock</Button>}
        </label>
      ))}
    </div>
  )
}

export default function Apps() {
  useSyncExternalStore(vis.subscribe, vis.getVersion, vis.getVersion)
  useSyncExternalStore(layout.onChange, layout.getVersion, layout.getVersion)
  const [hint, setHint] = useState('')
  return <AppsView {...appsProps(setHint)} hint={hint} />
}
