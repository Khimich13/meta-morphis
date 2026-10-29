import { createContext, type ReactNode, useEffect, useRef, useState } from 'react';

import type { Direction } from '../lib/swipe';
import './LargeView.css';

/**
 * Tells the large view when its card is zoomed in (see lib/zoom.ts), which
 * pauses moving to other cards until it is back to normal size
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

  useEffect(() => {
    // Already open when React runs this a second time (StrictMode, in
    // development): showModal on an open dialog is an error
    if (dialog.current && !dialog.current.open) dialog.current.showModal();
  }, []);

  return (
    <dialog
      ref={dialog}
      className={zoomed ? 'enlarged zoomed' : 'enlarged'}
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
