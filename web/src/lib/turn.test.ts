import { expect, test } from 'vitest';

import { turnStart } from './turn';

test('an upright card shrinks back from its old size', () => {
  // Upright phone 358px wide, sideways phone 262px wide
  const scale = turnStart(
    { width: 358, turned: false },
    { width: 262, turned: false },
  );
  expect(scale).toBeCloseTo(358 / 262);
});

test('a card printed sideways is not animated when it turns', () => {
  // Sideways on an upright phone; turned, in a landscape box, on a sideways one
  const sideways = { width: 358, turned: false };
  const turned = { width: 510, turned: true };
  expect(turnStart(sideways, turned)).toBe(1);
  expect(turnStart(turned, sideways)).toBe(1);
});

test('a card with no size yet is drawn as it is', () => {
  const scale = turnStart({ width: 300, turned: false }, { width: 0, turned: false });
  expect(scale).toBe(1);
});
