import { createContext, type ReactNode, type RefObject, useEffect, useRef, useState } from 'react';

import { isLandscape, useLandscapeAllowed } from '../lib/landscape';
import type { Direction } from '../lib/swipe';
import { type CardShape, turnStart } from '../lib/turn';
import './LargeView.css';

/**
 * Tells the large view when its card is zoomed in (see LargeCard in
 * CardPicture.tsx), which pauses moving to other cards until it is back
 * to normal size
 */
export const ZoomedContext = createContext<(zoomed: boolean) => void>(() => {});

/**
 * The large view, in the browser's own <dialog>: it dims the page and
 * keeps keyboard focus inside. Esc, the close button and a tap outside
 * the card all call onClose.
 */
interface LargeViewProps {
  children: ReactNode;
  onClose: () => void;
  /** Moving to another card, when there are others to move to */
  onMove?: (direction: Direction) => void;
  hasPrevious?: boolean;
  hasNext?: boolean;
}

export default function LargeView({
  children,
  onClose,
  onMove,
  hasPrevious,
  hasNext,
}: LargeViewProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [zoomed, setZoomed] = useState(false);
  // When the view opened: a quick second tap right after the one that
  // opened it (a double tap on the small card) must not close it again
  const openedAt = useRef(performance.now());

  useEffect(() => {
    // Already open when React runs this a second time (StrictMode, in
    // development): showModal on an open dialog is an error
    if (dialog.current && !dialog.current.open) dialog.current.showModal();
  }, []);

  // A phone may turn sideways while the large view is open, to read a
  // card printed sideways
  useLandscapeAllowed();

  // Turning the phone changes the card's size smoothly, as in a photo
  // app, see useSmoothTurn
  const turning = useSmoothTurn(dialog);

  return (
    <dialog
      ref={dialog}
      className={['enlarged', zoomed && 'zoomed', turning && 'turning'].filter(Boolean).join(' ')}
      // Esc: close it the same way as the other ways, through history
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onKeyDown={(event) => {
        if (onMove === undefined || zoomed) return;
        if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
        // Instead of the browser's own small scroll step
        event.preventDefault();
        onMove(event.key === 'ArrowRight' ? 'next' : 'previous');
      }}
      // A tap anywhere but on the card or a button counts as outside it
      onClick={(event) => {
        if (performance.now() - openedAt.current < 400) return;
        if (!(event.target as Element).closest('.card-picture, button')) onClose();
      }}
    >
      <button className="close" aria-label="Close" onClick={onClose}>
        ✕
      </button>
      {onMove !== undefined && hasPrevious && (
        <button
          className="move previous"
          aria-label="Previous card"
          onClick={() => onMove('previous')}
        >
          ‹
        </button>
      )}
      <ZoomedContext value={setZoomed}>{children}</ZoomedContext>
      {onMove !== undefined && hasNext && (
        <button className="move next" aria-label="Next card" onClick={() => onMove('next')}>
          ›
        </button>
      )}
    </dialog>
  );
}

/** How long the size must stay the same for a turn to count as done, in ms */
const SETTLED_TIME = 80;
/** The longest a turn may take to settle before the card moves anyway, in ms */
const TURN_LONGEST = 600;
/** How long the card takes to change to its new size, in ms */
const TURN_MOVE_TIME = 300;

/** Takes off what the turn animation put on a card's zoom area */
function putBack(area: HTMLElement) {
  area.style.removeProperty('transition');
  area.style.removeProperty('scale');
}

/**
 * The card in the middle of the screen - the one looked at, in the card
 * list's row - with the area it zooms in, which the turn animates
 */
