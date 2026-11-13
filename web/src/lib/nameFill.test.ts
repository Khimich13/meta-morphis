import { expect, test } from 'vitest';

import { fillName } from './nameFill';

/**
 * An area with what surrounds it, as RGBA, from gray levels by row: the
 * first and last rows are just above and below the area, and the first
 * and last `reach` columns are to its left and right
 */
function around(rows: number[][]): Uint8ClampedArray {
  return new Uint8ClampedArray(rows.flat().flatMap((gray) => [gray, gray, gray, 255]));
}

/** The gray level of each filled pixel, row by row */
function grays(pixels: Uint8ClampedArray, width: number): number[][] {
  const rows: number[][] = [];
  for (let at = 0; at < pixels.length; at += width * 4) {
    rows.push(Array.from({ length: width }, (_, x) => pixels[at + x * 4]));
  }
  return rows;
}

// Random numbers that make every bit of grain 0: a quarter turn in gaussian()
const NO_GRAIN = () => 0.25;

test('a plain bar is filled with its own color, opaque', () => {
  const plain = around(Array.from({ length: 4 }, () => Array(11).fill(120)));
  const pixels = fillName(plain, 11, 3, NO_GRAIN);
  expect(grays(pixels, 5)).toEqual([Array(5).fill(120), Array(5).fill(120)]);
  expect(pixels.filter((_, i) => i % 4 === 3).every((alpha) => alpha === 255)).toBe(true);
});

test('the fill follows shading from top to bottom, meeting each edge', () => {
  // Dark above, light below, and the sides shaded the same way between
  const shaded = around([
    Array(11).fill(0),
    Array(11).fill(100),
    Array(11).fill(200),
    Array(11).fill(255),
  ]);
  const pixels = grays(fillName(shaded, 11, 3, NO_GRAIN), 5);
  expect(pixels).toEqual([Array(5).fill(100), Array(5).fill(200)]);
});

test("a letter's tail touching the row above is left out", () => {
  const bar = Array.from({ length: 4 }, () => Array(11).fill(200));
  // A dark pixel just above the middle of the area
  bar[0][5] = 20;
  const pixels = grays(fillName(around(bar), 11, 3, NO_GRAIN), 5);
  expect(pixels.flat().every((gray) => gray === 200)).toBe(true);
});

test('the fill has the grain of the bar around it', () => {
  // Rows above and below that alternate light and dark pixels
  const grainy = Array.from({ length: 6 }, () => Array(31).fill(128));
  grainy[0] = grainy[0].map((_, x) => (x % 2 === 0 ? 108 : 148));
  grainy[5] = grainy[5].map((_, x) => (x % 2 === 0 ? 108 : 148));
  const plainEdges = grainy.map((row, y) => (y === 0 || y === 5 ? Array(31).fill(128) : row));
  const spread = (pixels: number[]) => Math.max(...pixels) - Math.min(...pixels);
  const withGrain = grays(fillName(around(grainy), 31, 3), 25).flat();
  const without = grays(fillName(around(plainEdges), 31, 3), 25).flat();
  expect(spread(without)).toBe(0);
  expect(spread(withGrain)).toBeGreaterThan(10);
});

test('print next to the area is not taken for grain', () => {
  // A plain bar, with dark letters in the rows above and below
  const printed = Array.from({ length: 6 }, () => Array(31).fill(200));
  printed[0] = printed[0].map((gray, x) => (x % 5 === 0 ? 30 : gray));
  printed[5] = printed[5].map((gray, x) => (x % 7 === 0 ? 30 : gray));
  const pixels = grays(fillName(around(printed), 31, 3), 25).flat();
  expect(pixels.every((gray) => gray === 200)).toBe(true);
});
