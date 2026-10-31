import {
  type ReactNode,
  type TouchEvent,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';
import { TransformComponent, TransformWrapper } from 'react-zoom-pan-pinch';

import { type Card, visibleName } from '../lib/cards';
import { useLargeView } from '../lib/largeView';
import { canSpeak, sayName } from '../lib/speech';
import { useLargePictures } from '../lib/largePictures';
import './CardPicture.css';
import LargeView, { ZoomedContext } from './LargeView';

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
}: CardPictureProps) {
  const [ownBack, setOwnBack] = useState(false);
  const showingBack = parentBack ?? ownBack;
  const flip = parentFlip ?? (() => setOwnBack(!ownBack));
  const large = useLargeView();

  return (
    <>
      <div className={pictureClass(card)}>
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
        <FlipButton card={card} showingBack={showingBack} onFlip={flip} />
      </div>
      {large.isOpen && (
        <LargeView onClose={large.close}>
          <LargeCard card={card} showingBack={showingBack} onFlip={flip} />
        </LargeView>
      )}
    </>
  );
}

/** Only a double-faced card gets the 3D settings - see CardPicture.css */
function pictureClass(card: Card): string {
  return card.images.length > 1 ? 'card-picture two-sided' : 'card-picture';
}

/**
 * A card in the large view, with its flip and speaker buttons. It zooms
 * over the whole screen, see Zoomable.
 */
export function LargeCard({
  card,
  showingBack,
  onFlip,
  lazy = false,
}: {
  card: Card;
  showingBack: boolean;
  onFlip: () => void;
  /** Load the picture only when it comes into view */
  lazy?: boolean;
}) {
  // Zoomed in: the large view pauses moving to other cards, and hides
  // its buttons and the page behind
  const reportZoomed = useContext(ZoomedContext);
  return (
    <Zoomable card={card} areaClass="zoom-area" onZoomedChange={reportZoomed}>
      {(pictures) => (
        <div className={pictureClass(card)}>
          <CardSides card={card} showingBack={showingBack} lazy={lazy} pictures={pictures} />
          <FlipButton card={card} showingBack={showingBack} onFlip={onFlip} />
          {/* The name of the side showing, not both of a double-faced card */}
          <SayOnCard name={visibleName(card, showingBack)} />
        </div>
      )}
    </Zoomable>
  );
}

/**
 * A card that zooms, with the react-zoom-pan-pinch library: a double tap
 * goes to 2x and back, a pinch up to 4x, and one finger moves around the
 * zoomed card. At normal size, one finger is left to the page (the large
 * view's row swipes with it). Only `areaClass`'s box shows the zoomed
 * card. `children` draws the card, given its sharper pictures once they
 * have loaded (see lib/largePictures.ts).
 */
function Zoomable({
  card,
  areaClass,
  onZoomedChange,
  children,
}: {
  card: Card;
  areaClass: string;
  /** Hears when the card is zoomed in, and back out */
  onZoomedChange: (zoomed: boolean) => void;
  children: (pictures: string[] | undefined) => ReactNode;
}) {
  const [zoomedIn, setZoomedIn] = useState(false);
  useEffect(() => {
    onZoomedChange(zoomedIn);
    // Leaving the card ends its zoom
    return () => {
      if (zoomedIn) onZoomedChange(false);
    };
  }, [zoomedIn, onZoomedChange]);
  const large = useLargePictures(card.large_images, zoomedIn);
  // When and where the last tap while zoomed in ended
  const lastTap = useRef<{ time: number; x: number; y: number } | null>(null);
  // Just shown: the end of the double tap or click that opened the large
  // view would otherwise count as one on the card, and zoom in
  const [justShown, setJustShown] = useState(true);
  useEffect(() => {
    const timer = setTimeout(() => setJustShown(false), 500);
    return () => clearTimeout(timer);
  }, []);
  return (
    <TransformWrapper
      minScale={1}
      maxScale={4}
      centerOnInit
      // A double tap zooms in to 2x where it is. Zooming back out is done
      // below: the library's own double tap doesn't zoom out on a touch
      // screen.
      doubleClick={{ disabled: zoomedIn || justShown, mode: 'zoomIn', step: 1 }}
      // Back in the middle after zooming out
      centerZoomedOut
      panning={{ disabled: !zoomedIn }}
      // The mouse wheel and touchpad keep scrolling and moving between cards
      wheel={{ disabled: true }}
      onTransform={(_, { scale }) => setZoomedIn(scale > 1.05)}
    >
      {({ resetTransform }) => (
        <TransformComponent
          wrapperClass={zoomedIn ? `${areaClass} zoomed` : areaClass}
          contentClass="zoom-content"
          wrapperProps={{
            // While zoomed in, a double tap or double click goes back to
            // normal size
            onTouchEnd: (event) => {
              if (!zoomedIn || !isDoubleTap(event, lastTap)) return;
              // Phones follow a tap with a pretend mouse press for older
              // websites, and the library stops any animation on a mouse
              // press: without this, the zoom-out stops at once
              event.preventDefault();
              resetTransform(250);
            },
            onDoubleClick: () => {
              if (zoomedIn) resetTransform(250);
            },
          }}
        >
          {children(large ?? undefined)}
        </TransformComponent>
      )}
    </TransformWrapper>
  );
}

/** How soon a second tap must follow the first to make a double tap, in ms */
const DOUBLE_TAP_TIME = 300;

/**
 * True when this tap ends close in time (300ms) and place (40px) to the
 * one before. Taps with more than one finger don't count.
 */
function isDoubleTap(
  event: TouchEvent,
  lastTap: { current: { time: number; x: number; y: number } | null },
): boolean {
  if (event.touches.length > 0 || event.changedTouches.length !== 1) return false;
  const { clientX: x, clientY: y } = event.changedTouches[0];
  const before = lastTap.current;
  const isDouble =
    before !== null &&
    event.timeStamp - before.time < DOUBLE_TAP_TIME &&
    Math.hypot(x - before.x, y - before.y) < 40;
  lastTap.current = isDouble ? null : { time: event.timeStamp, x, y };
  return isDouble;
}

/** The card's sides stacked, turned to the one showing */
function CardSides({
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
