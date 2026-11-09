import {
  type CSSProperties,
  lazy,
  type RefObject,
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { flushSync } from 'react-dom';

import { type Card, isHorizontal, SIDEWAYS_ART_BOX, visibleName } from '../lib/cards';
import { useLandscape, useLandscapeAllowed } from '../lib/landscape';
import { useLargeView } from '../lib/largeView';
import { canSpeak, sayName } from '../lib/speech';
import './CardPicture.css';
import type { TurnBack, TurnedFrom } from './LargeCard';
import LargeView from './LargeView';

// The large view's card, with the zoom library: loaded the first time a
// large view opens, so the rest of the app starts without it. Once
// loaded, it is also kept here and used directly: lazy shows its
// fallback for a moment the first time it draws, even when the code is
// already there, and a view opened as the phone turns (useOpenOnTurn)
// must show the card with the turn.
let loadedLargeCard: typeof import('./LargeCard').default | null = null;
function loadLargeCard() {
  return import('./LargeCard').then((module) => {
    loadedLargeCard = module.default;
    return module;
  });
}
const LazyLargeCard = lazy(loadLargeCard);

interface CardPictureProps {
  card: Card;
  /** Load the picture only when it scrolls into view (long lists) */
  lazy?: boolean;
  /** Shows the button that reads the name aloud, as the large view does */
  speaker?: boolean;
  /**
   * A side printed sideways opens in the large view when a phone turns
   * sideways, to read it the right way up: a lesson's answer card
   */
  openOnTurn?: boolean;
}

/**
 * A card's full picture with its own large view: tapping it shows the
 * card as large as the screen allows, where it can also zoom. A lesson's
 * answer card. The card list, whose one large view moves between cards,
 * uses PlainCardPicture instead.
 */
export default function CardPicture({
  card,
  lazy = false,
  speaker = false,
  openOnTurn = false,
}: CardPictureProps) {
  const [showingBack, setShowingBack] = useState(false);
  const flip = () => setShowingBack(!showingBack);
  const large = useLargeView();
  const LargeCard = loadedLargeCard ?? LazyLargeCard;
  const picture = useRef<HTMLDivElement>(null);
  const { turnedFrom, turnBack, goingBack, openByTap, followsPhone } = useOpenOnTurn(
    openOnTurn && isHorizontal(card, showingBack),
    picture,
    large,
  );
  // While the large view's card eases back into this one's place, the view's
  // copy of it stands in for it (see TurnBack in LargeCard.tsx)
  const standIn = goingBack !== false && large.isOpen;

  return (
    <>
      <PlainCardPicture
        ref={picture}
        card={card}
        lazy={lazy}
        showingBack={showingBack}
        onFlip={flip}
        onEnlarge={openByTap}
        // Two fingers on the card open the large view too, to pinch there
        onTwoFingers={openByTap}
        speaker={speaker}
        hidden={standIn}
      />
      {large.isOpen && (
        <LargeView
          onClose={large.close}
          uprightToClose={followsPhone}
          // For the page's and the view's rules (see Lesson.css and LargeView.css)
          className={[turnedFrom && 'opened-by-turn', goingBack === 'landed' && 'leaving']
            .filter(Boolean)
            .join(' ')}
        >
          <Suspense fallback={<div className="card-placeholder" />}>
            <LargeCard
              card={card}
              showingBack={showingBack}
              onFlip={flip}
              turnedFrom={turnedFrom}
              turnBack={turnBack}
            />
          </Suspense>
        </LargeView>
      )}
    </>
  );
}

/**
 * A card's full picture, which asks its parent to show it larger, and
 * to turn it over: the parent keeps track of the side showing.
 * A double-faced card gets a round button over its artwork that turns
 * it over to the back and back again.
 *
 * Card pictures are shown as they are: never stretched or dimmed. The
 * button sits over the artwork, never over the artist name or the
 * copyright at the bottom of the card, which Scryfall asks to keep visible.
 */
export function PlainCardPicture({
  ref,
  card,
  lazy = false,
  showingBack,
  onFlip,
  onEnlarge,
  onTwoFingers,
  speaker = false,
  hidden = false,
}: {
  ref?: RefObject<HTMLDivElement | null>;
  card: Card;
  lazy?: boolean;
  showingBack: boolean;
  onFlip: () => void;
  onEnlarge: () => void;
  /** Two fingers touching the card; in the card list, they pinch the list instead */
  onTwoFingers?: () => void;
  speaker?: boolean;
  /** Hidden but still taking its place */
  hidden?: boolean;
}) {
  return (
    <div
      ref={ref}
      className={pictureClass(card)}
      style={{ ...buttonCorner(card, showingBack), visibility: hidden ? 'hidden' : undefined }}
    >
      <button
        className="enlarge"
        aria-label={`Enlarge ${card.name}`}
        onClick={onEnlarge}
        onTouchStart={(event) => {
          if (event.touches.length === 2) onTwoFingers?.();
        }}
      >
        <CardSides card={card} showingBack={showingBack} lazy={lazy} />
      </button>
      {speaker && <SayOnCard name={visibleName(card, showingBack)} />}
      <FlipButton card={card} showingBack={showingBack} onFlip={onFlip} />
    </div>
  );
}

/**
 * While `enabled`, the large view follows the phone: turned sideways, it
 * opens, showing a side printed sideways the right way up; turned back
 * upright, it closes again - unless a tap had opened it before the turn,
 * and then it stays open. The card eases from its place here into the
 * view, as a card in the large view does when the phone turns, and back
 * into its place here before the view closes (see EaseNewSize in
 * LargeCard.tsx). Sideways, the view can't be closed by hand (see
 * uprightToClose in LargeView.tsx): the screen around the card is built
 * for an upright phone, and the page may turn sideways only for the
 * view. Only on touch screens: a computer's window is often wider than
 * tall anyway.
 *
 * Turned back upright, the view stays dark while its card eases back,
 * and only once the card is in its place, after the phone's own turn,
 * does the page fade in around it, before the view closes. As an iPhone
 * turns, it fills the edges of its turning frame with the page's
 * background color a moment late: fading while the phone turned, the
 * edges were darker than the page.
 *
 * Gives where the card was when the turn opened the view, if it did, and
 * how turning back closes the view; how far the card is on its way back;
 * how to open the view by tapping, which forgets the turn; and whether
 * the view follows the phone.
 */
function useOpenOnTurn(
  enabled: boolean,
  picture: RefObject<HTMLDivElement | null>,
  { isOpen, open, close }: { isOpen: boolean; open: () => void; close: () => void },
): {
  turnedFrom: TurnedFrom | undefined;
  turnBack: TurnBack | undefined;
  goingBack: GoingBack;
  openByTap: () => void;
  followsPhone: boolean;
} {
  const [turnedFrom, setTurnedFrom] = useState<TurnedFrom | undefined>(undefined);
  const [goingBack, setGoingBack] = useState<GoingBack>(false);
  // The same every time: the large view keeps the one it opened with
  const turnBack = useMemo<TurnBack>(
    () => ({
      place: () => placeOf(picture.current),
      // Before the frame is drawn, so the card here hides as its copy
      // starts out from the view
      onStart: () => flushSync(() => setGoingBack('easing')),
      onDone: () => setGoingBack('landed'),
    }),
    [picture],
  );
  // Back in its place: the page fades in around the card (.leaving in
  // LargeView.css), then the view closes
  useEffect(() => {
    if (goingBack !== 'landed' || !isOpen) return;
    const fading = matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : FADE_IN_TIME;
    const timer = setTimeout(close, fading);
    return () => clearTimeout(timer);
  }, [goingBack, isOpen, close]);
  const active = enabled && matchMedia('(pointer: coarse)').matches;
  const landscape = useLandscape();
  useLandscapeAllowed(active && (!landscape || isOpen));

  useEffect(() => {
    if (!active || isOpen) return;
    // The large view's code, loaded ahead, so the view opens with the turn
    void loadLargeCard();
    // Sideways by the page's own layout. Not by the window's size: as an
    // iPhone turns, the page is laid out sideways a frame before the
    // window's size follows, and the card, measured in that frame as if
    // upright, was in its sideways place.
    const root = document.documentElement;
    const sideways = () => root.clientWidth > root.clientHeight;
    // The card's place is measured while upright: once the phone has
    // turned, the page is laid out anew
    const measure = () => (sideways() ? null : placeOf(picture.current));
    let place = measure();
    // Watching the page's own box hears a turn before the new layout's
    // first frame is drawn, so the view opens in that frame (see
    // usePageSize in LargeView.tsx). On an iPhone, the window's resize
    // event can come frames later, after the turn has begun.
    const observer = new ResizeObserver(() => {
      if (!sideways()) {
        place = measure();
        return;
      }
      if (place === null) return;
      const from = place;
      flushSync(() => {
        setTurnedFrom(from);
        setGoingBack(false);
        open();
      });
    });
    observer.observe(root);
    return () => observer.disconnect();
  }, [active, isOpen, open, picture]);

  const openByTap = () => {
    setTurnedFrom(undefined);
    setGoingBack(false);
    open();
  };
  return {
    turnedFrom,
    // Only a view the turn opened closes by turning back
    turnBack: turnedFrom === undefined ? undefined : turnBack,
    goingBack,
    openByTap,
    followsPhone: active,
  };
}

/**
 * A view's card on its way back into the page, as the phone turns
 * upright (see useOpenOnTurn): not, easing back, or there
 */
type GoingBack = false | 'easing' | 'landed';

/** How long the page takes to fade in around it; keep in step with .leaving in LargeView.css */
const FADE_IN_TIME = 300;

/** Where a card's picture is on the screen, see TurnedFrom */
function placeOf(element: HTMLElement | null): TurnedFrom | null {
  if (element === null) return null;
  const box = element.getBoundingClientRect();
  return {
    x: box.left + box.width / 2,
    y: box.top + box.height / 2,
    // Its own width, not changed by the pulse or shake after an answer
    width: element.offsetWidth,
  };
}

/** Only a double-faced card gets the 3D settings - see CardPicture.css */
export function pictureClass(card: Card): string {
  return card.images.length > 1 ? 'card-picture two-sided' : 'card-picture';
}

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
    // The box's top left corner: the artwork's top right one, turned
    const [left, top] = SIDEWAYS_ART_BOX;
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
