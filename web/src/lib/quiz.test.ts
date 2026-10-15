import { expect, test } from 'vitest';

import type { Card } from './cards';
import {
  afterAnswer,
  isCorrect,
  isFinished,
  isFirstTry,
  LESSON_LENGTH,
  type LessonState,
  makeLesson,
  makeQuestion,
  OPTION_COUNT,
  type Random,
  shuffle,
  startLesson,
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

function onScreen(lesson: LessonState): Card {
  return lesson.queue[0].card;
}

test('a new lesson has ten cards to do and nothing done yet', () => {
  const lesson = startLesson(CARDS, seeded(1));
  expect(lesson.queue).toHaveLength(LESSON_LENGTH);
  expect(lesson.total).toBe(LESSON_LENGTH);
  expect(lesson.done).toBe(0);
  expect(lesson.score).toBe(0);
  expect(isFinished(lesson)).toBe(false);
});

test('a right answer finishes the card and counts toward the score', () => {
  const lesson = startLesson(CARDS, seeded(1));
  const after = afterAnswer(lesson, true, CARDS, seeded(2));

  expect(after.queue).toEqual(lesson.queue.slice(1));
  expect(after.done).toBe(1);
  expect(after.score).toBe(1);
});

test('a missed card comes back at the end as a new question', () => {
  const lesson = startLesson(CARDS, seeded(1));
  const missed = onScreen(lesson);
  const after = afterAnswer(lesson, false, CARDS, seeded(2));

  // Still ten questions: the other nine, then the missed card again
  expect(after.queue).toHaveLength(LESSON_LENGTH);
  expect(after.queue.slice(0, -1)).toEqual(lesson.queue.slice(1));
  const repeat = after.queue[after.queue.length - 1];
  expect(repeat.card).toEqual(missed);
  expect(repeat.options).toHaveLength(OPTION_COUNT);
  expect(repeat.options).toContainEqual(missed);
  expect(after.done).toBe(0);
  expect(after.missed).toEqual([missed.oracle_id]);
  expect(isFirstTry(after, missed)).toBe(false);
});

test('a card right only on a repeat does not count toward the score', () => {
  let lesson = startLesson(CARDS, seeded(1));
  const card = onScreen(lesson);
  lesson = afterAnswer(lesson, false, CARDS, seeded(2));
  // Answer the other nine right, which brings the missed card back
  for (let i = 0; i < LESSON_LENGTH - 1; i++) {
    lesson = afterAnswer(lesson, true, CARDS, seeded(3));
  }
  expect(onScreen(lesson)).toEqual(card);
  lesson = afterAnswer(lesson, true, CARDS, seeded(4));

  expect(isFinished(lesson)).toBe(true);
  expect(lesson.done).toBe(LESSON_LENGTH);
  expect(lesson.score).toBe(LESSON_LENGTH - 1);
});

test('a card keeps coming back until it is answered right', () => {
  let lesson = startLesson(CARDS, seeded(1));
  const card = onScreen(lesson);
  // Miss it, then answer everything else right, three times over
  for (let round = 0; round < 3; round++) {
    lesson = afterAnswer(lesson, false, CARDS, seeded(round + 2));
    while (onScreen(lesson).oracle_id !== card.oracle_id) {
      lesson = afterAnswer(lesson, true, CARDS, seeded(round + 5));
    }
  }
  expect(isFinished(lesson)).toBe(false);
  expect(lesson.missed).toEqual([card.oracle_id]);

  lesson = afterAnswer(lesson, true, CARDS, seeded(9));
  expect(isFinished(lesson)).toBe(true);
});

test('any mix of answers ends with every card done', () => {
  for (const seed of SEEDS) {
    const random = seeded(seed);
    let lesson = startLesson(CARDS, random);
    let steps = 0;
    while (!isFinished(lesson)) {
      // Wrong about a third of the time
      lesson = afterAnswer(lesson, random() > 0.33, CARDS, random);
      steps += 1;
      expect(steps).toBeLessThan(1000);
    }
    expect(lesson.done).toBe(LESSON_LENGTH);
    expect(lesson.score).toBe(LESSON_LENGTH - lesson.missed.length);
  }
});
