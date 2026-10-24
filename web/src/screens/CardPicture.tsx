import { type ReactNode, useEffect, useRef, useState } from 'react';

import { type Card, visibleName } from '../lib/cards';
import { isWorthEnlarging } from '../lib/enlarge';
import { useLargeView } from '../lib/largeView';
import { canSpeak, sayName } from '../lib/speech';
import { type Direction, swipeDirection } from '../lib/swipe';
import './CardPicture.css';

interface CardPictureProps {
  card: Card;
  /** Load the picture only when it scrolls into view (long lists) */
  lazy?: boolean;
  /**
   * Which side shows, and how to turn it over, when the parent keeps
   * track - the card list does, so its large view opens on the same
   * side. Otherwise this picture keeps track itself.
   */
  showingBack?: boolean;
  onFlip?: () => void;
  /**
   * Opens the parent's large view - the card list's, which can move
   * between cards. Otherwise this picture opens its own.
   */
  onEnlarge?: () => void;
}

/**
 * A card's full picture. Tapping it shows the card as large as the screen
 * allows, when that is noticeably larger than it is already shown. A
 * double-faced card also gets a round button over its artwork that turns
 * it over to the back and back again, in both sizes.
 *
 * Card pictures are shown as they are: never stretched or dimmed. The
 * button sits over the artwork, never over the artist name or the
 * copyright at the bottom of the card, which Scryfall asks to keep visible.
 */
export default function CardPicture({
  card,
  lazy = false,
  showingBack: parentBack,
  onFlip: parentFlip,
  onEnlarge,
}: CardPictureProps) {
  const [ownBack, setOwnBack] = useState(false);
  const showingBack = parentBack ?? ownBack;
  const flip = parentFlip ?? (() => setOwnBack(!ownBack));
  const large = useLargeView();

  // Enlarging is offered only when the large view would make the card
  // noticeably bigger - see lib/enlarge.ts. Checked again whenever the
  // card or the screen changes size.
  const picture = useRef<HTMLDivElement>(null);
  const [canEnlarge, setCanEnlarge] = useState(false);
  useEffect(() => {
    const element = picture.current;
    if (element === null) return;
    const check = () =>
      setCanEnlarge(
        isWorthEnlarging(element.offsetWidth, window.innerWidth, window.innerHeight),
      );
    check();
    // The card's own size, e.g. a lesson column that narrows
    const observer = new ResizeObserver(check);
    observer.observe(element);
    // The screen's size, which sets the large view's size
    window.addEventListener('resize', check);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', check);
    };
  }, []);

  return (
    <>
      <div className={pictureClass(card)} ref={picture}>
        {canEnlarge ? (
          <button
            className="enlarge"
            aria-label={`Enlarge ${card.name}`}
            onClick={onEnlarge ?? large.open}
          >
            <CardSides card={card} showingBack={showingBack} lazy={lazy} />
          </button>
        ) : (
          <CardSides card={card} showingBack={showingBack} lazy={lazy} />
        )}
        <FlipButton card={card} showingBack={showingBack} onFlip={flip} />
      </div>
      {large.isOpen && (
        <Enlarged onClose={large.close}>
          <LargeCard card={card} showingBack={showingBack} onFlip={flip} />
        </Enlarged>
      )}
    </>
  );
}

/** Only a double-faced card gets the 3D settings - see CardPicture.css */
function pictureClass(card: Card): string {
  return card.images.length > 1 ? 'card-picture two-sided' : 'card-picture';
}

/** A card in the large view, with its flip and speaker buttons */
export function LargeCard({
  card,
  showingBack,
  onFlip,
}: {
  card: Card;
  showingBack: boolean;
  onFlip: () => void;
}) {
  return (
    <div className={pictureClass(card)}>
      <CardSides card={card} showingBack={showingBack} lazy={false} />
      <FlipButton card={card} showingBack={showingBack} onFlip={onFlip} />
      {/* The name of the side showing, not both of a double-faced card */}
      <SayOnCard name={visibleName(card, showingBack)} />
    </div>
  );
}

