// The large view's own zoom: a double tap enlarges the card around the
// spot tapped, one finger then moves around it, and a pinch makes it
// bigger or smaller. The browser's zoom is off everywhere (see pinch.ts),
// so only the card grows, never the page.
//
// A zoom is a scale and a shift of the card's picture, from its top left
// corner: a point p of the card is drawn at shift + p * scale.

import { type PointerEvent, useEffect, useRef, useState } from 'react';

export interface Zoom {
  scale: number;
  x: number;
  y: number;
}

export const NO_ZOOM: Zoom = { scale: 1, x: 0, y: 0 };

/** How much a double tap enlarges the card */
export const TAP_SCALE = 2.5;
/** The most a pinch can enlarge it */
export const MAX_SCALE = 5;

/**
 * Where the card's frame is on the screen, and the screen's size. The
 * zoomed card may spread over the whole screen, not just its frame.
 */
export interface Bounds {
  left: number;
  top: number;
  width: number;
  height: number;
  screenWidth: number;
  screenHeight: number;
}

/**
 * Keeps the zoomed card in view: while it is bigger than the screen, its
 * edges never come inside the screen's edges, which would show a gap;
 * while it is smaller, it stays wholly on the screen.
 */
export function keepInside(zoom: Zoom, bounds: Bounds): Zoom {
  const scale = Math.min(Math.max(zoom.scale, 1), MAX_SCALE);
  // The shifts that put the card's near edge at the screen's near edge,
  // and its far edge at the screen's far edge: the card stays between
  const clamp = (shift: number, start: number, size: number, screen: number) => {
    const nearEdge = -start;
    const farEdge = screen - start - size * scale;
    return Math.min(Math.max(shift, Math.min(nearEdge, farEdge)), Math.max(nearEdge, farEdge));
  };
  return {
    scale,
    x: clamp(zoom.x, bounds.left, bounds.width, bounds.screenWidth),
    y: clamp(zoom.y, bounds.top, bounds.height, bounds.screenHeight),
  };
}

/**
 * The zoom at `scale`, keeping the part of the card now under the point
 * (x, y) - measured from the frame's top left corner - under it
 */
export function zoomAround(zoom: Zoom, x: number, y: number, scale: number, bounds: Bounds): Zoom {
  // The spot on the card, in the card's own unzoomed size, under the point
  const spotX = (x - zoom.x) / zoom.scale;
  const spotY = (y - zoom.y) / zoom.scale;
  const next = Math.min(Math.max(scale, 1), MAX_SCALE);
  return keepInside({ scale: next, x: x - spotX * next, y: y - spotY * next }, bounds);
}

/** The zoom moved by a finger's movement */
export function moveBy(zoom: Zoom, dx: number, dy: number, bounds: Bounds): Zoom {
  return keepInside({ ...zoom, x: zoom.x + dx, y: zoom.y + dy }, bounds);
}

/** Below this the card counts as back to its normal size */
export function isZoomedIn(zoom: Zoom): boolean {
  return zoom.scale > 1.05;
}

/** Two taps this close in time (milliseconds) and place (pixels) make a double tap */
export const DOUBLE_TAP_TIME = 300;
export const DOUBLE_TAP_DISTANCE = 40;

interface Point {
  x: number;
  y: number;
}

const distanceBetween = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);
const middleOf = (a: Point, b: Point) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });

/**
 * The large view's zoom for one card. Spread `handlers` on the element
 * that holds the card (its frame, which stays put) and apply `zoom` to
 * the element inside it. `moving` is true while a finger moves it, when
 * the zoom must follow without the smooth transition of a double tap.
 * `onZoomedChange` hears when the card is zoomed in and back out.
 */
