import { expect, test } from 'vitest';

import { type Card, halfArt, listAgeDays, partName, partType, visibleName } from './cards';

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

test('partType gives the type of the part asked about', () => {
  const delver: Card = {
    ...card('Delver of Secrets // Insectile Aberration', 2),
    type: 'creature',
    back: { art: 'back.webp', artist: 'Some Artist', art_box: null, type: 'creature' },
  };
  const azcanta: Card = {
    ...card('Search for Azcanta // Azcanta, the Sunken Ruin', 2),
    type: 'enchantment',
    back: { art: 'back.webp', artist: 'Some Artist', art_box: null, type: 'land' },
  };
  const borrower: Card = {
    ...card('Brazen Borrower // Petty Theft', 1),
    type: 'creature',
    spell: { name: 'Petty Theft', name_box: null, name_text_boxes: [], type: 'instant' },
  };
  const room: Card = {
    ...card('Unholy Annex // Ritual Chamber', 1),
    type: 'enchantment',
    halves: [
      { name: 'Unholy Annex', name_box: null, type: 'Room' },
      { name: 'Ritual Chamber', name_box: null, type: 'Room' },
    ],
  };
  expect(partType(delver, true, false)).toBe('creature');
  expect(partType(azcanta, false, false)).toBe('enchantment');
  expect(partType(azcanta, true, false)).toBe('land');
  expect(partType(borrower, false, true)).toBe('instant');
  expect(partType(borrower, false, false)).toBe('creature');
  expect(partType(room, false, false, 1)).toBe('Room');
});

test('partType says card in files written before types were added', () => {
  const old: Card = {
    ...card('Wear // Tear', 1),
    halves: [
      { name: 'Wear', name_box: null },
      { name: 'Tear', name_box: null },
    ],
  };
  expect(partType(card('Lightning Bolt', 1), false, false)).toBe('card');
  expect(partType(old, false, false, 0)).toBe('card');
});
