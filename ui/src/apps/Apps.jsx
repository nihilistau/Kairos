import { useSyncExternalStore } from 'react'
import { APPS, DOCK_HIDDEN_DEFAULT } from '../appRegistry.jsx'
import * as dock from '../dockPrefs.js'

/* APPS — the launcher, and the dock's own switchboard (2026-08-21, his ask:
 * "an icon on the side bar that brings up a panel containing icons to
 * add/remove from the sidebar live").
 *
 * Every app is listed here ALWAYS — hiding something from the dock never makes
 * it unreachable, because this panel is the way back and is itself unhideable.
 * The toggle is live: the dock re-renders on the spot, no reload. The choice is
 * per browser (localStorage), like taskbar pins on a real desktop.
 *
 * Prefix `ap-`, per G-ROOM-CSS.
 */
export default function Apps() {
  useSyncExternalStore(dock.subscribe, dock.getVersion)
  const hidden = dock.hiddenSet(DOCK_HIDDEN_DEFAULT)
  return (
    <div className="ap pad">
      <div className="muted ap-note">
        tick an app to keep it in the dock. everything stays reachable here
        either way — this list never hides.
      </div>
      {APPS.filter(a => a.id !== 'apps').map(a => (
        <label key={a.id} className="ap-row">
          <input type="checkbox" checked={!hidden.has(a.id)}
                 onChange={() => dock.toggle(a.id, DOCK_HIDDEN_DEFAULT)} />
          <span className="ap-ic">{a.icon}</span>
          <span className="ap-ti">{a.title}</span>
          <span className="ap-blurb">{a.blurb}</span>
        </label>
      ))}
    </div>
  )
}
