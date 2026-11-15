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
    const ids = question.options.map((option) => option.card.oracle_id);
    expect(new Set(ids).size).toBe(OPTION_COUNT);
    const correct = question.options.filter((option) => isCorrect(question, option.card));
    expect(correct.map((option) => option.card)).toEqual([question.card]);
    // A card with one side is named in full
    for (const option of question.options) expect(option.name).toBe(option.card.name);
  }
});

test('the correct option is not always in the same place', () => {
  const places = new Set(
    SEEDS.map((seed) => {
      const question = makeQuestion(CARDS[0], CARDS, seeded(seed));
      return question.options.findIndex((option) => option.card === question.card);
    }),
  );
  expect(places.size).toBe(OPTION_COUNT);
});

test('a card whose name can be hidden is asked both ways', () => {
  const hideable: Card = { ...CARDS[0], name_box: [0.06, 0.045, 0.88, 0.058] };
  // Also with its name in its text box, painted over there too
  const inText: Card = { ...hideable, name_text_boxes: [[0.1, 0.7, 0.2, 0.03]] };
  for (const card of [hideable, inText]) {
    const kinds = new Set(SEEDS.map((seed) => makeQuestion(card, CARDS, seeded(seed)).kind));
    expect(kinds).toEqual(new Set(['artwork', 'picture']));
  }
});

test('a card whose name can not be hidden is asked by its artwork only', () => {
  const kinds = new Set(SEEDS.map((seed) => makeQuestion(CARDS[0], CARDS, seeded(seed)).kind));
  expect(kinds).toEqual(new Set(['artwork']));
});

function doubleFaced(n: number): Card {
  return {
    ...card(n),
    name: `Front ${n} // Back ${n}`,
    images: [`${n}.webp`, `${n}-back.webp`],
    name_box: [0.16, 0.052, 0.7, 0.051],
    back: { art: `${n}-back-art.webp`, artist: 'Some Artist', art_box: null },
  };
}

test('a double-faced card is asked by either side, named by the side asked', () => {
  const card = doubleFaced(0);
  const asked = SEEDS.map((seed) => makeQuestion(card, CARDS, seeded(seed)));
  expect(new Set(asked.map((question) => question.back))).toEqual(new Set([false, true]));
  for (const question of asked) {
    const right = question.options.find((option) => option.card === card);
    expect(right?.name).toBe(question.back ? 'Back 0' : 'Front 0');
    // The back's name isn't hidden on its picture yet: only its artwork
    if (question.back) expect(question.kind).toBe('artwork');
  }
  // The front is still asked both ways
  const front = asked.filter((question) => !question.back).map((question) => question.kind);
  expect(new Set(front)).toEqual(new Set(['artwork', 'picture']));
});

test('a double-faced card without a back to ask about is asked by its front', () => {
  const card: Card = { ...doubleFaced(0), back: null };
  for (const seed of SEEDS) expect(makeQuestion(card, CARDS, seeded(seed)).back).toBe(false);
});

test('a double-faced wrong answer is named by either side', () => {
  // So a back's name on a button never tells the right answer apart
  const others = [CARDS[0], doubleFaced(1), doubleFaced(2), doubleFaced(3)];
  const names = new Set(
    SEEDS.flatMap((seed) =>
      makeQuestion(CARDS[0], others, seeded(seed)).options.map((option) => option.name),
    ),
  );
  for (const n of [1, 2, 3]) {
    expect(names).toContain(`Front ${n}`);
    expect(names).toContain(`Back ${n}`);
  }
  expect([...names].some((name) => name.includes(' // '))).toBe(false);
});

const TODAY = '2026-10-15';
const YESTERDAY = '2026-10-14';

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
  // Twelve cards missed yesterday, so all due today
  const missed = CARDS.slice(0, 12);
  const chosen = chooseLessonCards(CARDS, answered(YESTERDAY, false, ...missed), TODAY, seeded(1));
  // More due cards than room: no new cards at all
  expect(chosen.every((card) => missed.includes(card))).toBe(true);

  // Only five due: those five, three new, and two answered right but
  // not due yet - the soonest first
  const fiveDue = answered(YESTERDAY, false, ...CARDS.slice(0, 5));
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
    progress = recordAnswer(
      progress,
      card.oracle_id,
      false,
      `2026-10-${String(i + 1).padStart(2, '0')}`,
    );
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
  expect(repeat.options.map((option) => option.card)).toContainEqual(missed);
  expect(after.done).toBe(0);
  expect(after.missed).toEqual([missed.oracle_id]);
  expect(isFirstTry(after, missed)).toBe(false);
});

test('a missed card comes back as the same kind of question', () => {
  const pictured = CARDS.map((c) => ({ ...c, name_box: [0, 0, 1, 0.1] }) as Card);
  for (const seed of SEEDS) {
    let lesson = startLesson(pictured, EMPTY_PROGRESS, TODAY, seeded(seed));
    const kind = lesson.queue[0].kind;
    // Missed again and again, it never changes kind
    for (let round = 0; round < 3; round++) {
      lesson = afterAnswer(lesson, false, pictured, seeded(seed + round));
      expect(lesson.queue[lesson.queue.length - 1].kind).toBe(kind);
      for (let i = 0; i < LESSON_LENGTH - 1; i++) {
        lesson = { ...lesson, queue: [...lesson.queue.slice(1), lesson.queue[0]] };
      }
    }
  }
});

test('a missed card comes back on the same side', () => {
  const sided = CARDS.map((_, n) => doubleFaced(n));
  for (const seed of SEEDS) {
    let lesson = startLesson(sided, EMPTY_PROGRESS, TODAY, seeded(seed));
    const back = lesson.queue[0].back;
    for (let round = 0; round < 3; round++) {
      lesson = afterAnswer(lesson, false, sided, seeded(seed + round));
      expect(lesson.queue[lesson.queue.length - 1].back).toBe(back);
      for (let i = 0; i < LESSON_LENGTH - 1; i++) {
        lesson = { ...lesson, queue: [...lesson.queue.slice(1), lesson.queue[0]] };
      }
    }
  }
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
