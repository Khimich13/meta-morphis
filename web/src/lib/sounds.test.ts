import { expect, test } from 'vitest';

import { answerNotes } from './sounds';

/** The main pitch at each moment a pluck starts: its lowest note */
function plucks(correct: boolean): number[] {
  const notes = answerNotes(correct);
  const starts = [...new Set(notes.map((note) => note.start))].sort((a, b) => a - b);
  return starts.map((start) =>
    Math.min(...notes.filter((note) => note.start === start).map((note) => note.pitch)),
  );
}

test('a right answer is three plucks, each higher', () => {
  const [first, second, third] = plucks(true);
  expect(plucks(true)).toHaveLength(3);
  expect(second).toBeGreaterThan(first);
  expect(third).toBeGreaterThan(second);
});

test('a wrong answer is one pluck, lower than the right ones', () => {
  expect(plucks(false)).toHaveLength(1);
  expect(plucks(false)[0]).toBeLessThan(plucks(true)[0]);
});

test('every sound is short and not too loud', () => {
  for (const note of [...answerNotes(true), ...answerNotes(false)]) {
    expect(note.start + note.duration).toBeLessThanOrEqual(0.45);
    expect(note.volume).toBeLessThanOrEqual(0.3);
  }
});
