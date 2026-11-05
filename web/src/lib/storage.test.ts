import { afterEach, expect, test, vi } from 'vitest';

import { loadColumns, loadSoundsOn, saveColumns, saveSoundsOn } from './storage';

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

test('upright and sideways keep their own number of columns', () => {
  fakeStorage();
  expect(loadColumns(false)).toBeNull();
  expect(loadColumns(true)).toBeNull();
  saveColumns(2, false);
  saveColumns(5, true);
  expect(loadColumns(false)).toBe(2);
  expect(loadColumns(true)).toBe(5);
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
