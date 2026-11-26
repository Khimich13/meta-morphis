import { expect, test } from 'vitest';

import { type Card, halfArt, partName, partsOf, partType, shortDay, visibleName } from './cards';

test('shortDay writes the day without its year, the way of the language', () => {
  expect(shortDay('2026-11-19', 'en-US')).toBe('Nov 19');
  expect(shortDay('2027-01-01', 'en-US')).toBe('Jan 1');
  expect(shortDay('2026-11-19', 'en-GB')).toBe('19 Nov');
});

test('shortDay has no answer for a missing or broken day', () => {
  expect(shortDay(undefined)).toBeNull();
  expect(shortDay(null)).toBeNull();
  expect(shortDay('not a day')).toBeNull();
  expect(shortDay('2026-10-17T19:18:03Z')).toBeNull();
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
  expect(partName(split, 'first')).toBe('Wear');
  expect(partName(split, 'second')).toBe('Tear');
  expect(partName(split, 'main')).toBe('Wear // Tear');
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
  expect(partType(delver, 'back')).toBe('creature');
  expect(partType(azcanta, 'main')).toBe('enchantment');
  expect(partType(azcanta, 'back')).toBe('land');
  expect(partType(borrower, 'spell')).toBe('instant');
  expect(partType(borrower, 'main')).toBe('creature');
  expect(partType(room, 'second')).toBe('Room');
});

test('partType says card in files written before types were added', () => {
  const old: Card = {
    ...card('Wear // Tear', 1),
    halves: [
      { name: 'Wear', name_box: null },
      { name: 'Tear', name_box: null },
    ],
  };
  expect(partType(card('Lightning Bolt', 1), 'main')).toBe('card');
  expect(partType(old, 'first')).toBe('card');
});

test('partsOf lists the parts a question can ask about', () => {
  const back = { art: 'back.webp', artist: 'Some Artist', art_box: null };
  const spell = { name: 'Petty Theft', name_text_boxes: [] };
  const half = { name: 'Wear', name_box: null };
  expect(partsOf(card('Lightning Bolt', 1))).toEqual(['main']);
  expect(partsOf({ ...card('Delver', 2), back })).toEqual(['main', 'back']);
  expect(partsOf({ ...card('Borrower', 1), spell: { ...spell, name_box: [0, 0, 1, 1] } })).toEqual([
    'main',
    'spell',
  ]);
  // A spell whose name can't be covered is never asked about
  expect(partsOf({ ...card('Borrower', 1), spell: { ...spell, name_box: null } })).toEqual([
    'main',
  ]);
  expect(partsOf({ ...card('Wear // Tear', 1), halves: [half, half] })).toEqual([
    'first',
    'second',
  ]);
});
