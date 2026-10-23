import { expect, test } from 'vitest';

import {
  FIRST_FORMAT,
  kindFor,
  listFile,
  listsOf,
  startFormat,
  selectionLabel,
  startKind,
} from './formats';

test('a saved choice is used', () => {
  expect(startFormat('modern', true)).toBe('modern');
  expect(startFormat('modern', false)).toBe('modern');
});

test('a player with progress from before formats existed gets Pauper', () => {
  expect(startFormat(null, true)).toBe(FIRST_FORMAT);
});

test('a new player chooses', () => {
  expect(startFormat(null, false)).toBeNull();
});

test('a list file is named like the exporter names it', () => {
  expect(listFile({ format: 'pauper', kind: 'all' })).toBe('pauper');
  expect(listFile({ format: 'pauper', kind: 'creatures' })).toBe('pauper-creatures');
});

test('listsOf gives a format\'s lists in a fixed order', () => {
  const file = { formats: ['pauper'], lists: { pauper: ['lands', 'all', 'creatures'] } };
  expect(listsOf(file, 'pauper')).toEqual(['all', 'creatures', 'lands']);
});

test('an older formats.json without lists offers the overall list only', () => {
  expect(listsOf({ formats: ['pauper'] }, 'pauper')).toEqual(['all']);
});

test('a saved list kind is used only if the app knows it', () => {
  expect(startKind('lands')).toBe('lands');
  expect(startKind(null)).toBe('all');
  expect(startKind('artifacts')).toBe('all');
});

test('a kind the format lacks falls back to its overall list', () => {
  expect(kindFor('lands', ['all', 'lands'])).toBe('lands');
  expect(kindFor('lands', ['all', 'creatures'])).toBe('all');
});

test('a selection is named for the screen', () => {
  expect(selectionLabel({ format: 'pauper', kind: 'all' })).toBe('Pauper');
  expect(selectionLabel({ format: 'pauper', kind: 'lands' })).toBe('Pauper lands');
});
