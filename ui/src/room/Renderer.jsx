import { createContext, useContext } from 'react'
import Backdrop2D from './Backdrop2D.jsx'
import { describeRoom } from './describe.js'

/* Renderer — THE SEAM, put in on day one so "2D now, 3D later" is structural
 * rather than a hope.
 *
 * The operator chose rich 2D now with WebGL as a later layer. That decision is only
 * real if the later layer can arrive WITHOUT touching a single panel — otherwise
 * "later" quietly means "rewrite everything", which is how every 2D-first UI stays
 * 2D forever.
 *
 * So the room never draws directly. It describes its MOOD — the time, her state,
 * whether anyone is here — and a renderer decides what that looks like. Swapping
 * Backdrop2D for a three.js scene is one line here and nothing anywhere else.
 *
 * WHAT A RENDERER MAY NOT DO: fetch, own state, or know what a panel is. It gets a
 * description of the room's feeling and paints. Everything it needs arrives as
 * props, so a renderer is testable without a backend and cannot become the second
 * place the room's state lives.
 */
const RendererCtx = createContext({ kind: '2d' })

export const useRenderer = () => useContext(RendererCtx)

/* The contract lives in describe.js — plain JS with no imports, so a gate can
 * exercise it in node without a browser or a build. A seam that cannot be tested
 * without the thing on both sides of it is not a seam. */
export { MOOD_KEYS, describeRoom } from './describe.js'

export function Renderer({ kind = '2d', pulse, children }) {
  const room = describeRoom(pulse)
  const Impl = kind === '2d' ? Backdrop2D : Backdrop2D   // 3d slots in here
  return (
    <RendererCtx.Provider value={{ kind, room }}>
      <Impl room={room} />
      {children}
    </RendererCtx.Provider>
  )
}

export default Renderer
