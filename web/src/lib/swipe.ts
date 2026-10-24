// Moving between cards in the large view: which way a swipe went, and
// which card that leads to.

export type Direction = 'next' | 'previous';

/** A finger must move at least this far sideways to count as a swipe */
export const SWIPE_DISTANCE = 50;

/**
 * The direction of a swipe from how far the finger moved (dx to the
 * right, dy down), or null for a tap or a mostly vertical movement.
 * Swiping left brings the next card, like turning a page.
 */
export function swipeDirection(dx: number, dy: number): Direction | null {
  if (Math.abs(dx) < SWIPE_DISTANCE || Math.abs(dx) <= Math.abs(dy)) return null;
  return dx < 0 ? 'next' : 'previous';
}

/** The position of the card to move to; the same one at either end of the list */
export function step(index: number, direction: Direction, count: number): number {
  const target = direction === 'next' ? index + 1 : index - 1;
  return target < 0 || target >= count ? index : target;
}
