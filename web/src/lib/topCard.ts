// Finding the card at the top of the screen in the card list, which keeps
// that card in view when the phone turns - see useKeepPlaceOnResize in
// screens/CardList.tsx.

/**
 * The first card whose bottom is below the top of the screen; null when
 * every card is above it. The cards of a row share their bottom (see
 * .card-grid li in App.css), so bottoms only grow down the list. That
 * lets each step measure the middle card of the cards left and drop the
 * half the top card can't be in: about 9 measurements for 500 cards,
 * instead of one for every card above the screen, on every frame of a
 * scroll.
 */
export function topCard<T extends Element>(cards: ArrayLike<T>): T | null {
  // The top card is at `low` or after it, and at `high` or before it;
  // `high` past the end means none yet
  let low = 0;
  let high = cards.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (cards[middle].getBoundingClientRect().bottom > 0) high = middle;
    else low = middle + 1;
  }
  return low < cards.length ? cards[low] : null;
}
