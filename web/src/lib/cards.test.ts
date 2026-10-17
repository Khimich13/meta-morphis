import { expect, test } from 'vitest';

import { listAgeDays } from './cards';

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
