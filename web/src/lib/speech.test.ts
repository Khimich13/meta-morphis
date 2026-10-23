import { expect, test } from 'vitest';

import { spokenName } from './speech';

test('a single name is said as it is written', () => {
  expect(spokenName('Lightning Bolt')).toBe('Lightning Bolt');
});

test('a double-faced card is said as two names with a pause', () => {
  expect(spokenName('Fable of the Mirror-Breaker // Reflection of Kiki-Jiki')).toBe(
    'Fable of the Mirror-Breaker, Reflection of Kiki-Jiki',
  );
});
