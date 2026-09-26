import { useSyncExternalStore } from 'react'
import { APPS, DOCK_HIDDEN_DEFAULT } from '../appRegistry.jsx'
import * as dock from '../dockPrefs.js'
import { Icon } from '../kit/icons.jsx'

/* APPS — the launcher, and the desktop's own switchboard (2026-08-21, his ask:
 * "an icon on the side bar that brings up a panel containing icons to
 * add/remove from the sidebar live"; the dock left in stage 3, and the same list
 * now decides the desktop icons).
 *
 * Every app is listed here ALWAYS — hiding something from the desktop never makes
 * it unreachable, because this panel is the way back and is itself unhideable.
 * The toggle is live: the icons re-render on the spot, no reload. The choice is
 * per browser (localStorage), like taskbar pins on a real desktop.
 *
 * The third argument to useSyncExternalStore is the server snapshot: without it
 * renderToStaticMarkup throws, and G-ROOM-KIT leg 10 draws this panel that way.
 *
 * Prefix `ap-`, per G-ROOM-CSS.
 */
export default function Apps() {
  useSyncExternalStore(dock.subscribe, dock.getVersion, dock.getVersion)
  const hidden = dock.hiddenSet(DOCK_HIDDEN_DEFAULT)
  return (
    <div className="ap pad">
      {/* DeskIcons reads the same dockPrefs.hiddenSet — this list decides the desktop icons */}
      <div className="muted ap-note">
        tick an app to keep it on the desktop. everything stays reachable here
        either way — this list never hides.
      </div>
      {APPS.filter(a => a.id !== 'apps').map(a => (
        <label key={a.id} className="ap-row">
          <input type="checkbox" checked={!hidden.has(a.id)}
                 aria-label={'show ' + a.title + ' on the desktop'}
                 onChange={() => dock.toggle(a.id, DOCK_HIDDEN_DEFAULT)} />
          <span className="ap-ic"><Icon name={a.icon} size={16} /></span>
          <span className="ap-ti">{a.title}</span>
          <span className="ap-blurb">{a.blurb}</span>
        </label>
      ))}
    </div>
  )
}
