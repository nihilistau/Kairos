/* flight — where a minimising window flies to (redesign stage 6).
 *
 * The taskbar's middle scrolls (stage 3), and a minimised window's button is not the focused
 * one, so it can sit outside the strip's visible span. Aimed at its true centre, the window
 * flew past the strip's edge — at 375px off the screen. The target's x is clamped into the
 * strip, so the window lands where the strip IS, at its nearest edge. Pure, so G-ROOM-KIT
 * drives it under node; the window manager stays free of geometry (spec §8). */
export function flightTarget(btn, strip) {
  const x = btn.left + btn.width / 2, y = btn.top + btn.height / 2
  if (!strip) return { x, y }
  return { x: Math.min(Math.max(x, strip.left), strip.right), y }
}
