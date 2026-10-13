import { expect, test } from 'vitest';

import type { Card } from './cards';
import {
  isCorrect,
  LESSON_LENGTH,
  makeLesson,
  makeQuestion,
  OPTION_COUNT,
  type Random,
  shuffle,
} from './quiz';

function card(n: number): Card {
  return {
    oracle_id: `id-${n}`,
    name: `Card ${n}`,
    images: [`${n}.webp`],
    art: `${n}-art.webp`,
    artist: 'Some Artist',
  };
}

const CARDS = Array.from({ length: 50 }, (_, n) => card(n));

// Random numbers that are the same on every run for the same seed,
// so a failing test fails every time
function seeded(seed: number): Random {
  let state = seed;
  return () => {
    state = (state * 1664525 + 1013904223) % 4294967296;
    return state / 4294967296;
  };
}

const SEEDS = Array.from({ length: 200 }, (_, n) => n + 1);

test('shuffle keeps every item and leaves the original alone', () => {
  const original = [1, 2, 3, 4, 5];
  const shuffled = shuffle(original, seeded(1));

  expect(original).toEqual([1, 2, 3, 4, 5]);
  expect([...shuffled].sort()).toEqual([1, 2, 3, 4, 5]);
});

test('a question has four different options and exactly one is correct', () => {
  for (const seed of SEEDS) {
    const question = makeQuestion(CARDS[seed % CARDS.length], CARDS, seeded(seed));

    expect(question.options).toHaveLength(OPTION_COUNT);
    const ids = question.options.map((option) => option.oracle_id);
    expect(new Set(ids).size).toBe(OPTION_COUNT);
    const correct = question.options.filter((option) => isCorrect(question, option));
    expect(correct).toEqual([question.card]);
  }
});

test('the correct option is not always in the same place', () => {
  const places = new Set(
    SEEDS.map((seed) => {
      const question = makeQuestion(CARDS[0], CARDS, seeded(seed));
      return question.options.indexOf(question.card);
    }),
  );
  expect(places.size).toBe(OPTION_COUNT);
});

test('a lesson asks about ten different cards', () => {
  for (const seed of SEEDS) {
    const lesson = makeLesson(CARDS, seeded(seed));

    expect(lesson).toHaveLength(LESSON_LENGTH);
    const asked = lesson.map((question) => question.card.oracle_id);
    expect(new Set(asked).size).toBe(LESSON_LENGTH);
  }
});

test('lessons differ from each other', () => {
  const first = makeLesson(CARDS, seeded(1)).map((q) => q.card.oracle_id);
  const second = makeLesson(CARDS, seeded(2)).map((q) => q.card.oracle_id);
  expect(first).not.toEqual(second);
});

test('isCorrect compares cards by id', () => {
  const question = makeQuestion(CARDS[0], CARDS, seeded(1));
  expect(isCorrect(question, { ...CARDS[0] })).toBe(true);
  expect(isCorrect(question, CARDS[1])).toBe(false);
});
