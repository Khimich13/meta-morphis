import { expect, test } from 'vitest';

import { type Bounds, isZoomedIn, keepInside, MAX_SCALE, moveBy, NO_ZOOM, zoomAround } from './zoom';

// A card frame 300px wide and 420px tall, in the middle of a phone's screen
const B: Bounds = { left: 45, top: 212, width: 300, height: 420, screenWidth: 390, screenHeight: 844 };

test('zooming around a point keeps that point of the card under it', () => {
  const zoom = zoomAround(NO_ZOOM, 150, 200, 2.5, B);
  expect(zoom.scale).toBe(2.5);
  // The card's point (150, 200) is drawn at shift + point * scale
  expect(zoom.x + 150 * 2.5).toBeCloseTo(150);
  expect(zoom.y + 200 * 2.5).toBeCloseTo(200);
});

test('a card bigger than the screen covers it to its edges', () => {
  // Zoomed at the frame's top left corner: the card's corner moves to the
  // screen's corner instead of leaving a gap there
  expect(zoomAround(NO_ZOOM, 0, 0, 2.5, B)).toEqual({ scale: 2.5, x: -45, y: -212 });
  // Moved far: its far edges stop at the screen's far edges
  const far = moveBy({ scale: 2.5, x: -100, y: -300 }, -5000, -5000, B);
  expect(B.left + far.x + B.width * 2.5).toBeCloseTo(B.screenWidth);
  expect(B.top + far.y + B.height * 2.5).toBeCloseTo(B.screenHeight);
});

test('a card smaller than the screen stays wholly on it', () => {
  // 1.5 times: 450px wide, wider than the screen; 630px tall, shorter
  const zoom = moveBy({ scale: 1.5, x: 0, y: 0 }, 0, 5000, B);
  expect(B.top + zoom.y + B.height * 1.5).toBeCloseTo(B.screenHeight);
  expect(moveBy({ scale: 1.5, x: 0, y: 0 }, 0, -5000, B).y).toBeCloseTo(-B.top);
});

test('at normal size the card stays where it is', () => {
  expect(keepInside(NO_ZOOM, B)).toEqual(NO_ZOOM);
});

test('the scale stays between normal size and the most allowed', () => {
  expect(keepInside({ scale: 0.5, x: 0, y: 0 }, B).scale).toBe(1);
  expect(zoomAround(NO_ZOOM, 0, 0, 20, B).scale).toBe(MAX_SCALE);
});

test('a card pinched back to about normal size is no longer zoomed in', () => {
  expect(isZoomedIn(NO_ZOOM)).toBe(false);
  expect(isZoomedIn({ scale: 1.03, x: 0, y: 0 })).toBe(false);
  expect(isZoomedIn({ scale: 1.5, x: 0, y: 0 })).toBe(true);
});
