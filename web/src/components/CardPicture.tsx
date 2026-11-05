import { type CSSProperties, lazy, Suspense, useState } from 'react';

import { type Card, isHorizontal, visibleName } from '../lib/cards';
import { useLargeView } from '../lib/largeView';
import { canSpeak, sayName } from '../lib/speech';
import './CardPicture.css';
import LargeView from './LargeView';

// The large view's card, with the zoom library: loaded the first time a
// large view opens, so the rest of the app starts without it
const LargeCard = lazy(() => import('./LargeCard'));

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
  /** Shows the button that reads the name aloud, as the large view does */
  speaker?: boolean;
}

/**
 * A card's full picture. Tapping it shows the card as large as the screen
 * allows, in the large view, where it can also zoom.
 * A double-faced card also gets a round button over its artwork that turns
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
  speaker = false,
}: CardPictureProps) {
  const [ownBack, setOwnBack] = useState(false);
  const showingBack = parentBack ?? ownBack;
  const flip = parentFlip ?? (() => setOwnBack(!ownBack));
  const large = useLargeView();

  return (
    <>
      <div className={pictureClass(card)} style={buttonCorner(card, showingBack)}>
        <button
          className="enlarge"
          aria-label={`Enlarge ${card.name}`}
          onClick={onEnlarge ?? large.open}
          // Two fingers on the card open the large view too, to pinch there
          onTouchStart={(event) => {
            if (event.touches.length === 2 && onEnlarge === undefined) large.open();
          }}
        >
          <CardSides card={card} showingBack={showingBack} lazy={lazy} />
        </button>
        {speaker && <SayOnCard name={visibleName(card, showingBack)} />}
        <FlipButton card={card} showingBack={showingBack} onFlip={flip} />
      </div>
      {large.isOpen && (
        <LargeView onClose={large.close}>
          <Suspense fallback={<div className="card-placeholder" />}>
            <LargeCard card={card} showingBack={showingBack} onFlip={flip} />
          </Suspense>
        </LargeView>
      )}
    </>
  );
}

/** Only a double-faced card gets the 3D settings - see CardPicture.css */
export function pictureClass(card: Card): string {
  return card.images.length > 1 ? 'card-picture two-sided' : 'card-picture';
}

/**
 * Where the artwork's top right corner is on a side printed sideways
 * (split cards, Rooms), in the picture as it is stored - upright, with
 * the card's writing running up the side: [left, top]. Turned the right
 * way up, a quarter clockwise, this corner of the picture becomes the
 * artwork's top right one. Measured on Wear // Tear and Unholy Annex on
 * 2026-11-05, whose artwork corners are within 2% of each other.
 */
const SIDEWAYS_ART_CORNER = [0.145, 0.05];

/**
 * Where the buttons over a card go: the top right corner of its artwork,
 * a little inside it, from the card's art box (see art_box in
 * meta_morphis/export.py). Artwork on the left half of the card (classes
 * and cases) gets them in its top left corner instead, at the card's
 * edge rather than in its middle. Both sides of a double-faced card use
 * the front's box, so the buttons stay put when it turns. A side printed
 * sideways gets them in the corner that is the artwork's top right when
 * turned to read. Without a box, the buttons keep their usual place - see
 * .card-button in CardPicture.css.
 */
export function buttonCorner(card: Card, showingBack: boolean): CSSProperties | undefined {
  // CSS variables, which React's style types don't list
  if (isHorizontal(card, showingBack)) {
    const [left, top] = SIDEWAYS_ART_CORNER;
    return {
      '--button-top': `${(top + 0.015) * 100}%`,
      '--button-left': `${(left + 0.02) * 100}%`,
      '--button-right': 'auto',
    } as Record<string, string> as CSSProperties;
  }
  if (!card.art_box) return undefined;
  const [left, top, width] = card.art_box;
  const corner: Record<string, string> = { '--button-top': `${(top + 0.015) * 100}%` };
  if (left + width < 0.6) {
    corner['--button-left'] = `${(left + 0.02) * 100}%`;
    corner['--button-right'] = 'auto';
  } else {
    corner['--button-right'] = `${(1 - left - width + 0.02) * 100}%`;
  }
  return corner as CSSProperties;
}

/** The card's sides stacked, turned to the one showing */
export function CardSides({
  card,
  showingBack,
  lazy,
  pictures = card.images,
}: {
  card: Card;
  showingBack: boolean;
  lazy: boolean;
  /** Other pictures of the same sides, e.g. larger ones */
  pictures?: string[];
}) {
  const [front, back] = pictures;
  return (
    <div className={showingBack ? 'card-sides flipped' : 'card-sides'}>
      {/* crossOrigin lets the saved copy of the picture be used */}
      <img
        className="card-side"
        src={front}
        alt={card.name}
        loading={lazy ? 'lazy' : undefined}
        // Turned into pixels in the background, so scrolling never waits for it
        decoding="async"
        crossOrigin="anonymous"
        aria-hidden={showingBack}
      />
      {back !== undefined && (
        <img
          className="card-side card-back"
          src={back}
          alt={`${card.name}, back`}
          loading={lazy ? 'lazy' : undefined}
          decoding="async"
          crossOrigin="anonymous"
          aria-hidden={!showingBack}
        />
      )}
    </div>
  );
}

/** Nothing for a single-faced card */
export function FlipButton({
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
 * Reads the card's name aloud; in the large view and on a lesson's answer
 * card, where there is room for it. Nothing in a browser that can't speak.
 */
export function SayOnCard({ name }: { name: string }) {
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
