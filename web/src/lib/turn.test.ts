import { expect, test } from 'vitest';

import { GLIDE_TIME, glides, glideStep } from './turn';

test('an upright card glides to its new size', () => {
  expect(glides({ width: 358, turned: false }, { width: 262, turned: false })).toBe(true);
});

test('a card printed sideways does not glide when it turns', () => {
  const sideways = { width: 358, turned: false };
  const turned = { width: 510, turned: true };
  expect(glides(sideways, turned)).toBe(false);
  expect(glides(turned, sideways)).toBe(false);
});

test('a card with no size yet does not glide', () => {
  expect(glides({ width: 300, turned: false }, { width: 0, turned: false })).toBe(false);
});

test('the glide covers about two thirds of the way in GLIDE_TIME', () => {
  const after = glideStep(358, 262, GLIDE_TIME);
  expect((358 - after) / (358 - 262)).toBeCloseTo(1 - Math.exp(-1));
});

test('the glide takes the same time at any frame rate', () => {
  // 60 frames a second against 120, over the same 100ms
  let slow = 358;
  for (let i = 0; i < 6; i++) slow = glideStep(slow, 262, 100 / 6);
  let fast = 358;
  for (let i = 0; i < 12; i++) fast = glideStep(fast, 262, 100 / 12);
  expect(fast).toBeCloseTo(slow);
});

test('a frame with no time passed stays put', () => {
  expect(glideStep(300, 200, 0)).toBe(300);
  expect(glideStep(300, 200, -5)).toBe(300);
});
