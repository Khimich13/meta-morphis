import { expect, test } from 'vitest';

import { enlargedWidth, isWorthEnlarging } from './enlarge';

test('the large view is limited by width on a phone, by height on a computer', () => {
  // A phone: 375 wide, 667 tall - the width runs out first
  expect(enlargedWidth(375, 667)).toBe(343);
  // A computer window: 1440 wide, 900 tall - the height runs out first
  expect(enlargedWidth(1440, 900)).toBeCloseTo(594, 0);
});

test('a card that already fills a phone is not worth enlarging', () => {
  // The answer screen on a phone shows the card 343px wide
  expect(isWorthEnlarging(343, 375, 667)).toBe(false);
  // Slightly smaller still isn't 15% gained
  expect(isWorthEnlarging(310, 375, 667)).toBe(false);
});

test('small cards are worth enlarging', () => {
  // The card list on a phone: about 150px wide
  expect(isWorthEnlarging(150, 375, 667)).toBe(true);
  // The answer screen on a computer: the 480px lesson column
  expect(isWorthEnlarging(400, 1440, 900)).toBe(true);
});
