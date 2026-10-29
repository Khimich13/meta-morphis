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
export const TAP_SCALE = 2;
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

/** The CSS transform that draws a zoom */
export function transformOf(zoom: Zoom): string {
  return `translate(${zoom.x}px, ${zoom.y}px) scale(${zoom.scale})`;
}

/**
 * The large view's zoom for one card. Spread `handlers` on the element
 * that holds the card (its frame, which stays put) and put `contentRef`
 * on the element inside it, which the zoom grows and moves.
 * `onZoomedChange` hears when the card is zoomed in and back out.
 *
 * A finger moves the card many times a second, so the zoom is written
 * straight onto the element, at most once per frame the screen draws,
 * rather than redrawn by React each time. Only whether the card is
 * zoomed in at all goes through React.
 */
export function useCardZoom(onZoomedChange: (zoomed: boolean) => void) {
  const [zoomedIn, setZoomedIn] = useState(false);
  const zoom = useRef(NO_ZOOM);
  const contentRef = useRef<HTMLDivElement>(null);
  // The frame waiting to draw the latest zoom, if any
  const pendingFrame = useRef(0);
  // The fingers (or mouse) on the card, where each is now
  const pointers = useRef(new Map<number, Point>());
  // When and where the last finger went down, and the last tap
  const pressed = useRef<{ time: number; at: Point } | null>(null);
  const lastTap = useRef<{ time: number; at: Point } | null>(null);

  useEffect(() => {
    onZoomedChange(zoomedIn);
    // Closing the view or leaving the card ends its zoom
    return () => {
      if (zoomedIn) onZoomedChange(false);
    };
  }, [zoomedIn, onZoomedChange]);

  // A frame still waiting when the card goes away is not needed
  useEffect(() => () => cancelAnimationFrame(pendingFrame.current), []);

  /**
   * Shows a new zoom: with a short smooth transition (a double tap, or
   * letting go), or at once on the next frame (under a moving finger)
   */
  function show(next: Zoom, smoothly: boolean) {
    zoom.current = next;
    setZoomedIn(isZoomedIn(next));
    const element = contentRef.current;
    if (element === null) return;
    if (smoothly) {
      cancelAnimationFrame(pendingFrame.current);
      pendingFrame.current = 0;
      element.style.transition = '';
      element.style.transform = transformOf(next);
    } else if (pendingFrame.current === 0) {
      element.style.transition = 'none';
      pendingFrame.current = requestAnimationFrame(() => {
        pendingFrame.current = 0;
        element.style.transform = transformOf(zoom.current);
      });
    }
  }

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
    if (before === undefined || !isZoomedIn(zoom.current)) return;
    const { at, bounds } = place(event);
    const others = [...pointers.current].filter(([id]) => id !== event.pointerId);
    pointers.current.set(event.pointerId, at);
    if (others.length === 0) {
      // One finger: move around the card
      show(moveBy(zoom.current, at.x - before.x, at.y - before.y, bounds), false);
      return;
    }
    // Two fingers: bigger or smaller as they spread or close, around the
    // point between them, which also moves with them
    const other = others[0][1];
    const spread = distanceBetween(at, other) / distanceBetween(before, other);
    const middleBefore = middleOf(before, other);
    const middle = middleOf(at, other);
    const scaled = zoomAround(
      zoom.current,
      middleBefore.x,
      middleBefore.y,
      zoom.current.scale * spread,
      bounds,
    );
    show(moveBy(scaled, middle.x - middleBefore.x, middle.y - middleBefore.y, bounds), false);
  }

  function onPointerUp(event: PointerEvent<HTMLElement>) {
    if (!pointers.current.delete(event.pointerId)) return;
    if (pointers.current.size > 0) return;
    // Pinched back to about normal size: out of zoom
    if (!isZoomedIn(zoom.current) && zoom.current !== NO_ZOOM) show(NO_ZOOM, true);

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
      show(
        isZoomedIn(zoom.current)
          ? NO_ZOOM
          : zoomAround(zoom.current, at.x, at.y, TAP_SCALE, bounds),
        true,
      );
    }
  }

  return {
    contentRef,
    zoomedIn,
    handlers: {
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onPointerCancel: onPointerUp,
    },
  };
}

/**
 * The card's large pictures, once the player has zoomed in and they have
 * downloaded; null until then, while the normal ones show. They download
 * and are made ready to draw in the background, so swapping them in shows
 * no gap. Offline, or without large pictures, the normal ones stay.
 */
export function useLargePictures(
  large: string[] | undefined,
  zoomedIn: boolean,
): string[] | null {
  const [ready, setReady] = useState<string[] | null>(null);
  useEffect(() => {
    if (!zoomedIn || ready !== null || large === undefined || large.length === 0) return;
    let stopped = false;
    Promise.all(
      large.map((url) => {
        const picture = new Image();
        // The same way the card's <img> asks, so it finds this download
        picture.crossOrigin = 'anonymous';
        picture.src = url;
        return picture.decode();
      }),
    )
      .then(() => {
        if (!stopped) setReady(large);
      })
      .catch(() => {
        // No connection, or the picture is gone: the normal ones stay
      });
    return () => {
      stopped = true;
    };
  }, [zoomedIn, large, ready]);
  return ready;
}
