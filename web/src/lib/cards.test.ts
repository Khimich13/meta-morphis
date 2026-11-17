import { expect, test } from 'vitest';

import { type Card, halfArt, listAgeDays, partName, visibleName } from './cards';

const NOW = new Date('2026-10-20T12:00:00Z');

test('listAgeDays counts whole days since the list was fetched', () => {
  expect(listAgeDays('2026-10-20T08:00:00Z', NOW)).toBe(0);
  expect(listAgeDays('2026-10-19T12:00:00Z', NOW)).toBe(1);
  expect(listAgeDays('2026-10-17T13:00:00Z', NOW)).toBe(2);
  expect(listAgeDays('2026-10-15T19:17:00Z', NOW)).toBe(4);
});

test('listAgeDays has no answer for a missing or broken date', () => {
  expect(listAgeDays(undefined, NOW)).toBeNull();
  expect(listAgeDays('not a date', NOW)).toBeNull();
});

function card(name: string, sides: number): Card {
  return {
    oracle_id: name,
    name,
    images: Array.from({ length: sides }, (_, i) => `${i}.webp`),
    art: 'art.webp',
    artist: 'Some Artist',
  };
}

test('visibleName gives the face being looked at on a double-faced card', () => {
  const fable = card('Fable of the Mirror-Breaker // Reflection of Kiki-Jiki', 2);
  expect(visibleName(fable, false)).toBe('Fable of the Mirror-Breaker');
  expect(visibleName(fable, true)).toBe('Reflection of Kiki-Jiki');
});

test('visibleName keeps the full name of single-sided and split cards', () => {
  expect(visibleName(card('Lightning Bolt', 1), false)).toBe('Lightning Bolt');
  // Both halves of a split card are printed on its one side
  const room = card('Unholy Annex // Ritual Chamber', 1);
  expect(visibleName(room, false)).toBe('Unholy Annex // Ritual Chamber');
});

test("halfArt cuts either half of a split card's artwork, the same each time", () => {
  const split = card('Wear // Tear', 1);
  expect(halfArt(split, 0).art_from).toEqual({ picture: 'art.webp', box: [0, 0, 0.5, 1] });
  expect(halfArt(split, 1).art_from).toEqual({ picture: 'art.webp', box: [0.5, 0, 0.5, 1] });
  expect(halfArt(split, 1)).toBe(halfArt(split, 1));
});

test('partName names a split card by the half asked', () => {
  const split: Card = {
    ...card('Wear // Tear', 1),
    halves: [
      { name: 'Wear', name_box: null },
      { name: 'Tear', name_box: null },
    ],
  };
  expect(partName(split, false, false, 0)).toBe('Wear');
  expect(partName(split, false, false, 1)).toBe('Tear');
  expect(partName(split, false, false)).toBe('Wear // Tear');
});
