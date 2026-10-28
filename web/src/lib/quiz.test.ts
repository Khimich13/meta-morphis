import { expect, test } from 'vitest';

import type { Card } from './cards';
import { EMPTY_PROGRESS, type Progress, recordAnswer } from './progress';
import {
  afterAnswer,
  chooseLessonCards,
  isCorrect,
  isFinished,
  isFirstTry,
  LESSON_LENGTH,
  type LessonState,
  makeQuestion,
  NEW_PER_LESSON,
  OPTION_COUNT,
  type Random,
  segments,
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

const TODAY = '2026-10-15';

function start(seed: number, progress: Progress = EMPTY_PROGRESS): LessonState {
  return startLesson(CARDS, progress, TODAY, seeded(seed));
}

/** Progress in which each listed card was answered on `day` */
function answered(day: string, correct: boolean, ...cards: Card[]): Progress {
  return cards.reduce(
    (progress, card) => recordAnswer(progress, card.oracle_id, correct, day),
    EMPTY_PROGRESS,
  );
}

function ids(cards: Card[]): string[] {
  return cards.map((card) => card.oracle_id).sort();
}

test('a lesson asks about ten different cards', () => {
  for (const seed of SEEDS) {
    const lesson = start(seed);
    const asked = lesson.queue.map((question) => question.card.oracle_id);
    expect(new Set(asked).size).toBe(LESSON_LENGTH);
  }
});

test('first lessons differ from each other', () => {
  const first = start(1).queue.map((q) => q.card.oracle_id);
  const second = start(2).queue.map((q) => q.card.oracle_id);
  expect(first).not.toEqual(second);
});

test('cards due for review come first, then up to three new ones', () => {
  // Twelve cards missed today, so all due now
  const missed = CARDS.slice(0, 12);
  const chosen = chooseLessonCards(CARDS, answered(TODAY, false, ...missed), TODAY, seeded(1));
  // More due cards than room: no new cards at all
  expect(chosen.every((card) => missed.includes(card))).toBe(true);

  // Only five due: those five, three new, and two answered right but
  // not due yet - the soonest first
  const fiveDue = answered(TODAY, false, ...CARDS.slice(0, 5));
  let progress = fiveDue;
  for (const [i, card] of CARDS.slice(5, 9).entries()) {
    // Due in 1, 1, 3 and 3 days
    progress = recordAnswer(progress, card.oracle_id, true, TODAY);
    if (i >= 2) progress = recordAnswer(progress, card.oracle_id, true, '2026-10-16');
  }
  const mix = chooseLessonCards(CARDS, progress, TODAY, seeded(2));
  expect(mix).toHaveLength(LESSON_LENGTH);
  const unseen = mix.filter((card) => progress.cards[card.oracle_id] === undefined);
  expect(unseen).toHaveLength(NEW_PER_LESSON);
  expect(ids(mix.filter((card) => CARDS.slice(0, 5).includes(card)))).toEqual(
    ids(CARDS.slice(0, 5)),
  );
  // The two cards due tomorrow, not the two due in three days
  expect(ids(mix.filter((card) => CARDS.slice(5, 9).includes(card)))).toEqual(
    ids(CARDS.slice(5, 7)),
  );
});

test('the most overdue cards come first when not all fit', () => {
  let progress = EMPTY_PROGRESS;
  // Fifteen cards, each missed on a different earlier day
  for (const [i, card] of CARDS.slice(0, 15).entries()) {
    progress = recordAnswer(progress, card.oracle_id, false, `2026-10-${String(i + 1).padStart(2, '0')}`);
  }
  const chosen = chooseLessonCards(CARDS, progress, TODAY, seeded(3));
  expect(ids(chosen)).toEqual(ids(CARDS.slice(0, LESSON_LENGTH)));
});

test('with few cards seen, the lesson is filled with new ones', () => {
  const progress = answered(TODAY, true, CARDS[0], CARDS[1]);
  const chosen = chooseLessonCards(CARDS, progress, TODAY, seeded(4));
  expect(chosen).toHaveLength(LESSON_LENGTH);
  // The two seen cards are practised ahead; eight new cards fill the rest
  expect(chosen).toContain(CARDS[0]);
  expect(chosen).toContain(CARDS[1]);
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
  const lesson = startLesson(CARDS, EMPTY_PROGRESS, TODAY, seeded(1));
  expect(lesson.queue).toHaveLength(LESSON_LENGTH);
  expect(lesson.total).toBe(LESSON_LENGTH);
  expect(lesson.done).toBe(0);
  expect(lesson.score).toBe(0);
  expect(isFinished(lesson)).toBe(false);
});

test('a right answer finishes the card and counts toward the score', () => {
  const lesson = startLesson(CARDS, EMPTY_PROGRESS, TODAY, seeded(1));
  const after = afterAnswer(lesson, true, CARDS, seeded(2));

  expect(after.queue).toEqual(lesson.queue.slice(1));
  expect(after.done).toBe(1);
  expect(after.score).toBe(1);
});

test('a missed card comes back at the end as a new question', () => {
  const lesson = startLesson(CARDS, EMPTY_PROGRESS, TODAY, seeded(1));
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
  let lesson = startLesson(CARDS, EMPTY_PROGRESS, TODAY, seeded(1));
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
  let lesson = startLesson(CARDS, EMPTY_PROGRESS, TODAY, seeded(1));
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
    let lesson = startLesson(CARDS, EMPTY_PROGRESS, TODAY, random);
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

test('segments: one per card, the first one current, all to do', () => {
  const lesson = startLesson(CARDS, EMPTY_PROGRESS, TODAY, seeded(1));
  const bar = segments(lesson, null);
  expect(bar).toHaveLength(LESSON_LENGTH);
  expect(bar.every((segment) => segment.state === 'todo')).toBe(true);
  expect(bar.map((segment) => segment.current)).toEqual([true, ...Array(9).fill(false)]);
});

test('segments: an answer shows on its segment as soon as it is given', () => {
  const lesson = startLesson(CARDS, EMPTY_PROGRESS, TODAY, seeded(1));
  expect(segments(lesson, true)[0].state).toBe('right');
  expect(segments(lesson, false)[0].state).toBe('wrong');
});

test('segments: a missed card stays red until it is right on a repeat', () => {
  let lesson = startLesson(CARDS, EMPTY_PROGRESS, TODAY, seeded(1));
  lesson = afterAnswer(lesson, false, CARDS, seeded(2));
  lesson = afterAnswer(lesson, true, CARDS, seeded(3));
  let bar = segments(lesson, null);
  expect(bar.slice(0, 3).map((segment) => segment.state)).toEqual(['wrong', 'right', 'todo']);
  expect(bar[2].current).toBe(true);

  // The other eight right, which brings the missed card back on screen
  for (let i = 0; i < 8; i++) lesson = afterAnswer(lesson, true, CARDS, seeded(4));
  bar = segments(lesson, null);
  expect(bar[0]).toEqual({ state: 'wrong', current: true });
  expect(segments(lesson, true)[0].state).toBe('fixed');
  lesson = afterAnswer(lesson, true, CARDS, seeded(5));
  expect(segments(lesson, null)[0]).toEqual({ state: 'fixed', current: false });
});
