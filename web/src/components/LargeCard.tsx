// The card in a large view, which zooms with the react-zoom-pan-pinch
// library. Its own file so that it and the library load only when a large
// view first opens (see CardPicture.tsx and CardList.tsx), not with the
// rest of the app.

import { type ReactNode, type TouchEvent, useContext, useEffect, useRef, useState } from 'react';
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
  turnedFrom,
  turnBack,
}: {
  card: Card;
  showingBack: boolean;
  onFlip: () => void;
  /** Load the picture only when it comes into view */
  lazy?: boolean;
  /** Opened by turning the phone: where the card was before the turn */
  turnedFrom?: TurnedFrom;
  /** Opened by turning the phone: turning it back closes the view */
  turnBack?: TurnBack;
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
        turnedFrom={turnedFrom}
        turnBack={turnBack}
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
 * Where a card was on the screen just before the phone turned: its
 * middle, and its own width, without any quarter turn. In the page's
 * coordinates as they are on the screen; the screen's top left corner
 * stays put as the phone turns.
 */
export interface TurnedFrom {
  x: number;
  y: number;
  width: number;
}

/**
 * A view that turning the phone opened, which turning it back upright
 * closes: the card eases back into its place on the page underneath,
 * then the view closes
 */
export interface TurnBack {
  /** Where the card on the page is now, upright, to ease into */
  place: () => TurnedFrom | null;
  /** The easing back starts: the card on the page hides */
  onStart: () => void;
  /** The card is back in its place: the page shows, and the view closes */
  onDone: () => void;
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
  turnedFrom,
  turnBack,
  children,
}: {
  card: Card;
  areaClass: string;
  contentClass: string;
  /** Hears when the card is zoomed in, and back out */
  onZoomedChange: (zoomed: boolean) => void;
  turnedFrom?: TurnedFrom;
  turnBack?: TurnBack;
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
  // The card's scale when it last set the view's fade
  const lastScale = useRef(1);
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
      onTransform={(ref, { scale }) => {
        setZoomedIn(scale > 1.05);
        // The page behind darkens and the buttons fade as the card grows,
        // fully by 2x (see --zoom-fade in LargeView.css). Only when this
        // card's scale changes: the cards beside it, at normal size, are
        // also placed again when the phone turns, and would undo the fade.
        if (scale === lastScale.current) return;
        lastScale.current = scale;
        const fade = Math.min(Math.max(scale - 1, 0), 1);
        ref.instance.wrapperComponent
          ?.closest('dialog')
          ?.style.setProperty('--zoom-fade', String(fade));
      }}
    >
      {({ resetTransform }) => (
        <>
          <EaseNewSize turnedFrom={turnedFrom} turnBack={turnBack} />
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

/** A move of the card from its place: its scale, and how far its middle moves */
interface Move {
  scale: number;
  x: number;
  y: number;
}

/** No move: the card where it is */
const STILL: Move = { scale: 1, x: 0, y: 0 };

/** The same curve as CSS's ease-in-out, near enough, for t from 0 to 1 */
function easeInOut(t: number): number {
  return t < 0.5 ? 4 * t ** 3 : 1 - (2 - 2 * t) ** 3 / 2;
}

/**
 * Turning the phone gives the card its new size and place at once, as the
 * turn starts. But the phone draws the new page from the top left corner
 * of a frame that only gradually changes from the old screen's shape to
 * the new one as it rotates, so the card, in the middle of the new
 * screen, was drawn far from the middle of that frame, half off the
 * screen, and slid back as the turn ended. Instead, a copy of the card
 * is drawn at the card's old size and in the old screen's middle, and
 * eased to its new size and place over the turn, keeping the card in the
 * middle of the turning frame, as in a photo app. Only the drawing moves:
 * the layout, and the zoom library's sense of where the card is, are
 * already the new ones.
 *
 * The copy is in the page itself, above the dimmed page and below the
 * view. While the phone turns, it draws the view only inside the new
 * screen, and the card, still at its old size, was cut off at the new
 * screen's edge. The page is drawn in the whole turning frame. The card
 * itself is hidden until the copy is done, and stays where it is: eased
 * along with the copy while hidden, iOS drew it for a frame at the
 * easing's start as it showed it again. In the card list, the cards
 * beside it are hidden over the turn.
 *
 * The easing moves on frame by frame, by at most a frame's time each: as
 * it turns, the phone may draw no frames for a moment, and an easing by
 * the clock jumped ahead when the next frame came. A second change of
 * size during the easing, as the phone settles the screen's edges a
 * moment after its size, carries on from where the card is.
 *
 * A card printed sideways is turned a quarter in landscape (see
 * LargeView.css). Its copy starts at its old angle and turns to the new
 * one over the same time. Turned one way, the phone turns around the card,
 * which stays still; turned the other way, the card turns half around
 * with the screen, since it reads only one way up. Which way the phone
 * turned isn't known in time to do otherwise: iOS tells the page only
 * once its turn is over.
 *
 * A view that the turn itself opened (turnedFrom: a lesson's answer card
 * printed sideways, see CardPicture.tsx) eases the same way, from the
 * small card's place and size before the turn. Turned back upright, its
 * card eases back into that place on the page instead (turnBack), and the
 * view closes.
 */
function EaseNewSize({ turnedFrom, turnBack }: { turnedFrom?: TurnedFrom; turnBack?: TurnBack }) {
  // The library's two boxes, once it has set them up
  useTransformInit(({ instance }) => {
    const area = instance.wrapperComponent;
    const content = instance.contentComponent;
    if (area === null || content === null) return;
    // The card's own width, without its quarter turn: the box around a
    // card printed sideways is as wide as the card is long, in landscape
    const cardWidth = () => (content.firstElementChild as HTMLElement | null)?.offsetWidth ?? 0;
    const measure = () => ({
      width: cardWidth(),
      areaWidth: area.offsetWidth,
      areaHeight: area.offsetHeight,
    });
    // The card's and its area's sizes as drawn, which a turn starts from
    let { width, areaWidth, areaHeight } = measure();
    const take = (sizes: ReturnType<typeof measure>) => {
      ({ width, areaWidth, areaHeight } = sizes);
    };
    // A frame's request to take new sizes once they are drawn (see below)
    let settle = 0;
    // The copy's turn: from this many degrees from the card's angle after
    // the phone's turn, to 0, and how far along it is, in ms. It has a
    // clock of its own, so a second change of size during the easing,
    // which starts the other moves again from where they are, doesn't
    // start the turn again.
    let spinFrom = 0;
    let spun = 0;
    const angleAt = (time: number) => spinFrom * (1 - easeInOut(Math.min(time / EASE_TIME, 1)));
    // Whether a turn is being eased; during one, the copy's move, the
    // card's copy, and the next frame's request
    let turning = false;
    // Easing back into the page, to close (see turnBack)
    let goingBack = false;
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
      const sizes = measure();
      const landscape = sizes.areaWidth > sizes.areaHeight;
      // A turn: the area, the whole screen, changed from upright to
      // sideways or back. Not a window being resized, unless during a
      // turn's easing.
      const turned = before.areaWidth > before.areaHeight !== landscape;
      cancelAnimationFrame(settle);
      if (before.width > 0 && sizes.width > 0 && !turned && !turning) {
        // Not a turn: the new sizes count once drawn, from the next frame.
        // As an iPhone turns, the card may take its new size a step before
        // its area does, within one frame: the view follows the page's new
        // size a step after the page. The turn, seen at the second step,
        // must start from the card's size on the screen, not from the
        // first step's, which no frame showed: from that, the card shrank
        // at once as the turn began.
        settle = requestAnimationFrame(() => take(sizes));
        return;
      }
      take(sizes);
      // Laid out for the first time, as the view opens
      if (before.width === 0 && width > 0) startFromTurn();
      if (before.width === 0 || width === 0) return;
      // During the easing, the area alone may change: upright, the screen's
      // height can settle a moment after its width, leaving the card as
      // wide as before but its middle higher. The copy, aimed at the old
      // middle, landed too low and the card jumped up at the end.
      const resized =
        width !== before.width ||
        areaWidth !== before.areaWidth ||
        areaHeight !== before.areaHeight;
      if (!resized) return;
      // Turned back upright, in a view the turn opened: back into the page
      // underneath, then closed. Its place there is measured again on each
      // change of size, as the screen settles.
      const back = turnBack !== undefined && !landscape && (turned || goingBack);
      const target = back ? turnBack.place() : null;
      if (matchMedia('(prefers-reduced-motion: reduce)').matches || (back && target === null)) {
        if (back) turnBack.onDone();
        return;
      }
      if (back && !goingBack) {
        goingBack = true;
        turnBack.onStart();
      }
      // During an easing: from where the card is on screen, not from its
      // old size, place and angle. The copy shows it there.
      const style = copy === null ? null : getComputedStyle(copy);
      const shown = (style && parseFloat(style.scale)) || 1;
      const [x = 0, y = 0] =
        style === null || style.translate === 'none'
          ? []
          : style.translate.split(' ').map(parseFloat);
      const angle = turning ? angleAt(spun) : 0;
      // The quarter turn a card printed sideways has in landscape, which
      // its copy starts without, or with, to look as before
      const quarter = content.classList.contains('horizontal') ? (landscape ? -90 : 90) : 0;
      // The area was in the old screen's middle. The screen's top left
      // corner stays put.
      begin(
        {
          scale: (shown * before.width) / width,
          x: x + (before.areaWidth - areaWidth) / 2,
          y: y + (before.areaHeight - areaHeight) / 2,
        },
        turned ? angle + quarter : null,
        target,
      );
    });

    /**
     * Opened by turning the phone (see turnedFrom): the card eases from
     * where it was before the turn, at its size there and upright, as if
     * the view had been open all along. Once, when the card is first laid
     * out.
     */
    let startedFromTurn = false;
    const startFromTurn = () => {
      if (turnedFrom === undefined || startedFromTurn || width === 0) return;
      startedFromTurn = true;
      if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      const landscape = areaWidth > areaHeight;
      const quarter = content.classList.contains('horizontal') && landscape ? -90 : 0;
      // The area's middle, where the card is, moved onto the card's old middle
      begin(
        {
          scale: turnedFrom.width / width,
          x: turnedFrom.x - areaWidth / 2,
          y: turnedFrom.y - areaHeight / 2,
        },
        quarter,
      );
    };

    /**
     * Eases the card from `from` - the scale and move from its place now
     * that show it where it was - to its place now, or to `to` on the page
     * underneath. `spin`: the angle its copy starts at, from the card's
     * own; null carries on with the turn under way.
     */
    const begin = (from: Move, spin: number | null, to: TurnedFrom | null = null) => {
      stop();
      turning = true;
      if (spin !== null) {
        spinFrom = spin;
        spun = 0;
      }
      // The move that shows the card at its place now, or at `to`
      const goal = (target: TurnedFrom | null): Move =>
        target === null
          ? STILL
          : {
              scale: target.width / width,
              x: target.x - areaWidth / 2,
              y: target.y - areaHeight / 2,
            };
      // From where it was to there
      const movesTo = (target: TurnedFrom | null) =>
        [from, goal(target)].map((move) => ({
          scale: move.scale,
          translate: `${move.x}px ${move.y}px`,
        }));
      let aim = to;
      // The card's new place on the screen: the middle of its area, which
      // fills the screen from the top left corner once the card row is on
      // its card. Worked out rather than measured where it's drawn now. As
      // the phone turns, the row may be scrolled to another card for a
      // moment (see markShown in CardList.tsx), and the zoom library, which
      // centres the card with a move of its own, may not have caught up
      // with the new size yet: the copy was put far to the side.
      const card = {
        width: content.offsetWidth,
        height: content.offsetHeight,
        left: (areaWidth - content.offsetWidth) / 2,
        top: (areaHeight - content.offsetHeight) / 2,
      };
      const top = card.top + scrollY;
      const scrolled = scrollY;
      // In the card list's row, the card it's on (see markShown in
      // CardList.tsx), whatever its scroll position shows for the moment
      const row = area.closest<HTMLElement>('.card-row');
      const slide = area.closest('.card-slide');
      const inView =
        row === null ||
        slide === null ||
        [...row.children].indexOf(slide) === Number(row.dataset.shown);
      if (!inView) {
        // A card beside it is hidden over the turn. In the old layout it
        // was just past the old screen's edge, and the turning frame grows
        // past that edge: eased from there, the next card came into view.
        // Before and after the turn, it's off the screen anyway.
        area.style.visibility = 'hidden';
      } else {
        const moves = movesTo(aim);
        // Held at its end, which the last frame shows
        const timing: KeyframeAnimationOptions = {
          duration: EASE_TIME,
          easing: 'ease-in-out',
          fill: 'forwards',
        };
        // The copy, put in the page where the card is on the screen, makes
        // the move. The card is in the middle of its area, so the moves are
        // the area's middle's.
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
        document.body.append(copy);
        area.style.visibility = 'hidden';
        moving = [copy.animate(moves, timing)];
        // The close button and the card count have other spots upright and
        // sideways: hidden until the turn is done (see LargeView.css)
        view = area.closest('dialog');
        view?.classList.add('turning');
      }
      // The copy's angle
      const turnCopy = () => {
        if (copy !== null) copy.style.rotate = `${angleAt(spun)}deg`;
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
        spun = Math.min(spun + passed, EASE_TIME);
        // Easing back into the page: aimed at where the card there is now.
        // As the phone turns upright, the page has its new width first and
        // its new height a moment later, so the card there, small at
        // first, grows to its size: aimed at once, the copy shrank to the
        // small card, and the page's card then showed at its full size.
        if (aim !== null && turnBack !== undefined) {
          const now = turnBack.place();
          if (now !== null && (now.x !== aim.x || now.y !== aim.y || now.width !== aim.width)) {
            aim = now;
            for (const move of moving) (move.effect as KeyframeEffect).setKeyframes(movesTo(aim));
          }
        }
        for (const move of moving) move.currentTime = done;
        turnCopy();
        // If the page scrolls during the turn, the copy moves back by as
        // much, in the same frame
        if (copy !== null) copy.style.top = `${top + scrollY - scrolled}px`;
        if (done >= EASE_TIME && spun >= EASE_TIME) {
          // Back on the page: the copy stays there, exactly over the
          // page's card, until the view closes
          if (goingBack) turnBack?.onDone();
          else stop();
          return;
        }
        frame = requestAnimationFrame(step);
      };
      frame = requestAnimationFrame(step);
    };

    // Already laid out when the library set up: the view was open
    startFromTurn();
    observer.observe(content);
    observer.observe(area);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(settle);
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
