import { expect, test } from 'vitest';

import { topCard } from './topCard';

/**
 * Stand-ins for the list's cards, two per row, 100px tall, with the page
 * scrolled down by `scrolled` px; each counts how often it is measured
 */
function cards(count: number, scrolled: number) {
  let measured = 0;
  const list = Array.from({ length: count }, (_, position) => {
    const row = Math.floor(position / 2);
    return {
      position,
      getBoundingClientRect: () => {
        measured += 1;
        return { bottom: (row + 1) * 100 - scrolled } as DOMRect;
      },
    } as unknown as Element & { position: number };
  });
  return { list, measured: () => measured };
}

test('finds the first card of the row at the top of the screen', () => {
  // Rows 0-4 are above the screen; row 5 (cards 10 and 11) is partly in view
  expect(topCard(cards(50, 550).list)?.position).toBe(10);
});

test('a row just above the screen is not the top one', () => {
  // Row 2 ends exactly at the top of the screen
  expect(topCard(cards(50, 300).list)?.position).toBe(6);
});

test('the first card at the top of the page', () => {
  expect(topCard(cards(50, 0).list)?.position).toBe(0);
});

test('none when every card is above the screen, or there are no cards', () => {
  expect(topCard(cards(50, 5000).list)).toBeNull();
  expect(topCard([])).toBeNull();
});

test('a long list takes only a few measurements', () => {
  const long = cards(500, 20_000);
  expect(topCard(long.list)?.position).toBe(400);
  expect(long.measured()).toBeLessThanOrEqual(10);
});
