// Turning the phone with a card in the large view: the card should change
// size smoothly from how it looked to its new size, as in a photo app.
// The math, without the browser, so it can be tested alone.

/** The card on screen: its width, and whether it is turned a quarter */
export interface CardShape {
  width: number;
  /** A card printed sideways, shown turned the right way up (landscape) */
  turned: boolean;
}

/**
 * How much bigger to draw the card in its new layout, so that it looks
 * as it did in the old one; from there it shrinks or grows to its new
 * size (scale 1). A card printed sideways that changed between sideways
 * and turned isn't animated: it stays still as the phone turns around
 * it, so the browser's own turn already shows it right.
 */
export function turnStart(before: CardShape, now: CardShape): number {
  if (before.turned !== now.turned || now.width === 0) return 1;
  return before.width / now.width;
}
