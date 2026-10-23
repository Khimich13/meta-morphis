import { type ReactNode, useEffect, useRef, useState } from 'react';

import { type Card, visibleName } from '../lib/cards';
import { isWorthEnlarging } from '../lib/enlarge';
import { canSpeak, sayName } from '../lib/speech';
import './CardPicture.css';

interface CardPictureProps {
  card: Card;
  /** Load the picture only when it scrolls into view (long lists) */
  lazy?: boolean;
}

/**
 * A card's full picture. Tapping it shows the card as large as the screen
 * allows, when that is noticeably larger than it is already shown. A double-faced card also gets a round button over its artwork
 * that turns it over to the back and back again, in both sizes.
 *
 * Card pictures are shown as they are: never stretched or dimmed. The
 * button sits over the artwork, never over the artist name or the
 * copyright at the bottom of the card, which Scryfall asks to keep visible.
 */
export default function CardPicture({ card, lazy = false }: CardPictureProps) {
  // Shared by both sizes, so the large view opens on the side showing
  const [showingBack, setShowingBack] = useState(false);
  const [enlarged, setEnlarged] = useState(false);
  const flip = () => setShowingBack(!showingBack);
  // Only a double-faced card gets the 3D settings - see CardPicture.css
  const pictureClass = card.images.length > 1 ? 'card-picture two-sided' : 'card-picture';

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

  // The phone's back gesture should close the large view, not leave the
  // app. Opening it adds a step to the browser's history; every way of
  // closing goes back one step, and the view closes when that happens.
  function open() {
    history.pushState({ enlarged: true }, '');
    setEnlarged(true);
  }
  const close = () => history.back();

  useEffect(() => {
    if (!enlarged) return;
    const onBack = () => setEnlarged(false);
    window.addEventListener('popstate', onBack);
    return () => window.removeEventListener('popstate', onBack);
  }, [enlarged]);

  return (
    <>
      <div className={pictureClass} ref={picture}>
        {canEnlarge ? (
          <button
            className="enlarge"
            aria-label={`Enlarge ${card.name}`}
            onClick={open}
          >
            <CardSides card={card} showingBack={showingBack} lazy={lazy} />
          </button>
        ) : (
          <CardSides card={card} showingBack={showingBack} lazy={lazy} />
        )}
        <FlipButton card={card} showingBack={showingBack} onFlip={flip} />
      </div>
      {enlarged && (
        <Enlarged onClose={close}>
          <div className={pictureClass}>
            <CardSides card={card} showingBack={showingBack} lazy={false} />
            <FlipButton card={card} showingBack={showingBack} onFlip={flip} />
            {/* The name of the side showing, not both of a double-faced card */}
            <SayOnCard name={visibleName(card, showingBack)} />
          </div>
        </Enlarged>
      )}
    </>
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
function Enlarged({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);

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
      // A tap on the dimmed area lands on the dialog itself, not inside it
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <button className="close" aria-label="Close" onClick={onClose}>
        ✕
      </button>
      {children}
    </dialog>
  );
}
