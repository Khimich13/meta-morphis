// Turning the phone with a card in the large view: the card should glide
// smoothly from its old size to its new one, as in a photo app.
// The math, without the browser, so it can be tested alone.

/** The card on screen: its width, and whether it is turned a quarter */
export interface CardShape {
  width: number;
  /** A card printed sideways, shown turned the right way up (landscape) */
  turned: boolean;
}

/**
 * Whether the card glides to its new size. A card printed sideways that
 * changed between sideways and turned doesn't: it stays still as the
 * phone turns around it, so the browser's own turn already shows it right.
 */
export function glides(before: CardShape, now: CardShape): boolean {
  return before.turned === now.turned && now.width > 0;
}

/**
 * How long the glide takes to cover most of the way, in ms: after this
 * long about two thirds is covered, after three times this about 95%.
 */
export const GLIDE_TIME = 110;

/**
 * The card's width on screen one frame later: a step towards the new
 * width, the bigger the further it has to go, so it eases in like a
 * spring settling. `elapsed` is the time since the last frame, in ms;
 * the same glide takes the same time at any frame rate. If the new width
 * changes midway (the browser lays the page out in steps), the glide just
 * carries on towards it, without stopping or jumping.
 */
export function glideStep(shown: number, target: number, elapsed: number): number {
  const share = 1 - Math.exp(-Math.max(elapsed, 0) / GLIDE_TIME);
  return shown + (target - shown) * share;
}
