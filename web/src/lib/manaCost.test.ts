import { expect, test } from 'vitest';

import { nearCosts, symbols, symbolUrl } from './manaCost';

test('a cost is read symbol by symbol', () => {
  expect(symbols('{X}{1}{U}')).toEqual(['X', '1', 'U']);
  expect(symbols('{3}{R/G}{R/G}')).toEqual(['3', 'R/G', 'R/G']);
  expect(symbols('')).toEqual([]);
});

test("a symbol's picture is named without its slashes", () => {
  expect(symbolUrl('U')).toBe('https://svgs.scryfall.io/card-symbols/U.svg');
  expect(symbolUrl('B/P')).toBe('https://svgs.scryfall.io/card-symbols/BP.svg');
  expect(symbolUrl('W/U/P')).toBe('https://svgs.scryfall.io/card-symbols/WUP.svg');
});

test('near costs are one change away when that gives enough', () => {
  expect(nearCosts('{1}{U}', 3)).toEqual([['{2}{U}', '{U}', '{1}{U}{U}', '{U}{U}']]);
  expect(nearCosts('{1}{W}{U}', 3)).toEqual([
    ['{2}{W}{U}', '{W}{U}', '{1}{W}{W}{U}', '{W}{W}{U}', '{1}{W}{U}{U}', '{W}{U}{U}'],
  ]);
});

test('near costs keep every kind of symbol the cost has', () => {
  // The frame shows green: {1} alone would be plain to rule out
  const [first, second] = nearCosts('{G}', 3);
  expect(first).toEqual(['{1}{G}', '{G}{G}']);
  expect(second).toEqual(['{2}{G}', '{1}{G}{G}', '{G}{G}{G}']);
  for (const cost of [...first, ...second]) expect(cost).toContain('{G}');
});

test('X is added or taken away, never swapped for generic mana', () => {
  expect(nearCosts('{X}{X}{R}', 3)).toEqual([
    ['{X}{X}{1}{R}', '{X}{X}{X}{R}', '{X}{R}', '{X}{X}{R}{R}'],
  ]);
});

test('a cost of nothing but generic mana goes up and down', () => {
  expect(nearCosts('{0}', 3)).toEqual([['{1}'], ['{2}'], ['{3}']]);
  expect(nearCosts('{3}', 3)).toEqual([
    ['{4}', '{2}'],
    ['{5}', '{1}'],
  ]);
});

test('hybrid and Phyrexian symbols are kinds of their own', () => {
  expect(nearCosts('{1}{B/P}{B/P}', 3)[0]).toEqual([
    '{2}{B/P}{B/P}',
    '{B/P}{B/P}',
    '{1}{B/P}{B/P}{B/P}',
    '{1}{B/P}',
    '{2}{B/P}',
    '{B/P}{B/P}{B/P}',
  ]);
});
