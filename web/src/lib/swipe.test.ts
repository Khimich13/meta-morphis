import { expect, test } from 'vitest';

import { step, swipeDirection } from './swipe';

test('swiping left brings the next card, right the previous one', () => {
  expect(swipeDirection(-80, 10)).toBe('next');
  expect(swipeDirection(80, -10)).toBe('previous');
});

test('a tap or a short movement is not a swipe', () => {
  expect(swipeDirection(0, 0)).toBeNull();
  expect(swipeDirection(-30, 0)).toBeNull();
});

test('a mostly vertical movement is not a swipe', () => {
  expect(swipeDirection(-60, 90)).toBeNull();
});

test('moving stops at both ends of the list', () => {
  expect(step(0, 'next', 3)).toBe(1);
  expect(step(2, 'next', 3)).toBe(2);
  expect(step(1, 'previous', 3)).toBe(0);
  expect(step(0, 'previous', 3)).toBe(0);
});
