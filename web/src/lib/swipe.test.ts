import { expect, test } from 'vitest';

import { step } from './swipe';

test('moving stops at both ends of the list', () => {
  expect(step(0, 'next', 3)).toBe(1);
  expect(step(2, 'next', 3)).toBe(2);
  expect(step(1, 'previous', 3)).toBe(0);
  expect(step(0, 'previous', 3)).toBe(0);
});
