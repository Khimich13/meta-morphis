// Pinching with two fingers. Phones zoom the whole page on a pinch, which
// pushes the screens out of shape, so the app stops that everywhere. The
// large view zooms its card itself (see LargeCard in
// components/CardPicture.tsx), and in the card list a pinch changes how
// many cards fit in a row.

import { type RefObject, useEffect, useLayoutEffect, useRef, useState } from 'react';

/**
 * True while the page is zoomed in, which the app tries never to allow -
 * but should a browser zoom it anyway, the player must be able to undo it
 */
export function isZoomed(): boolean {
  return (window.visualViewport?.scale ?? 1) > 1.01;
}

/** Called once when the app starts */
export function stopPageZoom(): void {
  const stop = (event: Event) => {
    // A zoomed page must always be able to pinch back to normal size
    if (!isZoomed()) event.preventDefault();
  };
  // A second finger touching down, and two fingers moving: a pinch.
  // Not passive, or the browser ignores preventDefault.
  const twoFingers = (event: TouchEvent) => {
    if (event.touches.length > 1) stop(event);
  };
  document.addEventListener('touchstart', twoFingers, { passive: false });
  document.addEventListener('touchmove', twoFingers, { passive: false });
  // Safari's own pinch events, which it may act on before any of those.
  // On iPhones, these are what stops the zoom: Safari ignores the CSS
  // rule against it (touch-action in App.css), which other browsers obey.
  for (const name of ['gesturestart', 'gesturechange', 'gestureend']) {
    document.addEventListener(name, stop, { passive: false });
  }
}

/** The most cards in a row that pinching in can give */
const MAX_COLUMNS = 6;
/** The room each card needs in a row, with the space beside it, in pixels */
const MIN_CARD_ROOM = 50;

/** How many cards a pinch may fit in a row of this width */
export function mostColumns(width: number): number {
  return Math.min(MAX_COLUMNS, Math.max(1, Math.floor(width / MIN_CARD_ROOM)));
}

/** A card is this many times as tall as it is wide */
const CARD_SHAPE = 680 / 488;

/**
 * How wide each card is at this many per row, as App.css lays them out
 * (.card-grid.chosen): at most 480px, with less space between them the
 * more there are
 */
function cardWidth(rowWidth: number, columns: number): number {
  const gap = Math.min(16, 32 / columns);
  return Math.min(480, (rowWidth - gap * (columns - 1)) / columns);
}

/**
 * The fewest cards a pinch may leave in a row: the fewest at which a whole
 * card fits in the screen's height. On a phone turned sideways, one or two
 * per row made each card taller than the screen.
 */
export function fewestColumns(rowWidth: number, screenHeight: number): number {
  const most = mostColumns(rowWidth);
  for (let columns = 1; columns < most; columns++) {
    if (cardWidth(rowWidth, columns) * CARD_SHAPE <= screenHeight) return columns;
  }
  return most;
}

/**
 * The fewest cards per row for the grid (see fewestColumns), kept up to
 * date as the window changes size or the phone turns
 */
export function useFewestColumns(grid: RefObject<HTMLElement | null>): number {
  const [fewest, setFewest] = useState(1);
  useLayoutEffect(() => {
    const element = grid.current;
    if (element === null) return;
    const update = () => setFewest(fewestColumns(element.clientWidth, window.innerHeight));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    window.addEventListener('resize', update);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', update);
    };
  }, [grid]);
  return fewest;
}

/** How far apart the fingers must spread, at the fewest cards per row, to open the card */
const OPEN_SPREAD = 1.4;

/** How long the cards take to move to their new places, in milliseconds */
const MOVE_TIME = 250;

/** Where each card of the grid that is on the screen is drawn */
function cardsOnScreen(grid: HTMLElement): Map<Element, DOMRect> {
  const places = new Map<Element, DOMRect>();
  for (const card of grid.children) {
    const place = card.getBoundingClientRect();
    if (place.bottom > 0 && place.top < window.innerHeight) places.set(card, place);
  }
  return places;
}

/**
 * Moves each card that was on the screen smoothly from its old place to
 * its new one, and fades in the cards that have just come into view
 */
function animateCards(grid: HTMLElement, before: Map<Element, DOMRect>): void {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  for (const [card, now] of cardsOnScreen(grid)) {
    // A card still moving from the last step starts again from where it is
    for (const animation of card.getAnimations()) animation.cancel();
    const was = before.get(card);
    const timing = { duration: MOVE_TIME, easing: 'ease-out' };
    if (was === undefined) {
      card.animate([{ opacity: 0 }, { opacity: 1 }], timing);
      continue;
    }
    const x = was.left - now.left;
    const y = was.top - now.top;
    const scale = was.width / now.width;
    card.animate(
      [
        { transformOrigin: 'top left', transform: `translate(${x}px, ${y}px) scale(${scale})` },
        { transformOrigin: 'top left', transform: 'none' },
      ],
      timing,
    );
  }
}

