import { expect, test } from 'vitest';

import { type Card, listAgeDays, visibleName } from './cards';

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