export function useCardZoom(onZoomedChange: (zoomed: boolean) => void) {
  const [zoom, setZoom] = useState(NO_ZOOM);
  const [moving, setMoving] = useState(false);
  // The fingers (or mouse) on the card, where each is now
  const pointers = useRef(new Map<number, Point>());
  // When and where the last finger went down, and the last tap
  const pressed = useRef<{ time: number; at: Point } | null>(null);
  const lastTap = useRef<{ time: number; at: Point } | null>(null);

  const zoomedIn = isZoomedIn(zoom);
  useEffect(() => {
    onZoomedChange(zoomedIn);
    // Closing the view or leaving the card ends its zoom
    return () => {
      if (zoomedIn) onZoomedChange(false);
    };
  }, [zoomedIn, onZoomedChange]);

  /** Where the event is, from the frame's top left corner, and the bounds */
  function place(event: PointerEvent<HTMLElement>) {
    const frame = event.currentTarget.getBoundingClientRect();
    const bounds: Bounds = {
      left: frame.left,
      top: frame.top,
      width: frame.width,
      height: frame.height,
      screenWidth: window.innerWidth,
      screenHeight: window.innerHeight,
    };
    return { at: { x: event.clientX - frame.left, y: event.clientY - frame.top }, bounds };
  }

  function onPointerDown(event: PointerEvent<HTMLElement>) {
    // The flip and speaker buttons work as usual
    if (event.target instanceof Element && event.target.closest('button')) return;
    const { at } = place(event);
    pointers.current.set(event.pointerId, at);
    // Keep hearing this finger even when it leaves the card
    event.currentTarget.setPointerCapture(event.pointerId);
    pressed.current = pointers.current.size === 1 ? { time: event.timeStamp, at } : null;
  }

  function onPointerMove(event: PointerEvent<HTMLElement>) {
    const before = pointers.current.get(event.pointerId);
    if (before === undefined || !zoomedIn) return;
    const { at, bounds } = place(event);
    const others = [...pointers.current].filter(([id]) => id !== event.pointerId);
    pointers.current.set(event.pointerId, at);
    setMoving(true);
    if (others.length === 0) {
      // One finger: move around the card
      setZoom((zoom) => moveBy(zoom, at.x - before.x, at.y - before.y, bounds));
    } else {
      // Two fingers: bigger or smaller as they spread or close, around
      // the point between them, which also moves with them
      const other = others[0][1];
      const spread = distanceBetween(at, other) / distanceBetween(before, other);
      const middleBefore = middleOf(before, other);
      const middle = middleOf(at, other);
      setZoom((zoom) => {
        const scaled = zoomAround(
          zoom,
          middleBefore.x,
          middleBefore.y,
          zoom.scale * spread,
          bounds,
        );
        return moveBy(scaled, middle.x - middleBefore.x, middle.y - middleBefore.y, bounds);
      });
    }
  }

  function onPointerUp(event: PointerEvent<HTMLElement>) {
    if (!pointers.current.delete(event.pointerId)) return;
    if (pointers.current.size > 0) return;
    setMoving(false);
    // Pinched back to about normal size: out of zoom
    setZoom((zoom) => (isZoomedIn(zoom) ? zoom : NO_ZOOM));

    // A tap: down and up quickly, in about the same place
    const { at, bounds } = place(event);
    const down = pressed.current;
    pressed.current = null;
    const isTap =
      down !== null && event.timeStamp - down.time < 250 && distanceBetween(at, down.at) < 10;
    if (!isTap) return;
    const previous = lastTap.current;
    const isDouble =
      previous !== null &&
      event.timeStamp - previous.time < DOUBLE_TAP_TIME &&
      distanceBetween(at, previous.at) < DOUBLE_TAP_DISTANCE;
    lastTap.current = isDouble ? null : { time: event.timeStamp, at };
    if (isDouble) {
      setZoom((zoom) =>
        isZoomedIn(zoom) ? NO_ZOOM : zoomAround(zoom, at.x, at.y, TAP_SCALE, bounds),
      );
    }
  }

  return {
    zoom,
    moving,
    handlers: {
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onPointerCancel: onPointerUp,
    },
  };
}