/** The card's sides stacked, turned to the one showing */
function CardSides({
  card,
  showingBack,
  lazy,
}: {
  card: Card;
  showingBack: boolean;
  lazy: boolean;
}) {
  const [front, back] = card.images;
  return (
    <div className={showingBack ? 'card-sides flipped' : 'card-sides'}>
      {/* crossOrigin lets the saved copy of the picture be used */}
      <img
        className="card-side"
        src={front}
        alt={card.name}
        loading={lazy ? 'lazy' : undefined}
        crossOrigin="anonymous"
        aria-hidden={showingBack}
      />
      {back !== undefined && (
        <img
          className="card-side card-back"
          src={back}
          alt={`${card.name}, back`}
          loading={lazy ? 'lazy' : undefined}
          crossOrigin="anonymous"
          aria-hidden={!showingBack}
        />
      )}
    </div>
  );
}

/** Nothing for a single-faced card */
function FlipButton({
  card,
  showingBack,
  onFlip,
}: {
  card: Card;
  showingBack: boolean;
  onFlip: () => void;
}) {
  if (card.images.length < 2) return null;
  return (
    <button
      className="card-button flip"
      aria-label={showingBack ? 'Flip to see the front' : 'Flip to see the back'}
      onClick={onFlip}
    >
      ↻
    </button>
  );
}

/**
 * Reads the card's name aloud; only in the large view, where there is
 * room for it. Nothing in a browser that can't speak.
 */
function SayOnCard({ name }: { name: string }) {
  if (!canSpeak()) return null;
  return (
    <button
      className="card-button say-on-card"
      aria-label={`Say ${name}`}
      onClick={() => sayName(name)}
    >
      {/* A drawn speaker rather than an emoji, so it takes the button's
          see-through color like the flip symbol does */}
      <svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">
        <path d="M3 9v6h4l5 5V4L7 9H3z" />
        <path
          d="M16 8.5a5 5 0 0 1 0 7M18.5 6a8.5 8.5 0 0 1 0 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    </button>
  );
}

/**
 * The large view, in the browser's own <dialog>: it dims the page and
 * keeps keyboard focus inside. Esc, the close button and a tap outside
 * the card all call onClose.
 */
interface EnlargedProps {
  children: ReactNode;
  onClose: () => void;
  /** Moving to another card, when there are others to move to */
  onMove?: (direction: Direction) => void;
  hasPrevious?: boolean;
  hasNext?: boolean;
}

export function Enlarged({ children, onClose, onMove, hasPrevious, hasNext }: EnlargedProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  // Where a finger or mouse went down, to recognize a swipe when it lifts
  const pressed = useRef<{ x: number; y: number } | null>(null);
  // A swipe ends with a click too; it must not count as a tap outside
  const swiped = useRef(false);

  useEffect(() => {
    // Already open when React runs this a second time (StrictMode, in
    // development): showModal on an open dialog is an error
    if (dialog.current && !dialog.current.open) dialog.current.showModal();
  }, []);

  return (
    <dialog
      ref={dialog}
      className="enlarged"
      // Esc: close it the same way as the other ways, through history
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onPointerDown={(event) => {
        pressed.current = { x: event.clientX, y: event.clientY };
        swiped.current = false;
      }}
      onPointerUp={(event) => {
        const start = pressed.current;
        pressed.current = null;
        if (start === null || onMove === undefined) return;
        const direction = swipeDirection(event.clientX - start.x, event.clientY - start.y);
        if (direction !== null) {
          swiped.current = true;
          onMove(direction);
        }
      }}
      onKeyDown={(event) => {
        if (onMove === undefined) return;
        if (event.key === 'ArrowRight') onMove('next');
        if (event.key === 'ArrowLeft') onMove('previous');
      }}
      // A tap on the dimmed area lands on the dialog itself, not inside it
      onClick={(event) => {
        if (swiped.current) {
          swiped.current = false;
          return;
        }
        if (event.target === event.currentTarget) onClose();
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
      {children}
      {onMove !== undefined && hasNext && (
        <button className="move next" aria-label="Next card" onClick={() => onMove('next')}>
          ›
        </button>
      )}
    </dialog>
  );
}
