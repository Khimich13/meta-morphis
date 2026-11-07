import { expect, test } from 'vitest';

import { columnsAfterPinch, fewestColumns, mostColumns } from './pinch';

test('spreading the fingers makes fewer, bigger cards', () => {
  expect(columnsAfterPinch(2, 2, 1, 4)).toBe(1);
  expect(columnsAfterPinch(4, 2, 1, 4)).toBe(2);
  expect(columnsAfterPinch(2, 1.2, 1, 4)).toBe(2); // not far enough yet
});

test('pinching the fingers together makes more, smaller cards', () => {
  expect(columnsAfterPinch(2, 0.5, 1, 4)).toBe(4);
  expect(columnsAfterPinch(2, 0.7, 1, 4)).toBe(3);
});

test('columns stay between the fewest and as many as fit', () => {
  expect(columnsAfterPinch(1, 5, 1, 4)).toBe(1);
  expect(columnsAfterPinch(2, 0.1, 1, 4)).toBe(4);
  expect(columnsAfterPinch(4, 4, 3, 6)).toBe(3); // a phone turned sideways
});

test('mostColumns: up to six, each with 50px of room', () => {
  expect(mostColumns(358)).toBe(6); // a phone
  expect(mostColumns(1068)).toBe(6);
  expect(mostColumns(220)).toBe(4);
  expect(mostColumns(30)).toBe(1);
});

test('fewestColumns: as few as still fit a whole card on the screen', () => {
  // A phone upright: one card per row, 358px wide and 499px tall, fits
  expect(fewestColumns(358, 797)).toBe(1);
  // Turned sideways: one or two per row are taller than the 390px screen
  expect(fewestColumns(718, 390)).toBe(3);
  // A computer: one card per row, at most 480px wide, fits
  expect(fewestColumns(1200, 800)).toBe(1);
  // A screen too low for even the smallest cards: as many as fit
  expect(fewestColumns(358, 50)).toBe(6);
});
