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
import { TransformComponent, TransformWrapper, useTransformInit } from 'react-zoom-pan-pinch';

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
      // When the phone turns, the card moves to its new place at once,
      // with the rest of the screen. The library would otherwise glide it
      // there from its old place, showing it off to the side during the
      // turn. Zoomed in, it keeps its own easing (a card dragged past its
      // edge eases back).
      autoAlignment={zoomedIn ? undefined : { animationTime: 0 }}
      panning={{ disabled: !zoomedIn }}
      // The mouse wheel and touchpad keep scrolling and moving between cards
      wheel={{ disabled: true }}
      onTransform={(_, { scale }) => setZoomedIn(scale > 1.05)}
    >
      {({ resetTransform }) => (
        <>
          <EaseNewSize />
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
        </>
      )}
    </TransformWrapper>
  );
}

/** How long the card takes to reach its new size, about as long as the phone's own turn, in ms */
const EASE_TIME = 300;
/** The most the card's easing moves on in one drawn frame, in ms: a frame's time at 60 frames a second */
const EASE_STEP = 17;

/** The same curve as CSS's ease-in-out, near enough, for t from 0 to 1 */
function easeInOut(t: number): number {
  return t < 0.5 ? 4 * t ** 3 : 1 - (2 - 2 * t) ** 3 / 2;
}

/**
 * The screen's angle (screen.orientation.angle) with the phone turned a
 * quarter clockwise from upright, its top to the right. In that landscape,
 * a card printed sideways is turned the same way as the phone.
 */
const CLOCKWISE_ANGLE = 270;

/** The angle of the last landscape seen: turning back upright, the screen already says 0 */
let landscapeAngle = CLOCKWISE_ANGLE;

function rememberLandscape() {
  const angle = screen.orientation?.angle;
  if (angle === 90 || angle === 270) landscapeAngle = angle;
}

/** Whether the phone is in, or turning back upright from, the landscape it reaches by turning clockwise */
function turnedClockwise(): boolean {
  return landscapeAngle === CLOCKWISE_ANGLE;
}

/**
 * Turning the phone gives the card its new size and place at once, as the
 * turn starts. But the phone draws the new page from the top left corner
 * of a frame that only gradually changes from the old screen's shape to
 * the new one as it rotates, so the card, in the middle of the new
 * screen, was drawn far from the middle of that frame, half off the
 * screen, and slid back as the turn ended. Instead, the area the card
 * zooms in is drawn at the card's old size and in the old screen's
 * middle, and eased to its new size and place over the turn, keeping the
 * card in the middle of the turning frame, as in a photo app. Only the
 * drawing moves: the layout, and the zoom library's sense of where the
 * card is, are already the new ones.
 *
 * The card in view moves as a copy in the page itself, above the dimmed
 * page and below the view. While the phone turns, it draws the view only
 * inside the new screen, and the card, still at its old size, was cut off
 * at the new screen's edge. The page is drawn in the whole turning frame.
 * The card itself is hidden until the copy is done. In the card list, the
 * cards beside it are hidden over the turn.
 *
 * The easing moves on frame by frame, by at most a frame's time each: as
 * it turns, the phone may draw no frames for a moment, and an easing by
 * the clock jumped ahead when the next frame came. A second change of
 * size during the easing, as the phone settles the screen's edges a
 * moment after its size, carries on from where the card is.
 *
 * A card printed sideways is turned a quarter in landscape (see
 * LargeView.css). Its copy starts at its old angle and turns to the new
 * one over the same time, the opposite way to the screen's turn: it stays
 * still as the phone turns around it. That works for the landscape the
 * phone reaches by turning clockwise. In the other one, the card still
 * stays still, which leaves it upside down, so once the phone's turn is
 * done it turns half around, smaller while it's crosswise so it stays
 * inside the screen.
 */