/**
 * The number of columns after a pinch. `spread` is how far apart the
 * fingers are now, compared with when the pinch began: 2 means twice as
 * far apart. Twice as far halves the columns (bigger cards), half as far
 * doubles them, rounded to whole columns, between `fewest` and `most`.
 */
export function columnsAfterPinch(
  start: number,
  spread: number,
  fewest: number,
  most: number,
): number {
  return Math.min(most, Math.max(fewest, Math.round(start / spread)));
}

function distance(touches: TouchList): number {
  const [a, b] = [touches[0], touches[1]];
  return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
}

/**
 * Lets a pinch on the grid change its number of columns (`columns`, or
 * the number that fit by themselves while it is null). The card under
 * the fingers stays where it was on the screen while the grid changes.
 * At the fewest cards per row, spreading the fingers opens the card under
 * them.
 */
export function usePinchColumns(
  grid: RefObject<HTMLElement | null>,
  columns: number | null,
  setColumns: (columns: number) => void,
  /** Opens the large view on the card at this position of the grid */
  openCard: (position: number) => void,
): void {
  // The latest openCard, without setting up the touch handling again
  const open = useRef(openCard);
  useEffect(() => {
    open.current = openCard;
  });
  // The card under the fingers and how far it was from the screen's top
  const anchor = useRef<{ card: Element; top: number } | null>(null);
  // Where the cards on the screen were before the grid changed
  const before = useRef<Map<Element, DOMRect> | null>(null);

  useEffect(() => {
    const element = grid.current;
    if (element === null) return;
    let start: { spread: number; columns: number } | null = null;

    function begin(event: TouchEvent) {
      // While zoomed, a pinch zooms the page back out instead
      if (event.touches.length !== 2 || element === null || isZoomed()) return;
      const style = getComputedStyle(element);
      start = {
        spread: distance(event.touches),
        // How many columns there are now, chosen or automatic
        columns: style.gridTemplateColumns.split(' ').length,
      };
    }

    function pinch(event: TouchEvent) {
      // This pinch is the grid's, never the browser's zoom - stopped here
      // too, in case the page-wide blocker doesn't hear it
      if (event.touches.length > 1 && !isZoomed()) event.preventDefault();
      if (start === null || event.touches.length !== 2 || element === null) return;
      // The card between the two fingers
      const [a, b] = [event.touches[0], event.touches[1]];
      const under = document.elementFromPoint(
        (a.clientX + b.clientX) / 2,
        (a.clientY + b.clientY) / 2,
      );
      const card = under?.closest('.card-grid > li');
      const spread = distance(event.touches) / start.spread;
      const fewest = fewestColumns(element.clientWidth, window.innerHeight);
      // Already the fewest per row and spreading further: open that card,
      // like zooming into a photo
      if (start.columns <= fewest && spread >= OPEN_SPREAD && card) {
        start = null;
        open.current([...element.children].indexOf(card));
        return;
      }
      const most = mostColumns(element.clientWidth);
      const next = columnsAfterPinch(start.columns, spread, fewest, most);
      const now = getComputedStyle(element).gridTemplateColumns.split(' ').length;
      if (next === now) return;
      anchor.current = card ? { card, top: card.getBoundingClientRect().top } : null;
      before.current = cardsOnScreen(element);
      setColumns(next);
    }

    function end(event: TouchEvent) {
      if (event.touches.length < 2) start = null;
    }

    element.addEventListener('touchstart', begin);
    // Not passive, so it can stop the browser's zoom (see pinch)
    element.addEventListener('touchmove', pinch, { passive: false });
    element.addEventListener('touchend', end);
    element.addEventListener('touchcancel', end);
    return () => {
      element.removeEventListener('touchstart', begin);
      element.removeEventListener('touchmove', pinch);
      element.removeEventListener('touchend', end);
      element.removeEventListener('touchcancel', end);
    };
  }, [grid, setColumns]);

  // After the grid changed, before it is drawn: scroll the anchored card
  // back to where it was, then let the cards move there smoothly
  useLayoutEffect(() => {
    if (anchor.current !== null) {
      const { card, top } = anchor.current;
      window.scrollBy(0, card.getBoundingClientRect().top - top);
      anchor.current = null;
    }
    if (before.current !== null && grid.current !== null) {
      animateCards(grid.current, before.current);
      before.current = null;
    }
  }, [columns, grid]);
}
