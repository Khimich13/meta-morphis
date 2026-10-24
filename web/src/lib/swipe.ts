// Moving between cards in the card list's large view with the arrow keys
// or the previous and next buttons. Swiping is the browser's own
// scrolling - see CardRow in screens/CardList.tsx.

export type Direction = 'next' | 'previous';

/** The position of the card to move to; the same one at either end of the list */
export function step(index: number, direction: Direction, count: number): number {
  const target = direction === 'next' ? index + 1 : index - 1;
  return target < 0 || target >= count ? index : target;
}
