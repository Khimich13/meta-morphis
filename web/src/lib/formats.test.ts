import { expect, test } from 'vitest';

import { FIRST_FORMAT, startFormat } from './formats';

test('a saved choice is used', () => {
  expect(startFormat('modern', true)).toBe('modern');
  expect(startFormat('modern', false)).toBe('modern');
});

test('a player with progress from before formats existed gets Pauper', () => {
  expect(startFormat(null, true)).toBe(FIRST_FORMAT);
});

test('a new player chooses', () => {
  expect(startFormat(null, false)).toBeNull();
});