function cardInView(dialog: HTMLElement): { area: HTMLElement; shape: CardShape } | null {
  let best: { content: HTMLElement; distance: number } | null = null;
  for (const content of dialog.querySelectorAll<HTMLElement>('.zoom-content')) {
    const box = content.getBoundingClientRect();
    if (box.width === 0) continue;
    const distance = Math.abs(box.left + box.width / 2 - window.innerWidth / 2);
    if (best === null || distance < best.distance) best = { content, distance };
  }
  const area = best?.content.closest<HTMLElement>('.zoom-area');
  if (!best || !area) return null;
  return {
    area,
    shape: {
      // The layout size, which the animation's own scaling doesn't change
      width: best.content.offsetWidth,
      turned:
        best.content.classList.contains('horizontal') &&
        window.matchMedia('(orientation: landscape)').matches,
    },
  };
}

/**
 * Turning the phone. The browser resizes the page in steps, and the card
 * would jump through them. Instead, through every step the card is drawn
 * at the size it had before, and once the size has settled, it shrinks or
 * grows smoothly to its new size. A card printed sideways that turns with
 * the phone keeps its place, see turnStart. True while a turn is going on.
 */
function useSmoothTurn(dialog: RefObject<HTMLDialogElement | null>): boolean {
  const [turning, setTurning] = useState(false);
  useEffect(() => {
    const element = dialog.current;
    if (element === null) return;
    const lessMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    // How the card looked when last settled
    let before = cardInView(element)?.shape ?? null;
    let landscape = isLandscape();
    // The frame being waited for, while a turn is going on
    let frame: number | undefined;
    let moved: HTMLElement | null = null;

    // Swiping to another card, or a card's picture arriving: remember how
    // the card looks now, since once a turn starts it is already too late.
    // Only in the orientation last heard of: a browser may scroll or
    // redraw for a turn before telling about it (the resize event), and
    // the card would then be measured at its new size already.
    const remember = () => {
      if (frame !== undefined || isLandscape() !== landscape) return;
      before = cardInView(element)?.shape ?? before;
    };
    const every = setInterval(remember, 500);
    let measuring = false;
    const onScroll = () => {
      if (frame !== undefined || measuring) return;
      measuring = true;
      requestAnimationFrame(() => {
        measuring = false;
        remember();
      });
    };

    const draw = (area: HTMLElement, scale: number) => {
      area.style.transition = 'none';
      area.style.scale = `${scale}`;
    };

    const onResize = () => {
      // Only a turn, or more steps of one: not a window being resized
      if (isLandscape() === landscape && frame === undefined) return;
      landscape = isLandscape();
      setTurning(true);
      if (frame !== undefined) cancelAnimationFrame(frame);
      const started = performance.now();
      let size = '';
      let changedAt = started;
      const check = () => {
        const now = cardInView(element);
        if (now !== null && before !== null && !lessMotion) {
          // Another card's area than last frame: put that one back
          if (moved !== null && moved !== now.area) putBack(moved);
          moved = now.area;
          draw(now.area, turnStart(before, now.shape));
        }
        const viewport = `${window.innerWidth}x${window.innerHeight}`;
        if (viewport !== size) changedAt = performance.now();
        size = viewport;
        const still = performance.now() - changedAt;
        if (still < SETTLED_TIME && performance.now() - started < TURN_LONGEST) {
          frame = requestAnimationFrame(check);
          return;
        }
        // Settled: off to the new size
        frame = undefined;
        setTurning(false);
        before = now?.shape ?? before;
        const area = moved;
        if (area === null) return;
        area.style.transition = `scale ${TURN_MOVE_TIME}ms ease-out`;
        area.style.scale = '1';
        setTimeout(() => {
          if (frame === undefined) putBack(area);
        }, TURN_MOVE_TIME + 50);
      };
      frame = requestAnimationFrame(check);
    };

    window.addEventListener('resize', onResize);
    element.addEventListener('scroll', onScroll, { capture: true, passive: true });
    return () => {
      window.removeEventListener('resize', onResize);
      element.removeEventListener('scroll', onScroll, { capture: true });
      clearInterval(every);
      if (frame !== undefined) cancelAnimationFrame(frame);
    };
  }, [dialog]);
  return turning;
}
