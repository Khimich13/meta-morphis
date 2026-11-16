import { afterEach, expect, test, vi } from 'vitest';

import { newList } from './customLists';
import {
  loadColumns,
  loadCustomLists,
  loadOpenList,
  loadSoundsOn,
  saveColumns,
  saveCustomLists,
  saveOpenList,
  saveSoundsOn,
} from './storage';

/** A stand-in for the browser's localStorage */
function fakeStorage() {
  const values = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  });
  return values;
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

test('custom lists are saved and read back', () => {
  fakeStorage();
  expect(loadCustomLists()).toEqual([]);
  const list = newList('Burn');
  expect(saveCustomLists([list])).toBe(true);
  expect(loadCustomLists()).toEqual([list]);
});

test('unreadable saved lists are passed over', () => {
  const values = fakeStorage();
  values.set('meta-morphis-custom-lists', 'not json');
  expect(loadCustomLists()).toEqual([]);
  values.set('meta-morphis-custom-lists', JSON.stringify([{ id: 'a' }, newList('Burn')]));
  expect(loadCustomLists().map((list) => list.name)).toEqual(['Burn']);
});

test('saving reports full storage', () => {
  vi.stubGlobal('localStorage', {
    setItem: () => {
      throw new Error('quota exceeded');
    },
  });
  expect(saveCustomLists([newList('Burn')])).toBe(false);
});

test('the open list is remembered until a format is chosen', () => {
  fakeStorage();
  expect(loadOpenList()).toBeNull();
  saveOpenList('abc');
  expect(loadOpenList()).toBe('abc');
  saveOpenList(null);
  expect(loadOpenList()).toBeNull();
});