function EaseNewSize() {
  // The library's two boxes, once it has set them up
  useTransformInit(({ instance }) => {
    const area = instance.wrapperComponent;
    const content = instance.contentComponent;
    if (area === null || content === null) return;
    // The card's own width, without its quarter turn: the box around a
    // card printed sideways is as wide as the card is long, in landscape
    const cardWidth = () => (content.firstElementChild as HTMLElement | null)?.offsetWidth ?? 0;
    let width = cardWidth();
    let areaWidth = area.offsetWidth;
    let areaHeight = area.offsetHeight;
    // The copy's turn, in degrees from the card's angle after the phone's
    // turn: from, to, then back to 0 after the phone's turn if `to` isn't.
    // A second change of size during the easing doesn't start it again.
    let spin = { from: 0, to: 0 };
    let spun = 0;
    const angleAt = (time: number) =>
      time < EASE_TIME
        ? spin.from + (spin.to - spin.from) * easeInOut(time / EASE_TIME)
        : spin.to * (1 - easeInOut(Math.min((time - EASE_TIME) / EASE_TIME, 1)));
    const spinTime = () => (spin.to === 0 ? EASE_TIME : 2 * EASE_TIME);
    // Whether a turn is being eased; during one, the area's move and the
    // copy's, the card's copy, and the next frame's request
    let turning = false;
    let moving: Animation[] = [];
    let copy: HTMLElement | null = null;
    let frame = 0;
    // The large view, marked as turning while the card in view eases
    let view: Element | null = null;
    const stop = () => {
      turning = false;
      cancelAnimationFrame(frame);
      for (const move of moving) move.cancel();
      moving = [];
      copy?.remove();
      copy = null;
      view?.classList.remove('turning');
      view = null;
      area.style.removeProperty('visibility');
    };
    const observer = new ResizeObserver(() => {
      const before = { width, areaWidth, areaHeight };
      width = cardWidth();
      areaWidth = area.offsetWidth;
      areaHeight = area.offsetHeight;
      const landscape = areaWidth > areaHeight;
      if (landscape) rememberLandscape();
      if (before.width === 0 || width === 0 || width === before.width) return;
      // A turn: the area, the whole screen, changed from upright to
      // sideways or back. Not a window being resized, unless during a
      // turn's easing.
      const turned = before.areaWidth > before.areaHeight !== landscape;
      if (!turned && !turning) return;
      if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      // During an easing: from where the card is on screen, not from its
      // old size, place and angle
      const style = getComputedStyle(area);
      const shown = parseFloat(style.scale) || 1;
      const [x = 0, y = 0] = style.translate === 'none' ? [] : style.translate.split(' ').map(parseFloat);
      const angle = turning ? angleAt(spun) : 0;
      stop();
      turning = true;
      if (turned) {
        // The quarter turn a card printed sideways has in landscape, which
        // its copy starts without, or with, to look as before
        const quarter = content.classList.contains('horizontal') ? (landscape ? -90 : 90) : 0;
        const from = angle + quarter;
        spin = { from, to: from === 0 || turnedClockwise() ? 0 : 2 * from };
        spun = 0;
      }
      // The card's new place on the screen, before any move is drawn
      const card = content.getBoundingClientRect();
      const top = card.top + scrollY;
      const scrolled = scrollY;
      // In the card list's row, each area is one screen wide: only the
      // card in view's area is on the screen
      if (Math.round(area.getBoundingClientRect().left / areaWidth) !== 0) {
        // A card beside it is hidden over the turn. In the old layout it
        // was just past the old screen's edge, and the turning frame grows
        // past that edge: eased from there, the next card came into view.
        // Before and after the turn, it's off the screen anyway.
        area.style.visibility = 'hidden';
      } else {
        // The area was in the old screen's middle. The screen's top left
        // corner stays put.
        const fromX = x + (before.areaWidth - areaWidth) / 2;
        const fromY = y + (before.areaHeight - areaHeight) / 2;
        const moves = [
          { scale: (shown * before.width) / width, translate: `${fromX}px ${fromY}px` },
          { scale: 1, translate: '0px 0px' },
        ];
        const timing = { duration: EASE_TIME, easing: 'ease-in-out' };
        moving = [area.animate(moves, timing)];
        // Its copy, put in the page where the card is on the screen, makes
        // the same move. The card is in the middle of its area, so both
        // grow and shrink around the same point.
        copy = content.cloneNode(true) as HTMLElement;
        // For the view's rules for a card printed sideways (see LargeView.css)
        copy.classList.add('turn-copy');
        copy.inert = true;
        copy.setAttribute('aria-hidden', 'true');
        Object.assign(copy.style, {
          // In the page, which is the box it's placed in while the view is
          // open (see LargeView.css), above the dimming
          position: 'absolute',
          zIndex: '1',
          left: `${card.left + scrollX}px`,
          top: `${top}px`,
          width: `${card.width}px`,
          height: `${card.height}px`,
          margin: '0',
          // Not the zoom library's placing, which the copy doesn't need
          transform: 'none',
          transformOrigin: 'center',
        });
        // The buttons' size in the view (.enlarged .card-button)
        copy.style.setProperty('--size', '56px');
        document.body.append(copy);
        area.style.visibility = 'hidden';
        moving.push(copy.animate(moves, timing));
        // The close button and the card count have other spots upright and
        // sideways: hidden until the turn is done (see LargeView.css)
        view = area.closest('dialog');
        view?.classList.add('turning');
      }
      // The copy's angle, and its size while it turns half around: as large
      // as fits inside the screen's padding at that angle
      const turnCopy = () => {
        if (copy === null) return;
        const degrees = angleAt(spun);
        copy.style.rotate = `${degrees}deg`;
        let fit = 1;
        if (spun > EASE_TIME) {
          const sin = Math.abs(Math.sin((degrees * Math.PI) / 180));
          const cos = Math.abs(Math.cos((degrees * Math.PI) / 180));
          fit = Math.min(
            1,
            (areaWidth - 32) / (card.width * cos + card.height * sin),
            (areaHeight - 32) / (card.width * sin + card.height * cos),
          );
        }
        copy.style.transform = fit < 1 ? `scale(${fit})` : 'none';
      };
      turnCopy();
      // Frame by frame (see above)
      for (const move of moving) move.pause();
      let done = 0;
      let last = performance.now();
      const step = (now: number) => {
        const passed = Math.min(Math.max(now - last, 0), EASE_STEP);
        last = now;
        done = Math.min(done + passed, EASE_TIME);
        spun = Math.min(spun + passed, spinTime());
        if (done >= EASE_TIME && spun >= spinTime()) {
          stop();
          return;
        }
        for (const move of moving) move.currentTime = done;
        turnCopy();
        // If the page scrolls during the turn, the copy moves back by as
        // much, in the same frame
        if (copy !== null) copy.style.top = `${top + scrollY - scrolled}px`;
        frame = requestAnimationFrame(step);
      };
      frame = requestAnimationFrame(step);
    });
    observer.observe(content);
    return () => {
      observer.disconnect();
      stop();
    };
  });
  return null;
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
