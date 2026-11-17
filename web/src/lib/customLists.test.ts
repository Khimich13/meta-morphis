import { expect, test } from 'vitest';

import { type Card } from './cards';
import {
  addCards,
  cardNamesFrom,
  cardsByName,
  DEFAULT_LIST_NAME,
  nameKey,
  newList,
  removeCard,
} from './customLists';

/** A card with only what matching names looks at */
function card(name: string, extra: Partial<Card> = {}): Card {
  return { oracle_id: name, name, images: [], art: '', artist: '', ...extra };
}

test('a single name is one card', () => {
  expect(cardNamesFrom('Lightning Bolt')).toEqual(['Lightning Bolt']);
});

test("a decklist's counts, set codes and headings are left out", () => {
  const text = [
    'Deck',
    '4 Lightning Bolt (M10) 146',
    '2x Counterspell',
    '',
    'Sideboard',
    '1 Pyroblast (ICE) 212 *F*',
    'Creatures:',
  ].join('\n');
  expect(cardNamesFrom(text)).toEqual(['Lightning Bolt', 'Counterspell', 'Pyroblast']);
});

test('a name entered twice is kept once', () => {
  expect(cardNamesFrom('4 Counterspell\n2 counterspell')).toEqual(['Counterspell']);
});

test('names compare without case, accents, curly apostrophes or spacing', () => {
  expect(nameKey('Lórien  Revealed')).toBe(nameKey('lorien revealed'));
  expect(nameKey('Urza’s Saga')).toBe(nameKey("Urza's Saga"));
  expect(nameKey('Wear/Tear')).toBe(nameKey('Wear // Tear'));
});

test('a card is found by its full name or by either half', () => {
  const borrower = card('Brazen Borrower // Petty Theft');
  const byName = cardsByName([borrower]);
  expect(byName.get(nameKey('Brazen Borrower // Petty Theft'))).toBe(borrower);
  expect(byName.get(nameKey('brazen borrower'))).toBe(borrower);
  expect(byName.get(nameKey('Petty Theft'))).toBe(borrower);
});

test("a card's full name wins over another card's half", () => {
  const fire = card('Fire');
  const split = card('Fire // Ice');
  expect(cardsByName([split, fire]).get(nameKey('Fire'))).toBe(fire);
});

test('adding sorts the names into added, already there and unknown', () => {
  const bolt = card('Lightning Bolt');
  const spell = card('Counterspell');
  const known = cardsByName([bolt, spell]);
  const list = { ...newList('Burn'), cards: [bolt] };
  const result = addCards(list, ['Counterspell', 'lightning bolt', 'Pyroblast'], known);
  expect(result.list.cards).toEqual([bolt, spell]);
  expect(result.added).toEqual(['Counterspell']);
  expect(result.already).toEqual(['lightning bolt']);
  expect(result.unknown).toEqual(['Pyroblast']);
  // The list it was given stays as it was
  expect(list.cards).toEqual([bolt]);
});

test("adding refreshes the list's cards from the newer card files", () => {
  const old = card('Lightning Bolt', { art: 'old.jpg' });
  const fresh = card('Lightning Bolt', { art: 'new.jpg' });
  const result = addCards({ ...newList('Burn'), cards: [old] }, [], cardsByName([fresh]));
  expect(result.list.cards).toEqual([fresh]);
});

test('a card no file has any more stays in the list', () => {
  const gone = card('Mishra’s Bauble');
  const result = addCards({ ...newList('Burn'), cards: [gone] }, [], cardsByName([]));
  expect(result.list.cards).toEqual([gone]);
});

test('a new list without a name gets the default one', () => {
  expect(newList('  ').name).toBe(DEFAULT_LIST_NAME);
  expect(newList(' Burn ').name).toBe('Burn');
  expect(newList('a').id).not.toBe(newList('a').id);
});

test('removing a card leaves the others in their order', () => {
  const [a, b, c] = [card('A'), card('B'), card('C')];
  const list = { ...newList('Burn'), cards: [a, b, c] };
  expect(removeCard(list, 'B').cards).toEqual([a, c]);
  expect(list.cards).toEqual([a, b, c]);
});
