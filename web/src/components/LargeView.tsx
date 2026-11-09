import {
  createContext,
  type ReactNode,
  type RefObject,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';

import { isLandscape, useLandscapeAllowed } from '../lib/landscape';
import type { Direction } from '../lib/swipe';
import './LargeView.css';

/**
 * Tells the large view when its card is zoomed in (see LargeCard.tsx),
 * which pauses moving to other cards until it is back
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
  /**
   * While the phone is sideways, only turning it upright closes the view:
   * no close button, and Esc and taps outside the card do nothing. For a
   * lesson's sideways answer card, whose screen is built for an upright
   * phone (see useOpenOnTurn in CardPicture.tsx).
   */
  uprightToClose?: boolean;
  /** More classes for the view, for the rules of the page it's on */
  className?: string;
}

export default function LargeView({
  children,
  onClose,
  onMove,
  hasPrevious,
  hasNext,
  uprightToClose = false,
  className,
}: LargeViewProps) {
  // Closing by hand is off while sideways, see uprightToClose
  const closeByHand = () => {
    if (!(uprightToClose && isLandscape())) onClose();
  };
  const dialog = useRef<HTMLDialogElement>(null);
  const [zoomed, setZoomed] = useState(false);
  // When the view opened: a quick second tap right after the one that
  // opened it (a double tap on the small card) must not close it again
  const openedAt = useRef(performance.now());

  // A layout effect, which React runs before every plain effect, so the
  // view's content finds the dialog open in its own effects: only an open
  // dialog has a size (CardRow in CardList.tsx scrolls by it)
  useLayoutEffect(() => {
    const element = dialog.current;
    if (element === null) return;
    // Already open when React runs this a second time (StrictMode, in
    // development): showModal on an open dialog is an error
    if (!element.open) element.showModal();
    // Keyboard focus on the view itself, not on its first button, which
    // the browser would focus and ring - a ring on the close button for
    // every tap that opens the view. Tab still reaches the buttons.
    element.focus();
  }, []);

  // A phone may turn sideways while the large view is open, to read a
  // card printed sideways
  useLandscapeAllowed();
  usePageSize(dialog);

  return (
    <dialog
      ref={dialog}
      tabIndex={-1}
      className={['enlarged', zoomed && 'zoomed', uprightToClose && 'upright-to-close', className]
        .filter(Boolean)
        .join(' ')}
      // Esc: close it the same way as the other ways, through history
      onCancel={(event) => {
        event.preventDefault();
        closeByHand();
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
        if (!(event.target as Element).closest('.card-picture, button')) closeByHand();
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
      {/* Only on a sideways phone, see LargeView.css */}
      {uprightToClose && <p className="upright-hint">↻ Turn your phone upright to continue</p>}
      {onMove !== undefined && hasNext && (
        <button className="move next" aria-label="Next card" onClick={() => onMove('next')}>
          ›
        </button>
      )}
    </dialog>
  );
}

/**
 * Keeps the view the size of the page's own layout, in --page-width and
 * --page-height (see LargeView.css). As an iPhone app turns, the page's
 * layout has its new size from the first frame, while the box the screen
 * gives the view covers the old and the new screen at once for a frame or
 * two. The page's root element is as wide as its layout, so watching it
 * hears every turn before the frame is drawn; the window's resize event
 * catches a change of height alone.
 */
function usePageSize(dialog: RefObject<HTMLDialogElement | null>) {
  useLayoutEffect(() => {
    const element = dialog.current;
    if (element === null) return;
    const root = document.documentElement;
    const update = () => {
      element.style.setProperty('--page-width', `${root.clientWidth}px`);
      element.style.setProperty('--page-height', `${root.clientHeight}px`);
    };
    update();
    const observer = new ResizeObserver(update);
    // From the next frame: the view may open from another observer of the
    // page, as the phone turns (see useOpenOnTurn in CardPicture.tsx), and
    // the browser reports one starting on the same box meanwhile as an
    // error. The size is already set for this frame.
    const start = requestAnimationFrame(() => observer.observe(root));
    window.addEventListener('resize', update);
    return () => {
      cancelAnimationFrame(start);
      observer.disconnect();
      window.removeEventListener('resize', update);
    };
  }, [dialog]);
}
