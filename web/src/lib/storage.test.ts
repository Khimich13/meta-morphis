import { afterEach, expect, test, vi } from 'vitest';

import { loadSoundsOn, saveSoundsOn } from './storage';

/** A stand-in for the browser's localStorage */
function fakeStorage() {
  const values = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test('sounds are on until the player turns them off', () => {
  fakeStorage();
  expect(loadSoundsOn()).toBe(true);
  saveSoundsOn(false);
  expect(loadSoundsOn()).toBe(false);
  saveSoundsOn(true);
  expect(loadSoundsOn()).toBe(true);
});

test('sounds are on when storage is switched off', () => {
  vi.stubGlobal('localStorage', {
    getItem: () => {
      throw new Error('storage is off');
    },
  });
  expect(loadSoundsOn()).toBe(true);
});
