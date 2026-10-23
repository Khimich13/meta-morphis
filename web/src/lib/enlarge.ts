// Whether tapping a card is worth enlarging it: on a phone's answer
// screen the card already fills the width, and the large view would
// show it at the same size, only somewhere else.

/**
 * The card's width in the large view, for a screen of this size. Must
 * match the .enlarged rules in screens/CardPicture.css: 16px at each
 * side, 72px of height for the close button and margins.
 */
export function enlargedWidth(screenWidth: number, screenHeight: number): number {
  return Math.min(screenWidth - 2 * 16, ((screenHeight - 72) * 488) / 680);
}

/** The large view must make the card at least this much wider... */
export const MIN_GAIN = 1.15;

/** ...to be offered */
export function isWorthEnlarging(
  shownWidth: number,
  screenWidth: number,
  screenHeight: number,
): boolean {
  return enlargedWidth(screenWidth, screenHeight) >= shownWidth * MIN_GAIN;
}
