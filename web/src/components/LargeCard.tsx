// The card in a large view, which zooms with the react-zoom-pan-pinch
// library. Its own file so that it and the library load only when a large
// view first opens (see CardPicture.tsx and CardList.tsx), not with the
// rest of the app.

import {
  type ReactNode,
  type TouchEvent,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';
import { TransformComponent, TransformWrapper } from 'react-zoom-pan-pinch';

import { type Card, isHorizontal, visibleName } from '../lib/cards';
import { useLargePictures } from '../lib/largePictures';
import { buttonCorner, CardSides, FlipButton, pictureClass, SayOnCard } from './CardPicture';
import { ZoomedContext } from './LargeView';

/**
 * A card in the large view, with its flip and speaker buttons. It zooms
 * over the whole screen, see Zoomable.
 */
export default function LargeCard({
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
  // Printed sideways: turned the right way up in landscape, where it can
  // fill the screen's width (see LargeView.css)
  const horizontal = isHorizontal(card, showingBack);
  return (
    <>
      <Zoomable
        card={card}
        areaClass="zoom-area"
        contentClass={horizontal ? 'zoom-content horizontal' : 'zoom-content'}
        onZoomedChange={reportZoomed}
      >
        {(pictures) => (
          <div className={pictureClass(card)} style={buttonCorner(card, showingBack)}>
            <CardSides card={card} showingBack={showingBack} lazy={lazy} pictures={pictures} />
            {/* The name of the side showing, not both of a double-faced card */}
            <SayOnCard name={visibleName(card, showingBack)} />
            <FlipButton card={card} showingBack={showingBack} onFlip={onFlip} />
          </div>
        )}
      </Zoomable>
      {/* Only on an upright phone, see LargeView.css */}
      {horizontal && <p className="turn-hint">↻ Turn your phone to read this card</p>}
    </>
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
  contentClass,
  onZoomedChange,
  children,
}: {
  card: Card;
  areaClass: string;
  contentClass: string;
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
          contentClass={contentClass}
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
