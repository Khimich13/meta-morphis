import { expect, test } from 'vitest';

import { columnsAfterPinch, mostColumns } from './pinch';

test('spreading the fingers makes fewer, bigger cards', () => {
  expect(columnsAfterPinch(2, 2, 4)).toBe(1);
  expect(columnsAfterPinch(4, 2, 4)).toBe(2);
  expect(columnsAfterPinch(2, 1.2, 4)).toBe(2); // not far enough yet
});

test('pinching the fingers together makes more, smaller cards', () => {
  expect(columnsAfterPinch(2, 0.5, 4)).toBe(4);
  expect(columnsAfterPinch(2, 0.7, 4)).toBe(3);
});

test('columns stay between one and as many as fit', () => {
  expect(columnsAfterPinch(1, 5, 4)).toBe(1);
  expect(columnsAfterPinch(2, 0.1, 4)).toBe(4);
});

test('mostColumns: up to six, each with 50px of room', () => {
  expect(mostColumns(358)).toBe(6); // a phone
  expect(mostColumns(1068)).toBe(6);
  expect(mostColumns(220)).toBe(4);
  expect(mostColumns(30)).toBe(1);
});
